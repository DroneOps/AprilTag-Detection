#!/usr/bin/env python3
"""Menú del laboratorio: volar, guardar lo que pasó y subirlo a GitHub con un solo comando.

    python lab.py              # el menú
    python lab.py --practica   # igual, pero no vuela ni sube nada: solo muestra qué haría

Qué hace por ti:
- detecta qué Tello es por el nombre de su WiFi (config/drones.json), para no equivocarse
  de --dron;
- antes de volar te recuerda el montaje, la seguridad y cuándo "aprueba" la prueba;
- le pone nombre al video solo (videos/e5_dron7_2.mp4);
- al aterrizar te pregunta qué viste, guarda la sesión y la sube a GitHub (si no hay
  internet, la sube después);
- cambia ajustes del JSON sin que tengas que editarlo a mano, y te deja probarlos en el
  simulador.

Cada opción muestra el comando que corre por dentro ("→ python scripts/..."): son los mismos
que vienen en docs/laboratorio.md, para que con el uso los vayas aprendiendo.
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import time
from datetime import date
from pathlib import Path

ROOT = Path(__file__).resolve().parent
PY = sys.executable
PRACTICA = "--practica" in sys.argv
DRONES_JSON = ROOT / "config" / "drones.json"

# ---------------------------------------------------------------- colores en la terminal
NEGRITA, AZUL, VERDE, AMARILLO, ROJO, GRIS, FIN = ("\033[1m", "\033[94m", "\033[92m", "\033[93m", "\033[91m",
                                                   "\033[90m", "\033[0m")


def titulo(txt: str) -> None:
    print(f"\n{NEGRITA}{AZUL}=== {txt} ==={FIN}", flush=True)


def aviso(txt: str) -> None:
    print(f"{AMARILLO}{txt}{FIN}")


def error(txt: str) -> None:
    print(f"{ROJO}{txt}{FIN}")


def bien(txt: str) -> None:
    print(f"{VERDE}{txt}{FIN}")


def preguntar(txt: str, defecto: str = "") -> str:
    try:
        r = input(f"{NEGRITA}{txt}{FIN} ").strip()
    except EOFError:
        r = ""
    return r or defecto


def si(txt: str) -> bool:
    """Pregunta de sí o no; Enter = sí."""
    return preguntar(f"{txt} [Enter = sí, n = no]").lower() not in ("n", "no")


# ---------------------------------------------------------------- correr comandos
def correr(cmd: list[str], vuela: bool = False, capturar: bool = False) -> subprocess.CompletedProcess | None:
    """Corre un comando mostrándolo antes. En --practica no corre lo que vuela ni lo que sube."""
    visible = " ".join(("python" if c == PY else c) if " " not in c else f'"{c}"' for c in cmd)
    print(f"{GRIS}→ {visible}{FIN}", flush=True)
    if PRACTICA and (vuela or cmd[:2] in (["git", "commit"], ["git", "push"], ["git", "add"])):
        print(f"{GRIS}  (modo práctica: no se corre){FIN}")
        return None
    return subprocess.run(cmd, cwd=ROOT, text=True, capture_output=capturar)


def git(*args: str) -> str:
    """Un comando de git que solo consulta (no cambia nada); devuelve lo que imprime."""
    r = subprocess.run(["git", *args], cwd=ROOT, text=True, capture_output=True)
    return r.stdout.strip()


def subir(rutas: list[str], mensaje: str) -> None:
    """git add + commit + pull --rebase + push, como pide CLAUDE.md. Sin internet, se queda en la
    laptop y se sube después (opción u, o al abrir el menú)."""
    correr(["git", "add", *rutas])
    if not PRACTICA and not git("diff", "--cached", "--name-only"):
        print("No hay nada nuevo que subir.")
        return
    correr(["git", "commit", "-q", "-m", mensaje])
    if PRACTICA:
        return
    r = correr(["git", "pull", "-q", "--rebase", "--autostash"], capturar=True)
    if r.returncode != 0:
        error("No se pudo traer lo nuevo de GitHub (¿sin internet o hay un conflicto?).")
        print(r.stderr.strip()[:400])
        aviso("Quedó guardado en la laptop. Avísale a Fernando si dice 'conflict'.")
        return
    r = correr(["git", "push", "-q"], capturar=True)
    if r.returncode == 0:
        bien("Subido a GitHub.")
    else:
        aviso("Sin internet o GitHub no responde: quedó guardado en la laptop. Se sube después (opción u).")


def pendiente_de_subir() -> int:
    """Cuántos commits hay en la laptop que todavía no están en GitHub."""
    n = git("rev-list", "--count", "@{u}..HEAD")
    return int(n) if n.isdigit() else 0


# ---------------------------------------------------------------- qué dron es
def wifi_actual() -> str | None:
    """Nombre de la red WiFi a la que está conectada la laptop (el Tello crea TELLO-XXXXXX)."""
    if shutil.which("nmcli"):
        r = subprocess.run(["nmcli", "-t", "-f", "active,ssid", "dev", "wifi"], text=True, capture_output=True)
        for linea in r.stdout.splitlines():
            if linea.startswith("yes:"):
                return linea[4:]
    if shutil.which("iwgetid"):
        r = subprocess.run(["iwgetid", "-r"], text=True, capture_output=True)
        return r.stdout.strip() or None
    return None


def drones_conocidos() -> dict[str, str]:
    try:
        return {k: v for k, v in json.loads(DRONES_JSON.read_text()).items() if not k.startswith("_")}
    except (OSError, ValueError):
        return {}


def recordar_dron(ssid: str, numero: str) -> None:
    datos = {"_nota": "Qué número es cada Tello según el nombre de su WiFi; lo llena lab.py"}
    datos.update(drones_conocidos())
    datos[ssid] = numero
    if not PRACTICA:
        DRONES_JSON.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n")
    subir(["config/drones.json"], f"Laboratorio: {ssid} es el Tello {numero}")


def detectar_dron() -> tuple[str | None, str | None]:
    """(número del dron, WiFi). Si es un Tello nuevo, pregunta qué número es y lo recuerda."""
    ssid = wifi_actual()
    if not ssid or not ssid.upper().startswith("TELLO"):
        return None, ssid
    numero = drones_conocidos().get(ssid)
    if numero is None:
        aviso(f"Estás conectado a {ssid}, que no conozco.")
        numero = preguntar("¿Qué número de Tello es? (el que tiene escrito, p. ej. 1 o 7):")
        if numero:
            recordar_dron(ssid, numero)
    return numero or None, ssid


# ---------------------------------------------------------------- las pruebas (docs/laboratorio.md)
SEGURIDAD = [
    "Alguien en el teclado con la VENTANA DEL DRON enfocada:",
    "   ESPACIO = aterrizar YA     k = apagar motores (cae; SOLO si va hacia una persona)",
    "Temperatura abajo de ~70 °C antes de despegar (arriba de 80 no despega).",
]

PRUEBAS = [
    {"clave": "estacionario", "nombre": "Revisar el dron: estacionario", "script": "scripts/principales/first_flight.py",
     "args": [], "dron": False,
     "antes": ["Las 4 hélices bien (ninguna astillada, doblada o floja).",
               "Si se cayó o se porta raro: calibrar el IMU y el centro de gravedad en la app Tello.",
               "Sin tags debajo."],
     "aprueba": "En los 10 s quieto no se mueve más de ~30 cm ni sube o baja más de ~10 cm."},
    {"clave": "e1", "nombre": "E1: el espejo con el dron en la mano (no vuela)", "script": "scripts/principales/test_tags.py",
     "args": ["--source", "tello", "--espejo", "--tag-cm", "{tag_cm}"], "dron": False, "vuela": False,
     "antes": ["Sostén el dron a ~80 cm sobre un tag. Sal con q.",
               "Sirve para revisar que vea los tags y que 'ADELANTE' apunte a la nariz.",
               "La inclinación que imprime es solo de referencia: la buena se mide en vuelo (opción i)."],
     "aprueba": "Detecta el tag, la altura se parece a la cinta métrica (±5 cm) y 'ADELANTE' apunta a la nariz."},
    {"clave": "e2b", "nombre": "E2b: quieto sobre la cinta", "script": "scripts/principales/mision_espejo.py",
     "args": ["--quieto"], "dron": True,
     "antes": ["Marca el despegue con cinta. NINGÚN tag a menos de ~1 m.",
               "Sube a 100 cm y espera ~20 s."],
     "aprueba": "No se va más de ~20–30 cm de la cinta. Fíjate también si quedó adelante de la cinta."},
    {"clave": "e3", "nombre": "E3: tag debajo, sin avanzar", "script": "scripts/principales/mision_espejo.py",
     "args": ["--quieto"], "dron": True,
     "antes": ["Tag 9 (pausa) en el piso, justo debajo del despegue o un poco atrás."],
     "aprueba": "Se coloca encima del tag, hace la pausa de 5 s y aterriza."},
    {"clave": "e4", "nombre": "E4: un tag adelante", "script": "scripts/principales/mision_espejo.py", "args": [], "dron": True,
     "antes": ["Tag 2 en el piso ~1 m adelante. Lado izquierdo libre."],
     "aprueba": "Avanza, se pone ENCIMA del tag (míralo de lado), gira a la izquierda, avanza y aterriza."},
    {"clave": "e5", "nombre": "E5: circuito 1 → 2 → 7", "script": "scripts/principales/mision_espejo.py", "args": [],
     "dron": True,
     "antes": ["Tag 1 a 80 cm al frente; tag 2 a 70 cm a la derecha del 1; tag 7 a 70 cm adelante del 2."],
     "aprueba": "Ejecuta 1, 2 y 7 quedando ENCIMA de cada uno (míralo de lado)."},
    {"clave": "e6", "nombre": "E6: flip", "script": "scripts/principales/mision_espejo.py", "args": [], "dron": True,
     "antes": ["Batería de 70 % o más y ~1.7 m libres hacia arriba.", "Solo con el clip firme.",
               "Tag 4 a ~1 m adelante; luego el 8."],
     "aprueba": "Hace el flip, recupera la altura y el espejo no se movió (si se movió: repetir E1)."},
    {"clave": "e7", "nombre": "E7: ensayo de competencia", "script": "scripts/principales/mision_espejo.py", "args": [],
     "dron": True,
     "antes": ["Varios tags en orden al azar, a 0.7–1.5 m entre ellos (o usa una pista: python sim/pista.py 4).",
               "Incluye dos tags con el mismo número y un 3 u 8 que lo regrese a un tag ya hecho.",
               "3 intentos cronometrados, como en la competencia."],
     "aprueba": "Cuenta cuántos tags ejecutó bien en orden: es su puntaje."},
    {"clave": "intento", "nombre": "Competencia: un intento", "script": "scripts/principales/mision_espejo.py", "args": [],
     "dron": True,
     "antes": ["Ajustes revisados con lo que dijeron los jueces (docs/hoja_competencia.md).",
               "Batería al 100 % y temperatura abajo de 70 °C. Hélices bien y clip firme.",
               "Dron sobre el despegue, con la nariz hacia el primer tramo."],
     "aprueba": "Cuenta los tags que ejecutó bien en orden: es el puntaje del intento."},
]


def tag_cm() -> str:
    """El tamaño de tag que usa la misión (config/mission_tags.json), para E1."""
    return f"{json.loads((ROOT / 'config' / 'mission_tags.json').read_text()).get('tag_cm', 8):g}"


VIDEOS = ROOT / "videos"  # los videos de vuelo (no van a GitHub: pesan mucho)


def nombre_video(clave: str, dron: str | None) -> str:
    """videos/e5_dron7_1.mp4, videos/e5_dron7_2.mp4, ... (el primero que no exista)."""
    base, k = f"{clave}_dron{dron or 'X'}", 1
    while (VIDEOS / f"{base}_{k}.mp4").exists():
        k += 1
    return f"videos/{base}_{k}.mp4"


def volar(p: dict, dron: str | None) -> str | None:
    """Una prueba completa: montaje, vuelo, resumen, notas, guardar y subir. Devuelve el dron."""
    titulo(p["nombre"])
    vuela = p.get("vuela", True)
    print(f"{NEGRITA}Antes de empezar:{FIN}")
    for linea in p["antes"]:
        print(f"  • {linea}")
    print(f"{NEGRITA}Aprueba si:{FIN} {p['aprueba']}")
    if vuela:
        print()
        for linea in SEGURIDAD:
            aviso(linea)
    if p["dron"] and not dron:
        dron = preguntar("¿Qué número de Tello vas a volar? (1 o 7):") or None
    cmd = [PY, p["script"], *(tag_cm() if a == "{tag_cm}" else a for a in p["args"])]
    if p["dron"] and dron:
        if (ROOT / "config" / f"mision_dron{dron}.json").exists():
            cmd += ["--dron", dron]
        else:
            aviso(f"No hay config/mision_dron{dron}.json: vuela sin ajustes propios de ese dron.")
    video = nombre_video(p["clave"], dron)
    cmd += ["--record", video]
    print()
    if not si("¿Listo?"):
        return dron
    inicio = time.time()
    correr(cmd, vuela=True)
    if PRACTICA:
        print(f"{GRIS}(en el laboratorio aquí volaría y luego te mostraría el resumen){FIN}")
    elif vuela and _hay_bitacora_nueva(inicio):
        ver_ultimo_vuelo(p["script"].endswith("mision_espejo.py"))
    print()
    notas = preguntar("¿Qué viste? Cuenta qué hizo bien y qué hizo mal (Enter si nada):")
    texto = f"{p['nombre']}, Tello {dron or '?'} (video {video})" + (f": {notas}" if notas else "")
    if si("¿Guardo la sesión y la subo a GitHub?"):
        guardar_y_subir(texto, f"Sesión: {p['clave'].upper()} Tello {dron or '?'}" + (f": {notas[:60]}" if notas else ""))
    return dron


def _hay_bitacora_nueva(desde: float) -> bool:
    return any(f.stat().st_mtime >= desde for f in (ROOT / "logs").glob("*.csv")) if (ROOT / "logs").exists() else False


def guardar_y_subir(notas: str, mensaje: str) -> None:
    correr([PY, "scripts/documentar/guardar_sesion.py", "--notas", notas], vuela=PRACTICA)
    subir(["sesiones/"], mensaje)


def ver_ultimo_vuelo(espejo: bool = True) -> None:
    titulo("Cómo salió el último vuelo")
    correr([PY, "scripts/documentar/resumen_vuelos.py", "--ultimos", "1"])
    con_espejo = sorted((ROOT / "logs").glob("espejo_*.csv"), key=lambda p: p.stat().st_mtime)
    if espejo and con_espejo:
        correr([PY, "scripts/documentar/resumen_piso.py", str(con_espejo[-1].relative_to(ROOT))])


# ---------------------------------------------------------------- cambiar un ajuste
# (archivo, clave, para qué sirve, tipo, mínimo, máximo)
AJUSTES = [
    ("config/mission_espejo.json", "advance_timeout_s",
     "Segundos que avanza buscando el siguiente tag antes de aterrizar. Súbelo si los tags están más lejos.",
     float, 5, 40),
    ("config/mission_espejo.json", "advance_fb",
     "Qué tan rápido avanza buscando (rc). Más rápido llega antes, pero se puede pasar del tag.", int, 10, 30),
    ("config/mission_espejo.json", "cruise_alt_cm",
     "Altura de vuelo (cm). Más alto ve más piso, pero los tags se ven más chicos.", int, 70, 150),
    ("config/mission_tags.json", "tag_cm",
     "Lado del tag impreso, en cm (el cuadro negro). Si en la competencia son de otro tamaño, cámbialo.",
     float, 2, 30),
    ("config/mission_espejo.json", "vista_adelante_deg",
     "Inclinación del espejo hacia adelante (°). Se mide en vuelo con la opción i; cambia con cada clip.",
     float, -30, 30),
    ("config/mission_espejo.json", "vista_lado_deg", "Inclinación del espejo de lado (°). Igual que la anterior.",
     float, -30, 30),
    ("config/mission_espejo.json", "ignorar_inicio",
     "true = no ejecutar el tag que ve al despegar (el de inicio). En las pruebas va en false.", bool, None, None),
    ("config/mission_espejo.json", "sostener_piso",
     "true = se sostiene mirando el piso. false si el piso es liso (sin textura) y el dron se porta raro.",
     bool, None, None),
    ("config/mission_espejo.json", "advance_lr",
     "Empujón de lado fijo al avanzar (rc; negativo = izquierda), si siempre se va de un lado.", int, -20, 20),
    ("config/flight.json", "flip_min_alt_cm",
     "Altura a la que sube antes de un flip (cm). Bájala si el techo o la red están bajos: techo − 40, "
     "nunca menos de 110 (tras el flip cae ~45 cm).", int, 110, 160),
    ("config/mission_espejo.json", "mismo_tag_cm",
     "La mitad de la distancia más corta entre dos tags (cm). Bájalo si hay tags a menos de 70 cm.",
     float, 15, 60),
    ("config/mission_tags.json", "mission_max_s",
     "Tiempo máximo en el aire por intento (s); al pasarlo aterriza. ~30 s por tag: súbelo si hay más de 7.",
     int, 60, 600),
]


def leer_valor(tipo, minimo, maximo, actual):
    txt = preguntar(f"Nuevo valor (ahora: {json.dumps(actual)}; Enter = no cambiar):")
    if not txt:
        return None
    try:
        if tipo is bool:
            if txt.lower() not in ("true", "false", "si", "sí", "no"):
                raise ValueError
            return txt.lower() in ("true", "si", "sí")
        v = tipo(txt)
        if isinstance(actual, int) and not isinstance(actual, bool) and float(v).is_integer():
            v = int(v)  # 20, no 20.0, si el valor era entero
    except ValueError:
        error("Ese valor no sirve." + (" Escribe true o false." if tipo is bool else " Escribe un número."))
        return None
    if minimo is not None and not minimo <= v <= maximo:
        error(f"Fuera de lo razonable: debe estar entre {minimo} y {maximo}. Si de verdad lo necesitas, pregúntale a Fernando.")
        return None
    return v


def cambiar_ajuste() -> None:
    titulo("Cambiar un ajuste")
    for i, (archivo, clave, para, *_) in enumerate(AJUSTES, 1):
        actual = json.loads((ROOT / archivo).read_text()).get(clave)
        print(f" {i:2d}) {clave} = {NEGRITA}{json.dumps(actual)}{FIN}   {GRIS}({archivo}){FIN}")
    n = preguntar("¿Cuál? (número, Enter = regresar):")
    if not n.isdigit() or not 1 <= int(n) <= len(AJUSTES):
        return
    archivo, clave, para, tipo, minimo, maximo = AJUSTES[int(n) - 1]
    ruta = ROOT / archivo
    datos = json.loads(ruta.read_text())
    print(f"\n{NEGRITA}{clave}{FIN}: {para}")
    nuevo = leer_valor(tipo, minimo, maximo, datos.get(clave))
    if nuevo is None or nuevo == datos.get(clave):
        return
    motivo = preguntar("¿Por qué lo cambias? (queda en GitHub):") or "sin motivo escrito"
    viejo = datos.get(clave)
    datos[clave] = nuevo
    if PRACTICA:
        print(f"{GRIS}(modo práctica: no se escribe {archivo}){FIN}")
    else:
        ruta.write_text(json.dumps(datos, indent=2, ensure_ascii=False) + "\n")
        bien(f"{clave}: {json.dumps(viejo)} → {json.dumps(nuevo)} en {archivo}")
    subir([archivo], f"Ajuste: {clave} {json.dumps(viejo)} -> {json.dumps(nuevo)} ({motivo})")
    if si("¿Lo pruebo en el simulador antes de volar? (~1 min, circuito 1 → 2 → 7)"):
        simular("espejo_circuito", [])


# ---------------------------------------------------------------- inclinación del espejo
def medir_inclinacion() -> None:
    titulo("Medir la inclinación del espejo con los videos de vuelo")
    videos = sorted((p for p in VIDEOS.glob("*.mp4") if p.name.split("_")[0] in ("e4", "e5", "e6", "e7", "intento")),
                    key=lambda p: p.stat().st_mtime)[-3:]
    if not videos:
        aviso("No hay videos de E4, E5, E6, E7 o de un intento. Vuela uno de esos primero.")
        return
    print("Uso los últimos: " + ", ".join(v.name for v in videos) + " (tarda ~1 min por video)")
    correr([PY, "scripts/documentar/inclinacion_vuelo.py", *[str(v.relative_to(ROOT)) for v in videos]])
    print("Si los números son distintos a los del JSON por más de ~2°, cámbialos con la opción c.")


# ---------------------------------------------------------------- simulador
def simular(escenario: str, extra: list[str]) -> None:
    r = correr([PY, "sim/sim_world.py", escenario, *extra], capturar=True)
    if r is None:
        return
    resumen = False  # lo de "=====" en adelante: resultado, qué tan encima quedó y cada estado
    for linea in r.stdout.splitlines():
        resumen = resumen or linea.startswith("=====")
        if resumen or linea.startswith("[pista]") or linea.startswith("[sim] "):
            print(linea[:200])
    if r.returncode != 0:
        error(r.stderr.strip()[-400:])


def practicar() -> None:
    titulo("Practicar en el simulador (no hace falta el dron)")
    print(" 1) Circuito 1 → 2 → 7          (~1 min)")
    print(" 2) Pista al azar de competencia (~2–3 min)")
    print(" 3) Quieto sobre el despegue     (~40 s)")
    print(" 4) Otro escenario (por nombre; los retos de docs/aprende/ dicen cuál)")
    op = preguntar("¿Cuál?")
    esc = {"1": "espejo_circuito", "2": "espejo_competencia", "3": "espejo_estacionario"}.get(op)
    if op == "4":
        esc = preguntar("Nombre del escenario (p. ej. espejo_lejos):")
    if not esc:
        return
    extra = []
    if esc == "espejo_competencia":
        extra += ["--semilla", preguntar("¿Qué número de pista? (cualquier número):", "1")]
    d = preguntar("¿Qué dron simulado? (Enter = uno sano, 1 o 7 = con la deriva de ese dron):")
    if d in ("1", "7"):
        extra += ["--dron", d]
    cambios = preguntar("¿Cambiar ajustes solo en esta simulación? (p. ej. advance_fb=20 tag_cm=15; "
                        "Enter = no; el JSON no cambia):")
    for kv in cambios.split():
        if "=" not in kv:
            error(f"'{kv}' no sirve: escribe clave=valor, p. ej. advance_fb=20")
            return
        extra += ["--set", kv]
    if si("¿Grabo un video para verlo después?"):
        carpeta = f"sim/logs/videos_practica/{esc}_{int(time.time())}"
        correr([PY, "sim/grabar.py", esc, "--salida", carpeta, *extra])
        correr([PY, "sim/componer.py", carpeta, "--salida", carpeta, "--sin-gif"])
        bien(f"Video: {carpeta}.mp4")
    else:
        simular(esc, extra)


# ---------------------------------------------------------------- terminar el día
MESES = ["ene", "feb", "mar", "abr", "may", "jun", "jul", "ago", "sep", "oct", "nov", "dic"]


def terminar_dia() -> None:
    titulo("Terminar el día")
    correr([PY, "scripts/documentar/resumen_vuelos.py"])
    print("\nContesta en pocas palabras; queda en docs/bitacora.md para que el equipo lo lea en GitHub.")
    tema = preguntar("Título del día (p. ej. 'E5 con el Tello 1 y clip nuevo'):")
    if not tema:
        aviso("Sin título no escribo la bitácora. Puedes volver a esta opción.")
        return
    probo = preguntar("¿Qué se probó?")
    bueno = preguntar("¿Qué salió bien?")
    malo = preguntar("¿Qué salió mal o raro?")
    sigue = preguntar("¿Qué sigue?")
    hoy = date.today()
    quien = git("config", "user.name") or "el equipo"
    entrada = (f"## {hoy.day}-{MESES[hoy.month - 1]} — {tema}\n\n"
               f"Escrito con `lab.py` por {quien}. Sesión: `sesiones/{hoy.isoformat()}/`.\n\n"
               f"- **Qué se probó:** {probo or '—'}\n- **Qué salió bien:** {bueno or '—'}\n"
               f"- **Qué salió mal o raro:** {malo or '—'}\n- **Qué sigue:** {sigue or '—'}\n\n")
    ruta = ROOT / "docs" / "bitacora.md"
    texto = ruta.read_text()
    i = texto.find("\n## ", texto.find("## Pendiente ahora") + 1)  # la primera entrada, después de "Pendiente"
    if i < 0:
        error("No encontré dónde va la entrada en docs/bitacora.md; pásale el texto a Fernando:")
        print(entrada)
        return
    if PRACTICA:
        print(f"{GRIS}(modo práctica: no se escribe){FIN}\n{entrada}")
    else:
        ruta.write_text(texto[:i + 1] + entrada + texto[i + 1:])
        bien("Entrada agregada a docs/bitacora.md.")
    correr([PY, "scripts/documentar/guardar_sesion.py"], vuela=PRACTICA)
    subir(["sesiones/", "docs/bitacora.md"], f"Bitácora: {tema}")
    aviso("Al terminar: apaga los drones, pon a cargar las baterías y deja el espejo limpio.")


# ---------------------------------------------------------------- el menú
def revisar_repo() -> None:
    """Al abrir: estar en main y con lo último de GitHub (CLAUDE.md: git pull --rebase)."""
    rama = git("rev-parse", "--abbrev-ref", "HEAD")
    if rama != "main":
        aviso(f"Estás en la rama '{rama}', no en 'main'. Casi siempre se vuela desde main.")
        if si("¿Me cambio a main?"):
            correr(["git", "checkout", "main"])
    print("Trayendo lo último de GitHub...")
    r = correr(["git", "pull", "-q", "--rebase", "--autostash"], capturar=True)
    if r is not None and r.returncode != 0:
        aviso("No se pudo (¿sin internet?). Sigo con lo que hay en la laptop.")
    if pendiente_de_subir() and not PRACTICA:
        aviso(f"Hay {pendiente_de_subir()} cambio(s) guardados en la laptop que no están en GitHub.")
        if si("¿Los subo ahora?"):
            subir_pendiente()


def subir_pendiente() -> None:
    if not pendiente_de_subir():
        bien("No hay nada pendiente: todo está en GitHub.")
        return
    r = correr(["git", "pull", "-q", "--rebase", "--autostash"], capturar=True)
    r = correr(["git", "push", "-q"], capturar=True)
    if r is not None and r.returncode == 0:
        bien("Subido a GitHub.")
    elif r is not None:
        aviso("Todavía no se pudo (¿sin internet?).")


def menu() -> None:
    titulo("Laboratorio de drones" + ("  (MODO PRÁCTICA: no vuela ni sube nada)" if PRACTICA else ""))
    revisar_repo()
    dron, ssid = detectar_dron()
    while True:
        print()
        estado = f"Tello {dron}" if dron else "sin dron elegido"
        wifi = f"WiFi: {ssid}" if ssid else "WiFi: ninguno"
        if ssid and not ssid.upper().startswith("TELLO"):
            wifi += f"  {AMARILLO}(conéctate al WiFi TELLO-... del dron para volar){FIN}"
        print(f"{NEGRITA}Dron:{FIN} {estado}    {wifi}    {GRIS}rama {git('rev-parse', '--abbrev-ref', 'HEAD')}{FIN}")
        for i, p in enumerate(PRUEBAS, 1):
            print(f" {i}) {p['nombre']}")
        print(" v) Ver cómo salió el último vuelo")
        print(" i) Medir la inclinación del espejo (con los últimos videos de vuelo)")
        print(" c) Cambiar un ajuste")
        print(" d) Cambiar de dron")
        print(" s) Practicar en el simulador (sin dron)")
        print(" u) Subir lo pendiente a GitHub")
        print(" t) Terminar el día")
        print(" q) Salir")
        op = preguntar(">").lower()
        try:
            if op.isdigit() and 1 <= int(op) <= len(PRUEBAS):
                dron = volar(PRUEBAS[int(op) - 1], dron) or dron
            elif op == "v":
                ver_ultimo_vuelo()
            elif op == "i":
                medir_inclinacion()
            elif op == "c":
                cambiar_ajuste()
            elif op == "d":
                d, ssid = detectar_dron()
                dron = d or preguntar("¿Qué número de Tello? (1 o 7):") or dron
            elif op == "s":
                practicar()
            elif op == "u":
                subir_pendiente()
            elif op == "t":
                terminar_dia()
            elif op in ("q", "salir"):
                if pendiente_de_subir() and not PRACTICA:
                    aviso("Ojo: hay cambios sin subir a GitHub (opción u).")
                return
        except KeyboardInterrupt:
            print()
            aviso("Cancelado; regreso al menú.")


if __name__ == "__main__":
    try:
        menu()
    except KeyboardInterrupt:
        print()
