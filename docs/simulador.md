# Simulador (`sim/sim_world.py`)

Prueba las misiones **sin volar**. Dibuja lo que vería la cámara del Tello (con su
calibración y su inclinación de 11° reales) en un mundo 3D con tags, y la misión corre
**sin cambios**: el mismo detector, el mismo PnP y la misma máquina de estados. Solo
cambia el dron, que es un `SimTello` con la misma interfaz que djitellopy.

**Regla del equipo: todo cambio de control se prueba aquí antes de volar.**

## Uso

```bash
python sim/sim_world.py piso_uno                    # un escenario, con salida en consola
```
```bash
python sim/sim_world.py piso_uno piso_circuito      # varios, en paralelo de 4 en 4
```
```bash
python sim/sim_world.py todos > sim/logs/regresion.txt 2>&1   # los ~46, unos 12 min
```

Corre en tiempo real: cada escenario tarda 30–70 s. Para `todos`, mándalo a un archivo
y en segundo plano. Más de 4 a la vez satura el CPU y la visión se atrasa.

Al final de cada escenario imprime una línea como esta:

```
===== piso_uno: final DONE | choque: None | min pared 49 cm | ejecutados: ['2=Giro izquierda 90'] | ... | altura min en vuelo 49 cm
```

Le siguen los cambios de estado con la **posición verdadera** del dron
(`[x=… y=… z=… yaw=…]`, en cm; los tags están donde los pone el escenario). La bitácora
completa queda en `sim/logs/<escenario>.csv`, con el mismo formato que las de vuelo real.

## Qué modela: `config/sim_tello.json`

Cómo se comporta el dron simulado está en **`config/sim_tello.json`**, ajustado con las
bitácoras reales por `sim/comparar_vuelos.py` (ver abajo). Con `--ideal` se usa el modelo
de antes del 11-nov, que era más optimista:

```bash
python sim/sim_world.py espejo_circuito --ideal
```

| Qué | Realista (JSON, 9-nov) | Ideal (`--ideal`) |
|---|---|---|
| Horizontal | `1.45·(\|rc\| − 5)` cm/s, respuesta ~0.75 s | `1.7·(\|rc\| − 5)`, ~0.4 s |
| Vertical | `0.4·(\|rc\| − 3)` subiendo, `0.15·…` bajando | `0.9·…` y `0.5·…` |
| Giro | `0.75·(\|rc\| − 14)` °/s: con rc 15 casi no gira | `0.73·(\|rc\| − 6.6)` |
| Tras soltar un giro | sigue girando ~8° más, despacio (~2 s) | se detiene en ~0.15 s |
| Atraso del video | 170 ms | 0 |
| Deriva con rc en 0 | ~5 cm/s, aleatoria | ~2 cm/s |
| Hundimiento al avanzar | 1 cm/s | 15 cm/s solo en piso |
| Despegue | sube a 65–74 cm (+9 de pico); "ok" a los 4.5–7.8 s | 65 cm; "ok" a los 2.2 s |
| Temperatura | empieza en 65 °C y sube 6.5 °C/min volando | siempre 65 °C |

En los dos modos:

- **Tras un flip:** cae ~50 cm/s de 1 a 3 s, y subir a fondo lo frena.
- **Sensores:** `h` que deriva y tof con ruido.
- **Viento:** aleatorio, más un empuje fijo opcional (`bias`).
- **En piso**, pedir adelante y de lado a la vez lo frena (×0.55; `combo`).
- El paso de la física usa el **tiempo real transcurrido**. Con un paso fijo, cuando el CPU
  se saturaba el dron iba más lento y falseaba las velocidades.

**Despegues que fallan** (escenarios aparte, como el 9-nov): `despegue="cae"` sube ~40 cm y
regresa al piso mientras su `h` dice que sube; `"alto"` sube solo a ~141 cm; `"sin_ok"` no
contesta "ok" (pasó en 2 de 14 despegues).

Aun así, el simulador no modela desenfoque, IMU descalibrado, hélices dañadas ni el
sistema de visión de la panza. Si algo falla en simulación, seguro falla en el dron; al
revés no.

## ¿Se parece al dron? `sim/comparar_vuelos.py`

Le pasa al modelo del simulador los mismos `rc` que recibió el dron en vuelos reales y
compara lo que hizo cada uno: rumbo, altura y, con espejo, la posición del tag. También
compara despegue, deriva y temperatura. Tarda segundos.

```bash
python sim/comparar_vuelos.py                       # la sesión más reciente de sesiones/
```
```bash
python sim/comparar_vuelos.py sesiones/2026-11-09 --ajustar            # sugiere valores
```
```bash
python sim/comparar_vuelos.py sesiones/2026-11-09 --ajustar --guardar  # y los escribe
```

**Córrelo al terminar cada sesión de laboratorio** ([`laboratorio.md`](laboratorio.md)).
Si cambias de Tello o de clip, reajusta con los vuelos nuevos. `--ajustar` solo mueve un
valor si mejora el error al menos 1 %, así que con pocos datos deja lo que había. El
atraso del video no se ajusta: se midió aparte (~170 ms, [`tello.md`](tello.md)).

Con los 14 vuelos del 9-nov:

| | real | modelo ideal | ajustado |
|---|---|---|---|
| Giro con rc 15–19 (°/s) | −1.0 | 6.1 | −1.4 |
| Giro con rc 50+ (°/s) | 37.5 | 36.4 | 37.4 |
| Sigue girando tras un giro (°) | 8.0 | −4.4 | 8.0 |
| Subir con rc 10–19 (cm/s) | 4.2 | 11.5 | 5.3 |
| Error al predecir 1.5 s de rumbo | | 1.2° | 0.9° |
| Error al predecir 1.5 s de altura | | 6.2 cm | 4.6 cm |
| Error al predecir 1.5 s de posición del tag | | 14.2 cm | 10.0 cm |

Ojo: son pocos datos (128 tramos de 1.5 s; solo 37 con tag visible). En los vuelos de
octubre, sin el clip actual, el dron casi no seguía girando tras los giros (2° en 23 giros,
contra 8° en los 3 del 9-nov). Por eso el ajuste usa solo el 9-nov, que es el clip y los
drones de ahora. Cada sesión nueva lo mejora.

### Regresión con el dron realista (11-nov)

Los 46 escenarios con `config/sim_tello.json` contra `--ideal` (bitácoras locales en
`sim/logs/regresion_realista.txt` y `regresion_ideal.txt`):

- **Espejo (misión principal):** todo pasa igual, salvo `espejo_inicio`, que falló 1 de 5
  veces. Entre el despegue y la subida a 100 cm pasan ~12 s, y con la deriva medida
  (~5 cm/s) el dron se corrió 35 cm de lado. A 100 cm la cámara ve ±52 cm de lado, así que
  pasó junto al tag 2 sin verlo. Es lo mismo que pasó el 9-nov ("se iba a la derecha").
  También se ve el rumbo que sigue girando tras un giro (−90° → −93°).
- **Despegues que fallan:** `espejo_despegue_cae` aterriza con el aviso "el despegue se vino
  abajo"; `espejo_despegue_alto` y `espejo_sin_ok` completan el recorrido.
- **Piso:** todo pasa salvo `piso_hundimiento`. Es una prueba de estrés que lo hunde
  20 cm/s, y con lo que de verdad sube el Tello (~0.4·rc) no lo compensa; aterriza a salvo.
- **Pared (ya no se usa):** `circuito`, `ladeado`, `angulo38_deriva` y `tag_alto` ya no
  completan, y `pausa` choca con la pared. No se corrigió: esa misión ya no es prioridad.

Con la deriva aleatoria **el resultado puede cambiar entre corridas**. Si un escenario
falla, repítelo (`python sim/sim_world.py espejo_inicio espejo_inicio espejo_inicio`) para
saber si falla siempre o solo a veces.

## Escenarios

**Tags en pared** (`mission_tags.py`)

| Escenario | Qué prueba |
|---|---|
| `circuito` | 1 → 2 → 7 con un tag señuelo (ID 29) y el tag 1 desplazado |
| `pausa`, `giro360`, `sube_ciego` | tags 9, 10 y 5; tras subir, el tag deja de verse |
| `perdido` | el tag se pierde: debe buscarlo y aterrizar |
| `caja` | caja de 35 cm en el camino: pasa por encima sin falsos avisos |
| `deriva`, `deriva_sin_lateral` | viento lateral; la segunda apaga la corrección lateral (debe fallar) |
| `ladeado`, `ladeado_sin_alinear` | despega girado 8° |
| `angulo25`, `angulo38`, `angulo38_deriva` | tag girado respecto a la pista |
| `tag_alto`, `tag_bajo` | tag arriba o abajo de la altura de crucero |
| `flip4`, `flip8`, `flip4_bateria` | flip en misión; con 45 % de batería se omite |
| `flip_prueba`, `flip_prueba_bateria` | `first_flight.py --flip-test b` |
| `rc_calib`, `sin_tags` | calibración de `rc`; sin tags debe aterrizar |

**Con espejo** (`mision_espejo.py`)

| Escenario | Qué prueba |
|---|---|
| `espejo_uno`, `espejo_circuito` | centrarse encima sosteniendo el rumbo y ejecutar |
| `espejo_inicio` | despega encima de un tag 7: debe ignorarlo y seguir al siguiente |
| `espejo_cerca` | tag a 35 cm que solo se ve ya arriba: no es el de inicio, debe ejecutarlo |
| `espejo_girado` | tag girado 30°: el giro de 90° es respecto al rumbo, no al tag |
| `espejo_quieto` | sin avanzar: el tag ya está debajo, corrido y girado |
| `espejo_deriva`, `espejo_flip` | viento y flip con espejo |
| `espejo_inclinado`, `espejo_inclinado_sin_config` | espejo inclinado 8°, con y sin la medida en la config |
| `espejo_despegue_cae` | el despegue sube ~40 cm y regresa al piso: aterrizar con aviso |
| `espejo_despegue_alto` | el despegue sube solo a ~141 cm: bajar a crucero y seguir |
| `espejo_sin_ok` | el Tello no contesta "ok" al despegar: seguir tras asentarse |

**Tags en el piso, cámara al frente** (`mision_piso.py`)

| Escenario | Qué prueba |
|---|---|
| `piso_uno`, `piso_circuito` | un tag; circuito 1 → 2 → 7 |
| `piso_girado`, `piso_lado` | tag girado y corrido; tag muy de lado (debe centrarse, no irse a ciegas) |
| `piso_lento`, `piso_rapido` | el dron va 28 % más lento o 15 % más rápido: la velocidad medida lo compensa |
| `piso_hundimiento` | se hunde 20 cm/s: sostener altura |
| `piso_tof_falso` | el tof marca 14 cm durante 0.4 s: no debe aterrizar ni brincar |
| `piso_imu_mal` | se va solo hacia adelante y abajo: debe aterrizar antes del piso |
| `piso_deriva`, `piso_flip` | viento lateral; flip encima del tag |

## Agregar un escenario

En `scenario()` agrega una rama `elif sc == "mi_escenario":` que llame a
`run(sc, [tags], ...)`. Los tags de piso se crean con el ayudante `floor(id, x, y, giro)`.
Luego agrega el nombre a la lista `ALL` y al docstring del archivo. Las opciones de `run()`
(`bias`, `speed_factor`, `sag`, `glitches`, `imu_mal`, `mirror`, `boxes`, `bat`...) cubren la
mayoría de los casos.
