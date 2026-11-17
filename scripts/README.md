# Scripts

Están en tres carpetas, según para qué sirven:

| Carpeta | Qué hay | Cuándo se usa |
|---|---|---|
| [`principales/`](principales/README.md) | lo que vuela en la competencia: la misión con espejo y su base | en cada vuelo |
| [`documentar/`](documentar/README.md) | medir, analizar y guardar lo que pasó; también preparar (calibrar la cámara, imprimir tags) | después de volar, o antes de la primera vez |
| [`pausados/`](pausados/README.md) | lo que ya no se usa pero se puede retomar (Kalman, misión sin espejo, calibración de rc) | solo si el equipo decide retomarlo |

- **En el laboratorio casi todo se corre desde `python lab.py`.** El menú muestra el comando
  que usa en cada opción (`→ python scripts/...`).
- **Siempre desde la carpeta del repo, no desde `scripts/`:**
  ```bash
  python scripts/principales/mision_espejo.py --help
  ```
- **Los ajustes van en `config/*.json`, no en los `.py`.** El JSON pisa el valor que está en el
  código.
- **El simulador está aparte, en `sim/`** ([`docs/simulador.md`](../docs/simulador.md)). Usa la
  misma misión de `principales/`.
