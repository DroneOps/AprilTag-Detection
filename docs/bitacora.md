# Bitácora del proyecto

Qué se probó en cada sesión, qué se aprendió y qué se cambió. Lo más reciente va arriba.
Las bitácoras de vuelo (`logs/*.csv`) y los videos están en la laptop, no en el repo.

## Pendiente ahora

**Antes que nada: la inclinación del espejo está mal en el JSON**
([issue #2](https://github.com/DroneOps/AprilTag-Detection/issues/2)).
- **Qué se midió:** en vuelo, con los tags de los videos (`scripts/inclinacion_vuelo.py`), la vista
  está inclinada **~−10.5° adelante y ~−1° de lado en los dos drones**. El JSON dice +4.1°.
- **Qué hace eso:** a 100 cm, cuando la misión cree estar "encima" de un tag, queda ~25 cm
  corrida, probablemente adelante (Fernando lo vio en el Tello 1). Además, al subir, la medida
  del piso cree que el dron se fue hacia atrás.
- **El arreglo va junto:**
  1. `vista_adelante_deg` ≈ −10.5 y `vista_lado_deg` ≈ −1 en `config/mission_espejo.json`;
  2. que `FlujoPiso` escale alrededor del punto bajo el dron (centro volteado más esa
     inclinación).

  Primero en el simulador (con `mirror_tilt` −10.5); luego E5 en el laboratorio, mirando de
  lado si de verdad queda encima de cada tag.
- **E1 con el dron en la mano no sirve para esto:** dio −5.7° y −7.0°, y −13° de lado en el
  Tello 7, por cómo se sostiene.

**Tello 7: revisar el dron antes de volarlo.** El 12-nov (tarde) chocó con la malla.
- Pidiéndole adelante a fondo se fue ~75 cm hacia atrás y subió solo a 130 cm, y se le salió la
  pila al caer.
- Antes de volarlo: hélices, que la pila quede firme, calibrar el IMU, estacionario, y revisar
  en la app si dice "posicionamiento visual no disponible".

1. **PID o Kalman: en el laboratorio el Kalman no fue mejor** (12-nov tarde; ver la entrada).
   - **Con el Kalman se centró peor:** ejecutó a ~20 cm del tag contra ~6 del PID, según la
     cámara, y Fernando lo vio oscilar más en E5.
   - **Por qué, probablemente:** su modelo del dron no cuadra con lo real. Con rc 15 el piso
     mide ~9 cm/s, no los 14.5 que supone, así que cree que hay una deriva hacia atrás y, al
     centrarse, empuja de más hacia adelante.
   - **Recomendación:** quedarse con el PID (`"piso_control": "pid"`, como está) y no
     prender el Kalman hasta arreglar la medida del piso y reajustar su modelo con los
     vuelos reales (`kalman_ganancia`).
   - **Decidir:** juntar la branch a `main` con el PID por defecto, o dejarla aparte. Juntarla
     trae las herramientas (`resumen_piso.py`, `inclinacion_vuelo.py`, `comparar_control.py`,
     la columna `piso_modo`) y las sesiones de esta tarde, que hoy solo están en la branch.
   - Si después se afina el PID: el primer candidato del barrido rápido es `piso_kp` 1.2,
     `piso_kd` 1.2, `piso_ki` 0.3.
   - **Ojo con los seguros:** ninguno paró el choque del Tello 7. Avanzando, el seguro del piso
     solo mira de lado, y el de "no obedece" solo lo vertical. Hablar en equipo si se agrega uno
     para "pide adelante y se va para atrás".
2. **Probar en el laboratorio `sostener_piso` y `sostener_tag`** (sin volar todavía).
   - **E2b primero, con `--dron N`** ([`laboratorio.md`](laboratorio.md)), con cada dron;
     luego E5.
   - Si se aleja en vez de regresar: ESPACIO y `"sostener_piso": false`.
   - Al final de E2b, anotar `piso_ider`: es el `piso_i_inicial` de ese dron, en
     `config/mision_dron<N>.json`.
   - Con el Tello 7, probar también `"center_max": 20`.
3. **Decidir en equipo el vigilante "el dron no obedece".** Una sola lectura baja del tof
   (que baja ≤ 10 cm y regresa > 10) cuenta como bajada, y su regreso se descarta. Así dio
   una falsa alarma en el simulador, y en las bitácoras reales la del 27-oct 13:50. Filtrar
   con mediana de 5 la quita, pero tampoco habría avisado en las 1.2, 1.4 y 1.9 del 11-nov,
   que sí se hundían (26–40 cm en ~3 s). No se cambió.
4. **La deriva estando quieto (11-nov).** Los dos Tellos se van a la derecha en
   estacionario: el Tello 7 de 15 a 37 cm/s, y el Tello 1 ~4–7 cm/s, este también sin
   espejo. En el próximo laboratorio:
   - estacionario del Tello 7 **sin clip**, en el mismo lugar;
   - estacionario de los dos **sobre otro piso** (la cuadrícula de cinta azul podría
     confundir a la cámara de abajo; sospecha, sin medir);
   - calibrar el IMU antes.
5. **El Tello 1 falla caliente:** a 68–78 °C no despega o "no obedece"; frío (55 °C) va bien.
   Volarlo solo abajo de 65 °C, y revisar en la app si es el que avisaba "posicionamiento
   visual no disponible".
6. Con espejo, en orden: **E5 → E6 → E7** ([`laboratorio.md`](laboratorio.md)). Ajustar
   `advance_timeout_s` y `cruise_alt_cm` según la pista. Enfriar entre corridas: el 11-nov
   se volaron 27 en 26 min.
7. Respuestas del comité: tamaño de tags, cómo es la trayectoria visible y la etiqueta de
   inicio ([`competencia.md`](competencia.md)).
8. Al cerrar cada sesión, correr `python sim/comparar_vuelos.py` y, si cambió el Tello o el
   clip, reajustar `config/sim_tello.json` ([`simulador.md`](simulador.md)). Las bitácoras
   del 11-nov dicen en `sesiones/2026-11-11/notas.md` qué dron fue cada una. Falta medir bien
   la deriva durante el despegue: en el simulador se corre más que en lo real.

## 12-nov (tarde, 2) — PID contra Kalman en el laboratorio; el espejo está inclinado −10.5°

Desde la branch `kalman`. Las sesiones con las notas de Fernando están en `sesiones/2026-11-12/`.

**E5 (K2) en todo el día**, contando los vuelos con PID de las 13:18. Distancia al tag al
ejecutar, según la cámara:

| Dron | PID | Kalman |
|---|---|---|
| Tello 1 | 3 de 3 (4, 9, 33 cm) y 3 de 3 (9, 1, 13) | 3 de 3 (22, 4, 14) |
| Tello 7 | 1 de 3, 3 de 3 (8, 7, 4), 1 de 3 y 3 de 3 (4, 6, 6) | choque (abajo) y 3 de 3 (31, 19, 24) |

- **Con el PID, 4 de 6 circuitos completos, a una mediana de ~6 cm del tag.** Los dos que
  fallaron fueron con el Tello 7: se fue a la derecha y perdió el tag 2.
- **Con el Kalman, 2 de 2 completos (sin contar el choque), a una mediana de ~20 cm.** Fernando:
  en el Tello 1 "en el primer tag se ponía un poco más adelante"; en el Tello 7 "oscilaba
  mucho, tanto al avanzar como encima de un tag".
- **K1 (E2b, quieto):**
  - **Tello 7.** PID: media 17 cm del despegue (según el piso), máximo 49; aterrizó a menos de
    10 cm de donde despegó. Kalman: media 16, máximo 33; aterrizó a ~30 cm en diagonal.
  - **El Kalman estimó +16 cm/s de deriva a la derecha en el Tello 7,** parecida a la del 11-nov
    (~12).
  - **Tello 1 con PID (14:29):** empujó adelante a fondo los 20 s y el piso lo midió a 71–95 cm
    del despegue, con la altura entre 70 y 132 cm. Falta saber qué se vio.
  - Tello 1 con Kalman: media 12 cm, máximo 33.
  - El vuelo de las 14:32 (`k1_dron1_pid1`) tenía el tag 1 cerca: lo ejecutó y esperó 20 s,
    porque era `--quieto`. No es E5 con PID; ese no se voló.
- **Mandos:** el Kalman cambia 52–55 rc/s quieto, contra 29 del PID; avanzando, parecidos
  (24–30).
- **El modelo del Kalman no cuadra con el dron real.**
  - Con rc 15 adelante, el piso mide 5–11 cm/s (mediana ~9) en los dos drones; el modelo supone
    14.5.
  - El filtro toma la diferencia como una deriva hacia atrás (−5 a −8 cm/s al centrarse), y con
    `kalman_centrar` empuja de más hacia adelante.
  - En el simulador no se veía porque usa el mismo modelo.
- **El choque del Tello 7 con el Kalman (14:53) fue del dron, no del control.**
  - Desde que quedó en el aire pidió adelante a fondo (rc 20, luego 15) por 10 s, y el piso lo
    midió yéndose ~75 cm hacia atrás; Fernando lo vio irse para atrás hasta la malla.
  - Además subió solo de 100 a 130 cm.
  - El Kalman calculó una deriva de −46 cm/s, todavía abajo de su límite de 50; ningún seguro
    lo paró y Fernando usó `k`. Al caer se le salió la pila.
  - Es el síntoma de "el dron no obedece".
- **Inclinación del espejo, medida en vuelo** con los tags de los videos
  (`scripts/inclinacion_vuelo.py`, nuevo):

  | Video | Adelante | Lado |
  |---|---|---|
  | Tello 1, `k1_dron1_pid1` | −10.1° | 0.0° |
  | Tello 1, `k2_dron1_kal1` | −11.9° | −0.4° |
  | Tello 7, `k2_dron7_pid2` | −10.5° | −0.9° |
  | Tello 7, `k2_dron7_kal2` | −9.9° | −1.6° |

  - **El JSON dice +4.1°** (E1 del 9-nov).
  - **E1 en la mano dio** −5.7° (Tello 1) y −7.0° con −13.2° de lado (Tello 7): la mano
    también se inclina.
  - **Cuadra con la cámara del Tello**, que ve 11° hacia abajo, reflejada en un espejo a 45°.
  - **Explica** que la medida del piso marque hacia atrás al subir y hacia adelante al bajar
    ([issue #2](https://github.com/DroneOps/AprilTag-Detection/issues/2)), y que al centrarse
    quede adelante del tag.
- **Temperatura:** 75–84 °C. El Tello 1 no despegó a 84 °C.
- **`resumen_piso.py` confundía un vuelo quieto con uno avanzando** cuando el PID empujaba
  adelante todo el rato. Ahora lo distingue porque, avanzando, el mando de adelante es
  exactamente `advance_fb`.

## 12-nov (tarde) — E5 con el PID en los dos Tellos; el Kalman no se voló

- **La tanda para comparar PID y Kalman se voló en `main`.**
  - No se hizo `git checkout kalman`, y en `main` el `sed` no encuentra `piso_control`, así que
    los 5 vuelos fueron con el PID.
  - El video `k2_dron1_kal1.mp4` también es con PID.
  - Según Fernando, todos los vuelos fueron bien.
- **E5 con PID.** La distancia es al tag al ejecutar, según la cámara:
  - Tello 7: 1 de 3 (el tag 1 a 21 cm; no encontró el 2 en 12 s) y 3 de 3 (8, 7 y 4 cm).
  - Tello 1: 3 de 3 (4, 9 y 33 cm; se voló con `--dron 7` por error) y 3 de 3 (9, 1 y 13 cm).
  - Seis veces "centrado incompleto": a los 8 s ejecuta igual, a 6–34 cm.
- **K1 (E2b) no quedó limpio:** había un tag 1 debajo del despegue; se centró encima y giró.
- **Lo que mostró el PID en vuelo real:**
  - Los mandos cambian 14–32 rc/s (en el simulador, 18–28).
  - Al avanzar casi no se hunde: mínima de 90–94 cm.
  - La integral de adelante termina siempre negativa (−4.5 a −12 rc), en los dos drones. **No es
    una deriva hacia atrás.**
    - Al despegar, el piso mide que el dron se va 6–29 cm hacia atrás; el PID empuja hacia
      adelante para "regresar" y la integral se carga en esos segundos.
    - En E5 la integral de adelante solo trabaja al despegar (avanzando, adelante manda la
      misión), así que llega al final con ese valor.
- **La medida del piso se corre al subir y bajar.**
  - Subiendo marca hacia atrás y bajando hacia adelante (8–25 cm al aterrizar), en proporción
    a la altura: Tello 7 ~0.09 cm por cm y Tello 1 ~0.25.
  - La posición del tag, aterrizando sobre el 7, da casi lo mismo.
  - **Sospecha:** la inclinación real de cada clip no es la del JSON (4.1°, medida el 9-nov con
    un clip). Con el simulador sale Tello 7 ~0° y Tello 1 ~−10°. Si es así, al Tello 1 también
    lo centra ~20–25 cm corrido sobre los tags. Detalle en [`tello.md`](tello.md), "Espejo".
  - **Además, un error en el código:** la medida del piso corrige el cambio de escala alrededor
    del centro óptico de la imagen sin voltear (y = 386 px), cuando va volteada (y = 333).
    - Con los 4.1° del JSON, ese error casi se cancela con la inclinación. Por eso en el
      simulador el arreglo del 12-nov se veía bien.
    - La medida del piso no usa `vista_adelante_deg`: aunque se mida otra inclinación con E1,
      el piso no se entera.
    - Arreglo propuesto ([issue #2](https://github.com/DroneOps/AprilTag-Detection/issues/2)): escalar alrededor del punto que queda justo debajo del dron (centro
      volteado más la inclinación). En una prueba aparte en el simulador, subiendo y bajando
      80 cm con la vista a 4.1°, el error de adelante baja a menos de 1 cm.
- **Temperatura:** el Tello 7 llegó a 80 °C (despegó con 31 % de batería) y el Tello 1 a 77 °C.
- La sesión está en `sesiones/2026-11-12/` (notas, `resumen.txt` y `piso.txt`).

## 12-nov (noche) — Filtro de Kalman en la branch `kalman`, comparado en el simulador

Todo en el simulador, en la branch `kalman` (sale de `main` en `63df8f4`). `main` no cambió.

- **Qué es:** `scripts/kalman_piso.py`, con `"piso_control": "kalman"`. Por eje estima
  posición, velocidad y deriva con el modelo rc → velocidad del simulador; aplica cada medida
  en el momento de la imagen y predice hasta ahora (paso 3), y pide el rc exacto con el
  inverso del modelo (rc 6, 7, 8…: paso 5). Con `kalman_centrar` (prendido) suma la deriva
  estimada también al centrarse sobre el tag. Si deja de cuadrar con lo medido, regresa al
  PID. Cómo funciona y cómo ajustarlo: [`arquitectura.md`](arquitectura.md).
- **Cómo se comparó:** `sim/comparar_control.py` (nuevo), con las mismas semillas para todas
  las variantes: 4 corridas por caso, y 12 con el Tello 7. "PID afinado" es el mejor del
  barrido rápido (`piso_kp` 1.2, `piso_kd` 1.2, `piso_ki` 0.3), para que la comparación sea
  justa con lo que daría el paso 4.

| Simulador completo | PID (hoy) | PID afinado | Kalman | Kalman + centrar |
|---|---|---|---|---|
| Estacionario, dron sano: distancia media al despegue | 11 cm | 7 | 6 | 6 |
| Estacionario, Tello 1 | 10 cm | 6 | 7 | 6 |
| Estacionario, Tello 7 (mediana de 12) | 20 cm | 19 | 22 | 20 |
| Circuito, sano y Tello 1: completas | 8 de 8 | 8 de 8 | 8 de 8 | 8 de 8 |
| Circuito, sano y Tello 1: distancia real al tag al ejecutar (mediana) | 8 cm | 5–8 | 8–9 | **4–6** |
| Circuito, Tello 7: completas | 5 de 12 | 8 de 12 | 5 de 12 | **10 de 12**, luego 7 de 12 (*) |
| Circuito, Tello 7: distancia al tag al ejecutar (mediana) | 21 cm | 24 | 29 | **9–12** |
| Mandos, dron sano: cuánto cambian (rc/s) | 18–20 | 24–32 | 33–43 | 30–42 |

(*) La segunda tanda es con el ajuste de `kalman_lado_avanzando` (abajo); 2 de sus 5 fallas
fueron el seguro apagándose en una racha. Con 12 corridas, 7 contra 10 cabe en el ruido.

- **Kalman + centrar es el mejor en el circuito,** sobre todo en qué tan encima del tag
  ejecuta. Casi toda la mejora sale de cancelar la deriva al centrarse: sin eso, el Kalman
  completa lo mismo que el PID con el Tello 7.
- **Quieto, con dron sano o Tello 1,** el Kalman queda a 6–7 cm contra 10–11 del PID de hoy;
  el PID afinado también llega a 6–7.
- **Con el Tello 7 quieto, todos quedan en ~20 cm.** El simulador le mete rachas de deriva
  de 20–27 cm/s que duran segundos, más de lo que da el Tello con rc 20 (~22 cm/s): ningún
  control las alcanza. Kalman y Kalman + centrar son lo mismo sin tags, así que su diferencia
  (22 contra 20) es el ruido entre corridas.
- **El Kalman manda más seguido** (33–43 rc/s de cambio contra 18–20), pero en pasos chicos
  (rc 6–9) en vez de saltos de 0 a 10. Si el Tello se tambalea con eso, se ve en E2b.
- **De dónde sale la mejora** (modelo rápido sin video, 10 semillas): los pasos 3 y 5
  aplicados al PID con sus ganancias de hoy casi no cambian nada (11 → 10.5–13.6 cm con dron
  sano). Un Kalman con mandos "0 o 10" es igual de preciso que con mandos finos, solo más
  brusco. La mejora viene de que el filtro sabe qué hace cada rc. Afinando el PID (paso 4) se
  iguala la precisión con dron sano, pero con mandos más del doble de bruscos (96 contra 42
  rc/s en ese modelo).
- **Si el dron no es como el modelo** (2 corridas por caso, quieto): con el dron sano, el
  Kalman queda a 5–8 cm en todos los casos y el PID a 8–14. Con el Tello 7, el Kalman queda
  igual o mejor: video atrasado 0.30 s, 16 contra 32 cm; zona muerta 7, 17 contra 28; rc 30 %
  más fuerte, 10 contra 18. Con el dron 30 % más débil, los dos se van (Kalman 65 cm, PID
  187); ahí la deriva le gana a rc 20.
- **Medida al revés** (`--set espejo=h`): el seguro de siempre (`piso_alejandose_cm`) apaga la
  corrección en las 8 corridas, con los dos controles. El Kalman empuja más fuerte y se aleja
  más antes de que se apague: con dron sano, distancia media de 105–182 cm contra 33–103.
- **Se corrigió en el camino:**
  - el umbral de "deriva imposible" pasó de 40 a 50 cm/s (con 40, una racha del Tello 7 lo
    apagó), y al apagarse el PID arranca desde `piso_i_inicial`;
  - **`espejo_gastado` fallaba 4 de 4 con el Kalman** (`main`: 2 de 4; branch con PID: 3 de
    4). El Kalman corregía de lado un poco todo el tiempo mientras avanzaba, y lado y
    adelante a la vez hunden al Tello ~8 cm/s: volaba a 88–95 cm. Ahí el tag manchado no se
    detecta nunca (a 95–110 cm, a veces; probado renderizando encima del tag). Ahora,
    avanzando, no corrige de lado por menos de 4 cm/s (`kalman_lado_avanzando`): 2 de 4. **En
    el Tello real puede pasar lo mismo:** en E2b/E5 con Kalman, revisar `tof` mientras avanza.
- **Regresión completa** (`todos`), con PID y con Kalman: los 17 escenarios de espejo dan lo
  mismo con los dos y sin choques. En pared y piso (no usan este código) cambió lo de siempre
  por la deriva aleatoria (`piso_hundimiento` choca, ya se sabía; `tag_alto`, de pared, chocó
  en una de las dos).
- **Videos lado a lado** (izquierda PID, derecha Kalman, misma semilla), en la laptop, en
  `sim/logs/videos_kalman/`: estacionario y circuito del Tello 7, y circuito del dron sano.
  En esas corridas sueltas los dos completan; el Kalman ejecuta un poco más cerca del tag.
- **Herramientas nuevas en el simulador:** `--set`, `--sim`, `--semilla`, `--log-sufijo`, la
  distancia real al tag al ejecutar y `sim/comparar_control.py`
  ([`simulador.md`](simulador.md)).

## 12-nov — La medida del piso ya no se engaña al subir

- Con un Tello perfecto en el simulador (sin deriva), el control lo movía ~10–12 cm sin
  razón. Al subir, el piso se ve más chico, y la correlación lo tomaba como desplazamiento:
  de 30 a 100 cm en vertical "veía" +10 cm de lado y −7 adelante.
- **Arreglo:** escalar el cuadro anterior alrededor del centro óptico según cuánto cambió la
  altura (tof con la mediana de las pendientes). El error al subir y bajar baja a 2–4 cm; en
  los caminos de lado y adelante no cambia (1–3 cm). El Tello perfecto se queda a ~4 cm del
  despegue.
- **Circuito E5 simulado:** Tello 1, 4 de 4; Tello 7, 1 de 4 (como antes; su deriva aleatoria
  domina).

## 11-nov (noche, 3) — Tramo anclado en el tag e integral inicial por dron

- **`sostener_tag`:** al girar o pausar sobre un tag se centra con su posición, y el tramo
  siguiente pasa por el tag. En el simulador, al terminar de ejecutar queda a ~11 cm del tag
  (mediana), contra ~29 cm.
- **`piso_i_inicial` por dron,** en `config/mision_dron1.json` y `config/mision_dron7.json`;
  la misión real los carga con `--dron N`. Tello 7: 4.5 rc de lado (lo que juntó en el
  simulador); Tello 1: 0. Se confirma con E2b (`piso_ider` al final).
- **Si el dron ya no deriva,** la integral precargada empuja de más unos segundos y se
  corrige sola: +5 cm con 4.5 y +15 cm con 13, en el simulador.
- **Circuito E5 simulado:** Tello 1, 4 de 4; Tello 7, 2 de 4.

## 11-nov (noche, 2) — PID para sostener la posición

- **Parte integral (`piso_ki` 0.15, tope `piso_i_max` 15).** Sin ella, contra una deriva
  constante se quedaba corrido (Tello 7: ~26 cm en teoría y 42–68 en el simulador).
  - Estacionario simulado de 20 s (distancia media al despegue): Tello 7, de 42–68 cm a 21–22
    cm; Tello 1, de 8 a 11–14 cm (con poca deriva la I agrega un poco de vaivén).
  - Circuito E5: el Tello 7 completó 3 de 4 (antes 0) y el Tello 1, 3 de 4.
- Con `--quieto` (E2b) ahora sostiene también hacia adelante; antes solo de lado.
- Escenario nuevo `espejo_estacionario`, y la guía "Cómo ajustarlo" en
  [`arquitectura.md`](arquitectura.md).

## 11-nov (noche) — Simulador con la deriva de cada dron y misión que sostiene su posición

Sin volar. Detalle en [`simulador.md`](simulador.md) y [`arquitectura.md`](arquitectura.md).

- **Simulador:**
  - perfiles por dron (`--dron 1`, `--dron 7`) con la deriva medida;
  - hundimiento al pedir lado y adelante a la vez;
  - corrimiento al girar;
  - piso con la cuadrícula del laboratorio.

  Reproduce lo del 11-nov: el Tello 7 no ve ningún tag y el Tello 1 se salta el 1.
  `sim/deriva_video.py` mide la deriva con los videos.
- **Misión con espejo:** `sostener_piso` mide con el piso cuánto se mueve. Regresa al
  despegue mientras sube, avanza en línea recta y busca el tag que pierde (antes aterrizaba).
  - En el simulador, el Tello 1 pasó de 0 a 3 circuitos completos de 4.
  - Tiene un seguro: si, corrigiendo, se aleja 35 cm en 1.5 s, se apaga (probado con la medida
    al revés). Uno primero de 80 cm desde el despegue la apagaba sin razón con el Tello 7,
    que se va más de 80 cm mientras despega.
- **Regresión:** sin choques en espejo. Hubo dos en pared y piso por los cambios del
  simulador, no de la misión: `tag_bajo` chocó con la pared al girar 180° a 65 cm (el
  corrimiento al girar), y `piso_hundimiento` llegó a 8 cm (estrés de 20 cm/s más el
  hundimiento combinado).

## 11-nov (tarde) — E5 con dos Tellos

Detalle y bitácoras en [`../sesiones/2026-11-11/`](../sesiones/2026-11-11/).

- **E5 no salió sin ayuda.** De 27 corridas (19 del Tello 1, 8 del Tello 7), solo la 7.7
  completó 1 → 2 → 7, y con la mano sosteniéndolo sobre los tags. Sin mano, lo mejor fue la
  1.9: ejecutó 1 y 2 y aterrizó por "el dron no obedece".
- **Deriva a la derecha estando quieto, en los dos drones** (medida con el piso visto por el
  espejo, aproximada). Los tags aparecían en la orilla de la vista y, al ir por ellos, se
  salían: el dron se inclina para moverse y la vista del espejo se inclina con él.
- **El Tello 1 falla caliente:** 6 despegues malos y 4 "no obedece", todos a 68–78 °C.
- **Lo que sí funcionó:**
  - el rumbo tras los giros (88°, ya no se pasa como el 9-nov);
  - la detección de tags gastados: el tag 4 de 62 a 238 cuadros con el rescate, sin IDs
    falsos.
- Los paros con `k` fueron porque los drones se iban contra la malla de la arena.

## 11-nov — Simulador ajustado a los vuelos reales y tags gastados

Sin volar. Detalle en [`simulador.md`](simulador.md).

- Antes, el simulador era optimista. Con rc 15–19 giraba 6 °/s y el real no gira; tras un
  giro el real sigue girando 8° y el simulador no. Además: despegue siempre a 65 cm con
  "ok" a los 2 s, video sin atraso, la mitad de la deriva y subía el doble de rápido.
- Ahora el dron simulado se comporta según **`config/sim_tello.json`**, ajustado con los
  14 vuelos del 9-nov. `--ideal` deja el modelo de antes.
- **`sim/comparar_vuelos.py`** le pasa al modelo los mismos rc de los vuelos reales y compara
  lo que hizo cada uno; con `--ajustar --guardar` reajusta el JSON. Error al predecir 1.5 s
  de vuelo: rumbo 1.2° → 0.9°, altura 6.2 → 4.6 cm, posición del tag 14 → 10 cm.
- Escenarios nuevos: `espejo_despegue_cae`, `espejo_despegue_alto`, `espejo_sin_ok`.
- Según las bitácoras, el 9-nov 6 de 21 despegues se vinieron abajo (subieron y regresaron al piso).
- Regresión realista: la misión con espejo pasa, pero `espejo_inicio` falló 1 de 5 veces
  por la deriva durante el despegue (pendiente 6).
- **Tags gastados:** en los videos de E5 los tags se ven desteñidos (negro ~150 de 255,
  contraste ~105; [`tello.md`](tello.md)). El simulador ahora puede desteñirlos, mancharlos y
  arrancarles pedazos (escenarios `espejo_lab`, `espejo_gastado`).
  - El detector hace un **rescate** cuando no ve nada: umbral más sensible, o imagen
    erosionada con contornos menos exigentes, y solo acepta lo que parece tag.
  - Se confirma con **3 de los últimos 5** cuadros en vez de 3 seguidos.
  - Con `sim/prueba_desgaste.py`: muy desteñido 22 → 79 %, manchas 20 % 16 → 52 %, pedazos
    faltantes 8 % 35 → 60 %, sin IDs equivocados. En los videos reales, 1,634 → 1,685 cuadros
    con tag; el tag 2 dañado de 6 a 20; ningún ID falso.
  - En vuelo simulado con tags gastados, el detector de antes no ejecutó ninguno; el nuevo
    ejecuta 2 o 3 de 3.

## 9-nov — Espejo en vuelo real

Detalle y bitácoras en [`../sesiones/2026-11-09/`](../sesiones/2026-11-09/).

- **Antes de volar** se cambió la misión con espejo (`bb2398f`):
  - sostiene el rumbo en vez de alinearse con los bordes del tag;
  - vuela a 100 cm;
  - avanza hasta 12 s entre tags;
  - ignora el tag de inicio.
- **E1** con el clip impreso: la vista queda inclinada 4.1° hacia adelante y 0.8° de lado.
  **E2** salió bien.
- **E3** salió bien al segundo intento: quedó encima del tag a +2/+0 cm.
- **E5 falló:**
  - **Tag de inicio:** el dron se fue hacia adelante al despegar, vio el tag 1 al empezar a
    avanzar y lo tomó como el de inicio. Ahora solo se ignora el que ve *durante* el
    despegue (`8f23e77`).
  - **Despegue:** subió solo a 151 cm en uno y se regresó al piso en otros. Ahora el
    despegue pasa con el `ok` del Tello y aterriza con aviso si se viene abajo. Se sospecha
    que el clip interfiere con los sensores de la panza.
- **Tarde:**
  - con el Tello #1, el despegue se regresaba solo al piso con y sin clip, y la app avisó
    que su VPS no estaba disponible;
  - con otro Tello, sobre la pista del seguidor de línea, el estacionario con clip salió
    bien, pero en E5 se iba a la derecha.
  - Causas encontradas:
    - el tag 1 estaba debajo del despegue y se ignoraba como "de inicio"
      (`ignorar_inicio` → `false`);
    - el centrado oscilaba ±15–20 cm (ahora frena con la velocidad del tag y ejecuta a
      ≤12 cm o a los 8 s);
    - tras el giro, el rumbo seguía rotando de 90° a 101° porque la corrección con rc 15
      caía en la zona muerta del Tello (`heading_min` 20).

  `DroneOps/Line_Follower` funciona con el mismo dron, no tiene configuración especial y
  también usa espejo. Commits: `324a07d`, `4a93400`, `fcaaabd`.
- Se agregaron `sesiones/` (cada día con sus bitácoras), `scripts/guardar_sesion.py`,
  `scripts/traza_vuelo.py` y `CLAUDE.md`, para que el equipo trabaje y se revise desde GitHub.

## 28-oct — Clip de espejo para impresión 3D

Del STL del clip actual se sacaron las medidas: 43.5 × 25.2 × 11.7 mm, placa a 45°.
Con la cámara inclinada 11°, un espejo a 45° apunta la vista 11° hacia adelante de la
vertical; para ver justo abajo hace falta 50.5°. El prompt para diseñar los prototipos
está en `anexos/`.

## 27-oct (tarde) — El dron no obedece

Al dron se le pidió quedarse y subir a fondo: avanzó 120 cm y bajó 45 cm mientras su IMU
decía "nivelado". Pidiéndole bajar, subió. En estacionario se hundía solo. Diagnóstico:
**IMU descalibrado o hélice dañada**, tras varias caídas con paro de motores, volando a
80–86 °C.

En código (`bd9aa89`):
- el sostener altura es más suave y apunta a la altura de crucero;
- el despegue espera el `ok` del Tello;
- el dron aterriza solo si **no obedece** o si **avanza solo** mientras se centra.

Las reglas se verificaron sobre las bitácoras reales: se activan en los vuelos malos y
en ninguno de los buenos.

## 27-oct (mañana) — Piso sin espejo, primera tanda con el código nuevo

- **P1 (flip) aprobada:** de 125 a 81 cm, se estabilizó en 72.
- **Aterrizajes falsos por "obstáculo":** eran reales hundimientos (~10–13 cm/s al
  avanzar, confirmado con la altura que da el PnP). Se quitó el aterrizaje por obstáculo
  y se hizo más fuerte el sostener altura.
- **Se pasaba hasta 90 cm del tag:** pedir adelante y de lado a la vez lo frenaba a
  ~10 cm/s, así que la velocidad medida era baja; a ciegas iba a ~19. Ahora el
  acercamiento se centra primero y luego va recto, midiendo la velocidad solo en el
  tramo recto (`ce4484e`).
- **Detección pobre en movimiento:** se subió la corrección de bits (+15–130 % de
  detecciones, sin IDs falsos).
- **En el simulador:** su paso de física fijo hacía más lento al dron con el CPU ocupado;
  ahora usa el tiempo real.

## 26-oct — Espejo, piso y respuesta del comité

- **Espejo (E1–E3):**
  - la detección a través del espejo funciona;
  - la inclinación medida de la vista es 7.9° hacia adelante y 4.3° de lado;
  - problemas: el montaje tapó el sensor de abajo, la altura variaba 95–118 cm y el espejo
    estaba sucio.
- **Piso (F1–F4):**
  - se quedaba corto porque la velocidad real con `rc` 15 variaba de 12 a 20 cm/s;
  - **dos flips cayeron al piso:** el dron cae ~50 cm/s tras el flip y su `h` no se entera.

  Se cambió a: medir la velocidad en cada acercamiento, y subir a fondo tras el flip
  hasta frenar la caída (`bc656fe`).
- **Comité:** tags en el piso, espejo permitido, recorrido desconocido.

## 24-oct — Calibración de `rc` y pruebas de pared

- La tabla de velocidades reales está en [`tello.md`](tello.md).
- Aprobadas P4 (tag alto: sube mientras se acerca) y P5 (tag girado).
- **Flip:** cayó de 117 a 39 cm; la recuperación se daba por buena mientras seguía cayendo.

## 21-oct — Calibración, primeros vuelos, misión de pared y flips

- **Cámara:**
  - calibrada con el tablero del club (`config/camera_tello.json`);
  - la pose se validó contra alturas medidas (67 vs 66 cm, 105 vs 100 cm);
  - campo de visión real 55° × 43°, eje 11° hacia abajo.
- **Detección de tags en el piso:** medida a 30, 66 y 100 cm de altura (ver `tello.md`).
- **Primeros vuelos:** el estacionario es muy estable; la deriva ocurre en el despegue.
  Se ajustó el giro por `rc`.
- **Misión de pared:** el tag 2 se ejecutó de punta a punta. Se agregaron, uno a uno, el
  centrado lateral, la alineación de frente al tag y el control en el marco del tag.
- **Flips:** funcionan, pero el dron pierde 30–78 cm; sin corrección cae al piso. De ahí
  salió la subida previa a 130 cm.
- **`h` no sirve:** desde entonces la altura es `tof − 10`.

## 17-oct — Detección

- Se probó la detección con webcam y con el Tello en la mano.
- Los tags del reglamento decodifican a los IDs 1–10.
- El dron resultó ser un Tello estándar: no hay cámara de abajo.
- djitellopy entrega RGB y empareja las respuestas sin correlación.

## Decisiones que conviene no deshacer

| Decisión | Por qué |
|---|---|
| Altura con `tof − 10`, nunca con `h` | `h` deriva y a veces dice lo contrario de lo que pasa |
| Confirmar despegue, aterrizaje y flip por telemetría | las respuestas de djitellopy se desfasan |
| Sostener el rumbo del tramo, no alinearse con los bordes del tag | el reglamento pide tolerar tags girados |
| En piso, centrar primero y avanzar después | el mando combinado frena al dron y arruina la velocidad medida |
| Subir a 130 cm antes de cada flip y frenar la caída después | tras el flip el dron cae ~50 cm/s |
| Probar en el simulador antes de volar | cada vuelo real cuesta batería, tiempo y a veces una hélice |
