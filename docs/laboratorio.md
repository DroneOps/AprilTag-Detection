# Protocolo de laboratorio

Guía para llegar y solo ejecutar comandos. Las pruebas van **en orden de prioridad**: si
se acaba el tiempo, lo que falte es lo menos importante. Qué se probó antes y qué salió
está en [`bitacora.md`](bitacora.md).

**Orden actual (con espejo):** Revisar el dron (con el clip puesto) → E1 → E2 → E3 → E4 →
E5 → E6 → E7 (ensayo de competencia). Las de piso sin espejo (F1–F4) quedan de respaldo.

---

## Antes de salir

- [ ] **Baterías cargadas**, idealmente 3 al 90–100 %. Los flips necesitan > 50 % *en el
      momento del flip*.
- [ ] **Ventilador pequeño:** el Tello pasa de 60 a 85 °C en ~5 min en tierra y arriba de
      80 °C no despega.
- [ ] Tags impresos (`tags/tags_8cm.pdf`, opcional `tags/tags_15cm.pdf`): al menos **1, 2,
      4, 7 y 9**.
- [ ] Hélices de repuesto, cinta métrica, cinta adhesiva y vernier.

## Al llegar (5 min)

1. Abre una terminal en el proyecto y activa el entorno de Python (ver el
   [README](../README.md)).
2. **Espacio de vuelo:** ~2 m libres alrededor y **~1.7 m libres hacia arriba**, porque
   antes de cada flip el dron sube a 130 cm.
3. Seguridad:
   - Una persona en el teclado, con la ventana enfocada y el dedo sobre **ESPACIO**
     (paro = aterrizaje).
   - `k` mata motores y el dron **cae**: úsala **solo** si va hacia una persona. Cada caída
     puede dañar una hélice o descalibrar el IMU.
4. Cada prueba lleva `--record` con un **nombre distinto**, para no sobrescribir videos.

## Revisar el dron (10 min) ⭐ — al inicio y después de cualquier caída

Si el dron se inclina solo, deriva mucho o sube y baja sin que se le pida, el problema es
del dron, no del código: ninguna misión va a funcionar así.

1. **Hélices:** revisa las 4. Si alguna está astillada, doblada o floja, cámbiala por una
   **del mismo tipo** que la que quitas (hay dos tipos que giran al revés; vienen marcadas).
2. **Calibrar el IMU** en la app oficial Tello: en *Ajustes* (engrane) → *Más*, la opción de
   calibrar IMU. Sigue las posiciones que pide sobre una mesa plana. Ahí mismo está la de
   calibrar el centro de gravedad: hazla también.
3. **Enfriar:** que la temperatura esté abajo de ~70 °C antes de despegar (con el
   ventilador y el dron apagado entre corridas).
4. **Prueba de estacionario,** sin tags:
   ```bash
   python scripts/first_flight.py --record estacionario.mp4
   ```
   Durante los 10 s quieto **no debe moverse más de ~30 cm ni subir o bajar más de
   ~10 cm**. Si lo hace, repite la calibración del IMU antes de seguir.

---

## Piso sin espejo (cámara al frente) ⭐

**Quita el espejo.** El dron vuela a 60 cm y ve un tag de 8 cm en el piso entre ~1.0 y
~1.7 m adelante. Al verlo:

1. **centrar:** se detiene y se desliza de lado hasta tenerlo enfrente (no gira: sostiene
   el rumbo del tramo).
2. **recto:** avanza solo hacia adelante y mide su velocidad real con la distancia al tag.
3. **ciegas:** cuando el tag sale por abajo de la imagen, recorre lo que faltaba (~1 m) con
   esa velocidad, se detiene y ejecuta.

Si el tag se va por un costado, se desliza hacia él; no se va a ciegas. La consola y la HMI
muestran la fase.

Aterriza solo si el dron **no obedece** (pide subir y cae 15 cm en 0.7 s, o al revés) o si
**avanza solo** mientras se centra (40 cm en 2 s). Si pasa, no es un error de la misión:
haz "Revisar el dron".

**F1 — Un tag.** Tag **2** en el piso a **~1.7 m** frente al despegue. Deja libre el lado
izquierdo.

```bash
python scripts/mision_piso.py --record piso_m1.mp4
```

Debe avanzar, centrarse, ir recto, recorrer ~1 m a ciegas, detenerse **encima del tag**,
girar a la izquierda, avanzar ~10 s y aterrizar.

**Lo que hay que medir:** cuando se detiene para girar, ¿qué tan lejos queda la **nariz**
del centro del tag, adelante/atrás y de lado? Anótalo; el video también sirve. Anota
también lo que dice la consola en `... cm a ciegas, velocidad medida XX cm/s`.

- **Si dice `supuesta`** en vez de `medida`, no alcanzó a medir y usó `ciegas_cms` de
  `config/mission_piso.json`. Si así se queda corto, bájalo (por ejemplo, si le faltan 15 cm
  de 100, cambia 17 por ~14.5); si se pasa, súbelo.
- **Si dice `medida` y aun así se pasa o se queda corto siempre por lo mismo** (en
  simulación se pasa ~10 cm porque frena tarde), ajusta `ciegas_ajuste_cm` **en
  `config/mission_piso.json`** (no en el `.py`: el `.json` manda). Si se pasa 10 cm, ponlo en
  −10; si le faltan 10, en +10. Solo cuentan las corridas que **sí** llegaron al tramo a
  ciegas. Si el error cambia mucho entre corridas, no lo ajustes: anótalo.

**F2 — Tag girado y corrido.** Igual que F1, pero con el tag girado ~15–20° y corrido
~10 cm de lado. Debe centrarse de lado y girar 90° **respecto a su rumbo**, sin importar cómo
esté girado el tag (el reglamento pide eso).

**F3 — Circuito.** Visto desde arriba, con el dron mirando hacia "adelante":

```
                       [7]   ← 1.5 m adelante del 2
                        |
  [1] ──── 1.5 m ──── [2]
   |
 1.7 m
   |
 (dron)
```

```bash
python scripts/mision_piso.py --record piso_circuito.mp4
```

**F4 — Flip en el piso** (batería ≥ 70 % y ~1.7 m libres hacia arriba). Tag **4** a 1.7 m.
Mismo comando que F1.

## Flip solo (P1) — después de cambiar algo del flip

Confirma que el flip no deja al dron cerca del piso. Sube a 130 cm; en cuanto termina el
giro sube a fondo hasta frenar la caída, sostiene esa altura 2 s y baja suave a la de
crucero. Necesita batería ≥ 70 % y nada encima del dron hasta ~1.7 m.

```bash
python scripts/first_flight.py --flip-test b --record flip.mp4
```

En la consola debe aparecer, en orden:

1. `FLIP_CLIMB: subiendo a 130 cm para el flip`
2. `FLIP_TEST: flip b a ~130 cm`
3. `flip HECHO: ...`
4. `altura recuperada: ~70 cm, minima XX cm`

Al final aterriza solo.

**Aprueba si** la `minima` es de **40 cm o más**. Aprobó el 27-oct con 72–81 cm.

**Si no llega a 130 cm** (techo o red bajos), sale `flip omitido: no alcanzo 130 cm`. En ese
caso baja `flip_min_alt_cm` en `config/flight.json` (por ejemplo, a 115).

---

## Con espejo (cámara hacia abajo) ⭐

Con un espejo que cubre toda la cámara **no hay vista al frente**: el dron no ve paredes ni
obstáculos. Prueba en espacio abierto, con los tags en el piso. **Cada clip nuevo necesita
E1** para medir su inclinación.

Antes de volar con el clip: que esté firme, que el espejo esté limpio, que **no tape los
sensores de la panza** y que no quede más abajo que la base del dron.

Cómo vuela: sube a **100 cm**, avanza sosteniendo el rumbo hasta ver un tag debajo (hasta
12 s, ~2 m), se centra encima **sin girar** (aunque el tag esté girado), ejecuta y sigue. El
tag que está debajo al despegar se toma como el de inicio y **se ignora**. Se ajusta en
`config/mission_espejo.json`:

| Parámetro | Para qué |
|---|---|
| `cruise_alt_cm` | altura de vuelo; más alto ve más piso (a 100 cm: ±39 cm adelante, ±52 de lado) |
| `advance_fb`, `advance_timeout_s` | qué tan rápido y cuánto tiempo avanza buscando el siguiente tag |
| `ignorar_inicio` | `true` ignora el tag que ve al despegar. **En las pruebas va en `false`**: no hay tag de inicio especial y, si el tag 1 queda cerca del despegue, lo ignoraría (pasó el 9-nov). Para la competencia, decidir cuando se sepa cuál es el tag de inicio |
| `alinear_bordes` | `true` solo si los tags siempre van derechos respecto a la pista |
| `vista_adelante_deg`, `vista_lado_deg` | inclinación del clip, medida con E1 |

**E1 — Detección y orientación** (sin volar). Sostén el dron a ~80 cm sobre un tag en el piso:

```bash
python scripts/test_tags.py --source tello --espejo --tag-cm 8 --record espejo1.mp4
```

Revisa:

- `altura` igual a la cinta métrica (±5 cm).
- La flecha amarilla "ADELANTE" debe apuntar hacia la **nariz** del dron: con el tag frente
  a la nariz, `adelante` debe ser positivo. **Si sale al revés,** usa `--espejo h` aquí y en
  la misión, y pon `"espejo": "h"` en `config/mission_espejo.json`.
- Al salir se imprime `espejo: inclinacion de la vista ...`. **Copia esos dos números** a
  `config/mission_espejo.json` (`vista_adelante_deg` y `vista_lado_deg`). Sin ellos, el dron
  se coloca mal encima del tag (~11 cm de error a 80 cm con un espejo inclinado 8°).

**E2 — Estacionario y giro con espejo.** Aprueba si no deriva más que sin espejo y si el
espejo no se mueve.

```bash
python scripts/first_flight.py --yaw-test 90 --record espejo_giro.mp4
```

**E3 — Tag debajo, sin avanzar.** Tag 9 (pausa) en el piso, ~10–20 cm frente al despegue.
Debe colocarse encima, alinearse y hacer la pausa de 5 s.

```bash
python scripts/mision_espejo.py --quieto --record espejo_quieto.mp4
```

**E4 — Avanzar y encontrar el tag.** Tag 2 en el piso ~1 m adelante, con el lado izquierdo
libre. Avanza despacio, se coloca encima, gira a la izquierda, avanza 8 s y aterriza.

```bash
python scripts/mision_espejo.py --record espejo_m1.mp4
```

**E5 — Circuito en el piso.** Tag 1 a 80 cm al frente; tag 2 a 70 cm a la derecha del 1;
tag 7 a 70 cm adelante del 2. Mismo comando que E4.

**E6 — Flip con espejo** (batería ≥ 70 %, ~1.7 m libres arriba, **solo con el clip firme**).
Tag 4 a ~1 m adelante; luego el 8. Mismo comando que E4. Revisa después del flip que el
espejo no se haya movido (si se movió, repite E1).

**E7 — Ensayo de competencia.** Arma un recorrido con varios tags en un orden al azar (por
ejemplo 9 → 1 → 3 → 4 → 2 → 7), con 0.7–1.5 m entre ellos y un tag que no sea del 1 al 10, o
cualquiera, debajo del despegue como "inicio". Haz **3 intentos** cronometrados, como en la
competencia, y anota cuántos tags ejecutó bien cada uno. Mismo comando que E4.

---

## Pruebas de pared (ya no son prioridad)

Los tags irán en el piso, pero estas pruebas siguen sirviendo para probar acciones, flips
y control con la misión de pared (`scripts/mission_tags.py`). Montaje común: tag pegado
**vertical** en una caja, con el centro a ~80 cm del piso, a ~2 m frente al despegue.

| Prueba | Montaje y comando | Aprueba si |
|---|---|---|
| **P2** flip en misión | tag **4**; espacio libre detrás (el flip es hacia atrás). `python scripts/mission_tags.py --record mision_flip.mp4` | en "ejecutados": `4=Flip 360 (flip HECHO) (minima tras el flip XX cm)` con XX ≥ 40 |
| **P3** calibración de `rc` | cualquier tag de 8 cm a ~90 cm de altura y ~1.5 m; ~1 m libre alrededor. `python scripts/rc_calib.py --record rccal.mp4` (dura ~70 s; `--ejes fb lr` para la versión corta) | imprime la tabla y la guarda en `capturas/rc_calib_*.txt` |
| **P4** tag alto | tag **2** a ~105 cm de altura. `python scripts/mission_tags.py --record mision_alto.mp4` | sube de ~80 a ~100 cm mientras se acerca y ejecuta |
| **P5** tag girado | tag **2** con la caja girada ~25° y el dron ladeado ~10°. `python scripts/mission_tags.py --record mision_alineado.mp4` | `EXECUTE: tag 2 ... a ~60–70 cm, lateral ±5 cm, angulo ±3` |
| **P6** tag 8 | como P2 con el tag **8** (el flip sale hacia adelante). `python scripts/mission_tags.py --record mision_flip8.mp4` | gira 180°, voltea y recupera altura |
| **P7** tags de 15 cm | como P2 o P5. `python scripts/mission_tags.py --mission config/mission_tags_15cm.json --record mision_15cm.mp4` | igual que con los de 8 cm |
| **P8** enlace WiFi | sin volar: `python scripts/test_tags.py --source tello --tag-cm 8` 60 s; luego `sudo iw dev <interfaz> set power_save off` y repetir | menos frames > 100 ms y un máximo menor en la línea `enlace:` |

---

## Al terminar (2 min)

```bash
python scripts/resumen_vuelos.py
```

Imprime un **VEREDICTO** por cada vuelo de hoy y lo guarda en
`capturas/resumen_sesion_*.txt`:

- altura antes y después de cada flip, con `OK` o `PELIGRO`;
- tags ejecutados, problemas, batería y temperatura;
- la tabla de calibración de `rc` y las líneas del enlace.

Anota también lo que las bitácoras no ven: si tocó la red, si se movió raro, si algún paro
fue a mano y por qué. **Súbelo al repo** (también en cada pausa, no solo al final):

```bash
python scripts/guardar_sesion.py --notas "qué se probó, qué salió y qué se vio"
```

Luego haz commit y push de `sesiones/`. Al cerrar el día, agrega una entrada a
[`bitacora.md`](bitacora.md). Para ver un vuelo estado por estado:
`python scripts/traza_vuelo.py logs/<archivo>.csv`.

## Reglas rápidas

| Situación | Qué hacer |
|---|---|
| `NO despega: temperatura` | Apaga el dron y pon el ventilador 3–5 min. No lo dejes encendido con el programa abierto. |
| `NO despega: bateria` | Cambia de batería (el mínimo para despegar es 30 %). |
| `no subio ... algo tapa el sensor tof` | Algo tapa el sensor de abajo (un clip, cinta). Revísalo. |
| `flip omitido: bateria` | La batería bajó de 50 %. Cambia de batería y repite. |
| `flip omitido: no alcanzo` | Techo o red bajos: baja `flip_min_alt_cm` en `config/flight.json`. |
| `el dron no obedece` / `avanza solo` | Problema del dron: haz "Revisar el dron". |
| El dron va hacia algo | **ESPACIO**. `k` solo si va hacia una persona. |
| Quieres repetir una prueba | Mismo comando, otro nombre en `--record`. |

## Registro rápido (a mano)

| Prueba | Batería inicio | ¿Aprobó? | Tags ejecutados / distancia al tag | Notas |
|---|---|---|---|---|
| Estacionario con clip | | | — | |
| E1 inclinación | — | | — | adelante ___° lado ___° |
| E3 tag debajo | | | | |
| E4 un tag | | | | |
| E5 circuito | | | | |
| E6 flip | | | | |
| E7 intento 1 | | | __ de __ | tiempo: |
| E7 intento 2 | | | __ de __ | tiempo: |
| E7 intento 3 | | | __ de __ | tiempo: |
