# Sesiones de laboratorio

Una carpeta por día de pruebas con el dron, para revisar desde GitHub qué pasó sin estar en
el laboratorio.

```
sesiones/AAAA-MM-DD/
  notas.md      qué se probó, qué salió y qué sigue (lo escribe quien probó)
  resumen.txt   veredicto de cada vuelo (scripts/resumen_vuelos.py)
  vuelos/       bitácoras CSV de cada vuelo (copiadas de logs/)
  *.txt         calibración de rc y calidad del enlace, si hubo
```

Se arma con un comando al terminar (o a media sesión, las veces que quieras):

```bash
python scripts/guardar_sesion.py --notas "qué se probó y qué salió"
```

Luego se sube con commit y push. Los videos (`*.mp4`) y las imágenes no se guardan aquí: pesan
mucho y pueden salir personas.

Para ver una bitácora condensada:

```bash
python scripts/traza_vuelo.py sesiones/2026-11-09/vuelos/espejo_20261109_141631.csv
```

El resumen de lo aprendido en cada sesión está en [`docs/bitacora.md`](../docs/bitacora.md).
