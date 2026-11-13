#!/usr/bin/env python3
"""Graba un escenario del simulador cuadro por cuadro: el mapa visto desde arriba (por dónde va
el dron de verdad, qué ve la cámara, qué tags ya ejecutó) y la imagen que ve el detector.

    python sim/grabar.py espejo_competencia --semilla 2 --salida sim/logs/videos_pistas/p2_ahora
    python sim/grabar.py espejo_circuito --dron 7 --salida sim/logs/videos/circuito_t7

Guarda un JPG por cada 0.1 s de vuelo (~60 KB) en --salida, más resultado.json. No junta los
cuadros en memoria: con dos grabaciones a la vez así se colgó la app (11-nov). Para hacer el
video lado a lado (antes | ahora): sim/componer.py.

En espejo_competencia, junto a cada tag va el orden en que debe ejecutarlo (puede tener dos
números si se regresa a él), y en verde los que ya ejecutó.
"""
from __future__ import annotations

import argparse
import json
import math
import sys
from pathlib import Path

import cv2
import numpy as np

ROOT = Path(__file__).resolve().parent.parent
sys.path[:0] = [str(ROOT / "sim"), str(ROOT / "scripts")]
sys.argv = sys.argv[:1] + sys.argv[1:]  # sim_world solo lee argumentos en su __main__

import sim_world as SW  # noqa: E402

ANCHO, ALTO, MAPA = 960, 540, 540
FPS = 10
VERDE, GRIS, ROJO, AZUL, BLANCO = (90, 200, 90), (150, 150, 150), (60, 60, 230), (230, 160, 60), (240, 240, 240)


class Grabador:
    def __init__(self, salida: Path, tags, esperado: list[int] | None, visitas_xy, titulo: str):
        self.salida, self.tags, self.esperado, self.titulo = salida, tags, esperado, titulo
        self.visitas_xy = visitas_xy  # [(x, y)] en el orden esperado (pistas al azar)
        pts = [(0.0, 0.0)] + [(float(t.c[0]), float(t.c[1])) for t in tags]
        xs, ys = [p[0] for p in pts], [p[1] for p in pts]
        m = 70
        self.x0, self.y0, self.x1, self.y1 = min(xs) - m, min(ys) - m, max(xs) + m, max(ys) + m
        self.k = min((MAPA - 20) / (self.x1 - self.x0), (MAPA - 20) / (self.y1 - self.y0))
        self.n, self.t_sig, self.rastro, self.hechos, self.n_ejec = 0, 0.0, [], [], 0

    def px(self, x: float, y: float) -> tuple[int, int]:
        cx = 10 + (x - self.x0) * self.k + ((MAPA - 20) - (self.x1 - self.x0) * self.k) / 2
        cy = 10 + (self.y1 - y) * self.k + ((MAPA - 20) - (self.y1 - self.y0) * self.k) / 2
        return int(cx), int(cy)

    def cuadro(self, sim, mis, t: float) -> np.ndarray:
        img = np.full((ALTO, ANCHO, 3), 32, np.uint8)
        mapa = img[:, :MAPA]
        mapa[:] = (44, 44, 44)
        paso = 50  # cuadrícula cada 50 cm
        for gx in range(int(self.x0 // paso) * paso, int(self.x1) + paso, paso):
            cv2.line(mapa, self.px(gx, self.y0), self.px(gx, self.y1), (60, 60, 60), 1)
        for gy in range(int(self.y0 // paso) * paso, int(self.y1) + paso, paso):
            cv2.line(mapa, self.px(self.x0, gy), self.px(self.x1, gy), (60, 60, 60), 1)
        # el camino esperado (pistas al azar)
        if self.visitas_xy:
            camino = [self.px(0, 0)] + [self.px(*p) for p in self.visitas_xy]
            for a, b in zip(camino, camino[1:]):
                cv2.line(mapa, a, b, (85, 85, 85), 2, cv2.LINE_AA)
        # despegue
        c = self.px(0, 0)
        cv2.drawMarker(mapa, c, BLANCO, cv2.MARKER_TILTED_CROSS, 14, 2)
        # lo que ve la cámara (con el espejo inclinado: más hacia atrás que hacia adelante)
        z = max(sim.z, 1.0)
        tau = getattr(sim, "mirror_tilt", 0.0) or 0.0
        ade, atr = z * math.tan(math.radians(21.5) + tau), z * math.tan(math.radians(21.5) - tau)
        lado = z * math.tan(math.radians(27.5))
        a = math.radians(sim.yaw)
        f, r = (math.sin(a), math.cos(a)), (math.cos(a), -math.sin(a))
        esq = [(sim.x + fa * f[0] + la * r[0], sim.y + fa * f[1] + la * r[1])
               for fa, la in ((ade, -lado), (ade, lado), (-atr, lado), (-atr, -lado))]
        cv2.polylines(mapa, [np.array([self.px(*p) for p in esq], np.int32)], True, (110, 110, 60), 1, cv2.LINE_AA)
        # tags: verde = ya ejecutado; el número chico, en qué orden le toca
        for i, tg in enumerate(self.tags):
            p = self.px(float(tg.c[0]), float(tg.c[1]))
            col = VERDE if i in self.hechos else (GRIS if tg.id in range(1, 11) else (90, 90, 90))
            s = max(5, int(4 * self.k))
            cv2.rectangle(mapa, (p[0] - s, p[1] - s), (p[0] + s, p[1] + s), col, -1)
            cv2.putText(mapa, str(tg.id), (p[0] - 6, p[1] + 5), cv2.FONT_HERSHEY_SIMPLEX, 0.45, (20, 20, 20), 1,
                        cv2.LINE_AA)
            if self.visitas_xy:
                orden = [str(k + 1) for k, q in enumerate(self.visitas_xy)
                         if abs(q[0] - tg.c[0]) < 1 and abs(q[1] - tg.c[1]) < 1]
                if orden:
                    cv2.putText(mapa, ",".join(orden), (p[0] + s + 3, p[1] - s), cv2.FONT_HERSHEY_SIMPLEX, 0.45,
                                AZUL, 1, cv2.LINE_AA)
        # rastro y dron
        if len(self.rastro) > 1:
            cv2.polylines(mapa, [np.array([self.px(*p) for p in self.rastro], np.int32)], False, ROJO, 1, cv2.LINE_AA)
        d = self.px(sim.x, sim.y)
        cv2.circle(mapa, d, 7, ROJO, 2, cv2.LINE_AA)
        cv2.line(mapa, d, self.px(sim.x + 25 * f[0], sim.y + 25 * f[1]), ROJO, 2, cv2.LINE_AA)
        # derecha: lo que ve el detector y el estado
        cam = getattr(mis, "_shown", None)
        if cam is not None:
            img[10:310, MAPA + 10:MAPA + 410] = cv2.resize(cam if cam.ndim == 3 else cv2.cvtColor(cam, cv2.COLOR_GRAY2BGR),
                                                           (400, 300), interpolation=cv2.INTER_AREA)
        ejec = [e.split("=")[0] for e in mis.executed]
        y = 335
        lineas = [(self.titulo, BLANCO, 0.7), (f"t {t:5.1f} s   {mis.state}   altura {sim.z:.0f} cm", BLANCO, 0.5)]
        lineas += [(txt, (200, 200, 200), 0.42) for txt in _cortar(mis.reason, 52)[:2]]
        if self.esperado:
            ok = 0
            for a_, b_ in zip(ejec, self.esperado):
                if int(a_) != b_:
                    break
                ok += 1
            lineas += [(f"esperado: {' '.join(map(str, self.esperado))}", AZUL, 0.5),
                       (f"ejecuto:  {' '.join(ejec)}", VERDE, 0.5),
                       (f"puntos {ok} de {len(self.esperado)}", BLANCO, 0.6)]
        else:
            lineas += [(f"ejecuto: {' '.join(ejec)}", VERDE, 0.5)]
        for txt, col, esc in lineas:
            cv2.putText(img, txt, (MAPA + 10, y), cv2.FONT_HERSHEY_SIMPLEX, esc, col, 1, cv2.LINE_AA)
            y += int(34 * esc + 12)
        return img

    def tick(self, sim, mis, t: float) -> None:
        if len(mis.executed) > self.n_ejec:  # marcar en verde el tag que acaba de ejecutar
            self.n_ejec = len(mis.executed)
            tid = int(mis.executed[-1].split("=")[0])
            cerca = [(math.hypot(tg.c[0] - sim.x, tg.c[1] - sim.y), i) for i, tg in enumerate(self.tags) if tg.id == tid]
            if cerca:
                self.hechos.append(min(cerca)[1])
        if t < self.t_sig:
            return
        self.t_sig += 1 / FPS
        if not self.rastro or math.hypot(sim.x - self.rastro[-1][0], sim.y - self.rastro[-1][1]) > 2:
            self.rastro.append((sim.x, sim.y))
        cv2.imwrite(str(self.salida / f"{self.n:05d}.jpg"), self.cuadro(sim, mis, t), [cv2.IMWRITE_JPEG_QUALITY, 85])
        self.n += 1


def _cortar(txt: str, n: int) -> list[str]:
    out, linea = [], ""
    for w in txt.split():
        if len(linea) + len(w) + 1 > n:
            out.append(linea)
            linea = w
        else:
            linea = f"{linea} {w}".strip()
    return out + ([linea] if linea else [])


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("escenario")
    ap.add_argument("--salida", required=True, help="carpeta para los cuadros")
    ap.add_argument("--semilla", type=int, default=0)
    ap.add_argument("--dron", help="perfil del dron simulado (1, 7)")
    ap.add_argument("--titulo", default="")
    args = ap.parse_args()

    salida = Path(args.salida)
    salida.mkdir(parents=True, exist_ok=True)
    for f in salida.glob("*.jpg"):
        f.unlink()
    SW.SEMILLA = args.semilla
    if args.dron:
        SW.P, SW.DRON = SW.cargar_params(args.dron), args.dron
    esperado = visitas_xy = None
    if args.escenario == "espejo_competencia":
        import pista
        p = pista.generar(args.semilla)
        esperado = p.esperado()
        visitas_xy = [(p.tags[i][1], p.tags[i][2]) for i in p.visitas]
    titulo = args.titulo or f"{args.escenario} semilla {args.semilla}" + (f" Tello {args.dron}" if args.dron else "")
    rec: dict = {}
    run_original = SW.run

    def run_grabando(name, tags, **kw):
        g = rec.setdefault("g", Grabador(salida, tags, esperado, visitas_xy, titulo))
        previo = kw.get("events")

        def ev(sim, mis, t):
            if previo:
                previo(sim, mis, t)
            rec["sim"], rec["mis"] = sim, mis
            g.tick(sim, mis, t)
        kw["events"] = ev
        return run_original(name, tags, **kw)

    SW.run = run_grabando
    SW.scenario(args.escenario)
    g, sim, mis = rec.get("g"), rec.get("sim"), rec.get("mis")
    if g and sim and mis:
        final = g.cuadro(sim, mis, g.t_sig)
        for _ in range(2 * FPS):  # el resultado se queda 2 s en pantalla
            cv2.imwrite(str(salida / f"{g.n:05d}.jpg"), final, [cv2.IMWRITE_JPEG_QUALITY, 85])
            g.n += 1
        (salida / "resultado.json").write_text(json.dumps(
            {"ejecutados": mis.executed, "esperado": esperado, "estado": mis.state, "razon": mis.reason,
             "cuadros": g.n}, ensure_ascii=False, indent=1))
        print(f"[grabar] {g.n} cuadros en {salida}")


if __name__ == "__main__":
    main()
