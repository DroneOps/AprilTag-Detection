# Scripts principales: lo que vuela

La misión de la competencia es la del espejo. Cada archivo usa a los de abajo:

```
mision_espejo.py      la misión: avanzar, centrarse encima del tag, ejecutarlo, seguir
 ├─ espejo_config.py  sus ajustes (config/mission_espejo.json), con qué hace cada uno
 ├─ piso.py           medir cuánto se mueve el dron con el piso y sostenerlo (PID)
 └─ mission_tags.py   qué hace cada tag (ACTIONS), el flip seguro, sostener la altura
     └─ first_flight.py  despegue, aterrizaje, vigilantes de seguridad, ventana del dron, bitácora
test_tags.py          visión: detectar los tags y saber dónde están (lo usan todos)
```

## Para leerlo por primera vez

1. **`mision_espejo.py`, solo los métodos `_advance`, `_approach` y `_send_rc`:** qué hace en
   cada estado.
2. **`espejo_config.py`:** cada ajuste tiene un comentario con para qué sirve.
3. **`mission_tags.py`, busca `ACTIONS`:** qué hace cada tag.
4. **`first_flight.py`, busca "vigilantes":** por qué aterriza solo (batería, temperatura, sin
   video...).

Los retos de [`docs/aprende/`](../../docs/aprende/README.md) recorren estos archivos con el
simulador.

## Comandos

Con el menú (`python lab.py`) no hace falta escribirlos; estos son los que corre por dentro.

La misión con espejo, con los ajustes del Tello 7 y grabando el video:

```bash
python scripts/principales/mision_espejo.py --dron 7 --record videos/e5_dron7_1.mp4
```

Sin avanzar (pruebas E2b y E3):

```bash
python scripts/principales/mision_espejo.py --quieto
```

Prueba de estacionario ("Revisar el dron"):

```bash
python scripts/principales/first_flight.py
```

E1: ver los tags por el espejo con el dron en la mano (no vuela):

```bash
python scripts/principales/test_tags.py --source tello --espejo --tag-cm 8
```

Prueba del detector sin cámara:

```bash
python scripts/principales/test_tags.py --selftest
```

## Antes de cambiar algo aquí

- Los números van en `config/*.json`, no aquí.
- Todo cambio se prueba primero en el simulador:
  ```bash
  python sim/sim_world.py espejo_circuito espejo_inicio espejo_cerca
  ```
- **Nunca se apaga un vigilante de seguridad** para que una prueba pase.
- Cómo está hecho por dentro: [`docs/arquitectura.md`](../../docs/arquitectura.md).
