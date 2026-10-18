#!/usr/bin/env python3
"""Prueba de detección de AprilTags tag25h9 — AMGP 2026, categoría AprilTags.

No vuela: solo abre una fuente de video, detecta y muestra.

Uso:
    python scripts/test_tags.py --source 0                 # webcam /dev/video0
    python scripts/test_tags.py --source tello             # Tello, cámara frontal
    python scripts/test_tags.py --source tello --downward  # intenta cámara inferior
    python scripts/test_tags.py --source video.mp4         # repetir una grabación
    python scripts/test_tags.py --source tello --record vuelo.mp4
    python scripts/test_tags.py --selftest                 # prueba sintética sin cámara

Teclas: q/ESC salir · espacio pausa · s guardar captura.
"""
from __future__ import annotations

import argparse
import math
import threading
import time
from collections import defaultdict
from dataclasses import dataclass
from pathlib import Path

import cv2
import numpy as np

# Verificado 2026-10-17: las 10 imágenes de la Figura 1 del reglamento
# decodifican a los IDs 1..10 en el mismo orden de la tabla.
TAG_FUNCTIONS: dict[int, str] = {
    1: "Giro derecha 90",
    2: "Giro izquierda 90",
    3: "Giro 180",
    4: "Flip 360",
    5: "Subir 30 cm",
    6: "Bajar 30 cm",
    7: "Aterrizar",
    8: "Giro 180 + flip",
    9: "Pausa 5 s",
    10: "Giro 360",
}

GREEN = (0, 200, 0)
YELLOW = (0, 220, 255)
RED = (0, 0, 255)
GRAY = (160, 160, 160)


@dataclass
class Detection:
    tag_id: int
    corners: np.ndarray  # (4, 2) en orden: sup-izq, sup-der, inf-der, inf-izq del tag
    accepted: bool        # está en la lista blanca

    @property
    def center(self) -> tuple[float, float]:
        c = self.corners.mean(axis=0)
        return float(c[0]), float(c[1])

    @property
    def angle_deg(self) -> float:
        """Rotación del tag en la imagen: ángulo del borde superior (0 = derecho)."""
        (x0, y0), (x1, y1) = self.corners[0], self.corners[1]
        return math.degrees(math.atan2(y1 - y0, x1 - x0))

    @property
    def side_px(self) -> float:
        c = self.corners
        return float(np.mean([np.linalg.norm(c[i] - c[(i + 1) % 4]) for i in range(4)]))


class TagDetector:
    def __init__(self, whitelist: set[int] | None, refine: bool, decimate: float) -> None:
        dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_25h9)
        params = cv2.aruco.DetectorParameters()
        if refine:
            params.cornerRefinementMethod = cv2.aruco.CORNER_REFINE_SUBPIX
        params.aprilTagQuadDecimate = decimate
        self._det = cv2.aruco.ArucoDetector(dictionary, params)
        self.whitelist = whitelist

    def detect(self, gray: np.ndarray) -> list[Detection]:
        corners, ids, _ = self._det.detectMarkers(gray)
        if ids is None:
            return []
        out = []
        for c, i in zip(corners, ids.ravel()):
            tag_id = int(i)
            ok = self.whitelist is None or tag_id in self.whitelist
            out.append(Detection(tag_id, c.reshape(4, 2), ok))
        return out


class Confirmer:
    """Un ID se confirma tras verse en N frames consecutivos."""

    def __init__(self, n: int) -> None:
        self.n = n
        self.streak: dict[int, int] = defaultdict(int)

    def update(self, ids: set[int]) -> set[int]:
        for i in list(self.streak):
            if i not in ids:
                del self.streak[i]
        for i in ids:
            self.streak[i] += 1
        return {i for i, k in self.streak.items() if k >= self.n}


# ---------------------------------------------------------------- fuentes

class Source:
    def read(self) -> np.ndarray | None:  # BGR
        raise NotImplementedError

    def status(self) -> str:
        return ""

    def close(self) -> None:
        pass


class CvSource(Source):
    def __init__(self, spec: str) -> None:
        self.cap = cv2.VideoCapture(int(spec) if spec.isdigit() else spec)
        if not self.cap.isOpened():
            raise SystemExit(f"No se pudo abrir la fuente {spec!r}")
        self.is_file = not spec.isdigit()
        fps = self.cap.get(cv2.CAP_PROP_FPS)
        self.period = 1.0 / fps if self.is_file and fps > 0 else 0.0
        self._t = 0.0

    def read(self) -> np.ndarray | None:
        if self.period:  # reproducir archivos a su velocidad real
            dt = self.period - (time.monotonic() - self._t)
            if dt > 0:
                time.sleep(dt)
            self._t = time.monotonic()
        ok, frame = self.cap.read()
        return frame if ok else None

    def close(self) -> None:
        self.cap.release()


class TelloSource(Source):
    def __init__(self, downward: bool) -> None:
        from djitellopy import Tello

        self.t = Tello()
        self.t.connect()
        print(f"[tello] batería {self.t.get_battery()} %")
        for q in ("query_sdk_version", "query_serial_number"):
            try:
                print(f"[tello] {q}: {getattr(self.t, q)()}")
            except Exception as e:  # el modelo estándar no responde a todo
                print(f"[tello] {q}: falló ({e})")
        self.t.streamon()
        if downward:
            try:
                self.t.set_video_direction(Tello.CAMERA_DOWNWARD)
                print("[tello] cámara inferior: comando aceptado")
            except Exception as e:
                print(f"[tello] cámara inferior: RECHAZADA ({e})")
        self.reader = self.t.get_frame_read()
        self.snr = "?"
        self._last_id: int | None = None
        self.last_new = time.monotonic()
        self._stop = threading.Event()
        threading.Thread(target=self._poll_snr, daemon=True).start()

    def _poll_snr(self) -> None:
        # comando bloqueante: fuera del lazo de video
        while not self._stop.wait(5.0):
            try:
                self.snr = str(self.t.query_wifi_signal_noise_ratio())
            except Exception:
                self.snr = "err"

    def read(self) -> np.ndarray | None:
        f = self.reader.frame
        if f is None or not f.any():
            return None
        if id(f) != self._last_id:
            self._last_id = id(f)
            self.last_new = time.monotonic()
        # djitellopy 2.5 entrega RGB (PIL), no BGR
        return cv2.cvtColor(f, cv2.COLOR_RGB2BGR)

    def status(self) -> str:
        age = (time.monotonic() - self.last_new) * 1000
        return f"bat {self.t.get_battery()}%  SNR {self.snr}  frame {age:.0f} ms"

    def close(self) -> None:
        self._stop.set()
        try:
            self.t.streamoff()
        finally:
            self.t.end()


# ---------------------------------------------------------------- dibujo

def draw(frame: np.ndarray, dets: list[Detection], confirmed: set[int]) -> None:
    for d in dets:
        color = GRAY if not d.accepted else (GREEN if d.tag_id in confirmed else YELLOW)
        pts = d.corners.astype(np.int32)
        cv2.polylines(frame, [pts], True, color, 2)
        # borde superior del tag resaltado para ver la orientación
        cv2.line(frame, tuple(pts[0]), tuple(pts[1]), RED, 3)
        cx, cy = map(int, d.center)
        name = TAG_FUNCTIONS.get(d.tag_id, "fuera de lista") if d.accepted else "ignorado"
        label = f"ID {d.tag_id}: {name}"
        cv2.putText(frame, label, (cx - 60, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 0, 0), 4)
        cv2.putText(frame, label, (cx - 60, cy), cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        cv2.putText(frame, f"{d.angle_deg:+.0f} deg  {d.side_px:.0f}px",
                    (cx - 60, cy + 20), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    h, w = frame.shape[:2]
    cv2.drawMarker(frame, (w // 2, h // 2), (255, 255, 255), cv2.MARKER_CROSS, 20, 1)


def hud(frame: np.ndarray, lines: list[str]) -> None:
    for k, s in enumerate(lines):
        y = 22 + 22 * k
        cv2.putText(frame, s, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (0, 0, 0), 4)
        cv2.putText(frame, s, (8, y), cv2.FONT_HERSHEY_SIMPLEX, 0.55, (255, 255, 255), 1)


# ---------------------------------------------------------------- modos

def run_live(args: argparse.Namespace, detector: TagDetector) -> None:
    src: Source = TelloSource(args.downward) if args.source == "tello" else CvSource(args.source)
    confirmer = Confirmer(args.confirm)
    writer: cv2.VideoWriter | None = None
    stats_seen: dict[int, int] = defaultdict(int)
    stats_rejected: dict[int, int] = defaultdict(int)
    n_frames, det_ms_total = 0, 0.0
    t_fps, n_fps, fps = time.monotonic(), 0, 0.0
    paused, shown, frame = False, None, None
    out_dir = Path("capturas")
    out_dir.mkdir(exist_ok=True)

    try:
        while True:
            if not paused:
                frame = src.read()
                if frame is None:
                    if isinstance(src, CvSource) and src.is_file:
                        break
                    time.sleep(0.01)
                    continue
                if args.record:
                    if writer is None:
                        h, w = frame.shape[:2]
                        writer = cv2.VideoWriter(args.record, cv2.VideoWriter_fourcc(*"mp4v"), 30, (w, h))
                    writer.write(frame)

                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                t0 = time.perf_counter()
                dets = detector.detect(gray)
                dt = (time.perf_counter() - t0) * 1000
                det_ms_total += dt
                n_frames += 1
                for d in dets:
                    (stats_seen if d.accepted else stats_rejected)[d.tag_id] += 1
                confirmed = confirmer.update({d.tag_id for d in dets if d.accepted})

                n_fps += 1
                if (now := time.monotonic()) - t_fps >= 1.0:
                    fps, n_fps, t_fps = n_fps / (now - t_fps), 0, now

                shown = frame.copy()
                draw(shown, dets, confirmed)
                h, w = frame.shape[:2]
                hud(shown, [
                    f"{w}x{h}  {fps:.1f} fps  deteccion {dt:.1f} ms",
                    f"confirmados (N={args.confirm}): "
                    + (", ".join(f"{i}={TAG_FUNCTIONS.get(i, '?')}" for i in sorted(confirmed)) or "-"),
                    src.status(),
                ])
            if shown is not None:
                cv2.imshow("tag25h9", shown)
            key = cv2.waitKey(1) & 0xFF
            if key in (ord("q"), 27):
                break
            if key == ord(" "):
                paused = not paused
            if key == ord("s") and shown is not None:
                # el crudo sirve para volver a pasarlo por el detector
                stamp = time.strftime("%H%M%S")
                cv2.imwrite(str(out_dir / f"tag_{stamp}.png"), shown)
                cv2.imwrite(str(out_dir / f"tag_{stamp}_crudo.png"), frame)
                print(f"captura: {out_dir}/tag_{stamp}.png (+ _crudo)")
    except KeyboardInterrupt:
        pass
    finally:
        src.close()
        if writer is not None:
            writer.release()
        cv2.destroyAllWindows()

    if n_frames:
        lines = [f"fuente: {args.source}   frames: {n_frames}   "
                 f"detección media: {det_ms_total / n_frames:.1f} ms"]
        for i in sorted(stats_seen):
            lines.append(f"  ID {i:2d} ({TAG_FUNCTIONS.get(i, '?')}): {stats_seen[i]} frames "
                         f"({100 * stats_seen[i] / n_frames:.0f} %)")
        if stats_rejected:
            lines.append(f"  IDs fuera de lista blanca (posibles falsos positivos): {dict(stats_rejected)}")
        summary = out_dir / f"resumen_{time.strftime('%Y%m%d_%H%M%S')}.txt"
        summary.write_text("\n".join(lines) + "\n")
        print("\n" + "\n".join(lines) + f"\nresumen guardado en {summary}")


def run_selftest(detector: TagDetector) -> None:
    """Tags sintéticos rotados, en perspectiva, pequeños y borrosos."""
    dictionary = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_25h9)
    rng = np.random.default_rng(0)
    cases = ok = wrong = 0
    worst: dict[str, list[int]] = defaultdict(lambda: [0, 0])
    for tag_id in TAG_FUNCTIONS:
        marker = cv2.aruco.generateImageMarker(dictionary, tag_id, 200)
        marker = cv2.copyMakeBorder(marker, 40, 40, 40, 40, cv2.BORDER_CONSTANT, value=255)
        for angle in range(0, 360, 15):
            for side in (24, 40, 80):           # lado del tag en píxeles
                for tilt in (0.0, 0.35):        # perspectiva (vista oblicua)
                    canvas = np.full((480, 640), 200, np.uint8)
                    s = side / 200
                    h, w = marker.shape
                    src = np.float32([[0, 0], [w, 0], [w, h], [0, h]])
                    sq = (src - [w / 2, h / 2]) * s
                    sq[:2, 0] *= 1 - tilt       # borde de arriba más corto
                    sq[:2, 1] *= 1 - tilt / 2
                    a = math.radians(angle)
                    rot = np.array([[math.cos(a), -math.sin(a)], [math.sin(a), math.cos(a)]])
                    dst = (sq @ rot.T + [320, 240]).astype(np.float32)
                    M = cv2.getPerspectiveTransform(src, dst)
                    cv2.warpPerspective(marker, M, (640, 480), canvas,
                                        borderMode=cv2.BORDER_TRANSPARENT)
                    canvas = cv2.GaussianBlur(canvas, (3, 3), 0.8)
                    noisy = np.clip(canvas + rng.normal(0, 6, canvas.shape), 0, 255).astype(np.uint8)
                    ids = {d.tag_id for d in detector.detect(noisy) if d.accepted}
                    cases += 1
                    key = f"{side}px tilt{tilt}"
                    worst[key][1] += 1
                    if ids == {tag_id}:
                        ok += 1
                        worst[key][0] += 1
                    elif ids - {tag_id}:
                        wrong += 1
    print(f"selftest: {ok}/{cases} correctos ({100 * ok / cases:.1f} %), IDs equivocados: {wrong}")
    for k, (a, b) in sorted(worst.items()):
        print(f"  {k:16s} {a}/{b}")


def parse_ids(s: str) -> set[int] | None:
    if s.lower() == "all":
        return None
    out: set[int] = set()
    for part in s.split(","):
        lo, _, hi = part.partition("-")
        out.update(range(int(lo), int(hi or lo) + 1))
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--source", default="0", help="índice de webcam, 'tello' o ruta de video")
    ap.add_argument("--downward", action="store_true", help="Tello: pedir cámara inferior")
    ap.add_argument("--confirm", type=int, default=3, help="frames consecutivos para confirmar")
    ap.add_argument("--ids", default="1-10", help="lista blanca, p.ej. '1-10' o 'all'")
    ap.add_argument("--decimate", type=float, default=2.0, help="aprilTagQuadDecimate (1 = más lento y preciso)")
    ap.add_argument("--no-refine", action="store_true", help="sin refinamiento subpíxel de esquinas")
    ap.add_argument("--record", help="guardar el video crudo (mp4) para repetirlo después")
    ap.add_argument("--selftest", action="store_true", help="prueba sintética, sin cámara")
    args = ap.parse_args()

    print(f"OpenCV {cv2.__version__}")
    detector = TagDetector(parse_ids(args.ids), not args.no_refine, args.decimate)
    if args.selftest:
        run_selftest(detector)
    else:
        run_live(args, detector)


if __name__ == "__main__":
    main()
