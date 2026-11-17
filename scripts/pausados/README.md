# Scripts pausados

No se usan en la misión de hoy, pero funcionan y se pueden retomar. Antes de retomar uno, hay
que hablarlo con el equipo.

## `kalman_piso.py`: filtro de Kalman para sostener la posición

- **Qué es:** otra forma de sostener al dron con el piso. Estima la deriva con un modelo del
  dron, en vez del PID de `principales/piso.py`.
- **Por qué se pausó (12-nov):** en el laboratorio se centró peor que el PID (~20 cm del tag
  contra ~6) y oscilaba más. Su modelo del dron no cuadra con el Tello real (supone 14.5 cm/s
  con rc 15; el real con espejo da ~9).
- **Desde el 17-nov no está conectado a la misión.** Cómo estaba conectado:
  ```bash
  git show 02a4a11:scripts/mision_espejo.py
  ```
- **Detalle y pasos para retomarlo:** en su encabezado y en `docs/bitacora.md`, entradas
  "12-nov (tarde, 2)" y "12-nov (noche)".

## `mision_piso.py`: misión sin espejo (respaldo)

- **Qué es:** la cámara ve al frente, inclinada 11° hacia abajo. Ve los tags del piso entre ~1 y
  ~1.7 m adelante y recorre a ciegas el último metro.
- **Por qué se pausó:** con espejo el dron se centra encima de cada tag, mucho más preciso.
- **Cuándo usarla:** solo si en la competencia no se puede usar el espejo o se rompe el clip.
- **Cómo se prueba:** pruebas F1–F4 en `docs/laboratorio.md`; en el simulador, los escenarios
  `piso_*`.

```bash
python scripts/pausados/mision_piso.py --record videos/piso_m1.mp4
```

## `rc_calib.py`: calibración de rc contra un tag en la pared

- **Qué es:** mide cuánto se mueve el Tello con rc 10, 15 y 20 en cada eje, mirando un tag
  vertical con la cámara al frente. Se usó el 24-oct (resultados en `docs/tello.md`).
- **Por qué se pausó:** con el espejo la cámara no ve al frente. La velocidad ahora se mide con
  el piso (`documentar/resumen_piso.py`).

```bash
python scripts/pausados/rc_calib.py --ejes fb lr
```
