# Guía del dashboard generado, el panel, el ejemplo y las tarjetas

Esta guía cubre las cuatro formas de ver y controlar tu coche Deepal en Home Assistant:

1. **Dashboard generado**: una vista por coche que crea la propia integración desde el diálogo de
   nuevo dashboard, sin YAML.
2. **Panel integrado**: una página propia en la barra lateral que aparece sola, sin YAML ni
   tarjetas adicionales.
3. **Dashboard de ejemplo**: la vista de referencia para quien prefiera un dashboard propio.
4. **Tarjetas `deepal-card` y `deepal-compact-card`**: la tarjeta completa y una compacta para
   colocar en cualquier dashboard.

## 1. Dashboard generado

- En **Ajustes → Paneles → Añadir panel** elige **Community dashboards → Deepal**: la integración
  genera un dashboard con **una vista por coche**, sin YAML y sin configurar nada.
- Cada vista trae la **tarjeta completa** del coche más las secciones de su modelo: controles
  rápidos, gráficas de batería y autonomía (y de combustible en el PHEV), neumáticos y —en los
  modelos que lo reportan— **Conducción** (velocidad, marcha, kilómetros) y **Ambiente**
  (temperatura exterior, PM2.5, calidad del aire), además de una tarjeta de avisos.
- La entrada en el diálogo necesita Home Assistant 2026.5 o superior; en versiones anteriores se
  puede crear el mismo dashboard desde un panel en modo YAML con:
  ```yaml
  strategy:
    type: custom:deepal
  ```
- Se **regenera solo** cuando añades o quitas un coche o cambian sus entidades (la estrategia
  declara los registros de dispositivos y entidades como dependencias).
- El dashboard generado depende de la integración: si la quitas, sus vistas dejan de resolverse.

## 2. Panel integrado

- Es **opcional**: al configurar la integración se pregunta si quieres añadirlo (viene
  **desactivado**) y puedes cambiarlo después en las opciones de la integración (Configurar →
  «Mostrar el panel en la barra lateral»).
- Con el panel activado aparece **Deepal** en la barra lateral para **todos los usuarios** de Home
  Assistant. El botón **Configurar** abre las opciones de la integración (allí activas o desactivas
  el panel); el panel se abre desde la barra lateral.
- Se adapta a tu instalación: descubre el coche y sus entidades desde los registros de Home
  Assistant, así que funciona con cualquier nombre, área o idioma, y con varios coches.
- **Franja de datos fijos**: batería (con rayo mientras carga), autonomía, **cierre centralizado** y
  **frescura** (conexión con la nube y última actualización) siempre visibles, en cualquiera de las
  pestañas.
- Pestañas:
  - **Estado**: imagen del coche por capas girada 90° a la izquierda y recortada a un marco 750:550
    (capó, puertas, ventanillas, maletero y luces en vivo), con un único chip de **cierre
    centralizado** debajo; controles de
    cierre, ventanillas, maletero, destello, claxon y destello+claxon; odómetro y estado de carga;
    neumáticos con sus alarmas; **avisos** (batería de 12 V, ABS, frenos, dirección, potencia…), que
    aparecen solo mientras hay alguno activo; y el bloque **Energía** en los coches de combustible
    (PHEV).
  - **Conducción** (en los modelos que la reportan, como el S07): velocidad, marcha, freno de mano,
    estado del vehículo, km de ayer y del trayecto, y el bloque de ambiente (temperatura exterior,
    PM2.5, calidad del aire).
  - **Clima**: climatización (encender/apagar y temperatura), asientos delanteros
    (calefacción/ventilación) y **traseros** en los coches que los tengan, volante calefactable y la
    temperatura interior con la **humedad** a su lado.
  - **Carga**: cable, corriente (AC/DC cuando el coche las separa), tiempo restante en H:MM,
    **programación de carga** (interruptor y horas), **límite de carga** en los coches que lo
    permitan y las sesiones registradas —la última por encima de la programación y la que está en
    curso al final— con el nivel **y la autonomía** de inicio y fin.
- No necesita recursos Lovelace ni tarjetas de terceros: todo lo sirve la propia integración.

## 3. Dashboard de ejemplo

Fichero (en el repositorio, carpeta `guides/dashboards/`):

| Fichero | Qué es |
| --- | --- |
| `deepal-dashboard.example.yaml` | La vista completa: la tarjeta del coche más Controles, Batería y autonomía, Neumáticos y Avisos |

**Requisitos**

- La integración **Deepal Alternative** y nada más: el ejemplo usa la tarjeta que incluye la
  integración y tarjetas estándar de Home Assistant. No hacen falta tarjetas de HACS, ni
  ayudantes, ni recursos adicionales.

**Cómo montarlo**

1. Abre el dashboard donde quieras la vista y entra en el **editor de código (RAW)** (menú ⋮ →
   Editar → ⋮ → Editar en modo YAML).
2. Pega el contenido de `deepal-dashboard.example.yaml` (la clave raíz es `views:`).
3. Sustituye los marcadores:
   - `<device_id>`: el coche que muestra la tarjeta. Añade `custom:deepal-card` una vez desde el
     selector de tarjetas; el formulario lista los vehículos de la integración y el id que aparece
     allí es el que hay que pegar.
   - `garaje_deepal_s05_...`: los `entity_id` dependen del nombre, el área y el idioma con que se
     crearon tus entidades (consulta **Herramientas para desarrolladores → Estados**).
4. Guarda.

**Qué trae la vista**

- La **tarjeta completa** a ancho completo con las tres pestañas del panel.
- **Controles**: cierre (con botones de abrir y cerrar en el propio tile), ventanillas, maletero,
  destello, claxon, destello+claxon y actualizar datos.
- **Batería y autonomía**: dos gráficos de 24 h, una métrica por gráfico.
- **Neumáticos**: las cuatro presiones; pulsa para ver el detalle.
- **Avisos**: una línea con todo lo accionable (puertas, ventanillas, maletero, capó, cierre,
  alarmas de neumáticos, cable conectado sin cargar, batería baja y sin conexión) o «todo en
  orden».

**Si usabas el ejemplo anterior**

- El ejemplo antiguo necesitaba las tarjetas **mushroom** (HACS), dos ayudantes `input_select` de
  navegación y el fichero de ayudantes. Nada de eso hace falta ahora: puedes borrar esos
  `input_select` y los `select` de plantilla si solo los usabas para aquel dashboard.
- El **cargador doméstico (V2C)** sigue sin aparecer: la pestaña de carga de la tarjeta usa solo
  entidades de la integración. Si quieres tus atajos del cargador, añádelos como tarjetas propias.

## 4. Tarjetas Deepal

### Completa (`custom:deepal-card`)

- En cualquier dashboard: **Editar dashboard → Añadir tarjeta** y busca **Deepal vehicle** en el
  selector. También se puede escribir a mano:
  ```yaml
  type: custom:deepal-card
  device_id: <id del dispositivo del coche>
  ```
- Se configura con el **vehículo** (selector de dispositivo filtrado por la integración); no hay
  que indicar entidades.
- Trae la franja de datos fijos (batería, autonomía y frescura) y las mismas tres pestañas que el
  panel: **Estado**, **Clima** y **Carga**, con el botón de actualizar en la cabecera. El **cierre
  general** va en el único chip del candado bajo la imagen de Estado (y el tile de cierre muestra
  también su estado); la imagen se gira 90° a la izquierda. Es la tarjeta recomendada para el
  detalle.
- Los controles de puertas, ventanillas y maletero solo aparecen si guardaste el PIN de control
  remoto; el resto funciona sin PIN. Los errores de comando se muestran en la propia tarjeta.

### Compacta (`custom:deepal-compact-card`)

- Pensada para mirar de un vistazo: **Editar dashboard → Añadir tarjeta** y busca **Deepal vehicle
  (compact)**. También a mano:
  ```yaml
  type: custom:deepal-compact-card
  device_id: <id del dispositivo del coche>
  ```
- Muestra: el nombre del coche, la franja de datos fijos (con el **cierre centralizado**), la
  **imagen del vehículo con el estado real**: en el S05 se usa el isométrico por capas (sustituye a
  la foto de la API; incluye puertas, ventanillas, capó, portón y luces, con las puertas abiertas
  marcadas con un contorno); en el resto de perfiles se usa la entidad
  `image.*_vehicle_image`, el héroe o la vista de planta como respaldo. Añade un **control de
  clima** (encender/apagar y temperatura objetivo); las acciones rápidas (cierre y desbloqueo,
  **ventanillas**, destello y claxon) con el botón de actualizar en la cabecera; y una **franja de
  carga** con el estado, la corriente y el tiempo restante mientras el cable está conectado.
- No lleva pestañas: para el clima, la programación de carga o los neumáticos, usa la tarjeta
  completa o el panel.

**Sobre las dos tarjetas**

- Ambas se cargan desde la integración: **no requieren recursos Lovelace por tu parte** (la
  integración registra el módulo como recurso automáticamente y además se auto-inyecta). Si tus
  recursos están en modo YAML, el módulo se sigue cargando al abrir la página. Si justo después de
  un reinicio una tarjeta no pintara (raro), recarga la página una vez.

## Solución de problemas

- **No veo el panel en la barra lateral**: actívalo en las opciones de la integración
  (**Configurar** → «Mostrar el panel en la barra lateral») y espera a la recarga automática.
- **No veo el dashboard generado en el diálogo**: la entrada necesita Home Assistant 2026.5 o
  superior; en versiones anteriores créalo desde un panel en modo YAML con
  `strategy: {type: custom:deepal}`. Si aun así no aparece, revisa **Ajustes → Sistema → Registro**
  buscando `Deepal`.
- **El ejemplo se ve sin imágenes**: comprueba que la integración está instalada y que
  `/deepal/frontend/assets/s05/estado_planta/Ocar1.png` responde en tu Home Assistant.
- **La tarjeta dice que no hay ningún vehículo configurado**: revisa el `device_id` (el formulario
  de la tarjeta lo rellena solo al añadirla desde el selector).
- **La tarjeta no aparece en el selector**: recarga el navegador (Ctrl+Shift+R); si sigue igual,
  revisa **Ajustes → Sistema → Registro** buscando `Deepal`.
- **El botón de puertas no aparece en la tarjeta**: falta el PIN de control remoto en las opciones
  de la integración, así que la entidad de cierre no existe.
- **La tarjeta compacta no muestra el clima**: es a propósito; para eso están la tarjeta completa y
  el panel.
