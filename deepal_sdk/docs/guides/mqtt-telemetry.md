# MQTT telemetry guide

How to read live state from vehicles that report over MQTT, which client values are required and
which options matter. The protocol-level tables (endpoints, connection options, parameter mapping)
stay in the [MQTT telemetry reference](../reference/mqtt-telemetry.md).

## 1. Check whether the vehicle needs it

```python
if DeepalIntlClient.is_mqtt_vehicle(vehicle):
    ...  # read over MQTT instead of REST
```

- `protocol_type == "MQTT"` (for example the S05): the REST condition is a frozen snapshot; only
  the MQTT exchange reflects live state.
- `protocol_type == "SDA-MQTT"` (for example the E07): same broker, but the condition is read
  through the SDA/VOT services (beta).
- Anything else: use `get_vehicle_condition()` as described in the
  [telemetry guide](telemetry.md).

## 2. Read a legacy MQTT condition

One call performs the whole bootstrap/connect/read/close cycle:

```python
condition = await client.s05_mqtt_condition(vehicle.car_id, vin=vehicle.vin)
print(condition.battery.soc_percentage, condition.doors.locked)
```

Under the hood the SDK fetches the CA connection configuration and the account MQTT token,
connects over TLS, publishes the `loginout` exchange, requests the `car_condition` properties,
decrypts the response and maps the parameters into the same `VehicleCondition` model used by REST.

Requirements: a logged-in client (`user_id`) and a stable `device_id` — both already handled by the
[authentication guide](authentication.md).

## 3. Read an SDA-MQTT condition (beta)

```python
if DeepalIntlClient.is_sda_mqtt_vehicle(vehicle):
    try:
        condition = await client.s05_mqtt_condition(
            vehicle.car_id, vin=vehicle.vin, sda=True
        )
    except DeepalAPIError:
        condition = await client.get_sda_vehicle_condition(
            vehicle.car_id, vin=vehicle.vin
        )
```

- `sda=True` selects the SDA `Get_CarCondition` service; the SDK probes the function-tree device
  and signal codes within `mqtt_sda_probe_grace` seconds and falls back to the legacy request.
- `get_sda_vehicle_condition()` reads the flat SDA REST condition on the SDA gateway as a
  fallback when the broker path is unavailable.
- For read-only diagnostics, `open_sda_session(...)` connects and subscribes without ever
  publishing a control command.

This path is **beta**: recovered from the app and verified read-only against a live vehicle, but
SDA command publishing is not implemented yet. Details and endpoints are in the
[SDA-MQTT section of the reference](../reference/mqtt-telemetry.md#8-sda-mqtt-telemetry-and-wake-beta).

## 4. Wake a sleeping vehicle

```python
await client.wake_vehicle(vehicle.car_id)
condition = await client.s05_mqtt_condition(vehicle.car_id, vin=vehicle.vin)
```

`wake_vehicle()` publishes the app's wake service over MQTT and returns once the gateway
acknowledges it; the car then reports fresh data within a few seconds. The wait is bounded by
`mqtt_wake_timeout` (default `max(timeout, 20)` seconds).

## 5. Options that matter

| Constructor option | Default | When to touch it |
| --- | --- | --- |
| `mqtt_keepalive` | `60` | Broker drops long idle waits; the SDK sends `PINGREQ` while waiting |
| `mqtt_clean_start` | `True` | MQTT 5.0 clean-start flag, like the app |
| `mqtt_config_fallback`, `mqtt_token_fallback` | `True` | Allow the recovered fallback endpoints when the primary CA route fails |
| `mqtt_exchange_timeout` | `max(timeout, 20)` | Slow vehicles that need a longer read window |
| `mqtt_token_ttl` | `60.0` | Reuse window of the account MQTT token across several vehicles |
| `mqtt_tls_insecure` | `False` | **Diagnostics only**: disables certificate verification and logs a warning |
| `mqtt_client_id`, `mqtt_username` | `None` | Override the broker identity resolved from the connection config |

Authentication errors and rate limits are never masked by the fallbacks.

## 6. Reading the result

- The returned `VehicleCondition` is the same model as the REST path, so downstream code does not
  branch on the protocol.
- `condition.condition_source` tells you which service produced the snapshot (`sda-mqtt`,
  `sda-mqtt-signal-list`, `legacy-mqtt` or `rest`).
- `condition.mqtt_raw_data` keeps the decrypted parameters, `mqtt_variants` every variant
  attempted and `sda_plan` the derived SDA plan; all three are diagnostics-only.
- Sleeping modules report sentinel values: out-of-range comfort levels (for example seat level `6`)
  map to `None` (unknown). Retain the last valid value in your application.

## 7. Limitations

- One connection/read/close cycle per call: there is no background session or automatic reconnect.
  Poll at your own cadence.
- The broker identity and topics come from the server configuration; the app templates are only a
  fallback.
- The CA gateway can reject the account; the call fails and the REST condition remains available.
- The SDA-MQTT path is beta (see step 3).

## Next steps

- [MQTT telemetry reference](../reference/mqtt-telemetry.md): endpoints, options and the full
  parameter mapping.
- [Errors and diagnostics guide](errors-and-diagnostics.md): how MQTT failures surface.
