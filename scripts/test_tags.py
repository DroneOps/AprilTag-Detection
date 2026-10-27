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
import copy
import json
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

DEFAULT_CALIB = Path(__file__).resolve().parent.parent / "config" / "camera_tello.json"

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
        # corregir más bits: en los videos de vuelo del 27-oct, +15–130 % de detecciones y
        # ningún ID falso entre 1 y 10 (con 1.0 ya salían 5, 6 y 7 falsos)
        params.errorCorrectionRate = 0.8
        params.maxErroneousBitsInBorderRate = 0.5
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


@dataclass
class TagPose:
    """Posición del tag en el marco de la cámara, en cm: x derecha, y abajo, z adelante."""
    t: np.ndarray
    normal: np.ndarray  # normal del plano del tag (piso o pared)
    R: np.ndarray | None = None  # rotación tag -> cámara

    @property
    def cam_in_tag(self) -> np.ndarray:
        """Posición de la cámara en el marco del tag, en cm: x a la derecha del tag
        visto de frente, y arriba, z distancia perpendicular al plano. No cambia
        si el dron gira en su lugar."""
        return -self.R.T @ self.t

    @property
    def range_cm(self) -> float:
        return float(np.linalg.norm(self.t))

    @property
    def azimuth_deg(self) -> float:
        """Positivo = el tag está a la derecha."""
        return math.degrees(math.atan2(self.t[0], self.t[2]))

    @property
    def elevation_deg(self) -> float:
        """Positivo = el tag está por debajo del eje de la cámara."""
        return math.degrees(math.atan2(self.t[1], self.t[2]))

    @property
    def plane_cm(self) -> float:
        """Distancia de la cámara al plano del tag: altura si está en el piso,
        distancia a la pared si está vertical."""
        return abs(float(self.normal @ self.t))


class PoseEstimator:
    def __init__(self, calib_path: Path, tag_cm: float) -> None:
        cal = json.loads(calib_path.read_text())
        self.K = np.array(cal["K"])
        self.dist = np.array(cal["dist"])
        self.size = tuple(cal["resolution"])
        self.tag_cm = tag_cm
        self.name = calib_path.name
        s = tag_cm / 2
        # mismo orden de esquinas que ArUco: sup-izq, sup-der, inf-der, inf-izq
        self.obj = np.array([[-s, s, 0], [s, s, 0], [s, -s, 0], [-s, -s, 0]], np.float32)

    def mirrored(self, axis: str) -> PoseEstimator:
        """La misma lente vista por un espejo. La imagen se voltea antes de detectar
        (un tag espejado no se decodifica), así que el centro óptico pasa al otro lado
        y un término de distorsión tangencial cambia de signo (p1 al voltear en
        vertical, p2 en horizontal). La radial no cambia."""
        pe = copy.copy(self)
        pe.K, pe.dist = self.K.copy(), self.dist.copy()
        w, h = self.size
        if axis == "v":
            pe.K[1, 2], pe.dist[2] = h - 1 - self.K[1, 2], -self.dist[2]
        else:
            pe.K[0, 2], pe.dist[3] = w - 1 - self.K[0, 2], -self.dist[3]
        pe.name = f"{self.name} (espejo {axis})"
        return pe

    def estimate(self, d: Detection) -> TagPose | None:
        ok, rvec, tvec = cv2.solvePnP(self.obj, d.corners.astype(np.float32), self.K, self.dist,
                                      flags=cv2.SOLVEPNP_IPPE_SQUARE)
        if not ok:
            return None
        R, _ = cv2.Rodrigues(rvec)
        return TagPose(tvec.ravel(), R[:, 2], R)


def floor_view(pose: TagPose, tilt: tuple[float, float] | None = None) -> tuple[float, float, float, float, float]:
    """Con espejo (vista hacia abajo; imagen ya volteada: arriba = adelante del dron).
    Devuelve (adelante, derecha, altura) del tag respecto a la cámara en cm, medidos
    sobre el piso, y la inclinación de la vista (adelante, derecha) en grados medida
    con la orientación del tag (0, 0 = justo hacia abajo).

    tilt: inclinación FIJA de la vista (adelante, derecha) en grados. El espejo no se
    mueve, así que conviene medirla una vez y pasarla: con la orientación medida en
    cada frame el error llega a ~15 cm con el tag de frente; con la fija, < 1 cm."""
    n = pose.normal  # normal del piso (del tag) en la cámara, apuntando hacia la cámara
    tilt_fwd = math.degrees(math.atan2(-n[1], -n[2]))
    tilt_right = math.degrees(math.atan2(n[0], -n[2]))
    t = pose.t
    if tilt is None:
        right_cam = np.array([1.0, 0.0, 0.0])
        fwd_h = np.cross(n, right_cam)
        fwd_h /= np.linalg.norm(fwd_h)
        right_h = np.cross(fwd_h, n)
        return float(t @ fwd_h), float(t @ right_h), abs(float(n @ t)), tilt_fwd, tilt_right
    # ejes de la cámara virtual en un marco nivelado (X derecha, Y adelante, Z arriba)
    f = np.array([math.tan(math.radians(tilt[1])), math.tan(math.radians(tilt[0])), -1.0])
    f /= np.linalg.norm(f)
    r = np.cross(f, [0.0, 1.0, 0.0])
    r /= np.linalg.norm(r)
    d = np.cross(f, r)
    w = t[0] * r + t[1] * d + t[2] * f
    return float(w[1]), float(w[0]), float(-w[2]), tilt_fwd, tilt_right


def floor_from_front(pose: TagPose, pitch_deg: float) -> tuple[float, float, float, float, float]:
    """Tag en el PISO visto con la cámara al frente (inclinada pitch_deg hacia abajo).
    Devuelve (adelante, derecha, altura) de la cámara al tag en cm sobre el piso, el
    giro del tag respecto al rumbo del dron en grados (+ = su borde de arriba apunta a
    la derecha) y qué tan "de piso" es (1 = tag horizontal, 0 = vertical)."""
    p = math.radians(pitch_deg)

    def level(v):  # cámara -> marco nivelado (x derecha, y abajo, z adelante)
        return np.array([v[0], v[1] * math.cos(p) + v[2] * math.sin(p), -v[1] * math.sin(p) + v[2] * math.cos(p)])

    t, top, n = level(pose.t), level(pose.R[:, 1]), level(pose.R[:, 2])
    return float(t[2]), float(t[0]), float(t[1]), math.degrees(math.atan2(top[0], top[2])), float(-n[1])


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
        import logging

        from djitellopy import Tello

        Tello.LOGGER.setLevel(logging.WARNING)  # sin el spam de cada 'wifi?'
        self.t = Tello()
        self.t.connect()
        print(f"[tello] batería {self.t.get_battery()} %")
        print(f"[tello] sdk? -> {self._ask('sdk?')!r}")
        print(f"[tello] sn?  -> {self._ask('sn?')!r}")
        print(f"[tello] streamon -> {self._ask('streamon')!r}")
        if downward:
            print(f"[tello] downvision 1 -> {self._ask('downvision 1')!r}")
        # cola de 1: cada frame se entrega una sola vez y siempre el más reciente
        self.reader = self.t.get_frame_read(with_queue=True, max_queue_len=1)
        self._report_camera(downward)
        self.snr = "?"
        self.last_new = time.monotonic()
        self._stop = threading.Event()
        threading.Thread(target=self._poll_snr, daemon=True).start()

    def _ask(self, cmd: str) -> str:
        """Manda un comando y devuelve SU respuesta.

        djitellopy empareja cada comando con la primera respuesta en cola; una
        respuesta tardía o corrupta desfasa todas las siguientes. Se vacía la
        cola antes de mandar.
        """
        responses = self.t.get_own_udp_object()["responses"]
        time.sleep(0.3)
        if responses:
            print(f"[tello] (descartadas {len(responses)} respuestas viejas: {responses})")
            responses.clear()
        return self.t.send_command_with_return(cmd, timeout=5)

    def _report_camera(self, downward: bool) -> None:
        """El 'ok' no prueba nada: se verifica la cámara mirando la imagen."""
        # el último frame tras ~4 s (el cambio de cámara tarda), máximo 8 s
        f, t0 = None, time.monotonic()
        while (dt := time.monotonic() - t0) < 4 or (f is None and dt < 8):
            if (g := self.reader.frame) is not None:
                f = g
            time.sleep(0.05)
        if f is None:
            print("[tello] no llegaron frames de video")
            return
        h, w = f.shape[:2]
        spread = float(np.abs(f.astype(int) - f.mean(axis=2, keepdims=True)).mean())
        gray = spread < 2.0
        print(f"[tello] imagen {w}x{h}, {'GRIS' if gray else 'COLOR'} (dispersión color {spread:.1f})")
        if downward:
            verdict = "parece INFERIOR" if gray or w <= 320 else "sigue siendo la FRONTAL"
            print(f"[tello] cámara pedida: inferior -> {verdict}. Confírmalo viendo la ventana.")

    def _poll_snr(self) -> None:
        # comando bloqueante: fuera del lazo de video
        while not self._stop.wait(5.0):
            try:
                self.snr = str(self.t.query_wifi_signal_noise_ratio())
            except Exception:
                self.snr = "err"

    def read(self) -> np.ndarray | None:
        f = self.reader.frame
        if f is None:  # todavía no llega un frame nuevo
            return None
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

def draw(frame: np.ndarray, dets: list[Detection], confirmed: set[int],
         poses: list[TagPose | None] | None = None, floor: bool = False) -> None:
    for d, pose in zip(dets, poses or [None] * len(dets)):
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
        info = [f"rot {d.angle_deg:+.0f} deg  {d.side_px:.0f}px"]
        if pose is not None and floor:
            fwd, right, height, tf, tr = floor_view(pose)
            info = [f"adelante {fwd:+.0f} cm  derecha {right:+.0f} cm",
                    f"altura {height:.0f} cm (por el espejo)",
                    f"vista: {tf:+.0f} deg adelante, {tr:+.0f} deg lado"] + info
        elif pose is not None:
            info.insert(0, f"{pose.range_cm / 100:.2f} m  az {pose.azimuth_deg:+.0f}  el {pose.elevation_deg:+.0f}")
            info.append(f"plano a {pose.plane_cm:.0f} cm")
        for k, s in enumerate(info):
            cv2.putText(frame, s, (cx - 60, cy + 20 + 18 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.5, (0, 0, 0), 3)
            cv2.putText(frame, s, (cx - 60, cy + 20 + 18 * k), cv2.FONT_HERSHEY_SIMPLEX, 0.5, color, 1)
    h, w = frame.shape[:2]
    cv2.drawMarker(frame, (w // 2, h // 2), (255, 255, 255), cv2.MARKER_CROSS, 20, 1)


def draw_clock(frame: np.ndarray) -> None:
    """Reloj en ms abajo a la izquierda. Con la cámara apuntando a la pantalla, la
    captura muestra dos relojes: el actual y el que vio la cámara. Latencia = resta."""
    text = f"{time.time() % 100:06.3f}"
    h = frame.shape[0]
    (tw, th), _ = cv2.getTextSize(text, cv2.FONT_HERSHEY_SIMPLEX, 2.5, 6)
    cv2.rectangle(frame, (0, h - th - 40), (tw + 40, h), (0, 0, 0), -1)
    cv2.putText(frame, text, (20, h - 20), cv2.FONT_HERSHEY_SIMPLEX, 2.5, (255, 255, 255), 6, cv2.LINE_AA)


def hud(frame: np.ndarray, lines: list[str]) -> None:
    # fondo oscuro detrás del texto: legible sin el contorno grueso que se encima
    font, scale = cv2.FONT_HERSHEY_SIMPLEX, 0.55
    width = max((cv2.getTextSize(s, font, scale, 1)[0][0] for s in lines), default=0)
    box = frame[0:12 + 22 * len(lines), 0:min(frame.shape[1], width + 16)]
    box[:] = (box * 0.35).astype(frame.dtype)
    for k, s in enumerate(lines):
        cv2.putText(frame, s, (8, 22 + 22 * k), font, scale, (255, 255, 255), 1, cv2.LINE_AA)


# ---------------------------------------------------------------- modos

def run_live(args: argparse.Namespace, detector: TagDetector, pose_est: PoseEstimator | None) -> None:
    src: Source = TelloSource(args.downward) if args.source == "tello" else CvSource(args.source)
    confirmer = Confirmer(args.confirm)
    writer: cv2.VideoWriter | None = None
    stats_seen: dict[int, int] = defaultdict(int)
    stats_rejected: dict[int, int] = defaultdict(int)
    n_frames, det_ms_total = 0, 0.0
    gaps: list[float] = []  # ms entre frames que llegan: calidad del enlace
    tilts: list[tuple[float, float]] = []  # con --espejo: inclinación de la vista medida
    t_prev_frame: float | None = None
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
                    # sin frame nuevo: seguir atendiendo el teclado
                    if cv2.waitKey(5) & 0xFF in (ord("q"), 27):
                        break
                    continue
                if args.record:
                    if writer is None:
                        h, w = frame.shape[:2]
                        writer = cv2.VideoWriter(args.record, cv2.VideoWriter_fourcc(*"mp4v"), 30, (w, h))
                    writer.write(frame)  # crudo: para repetirlo con --espejo igual que en vivo
                if args.espejo:
                    frame = cv2.flip(frame, 0 if args.espejo == "v" else 1)

                if pose_est is not None and (frame.shape[1], frame.shape[0]) != pose_est.size:
                    print(f"[pose] la calibración es de {pose_est.size[0]}x{pose_est.size[1]} y el video "
                          f"es {frame.shape[1]}x{frame.shape[0]}: distancias desactivadas")
                    pose_est = None
                gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
                t0 = time.perf_counter()
                dets = detector.detect(gray)
                dt = (time.perf_counter() - t0) * 1000
                det_ms_total += dt
                n_frames += 1
                t_arr = time.monotonic()
                if t_prev_frame is not None:
                    gaps.append((t_arr - t_prev_frame) * 1000)
                t_prev_frame = t_arr
                for d in dets:
                    (stats_seen if d.accepted else stats_rejected)[d.tag_id] += 1
                confirmed = confirmer.update({d.tag_id for d in dets if d.accepted})

                n_fps += 1
                if (now := time.monotonic()) - t_fps >= 1.0:
                    fps, n_fps, t_fps = n_fps / (now - t_fps), 0, now

                shown = frame.copy()
                poses = [pose_est.estimate(d) if pose_est and d.accepted else None for d in dets]
                draw(shown, dets, confirmed, poses, floor=bool(args.espejo))
                if args.espejo:
                    tilts += [floor_view(p)[3:] for p in poses if p is not None]
                h, w = frame.shape[:2]
                if args.espejo:  # dirección que el programa supone como "adelante del dron"
                    cv2.arrowedLine(shown, (w // 2, 120), (w // 2, 50), (0, 255, 255), 3, tipLength=0.35)
                    cv2.putText(shown, "ADELANTE (supuesto)", (w // 2 + 15, 75), cv2.FONT_HERSHEY_SIMPLEX,
                                0.6, (0, 255, 255), 2, cv2.LINE_AA)
                hud(shown, [
                    f"pose: tag de {pose_est.tag_cm:g} cm, {pose_est.name}" if pose_est
                    else "pose: desactivada (sin calibracion)",
                    f"{w}x{h}  {fps:.1f} fps  deteccion {dt:.1f} ms",
                    f"confirmados (N={args.confirm}): "
                    + (", ".join(f"{i}={TAG_FUNCTIONS.get(i, '?')}" for i in sorted(confirmed)) or "-"),
                    src.status(),
                ])
                if args.clock:
                    draw_clock(shown)
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
        if tilts:
            tf, tr = np.median(np.array(tilts), axis=0)
            lines.append(f"espejo: inclinacion de la vista (mediana de {len(tilts)}): {tf:+.1f} adelante, "
                         f"{tr:+.1f} lado -> config/mission_espejo.json: "
                         f'"vista_adelante_deg": {tf:.1f}, "vista_lado_deg": {tr:.1f}')
        if len(gaps) > 60:
            g = np.array(gaps[30:])  # el primer segundo incluye abrir la ventana
            minutes = g.sum() / 60000
            lines.append(f"enlace: {len(g) + 1} frames en {g.sum() / 1000:.0f} s | intervalo mediano {np.median(g):.0f} ms | "
                         f"> 100 ms: {(g > 100).sum()} ({(g > 100).sum() / minutes:.1f}/min) | "
                         f"> 300 ms: {(g > 300).sum()} | maximo {g.max():.0f} ms")
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
    ap.add_argument("--calib", default=str(DEFAULT_CALIB), help="calibración de la cámara (json)")
    ap.add_argument("--espejo", nargs="?", const="v", choices=["v", "h"],
                    help="cámara con espejo hacia abajo: voltea la imagen (v por defecto) antes de detectar")
    ap.add_argument("--clock", action="store_true",
                    help="reloj grande para medir la latencia: apunta la cámara a esta ventana")
    ap.add_argument("--tag-cm", type=float, default=15.0,
                    help="lado REAL del cuadro negro del tag en cm (mídelo con regla)")
    args = ap.parse_args()

    print(f"OpenCV {cv2.__version__}")
    detector = TagDetector(parse_ids(args.ids), not args.no_refine, args.decimate)
    if args.selftest:
        run_selftest(detector)
    else:
        calib = Path(args.calib)
        pose_est = PoseEstimator(calib, args.tag_cm) if calib.exists() else None
        if pose_est is not None and args.espejo:
            pose_est = pose_est.mirrored(args.espejo)
        if pose_est is None:
            print(f"[pose] no existe {calib}: se detecta sin medir distancias")
        run_live(args, detector, pose_est)


if __name__ == "__main__":
    main()
