#!/usr/bin/env python3
"""Prototipo de misión AprilTags: avanzar, detectar un tag VERTICAL, acercarse
con la distancia estimada, ejecutar su función y seguir avanzando.

Supone tags verticales (pared o poste) frente al dron. Si el comité confirma
que van en el piso, cambia la fase de acercamiento; la detección y las
funciones se quedan igual.

Uso:
    python scripts/mission_tags.py
    python scripts/mission_tags.py --record mision1.mp4

Controles iguales a first_flight.py: t despega, ESPACIO / clic en la barra =
PARO, k mata motores. Parámetros en config/mission_tags.json y config/flight.json.

Estados de la misión:
    ADVANCE   avanza despacio manteniendo el rumbo, buscando un tag confirmado
    APPROACH  se acerca a stop_cm del tag. Lejos: avanza apuntándole. Cerca
              (< lateral_start_cm): control en el marco del tag (ángulo,
              lateral y distancia al plano) para quedar de frente y centrado.
              Si el tag se acerca al borde de la imagen, deja de avanzar y lo
              recentra; si se pierde, gira hacia donde se fue antes de aterrizar
    EXECUTE   ejecuta la función del tag (lista de primitivas) y vuelve a ADVANCE
"""
from __future__ import annotations

import argparse
import json
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, field, fields
from pathlib import Path

import cv2
import numpy as np

from first_flight import AIRBORNE, ROOT, Flight, FlightConfig, altitude, clamp, connect, run_app, wrap_deg
from test_tags import DEFAULT_CALIB, TAG_FUNCTIONS, Confirmer, Detection, PoseEstimator, TagDetector, TagPose, draw

MISSION_STATES = {"ADVANCE", "APPROACH", "EXECUTE"}

# Función de cada tag como primitivas. Giro + = a la derecha del dron (horario visto desde arriba).
ACTIONS: dict[int, list[tuple]] = {
    1: [("yaw", 90)],
    2: [("yaw", -90)],
    3: [("yaw", 180)],
    4: [("flip",)],
    5: [("climb", +1)],
    6: [("climb", -1)],
    7: [("land",)],
    8: [("yaw", 180), ("flip",)],
    9: [("wait",)],
    10: [("yaw", 360)],
}


@dataclass
class MissionConfig:
    tag_cm: float = 8.0
    confirm_n: int = 3
    start_hover_s: float = 2.0
    mission_max_s: float = 240.0
    advance_fb: int = 12
    advance_timeout_s: float = 10.0
    heading_kp: float = 1.0
    heading_max: int = 20
    min_front_cm: float = 50.0
    obstacle_drop_cm: float = 25.0
    blind_speed_cms: float = 20.0
    approach_start_cm: float = 250.0
    stop_cm: float = 60.0
    stop_tol_cm: float = 10.0
    approach_kp: float = 0.3
    approach_fb_max: int = 15
    approach_fb_min: int = 8
    az_kp: float = 1.2
    az_max: int = 40
    az_min: int = 15
    az_tol_deg: float = 5.0
    lateral_start_cm: float = 130.0
    lat_kp: float = 1.5
    lat_min: int = 12
    lat_max: int = 20
    lat_tol_cm: float = 5.0
    az_keep_deg: float = 15.0
    search_rate: int = 25
    align_kp: float = 1.0
    align_tol_deg: float = 3.0
    align_window: int = 9
    camera_pitch_deg: float = 11.0
    hold_s: float = 0.5
    approach_timeout_s: float = 25.0
    lost_s: float = 2.0
    reacquire_s: float = 1.5
    climb_cm: float = 30.0
    climb_kp: float = 1.0
    climb_max: int = 30
    climb_min: int = 15
    climb_tol_cm: float = 5.0
    climb_timeout_s: float = 6.0
    min_tof_cm: float = 30.0
    flip_dir: str = "b"
    flip_min_battery: int = 50
    flip_wait_s: float = 3.0
    wait_s: float = 5.0

    @classmethod
    def load(cls, path: Path) -> MissionConfig:
        data = json.loads(path.read_text()) if path.exists() else {}
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise SystemExit(f"{path}: claves desconocidas {sorted(unknown)}")
        return cls(**data)


@dataclass
class Vision:
    t: float
    dets: list[Detection]
    poses: list[TagPose | None]
    confirmed: set[int]
    # por tag: medianas de (ángulo relativo, lateral en el marco del tag, distancia al plano)
    tagframe: dict[int, tuple[float, float, float]] = field(default_factory=dict)


def relative_yaw(pose: TagPose, pitch_deg: float) -> float:
    """Cuántos grados está girado el dron respecto a estar de frente al tag.

    Positivo = girado a la derecha. Sale de la normal del plano del tag, pasada
    a un marco nivelado (la cámara mira 11° hacia abajo). Ruido medido con un
    tag de 8 cm: ~2° por frame a 1.1–1.6 m; 4–5° más allá de 2 m.
    """
    p = math.radians(pitch_deg)
    nx, ny, nz = pose.normal
    z_level = -math.sin(p) * ny + math.cos(p) * nz
    return math.degrees(math.atan2(nx, -z_level))


def with_min(value: float, minimum: float, limit: float) -> int:
    """P con piso: el Tello no se mueve con rc pequeños (zona muerta)."""
    if value == 0:
        return 0
    return clamp(math.copysign(max(abs(value), minimum), value), limit)


class TagMission(Flight):
    AIRBORNE_STATES = AIRBORNE | MISSION_STATES
    LOG_EXTRA = ["n_tags", "objetivo", "obj_z", "obj_az", "obj_x", "obj_angulo", "frente_cm"]

    def __init__(self, tello, cfg: FlightConfig, mcfg: MissionConfig, log_path: Path, calib: Path) -> None:
        super().__init__(tello, cfg, log_path, None)
        self.m = mcfg
        self.detector = TagDetector(set(TAG_FUNCTIONS), True, 2.0)
        self.pose_est = PoseEstimator(calib, mcfg.tag_cm)
        self.confirmer = Confirmer(mcfg.confirm_n)
        self._vis: Vision | None = None
        self._vis_lock = threading.Lock()
        self._last_seen: dict[int, float] = {}  # tags ya ejecutados -> última vez vistos
        self._heading = 0.0
        self._front_cm: float | None = None  # memoria del obstáculo al frente (ver _front_blocked)
        self._front_heading = 0.0
        self._t_front = 0.0
        self._yaw_prev: float | None = None
        self._turned = 0.0  # giro acumulado sin envolver: permite 360°
        self._target: int | None = None
        self._t_target_seen = 0.0
        self._t_hold: float | None = None
        self._plan: list[tuple] = []
        self._prim: tuple = ()
        self._prim_start = 0.0
        self._prim_goal = 0.0
        self.executed: list[str] = []
        self._alt_ref: float | None = None  # altura al entrar a ADVANCE/APPROACH
        self._ref_state = ""
        self._obj: tuple[float, float, float, float] | None = None  # (z, az, x, angulo) para la bitácora
        self._tf_hist: dict[int, deque] = {}  # últimas (ángulo, lateral, distancia) por tag
        self._last_az = 0.0  # para buscar hacia el lado por donde se fue el tag

    # ------------------------------------------------ visión (hilo de la HMI)

    def on_frame(self, bgr: np.ndarray, t: float) -> None:
        if (bgr.shape[1], bgr.shape[0]) != self.pose_est.size:
            self.reason = f"video {bgr.shape[1]}x{bgr.shape[0]} no coincide con la calibracion"
            return
        dets = self.detector.detect(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
        poses = [self.pose_est.estimate(d) if d.accepted else None for d in dets]
        confirmed = self.confirmer.update({d.tag_id for d in dets if d.accepted})
        tf = {}
        for d, p in zip(dets, poses):
            if p is not None:
                c = p.cam_in_tag
                hist = self._tf_hist.setdefault(d.tag_id, deque(maxlen=self.m.align_window))
                hist.append((relative_yaw(p, self.m.camera_pitch_deg), float(c[0]), float(c[2])))
                tf[d.tag_id] = tuple(float(v) for v in np.median(np.array(hist), axis=0))
        for tid in set(self._tf_hist) - set(tf):  # tag no visto: historia vieja fuera
            del self._tf_hist[tid]
        with self._vis_lock:
            self._vis = Vision(t, dets, poses, confirmed, tf)
            for d in dets:
                if d.tag_id in self._last_seen:
                    self._last_seen[d.tag_id] = t

    def _vision(self, now: float) -> Vision | None:
        with self._vis_lock:
            v = self._vis
        return v if v is not None and now - v.t <= self.cfg.video_hover_s else None

    def _ignored(self, tag_id: int, now: float) -> bool:
        """Un tag ejecutado se ignora mientras siga a la vista y reacquire_s después."""
        with self._vis_lock:
            t = self._last_seen.get(tag_id)
        return t is not None and now - t < self.m.reacquire_s

    # ------------------------------------------------ HMI

    def overlay(self, img: np.ndarray) -> None:
        v = self._vis
        if v is not None:
            draw(img, v.dets, v.confirmed, v.poses)

    def status_lines(self) -> list[str]:
        lines = [f"tag {self.m.tag_cm:g} cm | objetivo: "
                 + (f"{self._target} ({TAG_FUNCTIONS[self._target]})" if self._target else "-")]
        if self.executed:
            lines.append("ejecutados: " + ", ".join(self.executed[-6:]))
        return lines

    # ------------------------------------------------ misión (hilo de control)

    def _hover_done(self, yaw: float) -> None:
        self._heading = yaw
        self._goto("ADVANCE", "avanzando, buscando tag")

    def _log_extra(self) -> list:
        v = self._vis
        o = self._obj
        obj = [f"{o[0]:.0f}", f"{o[1]:.1f}", f"{o[2]:+.0f}", f"{o[3]:+.1f}"] if o else ["", "", "", ""]
        front = "" if self._front_cm is None else f"{self._front_cm:.0f}"
        return [len(v.dets) if v else "", self._target or "", *obj, front]

    def _extra_step(self, st: str, s: dict, now: float, elapsed: float) -> None:
        yaw = s.get("yaw", 0)
        if self._yaw_prev is not None:
            self._turned += wrap_deg(yaw - self._yaw_prev)
        self._yaw_prev = yaw
        # algo bajo el dron (caja, obstáculo): el tof baja sin que pidamos bajar
        if st in ("ADVANCE", "APPROACH"):
            alt = altitude(s)
            if self._ref_state != st or self._alt_ref is None:
                self._alt_ref, self._ref_state = alt, st
            elif alt < self._alt_ref - self.m.obstacle_drop_cm:
                return self._begin_landing("EMERGENCY_LAND",
                                           f"obstaculo debajo: altura {alt} cm (era {self._alt_ref:.0f})")
        else:
            self._ref_state = st
        if st == "ADVANCE":
            self._advance(yaw, now, elapsed)
        elif st == "APPROACH":
            self._approach(yaw, now, elapsed)
        elif st == "EXECUTE":
            self._execute(s, now)

    def _advance(self, yaw: float, now: float, elapsed: float) -> None:
        v = self._vision(now)
        if v is None:
            return self._send_rc(0, 0, 0, 0)
        candidates = []
        blocked = self._front_blocked(v, yaw, now)
        for d, p in zip(v.dets, v.poses):
            if p is None:
                continue
            fwd = float(p.t[2])
            if d.tag_id in v.confirmed and not self._ignored(d.tag_id, now) and fwd <= self.m.approach_start_cm:
                candidates.append((fwd, d.tag_id))
        if candidates:
            fwd, tid = min(candidates)
            self._target, self._t_target_seen, self._t_hold = tid, now, None
            return self._goto("APPROACH", f"tag {tid} ({TAG_FUNCTIONS[tid]}) a {fwd:.0f} cm")
        if elapsed > self.m.advance_timeout_s:
            why = "bloqueado por un tag al frente" if blocked else "sin tags al frente"
            return self._begin_landing("LANDING", f"{why} por {self.m.advance_timeout_s:.0f} s: fin")
        err = wrap_deg(self._heading - yaw)
        rate = 0 if abs(err) < 2 else clamp(self.m.heading_kp * err, self.m.heading_max)
        self._send_rc(0, 0 if blocked else self.m.advance_fb, 0, rate)

    def _front_blocked(self, v: Vision, yaw: float, now: float) -> bool:
        """¿Hay un tag (pared) a menos de min_front_cm al frente?

        Si el tag sale de la vista (p. ej. tras subir 30 cm), se recuerda su
        distancia y se le resta lo que el dron pudo avanzar, con una velocidad
        pesimista. La memoria se borra tras girar más de 45°.
        """
        fwds = [float(p.t[2]) for p in v.poses if p is not None]
        if fwds:
            self._front_cm, self._front_heading = min(fwds), yaw
        elif self._front_cm is not None:
            if abs(wrap_deg(yaw - self._front_heading)) > 45:
                self._front_cm = None
            elif self.rc[1] > 0:
                self._front_cm -= self.m.blind_speed_cms * (now - self._t_front)
        self._t_front = now
        return self._front_cm is not None and self._front_cm < self.m.min_front_cm

    def _approach(self, yaw: float, now: float, elapsed: float) -> None:
        m, v = self.m, self._vision(now)
        if v is None:
            return self._send_rc(0, 0, 0, 0)
        self._front_blocked(v, yaw, now)  # mantiene fresca la memoria del frente para después de EXECUTE
        match = [p for d, p in zip(v.dets, v.poses) if d.tag_id == self._target and p is not None]
        if not match:
            # buscar girando hacia el lado por donde se fue, antes de rendirse
            if now - self._t_target_seen > m.lost_s:
                return self._begin_landing("EMERGENCY_LAND", f"tag {self._target} perdido en el acercamiento")
            return self._send_rc(0, 0, 0, math.copysign(m.search_rate, self._last_az))
        self._t_target_seen = now
        p = min(match, key=lambda q: q.t[2])
        z, az = float(p.t[2]), p.azimuth_deg
        self._last_az = az
        ang, lat, dist = v.tagframe.get(self._target, (0.0, float(p.t[0]), z))
        self._obj = (z, az, lat, ang)
        ready = False

        keep = abs(az) > m.az_keep_deg  # el tag se acerca al borde de la imagen
        if z > m.lateral_start_cm:
            # lejos: avanzar apuntándole (la orientación del plano aún es ruidosa);
            # si el tag se va hacia el borde, no avanzar hasta recentrarlo
            lr = 0
            fb = 0 if keep else with_min(m.approach_kp * (z - m.stop_cm), m.approach_fb_min, m.approach_fb_max)
            yr = 0 if abs(az) <= m.az_tol_deg else with_min(m.az_kp * az, m.az_min, m.az_max)
        else:
            # cerca: control en el marco del TAG. lateral y distancia no cambian
            # cuando el dron gira, así que girar (alinear) y deslizarse (centrar)
            # ya no se estorban. La velocidad deseada se pide en el marco del tag
            # y se rota al marco del dron según cuánto está girado (ang).
            aligned = abs(ang) <= m.align_tol_deg
            centered = abs(lat) <= m.lat_tol_cm
            at_dist = abs(dist - m.stop_cm) <= m.stop_tol_cm
            yr = 0 if aligned else with_min(-m.align_kp * ang, m.az_min, m.az_max)
            # girar a la derecha mueve el tag a la izquierda de la imagen (az baja):
            # no seguir girando hacia donde el tag se saldría; el deslizamiento
            # lateral es lo que lo deja de frente y libera el giro
            soft = m.az_keep_deg - 3
            if (yr > 0 and az < -soft) or (yr < 0 and az > soft):
                yr = 0
            if keep:  # ya está en el borde: recentrarlo, sin dejar de deslizarse
                yr = with_min(m.az_kp * az, m.az_min, m.az_max)
            v_right = 0 if centered else with_min(-m.lat_kp * lat, m.lat_min, m.lat_max)
            v_fwd = 0 if at_dist else with_min(m.approach_kp * (dist - m.stop_cm), m.approach_fb_min, m.approach_fb_max)
            a = math.radians(ang)
            lr = v_right * math.cos(a) - v_fwd * math.sin(a)
            fb = v_right * math.sin(a) + v_fwd * math.cos(a)
            ready = aligned and centered and at_dist
        self._send_rc(lr, fb, 0, yr)
        if ready:
            self._t_hold = self._t_hold or now
            if now - self._t_hold >= m.hold_s:
                return self._start_execute(now, f"a {dist:.0f} cm, lateral {lat:+.0f} cm, angulo {ang:+.0f}")
        else:
            self._t_hold = None
        if elapsed > m.approach_timeout_s:
            self._start_execute(now, f"acercamiento incompleto ({z:.0f} cm, lateral {lat:+.0f}, angulo {ang:+.0f})")

    def _start_execute(self, now: float, how: str) -> None:
        tid = self._target
        self.executed.append(f"{tid}={TAG_FUNCTIONS[tid]}")
        with self._vis_lock:
            self._last_seen[tid] = now
        self._plan = list(ACTIONS[tid])
        self._goto("EXECUTE", f"tag {tid} ({TAG_FUNCTIONS[tid]}) {how}")
        self._next_primitive(now)

    def _next_primitive(self, now: float) -> None:
        s, _ = self.tel.snapshot()
        while self._plan:
            prim = self._plan.pop(0)
            kind = prim[0]
            if kind == "land":
                return self._begin_landing("LANDING", f"tag {self._target}: aterrizar")
            if kind == "flip" and s.get("bat", 0) < self.m.flip_min_battery:
                self.reason = f"flip omitido: bateria {s.get('bat')}% < {self.m.flip_min_battery}%"
                continue
            self._prim, self._prim_start, self._t_hold = prim, now, None
            if kind == "yaw":
                self._prim_goal = self._turned + prim[1]
            elif kind == "climb":
                goal = s.get("tof", 0) + prim[1] * self.m.climb_cm  # tof crudo, igual que en _execute
                self._prim_goal = max(goal, self.m.min_tof_cm)
            elif kind == "flip":
                self._send_rc(0, 0, 0, 0)
                self.t.send_command_without_return(f"flip {self.m.flip_dir}")
            return
        # sin primitivas pendientes: seguir hacia el frente con el rumbo actual
        self._heading = s.get("yaw", 0)
        self._obj = None
        self._goto("ADVANCE", f"tag {self._target} ejecutado, avanzando")
        self._target = None

    def _execute(self, s: dict, now: float) -> None:
        cfg, m = self.cfg, self.m
        kind, el = self._prim[0], now - self._prim_start
        done = False
        if kind == "yaw":
            err = self._prim_goal - self._turned
            on_goal = abs(err) <= cfg.yaw_tol_deg
            rate = 0 if on_goal else with_min(cfg.yaw_kp * err, cfg.yaw_min_rate, cfg.yaw_rate_limit)
            if self.video_age > cfg.video_hover_s:  # sin video fresco: quieto (no cuenta como llegado)
                rate = 0
            self._send_rc(0, 0, 0, rate)
            done = self._held(on_goal, now, 0.3) or el > cfg.yaw_timeout_s * max(1.0, abs(self._prim[1]) / 180)
        elif kind == "climb":
            err = self._prim_goal - s.get("tof", self._prim_goal)
            on_goal = abs(err) <= m.climb_tol_cm
            ud = 0 if on_goal else with_min(m.climb_kp * err, m.climb_min, m.climb_max)
            self._send_rc(0, 0, ud, 0)
            done = self._held(on_goal, now, 0.5) or el > m.climb_timeout_s
        elif kind == "flip":
            done = el > m.flip_wait_s  # sin rc mientras voltea
        elif kind == "wait":
            self._send_rc(0, 0, 0, 0)
            done = el > m.wait_s
        if done:
            self._next_primitive(now)

    def _held(self, ok: bool, now: float, hold: float) -> bool:
        if not ok:
            self._t_hold = None
            return False
        self._t_hold = self._t_hold or now
        return now - self._t_hold >= hold


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config" / "flight.json"))
    ap.add_argument("--mission", default=str(ROOT / "config" / "mission_tags.json"))
    ap.add_argument("--calib", default=str(DEFAULT_CALIB))
    ap.add_argument("--record", help="grabar el video (mp4)")
    args = ap.parse_args()

    cfg = FlightConfig.load(Path(args.config))
    mcfg = MissionConfig.load(Path(args.mission))
    cfg.hover_s, cfg.max_flight_s = mcfg.start_hover_s, mcfg.mission_max_s
    tello, reader = connect()
    log_path = ROOT / "logs" / time.strftime("mision_%Y%m%d_%H%M%S.csv")
    print(f"[hmi] bitácora: {log_path}  |  tags de {mcfg.tag_cm:g} cm")
    run_app(TagMission(tello, cfg, mcfg, log_path, Path(args.calib)), tello, reader, args.record, "mision tags")


if __name__ == "__main__":
    main()
