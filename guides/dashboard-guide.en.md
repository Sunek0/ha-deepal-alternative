# Panel, example dashboard and card guide

This guide covers the three ways to see and control your Deepal car in Home Assistant:

1. **Built-in panel**: a page of its own in the sidebar that appears by itself, with no YAML and no
   extra cards.
2. **Example dashboard**: the reference view for those who prefer their own dashboard.
3. **`deepal-card`**: a compact card to place on any dashboard.

## 1. Built-in panel

- It is **optional**: the setup asks whether to add it (disabled by default) and the integration
  options can change it later (Configure → "Show the sidebar panel").
- With the panel enabled, **Deepal** appears in the sidebar for **every Home Assistant user**. The
  integration's **Configure** button opens the integration options (enable or disable the panel
  there); the panel opens from the sidebar.
- It adapts to your installation: it discovers the vehicle and its entities from the Home Assistant
  registries, so it works with any name, area or language, and with several cars.
- Tabs:
  - **Status**: layered car picture (hood, doors, windows, trunk and lights live), lock, doors,
    windows, trunk, hood, lights, engine, tire pressures with their alarms, battery, range and
    odometer, plus the lock, windows, trunk, flash, horn and refresh controls.
  - **Climate**: cabin climate (on/off and target temperature), front seats (heating/ventilation)
    and steering wheel heating.
  - **Charging**: battery, cable, charging state, current, time left and the tracked sessions
    (current and last).
- It needs no Lovelace resources and no third-party cards: the integration serves everything.

## 2. Example dashboard

Files (in the repository, `guides/dashboards/` folder):

| File | What it is |
| --- | --- |
| `deepal-dashboard.example.yaml` | The full view, with four states: Exterior / Status / Climate / Charging |
| `deepal-dashboard.helpers.yaml` | The helpers it needs: two navigation `input_select`s and four seat `select`s |

**Requirements**

- The **Deepal Alternative** integration (it serves the car images under
  `/deepal/frontend/assets/s05/...`).
- The **mushroom** cards (HACS, `piitaya/lovelace-mushroom` plugin), the only frontend components
  the example uses.
- The helpers from the helpers file: create the `input_select`s from **Settings → Devices &
  services → Helpers** (or paste the block into `configuration.yaml` and restart) and add the
  template `select`s.

**How to install it**

1. Open the dashboard you want and switch to the **raw configuration editor** (⋮ menu → Edit → ⋮ →
   Edit in YAML).
2. Paste the contents of `deepal-dashboard.example.yaml` (the root key is `views:`).
3. Replace the `entity_id`s (`garaje_deepal_s05_...`) with yours: they depend on the name, area and
   language your entities were created with (check **Developer tools → States**).
4. Save. Navigation between Exterior/Status/Climate/Charging uses the menu cards (the
   `input_select.deepal_vista` helper) and the seats submenu uses `input_select.deepal_clima_vista`.

**A note about the charger**

The example **does not include** any home charger element (V2C or any other): no tiles, no session
sensors, no charge-to-target control. The charging section only uses integration entities. If you
want your charger shortcuts, add them back as your own cards.

## 3. Deepal card (`custom:deepal-card`)

- On any dashboard: **Edit dashboard → Add card** and look for **Deepal vehicle** in the picker.
  It can also be written by hand:
  ```yaml
  type: custom:deepal-card
  device_id: <your vehicle device id>
  ```
- It is configured with the **vehicle** (a device selector filtered by the integration); no
  entities are configured by hand.
- It carries the panel's three tabs: **Status** (layered picture, chips, tires and the lock,
  windows, trunk, flash and horn controls), **Climate** (cabin, seats and steering wheel) and
  **Charging** (battery, cable, current, time left and sessions), with the refresh button in the
  header.
- The lock, windows and trunk controls only appear when the remote control PIN is saved; the rest
  works without a PIN. Command errors are shown on the card itself.
- It is loaded by the integration itself: the module is registered as a Lovelace resource
  automatically (you do not have to add anything). If the card does not paint right after a
  restart (rare), reload the page once.

## Troubleshooting

- **I do not see the panel in the sidebar**: enable it in the integration options (**Configure** →
  "Show the sidebar panel") and wait for the automatic reload.
- **The example shows no images**: check that the integration is installed and that
  `/deepal/frontend/assets/s05/estado_planta/Ocar1.png` responds in your Home Assistant.
- **The menu cards do not change the view**: create the `input_select`s with the exact names
  (`deepal_vista` and `deepal_clima_vista`).
- **The card does not appear in the picker**: reload the browser (Ctrl+Shift+R); if it persists,
  check **Settings → System → Logs** for `Deepal`.
- **The door button does not appear on the card**: the remote control PIN is missing in the
  integration options, so the lock entity does not exist.
