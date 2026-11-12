# Sesión 2026-11-11

Veredictos por vuelo en `resumen.txt`; bitácoras en `vuelos/`.

## 20:17

E5 con espejo y dos drones: Tello 1 (19 corridas, videos e5_hoy1_dron1.*) y Tello 7 (8 corridas, dron7.*). Solo la 7.7 completó 1 -> 2 -> 7, y fue con la mano de Fernando sosteniéndolo sobre los tags: sirve para ver que la secuencia funciona, no para ajustar (los tres centrados se acabaron por tiempo). Sin mano, lo mejor fue la 1.9: ejecutó 1 y 2 y aterrizó por 'el dron no obedece'.
- Tello 1, caliente: 5 despegues que no subieron más de 16 cm (1.7, 1.10, 1.11, 1.12, 1.16); en la 1.8 el tof decía 12 cm y h 250 cm; 4 veces 'el dron no obedece' (1.2, 1.4, 1.9, 1.18), bajando 25–60 cm al pedirle subir (en la 1.18 llegó a 12 cm). Todo a 68–78 °C. Ya frío (1.14, 55 °C) despegó bien. Se volaron 27 corridas en 26 min sin enfriar.
- Deriva a la derecha en los dos, medida con el piso visto por el espejo (aproximada): Tello 7 de 15 a 37 cm/s en estacionario (estacionario2: +35 cm en 1.1 s; el primer estacionario se fue a la malla); Tello 1 ~6–7 cm/s parejo (estacionario_nuevo1: +67 cm en 10 s), también sin espejo. Sin ventiladores. Por la deriva los tags aparecían en la orilla de la vista (Tello 1: 35–46 cm a la izquierda) y se perdían al centrarse (1.1, 1.5, 1.14). Los paros con k fueron porque se iban a la malla.
- Rumbo tras los giros bien: quedó en 88° y no se siguió pasando. En el giro de la 1.9 el dron se desplazó ~33 cm.
- Tags gastados (test_tags.py con y sin --sin-rescate): el tag 4, el más gastado, pasó de 62 a 238 cuadros detectados con el rescate; en E5, de 1431 a 1666 cuadros con tag; ningún ID falso.
- Estacionarios: estacionario, 2 y 3 fueron con el Tello 7 (con espejo; en el 3 sale una mano); estacionario_nuevo1 y los dos sin espejo, con el Tello 1.

### Qué dron fue cada bitácora

Emparejadas por la hora de término del video (coinciden al segundo). Los estacionarios con espejo fueron con el Tello 7 y los "nuevo" con el Tello 1, según Fernando y la deriva medida.

| Bitácora | Video (en la laptop) | Dron |
|---|---|---|
| `espejo_20261111_164656.csv` | `e5_hoy1_dron1.mp4` | Tello 1 |
| `espejo_20261111_164909.csv` | `e5_hoy1_dron7.mp4` | Tello 7 |
| `espejo_20261111_165006.csv` | `e5_hoy1_dron7.1.mp4` | Tello 7 |
| `espejo_20261111_165036.csv` | `e5_hoy1_dron7.2.mp4` | Tello 7 |
| `espejo_20261111_165203.csv` | `e5_hoy1_dron1.1.mp4` | Tello 1 |
| `espejo_20261111_165237.csv` | `e5_hoy1_dron1.2.mp4` | Tello 1 |
| `espejo_20261111_165408.csv` | `e5_hoy1_dron1.3.mp4` | Tello 1 |
| `espejo_20261111_165451.csv` | `e5_hoy1_dron1.4.mp4` | Tello 1 |
| `espejo_20261111_165630.csv` | `e5_hoy1_dron7.3.mp4` | Tello 7 |
| `espejo_20261111_165659.csv` | `e5_hoy1_dron7.4.mp4` | Tello 7 |
| `espejo_20261111_165727.csv` | `e5_hoy1_dron7.5.mp4` | Tello 7 |
| `espejo_20261111_165927.csv` | `e5_hoy1_dron1.5.mp4` | Tello 1 |
| `espejo_20261111_170003.csv` | `e5_hoy1_dron1.6.mp4` | Tello 1 |
| `espejo_20261111_170058.csv` | `e5_hoy1_dron1.7.mp4` | Tello 1 |
| `espejo_20261111_170119.csv` | `e5_hoy1_dron1.8.mp4` | Tello 1 |
| `espejo_20261111_170151.csv` | `e5_hoy1_dron1.9.mp4` | Tello 1 |
| `espejo_20261111_170342.csv` | `e5_hoy1_dron1.10.mp4` | Tello 1 |
| `espejo_20261111_170359.csv` | `e5_hoy1_dron1.11.mp4` | Tello 1 |
| `espejo_20261111_170426.csv` | `e5_hoy1_dron1.12.mp4` | Tello 1 |
| `espejo_20261111_170612.csv` | `e5_hoy1_dron7.6.mp4` | Tello 7 |
| `espejo_20261111_170639.csv` | `e5_hoy1_dron7.7.mp4` | Tello 7 |
| `espejo_20261111_170958.csv` | `e5_hoy1_dron1.14.mp4` | Tello 1 |
| `espejo_20261111_171028.csv` | `e5_hoy1_dron1.15.mp4` | Tello 1 |
| `espejo_20261111_171121.csv` | `e5_hoy1_dron1.16.mp4` | Tello 1 |
| `espejo_20261111_171215.csv` | `e5_hoy1_dron1.17.mp4` | Tello 1 |
| `espejo_20261111_171241.csv` | `e5_hoy1_dron1.18.mp4` | Tello 1 |
| `vuelo_20261111_163147.csv` | `estacionario.mp4` | Tello 7 |
| `vuelo_20261111_163320.csv` | `estacionario2.mp4` | Tello 7 |
| `vuelo_20261111_163411.csv` | `estacionario3.mp4` | Tello 7 |
| `vuelo_20261111_163641.csv` | `estacionario_nuevo1.mp4` | Tello 1 |
| `vuelo_20261111_163722.csv` | `estacionario_nuevo_sinespejo.mp4` | Tello 1 |
| `vuelo_20261111_163749.csv` | `estacionario_nuevo_sinespejo2.mp4` | Tello 1 |
