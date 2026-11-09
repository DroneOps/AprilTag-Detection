#!/usr/bin/env python3
"""Guarda una sesión de laboratorio en el repo, en sesiones/AAAA-MM-DD/, para que el
equipo la pueda revisar en GitHub sin estar en el laboratorio.

Copia las bitácoras de vuelo de esa fecha (logs/*.csv -> vuelos/), los textos de
capturas/ (calibración de rc, enlace), genera resumen.txt con resumen_vuelos.py y
agrega tus notas a notas.md. Los videos y las imágenes NO se copian.

Uso:
    python scripts/guardar_sesion.py --notas "E5 con clip nuevo: ejecutó 1 y 2, el 7 se le pasó"
    python scripts/guardar_sesion.py                    # sin notas (se pueden agregar después)
    python scripts/guardar_sesion.py --fecha 20261027   # otra fecha

Después: git add sesiones/ && git commit -m "Sesión ..." && git pull --rebase && git push
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fecha", default=time.strftime("%Y%m%d"), help="AAAAMMDD (por defecto hoy)")
    ap.add_argument("--notas", help="qué se probó, qué salió y qué sigue (se agrega a notas.md)")
    ap.add_argument("--max-mb", type=float, default=2.0, help="no copiar bitácoras más grandes que esto")
    args = ap.parse_args()

    f = args.fecha
    if len(f) != 8 or not f.isdigit():
        raise SystemExit("--fecha va como AAAAMMDD, por ejemplo 20261109")
    out = ROOT / "sesiones" / f"{f[:4]}-{f[4:6]}-{f[6:]}"
    vuelos = out / "vuelos"  # no "logs/": .gitignore ignora cualquier carpeta con ese nombre
    vuelos.mkdir(parents=True, exist_ok=True)

    copied, skipped = [], []
    for p in sorted((ROOT / "logs").glob(f"*_{f}_*.csv")):
        if p.stat().st_size > args.max_mb * 1e6:
            skipped.append(f"{p.name} ({p.stat().st_size / 1e6:.1f} MB)")
            continue
        shutil.copy2(p, vuelos / p.name)
        copied.append(p.name)
    textos = []
    for pat in (f"rc_calib_{f}_*.txt", f"resumen_{f}_*.txt"):
        for p in sorted((ROOT / "capturas").glob(pat)):
            shutil.copy2(p, out / p.name)
            textos.append(p.name)

    if copied:
        res = subprocess.run([sys.executable, str(ROOT / "scripts" / "resumen_vuelos.py"), "--fecha", f],
                             capture_output=True, text=True, cwd=ROOT)
        lines = [ln for ln in res.stdout.splitlines() if not ln.startswith("guardado en")]
        (out / "resumen.txt").write_text("\n".join(lines) + "\n")

    notas = out / "notas.md"
    if not notas.exists():
        notas.write_text(f"# Sesión {out.name}\n\nVeredictos por vuelo en `resumen.txt`; bitácoras en `vuelos/`.\n")
    if args.notas:
        with notas.open("a") as fh:
            fh.write(f"\n## {time.strftime('%H:%M')}\n\n{args.notas.strip()}\n")

    print(f"sesión guardada en {out.relative_to(ROOT)}/")
    print(f"  {len(copied)} bitácoras en vuelos/" + (f", {len(textos)} textos de capturas/" if textos else ""))
    for s in skipped:
        print(f"  omitida por tamaño: {s}")
    if not copied:
        print(f"  aviso: no hay bitácoras de {f} en logs/")
    print("Ahora: git add sesiones/ && git commit -m \"Sesión ...\" && git pull --rebase && git push")


if __name__ == "__main__":
    main()
