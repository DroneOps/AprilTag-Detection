#!/usr/bin/env python3
"""Compara variantes del control (p. ej. PID contra Kalman) en el simulador, en tandas.

Corre cada escenario con cada dron N veces por variante, con las mismas semillas de deriva
aleatoria para todas las variantes, y resume:
- espejo_estacionario: distancia al despegue (media, máxima y al final) en los 20 s quieto;
- escenarios con tags: corridas completas, tags ejecutados y a qué distancia real del tag
  empezó a ejecutar cada uno.

Uso:
    python sim/comparar_control.py --variante pid: --variante "kalman:--set piso_control=kalman"
    python sim/comparar_control.py --escenarios espejo_circuito --drones 7 --n 8 \\
        --variante pid: --variante "kalman:--set piso_control=kalman" --salida sim/logs/comp.jsonl

Cada variante es "nombre:banderas de sim_world.py" (--set clave=valor, --sim clave=valor).
Corre en tiempo real: ~40 s por estacionario y ~60–90 s por circuito, de --paralelo en
--paralelo (con más de 3–4 a la vez el CPU no alcanza y la visión se atrasa).
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import shlex
import subprocess
import sys
import time
from collections import defaultdict
from pathlib import Path

import numpy as np

ROOT = Path(__file__).resolve().parent.parent
SIM = ROOT / "sim" / "sim_world.py"
COMPLETO = {"espejo_circuito": [1, 2, 7], "espejo_lab": [1, 2, 7], "espejo_gastado": [1, 2, 7]}


def leer(out: str) -> dict:
    """Lo que interesa de la salida de una corrida de sim_world.py."""
    r: dict = {"final": None, "choque": None, "ejecutados": [], "al_ejecutar": [], "apagado": []}
    m = re.search(r"=====.*final (\S+) \| choque: (\S+) .*ejecutados: (\[.*?\]) \| giro", out)
    if m:
        r["final"], r["choque"] = m.group(1), None if m.group(2) == "None" else m.group(2)
        r["ejecutados"] = [int(x) for x in re.findall(r"['\"](\d+)=", m.group(3))]  # ['1=derecha', ...]
    m = re.search(r"distancia al despegue media (\d+) cm, máxima (\d+), al final (\d+)", out)
    if m:
        r["media"], r["maxima"], r["final_cm"] = (float(x) for x in m.groups())
    m = re.search(r"al ejecutar \(real\): (.*)", out)
    if m:
        r["al_ejecutar"] = [(int(a), float(b)) for a, b in re.findall(r"tag (\d+) a (\d+) cm", m.group(1))]
    r["apagado"] = sorted(set(re.findall(r"\[vuelo\] (\S+) apagad[oa]", out)))
    m = re.search(r"\[pista\].*visitas: (\[[\d, ]*\])", out)  # espejo_competencia: lo que haría un dron perfecto
    if m:
        r["esperado"] = json.loads(m.group(1))
        fin = re.findall(r"\s\d+\.\ds (LANDING|EMERGENCY_LAND|DONE)\s+(.*?)  \[", out)
        r["fin"] = fin[0][1] if fin else ""
    return r


def puntos(r: dict) -> int:
    """Tags bien ejecutados en orden hasta el primero que falla (después ya va fuera de la pista)."""
    n = 0
    for a, b in zip(r["ejecutados"], r["esperado"]):
        if a != b:
            break
        n += 1
    return n


def suavidad(log: Path) -> dict:
    """Qué tan bruscos son los mandos de lado y adelante mientras sostiene (HOVER, CRUISE,
    ADVANCE): cuánto cambian por segundo (rc/s) y qué parte del tiempo van al tope (±20)."""
    try:
        filas = [f for f in csv.DictReader(log.open()) if f["state"] in ("HOVER", "CRUISE", "ADVANCE")]
    except (OSError, KeyError):
        return {}
    if len(filas) < 20:
        return {}
    t = np.array([float(f["t"]) for f in filas])
    rc = np.array([[float(f["rc_lr"] or 0), float(f["rc_fb"] or 0)] for f in filas])
    seg = np.diff(t)
    ok = seg < 0.2  # sin brincar entre tramos
    cambio = np.abs(np.diff(rc, axis=0))[ok].sum(axis=1)
    dur = seg[ok].sum()
    return {"cambio_rc_s": float(cambio.sum() / dur) if dur > 0 else None,
            "al_tope": float(np.mean(np.abs(rc[:, 0]) >= 20))}


def correr(trabajos: list[tuple], paralelo: int, salida: Path | None) -> list[dict]:
    hechos, vivos = [], []
    pendientes = list(trabajos)
    while pendientes or vivos:
        while pendientes and len(vivos) < paralelo:
            var, flags, esc, dron, sem = pendientes.pop(0)
            suf = f"_{var}_{dron}_{sem}"
            cmd = [sys.executable, str(SIM), esc, "--semilla", str(sem), "--log-sufijo", suf] \
                + (["--dron", dron] if dron != "sano" else []) + shlex.split(flags)
            vivos.append(((var, esc, dron, sem), subprocess.Popen(cmd, stdout=subprocess.PIPE,
                                                                   stderr=subprocess.STDOUT, text=True)))
        time.sleep(0.5)
        for item in list(vivos):
            (var, esc, dron, sem), p = item
            if p.poll() is None:
                continue
            vivos.remove(item)
            r = {"variante": var, "escenario": esc, "dron": dron, "semilla": sem, **leer(p.stdout.read()),
                 **suavidad(ROOT / "sim" / "logs" / f"{esc}_{var}_{dron}_{sem}.csv")}
            (ROOT / "sim" / "logs" / f"{esc}_{var}_{dron}_{sem}.csv").unlink(missing_ok=True)
            hechos.append(r)
            if salida:
                with salida.open("a") as f:
                    f.write(json.dumps(r) + "\n")
            print(f"  {var:14s} {esc:20s} dron {dron:4s} sem {sem}: {resumen_corrida(r)}", flush=True)
    return hechos


def resumen_corrida(r: dict) -> str:
    if "media" in r:
        txt = f"media {r['media']:.0f} cm, máx {r['maxima']:.0f}, final {r['final_cm']:.0f}"
    elif "esperado" in r:
        txt = f"{puntos(r)} de {len(r['esperado'])} puntos; ejecutó {r['ejecutados']} de {r['esperado']}"
        if r["al_ejecutar"]:
            txt += " a " + "/".join(f"{d:.0f}" for _, d in r["al_ejecutar"]) + " cm"
        if puntos(r) < len(r["esperado"]):
            txt += f"; terminó: {r['fin']}"
    else:
        txt = f"{r['final']} ejecutó {r['ejecutados']}"
        if r["al_ejecutar"]:
            txt += " a " + "/".join(f"{d:.0f}" for _, d in r["al_ejecutar"]) + " cm"
    if r.get("cambio_rc_s") is not None:
        txt += f"; mandos {r['cambio_rc_s']:.0f} rc/s, {100 * r['al_tope']:.0f}% al tope"
    if r["choque"]:
        txt += f" CHOQUE {r['choque']}"
    if r["apagado"]:
        txt += f" ({', '.join(r['apagado'])} apagado)"
    return txt


def tabla(res: list[dict]) -> str:
    g = defaultdict(list)
    for r in res:
        g[(r["escenario"], r["dron"], r["variante"])].append(r)
    filas = ["| Escenario | Dron | Variante | Corridas | Resultado |", "|---|---|---|---|---|"]
    for (esc, dron, var), rs in sorted(g.items()):
        if all("media" in r for r in rs):
            med = [r["media"] for r in rs]
            txt = (f"media {np.mean(med):.0f} cm (de {min(med):.0f} a {max(med):.0f}); "
                   f"máxima {max(r['maxima'] for r in rs):.0f}; al final {np.mean([r['final_cm'] for r in rs]):.0f}")
        elif all("esperado" in r for r in rs):
            pts, tot = sum(puntos(r) for r in rs), sum(len(r["esperado"]) for r in rs)
            dist = [d for r in rs for _, d in r["al_ejecutar"]]
            txt = (f"**{pts} de {tot} puntos** ({100 * pts / tot:.0f} %); "
                   f"{sum(puntos(r) == len(r['esperado']) for r in rs)} pistas completas")
            if dist:
                txt += f"; al ejecutar, a {np.median(dist):.0f} cm del tag (mediana), máx {max(dist):.0f}"
        else:
            completo = COMPLETO.get(esc)
            n_ok = sum(r["ejecutados"] == completo for r in rs) if completo else None
            tags = sum(len(r["ejecutados"]) for r in rs)
            dist = [d for r in rs for _, d in r["al_ejecutar"]]
            txt = (f"{n_ok} completas; " if completo else "") + f"{tags} tags ejecutados"
            if dist:
                txt += f"; al ejecutar, a {np.median(dist):.0f} cm del tag (mediana), máx {max(dist):.0f}"
        cr = [r["cambio_rc_s"] for r in rs if r.get("cambio_rc_s") is not None]
        if cr:
            txt += f"; mandos {np.mean(cr):.0f} rc/s, {100 * np.mean([r['al_tope'] for r in rs if 'al_tope' in r]):.0f}% al tope"
        choques = sum(1 for r in rs if r["choque"])
        apag = sum(1 for r in rs if r["apagado"])
        if choques:
            txt += f"; **{choques} choques**"
        if apag:
            txt += f"; {apag} con algo apagado ({', '.join(sorted({a for r in rs for a in r['apagado']}))})"
        filas.append(f"| {esc} | {dron} | {var} | {len(rs)} | {txt} |")
    return "\n".join(filas)


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--escenarios", nargs="+", default=["espejo_estacionario", "espejo_circuito"])
    ap.add_argument("--drones", nargs="+", default=["sano", "1", "7"], help="sano = sin --dron")
    ap.add_argument("--n", type=int, default=4, help="corridas por combinación")
    ap.add_argument("--desde", type=int, default=1, help="primera semilla (para seguir una tanda: --desde 5)")
    ap.add_argument("--variante", action="append", required=True, help='"nombre:banderas", p. ej. "pid:"')
    ap.add_argument("--paralelo", type=int, default=3)
    ap.add_argument("--salida", help="agrega cada corrida a este archivo (jsonl)")
    ap.add_argument("--solo-tabla", action="store_true", help="no correr: resumir lo que ya está en --salida")
    args = ap.parse_args()
    salida = Path(args.salida) if args.salida else None
    if args.solo_tabla:
        res = [json.loads(ln) for ln in salida.read_text().splitlines() if ln.strip()]
        print(tabla(res))
        return
    variantes = [v.split(":", 1) for v in args.variante]
    # intercaladas: así, si se corta a la mitad, todas las variantes llevan corridas parecidas
    trabajos = [(var, flags, esc, dron, sem) for sem in range(args.desde, args.desde + args.n) for esc in args.escenarios
                for dron in args.drones for var, flags in variantes]
    print(f"{len(trabajos)} corridas, {args.paralelo} a la vez", flush=True)
    res = correr(trabajos, args.paralelo, salida)
    print()
    print(tabla(res))


if __name__ == "__main__":
    main()
