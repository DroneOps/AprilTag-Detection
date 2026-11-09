# Sesión 2026-11-09

Veredictos por vuelo en `resumen.txt`; bitácoras en `vuelos/`.

## 15:17

Con espejo (clip impreso). E1: inclinación 4.1° adelante y 0.8° de lado (ya en config/mission_espejo.json). E2 bien. E3 bien al segundo intento (encima a +2/+0 cm). E5 falló: (1) tomó el tag 1 como 'tag de inicio' por la deriva del despegue y lo ignoró — corregido en 8f23e77; (2) despegues que subían solos a 151 cm o se regresaban al piso — sospecha: el clip interfiere con los sensores de la panza. Pendiente: prueba de estacionario con y sin clip.

## 17:16

Estacionario con clip (17:14) y sin clip (17:15), batería 90–95 %, 58–67 °C. En los DOS el despegue subió a ~70 cm y se regresó solo al piso; el aviso 'el despegue se vino abajo' aterrizó bien. El h del Tello subía (60→120) mientras el tof bajaba (70→13): la estimación de altura interna del Tello está mal. NO es el clip. Siguiente: calibrar IMU y centro de gravedad en la app Tello, encender el dron quieto sobre superficie plana, revisar firmware y repetir el estacionario sin clip.

## 17:21

Tras calibrar el IMU, volando con la app oficial Tello aparece 'Aviso de posicionamiento visual no disponible, aterrice cuanto antes'. El sistema de visión de abajo (VPS: cámara y sensores de la panza) no funciona; eso explica la deriva y la altura que se va de hoy, y no depende de nuestro código ni del clip. Revisar: sensores de la panza limpios y sin nada encima, buena luz, piso con textura; si persiste, daño del módulo VPS (hubo caídas) -> reparar o usar otro Tello.

## 17:21

El aviso de 'posicionamiento visual no disponible' sigue con buena luz, piso con textura y la panza limpia: el sistema de visión de abajo (VPS) de este Tello parece dañado (cámara, sensor o cable, probablemente por las caídas). Con este dron no se puede seguir; hay que usar otro Tello o reparar el módulo.

## 17:35

Con OTRO Tello (17:22–17:32) también deriva hacia atrás y se tambalea, durante el despegue y el estacionario con rc en 0 (el programa no manda nada). Voló a 73–84 °C y en dos corridas con 38–41 % de batería. Se revisó DroneOps/Line_Follower (funciona con ese mismo dron): no tiene configuración especial del Tello (connect, streamon, takeoff bloqueante, rc ~30 Hz) y también usa espejo (voltea la imagen). Conclusión: la diferencia es el lugar (luz y textura del piso para la cámara de abajo) y la temperatura, no el código. Siguiente: estacionario sobre la pista donde vuela el seguidor de línea, con el dron frío y batería > 70 %.
