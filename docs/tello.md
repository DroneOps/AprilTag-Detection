# Lo que sabemos del Tello (medido, no del catálogo)

Nuestro dron es un **Tello estándar** (se vendió como "Boost Combo": Tello normal más
baterías extra). No es EDU: responde `unknown command` a `sdk?`, no tiene modo estación y
**no da acceso a la cámara de abajo** (`downvision` no existe). Todo se hace con la cámara
frontal.

## Cámara

- Video a **960×720**, ~30 fps. Calibración en `config/camera_tello.json` (fx ≈ 912–920,
  error RMS 0.69 px).
- Campo de visión real: **55° × 43°** (el catálogo dice 82.6°; no es cierto para el video).
- El eje óptico apunta **11° hacia abajo**, así que el borde de abajo de la imagen queda a
  ~31° bajo la horizontal.
- Latencia total del video: **~170 ms**. Detectar tags toma ~5 ms por frame.
- **Tags en el piso con la cámara al frente:** la distancia máxima de detección sigue más
  o menos `d_max ≈ 7.75·√(tag_cm · altura_cm)`. Con un tag de 8 cm:
  - a 30 cm de altura, hasta ~120 cm;
  - a 66 cm, hasta ~180 cm;
  - a 100 cm, hasta ~215 cm.

  Más cerca de `altura / tan(31°)` el tag se sale por abajo de la imagen: a 60 cm de
  altura, eso es ~1 m.
- En movimiento la detección empeora (desenfoque). Por eso hay corrección de bits extra y
  confirmación de 3 frames.

## Altura

- El campo **`h` del Tello no sirve** para controlar: deriva, va en pasos de 10 cm y se ha
  visto decir "subo" mientras el dron bajaba. Usamos **`tof − 10`** (`altitude()`).
- **Al avanzar se hunde ~10–13 cm/s** aunque se le pida subir con `rc` 15–18. Por eso existe
  el sostener altura.
- El tof a veces da lecturas falsas (81 → 14 → 83 cm en 0.4 s). Hay filtro para eso.
- **Despegue:** el Tello sube por su cuenta hasta 50–110 cm e ignora los mandos hasta
  contestar `ok`. El programa espera ese `ok`.

## Velocidad según `rc` (calibración del 24-oct, `scripts/rc_calib.py`)

| `rc` | adelante | atrás | derecha | izquierda | arriba | abajo |
|---|---|---|---|---|---|---|
| 10 | 7.9 | 5.5 | 6.5 | 4.9 | 4.7 | 1.0 |
| 15 | 17.9 | 15.6 | 20.0 | 17.4 | 10.0 | 4.7 |
| 20 | 27.3 | 18.2 | 23.7 | 28.1 | 5.3 | 10.0 |

(cm/s). Por debajo de `rc` 10 casi no se mueve. Ojo:

- La velocidad real con `rc` 15 hacia adelante **varió de 12 a 20 cm/s** entre vuelos. Por
  eso la misión de piso la mide en cada acercamiento.
- **Adelante y de lado a la vez lo frena mucho:** fb 15 + lr 15 dio ~10 cm/s adelante y
  ~3 de lado. Por eso la misión de piso primero se centra y luego avanza.
- El 27-oct, `rc` 40 hacia arriba subió ~40 cm/s y `rc` −40 hacia abajo solo ~7. Vertical
  es irregular.
- Giro: con `rc` 60 gira ~44°/s; por debajo de `rc` 10–15 casi no gira.

## Flips

- Necesitan **batería ≥ 50 %** en el momento del flip; si no, el Tello no lo hace.
- Durante la vuelta el tof da basura (150–600 cm).
- **Después del flip el dron cae ~50 cm/s y su `h` no se entera.** Llegó a tocar el piso
  desde 77 cm y bajó de 117 a 39 cm. Ahora sube a 130 cm antes del flip y al terminar
  sube a fondo hasta frenar la caída. La prueba real del 27-oct cayó de 125 a 81 cm, bien.

## Batería y temperatura

- En vuelo gasta **~25–30 % por minuto**. Empieza cada intento cerca del 100 % si hay flips.
- En tierra con video encendido **se calienta de 60 a 85 °C en ~5 min**. Arriba de 80 °C
  no despega. Con más de ~80 °C su control de altura se vuelve raro. Usa ventilador y
  apágalo entre corridas.

## Enlace WiFi

Solo 2.4 GHz. `test_tags.py` imprime al salir una línea `enlace:` con frames atrasados
(> 100 ms) y el máximo. Apagar el ahorro de energía del WiFi de la laptop
(`sudo iw dev <interfaz> set power_save off`) puede ayudar.

## Espejo

- Un tag visto en el espejo **no se decodifica**: hay que voltear la imagen
  (`--espejo v`).
- La vista con el clip actual quedó inclinada **7.9° hacia adelante y 4.3° de lado**
  (medido con `test_tags.py --espejo`; está en `config/mission_espejo.json`).
- Un montaje tapó el **sensor de abajo** y el dron creía estar en el piso: no despegaba.
- Con espejo, el dron sostiene peor la altura (se vio variar de 95 a 118 cm).

## Cuando el dron "no obedece"

El 27-oct, tras varias caídas con paro de motores, el dron hizo lo contrario de lo pedido:

- se le pidió quedarse y subir a fondo, y avanzó 120 cm y bajó 45 cm;
- mientras tanto el IMU decía roll 0 y pitch 0;
- se le pidió bajar y subió.

Eso es **IMU descalibrado o hélice dañada**, no código. Antes de seguir probando, haz
**"Revisar el dron"** en [`laboratorio.md`](laboratorio.md): hélices, calibrar IMU y centro
de gravedad en la app oficial, enfriar y prueba de estacionario.

## Rarezas de djitellopy

- Los frames llegan en **RGB** (OpenCV usa BGR).
- Las respuestas se emparejan en orden, sin saber a qué comando pertenecen: un paquete de
  más desfasa todas las siguientes. Por eso se vacía la cola antes de comandos importantes
  y se confirma por telemetría.
