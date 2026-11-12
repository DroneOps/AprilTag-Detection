# Sesión 2026-11-12

Veredictos por vuelo en `resumen.txt`; bitácoras en `vuelos/`.

## 13:29

Tanda K1/K2 (PID contra Kalman), pero en main: no se hizo git checkout kalman, el sed no cambió nada (main no tiene piso_control) y los 5 vuelos fueron con el PID de main. El Kalman no se voló. Fernando: todos fueron muy bien. Distancias al tag según la cámara (piso.txt, de scripts/resumen_piso.py de la branch kalman).
- 13:17 Tello 7, --quieto (k1_dron7_pid1): había un tag 1 debajo; se centró (1 cm), giró y esperó 20 s. No sirve como E2b limpio.
- 13:18 Tello 7, E5 (k2_dron7_pid1): tag 1 a 21 cm (centrado incompleto por tiempo); no encontró el 2 en 12 s y aterrizó.
- 13:19 Tello 7, E5 (k2_dron7_pid2): 1, 2 y 7 a 8, 7 y 4 cm. Despegó con 31 % de batería y llegó a 80 °C.
- 13:21 Tello 1 con --dron 7 por error (piso_i_inicial 4.5 en vez de 0), E5 (k2_dron1_pid1): 1, 2 y 7 a 4, 9 y 33 cm.
- 13:23 Tello 1: PARO a mano con q al despegar (5 s).
- 13:23 Tello 1, E5 (grabado como k2_dron1_kal1, pero con PID): 1, 2 y 7 a 9, 1 y 13 cm.
PID en vuelo real: mandos 14-32 rc/s (el simulador da 18-28), altura al avanzar mínima 90-94 cm (casi no se hunde) y la integral de adelante termina siempre negativa (-4.5 a -12 rc).

## 14:37

PID1 Dron 1: Despues de detectar el primer tag este no continuo avanzando y se quedo en el mismo lugar, Kalman completo todo el circuito de manera correcta pero en el primer tag al intenter colocarse arriba del tag el dron se ponia un poco mas adelante de lo que debia, pero en general no tuvo tambaleos ni errores de deteccion.
