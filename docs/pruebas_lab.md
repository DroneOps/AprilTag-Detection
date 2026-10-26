# Pruebas de laboratorio — sesión corta

Todo el código ya está listo en la laptop. Esta guía es para llegar y solo
ejecutar comandos. Las pruebas van **en orden de prioridad**: si se acaba el
tiempo, lo que falte es lo menos importante.

Tiempo estimado: **~30 min para P1–P5**, contando cambios de batería.

> **Estado al 24-oct:** P3, P4 y P5 aprobadas. **Pendientes:** P1 (repetir: se
> corrigió la recuperación tras el flip, que dejó caer el dron de 117 a 39 cm),
> P2 y P6 (no se corrieron), y P7 (faltan tags de 15 cm). La próxima sesión
> empieza por **P1 → P2 → P6**.

---

## Antes de salir

- [ ] **Baterías cargadas**: idealmente 3 al 90–100 %. Los flips necesitan > 50 % *en el momento del flip*.
- [ ] **Ventilador pequeño**: el Tello pasa de 60 a 85 °C en ~5 min en tierra y arriba de 80 °C no despega.
- [ ] Tags de 8 cm ya impresos: **2, 3, 4 y 8** (están en `tags/tags_8cm.pdf`).
- [ ] Opcional: los mismos de 15 cm (`tags/tags_15cm.pdf`).
- [ ] Cinta métrica, cinta adhesiva, cajas para pegar los tags.

## Al llegar (5 min)

1. Abre una terminal y entra al proyecto:
   ```bash
   source /home/faraday/venv-ardupilot/bin/activate
   ```
   ```bash
   cd /home/faraday/AprilTag-Detection
   ```
2. **Espacio de vuelo**: ~2 m libres alrededor y **~1.7 m libres hacia arriba**,
   porque antes de cada flip el dron ahora sube a 130 cm (y puede pasarse un poco).
3. Recordatorios de seguridad:
   - Una persona en el teclado, con la ventana enfocada y el dedo sobre **ESPACIO** (paro = aterrizaje).
   - `k` mata motores (el dron cae): úsala **solo** si va hacia una persona.
4. Cada prueba lleva `--record` con un **nombre distinto**, para no sobrescribir videos.

---

## P1 — Flip solo, con subida previa ⭐ (3 min, batería ≥ 70 %)

**Para qué:** confirmar que el flip ya no deja al dron cerca del piso. En
pruebas reales cayó de 77 cm al piso, a 20 cm en una misión y de 117 a 39 cm
el 24-oct (la recuperación se daba por buena mientras seguía cayendo). Ahora
sube a 130 cm, no baja durante 3 s tras el flip y solo da por recuperada una
altura estable.

**Montaje:** espacio abierto; nada encima del dron hasta ~1.7 m.

```bash
python scripts/first_flight.py --flip-test b --record flip3.mp4
```

**Qué debe pasar** (la consola lo va diciendo):

1. `FLIP_CLIMB: subiendo a 130 cm para el flip`
2. `FLIP_TEST: flip b a ~130 cm`
3. `flip HECHO: ...`
4. `altura recuperada: ~70 cm, minima XX cm`: la **mínima** es la que importa.
5. Aterriza solo.

**Aprueba si:** la `minima` es de **40 cm o más**. En simulación sale ~65 cm.

**Si no llega a 130 cm** (techo o red baja): sale `flip omitido: no alcanzo 130 cm`.
Baja `flip_min_alt_cm` en `config/flight.json` (por ejemplo, a 115). Es el único
cambio de configuración que vale la pena hacer en el momento.

## P2 — Misión con tag 4 (flip en misión) ⭐ (4 min, batería ≥ 70 %)

**Montaje:**

- Tag **4** pegado **vertical** en una caja, con el centro a **~80 cm** del piso (la altura de crucero).
- Caja a **~2 m** frente al despegue.
- Espacio libre **detrás** del dron: el flip es hacia atrás, lejos del tag.

```bash
python scripts/mission_tags.py --record mision_flip5.mp4
```

**Qué debe pasar:**

1. Sube o baja a 80 cm (`CRUISE`).
2. Avanza, se acerca y se alinea frente al tag.
3. Sube a 130 cm, hace el flip **hacia atrás** y recupera la altura.
4. Avanza un poco, se detiene frente al tag y aterriza a los 6 s.

Si te pones nervioso cuando avanza hacia la caja después del flip, presiona `q`:
la prueba ya se cumplió.

**Aprueba si:** en la HMI, en "ejecutados", aparece
`4=Flip 360 (flip HECHO) (minima tras el flip XX cm)` con XX de 40 o más.

## P3 — Calibración de rc (4 min, batería ≥ 60 %)

**Para qué:** medir cuánto se mueve el dron realmente con rc 10, 15 y 20
(adelante, de lado y arriba/abajo). Con ese dato ajusto los mínimos de la
misión sin adivinar.

**Montaje:**

- Cualquier tag del 1 al 10, de 8 cm, pegado **vertical** con el centro a **~90 cm** de altura.
- A **~1.5 m** frente al despegue.
- ~1 m libre a los lados y detrás del dron.

```bash
python scripts/rc_calib.py --record rccal1.mp4
```

**Qué debe pasar:**

- Sube a 90 cm y da 18 pasos cortos (1.5 s moviéndose y 1.5 s quieto).
- Se ve como un baile lento: adelante y atrás, de lado, arriba y abajo.
- Dura ~70 s y aterriza solo.
- Al final imprime una tabla y la guarda en `capturas/rc_calib_*.txt`.

Si algún paso dice `omitido`, no pasa nada: el programa lo saltó para no salirse de la zona segura.

**Si tienes poca batería o poco tiempo:** `--ejes fb lr` hace solo adelante y lado (~45 s).

## P4 — Tag alto: seguimiento vertical (4 min, batería ≥ 50 %)

**Para qué:** la vez pasada un tag más alto que el vuelo se salió de la
imagen por arriba (misión 130227). Ahora el dron debe subir mientras se acerca.

**Montaje:** tag **2** (izquierda 90°) con el centro a **~105 cm** del piso
(unos 25 cm arriba del vuelo), a ~2 m. Deja libre el lado izquierdo.

```bash
python scripts/mission_tags.py --record mision_alto.mp4
```

**Qué debe pasar:** mientras se acerca, en la HMI la altura sube de ~80 a
~100 cm. Llega a ~60 cm del tag, se alinea y gira a la izquierda.

**Aprueba si:** ejecuta el tag sin perderlo. Un tag a más de ~125 cm no se ve
desde la altura de crucero, y eso es esperado.

## P5 — Tag girado y despegue ladeado (4 min, batería ≥ 50 %)

**Para qué:** verificar que se pone de frente al tag aunque despegue chueco o
el tag esté girado. Los giros quedan referidos **al tag**: si la caja está
girada respecto a la pista, el dron termina igual de girado respecto a las
líneas, y eso es lo correcto. Para comprobar el giro contra la pista, pon la
caja derecha (paralela a las líneas) y solo el dron ladeado.

**Montaje:**

- Tag **2** a ~80 cm de altura y ~2 m, con la caja **girada ~25°**.
- Pon el dron **ladeado ~10°** respecto a las líneas de la pista.

```bash
python scripts/mission_tags.py --record mision_alineado2.mp4
```

**Aprueba si:**

- La consola dice `EXECUTE: tag 2 ... a ~60–70 cm, lateral ±5 cm, angulo ±3`.
- Al ejecutar, el dron queda de frente a la cara de la caja; después del giro, a 90° de esa cara.
- Si la caja estaba derecha respecto a la pista, el dron termina paralelo o perpendicular a las líneas.

---

### Si sobra tiempo

**P6 — Tag 8 (giro 180° + flip hacia adelante)** (4 min, batería ≥ 70 %).
Mismo montaje que P2, pero con el tag **8**. Después de girar 180° el flip sale
**hacia adelante**, lejos del tag, así que deja libre el espacio entre la caja
y el punto de despegue.

```bash
python scripts/mission_tags.py --record mision_flip8.mp4
```

**P7 — Tags de 15 cm** (4 min). Mismo montaje que P2 o P5, pero con tags de 15 cm:

```bash
python scripts/mission_tags.py --mission config/mission_tags_15cm.json --record mision_15cm.mp4
```

**P8 — Calidad del enlace** (3 min, **sin volar**: el dron en la mesa).
Primero con el ahorro de energía del WiFi **encendido**, que es el estado normal:

```bash
python scripts/test_tags.py --source tello --tag-cm 8
```

Deja 60 s apuntando a cualquier lado y sal con `q`. Luego ve el nombre de tu interfaz WiFi:

```bash
iw dev
```

Apaga el ahorro de energía. Cambia `wlp2s0` por el nombre que te salió:

```bash
sudo iw dev wlp2s0 set power_save off
```

Repite la primera prueba 60 s. Compara las dos líneas `enlace:` que se
imprimen al salir: lo que buscamos es que haya menos frames de más de 100 ms y
que el máximo sea menor.

---

## Pruebas con espejo (cámara hacia abajo, tags en el piso)

Con el espejo cubriendo toda la cámara **no hay vista al frente**: el dron no ve
paredes ni obstáculos. Prueba en espacio abierto, con los tags en el piso.

**E1 — Detección y orientación** (sin volar). Sostén el dron a ~80 cm sobre un tag en el piso:

```bash
python scripts/test_tags.py --source tello --espejo --tag-cm 8 --record espejo1.mp4
```

Revisa:

- `altura` igual a la cinta métrica (±5 cm).
- La flecha amarilla "ADELANTE" debe apuntar hacia la **nariz** del dron. Con el tag frente a la nariz, `adelante` debe ser positivo.
  **Si sale al revés:** usa `--espejo h` aquí y en la misión, y pon `"espejo": "h"` en `config/mission_espejo.json`.
- Al salir se imprime `espejo: inclinacion de la vista ...`. **Copia esos dos números** a
  `config/mission_espejo.json` (`vista_adelante_deg`, `vista_lado_deg`). Sin ellos, el dron
  se coloca mal encima del tag (~11 cm de error a 80 cm con un espejo inclinado 8°).

**E2 — Estacionario y giro con espejo:**

```bash
python scripts/first_flight.py --yaw-test 90 --record espejo_giro.mp4
```

Aprueba si no deriva más que sin espejo y si el espejo no se mueve.

**E3 — Tag debajo, sin avanzar.** Pon el tag 9 (pausa) en el piso, ~10–20 cm frente al despegue:

```bash
python scripts/mision_espejo.py --quieto --record espejo_quieto.mp4
```

Debe colocarse encima, alinearse con los bordes del tag y hacer la pausa de 5 s.

**E4 — Avanzar y encontrar el tag.** Pon el tag 2 en el piso, ~1 m adelante; el lado izquierdo debe quedar libre:

```bash
python scripts/mision_espejo.py --record espejo_m1.mp4
```

Avanza despacio, se coloca encima, gira a la izquierda, avanza 8 s y aterriza.

**E5 — Circuito en el piso:** tag 1 a 80 cm al frente; tag 2 a 70 cm a la derecha del 1;
tag 7 a 70 cm adelante del 2. Mismo comando que E4.

Los flips con espejo, **solo con el montaje firme**.

## Al terminar (2 min)

```bash
python scripts/resumen_vuelos.py
```

Imprime un resumen de cada vuelo de hoy con un **VEREDICTO**:

- Altura antes y después de cada flip, con `OK` o `PELIGRO`.
- Tags ejecutados, problemas, batería y temperatura.
- La tabla de calibración de rc y las líneas del enlace.

Lo guarda en `capturas/resumen_sesion_*.txt`. Yo puedo leer eso, las
bitácoras y los videos directamente; no hace falta copiar nada.

Anota también lo que las bitácoras no ven: si tocó la red, si se movió raro,
si algún paro fue a mano y por qué.

## Reglas rápidas

| Situación | Qué hacer |
|---|---|
| `NO despega: temperatura` | Apaga el dron, ventilador 3–5 min. No lo dejes encendido con el programa abierto. |
| `NO despega: bateria` | Cambia de batería (el mínimo para despegar es 30 %). |
| `flip omitido: bateria` | La batería bajó de 50 %. Cambia de batería y repite. |
| `flip omitido: no alcanzo` | Techo o red bajos: baja `flip_min_alt_cm` en `config/flight.json`. |
| El dron va hacia algo | **ESPACIO**. Solo `k` si va hacia una persona. |
| Quieres repetir una prueba | Mismo comando, otro nombre en `--record`. |

## Registro rápido (a mano)

| Prueba | Batería inicio | ¿Aprobó? | Notas |
|---|---|---|---|
| P1 flip solo | | | |
| P2 misión tag 4 | | | |
| P3 calibración rc | | | |
| P4 tag alto | | | |
| P5 tag girado | | | |
| P6 tag 8 | | | |
| P7 tags 15 cm | | | |
| P8 enlace | — | | |
