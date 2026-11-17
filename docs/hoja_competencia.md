# Hoja de competencia: si algo es diferente

Para imprimir y llevar el 5 de diciembre (dos caras). Cada ajuste se cambia con
**`python lab.py` → `c`**: el menú revisa que el valor tenga sentido, lo guarda y lo sube a
GitHub. **Antes de cambiar uno, anota en la última columna el valor que tenía**: si sale peor,
lo regresas igual. Los valores de "Hoy" son los del 16-nov; el menú muestra los actuales.

## Al llegar: pregúntenle esto a los jueces

| Pregunta | Qué ajuste cambia |
|---|---|
| ¿Cuánto mide de lado el cuadro negro de los tags? | `tag_cm` |
| ¿Cuál es la distancia más larga y la más corta entre dos tags? | `advance_timeout_s`, `mismo_tag_cm` |
| ¿La etiqueta de inicio se ejecuta o solo marca el despegue? | `ignorar_inicio` |
| ¿A qué altura está el techo o la red? | `flip_min_alt_cm` |
| ¿Cuántos tags trae la pista y cuánto tiempo hay por intento? | `mission_max_s` |
| ¿Podemos hacer un vuelo de prueba en la pista? | si dicen que sí: opción 1 (estacionario) y opción 2 (E1) ahí mismo |

## Antes de cada intento

- [ ] Batería al **100 %**. Los flips piden más de 50 % en el momento del flip.
- [ ] Temperatura abajo de **70 °C** (arriba de 80 no despega). Ventilador entre intentos.
- [ ] Las 4 hélices sin daño y el clip firme.
- [ ] Laptop cerca de la pista, conectada al WiFi `TELLO-…`: `python lab.py` → **9) Competencia**.
- [ ] El dron sobre el despegue, con la nariz hacia el primer tramo.
- [ ] Una persona con la mano en el teclado y la ventana del dron enfocada:
  - **`t`** despega;
  - **ESPACIO**, o clic en la barra roja, aterriza;
  - **`k`** apaga los motores y el dron cae: **solo si va hacia una persona**.

## Si algo es diferente: qué mover

| Si… | Ajuste | Hoy | Cámbialo a | Antes |
|---|---|---|---|---|
| Los tags no miden 8 cm | `tag_cm` | 8 | lo que mida el cuadro negro, en cm | |
| Hay más de 1.5 m entre dos tags | `advance_timeout_s` | 18 | la distancia más larga en cm ÷ 8 (2 m → 25; 2.5 m → 31) | |
| Hay menos de 70 cm entre dos tags | `mismo_tag_cm` | 35 | la mitad de la distancia más corta | |
| Los tags son chicos (4 cm o menos) y E1 casi no los ve a 100 cm | `cruise_alt_cm` | 100 | 80 (ve menos de lado: ±42 cm en vez de ±52) | |
| El techo o la red están a menos de 1.7 m | `flip_min_alt_cm` | 130 | techo − 40 cm, **nunca menos de 110** (tras el flip cae ~45 cm) | |
| La pista trae más de 7 tags | `mission_max_s` | 240 | 30 × número de tags + 30 | |
| La etiqueta de inicio **no** se debe ejecutar | `ignorar_inicio` | false | true | |
| Al avanzar se va siempre del mismo lado (y ya pasó "Revisar el dron") | `advance_lr` | 0 | −10 si se va a la derecha, +10 si a la izquierda | |
| Sale `sostener_piso APAGADO`, o el piso es liso o brilla y el dron se porta raro | `sostener_piso` | true | false | |
| El espejo se movió o llegó un clip nuevo | `vista_adelante_deg`, `vista_lado_deg` | −10.3, −0.5 | lo que mida la opción `i` con el video de un intento | |

- `advance_timeout_s` cuenta desde que sale de un tag. Más alto alcanza tags más lejanos,
  pero si se le pasa uno sigue más lejos antes de aterrizar.
- Si hay tiempo entre intentos, después de un cambio acepta la prueba en el simulador que
  ofrece el menú (~1 min). Los tags del simulador miden lo que diga `tag_cm`.

## Si aterriza solo: qué dice la ventana y qué hacer

| Mensaje | Qué pasó | Qué hacer |
|---|---|---|
| `NO despega: temperatura …` | 80 °C o más | apagarlo y ventilador 3–5 min |
| `NO despega: bateria …` | menos de 30 % | cambiar la batería |
| `sin video …` o `telemetria perdida …` | se cortó el WiFi; con muchos drones cerca pasa más | acercar la laptop a la pista, que no haya hotspots de celulares cerca y reconectar al `TELLO-…` |
| `sin tags debajo por 18 s: fin` | no encontró el siguiente tag | ¿estaba a más de 1.5 m? Sube `advance_timeout_s`. ¿Se fue de lado? Mira `advance_lr` |
| `flip omitido: bateria …` | tenía menos de 50 % al llegar al flip | batería llena en el siguiente intento |
| `flip omitido: no alcanzo …` | no llegó a la altura del flip | batería; si es por el techo, `flip_min_alt_cm` |
| `tiempo maximo de vuelo` | pasó `mission_max_s` | subir `mission_max_s` |
| `el dron no obedece` o `el despegue se vino abajo` | es **el dron**, no la misión | opción 1 del menú: hélices, calibrar el IMU en la app Tello, enfriar |
| Pasa encima de un tag y no lo ejecuta | tag gastado, con brillo o muy chico | opción 2 (E1) sobre ese tag; si casi no lo ve, `cruise_alt_cm` más bajo |

## Lo que NO se mueve en la competencia

- El control: `piso_kp`, `piso_kd`, `piso_ki` y `center_*`. Están afinados con muchos vuelos.
- Ningún vigilante de seguridad: batería, temperatura, `desobedece_*`, video perdido.
- Los archivos `.py`. Si algo parece necesitar código, se para y se habla con Fernando.

## Después de cada intento

El menú pregunta **"¿Qué viste?"**. Escribe qué tags hizo bien y dónde falló, por ejemplo:
"intento 2: 1, 5 y 3 bien; en el 4 no hizo el flip, batería 45 %". Se guarda junto con el
video. Si no hay internet, se sube después con la opción `u`.
