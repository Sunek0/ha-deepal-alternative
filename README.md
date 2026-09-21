# ha-deepal-alternative

Home Assistant custom integration for **My Changan / Deepal** connected vehicles (S05 Max, S07, SL03,
L07) over the official international API, plus a standalone async Python SDK reverse-engineered from
the official Android app.

This repository is the `ha-deepal-alternative` fork of the original work. The Home Assistant
**domain stays `deepal`** (`custom_components/deepal/`): existing config entries, entity ids and
entity unique ids keep working after updating from the upstream project.

## Important warnings

- Unofficial project, not affiliated with Changan Automobile. Use it at your own risk.
- Remote commands act on the real vehicle. Make sure it is safe before using locks, windows, trunk,
  climate, lights or horn.
- It cannot drive the car: the BLE/digital-key path is not implemented.
- Signing in with an account can sign that account out of the official My Changan app, and signing
  in to the app again can invalidate the Home Assistant session. Use a **secondary account** shared
  from your main account to avoid this (see below).

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

- Home Assistant 2026.9.0 or newer (Python 3.14.2+), matching the `homeassistant` baseline in
  `hacs.json`.
- An international My Changan account (email or SMS login). The HACS metadata advertises `ES` as
  the supported country.

## Installation

### HACS

1. In HACS, add this repository as a custom repository of type **Integration**:
   `https://github.com/dbarreiro/ha-deepal-alternative`.
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
- **Scan interval**, **API logging** and the diagnostic options: polling cadence and troubleshooting
  helpers. Leave the defaults unless you are debugging.

## Features

- Email-code and SMS-code login, automatic session refresh.
- REST telemetry (battery, range, doors, windows, climate, seats, tires, lamps).
- MQTT telemetry for MQTT-backed vehicles (S05) through the CA gateway.
- Signed remote commands: climate, doors, windows, trunk, charging limit/schedule, lights/horn,
  and optional app commands (defrost, seats, steering-wheel heat, charge and departure plans).

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

## Repository layout

| Path | Purpose |
| --- | --- |
| `deepal_sdk/` | Standalone async Python SDK (`httpx` + `pydantic`). |
| `custom_components/deepal/` | Home Assistant integration. |
| `custom_components/deepal/deepal/` | Vendored SDK copy used by the integration (relative imports). |
| `docs/` | Protocol notes, recovered-app evidence and validation guides. |
| `openspec/` | Change proposals and capability specs. |

## Development

```bash
.venv/bin/pip install -e "deepal_sdk[dev]"
.venv/bin/python -m pytest deepal_sdk/tests -q
diff -r -x "__pycache__" -x "*.pyc" deepal_sdk/deepal custom_components/deepal/deepal
```

The last command must only report the rewritten relative imports: the vendored copy has to stay in
sync with the SDK.

## Disclaimer

Unofficial project, not affiliated with Changan Automobile. Use at your own risk.
