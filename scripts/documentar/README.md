# Scripts para documentar: medir, analizar y guardar

Ninguno de estos hace volar al dron. Leen las bitácoras (`logs/*.csv`) y los videos, o
preparan lo que hace falta antes de volar.

## Después de volar

| Script | Qué hace |
|---|---|
| `guardar_sesion.py` | copia las bitácoras del día y tus notas a `sesiones/<fecha>/` para subirlas a GitHub (`lab.py` lo hace solo) |
| `resumen_vuelos.py` | un veredicto por vuelo: cuánto voló, batería, temperatura, qué tags ejecutó, por qué aterrizó |
| `resumen_piso.py` | en vuelos con espejo: qué tan lejos del despegue o del tag quedó, si se hundió, cómo sostuvo con el piso |
| `traza_vuelo.py` | el vuelo renglón por renglón: estado, mandos, dónde veía el tag |
| `inclinacion_vuelo.py` | mide la inclinación del espejo con los videos de vuelo (opción `i` de `lab.py`) |

Guardar la sesión con tus notas:

```bash
python scripts/documentar/guardar_sesion.py --notas "E5: ejecutó 1 y 2; en el 7 se pasó ~15 cm"
```

Resumen de los vuelos de hoy (otro día: `--fecha AAAAMMDD`):

```bash
python scripts/documentar/resumen_vuelos.py
```

Resumen del último vuelo con espejo:

```bash
python scripts/documentar/resumen_piso.py --ultimos 1
```

Un vuelo renglón por renglón:

```bash
python scripts/documentar/traza_vuelo.py logs/<archivo>.csv --cada 4
```

Inclinación del espejo, con videos grabados en vuelo:

```bash
python scripts/documentar/inclinacion_vuelo.py videos/e5_dron7_1.mp4 videos/e5_dron7_2.mp4
```

Cómo leer una bitácora: "Cómo analizar un vuelo" en [`CLAUDE.md`](../../CLAUDE.md).

## Antes de volar (preparar)

| Script | Qué hace |
|---|---|
| `calibrate_camera.py` | calibra la cámara con el tablero (`tags/tablero_25mm.pdf`). Hace falta con cada Tello nuevo |
| `make_tags.py` | genera los PDF de los tags para imprimir (`tags/`) |

Calibrar la cámara de un Tello nuevo:

```bash
python scripts/documentar/calibrate_camera.py --source tello --square-mm 25
```

Generar los tags de 8 cm:

```bash
python scripts/documentar/make_tags.py --size-cm 8
```
