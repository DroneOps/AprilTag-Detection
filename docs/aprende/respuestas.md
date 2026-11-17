# Respuestas de los retos

Lo que salió cuando se probaron los retos en el simulador (16-nov). **Tus números no van a
salir iguales:** el simulador agrega viento y ruido distintos en cada vuelo. Lo que importa es
que lo que observes se parezca y que entiendas por qué pasa.

---

## Nivel 1

### Reto 1. Tu primer vuelo simulado

Dos corridas del circuito:

| | Corrida 1 | Corrida 2 |
|---|---|---|
| Ejecutados | 1, 2, 7 | 1, 2, 7 |
| Del centro al ejecutar | tag 1 a 7 cm, tag 2 a 6 cm | tag 1 a 10 cm, tag 2 a 5 cm |
| `ADVANCE` → `APPROACH` del tag 1 | 13.2 s → 17.8 s | 13.2 s → 18.1 s |
| Aterriza (`LANDING`) | 39.1 s | 41.0 s |

1. **Orden:** 1, 2, 7.
2. **Del centro:** entre 5 y 10 cm. Menos de ~12 cm es "encima".
3. **Tiempo hasta el tag 1:** empieza a avanzar a los ~13 s y lo ve unos 5 s después. En otras
   corridas tardó hasta 10 s, según el viento simulado.
4. **Vuelo completo:** ~40 s hasta `LANDING`, y unos segundos más para tocar el piso. Los
   primeros ~13 s son despegar, estabilizarse y subir a 100 cm.

### Reto 2. Míralo en video

1. **El rectángulo está casi todo atrás del dron:** a 100 cm ve ~20 cm hacia adelante, ~60
   hacia atrás y ~52 de cada lado.
2. **Cuando aparece el tag 1, el dron ya está casi encima:** en el reto 1, `APPROACH` dice
   "adelante +10".
3. **Por qué:** el espejo no queda perfectamente horizontal. La vista está inclinada 10.3°
   hacia atrás (medido en vuelo, ver `docs/tello.md`). Por eso el dron no ve venir los tags:
   avanza "a ciegas" hasta que el tag aparece casi debajo. De ahí salen dos reglas:
   - no avanzar muy rápido (reto 5);
   - darle tiempo suficiente para buscar (reto 4).

### Reto 3. Lee la bitácora y mide la velocidad

1. **Mientras avanza, `rc` adelante es 15:** es `advance_fb`.
   - Los otros mandos también se mueven.
   - El de lado (±10) sostiene la línea con el piso.
   - El de arriba (~20) sostiene la altura: el Tello se hunde al avanzar.
2. **Velocidad:** en una corrida, `piso_ade` pasó de −7 a +69 cm en ~4.5 s: **~17 cm/s**. En
   otras dio 9 y 12 cm/s.
   - El simulador avanza ~14.5 cm/s con rc 15, más o menos lo que lo empuje el "viento"
     simulado (~5 cm/s, distinto en cada vuelo).
   - **El dron real con espejo midió ~9 cm/s** (12-nov, de 5 a 11). El simulador va más rápido
     que el dron real.
3. **En `EXECUTE` del tag 1, el mando de giro (el cuarto) sube a 60:** está girando 90° a la
   derecha. Los de lado y adelante casi no se mueven: se sostiene encima del tag mientras gira.

---

## Nivel 2

### Reto 4. ¿Hasta dónde alcanza a buscar? (`advance_timeout_s`)

1. **Con 5 s:**
   - terminó con `sin tags debajo por 5 s: fin`;
   - aterrizó en `y=78`, a 2 cm del tag 1;
   - se rindió justo antes de verlo, porque necesita verlo en varios cuadros seguidos para
     confirmarlo.
2. **Con 12 s, el tag a 2 m:**
   - **La cuenta:** 12 s × ~13 cm/s ≈ 156 cm, más los ~20 cm que ve adelante ≈ 176 cm. No
     alcanza para 200.
   - **Lo que pasó:** en dos corridas aterrizó en `y=156` y `y=166`, sin ejecutar nada.
3. **Con 18 s:** sí llega. Vio el tag 2 a los ~16 s de avanzar y ejecutó el 2 y el 7. Con 25
   s también, lo vio a los ~15 s.
4. **Por qué la hoja dice "÷ 8":**
   - El dron real va a ~9 cm/s y a veces a 7.
   - Dividir la distancia entre 8 da los segundos que tarda a 8 cm/s; los ~20 cm que ve hacia
     adelante quedan de margen.
   - Con 18 s alcanza ~1.5 m, y por eso la hoja dice subirlo si hay más.
   - Si se usara la velocidad del simulador, en la competencia se quedaría corto.

### Reto 5. Más rápido, ¿mejor? (`advance_fb`)

Dos corridas de cada una:

| `advance_fb` | Hasta ver el tag 1 | Del centro (tag 1, tag 2) | Centrarse (tag 1, tag 2) | Aterriza |
|---|---|---|---|---|
| 10 | 7.3 s / 15.3 s | 7, 10 / 4, 4 cm | 0.6, 0.6 s / 1.8, 0.6 s | 53.0 / 59.8 s |
| 15 (hoy) | 4.6 s / 4.9 s | 7, 6 / 10, 5 cm | 1.9, 1.8 s / 2.1, 2.3 s | 39.1 / 41.0 s |
| 25 | 4.4 s / 5.1 s | 13, 7 / 3, 2 cm | 3.6, 7.7 s / 1.7, 4.9 s | 44.8 / 42.2 s |

1. **Lo que se ve:**
   - **Más lento (10):** se centra casi al instante, pero tarda mucho más en llegar.
   - **Más rápido (25):** llega un poco antes, pero tarda más en frenar y centrarse. Una vez
     tardó 7.7 s en el tag 2, casi el máximo de 8. En una corrida quedó a 13 cm del tag 1. En
     este circuito ni siquiera terminó antes que con 15.
2. **El riesgo:**
   - El tag aparece cuando ya está casi debajo (reto 2). Más rápido = menos tiempo para verlo y
     frenar encima.
   - En el dron real, además, la imagen sale más movida y cuesta más detectar el tag.
   - 15 es un buen punto medio. Si en la competencia se pasa de los tags, la hoja dice bajarlo.

### Reto 6. El tamaño del tag mal puesto (`tag_cm`)

1. **Una vez ejecutó los tres, otra vez solo el 1:**
   - **Primera corrida:** el tag 1 terminó como "centrado incompleto", porque se le acabaron
     los 8 s.
   - **Segunda corrida:** después del tag 1 se desvió, pasó lejos del tag 2 y aterrizó por
     `sin tags debajo por 18 s`.
   - Con el tamaño mal, a veces sale y a veces no: no es confiable.
2. **`altura_espejo` marcaba 173–180 cm mientras `tof − 10` decía ~90–95.**
   - La misión calcula distancias con el tamaño del tag.
   - Si cree que mide 15 y mide 8, todo le parece ~1.9 veces más lejos: la altura y también
     qué tan corrido está el tag. Por eso se centra mal.
3. **En la competencia:**
   - Después de un vuelo, mira en la bitácora si `altura_espejo` se parece a `tof − 10`.
   - Si no se parece, `tag_cm` está mal.
   - Si `tag_cm` es más grande que el tag de verdad, `altura_espejo` sale más alta que
     `tof − 10`; si es más chico, sale más baja.
4. **Tamaño real:** 15 × 92 ÷ 176 ≈ **7.8 cm**, casi los 8 de verdad. Así se puede medir el tag
   aunque no haya regla a la mano.

### Reto 7. Volar más bajo (`cruise_alt_cm`)

1. **A 70 cm ejecutó los tres** (tag 1 a 3 cm y tag 2 a 5 cm).
   - Tardó 11 s en encontrar el tag 1, pero con una sola corrida no se puede decir si fue por
     la altura o por el viento simulado.
   - El tag 2 lo encontró muy de lado (+25 cm) y terminó como "centrado incompleto".
2. **Lo que ve de cada lado:**
   - a 100 cm, 100 × 0.52 ≈ **52 cm**;
   - a 70 cm, 70 × 0.52 ≈ **36 cm**.
3. **Cuándo conviene:**
   - Con tags chicos que no detecta bien a 100 cm: más abajo se ven más grandes.
   - **Lo que se pierde:**
     - ve menos piso, así que un tag que quede corrido de la línea se le puede escapar;
     - después de un tag 6 (bajar 30 cm) quedaría a 40 cm del piso.

### Reto 8. El dron que se va solo (`sostener_piso`)

1. **Comparación:**

   | | Distancia media al despegue | Máxima | Al final |
   |---|---|---|---|
   | Con `sostener_piso` | 16 cm | 46 cm | 9 cm |
   | Sin `sostener_piso` | 264 cm | 439 cm | 439 cm |

   Sin sostenerse, el Tello 7 simulado se fue **más de 4 m** en 20 s.
2. **Qué hace:**
   - Mide con el piso, visto por el espejo, cuánto se ha movido el dron y lo regresa.
   - Quieto o subiendo, lo regresa al punto de despegue.
   - Avanzando, lo mantiene en la línea del tramo.
3. **Por qué solo apagarlo en esos casos:**
   - Sin él, un dron que se va solo no llega a los tags.
   - Solo se apaga si la medida del piso falla: piso liso o brillante, sin textura que seguir.
     O si la misión misma avisa `sostener_piso APAGADO`, que es cuando la corrección empujó
     hacia afuera.

### Reto 9. El espejo inclinado (`vista_adelante_deg`)

1. **Comparación:**
   - **Con la inclinación en la configuración:** el tag 2 quedó a **8 cm**.
   - **Sin ella:** quedó a **21 cm**, porque el dron se detuvo antes del tag. La misión creía
     tenerlo a 10 cm adelante ("encima"), pero de verdad le faltaban 21.
   - En los dos, después del tag 2 avanzó 18 s y aterrizó por `sin tags debajo`. Es normal: en
     esos escenarios solo hay un tag.
2. **Por qué medir otra vez:**
   - La inclinación cambia dónde cree la misión que está el tag. Con la medida equivocada queda
     corrido ~20 cm.
   - Cada clip queda distinto, y si el espejo se mueve con un golpe o un flip, también cambia.

### Reto 10. Tags gastados (`deteccion_rescate`)

1. **Con rescate ejecutó los tres; sin rescate, ninguno.** Pasó encima del tag 1 sin verlo y
   siguió hasta `y=248`, donde se rindió.
2. **Qué hace `deteccion_rescate` (`true` en `config/mission_tags.json`):**
   - Si en un cuadro no encuentra ningún tag, lo intenta otra vez con la imagen "erosionada":
     engorda el negro.
   - Así recupera tags manchados, desteñidos o con pedazos faltantes.
   - Lo dice el comentario de `deteccion_rescate` en `scripts/mission_tags.py`.
3. **En la competencia:**
   - Primero, que `deteccion_rescate` siga en `true`.
   - Luego, la opción 2 del menú (E1) sobre ese tag, para ver si lo detecta.
   - Si casi no lo ve, bajar `cruise_alt_cm`. **La pista no se puede tocar:** cambiar o marcar
     los tags descalifica.

---

## Nivel 3

### Reto 11. Qué hace cada tag

1. **El 8 hace dos cosas:** `("yaw", 180)` y luego `("flip",)`, es decir, gira 180° y hace el
   flip.
2. **Qué significan:**
   - `("yaw", -90)`: girar 90°; **negativo es a la izquierda**, por eso es el tag 2.
   - `("climb", +1)`: subir **una vez `climb_cm`**, que son 30 cm (`config/mission_tags.json`).
     Por eso el tag 6 es `("climb", -1)`: bajar 30.
3. **Los 5 s salen de `wait_s`** (5.0 en `config/mission_tags.json`). El código lo usa en
   `scripts/mission_tags.py`, donde dice `done = el > m.wait_s`.
4. **Con `wait_s=2`:**
   - `EXECUTE` empezó a los 16.0 s y volvió a `ADVANCE` a los 18.0: **2 s**.
   - El texto sigue diciendo "Pausa 5 s" porque es solo una etiqueta, escrita a mano en
     `TAG_FUNCTIONS` de `scripts/test_tags.py`.
   - Lección: el comportamiento sale del JSON; los nombres que se imprimen no siempre se
     actualizan solos.

### Reto 12. Un vigilante de seguridad

1. **Mensaje y estado:** `EMERGENCY_LAND` con
   `el despegue se vino abajo (subio a 41 y volvio a 13 cm): el Tello no sostiene la altura -
   revisa que el clip no tape los sensores de abajo`. Terminó en `DONE`, en el piso, sin
   ejecutar nada.
2. **Dónde está:** en `scripts/first_flight.py`, en la parte de `TAKEOFF` (cerca del renglón
   340). Se dispara si:
   - durante el despegue ya había subido al menos `takeoff_min_height_cm`;
   - y la altura (`tof − 10`) vuelve a 15 cm o menos.
3. **El ajuste:** `takeoff_min_height_cm`, 30 en `config/flight.json`.
4. **Sin este vigilante:**
   - La misión creería que el dron está volando y empezaría a mandarle mandos para avanzar y
     subir.
   - Pero el dron ya regresó al piso: podría arrastrarse, rebotar o despegar de golpe.
   - Esto pasó de verdad el 9-nov, con un clip que tapaba los sensores de abajo.
   - Si un vigilante "estorba", la causa está en el dron, no en el vigilante.

### Reto 13. Reto final: una pista de competencia

1. **La pista 1:**
   - **Tags:** 2 en (0, 90), 8 en (−133, 84), otro 8 en (4, 195), 9 en (91, 86), otro 2 en
     (233, 93) y 7 en (240, 206).
   - **Orden:** `[2, 8, 2, 8, 2, 9, 2, 7]`.
   - **El tag 2 de (0, 90) se visita cuatro veces:** cada 8 lo regresa con un giro de 180°.
2. **Puntos:**
   - **Dron sano: 8 de 8,** en ~168 s. Quedó a 3–14 cm de cada tag.
   - **Tello 7: 2 de 8.** Ejecutó el 2 y el primer 8, y luego aterrizó por
     `sin tags debajo por 18 s`.
3. **Por qué falló el Tello 7:**
   - Mientras ejecutaba el 8 (giro de 180°, subir a 130 cm, flip y recuperarse: ~20 s), se fue
     de (−137, 89) a (−198, −61). Son **~1.6 m**.
   - Además terminó apuntando a 110° en vez de ~87°.
   - Desde ahí, el tramo de regreso ya no pasaba por el tag 2.
   - En el video se ve el rastro rojo alejarse durante el flip. El Tello 7 se va solo ~12 cm/s
     a la derecha, y durante el flip casi no se puede corregir.
   - Es una de las fallas que el equipo todavía tiene pendientes.
4. **Extra:** en las corridas del 12-nov, con el dron sano:
   - pista 2: 6 de 6;
   - pista 3: 9 de 9;
   - pista 4: 4 de 7.

   Tus resultados pueden variar uno o dos tags.
