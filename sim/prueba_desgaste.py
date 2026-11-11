#!/usr/bin/env python3
"""¿Detecta los tags gastados? Banco de prueba de la detección, sin volar.

Dibuja un tag bajo el espejo (con la cámara y el espejo del simulador) en cientos de
posiciones al azar: dron a 85–115 cm, tag corrido y girado, desenfoque y compresión como el
video del Tello. Lo hace con distintos desgastes (desteñido como los del laboratorio, manchas
blancas, pedazos faltantes) y mide, para cada versión del detector:
  - % de cuadros en que encuentra el tag con su ID correcto;
  - IDs equivocados (lo peor: ejecutaría otra acción);
  - tiempo por cuadro.
No es en tiempo real: tarda 1–3 min.

Uso:
    python sim/prueba_desgaste.py                 # todos los desgastes, 150 cuadros cada uno
    python sim/prueba_desgaste.py --n 400         # más cuadros (más exacto, más lento)
    python sim/prueba_desgaste.py --videos        # además, los videos reales con espejo (*.mp4)
"""
from __future__ import annotations

import argparse
import glob
import math
import sys
import time
from collections import Counter
from pathlib import Path

import cv2
import numpy as np

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sim_world as SW  # noqa: E402

TT = SW.TT
ROOT = SW.ROOT
IDS = set(TT.TAG_FUNCTIONS)

NIVELES = [  # (nombre, desgaste); los números salen de los videos de E5 (ver sim_world.DESGASTE)
    ("limpio", None),
    ("lab (negro 150)", {"negro": 150}),
    ("desteñido 185", {"negro": 185, "blanco": 240}),
    ("desteñido 205", {"negro": 205, "blanco": 240}),
    ("manchas 10 %", {"negro": 150, "manchas": 0.10}),
    ("manchas 20 %", {"negro": 150, "manchas": 0.20}),
    ("manchas 30 %", {"negro": 150, "manchas": 0.30}),
    ("faltante 4 %", {"negro": 150, "faltante": 0.04}),
    ("faltante 8 %", {"negro": 150, "faltante": 0.08}),
    ("faltante 12 %", {"negro": 150, "faltante": 0.12}),
    ("todo junto", {"negro": 170, "blanco": 245, "manchas": 0.15, "faltante": 0.06}),
]


class Anterior:
    """El detector como estaba antes del 11-nov (para comparar)."""
    nombre = "anterior"

    def __init__(self) -> None:
        params = cv2.aruco.DetectorParameters()
        params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        params.aprilTagQuadDecimate = 2.0
        params.errorCorrectionRate = 0.8
        params.maxErroneousBitsInBorderRate = 0.5
        self._det = cv2.aruco.ArucoDetector(cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_25h9), params)

    def detect(self, gray):
        corners, ids, _ = self._det.detectMarkers(gray)
        return [] if ids is None else [int(i) for i in ids.ravel() if int(i) in IDS]


class Actual:
    """scripts/test_tags.TagDetector, el que usan las misiones."""
    nombre = "actual"

    def __init__(self) -> None:
        self._det = TT.TagDetector(IDS, True, 2.0)

    def detect(self, gray):
        return [d.tag_id for d in self._det.detect(gray) if d.accepted]


def cuadro(sim: SW.SimTello, tag: SW.Tag, rng) -> np.ndarray:
    """Un cuadro como lo recibe la misión: con espejo, desenfoque y compresión."""
    z = rng.uniform(85, 115)
    yaw = rng.uniform(-180, 180)
    adelante, derecha = rng.uniform(-25, 25), rng.uniform(-35, 35)  # dónde queda el tag
    ps = math.radians(yaw)
    sim.x = tag.c[0] - (adelante * math.sin(ps) + derecha * math.cos(ps))
    sim.y = tag.c[1] - (adelante * math.cos(ps) - derecha * math.sin(ps))
    sim.z, sim.yaw = z, yaw
    img = sim.render()
    s = rng.uniform(0.0, 1.2)
    if s > 0.2:
        img = cv2.GaussianBlur(img, (0, 0), s)
    q = int(rng.uniform(40, 90))  # el video del Tello llega comprimido
    img = cv2.imdecode(cv2.imencode(".jpg", img, [cv2.IMWRITE_JPEG_QUALITY, q])[1], cv2.IMREAD_COLOR)
    return cv2.cvtColor(cv2.flip(img, 0), cv2.COLOR_BGR2GRAY)  # la misión voltea la imagen


def banco(detectores, n: int) -> None:
    sim = SW.SimTello([], mirror="v", hilo=False)
    print(f"{n} cuadros por desgaste; % con el ID correcto (IDs equivocados entre paréntesis)\n")
    print(f"{'desgaste':18s}" + "".join(f"{d.nombre:>16s}" for d in detectores))
    tiempos = {d.nombre: [] for d in detectores}
    for nombre, desg in NIVELES:
        rng = np.random.default_rng(7)  # mismos cuadros para todos los detectores
        ok = Counter()
        mal = Counter()
        for k in range(n):
            tid = int(rng.integers(1, 11))
            d = {**desg, "semilla": int(rng.integers(1 << 30))} if desg else None
            tag = SW.Tag(tid, (0, 0, 0), (0, 0, 1), top=(math.sin(a := rng.uniform(0, 2 * math.pi)), math.cos(a), 0),
                         desgaste=d)
            sim.tags = [tag]
            gray = cuadro(sim, tag, rng)
            for det in detectores:
                t0 = time.perf_counter()
                ids = det.detect(gray)
                tiempos[det.nombre].append(time.perf_counter() - t0)
                ok[det.nombre] += tid in ids
                mal[det.nombre] += any(i != tid for i in ids)
        fila = "".join(f"{100 * ok[d.nombre] / n:12.0f} %{'' if not mal[d.nombre] else f'({mal[d.nombre]})':>3s}"
                       for d in detectores)
        print(f"{nombre:18s}{fila}", flush=True)
    sin_tag = np.full((720, 960), 110, np.uint8)  # cuadro sin tag (así se ve casi todo el avance)
    for det in detectores:
        t0 = time.perf_counter()
        for _ in range(20):
            det.detect(sin_tag)
        vacio = (time.perf_counter() - t0) / 20
        print(f"  tiempo {det.nombre}: {1000 * np.mean(tiempos[det.nombre]):.1f} ms por cuadro con tag, "
              f"{1000 * vacio:.1f} ms sin tag")


def videos(detectores) -> None:
    """Videos reales con espejo: cuántos cuadros con tag encuentra cada detector y qué IDs."""
    files = sorted(glob.glob(str(ROOT / "e5_circuito*.mp4"))) + sorted(glob.glob(str(ROOT / "con_clip*.mp4")))
    if not files:
        print("\n(no hay videos e5_circuito*.mp4 ni con_clip*.mp4 en la carpeta del proyecto)")
        return
    print("\nVideos reales con espejo (1 de cada 2 cuadros): cuadros con tag | IDs vistos")
    total = Counter()
    for f in files:
        cap = cv2.VideoCapture(f)
        cnt = {d.nombre: Counter() for d in detectores}
        con = Counter()
        k = 0
        while True:
            ok, fr = cap.read()
            if not ok:
                break
            k += 1
            if k % 2:
                continue
            gray = cv2.cvtColor(cv2.flip(fr, 0), cv2.COLOR_BGR2GRAY)
            for det in detectores:
                ids = det.detect(gray)
                con[det.nombre] += bool(ids)
                cnt[det.nombre].update(ids)
        cap.release()
        total.update(con)
        print(f"  {Path(f).name:18s}" + " | ".join(f"{d.nombre} {con[d.nombre]:4d} {dict(cnt[d.nombre])}"
                                                  for d in detectores))
    print("  total: " + ", ".join(f"{d.nombre} {total[d.nombre]}" for d in detectores))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--n", type=int, default=150, help="cuadros por desgaste")
    ap.add_argument("--videos", action="store_true", help="probar también con los videos reales (*.mp4)")
    args = ap.parse_args()
    detectores = [Anterior(), Actual()]
    banco(detectores, args.n)
    if args.videos:
        videos(detectores)


if __name__ == "__main__":
    main()
