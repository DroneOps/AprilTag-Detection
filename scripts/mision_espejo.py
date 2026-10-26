#!/usr/bin/env python3
"""Misión con espejo: la cámara ve HACIA ABAJO y los tags están en el piso.

El dron avanza despacio mirando el piso. Cuando un tag confirmado aparece
debajo, se centra ENCIMA de él (adelante/atrás y lados), se alinea con sus
bordes (giro módulo 90°, suponiendo tags puestos derechos respecto a la pista),
ejecuta su función y sigue hacia el frente. Las acciones, el flip seguro, el
paro y los vigilantes son los de mission_tags.py / first_flight.py.

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
import time
from collections import deque
from dataclasses import dataclass, fields
from pathlib import Path

import cv2
import numpy as np

from first_flight import ROOT, FlightConfig, connect, run_app, with_min, wrap_deg
from mission_tags import MissionConfig, TagMission, Vision
from test_tags import DEFAULT_CALIB, TAG_FUNCTIONS, draw, floor_view


@dataclass
class MirrorConfig:
    espejo: str = "v"  # cómo se voltea la imagen (ver test_tags.py --espejo)
    quieto: bool = False  # True: no avanza, espera a que haya un tag debajo
    advance_fb: int = 12  # rc 12 ≈ 10 cm/s (calibración real)
    advance_timeout_s: float = 8.0  # sin vista al frente: avanzar a ciegas poco
    quieto_timeout_s: float = 20.0
    center_kp: float = 0.6
    center_min: int = 10
    center_max: int = 15
    center_tol_cm: float = 4.0
    rot_kp: float = 1.0
    rot_tol_deg: float = 4.0
    window: int = 7  # mediana de N frames
    vista_adelante_deg: float = 0.0  # inclinación del espejo: medirla con test_tags.py --espejo
    vista_lado_deg: float = 0.0

    @classmethod
    def load(cls, path: Path) -> MirrorConfig:
        data = json.loads(path.read_text()) if path.exists() else {}
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise SystemExit(f"{path}: claves desconocidas {sorted(unknown)}")
        return cls(**data)


def rot_mod90(angle: float) -> float:
    """Giro del tag en la imagen, llevado a [-45, 45): un tag derecho vale 0 en
    cualquiera de sus 4 orientaciones."""
    return (angle + 45.0) % 90.0 - 45.0


class MirrorMission(TagMission):
    LOG_EXTRA = ["n_tags", "objetivo", "tag_adelante", "tag_derecha", "tag_giro", "altura_espejo"]

    def __init__(self, tello, cfg: FlightConfig, mcfg: MissionConfig, ecfg: MirrorConfig,
                 log_path: Path, calib: Path) -> None:
        super().__init__(tello, cfg, mcfg, log_path, calib)
        self.e = ecfg
        self.pose_est = self.pose_est.mirrored(ecfg.espejo)
        self._floor_hist: dict[int, deque] = {}
        self._heights: dict[int, float] = {}
        self._last_floor = (0.0, 0.0)

    # ---- visión: imagen volteada, posición del tag sobre el piso
    def on_frame(self, bgr: np.ndarray, t: float) -> None:
        if (bgr.shape[1], bgr.shape[0]) != self.pose_est.size:
            self.reason = f"video {bgr.shape[1]}x{bgr.shape[0]} no coincide con la calibracion"
            return
        img = cv2.flip(bgr, 0 if self.e.espejo == "v" else 1)  # un tag espejado no se decodifica
        dets = self.detector.detect(cv2.cvtColor(img, cv2.COLOR_BGR2GRAY))
        poses = [self.pose_est.estimate(d) if d.accepted else None for d in dets]
        confirmed = self.confirmer.update({d.tag_id for d in dets if d.accepted})
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
        return ["ESPEJO: vista hacia abajo, SIN vista al frente" + (" (quieto)" if self.e.quieto else "")] \
            + super().status_lines()

    def _log_extra(self) -> list:
        v, tid = self._vis, self._target
        fl = v.tagframe.get(tid) if (v and tid) else None
        cells = [f"{fl[0]:+.0f}", f"{fl[1]:+.0f}", f"{fl[2]:+.0f}", f"{self._heights.get(tid, 0):.0f}"] if fl \
            else [""] * 4
        return [len(v.dets) if v else "", tid or "", *cells]

    # ---- avanzar mirando el piso
    def _advance(self, yaw: float, now: float, elapsed: float) -> None:
        e, v = self.e, self._vision(now)
        if v is None:
            return self._send_rc(0, 0, 0, 0)
        cands = [(abs(v.tagframe[d.tag_id][0]) + abs(v.tagframe[d.tag_id][1]), d.tag_id)
                 for d in v.dets if d.tag_id in v.confirmed and d.tag_id in v.tagframe
                 and not self._ignored(d.tag_id, now)]
        if cands:
            _, tid = min(cands)
            fwd, right, rot = v.tagframe[tid]
            self._target, self._t_target_seen, self._t_hold = tid, now, None
            return self._goto("APPROACH", f"tag {tid} ({TAG_FUNCTIONS[tid]}) debajo: adelante {fwd:+.0f}, "
                                          f"lado {right:+.0f} cm")
        limit = e.quieto_timeout_s if e.quieto else e.advance_timeout_s
        if elapsed > limit:
            return self._begin_landing("LANDING", f"sin tags debajo por {limit:.0f} s: fin")
        err = wrap_deg(self._heading - yaw)
        rate = 0 if abs(err) <= 3 else with_min(self.m.heading_kp * err, self.m.az_min, self.m.heading_max)
        self._send_rc(0, 0 if e.quieto else e.advance_fb, 0, rate)

    # ---- centrarse encima y alinearse
    def _approach(self, yaw: float, alt: float, now: float, elapsed: float) -> None:
        e, m, v = self.e, self.m, self._vision(now)
        if v is None:
            return self._send_rc(0, 0, 0, 0)
        fl = v.tagframe.get(self._target)
        if fl is None:
            # se salió por un borde: ir hacia donde estaba, despacio, antes de rendirse
            if now - self._t_target_seen > m.lost_s:
                return self._begin_landing("EMERGENCY_LAND", f"tag {self._target} perdido al centrarse")
            lf, lr = self._last_floor
            return self._send_rc(math.copysign(e.center_min, lr) if abs(lr) > e.center_tol_cm else 0,
                                 math.copysign(e.center_min, lf) if abs(lf) > e.center_tol_cm else 0, 0, 0)
        self._t_target_seen = now
        fwd, right, rot = fl
        self._last_floor = (fwd, right)
        fb = 0 if abs(fwd) <= e.center_tol_cm else with_min(e.center_kp * fwd, e.center_min, e.center_max)
        lr = 0 if abs(right) <= e.center_tol_cm else with_min(e.center_kp * right, e.center_min, e.center_max)
        # tag girado a la derecha en la imagen (+): girar el dron a la derecha lo endereza
        yr = 0 if abs(rot) <= e.rot_tol_deg else with_min(e.rot_kp * rot, m.az_min, m.az_max)
        self._send_rc(lr, fb, 0, yr)
        if fb == 0 and lr == 0 and yr == 0:
            self._t_hold = self._t_hold or now
            if now - self._t_hold >= m.hold_s:
                return self._start_execute(now, f"encima: adelante {fwd:+.0f}, lado {right:+.0f} cm, giro {rot:+.0f}")
        else:
            self._t_hold = None
        if elapsed > m.approach_timeout_s:
            self._start_execute(now, f"centrado incompleto (adelante {fwd:+.0f}, lado {right:+.0f}, giro {rot:+.0f})")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config" / "flight.json"))
    ap.add_argument("--mission", default=str(ROOT / "config" / "mission_tags.json"))
    ap.add_argument("--espejo-config", default=str(ROOT / "config" / "mission_espejo.json"))
    ap.add_argument("--calib", default=str(DEFAULT_CALIB))
    ap.add_argument("--espejo", choices=["v", "h"], help="sobrescribe cómo se voltea la imagen")
    ap.add_argument("--quieto", action="store_true", help="no avanzar: esperar un tag debajo")
    ap.add_argument("--record", help="grabar el video crudo (mp4)")
    args = ap.parse_args()

    cfg = FlightConfig.load(Path(args.config))
    mcfg = MissionConfig.load(Path(args.mission))
    ecfg = MirrorConfig.load(Path(args.espejo_config))
    if args.espejo:
        ecfg.espejo = args.espejo
    if args.quieto:
        ecfg.quieto = True
    cfg.hover_s, cfg.max_flight_s = mcfg.start_hover_s, mcfg.mission_max_s
    tello, reader = connect()
    log_path = ROOT / "logs" / time.strftime("espejo_%Y%m%d_%H%M%S.csv")
    print(f"[hmi] bitácora: {log_path}  |  tags de {mcfg.tag_cm:g} cm  |  espejo {ecfg.espejo}")
    run_app(MirrorMission(tello, cfg, mcfg, ecfg, log_path, Path(args.calib)), tello, reader, args.record,
            "mision espejo")


if __name__ == "__main__":
    main()
