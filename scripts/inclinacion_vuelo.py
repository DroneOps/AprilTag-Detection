#!/usr/bin/env python3
"""Inclinación de la vista del espejo medida en vuelo, con los tags de los videos (--record).

E1 (test_tags.py --espejo) la mide con el dron en la mano, y la mano también se inclina: el
12-nov dio −5.7° y −7.0° adelante (y −13° de lado en el Tello 7), mientras que en vuelo, con
el dron nivelado, los dos drones dieron ~−10.5° adelante y ~−1° de lado.

Uso:
    python scripts/inclinacion_vuelo.py k2_dron7_pid2.mp4 k2_dron7_kal2.mp4
    python scripts/inclinacion_vuelo.py *.mp4 --min-alt 60

Toma la mediana de todos los tags detectados arriba de --min-alt cm (en el aire, no en la
mano ni aterrizando). Cada frame suelto varía ±6° porque el dron se inclina al moverse; la
mediana de varios cientos es estable (±1° entre videos). El resultado va en
config/mission_espejo.json (vista_adelante_deg, vista_lado_deg) o, si cambia por dron, en
config/mision_dron<N>.json.
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import test_tags as TT  # noqa: E402
from mission_tags import TAG_FUNCTIONS  # noqa: E402


def medir(video: Path, det, pe, min_alt: float, cada: int) -> list[tuple[float, float]]:
    cap = cv2.VideoCapture(str(video))
    out, n = [], 0
    while True:
        ok, frame = cap.read()
        if not ok:
            break
        n += 1
        if n % cada:
            continue
        gray = cv2.cvtColor(cv2.flip(frame, 0), cv2.COLOR_BGR2GRAY)
        for d in det.detect(gray):
            if d.accepted and (p := pe.estimate(d)) is not None:
                _, _, h, tf, tr = TT.floor_view(p)
                if h > min_alt:
                    out.append((tf, tr))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("videos", nargs="+", help="videos de vuelo con espejo (--record)")
    ap.add_argument("--min-alt", type=float, default=60.0, help="solo tags vistos arriba de esta altura (cm)")
    ap.add_argument("--cada", type=int, default=2, help="usar 1 de cada N frames")
    ap.add_argument("--espejo", choices=["v", "h"], default="v")
    ap.add_argument("--tag-cm", type=float, default=8.0)
    args = ap.parse_args()

    det = TT.TagDetector(set(TAG_FUNCTIONS), True, 2.0, True)
    pe = TT.PoseEstimator(ROOT / "config" / "camera_tello.json", args.tag_cm).mirrored(args.espejo)
    todas = []
    for v in map(Path, args.videos):
        t = medir(v, det, pe, args.min_alt, args.cada)
        todas += t
        if t:
            a = np.array(t)
            print(f"{v.name:28s} {len(a):5d} tags: adelante {np.median(a[:, 0]):+5.1f}°, lado {np.median(a[:, 1]):+5.1f}°")
        else:
            print(f"{v.name:28s} sin tags arriba de {args.min_alt:.0f} cm")
    if len(args.videos) > 1 and todas:
        a = np.array(todas)
        print(f"{'todos':28s} {len(a):5d} tags: adelante {np.median(a[:, 0]):+5.1f}°, lado {np.median(a[:, 1]):+5.1f}°"
              f'  ->  "vista_adelante_deg": {np.median(a[:, 0]):.1f}, "vista_lado_deg": {np.median(a[:, 1]):.1f}')


if __name__ == "__main__":
    main()
