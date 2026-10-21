#!/usr/bin/env python3
"""Mundo 3D simulado para probar mission_tags.py sin volar.

Renderiza la cámara del Tello (K, distorsión e inclinación de 11° reales de
config/camera_tello.json) con tags en paredes, y la misión los procesa con el
detector y el PnP reales. La física del dron está ajustada a bitácoras reales:
zona muerta de rc, giro ~0.73*(|rc|-6.6) grados/s, 'h' que deriva y tof con ruido.

Uso:
    python sim/sim_world.py circuito          # un escenario
    python sim/sim_world.py todos             # todos, en paralelo
Escenarios: circuito pausa giro360 sube_ciego perdido flip8 caja deriva
            deriva_sin_lateral ladeado ladeado_sin_alinear angulo25 angulo38
            angulo38_deriva flip_prueba flip_prueba_bateria flip4 flip4_bateria sin_tags

Corre en tiempo real (cada escenario tarda 30–70 s). Las bitácoras van a sim/logs/.
"""
from __future__ import annotations

import json
import math
import subprocess
import sys
import threading
import time
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
import first_flight as F  # noqa: E402
import mission_tags as M  # noqa: E402

CAL = json.loads((ROOT / "config" / "camera_tello.json").read_text())
K, D = np.array(CAL["K"]), np.array(CAL["dist"])
PITCH = math.radians(11)  # medido en las pruebas de piso
DICT = cv2.aruco.getPredefinedDictionary(cv2.aruco.DICT_APRILTAG_25h9)
OVER: dict = {}  # cambios a MissionConfig por escenario


class Tag:
    """Tag vertical en una pared. facing = hacia dónde mira (hacia el dron)."""

    def __init__(self, tag_id: int, pos, facing, size: float = 8.0) -> None:
        self.id, self.c = tag_id, np.array(pos, float)
        self.n = np.array(facing, float) / np.linalg.norm(facing)
        self.right = np.cross([0, 0, 1], self.n)
        up = np.array([0, 0, 1.0])
        a = size * 9 / 7 / 2  # medio lado exterior, con 1 módulo de borde blanco
        self.corners = [self.c - a * self.right + a * up, self.c + a * self.right + a * up,
                        self.c + a * self.right - a * up, self.c - a * self.right - a * up]
        m = cv2.aruco.generateImageMarker(DICT, tag_id, 7 * 20)
        self.img = cv2.copyMakeBorder(m, 20, 20, 20, 20, cv2.BORDER_CONSTANT, value=255)
        self.visible = True


def dead(rc: float, db: float = 5) -> float:
    return 0.0 if abs(rc) <= db else math.copysign(abs(rc) - db, rc)


class SimTello:
    """Imita la interfaz de djitellopy que usa la misión."""

    def __init__(self, tags, drift=2.0, seed=0, boxes=(), bias=(0.0, 0.0), yaw0=0.0, bat=90.0) -> None:
        self.tags, self.boxes, self.bias = tags, boxes, np.array(bias, float)
        self.udp = {"state": {}, "responses": []}
        self.x = self.y = self.z = 0.0
        self.yaw = yaw0  # rumbo respecto a la pista (el Tello real no lo sabe)
        self.v = np.zeros(3)
        self.yaw_rate = 0.0
        self.mode, self.rc, self.sent, self.is_flying = "ground", (0, 0, 0, 0), [], False
        self.t_flip, self.flips, self.crash, self.min_wall, self.bat = -1e9, 0, None, 1e9, bat
        self.flip_dir, self.pitch = "b", 0
        self.rng, self.drift, self.wind = np.random.default_rng(seed), drift, np.zeros(2)
        self.t0 = time.monotonic()
        self.lock = threading.Lock()
        self._stop = threading.Event()
        threading.Thread(target=self._loop, daemon=True).start()

    def _loop(self) -> None:
        dt, k = 0.02, 0
        while not self._stop.wait(dt):
            with self.lock:
                now = time.monotonic()
                if self.mode == "takeoff":
                    self.z = min(80.0, self.z + 30 * dt)
                    if self.z >= 80:
                        self.mode = "air"
                elif self.mode == "land":
                    self.z = max(0.0, self.z - 40 * dt)
                    if self.z <= 0:
                        self.mode = "ground"
                elif self.mode == "air" and now - self.t_flip < 1.0:
                    # flip: una vuelta en ~1 s, baja ~20 cm, se corre ~30 cm y queda un poco girado
                    frac = (now - self.t_flip) / 1.0
                    self.pitch = int(F.wrap_deg(360 * frac))
                    self.z = max(0.0, self.z - 20 * dt)
                    ps = math.radians(self.yaw)
                    sgn = {"f": 1, "b": -1}.get(self.flip_dir, 0)
                    self.x += sgn * 30 * math.sin(ps) * dt
                    self.y += sgn * 30 * math.cos(ps) * dt
                    self.yaw = F.wrap_deg(self.yaw + 6 * dt)
                elif self.mode == "air" and now - self.t_flip < 1.5:
                    self.pitch = 0  # se estabiliza tras el flip; ignora rc
                elif self.mode == "air":
                    lr, fb, ud, yr = self.rc
                    want = 0.9 * np.array([dead(fb), dead(lr), dead(ud)])
                    self.v += (want - self.v) * min(1, dt / 0.4)
                    wy = math.copysign(max(0, 0.73 * (abs(yr) - 6.6)), yr)
                    self.yaw_rate += (wy - self.yaw_rate) * min(1, dt / 0.15)
                    self.yaw = F.wrap_deg(self.yaw + self.yaw_rate * dt)
                    self.wind = 0.98 * self.wind + self.rng.normal(0, self.drift * 0.2, 2)
                    ps = math.radians(self.yaw)
                    self.x += (self.v[0] * math.sin(ps) + self.v[1] * math.cos(ps) + self.wind[0] + self.bias[0]) * dt
                    self.y += (self.v[0] * math.cos(ps) - self.v[1] * math.sin(ps) + self.wind[1] + self.bias[1]) * dt
                    self.z = max(0.0, self.z + self.v[2] * dt)
                    self._check_walls()
                k += 1
                if k % 5 == 0:  # estado UDP a 10 Hz
                    self.bat -= 0.01
                    floor = max([bh for (x0, y0, x1, y1, bh) in self.boxes
                                 if x0 <= self.x <= x1 and y0 <= self.y <= y1] or [0])
                    h_bad = self.z * 0.6 - 3 * (now - self.t0)  # 'h' que deriva, como el real
                    tof = int(self.z - floor + 10 + self.rng.normal(0, 2)) if self.z > 0 else 10
                    self.udp["state"] = {"h": int(round(h_bad / 10) * 10), "tof": max(10, tof),
                                         "bat": int(self.bat), "yaw": int(round(self.yaw)),
                                         "temph": 65, "pitch": self.pitch, "roll": 0, "vgx": 0, "vgy": 0, "vgz": 0}

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
            self.rc = rc

    def send_command_without_return(self, c: str) -> None:
        with self.lock:
            self.sent.append(c)
            if c == "takeoff" and self.mode == "ground":
                self.mode = "takeoff"
            elif c == "land" and self.mode != "ground":
                self.mode = "land"
            elif c == "emergency":
                self.mode, self.z = "ground", 0.0
            elif c.startswith("flip"):
                if self.bat < 50:  # el Tello real rechaza flips con poca carga
                    self.udp["responses"].append(b"error")
                else:
                    self.t_flip, self.flips, self.flip_dir = time.monotonic(), self.flips + 1, c.split()[-1]
                    self.udp["responses"].append(b"ok")

    def render(self) -> np.ndarray:
        with self.lock:
            O, ps = np.array([self.x, self.y, self.z]), math.radians(self.yaw)
        f = np.array([math.sin(ps) * math.cos(PITCH), math.cos(ps) * math.cos(PITCH), -math.sin(PITCH)])
        r = np.array([math.cos(ps), -math.sin(ps), 0.0])
        d = np.cross(f, r)
        img = np.full((720, 960), 110, np.uint8)
        img[400:] = 80
        for t in self.tags:
            if not t.visible or ((O - t.c) @ t.n) <= 0:
                continue
            pc = np.array([[r @ (P - O), d @ (P - O), f @ (P - O)] for P in t.corners])
            if (pc[:, 2] < 10).any():
                continue
            # La distorsión solo vale dentro de la imagen: fuera del campo de visión
            # "dobla" los puntos de regreso y pinta manchas enormes. Esos tags no se dibujan.
            nx, ny = pc[:, 0] / pc[:, 2], pc[:, 1] / pc[:, 2]
            if (np.abs(nx) > 1.1 * 480 / K[0, 0]).any() or (np.abs(ny) > 1.1 * 386 / K[1, 1]).any():
                continue
            uv, _ = cv2.projectPoints(pc.reshape(-1, 1, 3), np.zeros(3), np.zeros(3), K, D)
            uv = uv.reshape(-1, 2).astype(np.float32)
            if (np.abs(uv) > 5000).any():
                continue
            h, w = t.img.shape
            H = cv2.getPerspectiveTransform(np.float32([[0, 0], [w, 0], [w, h], [0, h]]), uv)
            cv2.warpPerspective(t.img, H, (960, 720), img, flags=cv2.INTER_LINEAR,
                                borderMode=cv2.BORDER_TRANSPARENT)
        img = cv2.GaussianBlur(img, (3, 3), 0.6)
        img = np.clip(img + self.rng.normal(0, 3, img.shape), 0, 255).astype(np.uint8)
        return cv2.cvtColor(img, cv2.COLOR_GRAY2BGR)


def run(name, tags, limit=120, events=None, drift=2.0, boxes=(), bias=(0.0, 0.0), yaw0=0.0, bat=90.0,
        flip_test=None):
    cfg = F.FlightConfig.load(ROOT / "config" / "flight.json")
    mcfg = M.MissionConfig.load(ROOT / "config" / "mission_tags.json")
    cfg.hover_s, cfg.max_flight_s = mcfg.start_hover_s, mcfg.mission_max_s
    for k, v in OVER.items():
        setattr(mcfg, k, v)
    sim = SimTello(tags, drift=drift, boxes=boxes, bias=bias, yaw0=yaw0, bat=bat)
    log = ROOT / "sim" / "logs" / f"{name}.csv"
    if flip_test:  # prueba de first_flight.py --flip-test, sin misión
        mis = F.Flight(sim, cfg, log, None, flip_test)
        mis.executed, mis._turned = [], 0.0
    else:
        mis = M.TagMission(sim, cfg, mcfg, log, ROOT / "config" / "camera_tello.json")
    time.sleep(0.3)
    stop = threading.Event()

    def video() -> None:
        while not stop.is_set():
            mis.on_frame(sim.render(), time.monotonic()) if not flip_test else sim.render()
            mis.video_age = 0.0
            time.sleep(1 / 30)

    vt = threading.Thread(target=video, daemon=True)
    vt.start()
    threading.Thread(target=mis.run, daemon=True).start()
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
          f"ejecutados: {mis.executed} | giro acumulado {mis._turned:.0f} | flips {sim.flips}")
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
    elif sc == "caja":  # caja de 35 cm en el camino: aterrizar por obstáculo debajo
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
    elif sc == "sin_tags":
        run(sc, [], limit=60)
    else:
        raise SystemExit(f"escenario desconocido: {sc}")


ALL = ["circuito", "pausa", "giro360", "sube_ciego", "perdido", "flip8", "caja",
       "deriva", "deriva_sin_lateral", "ladeado", "ladeado_sin_alinear",
       "angulo25", "angulo38", "angulo38_deriva", "flip_prueba", "flip_prueba_bateria",
       "flip4", "flip4_bateria", "sin_tags"]

if __name__ == "__main__":
    if len(sys.argv) < 2:
        raise SystemExit(__doc__)
    names = ALL if sys.argv[1] == "todos" else sys.argv[1:]
    if len(names) == 1:
        scenario(names[0])
    else:  # en paralelo, en tandas: con demasiados a la vez el CPU no alcanza, la visión
        # se atrasa y los acercamientos se alargan por algo que en vuelo real no pasa
        batch = 4
        for i in range(0, len(names), batch):
            procs = [subprocess.Popen([sys.executable, __file__, n], stdout=subprocess.PIPE, text=True)
                     for n in names[i:i + batch]]
            for p in procs:
                print(p.communicate()[0], end="", flush=True)
