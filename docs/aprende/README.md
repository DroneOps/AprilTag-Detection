# Aprende con el simulador

Retos para conocer cómo se porta el dron y dónde está cada cosa en el código, **sin volar**.
Son para quienes van a operar el dron en la competencia: el 5 de diciembre ustedes deciden qué
ajuste mover si algo es diferente ([`../hoja_competencia.md`](../hoja_competencia.md)), y aquí
ven qué pasa con cada uno antes de necesitarlo.

## Qué necesitas

- La laptop con el repo y el entorno listos ([`README.md`](../../README.md), "Inicio rápido").
  No hace falta el dron.
- Una terminal abierta en la carpeta del repo, con el entorno activado.
- Una hoja o cuaderno para anotar lo que veas.

## Cómo se corre el simulador

Cada simulación tarda lo mismo que un vuelo real (1 a 3 minutos): es el mismo programa de la
misión, con un dron y una cámara simulados. Hay dos formas de correrla.

Con el menú del laboratorio, sin dron:

```bash
python lab.py --practica
```

Ahí: `s` (practicar en el simulador) → elige el escenario → responde las preguntas.

O con el comando directo, que es el que corre el menú por dentro. Los retos lo dan listo para
copiar:

```bash
python sim/sim_world.py espejo_circuito
```

## Cambiar un ajuste sin tocar el JSON

Casi todos los retos cambian un ajuste. **No editen el JSON para los retos:** usen `--set`, que
lo cambia solo en esa simulación.

```bash
python sim/sim_world.py espejo_circuito --set advance_fb=25
```

Al empezar, el simulador lo confirma con una línea `[sim] advance_fb=25 ... el JSON no
cambia`. Se pueden poner varios `--set` a la vez. En el menú, cuando pregunta "¿Cambiar
ajustes solo en esta simulación?", escribe `advance_fb=25`.

## Cómo leer el resultado

Al terminar, el simulador imprime algo así:

```
===== espejo_circuito: final DONE | choque: None | ... | ejecutados: ['1=Giro derecha 90', '2=Giro izquierda 90', '7=Aterrizar'] | ...
    al ejecutar (real): tag 1 a 7 cm, tag 2 a 6 cm
     13.2s ADVANCE   avanzando a 93 cm, buscando tag  [x=0 y=-11 z=95 yaw=0]
     17.8s APPROACH  tag 1 (Giro derecha 90) debajo: adelante +10, lado +7 cm  [x=-8 y=76 z=97 yaw=0]
     19.7s EXECUTE   tag 1 (Giro derecha 90) encima: adelante -5, lado +7 cm, giro +0  [x=-6 y=83 z=98 yaw=0]
     ...
```

- **`final`:** cómo terminó. `DONE` es que ya está en el piso; por qué aterrizó lo dice la
  última línea (`tag 7: aterrizar`, `sin tags debajo por 18 s: fin`, un vigilante...).
- **`choque`:** `None` es que no chocó con nada.
- **`ejecutados`:** qué tags ejecutó y en qué orden. Es el puntaje.
- **`al ejecutar (real)`:** qué tan lejos del centro del tag estaba de verdad al ejecutarlo. La
  misión no lo sabe; solo el simulador. Menos de ~12 cm está bien.
- **Las líneas de abajo:** cada cambio de estado, con el segundo en que pasó, la razón y dónde
  estaba el dron de verdad. `x` es a la derecha del despegue, `y` hacia adelante y `z` la
  altura, todo en cm.

Los estados de la misión con espejo son:

| Estado | Qué hace |
|---|---|
| `TAKEOFF` | despega |
| `HOVER` | se estabiliza un momento |
| `CRUISE` | sube a la altura de vuelo (`cruise_alt_cm`) |
| `ADVANCE` | avanza buscando un tag debajo |
| `APPROACH` | vio un tag: se centra encima |
| `EXECUTE` | ejecuta la acción del tag (girar, flip, pausa...) |
| `LANDING` / `EMERGENCY_LAND` | aterriza (normal / por un vigilante de seguridad) |
| `DONE` | en el piso |

**El simulador no sale igual dos veces:** el viento y el ruido cambian un poco. Si un
resultado te sorprende, córrelo otra vez antes de sacar conclusiones.

## Los retos

Están en [`retos.md`](retos.md), en orden. Los primeros enseñan a correr y leer el simulador;
los de en medio, qué hace cada ajuste de la hoja de competencia; los últimos, dónde está cada
cosa en el código. Cada uno dice qué correr, qué observar y qué contestar.

Cuando termines uno, compara con [`respuestas.md`](respuestas.md). Ábrelo después, no antes:
la idea es que lo descubras tú.
