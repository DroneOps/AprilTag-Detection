#!/usr/bin/env python3
"""Primer vuelo: despegar, mantenerse con send_rc_control, aterrizar y paro.

Uso:
    python scripts/first_flight.py                    # despega, se mantiene, aterriza
    python scripts/first_flight.py --yaw-test 90      # además gira 90° por rc en lazo cerrado
    python scripts/first_flight.py --flip-test b      # además un flip hacia atrás (f, b, l, r)
    python scripts/first_flight.py --record vuelo1.mp4

Controles (con la ventana enfocada):
    t                       despegar (solo si el chequeo previo está en verde)
    ESPACIO, ENTER, l, ESC  PARO: aterrizaje forzoso   (también clic en la barra roja)
    k                       MATAR MOTORES: el dron CAE. Último recurso.
    q                       salir (en el aire equivale a PARO)

Parámetros en config/flight.json. Bitácora CSV en logs/.

Diseño: el hilo de control manda rc continuamente a rc_hz. Despegue y
aterrizaje se mandan sin esperar respuesta y se CONFIRMAN por telemetría
(altura), porque djitellopy empareja respuestas sin saber a qué comando
pertenecen. El paro no pasa por el lazo de control: solo levanta una
bandera que el lazo atiende en el siguiente ciclo (≤ 50 ms).
"""
from __future__ import annotations

import argparse
import csv
import json
import logging
import math
import threading
import time
from dataclasses import dataclass, fields
from pathlib import Path

import cv2
import numpy as np

from test_tags import hud

ROOT = Path(__file__).resolve().parent.parent
AIRBORNE = {"TAKEOFF", "HOVER", "YAW_TEST", "FLIP_CLIMB", "FLIP_TEST", "FLIP_RECOVER"}
LANDING = {"LANDING", "EMERGENCY_LAND"}
TERMINAL = {"DONE", "KILLED", "ABORTED"}


@dataclass
class FlightConfig:
    rc_hz: float = 20.0
    rc_limit: int = 20  # adelante/atrás y lados (rc 20 ≈ 20–28 cm/s medido)
    ud_limit: int = 40  # vertical aparte: el Tello sube lento (rc 20 ≈ 5–14 cm/s medido)
    hover_s: float = 10.0
    max_flight_s: float = 60.0
    takeoff_timeout_s: float = 10.0
    takeoff_min_height_cm: int = 30
    takeoff_settle_s: float = 2.0  # el Tello reporta h en pasos de 10 cm: ventana corta da falsos 'estable'
    takeoff_settle_cm: int = 8  # tof oscila ±3–4 cm en estacionario
    land_timeout_s: float = 10.0
    land_resend_s: float = 1.5
    landed_height_cm: int = 10
    battery_min_takeoff: int = 30
    battery_land: int = 15
    temp_max_takeoff_c: int = 80
    temp_land_c: int = 90
    video_hover_s: float = 0.3
    video_land_s: float = 3.0
    state_lost_s: float = 1.0
    yaw_kp: float = 2.0
    yaw_rate_limit: int = 60
    yaw_min_rate: int = 20  # rc 10 casi no gira (zona muerta medida)
    yaw_tol_deg: float = 3.0
    yaw_timeout_s: float = 10.0
    flip_min_battery: int = 50  # el Tello rechaza flips con poca carga
    flip_min_alt_cm: float = 130.0  # tras un flip el Tello cae 30–80 cm (medido): voltear con margen
    flip_hold_s: float = 3.0  # tras el flip: no bajar en este tiempo (sigue cayendo) y sostener altura
    flip_min_s: float = 1.0  # mínimo antes de dar la vuelta por terminada
    flip_wait_s: float = 3.0  # máximo sin rc esperando que termine la vuelta
    flip_settle_deg: float = 15.0  # nivelado de nuevo = vuelta terminada
    alt_kp: float = 1.0  # control de altura (subir antes del flip, recuperar después)
    alt_min: int = 15
    alt_max: int = 40
    alt_tol_cm: float = 5.0
    alt_timeout_s: float = 12.0
    floor_alt_cm: float = 3.0  # en el aire pero con esta altura por 1 s = en el piso

    @classmethod
    def load(cls, path: Path) -> FlightConfig:
        data = json.loads(path.read_text()) if path.exists() else {}
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise SystemExit(f"{path}: claves desconocidas {sorted(unknown)}")
        return cls(**data)


class Telemetry:
    """Estado UDP del Tello (~10 Hz) y su edad.

    djitellopy reemplaza el dict de estado en cada paquete; si el objeto
    cambió, llegó un paquete nuevo.
    """

    def __init__(self, tello) -> None:
        self._udp = tello.get_own_udp_object()
        self._last: dict | None = None
        self._t = -math.inf

    def snapshot(self) -> tuple[dict, float]:
        s = self._udp["state"]
        now = time.monotonic()
        if not s:  # djitellopy arranca con un dict vacío: aún no llega nada
            return {}, math.inf
        if s is not self._last:
            self._last, self._t = s, now
        return s or {}, now - self._t


def altitude(s: dict) -> int:
    """Altura sobre el piso en cm, por el sensor tof (en tierra marca ~10).

    'h' del Tello deriva: en vuelos reales marcó 10 cm volando a 76 y -30 en el
    piso. tof fuera de rango (>1000) cae a 'h' como respaldo.
    """
    tof = s.get("tof", 0)
    return tof - 10 if 0 < tof < 1000 else s.get("h", 0)


def wrap_deg(a: float) -> float:
    return (a + 180.0) % 360.0 - 180.0


def clamp(v: float, lim: float) -> int:
    return int(max(-lim, min(lim, v)))


def with_min(value: float, minimum: float, limit: float) -> int:
    """P con piso: el Tello no se mueve con rc pequeños (zona muerta)."""
    if value == 0:
        return 0
    return clamp(math.copysign(max(abs(value), minimum), value), limit)


class Flight:
    """Máquina de estados del vuelo. Corre en su propio hilo (run).

    Una misión hereda de aquí y usa los ganchos: AIRBORNE_STATES, _hover_done,
    _extra_step, on_frame, overlay y status_lines. Paro, vigilantes, despegue y
    aterrizaje se quedan en esta clase.
    """

    AIRBORNE_STATES = AIRBORNE
    LOG_EXTRA: list[str] = []  # columnas extra de la bitácora (ver _log_extra)

    def __init__(self, tello, cfg: FlightConfig, log_path: Path, yaw_test: float | None,
                 flip_test: str | None = None) -> None:
        self.t = tello
        self.cfg = cfg
        self.tel = Telemetry(tello)
        self.yaw_test = yaw_test
        self.flip_test = flip_test
        self._flip_done = False
        self._flip_peak = 0.0
        self._flip_alt_min = math.inf
        self._flip_ref_alt = 0.0  # altura a la que se regresa después del flip
        self._t_level: float | None = None
        self._t_floor: float | None = None
        self._recover_min = math.inf
        self.state = "IDLE"
        self.reason = "esperando despegue (t)"
        self.rc = (0, 0, 0, 0)
        self.video_age = math.inf  # lo actualiza la HMI
        self._lock = threading.Lock()
        self._takeoff_req = threading.Event()
        self._land_req: str | None = None
        self._kill_req = threading.Event()
        self._stop = threading.Event()
        self._t_state = time.monotonic()
        self._t_air: float | None = None
        self._t_land_sent = 0.0
        self._h_at_land_sent = math.inf
        self._t_low: float | None = None
        self._t_on_target: float | None = None
        self._takeoff_h: list[tuple[float, int]] = []
        self._yaw_target = 0.0
        self._yaw_done = False
        log_path.parent.mkdir(exist_ok=True)
        self._log_file = log_path.open("w", newline="", buffering=1)  # por línea: sobrevive a un cierre brusco
        self._log = csv.writer(self._log_file)
        self._log.writerow(["t", "state", "bat", "h", "tof", "yaw", "pitch", "roll", "temph",
                            "rc_lr", "rc_fb", "rc_ud", "rc_yaw", "state_age", "video_age", "reason",
                            "vgx", "vgy", "vgz", *self.LOG_EXTRA])
        self._t0 = time.monotonic()

    # ------------------------------------------------ API para la HMI

    def preflight(self) -> list[tuple[str, bool]]:
        s, age = self.tel.snapshot()
        bat, temp = s.get("bat", 0), s.get("temph", 0)
        return [
            (f"telemetria ({age:.1f} s)", age < self.cfg.state_lost_s),
            (f"video ({self.video_age:.1f} s)", self.video_age < 1.0),
            (f"bateria {bat}% >= {self.cfg.battery_min_takeoff}%", bat >= self.cfg.battery_min_takeoff),
            (f"temperatura {temp} C < {self.cfg.temp_max_takeoff_c} C", temp < self.cfg.temp_max_takeoff_c),
        ]

    def request_takeoff(self) -> None:
        if self.state != "IDLE":
            return
        failed = [name for name, ok in self.preflight() if not ok]
        if failed:
            self.reason = "NO despega: " + "; ".join(failed)
        else:
            self._takeoff_req.set()

    def request_land(self, reason: str) -> None:
        with self._lock:
            if self._land_req is None:
                self._land_req = reason

    def request_kill(self) -> None:
        self._kill_req.set()

    @property
    def airborne(self) -> bool:
        return self.state in self.AIRBORNE_STATES | LANDING

    def stop(self) -> None:
        self._stop.set()

    # ------------------------------------------------ lazo de control

    def run(self) -> None:
        period = 1.0 / self.cfg.rc_hz
        try:
            while not self._stop.is_set():
                t0 = time.monotonic()
                try:
                    self._step()
                except Exception as e:  # ninguna excepción mata el lazo: se aterriza
                    self.reason = f"excepcion: {e!r}"
                    try:
                        if self.state in self.AIRBORNE_STATES:
                            self._begin_landing("EMERGENCY_LAND", self.reason)
                    except Exception:
                        pass
                time.sleep(max(0.0, period - (time.monotonic() - t0)))
        finally:
            self._log_file.close()

    def _goto(self, state: str, reason: str) -> None:
        self.state, self.reason = state, reason
        self._t_state = time.monotonic()
        print(f"[vuelo] {state}: {reason}")

    def _send_rc(self, lr: float, fb: float, ud: float, yaw: float) -> None:
        lim = self.cfg.rc_limit
        self.rc = (clamp(lr, lim), clamp(fb, lim), clamp(ud, self.cfg.ud_limit), clamp(yaw, self.cfg.yaw_rate_limit))
        self.t.send_rc_control(*self.rc)

    def _begin_landing(self, state: str, reason: str) -> None:
        # 'land' primero y el estado después: si algo más falla, el aterrizaje ya salió
        self.t.send_command_without_return("land")
        self._t_land_sent = time.monotonic()
        self._h_at_land_sent = math.inf
        self._t_low = None
        self._goto(state, reason)
        self.rc = (0, 0, 0, 0)
        try:
            self.t.send_rc_control(0, 0, 0, 0)
        except Exception:
            pass

    def _step(self) -> None:
        cfg, now = self.cfg, time.monotonic()
        s, state_age = self.tel.snapshot()
        h, bat, temp, yaw = altitude(s), s.get("bat", 0), s.get("temph", 0), s.get("yaw", 0)
        self._log.writerow([f"{now - self._t0:.3f}", self.state, bat, s.get("h", ""), s.get("tof", ""), yaw,
                            s.get("pitch", ""), s.get("roll", ""), temp, *self.rc,
                            f"{state_age:.2f}", f"{self.video_age:.2f}", self.reason,
                            s.get("vgx", ""), s.get("vgy", ""), s.get("vgz", ""), *self._log_extra()])

        if self._kill_req.is_set() and self.state != "KILLED":
            for _ in range(3):
                self.t.send_command_without_return("emergency")
            self.t.is_flying = False
            self.rc = (0, 0, 0, 0)
            self._goto("KILLED", "motores apagados por el usuario")
            return

        st = self.state
        if st == "IDLE":
            if self._takeoff_req.is_set():
                self._takeoff_req.clear()
                self.t.send_command_without_return("takeoff")
                self._takeoff_h = []
                self._goto("TAKEOFF", "despegando")
            return
        if st in TERMINAL:
            return

        # ---- en el aire: paro y vigilantes (en orden de prioridad)
        if st in self.AIRBORNE_STATES:
            with self._lock:
                land_req = self._land_req
            if land_req:
                return self._begin_landing("EMERGENCY_LAND", land_req)
            if state_age > cfg.state_lost_s:
                return self._begin_landing("EMERGENCY_LAND", f"telemetria perdida {state_age:.1f} s")
            if 0 < bat < cfg.battery_land:
                return self._begin_landing("EMERGENCY_LAND", f"bateria baja {bat}%")
            if temp >= cfg.temp_land_c:
                return self._begin_landing("EMERGENCY_LAND", f"temperatura {temp} C")
            if self.video_age > cfg.video_land_s:
                return self._begin_landing("EMERGENCY_LAND", f"sin video {self.video_age:.1f} s")
            if st != "TAKEOFF" and 0 < s.get("tof", 0) < 1000 and h <= cfg.floor_alt_cm:
                self._t_floor = self._t_floor or now  # p. ej. se hundió tras un flip
                if now - self._t_floor > 1.0:
                    return self._begin_landing("EMERGENCY_LAND", "dron en el piso sin pedirlo")
            else:
                self._t_floor = None
            if self._t_air is not None and now - self._t_air > cfg.max_flight_s:
                return self._begin_landing("EMERGENCY_LAND", "tiempo maximo de vuelo")

        elapsed = now - self._t_state
        if st == "TAKEOFF":
            # El despegue automático sigue subiendo ~6 s después de pasar 30 cm; mandar
            # rc antes lo interrumpe. Sin rc hasta que la altura se estabilice.
            self._takeoff_h.append((now, h))
            while self._takeoff_h and now - self._takeoff_h[0][0] > cfg.takeoff_settle_s:
                self._takeoff_h.pop(0)
            hs = [x for _, x in self._takeoff_h]
            settled = elapsed > cfg.takeoff_settle_s and max(hs) - min(hs) <= cfg.takeoff_settle_cm
            if h >= cfg.takeoff_min_height_cm and (settled or elapsed > cfg.takeoff_timeout_s):
                self._t_air = now
                self.t.is_flying = True  # Tello.end() aterriza si esto queda en True
                how = "estable" if settled else "sin estabilizar"
                self._goto("HOVER", f"en el aire a {h} cm ({how}, despegue {elapsed:.1f} s)")
            elif elapsed > cfg.takeoff_timeout_s:
                self._begin_landing("EMERGENCY_LAND", f"no subio ({h} cm en {elapsed:.0f} s)")

        elif st == "HOVER":
            self._send_rc(0, 0, 0, 0)
            duration = 3.0 if self._yaw_done or self._flip_done else cfg.hover_s
            if elapsed >= duration:
                self._hover_done(yaw)

        elif st == "YAW_TEST":
            err = wrap_deg(self._yaw_target - yaw)
            rate = cfg.yaw_kp * err
            if abs(rate) < cfg.yaw_min_rate:  # zona muerta del Tello
                rate = math.copysign(cfg.yaw_min_rate, err)
            if abs(err) <= cfg.yaw_tol_deg:
                rate = 0
                self._t_on_target = self._t_on_target or now
            else:
                self._t_on_target = None
            if self.video_age > cfg.video_hover_s:  # sin video fresco: quieto
                rate = 0
            self._send_rc(0, 0, 0, rate)
            if self._t_on_target is not None and now - self._t_on_target > 0.5:
                self._yaw_done = True
                self._goto("HOVER", f"giro completado (error {err:+.0f} grados)")
            elif elapsed > cfg.yaw_timeout_s:
                self._yaw_done = True
                self._goto("HOVER", f"giro NO completado en {cfg.yaw_timeout_s:.0f} s (error {err:+.0f})")

        elif st == "FLIP_CLIMB":
            ud, high_enough = self._flip_climb_rc(s)
            self._send_rc(0, 0, ud, 0)
            if self._held_alt(high_enough, now, 0.3):
                self._start_flip(self.flip_test)
                self._goto("FLIP_TEST", f"flip {self.flip_test} a {h} cm")
            elif elapsed > cfg.alt_timeout_s:
                self._flip_done = True
                self._goto("HOVER", f"flip omitido: no alcanzo {cfg.flip_min_alt_cm:.0f} cm (esta a {h})")

        elif st == "FLIP_TEST":
            self._flip_progress(s)
            if self._flip_finished(s, now, elapsed):
                self._recover_min, self._t_on_target = math.inf, None
                self._goto("FLIP_RECOVER", self._flip_result())

        elif st == "FLIP_RECOVER":
            # el Tello se hunde tras el flip: corregir en cuanto termina la vuelta,
            # sin bajar mientras sigue cayendo, y solo dar por buena una altura estable
            ud, on_goal = self._recover_rc(self._flip_ref_alt, s, elapsed)
            self._send_rc(0, 0, ud, 0)
            stable = self._held_alt(on_goal, now, 1.0) and elapsed >= cfg.flip_hold_s
            if stable or elapsed > cfg.alt_timeout_s:
                self._flip_done = True
                self._goto("HOVER", f"altura recuperada: {h} cm, minima {self._recover_min:.0f} cm ({self.reason})")
            self._recover_min = min(self._recover_min, h)

        elif st in LANDING:
            if h <= cfg.landed_height_cm:
                self._t_low = self._t_low or now
                if now - self._t_low > 1.5:
                    self.t.is_flying = False
                    self._goto("DONE", f"aterrizado ({self.reason})")
            else:
                self._t_low = None
                if now - self._t_land_sent > cfg.land_resend_s:
                    # si no bajó desde el último 'land', se perdió: reenviar
                    if h >= self._h_at_land_sent - 5:
                        self.t.send_command_without_return("land")
                    self._t_land_sent, self._h_at_land_sent = now, h
                if elapsed > cfg.land_timeout_s:
                    self.reason = f"aterrizaje sin confirmar ({h} cm), reenviando land"

        else:
            self._extra_step(st, s, now, elapsed)

    # ------------------------------------------------ ganchos para misiones

    def _hover_done(self, yaw: float) -> None:
        """Al terminar el estacionario: giro de prueba, flip de prueba o aterrizar."""
        if self.yaw_test and not self._yaw_done:
            self._yaw_target = wrap_deg(yaw + self.yaw_test)
            self._t_on_target = None
            self._goto("YAW_TEST", f"girando {self.yaw_test:+.0f} grados hacia {self._yaw_target:.0f}")
        elif self.flip_test and not self._flip_done:
            bat = self.tel.snapshot()[0].get("bat", 0)
            if bat < self.cfg.flip_min_battery:
                self._begin_landing("LANDING", f"flip no permitido: bateria {bat}% < {self.cfg.flip_min_battery}%")
            else:
                self._flip_ref_alt = altitude(self.tel.snapshot()[0])
                self._t_on_target = None
                self._goto("FLIP_CLIMB", f"subiendo a {self.cfg.flip_min_alt_cm:.0f} cm para el flip")
        else:
            self._begin_landing("LANDING", "fin de la prueba")

    # ------------------------------------------------ flip verificado

    def _alt_rc(self, target: float, s: dict) -> tuple[int, bool]:
        """rc vertical para llegar a una altura (cm sobre el piso, por tof)."""
        c = self.cfg
        err = target - altitude(s)
        on_goal = abs(err) <= c.alt_tol_cm
        return (0 if on_goal else with_min(c.alt_kp * err, c.alt_min, c.alt_max)), on_goal

    def _held_alt(self, on_goal: bool, now: float, hold: float = 0.5) -> bool:
        """En la altura objetivo durante `hold` s seguidos."""
        if not on_goal:
            self._t_on_target = None
            return False
        self._t_on_target = self._t_on_target or now
        return now - self._t_on_target >= hold

    def _flip_climb_rc(self, s: dict) -> tuple[int, bool]:
        """Subir para el flip. Basta con estar en o arriba de flip_min_alt_cm: pasarse un
        poco no importa, y esperar a clavar la altura con rc pequeños tardaba demasiado."""
        c = self.cfg
        ud, _ = self._alt_rc(c.flip_min_alt_cm + 5, s)
        return ud, altitude(s) >= c.flip_min_alt_cm - c.alt_tol_cm

    def _recover_rc(self, target: float, s: dict, since_flip: float) -> tuple[int, bool]:
        """Tras el flip: hacia la altura objetivo, pero sin bajar durante flip_hold_s.
        En una prueba real, al terminar la vuelta estaba a 80 cm *cayendo*; como el
        objetivo era 74, se dio por recuperado y siguió cayendo hasta 39 cm."""
        ud, on_goal = self._alt_rc(target, s)
        if since_flip < self.cfg.flip_hold_s:
            ud = max(ud, 0)
        return ud, on_goal

    def _start_flip(self, direction: str) -> None:
        """Manda el flip. Se vacían las respuestas viejas para poder leer la suya."""
        self._send_rc(0, 0, 0, 0)
        self.t.get_own_udp_object()["responses"].clear()
        self.t.send_command_without_return(f"flip {direction}")
        self._flip_peak, self._flip_alt_min, self._t_level = 0.0, math.inf, None

    def _flip_finished(self, s: dict, now: float, elapsed: float) -> bool:
        """La vuelta terminó: ya hubo inclinación grande y volvió a nivel 0.3 s.
        Si nunca se inclinó (flip rechazado), se espera hasta flip_wait_s."""
        c = self.cfg
        level = abs(s.get("pitch", 0)) <= c.flip_settle_deg and abs(s.get("roll", 0)) <= c.flip_settle_deg
        if self._flip_peak >= 60 and level and elapsed >= c.flip_min_s:
            self._t_level = self._t_level or now
            if now - self._t_level >= 0.3:
                return True
        else:
            self._t_level = None
        return elapsed > c.flip_wait_s

    def _flip_progress(self, s: dict) -> None:
        """Mientras voltea: sin rc; se registra la inclinación máxima y la altura mínima."""
        self._flip_peak = max(self._flip_peak, abs(s.get("pitch", 0)), abs(s.get("roll", 0)))
        self._flip_alt_min = min(self._flip_alt_min, altitude(s))

    def _flip_result(self) -> str:
        """El 'ok' no basta (respuestas desfasadas): se confirma por la telemetría."""
        resp = [r.decode(errors="replace").strip() if isinstance(r, bytes) else str(r)
                for r in list(self.t.get_own_udp_object()["responses"])]
        done = self._flip_peak >= 60
        text = (f"flip {'HECHO' if done else 'NO detectado'}: inclinacion max {self._flip_peak:.0f} grados, "
                f"altura min {self._flip_alt_min:.0f} cm, respuesta {resp or 'ninguna'}")
        print(f"[vuelo] {text}")
        return text

    def _extra_step(self, st: str, s: dict, now: float, elapsed: float) -> None:
        """Estados propios de una misión."""

    def on_frame(self, bgr: np.ndarray, t: float) -> None:
        """Cada frame nuevo de video (hilo de la HMI)."""

    def overlay(self, img: np.ndarray) -> None:
        """Dibujo extra sobre el video de la HMI."""

    def status_lines(self) -> list[str]:
        return []

    def _log_extra(self) -> list:
        return []


# ---------------------------------------------------------------- HMI

class Hmi:
    BAR_H = 70

    def __init__(self, flight: Flight, title: str = "primer vuelo") -> None:
        self.flight = flight
        self.title = title
        self.size = (960, 720)
        cv2.namedWindow(title, cv2.WINDOW_AUTOSIZE)
        cv2.setMouseCallback(title, self._on_mouse)

    def _on_mouse(self, event, x, y, flags, param) -> None:
        if event == cv2.EVENT_LBUTTONDOWN and y >= self.size[1] - self.BAR_H:
            self.flight.request_land("PARO: boton (mouse)")

    def render(self, frame: np.ndarray | None) -> np.ndarray:
        f = self.flight
        img = frame.copy() if frame is not None else np.zeros((720, 960, 3), np.uint8)
        h, w = img.shape[:2]
        self.size = (w, h)
        s, age = f.tel.snapshot()
        lines = [
            f"ESTADO: {f.state}",
            f.reason,
            f"bat {s.get('bat', '?')}%  altura {altitude(s)} cm (tof {s.get('tof', '?')}, h {s.get('h', '?')})  "
            f"yaw {s.get('yaw', '?')}  temp {s.get('temph', '?')} C",
            f"rc {f.rc}   telemetria {age * 1000:.0f} ms   video {f.video_age * 1000:.0f} ms",
        ]
        lines += f.status_lines()
        f.overlay(img)
        if f.state == "IDLE":
            lines += ["chequeo previo:"] + [f"  [{'OK' if ok else 'NO'}] {name}" for name, ok in f.preflight()]
            lines.append("t = despegar")
        hud(img, lines)
        color = (0, 0, 200) if f.airborne else (60, 60, 60)
        cv2.rectangle(img, (0, h - self.BAR_H), (w, h), color, -1)
        label = "PARO DE EMERGENCIA - clic aqui o ESPACIO" if f.airborne else "k = matar motores (solo emergencia)"
        (tw, th), _ = cv2.getTextSize(label, cv2.FONT_HERSHEY_SIMPLEX, 0.9, 2)
        cv2.putText(img, label, ((w - tw) // 2, h - (self.BAR_H - th) // 2), cv2.FONT_HERSHEY_SIMPLEX,
                    0.9, (255, 255, 255), 2, cv2.LINE_AA)
        return img

    def handle_key(self, key: int) -> bool:
        """Devuelve True si hay que salir."""
        f = self.flight
        if key == ord("t"):
            f.request_takeoff()
        elif key in (ord(" "), 13, 10, ord("l"), 27):
            if f.airborne:
                f.request_land("PARO: teclado")
        elif key == ord("k"):
            f.request_kill()
        elif key == ord("q"):
            if f.airborne:
                f.request_land("PARO: q en el aire")
            else:
                return True
        return False

    def closed(self) -> bool:
        return cv2.getWindowProperty(self.title, cv2.WND_PROP_VISIBLE) < 1


def ask(tello, cmd: str) -> str:
    """Comando con respuesta, vaciando antes respuestas viejas (ver test_tags.TelloSource._ask)."""
    responses = tello.get_own_udp_object()["responses"]
    time.sleep(0.3)
    responses.clear()
    return tello.send_command_with_return(cmd, timeout=5)


def connect():
    """Conecta, enciende el video y devuelve (tello, lector de frames)."""
    from djitellopy import Tello

    Tello.LOGGER.setLevel(logging.WARNING)
    tello = Tello()
    tello.connect()
    print(f"[tello] streamon -> {ask(tello, 'streamon')!r}")
    return tello, tello.get_frame_read(with_queue=True, max_queue_len=1)


def run_app(flight: Flight, tello, reader, record: str | None, title: str) -> None:
    """Hilo de control + HMI en el hilo principal hasta salir; aterriza si hace falta."""
    threading.Thread(target=flight.run, daemon=True, name="control").start()
    hmi = Hmi(flight, title)
    writer = None
    last_frame, t_frame = None, -math.inf
    t_start = time.monotonic()
    try:
        while True:
            rgb = reader.frame
            if rgb is not None:
                last_frame, t_frame = cv2.cvtColor(rgb, cv2.COLOR_RGB2BGR), time.monotonic()
                if record:
                    if writer is None:
                        hh, ww = last_frame.shape[:2]
                        writer = cv2.VideoWriter(record, cv2.VideoWriter_fourcc(*"mp4v"), 30, (ww, hh))
                    writer.write(last_frame)
                flight.on_frame(last_frame, t_frame)
            flight.video_age = time.monotonic() - t_frame
            cv2.imshow(title, hmi.render(last_frame))
            if hmi.handle_key(cv2.waitKey(15) & 0xFF):
                break
            if hmi.closed():
                if flight.airborne:
                    flight.request_land("PARO: ventana cerrada")
                break
            # en tierra y sin telemetría ni video: el Tello se apagó; no dejar la ventana abierta
            if (not flight.airborne and time.monotonic() - t_start > 15
                    and flight.tel.snapshot()[1] > 15 and flight.video_age > 15):
                print("[hmi] el dron no responde desde hace 15 s (¿apagado?): cerrando")
                break
    except KeyboardInterrupt:
        flight.request_land("PARO: Ctrl+C")
    finally:
        # si sigue en el aire, esperar a que aterrice antes de cerrar todo
        t_end = time.monotonic() + flight.cfg.land_timeout_s + 5
        while flight.airborne and time.monotonic() < t_end:
            flight.request_land("cerrando programa")
            time.sleep(0.1)
        flight.stop()
        if writer is not None:
            writer.release()
        cv2.destroyAllWindows()
        tello.send_command_without_return("streamoff")
        tello.end()  # si is_flying quedó en True, djitellopy manda land
        print(f"[vuelo] final: {flight.state} — {flight.reason}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config" / "flight.json"))
    ap.add_argument("--yaw-test", type=float, help="grados a girar por rc tras el estacionario (p.ej. 90)")
    ap.add_argument("--flip-test", choices=["f", "b", "l", "r"], help="flip de prueba tras el estacionario")
    ap.add_argument("--record", help="grabar el video (mp4)")
    args = ap.parse_args()

    cfg = FlightConfig.load(Path(args.config))
    tello, reader = connect()
    log_path = ROOT / "logs" / time.strftime("vuelo_%Y%m%d_%H%M%S.csv")
    print(f"[hmi] bitácora: {log_path}")
    run_app(Flight(tello, cfg, log_path, args.yaw_test, args.flip_test), tello, reader, args.record, "primer vuelo")


if __name__ == "__main__":
    main()
