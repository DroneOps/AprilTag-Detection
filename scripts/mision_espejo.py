#!/usr/bin/env python3
"""Misión con espejo: la cámara ve HACIA ABAJO y los tags están en el piso.

El dron avanza despacio mirando el piso. Cuando un tag confirmado aparece
debajo, se centra ENCIMA de él (adelante/atrás y lados) sosteniendo el rumbo del
tramo, ejecuta su función y sigue hacia el frente. No se alinea con los bordes
del tag: el reglamento pide funcionar con tags girados (alinear_bordes lo
reactiva). El tag que ve mientras despega (el de inicio) se ignora
(ignorar_inicio). Las acciones,
el flip seguro, el paro y los vigilantes son los de mission_tags.py / first_flight.py.

ATENCIÓN: con el espejo cubriendo toda la cámara NO hay vista al frente: el dron
no ve paredes ni obstáculos. Avanza como máximo advance_timeout_s sin ver tags.

Uso:
    python scripts/mision_espejo.py --record espejo_m1.mp4
    python scripts/mision_espejo.py --quieto            # no avanza: espera un tag debajo
    python scripts/mision_espejo.py --espejo h          # si "adelante" sale al revés en test_tags

Parámetros propios en config/mission_espejo.json (más config/mission_tags.json
y config/flight.json).
"""
from __future__ import annotations

import argparse
import json
import math
import threading
import time
from collections import deque
from dataclasses import dataclass, fields
from pathlib import Path

import cv2
import numpy as np

from first_flight import ROOT, FlightConfig, altitude, connect, run_app, with_min, wrap_deg
from mission_tags import ACTIONS, MissionConfig, TagMission, Vision
from test_tags import DEFAULT_CALIB, TAG_FUNCTIONS, draw, floor_view


@dataclass
class MirrorConfig:
    espejo: str = "v"  # cómo se voltea la imagen (ver test_tags.py --espejo)
    quieto: bool = False  # True: no avanza, espera a que haya un tag debajo
    cruise_alt_cm: float = 100.0  # más alto = ve más piso debajo (a 100 cm, vista a −10.3°: ~20 cm adelante, ~60 atrás, ±52 de lado)
    advance_fb: int = 15  # rc 15 ≈ 16–20 cm/s (calibración real)
    advance_timeout_s: float = 12.0  # sin ver tag debajo por esto: fin (sin vista al frente)
    advance_lr: int = 0  # rc lateral fijo al avanzar sin tag, para compensar si el dron se va de un lado
    # (se va a la derecha: negativo, p. ej. -10)
    alinear_bordes: bool = False  # True: girar para alinearse con los bordes del tag (supone tags derechos)
    ignorar_inicio: bool = True  # ignorar el tag que se ve mientras despega (el de inicio)
    inicio_alt_cm: float = 70.0  # ...solo el visto abajo de esta altura, aún sobre el punto de despegue
    quieto_timeout_s: float = 20.0
    center_kp: float = 0.6
    center_kd: float = 1.0  # rc por cm/s: frena según qué tan rápido se acerca (real 9-nov: oscilaba ±15–20 cm)
    center_min: int = 10
    center_max: int = 15
    center_dead: float = 5.0  # mando calculado menor que esto: no mandar nada (el Tello frena solo)
    center_tol_cm: float = 6.0
    center_vel_tol: float = 4.0  # cm/s: para ejecutar, además de cerca, casi quieto
    centrar_max_s: float = 8.0  # si no se estabiliza encima en este tiempo, ejecuta igual (el punto es por el tag)
    rot_kp: float = 1.0
    rot_tol_deg: float = 4.0
    window: int = 7  # mediana de N frames
    # sostener la posición con el piso visto por el espejo (11-nov: los dos Tellos se iban solos
    # a la derecha, 4–12 cm/s, y el primer tag quedaba en la orilla de la vista o fuera)
    sostener_piso: bool = True  # quieto y subiendo: volver al punto de despegue; avanzando: sostener la línea
    piso_calidad: float = 0.1  # calidad mínima de la correlación de fase para creerle
    piso_kp: float = 0.5  # rc por cm de distancia a donde debería estar
    piso_kd: float = 0.8  # rc por cm/s que se está yendo
    piso_ki: float = 0.15  # rc por cm·s: junta el empuje que hace falta contra una deriva constante
    # (sin esto, con el Tello 7 se quedaba ~26 cm corrido: el PD solo empuja si hay error)
    piso_i_max: float = 15.0  # tope de lo juntado, en rc (que no se pase de largo)
    # integral al despegar, en rc (lado, adelante): + si el dron se va solo a la derecha / adelante.
    # Va en config/mision_dron<N>.json de cada dron. OJO: si el dron ya no deriva, empuja de más al
    # principio hasta que la integral se corrige sola (unos segundos)
    piso_i_inicial: tuple = (0.0, 0.0)
    # ejecutando un tag (giros, pausa): sostenerse sobre él con su posición (11-nov: en un giro de
    # 90° se corría 26–42 cm), y que el tramo nuevo pase por el tag y no por donde quedó el dron
    sostener_tag: bool = True
    # rc máximo para quedarse sobre el tag mientras lo ejecuta. Con 20 (por si al girar no le
    # alcanzaba contra los ~12 cm/s que se corre) fue peor en las pistas al azar: 76 % de los puntos
    # contra 86 % con 15 (16-nov)
    sostener_tag_max: int = 15
    # el tag recién ejecutado se sigue cuadro por cuadro: un tag con su número a menos de esto de
    # donde debe estar (su última posición, corrida con lo que avanzó el dron) es el mismo y se
    # ignora; en otra parte es OTRO tag y se ejecuta. Antes se ignoraba por número y se perdían los
    # tags repetidos y los que se vuelven a visitar tras un 180° (pistas al azar, 12-nov)
    mismo_tag_cm: float = 35.0  # la mitad de la separación mínima entre tags (70 cm)
    # un tag ya ejecutado antes (no el último) solo cuenta si está en la línea del tramo: adelante y a
    # menos de esto de lado (al regresar tras un 180° está enfrente; uno viejo a un lado no se toma)
    pasillo_cm: float = 40.0
    piso_min: int = 10
    piso_max: int = 20
    piso_dead: float = 4.0  # mando menor que esto: nada
    # seguro, por si en el dron real la medida sale al revés y la corrección empuja hacia afuera:
    # apagarla si, corrigiendo, se aleja piso_alejandose_cm en 1.5 s (al revés, deriva y corrección
    # suman >30 cm/s) o si se pasa de piso_limite_cm. No cuenta lo que se fue al despegar: ahí el
    # Tello ignora el rc (el Tello 7 se va >80 cm)
    piso_alejandose_cm: float = 35.0
    piso_limite_cm: float = 150.0
    buscar_s: float = 4.0  # tag perdido al centrarse: buscarlo donde debe estar esto, luego seguir avanzando
    vista_adelante_deg: float = 0.0  # inclinación del espejo: medirla con test_tags.py --espejo
    vista_lado_deg: float = 0.0

    @classmethod
    def load(cls, path: Path) -> MirrorConfig:
        data = json.loads(path.read_text()) if path.exists() else {}
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise SystemExit(f"{path}: claves desconocidas {sorted(unknown)}")
        return cls(**data)


def ajustes_dron(ecfg: "MirrorConfig", dron: str | None) -> list[str]:
    """Aplica config/mision_dron<N>.json (lo que cambia en la misión con ese dron, p. ej. la
    integral inicial). Devuelve lo que cambió."""
    if not dron:
        return []
    path = ROOT / "config" / f"mision_dron{dron}.json"
    if not path.exists():
        raise SystemExit(f"no existe {path.relative_to(ROOT)}")
    data = {k: v for k, v in json.loads(path.read_text()).items() if not k.startswith("_")}
    unknown = set(data) - {f.name for f in fields(MirrorConfig)}
    if unknown:
        raise SystemExit(f"{path}: claves desconocidas {sorted(unknown)}")
    for k, v in data.items():
        setattr(ecfg, k, tuple(v) if isinstance(v, list) else v)
    return [f"{k}={v}" for k, v in data.items()]


class FlujoPiso:
    """Cuánto se mueve el dron sobre el piso, con la imagen del espejo: correlación de fase entre
    un cuadro y el anterior, pasada a cm con la altura. Posición y velocidad en el marco del dron,
    (derecha, adelante). Con el piso del laboratorio (cuadrícula de cinta) mide bien de lado;
    hacia adelante es peor si las rayas van en la dirección del avance (videos del 11-nov).

    Al subir o bajar, el piso se ve más chico o más grande, y la correlación confundía ese cambio
    de escala con desplazamiento: subiendo de 30 a 100 cm "veía" +10 cm de lado y el control movía
    al dron sin razón. Por eso, antes de comparar, el cuadro anterior se escala según cuánto cambió
    la altura (velocidad vertical robusta del tof), alrededor del punto de la imagen que queda
    justo debajo del dron (punto_bajo_dron).

    Antes se escalaba alrededor del centro óptico de la imagen SIN voltear (y = 386 px, cuando la
    imagen va volteada: 333) y sin la inclinación del espejo. Con la vista real (−10.3°, 12-nov),
    subir del piso a 100 cm "veía" al dron irse 6–29 cm hacia atrás, y el PID lo empujaba de más
    hacia adelante (issue #2)."""

    TAM = (240, 180)

    def __init__(self, fx: float, calidad: float, centro: tuple[float, float] = (480.0, 360.0)) -> None:
        self.f = fx * self.TAM[0] / 960  # px por unidad a esta resolución
        self.k = self.TAM[0] / 960
        self.c = (centro[0] * self.k, centro[1] * self.k)  # punto bajo el dron, en la imagen ya volteada
        self.calidad = calidad
        self.win = cv2.createHanningWindow(self.TAM, cv2.CV_32F)
        self.prev, self.t_prev = None, 0.0
        self.alts: deque = deque()  # (t, altura) del último ~0.6 s
        self.pos = np.zeros(2)
        self.vel = np.zeros(2)
        self.q, self.t_ok = 0.0, -math.inf
        self.lock = threading.Lock()

    def _vz(self) -> float:
        """Velocidad vertical (cm/s) robusta a lecturas sueltas del tof: mediana de las pendientes."""
        h = self.alts
        s = [(h[j][1] - h[i][1]) / (h[j][0] - h[i][0]) for i in range(len(h)) for j in range(i + 1, len(h))
             if h[j][0] - h[i][0] > 0.05]
        return float(np.median(s)) if len(s) >= 3 else 0.0

    def actualizar(self, gray: np.ndarray, t: float, alt: float, girando: bool) -> None:
        small = cv2.resize(gray, self.TAM, interpolation=cv2.INTER_AREA).astype(np.float32)
        if not self.alts or self.alts[-1][1] != alt or t - self.alts[-1][0] > 0.09:
            self.alts.append((t, alt))  # una por lectura nueva del tof (llegan a ~10 Hz)
        while self.alts and t - self.alts[0][0] > 0.6:
            self.alts.popleft()
        if self.prev is not None and not girando and alt > 25 and t > self.t_prev:
            # el cuadro anterior, a la escala de ahora: subiendo se veía más grande (m < 1 lo achica)
            a = float(np.median([x[1] for x in self.alts]))
            m = min(1.1, max(0.9, (a - self._vz() * (t - self.t_prev)) / a))
            ref = self.prev
            if abs(m - 1) > 1e-4:
                M = np.float32([[m, 0, (1 - m) * self.c[0]], [0, m, (1 - m) * self.c[1]]])
                ref = cv2.warpAffine(self.prev, M, self.TAM, flags=cv2.INTER_LINEAR, borderMode=cv2.BORDER_REFLECT)
            (dx, dy), q = cv2.phaseCorrelate(ref, small, self.win)
            self.q = q
            dt, cm = t - self.t_prev, alt / self.f
            v = np.array([-dx * cm / dt, dy * cm / dt])  # el piso se mueve al revés que el dron
            if q >= self.calidad and np.hypot(*v) < 150:  # más de 1.5 m/s: correlación equivocada
                with self.lock:
                    self.pos += v * dt
                    self.vel += 0.25 * (v - self.vel)
                    self.t_ok = t
        self.prev, self.t_prev = (None if girando else small), t

    def reiniciar(self, pos=(0.0, 0.0)) -> np.ndarray:
        """Toma la posición de ahora como pos (por defecto, el origen). Devuelve cuánto se movió el origen."""
        with self.lock:
            delta = np.asarray(pos, float) - self.pos
            self.pos[:] = pos
            return delta

    def estado(self) -> tuple[np.ndarray, np.ndarray]:
        with self.lock:
            return self.pos.copy(), self.vel.copy()

    def medida(self) -> tuple[float, np.ndarray]:
        """(tiempo en que llegó la última imagen buena, posición con ella)."""
        with self.lock:
            return self.t_ok, self.pos.copy()

    def valido(self, now: float) -> bool:
        return now - self.t_ok < 0.5


def punto_bajo_dron(K: np.ndarray, vista_adelante_deg: float, vista_lado_deg: float) -> tuple[float, float]:
    """Pixel de la imagen ya volteada (960x720) que queda justo debajo del dron: el centro óptico
    de la cámara espejada (K de PoseEstimator.mirrored) corrido por la inclinación de la vista.
    Inclinada hacia adelante, lo de abajo del dron sale más abajo en la imagen (hacia atrás);
    inclinada a la derecha, sale a la izquierda. Al subir o bajar en vertical, el piso crece o se
    encoge alrededor de este punto."""
    return (float(K[0, 2] - K[0, 0] * math.tan(math.radians(vista_lado_deg))),
            float(K[1, 2] + K[1, 1] * math.tan(math.radians(vista_adelante_deg))))


def rot_mod90(angle: float) -> float:
    """Giro del tag en la imagen, llevado a [-45, 45): un tag derecho vale 0 en
    cualquiera de sus 4 orientaciones."""
    return (angle + 45.0) % 90.0 - 45.0


class MirrorMission(TagMission):
    LOG_EXTRA = ["n_tags", "objetivo", "tag_adelante", "tag_derecha", "tag_giro", "altura_espejo",
                 "piso_der", "piso_ade", "piso_vder", "piso_vade", "piso_q", "piso_ider", "piso_iade",
                 "piso_modo"]

    def __init__(self, tello, cfg: FlightConfig, mcfg: MissionConfig, ecfg: MirrorConfig,
                 log_path: Path, calib: Path) -> None:
        mcfg.cruise_alt_cm = ecfg.cruise_alt_cm
        super().__init__(tello, cfg, mcfg, log_path, calib)
        self.e = ecfg
        self._started = False
        self._center_hist: deque = deque(maxlen=60)  # (t del frame, adelante, derecha) del tag objetivo
        self._start_ids: set[int] = set()  # tags vistos durante el despegue
        self._ult_ejecutado: int | None = None  # número del último tag ejecutado
        self._ejecutados_ids: set[int] = set()  # números ya ejecutados en este vuelo
        # seguimiento del recién ejecutado: (adelante, derecha) la última vez que se vio y la posición del
        # piso en ese momento; None si no se vio al arrancar el tramo (entonces se ignora por número)
        self._ult_track: tuple[float, float, np.ndarray] | None = None
        # (t, adelante, derecha, piso, yaw) la última vez que se vio el objetivo: para saber dónde quedó si
        # se deja de ver (p. ej. girando sobre él)
        self._target_visto: tuple | None = None
        self._avisados: set[int] = set()  # tags ignorados ya avisados en este tramo
        self.pose_est = self.pose_est.mirrored(ecfg.espejo)
        centro = punto_bajo_dron(self.pose_est.K, ecfg.vista_adelante_deg, ecfg.vista_lado_deg)
        self._floor_hist: dict[int, deque] = {}
        self._heights: dict[int, float] = {}
        self._last_floor = (0.0, 0.0)
        self.piso = FlujoPiso(float(self.pose_est.K[0, 0]), ecfg.piso_calidad, centro)
        self._pos_visto = np.zeros(2)  # posición (piso) cuando se vio el tag objetivo por última vez
        self._yaw_frame = None
        self._piso_apagado = False
        self._piso_lejos: deque = deque()  # (t, distancia a donde debería estar) mientras corrige
        self._piso_i = np.zeros(2)  # parte integral (derecha, adelante), en rc
        self._piso_t = None  # última vez que corrigió

    # ---- visión: imagen volteada, posición del tag sobre el piso
    def on_frame(self, bgr: np.ndarray, t: float) -> None:
        if (bgr.shape[1], bgr.shape[0]) != self.pose_est.size:
            self.reason = f"video {bgr.shape[1]}x{bgr.shape[0]} no coincide con la calibracion"
            return
        img = cv2.flip(bgr, 0 if self.e.espejo == "v" else 1)  # un tag espejado no se decodifica
        gray = cv2.cvtColor(img, cv2.COLOR_BGR2GRAY)
        s = self.tel.snapshot()[0]
        yaw = s.get("yaw", 0)
        girando = self.rc[3] != 0 or (self._yaw_frame is not None and abs(((yaw - self._yaw_frame) + 180) % 360 - 180) > 1)
        self._yaw_frame = yaw
        self.piso.actualizar(gray, t, altitude(s), girando)
        dets = self.detector.detect(gray)
        poses = [self.pose_est.estimate(d) if d.accepted else None for d in dets]
        confirmed = self.confirmer.update({d.tag_id for d in dets if d.accepted})
        if self.state in ("IDLE", "TAKEOFF") and altitude(self.tel.snapshot()[0]) < self.e.inicio_alt_cm:
            self._start_ids.update(d.tag_id for d in dets if d.accepted)
        por_id: dict[int, list] = {}
        for d, p in zip(dets, poses):
            if p is not None:
                fwd, right, height, _, _ = floor_view(p, (self.e.vista_adelante_deg, self.e.vista_lado_deg))
                por_id.setdefault(d.tag_id, []).append((fwd, right, rot_mod90(d.angle_deg), height))
        floor = {}
        for tid, vistos in por_id.items():
            if tid == self._ult_ejecutado and self._ult_track is not None:
                # seguir al recién ejecutado; si hay otro con su número, quedarse con el otro
                viejos = [x for x in vistos if self._es_el_ejecutado(tid, x[0], x[1], t)]
                if viejos:
                    pred = self._ult_pred(t)
                    v0 = min(viejos, key=lambda x: math.hypot(x[0] - pred[0], x[1] - pred[1]))
                    self._ult_track = (v0[0], v0[1], self.piso.estado()[0])
                otros = [x for x in vistos if not any(x is v for v in viejos)]
                vistos = otros or vistos
            fwd, right, rot, height = min(vistos, key=lambda x: abs(x[0]) + abs(x[1]))
            hist = self._floor_hist.setdefault(tid, deque(maxlen=self.e.window))
            if hist and math.hypot(*(np.median(np.array(hist), axis=0)[:2] - (fwd, right))) > 30:
                hist.clear()  # saltó a otro tag con el mismo número: no mezclar sus posiciones
            hist.append((fwd, right, rot))
            floor[tid] = tuple(float(v) for v in np.median(np.array(hist), axis=0))
            self._heights[tid] = height
        for tid in set(self._floor_hist) - set(floor):
            del self._floor_hist[tid]
        if self._target in floor:
            self._target_visto = (t, floor[self._target][0], floor[self._target][1], self.piso.estado()[0], yaw)
        self._shown = img
        with self._vis_lock:
            self._vis = Vision(t, dets, poses, confirmed, floor)  # tagframe = (adelante, derecha, giro)
            for d in dets:
                if d.tag_id in self._last_seen:
                    self._last_seen[d.tag_id] = t

    # ---- HMI: se muestra la imagen ya volteada (la que ve el detector)
    def overlay(self, img: np.ndarray) -> None:
        shown = getattr(self, "_shown", None)
        if shown is not None and shown.shape == img.shape:
            img[:] = shown
        v = self._vis
        if v is not None:
            draw(img, v.dets, v.confirmed, v.poses, floor=True)
        w = img.shape[1]
        cv2.arrowedLine(img, (w // 2, 200), (w // 2, 140), (0, 255, 255), 3, tipLength=0.35)
        cv2.putText(img, "ADELANTE", (w // 2 + 12, 165), cv2.FONT_HERSHEY_SIMPLEX, 0.6, (0, 255, 255), 2,
                    cv2.LINE_AA)

    def status_lines(self) -> list[str]:
        piso = ("sostener piso: APAGADO (se alejo demasiado)" if self._piso_apagado else
                f"sostener piso: {'si' if self.e.sostener_piso else 'no'}, calidad {self.piso.q:.2f}")
        return ["ESPEJO: vista hacia abajo, SIN vista al frente" + (" (quieto)" if self.e.quieto else ""), piso] \
            + super().status_lines()

    def _log_extra(self) -> list:
        v, tid = self._vis, self._target
        fl = v.tagframe.get(tid) if (v and tid) else None
        cells = [f"{fl[0]:+.0f}", f"{fl[1]:+.0f}", f"{fl[2]:+.0f}", f"{self._heights.get(tid, 0):.0f}"] if fl \
            else [""] * 4
        (pr, pf), (vr, vf) = self.piso.estado()
        return [len(v.dets) if v else "", tid or "", *cells,
                f"{pr:+.1f}", f"{pf:+.1f}", f"{vr:+.1f}", f"{vf:+.1f}", f"{self.piso.q:.2f}",
                f"{self._piso_i[0]:+.1f}", f"{self._piso_i[1]:+.1f}",
                self._piso_modo()]

    def _piso_modo(self) -> str:
        """Quién sostiene la posición con el piso: "pid", "apagado" (el seguro la apagó) o "no"
        (sostener_piso en false). Para revisar vuelos (resumen_piso.py; en las bitácoras de antes
        del 17-nov también puede decir "kalman")."""
        if not self.e.sostener_piso:
            return "no"
        return "apagado" if self._piso_apagado else "pid"

    # ---- sostener la posición con el piso
    def _goto(self, state: str, reason: str) -> None:
        prev = getattr(self, "state", None)
        super()._goto(state, reason)
        piso = getattr(self, "piso", None)
        if piso is not None and (state == "TAKEOFF" or (state == "ADVANCE" and prev == "EXECUTE")):
            pos = (0.0, 0.0)  # el punto de despegue, o el inicio del tramo nuevo
            if state == "ADVANCE":
                self._avisados = set()
                fl = self._tag_visto()
                if fl is None:
                    # justo ahora no se ve (se corrió al girar, parpadeo): donde debe estar, desde la
                    # última vez que se vio. Antes el tramo arrancaba desde donde quedó el dron y, si
                    # se había corrido ~40 cm al girar, no pasaba por el siguiente tag (pista 2, 12-nov)
                    pred = self._donde_objetivo(time.monotonic(), 2.0)
                    fl = None if pred is None else (pred[0], pred[1], 0.0)
                    if pred is not None:
                        print(f"[vuelo] tramo nuevo desde donde debe estar el tag {self._target}, que no se ve "
                              f"(adelante {pred[0]:+.0f}, lado {pred[1]:+.0f} cm)")
                # dónde queda el tag recién ejecutado en el piso del tramo: para no volver a
                # ejecutarlo, pero sí a otro con el mismo número (ver mismo_tag_cm)
                self._ult_ejecutado = self._target
                self._ejecutados_ids.add(self._target)
                if self.e.sostener_tag and fl is not None:  # la línea del tramo pasa por el tag ejecutado,
                    pos = (-fl[1], -fl[0])  # no por donde quedó el dron: el dron respecto al tag
            piso.reiniciar(pos)
            if state == "ADVANCE":
                self._ult_track = None if fl is None else (fl[0], fl[1], piso.estado()[0])
            getattr(self, "_piso_lejos", deque()).clear()
        if state == "TAKEOFF" and hasattr(self, "_piso_i"):
            # vuelo nuevo: la integral empieza con lo que se sabe de este dron (piso_i_inicial). Entre
            # tramos se conserva: la deriva es del dron y va con él (siempre a su derecha)
            self._piso_i[:] = self.e.piso_i_inicial

    def _start_execute(self, now: float, how: str) -> None:
        giro = sum(p[1] for p in ACTIONS.get(self._target, []) if p[0] == "yaw")
        super()._start_execute(now, how)
        # Con espejo el dron no se alinea con el tag: sostiene el rumbo del tramo. El rumbo de
        # salida va desde ese rumbo, no desde el yaw medido al llegar: si no, el error de cada
        # giro se suma y tras 6–8 tags iba ~10° chueco y pasaba de largo (pistas al azar, 12-nov)
        if not self.e.alinear_bordes:
            salida = wrap_deg(self._heading + giro)
            if self.state == "ADVANCE":  # ya terminó (p. ej. flip omitido por batería)
                self._heading = salida
            self._exit_heading = salida

    def _ult_pred(self, now: float) -> tuple[float, float]:
        """Dónde debe verse ahora el recién ejecutado (adelante, derecha): donde se vio la última
        vez, corrido con lo que se movió el dron desde entonces (medida del piso, si la hay)."""
        f, r, p0 = self._ult_track
        if self.piso.valido(now):
            d = self.piso.estado()[0] - p0  # (derecha, adelante) que avanzó el dron
            f, r = f - d[1], r - d[0]
        return f, r

    def _es_el_ejecutado(self, tid: int, fwd: float, right: float, now: float) -> bool | None:
        """¿Este tag (adelante, derecha respecto al dron) es el recién ejecutado? Por seguimiento:
        a menos de mismo_tag_cm de donde debe estar. None si no se puede saber (no se vio al
        arrancar el tramo)."""
        if tid != self._ult_ejecutado:
            return None
        if self._ult_track is None:
            return None
        pf, pr = self._ult_pred(now)
        return math.hypot(fwd - pf, right - pr) < self.e.mismo_tag_cm

    def _ignorar(self, tid: int, fl, now: float) -> bool:
        """Avanzando, ¿no hay que ejecutar este tag?
        - El recién ejecutado: por seguimiento (ver mismo_tag_cm); si no se vio al arrancar, por número.
        - Antes del primer tag, el de inicio (ignorar_inicio), como antes.
        - Uno que ya se ejecutó antes (no el último): solo si está en la línea del tramo (adelante y
          a menos de pasillo_cm de lado). Con un giro de 180° se vuelve a pasar por el anterior, y
          en la pista puede haber dos tags con el mismo número; uno viejo a un lado no se toma.
        - Uno nuevo: siempre, esté donde esté (como antes)."""
        if tid == self._ult_ejecutado:
            mismo = self._es_el_ejecutado(tid, fl[0], fl[1], now)
            return self._ignored(tid, now) if mismo is None else mismo
        if tid in self._ejecutados_ids:
            return not (fl[0] > -10 and abs(fl[1]) < self.e.pasillo_cm)
        return self._ult_ejecutado is None and self._ignored(tid, now)

    def _donde_objetivo(self, now: float, max_s: float) -> tuple[float, float] | None:
        """(adelante, derecha) donde debe estar ahora el tag objetivo aunque no se vea: donde se vio
        la última vez, girado con lo que giró el dron desde entonces y corrido con lo que se movió
        (medida del piso; girando no mide, así que ahí cuenta solo el giro). None si hace más de
        max_s que no se ve."""
        tv = self._target_visto
        if tv is None or now - tv[0] > max_s:
            return None
        _, f, r, p0, yaw0 = tv
        th = math.radians(wrap_deg(self.tel.snapshot()[0].get("yaw", 0) - yaw0))
        f, r = f * math.cos(th) + r * math.sin(th), -f * math.sin(th) + r * math.cos(th)  # girar a la derecha: lo de adelante queda a la izquierda
        d = self.piso.estado()[0] - p0  # (derecha, adelante) que se movió
        return f - d[1], r - d[0]

    def _tag_visto(self):
        """(adelante, derecha, giro) del tag objetivo si se ve ahora, si no None."""
        v = self._vision(time.monotonic())
        return v.tagframe.get(self._target) if (v is not None and self._target) else None

    def _piso_mando(self, eje: int, err: float, vel: float, dt: float) -> int:
        """PID de un eje (0 = de lado, 1 = adelante). err: cm que está corrido de donde debería
        estar; vel: cm/s que se está yendo. Devuelve el rc a sumar (al revés del error)."""
        e = self.e
        pd = e.piso_kp * err + e.piso_kd * vel
        total = pd + self._piso_i[eje]
        # anti-windup: no juntar más si ya va al tope empujando hacia el mismo lado
        if dt > 0 and not (abs(total) >= e.piso_max and total * err > 0):
            self._piso_i[eje] = max(-e.piso_i_max, min(e.piso_i_max, self._piso_i[eje] + e.piso_ki * err * dt))
        u = -(pd + self._piso_i[eje])
        return 0 if abs(u) < e.piso_dead else with_min(u, e.piso_min, e.piso_max)

    def _send_rc(self, lr: float, fb: float, ud: float, yaw: float) -> None:
        """Quieto y subiendo: volver al punto de despegue. Avanzando sin tag: sostener la línea
        del tramo (de lado). Solo con una medida del piso reciente; sin ella, como antes."""
        e, piso = self.e, getattr(self, "piso", None)
        if e.sostener_piso and piso is not None and not self._piso_apagado \
                and self.state in ("HOVER", "CRUISE", "ADVANCE") and piso.valido(time.monotonic()):
            (pr, pf), (vr, vf) = piso.estado()
            now = time.monotonic()
            lejos = abs(pr) if self.state == "ADVANCE" else math.hypot(pr, pf)
            h = self._piso_lejos
            if h and (h[-1][2] != (self.state == "ADVANCE") or now - h[-1][0] > 0.5):
                h.clear()  # otro tipo de corrección, o hubo una pausa
            h.append((now, lejos, self.state == "ADVANCE"))
            while now - h[0][0] > 1.5:
                h.popleft()
            alejo = lejos - min(x[1] for x in h)
            if alejo > e.piso_alejandose_cm or lejos > e.piso_limite_cm:
                self._piso_apagado = True
                why = f"se alejo {alejo:.0f} cm en 1.5 s corrigiendo" if alejo > e.piso_alejandose_cm \
                    else f"esta a {lejos:.0f} cm"
                self.reason += f" | sostener_piso APAGADO: {why} (revisar la medida del piso)"
                print(f"[vuelo] sostener_piso apagado: {why}")
            if not self._piso_apagado:
                dt = now - self._piso_t if self._piso_t is not None and now - self._piso_t < 0.5 else 0.0
                self._piso_t = now
                lr = lr + self._piso_mando(0, pr, vr, dt)
                if self.state != "ADVANCE" or fb == 0:  # avanzando, adelante manda la misión (salvo --quieto)
                    fb = fb + self._piso_mando(1, pf, vf, dt)
        elif e.sostener_tag and self.state == "EXECUTE" and self._prim \
                and (self._prim[0] in ("yaw", "wait", "alt_to")):
            # girando, en pausa, subiendo/bajando (también antes y después del flip): quedarse sobre
            # el tag. Solo de lado y adelante; la altura la manda la recuperación del flip. Antes no
            # se sostenía en el flip y en sus ~15 s se iba ~1 m (simulador, 12-nov)
            now = time.monotonic()
            v = self._vision(now)
            fl = v.tagframe.get(self._target) if (v is not None and self._target) else None
            if fl is not None:
                self._aviso_perdido = False
                vf, vr = self._tag_velocity(v.t, fl[0], fl[1], self.tel.snapshot()[0].get("yaw", 0))
                tope = e.sostener_tag_max
                lr, fb = lr + self._center_axis(fl[1], vr, tope), fb + self._center_axis(fl[0], vf, tope)
            else:
                # se dejó de ver (al girar, si se corrió más de ~20 cm, el tag sale por la orilla de
                # adelante de la vista: 16-nov). Dejar de girar e ir a donde debe estar; al volver a
                # verlo sigue el giro. Si no aparece en buscar_s, seguir como antes
                pred = self._donde_objetivo(now, e.buscar_s)
                if pred is not None:
                    pf, pr = pred
                    if yaw and not getattr(self, "_aviso_perdido", False):
                        self._aviso_perdido = True
                        print(f"[vuelo] tag {self._target} perdido girando: dejo de girar y regreso a él "
                              f"(adelante {pf:+.0f}, lado {pr:+.0f} cm)")
                    yaw = 0
                    lr += with_min(e.center_kp * pr, e.center_min, e.sostener_tag_max) if abs(pr) > e.center_tol_cm else 0
                    fb += with_min(e.center_kp * pf, e.center_min, e.sostener_tag_max) if abs(pf) > e.center_tol_cm else 0
        super()._send_rc(lr, fb, ud, yaw)

    # ---- avanzar mirando el piso
    def _advance(self, yaw: float, now: float, elapsed: float) -> None:
        e, v = self.e, self._vision(now)
        if v is None:
            return self._send_rc(0, 0, 0, 0)
        if not self._started:
            self._started = True
            if e.ignorar_inicio and not e.quieto and self._start_ids:  # en --quieto el de debajo es el de la prueba
                # el tag que vio al despegar es el de inicio: no ejecutarlo. Antes se tomaba el
                # que estuviera debajo al empezar a avanzar, pero tras la deriva del despegue
                # ese ya podía ser el primero del recorrido (real 9-nov: ignoró el tag 1)
                with self._vis_lock:
                    for tid in self._start_ids:
                        self._last_seen[tid] = now
                print(f"[vuelo] ADVANCE: ignorando el tag de inicio {sorted(self._start_ids)}")
        cands = []
        for d in v.dets:
            if d.tag_id not in v.confirmed or d.tag_id not in v.tagframe:
                continue
            fl = v.tagframe[d.tag_id]
            if not self._ignorar(d.tag_id, fl, now):
                cands.append((abs(fl[0]) + abs(fl[1]), d.tag_id))
            elif d.tag_id != self._ult_ejecutado and d.tag_id not in self._avisados:
                # un tag ya ejecutado antes que se ve fuera de la línea del tramo: avisar una vez por
                # tramo (si se pasa de uno así, aquí se ve por qué; 16-nov)
                self._avisados.add(d.tag_id)
                print(f"[vuelo] ADVANCE: tag {d.tag_id} ignorado (ya ejecutado, fuera del pasillo): "
                      f"adelante {fl[0]:+.0f}, lado {fl[1]:+.0f} cm")
        if cands:
            _, tid = min(cands)
            fwd, right, rot = v.tagframe[tid]
            self._target, self._t_target_seen, self._t_hold = tid, now, None
            self._center_hist.clear()
            return self._goto("APPROACH", f"tag {tid} ({TAG_FUNCTIONS[tid]}) debajo: adelante {fwd:+.0f}, "
                                          f"lado {right:+.0f} cm")
        limit = e.quieto_timeout_s if e.quieto else e.advance_timeout_s
        if elapsed > limit:
            return self._begin_landing("LANDING", f"sin tags debajo por {limit:.0f} s: fin")
        self._send_rc(0 if e.quieto else e.advance_lr, 0 if e.quieto else e.advance_fb, 0, self._heading_rate(yaw))

    # ---- centrarse encima y alinearse
    def _approach(self, yaw: float, alt: float, now: float, elapsed: float) -> None:
        e, m, v = self.e, self.m, self._vision(now)
        if v is None:
            return self._send_rc(0, 0, 0, 0)
        fl = v.tagframe.get(self._target)
        if fl is None:
            # se salió de la vista (11-nov: por la deriva, casi siempre por la orilla): ir a donde
            # debe estar, contando lo que el dron se movió desde que lo vio; si no aparece en
            # buscar_s, seguir avanzando en vez de aterrizar
            if now - self._t_target_seen > e.buscar_s:
                return self._goto("ADVANCE", f"tag {self._target} perdido al centrarse: sigo avanzando")
            lf, lr = self._last_floor
            if self.piso.valido(now):
                d = self.piso.estado()[0] - self._pos_visto
                lr, lf = lr - d[0], lf - d[1]
            return self._send_rc(with_min(e.center_kp * lr, e.center_min, e.piso_max) if abs(lr) > e.center_tol_cm else 0,
                                 with_min(e.center_kp * lf, e.center_min, e.piso_max) if abs(lf) > e.center_tol_cm else 0,
                                 0, self._heading_rate(yaw))
        self._t_target_seen = now
        self._pos_visto = self.piso.estado()[0]
        fwd, right, rot = fl
        self._last_floor = (fwd, right)
        vf, vr = self._tag_velocity(v.t, fwd, right, yaw)
        fb, lr = self._center_axis(fwd, vf), self._center_axis(right, vr)
        if e.alinear_bordes:
            # tag girado a la derecha en la imagen (+): girar el dron a la derecha lo endereza
            yr = 0 if abs(rot) <= e.rot_tol_deg else with_min(e.rot_kp * rot, m.az_min, m.az_max)
        else:
            yr = self._heading_rate(yaw)  # sostener el rumbo del tramo, esté como esté girado el tag
        self._send_rc(lr, fb, 0, yr)
        settled = (abs(fwd) <= e.center_tol_cm and abs(right) <= e.center_tol_cm
                   and abs(vf) <= e.center_vel_tol and abs(vr) <= e.center_vel_tol)
        if settled and yr == 0:
            self._t_hold = self._t_hold or now
            if now - self._t_hold >= m.hold_s:
                return self._start_execute(now, f"encima: adelante {fwd:+.0f}, lado {right:+.0f} cm, giro {rot:+.0f}")
        else:
            self._t_hold = None
        if elapsed > e.centrar_max_s:
            self._start_execute(now, f"centrado incompleto (adelante {fwd:+.0f}, lado {right:+.0f}, giro {rot:+.0f})")

    def _tag_velocity(self, t_frame: float, fwd: float, right: float, yaw: float | None = None) -> tuple[float, float]:
        """Velocidad del tag respecto al dron (cm/s) en el último ~0.5 s, una muestra por frame.
        Con yaw, sin lo que se mueve solo porque el dron gira: cada muestra se pasa al rumbo de
        ahora. Si no, girando sobre un tag a 10 cm parecía moverse ~6 cm/s y el freno empujaba
        de lado (16-nov)."""
        h = self._center_hist
        if not h or t_frame > h[-1][0]:
            h.append((t_frame, fwd, right, yaw))
        pts = [p for p in h if t_frame - p[0] <= 0.5]
        if len(pts) < 4 or pts[-1][0] - pts[0][0] < 0.25:
            return 0.0, 0.0
        t, fs, rs = [p[0] for p in pts], [p[1] for p in pts], [p[2] for p in pts]
        if yaw is not None and all(p[3] is not None for p in pts):
            fs, rs = [], []
            for _, f, r, y in pts:
                th = math.radians(wrap_deg(yaw - y))
                fs.append(f * math.cos(th) + r * math.sin(th))
                rs.append(-f * math.sin(th) + r * math.cos(th))
        return float(np.polyfit(t, fs, 1)[0]), float(np.polyfit(t, rs, 1)[0])

    def _center_axis(self, err: float, vel: float, tope: float | None = None) -> int:
        """Mando de un eje para quedar encima del tag. Con el retraso del video y la
        inercia, sin frenar se pasaba y oscilaba; aquí la velocidad resta: si ya va
        hacia el tag lo bastante rápido, no empuja, y si se pasa, manda en contra.
        tope: rc máximo (center_max si no se dice)."""
        e = self.e
        tope = e.center_max if tope is None else tope
        u = e.center_kp * err + e.center_kd * vel  # vel = cambio de err; acercarse la hace negativa
        if abs(err) > e.center_tol_cm and abs(vel) < e.center_vel_tol and u * err > 0:
            return with_min(u, e.center_min, tope)  # lejos y quieto: empujar hacia el tag
        if abs(u) < e.center_dead:
            return 0
        return with_min(u, e.center_min, tope)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--config", default=str(ROOT / "config" / "flight.json"))
    ap.add_argument("--mission", default=str(ROOT / "config" / "mission_tags.json"))
    ap.add_argument("--espejo-config", default=str(ROOT / "config" / "mission_espejo.json"))
    ap.add_argument("--calib", default=str(DEFAULT_CALIB))
    ap.add_argument("--espejo", choices=["v", "h"], help="sobrescribe cómo se voltea la imagen")
    ap.add_argument("--quieto", action="store_true", help="no avanzar: esperar un tag debajo")
    ap.add_argument("--record", help="grabar el video crudo (mp4)")
    ap.add_argument("--dron", help="ajustes de ese dron: config/mision_dron<N>.json (p. ej. --dron 7)")
    args = ap.parse_args()

    cfg = FlightConfig.load(Path(args.config))
    mcfg = MissionConfig.load(Path(args.mission))
    ecfg = MirrorConfig.load(Path(args.espejo_config))
    if args.espejo:
        ecfg.espejo = args.espejo
    if args.quieto:
        ecfg.quieto = True
    for cambio in ajustes_dron(ecfg, args.dron):
        print(f"[hmi] Tello {args.dron}: {cambio}")
    cfg.hover_s, cfg.max_flight_s = mcfg.start_hover_s, mcfg.mission_max_s
    tello, reader = connect()
    log_path = ROOT / "logs" / time.strftime("espejo_%Y%m%d_%H%M%S.csv")
    print(f"[hmi] bitácora: {log_path}  |  tags de {mcfg.tag_cm:g} cm  |  espejo {ecfg.espejo}")
    run_app(MirrorMission(tello, cfg, mcfg, ecfg, log_path, Path(args.calib)), tello, reader, args.record,
            "mision espejo")


if __name__ == "__main__":
    main()
