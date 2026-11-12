# HANDOFF — AprilTag-Detection
_Actualizado: 2026-11-12_

## Estado actual

- **Misión principal: con espejo** (`scripts/mision_espejo.py`, `config/mission_espejo.json`).
  Desde el 11–12 nov **corrige la deriva sola**. ⚠️ Todo esto está probado solo en el
  simulador, no en vuelo:
  - `FlujoPiso` mide cuánto se mueve el dron con el piso visto por el espejo (correlación de
    fase) y compensa el cambio de escala al subir o bajar.
  - `sostener_piso`: un PID (`piso_kp` 0.5, `piso_kd` 0.8, `piso_ki` 0.15). Quieto y subiendo,
    regresa al despegue; avanzando, sostiene la línea del tramo. Tiene un seguro: se apaga si,
    corrigiendo, se aleja 35 cm en 1.5 s.
  - `sostener_tag`: al girar o hacer la pausa se centra sobre el tag, y el tramo siguiente
    pasa por el tag.
  - Si pierde un tag al centrarse, lo busca 4 s y sigue avanzando (antes aterrizaba).
  - `--dron N` carga `config/mision_dron<N>.json`; hoy solo `piso_i_inicial` (Tello 7: 4.5;
    Tello 1: 0).
  - Último commit de código: `99000ac`.
- **Simulador** (`sim/sim_world.py`): dron realista (`config/sim_tello.json`, ajustado con
  vuelos reales) y perfiles `--dron 1` / `--dron 7` con la deriva medida el 11-nov. Tiene
  piso con cuadrícula y escenario `espejo_estacionario` (como E2b). E5 simulado: Tello 1, 4
  de 4; Tello 7, 1–3 de 4 según la tanda. En la regresión, el único choque es
  `piso_hundimiento` (estrés de la misión de piso).
- **Detección:** rescate para tags gastados y confirmación con 3 de 5 (`config/mission_tags.json`).
  Más detecciones en los videos reales y ningún ID falso; ya voló así el 11-nov sin ejecutar
  tags equivocados.
- **Vuelo real del 11-nov** (`sesiones/2026-11-11/`, con Tello 1 y Tello 7):
  - E5 solo salió con la mano sosteniendo el dron;
  - los dos se van a la derecha estando quietos (el Tello 7 mucho más);
  - el Tello 1 falla caliente (68–78 °C);
  - el rumbo tras los giros ya está bien.
- Herramientas: `sim/comparar_vuelos.py` (simulador contra vuelos reales),
  `sim/deriva_video.py` (deriva con los videos), `sim/prueba_desgaste.py` (detección de tags
  gastados).

## Pendientes

Los lleva el equipo en `docs/bitacora.md`, sección **"Pendiente ahora"** (el repo no usa
issues).
- **Siguiente tarea principal (código): los pasos 3 a 6** para mejorar todavía más la
  deriva y el PID: compensar el atraso, barrido de ganancias en el simulador, mandos más
  finos y filtro de Kalman.
- **Lo inmediato en el laboratorio:** E2b con `--dron 1` y `--dron 7`.

## Contexto que no está en el código

- Varias personas trabajan en el repo y Fernando lo revisa desde GitHub. Por eso
  `CLAUDE.md` pide commit y push después de cada acción, y `scripts/guardar_sesion.py`
  después de cada tanda de vuelos.
- Lo que falla en vuelo real casi siempre es el dron o el lugar (luz, piso, temperatura,
  caídas), no la detección. Antes de culpar al código, revisar con
  `scripts/traza_vuelo.py` si el programa mandó ese movimiento (columnas `rc_*`).
- **La retroalimentación del PID solo reacciona a lo que mide:** un dron sin deriva casi no
  recibe mandos. Lo que puede moverlo de más es lo que supone una deriva sin medirla: la
  integral precargada (+5 cm con 4.5 y +15 cm con 13 en el simulador) o, en el futuro, la
  deriva inicial de un Kalman. Si un dron se arregla, su `piso_i_inicial` vuelve a [0, 0].
- **La deriva del simulador es un modelo de los videos del 11-nov** (constante a la derecha
  más aleatoria), todavía no comparado con el control real. Por eso conviene E2b antes de
  afinar ganancias en el simulador.
- Con deriva aleatoria, los resultados del simulador cambian de una corrida a otra. Para
  comparar, correr tandas de 4 y no fiarse de una sola corrida.
- El vigilante "el dron no obedece" puede dar falsas alarmas con una lectura suelta del tof,
  pero hacerlo menos sensible es decisión del equipo (punto 3 de la bitácora).
