# Bitácora del proyecto

Qué se probó en cada sesión, qué se aprendió y qué se cambió. Lo más reciente va arriba.
Las bitácoras de vuelo (`logs/*.csv`) y los videos están en la laptop, no en el repo.

## Pendiente ahora

1. **Probar en el laboratorio los cambios del 9-nov (noche), sin volar todavía:** rumbo más
   firme tras los giros (`heading_min` 20), centrado de ≤12 cm con máximo 8 s, y
   `ignorar_inicio` en `false`. Repetir **E5** sobre la pista del seguidor de línea, con el
   dron frío y la batería arriba de 70 %.
2. **Si se sigue yendo a la derecha al avanzar sin ver tags:** probar `advance_lr` en -10 o
   -15 (`config/mission_espejo.json`) y revisar si hay ventilador o corriente de aire. La
   solución de fondo propuesta, sin hacer: corregir la deriva con el **flujo del piso visto
   por el espejo**. En el video del 9-nov, la pista del seguidor dio calidad ~0.9 con
   correlación de fase.
3. **Tello #1:** su sistema de visión de abajo (VPS) parece dañado; la app avisa
   "posicionamiento visual no disponible" aun con buena luz y la panza limpia. Repararlo o
   no usarlo. Las pruebas del 9-nov (tarde) se hicieron con otro Tello, que también usa el
   seguidor de línea.
4. Con espejo, en orden: **E5 → E6 → E7** ([`laboratorio.md`](laboratorio.md)). Ajustar
   `advance_timeout_s` y `cruise_alt_cm` según la pista.
5. Respuestas del comité: tamaño de tags, cómo es la trayectoria visible y la etiqueta de
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
- **Tarde:**
  - con el Tello #1, el despegue se regresaba solo al piso con y sin clip, y la app avisó
    que su VPS no estaba disponible;
  - con otro Tello, sobre la pista del seguidor de línea, el estacionario con clip salió
    bien, pero en E5 se iba a la derecha.
  - Causas encontradas:
    - el tag 1 estaba debajo del despegue y se ignoraba como "de inicio"
      (`ignorar_inicio` → `false`);
    - el centrado oscilaba ±15–20 cm (ahora frena con la velocidad del tag y ejecuta a
      ≤12 cm o a los 8 s);
    - tras el giro, el rumbo seguía rotando de 90° a 101° porque la corrección con rc 15
      caía en la zona muerta del Tello (`heading_min` 20).

  `DroneOps/Line_Follower` funciona con el mismo dron, no tiene configuración especial y
  también usa espejo. Commits: `324a07d`, `4a93400`, `fcaaabd`.
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
