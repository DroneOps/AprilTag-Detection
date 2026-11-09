#!/usr/bin/env python3
"""Muestra una bitácora de vuelo (CSV) condensada: estado, altura, rc enviados,
actitud y las columnas de visión de cada misión. Es la forma rápida de ver qué
hizo el dron y por qué.

Uso:
    python scripts/traza_vuelo.py logs/espejo_20261109_141631.csv
    python scripts/traza_vuelo.py sesiones/2026-11-09/vuelos/espejo_20261109_141631.csv --cada 4
    python scripts/traza_vuelo.py <csv> --desde 12 --hasta 20      # solo ese tramo (s desde el inicio)
    python scripts/traza_vuelo.py <csv> --estados ADVANCE APPROACH

Columnas: t (s desde el primer registro), estado y fase, tof y h, rc enviados
(lr fb ud yaw), roll/pitch/yaw, y después las columnas propias de la misión
(objetivo, posición del tag, etc.). El motivo se imprime cuando cambia.
Recuerda: altura real = tof − 10; 'h' no es confiable (ver docs/tello.md).
"""
from __future__ import annotations

import argparse
import csv
from pathlib import Path

BASE = ["t", "state", "bat", "h", "tof", "yaw", "pitch", "roll", "temph", "rc_lr", "rc_fb", "rc_ud", "rc_yaw",
        "state_age", "video_age", "reason", "vgx", "vgy", "vgz"]


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("csv")
    ap.add_argument("--cada", type=int, default=2, help="imprimir 1 de cada N filas (la bitácora va a 20 Hz)")
    ap.add_argument("--desde", type=float, default=0.0)
    ap.add_argument("--hasta", type=float, default=1e9)
    ap.add_argument("--estados", nargs="*", help="solo estos estados (p. ej. ADVANCE APPROACH)")
    args = ap.parse_args()

    rows = list(csv.DictReader(Path(args.csv).open()))
    if not rows:
        raise SystemExit("bitácora vacía")
    extra = [c for c in rows[0] if c not in BASE and c != "fase"]
    t0, last_reason = float(rows[0]["t"]), None
    for i, r in enumerate(rows):
        t = float(r["t"]) - t0
        if not args.desde <= t <= args.hasta or (args.estados and r["state"] not in args.estados):
            continue
        changed = r["reason"] != last_reason
        if i % args.cada and not changed:
            continue
        fase = r.get("fase", "")
        vis = " ".join(f"{c}={r[c]}" for c in extra if r.get(c))
        line = (f"{t:6.1f} {r['state']:<14} {fase:<7} tof={r['tof']:>4} h={r['h']:>4} "
                f"rc=({r['rc_lr']:>3},{r['rc_fb']:>3},{r['rc_ud']:>3},{r['rc_yaw']:>3}) "
                f"roll={r['roll']:>3} pitch={r['pitch']:>3} yaw={r['yaw']:>4} {vis}")
        if changed:
            line += f"  <- {r['reason']}"
            last_reason = r["reason"]
        print(line)


if __name__ == "__main__":
    main()
