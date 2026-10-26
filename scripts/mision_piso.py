#!/usr/bin/env python3
"""Misión con tags en el PISO y la cámara al frente (sin espejo).

La cámara mira al frente, inclinada 11° hacia abajo: un tag en el piso solo se
ve entre ~1.0 y ~1.7 m adelante (a 60 cm de altura, tag de 8 cm). Por eso:

    ADVANCE   avanza buscando un tag en el piso
    APPROACH  fase "visible": se acerca a velocidad constante, centrándolo de
              lado y alineándose con sus bordes (giro módulo 90°)
              fase "ciegas": el tag salió por abajo de la imagen; recorre a
              ciegas la distancia que faltaba con la velocidad calibrada de rc
              fase "quieto": se detiene sobre el tag y estabiliza
    EXECUTE   ejecuta la función del tag y sigue hacia el frente

El error en el tramo a ciegas depende de qué tan real es la velocidad
medida en ese mismo acercamiento (la real de rc 15 varió 12–20 cm/s entre vuelos);
ciegas_cms solo se usa si no se pudo medir. Las acciones, el flip seguro,
el paro y los vigilantes son los de mission_tags.py / first_flight.py.

Uso:
    python scripts/mision_piso.py --record piso_m1.mp4
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
from mision_espejo import rot_mod90
from test_tags import DEFAULT_CALIB, TAG_FUNCTIONS, draw, floor_from_front


@dataclass
class FloorConfig:
    cruise_alt_cm: float = 60.0  # más bajo = ve el tag más cerca y el tramo a ciegas es más corto
    advance_fb: int = 15
    advance_timeout_s: float = 10.0
    detect_max_cm: float = 220.0
    approach_fb: int = 15  # misma velocidad que a ciegas: lo que se ve y lo que no, parejo
    lat_kp: float = 0.8
    lat_min: int = 10
    lat_max: int = 15
    lat_tol_cm: float = 4.0
    rot_kp: float = 1.0
    rot_tol_deg: float = 4.0
    align_max_cm: float = 170.0  # alinear el giro solo de cerca (de lejos el ángulo es ruidoso)
    ciegas_cms: float = 17.0  # respaldo si no se pudo medir la velocidad en el acercamiento
    ciegas_ajuste_cm: float = 0.0  # se suma al tramo a ciegas: negativo si siempre se pasa, positivo si se queda corto
    vel_ventana_s: float = 2.5  # se mide con la distancia al tag de los últimos N s visibles
    vel_arranque_s: float = 1.0  # tras cambiar el avance acelera: no medir durante esto
    vel_min_cms: float = 6.0  # mediciones fuera de este rango se descartan
    vel_max_cms: float = 40.0
    keep_deg: float = 12.0  # tag más de esto hacia un lado: dejar de avanzar y girar hacia él
    lado_max_cm: float = 25.0  # si al perderlo estaba más de lado que esto, se fue por un costado
    salida_abajo: float = 0.75  # si el tag desaparece con su centro abajo de esta fracción de la imagen: pasó por debajo
    gracia_s: float = 0.3  # tiempo sin verlo para considerar que salió
    quieto_s: float = 0.8  # estabilizar sobre el tag antes de ejecutar
    piso_min: float = 0.8  # qué tan horizontal debe ser el tag (descarta tags en pared)
    window: int = 5

    @classmethod
    def load(cls, path: Path) -> FloorConfig:
        data = json.loads(path.read_text()) if path.exists() else {}
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise SystemExit(f"{path}: claves desconocidas {sorted(unknown)}")
        return cls(**data)


class FloorMission(TagMission):
    LOG_EXTRA = ["n_tags", "objetivo", "piso_adelante", "piso_lado", "piso_giro", "fase", "a_ciegas_cm", "vel_medida"]

    def __init__(self, tello, cfg: FlightConfig, mcfg: MissionConfig, fcfg: FloorConfig,
                 log_path: Path, calib: Path) -> None:
        mcfg.cruise_alt_cm = fcfg.cruise_alt_cm
        super().__init__(tello, cfg, mcfg, log_path, calib)
        self.f = fcfg
        self._hist: dict[int, deque] = {}
        self._cy: dict[int, float] = {}
        self._phase = ""
        self._last = (0.0, 0.0, 0.0, 0.0)  # (adelante, derecha, giro, y en imagen) al último verlo
        self._samples: deque = deque(maxlen=300)  # (t del frame, adelante) mientras avanza viéndolo
        self._speed: float | None = None
        self._fb_req, self._t_fb = 0.0, 0.0  # último avance pedido y desde cuándo
        self._t_phase = 0.0
        self._blind_cm = 0.0
        self._blind_s = 0.0

    # ---- visión: posición de cada tag sobre el piso
    def on_frame(self, bgr: np.ndarray, t: float) -> None:
        if (bgr.shape[1], bgr.shape[0]) != self.pose_est.size:
            self.reason = f"video {bgr.shape[1]}x{bgr.shape[0]} no coincide con la calibracion"
            return
        dets = self.detector.detect(cv2.cvtColor(bgr, cv2.COLOR_BGR2GRAY))
        poses = [self.pose_est.estimate(d) if d.accepted else None for d in dets]
        confirmed = self.confirmer.update({d.tag_id for d in dets if d.accepted})
        floor = {}
        for d, p in zip(dets, poses):
            if p is None:
                continue
            fwd, right, _, rot, flat = floor_from_front(p, self.m.camera_pitch_deg)
            if flat < self.f.piso_min:
                continue  # tag vertical: no es de esta misión
            hist = self._hist.setdefault(d.tag_id, deque(maxlen=self.f.window))
            hist.append((fwd, right, rot_mod90(rot)))
            floor[d.tag_id] = tuple(float(v) for v in np.median(np.array(hist), axis=0))
            self._cy[d.tag_id] = d.center[1] / bgr.shape[0]
        for tid in set(self._hist) - set(floor):
            del self._hist[tid]
        with self._vis_lock:
            self._vis = Vision(t, dets, poses, confirmed, floor)  # tagframe = (adelante, derecha, giro)
            for d in dets:
                if d.tag_id in self._last_seen:
                    self._last_seen[d.tag_id] = t

    def overlay(self, img: np.ndarray) -> None:
        v = self._vis
        if v is not None:
            draw(img, v.dets, v.confirmed, v.poses)

    def status_lines(self) -> list[str]:
        extra = f"PISO (camara al frente) | fase {self._phase or '-'}"
        if self._phase == "ciegas":
            extra += f" | a ciegas {self._blind_cm:.0f} cm"
        return [extra] + super().status_lines()

    def _log_extra(self) -> list:
        v, tid = self._vis, self._target
        fl = v.tagframe.get(tid) if (v and tid) else None
        cells = [f"{fl[0]:.0f}", f"{fl[1]:+.0f}", f"{fl[2]:+.0f}"] if fl else [""] * 3
        return [len(v.dets) if v else "", tid or "", *cells, self._phase, f"{self._blind_cm:.0f}" if self._blind_cm else "",
                f"{self._speed:.1f}" if self._speed else ""]

    # ---- avanzar buscando tags en el piso
    def _advance(self, yaw: float, now: float, elapsed: float) -> None:
        f, v = self.f, self._vision(now)
        if v is None:
            return self._send_rc(0, 0, 0, 0)
        cands = [(v.tagframe[d.tag_id][0], d.tag_id) for d in v.dets
                 if d.tag_id in v.confirmed and d.tag_id in v.tagframe and not self._ignored(d.tag_id, now)
                 and v.tagframe[d.tag_id][0] <= f.detect_max_cm]
        if cands:
            fwd, tid = min(cands)
            self._target, self._t_target_seen, self._t_hold = tid, now, None
            self._phase, self._blind_cm, self._speed = "visible", 0.0, None
            self._samples.clear()
            return self._goto("APPROACH", f"tag {tid} ({TAG_FUNCTIONS[tid]}) en el piso a {fwd:.0f} cm")
        if elapsed > f.advance_timeout_s:
            return self._begin_landing("LANDING", f"sin tags en el piso por {f.advance_timeout_s:.0f} s: fin")
        err = wrap_deg(self._heading - yaw)
        rate = 0 if abs(err) <= 3 else with_min(self.m.heading_kp * err, self.m.az_min, self.m.heading_max)
        self._send_rc(0, f.advance_fb, 0, rate)

    # ---- acercarse, recorrer a ciegas, quedarse encima
    def _approach(self, yaw: float, alt: float, now: float, elapsed: float) -> None:
        f, m, v = self.f, self.m, self._vision(now)
        if v is None:
            return self._send_rc(0, 0, 0, 0)
        if self._phase == "visible" and elapsed > m.approach_timeout_s:
            self._phase = ""
            return self._start_execute(now, "acercamiento incompleto (el tag nunca salio de la imagen)")

        if self._phase == "visible":
            fl = v.tagframe.get(self._target)
            if fl is not None:
                self._t_target_seen = now
                fwd, right, rot = fl
                self._last = (fwd, right, rot, self._cy.get(self._target, 0.0))
                lr = 0 if abs(right) <= f.lat_tol_cm else with_min(f.lat_kp * right, f.lat_min, f.lat_max)
                az = math.degrees(math.atan2(right, max(fwd, 1.0)))
                if abs(az) > f.keep_deg:
                    # se va hacia un lado de la imagen: dejar de avanzar y girar hacia él
                    return self._send_rc(lr, 0, 0, with_min(m.az_kp * az, m.az_min, m.az_max))
                yr = 0
                if fwd <= f.align_max_cm and abs(rot) > f.rot_tol_deg:
                    yr = with_min(f.rot_kp * rot, m.az_min, m.az_max)  # + = girar a la derecha
                # para la velocidad: una muestra por frame, solo con el avance ya estable
                if self._fb_req == f.approach_fb and v.t - self._t_fb >= f.vel_arranque_s \
                        and (not self._samples or v.t > self._samples[-1][0]):
                    self._samples.append((v.t, fwd))
                return self._send_rc(lr, f.approach_fb, 0, yr)
            gone = now - self._t_target_seen
            if gone < f.gracia_s:
                return self._send_rc(0, f.approach_fb, 0, 0)
            fwd, right, rot, cy = self._last
            if cy < f.salida_abajo or abs(right) > f.lado_max_cm:
                # no salió por abajo: se perdió (lejos, o por un costado). Buscarlo girando
                # hacia donde se fue antes de rendirse; no irse a ciegas.
                if gone > m.lost_s + f.gracia_s:
                    why = "por un costado" if abs(right) > f.lado_max_cm else f"a {fwd:.0f} cm"
                    return self._begin_landing("EMERGENCY_LAND", f"tag {self._target} perdido {why}")
                turn = math.copysign(m.search_rate, right) if abs(right) > f.lat_tol_cm else 0
                return self._send_rc(0, 0, 0, turn)
            # salió por abajo: lo que faltaba menos lo que ya avanzó en la gracia,
            # con la velocidad medida en este mismo acercamiento
            self._speed = self._measured_speed(now)
            speed = self._speed or f.ciegas_cms
            self._blind_cm = max(0.0, fwd - speed * gone + f.ciegas_ajuste_cm)
            self._blind_s = self._blind_cm / speed
            self._phase, self._t_phase = "ciegas", now
            src = f"medida {speed:.1f} cm/s" if self._speed else f"supuesta {speed:.1f} cm/s (no se pudo medir)"
            self.reason = f"tag {self._target} debajo de la imagen: {self._blind_cm:.0f} cm a ciegas, velocidad {src}"
            print(f"[vuelo] APPROACH: {self.reason}")

        if self._phase == "ciegas":
            if now - self._t_phase < self._blind_s:
                return self._send_rc(0, f.approach_fb, 0, 0)  # la misma rc con la que se midió
            self._phase, self._t_phase = "quieto", now
            return self._send_rc(0, 0, 0, 0)

        if self._phase == "quieto":
            self._send_rc(0, 0, 0, 0)
            if now - self._t_phase >= f.quieto_s:
                fwd, right, rot, _ = self._last
                self._phase = ""
                vel = f"{self._speed:.1f} medida" if self._speed else f"{f.ciegas_cms:.1f} supuesta"
                self._start_execute(now, f"(a ciegas {self._blind_cm:.0f} cm a {vel} cm/s; al ultimo verlo: "
                                         f"lado {right:+.0f} cm, giro {rot:+.0f})")
            return

    def _send_rc(self, lr: float, fb: float, ud: float, yaw: float) -> None:
        if fb != self._fb_req:  # cambió el avance: vuelve a acelerar, la medición empieza de cero
            self._fb_req, self._t_fb = fb, time.monotonic()
            self._samples.clear()
        super()._send_rc(lr, fb, ud, yaw)

    def _measured_speed(self, now: float) -> float | None:
        """Velocidad real hacia el tag: pendiente de la distancia en los últimos
        vel_ventana_s mientras avanzaba con approach_fb ya estable."""
        f = self.f
        pts = [(t, d) for t, d in self._samples if now - t <= f.vel_ventana_s + f.gracia_s]
        if len(pts) < 8 or pts[-1][0] - pts[0][0] < 1.0:
            return None
        v = -float(np.polyfit([t for t, _ in pts], [d for _, d in pts], 1)[0])
        return v if f.vel_min_cms <= v <= f.vel_max_cms else None


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config" / "flight.json"))
    ap.add_argument("--mission", default=str(ROOT / "config" / "mission_tags.json"))
    ap.add_argument("--piso-config", default=str(ROOT / "config" / "mission_piso.json"))
    ap.add_argument("--calib", default=str(DEFAULT_CALIB))
    ap.add_argument("--record", help="grabar el video (mp4)")
    args = ap.parse_args()

    cfg = FlightConfig.load(Path(args.config))
    mcfg = MissionConfig.load(Path(args.mission))
    fcfg = FloorConfig.load(Path(args.piso_config))
    cfg.hover_s, cfg.max_flight_s = mcfg.start_hover_s, mcfg.mission_max_s
    tello, reader = connect()
    log_path = ROOT / "logs" / time.strftime("piso_%Y%m%d_%H%M%S.csv")
    print(f"[hmi] bitácora: {log_path}  |  tags de {mcfg.tag_cm:g} cm  |  crucero {fcfg.cruise_alt_cm:.0f} cm")
    run_app(FloorMission(tello, cfg, mcfg, fcfg, log_path, Path(args.calib)), tello, reader, args.record, "mision piso")


if __name__ == "__main__":
    main()
