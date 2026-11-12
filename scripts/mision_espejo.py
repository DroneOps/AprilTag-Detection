#!/usr/bin/env python3
"""Misión con espejo: la cámara ve HACIA ABAJO y los tags están en el piso.

El dron avanza despacio mirando el piso. Cuando un tag confirmado aparece
debajo, se centra ENCIMA de él (adelante/atrás y lados) sosteniendo el rumbo del
tramo, ejecuta su función y sigue hacia el frente. No se alinea con los bordes
del tag: el reglamento pide funcionar con tags girados (alinear_bordes lo
reactiva). El tag que ve mientras despega (el de inicio) se ignora
(ignorar_inicio). Las acciones,
el flip seguro, el paro y los vigilantes son los de mission_tags.py / first_flight.py.

ATENCIÓN: con el espejo cubriendo toda la cámara NO hay vista al frente: el dron
no ve paredes ni obstáculos. Avanza como máximo advance_timeout_s sin ver tags.

Uso:
    python scripts/mision_espejo.py --record espejo_m1.mp4
    python scripts/mision_espejo.py --quieto            # no avanza: espera un tag debajo
    python scripts/mision_espejo.py --espejo h          # si "adelante" sale al revés en test_tags

Parámetros propios en config/mission_espejo.json (más config/mission_tags.json
y config/flight.json).
"""
from __future__ import annotations

import argparse
import json
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, fields
from pathlib import Path

import cv2
import numpy as np

from first_flight import ROOT, FlightConfig, altitude, connect, run_app, with_min
from mission_tags import MissionConfig, TagMission, Vision
from test_tags import DEFAULT_CALIB, TAG_FUNCTIONS, draw, floor_view


@dataclass
class MirrorConfig:
    espejo: str = "v"  # cómo se voltea la imagen (ver test_tags.py --espejo)
    quieto: bool = False  # True: no avanza, espera a que haya un tag debajo
    cruise_alt_cm: float = 100.0  # más alto = ve más piso debajo (a 100 cm: ±39 cm adelante, ±52 de lado)
    advance_fb: int = 15  # rc 15 ≈ 16–20 cm/s (calibración real)
    advance_timeout_s: float = 12.0  # sin ver tag debajo por esto: fin (sin vista al frente)
    advance_lr: int = 0  # rc lateral fijo al avanzar sin tag, para compensar si el dron se va de un lado
    # (se va a la derecha: negativo, p. ej. -10)
    alinear_bordes: bool = False  # True: girar para alinearse con los bordes del tag (supone tags derechos)
    ignorar_inicio: bool = True  # ignorar el tag que se ve mientras despega (el de inicio)
    inicio_alt_cm: float = 70.0  # ...solo el visto abajo de esta altura, aún sobre el punto de despegue
    quieto_timeout_s: float = 20.0
    center_kp: float = 0.6
    center_kd: float = 1.0  # rc por cm/s: frena según qué tan rápido se acerca (real 9-nov: oscilaba ±15–20 cm)
    center_min: int = 10
    center_max: int = 15
    center_dead: float = 5.0  # mando calculado menor que esto: no mandar nada (el Tello frena solo)
    center_tol_cm: float = 6.0
    center_vel_tol: float = 4.0  # cm/s: para ejecutar, además de cerca, casi quieto
    centrar_max_s: float = 8.0  # si no se estabiliza encima en este tiempo, ejecuta igual (el punto es por el tag)
    rot_kp: float = 1.0
    rot_tol_deg: float = 4.0
    window: int = 7  # mediana de N frames
    # sostener la posición con el piso visto por el espejo (11-nov: los dos Tellos se iban solos
    # a la derecha, 4–12 cm/s, y el primer tag quedaba en la orilla de la vista o fuera)
    sostener_piso: bool = True  # quieto y subiendo: volver al punto de despegue; avanzando: sostener la línea
    piso_calidad: float = 0.1  # calidad mínima de la correlación de fase para creerle
    piso_kp: float = 0.5  # rc por cm de distancia a donde debería estar
    piso_kd: float = 0.8  # rc por cm/s que se está yendo
    piso_ki: float = 0.15  # rc por cm·s: junta el empuje que hace falta contra una deriva constante
    # (sin esto, con el Tello 7 se quedaba ~26 cm corrido: el PD solo empuja si hay error)
    piso_i_max: float = 15.0  # tope de lo juntado, en rc (que no se pase de largo)
    # integral al despegar, en rc (lado, adelante): + si el dron se va solo a la derecha / adelante.
    # Va en config/mision_dron<N>.json de cada dron. OJO: si el dron ya no deriva, empuja de más al
    # principio hasta que la integral se corrige sola (unos segundos)
    piso_i_inicial: tuple = (0.0, 0.0)
    # ejecutando un tag (giros, pausa): sostenerse sobre él con su posición (11-nov: en un giro de
    # 90° se corría 26–42 cm), y que el tramo nuevo pase por el tag y no por donde quedó el dron
    sostener_tag: bool = True
    piso_min: int = 10
    piso_max: int = 20
    piso_dead: float = 4.0  # mando menor que esto: nada
    # seguro, por si en el dron real la medida sale al revés y la corrección empuja hacia afuera:
    # apagarla si, corrigiendo, se aleja piso_alejandose_cm en 1.5 s (al revés, deriva y corrección
    # suman >30 cm/s) o si se pasa de piso_limite_cm. No cuenta lo que se fue al despegar: ahí el
    # Tello ignora el rc (el Tello 7 se va >80 cm)
    piso_alejandose_cm: float = 35.0
    piso_limite_cm: float = 150.0
    buscar_s: float = 4.0  # tag perdido al centrarse: buscarlo donde debe estar esto, luego seguir avanzando
    vista_adelante_deg: float = 0.0  # inclinación del espejo: medirla con test_tags.py --espejo
    vista_lado_deg: float = 0.0

    @classmethod
    def load(cls, path: Path) -> MirrorConfig:
        data = json.loads(path.read_text()) if path.exists() else {}
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise SystemExit(f"{path}: claves desconocidas {sorted(unknown)}")
        return cls(**data)


def ajustes_dron(ecfg: "MirrorConfig", dron: str | None) -> list[str]:
    """Aplica config/mision_dron<N>.json (lo que cambia en la misión con ese dron, p. ej. la
    integral inicial). Devuelve lo que cambió."""
    if not dron:
        return []
    path = ROOT / "config" / f"mision_dron{dron}.json"
    if not path.exists():
        raise SystemExit(f"no existe {path.relative_to(ROOT)}")
    data = {k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("_")}
    unknown = set(data) - {f.name for f in fields(MirrorConfig)}
    if unknown:
        raise SystemExit(f"{path}: claves desconocidas {sorted(unknown)}")
    for k, v in data.items():
        setattr(ecfg, k, tuple(v) if isinstance(v, list) else v)
    return [f"{k}={v}" for k, v in data.items()]


class FlujoPiso:
    """Cuánto se mueve el dron sobre el piso, con la imagen del espejo: correlación de fase entre
    un cuadro y el anterior, pasada a cm con la altura. Posición y velocidad en el marco del dron,
    (derecha, adelante). Con el piso del laboratorio (cuadrícula de cinta) mide bien de lado;
    hacia adelante es peor si las rayas van en la dirección del avance (videos del 11-nov)."""

    TAM = (240, 180)

    def __init__(self, fx: float, calidad: float) -> None:
        self.f = fx * self.TAM[0] / 960  # px por unidad a esta resolución
        self.calidad = calidad
        self.win = cv2.createHanningWindow(self.TAM, cv2.CV_32F)
        self.prev, self.t_prev = None, 0.0
        self.pos = np.zeros(2)
        self.vel = np.zeros(2)
        self.q, self.t_ok = 0.0, -math.inf
        self.lock = threading.Lock()

    def actualizar(self, gray: np.ndarray, t: float, alt: float, girando: bool) -> None:
        small = cv2.resize(gray, self.TAM, interpolation=cv2.INTER_AREA).astype(np.float32)
        if self.prev is not None and not girando and alt > 25 and t > self.t_prev:
            (dx, dy), q = cv2.phaseCorrelate(self.prev, small, self.win)
            self.q = q
            dt, cm = t - self.t_prev, alt / self.f
            v = np.array([-dx * cm / dt, dy * cm / dt])  # el piso se mueve al revés que el dron
            if q >= self.calidad and np.hypot(*v) < 150:  # más de 1.5 m/s: correlación equivocada
                with self.lock:
                    self.pos += v * dt
                    self.vel += 0.25 * (v - self.vel)
                    self.t_ok = t
        self.prev, self.t_prev = (None if girando else small), t

    def reiniciar(self, pos=(0.0, 0.0)) -> None:
        """Toma la posición de ahora como pos (por defecto, el origen)."""
        with self.lock:
            self.pos[:] = pos

    def estado(self) -> tuple[np.ndarray, np.ndarray]:
        with self.lock:
            return self.pos.copy(), self.vel.copy()

    def valido(self, now: float) -> bool:
        return now - self.t_ok < 0.5


def rot_mod90(angle: float) -> float:
    """Giro del tag en la imagen, llevado a [-45, 45): un tag derecho vale 0 en
    cualquiera de sus 4 orientaciones."""
    return (angle + 45.0) % 90.0 - 45.0


class MirrorMission(TagMission):
    LOG_EXTRA = ["n_tags", "objetivo", "tag_adelante", "tag_derecha", "tag_giro", "altura_espejo",
                 "piso_der", "piso_ade", "piso_vder", "piso_vade", "piso_q", "piso_ider", "piso_iade"]

    def __init__(self, tello, cfg: FlightConfig, mcfg: MissionConfig, ecfg: MirrorConfig,
                 log_path: Path, calib: Path) -> None:
        mcfg.cruise_alt_cm = ecfg.cruise_alt_cm
        super().__init__(tello, cfg, mcfg, log_path, calib)
        self.e = ecfg
        self._started = False
        self._center_hist: deque = deque(maxlen=60)  # (t del frame, adelante, derecha) del tag objetivo
        self._start_ids: set[int] = set()  # tags vistos durante el despegue
        self.pose_est = self.pose_est.mirrored(ecfg.espejo)
        self._floor_hist: dict[int, deque] = {}
        self._heights: dict[int, float] = {}
        self._last_floor = (0.0, 0.0)
        self.piso = FlujoPiso(float(self.pose_est.K[0, 0]), ecfg.piso_calidad)
        self._pos_visto = np.zeros(2)  # posición (piso) cuando se vio el tag objetivo por última vez
        self._yaw_frame = None
        self._piso_apagado = False
        self._piso_lejos: deque = deque()  # (t, distancia a donde debería estar) mientras corrige
        self._piso_i = np.zeros(2)  # parte integral (derecha, adelante), en rc
        self._piso_t = None  # última vez que corrigió

    # ---- visión: imagen volteada, posición del tag sobre el piso
    def on_frame(self, bgr: np.ndarray, t: float) -> None:
        if (bgr.shape[1], bgr.shape[0]) != self.pose_est.size:
            self.reason = f"video {bgr.shape[1]}x{bgr.shape[0]} no coincide con la calibracion"
            return
        img = cv2.flip(bgr, 0 if self.e.espejo == "v" else 1)  # un tag espejado no se decodifica
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        s = self.tel.snapshot()[0]
        yaw = s.get("yaw", 0)
        girando = self.rc[3] != 0 or (self._yaw_frame is not None and abs(((yaw - self._yaw_frame) + 180) % 360 - 180) > 1)
        self._yaw_frame = yaw
        self.piso.actualizar(gray, t, altitude(s), girando)
        dets = self.detector.detect(gray)
        poses = [self.pose_est.estimate(d) if d.accepted else None for d in dets]
        confirmed = self.confirmer.update({d.tag_id for d in dets if d.accepted})
        if self.state in ("IDLE", "TAKEOFF") and altitude(self.tel.snapshot()[0]) < self.e.inicio_alt_cm:
            self._start_ids.update(d.tag_id for d in dets if d.accepted)
        floor = {}
        for d, p in zip(dets, poses):
            if p is not None:
                fwd, right, height, _, _ = floor_view(p, (self.e.vista_adelante_deg, self.e.vista_lado_deg))
                hist = self._floor_hist.setdefault(d.tag_id, deque(maxlen=self.e.window))
                hist.append((fwd, right, rot_mod90(d.angle_deg)))
                floor[d.tag_id] = tuple(float(v) for v in np.median(np.array(hist), axis=0))
                self._heights[d.tag_id] = height
        for tid in set(self._floor_hist) - set(floor):
            del self._floor_hist[tid]
        self._shown = img
        with self._vis_lock:
            self._vis = Vision(t, dets, poses, confirmed, floor)  # tagframe = (adelante, derecha, giro)
            for d in dets:
                if d.tag_id in self._last_seen:
                    self._last_seen[d.tag_id] = t

    # ---- HMI: se muestra la imagen ya volteada (la que ve el detector)
    def overlay(self, img: np.ndarray) -> None:
        shown = getattr(self, "_shown", None)
        if shown is not None and shown.shape == img.shape:
            img[:] = shown
        v = self._vis
        if v is not None:
            draw(img, v.dets, v.confirmed, v.poses, floor=True)
        w = img.shape[1]
        cv2.arrowedLine(img, (w // 2, 200), (w // 2, 140), (0, 255, 255), 3, tipLength=0.35)
        cv2.putText(img, "ADELANTE", (w // 2 + 12, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2,
                    cv2.LINE_AA)

    def status_lines(self) -> list[str]:
        piso = ("sostener piso: APAGADO (se alejo demasiado)" if self._piso_apagado else
                f"sostener piso: {'si' if self.e.sostener_piso else 'no'}, calidad {self.piso.q:.2f}")
        return ["ESPEJO: vista hacia abajo, SIN vista al frente" + (" (quieto)" if self.e.quieto else ""), piso] \
            + super().status_lines()

    def _log_extra(self) -> list:
        v, tid = self._vis, self._target
        fl = v.tagframe.get(tid) if (v and tid) else None
        cells = [f"{fl[0]:+.0f}", f"{fl[1]:+.0f}", f"{fl[2]:+.0f}", f"{self._heights.get(tid, 0):.0f}"] if fl \
            else [""] * 4
        (pr, pf), (vr, vf) = self.piso.estado()
        return [len(v.dets) if v else "", tid or "", *cells,
                f"{pr:+.1f}", f"{pf:+.1f}", f"{vr:+.1f}", f"{vf:+.1f}", f"{self.piso.q:.2f}",
                f"{self._piso_i[0]:+.1f}", f"{self._piso_i[1]:+.1f}"]

    # ---- sostener la posición con el piso
    def _goto(self, state: str, reason: str) -> None:
        prev = getattr(self, "state", None)
        super()._goto(state, reason)
        piso = getattr(self, "piso", None)
        if piso is not None and (state == "TAKEOFF" or (state == "ADVANCE" and prev == "EXECUTE")):
            pos = (0.0, 0.0)  # el punto de despegue, o el inicio del tramo nuevo
            if state == "ADVANCE" and self.e.sostener_tag:
                fl = self._tag_visto()
                if fl is not None:  # la línea del tramo pasa por el tag ejecutado, no por donde quedó el dron
                    pos = (-fl[1], -fl[0])  # el dron respecto al tag
            piso.reiniciar(pos)
            getattr(self, "_piso_lejos", deque()).clear()
        if state == "TAKEOFF" and hasattr(self, "_piso_i"):
            # vuelo nuevo: la integral empieza con lo que se sabe de este dron (piso_i_inicial). Entre
            # tramos se conserva: la deriva es del dron y va con él (siempre a su derecha)
            self._piso_i[:] = self.e.piso_i_inicial

    def _tag_visto(self):
        """(adelante, derecha, giro) del tag objetivo si se ve ahora, si no None."""
        v = self._vision(time.monotonic())
        return v.tagframe.get(self._target) if (v is not None and self._target) else None

    def _piso_mando(self, eje: int, err: float, vel: float, dt: float) -> int:
        """PID de un eje (0 = de lado, 1 = adelante). err: cm que está corrido de donde debería
        estar; vel: cm/s que se está yendo. Devuelve el rc a sumar (al revés del error)."""
        e = self.e
        pd = e.piso_kp * err + e.piso_kd * vel
        total = pd + self._piso_i[eje]
        # anti-windup: no juntar más si ya va al tope empujando hacia el mismo lado
        if dt > 0 and not (abs(total) >= e.piso_max and total * err > 0):
            self._piso_i[eje] = max(-e.piso_i_max, min(e.piso_i_max, self._piso_i[eje] + e.piso_ki * err * dt))
        u = -(pd + self._piso_i[eje])
        return 0 if abs(u) < e.piso_dead else with_min(u, e.piso_min, e.piso_max)

    def _send_rc(self, lr: float, fb: float, ud: float, yaw: float) -> None:
        """Quieto y subiendo: volver al punto de despegue. Avanzando sin tag: sostener la línea
        del tramo (de lado). Solo con una medida del piso reciente; sin ella, como antes."""
        e, piso = self.e, getattr(self, "piso", None)
        if e.sostener_piso and piso is not None and not self._piso_apagado \
                and self.state in ("HOVER", "CRUISE", "ADVANCE") and piso.valido(time.monotonic()):
            (pr, pf), (vr, vf) = piso.estado()
            now = time.monotonic()
            lejos = abs(pr) if self.state == "ADVANCE" else math.hypot(pr, pf)
            h = self._piso_lejos
            if h and (h[-1][2] != (self.state == "ADVANCE") or now - h[-1][0] > 0.5):
                h.clear()  # otro tipo de corrección, o hubo una pausa
            h.append((now, lejos, self.state == "ADVANCE"))
            while now - h[0][0] > 1.5:
                h.popleft()
            alejo = lejos - min(x[1] for x in h)
            if alejo > e.piso_alejandose_cm or lejos > e.piso_limite_cm:
                self._piso_apagado = True
                why = f"se alejo {alejo:.0f} cm en 1.5 s corrigiendo" if alejo > e.piso_alejandose_cm \
                    else f"esta a {lejos:.0f} cm"
                self.reason += f" | sostener_piso APAGADO: {why} (revisar la medida del piso)"
                print(f"[vuelo] sostener_piso apagado: {why}")
            else:
                dt = now - self._piso_t if self._piso_t is not None and now - self._piso_t < 0.5 else 0.0
                self._piso_t = now
                lr = lr + self._piso_mando(0, pr, vr, dt)
                if self.state != "ADVANCE" or fb == 0:  # avanzando, adelante manda la misión (salvo --quieto)
                    fb = fb + self._piso_mando(1, pf, vf, dt)
        elif e.sostener_tag and self.state == "EXECUTE" and self._prim \
                and (self._prim[0] in ("yaw", "wait") or (self._prim[0] == "alt_to" and len(self._prim) < 3)):
            # girando o en pausa: quedarse sobre el tag (con el flip no: ahí manda la recuperación)
            v = self._vision(time.monotonic())
            fl = v.tagframe.get(self._target) if (v is not None and self._target) else None
            if fl is not None:
                vf, vr = self._tag_velocity(v.t, fl[0], fl[1])
                lr, fb = lr + self._center_axis(fl[1], vr), fb + self._center_axis(fl[0], vf)
        super()._send_rc(lr, fb, ud, yaw)

    # ---- avanzar mirando el piso
    def _advance(self, yaw: float, now: float, elapsed: float) -> None:
        e, v = self.e, self._vision(now)
        if v is None:
            return self._send_rc(0, 0, 0, 0)
        if not self._started:
            self._started = True
            if e.ignorar_inicio and not e.quieto and self._start_ids:  # en --quieto el de debajo es el de la prueba
                # el tag que vio al despegar es el de inicio: no ejecutarlo. Antes se tomaba el
                # que estuviera debajo al empezar a avanzar, pero tras la deriva del despegue
                # ese ya podía ser el primero del recorrido (real 9-nov: ignoró el tag 1)
                with self._vis_lock:
                    for tid in self._start_ids:
                        self._last_seen[tid] = now
                print(f"[vuelo] ADVANCE: ignorando el tag de inicio {sorted(self._start_ids)}")
        cands = [(abs(v.tagframe[d.tag_id][0]) + abs(v.tagframe[d.tag_id][1]), d.tag_id)
                 for d in v.dets if d.tag_id in v.confirmed and d.tag_id in v.tagframe
                 and not self._ignored(d.tag_id, now)]
        if cands:
            _, tid = min(cands)
            fwd, right, rot = v.tagframe[tid]
            self._target, self._t_target_seen, self._t_hold = tid, now, None
            self._center_hist.clear()
            return self._goto("APPROACH", f"tag {tid} ({TAG_FUNCTIONS[tid]}) debajo: adelante {fwd:+.0f}, "
                                          f"lado {right:+.0f} cm")
        limit = e.quieto_timeout_s if e.quieto else e.advance_timeout_s
        if elapsed > limit:
            return self._begin_landing("LANDING", f"sin tags debajo por {limit:.0f} s: fin")
        self._send_rc(0 if e.quieto else e.advance_lr, 0 if e.quieto else e.advance_fb, 0, self._heading_rate(yaw))

    # ---- centrarse encima y alinearse
    def _approach(self, yaw: float, alt: float, now: float, elapsed: float) -> None:
        e, m, v = self.e, self.m, self._vision(now)
        if v is None:
            return self._send_rc(0, 0, 0, 0)
        fl = v.tagframe.get(self._target)
        if fl is None:
            # se salió de la vista (11-nov: por la deriva, casi siempre por la orilla): ir a donde
            # debe estar, contando lo que el dron se movió desde que lo vio; si no aparece en
            # buscar_s, seguir avanzando en vez de aterrizar
            if now - self._t_target_seen > e.buscar_s:
                return self._goto("ADVANCE", f"tag {self._target} perdido al centrarse: sigo avanzando")
            lf, lr = self._last_floor
            if self.piso.valido(now):
                d = self.piso.estado()[0] - self._pos_visto
                lr, lf = lr - d[0], lf - d[1]
            return self._send_rc(with_min(e.center_kp * lr, e.center_min, e.piso_max) if abs(lr) > e.center_tol_cm else 0,
                                 with_min(e.center_kp * lf, e.center_min, e.piso_max) if abs(lf) > e.center_tol_cm else 0,
                                 0, self._heading_rate(yaw))
        self._t_target_seen = now
        self._pos_visto = self.piso.estado()[0]
        fwd, right, rot = fl
        self._last_floor = (fwd, right)
        vf, vr = self._tag_velocity(v.t, fwd, right)
        fb, lr = self._center_axis(fwd, vf), self._center_axis(right, vr)
        if e.alinear_bordes:
            # tag girado a la derecha en la imagen (+): girar el dron a la derecha lo endereza
            yr = 0 if abs(rot) <= e.rot_tol_deg else with_min(e.rot_kp * rot, m.az_min, m.az_max)
        else:
            yr = self._heading_rate(yaw)  # sostener el rumbo del tramo, esté como esté girado el tag
        self._send_rc(lr, fb, 0, yr)
        settled = (abs(fwd) <= e.center_tol_cm and abs(right) <= e.center_tol_cm
                   and abs(vf) <= e.center_vel_tol and abs(vr) <= e.center_vel_tol)
        if settled and yr == 0:
            self._t_hold = self._t_hold or now
            if now - self._t_hold >= m.hold_s:
                return self._start_execute(now, f"encima: adelante {fwd:+.0f}, lado {right:+.0f} cm, giro {rot:+.0f}")
        else:
            self._t_hold = None
        if elapsed > e.centrar_max_s:
            self._start_execute(now, f"centrado incompleto (adelante {fwd:+.0f}, lado {right:+.0f}, giro {rot:+.0f})")

    def _tag_velocity(self, t_frame: float, fwd: float, right: float) -> tuple[float, float]:
        """Velocidad del tag respecto al dron (cm/s) en el último ~0.5 s, una muestra por frame."""
        h = self._center_hist
        if not h or t_frame > h[-1][0]:
            h.append((t_frame, fwd, right))
        pts = [p for p in h if t_frame - p[0] <= 0.5]
        if len(pts) < 4 or pts[-1][0] - pts[0][0] < 0.25:
            return 0.0, 0.0
        t = [p[0] for p in pts]
        return float(np.polyfit(t, [p[1] for p in pts], 1)[0]), float(np.polyfit(t, [p[2] for p in pts], 1)[0])

    def _center_axis(self, err: float, vel: float) -> int:
        """Mando de un eje para quedar encima del tag. Con el retraso del video y la
        inercia, sin frenar se pasaba y oscilaba; aquí la velocidad resta: si ya va
        hacia el tag lo bastante rápido, no empuja, y si se pasa, manda en contra."""
        e = self.e
        u = e.center_kp * err + e.center_kd * vel  # vel = cambio de err; acercarse la hace negativa
        if abs(err) > e.center_tol_cm and abs(vel) < e.center_vel_tol and u * err > 0:
            return with_min(u, e.center_min, e.center_max)  # lejos y quieto: empujar hacia el tag
        if abs(u) < e.center_dead:
            return 0
        return with_min(u, e.center_min, e.center_max)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config" / "flight.json"))
    ap.add_argument("--mission", default=str(ROOT / "config" / "mission_tags.json"))
    ap.add_argument("--espejo-config", default=str(ROOT / "config" / "mission_espejo.json"))
    ap.add_argument("--calib", default=str(DEFAULT_CALIB))
    ap.add_argument("--espejo", choices=["v", "h"], help="sobrescribe cómo se voltea la imagen")
    ap.add_argument("--quieto", action="store_true", help="no avanzar: esperar un tag debajo")
    ap.add_argument("--record", help="grabar el video crudo (mp4)")
    ap.add_argument("--dron", help="ajustes de ese dron: config/mision_dron<N>.json (p. ej. --dron 7)")
    args = ap.parse_args()

    cfg = FlightConfig.load(Path(args.config))
    mcfg = MissionConfig.load(Path(args.mission))
    ecfg = MirrorConfig.load(Path(args.espejo_config))
    if args.espejo:
        ecfg.espejo = args.espejo
    if args.quieto:
        ecfg.quieto = True
    for cambio in ajustes_dron(ecfg, args.dron):
        print(f"[hmi] Tello {args.dron}: {cambio}")
    cfg.hover_s, cfg.max_flight_s = mcfg.start_hover_s, mcfg.mission_max_s
    tello, reader = connect()
    log_path = ROOT / "logs" / time.strftime("espejo_%Y%m%d_%H%M%S.csv")
    print(f"[hmi] bitácora: {log_path}  |  tags de {mcfg.tag_cm:g} cm  |  espejo {ecfg.espejo}")
    run_app(MirrorMission(tello, cfg, mcfg, ecfg, log_path, Path(args.calib)), tello, reader, args.record,
            "mision espejo")


if __name__ == "__main__":
    main()
