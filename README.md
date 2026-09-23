# ha-deepal-alternative

Home Assistant custom integration for **My Changan / Deepal** connected vehicles (S05, S07, SL03,
L07) over the official international and chinese API.

## Important warnings

- Unofficial project, not affiliated with Changan Automobile. Use it at your own risk.
- Remote commands act on the real vehicle. Make sure it is safe before using locks, windows, trunk,
  climate, lights or horn.
- It cannot drive the car: the BLE/digital-key path is not implemented.
- Signing in with an account can sign that account out of the official My Changan app, and signing
  in to the app again can invalidate the Home Assistant session. Use a **secondary account** shared
  from your main account to avoid this (see below).

## Supported vehicles

The integration talks to the official international My Changan platform and targets the European
models; Chinese SDA accounts can also be configured by pasting an access token.

| Model | Notes |
| --- | --- |
| S05 / S05 Max (`C857` in Europe) | Telemetry over MQTT. Remote controls are experimental and opt-in. |
| S07 | Telemetry and signed remote controls through the REST API. |
| SL03 | Telemetry and signed remote controls through the REST API. |
| L07 | Telemetry and signed remote controls through the REST API. |

Vehicles whose API reports `protocolType: MQTT` (S05 in Europe) report telemetry through the
CA/MQTT gateway and stay read-only unless you enable the experimental remote controls option;
the rest use the signed REST command flow. Controls also depend on what each car and account
allow. For a model not listed here, telemetry and the generic vehicle image still work.

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

## Requirements

- Home Assistant 2026.3.0 or newer, matching the `homeassistant` baseline in `hacs.json`
  (Python 3.13+; Home Assistant 2026.9 uses Python 3.14).
- An international My Changan account (email or SMS login). The HACS metadata advertises the
  countries with a translated language: Spain, Portugal, the United Kingdom, Ireland, France,
  Belgium, Luxembourg, Germany, Austria, Switzerland, Italy and Greece.

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

- **Enable experimental remote controls for MQTT vehicles (S05)**: required to control climate,
  lights and horn on vehicles that report over MQTT (S05). Without it, those vehicles stay
  read-only.
- **Remote control PIN**: required for the door lock, window and trunk commands. Use the PIN created
  with the account Home Assistant signs in with (the secondary one); a PIN created with another
  account is rejected.
- **Scan interval**, **API logging**, **regional environment** and **declared Android version**:
  polling cadence and troubleshooting helpers. Leave the defaults unless you are debugging.

## Supported features

### Authentication and session

- Email-code and SMS-code login on the international platform, with automatic token refresh and a
  reauthentication flow.
- Integration options for the scan interval, API logging, the regional environment and the declared
  Android version.

### Telemetry

- REST telemetry: battery and range, charging state and currents, remaining charge time, charge
  limit, charge schedule and plan, doors, windows, climate, seats, tires and lamps.
- MQTT telemetry for MQTT-backed vehicles (S05) through the CA gateway, including the mileage
  fields.
- Fuel telemetry on PHEV/range-extender vehicles (fuel level, fuel range and tank capacity); the
  entities are only created when the vehicle reports the fuel capability and its model is not a
  BEV, so electric vehicles keep their current entity set.
- One Home Assistant device per vehicle, with translated entity names.

### Remote controls

- Signed REST commands: climate, door lock, windows, trunk, charge limit, charge schedule, lights
  and horn.
- Comfort commands: seat heating and ventilation levels and steering-wheel heating.
- On the S05 the controls are experimental and opt-in over MQTT, and the charge limit number is
  not created because the car does not support it.
- The door lock, window and trunk commands require the remote control PIN created with the account
  Home Assistant signs in with; their entities are only created once the PIN is saved in the
  integration options.

### Vehicle image

- One image entity per vehicle: the API picture when it loads, and a bundled per-model render
  (S05, S07, SL03, L07 or a generic Deepal placeholder) served instantly otherwise, so the device
  page always shows a picture even when the API image is slow or missing.

### Diagnostics

- Redacted diagnostics download with the mapped telemetry, the raw payloads, the unmapped MQTT
  keys and the per-vehicle capability codes reported by the app backend.

## Troubleshooting

- **No control can be changed**: check first whether the official app can change it with the same
  account. The car sometimes refuses every remote command until it has been driven for a few
  minutes.
- **"Remote control PIN is not set" although a PIN is configured in Home Assistant**: the PIN was
  not created in the account Home Assistant uses. Sign in to the app with that account, create the
  PIN (step 4 above) and save it again in the integration options.
- **Home Assistant asks to reauthenticate**: the session was invalidated from the app or another
  device. Sign in again; using the secondary account avoids most of these.
- **Values look stale**: the vehicle only reports telemetry while it is awake; the integration shows
  the last known snapshot until the car reports again.
- **"Límite de carga" does not appear on an S05**: the signed `charge_max` command is accepted by
  the API but does not change the limit on that model and its function configuration reports no
  SOC-set capability, so the integration does not create the number or the sensor. The charging
  schedule stays available; delete the orphaned `number.*_charge_limit` entity from the entity
  registry after updating.
- **Some sensors are missing on an S05**: speed, gear, outside temperature, PM2.5, air quality,
  vehicle status, electronic parking brake, rear seat heating, mileage yesterday/trip and the
  charge limit are not created because the car does not report them. The remaining charge time
  shows `unknown` while the car has no estimate. Delete the orphaned sensor entries from the entity
  registry after updating.
- **Fuel entities are missing on a PHEV**: the integration creates them only when the vehicle's
  function configuration reports `#oilMileage` and the model is not a BEV. Check `capabilities` in
  the diagnostics; if the code is absent, the gate does not fire and the change is documented in
  `docs/phev-fuel-telemetry.md` (pending verification on a real PHEV).
- **A telemetry field is missing**: download the diagnostics from the device page and check
  `unmapped_mqtt_keys`; enable debug logging for `deepal_sdk` to see the candidate values in the
  Home Assistant log. Credentials, VIN and location-like values are redacted in the report.
- **"Login attempt or request with invalid authentication" with `/api/image_proxy/...`**: the
  browser replayed a stale vehicle image URL, something that happens after a reload, a tab resume
  or a network change and also with other image entities. The vehicle image itself keeps working:
  the integration falls back to the bundled render. It is a known Home Assistant issue
  ([core#173230](https://github.com/home-assistant/core/issues/173230)); with `ip_ban_enabled`
  disabled (the default) the warning is harmless, and a hard refresh drops the stale URL.

## Disclaimer

Unofficial project, not affiliated with Changan Automobile. Use at your own risk.
