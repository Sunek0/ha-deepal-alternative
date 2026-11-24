# Changelog

All notable changes to Deepal Alternative are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## 1.9.1-b1 - 2026-11-24

### Fixed

- **The card's settings sheet can be closed on phones.** On narrow screens the sheet is full
  screen: the close button now stays below the device safe areas, the scrollable body clears the
  home indicator and the sheet uses the dynamic viewport height. The close control has a 44 px
  target and the panel is announced as a dialog. Escape, a tap outside the panel and the close
  button all dismiss it through the same path that saves pending changes; focus returns to the
  settings button.

### Upgrade

- Update through HACS and restart Home Assistant. No entity ids change. Reload the dashboard (or
  reopen the Companion app) to load the new card bundle.

## 1.9.0 - 2026-11-22

### Added

- **Live MQTT telemetry for the S05 family.** One supervised connection receives the car's
  unsolicited reports within seconds, merges the partial deltas and publishes them to Home
  Assistant; the periodic poll remains the fallback and keeps refreshing the REST-only fields. The
  session is enabled by default and can be disabled in the options.
- **Charge-schedule control.** A switch and start/end time entities for the S05 BEV and PHEV, a
  read-only "Charge schedule enabled" binary sensor, the `deepal.set_charge_schedule` service and a
  **Charge schedule to full** switch on the S05 PHEV for the plan the app stores as a start with no
  end time. The PHEV switches expose `set_by` (`app_or_car`, `home_assistant` or `none`) and
  `controllable`, so a dashboard can disable its controls for a plan Home Assistant cannot change.
- **Absolute and relative cabin humidity.** `absolute_humidity` exposes the g/m³ value the car
  reports, and `cabin_humidity` now derives the relative percentage from it instead of showing the
  raw absolute reading.
- Tester tools: `tools/deepal-cn-probe/` renders a China `car/data` payload, including the offline
  `--payload-file` mode, and `tools/mqtt-live-probe/` validates topics, identity, latency and
  coexistence with the phone app.

### Changed

- The S05 PHEV charge schedule replaces the plan instead of editing it: `add-plan` enables it and
  applies time edits and full charge, `delete-plan` disables it. The car rejects `modify-plan` and
  the plan on/off command for the plan the app and the car follow.
- An S05 plan whose end is less than 30 minutes after its start is rejected before the command, as
  the app does, including windows that cross midnight.
- Dashboard warning lights wait for a settled 60-second ready window before reporting a fault, and a
  confirmed fault is hidden while the car is off or asleep. Healthy values keep their last known
  state.
- The 10-minute charging read requests the telemetry on the open MQTT connection instead of waking
  the vehicle; the REST-only charge plan keeps refreshing through the app-condition overlay.
- The SDA (China) client uses the production gateway, the `/app-apigw` prefix and the
  `X-VCS-User-Token` header; SDA entries expose the charging sessions and start the charge read loop
  as soon as a session is detected.

### Fixed

- The S05 PHEV switch no longer stays on after the app switched the plan off, no longer shows the
  times of a plan the car does not follow and no longer needs a second press: plan fields are held
  for 30 seconds so a push or an old REST read cannot revert them.
- Switching the PHEV schedule off no longer fails with `HW_1_1_01_001` for a plan saved in the app
  or on the car: the integration explains where to switch it off, and only reports the schedule as
  off once the plan list confirms it.
- The S05 no longer reports the dashboard self-check as a fault when it wakes: the live session
  drops the light bits of a report that predates the ready state, removing the false brake, airbag,
  ABS and power-steering warnings.
- The module-initialisation values the car publishes when it wakes no longer reach Home Assistant:
  a `0.0 bar` tire pressure is held for 60 seconds, an impossible cabin target is ignored, a
  `0 min` remaining charge time without an active charge is unknown and the `-400 A` DC sentinel is
  dropped.
- SDA condition polls complete their first refresh; expired or missing SDA tokens (`46000`/`40005`)
  start reauthentication, a transport error during the token refresh is an update failure and
  impossible readings such as the `255` SOC sentinel become unknown.
- The vehicle image stays available and keeps serving the cached or bundled image across failed
  polls.
- The S05 scheduled charge state follows the car's `ChrgSts` values instead of the previous
  heuristic.

### Removed

- **The "Log API traffic" option.** The full diagnostics capture replaces it: it records every REST
  request/response and MQTT exchange, survives reloads and can be downloaded. Entries that stored
  the option stop writing those log lines, and the stale key is dropped the next time the options
  are saved. The SDK-level `enable_api_logging` flag is unchanged.
- `sensor.mileage_yesterday` and `sensor.trip_mileage`, which no source reports, and the S05 PHEV
  fuel tank capacity sensor, which is always unknown. Their entity-registry entries are removed on
  setup.

### Upgrade

- **Home Assistant 2026.11.0 or newer is required.** Update through HACS and restart Home
  Assistant.
- New entities: `absolute_humidity`, the S05 BEV charge-schedule entities and, on the S05 PHEV,
  `switch.<car>_charge_schedule_to_full`. Removed: the two mileage sensors and the S05 PHEV tank
  capacity sensor. The other entity ids and unique ids do not change.
- `cabin_humidity` keeps its entity id but now shows the derived relative percentage.
- The live MQTT session is enabled by default; disable **Keep a live MQTT connection** in the
  options to fall back to polling.
- SDA entries now validate against the production gateway. If a stored token is expired, use the
  reauthentication flow to paste a fresh one.

## 1.9.0-b8 - 2026-11-22

### Added

- **"Charge schedule to full" switch (S05 PHEV).** The app and the car store a "continue to full
  charge" plan as a start with no end time, and the end time entity cannot be cleared, so the new
  switch is the way to set it from Home Assistant. Turning it off gives the plan an end time again
  (08:00, or the end time entity).
- The S05 PHEV schedule switches expose `set_by` (`app_or_car`, `home_assistant` or `none`) and
  `controllable`, so a dashboard can disable its controls for a plan Home Assistant cannot change.

### Changed

- The S05 PHEV charge schedule replaces the plan instead of editing it: `add-plan` to enable, on a
  time edit and for full charge, `delete-plan` to disable. The car rejects `modify-plan` and the
  plan on/off command for the plan the app and the car follow, so that path never worked.
- The S05 PHEV parser follows the first `chargePlanList` entry, on or off, and treats a missing end
  time as unknown (full charge) instead of reusing another entry's end. Other models keep the
  first valid plan.
- An S05 plan whose end is less than 30 minutes after its start is rejected before the command, as
  the app does, including windows that cross midnight. A plan without an end time is exempt.
- Dashboard warning lights are only published as a fault once the car has been ready for 60 seconds,
  and a confirmed fault stops being shown while the car is off or asleep. Healthy values keep their
  last known state.

### Fixed

- The S05 PHEV switch no longer stays on after the app switched the plan off, no longer shows the
  times of a plan the car does not follow, and no longer needs a second press: plan fields are
  held for 30 seconds so a push or an old REST read cannot revert them.
- Switching the schedule off no longer fails with `HW_1_1_01_001` for a plan saved in the app or on
  the car: the integration explains where to switch it off instead of sending a command the car
  rejects, and only reports the schedule as off once the plan list confirms it.
- Older plans Home Assistant added are removed only after the car lists the new one, and a delete
  the car no longer lists is skipped instead of retried.
- The S05 no longer reports the dashboard self-check as a fault when it wakes: the live session
  drops the light bits of a report that predates the ready state, and every warning light waits for
  the settled ready window. This removes the false brake warning seen for a few seconds after a
  wake or a command, and closes the same window for the other dashboard lights.

### Upgrade

- Update through HACS and restart Home Assistant. The new `switch.<car>_charge_schedule_to_full`
  appears on S05 PHEV vehicles only; the existing schedule switch and time entities keep their ids.
  A PHEV schedule may need one action in the app or on the car if it was set there.
- A warning light can take up to 60 seconds to appear after the car starts, and a confirmed fault no
  longer stays on while the car sleeps. No entity ids change.

## 1.9.0-b7 - 2026-11-21

### Added

- **Absolute and relative cabin humidity.** The car reports `innerHumidity` as an absolute humidity
  in g/m³, not a percentage. The integration now creates an `absolute_humidity` sensor in g/m³ and
  derives the relative percentage from the cabin temperature, so `cabin_humidity` keeps its entity
  id and `%` unit but shows the real value (for example ~46 % where it used to show 11.1).

### Changed

- The 10-minute charging read no longer wakes an MQTT vehicle: the live session already streams the
  charge telemetry, so the read requests it on the open connection and the REST-only charge plan
  keeps refreshing through the app-condition overlay.
- The power status sensor accepts the `3` transition the car reports for about 0.1 s during a power
  cycle as `on`.

### Fixed

- The module-initialisation values the car publishes when it wakes no longer reach Home Assistant:
  a `0.0 bar` tire pressure is held for 60 seconds (and published if it persists, so a real puncture
  is still visible), an impossible cabin target temperature is ignored, a `0 min` remaining charge
  time without an active charge is unknown, and the `-400 A` DC current sentinel is dropped.

### Removed

- `sensor.mileage_yesterday` and `sensor.trip_mileage`: neither the MQTT reports nor the European
  REST condition carry `totalMeterYesterday`/`igniteCumulativeMileage`, so the entities were
  permanently unknown. Their entity-registry entries are removed on setup.

### Upgrade

- Update through HACS and restart Home Assistant. The two mileage entities disappear,
  `cabin_humidity` changes from the raw absolute reading to the derived percentage and the new
  `absolute_humidity` entity appears. The other entity ids and unique ids do not change.

## 1.9.0-b6 - 2026-11-21

### Fixed

- The S05 PHEV no longer creates the fuel tank capacity sensor, which was always unknown because
  the car reports fuel level, range and litres left but never a tank capacity. The entity-registry
  entry is removed on setup; other fuel vehicles keep the sensor. Contributed by @rmxs.

## 1.9.0-b5 - 2026-11-21

### Added

- `--payload-file` mode in `tools/deepal-cn-probe/`: render a captured `car/data` payload from
  disk, with the same redacted summary and `--raw` output, without a token or a network request.
  The file can be the full gateway envelope or the bare data object.

### Upgrade

- No integration behaviour changes; this beta only updates the tester tool. HACS users can stay on
  `1.9.0-b4` unless they want the tool update.

## 1.9.0-b4 - 2026-11-20

### Added

- Live MQTT telemetry for international MQTT entries (S05 family): one supervised connection
  receives the vehicle's unsolicited reports in seconds, accumulates partial deltas and publishes
  them to Home Assistant with burst coalescing. The live session is enabled by default and can be
  disabled in the options; the one-shot exchange remains the fallback. REST-only fields (charge
  plan, seats while asleep, steering wheel, defrost and static fuel values) keep refreshing with the
  periodic scan.
- A read-only MQTT live probe under `tools/mqtt-live-probe/` to validate topics, identity,
  coexistence with the phone app and message latency.

### Fixed

- The S05 airbag, ABS and power-steering warning lights no longer report a false `Problem` after a
  wake or a Home Assistant restart. A non-zero REST subsystem register is only trusted after a
  settled ready window and a fresh app report; healthy last values survive sleep and restart, but an
  unconfirmed fault is not revived. Live pushes and command confirmations go through the same rule,
  and a confirmed fault is kept when a push wins the poll.
- A REST-only S05, or an MQTT vehicle that falls back to REST, follows the same warning rule.

## 1.9.0-b3 - 2026-11-19

### Changed

- The S05 PHEV charge schedule follows the reported plan id: a plan is updated with
  `modify-plan` and falls back to `add-plan` when the car rejects it, while a car without a plan
  creates one with `add-plan`. Disabling uses the plan on/off command (`/charge/validity`) and
  deletes the plan when the command fails.
- The plan-command fallback is applied after any plan-command failure, not only after the
  `HW_1_1_01_001` rejection, and the service response no longer includes the `noop` strategy.

## 1.9.0-b2 - 2026-11-19

### Fixed

- The S05 PHEV charge schedule works when the car only reports the placeholder plan (a
  `planId` without an end time or end switch): the reservation is created with
  `/charge/add-plan` instead of a `modify-plan` the car rejects with `HW_1_1_01_001`.
- The charge schedule switch uses the plan on/off command (`/charge/validity`) to enable and
  disable the PHEV reservation, so turning it off no longer rewrites the plan. A rejected
  disable deletes the plan and never creates a new one; if the delete also fails, the service
  reports one translated error.
- A rejected `modify-plan` falls back to `/charge/add-plan` when enabling and to
  `/charge/delete-plan` when disabling. Authentication, rate-limit and transport errors are
  still reported instead of retried, and the service response names the command that ran
  (`plan-validity`, `modify-plan`, `add-plan`, `delete-plan` or `noop`).

## 1.9.0-b1 - 2026-11-19

### Added

- `deepal.set_charge_schedule` service for the S05 BEV and PHEV, with the model-aware
  `add-plan`/`delete-plan` (BEV) and `modify-plan` (PHEV) paths.
- Charge schedule switch and start/end time entities for the S05 BEV, plus the read-only
  "Charge schedule enabled" binary sensor, driven by the active plan (`isValid`).
- `tools/deepal-cn-probe/`, a read-only tester probe for the China Deepal app
  `app2/api/car/data` endpoint. It prints a redacted telemetry summary and never logs in,
  requests an SMS or sends commands.

### Changed

- The SDA (China) client now uses the production gateway, the `/app-apigw` prefix and the
  `X-VCS-User-Token` header; the login requests are form-encoded on `v3`.
- SDA entries expose the charging session entities and start the charge read loop as soon as
  a session is detected.
- The location option is offered only to international entries; leftover SDA
  `device_tracker` entities are removed during setup.
- A rejected CA MQTT bootstrap triggers at most one token refresh per hour; skipped attempts
  stay on the REST condition.

### Fixed

- SDA condition polls no longer pass the international-only `model_code` argument, so SDA
  entries complete their first refresh.
- Expired or missing SDA tokens (`46000`/`40005`) raise an auth error, so Home Assistant
  starts reauthentication instead of reporting a connection failure.
- A transport error while refreshing the session is reported as an update failure, not as a
  rejected session.
- The vehicle image stays available and keeps serving the cached or bundled image across
  failed polls.
- The S05 scheduled charge state follows the car's `ChrgSts` values instead of the previous
  heuristic.
- SDA telemetry parsing sanitizes impossible readings (for example the `255` SOC sentinel)
  and tolerates unusable `data` payloads instead of aborting the poll.

### Upgrade

- Update through HACS and restart Home Assistant. Entity IDs and unique IDs do not change.
- SDA entries now validate against the production gateway. If a stored token is expired, use
  the reauthentication flow to paste a fresh one.
- The SMS login for SDA remains captcha-gated; a pasted access token is the supported path.

## 1.8.1 - 2026-11-17

### Fixed

- The S05 power-steering, ABS and airbag warning lights keep their last value while the car
  sleeps, update on the next ready report and survive a Home Assistant restart, without using
  the unreliable MQTT bits.

## 1.8.0 - 2026-11-14

### Added

- One vehicle dialog with Climate, Seats and Tyres tabs, and the seats/steering-wheel map.
- Single status block with the `info_order` setting.
- Vehicle condition preserved across Home Assistant restarts.
- S05 warning lights from the REST subsystem registers.

### Changed

- S05 BEV no longer creates the charge-schedule entities; the PHEV keeps them.
- The PHEV rejects charge-current readings above 250 A.
- The one-shot MQTT exchange uses the broker cluster's QoS, timeouts and keepalive.
