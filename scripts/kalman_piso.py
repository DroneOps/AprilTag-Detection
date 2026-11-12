"""Filtro de Kalman para sostener la posición con el piso (mision_espejo.py, piso_control "kalman").

Por cada eje del dron (0 = de lado, + a la derecha; 1 = adelante) estima tres cosas:

    p  posición (cm) respecto a donde debería estar      (la mide FlujoPiso, atrasada)
    v  velocidad que le dan los rc (cm/s)                 (no se mide: sale del modelo)
    d  deriva (cm/s): lo que se mueve solo                (no se mide: sale de la diferencia)

con el modelo del Tello medido en las calibraciones de rc (docs/tello.md, config/sim_tello.json):

    rc -> velocidad pedida  vc = ganancia·(|rc| − zona) con el signo del rc (0 si |rc| ≤ zona)
    v  se acerca a vc con una constante de tiempo respuesta_s
    p' = v + d

La deriva hace el trabajo de la integral del PID, pero sin esperar a que haya error: el filtro
ve que el dron se mueve sin que se lo pidan y lo aprende en ~1–2 s (también al despegar). Por
eso no hace falta suponer una deriva por dron: arranca en 0 y la mide.

El video llega atrasado (~0.17 s): cada medida se aplica en el momento en que se tomó la imagen
y luego se predice hasta ahora con los rc que ya se mandaron. El control usa esa predicción.

Si lo medido deja de cuadrar con lo predicho (NIS promedio alto), se apaga y la misión regresa
al PID: el modelo no sirve para ese dron (otra ganancia, otro atraso, la medida al revés).
"""
from __future__ import annotations

import math
from collections import deque
from dataclasses import dataclass

import numpy as np


@dataclass
class ModeloRc:
    ganancia: float = 1.45  # cm/s por rc arriba de la zona muerta
    zona: float = 5.0  # rc que no mueve al dron
    respuesta_s: float = 0.75  # constante de tiempo de la velocidad
    atraso_mando_s: float = 0.04  # el rc hace efecto esto después de mandarlo
    atraso_video_s: float = 0.17  # la imagen es de esto antes de que llega

    def vel(self, rc: float) -> float:
        """Velocidad estable que pide un rc."""
        return math.copysign(self.ganancia * (abs(rc) - self.zona), rc) if abs(rc) > self.zona else 0.0

    def rc(self, vel: float) -> float:
        """El rc (sin redondear) que pide esa velocidad: el inverso de vel()."""
        if abs(vel) < 1e-6:
            return 0.0
        return math.copysign(self.zona + abs(vel) / self.ganancia, vel)


class KalmanPiso:
    """Los dos ejes (derecha, adelante). Uso, en cada paso del control:
        mando(t, (lr, fb))          los rc que se mandaron
        medida(t_imagen, (der, ade))  cuando FlujoPiso da una posición nueva
        p, v, d = prediccion(ahora)   para el control
    """

    def __init__(self, m: ModeloRc, q_deriva: float = 50.0, q_vel: float = 20.0, r_cm: float = 1.5,
                 deriva0=(0.0, 0.0), sd_deriva0: float = 8.0, hueco_s: float = 0.3, salto_nis: float = 25.0,
                 nis_s: float = 1.0) -> None:
        self.m = m
        self.qd, self.qv, self.r = q_deriva, q_vel, r_cm ** 2
        self.deriva0, self.sd_d0 = np.array(deriva0, float), sd_deriva0
        self.hueco_s = hueco_s  # sin medidas por esto (girando, flip, sin textura): la siguiente re-ancla
        self.salto_nis = salto_nis  # una medida así de lejos de lo esperado: re-anclar en vez de corregir
        self.nis_s = nis_s
        self.mandos: deque = deque()  # (t en que hace efecto, (vc_der, vc_ade))
        self.reiniciar()

    def reiniciar(self, deriva=None) -> None:
        """Al despegar: posición y velocidad 0, deriva la inicial (con su incertidumbre)."""
        d0 = self.deriva0 if deriva is None else np.array(deriva, float)
        self.x = np.zeros((2, 3))
        self.x[:, 2] = d0
        self.P = np.array([np.diag([4.0, 4.0, self.sd_d0 ** 2]) for _ in range(2)])
        self.t: float | None = None  # tiempo del estado (el de la última medida)
        self.t_medida = -math.inf
        self.nis = 0.0  # promedio (~nis_s) de la innovación normalizada; ~1 si el modelo cuadra
        self.innov = np.zeros(2)
        self.saltos = 0
        self.mandos.clear()

    def desplazar(self, delta) -> None:
        """La misión cambió el origen de la posición (tramo nuevo): mover p igual."""
        self.x[:, 0] += np.asarray(delta, float)

    # ---- entradas
    def mando(self, t: float, rc) -> None:
        vc = (self.m.vel(rc[0]), self.m.vel(rc[1]))
        te = t + self.m.atraso_mando_s
        if not self.mandos or self.mandos[-1][1] != vc:
            self.mandos.append((te, vc))
        # los que ya no hacen falta (anteriores al estado) se van, menos el vigente
        while len(self.mandos) > 1 and self.t is not None and self.mandos[1][0] <= self.t:
            self.mandos.popleft()

    def _vc(self, t: float) -> np.ndarray:
        vc = (0.0, 0.0)
        for te, v in self.mandos:
            if te <= t:
                vc = v
            else:
                break
        return np.array(vc)

    def _propagar(self, x: np.ndarray, P: np.ndarray, t0: float, t1: float) -> tuple[np.ndarray, np.ndarray]:
        """De t0 a t1 con los mandos, por tramos de mando constante (exacto para el modelo)."""
        x, P = x.copy(), P.copy()
        cortes = [te for te, _ in self.mandos if t0 < te < t1]
        ts = [t0, *cortes, t1]
        tau = self.m.respuesta_s
        for a, b in zip(ts[:-1], ts[1:]):
            dt = b - a
            if dt <= 0:
                continue
            vc = self._vc(a + 1e-9)
            e = math.exp(-dt / tau)
            F = np.array([[1.0, tau * (1 - e), dt], [0.0, e, 0.0], [0.0, 0.0, 1.0]])
            # ruido: la deriva y la velocidad como caminatas al azar (q·dt), integradas a la posición
            qd, qv = self.qd, self.qv
            Q = np.array([[(qd + qv) * dt ** 3 / 3, qv * dt ** 2 / 2, qd * dt ** 2 / 2],
                          [qv * dt ** 2 / 2, qv * dt, 0.0],
                          [qd * dt ** 2 / 2, 0.0, qd * dt]])
            for k in range(2):
                p, v, d = x[k]
                x[k] = (p + d * dt + vc[k] * dt + (v - vc[k]) * tau * (1 - e),
                        vc[k] + (v - vc[k]) * e,
                        d)
                P[k] = F @ P[k] @ F.T + Q
        return x, P

    def medida(self, t_recibida: float, pos) -> bool:
        """Posición de FlujoPiso de la imagen que llegó en t_recibida. Devuelve True si corrigió
        con ella (False si solo re-ancló: tras un hueco o un salto)."""
        tm = t_recibida - self.m.atraso_video_s
        z = np.asarray(pos, float)
        if self.t is None or tm - self.t > self.hueco_s or tm <= self.t:
            if self.t is not None and tm <= self.t:
                return False  # medida vieja
            # primera medida o tras un hueco (girando, flip): lo que se movió sin medirse no se
            # puede corregir; se toma la medida como está y se conservan la velocidad y la deriva
            if self.t is not None:
                self.x, self.P = self._propagar(self.x, self.P, self.t, tm)
            self._anclar(z)
            self.t = self.t_medida = tm
            return False
        x, P = self._propagar(self.x, self.P, self.t, tm)
        corrigio = True
        nis_med = []
        for k in range(2):
            y = z[k] - x[k, 0]
            S = P[k, 0, 0] + self.r
            nis = y * y / S
            if nis > self.salto_nis:  # salto (la medida brincó): re-anclar este eje
                x[k, 0] = z[k]
                P[k, 0, :] = P[k, :, 0] = 0.0
                P[k, 0, 0] = self.r
                self.saltos += 1
                corrigio = False
            else:
                K = P[k, :, 0] / S
                x[k] = x[k] + K * y
                P[k] = P[k] - np.outer(K, P[k, 0, :])
            self.innov[k] = y
            nis_med.append(min(nis, 50.0))
        a = min(1.0, (tm - self.t) / self.nis_s)
        self.nis += a * (float(np.mean(nis_med)) - self.nis)
        self.x, self.P, self.t, self.t_medida = x, P, tm, tm
        return corrigio

    def _anclar(self, z: np.ndarray) -> None:
        for k in range(2):
            self.x[k, 0] = z[k]
            self.P[k, 0, :] = self.P[k, :, 0] = 0.0
            self.P[k, 0, 0] = self.r

    # ---- salida
    def prediccion(self, ahora: float) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
        """(p, v, d) de cada eje cuando haga efecto el mando que se manda ahora."""
        if self.t is None:
            return np.zeros(2), np.zeros(2), self.x[:, 2].copy()
        x, _ = self._propagar(self.x, self.P, self.t, ahora + self.m.atraso_mando_s)
        return x[:, 0].copy(), x[:, 1].copy(), x[:, 2].copy()

    def sd_deriva(self) -> np.ndarray:
        return np.sqrt(self.P[:, 2, 2])


def vel_eje(p: float, v: float, d: float, kp: float, kd: float) -> float:
    """Velocidad a pedir con el rc en un eje para llegar a p = 0 y quedarse: la que cancela la
    deriva, más la que lo regresa (kp·p) y la que frena (kd·velocidad total). Con τ la respuesta
    del dron, el lazo queda τ·p'' + (1 + kd)·p' + kp·p = 0: con τ 0.75, kp 1.2 y kd 1.0, sin
    oscilar (amortiguamiento ~1) y en ~3 s."""
    return -d - kp * p - kd * (v + d)
