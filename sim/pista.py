"""Pistas al azar como las de la competencia, para el simulador (escenario espejo_competencia).

Del reglamento (docs/competencia.md): los tags van en el piso, en las intersecciones de una
trayectoria; se colocan al azar y pueden estar girados; tras ejecutar cada uno, el dron avanza
siempre hacia el frente hasta el siguiente; el último es aterrizar (7). Lo que no sabemos
(cuántos tags, separación, tamaño, cómo es el tag de inicio) va como parámetro.

La pista se arma como la recorrería un dron perfecto: sale del despegue hacia adelante, en cada
tag aplica su giro y sigue derecho. Si al frente ya hay un tag (p. ej. tras un giro de 180° se
regresa al anterior), lo vuelve a visitar y lo ejecuta otra vez; si no, se pone uno nuevo a
70–150 cm. Se descartan las pistas donde un tag nuevo quedaría en el camino de un tramo anterior
(el dron lo habría visto antes), las que dan vueltas en círculo y las que se salen de la caja.

La misma semilla da la misma pista:
    python sim/pista.py 3          # imprime la pista 3
    python sim/sim_world.py espejo_competencia --semilla 3
"""
from __future__ import annotations

import math
import random
import sys
from dataclasses import dataclass

GIRO = {1: 90, 2: -90, 3: 180, 4: 0, 5: 0, 6: 0, 8: 180, 9: 0, 10: 0}  # cómo cambia el rumbo (+ = derecha)
ALTURA = {5: 30, 6: -30}  # la misión sostiene la altura nueva después de subir o bajar
PASILLO = 50.0  # cm de lado: un tag más cerca que esto del camino se ve al pasar (a 100 cm se ven ±52)
ATRAS = 65.0  # cm: con la vista inclinada hacia atrás (−10.3°) se ve hasta ~60 cm detrás del dron


@dataclass
class Pista:
    semilla: int
    tags: list[tuple[int, float, float, float]]  # (id, x, y, giro del tag en °): cm, x a la derecha del despegue, y adelante
    visitas: list[int]  # índices de tags en el orden en que los recorre un dron perfecto
    inicio: tuple[int, float] | None  # (id, giro) del tag de inicio, debajo del despegue

    def esperado(self) -> list[int]:
        return [self.tags[i][0] for i in self.visitas]

    def texto(self) -> str:
        seps, prev = [], (0.0, 0.0)
        for i in self.visitas:
            _, x, y, _ = self.tags[i]
            seps.append(math.hypot(x - prev[0], y - prev[1]))
            prev = (x, y)
        tags = ", ".join(f"{tid}@({x:.0f},{y:.0f}) {g:+.0f}°" for tid, x, y, g in self.tags)
        return (f"[pista] semilla {self.semilla}: {len(self.tags)} tags, {len(self.visitas)} visitas; "
                f"visitas: {self.esperado()} | separaciones {', '.join(f'{s:.0f}' for s in seps)} cm | "
                f"tags {tags}" + (f" | inicio id {self.inicio[0]}" if self.inicio else ""))


def _ejes(rumbo: float) -> tuple[tuple[float, float], tuple[float, float]]:
    a = math.radians(rumbo)
    return (math.sin(a), math.cos(a)), (math.cos(a), -math.sin(a))  # adelante, derecha


def _relativo(p, q, rumbo) -> tuple[float, float]:
    """(adelante, lado) de q visto desde p con ese rumbo."""
    u, r = _ejes(rumbo)
    dx, dy = q[0] - p[0], q[1] - p[1]
    return dx * u[0] + dy * u[1], dx * r[0] + dy * r[1]


def _intento(rng: random.Random, n: int, sep: tuple[float, float], giro_tag: float, desvio: float,
             alt: tuple[float, float], alt0: float, flips: bool, caja: float) -> tuple[list, list] | None:
    tags: list[tuple[int, float, float, float]] = []
    tramos: list[tuple[tuple[float, float], float, float]] = []  # (desde, rumbo, largo)
    salidas: list[tuple[tuple[float, float], float, int | None]] = []  # (desde, rumbo, tag de ahí)
    visitas: list[int] = []
    vistos: set[tuple[int, int]] = set()
    pos, rumbo, h, actual = (0.0, 0.0), 0.0, alt0, None
    while True:
        # al arrancar, un tag que se vea detrás o debajo (que no sea el de ahí) se lo llevaría
        salidas.append((pos, rumbo, actual))
        if any(_al_arrancar(pos, rumbo, (x, y)) for i, (_, x, y, _) in enumerate(tags) if i != actual):
            return None
        # ¿hay un tag al frente, en el pasillo? (el de debajo y los de atrás no cuentan)
        delante = []
        for i, (_, x, y, _) in enumerate(tags):
            f, l = _relativo(pos, (x, y), rumbo)
            if i != actual and 20 < f <= sep[1] + 30 and abs(l) < PASILLO:
                delante.append((f, i))
        if delante:
            f, i = min(delante)
            tramos.append((pos, rumbo, f))
        else:
            if len(tags) == n:
                return None
            tid = 7 if len(tags) == n - 1 else _elegir(rng, h, alt, flips)
            if tid is None:
                return None
            for _ in range(40):
                d, lado = rng.uniform(*sep), rng.uniform(-desvio, desvio)
                u, r = _ejes(rumbo)
                q = (pos[0] + d * u[0] + lado * r[0], pos[1] + d * u[1] + lado * r[1])
                if _cabe(q, pos, rumbo, d, tags, tramos, actual, caja) \
                        and not any(_al_arrancar(p0, rb, q) for p0, rb, _ in salidas):
                    break
            else:
                return None
            tags.append((tid, q[0], q[1], rng.uniform(-giro_tag, giro_tag)))
            tramos.append((pos, rumbo, d))
            i = len(tags) - 1
        if (i, int(rumbo) % 360) in vistos or len(visitas) > 2 * n + 2:
            return None  # da vueltas en círculo
        vistos.add((i, int(rumbo) % 360))
        visitas.append(i)
        tid, x, y, _ = tags[i]
        if tid == 7:
            return (tags, visitas) if len(tags) == n else None
        pos, actual = (x, y), i
        rumbo = (rumbo + GIRO[tid]) % 360
        h += ALTURA.get(tid, 0)
        if not alt[0] <= h <= alt[1]:
            return None


def _al_arrancar(desde, rumbo, q) -> bool:
    """¿q se ve al arrancar desde ahí (detrás, debajo o apenas adelante)?"""
    f, l = _relativo(desde, q, rumbo)
    return -ATRAS < f <= 20 and abs(l) < PASILLO + 5


def _elegir(rng: random.Random, h: float, alt: tuple[float, float], flips: bool) -> int | None:
    ops = [t for t in GIRO if (flips or t not in (4, 8)) and alt[0] <= h + ALTURA.get(t, 0) <= alt[1]]
    return rng.choice(ops) if ops else None


def _cabe(q, pos, rumbo, d, tags, tramos, actual, caja) -> bool:
    if abs(q[0]) > caja or abs(q[1]) > caja:
        return False
    for i, (_, x, y, _) in enumerate(tags):
        if math.hypot(q[0] - x, q[1] - y) < (70 if i == actual else 90):
            return False
        f, l = _relativo(pos, (x, y), rumbo)  # un tag viejo en el camino nuevo
        if i != actual and -20 < f < d + 20 and abs(l) < PASILLO + 10:
            return False
    for desde, rb, largo in tramos:  # el tag nuevo en el camino de un tramo anterior
        f, l = _relativo(desde, q, rb)
        if -20 < f < largo + 20 and abs(l) < PASILLO + 10:
            return False
    return True


def generar(semilla: int, n: int | None = None, sep: tuple[float, float] = (70.0, 150.0), giro_tag: float = 45.0,
            desvio: float = 8.0, alt: tuple[float, float] = (70.0, 130.0), alt0: float = 100.0,
            flips: bool = True, caja: float = 300.0, inicio: int | None = 0) -> Pista:
    """Pista de n tags distintos (5–8 al azar si no se dice), el último el 7. sep: separación
    entre tags (cm); giro_tag: qué tanto pueden estar girados (°); desvio: qué tanto se salen de
    la línea (cm); alt: alturas permitidas tras subir/bajar; caja: la pista cabe en ±caja cm;
    inicio: id del tag de inicio debajo del despegue (None: sin tag de inicio; 0 no es de los
    1–10, así que la misión no lo toma en cuenta)."""
    rng = random.Random(semilla)
    n = n or rng.randint(5, 8)
    for _ in range(2000):
        r = _intento(rng, n, sep, giro_tag, desvio, alt, alt0, flips, caja)
        if r:
            tags, visitas = r
            return Pista(semilla, tags, visitas, None if inicio is None else (inicio, rng.uniform(-giro_tag, giro_tag)))
    raise RuntimeError(f"no salió una pista con la semilla {semilla}")


if __name__ == "__main__":
    for s in (sys.argv[1:] or ["1"]):
        print(generar(int(s)).texto())
