# Data models reference

The SDK exposes its data as **Pydantic v2** models with snake_case fields; raw API payloads are
parsed into these models and never returned directly (except where a method documents a `dict`
result). Unknown fields in a response are ignored, and absent fields keep their documented default,
so a partial payload is always a valid model.

All models listed here are importable from the `deepal` package and from `deepal.models`.

## Contents

1. [Authentication](#1-authentication)
2. [Vehicles and capabilities](#2-vehicles-and-capabilities)
3. [Telemetry](#3-telemetry)
4. [Commands](#4-commands)
5. [Digital key](#5-digital-key)
6. [Module constants](#6-module-constants)

## 1. Authentication

### `AuthToken`

Result of a successful login or refresh.

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `access_token` | `str` | required | API bearer token |
| `token_type` | `str` | `"Bearer"` | Token type |
| `expires_in` | `int?` | `None` | Lifetime in seconds when the API reports it |
| `refresh_token` | `str?` | `None` | Refresh token |
| `cac_token` | `str?` | `None` | CAC/TSP token of the international session |
| `ca_user_id` | `str?` | `None` | International CA user id |
| `cac_user_id` | `str?` | `None` | International CAC user id |
| `user_id` | `str?` | `None` | Account user id |

### `UserProfile`

Account profile placeholder (`user_id`, `phone`, `nickname`, `avatar_url`). The current client flows
do not return it; it is exported for applications that persist account metadata.

## 2. Vehicles and capabilities

### `Vehicle`

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `car_id` | `str` | required | Unique vehicle id used by every call |
| `vin` | `str` | required | Vehicle identification number |
| `series_name` | `str?` | `"Deepal S05"` | Series/model name |
| `series_code` | `str?` | `None` | Series code (for example `CD701`) |
| `model_name` | `str?` | `None` | Model name |
| `model_code` | `str?` | `None` | Model code |
| `car_name` | `str?` | `None` | Custom nickname |
| `license_plate` | `str?` | `None` | Plate |
| `thumbnail_url` | `str?` | `None` | Vehicle image URL |
| `protocol_type` | `str?` | `None` | Backend telemetry protocol; `MQTT` marks MQTT-backed vehicles |

### `SeatCapabilities` and `VehicleCapabilities`

`SeatCapabilities` holds `heating` and `ventilation` booleans for one seat position.

`VehicleCapabilities` is built from the per-vehicle function configuration:

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `raw_codes` | `list[str]` | `[]` | Raw function codes |
| `seats` | `dict[str, SeatCapabilities]` | `{}` | Capabilities per position (`front_left`, `front_right`, `rear_left`, `rear_right`) |
| `has_fuel` | `bool` | `False` | The vehicle declares the `#oilMileage` code (PHEV / range extender) |
| `trim_hint` | `"max" \| "pro" \| "unknown"` | `"unknown"` | S05 trim derived from front-seat ventilation |

`VehicleCapabilities.from_codes(codes)` performs the derivation.

## 3. Telemetry

### `VehicleCondition`

Full telemetry snapshot shared by the REST and MQTT paths.

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `car_id` | `str` | required | Vehicle id |
| `vin` | `str` | `""` | VIN |
| `total_odometer_km` | `float?` | `None` | Total odometer (km) |
| `mileage_yesterday_km` | `float?` | `None` | Mileage yesterday (km) |
| `trip_mileage_km` | `float?` | `None` | Mileage since the current ignition cycle (km) |
| `speed_kmh` | `float?` | `None` | Speed (km/h) |
| `gear` | `str?` | `None` | Raw gear signal |
| `epb_status` | `int?` | `None` | Raw electronic parking brake status |
| `power_status` | `int?` | `None` | Raw power status |
| `vehicle_status` | `int?` | `None` | Raw vehicle status |
| `engine_on` | `bool` | `False` | Drivetrain running |
| `connected` | `bool?` | `None` | Cloud connection (`None` when not reported) |
| `battery` | `BatteryCondition` | empty | Battery and charging |
| `fuel` | `FuelCondition` | empty | Fuel (PHEV / range extender) |
| `doors` | `DoorsCondition` | empty | Doors, trunk and hood |
| `windows` | `WindowsCondition` | empty | Window positions |
| `seats` | `SeatsCondition` | empty | Seat comfort levels |
| `climate` | `ClimateCondition` | empty | Climate and air quality |
| `tires` | `TiresCondition` | empty | Tire pressure and temperature |
| `lamps` | `LampsCondition` | empty | Exterior lamps |
| `last_updated_timestamp` | `int?` | `None` | Report time, Unix seconds |
| `raw_data` | `dict?` | `None` | Normalized payload for diagnostics |
| `mqtt_raw_data` | `dict?` | `None` | Original decrypted S05 MQTT parameters |

### `BatteryCondition`

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `soc_percentage` | `int?` (0-100) | `None` | State of charge (%) |
| `remaining_range_km` | `int?` | `None` | Estimated range (km) |
| `charging_status` | `str?` | `None` | Raw charging/discharging state |
| `charger_connected` | `bool` | `False` | Charging cable plugged in |
| `dc_gun_connected` | `bool` | `False` | DC charging gun connected |
| `charge_current_a` | `float?` | `None` | Charging current (A) |
| `ac_charge_current_a` | `float?` | `None` | AC charging current (A) |
| `dc_charge_current_a` | `float?` | `None` | DC charging current (A) |
| `remaining_charge_time_min` | `int?` | `None` | Remaining charge time (min); the `8191` sentinel becomes `None` |
| `charge_limit_percent` | `int?` (0-100) | `None` | Charge limit (%) |
| `charge_schedule_enabled` | `bool` | `False` | Both schedule switches are on |
| `charge_schedule_start` / `charge_schedule_end` | `str?` | `None` | Schedule window |
| `charge_plan_id` / `charge_plan_type` / `charge_plan_time_format` / `charge_plan_time_zone` | `str?` / `int?` / `int?` / `str?` | `None` | Raw plan metadata |

### `FuelCondition`

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `level_percent` | `int?` | `None` | Fuel level (%) |
| `volume_l` | `float?` | `None` | Fuel volume (L) |
| `tank_capacity_l` | `float?` | `None` | Tank capacity (L) |
| `remaining_range_km` | `int?` | `None` | Fuel range (km) |
| `temperature_c` | `float?` | `None` | Fuel temperature (C) |

A BEV reports no fuel block and every field stays `None`.

### `DoorsCondition`

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `locked` | `bool` | `True` | Doors locked (driver lock preferred, else passenger, else `True`) |
| `driver_locked` / `passenger_locked` | `bool?` | `None` | Individual lock states when reported |
| `driver_door_open`, `passenger_door_open`, `rear_left_door_open`, `rear_right_door_open` | `bool` | `False` | Open doors |
| `trunk_open` / `hood_open` | `bool` | `False` | Boot / hood |

### `WindowsCondition`

`front_left_open`, `front_right_open`, `rear_left_open`, `rear_right_open` (all `bool`, default
`False`).

### `SeatStatus` and `SeatsCondition`

`SeatStatus` holds `heating_level` and `ventilation_level`, both `int?` in the `0-3` range; `None`
means unknown (missing or out-of-range, including the sleep sentinel `6`). `SeatsCondition` has the
four positions `front_left`, `front_right`, `rear_left`, `rear_right`.

### `ClimateCondition`

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `power_on` | `bool?` | `None` | AC state; `None` when not reported (unknown, not off) |
| `target_temperature_c` | `float?` | `None` | Target temperature (C) |
| `inside_temperature_c` / `outside_temperature_c` | `float?` | `None` | Cabin / outside temperature (C) |
| `humidity` | `float?` | `None` | Cabin humidity |
| `inside_pm25` | `float?` | `None` | PM2.5 |
| `air_quality_level` | `int?` | `None` | Air quality level |
| `defrost_on` | `bool?` | `None` | Front defrost; `None` when not reported |
| `fan_level` | `int?` | `None` | Fan level |
| `steering_wheel_heater_on` | `bool?` | `None` | Steering wheel heater; `None` when not reported |
| `steering_wheel_heater_level` | `int?` | `None` | Heater level |
| `driver_seat_ventilation_level` / `driver_seat_heating_level` | `int` | `0` | Legacy driver-seat levels, retained for compatibility; seat data lives in `SeatsCondition` |

### `TireStatus` and `TiresCondition`

`TireStatus` holds `pressure_bar` (`float?`, converted from kPa), `temperature_c` (`float?`) and
`alarm` (`bool`, default `False`). `TiresCondition` has the four positions `front_left`,
`front_right`, `rear_left`, `rear_right`.

### `LampsCondition`

`high_beam`, `low_beam`, `position_lamp`, `front_fog`, `rear_fog`, `left_turn`, `right_turn` (all
`bool`, default `False`).

## 4. Commands

### `CommandResultStatus`

String enum: `pending`, `success`, `already_done`, `failed`.

### `CommandResult`

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `code` | `int?` | `None` | Raw `resultCode` when parsable |
| `status` | `CommandResultStatus` | required | Normalized status |
| `error_message` | `str?` | `None` | Gateway `errorMsg` |
| `raw` | `dict` | `{}` | Original payload |

`CommandResult.from_payload(payload)` classifies `-100`/absent as `pending`, `0`/`1201` as
`success`, `1015` as `already_done` and `-1`/`-2`/unknown as `failed`.

## 5. Digital key

### `DigitalKeySupport`

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `flag` | `int` | required | Raw flag from `query-supported-featured` |
| `key_type` | `DigitalKeyKeyType` (`"ca" \| "icce" \| "honor" \| "unknown"`) | required | Key scheme the phone should use |
| `raw` | `dict` | `{}` | Raw payload |

`supported` is `True` when `key_type != "unknown"`. `from_flag(flag)` maps `0` to `ca`, `1` to
`icce` and `2` to `honor`.

### `VehicleAuthorizations`

| Field | Type | Default | Description |
| --- | --- | --- | --- |
| `raw_codes` | `list[str]` | `[]` | Function codes authorized for the account |
| `digital_key` | `bool` | `False` | The `DigitalKey` code is present |
| `raw` | `dict` | `{}` | Raw payload |

`has_code(code)` checks the list; `from_payload(payload)` tolerates the candidate payload shapes
because the service contract is inferred (it is not deployed in every region).

## 6. Module constants

| Constant | Value | Purpose |
| --- | --- | --- |
| `S05_TRIM_MAX` / `S05_TRIM_PRO` / `S05_TRIM_UNKNOWN` | `"max"` / `"pro"` / `"unknown"` | Capability trim hints |
| `SEAT_HEAT_FUNCTION_CODES` | position to function code | Seat heating capabilities |
| `SEAT_VENT_FUNCTION_CODES` | position to function code | Seat ventilation capabilities |
| `DIGITAL_KEY_FUNCTION_CODE` | `"DigitalKey"` | Digital key authorization code |
| `PHONE_SUPPORT_CA_KEY` / `PHONE_SUPPORT_ICCE_KEY` / `PHONE_SUPPORT_HONOR_KEY` | `0` / `1` / `2` | Digital key `flag` values |
