# Cómo está hecho el código

Python 3.12, [djitellopy](https://github.com/damiafuentes/DJITelloPy) 2.5.0, OpenCV 5.0
(detector ArUco con el diccionario `DICT_APRILTAG_25h9`) y numpy. Sin ROS. Todo corre en
la laptop: el Tello solo manda video y telemetría por WiFi y recibe comandos `rc`.

## Capas

```
test_tags.py        visión: detector, confirmación, pose (PnP), dibujo, fuentes de video
     │
first_flight.py     Flight: máquina de estados de vuelo, seguridad, HMI, bitácora
     │
mission_tags.py     TagMission: acciones de cada tag, flip seguro, sostener altura,
     │              "el dron no obedece". Acercamiento a tags de PARED.
     ├── mision_piso.py     FloorMission: tags en el piso con la cámara al frente
     └── mision_espejo.py   MirrorMission: tags en el piso viendo hacia abajo con espejo
```

Cada misión hereda de la anterior y solo cambia la visión (`on_frame`) y las fases
`ADVANCE` y `APPROACH`. Las acciones, el flip, el paro y los vigilantes se comparten.

## Hilos

`run_app()` en `first_flight.py` arma todo:

- **Hilo principal:** lee el frame más reciente, corre la visión (`flight.on_frame`),
  dibuja la HMI y atiende el teclado. djitellopy decodifica el video en su propio hilo
  (`get_frame_read(with_queue=True, max_queue_len=1)`, para que el frame nunca sea viejo).
- **Hilo de control** (`Flight.run`): corre la máquina de estados a **20 Hz** (`rc_hz`) y
  manda `send_rc_control` en cada ciclo.
- El **paro** no pasa por el lazo: la tecla levanta una bandera que el lazo atiende en el
  siguiente ciclo (≤ 50 ms) y manda `land`.

## Máquina de estados

`Flight` (vuelo base):

```
IDLE ─t─▶ TAKEOFF ─▶ HOVER ─▶ (YAW_TEST | FLIP_CLIMB ▶ FLIP_TEST ▶ FLIP_RECOVER) ─▶ LANDING ─▶ DONE
                 cualquier estado en el aire ─▶ EMERGENCY_LAND ─▶ DONE       k ─▶ KILLED
```

`TagMission` y sus hijas, después de `HOVER`:

```
CRUISE ─▶ ADVANCE ─▶ APPROACH ─▶ EXECUTE ─▶ ADVANCE ... (hasta el tag 7 o sin tags por N s)
```

- **CRUISE:** sube o baja a la altura de crucero.
- **ADVANCE:** avanza sosteniendo el rumbo del tramo hasta ver un tag confirmado.
- **APPROACH:** se acerca. En el piso con la cámara al frente las fases son
  `centrar` → `recto` (mide la velocidad real) → `ciegas` (último metro sin ver el tag)
  → `quieto`. Con espejo, se centra encima del tag.
- **EXECUTE:** ejecuta la lista de primitivas del tag (`ACTIONS` en `mission_tags.py`):
  `yaw`, `alt_to`, `flip_go`, `wait`, `land`. El flip sube primero a 130 cm, voltea
  alejándose del tag y luego recupera la altura en tres fases: frenar, sostener y asentar.

## Visión (`test_tags.py`)

- `TagDetector`: lista blanca de IDs 1–10 y `errorCorrectionRate` 0.8 (en videos de
  vuelo da +15–130 % de detecciones sin IDs falsos). Si en un frame no encuentra ningún tag,
  hace un **rescate para tags gastados** (`deteccion_rescate`, 11-nov):
  1. umbral más sensible;
  2. imagen erosionada 3 y 5 px con contornos menos exigentes.

  Cada rescate cambia una sola cosa, y lo rescatado debe verse como un tag (casi cuadrado,
  ≥ 20 px); si no, salían IDs falsos. Ver `sim/prueba_desgaste.py`.
- `Confirmer`: un ID cuenta solo si se ve en el frame actual y en `confirm_n` de los últimos
  `confirm_ventana` frames: **3 de 5** en `config/mission_tags.json` (antes del 11-nov, 3
  seguidos; con tags gastados la detección parpadea).
- `PoseEstimator`: `solvePnP` (`IPPE_SQUARE`) con la calibración de
  `config/camera_tello.json`. Su método `mirrored()` da la versión para el espejo.
- `floor_from_front(pose, 11°)`: para un tag en el piso visto con la cámara al frente,
  devuelve adelante, lado, altura y giro, compensando la inclinación de 11° de la cámara.
- `floor_view(pose, tilt)`: lo mismo para la vista con espejo (la imagen se voltea antes
  de detectar, porque un tag espejado no se decodifica).

## Altura y seguridad

- **Altura = `tof − 10`** (sensor de distancia de abajo). El `h` del Tello deriva y a veces
  dice lo contrario de lo que pasa; no se usa para controlar.
- **Sostener altura:** en `ADVANCE`, `APPROACH` y `EXECUTE`, un `rc` vertical de 0 significa
  "sostener la altura de crucero". Es un control PI con filtro de saltos del tof, porque el
  Tello se hunde ~10–13 cm/s al avanzar.
- **Vigilantes** (aterrizan solos):
  - pérdida de telemetría o de video;
  - batería baja o temperatura alta;
  - tiempo máximo de vuelo;
  - dron en el piso sin pedirlo;
  - **"el dron no obedece"**: pide subir y cae 15 cm en 0.7 s, o al revés;
  - **"avanza solo"**: en piso, mientras se centra.
- Respuestas del Tello: djitellopy las empareja en orden, sin saber a qué comando
  pertenecen, así que un `ok` suelto no prueba nada. Despegue, aterrizaje y flips **se
  confirman por telemetría**.

## Configuración (`config/`)

Cada archivo JSON sobrescribe los valores por defecto de una `dataclass` del código. Si una
clave no existe en la clase, el programa no arranca (así se detectan errores de dedo).
**Para ajustar algo, cambia el JSON, no el `.py`.**

| Archivo | Clase | Qué controla |
|---|---|---|
| `flight.json` | `FlightConfig` | despegue, límites de `rc`, vigilantes, flip, recuperación |
| `mission_tags.json` | `MissionConfig` | tamaño de tag, confirmación, crucero, sostener altura, acercamiento a pared |
| `mission_tags_15cm.json` | `MissionConfig` | lo mismo para tags de 15 cm |
| `mission_piso.json` | `FloorConfig` | misión de piso: centrar, recto, tramo a ciegas |
| `mission_espejo.json` | `MirrorConfig` | misión con espejo: volteo e inclinación del espejo |
| `camera_tello.json` | — | calibración de la cámara (K y distorsión, 960×720) |

## Lo que se guarda en cada vuelo

- `logs/<misión>_<fecha>_<hora>.csv`: una fila por ciclo de control con estado, batería,
  `h`, `tof`, actitud, temperatura, los cuatro `rc` enviados, el motivo y columnas de
  visión de cada misión. **Es lo primero que hay que revisar cuando algo sale mal.**
- `capturas/`: calibraciones, resúmenes de sesión y capturas de pantalla.
- Video, si se corre con `--record nombre.mp4`.

`logs/`, `capturas/` y `*.mp4` están en `.gitignore`: se quedan en la laptop. Para
compartir una sesión, `scripts/guardar_sesion.py` copia sus bitácoras y resúmenes a
`sesiones/`, que sí va a git.

## Herramientas

| Script | Para qué |
|---|---|
| `test_tags.py` | probar detección y pose sin volar (webcam, Tello en la mano, video o `--selftest`) |
| `calibrate_camera.py` | calibrar la cámara con un tablero de ajedrez |
| `make_tags.py` | PDF de los tags 1–10 al tamaño que quieras |
| `rc_calib.py` | medir cuánto se mueve el dron con `rc` 10/15/20 |
| `resumen_vuelos.py` | veredicto de cada vuelo de una sesión, leyendo `logs/` |
| `traza_vuelo.py` | una bitácora condensada, estado por estado, con las columnas de visión |
| `guardar_sesion.py` | copia las bitácoras, resúmenes y notas del día a `sesiones/AAAA-MM-DD/` |
| `first_flight.py` | vuelo base: estacionario, prueba de giro y prueba de flip |
| `sim/sim_world.py` | simulador 3D (ver `simulador.md`) |
