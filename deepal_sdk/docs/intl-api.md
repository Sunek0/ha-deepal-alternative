# International platform API reference

Reference for `DeepalIntlClient`, the client for the **My Changan / Deepal international**
platform (Europe and Latin America). It documents the behaviour implemented in
`deepal_sdk/deepal/intl.py`, `endpoints.py` and `models/`.

> All requests are **POST** with a compact JSON body, including reads. There is no GET.

## Contents

1. [Architecture and gateways](#1-architecture-and-gateways)
2. [Environments](#2-environments)
3. [Client construction](#3-client-construction)
4. [Request headers](#4-request-headers)
5. [Authentication](#5-authentication)
6. [Vehicles](#6-vehicles)
7. [REST telemetry](#7-rest-telemetry)
8. [Vehicle capabilities](#8-vehicle-capabilities)
9. [Digital key (read-only)](#9-digital-key-read-only)
10. [Remote commands](#10-remote-commands)
11. [Errors](#11-errors)
12. [Diagnostics and redaction](#12-diagnostics-and-redaction)
13. [Public method index](#13-public-method-index)

## 1. Architecture and gateways

The international platform is reached through three hosts:

| Gateway | Purpose | Path prefix |
| --- | --- | --- |
| International | Login, vehicles, REST telemetry, signed commands | `/intl-app-gw/...` |
| CA (`ca_base_url`) | MQTT bootstrap: connection config and auth token | `/user-apigw/...` and `/app-apigw/...` |
| Regional SDA (`sda_base_url`) | Read-only digital key checks | `/app-apigw/...` |

Response envelope:

```json
{ "success": true, "code": "0", "msg": "", "data": {} }
```

`DeepalIntlClient` returns the `data` field. A `success: false` response raises a typed exception
(see [Errors](#11-errors)).

## 2. Environments

`DeepalIntlClient(environment=...)` resolves all three hosts plus the `appid` value from
`deepal/endpoints.py::INTL_ENVIRONMENTS`, reconstructed from the app's `LocalEnvironments`:

| `environment` | Region | International | CA | Regional SDA | `appid` |
| --- | --- | --- | --- | --- | --- |
| `release_eu` (default) | Europe | `https://m.iov.changanauto.com.de` | `https://ca-m.iov.changanauto.com.de` | `https://sda-m.iov.changanauto.com.de` | `ca` |
| `release_znm` | Latin America | `https://m.mx.changanauto.link` | `https://m.mx.changanauto.link` | `https://sda-m.mx.changanauto.link` | `ca` |

Retired identifiers (`release_eu_mix`, `preprod_eu`, `release_ase`, `release_ase_connect`,
`release_dlt`, `release_st`, `release_alq`) resolve to `release_eu` so stored configurations do not
break; an account from those regions must select the correct environment explicitly. Unknown
values raise `ValueError`. `base_url`, `ca_base_url` and `sda_base_url` override the hosts
individually (diagnostics or tests).

## 3. Client construction

```python
DeepalIntlClient(
    country="GB",
    language="en_US",
    app_version="V1.12.0",
    app_type="Android",
    device_type="samsung",
    os_version="9",
    tsp_token_source="access",
    environment="release_eu",
    mqtt_config_fallback=True,
    mqtt_token_fallback=True,
    mqtt_client_id=None,
    mqtt_username=None,
    mqtt_keepalive=60,
    mqtt_clean_start=True,
    mqtt_tls_insecure=False,
    device_id=None,
    private_key_pem=None,
    public_key=None,
    base_url=None,
    ca_base_url=None,
    sda_base_url=None,
    timeout=15.0,
    enable_api_logging=False,
    signing_policy="app",
    httpx_client=None,
)
```

| Parameter | Description |
| --- | --- |
| `country` | Sales country sent as `selectcountry` and used by the login flows (`GB` default). |
| `language` | Sent as `language` and `accept-language` (`en_US` default). |
| `app_version`, `app_type`, `device_type`, `os_version` | Declared app identity; defaults match the 1.12.0 app capture. Overridable for diagnostics. |
| `tsp_token_source` | Which session value is sent as `X-Tsp-User-Token`/`X-VCS-User-Token`: `access` (default, verified live), `cac`, `cac_user_id` or `ca_user_id`. Diagnostic only. |
| `environment` | Regional gateway set (see [Environments](#2-environments)). |
| `mqtt_config_fallback`, `mqtt_token_fallback` | Allow the app's fallback endpoints when the CA bootstrap fails (see `mqtt-telemetry.md`). |
| `mqtt_client_id`, `mqtt_username` | MQTT identity overrides; otherwise resolved from the connection config. |
| `mqtt_keepalive` | MQTT keepalive seconds (default 60). |
| `mqtt_clean_start` | MQTT clean-start flag (default `True`). |
| `mqtt_tls_insecure` | Disables MQTT certificate and hostname verification (diagnostic; logs a warning). |
| `device_id` | Persistent client fingerprint; generated as 32 lowercase hex characters when omitted. Reuse the same value across restarts. |
| `private_key_pem`, `public_key` | Command-signing keypair to reuse; see [Login keypair](#52-login-keypair). |
| `timeout` | HTTP timeout in seconds (default 15). |
| `enable_api_logging` | Log redacted requests and responses at `WARNING` level. |
| `signing_policy` | `app` (default) or `legacy`; see [Signature](#103-signature). |
| `httpx_client` | Inject an `httpx.AsyncClient`; the SDK uses it as-is and never closes it. |

`base_url`, `ca_base_url` and `sda_base_url` default to the selected environment. The managed HTTP
client is created lazily on the first request (TLS setup off the event loop); `close()` tolerates a
client that was never created. The client is an async context manager.

## 4. Request headers

Every request carries the declared app identity:

| Header | Value |
| --- | --- |
| `appid` | Environment app id (`ca`) |
| `apptype` | `Android` |
| `appversion` | `V1.12.0` |
| `devicetype` | `samsung` |
| `deviceid` | Persistent client id (32 hex chars) |
| `selectcountry` | `country` |
| `language` / `accept-language` | `language` |
| `x-os-version` | `os_version` (`9` by default) |
| `content-type` | `application/json; charset=UTF-8` |
| `user-agent` | `okhttp/4.12.0` |

With a session, authenticated requests add:

| Header | Value |
| --- | --- |
| `authorization` | `access_token`, or `access_token\|cac_token` when a CAC token is present |
| `X-Tsp-User-Token` / `X-VCS-User-Token` | Access token (verified against the production CA gateway on 2026-09-19; the CAC token is rejected with `APIGW_-1_7_01_004` and an empty header with `APIGW_1_7_02_001`) |

`X-Tsp-Timestamp` and `X-VCS-Timestamp` are never sent.

## 5. Authentication

### 5.1 Sensitive value encryption

Email, phone, password and PIN are encrypted with the app's RSA public key
(`endpoints.REQUEST_ENCRYPTION_PUBLIC_KEY`, DER/SPKI in base64) using **RSA PKCS#1 v1.5** and sent
base64-encoded:

```python
encrypted = DeepalIntlClient.encrypt_request_value("you@example.com")
```

### 5.2 Login keypair

The login registers a public key (`pubKey`) that later signs remote commands. It is an RSA 1024-bit
identity, like the app's persisted `SP_KEY_SELF_PUBKEY`/`SP_KEY_SELF_PRIKEY`:

- `generate_login_keypair()` returns `(private_key_pem, public_key_body)`.
- `public_key_body_from_private(private_key_pem)` derives the app `pubKey` body (base64 DER without
  PEM headers) from a stored private key.
- `set_login_keypair(private_key_pem, public_key=None)` restores a persisted pair; the public key
  is derived when omitted.
- When a login runs without any key material, the SDK generates a pair and exposes
  `client.private_key_pem` and `client.public_key`.
- A stored keypair is never replaced while only the public half is missing; a login does not
  register a new public key when one is already available.

If a login only provides `pub_key` (no private key), commands cannot be signed: signed command
methods raise `DeepalCommandNotReady`.

### 5.3 Email verification code

```python
await client.request_email_code("you@example.com")
token = await client.login_with_email_code("you@example.com", code)
```

Optional `sales_country` and `pub_key` arguments override the client `country` and the stored
keypair for that login.

### 5.4 SMS verification code

```python
await client.request_sms_code("600000000", "34")
token = await client.login_with_sms_code("600000000", code, "34")
```

Input rules (validated locally before any HTTP call):

- `phone` is the **national** number without the country prefix; a leading `+` raises `ValueError`.
- `country_code` must contain digits only; a leading `+` is stripped (`+34` becomes `34`).
- Empty values raise `ValueError`.

### 5.5 Password logins (unverified)

`login_with_email_password(email, password, ...)` and
`login_with_password(phone, password, country_code, ...)` call the routes recovered from the 1.12.0
app (`email-pass-in` and `login-by-pwd`). The app method bodies are VMP-extracted, so the field
names are modelled on the code flows and **have not been verified against live traffic**. The
verification-code flows remain the supported path.

### 5.6 Session and tokens

A successful login stores, and returns as `AuthToken`:

| Attribute | `AuthToken` field | Description |
| --- | --- | --- |
| `client.access_token` | `access_token` | Bearer token |
| `client.refresh_token` | `refresh_token` | Refresh token (exchanged at `auth/refresh-token`) |
| `client.cac_token` | `cac_token` | CAC/TSP token; when present, `authorization` becomes `access\|cac` |
| `client.user_id` | `user_id` | Account user id (required by MQTT and digital key checks) |
| `client.ca_user_id` | `ca_user_id` | CA user id |
| `client.cac_user_id` | `cac_user_id` | CAC user id |

`access_token_expires_soon(margin_seconds=300)` reports whether the JWT `exp` claim is within the
margin, parsing the token lazily when the session was restored without parsing it.

### 5.7 Token refresh

`await client.refresh_tokens(force=False)`:

- **Throttled** with a monotonic 30-minute window (`INTL_REFRESH_THROTTLE_SECONDS = 1800.0`),
  matching the app's `tokenExpireTime = 1800000`. A throttled call returns the current session
  without raising or sending a request.
- **Single-flight**: an internal lock serializes attempts; concurrent callers share the outcome.
- **Proactive**: a refresh bypasses the window when the access token expires within five minutes.
- **Forced**: `force=True` bypasses the window after an authentication rejection.
- The response may omit fields: omitted `refreshToken`, `cacToken`, `userId`, `caUserId` and
  `cacUserId` keep their previous values.

The CAC token is not guaranteed to be renewed by a refresh; when the response does not carry a new
one, the SDK logs a warning and the CA/MQTT bootstrap keeps the previous token. Requires a stored
`refresh_token`, otherwise `DeepalAuthError`.

### 5.8 Logout (unverified)

`await client.logout()` posts to the logout route with the session headers and clears
`access_token`, `refresh_token`, `cac_token`, `rc_token` and `access_token_expires_at` even when
the remote call fails. Without an access token it does nothing. The body was not verified against
live traffic.

## 6. Vehicles

`await client.get_vehicles()` returns the account vehicles as `Vehicle` models:

| API field | Model field |
| --- | --- |
| `carId` | `car_id` |
| `vin` | `vin` |
| `seriesName` | `series_name` |
| `seriesCode` | `series_code` |
| `modelName` / `modelCode` | `model_name` / `model_code` |
| `nickName` | `car_name` |
| `licensePlate` | `license_plate` |
| `imgUrl` (and image aliases) | `thumbnail_url` |
| `protocolType` | `protocol_type` (`MQTT` marks MQTT-backed telemetry) |

`data` is a list or a `{ "list": [...] }` object. `is_mqtt_vehicle(vehicle)` is a static helper
returning whether `protocol_type` is `MQTT`.

## 7. REST telemetry

`await client.get_vehicle_condition(vehicle_id, vin=None)` requests the app's condition sections
(`seat`, `door`, `hvac`, `charge`, `lamp`, `window`, `tire`, `vehicleStatus`, `fuel`; the API field
is the intentional typo `vechileCriteria`) and maps the response into `VehicleCondition`.
`parse_condition(raw, vehicle_id, vin=None)` applies the same mapping to a raw payload (used by the
MQTT path).

Mapping:

| API field | Meaning | Model property |
| --- | --- | --- |
| `vin` | VIN | `vin` |
| `lastUpdatedAt` (root or `vehicleStatus`) | Unix ms or ISO-8601 | `last_updated_timestamp` (seconds) |
| `vehicleStatus.soc` | State of charge (%) | `battery.soc_percentage` |
| `vehicleStatus.drvMileage` | Estimated range (km) | `battery.remaining_range_km` |
| `vehicleStatus.totalMileage` | Total odometer (km) | `total_odometer_km` |
| `vehicleStatus.totalMeterYesterday` | Mileage yesterday (km) | `mileage_yesterday_km` |
| `vehicleStatus.igniteCumulativeMileage` | Mileage since ignition (km) | `trip_mileage_km` |
| `vehicleStatus.speed` | Speed (km/h) | `speed_kmh` |
| `vehicleStatus.gearSignal` | Raw gear signal | `gear` (string) |
| `vehicleStatus.epbSts` / `powerStatus` / `status` | Raw states | `epb_status` / `power_status` / `vehicle_status` |
| `vehicleStatus.engineSts` | Engine running (`!= 0`) | `engine_on` |
| `vehicleStatus.connectStatus` | Cloud connection (`== 1`) | `connected` |
| `vehicleStatus.steeringWheelHeater` | Steering wheel heater (`!= 0`) | `climate.steering_wheel_heater_on` |
| `vehicleStatus.steeringWheelHeaterLevel` | Heater level | `climate.steering_wheel_heater_level` |
| `charge.chargeStatus` | Charging state (`!= 0` means connected) | `battery.charging_status` (string) |
| `charge.chargeConStatus` | Cable state (`0`/`1` disconnected) | `battery.charger_connected` fallback |
| `charge.dcChargeGunConnectStatus` | DC gun (`0`/`1` disconnected) | `battery.dc_gun_connected` |
| `charge.chargeCurrent` / `acChargeCurrent` / `dcChargeCurrent` | Charging currents (A) | `battery.charge_current_a` / `ac_charge_current_a` / `dc_charge_current_a` |
| `charge.remainChargeTime` | Remaining minutes; `8191` = no estimate | `battery.remaining_charge_time_min` (`8191` becomes `None`) |
| `charge.maxSocPercent` | Charge limit (%) | `battery.charge_limit_percent` |
| `charge.chargePlanList[0]` | `startSwitch`, `endSwitch`, `startTime`, `endTime`, `planId`, `planType`, `timeFormat`, `timeZone` | `battery.charge_schedule_*` (`charge_schedule_enabled` requires both switches `1`) and `battery.charge_plan_*` |
| `fuel.leftPercent` | Fuel level (%) | `fuel.level_percent` |
| `fuel.leftVolume` / `tankVolume` | Fuel volume / tank capacity (L) | `fuel.volume_l` / `fuel.tank_capacity_l` |
| `fuel.temperature` | Fuel temperature (C) | `fuel.temperature_c` |
| `fuel.*RemainingMileage` | Fuel range (km), WLTC preferred | `fuel.remaining_range_km` |
| `door.doors[0..3]` | Driver, passenger, rear left, rear right | `doors.*_door_open` |
| `door.trunk` / `door.hood` | Boot / hood | `doors.trunk_open` / `doors.hood_open` |
| `door.driverLock` / `passengerLock` | `0` = locked | `doors.locked` (driver preferred, else passenger, else `True`) and `doors.driver_locked` / `passenger_locked` |
| `hvac.acStatus` | AC (`!= 0` on; absent stays unknown) | `climate.power_on` |
| `hvac.remoteTemp` | Target temperature (tenths of degree) | `climate.target_temperature_c` |
| `hvac.insideTemp` / `outsideTemp` | Cabin / outside temperature (tenths) | `climate.inside_temperature_c` / `outside_temperature_c` |
| `hvac.insideHumidity` / `insidePm25` / `insideAirQualityLevel` | Air quality | `climate.humidity` / `inside_pm25` / `air_quality_level` |
| `hvac.defrostStatus` / `fanLevel` | Defrost / fan | `climate.defrost_on` / `fan_level` |
| `lamp.highBeam`, `lowBeam`, `positionLamp`, `frontFoglamp`, `rearFoglamp`, `leftTurn`, `rightTurn` | Exterior lamps | `lamps.*` |
| `window.windows[0..3]` | Front left, front right, rear left, rear right | `windows.*_open` |
| `seat.leftFront` / `rightFront` | `heatStatus`, `ventStatus` | `seats.front_left` / `front_right` |
| `seat.leftBack` / `rightBack` | `level` (heating) | `seats.rear_left` / `rear_right` |
| `tire.leftFront`, `rightFront`, `leftBack`, `rightBack` | `pressure` (kPa), `temperature`, `alarm`/`status` | `tires.*` (`pressure_bar` = kPa / 100) |

Notes:

- Missing groups default to `None`, `False` or `0`; no error is raised, so a partial payload is a
  valid snapshot.
- Sleep sentinels and out-of-range seat levels (`> 3`, for example `6` on a sleeping module) map to
  `None` ("unknown"), never to a made-up level.
- `climate.power_on` and other comfort states are tri-state: absent means unknown, not off.
- The original payload is kept in `VehicleCondition.raw_data`.

## 8. Vehicle capabilities

`await client.get_vehicle_capabilities(vehicle_id, vin=None)` queries the per-vehicle function
configuration the app uses to decide which controls to offer. The request body key was not
recovered from the DEX, so the known candidates are tried in order (`carId`, `vehicleId`, `vin`).

Returns `VehicleCapabilities` built from the response `confList`, or `None` when unavailable. The
function is non-fatal: authentication failures, rate limits and unavailable endpoints return
`None`; rejected body candidates are tried in turn.

`VehicleCapabilities` exposes `raw_codes`, per-seat `seats` (`heating`/`ventilation`), `has_fuel`
(the `#oilMileage` function code) and `trim_hint` (`max` when a front seat has ventilation, else
`pro`, else `unknown`).

## 9. Digital key (read-only)

Two non-fatal, read-only checks against the regional SDA gateway. They never provision, download
or share keys and never touch BLE; any failure logs and returns `None`.

| Method | Purpose |
| --- | --- |
| `await client.get_digital_key_support(vehicle_id=None)` | Phone key scheme: `flag` 0 = `ca`, 1 = `icce`, 2 = `honor`, anything else `unknown` (`DigitalKeySupport.supported`) |
| `await client.get_vehicle_authorizations(car_id)` | Function codes the account may use on the vehicle (`DigitalKey` flags the digital key); the service is not deployed in every region (the European gateway answers 404) |

## 10. Remote commands

All commands send a signed JSON body and return a `commandId` string that is polled through the
command-result endpoint.

### 10.1 Prerequisites

- `private_key_pem`: signs the payload (`DeepalCommandNotReady` otherwise).
- `rc_token`: required by PIN-gated commands (doors, windows, trunk). Obtained once with the
  remote-control PIN and cached; the server rejects it only when a command reuses it, at which
  point the SDK re-exchanges the PIN and retries once.
- `control_pin`: the account PIN, used to obtain `rc_token` automatically when the first
  PIN-gated command runs.
- Serial number: fetched per command family (`type: "1"` or `"2"`) and decrypted with the private
  key.

### 10.2 Control code exchange

| Method | Behaviour |
| --- | --- |
| `await client.get_security_code_status()` | Fetches `retryQuantity` and PIN state; called before every exchange |
| `await client.check_control_code(pin)` | Encrypts the PIN, exchanges it for `rcToken`, stores it in `client.rc_token` and returns it |

When `get-status` reports no remaining attempts, `DeepalRateLimitError` is raised and no exchange
is attempted. `HW_1_1_01_073` (expired) and `HW_1_1_01_074` (not set) raise
`DeepalCommandAuthError` with guidance to set or reset the PIN in the app.

### 10.3 Signature

`sign_payload(payload, omit_keys=None)` builds the canonical string and signs it:

- Keys sorted alphabetically, `key=value` pairs joined with `&`.
- The `app` policy (default) excludes exactly `sign`, `class` and `command`; per-command
  `omit_keys` are ignored. `APP_SIGN_EXCLUDED_KEYS` exposes the set.
- The `legacy` policy keeps the previous per-command omission sets for rollback and A/B checks.
  `SIGNING_POLICY_APP` (`"app"`), `SIGNING_POLICY_LEGACY` (`"legacy"`) and `SIGNING_POLICIES`
  expose the supported values.
- Booleans become lowercase `true`/`false`; `None` becomes `null`.
- Signature: **RSA PKCS#1 v1.5 + SHA-256** with the login private key, base64 **MIME** encoded
  (with line breaks), like the app.

Example canonical string for the air conditioner with the `app` policy and no cached `rcToken`:

```
enabled=true&runTime=30&seriralNo=SN123&targetTemp=220&vehicleId=car-1&windMode=1
```

`rc_token` is serialized into the body only by the PIN-gated commands; every other family omits it
even when a cached token exists. An empty `rcToken` is rejected with `COMMON_1_1_01_008`.

### 10.4 Command reference

`serial_type` is the serial-number family fetched before signing. "PIN" marks commands that
require and send `rc_token`.

| Method | Endpoint | Payload | PIN | `serial_type` | Status |
| --- | --- | --- | --- | --- | --- |
| `control_air_conditioner(vehicle_id, enabled, target_temp_c, run_time=30, wind_mode=1)` | `/control/air-conditioner` | `command="air"`, `enabled`, `runTime`, `targetTemp` (tenths), `windMode` | No | `1` | Verified live |
| `control_condition_inquiry(vehicle_id)` | `/control/condition-inquiry` | `command="COMMAND_GET_NEW_CONDITION"` | No | `1` | Verified live |
| `control_doors(vehicle_id, open_value)` | `/control/doors` | `command="lock"`, `open` | Yes | `1` | Verified live |
| `control_windows(vehicle_id, open_value, open_type=10)` | `/control/windows` | `command="window"`, `open`, `openType` | Yes | `1` | Verified live |
| `control_trunk(vehicle_id, open_value)` | `/control/trunk` | `command="trunk"`, `open` | Yes | `1` | Verified live |
| `control_charge_limit(vehicle_id, percentage)` | `/charge/percentage` | `command="charge_max"`, `chargePercentageMax` | No | `2` | Verified live |
| `control_charge_schedule(vehicle_id, plan_id, start_time, end_time, enabled, plan_type=1, time_format=1, time_zone="GMT+08:00")` | `/charge/modify-plan` | `command="modify-plan"`, `planId`, `startTime`, `endTime`, `endSwitch`, `planType`, `timeFormat`, `timeZone` | No | `2` | Verified live |
| `control_flashing_honking(vehicle_id, action_type)` | `/control/flashing-honking` | `command="flash_bee"`, `type` | No | `1` | Verified live |
| `control_defrost(vehicle_id, enabled, serial_type="1", require_rc_token=False)` | `/control/defrost` | `command="defrost"`, `enabled` | Optional | `1` | Recovered; the car did not act on it |
| `control_seats_heat(vehicle_id, master_switch=None, master_level=None, copilot_switch=None, copilot_level=None, ...)` | `/control/seats/heat` | `command="seats_heat"` plus only the provided positions | Optional | `1` | Verified live |
| `control_seats_wind(...)` | `/control/seats/wind` | `command="seats_wind"` plus only the provided positions | Optional | `1` | Verified live |
| `control_steering_wheel_heat(vehicle_id, open_value, ...)` | `/control/steering-wheel/heat` | `command="steering_wheel_heating"`, `open` | Optional | `1` | Verified live |
| `control_charge_plan_add(vehicle_id, start_time, end_time, end_switch, ...)` | `/charge/add-plan` | `command="add_charge_plan"`, `startTime`, `endTime`, `endSwitch`, `planType`, `timeFormat`, `timeZone` | Optional | `2` | Recovered |
| `control_charge_plan_delete(vehicle_id, plan_id, ...)` | `/charge/delete-plan` | `command="delete_charge_plan"`, `planId` | Optional | `2` | Recovered |
| `control_charge_plan_validity(vehicle_id, plan_id, enabled, ...)` | `/charge/validity` | `command="COMMAND_VALID_CHARGE_PLAN"`, `enabled`, `planId` | Optional | `2` | Recovered |
| `control_departure_plan_add(vehicle_id, start_time, weeks, ...)` | `/departure-plans/add-plan` | `command="COMMAND_TRAVELPLAN_ADD"`, `isValid`, `planType`, `startTime`, `type`, `weeks` | Optional | `1` | Recovered |
| `control_departure_plan_modify(vehicle_id, plan_id, start_time, weeks, ...)` | `/departure-plans/modify-plan` | `command="COMMAND_TRAVELPLAN_MODIFY_PLAN"`, `planId`, `isValid`, `planType`, `startTime`, `type`, `weeks` | Optional | `1` | Recovered |
| `control_departure_plan_delete(vehicle_id, plan_id, ...)` | `/departure-plans/delete` | `command="COMMAND_TRAVELPLAN_DELETE"`, `planId` | Optional | `1` | Recovered |
| `control_departure_plan_validity(vehicle_id, plan_id, enabled, ...)` | `/departure-plans/validity` | `command="COMMAND_TRAVELPLAN_MODIFY_VALIDITY"`, `planId`, `enabled` | Optional | `1` | Recovered |
| `control_departure_plan_enabled(vehicle_id, plan_id, enabled, ...)` | `/departure-plans/enabled` | `command="COMMAND_TRAVELPLAN_STARTSTOPPINGPLANNOW"`, `planId`, `enabled` | Optional | `1` | Recovered |
| `control_fota_plan(vehicle_id, appointment, timestamp, ...)` | `/control/fota-plan` | `command="COMMAND_APPOINT_UPGRADE"`, `appointment`, `timestamp` | Optional | `1` | Recovered |

Flash/horn action codes: `FLASH_HONK_OFF = 0`, `FLASH_HONK_FLASH = 1`, `FLASH_HONK_BEE = 2`,
`FLASH_HONK_FLASH_BEE = 3`.

Seat commands serialize only the provided positions. Turning a seat off sends `switch: 0` without a
level, because a zero level is rejected with `COMMON_1_1_01_005`.

The optional families expose `serial_type` and `require_rc_token`; their defaults (`"1"`/`"2"` and
`False`) come from the app constants and are pending full live validation.

### 10.5 Command results

```python
raw = await client.control_result(vehicle_id, command_id)          # dict
result = await client.control_result_status(vehicle_id, command_id)  # CommandResult
```

`CommandResult` classifies `resultCode`:

| `resultCode` | `status` |
| --- | --- |
| absent, `-100` | `pending` |
| `0`, `1201` | `success` |
| `1015` | `already_done` |
| `-1`, `-2`, unknown | `failed` |

`error_message` carries `errorMsg` when present and `raw` keeps the original payload.

## 11. Errors

| Situation | Exception |
| --- | --- |
| HTTP 401/403 | `DeepalAuthError` |
| `success: false` with `AUTH*`, `401*` or an app kick-out code (`APP_1_1_02_003/004/005/006`, `CAC_1_1_01_045`, `46000`) | `DeepalAuthError` |
| Rate limit (`CAC_1_1_01_033`) or exhausted PIN attempts (`HW_1_1_01_047`) | `DeepalRateLimitError` |
| PIN expired (`HW_1_1_01_073`) or not set (`HW_1_1_01_074`) | `DeepalCommandAuthError` |
| `COMMON_1_1_01_001` on `serial-no/get`, serial decryption failure or rejected `rcToken` | `DeepalCommandAuthError` |
| Signed command without a private key or required PIN | `DeepalCommandNotReady` |
| Any other `success: false` code | `DeepalAPIError` (with `code`) |
| Non-2xx HTTP status | `DeepalAPIError` (with `status_code`) |
| Invalid JSON or unexpected payload type | `DeepalAPIError` |
| Transport failure or timeout (`httpx.RequestError`) | `DeepalConnectionError` |

The specific errors inherit from `DeepalAuthError`/`DeepalAPIError`, so existing `except` clauses
keep working. Error messages include the gateway code when one is available.

## 12. Diagnostics and redaction

`enable_api_logging=True` logs each request path, safe headers and redacted payload at `WARNING`
level, and each response status and redacted body. Redaction masks tokens, keys, VINs, emails,
phones, PINs, serial numbers and user ids, and truncates strings longer than 500 characters
(`deepal/redact.py`). Only the non-sensitive headers are logged as-is: `selectcountry`,
`appversion`, `language`, `x-os-version`, `x-tsp-timestamp`, `x-vcs-timestamp`.

The SDK also logs whether a login/refresh produced `cacToken`, `userId`, `caUserId` and
`cacUserId` (booleans only, never values).

## 13. Public method index

Authentication and session:

| Method | Summary |
| --- | --- |
| `close()` | Close the managed HTTP client |
| `request_email_code(email)` | Send an email code |
| `login_with_email_code(email, code, sales_country=None, pub_key=None)` | Email-code login |
| `login_with_email_password(email, password, sales_country=None, pub_key=None)` | Email/password login (unverified) |
| `request_sms_code(phone, country_code)` | Send an SMS code |
| `login_with_sms_code(phone, code, country_code, sales_country=None, pub_key=None)` | SMS-code login |
| `login_with_password(phone, password, country_code, sales_country=None, pub_key=None)` | Mobile/password login (unverified) |
| `refresh_tokens(force=False)` | Refresh the session tokens |
| `access_token_expires_soon(margin_seconds=300)` | JWT expiry check |
| `logout()` | Clear the session (unverified remote call) |
| `generate_login_keypair()` | Static: generate the signing keypair |
| `public_key_body_from_private(private_key_pem)` | Static: derive the `pubKey` body |
| `set_login_keypair(private_key_pem, public_key=None)` | Restore a persisted keypair |
| `encrypt_request_value(value)` | Static: RSA-encrypt a sensitive value |

Vehicles and telemetry:

| Method | Summary |
| --- | --- |
| `get_vehicles()` | List the account vehicles |
| `get_vehicle_condition(vehicle_id, vin=None)` | Full REST condition |
| `parse_condition(raw, vehicle_id, vin=None)` | Map a raw condition payload |
| `get_vehicle_capabilities(vehicle_id, vin=None)` | Function configuration or `None` |
| `is_mqtt_vehicle(vehicle)` | Static: whether the vehicle uses MQTT telemetry |
| `get_mqtt_config(vehicle_id)` | CA MQTT connection configuration |
| `get_mqtt_token()` | MQTT auth token |
| `s05_mqtt_condition(vehicle_id, vin=None)` | Live MQTT condition snapshot |
| `get_digital_key_support(vehicle_id=None)` | Phone digital key scheme or `None` |
| `get_vehicle_authorizations(car_id)` | Function codes or `None` |

Commands and results:

| Method | Summary |
| --- | --- |
| `sign_payload(payload, omit_keys=None)` | Build and sign the canonical payload |
| `get_serial_data(serial_type="1")` | Fetch the encrypted vehicle serial |
| `decrypt_serial_no(serial_data)` | Decrypt the serial with the private key |
| `get_security_code_status()` | Control PIN state (`retryQuantity`) |
| `check_control_code(control_pin)` | Exchange the PIN for an `rcToken` |
| `control_air_conditioner(...)`, `control_condition_inquiry(...)`, `control_doors(...)`, `control_windows(...)`, `control_trunk(...)`, `control_charge_limit(...)`, `control_charge_schedule(...)`, `control_flashing_honking(...)`, `control_defrost(...)`, `control_seats_heat(...)`, `control_seats_wind(...)`, `control_steering_wheel_heat(...)`, `control_charge_plan_add/delete/validity(...)`, `control_departure_plan_add/modify/delete/validity/enabled(...)`, `control_fota_plan(...)` | Signed commands, returning the `commandId` (see [Command reference](#104-command-reference)) |
| `control_result(vehicle_id, command_id)` | Raw command status |
| `control_result_status(vehicle_id, command_id)` | Classified `CommandResult` |
