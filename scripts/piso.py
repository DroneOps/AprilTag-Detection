"""Medir y sostener la posición del dron con el piso visto por el espejo.

- FlujoPiso: cuánto se movió el dron sobre el piso (correlación de fase entre cuadros).
- punto_bajo_dron: qué pixel queda justo debajo del dron (depende de la inclinación del espejo).
- SostenerPiso: el PID que lo regresa a donde debe estar, con su seguro.

Lo usa mision_espejo.py. Cómo funciona y cómo ajustarlo: docs/arquitectura.md, "Sostener la
posición con el piso".
"""
from __future__ import annotations

import math
import threading
from collections import deque

import cv2
import numpy as np

from first_flight import with_min


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


class SostenerPiso:
    """Sostener la posición con el piso: un PID por eje (de lado y adelante) con la medida de
    FlujoPiso, más un seguro que lo apaga si la corrección empuja hacia afuera.

    - Quieto y subiendo (HOVER, CRUISE): regresa al punto de despegue (los dos ejes).
    - Avanzando (ADVANCE): sostiene la línea del tramo, solo de lado; adelante manda la misión.
    La integral junta el empuje que hace falta contra una deriva constante (el Tello 7 se va
    ~12 cm/s a la derecha). Empieza cada vuelo con piso_i_inicial y se conserva entre tramos:
    la deriva es del dron. Ajustes: piso_kp, piso_kd, piso_ki, piso_i_max, piso_min, piso_max,
    piso_dead, piso_alejandose_cm y piso_limite_cm (espejo_config.py). Cómo ajustarlos: "Cómo
    ajustarlo" en docs/arquitectura.md."""

    def __init__(self, e) -> None:
        self.e = e  # MirrorConfig
        self.i = np.zeros(2)  # parte integral (derecha, adelante), en rc
        self.t = None  # última vez que corrigió
        self.apagado = False  # el seguro lo apagó en este vuelo
        self.lejos: deque = deque()  # (t, distancia a donde debería estar, avanzando) mientras corrige

    def nuevo_vuelo(self) -> None:
        """Al despegar: la integral empieza con lo que se sabe de este dron (piso_i_inicial)."""
        self.i[:] = self.e.piso_i_inicial

    def nuevo_tramo(self) -> None:
        """Al despegar o al empezar un tramo: el seguro empieza a contar de nuevo."""
        self.lejos.clear()

    def _eje(self, eje: int, err: float, vel: float, dt: float) -> int:
        """PID de un eje (0 = de lado, 1 = adelante). err: cm que está corrido de donde debería
        estar; vel: cm/s que se está yendo. Devuelve el rc a sumar (al revés del error)."""
        e = self.e
        pd = e.piso_kp * err + e.piso_kd * vel
        total = pd + self.i[eje]
        # anti-windup: no juntar más si ya va al tope empujando hacia el mismo lado
        if dt > 0 and not (abs(total) >= e.piso_max and total * err > 0):
            self.i[eje] = max(-e.piso_i_max, min(e.piso_i_max, self.i[eje] + e.piso_ki * err * dt))
        u = -(pd + self.i[eje])
        return 0 if abs(u) < e.piso_dead else with_min(u, e.piso_min, e.piso_max)

    def mando(self, pos, vel, avanzando: bool, con_adelante: bool, now: float) -> tuple[int, int, str | None]:
        """rc (lado, adelante) a sumar a lo que pide la misión, con la posición y velocidad del
        piso (derecha, adelante). con_adelante: corregir también hacia adelante (avanzando no,
        salvo en --quieto). El tercer valor dice por qué se apagó el seguro (None si no)."""
        e = self.e
        (pr, pf), (vr, vf) = pos, vel
        # seguro, por si en el dron real la medida sale al revés y la corrección empuja hacia
        # afuera: apagarlo si, corrigiendo, se aleja piso_alejandose_cm en 1.5 s, o si se pasa de
        # piso_limite_cm
        lejos = abs(pr) if avanzando else math.hypot(pr, pf)
        h = self.lejos
        if h and (h[-1][2] != avanzando or now - h[-1][0] > 0.5):
            h.clear()  # otro tipo de corrección, o hubo una pausa
        h.append((now, lejos, avanzando))
        while now - h[0][0] > 1.5:
            h.popleft()
        alejo = lejos - min(x[1] for x in h)
        if alejo > e.piso_alejandose_cm or lejos > e.piso_limite_cm:
            self.apagado = True
            why = f"se alejo {alejo:.0f} cm en 1.5 s corrigiendo" if alejo > e.piso_alejandose_cm \
                else f"esta a {lejos:.0f} cm"
            return 0, 0, why
        dt = now - self.t if self.t is not None and now - self.t < 0.5 else 0.0
        self.t = now
        lr = self._eje(0, pr, vr, dt)
        fb = self._eje(1, pf, vf, dt) if con_adelante else 0
        return lr, fb, None
