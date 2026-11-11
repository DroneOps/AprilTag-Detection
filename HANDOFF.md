# HANDOFF — AprilTag-Detection
_Actualizado: 2026-11-10_

## Estado actual

- **Misión principal: con espejo** (`scripts/mision_espejo.py`, `config/mission_espejo.json`).
  En el simulador pasan todos los escenarios de espejo, de piso y de pared (corridos el
  9-nov tras los últimos cambios; último commit `fcaaabd`).
- **En vuelo real (9-nov):**
  - detecta los tags a través del espejo;
  - se centra encima y ejecuta la acción (E3, y el tag 1 en E5);
  - **el circuito E5 no ha salido nunca**: entre tags, donde vuela a ciegas, el dron se va
    a la derecha.
- **Cambios del 9-nov (noche), ⚠️ sin probar en vuelo:**
  - rumbo más firme tras los giros (`heading_min` 20);
  - centrado que frena y ejecuta a ≤12 cm o a los 8 s;
  - `ignorar_inicio` en `false`;
  - ajuste lateral `advance_lr` (en 0).
- **Tello #1:** su sistema de visión de abajo (VPS) parece dañado (la app oficial lo avisa).
  Se está usando otro Tello, que es el mismo con el que funciona `DroneOps/Line_Follower`.
- Cada día de laboratorio está guardado en `sesiones/`, del 17-oct al 9-nov.

## Pendientes

Los lleva el equipo en `docs/bitacora.md`, sección **"Pendiente ahora"** (el repo no usa
issues). Lo inmediato: repetir E5 con los cambios del 9-nov sobre la pista del seguidor de
línea y, si sigue yéndose a la derecha, probar `advance_lr` en -10.

## Contexto que no está en el código

- Varias personas trabajan en el repo y Fernando lo revisa desde GitHub. Por eso `CLAUDE.md`
  pide commit y push después de cada acción, y `scripts/guardar_sesion.py` después de cada
  tanda de vuelos.
- Lo que falla en vuelo real casi siempre es el dron o el lugar (luz, piso, temperatura,
  caídas), no la detección. Antes de culpar al código, revisar con
  `scripts/traza_vuelo.py` si el programa mandó ese movimiento (columnas `rc_*`).
- **Propuesta sin hacer:** corregir la deriva usando el flujo del piso visto por el espejo.
  El video del 9-nov sobre la pista del seguidor dio calidad ~0.9 con correlación de fase
  (`cv2.phaseCorrelate`). Ojo: al girar, la vista "barre" de lado (el espejo ve ~20–25 cm
  adelante del centro del dron); eso no es deriva.
