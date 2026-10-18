# ha-deepal-alternative

Home Assistant custom integration for **My Changan / Deepal** connected vehicles (S05, S07, E07) over the official international and chinese API.

## Important warnings

- Unofficial project, not affiliated with Changan Automobile. Use it at your own risk.
- Remote commands act on the real vehicle. Make sure it is safe before using locks, windows, trunk,
  climate, lights or horn.
- Signing in with an account can sign that account out of the official My Changan app, and signing
  in to the app again can invalidate the Home Assistant session. Use a **secondary account** shared
  from your main account to avoid this (see below).

## Requirements

- Home Assistant 2026.8.0.
- An international My Changan account (email or SMS login). The HACS metadata advertises the
  countries with a translated language: Spain, Portugal, the United Kingdom, Ireland, France,
  Belgium, Luxembourg, Germany, Austria, Switzerland, Italy and Greece.

## Supported vehicles

The integration talks to the official international My Changan platform and targets the European
models; Chinese SDA accounts can also be configured by pasting an access token.

| Model | Notes |
| --- | --- |
| S05 EV / S05 PHEV | Telemetry and signed remote controls over MQTT and the REST API. |
| S07 | Not tested. Telemetry and signed remote controls through the REST API. |
| E07 | Only tested on SDA API. Telemetry through the REST API. |

Charge limit: the S05 EV does not support setting it — the signed `charge_max` command is accepted
without changing the limit — so the integration does not create the charge-limit control for it; the
S05 PHEV reports the charge-limit function code, so it does offer the control. The charge schedule
remains available on both.

## Supported features

### Authentication and session

- Email-code and SMS-code login on the international platform, with automatic token refresh and a
  reauthentication flow. If a verification code does not arrive, the login step can resend it or
  correct the destination; Changan is currently not delivering SMS codes, so the email method is
  recommended.
- Integration options for the scan interval, API logging and the regional environment.

### Telemetry

- REST telemetry: battery and range, charging state and currents, remaining charge time (numeric
  minutes and a `H:MM` sensor for dashboards), charge limit, charge schedule and plan, doors,
  windows, climate, seats, tires and lamps. The charging sensor also exposes the tracked
  `current_charge` and `last_charge` sessions (start and end time, battery level and range).
- Charging entities follow the car instead of a non-zero flag: the charging state is a translated
  enum (`not_charging`, `connected_ac`, `connected_dc`, `charging_ac`, `charging_dc`), the
  "Charging" sensor is on only for the charging states, the charge current is taken from the
  active charger and validated (`0-600 A`), and the power state is a translated off/on sensor.
- MQTT telemetry for MQTT-backed vehicles (S05) through the CA gateway, including the mileage
  fields, the dashboard warning lights (12 V battery, tire pressure, ABS, brake fluid,
  brakes, power steering, power limit, power system and traction battery low), the key fob
  battery, the air recirculation state and the rear fog lamp.
- Beta MQTT telemetry for SDA-platform vehicles (`SDA-MQTT`, E07) through the SDA condition
  service, with fallback to the legacy service and the REST condition.
- Climate target temperature and fan level, the license plate and per-window opening-degree sensors
  (the opening sensors ship disabled by default because the scale is not confirmed).
- Fuel telemetry on PHEV/range-extender vehicles (fuel level, fuel range and tank capacity).
- **Opt-in vehicle location**: enable *Fetch the vehicle location* in the options to request and
  expose the car position as a device tracker. European vehicles currently report no location, so
  the tracker may stay unknown; the option targets servers that expose it (and SDA accounts, where
  the payload carries `Lat`/`Lng`). The last known position is kept while the car sleeps.
- One Home Assistant device per vehicle, with translated entity names.

### Vehicle wake

- MQTT-backed vehicles (S05) report telemetry only while they are awake. The refresh button wakes a
  sleeping vehicle with the same service the official app uses and waits for a fresh report; wakes
  are throttled per vehicle so Home Assistant cannot drain the 12 V battery, and the periodic poll
  never wakes the car.
- Waking the vehicle can take up to 20 seconds before it reports again.
- REST-backed and `SDA-MQTT` vehicles keep using the signed condition request; the MQTT wake is only
  available for CA/MQTT vehicles.

### Remote controls

- Signed REST commands: climate, door lock, windows, trunk, charge limit, charge schedule, lights,
  horn and lights-and-horn together.
- Comfort commands: seat heating and ventilation levels and steering-wheel heating.
- Every command-capable international vehicle, MQTT-backed S05 included, sends these commands
  through the same signed flow.
- The door lock, window and trunk commands require the remote control PIN created with the account
  Home Assistant signs in with; their entities are only created once the PIN is saved in the
  integration options. The PIN is verified against the account when it is saved, so an invalid one,
  or one created with another account, is rejected instead of stored.
- When the car is asleep, the PIN commands wake it first: the first attempt can take up to 20
  seconds while the vehicle wakes up and reports before the command is sent.
- Flashing the lights, sounding the horn and the combined lights-and-horn button make the car run a
  physical cycle (about 30 s, 6 s and 30 s respectively); repeating them sooner shows how many
  seconds to wait instead of sending the command and being rejected by the vehicle. Climate, seat
  and steering wheel changes have no such wait.

### Vehicle image

- One image entity per vehicle: the API picture when it loads, and a bundled per-model render
  (S05, S07, E07 or a generic Deepal placeholder) served instantly otherwise, so the device
  page always shows a picture even when the API image is slow or missing.

### Using the dashboard, the panel and the cards

Three ways to see and control your car; everything is served by the integration itself, with no
HACS cards, no helpers and no Lovelace resources to configure.

**Generated dashboard** — one view per car, nothing to configure:

1. Open **Settings → Dashboards → Add dashboard** and pick **Deepal** under *Community dashboards*
   (Home Assistant 2026.5+).
2. Each view shows the complete card plus the sections of that car's model: quick controls, energy
   graphs (fuel readings on the PHEV), tire pressures, driving and ambience on the models that
   report them, and a templated alerts card. It rebuilds itself when a car or its entities change.
   On older Home Assistant versions, create a dashboard in YAML mode with
   `strategy: {type: custom:deepal}`.

**Sidebar panel** (optional) — no dashboard needed:

1. The setup asks whether to add it (disabled by default); change it later in **Configure → Show
   the sidebar panel**. Once enabled it is visible to every Home Assistant user, and the
   integration's **Configure** button keeps opening the options, not the panel.
2. Open **Deepal** in the sidebar; with several cars, switch them with the header selector. The
   panel discovers the vehicles and their entities from the Home Assistant registries, so any
   name, area or language works.
3. The vitals strip (battery, range, general closure and freshness) stays on top and the tabs are
   **Status** (layered picture of the car's model, state chips, the controls, tire pressures,
   health warnings while one is active and the energy block on fuel cars), **Driving** on the
   models that report it, **Climate** and **Charging**.
   Controls that need the remote control PIN (lock, windows, trunk) simply do not appear without
   it, and missing optional entities hide their own controls.

**Cards** — for your own dashboards:

1. **Edit dashboard → Add card** and pick **Deepal vehicle** (complete, with the panel's views and
   controls) or **Deepal vehicle (compact)** (vitals with the closure, the vehicle picture with the
   opening chips, a climate control, quick actions and a charging strip), then select the car in
   the form.
2. By hand:
   ```yaml
   type: custom:deepal-card        # or custom:deepal-compact-card
   device_id: <your vehicle device id>
   ```
   Both are loaded by the integration itself, so they need no Lovelace resource; the lock control
   needs the control PIN like the panel.

**Example dashboard**: `guides/dashboards/deepal-dashboard.example.yaml` is a copy-ready sections
view built only on the bundled card and core Home Assistant cards; paste it in the raw editor and
replace the device and entity ids with yours.

Full walkthrough and troubleshooting:
[generated dashboard, panel, example and cards guide (English)](guides/dashboard-guide.en.md) ·
[guía del dashboard generado, el panel, el ejemplo y las tarjetas (español)](guides/dashboard-guide.es.md).

### Diagnostics

- Redacted diagnostics download with the mapped telemetry, the raw payloads, the unmapped MQTT
  keys and the per-vehicle capability codes reported by the app backend. Credentials, personal
  identifiers, location values and the device id embedded in MQTT topics are redacted at any
  nesting depth, without distinguishing letter case.

## Recommended setup: use a secondary account

Logging in to Home Assistant with your main My Changan account can sign it out of your phone. The
recommended setup is to create a second account, share the vehicle from the main account and use the
secondary account only for Home Assistant:

1. In the My Changan app, create a new account with a different email and note its credentials.
2. Still signed in with your **main** account, open the vehicle, tap **Share** and invite the new
   account.
3. Sign in to the app with the **new** account and accept the shared vehicle control.
4. If you want to control the doors, windows or trunk, create the control PIN with the new account:
   try to lower the windows from the app, it asks you to create a PIN, create it and check that the
   command works. Those commands are signed with the PIN and require it; climate, lights and horn do
   not need it.
5. Sign out of the app and add the integration in Home Assistant with the **new** account. Your main
   account can stay signed in on the phone.

## Installation guide

A complete step-by-step guide (secondary account, HACS install, configuration, remote control PIN and
troubleshooting) is available in every language the integration supports:

- [Español](guides/installation-guide.es.md)
- [English](guides/installation-guide.en.md)
- [Deutsch](guides/installation-guide.de.md)
- [Français](guides/installation-guide.fr.md)
- [Italiano](guides/installation-guide.it.md)
- [Português](guides/installation-guide.pt.md)

## Installation

### HACS

1. In HACS, add this repository as a custom repository of type **Integration**:
   `https://github.com/Sunek0/ha-deepal-alternative`.
2. Install **Deepal Alternative** and restart Home Assistant.
3. Add the integration from **Settings > Devices & services**, choose the international platform and
   log in with an email or SMS code (use the secondary account from above).

Updating keeps the same `deepal` domain, so no reconfiguration is needed.

### Manual

1. Copy `custom_components/deepal/` into your Home Assistant `config/custom_components/` directory.
2. Restart Home Assistant and add the integration as described above.

## Configuration

Open **Settings > Devices & services > Deepal Alternative > Configure** to change these options:

- **Remote control PIN**: required for the door lock, window and trunk commands. Use the PIN created
  with the account Home Assistant signs in with (the secondary one); it is verified against the
  account when saved, so a PIN created with another account is rejected before it is stored.
- **Scan interval**, **API logging** and **regional environment**: polling cadence and
  troubleshooting helpers. Leave the defaults unless you are debugging. Every cycle reads each
  vehicle over MQTT plus the app condition, so an account with several cars can raise the interval
  (for example to 5 minutes) to make fewer cloud requests.

## Automation examples

The examples below use entities the integration creates for every command-capable vehicle. Entity
ids follow your vehicle name, so adjust them before copying (the ones below assume a vehicle named
`Deepal S05`); the examples only call entities the integration provides.

Notify when the car starts charging:

```yaml
automation:
  - alias: "Deepal charging started"
    triggers:
      - trigger: state
        entity_id: binary_sensor.deepal_s05_charging
        from: "off"
        to: "on"
    actions:
      - action: notify.mobile_app_your_phone
        data:
          title: "Deepal"
          message: "Charging started."
```

Lock the doors when the driver door stays unlocked for five minutes:

```yaml
automation:
  - alias: "Deepal doors left unlocked"
    triggers:
      - trigger: state
        entity_id: binary_sensor.deepal_s05_driver_door_unlocked
        to: "on"
        for: "00:05:00"
    actions:
      - action: lock.lock
        target:
          entity_id: lock.deepal_s05_doors
      - action: notify.mobile_app_your_phone
        data:
          title: "Deepal"
          message: "The doors were unlocked; locking them now."
```

## Data and security

- **Secrets at rest.** The integration stores the session tokens, the login private key and the
  remote control PIN inside the Home Assistant config entry (`.storage/core.config_entries`). Home
  Assistant does not encrypt config entries: restrict the permissions of the `.storage` directory
  and keep your backups encrypted.
- **Vehicle image.** The image entity only downloads `https` URLs from the account payload and does
  not follow redirects; when the image cannot be fetched, the bundled asset is shown.
- **Panel visibility.** The optional vehicle panel is visible to every Home Assistant user, like
  the entities themselves. The controls that act on the car require the remote control PIN when
  one is configured.
- **Secondary account.** Running the integration with a secondary My Changan account limits what
  the stored session can do; see the recommended setup section above.

## Troubleshooting

- **No control can be changed**: check first whether the official app can change it with the same
  account. The car sometimes refuses every remote command until it has been driven for a few
  minutes.
- **"Remote control PIN is not set" although a PIN is configured in Home Assistant**: the PIN was
  not created in the account Home Assistant uses. Sign in to the app with that account, create the
  PIN (step 4 above) and save it again in the integration options.
- **Home Assistant asks to reauthenticate**: the session was invalidated from the app or another
  device. Sign in again; using the secondary account avoids most of these.
- **The login verification code does not arrive**: the login step offers resending the code and
  correcting the email or mobile number without restarting. Changan is currently not delivering SMS
  codes (verified against the official app with the same account), so use the email method.
- **Values look stale**: the vehicle only reports telemetry while it is awake; use the refresh
  button to wake an MQTT-backed car (the first PIN command wakes it too), or the integration shows
  the last known snapshot until the car reports again.
- **Fuel entities are missing on a PHEV**: the integration creates them only when the vehicle's
  function configuration reports `#oilMileage` and the model is not a BEV.
- **A telemetry field is missing**: download the diagnostics from the device page and check
  `unmapped_mqtt_keys`; enable debug logging for `deepal_sdk` to see the candidate values in the
  Home Assistant log. Credentials, VIN and location-like values are redacted in the report.
- **SDA vehicle (E07) remote controls or MQTT telemetry misbehave**: remote controls are not
  supported on the SDA platform yet. For telemetry or MQTT reports, the release ships two helpers
  under [`tools/`](tools): the [`sda-mqtt-probe`](tools/sda-mqtt-probe) runs on your computer with no
  phone setup and reports how the broker session works, and the
  [`sda-mqtt-capture`](tools/sda-mqtt-capture) kit decodes the official app's MQTT frames locally
  (secrets, plate and location are masked in the logs they produce). Neither is part of the HACS
  install.

## Removal

1. Open **Settings > Devices & services**, select **Deepal Alternative** and delete the integration
   entry. This removes the vehicle devices and their entities and deletes the stored charging
   sessions; for international entries the integration also asks the server to log the session out
   (best effort: a failure never blocks the removal).
2. Remove the files: with HACS, remove the **Deepal Alternative** repository from HACS; with a
   manual install, delete the `custom_components/deepal` directory from your configuration.
3. Restart Home Assistant.

## Credits

The charging-session tracking follows the approach of
[DEC Deepal](https://github.com/manuelem1984/dec_deepal) (MIT), which documents the same session
rules.

## Disclaimer

Unofficial project, not affiliated with Changan Automobile. Use at your own risk.
