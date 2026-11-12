#!/usr/bin/env python3
"""¿Cuánto se va solo el dron? Deriva medida con el piso visto por el espejo.

Con rc en 0 (despegando, quieto, subiendo, o sobre un tag sin corregir), compara cada cuadro
del video con el anterior (correlación de fase) y, con la altura de la bitácora, lo pasa a cm.
Separa lo constante (la mediana: hacia dónde se va siempre) de lo aleatorio (lo que varía en
1 s), por dron. Son los valores deriva_lado_cm_s, deriva_adelante_cm_s y deriva_cm_s de
config/sim_tello.json y config/sim_tello_dron<N>.json.

Necesita los videos (--record) en la carpeta del proyecto; no se suben al repo. Qué video y
qué dron fue cada bitácora sale de la tabla de sesiones/<fecha>/notas.md; sin tabla, el video
se empareja por la hora y el dron sale del nombre del video ("dron7" -> 7).

Medida aproximada (11-nov): de lado coincide en signo con la del tag en 72 % de los tramos;
hacia adelante es peor cuando las rayas del piso van en la dirección del avance.

Uso:
    python sim/deriva_video.py sesiones/2026-11-11
    python sim/deriva_video.py sesiones/2026-11-11 --videos ~/videos_lab
"""
from __future__ import annotations

import argparse
import csv
import glob
import os
import re
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
F = 915 / 4  # px de la cámara a 1/4 de resolución (config/camera_tello.json)
ESTADOS = ("TAKEOFF", "HOVER", "CRUISE", "APPROACH", "EXECUTE", "ADVANCE")


def emparejar(sesion: Path, videos: Path) -> list[tuple[Path, Path, str]]:
    """(bitácora, video, dron) de cada vuelo con espejo."""
    notas = (sesion / "notas.md").read_text() if (sesion / "notas.md").exists() else ""
    tabla = {m.group(1): (m.group(2), m.group(3))
             for m in re.finditer(r"`(\S+\.csv)` \| `(\S+)` \| Tello (\d+)", notas)}
    vids = {f: os.path.getmtime(f) for f in glob.glob(str(videos / "*.mp4"))}
    out = []
    for log in sorted((sesion / "vuelos").glob("*.csv")):
        if log.name in tabla:
            vid, dron = videos / tabla[log.name][0], tabla[log.name][1]
        else:  # por la hora de término, con la bitácora original de logs/
            orig = ROOT / "logs" / log.name
            if not vids or not orig.exists():
                continue
            t = os.path.getmtime(orig)
            v = min(vids, key=lambda f: abs(vids[f] - t))
            m = re.search(r"dron(\d+)", Path(v).name)
            if abs(vids[v] - t) > 20 or not m:
                continue
            vid, dron = Path(v), m.group(1)
        if vid.exists():
            out.append((log, vid, dron))
    return out


def tramos_quietos(log: Path, vid: Path) -> list[np.ndarray]:
    """Velocidades (t, derecha, adelante) en cm/s mientras el rc está en 0, por tramo."""
    R = list(csv.DictReader(log.open()))
    if not R or "tag_adelante" not in R[0]:
        return []  # sin espejo: la cámara ve al frente
    t0 = float(R[0]["t"])
    ts = np.array([float(r["t"]) - t0 for r in R])
    cap = cv2.VideoCapture(str(vid))
    fps, n = cap.get(cv2.CAP_PROP_FPS) or 30, int(cap.get(cv2.CAP_PROP_FRAME_COUNT))
    if n == 0:
        return []
    esc = ts[-1] / (n / fps)  # el video y la bitácora empiezan casi juntos; se estira al largo de la bitácora
    win = cv2.createHanningWindow((240, 180), cv2.CV_32F)
    prev, k, buf, segs = None, 0, [], []
    while True:
        ok, fr = cap.read()
        if not ok:
            break
        k += 1
        if k % 2:
            continue
        t = k / fps * esc
        r = R[min(len(ts) - 1, int(np.searchsorted(ts, t)))]
        g = cv2.resize(cv2.cvtColor(cv2.flip(fr, 0), cv2.COLOR_BGR2GRAY), (240, 180),
                       interpolation=cv2.INTER_AREA).astype(np.float32)
        alt = float(r["tof"]) - 10
        quieto = (r["state"] in ESTADOS and 40 < alt < 300
                  and all(float(r[c] or 0) == 0 for c in ("rc_lr", "rc_fb", "rc_yaw")))
        if quieto and prev is not None:
            (dx, dy), q = cv2.phaseCorrelate(prev, g, win)
            if q > 0.05:
                dt, cm = 2 / fps * esc, alt / F
                buf.append((t, -dx * cm / dt, dy * cm / dt))  # imagen: arriba = adelante del dron
        elif buf:
            if len(buf) >= 10:
                segs.append(np.array(buf))
            buf = []
        prev = g if quieto else None
    cap.release()
    if len(buf) >= 10:
        segs.append(np.array(buf))
    return segs


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("sesion", help="carpeta sesiones/<fecha>")
    ap.add_argument("--videos", default=str(ROOT), help="carpeta con los .mp4 (por defecto, la del proyecto)")
    args = ap.parse_args()
    pares = emparejar(Path(args.sesion), Path(args.videos).expanduser())
    if not pares:
        raise SystemExit("no encontré videos para las bitácoras de esa sesión")
    por_dron: dict[str, list[np.ndarray]] = {}
    for log, vid, dron in pares:
        segs = tramos_quietos(log, vid)
        por_dron.setdefault(dron, []).extend(segs)
        print(f"  {log.name} <- {vid.name} (Tello {dron}): {sum(len(s) for s in segs)} cuadros quietos", flush=True)
    print("\nDeriva con rc en 0 (cm/s; + = a la derecha / hacia adelante del dron):")
    for dron, segs in sorted(por_dron.items()):
        v1 = np.array([s[j:j + 15, 1:].mean(axis=0) for s in segs for j in range(0, len(s) - 15, 15)])
        if len(v1) < 5:
            print(f"  Tello {dron}: pocos datos")
            continue
        lado, ade = np.median(v1[:, 0]), np.median(v1[:, 1])
        alea = np.median(np.hypot(v1[:, 0] - lado, v1[:, 1] - ade)) / 1.18
        print(f"  Tello {dron}: constante {lado:+.1f} de lado, {ade:+.1f} adelante; aleatoria ~{alea:.1f} "
              f"({len(v1)} s de vuelo quieto)")
        print(f'    -> config/sim_tello_dron{dron}.json: "deriva_lado_cm_s": {lado:.1f}, '
              f'"deriva_cm_s": {alea:.1f}  (adelante es menos confiable; revisar antes de ponerlo)')


if __name__ == "__main__":
    main()
