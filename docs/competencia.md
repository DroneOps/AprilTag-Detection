# La competencia

**Autonomous Mechatronics Grand Prix 2026 (TECH FEST 2026)** — sábado 5 de diciembre
de 2026, Campus Hidalgo. Categoría **Drones autónomos – Detector de AprilTags**.

El reglamento original (`Reglamento_05_Drones_Autonomos_AprilTags.docx`) no está en el
repo: pídeselo al equipo. Aquí va lo que importa para el código.

## Reglas clave

- Equipos de 1 a 5 alumnos del Tec. Dron sugerido: **DJI Tello** (estándar o EDU).
- **Prohibido:** control manual, alterar la pista o poner marcas, modificaciones
  estructurales al dron y prestar drones entre equipos.
- **Interfaz (HMI) obligatoria:** video en vivo, detección de tags, estado del sistema y un
  **botón de paro** que aterrice (con mouse y teclado). Solo monitorea: no manda comandos.
- **Descalificación:** intervención manual, falta de autonomía, comportamiento inseguro,
  manipular el entorno o cualquier evidencia de ruta preprogramada.

## Pista y etiquetas

- Pista física sobre MDF con **trayectoria visible**. Las **intersecciones** tienen
  etiquetas AprilTag de la familia **tag25h9**. Hay una etiqueta especial de inicio y
  otra de final.
- Las etiquetas se colocan al azar. Tras ejecutar cada una, el dron **avanza siempre hacia
  el frente** hasta la siguiente; la última es la de aterrizar.
- El comité puede reacomodar las etiquetas durante la competencia y el sistema debe
  tolerar **etiquetas giradas**.

| ID | Función | ID | Función |
|---|---|---|---|
| 1 | Giro a la derecha 90° | 6 | Bajar 30 cm |
| 2 | Giro a la izquierda 90° | 7 | Aterrizar |
| 3 | Giro de 180° | 8 | Giro de 180° y flip de 360° |
| 4 | Flip de 360° | 9 | Detenerse 5 s y continuar |
| 5 | Subir 30 cm | 10 | Giro de 360° |

Verificado el 17-oct: los tags de la Figura 1 del reglamento decodifican a los IDs 1–10
en el orden de la figura, así que **ID = número de función** (`TAG_FUNCTIONS` en
`scripts/test_tags.py`).

## Puntuación

Tres intentos por equipo. **Un punto por cada etiqueta detectada correctamente**; se suman
los tres intentos y el tiempo total solo desempata. Importa llegar a cada tag sin fallar,
no la velocidad. Hay que estar presente al iniciar la ronda (2 min de tolerancia).

## Lo que respondió el comité (26-oct)

- Las etiquetas estarán **en el piso**.
- El tamaño "está en el reglamento", pero **nuestra copia no lo trae**: en la Figura 1
  miden 2.6 cm y es solo una ilustración. Seguimos sin saberlo.
- **Se permite** un accesorio como el espejo.
- El trazo no está definido: hay que darle continuidad al recorrido **sin conocer el orden**.

## Preguntas abiertas

Lo que el comité no ha respondido está en el correo (`anexos/correo_comite.md`). Lo más
importante:

1. **Tamaño de las etiquetas** (cm por lado). Cambia desde qué distancia se detectan.
2. **Cómo es la trayectoria visible:** ¿una línea como la del seguidor (10 cm)? ¿De qué
   color? ¿El tag va encima de la línea en cada intersección?
3. **Etiqueta de inicio:** ¿es una de las 10 o una distinta?
4. Distancia típica entre intersecciones, obstáculos y tiempo límite por intento.

## Estrategia actual

- **Sin espejo** (`scripts/mision_piso.py`): la cámara al frente ve los tags del piso
  entre ~1 y ~1.7 m adelante y recorre a ciegas el último metro.
- **Con espejo** (`scripts/mision_espejo.py`): la cámara ve hacia abajo y el dron se
  centra encima del tag. Es más preciso, pero no ve hacia adelante. Hay prototipos de
  clip en diseño (`anexos/prompt_espejo_3d.md`), incluido uno de mitad frente y mitad piso.
- **Misión de pared** (`scripts/mission_tags.py`): quedó como base de las otras dos (las
  acciones, el flip y la seguridad viven ahí). Los tags no irán en pared.
