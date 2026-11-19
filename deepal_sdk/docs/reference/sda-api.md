# SDA (China) platform API reference

Reference for `DeepalClient`, the client for the **SDA platform** used by mainland-China Changan
accounts. It documents the behaviour implemented in `deepal_sdk/deepal/client.py` and
`endpoints.py`.

> Scope: this is a thin access-token client. It lists vehicles, reads a condition snapshot and
> exposes two control commands. It has no token refresh, no signed commands and no MQTT support.
> The transport (host, gateway prefix and `X-VCS-User-Token` header) is aligned with the live
> gateway and the 1.12.0 app protocol. The SMS login is **not usable on its own**: the send-code
> request is gated by a captcha authorization code the client does not produce. The recommended
> path is an access token issued by the SDA platform.

## Contents

1. [Base URL and headers](#1-base-url-and-headers)
2. [Client construction](#2-client-construction)
3. [Authentication](#3-authentication)
4. [Vehicles](#4-vehicles)
5. [Telemetry](#5-telemetry)
6. [Remote commands (unverified)](#6-remote-commands-unverified)
7. [Errors](#7-errors)
8. [Public method index](#8-public-method-index)
9. [Limitations](#9-limitations)

## 1. Base URL and headers

The default host is `https://m.sda.changan.com.cn` (`DEFAULT_BASE_URL`), the production host the
official app uses. `https://acenter.sda.changan.com.cn` serves the same API, and
`https://pre-acenter.sda.changan.com.cn` is a preproduction host. Pass `base_url` to target another
deployment; the `/app-apigw` prefix is part of every path, so a custom host does not need it.

Requests are GET or POST depending on the method. Authenticated calls carry:

| Header | Value |
| --- | --- |
| `Content-Type` | `application/json;charset=utf-8` (form-encoded on the login endpoints) |
| `Timestamp` | Current Unix time in **seconds** |
| `Version` | `1.12.0` |
| `User-Agent` | `MyChangan/1.12.0 (Android; Deepal S05)` |
| `X-VCS-User-Token` | `<access_token>` (only with a session) |

`Authorization` and `token` are not sent: the gateway ignores them and uses the VCS header.

## 2. Client construction

```python
DeepalClient(
    access_token=None,
    base_url="https://m.sda.changan.com.cn",
    timeout=15.0,
    httpx_client=None,
    on_exchange=None,
)
```

- `access_token` may be provided at construction or assigned later; authenticated calls without
  one raise `DeepalAuthError` before any request.
- `httpx_client` injects an `httpx.AsyncClient`; the SDK uses it as-is and never closes it.
  Otherwise the client is created in the constructor and `close()` releases it.
- `on_exchange` is an optional synchronous callback that receives one structured event per REST
  exchange, with the same envelope as the international client. It is never called for MQTT
  because this client is REST-only. Redact the event before persisting it.
- The client is an async context manager (`async with DeepalClient(...) as client:`).

## 3. Authentication

### 3.1 SMS verification code (captcha-gated)

```python
success = await client.request_sms_code("13800000000")
token = await client.login_with_code("13800000000", code)
```

| Method | Request | Result |
| --- | --- | --- |
| `request_sms_code(phone)` | `POST /app-apigw/appauth/sda-app/api/user/login/code` with form `phone=<phone>` | `True` when the response code is `0`/`200` |
| `login_with_code(phone, code)` | `POST /app-apigw/appauth/sda-app/api/v3/oauth2-login/token/bind` with form `phone` and `code` | `AuthToken`; stores `client.access_token` |

The send-code request is rejected with business code `777` ("图形验证授权码不能为空") unless it
carries a captcha authorization code issued by the official app or its captcha vendor. The client
does not implement that step, so `request_sms_code` surfaces the gateway error as a
`DeepalAPIError`; obtaining the SMS code outside Home Assistant is a prerequisite.

The login reads `data.token` (or `data.access_token`), `data.expires_in` and `data.user_id`, and
raises `DeepalAuthError` when no token is returned. The integration obtains the token from the SDA
platform and validates it through [`get_vehicles()`](#4-vehicles).

### 3.2 Access token

The token is long-lived; the client never refreshes it. An HTTP 401/403, business code `46000`, or
business code `40005` naming the user-token header raises `DeepalAuthError`, which for the
integration means the token must be replaced.

## 4. Vehicles

`await client.get_vehicles()` calls
`GET /app-apigw/dae-terminal-mobile/api/v1/car/my-cars` and maps each entry, accepting the SDA and
international field spellings:

| API field candidates | Model field |
| --- | --- |
| `car_id`, `carId`, `id` | `car_id` |
| `vin` | `vin` |
| `series_name`, `carModelName` (default `Deepal S05`) | `series_name` |
| `car_name`, `nickName` | `car_name` |
| `car_num`, `licensePlate` | `license_plate` |
| `car_pic`, `thumbnailUrl` | `thumbnail_url` |

## 5. Telemetry

`await client.get_vehicle_condition(car_id)` calls
`GET /app-apigw/dae-terminal-mobile/api/v1/car/full-condition?carId=<car_id>` and maps the raw
parameters.
The method also accepts an optional `vin` keyword for call compatibility with the international
client (the coordinator passes the VIN for every platform); the SDA endpoint ignores it because it
addresses vehicles by car id:

| API field | Meaning | Model property |
| --- | --- | --- |
| `vin` | VIN | `vin` |
| `CdcTotMilg`, `total_odometer` | Total odometer (km) | `total_odometer_km` |
| `BatterySoc`, `battery_level` | State of charge (%) | `battery.soc_percentage` |
| `RemainingRange`, `battery_range` | Estimated range (km) | `battery.remaining_range_km` |
| `ChargingState` | Charging state (raw) | `battery.charging_status` |
| `ChargerPlugged` | Charging cable plugged in | `battery.charger_connected` |
| `DoorsLocked` (default `True`) | Doors locked | `doors.locked` |
| `DoorFLOpen`, `DoorFROpen`, `DoorRLOpen`, `DoorRROpen` | Open doors | `doors.driver_door_open`, `passenger_door_open`, `rear_left_door_open`, `rear_right_door_open` |
| `TrunkOpen` / `HoodOpen` | Boot / hood | `doors.trunk_open` / `doors.hood_open` |
| `AcPowerOn` | Climate on | `climate.power_on` |
| `AcTargetTemp` | Target temperature (raw) | `climate.target_temperature_c` |

`last_updated_timestamp` is set to the local time of the response because the payload does not
report a reliable timestamp. The untouched payload is available in `raw_data`; only the fields in
the table are parsed, so the rest of the condition groups stay at their model defaults.

## 6. Remote commands (unverified)

Two commands are implemented from the app protocol; neither is exercised by the Home Assistant
integration and neither has been verified against a live vehicle.

| Method | Request | Result |
| --- | --- | --- |
| `set_climate_control(car_id, power_on, target_temp_c=None)` | `POST /app-apigw/dae-terminal-mobile/api/v1/control/climate` with `{"carId", "acPower": 1/0, "targetTemp"}` | `True` on a success code |
| `set_door_lock(car_id, lock)` | `POST /app-apigw/dae-terminal-mobile/api/v1/control/lock` with `{"carId", "action": "lock"/"unlock"}` | `True` on a success code |

Both return a boolean derived from the response `code` and raise `DeepalAPIError` when the gateway
rejects the request. Do not rely on them without testing against the target account and vehicle.

## 7. Errors

| Situation | Exception |
| --- | --- |
| Missing access token on an authenticated call | `DeepalAuthError` |
| HTTP 401/403 | `DeepalAuthError` |
| Business code `46000` (token invalid or expired) | `DeepalAuthError` |
| Business code `40005` naming `X-VCS-User-Token` | `DeepalAuthError` |
| Invalid JSON response | `DeepalAPIError` |
| Other business code outside `0`/`200` (for example `777` captcha, `40001` busy) | `DeepalAPIError` (with `code` and `status_code`) |
| Non-2xx HTTP status | `DeepalAPIError` (with `status_code`) |
| Transport failure or timeout (`httpx.RequestError`) | `DeepalConnectionError` |

## 8. Public method index

| Method | Summary |
| --- | --- |
| `close()` | Close the managed HTTP client |
| `request_sms_code(phone)` | Request an SMS login code (unverified) |
| `login_with_code(phone, code)` | Exchange the code for an access token (unverified) |
| `get_vehicles()` | List the account vehicles |
| `get_vehicle_condition(car_id, vin=None)` | Condition snapshot (`vin` accepted for call compatibility and ignored) |
| `set_climate_control(car_id, power_on, target_temp_c=None)` | Climate command (unverified) |
| `set_door_lock(car_id, lock)` | Door lock/unlock command (unverified) |

## 9. Limitations

- No token refresh, token expiry tracking or logout; replace the token when the API rejects it.
- The SMS login is captcha-gated: `request_sms_code` cannot obtain a code without an authorization
  code produced outside the SDK. The supported setup path is a pasted access token.
- No signed remote commands, no control PIN and no command-result polling.
- No MQTT telemetry; the S05 path and the `SDA-MQTT` beta are international-client features.
- Only the endpoints listed above are implemented. `endpoints.py` also declares constants for car
  status, settings, home charger, charge history and parking commands that no client method uses.
- `https://pre-acenter.sda.changan.com.cn` is preproduction; production entries should use the
  default host or another deployment confirmed with the account.
- The vehicle and control paths have only been verified up to the gateway's authentication response
  (a fake token returns `46000`); a live token is still needed to validate the payloads.
