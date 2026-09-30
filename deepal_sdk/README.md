# Deepal SDK

Asynchronous Python SDK for the **Changan Deepal / My Changan** connected-vehicle platforms.
It signs in, reads telemetry and sends remote commands to Deepal vehicles (S05, S07, SL03, L07)
through the official mobile-app APIs.

> Unofficial project, not affiliated with Changan Automobile. Use it at your own risk. Remote
> commands act on a real vehicle: make sure it is safe before locking doors, moving windows or
> starting the climate control.

## Platforms

The SDK speaks to two different Changan platforms, each with its own client:

| Client | Platform | Base host | Login | Reference |
| --- | --- | --- | --- | --- |
| `DeepalIntlClient` | International (My Changan app, Europe/LatAm) | `m.iov.changanauto.com.de` | Email or SMS verification code | [`docs/intl-api.md`](docs/intl-api.md) |
| `DeepalClient` | SDA (mainland China) | `pre-acenter.sda.changan.com.cn` | SMS code or a pasted access token | [`docs/sda-api.md`](docs/sda-api.md) |

The international platform is the fully implemented path: REST telemetry, remote commands signed
with the account keypair, S05 MQTT telemetry (`docs/mqtt-telemetry.md`) and read-only digital key
checks. The SDA client is a thin access-token client for the Chinese platform; its commands are
recovered from the app but not verified live.

## Requirements

- Python 3.10 or newer.
- Runtime dependencies: `httpx`, `pydantic` v2 and `cryptography`.

## Installation

The package is distributed from the repository (it is not on PyPI):

```bash
pip install -e deepal_sdk
```

For the test dependencies:

```bash
pip install -e "deepal_sdk[dev]"
```

The examples under `deepal_sdk/examples/` make the SDK importable from their own location, so they
also run from a clean checkout with any interpreter that has the runtime dependencies.

## Quickstart: international platform

```python
import asyncio

from deepal import DeepalIntlClient


async def main() -> None:
    async with DeepalIntlClient(country="ES", language="es_ES") as client:
        await client.request_email_code("you@example.com")
        code = input("Verification code: ").strip()
        token = await client.login_with_email_code("you@example.com", code)

        vehicles = await client.get_vehicles()
        for vehicle in vehicles:
            condition = await client.get_vehicle_condition(vehicle.car_id)
            print(
                vehicle.series_name,
                condition.battery.soc_percentage,
                condition.total_odometer_km,
            )

        print("Logged in:", bool(token.access_token))


asyncio.run(main())
```

SMS login is equivalent: `request_sms_code(phone, country_code)` followed by
`login_with_sms_code(phone, code, country_code)`. The phone number is national (no `+` prefix) and
the dial code is passed separately.

### Persist the session

The access token, the command-signing keypair and the device id are account credentials. Persist
them so a restart does not force a new login (the app treats the keypair as a stable identity):

```python
# Save after login
access_token = token.access_token
refresh_token = token.refresh_token
cac_token = token.cac_token
user_id = client.user_id
private_key_pem = client.private_key_pem
public_key = client.public_key
device_id = client.device_id

# Restore later
client = DeepalIntlClient(country="ES", device_id=device_id)
client.access_token = access_token
client.refresh_token = refresh_token
client.cac_token = cac_token
client.user_id = user_id
client.set_login_keypair(private_key_pem, public_key)
```

Store these values as secrets (for example in an OS keyring or the password manager of your
application), never in source control.

### Send a remote command

Commands are signed with the login private key. Door, window and trunk commands additionally
require the remote-control PIN created with the account, which the SDK exchanges for a short-lived
control token:

```python
client.control_pin = "123456"

command_id = await client.control_air_conditioner(
    vehicle.car_id, enabled=True, target_temp_c=22.0
)
result = await client.control_result_status(vehicle.car_id, command_id)
print(result.status)
```

See [`docs/intl-api.md`](docs/intl-api.md#10-remote-commands) for the complete command list, the
signature construction, the PIN/token rules and the command result codes.

### MQTT telemetry (S05)

Vehicles that report `protocol_type == "MQTT"` do not refresh their state over REST; the SDK
performs the app's single-use MQTT exchange instead:

```python
if DeepalIntlClient.is_mqtt_vehicle(vehicle):
    condition = await client.s05_mqtt_condition(vehicle.car_id)
else:
    condition = await client.get_vehicle_condition(vehicle.car_id)
```

The bootstrap, the connection options and the parameter mapping are documented in
[`docs/mqtt-telemetry.md`](docs/mqtt-telemetry.md).

## Quickstart: SDA (China) platform

```python
import asyncio

from deepal import DeepalClient


async def main() -> None:
    async with DeepalClient(access_token="sda_access_token") as client:
        vehicles = await client.get_vehicles()
        condition = await client.get_vehicle_condition(vehicles[0].car_id)
        print(condition.battery.soc_percentage, condition.doors.locked)


asyncio.run(main())
```

The SMS login flow (`request_sms_code` / `login_with_code`) is implemented but the recommended path
is an access token issued by the SDA platform. See [`docs/sda-api.md`](docs/sda-api.md) for the
headers, the telemetry mapping and the unverified caveats.

## Error handling

All errors derive from `DeepalError`, so a single `except` can cover the SDK:

```python
from deepal import (
    DeepalAPIError,
    DeepalAuthError,
    DeepalCommandAuthError,
    DeepalCommandNotReady,
    DeepalConnectionError,
    DeepalRateLimitError,
)

try:
    condition = await client.get_vehicle_condition(vehicle.car_id)
except DeepalAuthError:
    ...  # the session is gone: log in again (or refresh the tokens)
except DeepalConnectionError:
    ...  # network or timeout: retry later
except DeepalAPIError as err:
    ...  # gateway rejected the call; err.code and err.status_code carry the detail
```

- `DeepalAuthError`: missing, expired or rejected session (HTTP 401/403 and the app kick-out codes).
- `DeepalRateLimitError`: the gateway rate-limits the request or the control PIN has no attempts
  left.
- `DeepalCommandAuthError`: the command-signing material was rejected, or the PIN is expired/not
  set.
- `DeepalCommandNotReady`: a signed command was attempted without the private key or the PIN.
- `DeepalAPIError`: any other gateway or HTTP failure, with `code` and `status_code`.
- `DeepalConnectionError`: transport failure (`httpx.RequestError`).

The full code-to-exception mapping is in [`docs/intl-api.md`](docs/intl-api.md#11-errors). For the SDA
client only `DeepalAuthError`, `DeepalAPIError` and `DeepalConnectionError` are raised.

## Diagnostics

`DeepalIntlClient(enable_api_logging=True)` logs every request and response at `WARNING` level with
tokens, keys, VINs, emails, phones, PINs and serial numbers redacted, and truncates long strings.
Payload parsing never fails on missing groups: absent telemetry is reported as `None`, `False` or
`0` according to [`docs/models.md`](docs/models.md).

## Documentation

| Document | Contents |
| --- | --- |
| [`docs/intl-api.md`](docs/intl-api.md) | International platform: environments, headers, login, session refresh, telemetry, capabilities, digital key, signed commands, errors, diagnostics |
| [`docs/sda-api.md`](docs/sda-api.md) | SDA (China) platform: access token, headers, methods, telemetry mapping, limitations |
| [`docs/mqtt-telemetry.md`](docs/mqtt-telemetry.md) | S05 MQTT bootstrap, connection options and parameter mapping |
| [`docs/models.md`](docs/models.md) | Every public Pydantic model, its fields and their semantics |

Runnable examples:

| Example | Shows |
| --- | --- |
| [`examples/email_login_example.py`](examples/email_login_example.py) | Email-code login against the international platform |
| [`examples/sms_login_example.py`](examples/sms_login_example.py) | SMS-code login against the international platform |
| [`examples/basic_status.py`](examples/basic_status.py) | Vehicle list and telemetry over the SDA client |
| [`examples/login_example.py`](examples/login_example.py) | SMS login against the SDA platform |
| [`examples/digital_key_status.py`](examples/digital_key_status.py) | Read-only digital key and authorization checks |

## Development

```bash
.venv/bin/python -m pytest deepal_sdk/tests -q
```

The test suite uses `httpx.MockTransport` and fake clients; it never contacts the real API. When
changing the SDK, update the reference document for the affected platform in the same change.

## Home Assistant integration

The repository also ships a Home Assistant integration that consumes the SDK; its user
documentation is in the [root README](../README.md).
