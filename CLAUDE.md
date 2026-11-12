# Instrucciones para Claude

Proyecto del grupo de drones del Tec para la categoría **Drones autónomos – Detector de
AprilTags** del Autonomous Mechatronics Grand Prix 2026 (5 de diciembre de 2026, Campus
Hidalgo). Un DJI Tello estándar, controlado desde una laptop por WiFi, recorre una pista con
etiquetas AprilTag tag25h9 **en el piso**, detecta cada una y ejecuta su acción. La
estrategia principal es un **espejo** frente a la cámara que la hace ver hacia abajo
(`scripts/mision_espejo.py`).

El equipo trabaja en español: responde siempre en español, claro y con comandos listos para
copiar. Varias personas trabajan en este repo y el responsable (Fernando) revisa el avance
desde GitHub cuando no está en el laboratorio.

## Lee primero

1. `docs/bitacora.md`: **"Pendiente ahora"** y lo que pasó en cada sesión. Empieza aquí.
2. `docs/laboratorio.md`: el protocolo de pruebas con el dron, en orden.
3. `docs/tello.md`: lo que medimos del dron real. Casi todo el código sale de aquí.
4. `docs/arquitectura.md` y `docs/simulador.md`, antes de tocar código.
5. `sesiones/<fecha más reciente>/notas.md`: lo último que se probó.

## Regla número uno: todo se guarda en el repo, en cuanto pasa

Fernando sigue el proyecto por GitHub. Nada debe quedarse solo en la laptop.

- **Al empezar a trabajar:** `git pull --rebase`.
- **Después de CADA acción con resultado**, haz commit y push de inmediato. No acumules
  varias acciones en un commit al final del día. Cuenta como acción:
  - un cambio de código o de configuración;
  - una prueba en el simulador con conclusión;
  - un vuelo o grupo de vuelos;
  - un documento.
  ```bash
  git add <archivos> && git commit -m "<mensaje>" && git pull --rebase && git push
  ```
- **Después de cada vuelo o tanda de vuelos** en el laboratorio, guarda la sesión con lo que
  la persona observó (qué hizo el dron, qué salió bien o mal) y súbela:
  ```bash
  python scripts/guardar_sesion.py --notas "E5: ejecutó 1 y 2; en el 7 se pasó ~15 cm; el clip se movió tras el aterrizaje"
  ```
  ```bash
  git add sesiones/ && git commit -m "Sesión: E5 con clip nuevo" && git pull --rebase && git push
  ```
  Se puede correr varias veces en el mismo día: agrega notas y bitácoras nuevas.
- **Al cerrar el día:** agrega una entrada a `docs/bitacora.md` (qué se probó, qué se aprendió,
  qué se cambió), actualiza su sección "Pendiente ahora" y súbelo.
- Los mensajes de commit y las notas deben decir **qué se hizo y qué salió**, no solo
  "cambios" o "pruebas". Quien revisa no estuvo ahí.

## Commits

- Mensajes **cortos y en español** que describan el cambio, por ejemplo
  `Espejo: avanzar 15 s entre tags` o `Sesión: E3 y E4 con clip ajustado`.
- **Sin ninguna firma o marca de IA:** nunca agregues `Co-Authored-By`, "Generated with
  Claude", emojis de robot ni nada parecido, ni en commits ni en PR. El autor es la persona
  (su `git config user.name`).
- Se trabaja directo en `main`, con `git pull --rebase` antes de cada push. Si hay
  conflicto, resuélvelo conservando los cambios de ambos; si no está claro, pregunta.
- Nunca `git push --force`, nunca reescribas la historia de `main` y nunca borres trabajo de
  otros sin preguntar.
- **No se sube:**
  - videos (`*.mp4`);
  - `logs/` y `capturas/` crudos (para eso está `sesiones/`);
  - fotos o capturas donde salgan personas;
  - contraseñas.

## Código y pruebas

- **Parámetros en `config/*.json`, no en el `.py`.** El JSON sobrescribe el valor por defecto
  de la clase; si cambias el `.py`, el JSON lo pisa. En el laboratorio, los ajustes se hacen
  solo en el JSON.
- **Simulador antes de volar.** Todo cambio de control o de misión se prueba primero:
  ```bash
  python sim/sim_world.py espejo_circuito espejo_inicio espejo_cerca
  ```
  Si el cambio es grande, corre la regresión completa (~10 min) **en segundo plano y a un
  archivo**, y revisa que no haya choques:
  ```bash
  python sim/sim_world.py todos > sim/logs/regresion.txt 2>&1
  ```
- Si agregas un escenario, documéntalo en `docs/simulador.md`. Si mides algo del dron, va en
  `docs/tello.md`. Si cambias el protocolo, en `docs/laboratorio.md`.
- **No deshagas** las "Decisiones que conviene no deshacer" de `docs/bitacora.md` sin
  hablarlo con el equipo. Por ejemplo: la altura se mide con `tof − 10`, nunca con `h`.
- **Nunca desactives un vigilante de seguridad** para que una prueba "pase".

## Seguridad en el laboratorio

- Nunca indiques volar sin alguien en el teclado con la ventana enfocada:
  - **ESPACIO** = paro (aterriza);
  - `k` mata motores y el dron cae: solo si va hacia una persona.
- Si sale `el dron no obedece`, `el despegue se vino abajo` o `avanza solo`, **no es la
  misión**: es el dron o el clip. Sigue "Revisar el dron" en `docs/laboratorio.md` (hélices,
  calibrar IMU, temperatura, estacionario) antes de seguir.
- Temperatura abajo de ~70 °C antes de despegar (arriba de 80 no despega). Flips con
  batería ≥ 70 % y ~1.7 m libres hacia arriba.

## Cómo está el código

| Archivo | Qué es |
|---|---|
| `scripts/mision_espejo.py` + `config/mission_espejo.json` | **misión principal**: sube a 100 cm, avanza hasta ver un tag debajo, se centra encima sosteniendo el rumbo (≤12 cm, máximo 8 s), ejecuta y sigue. Con `sostener_piso` mide con el piso cuánto se mueve: regresa al despegue mientras sube, avanza en línea recta y busca el tag que pierde |
| `scripts/kalman_piso.py` | (branch `kalman`) filtro de Kalman por eje para sostener la posición con el piso: estima posición, velocidad y deriva con el modelo rc → velocidad. Se usa con `"piso_control": "kalman"`; si deja de cuadrar con lo medido, regresa al PID |
| `scripts/mision_piso.py` + `config/mission_piso.json` | respaldo sin espejo: cámara al frente, último metro a ciegas |
| `scripts/mission_tags.py` + `config/mission_tags.json` | base de las misiones: acciones de cada tag, flip seguro, sostener altura, "el dron no obedece" |
| `scripts/first_flight.py` + `config/flight.json` | vuelo base, despegue, seguridad, HMI, bitácora; prueba de estacionario, giro y flip |
| `scripts/test_tags.py` | visión: detector, pose, `--espejo`; prueba sin volar |
| `sim/sim_world.py` + `config/sim_tello.json` | simulador 3D con el detector y la misión reales; el dron simulado se comporta como dice el JSON (un dron sano). `--dron 1` / `--dron 7` agregan la deriva de cada dron (`config/sim_tello_dron<N>.json`); `--ideal`, el modelo optimista de antes |
| `sim/deriva_video.py` | mide cuánto se va solo cada dron con el piso visto por el espejo en los videos (`--record`); da los valores para `config/sim_tello_dron<N>.json` |
| `sim/prueba_desgaste.py` | detección de tags gastados (desteñidos, manchas, pedazos faltantes) sin volar; antes de tocar el detector, correrla junto con `test_tags.py --selftest` |
| `sim/comparar_control.py` | compara variantes del control en el simulador en tandas (mismas semillas), p. ej. PID contra Kalman: distancia al despegue, tags, distancia al tag y qué tan bruscos son los mandos |
| `sim/comparar_vuelos.py` | compara el simulador con vuelos reales y reajusta `config/sim_tello.json`; correr al cerrar cada sesión |
| `scripts/resumen_vuelos.py`, `scripts/traza_vuelo.py` | analizar vuelos |
| `scripts/resumen_piso.py` | por vuelo con espejo: quién sostuvo la posición (PID o Kalman), qué tan lejos del despegue o del tag quedó, si se hundió y qué tan bruscos fueron los mandos; `guardar_sesion.py` lo guarda en `piso.txt` |
| `scripts/guardar_sesion.py` | subir una sesión de laboratorio a `sesiones/` |

Ajustes de `config/mission_espejo.json` que más se mueven en el laboratorio:

| Parámetro | Para qué |
|---|---|
| `advance_timeout_s` | cuánto avanza buscando el siguiente tag antes de terminar |
| `advance_fb` | qué tan rápido avanza buscando |
| `cruise_alt_cm` | altura de vuelo; más alto ve más piso |
| `vista_adelante_deg`, `vista_lado_deg` | inclinación del clip, medida con E1; cambia con cada clip |
| `ignorar_inicio` | ignorar o no el tag que ve al despegar; en las pruebas va en `false` |
| `advance_lr` | rc lateral fijo al avanzar sin tag, para compensar si el dron se va siempre de un lado (negativo = a la izquierda); con `sostener_piso` casi no hace falta |
| `piso_kp`, `piso_kd`, `piso_ki` | el PID que sostiene la posición con el piso; síntomas y qué cambiar en "Cómo ajustarlo" de `docs/arquitectura.md` |
| `piso_control`, `kalman_*` | (branch `kalman`) `"pid"` o `"kalman"`; el Kalman y cómo ajustarlo, en `docs/arquitectura.md` |
| `config/mision_dron<N>.json` | ajustes de la misión de cada dron (`--dron N`); hoy, `piso_i_inicial`: la integral con que arranca. Si el dron se arregla, ponerla en [0, 0] |

## Cómo guiar una sesión de laboratorio

1. `git pull --rebase` y activar el entorno (ver `README.md`).
2. "Revisar el dron" (`docs/laboratorio.md`). Si el estacionario falla, no sigas con misiones.
3. Pruebas **una por una** en el orden de `docs/laboratorio.md`. Después de cada una:
   - pregunta qué vio la persona;
   - revisa la bitácora (abajo);
   - explica en lenguaje simple qué pasó y qué sigue.
4. En cada pausa, no solo al final, corre `guardar_sesion.py` con las observaciones, y luego
   commit y push.
5. Al terminar, entrada en `docs/bitacora.md` y push.

## Cómo analizar un vuelo

```bash
python scripts/resumen_vuelos.py
```
Da un veredicto de cada vuelo de hoy; con `--fecha AAAAMMDD` revisa otro día.

Para comparar PID y Kalman (columna `piso_modo` de la bitácora): `python scripts/resumen_piso.py --ultimos 1`.

```bash
python scripts/traza_vuelo.py logs/<archivo>.csv --cada 4
```
Muestra estado por estado. También sirve con `sesiones/<fecha>/vuelos/<archivo>.csv`.

- **Altura real = `tof − 10`.** El campo `h` del Tello no es confiable.
- `rc_lr`, `rc_fb`, `rc_ud` y `rc_yaw` son los mandos que **sí** se enviaron.
- `reason` dice por qué cambió de estado.
- En espejo:
  - `tag_adelante` y `tag_derecha` (cm) son dónde está el tag respecto al dron;
  - `objetivo` es el tag que persigue;
  - `n_tags` es cuántos detecta en ese frame.

Síntomas que ya conocemos:

| Síntoma | Causa probable | Qué hacer |
|---|---|---|
| Al despegar sube solo a ~150 cm, o se regresa al piso; `h` sube mientras `tof` baja | la estimación de altura interna del Tello está mal (IMU); pasó igual con y sin clip (9-nov) | calibrar IMU y centro de gravedad en la app Tello, encender el dron quieto, repetir el estacionario sin clip |
| `el dron no obedece` / `avanza solo` | IMU descalibrado o hélice dañada | "Revisar el dron" |
| La app oficial dice "posicionamiento visual no disponible" | el sistema de visión de la panza (VPS) no funciona: sensores sucios o tapados, poca luz, piso sin textura, o el módulo dañado por una caída | limpiar la panza, buena luz, piso con textura; si sigue, reparar o usar otro Tello |
| Se hunde ~10–13 cm/s al avanzar | normal en este Tello | lo corrige el sostener altura |
| Al centrarse oscila ±10 cm | deriva normal (~5 cm/s); el centrado frena con la velocidad del tag | normal; si oscila mucho más, subir `center_kd` |
| Se va siempre a la derecha (o izquierda) al avanzar sin ver tags | el rumbo sigue rotando tras un giro, o deriva propia del dron o una corriente de aire | revisar `rc_yaw` y `yaw` en la bitácora; ajustar `advance_lr`; apagar ventiladores |
| `sostener_piso APAGADO: se alejo ... corrigiendo` | la corrección empujó al dron hacia afuera (medida al revés) | ver `piso_der`/`piso_ade` y `piso_q` en la bitácora; si sale al revés, `"sostener_piso": false` y avisar; hacer E2b |
| Pasa encima de un tag y no lo ve, aunque está en el centro | tag gastado o desteñido (por el espejo el negro ya se ve gris, ~150) | revisar que `deteccion_rescate` esté en `true` (`config/mission_tags.json`); reimprimir el tag; probar con `test_tags.py --espejo` |
| No encuentra el siguiente tag | estaba lejos o fuera de lo que ve debajo (±39 cm adelante a 100 cm) | subir `advance_timeout_s` o `cruise_alt_cm` |
| Ignora el primer tag del recorrido | se vio al despegar | revisar `ignorar_inicio` e `inicio_alt_cm` |
| `flip omitido: bateria` | menos de 50 % | cambiar de batería |
| `NO despega: temperatura` | ≥ 80 °C | apagar y ventilador 3–5 min |

## Si usas otro Tello o una laptop nueva

- Instalación en `README.md`: venv y `pip install -r requirements.txt`.
- Configura tu identidad de git: `git config user.name` y `git config user.email`.
- La calibración de la cámara (`config/camera_tello.json`) es de **nuestro** Tello. Con otro
  Tello hay que recalibrar (`scripts/calibrate_camera.py`) y repetir E1 con su clip.
