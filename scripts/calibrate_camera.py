#!/usr/bin/env python3
"""Calibración de la cámara (matriz K y distorsión) con un tablero de ajedrez.

Sin calibración no se puede estimar a qué distancia está un tag (solvePnP).
La calibración vale para UNA resolución: el Tello transmite a 960x720.

Uso:
    python scripts/calibrate_camera.py --make-board            # tags/tablero_25mm.pdf
    python scripts/calibrate_camera.py --source tello --square-mm 25
    python scripts/calibrate_camera.py --source 0 --squares 9x6 --square-mm 30   # otro tablero
    python scripts/calibrate_camera.py --from-dir capturas/calib_20261021_101500 --square-mm 25

Durante la captura: mueve el TABLERO (o el dron) para cubrir todo el
cuadro: centro, esquinas, cerca, lejos e inclinado. Se captura solo cuando la
vista es nueva. Teclas: c fuerza captura · q termina y calibra.
"""
from __future__ import annotations

import argparse
import json
import time
from pathlib import Path

import cv2
import numpy as np

from test_tags import CvSource, Source, TelloSource, hud

PATTERN = (9, 6)  # esquinas internas: tablero de 10 x 7 cuadros
MIN_VIEWS = 12
DPI = 300


# ---------------------------------------------------------------- tablero

def make_board(square_mm: float, out_dir: Path) -> Path:
    from PIL import Image, ImageDraw, ImageFont

    cols, rows = PATTERN[0] + 1, PATTERN[1] + 1
    page_w, page_h = int(11 * DPI), int(8.5 * DPI)  # carta horizontal
    sq = round(square_mm / 25.4 * DPI)
    if cols * sq > page_w - 0.6 * DPI or rows * sq > page_h - 0.9 * DPI:
        raise SystemExit("El tablero no cabe en hoja carta; usa un --square-mm menor")
    page = Image.new("L", (page_w, page_h), 255)
    draw = ImageDraw.Draw(page)
    x0, y0 = (page_w - cols * sq) // 2, (page_h - rows * sq) // 2
    for r in range(rows):
        for c in range(cols):
            if (r + c) % 2 == 0:
                draw.rectangle([x0 + c * sq, y0 + r * sq, x0 + (c + 1) * sq - 1, y0 + (r + 1) * sq - 1], fill=0)
    try:
        font = ImageFont.truetype("DejaVuSans.ttf", 40)
    except OSError:
        font = ImageFont.load_default()
    draw.text((page_w // 2, page_h - 60),
              f"Tablero {cols}x{rows} cuadros, {square_mm:g} mm. Imprimir al 100 % y MEDIR un cuadro.",
              fill=0, font=font, anchor="mm")
    out_dir.mkdir(exist_ok=True)
    pdf = out_dir / f"tablero_{square_mm:g}mm.pdf"
    page.save(pdf, resolution=DPI)
    return pdf


# ---------------------------------------------------------------- detección

def find_corners(gray: np.ndarray) -> np.ndarray | None:
    ok, corners = cv2.findChessboardCornersSB(gray, PATTERN, flags=cv2.CALIB_CB_NORMALIZE_IMAGE)
    return corners.reshape(-1, 2) if ok else None


def view_signature(corners: np.ndarray, size: tuple[int, int]) -> np.ndarray:
    """Posición, tamaño e inclinación del tablero en la imagen, normalizados."""
    w, h = size
    cx, cy = corners.mean(axis=0) / [w, h]
    span = np.ptp(corners, axis=0) / [w, h]
    nx, ny = PATTERN
    top = np.linalg.norm(corners[nx - 1] - corners[0])
    bottom = np.linalg.norm(corners[-1] - corners[-nx])
    left = np.linalg.norm(corners[-nx] - corners[0])
    right = np.linalg.norm(corners[-1] - corners[nx - 1])
    return np.array([cx, cy, span.mean(), np.log(top / bottom), np.log(left / right)])


def is_new_view(sig: np.ndarray, taken: list[np.ndarray], min_dist: float = 0.12) -> bool:
    return all(np.linalg.norm(sig - s) > min_dist for s in taken)


# ---------------------------------------------------------------- calibración

def calibrate(corner_sets: list[np.ndarray], size: tuple[int, int], square_mm: float) -> dict:
    obj = np.zeros((PATTERN[0] * PATTERN[1], 3), np.float32)
    obj[:, :2] = np.mgrid[0:PATTERN[0], 0:PATTERN[1]].T.reshape(-1, 2) * square_mm
    views = list(corner_sets)

    def run(vs: list[np.ndarray]):
        objp = [obj] * len(vs)
        imgp = [v.reshape(-1, 1, 2).astype(np.float32) for v in vs]
        rms, K, dist, rvecs, tvecs = cv2.calibrateCamera(objp, imgp, size, None, None)
        errs = []
        for o, i, r, t in zip(objp, imgp, rvecs, tvecs):
            proj, _ = cv2.projectPoints(o, r, t, K, dist)
            errs.append(float(np.sqrt(np.mean(np.sum((proj - i) ** 2, axis=2)))))
        return rms, K, dist, errs

    rms, K, dist, errs = run(views)
    # una pasada de limpieza: fuera vistas con error muy por encima de la mediana
    limit = max(2.5 * float(np.median(errs)), 0.5)
    keep = [v for v, e in zip(views, errs) if e <= limit]
    dropped = len(views) - len(keep)
    if dropped and len(keep) >= MIN_VIEWS:
        rms, K, dist, errs = run(keep)
        views = keep
    else:
        dropped = 0

    fovx, fovy, *_ = cv2.calibrationMatrixValues(K, size, 0.0, 0.0)
    return {
        "resolution": list(size),
        "K": K.tolist(),
        "dist": dist.ravel().tolist(),
        "rms_px": round(float(rms), 4),
        "fov_deg": {"x": round(fovx, 2), "y": round(fovy, 2)},
        "views": len(views),
        "views_dropped": dropped,
        "square_mm": square_mm,
        "date": time.strftime("%Y-%m-%d %H:%M"),
    }


def report(result: dict) -> None:
    K = np.array(result["K"])
    print(f"\nvistas usadas: {result['views']} (descartadas {result['views_dropped']})")
    print(f"error de reproyección RMS: {result['rms_px']:.3f} px  "
          f"({'bueno' if result['rms_px'] < 0.5 else 'aceptable' if result['rms_px'] < 1.0 else 'MALO: repetir'})")
    print(f"fx={K[0, 0]:.1f}  fy={K[1, 1]:.1f}  cx={K[0, 2]:.1f}  cy={K[1, 2]:.1f}")
    print(f"campo de visión: {result['fov_deg']['x']:.1f}° x {result['fov_deg']['y']:.1f}°")
    print("distorsión:", ", ".join(f"{d:+.4f}" for d in result["dist"]))


def save(result: dict, out: Path) -> None:
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(result, indent=2) + "\n")
    print(f"guardado en {out}")


# ---------------------------------------------------------------- modos

def run_capture(args: argparse.Namespace) -> None:
    src: Source = TelloSource(False) if args.source == "tello" else CvSource(args.source)
    shot_dir = Path("capturas") / time.strftime("calib_%Y%m%d_%H%M%S")
    shot_dir.mkdir(parents=True)
    corner_sets: list[np.ndarray] = []
    sigs: list[np.ndarray] = []
    size: tuple[int, int] | None = None
    last_shot = 0.0
    try:
        while True:
            frame = src.read()
            if frame is None:
                if isinstance(src, CvSource) and src.is_file:
                    break
                if cv2.waitKey(5) & 0xFF in (ord("q"), 27):
                    break
                continue
            h, w = frame.shape[:2]
            if size is None:
                size = (w, h)
            elif size != (w, h):
                raise SystemExit(f"La resolución cambió de {size} a {(w, h)}; la calibración no sería válida")
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            corners = find_corners(gray)
            key = cv2.waitKey(1) & 0xFF
            shown = frame.copy()
            for cs in corner_sets:  # cobertura acumulada
                for x, y in cs[:: max(1, len(cs) // 12)]:
                    cv2.circle(shown, (int(x), int(y)), 2, (0, 200, 255), -1)
            status = "tablero NO detectado"
            if corners is not None:
                cv2.drawChessboardCorners(shown, PATTERN, corners.reshape(-1, 1, 2), True)
                sig = view_signature(corners, size)
                new = is_new_view(sig, sigs)
                status = "vista nueva" if new else "vista repetida: mueve o inclina el tablero"
                now = time.monotonic()
                if (new and now - last_shot > 0.8) or key == ord("c"):
                    cv2.imwrite(str(shot_dir / f"{len(corner_sets):03d}.png"), frame)
                    corner_sets.append(corners)
                    sigs.append(sig)
                    last_shot = now
                    shown[:] = 255 - shown  # destello: captura tomada
            hud(shown, [f"capturas: {len(corner_sets)} (mín {MIN_VIEWS}, ideal 25+)",
                        status, "c: forzar captura   q: calibrar y salir"])
            cv2.imshow("calibracion", shown)
            if key in (ord("q"), 27):
                break
    finally:
        src.close()
        cv2.destroyAllWindows()

    print(f"\n{len(corner_sets)} capturas guardadas en {shot_dir}")
    if len(corner_sets) < MIN_VIEWS or size is None:
        print(f"Se necesitan al menos {MIN_VIEWS}. Puedes recalibrar después con --from-dir.")
        return
    result = calibrate(corner_sets, size, args.square_mm)
    result["source"] = args.source
    report(result)
    save(result, Path(args.out))


def run_from_dir(args: argparse.Namespace) -> None:
    corner_sets, size = [], None
    files = sorted(Path(args.from_dir).glob("*.png"))
    for p in files:
        gray = cv2.imread(str(p), cv2.IMREAD_GRAYSCALE)
        if size is None:
            size = (gray.shape[1], gray.shape[0])
        c = find_corners(gray)
        if c is not None:
            corner_sets.append(c)
    print(f"tablero detectado en {len(corner_sets)}/{len(files)} imágenes")
    if len(corner_sets) < MIN_VIEWS or size is None:
        raise SystemExit(f"Se necesitan al menos {MIN_VIEWS}")
    result = calibrate(corner_sets, size, args.square_mm)
    result["source"] = str(args.from_dir)
    report(result)
    save(result, Path(args.out))


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--make-board", action="store_true", help="generar el PDF del tablero")
    ap.add_argument("--source", default="tello", help="'tello', índice de webcam o ruta de video")
    ap.add_argument("--from-dir", help="recalibrar desde una carpeta de capturas")
    ap.add_argument("--square-mm", type=float, default=25.0, help="lado REAL medido de un cuadro")
    ap.add_argument("--squares", default="10x7",
                    help="cuadros del tablero, ancho x alto (p.ej. 10x7); se cuentan TODOS los cuadros")
    ap.add_argument("--out", default="config/camera_tello.json", help="archivo de salida")
    args = ap.parse_args()

    global PATTERN
    cols, rows = (int(v) for v in args.squares.lower().split("x"))
    PATTERN = (cols - 1, rows - 1)  # OpenCV usa esquinas internas
    print(f"tablero: {cols}x{rows} cuadros -> {PATTERN[0]}x{PATTERN[1]} esquinas internas, "
          f"cuadro de {args.square_mm:g} mm")

    if args.make_board:
        print(make_board(args.square_mm, Path("tags")))
    elif args.from_dir:
        run_from_dir(args)
    else:
        run_capture(args)


if __name__ == "__main__":
    main()
