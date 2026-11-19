# Changelog

All notable changes to Deepal Alternative are documented here. The format follows
[Keep a Changelog](https://keepachangelog.com/en/1.1.0/) and the project uses
[Semantic Versioning](https://semver.org/spec/v2.0.0.html).

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
