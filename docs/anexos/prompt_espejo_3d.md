Necesito diseñar en Autodesk Fusion 360 y preparar para impresión en OrcaSlicer varios prototipos de un clip con espejo para un dron DJI Ryze Tello (modelo estándar). Usa tus conexiones con Fusion 360 y OrcaSlicer. Te adjunto el STL del clip que ya tenemos (Tello_Mirror_Clip_2.STL) y fotos de cómo se monta.

## Para qué es

Competencia de drones autónomos: el Tello debe detectar etiquetas AprilTag **pegadas en el piso** usando su única cámara, que mira al frente. El espejo, puesto delante de la lente, desvía la vista hacia el suelo. Las reglas permiten el espejo como accesorio.

## Datos de la cámara (medidos, no del catálogo)

- Lente al centro del frente del Tello, en la parte de arriba de la "nariz".
- Campo de visión real: **55° horizontal × 43° vertical** (imagen 960×720).
- El eje óptico apunta **11° hacia abajo** respecto al plano horizontal del dron.
- Con el clip actual (placa a 45°), la vista reflejada quedó **7.9° hacia adelante** de la vertical y 4.3° hacia un lado. Eso cuadra con la teoría: espejo a 45° ⇒ vista a 11° de la vertical.

Relación útil, en vista lateral y con ángulos medidos desde la horizontal (negativo = hacia abajo): si un rayo sale de la cámara con ángulo θ_in y el espejo forma una línea con ángulo φ, el rayo reflejado sale con **θ_out = 2·φ − θ_in**.
- Para ver justo hacia abajo (θ_out = −90°) con el eje a θ_in = −11°: **φ = −50.5°**, o sea, espejo a 50.5° de la horizontal.
- Con φ = −45°: el centro de la vista queda a 11° de la vertical, hacia adelante.

La cara reflejante mira hacia atrás y hacia abajo (hacia la lente). El borde de arriba del espejo queda cerca de la lente y el de abajo más adelante.

## Clip actual (del STL adjunto, en mm)

- Caja total: **43.5 × 25.2 × 11.7 mm**. Volumen ~786 mm³ (~1 g en PLA).
- Marco de **3.5 mm** de grueso con dos brazos laterales (x ≈ ±16.3 a ±21.8 mm) que terminan en ganchos. Así se sujeta al Tello; **este ajuste ya funciona**: reprodúcelo igual (importa el STL como referencia o mídelo de ahí).
- Placa central para el espejo: **20.2 mm de ancho, a 45°, ~16.7 mm a lo largo de la inclinación**.
- Con esa placa, el espejo tapaba toda la imagen.

## El espejo nuevo

- **~23 × 15 mm**. El grosor está por medir; pregúntamelo. Deja 0.2 mm de holgura por lado en el alojamiento.
- Va pegado o encajado sobre la cara del lado de la lente. El marco no debe tapar la superficie reflejante dentro del campo de visión.

## Requisitos para todos los prototipos

1. **Paramétrico** (parámetros de usuario en Fusion): ángulo del espejo, ancho, alto y grosor del espejo, distancia de la lente al espejo, holgura del ajuste, y para el prototipo C la línea de corte.
2. **Mismo sistema de sujeción** que el clip actual. Que se pueda poner y quitar sin herramientas y que **no se mueva ni vibre**: si el espejo se mueve, la imagen no sirve y además se hacen flips de 360°.
3. **No tapar los sensores de abajo** del Tello (cámara de posicionamiento y sensor de distancia en la panza). Ya nos pasó con un montaje: el dron creía estar en el piso y no despegaba.
4. **Nada más abajo que la base del dron**: el Tello aterriza sobre su panza y el clip no debe tocar el piso antes.
5. No acercarse a las hélices ni a sus protectores.
6. **Peso: ≤ 2 g** la pieza impresa, sin contar el espejo.
7. Que se imprima sin soportes, o con soportes mínimos fáciles de quitar.
8. Ninguna parte del marco dentro del cono de visión (ni el directo ni el reflejado). **Verifícalo en Fusion**: modela el campo de visión como una pirámide de 55°×43° desde la lente, inclinada 11° hacia abajo, y su reflejo en el espejo. Revisa que el espejo cubra la parte que le toca y que nada del clip se meta en los conos.

## Prototipos

**A. Espejo completo a 45°** (como el actual, con el espejo nuevo).
Cubre toda la imagen; la vista apunta ~11° hacia adelante de la vertical. Haz dos variantes con el espejo girado: el lado de 23 mm horizontal y el lado de 23 mm a lo largo de la inclinación. Dime cuál cubre todo el campo de visión según tu verificación.

**B. Espejo completo a 50.5°**: la vista apunta justo hacia abajo. Igual que A en todo lo demás.

**C. Mitad al frente, mitad al piso.**
El espejo tapa solo la **mitad de arriba de la imagen**. La mitad de abajo sigue viendo al frente sin obstáculos.
- **Por qué arriba:** el eje va 11° hacia abajo. Volando a 60 cm, la mitad de abajo de la imagen ve el piso entre ~1 y ~3 m adelante, que es donde detectamos los tags; la mitad de arriba solo ve paredes.
- **Ángulo:** 45°, para que el centro de esa mitad (rayos a ~0°) se refleje justo hacia abajo.
- **Línea de corte:** el borde de abajo del espejo (el de adelante) debe quedar sobre el eje óptico, para que corte la imagen a la mitad. Hazlo un parámetro y saca tres variantes: el espejo tapando el 40 %, el 50 % y el 60 % de arriba.
- **Sujeción:** el espejo debe sostenerse desde arriba y por los lados. Debajo del espejo no puede haber nada, porque por ahí pasan la vista directa al frente y la vista reflejada hacia el piso.

## OrcaSlicer

Antes de laminar, pregúntame qué impresora y qué filamento uso. Mi sugerencia de partida, que puedes ajustar:
- PETG si los ganchos deben flexionar; si no, PLA.
- Capa de 0.12–0.16 mm, porque las piezas son chicas.
- 3–4 perímetros e infill alto, para que no flexione.
- Orientación que deje lisa la cara donde va el espejo y que no dependa de soportes en los ganchos.
- Borde (brim) si la pieza es muy pequeña para pegarse a la cama.

## Lo que necesito que entregues

1. El diseño en Fusion 360 con sus parámetros, y un STL o 3MF por prototipo y variante (A1, A2, B, C40, C50, C60).
2. El proyecto de OrcaSlicer laminado de cada uno, con tiempo y peso estimados.
3. Una tabla por prototipo con:
   - ángulo del espejo;
   - hacia dónde apunta el centro de la vista reflejada;
   - qué porcentaje del campo de visión cubre el espejo;
   - confirmación de que no hay obstrucciones;
   - peso de la pieza.
4. Una lista de qué debo medir en el dron real si algo no está en el STL: posición de la lente respecto a los ganchos, grosor del espejo, etc.

Antes de empezar, hazme las preguntas que necesites: impresora, filamento, grosor del espejo y cualquier medida del dron que no puedas sacar del STL.
