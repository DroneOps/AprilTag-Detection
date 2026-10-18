#!/usr/bin/env python3
"""Genera un PDF imprimible con los AprilTags tag25h9 del reglamento (IDs 1-10).

Uso:
    python scripts/make_tags.py                 # tags/tags_15cm.pdf, uno por hoja carta
    python scripts/make_tags.py --size-cm 8     # tags más chicos (prueba de distancia)

Imprimir al 100 % ("tamaño real"), NO "ajustar a la página", y medir el
cuadro negro con una regla: debe medir exactamente --size-cm.
"""
from __future__ import annotations

import argparse
from pathlib import Path

import cv2
import numpy as np
from PIL import Image, ImageDraw, ImageFont

from test_tags import TAG_FUNCTIONS

DPI = 300
LETTER_IN = (8.5, 11.0)


def page_for(tag_id: int, size_cm: float) -> Image.Image:
    w, h = (int(v * DPI) for v in LETTER_IN)
    page = Image.new("L", (w, h), 255)

    # tag25h9 = 5x5 datos + 1 módulo de borde negro por lado = 7 módulos
    side_px = round(size_cm / 2.54 * DPI)
    module = side_px // 7
    side_px = module * 7  # múltiplo exacto para que los módulos no se deformen
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_25h9)
    small = cv2.aruco.generateImageMarker(dictionary, tag_id, 7)
    tag = cv2.resize(small, (side_px, side_px), interpolation=cv2.INTER_NEAREST)
    page.paste(Image.fromarray(tag), ((w - side_px) // 2, (h - side_px) // 2))

    draw = ImageDraw.Draw(page)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 60)
    except OSError:
        font = ImageFont.load_default()
    text = f"ID {tag_id} - {TAG_FUNCTIONS[tag_id]}   (cuadro negro = {side_px / DPI * 2.54:.1f} cm)"
    draw.text((w // 2, h - 250), text, fill=0, font=font, anchor="mm")
    # marca de orientación: este lado es el "arriba" del tag
    draw.text((w // 2, (h - side_px) // 2 - 80), "arriba", fill=0, font=font, anchor="mm")
    return page


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--size-cm", type=float, default=15.0, help="lado del cuadro negro en cm")
    ap.add_argument("--out", default="tags", help="carpeta de salida")
    args = ap.parse_args()

    max_cm = LETTER_IN[0] * 2.54 - 2 * 1.5  # deja ≥1.5 cm de blanco a los lados
    if args.size_cm > max_cm:
        raise SystemExit(f"--size-cm máximo para hoja carta: {max_cm:.1f}")

    out = Path(args.out)
    out.mkdir(exist_ok=True)
    pages = [page_for(i, args.size_cm) for i in TAG_FUNCTIONS]
    pdf = out / f"tags_{args.size_cm:g}cm.pdf"
    pages[0].save(pdf, resolution=DPI, save_all=True, append_images=pages[1:])
    print(f"{pdf}  ({len(pages)} hojas carta)")


if __name__ == "__main__":
    main()
