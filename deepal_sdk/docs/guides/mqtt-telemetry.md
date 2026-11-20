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
[SDA-MQTT section of the reference](../reference/mqtt-telemetry.md#9-sda-mqtt-telemetry-and-wake-beta).

## 4. Keep a live session

The one-shot call above is fine for a single snapshot. For live updates, open a supervised session
and let it dispatch the car's unsolicited reports:

```python
def on_condition(vehicle_id: str, condition):
    print(vehicle_id, condition.battery.soc_percentage, condition.doors.locked)

def on_state(state: str, details: dict):
    print("live MQTT:", state, details)

session = client.create_mqtt_session(
    [vehicle],
    on_condition=on_condition,
    on_state=on_state,
)
await session.start()
try:
    ...
finally:
    await session.stop()
```

The callbacks are synchronous and run in the event loop: do not declare them `async def` and keep
them short (hand work off to a queue if it blocks). Always `stop()` the session before closing the
client; the `finally` block above is required, not optional.

- The session keeps one connection per broker identity, subscribes to the configured topics, logs
  in once and reconnects with exponential backoff. If the broker accepts and immediately closes
  several short connections in a row, the session enters a long `conflict` backoff instead of
  retrying in a tight loop; `on_state` reports it.
- It accumulates full snapshots and partial deltas per vehicle before parsing, so a two-field
  window report does not reset the rest of the condition.
- `request_condition()`, `wake()` and `wait_for_report()` use the open session. The one-shot methods
  remain available as the fallback.
- `session.stats()` exposes the state, connection/reconnect counters, received messages and last
  error for diagnostics.
- The session is read-only: it publishes the login, logout, condition requests, wake requests and
  protocol acknowledgements only.

## 5. Wake a sleeping vehicle

```python
await client.wake_vehicle(vehicle.car_id)
condition = await client.s05_mqtt_condition(vehicle.car_id, vin=vehicle.vin)
```

`wake_vehicle()` publishes the app's wake service over MQTT at **QoS 1** and returns once the
gateway acknowledges it; the car then reports fresh data within a few seconds. The wake ignores the
cluster's telemetry `qos` so the broker can queue it for a sleeping vehicle; only a CONNACK
`maximum_qos` of 0 downgrades it. The wait is bounded by `mqtt_wake_timeout` (default
`max(timeout, 20)` seconds).

## 6. Options that matter

| Constructor option | Default | When to touch it |
| --- | --- | --- |
| `mqtt_keepalive` | `None` (effective 50) | Explicit override; when left unset the cluster `heartTimeInterval` governs the session and the SDK sends `PINGREQ` while waiting |
| `mqtt_clean_start` | `True` | MQTT 5.0 clean-start flag, like the app |
| `mqtt_exchange_timeout` | `max(timeout, 20)` | Slow vehicles that need a longer read window |
| `mqtt_token_ttl` | `60.0` | Reuse window of the account MQTT token across several vehicles |
| `mqtt_tls_insecure` | `False` | **Diagnostics only**: disables certificate verification and logs a warning. The TLS context is cached per client and rebuilt only when this changes |
| `mqtt_client_id`, `mqtt_username` | `None` | Override the broker identity resolved from the connection config |

The broker settings come from the connection config's `clusterInfos[0]`: `qos` (0/1),
`timeOutInterval` (TCP/TLS connect bound) and `heartTimeInterval` (keepalive). A CONNACK
`server_keep_alive`/`maximum_qos` overrides or caps them. An authentication rejection (`0x86`,
`0x87` or `0x8C`) drops the cached token and configuration and retries the exchange once; other
CONNACK failures are not retried. `getConnConf` has no fallback endpoint: a failure propagates with
its gateway code, and the coordinator refreshes the session and retries. A completed exchange
publishes a `logout` before `DISCONNECT`; a logout failure never prevents the socket from closing.

## 7. Reading the result

- The returned `VehicleCondition` is the same model as the REST path, so downstream code does not
  branch on the protocol.
- `condition.condition_source` tells you which service produced the snapshot (`sda-mqtt`,
  `sda-mqtt-signal-list`, `legacy-mqtt`, `mqtt-push` or `rest`). `mqtt-push` is only used for an
  unsolicited live-session report; a matching response to a direct condition request on the live
  session reports `legacy-mqtt` (an unsolicited report that satisfies a wait still reports
  `mqtt-push`).
- `condition.mqtt_raw_data` keeps the decrypted parameters, `mqtt_variants` every variant
  attempted and `sda_plan` the derived SDA plan; all three are diagnostics-only.
- Sleeping modules report the sentinel `6` for seat levels; it maps to `0` (off), matching the
  app. Other out-of-range comfort values map to `None` (unknown); retain the last valid value in
  your application.

## 8. Limitations

- The one-shot API keeps one connection/read/close cycle per call. Use the live session when you
  need unsolicited reports and automatic reconnect; use the one-shot call for a single snapshot or
  as a fallback.
- The broker identity and topics come from the server configuration; the app templates are only a
  fallback.
- The CA gateway can reject the account; the call fails and the REST condition remains available.
- The SDA-MQTT path is beta (see step 3).

## Next steps

- [MQTT telemetry reference](../reference/mqtt-telemetry.md): endpoints, options and the full
  parameter mapping.
- [Errors and diagnostics guide](errors-and-diagnostics.md): how MQTT failures surface.
