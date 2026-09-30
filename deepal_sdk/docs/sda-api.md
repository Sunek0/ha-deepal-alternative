# SDA (China) platform API reference

Reference for `DeepalClient`, the client for the **SDA platform** used by mainland-China Changan
accounts. It documents the behaviour implemented in `deepal_sdk/deepal/client.py` and
`endpoints.py`.

> Scope: this is a thin access-token client. It lists vehicles, reads a condition snapshot and
> exposes two control commands. It has no token refresh, no signed commands and no MQTT support.
> Most flows are recovered from the app protocol but are **not verified against the live platform**;
> the recommended path is an access token issued by the SDA platform.

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

The default host is `https://pre-acenter.sda.changan.com.cn` (`DEFAULT_BASE_URL`); pass
`base_url` to target another SDA deployment. Requests are GET or POST depending on the method, and
authenticated calls carry:

| Header | Value |
| --- | --- |
| `Content-Type` | `application/json;charset=utf-8` |
| `Timestamp` | Current Unix time in **seconds** |
| `Version` | `1.12.0` |
| `User-Agent` | `MyChangan/1.12.0 (Android; Deepal S05)` |
| `Authorization` | `Bearer <access_token>` (only with a session) |
| `token` | `<access_token>` (same value, sent alongside `Authorization`) |

## 2. Client construction

```python
DeepalClient(
    access_token=None,
    base_url="https://pre-acenter.sda.changan.com.cn",
    timeout=15.0,
    httpx_client=None,
)
```

- `access_token` may be provided at construction or assigned later; authenticated calls without
  one raise `DeepalAuthError` before any request.
- `httpx_client` injects an `httpx.AsyncClient`; the SDK uses it as-is and never closes it.
  Otherwise the client is created in the constructor and `close()` releases it.
- The client is an async context manager (`async with DeepalClient(...) as client:`).

## 3. Authentication

### 3.1 SMS verification code (unverified)

```python
success = await client.request_sms_code("13800000000")
token = await client.login_with_code("13800000000", code)
```

| Method | Request | Result |
| --- | --- | --- |
| `request_sms_code(phone)` | `POST /appauth/sda-app/api/user/login/code` with `{"phone": phone}` | `True` when the response code is `0`/`200` |
| `login_with_code(phone, code)` | `POST /appauth/sda-app/api/v2/oauth2-login/token/bind` with `{"phone": phone, "code": code}` | `AuthToken`; stores `client.access_token` |

The login reads `data.token` (or `data.access_token`), `data.expires_in` and `data.user_id`, and
raises `DeepalAuthError` when no token is returned. The request/response field names follow the app
protocol and **have not been verified live**; the integration obtains the token from the SDA
platform and validates it through [`get_vehicles()`](#4-vehicles).

### 3.2 Access token

The token is long-lived; the client never refreshes it. An HTTP 401/403 raises `DeepalAuthError`,
which for the integration means the token must be replaced.

## 4. Vehicles

`await client.get_vehicles()` calls `GET /dae-terminal-mobile/api/v1/car/my-cars` and maps each
entry, accepting the SDA and international field spellings:

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
`GET /dae-terminal-mobile/api/v1/car/full-condition?carId=<car_id>` and maps the raw parameters:

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
| `set_climate_control(car_id, power_on, target_temp_c=None)` | `POST /dae-terminal-mobile/api/v1/control/climate` with `{"carId", "acPower": 1/0, "targetTemp"}` | `True` on a success code |
| `set_door_lock(car_id, lock)` | `POST /dae-terminal-mobile/api/v1/control/lock` with `{"carId", "action": "lock"/"unlock"}` | `True` on a success code |

Both return a boolean derived from the response `code` and raise `DeepalAPIError` when the gateway
rejects the request. Do not rely on them without testing against the target account and vehicle.

## 7. Errors

| Situation | Exception |
| --- | --- |
| Missing access token on an authenticated call | `DeepalAuthError` |
| HTTP 401/403 | `DeepalAuthError` |
| Invalid JSON response | `DeepalAPIError` |
| Response code outside `0`/`200` | `DeepalAPIError` (with `code` and `status_code`) |
| Non-2xx HTTP status | `DeepalAPIError` (with `status_code`) |
| Transport failure or timeout (`httpx.RequestError`) | `DeepalConnectionError` |

## 8. Public method index

| Method | Summary |
| --- | --- |
| `close()` | Close the managed HTTP client |
| `request_sms_code(phone)` | Request an SMS login code (unverified) |
| `login_with_code(phone, code)` | Exchange the code for an access token (unverified) |
| `get_vehicles()` | List the account vehicles |
| `get_vehicle_condition(car_id)` | Condition snapshot |
| `set_climate_control(car_id, power_on, target_temp_c=None)` | Climate command (unverified) |
| `set_door_lock(car_id, lock)` | Door lock/unlock command (unverified) |

## 9. Limitations

- No token refresh, token expiry tracking or logout; replace the token when the API rejects it.
- No signed remote commands, no control PIN and no command-result polling.
- No MQTT telemetry; the S05 path and the `SDA-MQTT` beta are international-client features.
- Only the endpoints listed above are implemented. `endpoints.py` also declares constants for car
  status, settings, home charger, charge history and parking commands that no client method uses.
- The default base URL points at a pre-production host; production integrations should pass an
  explicit `base_url` only after confirming it with the account.
