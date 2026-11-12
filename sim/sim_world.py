#!/usr/bin/env python3
"""Mundo 3D simulado para probar las misiones sin volar (ver docs/simulador.md).

Renderiza la cámara del Tello (K, distorsión e inclinación de 11° reales de
config/camera_tello.json) con tags en paredes o en el piso, también a través del
espejo, y la misión los procesa con el detector y el PnP reales. La física del
dron está ajustada a bitácoras reales y a la calibración de rc del 24-oct:
horizontal 1.7*(|rc|-5) cm/s, vertical 0.9*(|rc|-3) subiendo y 0.5*(|rc|-3)
bajando, giro ~0.73*(|rc|-6.6) grados/s, 'h' que deriva, tof con ruido, y tras
un flip cae ~50 cm/s por 1–3 s. En piso, además, se hunde al avanzar y el mando
adelante + lado a la vez lo frena (como el 27-oct).

Uso:
    python sim/sim_world.py circuito          # un escenario
    python sim/sim_world.py todos             # todos, en paralelo
Escenarios: circuito pausa giro360 sube_ciego perdido flip8 caja deriva
            deriva_sin_lateral ladeado ladeado_sin_alinear angulo25 angulo38
            angulo38_deriva flip_prueba flip_prueba_bateria flip4 flip4_bateria tag_alto
            tag_bajo rc_calib sin_tags espejo_uno espejo_inicio espejo_cerca espejo_girado espejo_circuito espejo_quieto
            espejo_deriva espejo_flip espejo_inclinado espejo_inclinado_sin_config
            espejo_despegue_cae espejo_despegue_alto espejo_sin_ok
            espejo_lab espejo_gastado espejo_gastado_sin_rescate espejo_estacionario
            piso_uno piso_girado piso_circuito piso_deriva piso_flip piso_lento piso_rapido
            piso_hundimiento piso_lado piso_tof_falso piso_imu_mal

Corre en tiempo real (cada escenario tarda 30–70 s). Las bitácoras van a sim/logs/.
Con --dron N, encima de config/sim_tello.json se usa config/sim_tello_dron<N>.json (lo que
cambia en ese dron; el Tello 7 se va mucho más a la derecha):
    python sim/sim_world.py espejo_circuito --dron 7

El dron simulado se comporta según config/sim_tello.json (lo medido en vuelos reales; se
ajusta con sim/comparar_vuelos.py). Con --ideal usa el modelo de antes del 11-nov:
    python sim/sim_world.py espejo_circuito --ideal
"""
from __future__ import annotations

import collections
import json
import math
import subprocess
import sys
import threading
import time
from dataclasses import dataclass, fields, replace
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import first_flight as F  # noqa: E402
import mission_tags as M  # noqa: E402
import rc_calib as RC  # noqa: E402
import mision_espejo as ME  # noqa: E402
import mision_piso as MP  # noqa: E402
import test_tags as TT  # noqa: E402

CAL = json.loads((ROOT / "config" / "camera_tello.json").read_text())
K, D = np.array(CAL["K"]), np.array(CAL["dist"])
PITCH = math.radians(11)  # medido en las pruebas de piso
DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_25h9)
OVER: dict = {}  # cambios a MissionConfig por escenario


@dataclass
class SimParams:
    """Cómo se comporta el dron simulado. Los valores por defecto son el modelo "ideal" (el de
    antes del 11-nov). config/sim_tello.json los sobrescribe con lo medido en vuelos reales
    (sim/comparar_vuelos.py --ajustar). Con --ideal se ignora el JSON."""
    fuente: str = ""  # de dónde salieron los valores
    # horizontal: cm/s = ganancia·(|rc| − zona muerta); vertical igual, más rápido subiendo
    avance_ganancia: float = 1.7
    avance_zona_muerta: float = 5.0
    subir_ganancia: float = 0.9
    bajar_ganancia: float = 0.5
    vertical_zona_muerta: float = 3.0
    respuesta_s: float = 0.4  # tiempo en llegar a la velocidad horizontal pedida
    vertical_respuesta_s: float = 0.4  # ...y a la vertical
    # giro: °/s = ganancia·(|rc| − zona muerta); "sigue" = parte del giro que continúa después
    # de soltar el mando y se apaga en giro_sigue_s (real 9-nov: de 88° siguió hasta 101°)
    giro_ganancia: float = 0.73
    giro_zona_muerta: float = 6.6
    giro_respuesta_s: float = 0.15
    giro_sigue: float = 0.0
    giro_sigue_s: float = 2.0
    mando_atraso_s: float = 0.0  # el rc tarda esto en hacer efecto
    video_atraso_s: float = 0.0  # la imagen llega con este atraso (real ~0.17 s)
    deriva_cm_s: float = 2.0  # viento/deriva aleatoria con rc en 0 (desviación)
    # deriva constante en el marco del dron, también al despegar (11-nov, medida con el piso
    # visto por el espejo: los dos Tellos se van a la derecha, el 1 ~4 cm/s y el 7 ~14 cm/s)
    deriva_lado_cm_s: float = 0.0  # + = a la derecha del dron
    deriva_adelante_cm_s: float = 0.0
    hundimiento_combo_cm_s: float = 0.0  # extra al pedir lado y adelante a la vez (11-nov: ~7–8)
    giro_deriva_cm_s: float = 0.0  # al girar fuerte se corre hacia un lado al azar (11-nov: 26–42 cm en giros de 90°)
    hundimiento_cm_s: float | None = None  # al avanzar; None: 15 en piso y 0 en otro caso
    combo: float | None = None  # adelante y de lado a la vez; None: 0.55 en piso y 1 en otro caso
    # despegue: sube a pico y se asienta en una altura entre los dos valores; el "ok" llega
    # entre despegue_ok_s (null: al llegar arriba, como el modelo ideal)
    despegue_cm: tuple = (65.0, 65.0)
    despegue_pico_cm: float = 0.0
    despegue_ok_s: tuple | None = None
    temp_inicial_c: float = 65.0
    temp_c_por_min: float = 0.0  # cuánto se calienta volando

    @classmethod
    def load(cls, path: Path) -> SimParams:
        data = json.loads(path.read_text()) if path.exists() else {}
        unknown = set(data) - {f.name for f in fields(cls)}
        if unknown:
            raise SystemExit(f"{path}: claves desconocidas {sorted(unknown)}")
        for k in ("despegue_cm", "despegue_ok_s"):
            if isinstance(data.get(k), list):
                data[k] = tuple(data[k])
        return cls(**data)


SIM_JSON = ROOT / "config" / "sim_tello.json"


def json_dron(dron: str) -> Path:
    return ROOT / "config" / f"sim_tello_dron{dron}.json"


def cargar_params(dron: str | None = None) -> SimParams:
    """config/sim_tello.json y, con dron, encima config/sim_tello_dron<N>.json (solo lo que
    cambia en ese dron, p. ej. su deriva)."""
    p = SimParams.load(SIM_JSON)
    if dron:
        path = json_dron(dron)
        if not path.exists():
            raise SystemExit(f"no existe {path.relative_to(ROOT)}")
        extra = SimParams.load(path)  # valida las claves
        data = json.loads(path.read_text())
        p = replace(p, **{k: getattr(extra, k) for k in data})
    return p


P = cargar_params()  # --ideal lo cambia por SimParams() y --dron N agrega su perfil


def mando(rc: float, zona: float, ganancia: float) -> float:
    """Velocidad estable (cm/s o °/s) que da un rc, con su zona muerta."""
    return math.copysign(ganancia * (abs(rc) - zona), rc) if abs(rc) > zona else 0.0


def paso_giro(rate: float, sigue: float, yr: float, dt: float, p: SimParams) -> tuple[float, float]:
    """Un paso del giro. El rumbo avanza (rate + sigue)·dt."""
    w = mando(yr, p.giro_zona_muerta, p.giro_ganancia)
    rate += (w - rate) * min(1.0, dt / max(p.giro_respuesta_s, 1e-3))
    sigue += (p.giro_sigue * w - sigue) * min(1.0, dt / max(p.giro_sigue_s, 1e-3))
    return rate, sigue


def paso_vel(v, rc, dt: float, p: SimParams, speed_factor=1.0, combo=1.0, sag=0.0) -> list[float]:
    """Un paso de la velocidad [adelante, derecha, arriba] en el marco del dron."""
    lr, fb, ud = rc[0], rc[1], rc[2]
    g = p.avance_ganancia * speed_factor
    want = [mando(fb, p.avance_zona_muerta, g), mando(lr, p.avance_zona_muerta, g),
            mando(ud, p.vertical_zona_muerta, p.subir_ganancia if ud > 0 else p.bajar_ganancia)]
    if want[0] and want[1]:
        want[0], want[1] = want[0] * combo, want[1] * combo
        want[2] -= p.hundimiento_combo_cm_s  # lado y adelante a la vez: se hunde (real 11-nov)
    if sag and want[0]:
        want[2] -= sag  # se hunde avanzando, aunque se pida subir un poco (real)
    k = min(1.0, dt / max(p.respuesta_s, 1e-3))
    kz = min(1.0, dt / max(p.vertical_respuesta_s, 1e-3))
    return [v[0] + (want[0] - v[0]) * k, v[1] + (want[1] - v[1]) * k, v[2] + (want[2] - v[2]) * kz]


class RcAtrasado:
    """El rc que de verdad mueve al dron: el enviado hace atraso_s."""

    def __init__(self) -> None:
        self.hist: collections.deque = collections.deque()

    def put(self, t: float, rc) -> None:
        self.hist.append((t, tuple(rc)))

    def at(self, t: float, atraso: float):
        lim = t - atraso
        while len(self.hist) > 1 and self.hist[1][0] <= lim:
            self.hist.popleft()
        return self.hist[0][1] if self.hist and self.hist[0][0] <= lim else (0, 0, 0, 0)


class Tag:
    """Tag en una pared (facing = hacia dónde mira) o en el piso (facing = (0,0,1) y
    top = hacia dónde apunta su borde de arriba, p. ej. (0,1,0) = norte)."""

    def __init__(self, tag_id: int, pos, facing, size: float = 8.0, top=(0, 0, 1), desgaste=None) -> None:
        self.id, self.c = tag_id, np.array(pos, float)
        self.n = np.array(facing, float) / np.linalg.norm(facing)
        up = np.array(top, float) / np.linalg.norm(top)
        self.right = np.cross(up, self.n)
        a = size * 9 / 7 / 2  # medio lado exterior, con 1 módulo de borde blanco
        self.corners = [self.c - a * self.right + a * up, self.c + a * self.right + a * up,
                        self.c + a * self.right - a * up, self.c - a * self.right - a * up]
        m = cv2.aruco.generateImageMarker(DICT, tag_id, 7 * 20)
        self.img = cv2.copyMakeBorder(m, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        if desgaste:  # dict con las opciones de desgastar(); la semilla por defecto es el ID
            self.img = desgastar(self.img, **{"semilla": tag_id, **desgaste})
        self.visible = True


# Tags del laboratorio vistos por el espejo (videos de E5, 9-nov): el "negro" se ve en ~150 y el
# papel en ~252; el contraste va de ~75 a ~105 (p10 y mediana).
DESGASTE = {
    "lab": {"negro": 150},
    "muy_desteñido": {"negro": 185, "blanco": 240},
    "manchas": {"negro": 150, "manchas": 0.2},
    "faltante": {"negro": 150, "faltante": 0.08},
    "todo": {"negro": 170, "blanco": 245, "manchas": 0.15, "faltante": 0.06},
}


def desgastar(img: np.ndarray, negro: float = 0, blanco: float = 255, manchas: float = 0.0,
              faltante: float = 0.0, semilla: int = 0) -> np.ndarray:
    """Tag gastado. img: 180x180 (9 módulos de 20 px; 0 = negro, 255 = blanco).
    negro/blanco: a qué gris quedan (desteñido, parejo solo más o menos: ±20 en manchones);
    manchas: fracción del negro con puntos y rayones blancos (0.2 = 20 %);
    faltante: fracción del tag (sin el margen blanco) arrancada en 1–3 pedazos, que pueden caer
    en el borde negro (lo que más estorba para detectarlo)."""
    rng = np.random.default_rng(semilla)
    n = img.shape[0]
    dark = img < 128
    ink = np.zeros(img.shape, np.float32)  # 1 = hay tinta negra
    ink[dark] = 1.0
    inner = np.zeros(img.shape, bool)
    inner[20:n - 20, 20:n - 20] = True
    if manchas > 0:  # puntos de 2–7 px y algún rayón, hasta cubrir esa fracción del negro
        objetivo, total = manchas * dark.sum(), 0
        while total < objetivo:
            hueco = np.zeros(img.shape, np.uint8)
            if rng.random() < 0.15:
                p0, p1 = rng.integers(20, n - 20, 2), rng.integers(20, n - 20, 2)
                cv2.line(hueco, tuple(int(v) for v in p0), tuple(int(v) for v in p1), 1, int(rng.integers(1, 3)))
            else:
                c = tuple(int(v) for v in rng.integers(20, n - 20, 2))
                cv2.circle(hueco, c, int(rng.integers(2, 8)), 1, -1)
            nuevo = (hueco > 0) & (ink > 0)
            total += nuevo.sum()
            ink[nuevo] = 0.0
    if faltante > 0:  # 1–3 pedazos irregulares (elipses giradas) que se llevan tinta y todo
        k = int(rng.integers(1, 4))
        area = faltante * (n - 40) ** 2 / k
        for _ in range(k):
            ax = math.sqrt(area / math.pi) * rng.uniform(0.6, 1.6)
            ay = area / (math.pi * ax)
            c = tuple(int(v) for v in rng.integers(20, n - 20, 2))
            hueco = np.zeros(img.shape, np.uint8)
            cv2.ellipse(hueco, c, (max(1, int(ax)), max(1, int(ay))), float(rng.uniform(0, 180)), 0, 360, 1, -1)
            ink[(hueco > 0) & inner] = 0.0
    # desteñido disparejo: el gris del negro varía ±20 en manchones grandes
    campo = cv2.resize(rng.uniform(-1, 1, (4, 4)).astype(np.float32), img.shape[::-1], interpolation=cv2.INTER_CUBIC)
    gris_negro = np.clip(negro + 20 * campo * (negro > 0), 0, 255)
    out = blanco * (1 - ink) + gris_negro * ink
    out = cv2.GaussianBlur(out, (3, 3), 0.7)  # orillas de la tinta no perfectas
    return np.clip(out, 0, 255).astype(np.uint8)


def dead(rc: float, db: float = 5) -> float:
    return 0.0 if abs(rc) <= db else math.copysign(abs(rc) - db, rc)


# ---- piso del laboratorio: oscuro, con cuadrícula de cinta azul (videos del 11-nov)
PISO_PX_CM = 2.0  # resolución de la textura
PISO_LADO_CM = 1400  # textura de 14 x 14 m centrada en el despegue
_PISO: np.ndarray | None = None


def textura_piso() -> np.ndarray:
    """Gris oscuro (~85) con manchas suaves, y cinta (~150) de 6 cm cada 60 cm en las dos
    direcciones. Se genera una vez por proceso (3.9 MB)."""
    global _PISO
    if _PISO is None:
        n = int(PISO_LADO_CM * PISO_PX_CM)
        rng = np.random.default_rng(3)
        base = cv2.resize(rng.normal(0, 1, (n // 16, n // 16)).astype(np.float32), (n, n), interpolation=cv2.INTER_CUBIC)
        fino = rng.normal(0, 1, (n, n)).astype(np.float32)
        tex = 85 + 7 * base + 4 * cv2.GaussianBlur(fino, (0, 0), 1.5)
        paso, ancho = int(60 * PISO_PX_CM), int(6 * PISO_PX_CM)
        for k in range(0, n, paso):
            tex[:, k:k + ancho] = 150 + 4 * fino[:, k:k + ancho]
            tex[k:k + ancho, :] = 150 + 4 * fino[k:k + ancho, :]
        _PISO = np.clip(tex, 0, 255).astype(np.uint8)
    return _PISO


def piso_en_imagen(img: np.ndarray, O, r, d, f, Kc) -> None:
    """Dibuja el piso (z = 0) que ve la cámara desde O, con la cámara sin distorsión (el piso
    solo sirve para medir cuánto se mueve el dron; los tags se dibujan encima con la distorsión)."""
    tex = textura_piso()
    n, s = tex.shape[0], PISO_PX_CM
    m = max(30.0, O[2]) * 0.9 + 25  # media ventana de piso que cubre la vista, en cm
    x0, x1, y0, y1 = O[0] - m, O[0] + m, O[1] - m, O[1] + m
    u0, u1 = int((x0 + PISO_LADO_CM / 2) * s), int((x1 + PISO_LADO_CM / 2) * s)
    v0, v1 = int((PISO_LADO_CM / 2 - y1) * s), int((PISO_LADO_CM / 2 - y0) * s)
    if u0 < 0 or v0 < 0 or u1 >= n or v1 >= n:
        return  # fuera de la textura: piso liso
    esquinas = [(x0, y1), (x1, y1), (x1, y0), (x0, y0)]  # en el orden del recorte (arriba-izq, ...)
    pts = []
    for X, Y in esquinas:
        P = np.array([X, Y, 0.0]) - O
        pc = np.array([r @ P, d @ P, f @ P])
        if pc[2] <= 1:
            return
        pts.append((Kc[0, 0] * pc[0] / pc[2] + Kc[0, 2], Kc[1, 1] * pc[1] / pc[2] + Kc[1, 2]))
    crop = tex[v0:v1, u0:u1]
    h, w = crop.shape
    H = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), np.float32(pts))
    cv2.warpPerspective(crop, H, (img.shape[1], img.shape[0]), img, flags=cv2.INTER_LINEAR,
                        borderMode=cv2.BORDER_TRANSPARENT)


class SimTello:
    """Imita la interfaz de djitellopy que usa la misión."""

    def __init__(self, tags, drift=None, seed=0, boxes=(), bias=(0.0, 0.0), yaw0=0.0, bat=90.0,
                 mirror=None, mirror_tilt=0.0, speed_factor=1.0, sag=0.0, combo=1.0, glitches=(),
                 imu_mal=None, despegue="normal", temp=None, params=None, hilo=True, piso=True) -> None:
        # params: SimParams (por defecto P, de config/sim_tello.json). hilo=False: sin hilo de
        # física; quien lo use llama step() (sim/comparar_vuelos.py).
        # despegue: "normal", "alto" (sube solo a ~141 cm, real 9-nov) o "cae" (sube ~40 cm y
        # regresa al piso mientras su 'h' dice que sube, real 9-nov)
        self.p = params or P
        self.piso = piso  # con espejo: piso con textura (cuadrícula del laboratorio); False: gris liso
        drift = self.p.deriva_cm_s if drift is None else drift
        self.despegue, self.t_takeoff, self._ok_sent = despegue, None, False
        self.temp = self.p.temp_inicial_c if temp is None else temp
        self._rc = RcAtrasado()
        self.yaw_sigue = 0.0
        self._goal, self._ok_t, self._peaked = None, None, False
        self._giro_dir = None
        # speed_factor: la misma rc mueve más o menos (real: rc 15 dio 12–20 cm/s entre vuelos).
        # sag: cm/s que se hunde al avanzar sin rc vertical (real: 60 -> 33 cm a 60 cm de altura).
        self.speed_factor, self.sag, self.vz_sink = speed_factor, sag, 0.0
        # combo: pedir adelante y de lado a la vez lo frena (real 27-oct: fb 15 + lr 15 -> ~10 y ~3 cm/s)
        # glitches: (desde, hasta, valor) en s desde el arranque: el tof da ese valor (real: 81 -> 14 -> 83)
        self.combo, self.glitches = combo, glitches
        # imu_mal: (desde s, cm/s adelante, cm/s vertical) que se mueve solo, pida lo que se pida
        # (real 27-oct: avanzó 120 cm y bajó 45 cm pidiendo quedarse y subir a fondo)
        self.imu_mal = imu_mal
        # mirror: None = cámara al frente; "v" = espejo hacia abajo (la imagen sale espejada,
        # como la real). mirror_tilt: grados que la vista se inclina hacia adelante.
        self.mirror, self.mirror_tilt = mirror, math.radians(mirror_tilt)
        if mirror:
            pm = TT.PoseEstimator(ROOT / "config" / "camera_tello.json", 8.0).mirrored(mirror)
            self.Km, self.Dm = pm.K, pm.dist
        self.tags, self.boxes, self.bias = tags, boxes, np.array(bias, float)
        self.udp = {"state": {}, "responses": []}
        self.x = self.y = self.z = 0.0
        self.yaw = yaw0  # rumbo respecto a la pista (el Tello real no lo sabe)
        self.v = np.zeros(3)
        self.yaw_rate = 0.0
        self.mode, self.rc, self.sent, self.is_flying = "ground", (0, 0, 0, 0), [], False
        self.t_flip, self.flips, self.crash, self.min_wall, self.bat = -1e9, 0, None, 1e9, bat
        self.flip_dir, self.pitch, self.sink_end, self.tof_garbage = "b", 0, -1e9, None
        self.min_z_after_takeoff = 1e9
        self.rng, self.drift, self.wind = np.random.default_rng(seed), drift, np.zeros(2)
        self.t0 = time.monotonic()
        self._k = 0
        self.lock = threading.Lock()
        self._stop = threading.Event()
        if hilo:
            threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        period, last = 0.02, time.monotonic()
        while not self._stop.wait(period):
            with self.lock:
                # el paso es el tiempo real transcurrido: con el CPU ocupado (varios escenarios
                # dibujando y detectando) el ciclo se atrasa, y un paso fijo frenaba al dron
                now = time.monotonic()
                dt, last = min(0.1, now - last), now
                self.step(dt, now)

    def _takeoff_step(self, dt: float, now: float) -> None:
        """Despegue: el Tello sube solo e ignora el rc hasta su "ok" (o hasta asentarse sin ok)."""
        p, el = self.p, now - self.t_takeoff
        if self.despegue == "cae":  # sube ~40 cm y se regresa al piso; nunca contesta ok
            goal, ok_t = (40.0 if el < 2.5 else 0.0), None
        elif self.despegue == "alto":  # sube solo hasta ~141 cm (real 9-nov: "ok" a los 10 s)
            goal, ok_t = 141.0, 10.0
        else:  # "normal" o "sin_ok" (real 9-nov: 2 de 14 despegues no contestaron ok)
            if self._goal is None:
                lo, hi = p.despegue_cm
                self._goal = float(self.rng.uniform(lo, hi)) if hi > lo else float(lo)
                self._ok_t = float(self.rng.uniform(*p.despegue_ok_s)) if p.despegue_ok_s else None
                if self.despegue == "sin_ok" and self._ok_t is None:
                    self._ok_t = 7.5
            self._peaked = self._peaked or self.z >= self._goal + p.despegue_pico_cm - 0.5
            goal = self._goal if self._peaked else self._goal + p.despegue_pico_cm
            ok_t = self._ok_t
        speed = 30.0 if goal > self.z else 15.0
        self.z = goal if abs(goal - self.z) <= speed * dt else self.z + math.copysign(speed * dt, goal - self.z)
        if self.z > 10:  # ya despegado: la deriva también lo mueve (real 11-nov: el Tello 7 se fue a la malla)
            self.wind = 0.98 * self.wind + self.rng.normal(0, self.drift * 0.2, 2)
            fw, rt = self._deriva_propia(False)
            ps = math.radians(self.yaw)
            self.x += (fw * math.sin(ps) + rt * math.cos(ps) + self.wind[0] + self.bias[0]) * dt
            self.y += (fw * math.cos(ps) - rt * math.sin(ps) + self.wind[1] + self.bias[1]) * dt
        if ok_t is None:
            if self.despegue == "normal" and self.z >= self._goal:  # modelo ideal: ok al llegar arriba
                self.mode = "air"
                self.udp["responses"].append(b"ok")
        elif el >= ok_t:
            self.mode = "air"  # ya obedece el rc
            if self.despegue != "sin_ok":
                self.udp["responses"].append(b"ok")

    def _deriva_propia(self, girando: bool) -> tuple[float, float]:
        """(adelante, derecha) en cm/s que el dron se mueve solo: la deriva constante y, mientras
        gira fuerte, un corrimiento hacia un lado al azar que se elige al empezar cada giro."""
        p = self.p
        fw, rt = p.deriva_adelante_cm_s, p.deriva_lado_cm_s
        if girando and p.giro_deriva_cm_s:
            if self._giro_dir is None:
                self._giro_dir = float(self.rng.uniform(0, 2 * math.pi))
            fw += p.giro_deriva_cm_s * math.cos(self._giro_dir)
            rt += p.giro_deriva_cm_s * math.sin(self._giro_dir)
        elif not girando:
            self._giro_dir = None
        return fw, rt

    def step(self, dt: float, now: float) -> None:
        """Un paso de la física (lo llama el hilo o, sin hilo, quien lo use)."""
        p = self.p
        rc = self._rc.at(now, p.mando_atraso_s)  # el rc que ya hizo efecto
        if self.mode == "takeoff":
            self._takeoff_step(dt, now)
        elif self.mode == "land":
            self.z = max(0.0, self.z - 40 * dt)
            if self.z <= 0:
                self.mode = "ground"
        elif self.mode == "air" and now - self.t_flip < 1.0:
            # flip: una vuelta en ~1 s, baja ~20 cm, se corre ~30 cm y queda un poco girado;
            # el tof da basura mientras voltea (real: 154, 454, 567)
            frac = (now - self.t_flip) / 1.0
            self.pitch = int(F.wrap_deg(360 * frac))
            self.tof_garbage = int(self.rng.uniform(150, 600)) if 0.2 < frac < 0.8 else None
            self.z = max(0.0, self.z - 20 * dt)
            ps = math.radians(self.yaw)
            sgn = {"f": 1, "b": -1}.get(self.flip_dir, 0)
            self.x += sgn * 30 * math.sin(ps) * dt
            self.y += sgn * 30 * math.cos(ps) * dt
            self.yaw = F.wrap_deg(self.yaw + 6 * dt)
        elif self.mode == "air" and now < self.sink_end:
            # tras el flip el Tello CAE ~50 cm/s (real, 26-oct: de 130 al piso) y su
            # propia altura no se entera; pedir subir a fondo lo frena en ~1 s
            self.pitch, self.tof_garbage = 0, None
            climb = 1.25 * dead(rc[2], 3) if now - self.t_flip >= 1.2 and rc[2] > 0 else 0.0
            self.vz_sink += ((-50 + climb) - self.vz_sink) * min(1, dt / 0.3)
            self.z = max(0.0, self.z + self.vz_sink * dt)
            if self.z <= 0:
                self.mode = "ground"  # tocó el piso: el Tello apaga motores
        elif self.mode == "air":
            # subir es más rápido que bajar (real 27-oct: rc 40 subió ~40 cm/s; rc -40 bajó ~7)
            self.v = np.array(paso_vel(self.v, rc, dt, p, self.speed_factor, self.combo, self.sag))
            self.yaw_rate, self.yaw_sigue = paso_giro(self.yaw_rate, self.yaw_sigue, rc[3], dt, p)
            self.yaw = F.wrap_deg(self.yaw + (self.yaw_rate + self.yaw_sigue) * dt)
            self.wind = 0.98 * self.wind + self.rng.normal(0, self.drift * 0.2, 2)
            ps = math.radians(self.yaw)
            fw, rt = self._deriva_propia(abs(self.yaw_rate + self.yaw_sigue) > 15)
            fw, rt = fw + self.v[0], rt + self.v[1]
            self.x += (fw * math.sin(ps) + rt * math.cos(ps) + self.wind[0] + self.bias[0]) * dt
            self.y += (fw * math.cos(ps) - rt * math.sin(ps) + self.wind[1] + self.bias[1]) * dt
            self.z = max(0.0, self.z + self.v[2] * dt)
            if self.imu_mal and now - self.t0 >= self.imu_mal[0]:
                self.x += self.imu_mal[1] * math.sin(ps) * dt
                self.y += self.imu_mal[1] * math.cos(ps) * dt
                self.z = max(0.0, self.z + self.imu_mal[2] * dt)
            self._check_walls()
            self.min_z_after_takeoff = min(self.min_z_after_takeoff, self.z)
        if self.mode != "ground":
            self.temp += p.temp_c_por_min / 60 * dt
        self._k += 1
        if self._k % 5 == 0:  # estado UDP a 10 Hz
            self.bat -= 0.01
            floor = max([bh for (x0, y0, x1, y1, bh) in self.boxes
                         if x0 <= self.x <= x1 and y0 <= self.y <= y1] or [0])
            h_bad = self.z * 0.6 - 3 * (now - self.t0)  # 'h' que deriva, como el real
            if self.mode == "takeoff" and self.despegue == "cae":  # real 9-nov: h subía y el tof bajaba
                h_bad = 60 + 10 * (now - self.t_takeoff)
            tof = int(self.z - floor + 10 + self.rng.normal(0, 2)) if self.z > 0 else 10
            if self.tof_garbage is not None:
                tof = self.tof_garbage
            for g0, g1, gv in self.glitches:
                if g0 <= now - self.t0 < g1:
                    tof = gv
            self.udp["state"] = {"h": int(round(h_bad / 10) * 10), "tof": max(10, tof),
                                 "bat": int(self.bat), "yaw": int(round(self.yaw)),
                                 "temph": int(round(self.temp)), "pitch": self.pitch, "roll": 0,
                                 "vgx": 0, "vgy": 0, "vgz": 0}

    def _check_walls(self) -> None:
        p = np.array([self.x, self.y, self.z])
        for t in self.tags:
            d = float((p - t.c) @ t.n)
            lat = abs(float((p - t.c) @ t.right))
            if lat < 60 and d > -5:
                self.min_wall = min(self.min_wall, d)
                if d < 12 and self.crash is None:
                    self.crash = f"choque con la pared del tag {t.id} (d={d:.0f} cm)"

    # ---- interfaz tipo djitellopy
    def get_own_udp_object(self):
        return self.udp

    def send_rc_control(self, *rc) -> None:
        with self.lock:
            self.set_rc(rc, time.monotonic())

    def set_rc(self, rc, t: float) -> None:
        self.rc = tuple(rc)
        self._rc.put(t, rc)

    def send_command_without_return(self, c: str) -> None:
        with self.lock:
            self.sent.append(c)
            if c == "takeoff" and self.mode == "ground":
                self.mode, self.t_takeoff, self._goal, self._peaked = "takeoff", time.monotonic(), None, False
            elif c == "land" and self.mode != "ground":
                self.mode = "land"
            elif c == "emergency":
                self.mode, self.z = "ground", 0.0
            elif c.startswith("flip"):
                if self.bat < 50:  # el Tello real rechaza flips con poca carga
                    self.udp["responses"].append(b"error")
                else:
                    self.t_flip, self.flips, self.flip_dir = time.monotonic(), self.flips + 1, c.split()[-1]
                    self.sink_end = self.t_flip + 1.0 + self.rng.uniform(1.0, 3.0)
                    self.vz_sink = -30.0
                    self.udp["responses"].append(b"ok")

    def render(self) -> np.ndarray:
        with self.lock:
            O, ps = np.array([self.x, self.y, self.z]), math.radians(self.yaw)
        heading = np.array([math.sin(ps), math.cos(ps), 0.0])
        r = np.array([math.cos(ps), -math.sin(ps), 0.0])
        if self.mirror:  # cámara virtual mirando abajo; arriba de la imagen = adelante del dron
            tau = self.mirror_tilt
            f = math.cos(tau) * np.array([0, 0, -1.0]) + math.sin(tau) * heading
            Kc, Dc = self.Km, self.Dm
        else:
            f = math.cos(PITCH) * heading + np.array([0, 0, -math.sin(PITCH)])
            Kc, Dc = K, D
        d = np.cross(f, r)
        img = np.full((720, 960), 110, np.uint8)
        if not self.mirror:
            img[400:] = 80
        elif self.piso:  # el piso del laboratorio, para medir con él la deriva (sostener_piso)
            piso_en_imagen(img, O, r, d, f, Kc)
        for t in self.tags:
            if not t.visible or ((O - t.c) @ t.n) <= 0:
                continue
            pc = np.array([[r @ (P - O), d @ (P - O), f @ (P - O)] for P in t.corners])
            if (pc[:, 2] < 10).any():
                continue
            # La distorsión solo vale dentro de la imagen: fuera del campo de visión
            # "dobla" los puntos de regreso y pinta manchas enormes. Esos tags no se dibujan.
            nx, ny = pc[:, 0] / pc[:, 2], pc[:, 1] / pc[:, 2]
            if (np.abs(nx) > 1.1 * 480 / Kc[0, 0]).any() or (np.abs(ny) > 1.1 * 386 / Kc[1, 1]).any():
                continue
            uv, _ = cv2.projectPoints(pc.reshape(-1, 1, 3), np.zeros(3), np.zeros(3), Kc, Dc)
            uv = uv.reshape(-1, 2).astype(np.float32)
            if (np.abs(uv) > 5000).any():
                continue
            h, w = t.img.shape
            H = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), uv)
            cv2.warpPerspective(t.img, H, (960, 720), img, flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_TRANSPARENT)
        img = cv2.GaussianBlur(img, (3, 3), 0.6)
        img = np.clip(img + self.rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
        if self.mirror:  # lo que entrega la cámara real: la imagen reflejada
            img = cv2.flip(img, 0 if self.mirror == "v" else 1)
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


OVER_E: dict = {}  # cambios a MirrorConfig por escenario
OVER_P: dict = {}  # cambios a FloorConfig por escenario


def run(name, tags, limit=120, events=None, drift=None, boxes=(), bias=(0.0, 0.0), yaw0=0.0, bat=90.0,
        flip_test=None, rc_calib=False, mirror=None, mirror_tilt=0.0, start=(0.0, 0.0), piso=False,
        speed_factor=1.0, sag=None, combo=None, glitches=(), imu_mal=None, despegue="normal", temp=None):
    # hundimiento y mando combinado: los de config/sim_tello.json; en el modelo ideal, solo en
    # piso (lo visto en vuelo real el 27-oct)
    if sag is None:
        sag = P.hundimiento_cm_s if P.hundimiento_cm_s is not None else (15.0 if piso else 0.0)
    if combo is None:
        combo = P.combo if P.combo is not None else (0.55 if piso else 1.0)
    cfg = F.FlightConfig.load(ROOT / "config" / "flight.json")
    mcfg = M.MissionConfig.load(ROOT / "config" / "mission_tags.json")
    cfg.hover_s, cfg.max_flight_s = mcfg.start_hover_s, mcfg.mission_max_s
    for k, v in OVER.items():
        setattr(mcfg, k, v)
    sim = SimTello(tags, drift=drift, boxes=boxes, bias=bias, yaw0=yaw0, bat=bat, mirror=mirror,
                   mirror_tilt=mirror_tilt, speed_factor=speed_factor, sag=sag, combo=combo, glitches=glitches,
                   imu_mal=imu_mal, despegue=despegue, temp=temp)
    sim.x, sim.y = start
    log = ROOT / "sim" / "logs" / f"{name}.csv"
    if flip_test:  # prueba de first_flight.py --flip-test, sin misión
        mis = F.Flight(sim, cfg, log, None, flip_test)
        mis.executed, mis._turned = [], 0.0
    elif rc_calib:  # scripts/rc_calib.py
        cfg.hover_s, cfg.max_flight_s = 3.0, 150.0
        mis = RC.RcCalib(sim, cfg, log, ROOT / "config" / "camera_tello.json", 8.0, ["fb", "lr", "ud"],
                         report_dir=ROOT / "sim" / "logs")  # no mezclar con las calibraciones reales
        mis.executed, mis._turned = [], 0.0
    elif piso:  # scripts/mision_piso.py
        fcfg = MP.FloorConfig.load(ROOT / "config" / "mission_piso.json")
        for k, v in OVER_P.items():
            setattr(fcfg, k, v)
        mis = MP.FloorMission(sim, cfg, mcfg, fcfg, log, ROOT / "config" / "camera_tello.json")
    elif mirror:  # scripts/mision_espejo.py
        ecfg = ME.MirrorConfig.load(ROOT / "config" / "mission_espejo.json")
        ecfg.espejo = mirror
        for k, v in OVER_E.items():
            setattr(ecfg, k, v)
        mis = ME.MirrorMission(sim, cfg, mcfg, ecfg, log, ROOT / "config" / "camera_tello.json")
    else:
        mis = M.TagMission(sim, cfg, mcfg, log, ROOT / "config" / "camera_tello.json")
    time.sleep(0.3)
    stop = threading.Event()

    def video() -> None:
        frames: collections.deque = collections.deque()  # el video real llega atrasado (~170 ms)
        while not stop.is_set():
            now = time.monotonic()
            frames.append((now, sim.render()))
            while len(frames) > 1 and now - frames[1][0] >= P.video_atraso_s:
                frames.popleft()
            if not flip_test:
                mis.on_frame(frames[0][1], now)
            mis.video_age = 0.0
            time.sleep(1 / 30)

    vt = threading.Thread(target=video, daemon=True)
    vt.start()
    threading.Thread(target=mis.run, daemon=True).start()
    t_espera = time.monotonic()  # despegar hasta que llegue el primer cuadro: con varios escenarios a
    while mis.video_age > 1.0 and time.monotonic() - t_espera < 15:  # la vez tardaba y la revisión
        time.sleep(0.05)  # previa decía "NO despega: video"
    time.sleep(0.5)
    mis.request_takeoff()
    t0, log, last = time.monotonic(), [], None
    while time.monotonic() - t0 < limit and mis.state not in F.TERMINAL:
        if (mis.state, mis.reason) != last:
            last = (mis.state, mis.reason)
            log.append(f"{time.monotonic() - t0:5.1f}s {mis.state:9s} {mis.reason}  "
                       f"[x={sim.x:.0f} y={sim.y:.0f} z={sim.z:.0f} yaw={sim.yaw:.0f}]")
        if events:
            events(sim, mis, time.monotonic() - t0)
        time.sleep(0.02)
    stop.set()
    vt.join(timeout=1)  # que el render termine antes de salir (evita abortos de OpenCV al cerrar)
    mis.stop()
    sim._stop.set()
    print(f"===== {name}: final {mis.state} | choque: {sim.crash} | min pared {sim.min_wall:.0f} cm | "
          f"ejecutados: {mis.executed} | giro acumulado {mis._turned:.0f} | flips {sim.flips} | "
          f"altura min en vuelo {sim.min_z_after_takeoff:.0f} cm")
    for line in log:
        print("   ", line)


def scenario(sc: str) -> None:
    south = (0, -1, 0)
    if sc == "circuito":  # 1 (derecha) -> 2 (izquierda) -> 7 (aterrizar); señuelo ID 29; tag 1 desplazado
        run(sc, [Tag(1, (25, 200, 85), south), Tag(29, (-70, 210, 85), south),
                 Tag(2, (200, 140, 85), (-1, 0, 0)), Tag(7, (140, 330, 85), south)])
    elif sc == "pausa":
        run(sc, [Tag(9, (0, 200, 85), south)])
    elif sc == "giro360":
        run(sc, [Tag(10, (0, 200, 85), south)])
    elif sc == "sube_ciego":  # tras subir, el tag deja de verse: la memoria del frente debe frenar
        OVER["advance_timeout_s"] = 30

        def ev(sim, mis, el):
            if mis.state == "ADVANCE" and mis.executed:
                sim.tags[0].visible = False
        run(sc, [Tag(5, (0, 200, 85), south)], events=ev)
    elif sc == "perdido":
        def ev(sim, mis, el):
            if mis.state == "APPROACH" and sim.y > 60:
                sim.tags[0].visible = False
        run(sc, [Tag(3, (0, 200, 85), south)], events=ev)
    elif sc == "flip8":
        run(sc, [Tag(8, (0, 200, 85), south)])
    elif sc == "caja":  # caja de 35 cm en el camino: pasar por encima sin falsos avisos
        run(sc, [Tag(3, (0, 260, 85), south)], boxes=[(-40, 90, 40, 140, 35)])
    elif sc in ("deriva", "deriva_sin_lateral"):  # viento lateral constante, como el vuelo real del tag 9
        if sc == "deriva_sin_lateral":
            OVER["lateral_start_cm"] = 0
        run(sc, [Tag(9, (0, 230, 85), south)], bias=(5.0, 0.0))
    elif sc in ("ladeado", "ladeado_sin_alinear"):  # despega girado 8° a la derecha; tras el tag 2 debe quedar a -90° de la pista
        if sc == "ladeado_sin_alinear":
            OVER["lateral_start_cm"] = 0
        run(sc, [Tag(2, (0, 230, 85), south), Tag(7, (-230, 170, 85), (1, 0, 0))], yaw0=8.0)
    elif sc in ("angulo25", "angulo38", "angulo38_deriva"):  # tag girado (como en las pruebas reales)
        th = math.radians(25 if sc == "angulo25" else 38)  # al quedar de frente: yaw = th; tras girar: th - 90
        run(sc, [Tag(2, (0, 230, 85), (-math.sin(th), -math.cos(th), 0))],
            bias=(-4.0, 0.0) if sc.endswith("deriva") else (0.0, 0.0))
    elif sc == "flip_prueba":  # first_flight.py --flip-test b
        run(sc, [], limit=40, flip_test="b")
    elif sc == "flip_prueba_bateria":  # con 45 %: no debe intentar el flip
        run(sc, [], limit=40, flip_test="b", bat=45.0)
    elif sc == "flip4":  # misión con tag 4: flip y luego seguir con el rumbo de antes
        run(sc, [Tag(4, (0, 200, 85), south)])
    elif sc == "flip4_bateria":  # misión con tag 4 y 45 %: flip omitido y visible
        run(sc, [Tag(4, (0, 200, 85), south)], bat=45.0)
    elif sc == "tag_alto":  # tag 25 cm más alto que el crucero (como la prueba real): subir y no perderlo
        run(sc, [Tag(3, (0, 220, 105), south)])
    elif sc == "tag_bajo":  # tag más bajo: debe bajar sin pasar de min_alt_cm
        run(sc, [Tag(3, (0, 220, 45), south)])
    elif sc == "rc_calib":  # simulador: fb/lr 1.7*(|rc|-5) -> 8.5 / 17 / 25.5 cm/s; ud 0.9/0.5*(|rc|-3)
        run(sc, [Tag(1, (0, 160, 90), south)], limit=150, drift=0.5, rc_calib=True)
    # ---- misión con espejo (cámara hacia abajo, tags en el piso)
    elif sc.startswith("espejo"):
        up = (0, 0, 1)

        def floor(tid, x, y, rot=0.0, desgaste=None):  # rot: grados que el tag está girado (horario visto desde arriba)
            a = math.radians(rot)
            return Tag(tid, (x, y, 0), up, top=(math.sin(a), math.cos(a), 0),
                       desgaste=DESGASTE[desgaste] if desgaste else None)
        if sc == "espejo_uno":  # tag 2 girado 12°: sostiene el rumbo y gira a la izquierda (yaw -90)
            run(sc, [floor(2, 6, 90, 12)], mirror="v")
        elif sc == "espejo_inicio":  # despega encima de un tag 7: con ignorar_inicio, ignorarlo y seguir al 2
            OVER_E["ignorar_inicio"] = True
            run(sc, [floor(7, 0, 0), floor(2, 0, 120)], mirror="v")
        elif sc == "espejo_cerca":  # tag 1 a 35 cm: no se ve al despegar pero sí a 100 cm; no es el de inicio
            run(sc, [floor(1, 0, 35)], mirror="v")
        elif sc == "espejo_girado":  # tag 1 girado 30°: el giro de 90° es respecto al rumbo, no al tag
            run(sc, [floor(1, 0, 100, 30)], mirror="v")
        elif sc == "espejo_circuito":  # 1 (derecha) -> 2 (izquierda) -> 7 (aterrizar), a 70 cm
            run(sc, [floor(1, 0, 80), floor(2, 70, 80), floor(7, 70, 150)], mirror="v")
        elif sc == "espejo_quieto":  # sin avanzar: el tag ya está debajo, desplazado y girado
            OVER_E["quieto"] = True
            OVER_E["quieto_timeout_s"] = 8
            run(sc, [floor(9, 10, 15, -20)], mirror="v", limit=70)
        elif sc == "espejo_deriva":
            run(sc, [floor(2, 0, 90)], mirror="v", bias=(3.0, 0.0))
        elif sc == "espejo_flip":
            run(sc, [floor(4, 0, 90)], mirror="v")
        elif sc == "espejo_inclinado":  # espejo 8° hacia adelante, medido y puesto en la config
            OVER_E["vista_adelante_deg"] = 8.0
            run(sc, [floor(2, 0, 90)], mirror="v", mirror_tilt=8.0)
        elif sc == "espejo_inclinado_sin_config":  # mismo espejo sin decirle a la misión: se centra mal
            run(sc, [floor(2, 0, 90)], mirror="v", mirror_tilt=8.0)
        elif sc == "espejo_estacionario":  # como E2b: sin tags, quieto ~20 s. ¿Se queda sobre el despegue?
            OVER_E["quieto"], OVER_E["quieto_timeout_s"] = True, 20
            dist = []

            def ev(sim, mis, el):
                if mis.state == "ADVANCE":  # (quieto: esperando un tag que no hay)
                    dist.append(math.hypot(sim.x, sim.y))
            run(sc, [], mirror="v", limit=60, events=ev)
            if dist:
                print(f"    quieto {len(dist) * 0.02:.0f} s: distancia al despegue media {np.mean(dist):.0f} cm, "
                      f"máxima {max(dist):.0f}, al final {dist[-1]:.0f}")
        elif sc == "espejo_lab":  # circuito con los tags desteñidos como los del laboratorio (negro ~150)
            run(sc, [floor(1, 0, 80, desgaste="lab"), floor(2, 70, 80, desgaste="lab"),
                     floor(7, 70, 150, desgaste="lab")], mirror="v")
        elif sc in ("espejo_gastado", "espejo_gastado_sin_rescate"):  # 1 manchado, 2 con pedazos faltantes, 7 muy desteñido
            if sc.endswith("sin_rescate"):
                OVER["deteccion_rescate"] = False  # el detector de antes del 11-nov
            run(sc, [floor(1, 0, 80, desgaste="manchas"), floor(2, 70, 80, desgaste="faltante"),
                     floor(7, 70, 150, desgaste="muy_desteñido")], mirror="v")
        elif sc == "espejo_despegue_cae":  # sube ~40 cm y regresa al piso (real 9-nov): aterrizar con aviso
            run(sc, [floor(2, 0, 90)], mirror="v", despegue="cae", limit=40)
        elif sc == "espejo_despegue_alto":  # sube solo a ~141 cm (real 9-nov): bajar a crucero y seguir
            run(sc, [floor(2, 0, 90), floor(7, -70, 90)], mirror="v", despegue="alto")
        elif sc == "espejo_sin_ok":  # el Tello no contesta "ok" al despegar (real 9-nov, 2 de 14)
            run(sc, [floor(2, 0, 90), floor(7, -70, 90)], mirror="v", despegue="sin_ok")
        else:
            raise SystemExit(f"escenario desconocido: {sc}")
    # ---- tags en el piso con la cámara al frente (sin espejo)
    elif sc.startswith("piso"):
        def floor(tid, x, y, rot=0.0):
            a = math.radians(rot)
            return Tag(tid, (x, y, 0), (0, 0, 1), top=(math.sin(a), math.cos(a), 0))
        if sc == "piso_uno":  # tag 2 a ~1.7 m: acercarse, ~1 m a ciegas, girar a la izquierda
            run(sc, [floor(2, 5, 170)], piso=True)
        elif sc == "piso_girado":  # tag girado 15° y corrido: centrarse y girar respecto al rumbo, no al tag
            run(sc, [floor(2, -10, 160, 15)], piso=True)
        elif sc == "piso_circuito":  # 1 (derecha) -> 2 (izquierda) -> 7 (aterrizar), a 1.5 m
            run(sc, [floor(1, 0, 170), floor(2, 150, 170), floor(7, 150, 320)], piso=True)
        elif sc == "piso_deriva":
            run(sc, [floor(2, 0, 170)], piso=True, bias=(3.0, 0.0))
        elif sc == "piso_flip":
            run(sc, [floor(4, 0, 170)], piso=True)
        elif sc == "piso_lento":  # rc 15 mueve 28 % menos que lo calibrado (real: 12 vs 17 cm/s)
            run(sc, [floor(2, 0, 170)], piso=True, speed_factor=0.72)
        elif sc == "piso_rapido":  # 15 % más rápido que lo calibrado
            run(sc, [floor(2, 0, 170)], piso=True, speed_factor=1.15)
        elif sc == "piso_hundimiento":  # se hunde más que lo normal (20 cm/s): sostener altura sin tocar el piso
            run(sc, [floor(2, 0, 170)], piso=True, sag=20.0)
        elif sc == "piso_lado":  # tag muy de lado: debe centrarse deslizándose, no irse a ciegas
            run(sc, [floor(2, 75, 175)], piso=True)
        elif sc == "piso_tof_falso":  # el tof da 14 cm 0.4 s en pleno avance (real): no aterrizar ni brincar
            run(sc, [floor(2, 0, 170)], piso=True, glitches=[(9.0, 9.4, 14)])
        elif sc == "piso_imu_mal":  # se va solo hacia adelante y abajo: debe aterrizar antes del piso
            run(sc, [floor(2, 25, 170)], piso=True, imu_mal=(10.0, 30.0, -35.0))
        else:
            raise SystemExit(f"escenario desconocido: {sc}")
    elif sc == "sin_tags":
        run(sc, [], limit=60)
    else:
        raise SystemExit(f"escenario desconocido: {sc}")


ALL = ["circuito", "pausa", "giro360", "sube_ciego", "perdido", "flip8", "caja",
       "deriva", "deriva_sin_lateral", "ladeado", "ladeado_sin_alinear",
       "angulo25", "angulo38", "angulo38_deriva", "flip_prueba", "flip_prueba_bateria",
       "flip4", "flip4_bateria", "tag_alto", "tag_bajo", "rc_calib", "sin_tags",
       "espejo_uno", "espejo_inicio", "espejo_cerca", "espejo_girado", "espejo_circuito", "espejo_quieto", "espejo_deriva",
       "espejo_flip",
       "espejo_inclinado", "espejo_inclinado_sin_config",
       "espejo_despegue_cae", "espejo_despegue_alto", "espejo_sin_ok",
       "espejo_lab", "espejo_gastado", "espejo_gastado_sin_rescate", "espejo_estacionario",
       "piso_uno", "piso_girado", "piso_circuito", "piso_deriva", "piso_flip", "piso_lento", "piso_rapido",
       "piso_hundimiento", "piso_lado", "piso_tof_falso", "piso_imu_mal"]

if __name__ == "__main__":
    args = sys.argv[1:]
    ideal = "--ideal" in args
    args = [a for a in args if a != "--ideal"]
    num = None
    if "--dron" in args:
        k = args.index("--dron")
        num = args[k + 1] if k + 1 < len(args) else None
        args = args[:k] + args[k + 2:]
        if not num:
            raise SystemExit("--dron va con el número del dron, p. ej. --dron 7")
    if not args:
        raise SystemExit(__doc__)
    if ideal:  # el modelo de antes del 11-nov, sin lo medido en config/sim_tello.json
        P = SimParams()
    elif num:
        P = cargar_params(num)
    dron = ("ideal (--ideal)" if ideal else str(SIM_JSON.relative_to(ROOT)) + (f" + {json_dron(num).name}" if num else "")
            if SIM_JSON.exists() else "ideal (no hay config/sim_tello.json)")
    print(f"[sim] dron: {dron}", flush=True)
    names = ALL if args[0] == "todos" else args
    if len(names) == 1:
        scenario(names[0])
    else:  # en paralelo, en tandas: con demasiados a la vez el CPU no alcanza, la visión
        # se atrasa y los acercamientos se alargan por algo que en vuelo real no pasa
        batch = 4
        extra = (["--ideal"] if ideal else []) + (["--dron", num] if num else [])
        for i in range(0, len(names), batch):
            procs = [subprocess.Popen([sys.executable, __file__, n] + extra, stdout=subprocess.PIPE, text=True)
                     for n in names[i:i + batch]]
            for p in procs:
                out = p.communicate()[0]
                print("".join(ln for ln in out.splitlines(True) if not ln.startswith("[sim] dron:")),
                      end="", flush=True)
