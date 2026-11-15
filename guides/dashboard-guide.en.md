# Deepal dashboard card guide

The integration ships **one configurable card**: `custom:deepal-card`. It replaces the former
sidebar panel, the generated dashboard strategy and the complete and compact cards. The card
discovers the vehicle and its entities from the Home Assistant registries, so it works with any
entity-id prefix, area or language, and it only shows the artwork and sections the selected vehicle
supports.

## 1. Add the card

1. Open the dashboard where you want the car and choose **Edit dashboard → Add card**.
2. Pick **Deepal vehicle** and select the car in the visual editor.
3. By hand, the minimum configuration is:
   ```yaml
   type: custom:deepal-card
   device_id: <your vehicle device id>
   ```
   The card form fills in the device id when it is added from the picker.

The card is loaded by the integration itself, so there is no Lovelace resource to configure.

## 2. Hero and vehicle image

Open the card's **Settings** button (or the visual editor) and use the **Vehicle** tab:

- **Show on the hero**: name, model, plate, remaining range, closure, cloud connection and
  freshness. Any combination is valid.
- **Vehicle image**:
  - **Plant**: the layered top view rotated 90° to the left, with live doors, windows, trunk, hood
  and lights.
  - **Isometric**: the live 3/4 Car View with the same state layers.
  - **Photos**: the bundled photos or the vehicle image entity, depending on the model.
  - **Vehicle image**: the `image.*_vehicle_image` entity (API picture or per-model fallback).
  - **Automatic**: isometric on the S05, the profile photo on the S07 and the image entity on other
    models.
- **Zoom** and **aspect ratio** adjust the picture; **card margins** control whether the hero is
  edge to edge.
- On the S05, while the charger is connected the isometric view switches to the charging view with
  its cable and charging line.

The card prefers the official per-vehicle image pack when the integration has downloaded and
validated it, and falls back to the bundled profile art without showing another model's car.

## 3. Sections below the image

The **Sections** tab controls the content and its order. The available sections are:

- **Actions**: the control buttons.
- **Climate**: cabin climate, a temperature wheel, on/off and cabin humidity. The **Climate** action
  opens the climate tab of the vehicle dialog, so this section is hidden by default to keep the card
  short.
- **Charging**: cable, AC/DC current, remaining time, charge schedule, charge limit and sessions.
  It is shown only while the charger is connected and no longer repeats the car picture.
- **Driving** and **Ambience**: only on models that report them, such as the S07.
- **Energy**: the PHEV fuel and electric readings.
- **Status**: the configurable metric block built from the built-in tiles (odometer, temperatures,
  humidity, fuel, charge state, speed, gear, mileage) and your own entity tiles. The **Sensors** tab
  lets you choose which tiles appear and their order. It replaces the former separate status and
  information sections.
- **Seats**: the interior top view with the seat heating, seat ventilation and steering-wheel
  controls over the front seats. Models without interior artwork show the same controls as a list.
- **Diagnostics**: active warnings, or all warnings when you choose that mode.
- **Tyres**: the four pressures with their alarms. The same rotated top view with the pressure text
  beside each wheel is used in the **Tyres** section on the card; the **Tyres** action opens the
  tyres tab of the vehicle dialog, so this section is hidden by default.

Use the arrows to reorder a section and the switch to hide it. A section whose entities are missing
hides itself; it never leaves an empty shell. The default card shows actions, the charging section
while connected, status (with the vehicle icon) and seats. The same tab enables Climate, Tyres,
Driving or Energy inline instead of in the dialogs. Diagnostics appears only while a warning is
active. Range and odometer are shown as whole numbers (no decimals).

## 4. Actions

The **Actions** tab controls:

- which buttons appear and in what order: lock, windows, trunk, climate, seats, tyres, lights,
  horn and lights-and-horn. The hero can show a refresh button; turn it on or off in the **Vehicle**
  settings.
- the layout (`grid`, `scroll`, `split` or `fit`), the number of primary buttons, the size and the
  labels (title, status or both);
- which actions ask for confirmation before sending the command: unlock, lock, trunk, windows,
  climate, refresh, lights, horn and find.

The **Climate**, **Seats** and **Tyres** buttons open one vehicle dialog with three tabs. The
climate tab shows the climate artwork with the airflow layer while the climate is on, plus the
temperature wheel, power and humidity controls. The seats tab shows the interior top view cropped to the
front seats, with a control over each seat function and the steering wheel; tap a control to cycle
its level. Models without interior artwork show the same controls as a list. The same seats map and
controls are available on the card itself from the **Seats** section. The tyres tab shows the
vehicle top view rotated 90 degrees with each pressure and warning as text beside its wheel.
The dialog only offers the tabs that have data, updates live and closes without sending anything.
The lock, windows and trunk controls only appear when the remote control PIN is configured in the
integration options; the rest works without a PIN. Every command shows its result or a translated
error on the card.

## 5. Status, diagnostics and appearance

- **Sensors**: choose and reorder the built-in status tiles and the diagnostics mode (active
  warnings only, or all warnings). Only the sensors the vehicle exposes are offered. Custom entities
  can be added to `info_custom` and `diag_custom` in YAML; they appear after the built-in status
  tiles.
- **Appearance**: language (automatic, or English, Spanish, German, French, Italian or Portuguese),
  on-screen messages and their position, and whether the **Settings** button is visible on the card.
- **Card margins** keep the card aligned with the rest of your dashboard.

## 6. Settings persistence

Settings changed from the card's **Settings** button are written to the card YAML when the dashboard
is UI-managed and the user is an administrator. They are shared by every user and device. When the
dashboard cannot be written (not an administrator or YAML mode), the card stores the settings in
the Home Assistant user data for that card and shows a non-blocking notice. If more than one card
uses the same vehicle, the card does not guess: it keeps the change in your account instead of
overwriting another card.

## 7. Example dashboard

`guides/dashboards/deepal-dashboard.example.yaml` is a copy-ready sections view built only on the
bundled card and core Home Assistant cards. Paste it in the raw editor and replace the `<device_id>`
placeholder and the `garaje_deepal_s05_...` entity ids with yours. It needs no HACS cards, helpers or
navigation helpers.

## 8. Troubleshooting

- **The card is missing from the picker**: reload the browser (Ctrl+Shift+R); if it persists, check
  **Settings → System → Logs** for `Deepal`.
- **The card says no vehicle is configured**: check the `device_id` in the card configuration.
- **The image is the generic fallback**: the API image or the official pack is not available yet;
  the bundled profile art is shown instead and the card keeps working.
- **The lock, windows or trunk buttons are missing**: the remote control PIN is not configured in
  the integration options, so those entities do not exist.
- **The settings are not written to the dashboard**: the dashboard is not UI-managed or the user is
  not an administrator; the card keeps the settings in the user data and tells you so.
- **I used the old panel, the generated dashboard or the compact card**: those surfaces were
  removed. Add `custom:deepal-card` and configure the hero and sections in its settings. The
  integration's entities, services and device ids are unchanged.
