# Bitácora del proyecto

Qué se probó en cada sesión, qué se aprendió y qué se cambió. Lo más reciente va arriba.
Las bitácoras de vuelo (`logs/*.csv`) y los videos están en la laptop, no en el repo.

## Pendiente ahora

1. **La deriva estando quieto (11-nov), lo más urgente.** Los dos Tellos se van a la derecha
   en estacionario: el Tello 7 de 15 a 37 cm/s y el Tello 1 ~6–7 cm/s, este también sin
   espejo. Por eso E5 falla: los tags aparecen en la orilla de la vista y se pierden al
   centrarse. En el próximo laboratorio:
   - estacionario del Tello 7 **sin clip**, en el mismo lugar;
   - estacionario de los dos **sobre otro piso**: la cuadrícula de cinta azul se repite mucho
     y podría confundir a la cámara de abajo (sospecha, sin medir);
   - calibrar el IMU antes.
2. **Corregir la deriva con el piso visto por el espejo.** El 11-nov, la medición de lado con
   correlación de fase coincidió en signo con la del tag en 72 % de los tramos. Hacia
   adelante cuesta, porque las rayas de la pista van en la dirección del avance. Mientras,
   probar `advance_lr` en -10 y acortar el tiempo quieto antes de avanzar (`start_hover_s`).
3. **El Tello 1 falla caliente:** a 68–78 °C no despega o "no obedece"; frío (55 °C) va bien.
   Volarlo solo abajo de 65 °C y revisar en la app si es el que avisaba "posicionamiento
   visual no disponible".
4. **Al perder un tag al centrarse, buscarlo en vez de aterrizar** (4 corridas del 11-nov
   terminaron así). El simulador ya lo reproduce con `--dron 1` y `--dron 7` (deriva medida
   de cada dron): probar ahí cualquier cambio de la misión antes de volar. Falta medir bien la
   deriva durante el despegue: en el simulador se corre más que en lo real.
5. Con espejo, en orden: **E5 → E6 → E7** ([`laboratorio.md`](laboratorio.md)). Ajustar
   `advance_timeout_s` y `cruise_alt_cm` según la pista. Enfriar entre corridas: el 11-nov
   se volaron 27 en 26 min.
6. Respuestas del comité: tamaño de tags, cómo es la trayectoria visible y la etiqueta de
   inicio ([`competencia.md`](competencia.md)).
7. Al cerrar cada sesión, correr `python sim/comparar_vuelos.py` y, si cambió el Tello o el
   clip, reajustar `config/sim_tello.json` ([`simulador.md`](simulador.md)). Las bitácoras
   del 11-nov dicen en `sesiones/2026-11-11/notas.md` qué dron fue cada una.

## 11-nov (tarde) — E5 con dos Tellos

Detalle y bitácoras en [`../sesiones/2026-11-11/`](../sesiones/2026-11-11/).

- **E5 no salió sin ayuda.** De 27 corridas (19 del Tello 1, 8 del Tello 7), solo la 7.7
  completó 1 → 2 → 7, y con la mano sosteniéndolo sobre los tags. Sin mano, lo mejor fue la
  1.9: ejecutó 1 y 2 y aterrizó por "el dron no obedece".
- **Deriva a la derecha estando quieto, en los dos drones** (medida con el piso visto por el
  espejo, aproximada). Los tags aparecían en la orilla de la vista y, al ir por ellos, se
  salían: el dron se inclina para moverse y la vista del espejo se inclina con él.
- **El Tello 1 falla caliente:** 6 despegues malos y 4 "no obedece", todos a 68–78 °C.
- **Lo que sí funcionó:**
  - el rumbo tras los giros (88°, ya no se pasa como el 9-nov);
  - la detección de tags gastados: el tag 4 de 62 a 238 cuadros con el rescate, sin IDs
    falsos.
- Los paros con `k` fueron porque los drones se iban contra la malla de la arena.

## 11-nov — Simulador ajustado a los vuelos reales y tags gastados

Sin volar. Detalle en [`simulador.md`](simulador.md).

- Antes, el simulador era optimista. Con rc 15–19 giraba 6 °/s y el real no gira; tras un
  giro el real sigue girando 8° y el simulador no. Además: despegue siempre a 65 cm con
  "ok" a los 2 s, video sin atraso, la mitad de la deriva y subía el doble de rápido.
- Ahora el dron simulado se comporta según **`config/sim_tello.json`**, ajustado con los
  14 vuelos del 9-nov. `--ideal` deja el modelo de antes.
- **`sim/comparar_vuelos.py`** le pasa al modelo los mismos rc de los vuelos reales y compara
  lo que hizo cada uno; con `--ajustar --guardar` reajusta el JSON. Error al predecir 1.5 s
  de vuelo: rumbo 1.2° → 0.9°, altura 6.2 → 4.6 cm, posición del tag 14 → 10 cm.
- Escenarios nuevos: `espejo_despegue_cae`, `espejo_despegue_alto`, `espejo_sin_ok`.
- Según las bitácoras, el 9-nov 6 de 21 despegues se vinieron abajo (subieron y regresaron al piso).
- Regresión realista: la misión con espejo pasa, pero `espejo_inicio` falló 1 de 5 veces
  por la deriva durante el despegue (pendiente 6).
- **Tags gastados:** en los videos de E5 los tags se ven desteñidos (negro ~150 de 255,
  contraste ~105; [`tello.md`](tello.md)). El simulador ahora puede desteñirlos, mancharlos y
  arrancarles pedazos (escenarios `espejo_lab`, `espejo_gastado`).
  - El detector hace un **rescate** cuando no ve nada: umbral más sensible, o imagen
    erosionada con contornos menos exigentes, y solo acepta lo que parece tag.
  - Se confirma con **3 de los últimos 5** cuadros en vez de 3 seguidos.
  - Con `sim/prueba_desgaste.py`: muy desteñido 22 → 79 %, manchas 20 % 16 → 52 %, pedazos
    faltantes 8 % 35 → 60 %, sin IDs equivocados. En los videos reales, 1,634 → 1,685 cuadros
    con tag; el tag 2 dañado de 6 a 20; ningún ID falso.
  - En vuelo simulado con tags gastados, el detector de antes no ejecutó ninguno; el nuevo
    ejecuta 2 o 3 de 3.

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
