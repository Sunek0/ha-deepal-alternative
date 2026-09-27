# ha-deepal-alternative

Home Assistant custom integration for **My Changan / Deepal** connected vehicles (S05, S07, SL03,
L07) over the official international and chinese API.

## Important warnings

- Unofficial project, not affiliated with Changan Automobile. Use it at your own risk.
- Remote commands act on the real vehicle. Make sure it is safe before using locks, windows, trunk,
  climate, lights or horn.
- Signing in with an account can sign that account out of the official My Changan app, and signing
  in to the app again can invalidate the Home Assistant session. Use a **secondary account** shared
  from your main account to avoid this (see below).

## Requirements

- Home Assistant 2026.3.0.
- An international My Changan account (email or SMS login). The HACS metadata advertises the
  countries with a translated language: Spain, Portugal, the United Kingdom, Ireland, France,
  Belgium, Luxembourg, Germany, Austria, Switzerland, Italy and Greece.

## Supported vehicles

The integration talks to the official international My Changan platform and targets the European
models; Chinese SDA accounts can also be configured by pasting an access token.

| Model | Notes |
| --- | --- |
| S05 EV / S05 PHEV | Telemetry and signed remote controls over MQTT. |
| E07 (SDA platform) | **Beta:** MQTT telemetry through the SDA condition service; pending verification on a real car (issue #2). |
| S07 | Not tested. Telemetry and signed remote controls through the REST API. |
| SL03 | Not tested. Telemetry and signed remote controls through the REST API. |
| L07 | Not tested. Telemetry and signed remote controls through the REST API. |

Vehicles whose API reports `protocolType: MQTT` (S05 in Europe) report telemetry through the
CA/MQTT gateway; every command-capable model, MQTT-backed included, uses the same signed command
flow. Vehicles reporting `protocolType: SDA-MQTT` (E07) use the same gateway with the SDA
`Get_CarCondition` service. Climate, lights and horn are verified on a real S05. Controls also
depend on what each car and account allow. For a model not listed here, telemetry and the generic
vehicle image still work.

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
- Beta MQTT telemetry for SDA-platform vehicles (`SDA-MQTT`, E07) through the SDA condition
  service, with fallback to the legacy service and the REST condition.
- Fuel telemetry on PHEV/range-extender vehicles (fuel level, fuel range and tank capacity); the
  entities are only created when the vehicle reports the fuel capability and its model is not a
  BEV, so electric vehicles keep their current entity set.
- One Home Assistant device per vehicle, with translated entity names.

### Remote controls

- Signed REST commands: climate, door lock, windows, trunk, charge limit, charge schedule, lights
  and horn.
- Comfort commands: seat heating and ventilation levels and steering-wheel heating.
- Every command-capable international vehicle, MQTT-backed S05 included, sends these commands
  through the same signed flow.
- On the S05 the charge limit number is not created because the car does not support it.
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
  with the account Home Assistant signs in with (the secondary one); a PIN created with another
  account is rejected.
- **Scan interval**, **API logging**, **regional environment** and **declared Android version**:
  polling cadence and troubleshooting helpers. Leave the defaults unless you are debugging.

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
- **Fuel entities are missing on a PHEV**: the integration creates them only when the vehicle's
  function configuration reports `#oilMileage` and the model is not a BEV.
- **A telemetry field is missing**: download the diagnostics from the device page and check
  `unmapped_mqtt_keys`; enable debug logging for `deepal_sdk` to see the candidate values in the
  Home Assistant log. Credentials, VIN and location-like values are redacted in the report.

## Disclaimer

Unofficial project, not affiliated with Changan Automobile. Use at your own risk.
