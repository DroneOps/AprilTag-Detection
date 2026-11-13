#!/usr/bin/env python3
"""Cómo sostuvo la posición con el piso cada vuelo con espejo: para comparar el PID y el
Kalman en el laboratorio con números, no solo a ojo.

Uso:
    python scripts/resumen_piso.py                     # vuelos con espejo de hoy (logs/)
    python scripts/resumen_piso.py --ultimos 2         # los 2 más recientes
    python scripts/resumen_piso.py --fecha 20261113
    python scripts/resumen_piso.py sesiones/2026-11-13/vuelos/espejo_20261113_101500.csv

Por vuelo:
- quién sostuvo la posición (columna piso_modo: pid, kalman, apagado) y si cambió en vuelo;
- quieto (E2b, E3): qué tan lejos del despegue anduvo, según lo que mide el piso por el
  espejo (no es la verdad: la cinta en el piso manda);
- avanzando (E4, E5): a qué distancia del tag ejecutó cada uno (según la cámara), cuánto se
  salió de la línea del tramo y si se hundió al avanzar (lado y adelante a la vez lo hunden);
- qué tan bruscos fueron los mandos (rc/s, como sim/comparar_control.py) y, con el Kalman,
  la deriva que estimó (cm/s; el 11-nov medimos Tello 7 ~12 a la derecha, Tello 1 ~4).
"""
from __future__ import annotations

import argparse
import csv
import json
import math
import re
import statistics as st
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
SOSTIENE = ("HOVER", "CRUISE", "ADVANCE")


def num(x: str | None) -> float | None:
    try:
        return float(x)
    except (TypeError, ValueError):
        return None


def ajuste(clave: str, defecto: float) -> float:
    try:
        return float(json.loads((ROOT / "config" / "mission_espejo.json").read_text())[clave])
    except (OSError, KeyError, ValueError):
        return defecto


def modos(filas: list[dict], t0: float) -> str:
    """Quién sostuvo la posición y cuándo cambió."""
    if "piso_modo" in filas[0]:
        seq: list[tuple[str, float]] = []
        for f in filas:
            m = f["piso_modo"]
            if f["state"] in SOSTIENE and m and (not seq or seq[-1][0] != m):
                seq.append((m, float(f["t"]) - t0))
        if not seq:
            return "?"
        txt = seq[0][0] + "".join(f" -> {m} a los {t:.0f} s" for m, t in seq[1:])
    else:  # bitácoras de antes de piso_modo
        txt = "kalman" if any(f.get("kal_nis") for f in filas) else "pid"
    avisos = sorted({m.group(0) for f in filas for m in [re.search(r"(sostener_piso|kalman) APAGADO: [^|]*", f["reason"])] if m})
    return txt + "".join(f"\n    ({a.strip()})" for a in avisos)


def suavidad(filas: list[dict]) -> str:
    """Cuánto cambian los mandos de lado y adelante por segundo mientras sostiene."""
    s = [f for f in filas if f["state"] in SOSTIENE]
    cambio = dur = 0.0
    for a, b in zip(s, s[1:]):
        dt = float(b["t"]) - float(a["t"])
        if 0 < dt < 0.2:  # sin brincar entre tramos
            cambio += sum(abs((num(b[k]) or 0) - (num(a[k]) or 0)) for k in ("rc_lr", "rc_fb"))
            dur += dt
    if dur < 2:
        return "mandos: muy poco tiempo sosteniendo"
    tope = sum(abs(num(f["rc_lr"]) or 0) >= 20 for f in s) / len(s)
    return f"mandos: cambian {cambio / dur:.0f} rc/s, {tope:.0%} del tiempo al tope de lado"


def analizar(path: Path, alt_crucero: float, advance_fb: float) -> list[str] | None:
    try:
        filas = [f for f in csv.DictReader(path.open()) if num(f.get("t")) is not None]
    except (OSError, csv.Error):
        return None
    if not filas or "piso_der" not in filas[0]:
        return None  # no es un vuelo con espejo
    m = re.search(r"_(\d{8})_(\d{2})(\d{2})(\d{2})", path.name)
    hora = f"{m.group(2)}:{m.group(3)}:{m.group(4)}" if m else ""
    despegue = next((float(f["t"]) for f in filas if f["state"] == "TAKEOFF"), None)
    if despegue is None:
        return [f"{path.name}  {hora}  no despegó"]
    aire = float(filas[-1]["t"]) - despegue

    # avanzando o quieto: avanzando, el mando de adelante es exactamente advance_fb en ~99 % de
    # las filas; quieto, en ~1 % (el PID puede empujar adelante todo el rato, pero no siempre a 15)
    adv = [num(f["rc_fb"]) or 0 for f in filas if f["state"] == "ADVANCE"]
    avanza = bool(adv) and sum(v == advance_fb for v in adv) > 0.8 * len(adv)
    out = [f"{path.name}  {hora}  {'avanzando' if avanza else 'quieto'}, {aire:.0f} s en el aire",
           f"  control: {modos(filas, despegue)}"]

    # tags: al entrar a EXECUTE, o al aterrizar por un tag, a qué distancia estaba según la cámara
    tags = []
    for a, b in zip(filas, filas[1:]):
        m = re.match(r"tag (\d+)", b["reason"])
        if a["state"] == "APPROACH" and b["state"] in ("EXECUTE", "LANDING") and m:
            ade, der = num(b["tag_adelante"]), num(b["tag_derecha"])
            if ade is None or der is None:
                ade, der = num(a["tag_adelante"]), num(a["tag_derecha"])
            tags.append(f"{m.group(1)} a {math.hypot(ade, der):.0f} cm" if ade is not None and der is not None
                        else f"{m.group(1)}")
    if tags:
        out.append(f"  tags ejecutados (distancia al tag según la cámara): {', '.join(tags)}")

    if avanza:
        lado = [abs(v) for f in filas if f["state"] == "ADVANCE" and (v := num(f["piso_der"])) is not None]
        if lado:
            out.append(f"  de lado al avanzar: hasta {max(lado):.0f} cm fuera de la línea del tramo")
        alt = [t - 10 for f in filas if f["state"] == "ADVANCE" and (num(f["rc_fb"]) or 0) > 0
               and (t := num(f["tof"])) is not None and t > 10]
        if alt:
            aviso = "  <- se hunde al avanzar" if min(alt) < alt_crucero - 15 else ""
            out.append(f"  altura al avanzar: mínima {min(alt):.0f}, media {st.mean(alt):.0f} cm{aviso}")
    else:
        # hasta el primer tag (después se ancla en el tag y la medida ya no es desde el despegue)
        subiendo, quieto = [], []
        for f in filas:
            if f["state"] in ("APPROACH", "EXECUTE", "LANDING"):
                break
            if f["state"] in SOSTIENE and (x := num(f["piso_der"])) is not None and (y := num(f["piso_ade"])) is not None:
                (quieto if f["state"] == "ADVANCE" else subiendo).append(math.hypot(x, y))
        if subiendo:
            out.append(f"  distancia al despegue (medida con el piso): subiendo, hasta {max(subiendo):.0f} cm")
        if quieto:
            out.append(f"  esperando quieto arriba: media {st.mean(quieto):.0f}, máxima {max(quieto):.0f}, "
                       f"al final {quieto[-1]:.0f} cm")
        alt = [t - 10 for f in filas if f["state"] in ("CRUISE", "ADVANCE") and (t := num(f["tof"])) is not None and t > 10]
        if alt:
            out.append(f"  altura sosteniendo: media {st.mean(alt):.0f} cm")
    out.append("  " + suavidad(filas))

    # lo que juntó cada control para la deriva, en los últimos 5 s sosteniendo
    s = [f for f in filas if f["state"] in SOSTIENE]
    if s:
        fin = [f for f in s if float(f["t"]) > float(s[-1]["t"]) - 5]
        kd = [(num(f["kal_dder"]), num(f["kal_dade"])) for f in fin if num(f.get("kal_dder")) is not None]
        if kd:
            out.append(f"  deriva estimada por el Kalman: {st.mean(d[0] for d in kd):+.0f} lado, "
                       f"{st.mean(d[1] for d in kd):+.0f} adelante cm/s")
        ii = (num(fin[-1].get("piso_ider")), num(fin[-1].get("piso_iade")))
        con_pid = fin[-1].get("piso_modo", "pid" if not kd else "kalman") == "pid"
        if con_pid and None not in ii:
            out.append(f"  integral del PID al final: {ii[0]:+.1f} lado, {ii[1]:+.1f} adelante (rc)")
    return out


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("archivos", nargs="*", help="bitácoras .csv o carpetas (por defecto, las de hoy en logs/)")
    ap.add_argument("--fecha", default=time.strftime("%Y%m%d"), help="AAAAMMDD (por defecto hoy)")
    ap.add_argument("--ultimos", type=int, help="solo los N vuelos más recientes")
    args = ap.parse_args()

    if args.archivos:
        logs = []
        for a in map(Path, args.archivos):
            logs += sorted(a.glob("*.csv")) if a.is_dir() else [a]
    else:
        logs = sorted((ROOT / "logs").glob(f"*_{args.fecha}_*.csv"))
    logs.sort(key=lambda p: p.name)
    alt, fb = ajuste("cruise_alt_cm", 100.0), ajuste("advance_fb", 15.0)
    bloques = [b for p in logs if (b := analizar(p, alt, fb))]
    if args.ultimos:
        bloques = bloques[-args.ultimos:]
    if not bloques:
        print("no hay vuelos con la medida del piso" + ("" if args.archivos else f" del {args.fecha} en logs/")
              + " (las bitácoras de antes del 11-nov no la traen)")
        return
    print("\n\n".join("\n".join(b) for b in bloques))


if __name__ == "__main__":
    main()
