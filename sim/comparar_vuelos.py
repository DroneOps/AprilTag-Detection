#!/usr/bin/env python3
"""¿El simulador se parece al dron? Compara el modelo de sim_world.py con vuelos reales.

Toma bitácoras reales, le pasa al modelo del simulador los mismos rc que recibió el dron y
compara lo que hizo cada uno: rumbo, altura y, en vuelos con espejo, la posición del tag
(que da el movimiento horizontal real). También compara despegue, deriva y temperatura.

Uso:
    python sim/comparar_vuelos.py                        # la sesión más reciente de sesiones/
    python sim/comparar_vuelos.py sesiones/2026-11-09    # días o archivos .csv (varios)
    python sim/comparar_vuelos.py --ideal                # el modelo ideal en vez del JSON
    python sim/comparar_vuelos.py --ajustar              # además busca los valores que mejor
                                                         # reproducen los vuelos
    python sim/comparar_vuelos.py --ajustar --guardar    # ...y los guarda en config/sim_tello.json
    python sim/comparar_vuelos.py <bitácoras del Tello 7> --dron 7   # contra el perfil de un dron

Córrelo después de cada sesión de laboratorio: si el simulador ya no se parece al dron, el
resumen lo dice y --ajustar propone los valores nuevos. Ver docs/simulador.md.
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics as st
import sys
from dataclasses import asdict, replace
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parent))
import sim_world as SW  # noqa: E402

ROOT = SW.ROOT
EN_EL_AIRE = {"HOVER", "CRUISE", "ADVANCE", "APPROACH", "EXECUTE", "RC_STEP", "YAW_TEST", "RC_ALT",
              "FLIP_CLIMB"}
VENTANA_S = 1.5  # se compara cuánto cambió cada cosa en tramos de este largo
FILTRO_TAG_S = 0.1  # la misión usa la mediana de 7 cuadros: la posición del tag llega ~3 cuadros tarde
SUB_DT = 0.025


# ------------------------------------------------------------------ bitácoras

def _f(v):
    try:
        return float(v)
    except (TypeError, ValueError):
        return None


class Vuelo:
    def __init__(self, path: Path) -> None:
        self.path, self.nombre = path, path.name
        self.tipo = path.name.split("_")[0]
        rows = list(csv.DictReader(path.open()))
        self.rows = rows
        self.t = [_f(r.get("t")) for r in rows]
        self.state = [r.get("state", "") for r in rows]
        self.reason = [r.get("reason", "") for r in rows]
        self.tof = [_f(r.get("tof")) for r in rows]
        self.temp = [_f(r.get("temph")) for r in rows]
        self.rc = [tuple(_f(r.get(k)) or 0.0 for k in ("rc_lr", "rc_fb", "rc_ud", "rc_yaw")) for r in rows]
        self.tag = [(_f(r.get("tag_adelante")), _f(r.get("tag_derecha"))) for r in rows]
        self.obj = [r.get("objetivo", "") for r in rows]
        # rumbo continuo (sin el salto de 180 a -180)
        self.yaw, prev, off = [], None, 0.0
        for r in rows:
            y = _f(r.get("yaw"))
            if y is None:
                self.yaw.append(None)
                continue
            if prev is not None:
                d = y - prev
                off -= 360 * round(d / 360)
            prev = y
            self.yaw.append(y + off)
        # filas válidas: en el aire, tof creíble, sin flip cerca
        flip_t = [self.t[i] for i, r in enumerate(rows)
                  if abs(_f(r.get("pitch")) or 0) > 30 or "flip" in self.reason[i].lower()]
        self.ok = []
        for i in range(len(rows)):
            good = (self.state[i] in EN_EL_AIRE and self.t[i] is not None and self.yaw[i] is not None
                    and self.tof[i] is not None and 20 < self.tof[i] < 400
                    and not any(-0.5 <= self.t[i] - ft <= 3.0 for ft in flip_t))
            self.ok.append(good)
        self.alt = [None if x is None else x - 10 for x in self.tof]

    def piso(self) -> bool:
        return self.tipo == "piso"


def buscar(paths: list[str]) -> list[Path]:
    if not paths:
        dias = sorted(d for d in (ROOT / "sesiones").iterdir() if (d / "vuelos").is_dir())
        if not dias:
            raise SystemExit("no hay sesiones con vuelos en sesiones/")
        paths = [str(dias[-1])]
    out = []
    for p in map(Path, paths):
        if p.is_dir():
            out += sorted((p / "vuelos" if (p / "vuelos").is_dir() else p).glob("*.csv"))
        elif p.suffix == ".csv":
            out.append(p)
    return out


# ------------------------------------------------------------------ el modelo con los mismos rc

def replay(v: Vuelo, p: SW.SimParams):
    """Integra el modelo del simulador con los rc del vuelo. Devuelve, por fila, lo acumulado
    de giro (°), altura (cm), adelante y derecha (cm, marco del dron). Sin viento: la deriva se
    compara aparte."""
    sag = p.hundimiento_cm_s if p.hundimiento_cm_s is not None else (15.0 if v.piso() else 0.0)
    combo = p.combo if p.combo is not None else (0.55 if v.piso() else 1.0)
    rcq = SW.RcAtrasado()
    rate = sigue = 0.0
    vel = [0.0, 0.0, 0.0]
    Y, Z, A, R = [0.0], [0.0], [0.0], [0.0]
    for i in range(len(v.t) - 1):
        t0, t1 = v.t[i], v.t[i + 1]
        if t0 is None or t1 is None or t1 <= t0:
            Y.append(Y[-1]), Z.append(Z[-1]), A.append(A[-1]), R.append(R[-1])
            continue
        rcq.put(t0, v.rc[i])
        y, z, a, r = Y[-1], Z[-1], A[-1], R[-1]
        if v.ok[i] or v.state[i] in EN_EL_AIRE:
            n = max(1, round((t1 - t0) / SUB_DT))
            h = (t1 - t0) / n
            for k in range(n):
                rc = rcq.at(t0 + (k + 1) * h, p.mando_atraso_s)
                vel = SW.paso_vel(vel, rc, h, p, 1.0, combo, sag)
                rate, sigue = SW.paso_giro(rate, sigue, rc[3], h, p)
                y += (rate + sigue) * h
                z += vel[2] * h
                a += (vel[0] + p.deriva_adelante_cm_s) * h  # la deriva constante también (la aleatoria no)
                r += (vel[1] + p.deriva_lado_cm_s) * h
        else:  # en tierra o despegando: el dron no obedece el rc
            rate = sigue = 0.0
            vel = [0.0, 0.0, 0.0]
        Y.append(y), Z.append(z), A.append(a), R.append(r)
    return Y, Z, A, R


def _interp(ts, xs, t):
    """xs en el tiempo t (lineal); ts creciente."""
    lo, hi = 0, len(ts) - 1
    if t <= ts[0]:
        return xs[0]
    if t >= ts[hi]:
        return xs[hi]
    while hi - lo > 1:
        mid = (lo + hi) // 2
        if ts[mid] <= t:
            lo = mid
        else:
            hi = mid
    f = (t - ts[lo]) / (ts[hi] - ts[lo]) if ts[hi] > ts[lo] else 0
    return xs[lo] + f * (xs[hi] - xs[lo])


def tramos(v: Vuelo, largo: float):
    """Pares (i, j) de filas válidas separadas ~largo s, todas válidas en medio."""
    i, n = 0, len(v.t)
    while i < n:
        if not v.ok[i]:
            i += 1
            continue
        j = i
        while j + 1 < n and v.ok[j + 1] and v.t[j + 1] - v.t[i] <= largo + 1e-6:
            j += 1
        if v.t[j] - v.t[i] >= largo * 0.9:
            yield i, j
        i = j if j > i else i + 1


def errores(vuelos, modelos, p):
    """Error del modelo al predecir cuánto cambió cada cosa en tramos de VENTANA_S."""
    e_yaw, e_alt, e_xy = [], [], []
    for v, (Y, Z, A, R) in zip(vuelos, modelos):
        ts = [x if x is not None else 0 for x in v.t]
        for i, j in tramos(v, VENTANA_S):
            e_yaw.append((Y[j] - Y[i]) - (v.yaw[j] - v.yaw[i]))
            if abs(v.alt[j] - v.alt[i]) < 60:  # sin saltos falsos del tof
                e_alt.append((Z[j] - Z[i]) - (v.alt[j] - v.alt[i]))
            ti, tj = v.tag[i], v.tag[j]
            if (None not in ti and None not in tj and v.obj[i] == v.obj[j]
                    and abs(v.yaw[j] - v.yaw[i]) < 5):
                lat = p.video_atraso_s + FILTRO_TAG_S  # el tag de la fila se vio con este atraso
                da = _interp(ts, A, v.t[j] - lat) - _interp(ts, A, v.t[i] - lat)
                dr = _interp(ts, R, v.t[j] - lat) - _interp(ts, R, v.t[i] - lat)
                e_xy.append(math.hypot(da + (tj[0] - ti[0]), dr + (tj[1] - ti[1])))
    return e_yaw, e_alt, e_xy


def mean_abs(xs):
    return sum(abs(x) for x in xs) / len(xs) if xs else float("nan")


# ------------------------------------------------------------------ rasgos: real contra modelo

def rasgos(vuelos, modelos, p):
    """Lo mismo medido en el dron real y en el modelo, sobre los mismos tramos."""
    out = {}

    def add(k, real, sim):
        out.setdefault(k, ([], []))
        out[k][0].append(real)
        out[k][1].append(sim)

    for v, (Y, Z, A, R) in zip(vuelos, modelos):
        n = len(v.t)
        ts = [x if x is not None else 0 for x in v.t]
        i = 0
        while i < n:  # giro con rc constante (0.6–1 s)
            yr = v.rc[i][3]
            if not v.ok[i] or yr == 0:
                i += 1
                continue
            j = i
            while j + 1 < n and v.ok[j + 1] and v.rc[j + 1][3] == yr and v.t[j + 1] - v.t[i] <= 1.0:
                j += 1
            dt = v.t[j] - v.t[i]
            if dt >= 0.6:
                a = abs(yr)
                b = "15–19" if a < 20 else "20–29" if a < 30 else "30–49" if a < 50 else "50+"
                s = math.copysign(1, yr)
                add(f"giro con rc {b} (°/s)", s * (v.yaw[j] - v.yaw[i]) / dt, s * (Y[j] - Y[i]) / dt)
            i = j + 1
        for i in range(1, n):  # lo que sigue girando en 2 s tras soltar un giro grande
            if v.ok[i] and v.rc[i][3] == 0 and v.rc[i - 1][3] != 0:
                k, big, s = i - 1, False, math.copysign(1, v.rc[i - 1][3])
                while k > 0 and v.rc[k][3] != 0 and v.t[i] - v.t[k] < 3:
                    big = big or abs(v.rc[k][3]) >= 40
                    k -= 1
                j = i
                while j + 1 < n and v.ok[j + 1] and v.t[j + 1] - v.t[i] <= 2.0:
                    j += 1
                if big and v.t[j] - v.t[i] >= 1.8:
                    add("sigue girando tras un giro (°)", s * (v.yaw[j] - v.yaw[i]), s * (Y[j] - Y[i]))
        for i, j in tramos(v, 1.0):  # altura avanzando sin pedir subir
            seg = range(i, j + 1)
            if all(v.rc[k][1] >= 10 and v.rc[k][2] == 0 for k in seg) and abs(v.alt[j] - v.alt[i]) < 40:
                dt = v.t[j] - v.t[i]
                add("altura al avanzar sin rc vertical (cm/s)", (v.alt[j] - v.alt[i]) / dt, (Z[j] - Z[i]) / dt)
            if all(v.rc[k][0] != 0 and v.rc[k][1] != 0 and v.rc[k][3] == 0 for k in seg) and abs(v.alt[j] - v.alt[i]) < 40:
                dt = v.t[j] - v.t[i]
                add("altura con lado y adelante a la vez (cm/s)", (v.alt[j] - v.alt[i]) / dt, (Z[j] - Z[i]) / dt)
            ud = v.rc[i][2]
            if ud > 0 and all(v.rc[k][2] == ud and v.rc[k][1] == 0 for k in seg) and abs(v.alt[j] - v.alt[i]) < 60:
                dt = v.t[j] - v.t[i]
                b = "10–19" if ud < 20 else "20+"
                add(f"subir con rc {b} (cm/s)", (v.alt[j] - v.alt[i]) / dt, (Z[j] - Z[i]) / dt)
        lat = p.video_atraso_s + FILTRO_TAG_S
        for i, j in tramos(v, 0.8):  # adelante con rc fijo y deriva con rc 0, por el tag
            ti, tj = v.tag[i], v.tag[j]
            if None in ti or None in tj or v.obj[i] != v.obj[j] or abs(v.yaw[j] - v.yaw[i]) > 5:
                continue
            seg = range(i, j + 1)
            dt = v.t[j] - v.t[i]
            fb = v.rc[i][1]
            if fb >= 10 and all(v.rc[k][1] == fb and v.rc[k][0] == 0 for k in seg):
                sim = (_interp(ts, A, v.t[j] - lat) - _interp(ts, A, v.t[i] - lat)) / dt
                add(f"adelante con rc {int(fb)} (cm/s, por el tag)", -(tj[0] - ti[0]) / dt, sim)
            quieto = all(v.rc[k][:2] == (0.0, 0.0) for k in range(i, j + 1))
            antes = [k for k in range(max(0, i - 40), i) if v.t[i] - v.t[k] <= 1.0]
            if quieto and all(v.rc[k][:2] == (0.0, 0.0) for k in antes):
                der, ade = -(tj[1] - ti[1]) / dt, -(tj[0] - ti[0]) / dt  # el tag se mueve al revés que el dron
                add("deriva con rc 0 (cm/s, por el tag)", math.hypot(der, ade),
                    math.hypot(p.deriva_lado_cm_s, p.deriva_adelante_cm_s) + 1.18 * p.deriva_cm_s)
                add("deriva a la derecha con rc 0 (cm/s, por el tag)", der, p.deriva_lado_cm_s)
                add("deriva adelante con rc 0 (cm/s, por el tag)", ade, p.deriva_adelante_cm_s)
        for k in range(1, n):  # giros grandes con el tag a la vista: cuánto se corrió el dron
            if not (v.ok[k] and abs(v.rc[k][3]) >= 40 and v.rc[k - 1][3] == 0 and None not in v.tag[k]):
                continue
            e = k
            while e + 1 < n and v.ok[e + 1] and (v.rc[e + 1][3] != 0 or abs(v.yaw[e + 1] - v.yaw[e]) > 0.5) \
                    and v.t[e + 1] - v.t[k] < 4:
                e += 1
            while e > k and None in v.tag[e]:
                e -= 1
            dt = v.t[e] - v.t[k]
            if e - k < 10 or abs(v.yaw[e] - v.yaw[k]) < 45:
                continue

            def pos(i):  # dron respecto al tag, en el marco de antes del giro
                g = math.radians(v.yaw[i] - v.yaw[k])
                a, b = v.tag[i]
                return -(a * math.cos(g) - b * math.sin(g)), -(a * math.sin(g) + b * math.cos(g))
            p0, p1 = pos(k), pos(e)
            add("se corre al girar 90° (cm/s)", math.hypot(p1[0] - p0[0], p1[1] - p0[1]) / dt,
                math.hypot(p.deriva_lado_cm_s, p.deriva_adelante_cm_s) + p.giro_deriva_cm_s)
    return out


def despegues(vuelos):
    """Altura final, pico, cuándo llegó el ok y si se vino abajo, según la bitácora."""
    res = []
    for v in vuelos:
        msg = next((r for r in v.reason if r.startswith("en el aire a")), None)
        alts = [v.alt[i] for i in range(len(v.t)) if v.state[i] == "TAKEOFF" and v.alt[i] is not None
                and v.tof[i] < 400]
        if not alts:
            continue
        # se vino abajo: subió 30 cm o más y, sin terminar el despegue, regresó al piso (real 9-nov)
        cayo = any(alts[k] >= 30 for k in range(len(alts))) and any(
            a <= 5 for a in alts[next(k for k in range(len(alts)) if alts[k] >= 30):])
        d = {"vuelo": v.nombre, "pico": max(alts),
             "cayo": cayo or any("se vino abajo" in r for r in v.reason)}
        if msg:
            m = re.search(r"en el aire a (\d+) cm \(([^)]*)despegue ([\d.]+) s\)", msg)
            if m:
                d["final"], d["ok"], d["t"] = float(m.group(1)), "ok del Tello" in m.group(2), float(m.group(3))
        res.append(d)
    return res


def temperatura(vuelos):
    out = []
    for v in vuelos:
        pts = [(v.t[i], v.temp[i]) for i in range(len(v.t)) if v.state[i] in EN_EL_AIRE and v.temp[i]]
        if len(pts) > 2 and pts[-1][0] - pts[0][0] > 15:
            out.append((pts[-1][1] - pts[0][1]) / (pts[-1][0] - pts[0][0]) * 60)
    return out


# ------------------------------------------------------------------ ajuste

MEJORA_MIN = 0.01  # un valor solo cambia si baja el error al menos 1 %
GRUPOS = {  # cada parámetro se ajusta con el error de su canal (el atraso del video no: se midió aparte)
    "giro": ("yaw", {"giro_ganancia": (0.5, 1.4, 0.05), "giro_zona_muerta": (2, 26, 1),
                     "giro_respuesta_s": (0.05, 0.8, 0.05), "giro_sigue": (0.0, 0.8, 0.02),
                     "giro_sigue_s": (0.5, 5.0, 0.25), "mando_atraso_s": (0.0, 0.4, 0.02)}),
    "vertical": ("alt", {"subir_ganancia": (0.3, 1.5, 0.05), "bajar_ganancia": (0.1, 1.2, 0.05),
                         "vertical_respuesta_s": (0.1, 1.5, 0.05), "hundimiento_cm_s": (0.0, 20.0, 1.0),
                         "hundimiento_combo_cm_s": (0.0, 20.0, 1.0)}),
    "horizontal": ("xy", {"avance_ganancia": (0.8, 2.5, 0.05), "avance_zona_muerta": (2, 10, 0.5),
                          "respuesta_s": (0.1, 1.0, 0.05), "combo": (0.3, 1.0, 0.05)}),
}


RASGOS_CANAL = {"yaw": ("giro con rc", "sigue girando"), "alt": ("altura al avanzar", "subir con rc", "altura con lado"),
                "xy": ("adelante con rc",)}


def perdida(vuelos, p, canal):
    """Error medio en los tramos más la diferencia en los rasgos (con 3 o más casos): así cuentan
    también los eventos raros que importan, como lo que sigue girando tras un giro."""
    modelos = [replay(v, p) for v in vuelos]
    e_yaw, e_alt, e_xy = errores(vuelos, modelos, p)
    base = mean_abs({"yaw": e_yaw, "alt": e_alt, "xy": e_xy}[canal])
    r = rasgos(vuelos, modelos, p)
    dif = [abs(st.median(sim) - st.median(real)) for k, (real, sim) in r.items()
           if k.startswith(RASGOS_CANAL[canal]) and len(real) >= 3]
    return base + (0.5 * sum(dif) / len(dif) if dif else 0.0)


def ajustar(vuelos, p: SW.SimParams) -> SW.SimParams:
    for grupo, (canal, params) in GRUPOS.items():
        best = perdida(vuelos, p, canal)
        if math.isnan(best):
            print(f"  {grupo}: sin datos, se deja igual")
            continue
        for _ in range(3):  # descenso por coordenadas
            for k, (lo, hi, paso) in params.items():
                vals = [round(lo + i * paso, 4) for i in range(int(round((hi - lo) / paso)) + 1)]
                for val in vals:  # (hundimiento y combo sin valor = lo de piso; solo cambian con datos)
                    q = replace(p, **{k: val})
                    e = perdida(vuelos, q, canal)
                    if e < best * (1 - MEJORA_MIN):  # con pocos datos, no mover lo que no importa
                        best, p = e, q
        print(f"  {grupo}: error medio {best:.2f}")
    return p


def ajustar_resto(vuelos, p: SW.SimParams, r, dsp, temps) -> SW.SimParams:
    """Despegue, deriva y temperatura: directo de lo medido."""
    cambios = {}
    der = r.get("deriva a la derecha con rc 0 (cm/s, por el tag)", ([], []))[0]
    ade = r.get("deriva adelante con rc 0 (cm/s, por el tag)", ([], []))[0]
    if len(der) >= 3:  # lo constante es la mediana; lo aleatorio, lo que varía alrededor
        cambios["deriva_lado_cm_s"] = round(st.median(der), 1)
        cambios["deriva_adelante_cm_s"] = round(st.median(ade), 1)
        resto = [math.hypot(a - cambios["deriva_lado_cm_s"], b - cambios["deriva_adelante_cm_s"]) for a, b in zip(der, ade)]
        cambios["deriva_cm_s"] = round(st.median(resto) / 1.18, 1)
    giros = r.get("se corre al girar 90° (cm/s)", ([], []))[0]
    if len(giros) >= 3:
        constante = math.hypot(cambios.get("deriva_lado_cm_s", p.deriva_lado_cm_s),
                               cambios.get("deriva_adelante_cm_s", p.deriva_adelante_cm_s))
        cambios["giro_deriva_cm_s"] = round(max(0.0, st.median(giros) - constante), 1)
    finales = sorted(d["final"] for d in dsp if "final" in d and d["final"] < 120)
    if len(finales) >= 3:
        cambios["despegue_cm"] = (finales[len(finales) // 10], finales[(9 * len(finales)) // 10])
        picos = [d["pico"] - d["final"] for d in dsp if "final" in d and d["final"] < 120]
        cambios["despegue_pico_cm"] = round(max(0.0, st.median(picos)), 0)
        oks = sorted(d["t"] for d in dsp if d.get("ok") and d["final"] < 120)
        if len(oks) >= 3:
            cambios["despegue_ok_s"] = (oks[len(oks) // 10], oks[(9 * len(oks)) // 10])
    if len(temps) >= 3:
        cambios["temp_c_por_min"] = round(st.median(temps), 1)
    return replace(p, **cambios)


# ------------------------------------------------------------------ informe

def informe(vuelos, p, titulo):
    modelos = [replay(v, p) for v in vuelos]
    e_yaw, e_alt, e_xy = errores(vuelos, modelos, p)
    r = rasgos(vuelos, modelos, p)
    print(f"\n== {titulo}")
    print(f"{'':46s} {'real':>8s} {'simulador':>10s}   n")
    for k in sorted(r):
        real, sim = r[k]
        if real:
            print(f"  {k:44s} {st.median(real):8.1f} {st.median(sim):10.1f}   {len(real)}")
    print(f"  error al predecir {VENTANA_S:g} s de vuelo (promedio):")
    print(f"    rumbo {mean_abs(e_yaw):.1f}°  ({len(e_yaw)} tramos) | altura {mean_abs(e_alt):.1f} cm "
          f"({len(e_alt)}) | posición del tag {mean_abs(e_xy):.1f} cm ({len(e_xy)})")
    return r


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("rutas", nargs="*", help="días de sesiones/ o bitácoras .csv")
    ap.add_argument("--ideal", action="store_true", help="comparar el modelo ideal, sin config/sim_tello.json")
    ap.add_argument("--ajustar", action="store_true", help="buscar los valores que mejor reproducen los vuelos")
    ap.add_argument("--guardar", action="store_true", help="con --ajustar: escribir config/sim_tello.json "
                    "(con --dron, solo lo que cambia, en config/sim_tello_dron<N>.json)")
    ap.add_argument("--dron", help="comparar contra el perfil de ese dron (config/sim_tello_dron<N>.json)")
    args = ap.parse_args()

    files = buscar(args.rutas)
    todos = [Vuelo(f) for f in files]
    vuelos = [v for v in todos if any(v.ok)]
    if not vuelos:
        raise SystemExit("ninguna bitácora con tramos en el aire")
    dias = sorted({f.parent.parent.name if f.parent.name == "vuelos" else f.parent.name for f in files})
    p = SW.SimParams() if args.ideal else SW.cargar_params(args.dron)
    fuente = ("modelo ideal" if args.ideal else "config/sim_tello.json"
              + (f" + {SW.json_dron(args.dron).name}" if args.dron else ""))
    print(f"{len(vuelos)} vuelos con tramos en el aire ({', '.join(dias)}); simulador: {fuente}")

    r = informe(vuelos, p, f"simulador actual ({fuente})")
    dsp, temps = despegues(todos), temperatura(vuelos)  # despegues: también los que no llegaron a volar
    fin = [d for d in dsp if "final" in d]
    print("  despegue real: altura final " + ", ".join(f"{d['final']:.0f}" for d in fin)
          + f" cm | ok del Tello en {sum(d['ok'] for d in fin)} de {len(fin)}"
          + f" | se vino abajo: {sum(d['cayo'] for d in dsp)}")
    print(f"  despegue simulador: {p.despegue_cm[0]:.0f}–{p.despegue_cm[1]:.0f} cm (+{p.despegue_pico_cm:.0f} de pico), "
          f"ok {'al llegar arriba' if not p.despegue_ok_s else f'a los {p.despegue_ok_s[0]:.1f}–{p.despegue_ok_s[1]:.1f} s'}")
    if temps:
        print(f"  temperatura real al volar: {st.median(temps):.1f} °C/min (simulador {p.temp_c_por_min:.1f})")

    if args.ajustar:
        print("\nAjustando (unos minutos)...")
        q = ajustar(vuelos, p)
        q = ajustar_resto(vuelos, q, r, dsp, temps)
        fuente = (f"ajustado con {len(vuelos)} vuelos de {', '.join(dias)} (sim/comparar_vuelos.py); "
                  "el atraso del video se midió aparte (docs/tello.md)")
        if q.deriva_cm_s == p.deriva_cm_s:
            fuente += f"; deriva: pocos datos, se dejó la de antes ({p.deriva_cm_s:g} cm/s)"
        q = replace(q, fuente=fuente)
        informe(vuelos, q, "con los valores ajustados")
        data = {k: (list(v) if isinstance(v, tuple) else v) for k, v in asdict(q).items()}
        texto = json.dumps(data, indent=2, ensure_ascii=False) + "\n"
        if args.guardar and args.dron:  # el perfil del dron: solo lo que difiere de la base
            base = asdict(SW.cargar_params())
            path = SW.json_dron(args.dron)
            perfil = json.loads(path.read_text()) if path.exists() else {}
            perfil.update({k: v for k, v in data.items() if k != "fuente" and v != (list(base[k]) if isinstance(base[k], tuple) else base[k])})
            perfil["fuente"] = q.fuente
            path.write_text(json.dumps(perfil, indent=2, ensure_ascii=False) + "\n")
            print(f"\nguardado en {path.relative_to(ROOT)}")
        elif args.guardar:
            SW.SIM_JSON.write_text(texto)
            print(f"\nguardado en {SW.SIM_JSON.relative_to(ROOT)}")
        else:
            print("\nvalores sugeridos (con --guardar se escriben en config/sim_tello.json):\n" + texto)


if __name__ == "__main__":
    main()
