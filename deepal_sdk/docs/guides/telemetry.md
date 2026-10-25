# Telemetry guide

How to list an account's vehicles, read their condition, learn what each car supports and pick the
right telemetry path. Everything here assumes a logged-in `DeepalIntlClient` (see the
[authentication guide](authentication.md)).

> Field-level mapping and unknown-value semantics live in the
> [REST telemetry section](../reference/intl-api.md#7-rest-telemetry) and the
> [models reference](../reference/models.md).

## 1. List the vehicles

```python
vehicles = await client.get_vehicles()
for vehicle in vehicles:
    print(vehicle.car_id, vehicle.series_name, vehicle.vin, vehicle.protocol_type)
```

Every `Vehicle` carries the ids used by the rest of the API (`car_id`, `vin`), the model identity
(`series_name`, `series_code`, `model_name`, `model_code`), the account nickname
(`car_name`), the plate (`license_plate`), a thumbnail URL, the backend `car_platform` and
`protocol_type`, which decides how telemetry is read (see [step 3](#3-choose-the-telemetry-path)).

### Layered model assets

The app downloads the official layered car images as a per-vehicle ZIP. The SDK exposes the
descriptor and the raw archive; extraction and rendering are the application's choice:

```python
asset = await client.get_vehicle_model(vehicle.car_id, vehicle.car_platform)
archive = await client.download_vehicle_model_archive(
    vehicle.car_id, vehicle.car_platform
)
```

The request body was confirmed against a live S05 BEV session on 2026-10-21 (`carPlatform` 2); the
archive download accepts only HTTPS, does not follow redirects and verifies the advertised MD5.
See [the API reference](../reference/intl-api.md#61-layered-model-assets) for the response shape
and the app's on-device layout.

## 2. Read a condition over REST

```python
condition = await client.get_vehicle_condition(vehicle.car_id, vin=vehicle.vin)
print(
    condition.battery.soc_percentage,
    condition.battery.remaining_range_km,
    condition.total_odometer_km,
    condition.doors.locked,
)
```

- The SDK requests the app's condition sections (seats, doors, climate, charge, lamps, windows,
  tires, vehicle status, fuel) and maps the response into `VehicleCondition`.
- A partial payload is valid: absent groups stay at their defaults (`None`, `False` or `0`), so
  check for `None` when a field matters.
- `condition.raw_data` keeps the untouched payload for diagnostics.
- To map a raw payload you already have (for example one captured from the app), use
  `client.parse_condition(raw, vehicle_id, vin=vehicle.vin)`.

Units and semantics per field are in the [models reference](../reference/models.md); the mapping
from wire names is in the [reference table](../reference/intl-api.md#7-rest-telemetry).

## 3. Choose the telemetry path

Some vehicles do not refresh their REST condition — it is a frozen snapshot. The API tells you
through `protocol_type`, and the client offers two static helpers:

```python
if DeepalIntlClient.is_mqtt_vehicle(vehicle):
    if DeepalIntlClient.is_sda_mqtt_vehicle(vehicle):
        ...  # SDA-MQTT vehicle (for example an E07)
    else:
        ...  # legacy MQTT vehicle (for example an S05)
else:
    ...  # REST vehicle
```

| `protocol_type` | Telemetry path |
| --- | --- |
| `MQTT` | Single-use MQTT exchange; see the [MQTT guide](mqtt-telemetry.md) |
| `SDA-MQTT` | SDA/VOT MQTT exchange (beta) with an SDA REST fallback; see the [MQTT guide](mqtt-telemetry.md) |
| anything else | REST condition, as in step 2 |

Sending commands works the same way for every protocol: the signed-command flow is independent of
how telemetry is read (see the [remote commands guide](remote-commands.md)).

## 4. Discover what the car supports

```python
capabilities = await client.get_vehicle_capabilities(vehicle.car_id, vin=vehicle.vin)
if capabilities is None:
    ...  # unavailable for this vehicle or region
else:
    print(capabilities.trim_hint, capabilities.has_fuel, capabilities.seats)
```

`get_vehicle_capabilities()` reads the per-vehicle function configuration the app uses to decide
which controls to offer. It is **non-fatal**: authentication failures, rate limits and unavailable
endpoints return `None` instead of raising, and the request body candidates are tried in order
because the app key was not recovered. The returned `VehicleCapabilities` exposes the raw function
codes (`raw_codes`), per-seat heating and ventilation (`seats`), `has_fuel` (derived from the
`#oilMileage` function code) and `trim_hint` (`max`, `pro` or `unknown`).

## 5. Read-only digital key checks

```python
support = await client.get_digital_key_support(vehicle.car_id)
authorizations = await client.get_vehicle_authorizations(vehicle.car_id)
```

Two non-fatal checks against the regional SDA gateway:

| Method | Returns |
| --- | --- |
| `get_digital_key_support(vehicle_id=None)` | `DigitalKeySupport` with the phone-key scheme (`ca`, `icce`, `honor` or `unknown`) |
| `get_vehicle_authorizations(car_id)` | The function codes the account may use (`DigitalKey` flags the digital key service) |

Both return `None` on any failure, never provision or download keys and never touch BLE. The
authorizations service is not deployed in every region (the European gateway answers 404).

## 6. Freshness and unknown values

- `condition.last_updated_timestamp` is the report time in Unix seconds; treat a snapshot as stale
  when it does not move.
- Comfort states are tri-state: `climate.power_on` is `None` when the report omits it, which means
  **unknown**, not off.
- Sleeping modules report sentinel values (for example seat level `6`); out-of-range comfort levels
  map to `None`, never to a made-up level. Keep the last valid value in your application until a
  good report arrives.
- Mileage and charge fields follow the same rule: a missing or invalid value is `None` (or a model
  default), not an error.

## Next steps

- [MQTT guide](mqtt-telemetry.md): read live state from MQTT-backed vehicles.
- [Remote commands guide](remote-commands.md): act on the vehicle.
- [Errors and diagnostics guide](errors-and-diagnostics.md): handle failures and log safely.
