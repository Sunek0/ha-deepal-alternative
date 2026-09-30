# MQTT telemetry reference (S05)

Deepal S05 (and other vehicles whose API reports `protocolType: MQTT`) do not refresh their state
over REST: the REST condition returns a frozen snapshot. The app keeps a foreground MQTT session
with the CA gateway, and the SDK replicates the same one-shot exchange to fetch a live condition.

> This branch covers the international `MQTT` protocol path. Other protocol types (for example the
> SDA-platform `SDA-MQTT` value) are not handled here.

## Contents

1. [Requirements](#1-requirements)
2. [Bootstrap on the CA gateway](#2-bootstrap-on-the-ca-gateway)
3. [Connection options](#3-connection-options)
4. [The exchange](#4-the-exchange)
5. [Parameter mapping](#5-parameter-mapping)
6. [Unknown and sleep semantics](#6-unknown-and-sleep-semantics)
7. [Methods](#7-methods)
8. [Limitations](#8-limitations)

## 1. Requirements

- A logged-in `DeepalIntlClient` with `user_id` (returned by the login) and a stable `device_id`.
- The vehicle's `protocol_type` must be `MQTT`; use
  `DeepalIntlClient.is_mqtt_vehicle(vehicle)` to check it.
- Network access to the environment's CA gateway and MQTT broker.

## 2. Bootstrap on the CA gateway

The CA host (`ca_base_url`, see [Environments](intl-api.md#2-environments)) serves the connection
configuration and the MQTT password. All requests are POST with the same session headers and
`authorization` as the international gateway.

| Method | Endpoint | Body | Response |
| --- | --- | --- | --- |
| `get_mqtt_config(vehicle_id)` | `/user-apigw/vot-connect-conf-center/api/device/getConnConf` | `deviceId`, `carId`, `deviceType: 1`, `confTimestamp: 0`, `deviceTimestamp` (ms) | `mqttConnectionInfos[0]` with the broker URL/port and the topic maps |
| `get_mqtt_token()` | `/user-apigw/vot-connect-auth-center/api/auth/getAuthTokenByUserId` | `userId` | `authToken`, used as the MQTT password |

Fallbacks (recovered from the 1.12.0 app; on by default):

- If `getConnConf` fails with a non-authentication, non-rate-limit API error and
  `mqtt_config_fallback=True`, the SDK retries
  `/user-apigw/vot-connect-conf-center/api/device/appGetCarConfFunc` with the same body.
- If `getAuthTokenByUserId` fails with an API error and `mqtt_token_fallback=True`, the SDK retries
  `/app-apigw/vot-auth/api/token/getAuthTokenByUserId`.

Authentication errors and rate limits are never masked by the fallbacks; both are re-raised.
`get_mqtt_token()` requires `user_id` and raises `DeepalAPIError` without it.

The `X-Tsp-User-Token`/`X-VCS-User-Token` headers must carry the **access token**; the CA gateway
rejects the CAC token with `APIGW_-1_7_01_004` and an empty header with `APIGW_1_7_02_001`
(verified against the production EU gateway on 2026-09-19).

## 3. Connection options

| Constructor option | Default | Purpose |
| --- | --- | --- |
| `mqtt_config_fallback` | `True` | Allow the connection-config fallback endpoint |
| `mqtt_token_fallback` | `True` | Allow the auth-token fallback endpoint |
| `mqtt_client_id` | `None` | Override the MQTT client id; otherwise resolved from the connection config with a fallback to the login DID |
| `mqtt_username` | `None` | Override the MQTT username; otherwise resolved from the connection config with a fallback to the login DID |
| `mqtt_keepalive` | `60` | Keepalive seconds (`PINGREQ` is sent while waiting) |
| `mqtt_clean_start` | `True` | MQTT 5.0 clean-start flag |
| `mqtt_tls_insecure` | `False` | Disables TLS certificate and hostname verification (diagnostic; logs a warning on every connection) |

TLS uses `ssl.create_default_context()` by default. The SDK speaks MQTT 5.0 (protocol level 5) with
an empty properties block, like the app's Paho client.

## 4. The exchange

`s05_mqtt_condition(vehicle_id, vin=None)` runs one connection/read/close cycle:

1. Fetch the connection config and the auth token.
2. Connect over TLS to the broker (`ssl://host`, default port `8883`) with the resolved client id
   and username and the auth token as password. A non-zero CONNACK reason code raises
   `DeepalAPIError` with the MQTT 5.0 reason description.
3. Subscribe to the configured topics; command topics (`/commands/`, `/set/`, `/client/action` and
   the app `msgType` command values) are excluded. When the config omits the login or event
   topics, they are derived from the app templates (`$vdp/<did>/client/loginout`,
   `$vdp/<did>/server/loginout`, `$vdp/<did>/<did>/server/event`).
4. Publish the `loginout` message with the `ReqPayLoad` envelope (`did`, `r`, `v`, `mt`, `e`, `z`,
   `tf`, `dt`, `sers` and `b` with the known `vin`/`sc`/`mc`/`uid`/`cid`/`ruid` identifiers).
5. The response carries a `secretKey`. Publish the `car_condition` properties request, with the
   payload AES-CBC encrypted (key = `secretKey`, IV = MD5 of the request id) over
   `base64 + gzip + JSON`.
6. Decrypt the `rs`/`sers` fields of the responses and accumulate the parameters of the
   `car_condition`, `BDC_Service`, `BMS_Service`, `OBC_Service` and `THU_Service` services.
7. Send `PINGREQ` when the keepalive expires while waiting, and `DISCONNECT` (reason code `0`)
   before closing.

The exchange returns as soon as a `/properties/get/res` message carries more than 10 parameters, or
once the accumulated partial set exceeds 30 parameters after the request, or at the timeout
(`max(timeout, 20)` seconds) with whatever was collected. The raw decrypted parameters are kept in
`VehicleCondition.mqtt_raw_data` for diagnostics; `raw_data` holds the normalized payload that
`parse_condition` maps into the shared model.

## 5. Parameter mapping

`normalize_s05_params()` translates the S05 parameter names into the international condition shape;
the tables in [REST telemetry](intl-api.md#7-rest-telemetry) then apply unchanged.

| S05 parameter | Normalized field | Model property |
| --- | --- | --- |
| `lastUpdatedTime`, `lastUpdatedAt`, `latestDate` | `lastUpdatedAt` | `last_updated_timestamp` (seconds) |
| `soc`, `socDsp`, `remainPower` | `vehicleStatus.soc` | `battery.soc_percentage` |
| `remainedPowerMile`, `totalResidualMileage` | `vehicleStatus.drvMileage` | `battery.remaining_range_km` |
| `totalOdometer` | `vehicleStatus.totalMileage` | `total_odometer_km` |
| `totalMeterYesterday` | `vehicleStatus.totalMeterYesterday` | `mileage_yesterday_km` |
| `igniteCumulativeMileage` | `vehicleStatus.igniteCumulativeMileage` | `trip_mileage_km` |
| `engineStatus` / `powerStatusFeedBack` / `electronichandbrakeStatus` | `vehicleStatus.engineSts` / `powerStatus` / `epbSts` | `engine_on` / `power_status` / `epb_status` |
| `vehicleTemperature` | `hvac.insideTemp` (x10) | `climate.inside_temperature_c` |
| `innerHumidity` | `hvac.insideHumidity` | `climate.humidity` |
| `airConditioningSetTemperature` | `hvac.remoteTemp` (x10) | `climate.target_temperature_c` |
| `airStatus` | `hvac.acStatus` | `climate.power_on` |
| `frontDefrostStatus` | `hvac.defrostStatus` | `climate.defrost_on` |
| `airPurifierStatus` | `hvac.insideAirQualityLevel` | `climate.air_quality_level` |
| `airConditioningHairRatings` | `hvac.fanLevel` | `climate.fan_level` |
| `ChrgSts` | `charge.chargeStatus` | `battery.charging_status` |
| `acChargeGunConnectionState`, `dcDhargeGunConnectionState`, `dcChargeGunConnectionState` | `charge.chargeConStatus` | `battery.charger_connected` |
| `BattACChrgInCurr` / `BattDCChrgInCurr` | `charge.acChargeCurrent` / `dcChargeCurrent` and `chargeCurrent` | `battery.ac_charge_current_a` / `dc_charge_current_a`, `charge_current_a` |
| `chargDeltMins` | `charge.remainChargeTime` (`8191` sentinel to unknown) | `battery.remaining_charge_time_min` |
| `remainingFuel` / `remainedOilMile` | `fuel.leftPercent` / `fuel.remainingRange` | `fuel.level_percent` / `fuel.remaining_range_km` |
| `driverDoor`, `passengerDoor`, `leftRearDoor`, `rightRearDoor` | `door.doors[0..3]` | `doors.*_door_open` |
| `trunk` | `door.trunk` | `doors.trunk_open` |
| `hood`, `hoodStatus` | `door.hood` | `doors.hood_open` |
| `driverDoorLock`, `passengerDoorLock` | `door.driverLock`, `door.passengerLock` | `doors.locked`, `doors.driver_locked`, `doors.passenger_locked` |
| `diverWindow`, `passengerWindow`, `leftRearWindow`, `rightRearWindow` | `window.windows[0..3]` | `windows.*_open` |
| `highBeam`, `lowBeam`, `positionLamp`, `frontFoglamp`, `rearFoglamp`, `turnLndicatorLeft`, `turnLndicatorRight` | `lamp.*` | `lamps.*` |
| `lfTyrePressure`, `rfTyrePressure`, `lrTyrePressure`, `rrTyrePressure` | `tire.*.pressure` (kPa) | `tires.*.pressure_bar` (kPa / 100) |
| `leftFrontTireTemperature`, `rightFrontTireTemperature`, `leftRearTireTemperature`, `rightRearTireTemperature` | `tire.*.temperature` | `tires.*.temperature_c` |
| `lfPressureWarning`, `rfPressureWarning`, `lrPressureWarning`, `rrPressureWarning` | `tire.*.alarm` | `tires.*.alarm` |
| `driverSeatHeatStatus` / `driverSeatAirStatus` | `seat.leftFront.heatStatus` / `ventStatus` | `seats.front_left.heating_level` / `ventilation_level` |
| `passengerSeatHeatStatus` / `passengerSeatAirStatus` | `seat.rightFront.heatStatus` / `ventStatus` | `seats.front_right.*` |
| `leftBackSeatHeatStatus` / `leftBackSeatVentilateStatus` | `seat.leftBack.heatStatus` / `ventStatus` | `seats.rear_left.*` |
| `rightBackSeatHeatStatus` / `rightBackSeatVentilateStatus` | `seat.rightBack.heatStatus` / `ventStatus` | `seats.rear_right.*` |

`steeringWheelHeating` is intentionally **not mapped**: it reads `1` even with the wheel heater
off. The real steering-wheel heater switch and level come from the REST condition
(`vehicleStatus.steeringWheelHeater` / `steeringWheelHeaterLevel`).

Every S05 parameter not listed above is currently unmapped. Debug logging of unmapped keys is
available through `logging.getLogger("deepal_sdk")` at `DEBUG` level.

## 6. Unknown and sleep semantics

Seat heating and ventilation levels are only trusted in the `0-3` range. A sleeping module reports
the sentinel `6`, and out-of-range values are mapped to `None` (unknown) instead of a level;
callers that keep state should retain the last valid level until a good report arrives. The same
applies to `climate.defrost_on`, `steering_wheel_heater_on` and `steering_wheel_heater_level`,
which are exposed as unknown when the report omits them.

## 7. Methods

| Method | Purpose |
| --- | --- |
| `is_mqtt_vehicle(vehicle)` | Static: `vehicle.protocol_type.upper() == "MQTT"` |
| `get_mqtt_config(vehicle_id)` | CA connection configuration (with fallback) |
| `get_mqtt_token()` | MQTT auth token from the account user id (with fallback) |
| `s05_mqtt_condition(vehicle_id, vin=None)` | Full single-use exchange returning a `VehicleCondition` |

Errors: a refused CONNACK, missing topics, a missing `authToken`, and timeouts/EOF/TLS failures
surface as `DeepalAPIError`; transport errors on the CA requests use the standard taxonomy
(`DeepalConnectionError`, `DeepalAuthError`, `DeepalRateLimitError`).

## 8. Limitations

- One connection/read/close cycle per call; there is no background session or reconnect. Callers
  poll at their own cadence.
- The REST condition of an MQTT vehicle is a frozen snapshot; only the MQTT exchange reflects live
  state.
- The CA gateway can reject the account (TSP/VCS headers); the call fails and the REST condition
  remains the fallback.
- The broker identity and topic layout come from the server configuration; the app templates are
  only used when the configuration omits them.
- `mqtt_tls_insecure=True` disables certificate verification and is meant for diagnostics only.
