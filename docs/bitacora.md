# Bitácora del proyecto

Qué se probó en cada sesión, qué se aprendió y qué se cambió. Lo más reciente va arriba.
Las bitácoras de vuelo (`logs/*.csv`) y los videos están en la laptop, no en el repo.

## Pendiente ahora

1. **Arreglar la altura del Tello.** El 9-nov a las 17:15, con y sin clip, el despegue subió
   a ~70 cm y se regresó solo al piso, mientras el `h` del Tello subía: su estimación interna
   de altura está mal. **No es el clip.** Calibrar IMU y centro de gravedad en la app Tello
   (con el dron quieto sobre superficie plana al encenderlo), revisar firmware y repetir el
   estacionario sin clip hasta que salga bien.
2. Con espejo, en orden: **E3 → E4 → E5 → E6 → E7** ([`laboratorio.md`](laboratorio.md)).
   Ajustar `advance_timeout_s` y `cruise_alt_cm` según la pista.
3. Respuestas del comité: tamaño de tags, cómo es la trayectoria visible y la etiqueta de
   inicio ([`competencia.md`](competencia.md)).

## 9-nov — Espejo en vuelo real

Detalle y bitácoras en [`../sesiones/2026-11-09/`](../sesiones/2026-11-09/).

- **Antes de volar** se cambió la misión con espejo (`bb2398f`):
  - sostiene el rumbo en vez de alinearse con los bordes del tag;
  - vuela a 100 cm;
  - avanza hasta 12 s entre tags;
  - ignora el tag de inicio.
- **E1** con el clip impreso: la vista queda inclinada 4.1° hacia adelante y 0.8° de lado.
  **E2** salió bien.
- **E3** salió bien al segundo intento: quedó encima del tag a +2/+0 cm.
- **E5 falló:**
  - **Tag de inicio:** el dron se fue hacia adelante al despegar, vio el tag 1 al empezar a
    avanzar y lo tomó como el de inicio. Ahora solo se ignora el que ve *durante* el
    despegue (`8f23e77`).
  - **Despegue:** subió solo a 151 cm en uno y se regresó al piso en otros. Ahora el
    despegue pasa con el `ok` del Tello y aterriza con aviso si se viene abajo. Se sospecha
    que el clip interfiere con los sensores de la panza.
- Se agregaron `sesiones/` (cada día con sus bitácoras), `scripts/guardar_sesion.py`,
  `scripts/traza_vuelo.py` y `CLAUDE.md`, para que el equipo trabaje y se revise desde GitHub.

## 28-oct — Clip de espejo para impresión 3D

Del STL del clip actual se sacaron las medidas: 43.5 × 25.2 × 11.7 mm, placa a 45°.
Con la cámara inclinada 11°, un espejo a 45° apunta la vista 11° hacia adelante de la
vertical; para ver justo abajo hace falta 50.5°. El prompt para diseñar los prototipos
está en `anexos/`.

## 27-oct (tarde) — El dron no obedece

Al dron se le pidió quedarse y subir a fondo: avanzó 120 cm y bajó 45 cm mientras su IMU
decía "nivelado". Pidiéndole bajar, subió. En estacionario se hundía solo. Diagnóstico:
**IMU descalibrado o hélice dañada**, tras varias caídas con paro de motores, volando a
80–86 °C.

En código (`bd9aa89`):
- el sostener altura es más suave y apunta a la altura de crucero;
- el despegue espera el `ok` del Tello;
- el dron aterriza solo si **no obedece** o si **avanza solo** mientras se centra.

Las reglas se verificaron sobre las bitácoras reales: se activan en los vuelos malos y
en ninguno de los buenos.

## 27-oct (mañana) — Piso sin espejo, primera tanda con el código nuevo

- **P1 (flip) aprobada:** de 125 a 81 cm, se estabilizó en 72.
- **Aterrizajes falsos por "obstáculo":** eran reales hundimientos (~10–13 cm/s al
  avanzar, confirmado con la altura que da el PnP). Se quitó el aterrizaje por obstáculo
  y se hizo más fuerte el sostener altura.
- **Se pasaba hasta 90 cm del tag:** pedir adelante y de lado a la vez lo frenaba a
  ~10 cm/s, así que la velocidad medida era baja; a ciegas iba a ~19. Ahora el
  acercamiento se centra primero y luego va recto, midiendo la velocidad solo en el
  tramo recto (`ce4484e`).
- **Detección pobre en movimiento:** se subió la corrección de bits (+15–130 % de
  detecciones, sin IDs falsos).
- **En el simulador:** su paso de física fijo hacía más lento al dron con el CPU ocupado;
  ahora usa el tiempo real.

## 26-oct — Espejo, piso y respuesta del comité

- **Espejo (E1–E3):**
  - la detección a través del espejo funciona;
  - la inclinación medida de la vista es 7.9° hacia adelante y 4.3° de lado;
  - problemas: el montaje tapó el sensor de abajo, la altura variaba 95–118 cm y el espejo
    estaba sucio.
- **Piso (F1–F4):**
  - se quedaba corto porque la velocidad real con `rc` 15 variaba de 12 a 20 cm/s;
  - **dos flips cayeron al piso:** el dron cae ~50 cm/s tras el flip y su `h` no se entera.

  Se cambió a: medir la velocidad en cada acercamiento, y subir a fondo tras el flip
  hasta frenar la caída (`bc656fe`).
- **Comité:** tags en el piso, espejo permitido, recorrido desconocido.

## 24-oct — Calibración de `rc` y pruebas de pared

- La tabla de velocidades reales está en [`tello.md`](tello.md).
- Aprobadas P4 (tag alto: sube mientras se acerca) y P5 (tag girado).
- **Flip:** cayó de 117 a 39 cm; la recuperación se daba por buena mientras seguía cayendo.

## 21-oct — Calibración, primeros vuelos, misión de pared y flips

- **Cámara:**
  - calibrada con el tablero del club (`config/camera_tello.json`);
  - la pose se validó contra alturas medidas (67 vs 66 cm, 105 vs 100 cm);
  - campo de visión real 55° × 43°, eje 11° hacia abajo.
- **Detección de tags en el piso:** medida a 30, 66 y 100 cm de altura (ver `tello.md`).
- **Primeros vuelos:** el estacionario es muy estable; la deriva ocurre en el despegue.
  Se ajustó el giro por `rc`.
- **Misión de pared:** el tag 2 se ejecutó de punta a punta. Se agregaron, uno a uno, el
  centrado lateral, la alineación de frente al tag y el control en el marco del tag.
- **Flips:** funcionan, pero el dron pierde 30–78 cm; sin corrección cae al piso. De ahí
  salió la subida previa a 130 cm.
- **`h` no sirve:** desde entonces la altura es `tof − 10`.

## 17-oct — Detección

- Se probó la detección con webcam y con el Tello en la mano.
- Los tags del reglamento decodifican a los IDs 1–10.
- El dron resultó ser un Tello estándar: no hay cámara de abajo.
- djitellopy entrega RGB y empareja las respuestas sin correlación.

## Decisiones que conviene no deshacer

| Decisión | Por qué |
|---|---|
| Altura con `tof − 10`, nunca con `h` | `h` deriva y a veces dice lo contrario de lo que pasa |
| Confirmar despegue, aterrizaje y flip por telemetría | las respuestas de djitellopy se desfasan |
| Sostener el rumbo del tramo, no alinearse con los bordes del tag | el reglamento pide tolerar tags girados |
| En piso, centrar primero y avanzar después | el mando combinado frena al dron y arruina la velocidad medida |
| Subir a 130 cm antes de cada flip y frenar la caída después | tras el flip el dron cae ~50 cm/s |
| Probar en el simulador antes de volar | cada vuelo real cuesta batería, tiempo y a veces una hélice |
