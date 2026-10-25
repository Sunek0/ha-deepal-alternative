# Panel, example dashboard and cards guide

This guide covers the four ways to see and control your Deepal car in Home Assistant:

1. **Generated dashboard**: one view per car, created by the integration from the new-dashboard
   dialog, with no YAML.
2. **Built-in panel**: a page of its own in the sidebar that appears by itself, with no YAML and no
   extra cards.
3. **Example dashboard**: the reference view for those who prefer their own dashboard.
4. **`deepal-card` and `deepal-compact-card`**: the complete card and a compact one to place on any
   dashboard.

## 1. Generated dashboard

- In **Settings → Dashboards → Add dashboard** pick **Community dashboards → Deepal**: the
  integration generates a dashboard with **one view per car**, no YAML and nothing to configure.
- Each view brings the **complete card** of the car plus its model's sections: quick controls,
  battery and range graphs (and fuel graphs on the PHEV), tire pressures, and — on the models that
  report them — a **Driving** section (speed, gear, mileage) and an **Ambience** one (outside
  temperature, PM2.5, air quality), plus a templated alerts card.
- The dialog entry needs Home Assistant 2026.5 or later; on older versions the same dashboard can be
  created from a YAML-mode dashboard with:
  ```yaml
  strategy:
    type: custom:deepal
  ```
- It **regenerates itself** when you add or remove a car or its entities change (the strategy
  declares the device and entity registries as dependencies).
- The generated dashboard depends on the integration: if you remove it, its views stop resolving.

## 2. Built-in panel

- It is **optional**: the setup asks whether to add it (disabled by default) and the integration
  options can change it later (Configure → "Show the sidebar panel").
- With the panel enabled, **Deepal** appears in the sidebar for **every Home Assistant user**. The
  integration's **Configure** button opens the integration options (enable or disable the panel
  there); the panel opens from the sidebar.
- It adapts to your installation: it discovers the vehicle and its entities from the Home Assistant
  registries, so it works with any name, area or language, and with several cars.
- **Persistent vitals**: battery (with a charging bolt), range, the **central locking** and
  **freshness** (cloud connection and last update) stay visible on all tabs.
- Tabs:
  - **Status**: layered car picture rotated 90° counter-clockwise and cropped to a 750:550 frame
    (hood, doors, windows, trunk and lights live), with a single **central-locking** chip below it;
    the lock, windows, trunk, flash,
    horn and flash-and-horn controls; odometer and charge state; tire pressures with their alarms;
    **warnings** (12 V battery, ABS, brakes, steering, power…), shown only while one is active;
    and the **Energy** block on fuel cars (PHEV).
  - **Driving** (on the models that report it, like the S07): speed, gear, parking brake, vehicle
    status, yesterday/trip mileage, and the ambience readings (outside temperature, PM2.5, air
    quality).
  - **Climate**: cabin climate (on/off and target temperature), front seats
    (heating/ventilation) and **rear seats** on cars that have them, steering wheel heating, and
    the inside temperature with the **humidity** next to it.
  - **Charging**: cable, current (AC/DC when the car reports them separately), time left in H:MM,
    the **charge schedule** (switch and times), the **charge limit** on cars that support it, and
    the tracked sessions — the completed one above the schedule and the one in progress at the
    end — with both the level **and the range** at start and end.
- It needs no Lovelace resources and no third-party cards: the integration serves everything.

## 3. Example dashboard

File (in the repository, `guides/dashboards/` folder):

| File | What it is |
| --- | --- |
| `deepal-dashboard.example.yaml` | The complete view: the car card plus Controls, Battery and range, Tires and Alerts |

**Requirements**

- The **Deepal Alternative** integration and nothing else: the example uses the card that ships
  with the integration and standard Home Assistant cards. No HACS cards, no helpers, no extra
  resources.

**How to install it**

1. Open the dashboard you want and switch to the **raw configuration editor** (⋮ menu → Edit → ⋮ →
   Edit in YAML).
2. Paste the contents of `deepal-dashboard.example.yaml` (the root key is `views:`).
3. Replace the placeholders:
   - `<device_id>`: the car the card shows. Add `custom:deepal-card` once from the card picker;
     the form lists the integration's vehicles and the id shown there is the one to paste.
   - `garaje_deepal_s05_...`: the entity ids depend on the name, area and language your entities
     were created with (check **Developer tools → States**).
4. Save.

**What the view brings**

- The **complete card** full width with the panel's three tabs.
- **Controls**: lock (with lock and unlock buttons on the tile itself), windows, trunk, flash,
  horn, flash-and-horn and refresh.
- **Battery and range**: two 24 h graphs, one metric per graph.
- **Tires**: the four pressures; tap for the details.
- **Alerts**: one line with everything worth acting on (doors, windows, trunk, hood, lock, tire
  alarms, cable connected without charging, low battery and no cloud connection) or "all clear".

**If you used the previous example**

- The old example needed the **mushroom** cards (HACS), two navigation `input_select` helpers and
  the helpers file. None of that is needed now: you can delete those `input_select`s and the
  template `select`s if you only used them for that dashboard.
- The **home charger (V2C)** stays out as before: the card's charging tab only uses integration
  entities. If you want your charger shortcuts, add them back as your own cards.

## 4. Deepal cards

### Complete (`custom:deepal-card`)

- On any dashboard: **Edit dashboard → Add card** and look for **Deepal vehicle** in the picker.
  It can also be written by hand:
  ```yaml
  type: custom:deepal-card
  device_id: <your vehicle device id>
  ```
- It is configured with the **vehicle** (a device selector filtered by the integration); no
  entities are configured by hand.
- It carries the vitals strip (battery, range and freshness) and the panel's three tabs —
  **Status**, **Climate** and **Charging** — with the refresh button in the header. The **general
  closure** sits in the only padlock chip below the status picture (the lock control reports its
  state too), and the picture is rotated 90° counter-clockwise. This is the recommended card for
  details.
- The lock, windows and trunk controls only appear when the remote control PIN is saved; the rest
  works without a PIN. Command errors are shown on the card itself.

### Compact (`custom:deepal-compact-card`)

- Meant for a quick glance: **Edit dashboard → Add card** and look for **Deepal vehicle
  (compact)**. By hand:
  ```yaml
  type: custom:deepal-compact-card
  device_id: <your vehicle device id>
  ```
- It shows the car name, the vitals strip (with the **central locking**), the **state-aware vehicle
  picture**: the S05 uses the isometric layered view instead of the API photo (doors, windows, hood,
  trunk and lights, with open doors marked by an outline), while other profiles fall back to the
  `image.*_vehicle_image` entity, the hero picture or the status view. It also offers a **climate
  control** (on/off and target temperature); quick actions (lock and unlock, **windows**, flash and
  horn) with the refresh button in the header; and a **charging strip** with the state, current and
  time left while the cable is connected.
- It has no tabs: for climate, the charge schedule or the tires, use the complete card or the
  panel.

**About both cards**

- Both are loaded by the integration itself: the module is registered as a Lovelace resource
  automatically (you do not have to add anything). If a card does not paint right after a restart
  (rare), reload the page once.

## Troubleshooting

- **I do not see the panel in the sidebar**: enable it in the integration options (**Configure** →
  "Show the sidebar panel") and wait for the automatic reload.
- **I do not see the generated dashboard in the dialog**: the entry needs Home Assistant 2026.5 or
  later; on older versions create it from a YAML-mode dashboard with
  `strategy: {type: custom:deepal}`. Check **Settings → System → Logs** for `Deepal` if it never
  appears.
- **The example shows no images**: check that the integration is installed and that
  `/deepal/frontend/assets/s05/estado_planta/Ocar1.png` responds in your Home Assistant.
- **The card says no vehicle is configured**: check the `device_id` (the card form fills it in when
  the card is added from the picker).
- **The card does not appear in the picker**: reload the browser (Ctrl+Shift+R); if it persists,
  check **Settings → System → Logs** for `Deepal`.
- **The door button does not appear on the card**: the remote control PIN is missing in the
  integration options, so the lock entity does not exist.
- **The compact card has no climate controls**: that is on purpose; the complete card and the panel
  have them.
