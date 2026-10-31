# Guía de la tarjeta Deepal para el dashboard

La integración incluye **una sola tarjeta configurable**: `custom:deepal-card`. Sustituye al panel
lateral, al dashboard generado y a las tarjetas completa y compacta anteriores. La tarjeta descubre
el vehículo y sus entidades desde los registros de Home Assistant, así que funciona con cualquier
prefijo de `entity_id`, área o idioma, y solo muestra el arte y las secciones que soporta el coche
seleccionado.

## 1. Añadir la tarjeta

1. Abre el dashboard donde quieras el coche y entra en **Editar dashboard → Añadir tarjeta**.
2. Elige **Vehículo Deepal** y selecciona el coche en el editor visual.
3. A mano, la configuración mínima es:
   ```yaml
   type: custom:deepal-card
   device_id: <id del dispositivo del coche>
   ```
   El formulario de la tarjeta rellena el `device_id` al añadirla desde el selector.

La tarjeta la sirve la propia integración: no hay que configurar ningún recurso de Lovelace.

## 2. Imagen y parte superior

Abre el botón **Ajustes** de la tarjeta (o el editor visual) y usa la pestaña **Vehículo**:

- **Mostrar en la imagen**: nombre, modelo, matrícula, autonomía, cierre, conexión con la nube y
  frescura. Puedes combinar lo que quieras.
- **Imagen del coche**:
  - **Planta**: vista superior por capas girada 90° a la izquierda, con puertas, ventanillas, portón,
  capó y luces en vivo.
  - **Isométrico**: vista 3/4 por capas, también con el estado real.
  - **Fotos**: las fotos empaquetadas o la entidad de imagen del vehículo, según el modelo.
  - **Imagen del vehículo**: la entidad `image.*_vehicle_image` (foto de la API o reserva por
    modelo).
  - **Automático**: isométrico en el S05, foto del perfil en el S07 y entidad de imagen en el resto.
- **Zoom** y **proporción** ajustan la imagen; **márgenes de la tarjeta** permiten que la imagen
  llegue de borde a borde.
- En el S05, mientras el cargador está conectado la vista isométrica cambia a la vista de carga con
  su cable y la línea de carga.

La tarjeta prefiere el pack oficial por vehículo cuando la integración lo ha descargado y validado,
y cae al arte empaquetado del perfil sin enseñar el coche de otro modelo.

## 3. Secciones debajo de la imagen

La pestaña **Secciones** controla el contenido y su orden. Las secciones disponibles son:

- **Acciones**: los botones de control.
- **Estado**: odómetro, estado de carga, batería y autonomía.
- **Clima**: climatización, asientos delanteros y traseros cuando el coche los expone, volante,
  temperatura interior y humedad. La acción **Clima** abre estos controles en un diálogo, así que la
  sección viene oculta por defecto para que la tarjeta no crezca.
- **Carga**: cable, corriente AC/DC, tiempo restante, programación, límite y sesiones. Solo se
  muestra mientras el cargador está conectado y ya no repite la imagen del coche.
- **Conducción** y **Ambiente**: solo en modelos que los reportan, como el S07.
- **Energía**: lecturas eléctricas y de combustible del PHEV.
- **Información**: fichas integradas (odómetro, temperaturas, humedad, combustible, estado de carga,
  velocidad, marcha, kilómetros) y tus propias entidades.
- **Diagnóstico**: avisos activos, o todos los avisos si eliges ese modo.
- **Neumáticos**: las cuatro presiones con sus alarmas. La acción **Neumáticos** las abre en un
  diálogo, así que la sección viene oculta por defecto.

Usa las flechas para reordenar una sección y el interruptor para ocultarla. Una sección cuyas
entidades no existan se oculta sola; nunca deja un hueco vacío. La tarjeta muestra por defecto
acciones, la sección de carga mientras el cable está conectado e información (con el icono del
coche). Estado queda oculto por defecto porque duplica información; actívalo desde **Secciones** si
lo quieres. En esa misma pestaña puedes activar Clima, Neumáticos, Conducción o Energía dentro de la
tarjeta en vez de en los diálogos. El diagnóstico solo aparece mientras hay un aviso activo. La
autonomía y el kilometraje se muestran sin decimales.

## 4. Acciones

La pestaña **Acciones** controla:

- qué botones aparecen y en qué orden: cierre, ventanillas, maletero, clima, neumáticos, luces,
  claxon y luces+claxon. Actualizar ya no forma parte de la tarjeta; usa la entidad de botón de
  actualización de la integración si necesitas despertar el coche.
- la disposición (`grid`, `scroll`, `split` o `fit`), el número de botones principales, el tamaño y
  las etiquetas (título, estado o ambos);
- qué acciones piden confirmación antes de enviar la orden: desbloquear, bloquear, maletero,
  ventanillas, clima, luces, claxon, localizar y actualizar.

Los botones **Clima** y **Neumáticos** abren diálogos modales. El de clima muestra la climatización
en un lado y los controles de asientos/volante en el otro; el de neumáticos muestra las cuatro
presiones y sus alarmas. Los controles de cierre, ventanillas y maletero solo aparecen si guardaste
el PIN de control remoto en las opciones de la integración; el resto funciona sin PIN. Cada comando
muestra su resultado o un error traducido en la propia tarjeta.

## 5. Información, diagnóstico y apariencia

- **Sensores**: elige las fichas de información integradas y el modo de diagnóstico (solo avisos
  activos o todos). Las entidades propias se pueden añadir a `info_custom` y `diag_custom` en YAML.
- **Apariencia**: idioma (automático, inglés, español, alemán, francés, italiano o portugués),
  mensajes en pantalla y su posición, y si el botón **Ajustes** se ve en la tarjeta.
- **Márgenes de la tarjeta** mantienen la tarjeta alineada con el resto del dashboard.

## 6. Guardado de los ajustes

Los ajustes del botón **Ajustes** se escriben en el YAML de la tarjeta cuando el dashboard se edita
desde la interfaz y el usuario es administrador; así los comparten todos los usuarios y
dispositivos. Si el dashboard no se puede escribir (no eres administrador o está en modo YAML), la
tarjeta guarda los ajustes en los datos de usuario de Home Assistant para esa tarjeta y muestra un
aviso no bloqueante. Si hay más de una tarjeta con el mismo coche, no adivina: guarda el cambio en
tu cuenta en lugar de sobrescribir otra tarjeta.

## 7. Dashboard de ejemplo

`guides/dashboards/deepal-dashboard.example.yaml` es una vista de secciones lista para copiar,
construida solo con la tarjeta de la integración y tarjetas estándar de Home Assistant. Pega el
contenido en el editor RAW y sustituye el marcador `<device_id>` y los `entity_id`
`garaje_deepal_s05_...` por los tuyos. No necesita tarjetas de HACS, ayudantes ni navegación.

## 8. Resolución de problemas

- **La tarjeta no aparece en el selector**: recarga el navegador (Ctrl+Shift+R); si sigue igual,
  revisa **Ajustes → Sistema → Registro** buscando `Deepal`.
- **La tarjeta dice que no hay vehículo configurado**: revisa el `device_id` de la configuración.
- **La imagen es la reserva genérica**: la foto de la API o el pack oficial aún no están disponibles;
  se muestra el arte del perfil y la tarjeta sigue funcionando.
- **Faltan los botones de cierre, ventanillas o maletero**: no hay PIN de control remoto configurado
  en las opciones de la integración, así que esas entidades no existen.
- **Los ajustes no se escriben en el dashboard**: el dashboard no se edita desde la interfaz o el
  usuario no es administrador; la tarjeta los guarda en los datos de usuario y lo indica.
- **Usaba el panel, el dashboard generado o la tarjeta compacta**: esas superficies se han retirado.
  Añade `custom:deepal-card` y configura la imagen y las secciones en sus ajustes. Las entidades,
  servicios y `device_id` de la integración no cambian.
