#!/usr/bin/env python3
"""Resumen de una sesión de pruebas: qué pasó en cada vuelo, sin abrir los CSV.

Uso:
    python scripts/resumen_vuelos.py                # vuelos de hoy
    python scripts/resumen_vuelos.py --ultimos 3    # los 3 más recientes
    python scripts/resumen_vuelos.py --fecha 20261021

Lee logs/*.csv (first_flight, mission_tags, rc_calib) y capturas/ (calibración
de rc y enlace de test_tags). Imprime un veredicto por vuelo y guarda todo en
capturas/resumen_sesion_*.txt.
"""
from __future__ import annotations

import argparse
import csv
import re
import time
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
AIR = {"HOVER", "YAW_TEST", "FLIP_CLIMB", "FLIP_TEST", "FLIP_RECOVER", "CRUISE", "ADVANCE", "APPROACH",
       "EXECUTE", "RC_ALT", "RC_STEP"}
PROBLEMS = {  # texto en el motivo -> descripción corta
    "perdido": "tag perdido", "obstaculo": "obstáculo debajo", "piso sin pedirlo": "en el piso sin pedirlo",
    "sin video": "video perdido", "telemetria perdida": "telemetría perdida", "bateria baja": "batería baja",
    "temperatura": "temperatura alta", "excepcion": "excepción en el programa", "no subio": "no despegó bien",
    "no alcanzo": "no alcanzó la altura del flip", "omitido": "flip omitido", "NO detectado": "flip no detectado",
    "incompleto": "acercamiento incompleto (por tiempo)", "no veo ningun tag": "sin tag para calibrar",
}
OK_ENDINGS = ("fin de la prueba", "sin tags al frente", "bloqueado por un tag", "aterrizar", "calibracion terminada")


def num(v, default=None):
    try:
        return float(v)
    except (TypeError, ValueError):
        return default


def alt_of(r) -> float | None:
    tof = num(r.get("tof"))
    return tof - 10 if tof is not None and 0 < tof < 400 else None  # >400: basura durante un flip


def flips(rows) -> list[dict]:
    """Flips detectados por la telemetría (inclinación >= 60° en el aire; en tierra es alguien
    levantando el dron). Durante la vuelta el tof da basura, así que la altura de antes se
    toma de 1.5–0.3 s antes y el mínimo de después desde 1 s después del pico."""
    out, last = [], -10.0
    for r in rows:
        t = num(r["t"], 0)
        tilt = max(abs(num(r.get("pitch"), 0)), abs(num(r.get("roll"), 0)))
        if tilt >= 60 and r["state"] in AIR and t - last > 3:
            before = [alt_of(x) for x in rows if alt_of(x) is not None and -1.5 <= num(x["t"]) - t <= -0.3]
            after = [alt_of(x) for x in rows if alt_of(x) is not None and 1.0 <= num(x["t"]) - t <= 5.0]
            out.append({"t": t, "antes": round(sorted(before)[len(before) // 2]) if before else None,
                        "min": min(after) if after else None, "final": after[-1] if after else None})
        if tilt >= 60:
            last = t
    return out


def in_flip(t: float, fl: list[dict]) -> bool:
    return any(-0.5 <= t - f["t"] <= 1.0 for f in fl)


def analyze(path: Path) -> list[str]:
    rows = list(csv.DictReader(path.open()))
    if not rows:
        return [f"== {path.name}: vacío"]
    kind = path.name.split("_")[0]
    trans, prev = [], None
    for r in rows:
        if (r["state"], r["reason"]) != prev:
            prev = (r["state"], r["reason"])
            trans.append((num(r["t"], 0), r["state"], r["reason"]))
    states = {s for _, s, _ in trans}
    lines = [f"== {path.name}  ({kind})"]
    bats = [num(r["bat"]) for r in rows if num(r.get("bat"))]
    temps = [num(r["temph"]) for r in rows if num(r.get("temph"))]

    if "TAKEOFF" not in states:
        reasons = [rs for _, s, rs in trans if rs.startswith("NO despega")]
        lines.append(f"   NO DESPEGÓ: {reasons[-1] if reasons else trans[-1][2]}")
        lines.append(f"   batería {bats[0] if bats else '?'}%, temperatura {temps[-1] if temps else '?'} C")
        lines.append("   VEREDICTO: sin vuelo")
        return lines

    t_take = next(t for t, s, _ in trans if s == "TAKEOFF")
    t_end = next((t for t, s, _ in trans if s in ("DONE", "KILLED")), num(rows[-1]["t"]))
    lines.append(f"   vuelo {t_end - t_take:.0f} s | batería {bats[0]:.0f}% -> {bats[-1]:.0f}% | "
                 f"temp max {max(temps):.0f} C")
    takeoff = next((rs for _, s, rs in trans if s == "HOVER" and "en el aire" in rs), None)
    if takeoff:
        lines.append(f"   despegue: {takeoff}")
    fl = flips(rows)
    air = [alt_of(r) for r in rows if r["state"] in AIR and alt_of(r) is not None and not in_flip(num(r["t"]), fl)]
    if air:
        lines.append(f"   altura en vuelo: min {min(air):.0f} cm, max {max(air):.0f} cm")

    for f in fl:
        safe = f["min"] is not None and f["min"] >= 30
        lines.append(f"   flip a los {f['t']:.1f} s: antes {f['antes']} cm, minimo despues {f['min']} cm, "
                     f"a los 5 s {f['final']} cm -> {'OK' if safe else 'PELIGRO: quedo muy bajo'}")
    for _, s, rs in trans:
        if s in ("FLIP_RECOVER", "HOVER") and ("flip" in rs or "altura recuperada" in rs):
            lines.append(f"   {rs}")
    for _, s, rs in trans:
        if s == "EXECUTE" and rs.startswith("tag"):
            lines.append(f"   EJECUTÓ {rs}")
    for _, s, rs in trans:
        if s == "APPROACH" and rs.startswith("tag"):
            lines.append(f"   vio {rs}")

    problems = []
    for _, s, rs in trans:
        for key, desc in PROBLEMS.items():
            if key in rs and desc not in problems:
                problems.append(desc)
    manual = [rs for _, s, rs in trans if rs.startswith("PARO")]
    end_state, end_reason = trans[-1][1], trans[-1][2]
    lines.append(f"   final: {end_state} — {end_reason}")
    if problems:
        lines.append(f"   problemas: {', '.join(problems)}")
    if manual:
        lines.append(f"   detenido a mano: {manual[0]}")
    bad_flip = any(f["min"] is not None and f["min"] < 30 for f in fl)
    serious = [p for p in problems if p not in ("acercamiento incompleto (por tiempo)", "flip omitido")]
    if bad_flip or serious or end_state == "KILLED":
        verdict = "REVISAR"
    elif manual:
        verdict = "OK hasta que se detuvo a mano"
    elif any(k in end_reason for k in OK_ENDINGS):
        verdict = "OK"
    else:
        verdict = "REVISAR"
    lines.append(f"   VEREDICTO: {verdict}")
    return lines


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--fecha", default=time.strftime("%Y%m%d"), help="AAAAMMDD (por defecto hoy)")
    ap.add_argument("--ultimos", type=int, help="solo los N vuelos más recientes")
    args = ap.parse_args()

    logs = sorted((ROOT / "logs").glob("*.csv"), key=lambda p: p.stat().st_mtime)
    if args.ultimos:
        logs = logs[-args.ultimos:]
    else:
        logs = [p for p in logs if re.search(rf"_{args.fecha}_", p.name)]
    out = [f"Resumen de sesión — {time.strftime('%Y-%m-%d %H:%M')} — {len(logs)} bitácoras", ""]
    for p in logs:
        out += analyze(p) + [""]

    caps = ROOT / "capturas"
    stamp = args.fecha if not args.ultimos else ""
    for f in sorted(caps.glob(f"rc_calib_{stamp}*.txt")):
        out += [f"== {f.name}", f.read_text(), ""]
    links = []
    for f in sorted(caps.glob(f"resumen_{stamp}*.txt")):
        text = f.read_text()
        link = [ln for ln in text.splitlines() if ln.startswith("enlace:")]
        if link:
            links.append(f"   {f.name}: {link[0]}")
    if links:
        out += ["== enlace (test_tags.py)", *links, ""]

    text = "\n".join(out)
    print(text)
    dest = caps / time.strftime("resumen_sesion_%Y%m%d_%H%M%S.txt")
    caps.mkdir(exist_ok=True)
    dest.write_text(text + "\n")
    print(f"guardado en {dest}")


if __name__ == "__main__":
    main()
