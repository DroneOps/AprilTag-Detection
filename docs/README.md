# Documentación

Si eres nuevo en el proyecto, léelos en este orden:

1. [`competencia.md`](competencia.md): qué hay que lograr, reglas, puntuación, lo que
   respondió el comité y lo que falta saber.
2. [`tello.md`](tello.md): lo que medimos del dron real. Casi cada decisión del código sale
   de aquí.
3. [`arquitectura.md`](arquitectura.md): cómo está organizado el código, los hilos, la
   máquina de estados, la visión, la seguridad y la configuración.
4. [`simulador.md`](simulador.md): cómo probar sin volar y qué escenarios hay.
5. [`laboratorio.md`](laboratorio.md): el protocolo para las sesiones con el dron.
6. [`bitacora.md`](bitacora.md): qué se probó en cada sesión, qué salió, qué está pendiente
   y las decisiones que conviene no deshacer.

## Anexos

- [`anexos/correo_comite.md`](anexos/correo_comite.md): dudas que le mandamos al comité.
- [`anexos/prompt_espejo_3d.md`](anexos/prompt_espejo_3d.md): prompt para diseñar e
  imprimir los prototipos del clip de espejo, con Fusion 360 y OrcaSlicer.

## Mantener esto al día

- Al terminar una sesión de laboratorio, agrega una entrada en `bitacora.md`.
- Si cambia el protocolo, actualiza `laboratorio.md`.
- Si medimos algo nuevo del dron, va en `tello.md`.
- Si cambia la estructura del código o se agrega un archivo de configuración, actualiza
  `arquitectura.md`.
- Si se agrega un escenario al simulador, va en `simulador.md`.
