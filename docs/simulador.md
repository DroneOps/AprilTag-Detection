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
python sim/sim_world.py todos > sim/logs/regresion.txt 2>&1   # los ~40, unos 10 min
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

## Qué modela (ajustado a vuelos reales)

- **Horizontal:** `1.7·(|rc| − 5)` cm/s, con respuesta de ~0.4 s.
- **Vertical:** `0.9·(|rc| − 3)` subiendo y `0.5·(|rc| − 3)` bajando.
- **Giro:** `0.73·(|rc| − 6.6)` °/s.
- **Despegue:** sube a 65 cm y contesta `ok`.
- **Tras un flip:** cae ~50 cm/s de 1 a 3 s, y subir a fondo lo frena.
- **Sensores:** `h` que deriva y tof con ruido.
- **Viento:** aleatorio, más un empuje fijo opcional (`bias`).
- **En piso**, por defecto:
  - se hunde 15 cm/s al avanzar;
  - pedir adelante y de lado a la vez lo frena (×0.55).
- El paso de la física usa el **tiempo real transcurrido**. Con un paso fijo, cuando el CPU
  se saturaba el dron iba más lento y falseaba las velocidades.

El simulador es **optimista**: no modela desenfoque, IMU descalibrado ni hélices dañadas.
Si algo falla en simulación, seguro falla en el dron; al revés no.

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
| `espejo_uno`, `espejo_circuito` | centrarse encima, alinearse y ejecutar |
| `espejo_quieto` | sin avanzar: el tag ya está debajo, corrido y girado |
| `espejo_deriva`, `espejo_flip` | viento y flip con espejo |
| `espejo_inclinado`, `espejo_inclinado_sin_config` | espejo inclinado 8°, con y sin la medida en la config |

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
