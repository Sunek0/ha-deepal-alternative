# Guía del panel, el dashboard de ejemplo y la tarjeta

Esta guía cubre las tres formas de ver y controlar tu coche Deepal en Home Assistant:

1. **Panel integrado**: una página propia en la barra lateral que aparece sola, sin YAML ni
   tarjetas adicionales.
2. **Dashboard de ejemplo**: la vista de referencia para quien prefiera un dashboard propio.
3. **Tarjeta `deepal-card`**: una tarjeta compacta para colocar en cualquier dashboard.

## 1. Panel integrado

- Es **opcional**: al configurar la integración se pregunta si quieres añadirlo (viene
  **desactivado**) y puedes cambiarlo después en las opciones de la integración (Configurar →
  «Mostrar el panel en la barra lateral»).
- Con el panel activado aparece **Deepal** en la barra lateral para **todos los usuarios** de Home
  Assistant. El botón **Configurar** abre las opciones de la integración (allí activas o desactivas
  el panel); el panel se abre desde la barra lateral.
- Se adapta a tu instalación: descubre el coche y sus entidades desde los registros de Home
  Assistant, así que funciona con cualquier nombre, área o idioma, y con varios coches.
- Pestañas:
  - **Estado**: imagen del coche por capas (capó, puertas, ventanillas, maletero y luces en vivo),
    cierre, puertas, ventanillas, maletero, capó, luces, motor, neumáticos con sus alarmas,
    batería, autonomía y kilómetros, más los controles de puertas, ventanillas, maletero, destello,
    claxon y actualizar.
  - **Clima**: climatización (encender/apagar y temperatura), asientos delanteros
    (calefacción/ventilación) y volante calefactable.
  - **Carga**: batería, cable, carga en curso, corriente, tiempo restante y las sesiones
    registradas (actual y última).
- No necesita recursos Lovelace ni tarjetas de terceros: todo lo sirve la propia integración.

## 2. Dashboard de ejemplo

Ficheros (en el repositorio, carpeta `guides/dashboards/`):

| Fichero | Qué es |
| --- | --- |
| `deepal-dashboard.example.yaml` | La vista completa, con cuatro estados: Exterior / Estado / Clima / Carga |
| `deepal-dashboard.helpers.yaml` | Los ayudantes que necesita: dos `input_select` de navegación y cuatro `select` de asientos |

**Requisitos**

- La integración **Deepal Alternative** (sirve las imágenes del coche en
  `/deepal/frontend/assets/s05/...`).
- Las tarjetas **mushroom** (HACS, plugin `piitaya/lovelace-mushroom`), únicos componentes
  frontend que usa el ejemplo.
- Los ayudantes del fichero de helpers: crea los `input_select` desde **Ajustes → Dispositivos y
  servicios → Ayudantes** (o pega el bloque en `configuration.yaml` y reinicia) y añade los
  `select` de plantilla.

**Cómo montarlo**

1. Abre el dashboard donde quieras la vista y entra en el **editor de código (RAW)** (menú ⋮ →
   Editar → ⋮ → Editar en modo YAML).
2. Pega el contenido de `deepal-dashboard.example.yaml` (la clave raíz es `views:`).
3. Sustituye los `entity_id` (`garaje_deepal_s05_...`) por los de tu instalación: dependen del
   nombre, el área y el idioma con que se crearon tus entidades (consulta **Herramientas para
   desarrolladores → Estados**).
4. Guarda. La navegación entre Exterior/Estado/Clima/Carga se hace con las tarjetas de menú (el
   ayudante `input_select.deepal_vista`) y el submenú de asientos con `input_select.deepal_clima_vista`.

**Nota sobre el cargador**

El ejemplo **no incluye** ningún elemento del cargador doméstico (V2C u otro): ni tiles, ni
sensores de sesión, ni el control de carga hasta objetivo. La sección de carga usa solo entidades
de la integración. Si quieres tus atajos del cargador, añádelos de vuelta como tarjetas propias.

## 3. Tarjeta Deepal (`custom:deepal-card`)

- En cualquier dashboard: **Editar dashboard → Añadir tarjeta** y busca **Deepal vehicle** en el
  selector. También se puede escribir a mano:
  ```yaml
  type: custom:deepal-card
  device_id: <id del dispositivo del coche>
  ```
- Se configura con el **vehículo** (selector de dispositivo filtrado por la integración); no hay
  que indicar entidades.
- Trae las mismas tres pestañas que el panel: **Estado** (imagen por capas, chips, neumáticos y
  controles de puertas, ventanillas, maletero, destello y claxon), **Clima** (habitáculo, asientos
  y volante) y **Carga** (batería, cable, corriente, tiempo restante y sesiones), con el botón de
  actualizar en la cabecera.
- Los controles de puertas, ventanillas y maletero solo aparecen si guardaste el PIN de control
  remoto; el resto funciona sin PIN. Los errores de comando se muestran en la propia tarjeta.
- Se carga sola desde la integración: **no requiere recursos Lovelace por tu parte** (la
  integración registra el módulo como recurso automáticamente y además se auto-inyecta). Si tus
  recursos están en modo YAML, el módulo se sigue cargando al abrir la página. Si justo después de
  un reinicio la tarjeta no pintara (raro), recarga la página una vez.

## Solución de problemas

- **No veo el panel en la barra lateral**: actívalo en las opciones de la integración
  (**Configurar** → «Mostrar el panel en la barra lateral») y espera a la recarga automática.
- **El ejemplo se ve sin imágenes**: comprueba que la integración está instalada y que
  `/deepal/frontend/assets/s05/estado_planta/Ocar1.png` responde en tu Home Assistant.
- **Las tarjetas de navegación no cambian de vista**: crea los `input_select` con los nombres
  exactos (`deepal_vista` y `deepal_clima_vista`).
- **La tarjeta no aparece en el selector**: recarga el navegador (Ctrl+Shift+R); si sigue igual,
  revisa **Ajustes → Sistema → Registro** buscando `Deepal`.
- **El botón de puertas no aparece en la tarjeta**: falta el PIN de control remoto en las opciones
  de la integración, así que la entidad de cierre no existe.
