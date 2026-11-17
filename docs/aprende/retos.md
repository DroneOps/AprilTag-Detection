# Retos con el simulador

Antes de empezar, lee [`README.md`](README.md): cómo se corre, cómo se cambia un ajuste con
`--set` y cómo se lee el resultado. Anota tus respuestas y, al terminar cada reto, compáralas
con [`respuestas.md`](respuestas.md).

Cada simulación tarda 1–3 minutos. Si un resultado te parece raro, córrela otra vez: no sale
igual dos veces.

---

## Nivel 1: usar el simulador

### Reto 1. Tu primer vuelo simulado

```bash
python sim/sim_world.py espejo_circuito
```

En el circuito hay tres tags: el 1 (girar a la derecha) a 80 cm al frente, el 2 (girar a la
izquierda) a 70 cm a la derecha del 1 y el 7 (aterrizar) a 70 cm adelante del 2.

1. ¿Qué tags ejecutó y en qué orden?
2. ¿Qué tan lejos del centro de cada tag estaba al ejecutarlo?
3. ¿En qué segundo empezó a avanzar (`ADVANCE`) y en cuál vio el tag 1 (`APPROACH`)?
4. ¿Cuánto duró el vuelo completo, del despegue al aterrizaje?

### Reto 2. Míralo en video

```bash
python sim/grabar.py espejo_circuito --salida sim/logs/videos_aprende/circuito
```
```bash
python sim/componer.py sim/logs/videos_aprende/circuito --salida sim/logs/videos_aprende/circuito --sin-gif
```

Abre `sim/logs/videos_aprende/circuito.mp4` con cualquier reproductor de video. A la
izquierda está el mapa visto desde arriba:
- el círculo rojo es el dron y la raya, hacia dónde apunta su nariz;
- el rectángulo es lo que ve la cámara por el espejo;
- los tags se ponen verdes cuando ya los ejecutó.

A la derecha está lo que ve la cámara y el estado de la misión.

1. ¿El rectángulo de lo que ve la cámara está más adelante o más atrás del dron?
2. Cuando el tag 1 aparece por primera vez en la cámara, ¿dónde está el dron respecto al tag?
3. ¿Por qué crees que es así? Pista: busca "Lo que se ve con la vista a −10.3°" en
   [`../tello.md`](../tello.md).

### Reto 3. Lee la bitácora y mide la velocidad

Cada vuelo, real o simulado, deja una bitácora (un CSV) con un renglón por cada instante. El
del reto 1 quedó en `sim/logs/espejo_circuito.csv`. Si ya corriste otra simulación del
circuito, repite el reto 1 primero.

```bash
python scripts/traza_vuelo.py sim/logs/espejo_circuito.csv --cada 5
```

En cada renglón:
- `rc=(lado, adelante, arriba, giro)` son los mandos que se mandaron al dron;
- `piso_ade` dice cuántos cm se ha movido hacia adelante, medido con el piso visto por el
  espejo;
- al final, después de `<-`, la razón de cada cambio de estado.

1. ¿Qué mando de adelante (`rc`, el segundo número) manda mientras avanza buscando el tag 1?
2. Busca el renglón donde empieza `ADVANCE` y el primero de `APPROACH`. ¿Cuántos cm cambió
   `piso_ade` y en cuántos segundos? ¿A qué velocidad avanzó, en cm/s?
3. Durante `EXECUTE` del tag 1, ¿qué mando cambia mucho? ¿Por qué?

---

## Nivel 2: los ajustes de la hoja de competencia

Estos son los ajustes de [`../hoja_competencia.md`](../hoja_competencia.md). Aquí ven qué pasa
con cada uno antes de necesitarlo.

### Reto 4. ¿Hasta dónde alcanza a buscar? (`advance_timeout_s`)

`advance_timeout_s` (hoy 18) es cuántos segundos avanza buscando el siguiente tag antes de
rendirse y aterrizar.

```bash
python sim/sim_world.py espejo_circuito --set advance_timeout_s=5
```

1. ¿Qué pasó? ¿Dónde aterrizó (`y`) comparado con el tag 1, que está en `y=80`?

En `espejo_lejos` el tag 2 está a 2 m del despegue.

2. Con la velocidad que mediste en el reto 3, calcula hasta cuántos cm alcanza a buscar con
   12 s. Ojo: ve el tag ~20 cm antes de estar encima. ¿Le alcanza para 2 m? Compruébalo:
   ```bash
   python sim/sim_world.py espejo_lejos --set advance_timeout_s=12
   ```
3. Ahora con el valor de hoy (18):
   ```bash
   python sim/sim_world.py espejo_lejos
   ```
4. El dron real con espejo avanza más lento que el simulado: ~9 cm/s, a veces 7. ¿Por qué la
   hoja de competencia dice "la distancia más larga en cm ÷ 8"?

### Reto 5. Más rápido, ¿mejor? (`advance_fb`)

`advance_fb` (hoy 15) es el mando de adelante mientras busca. Corre las dos:

```bash
python sim/sim_world.py espejo_circuito --set advance_fb=10
```
```bash
python sim/sim_world.py espejo_circuito --set advance_fb=25
```

1. Llena una tabla con las dos y la del reto 1 (que fue con 15):
   - segundos de `ADVANCE` a `APPROACH` del tag 1;
   - cm del centro al ejecutar cada tag;
   - segundos que tardó en centrarse (`APPROACH` a `EXECUTE`) en cada tag.
2. ¿Qué se gana y qué se arriesga al ir más rápido? Recuerda el reto 2: el tag aparece cuando
   ya está casi debajo.

### Reto 6. El tamaño del tag mal puesto (`tag_cm`)

Los tags del simulador miden 8 cm, como dice `config/mission_tags.json`. Imagina que alguien
puso 15 por error:

```bash
python sim/sim_world.py espejo_circuito --set tag_cm=15
```

1. ¿Ejecutó los tres tags? ¿Algún centrado dice "incompleto"?
2. Mira la bitácora durante `APPROACH`:
   ```bash
   python scripts/traza_vuelo.py sim/logs/espejo_circuito.csv --cada 2
   ```
   Compara `altura_espejo` (la altura que calcula con el tag) con `tof − 10` (la altura de
   verdad). ¿Qué notas?
3. En la competencia, ¿cómo usarías eso para saber si `tag_cm` está bien puesto?
4. Extra: calcula el tamaño real del tag con `tag_cm × (tof − 10) ÷ altura_espejo`.

### Reto 7. Volar más bajo (`cruise_alt_cm`)

```bash
python sim/sim_world.py espejo_circuito --set cruise_alt_cm=70
```

1. ¿Ejecutó todo? ¿Tardó más o menos en encontrar el tag 1 que en el reto 1?
2. La cámara ve hacia los lados `altura × 0.52` cm (la mitad de su ángulo es 27.5°). ¿Cuánto
   ve de cada lado a 100 cm y a 70 cm?
3. ¿Cuándo convendría bajar la altura en la competencia? ¿Qué se pierde?

### Reto 8. El dron que se va solo (`sostener_piso`)

El Tello 7 se va solo hacia la derecha (~12 cm/s). El simulador lo imita con `--dron 7`.
`espejo_estacionario` es como la prueba E2b: sube y se queda quieto 20 s, sin tags.

```bash
python sim/sim_world.py espejo_estacionario --dron 7
```
```bash
python sim/sim_world.py espejo_estacionario --dron 7 --set sostener_piso=false
```

1. Compara la línea `quieto 20 s: distancia al despegue media ..., máxima ...` de las dos.
2. ¿Qué hace `sostener_piso`? Lee su comentario en `scripts/mision_espejo.py` (busca
   `sostener_piso: bool`).
3. ¿Por qué la hoja de competencia solo dice apagarlo si sale `sostener_piso APAGADO` o si el
   piso es liso?

### Reto 9. El espejo inclinado (`vista_adelante_deg`)

En estos dos escenarios el espejo está inclinado 8°. En el primero la misión lo sabe (está en
la configuración); en el segundo no.

```bash
python sim/sim_world.py espejo_inclinado
```
```bash
python sim/sim_world.py espejo_inclinado_sin_config
```

1. Compara `al ejecutar (real)` de los dos.
2. ¿Por qué hay que volver a medir la inclinación (opción `i` de `lab.py`) cuando cambia el
   clip o el espejo se mueve?

### Reto 10. Tags gastados (`deteccion_rescate`)

En estos escenarios el tag 1 está manchado, al 2 le faltan pedazos y el 7 está muy desteñido.

```bash
python sim/sim_world.py espejo_gastado
```
```bash
python sim/sim_world.py espejo_gastado_sin_rescate
```

1. ¿Cuántos tags ejecutó cada uno?
2. Busca `deteccion_rescate` en `config/mission_tags.json` y en `scripts/mission_tags.py`. ¿Qué
   hace?
3. Si en la competencia el dron pasa encima de un tag y no lo ve, ¿qué revisarías primero?

---

## Nivel 3: el código

Para buscar en el código: en VS Code, `Ctrl+Shift+F` busca en todos los archivos y `Ctrl+F`
en el que tienes abierto. En la terminal:

```bash
grep -rn "lo que buscas" scripts/
```

### Reto 11. Qué hace cada tag

Abre `scripts/mission_tags.py` y busca `ACTIONS`.

1. ¿Qué tag hace dos cosas? ¿Cuáles?
2. ¿Qué significa `("yaw", -90)`? ¿Y `("climb", +1)`?
3. ¿De dónde salen los 5 s de pausa del tag 9? Pista: busca `wait_s`.
4. Pruébalo con 2 s:
   ```bash
   python sim/sim_world.py espejo_quieto --set wait_s=2
   ```
   ¿Cuántos segundos duró `EXECUTE`? ¿Por qué el texto sigue diciendo "Pausa 5 s"? Pista:
   búscalo en `scripts/test_tags.py`.

### Reto 12. Un vigilante de seguridad

```bash
python sim/sim_world.py espejo_despegue_cae
```

1. ¿Qué mensaje salió y en qué estado terminó?
2. Busca parte del mensaje en el código (`grep -rn "se vino abajo" scripts/`). ¿En qué archivo
   y renglón está? ¿Qué condición lo dispara?
3. ¿Qué ajuste, de qué archivo JSON, decide cuántos cm cuentan como "ya subió"?
4. En `CLAUDE.md` dice "Nunca desactives un vigilante de seguridad para que una prueba pase".
   ¿Qué podría pasar en el dron real si este vigilante no existiera?

### Reto 13. Reto final: una pista de competencia

`sim/pista.py` arma pistas al azar como las de la competencia: tags repetidos, regresos tras
un 180°, flips, subir y bajar. Cada número da una pista distinta.

```bash
python sim/pista.py 1
```

1. Dibuja la pista en tu hoja: dónde está cada tag (`id@(x,y)`, en cm) y en qué orden debe
   ejecutarlos (`visitas`).
2. Vuélala con un dron sano y con el Tello 7:
   ```bash
   python sim/sim_world.py espejo_competencia --semilla 1
   ```
   ```bash
   python sim/sim_world.py espejo_competencia --semilla 1 --dron 7
   ```
   ¿Cuántos puntos hizo cada uno? Un punto por tag bien ejecutado, en orden, hasta el primer
   error.
3. Graba en video el que falló y explica por qué falló:
   ```bash
   python sim/grabar.py espejo_competencia --semilla 1 --dron 7 --salida sim/logs/videos_aprende/pista1_t7
   ```
   ```bash
   python sim/componer.py sim/logs/videos_aprende/pista1_t7 --salida sim/logs/videos_aprende/pista1_t7 --sin-gif
   ```
4. Extra: vuela las pistas 2, 3 y 4 con el dron sano y saca el promedio de puntos.
