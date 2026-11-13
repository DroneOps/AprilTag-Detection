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

**Con espejo, qué tag se ejecuta al avanzar** (`_ignorar`, desde el 12-nov):
- **El recién ejecutado se sigue cuadro por cuadro**, porque al avanzar sigue a la vista
  ~60 cm detrás.
  - Uno con su número a menos de `mismo_tag_cm` (35) de donde debe estar (su última posición,
    corrida con lo que avanzó el dron según el piso) es el mismo y se ignora.
  - En otra parte, es otro tag con el mismo número y se ejecuta.
  - Si no se vio al arrancar el tramo, se ignora por número, como antes.
- **Uno ya ejecutado antes (no el último)** solo cuenta si está en la línea del tramo:
  adelante y a menos de `pasillo_cm` (40) de lado. Así funciona regresar a un tag después de
  un 180°, y no se toma uno viejo que quedó a un lado.
- **Uno nuevo,** siempre.
- **Antes,** cualquier número ya ejecutado se ignoraba mientras se viera, así que se perdían
  los tags repetidos y los regresos tras un 180°.

**El rumbo de salida** (con espejo) es el rumbo del tramo más los giros del tag, no el yaw
medido al llegar. Si no, el error de cada giro se sumaba, y tras 6–8 tags iba ~10° chueco.

**Durante el flip** (la subida a 130 cm, la vuelta y la recuperación) se sostiene sobre el tag,
pero solo de lado y adelante; la altura la manda la recuperación. Antes se iba ~1 m en esos
~15 s.

## Sostener la posición con el piso (`mision_espejo.py`, 11-nov)

`FlujoPiso` compara cada cuadro del espejo con el anterior (correlación de fase a 240×180, ~2
ms) y, con la altura, saca cuánto se movió el dron sobre el piso (derecha, adelante). No
mide mientras gira.

**Al subir o bajar, el piso cambia de tamaño en la imagen**, y la correlación confundía ese
cambio de escala con desplazamiento. Subiendo de 30 a 100 cm en vertical "veía" +10 cm de
lado, y el control movía al dron sin razón: un Tello perfecto, sin deriva, terminaba ~12 cm
corrido. Desde el 12-nov, antes de comparar, el cuadro anterior se escala según cuánto
cambió la altura. La velocidad vertical sale del tof con la mediana de las pendientes, para
que una lectura suelta no la mueva.

**Alrededor de qué punto se escala.** Del punto de la imagen que queda justo debajo del dron
(`punto_bajo_dron`): el centro óptico de la cámara espejada, corrido por la inclinación de la
vista (`vista_adelante_deg`, `vista_lado_deg`).
- **Hasta el 12-nov (tarde)** se usaba el centro óptico sin voltear y sin la inclinación.
  Con la vista real (−10.3°), al despegar "veía" al dron irse 6–29 cm hacia atrás, y el PID lo
  empujaba hacia adelante ([issue #2](https://github.com/DroneOps/AprilTag-Detection/issues/2)).
- **Si cambia el clip,** hay que volver a medir la inclinación (con
  `scripts/inclinacion_vuelo.py`, en vuelo): de ella dependen la posición de los tags y esta
  medida.

| Estado | Qué hace con esa medida (`sostener_piso`) |
|---|---|
| HOVER, CRUISE | regresar al punto de despegue (se mide desde que empieza a despegar) |
| ADVANCE | sostener la línea del tramo, solo de lado (con `--quieto`, los dos ejes). El tramo nuevo pasa **por el tag ejecutado** (si se ve), no por donde quedó el dron |
| EXECUTE (giros, pausa) | `sostener_tag`: centrarse sobre el tag con su posición mientras gira. En un giro de 90° se corría 26–42 cm; así queda a ~11 cm (mediana en el simulador) |
| APPROACH, tag perdido | ir a donde debe estar el tag, contando lo que se movió el dron; a los `buscar_s` volver a ADVANCE en vez de aterrizar |

### El control: un PID por eje

En cada paso del control (20 por segundo), para cada eje (de lado y adelante):

```
error = cm que está corrido de donde debería estar        (lo da FlujoPiso)
vel   = cm/s que se está yendo                             (lo da FlujoPiso)
I     = I + piso_ki · error · dt     (con tope ±piso_i_max)
u     = −(piso_kp · error + piso_kd · vel + I)
rc    = 0 si |u| < piso_dead;  si no, entre piso_min y piso_max con el signo de u
```

El rc se **suma** al que manda la misión (`MirrorMission._send_rc`), y luego pasa por los
límites de siempre (`rc_limit` 20 de `config/flight.json`).

- **P** (`piso_kp`, rc por cm): empuja hacia donde debe estar, más fuerte entre más lejos.
- **D** (`piso_kd`, rc por cm/s): frena. Si ya va regresando rápido, empuja menos; si se va
  yendo, empuja más antes de que el error crezca. Con el video atrasado ~0.17 s, sin D se
  pasaría de largo.
- **I** (`piso_ki`, rc por cm·s): junta el empuje que hace falta contra una **deriva
  constante**. Sin I, el dron se queda corrido lo justo para que P empuje lo que la deriva
  pide: con el Tello 7 (~12 cm/s, que pide rc ~13), 13 / 0.5 = ~26 cm. La I llega a ese
  rc y el error regresa a ~0.
  - Tope `piso_i_max`, y no junta más si ya va al máximo empujando hacia ese lado
    (anti-windup).
  - En cada despegue arranca en `piso_i_inicial`, que va en `config/mision_dron<N>.json` de
    cada dron (`python scripts/mision_espejo.py --dron 7`). Entre tramos se conserva, porque
    la deriva medida va con el dron (siempre a su derecha).
  - Lo que juntó queda en la bitácora en `piso_ider` y `piso_iade`. Al final de un E2b, ese es
    el valor para `piso_i_inicial` de ese dron.
  - **Si el dron ya no deriva, una integral precargada empuja de más al principio** y luego se
    corrige sola. En el simulador, con un dron sin deriva: precargada en 4.5 se fue ~5 cm más
    en los primeros 8 s; en 13, ~15 cm más. Si un dron se arregla, regresar su
    `piso_i_inicial` a [0, 0].
- **Zona muerta y mínimo:** con rc menor a ~5 el Tello no se mueve. Por eso un mando chico
  (< `piso_dead`) no se manda, y uno que sí se manda es de al menos `piso_min` (10).
  El costo es que con poca deriva corrige de más y queda en un vaivén de ~10 cm.

**Dónde está** (todo en `scripts/mision_espejo.py`):
- `MirrorConfig`: los parámetros;
- `ajustes_dron`: los ajustes de cada dron;
- `FlujoPiso`: la medida;
- `_piso_mando`: el PID de un eje;
- `_send_rc`: cuándo se aplica, el seguro y sostenerse sobre el tag;
- `_goto`: qué se reinicia en cada estado y cómo se ancla el tramo en el tag.

**Seguro:** si, corrigiendo, se aleja más de `piso_alejandose_cm` (35) en 1.5 s, o se pasa de
`piso_limite_cm` (150), se apaga para todo el vuelo: la medida podría estar al revés. No
cuenta lo que se fue al despegar, porque ahí el Tello ignora el rc: el Tello 7 se va más de
80 cm. Lo que mide va en la bitácora en `piso_der`, `piso_ade` (el error), `piso_vder`,
`piso_vade` (la velocidad) y `piso_q` (la calidad).

**En el simulador** (`espejo_estacionario`: quieto 20 s; distancia media al despegue):

| Dron | Sin sostener | Solo PD | PID (`piso_ki` 0.15) |
|---|---|---|---|
| Tello 1 | 46–115 cm | 8 cm | 11–14 cm |
| Tello 7 | 262–341 cm | 42–68 cm | 21–22 cm |

En el circuito E5, el Tello 7 completó 3 de 4 con PID y 0 de 4 con solo PD. El Tello 1, 3 de
4 con los dos. Con `piso_ki` 0.08 y 0.25 salió parecido; se dejó 0.15.

### Otra opción: filtro de Kalman (`"piso_control": "kalman"`, 12-nov) — NO SE USA

**Se queda el PID.** En el laboratorio del 12-nov el Kalman se centró peor sobre los tags (~20
cm contra ~6) y oscilaba más. Su modelo del dron (rc 15 → 14.5 cm/s) no cuadra con el real
(~9 cm/s medido con el piso). El código queda apagado como opción; por qué y qué haría falta
para retomarlo, en el encabezado de `scripts/kalman_piso.py`.

`scripts/kalman_piso.py`. En vez de reaccionar al error como el PID, **estima** por cada eje
(de lado y adelante) tres cosas:

| Estado | Qué es | De dónde sale |
|---|---|---|
| `p` | cm que está corrido de donde debería estar | lo mide `FlujoPiso` (atrasado) |
| `v` | cm/s que le dan los rc que se mandaron | del modelo del dron, no se mide |
| `d` | cm/s que se va solo: la deriva | de la diferencia entre lo que se mueve y lo que se le pidió |

El modelo es el del simulador, medido en las calibraciones de rc (`docs/tello.md`):
`velocidad pedida = kalman_ganancia · (|rc| − kalman_zona)`, y el dron llega a ella con una
constante de tiempo `kalman_respuesta_s`. Lo que se mueve de más o de menos es la deriva.

- **Atraso:** cada medida se aplica en el momento en que se tomó la imagen
  (`kalman_atraso_video_s`, 0.17 s antes de llegar) y luego se predice hasta ahora con los rc
  que ya se mandaron. El control usa esa predicción, no la posición atrasada (es el paso 3,
  ya incluido).
- **Mando:** pide la velocidad que cancela la deriva, más la que lo regresa y la que frena:
  ```
  vc = −d − kalman_kp · p − kalman_kd · (v + d)
  rc = el que da esa velocidad según el modelo: kalman_zona + |vc| / kalman_ganancia (con su signo)
  ```
  Con τ 0.75 s, kp 1.2 y kd 1.0, el lazo regresa en ~3 s sin oscilar. Los rc salen finos
  (6, 7, 8…) en vez de "0 o 10" (es el paso 5, ya incluido).
- **La deriva hace el trabajo de la integral,** pero sin esperar a que haya error: el filtro ve
  que el dron se mueve sin que se lo pidan y lo aprende en ~1–2 s, ya desde el despegue. Por
  eso **arranca en 0 en todos los drones** (`kalman_deriva_inicial`) y no hace falta suponer
  una deriva por dron: si un dron se arregla, no empuja de más.
- **Huecos:** mientras gira o hace un flip no hay medida; en la siguiente se re-ancla la
  posición (se conservan la velocidad y la deriva). Una medida que brinca mucho también re-ancla.
- **Seguros:** si lo medido deja de cuadrar con lo predicho (NIS promedio >
  `kalman_nis_max`) o la deriva estimada pasa de `kalman_deriva_max` (50 cm/s), se apaga y
  sigue con el PID, desde `piso_i_inicial`. Con la medida al revés, el filtro lo explica como
  una deriva enorme (49–83 cm/s) y el NIS no lo ve; en vuelos normales del Tello 7 simulado
  llega hasta ~43 (con 40 se apagaba solo en una racha). Sigue funcionando el seguro de
  siempre (`piso_alejandose_cm`), que apaga todo y es el que de verdad cuida la medida al revés.
- **`kalman_centrar`** (prendido): al centrarse sobre el tag (APPROACH) y al sostenerse sobre
  él (giros, pausa), suma al mando del centrado lo que cancela la deriva estimada. El centrado
  sigue siendo el de siempre; solo ya no pelea contra la deriva. **De aquí sale casi toda la
  mejora en el circuito:** con el Tello 7 simulado, sin esto el Kalman completó lo mismo que
  el PID (5 de 12) y con esto, 10 de 12.
- **Avanzando, no corrige de lado por poco** (`kalman_lado_avanzando`, 4 cm/s). Mandar de lado
  y adelante a la vez hunde al Tello ~8 cm/s (11-nov). Con correcciones chicas todo el tiempo,
  el sostener altura no alcanzaba y volaba a 88–95 cm. Ahí el tag gastado de `espejo_gastado`
  no se detecta nunca, y a 95–110 cm a veces. Pasó de 0 de 4 a 2 de 4, como `main`.
- **Resultados contra el PID** (simulador, tandas con las mismas semillas): tabla en la
  bitácora, entrada "12-nov (noche)". Se comparan con `sim/comparar_control.py`.
- **Para usarlo:** en `config/mission_espejo.json`, `"piso_control": "kalman"`. Está en
  `"pid"` hasta probarlo en el laboratorio.
- **Bitácora:** `kal_der`, `kal_ade` (posición predicha), `kal_dder`, `kal_dade` (deriva
  estimada, cm/s) y `kal_nis` (≈ 0.1–0.5 si el modelo cuadra).

**Cómo ajustarlo** (`config/mission_espejo.json`):

| Qué se ve | Qué cambiar |
|---|---|
| `kalman APAGADO: no cuadra` o `deriva estimada imposible` | la medida o el modelo están mal: revisar `espejo` con E1 y `kalman_ganancia` con `scripts/rc_calib.py` |
| Va y viene, o se pasa de largo | bajar `kalman_kp`; subir `kalman_kd` |
| Regresa lento | subir `kalman_kp` (1.2 → 2.0) |
| Tiembla o se tambalea (mandos que cambian mucho) | bajar `kalman_q_deriva` (50 → 20): sigue la deriva más despacio |
| La deriva cambia rápido (corrientes de aire) y no la alcanza | subir `kalman_q_deriva` (50 → 200) |
| Otro dron u otra calibración de rc | `kalman_ganancia`, `kalman_zona` y `kalman_respuesta_s`, de `scripts/rc_calib.py`; si el modelo falla poco, la deriva absorbe la diferencia |

### Cómo ajustarlo

Todo va en `config/mission_espejo.json`. Primero en el simulador (`python sim/sim_world.py
espejo_estacionario --dron N` da la distancia media al despegue), luego E2b en el
laboratorio. Cambia un valor a la vez.

| Qué se ve (video o `piso_der`/`piso_ade`) | Qué cambiar |
|---|---|
| Se queda corrido siempre del mismo lado | subir `piso_ki` (0.15 → 0.25) o `piso_i_max` |
| Al despegar se va de un lado unos segundos y luego regresa | poner en `piso_i_inicial` de ese dron el `piso_ider` con que terminó un E2b |
| Al principio empuja hacia un lado sin que haya deriva | `piso_i_inicial` de más (el dron ya no deriva tanto): bajarlo o [0, 0] |
| Va y viene de un lado al otro, cada vez más | bajar `piso_kp` o `piso_ki`; subir `piso_kd` |
| Se pasa de largo al regresar | subir `piso_kd` (0.8 → 1.2) o bajar `piso_ki` |
| Regresa muy lento, o la deriva le gana | subir `piso_kp`; subir `piso_max` no sirve, porque `rc_limit` es 20 |
| Vaivén chico (~10 cm) aunque casi no hay deriva | normal por `piso_min` 10; si estorba, bajar `piso_min` a 8 (abajo de ~6 el Tello no se mueve) |
| Tiembla con correcciones chiquitas | subir `piso_dead` |
| `piso_q` casi siempre abajo de 0.1, no corrige | el piso no tiene textura (liso, brillante, poca luz): más luz u otro piso; o bajar `piso_calidad` con cuidado |
| `sostener_piso APAGADO` sin que se fuera mal | subir `piso_alejandose_cm` (35 → 45) |
| `sostener_piso APAGADO` porque sí se iba al revés | la medida sale invertida: `"sostener_piso": false` y revisar `espejo` (v/h) con E1 |

Casos en los que hará falta ajustarlo:
- **Otro dron o el mismo después de una caída o de calibrar el IMU:** cambia la deriva.
- **Otro clip o espejo,** u otra altura de vuelo (`cruise_alt_cm`): cambia la escala de la
  medida.
- **Otro piso:** el de la competencia puede tener otra textura o brillo, y la medida depende
  de él.
- **Si se cambia `advance_fb` o el centrado:** el PID se suma a esos mandos.

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
