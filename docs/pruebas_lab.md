# Pruebas de laboratorio — sesión corta

Todo el código ya está listo en la laptop. Esta guía es para llegar y solo
ejecutar comandos. Las pruebas van **en orden de prioridad**: si se acaba el
tiempo, lo que falte es lo menos importante.

Tiempo estimado: **~30 min para P1–P5**, contando cambios de batería.

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
2. **Espacio de vuelo**: ~2 m libres alrededor y **~1.5 m libres hacia arriba**,
   porque antes de cada flip el dron ahora sube a 120 cm.
3. Recordatorios de seguridad:
   - Una persona en el teclado, con la ventana enfocada y el dedo sobre **ESPACIO** (paro = aterrizaje).
   - `k` mata motores (el dron cae): úsala **solo** si va hacia una persona.
4. Cada prueba lleva `--record` con un **nombre distinto**, para no sobrescribir videos.

---

## P1 — Flip solo, con subida previa ⭐ (3 min, batería ≥ 70 %)

**Para qué:** confirmar que el flip ya no deja al dron cerca del piso. La vez
pasada bajó de 77 cm al piso y en una misión quedó a 20 cm.

**Montaje:** espacio abierto; nada encima del dron hasta ~1.5 m.

```bash
python scripts/first_flight.py --flip-test b --record flip3.mp4
```

**Qué debe pasar** (la consola lo va diciendo):

1. `FLIP_CLIMB: subiendo a 120 cm para el flip`
2. `FLIP_TEST: flip b a ~120 cm`
3. `flip HECHO: ...`
4. `altura recuperada: ~65 cm`
5. Aterriza solo.

**Aprueba si:** nunca baja de ~30 cm después del flip.

**Si no llega a 120 cm** (techo o red baja): sale `flip omitido: no alcanzo 120 cm`.
Baja `flip_min_alt_cm` en `config/flight.json` (por ejemplo, a 100). Es el único
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
3. Sube a 120 cm, hace el flip **hacia atrás** y recupera la altura.
4. Avanza un poco, se detiene frente al tag y aterriza a los 6 s.

Si te pones nervioso cuando avanza hacia la caja después del flip, presiona `q`:
la prueba ya se cumplió.

**Aprueba si:** en la HMI, en "ejecutados", aparece `4=Flip 360 (flip HECHO)`, y no baja de ~30 cm.

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

**Para qué:** verificar con el código nuevo que se pone de frente al tag y que
el giro queda referido a la pista.

**Montaje:**

- Tag **2** a ~80 cm de altura y ~2 m, con la caja **girada ~25°**.
- Pon el dron **ladeado ~10°** respecto a las líneas de la pista.

```bash
python scripts/mission_tags.py --record mision_alineado2.mp4
```

**Aprueba si:**

- La consola dice `EXECUTE: tag 2 ... a ~60–70 cm, lateral ±5 cm, angulo ±3`.
- Después del giro, el dron queda paralelo o perpendicular a las líneas de la pista.

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
