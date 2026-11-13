#!/usr/bin/env python3
"""Junta grabaciones de sim/grabar.py lado a lado (p. ej. antes | ahora) en un mp4 y un GIF.

    python sim/componer.py sim/logs/videos_pistas/p2_antes sim/logs/videos_pistas/p2_ahora \\
        --salida sim/logs/videos_pistas/pista2_antes_ahora

Lee los cuadros uno por uno (no los junta en memoria). La más corta se queda en su último
cuadro hasta que termina la otra. --vel: qué tan acelerado va el mp4; --gif-vel y --escala
para que el GIF quede de ~5 MB o menos.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image

FPS = 10  # cuadros por segundo de vuelo que guarda sim/grabar.py


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("carpetas", nargs="+", help="una o más carpetas de cuadros, de izquierda a derecha")
    ap.add_argument("--salida", required=True, help="nombre sin extensión: escribe .mp4 y .gif")
    ap.add_argument("--vel", type=float, default=4.0, help="velocidad del mp4 (4 = 4x)")
    ap.add_argument("--gif-vel", type=float, default=6.0, help="velocidad del GIF")
    ap.add_argument("--escala", type=float, default=0.45, help="tamaño del GIF respecto al mp4")
    ap.add_argument("--colores", type=int, default=64)
    ap.add_argument("--sin-gif", action="store_true")
    args = ap.parse_args()

    listas = [sorted(Path(c).glob("*.jpg")) for c in args.carpetas]
    if not all(listas):
        raise SystemExit("alguna carpeta no tiene cuadros")
    n = max(len(lst) for lst in listas)
    salida = Path(args.salida)
    salida.parent.mkdir(parents=True, exist_ok=True)

    def cuadro(i: int) -> np.ndarray:
        partes = [cv2.imread(str(lst[min(i, len(lst) - 1)])) for lst in listas]
        sep = np.full((partes[0].shape[0], 6, 3), 255, np.uint8)
        out = partes[0]
        for p in partes[1:]:
            out = np.hstack([out, sep, p])
        return out

    h, w = cuadro(0).shape[:2]
    vw = cv2.VideoWriter(str(salida.with_suffix(".mp4")), cv2.VideoWriter_fourcc(*"mp4v"), FPS * args.vel, (w, h))
    gif, paso = [], max(1, round(args.gif_vel))
    for i in range(n):
        c = cuadro(i)
        vw.write(c)
        if not args.sin_gif and i % paso == 0:
            small = cv2.resize(c, (int(w * args.escala), int(h * args.escala)), interpolation=cv2.INTER_AREA)
            gif.append(Image.fromarray(cv2.cvtColor(small, cv2.COLOR_BGR2RGB)).quantize(args.colores))
    vw.release()
    print(f"{salida.with_suffix('.mp4')}: {n} cuadros, {n / FPS:.0f} s de vuelo a {args.vel:g}x")
    if gif:
        dur = int(1000 / FPS * paso / args.gif_vel)
        gif[0].save(salida.with_suffix(".gif"), save_all=True, append_images=gif[1:], duration=dur, loop=0,
                    optimize=True)
        mb = salida.with_suffix(".gif").stat().st_size / 1e6
        print(f"{salida.with_suffix('.gif')}: {len(gif)} cuadros, {mb:.1f} MB")


if __name__ == "__main__":
    main()
