# ha-deepal-alternative

Home Assistant custom integration for **My Changan / Deepal** connected vehicles (S05 Max, S07, SL03,
L07) over the official international API, plus a standalone async Python SDK reverse-engineered from
the official Android app.

This repository is the `ha-deepal-alternative` fork of the original work. The Home Assistant
**domain stays `deepal`** (`custom_components/deepal/`): existing config entries, entity ids and
entity unique ids keep working after updating from the upstream project.

## Requirements

- Home Assistant 2026.9.0 or newer (Python 3.14.2+), matching the `homeassistant` baseline in
  `hacs.json`.
- An international My Changan account (email or SMS login). The HACS metadata advertises `ES` as
  the supported country.

## Installation (HACS)

1. In HACS, add this repository as a custom repository of type **Integration**:
   `https://github.com/dbarreiro/ha-deepal-alternative`.
2. Install **Deepal Alternative** and restart Home Assistant.
3. Add the integration from **Settings > Devices & services**, choose the international platform and
   log in with an email or SMS code. The remote-control PIN is optional and can be set later in the
   integration options.

Updating keeps the same `deepal` domain, so no reconfiguration is needed.

## Features

- Email-code and SMS-code login, automatic session refresh.
- REST telemetry (battery, range, doors, windows, climate, seats, tires, lamps).
- MQTT telemetry for MQTT-backed vehicles (S05) through the CA gateway.
- Signed remote commands: climate, doors, windows, trunk, charging limit/schedule, lights/horn,
  and optional app commands (defrost, seats, steering-wheel heat, charge and departure plans).

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
