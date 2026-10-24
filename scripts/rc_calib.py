#!/usr/bin/env python3
"""Calibración de rc: cuánto se mueve el Tello con rc 10, 15 y 20.

El dron se para frente a un tag (vertical, a ~1.5 m) y da pasos cortos:
mueve 1.5 s en un eje, se detiene 1.5 s y mide cuánto se desplazó. Adelante
y de lado se mide con el tag (PnP); arriba/abajo con el tof. Así sabemos la
zona muerta real y los mínimos que hay que usar en config/mission_tags.json.

Uso:
    python scripts/rc_calib.py                 # adelante, lado y vertical (~70 s de vuelo)
    python scripts/rc_calib.py --ejes fb lr    # solo algunos ejes
    python scripts/rc_calib.py --tag-cm 15

Montaje: tag vertical a la altura del vuelo (~90 cm), a ~1.5 m frente al
despegue, con ~1 m libre a los lados y detrás del dron.
Controles iguales a first_flight.py (t despega, ESPACIO = PARO).
Resultado: tabla en la consola y en capturas/rc_calib_*.txt.
"""
from __future__ import annotations

import argparse
import threading
import time
from collections import deque
from pathlib import Path

import cv2
import numpy as np

from first_flight import AIRBORNE, ROOT, Flight, FlightConfig, altitude, connect, run_app
from test_tags import DEFAULT_CALIB, TAG_FUNCTIONS, PoseEstimator, TagDetector, draw

VALUES = (10, 15, 20)
MOVE_S, SETTLE_S = 1.5, 1.5
ALT_CM = 90.0  # altura de trabajo: margen para pasos arriba y abajo
LIMITS = {  # no dar un paso que pueda sacar el dron de la zona segura
    "fb": (90.0, 260.0),  # distancia al tag (z) permitida antes de avanzar / retroceder
    "lr": 50.0,  # |desplazamiento lateral| máximo antes del paso
    "ud": (50.0, 150.0),  # altura permitida
}


class RcCalib(Flight):
    AIRBORNE_STATES = AIRBORNE | {"RC_ALT", "RC_STEP"}
    LOG_EXTRA = ["tag_z", "tag_x", "paso"]

    def __init__(self, tello, cfg: FlightConfig, log_path: Path, calib: Path, tag_cm: float, axes) -> None:
        super().__init__(tello, cfg, log_path, None)
        self.detector = TagDetector(set(TAG_FUNCTIONS), True, 2.0)
        self.pose_est = PoseEstimator(calib, tag_cm)
        self._tags: deque = deque(maxlen=90)  # (t, z, x) del tag más cercano
        self._alts: deque = deque(maxlen=60)  # (t, altura)
        self._lock = threading.Lock()
        self._overlay = None
        self.steps = [(a, sign * v) for a in axes for v in VALUES for sign in (1, -1)]
        self.results: list[tuple[str, int, float | None, str]] = []
        self._i, self._phase, self._t_phase, self._pre = 0, "start", 0.0, None

    # ---- visión (hilo de la HMI)
    def on_frame(self, bgr: np.ndarray, t: float) -> None:
        if (bgr.shape[1], bgr.shape[0]) != self.pose_est.size:
            return
        dets = [d for d in self.detector.detect(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY)) if d.accepted]
        poses = [self.pose_est.estimate(d) for d in dets]
        self._overlay = (dets, poses)
        valid = [p for p in poses if p is not None]
        if valid:
            p = min(valid, key=lambda q: q.t[2])
            with self._lock:
                self._tags.append((t, float(p.t[2]), float(p.t[0])))

    def overlay(self, img: np.ndarray) -> None:
        if self._overlay:
            dets, poses = self._overlay
            draw(img, dets, {d.tag_id for d in dets}, poses)

    def status_lines(self) -> list[str]:
        lines = [f"calibracion rc: paso {min(self._i + 1, len(self.steps))}/{len(self.steps)}"]
        for axis, rc, speed, note in self.results[-4:]:
            lines.append(f"  {axis} {rc:+3d}: " + (f"{speed:+5.1f} cm/s" if speed is not None else note))
        return lines

    def _log_extra(self) -> list:
        m = self._tag_median(time.monotonic(), 0.3)
        step = f"{self.steps[self._i][0]}{self.steps[self._i][1]:+d}" if self._i < len(self.steps) else ""
        return [f"{m[0]:.0f}" if m else "", f"{m[1]:+.0f}" if m else "", step]

    # ---- mediciones
    def _tag_median(self, now: float, window: float) -> tuple[float, float] | None:
        with self._lock:
            pts = [(z, x) for t, z, x in self._tags if now - t <= window]
        if len(pts) < 3:
            return None
        a = np.median(np.array(pts), axis=0)
        return float(a[0]), float(a[1])

    def _alt_median(self, now: float, window: float) -> float | None:
        pts = [a for t, a in self._alts if now - t <= window]
        return float(np.median(pts)) if len(pts) >= 2 else None

    def _measure(self, axis: str, now: float) -> float | None:
        if axis == "ud":
            return self._alt_median(now, 0.4)
        m = self._tag_median(now, 0.3)
        return None if m is None else (m[0] if axis == "fb" else m[1])

    def _safe(self, axis: str, rc: int, now: float) -> str | None:
        """Motivo para saltar el paso, o None si es seguro darlo."""
        if axis == "ud":
            alt = self._alt_median(now, 0.4)
            lo, hi = LIMITS["ud"]
            if alt is None or (rc > 0 and alt > hi) or (rc < 0 and alt < lo):
                return f"omitido: altura {alt}"
            return None
        m = self._tag_median(now, 0.3)
        if m is None:
            return "omitido: sin tag a la vista"
        z, x = m
        if axis == "fb" and ((rc > 0 and z < LIMITS["fb"][0]) or (rc < 0 and z > LIMITS["fb"][1])):
            return f"omitido: tag a {z:.0f} cm"
        if axis == "lr" and abs(x) > LIMITS["lr"]:
            return f"omitido: lateral {x:+.0f} cm"
        return None

    # ---- misión
    def _hover_done(self, yaw: float) -> None:
        self._t_on_target = None
        self._goto("RC_ALT", f"a {ALT_CM:.0f} cm para calibrar")

    def _extra_step(self, st: str, s: dict, now: float, elapsed: float) -> None:
        self._alts.append((now, altitude(s)))
        if st == "RC_ALT":
            ud, on_goal = self._alt_rc(ALT_CM, s)
            self._send_rc(0, 0, ud, 0)
            if self._held_alt(on_goal, now) or elapsed > self.cfg.alt_timeout_s:
                if self._tag_median(now, 0.5) is None:
                    return self._begin_landing("LANDING", "no veo ningun tag al frente: no se puede calibrar")
                self._goto("RC_STEP", "calibrando")
            return
        if st != "RC_STEP":
            return
        if self._i >= len(self.steps):
            self._report()
            return self._begin_landing("LANDING", "calibracion terminada")
        axis, rc = self.steps[self._i]
        if self._phase == "start":
            skip = self._safe(axis, rc, now)
            self._pre = None if skip else self._measure(axis, now)
            if skip or self._pre is None:
                self.results.append((axis, rc, None, skip or "omitido: sin medicion"))
                self._i += 1
                return self._send_rc(0, 0, 0, 0)
            self._phase, self._t_phase = "move", now
        if self._phase == "move":
            self._send_rc(rc if axis == "lr" else 0, rc if axis == "fb" else 0, rc if axis == "ud" else 0, 0)
            if now - self._t_phase >= MOVE_S:
                self._phase, self._t_phase = "settle", now
        elif self._phase == "settle":
            self._send_rc(0, 0, 0, 0)
            if now - self._t_phase >= SETTLE_S:
                post = self._measure(axis, now)
                if post is None:
                    self.results.append((axis, rc, None, "sin medicion al final"))
                else:
                    # adelante: el tag se acerca (z baja); derecha: el tag se va a la izquierda (x baja)
                    delta = post - self._pre if axis == "ud" else self._pre - post
                    self.results.append((axis, rc, delta / MOVE_S, ""))
                    print(f"[rc] {axis} {rc:+3d}: {delta / MOVE_S:+5.1f} cm/s ({delta:+.0f} cm)")
                self._i += 1
                self._phase = "start"

    def _report(self) -> None:
        names = {"fb": "adelante(+)/atras(-)", "lr": "derecha(+)/izquierda(-)", "ud": "arriba(+)/abajo(-)"}
        lines = ["Calibracion rc  (velocidad efectiva: desplazamiento total / 1.5 s de mando)", ""]
        for axis in dict.fromkeys(a for a, *_ in self.results):
            lines.append(f"{axis}  {names[axis]}")
            for a, rc, speed, note in self.results:
                if a == axis:
                    lines.append(f"   rc {rc:+3d}: " + (f"{speed:+6.1f} cm/s" if speed is not None else note))
            moving = [abs(rc) for a, rc, sp, _ in self.results if a == axis and sp is not None and abs(sp) >= 3]
            lines.append(f"   menor rc que mueve (>= 3 cm/s): {min(moving) if moving else 'ninguno de 10/15/20'}")
            lines.append("")
        text = "\n".join(lines)
        print("\n" + text)
        out = ROOT / "capturas" / time.strftime("rc_calib_%Y%m%d_%H%M%S.txt")
        out.parent.mkdir(exist_ok=True)
        out.write_text(text + "\n")
        print(f"[rc] guardado en {out}")


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config" / "flight.json"))
    ap.add_argument("--calib", default=str(DEFAULT_CALIB))
    ap.add_argument("--tag-cm", type=float, default=8.0, help="lado real del tag en cm")
    ap.add_argument("--ejes", nargs="+", choices=["fb", "lr", "ud"], default=["fb", "lr", "ud"])
    ap.add_argument("--record", help="grabar el video (mp4)")
    args = ap.parse_args()

    cfg = FlightConfig.load(Path(args.config))
    cfg.hover_s, cfg.max_flight_s = 3.0, 150.0
    tello, reader = connect()
    log_path = ROOT / "logs" / time.strftime("rccal_%Y%m%d_%H%M%S.csv")
    print(f"[hmi] bitácora: {log_path}")
    flight = RcCalib(tello, cfg, log_path, Path(args.calib), args.tag_cm, args.ejes)
    run_app(flight, tello, reader, args.record, "calibracion rc")


if __name__ == "__main__":
    main()
