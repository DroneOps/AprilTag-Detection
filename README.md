# AprilTag-Detection

Dron autónomo para la categoría **Drones autónomos – Detector de AprilTags** del
**Autonomous Mechatronics Grand Prix 2026** (TECH FEST 2026, 5 de diciembre, Campus
Hidalgo). Un DJI Tello recorre una pista, detecta etiquetas AprilTag **tag25h9 en el piso**
y ejecuta la acción de cada una (girar, flip, subir, aterrizar...). Todo el procesamiento
corre en una laptop conectada al Tello por WiFi.

## Estado (2-nov)

- **Funciona en simulación:**
  - detección (ID 1–10, 100 % en la prueba sintética);
  - misiones con tags en el piso, con cámara al frente o con espejo;
  - flips seguros, sostener altura y aterrizaje si el dron no obedece;
  - ~40 escenarios.
- **En vuelo real:**
  - el flip está aprobado;
  - la misión de piso está a medias;
  - el dron necesita revisión (IMU y hélices) antes de seguir probando.
- **Siguiente:** revisar el dron, repetir las pruebas de piso F1 y F3, e imprimir los
  clips de espejo.

El detalle está en [`docs/bitacora.md`](docs/bitacora.md).

## Inicio rápido

### 1. Instalar

Python 3.12. En Linux:

```bash
git clone <url-del-repo> AprilTag-Detection
```
```bash
cd AprilTag-Detection
```
```bash
python3 -m venv .venv
```
```bash
source .venv/bin/activate
```
```bash
pip install -r requirements.txt
```

### 2. Probar sin dron

```bash
python scripts/test_tags.py --selftest
```

Debe decir `selftest: 1440/1440 correctos (100.0 %)`. Con la webcam y un tag impreso
(`tags/tags_8cm.pdf`, al 100 % sin "ajustar a la página"):

```bash
python scripts/test_tags.py --source 0 --tag-cm 8
```

Una misión completa en el simulador (sin ventana: imprime lo que hace y tarda ~40 s):

```bash
python sim/sim_world.py piso_uno
```

### 3. Con el Tello

1. Enciende el Tello y conecta la laptop a su red WiFi (`TELLO-XXXXXX`).
2. Sin volar, con el dron en la mano:
   ```bash
   python scripts/test_tags.py --source tello --tag-cm 8
   ```
3. Antes de volar lee [`docs/laboratorio.md`](docs/laboratorio.md) (seguridad y "Revisar el
   dron"). El primer vuelo es solo despegar, quedarse quieto 10 s y aterrizar:
   ```bash
   python scripts/first_flight.py --record estacionario.mp4
   ```

**Teclas en todos los programas que vuelan** (con la ventana enfocada):

| Tecla | Qué hace |
|---|---|
| `t` | despegar (solo si el chequeo previo está en verde) |
| `ESPACIO`, `ENTER`, `l`, `ESC` o clic en la barra roja | **PARO**: aterrizaje forzoso |
| `k` | **mata motores**: el dron cae. Solo si va hacia una persona |
| `q` | salir (en el aire equivale a PARO) |

## Qué hay en el repo

```
scripts/
  test_tags.py          visión: detector, pose (PnP) y prueba de detección sin volar
  first_flight.py       vuelo base: estados, seguridad, HMI y bitácora; prueba de flip y giro
  mission_tags.py       misión base: acciones de cada tag, flip seguro, sostener altura
  mision_piso.py        MISIÓN PRINCIPAL: tags en el piso con la cámara al frente
  mision_espejo.py      tags en el piso viendo hacia abajo con un espejo
  calibrate_camera.py   calibración de la cámara con tablero de ajedrez
  rc_calib.py           mide la velocidad real del dron según el rc
  resumen_vuelos.py     veredicto de cada vuelo de la sesión, leyendo logs/
  make_tags.py          PDF de los tags 1–10 al tamaño que quieras
sim/
  sim_world.py          simulador 3D con el detector y la misión reales
config/                 todos los parámetros ajustables (JSON)
tags/                   PDFs listos para imprimir: tags de 8 y 15 cm y tablero de calibración
docs/                   documentación (empieza por docs/README.md)
logs/  capturas/        se crean al volar; no van a git
```

## Documentación

Empieza por [`docs/README.md`](docs/README.md): dice qué leer y en qué orden.

| Documento | De qué trata |
|---|---|
| [`competencia.md`](docs/competencia.md) | reglas, puntuación, respuestas del comité, preguntas abiertas |
| [`tello.md`](docs/tello.md) | lo que medimos del dron real |
| [`arquitectura.md`](docs/arquitectura.md) | cómo está hecho el código |
| [`simulador.md`](docs/simulador.md) | cómo probar sin volar |
| [`laboratorio.md`](docs/laboratorio.md) | protocolo de pruebas con el dron |
| [`bitacora.md`](docs/bitacora.md) | historial de sesiones, pendientes y decisiones |

## Cómo trabajamos

- **Parámetros en `config/*.json`, no en el código.** El JSON sobrescribe los valores por
  defecto; si cambias el `.py`, el JSON lo pisa.
- **Simulador antes de volar.** Todo cambio de control se prueba primero con
  `python sim/sim_world.py <escenario>`. Antes de subir algo grande, corre la regresión
  completa (ver `docs/simulador.md`).
- **Después de cada sesión de laboratorio:** `python scripts/resumen_vuelos.py` y una entrada
  en `docs/bitacora.md`.
- **Git:**
  - mensajes cortos en español;
  - cada quien en su rama y se une por pull request, para no pisarse;
  - no se suben videos, bitácoras (`logs/`), `capturas/` ni fotos donde salgan personas.
- **Seguridad:** nunca se vuela sin alguien en el teclado listo para el paro.
