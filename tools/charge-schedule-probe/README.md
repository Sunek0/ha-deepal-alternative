# Charge-schedule probe

Diagnostic probe for the Deepal international `/charge/modify-plan` command used by the
integration and the My Changan app. It reads the Deepal config entry stored by Home Assistant,
prints the current plan and, only with `--apply`, sends a signed schedule change to the car.

This is the command path the S05 BEV uses to reserve a charging window. It is **not** the
PHEV VOT `charge/add-plan` flow in `tools/phev-charge-probe/`.

## Safety

- **Dry-run by default.** Without `--apply` the script only reads the vehicle list and the
  current condition; it does not send the command.
- `--apply` writes a real schedule to the car. Only run it on a car you own, with the owner's
  consent, while the car is parked.
- The schedule command does **not** require the control PIN.
- The script **does not refresh the token by default**. A second refresh can rotate the
  refresh token and log the Home Assistant integration out. If the access token is about to
  expire, wait for the integration to refresh it, or pass `--allow-refresh` only if you accept
  the reauthentication.
- The HA config entry contains the access token and the command-signing private key. The
  script reads it at runtime and never prints it. If you copy the entry to a temporary file,
  keep it mode `0600` and delete it afterwards.

## Requirements

From the repository root:

```bash
.venv/bin/pip install -e "deepal_sdk[dev]"
```

The script adds `deepal_sdk/` to `sys.path`, so it also works from a checkout without
installing the package.

## Usage

Read the current plan without changing anything:

```bash
.venv/bin/python tools/charge-schedule-probe/probe_charge_schedule.py
```

Preview a 00:00-01:00 reservation (still dry-run):

```bash
.venv/bin/python tools/charge-schedule-probe/probe_charge_schedule.py \
  --start 0000 --end 0100
```

Send it after reviewing the dry-run output. On the S05 BEV the working path is `--add-plan`:

```bash
.venv/bin/python tools/charge-schedule-probe/probe_charge_schedule.py \
  --start 0000 --end 0100 --add-plan --apply --watch 60
```

Disable the reservation instead of enabling it:

```bash
.venv/bin/python tools/charge-schedule-probe/probe_charge_schedule.py \
  --start 0000 --end 0100 --disabled --apply
```

Delete a plan (the id comes from the condition or `--plan-id`):

```bash
.venv/bin/python tools/charge-schedule-probe/probe_charge_schedule.py \
  --delete-plan --plan-id 2123350099388235778 --apply
```

## Entry file

By default the script reads `/mnt/ha-config/.storage/core.config_entries`. That file is
normally root-owned; either run the script with `sudo` or copy just the Deepal entry to a
private file:

```bash
sudo python3 - <<'PY' > /tmp/opencode/deepal_entry.json
import json
source = "/mnt/ha-config/.storage/core.config_entries"
data = json.load(open(source))
entry = next(item for item in data["data"]["entries"] if item["domain"] == "deepal")
print(json.dumps({"title": entry.get("title"), "data": entry["data"]}))
PY
chmod 600 /tmp/opencode/deepal_entry.json
.venv/bin/python tools/charge-schedule-probe/probe_charge_schedule.py \
  --entry-file /tmp/opencode/deepal_entry.json --start 0000 --end 0100
rm -f /tmp/opencode/deepal_entry.json
```

## What the script prints

- The vehicle series, `carId`, VIN and model code.
- The current condition: SOC, `ChrgSts`, charger connection, plan id, start/end, enabled flag
  and timezone.
- The raw `chargePlanList` returned by the condition, which is useful to see whether the car
  returns `endTime`/`endSwitch` for the S05 BEV.
- The payload that will be signed (without the signature).
- After `--apply`: the command id, the command result status and the refreshed condition/MQTT
  state.

## S05 BEV notes

The S05 BEV condition reports the plan as:

```json
{"planId": 1, "planType": 1, "isValid": 0, "startTime": "0000",
 "startSwitch": 1, "endTime": "0100", "endSwitch": 1}
```

It may omit `endTime`/`endSwitch` in some reports and include them after the app writes the plan.
`isValid` is the actual enable flag; `switches_enabled` (the integration's
`charge_schedule_enabled`) only means both switches are on and can be true while the plan is
disabled.

### What works on the S05 BEV (2026-11-19)

- `/charge/modify-plan` (the default mode) returns `HW_1_1_01_001 Operation failed`, even after a
  wake.
- `/charge/validity` returns the same error.
- **`/charge/add-plan` works**: the command returned a `commandId`, the condition moved to a new
  plan id, `isValid` became `1`, and the car switched to `ChrgSts=8` (connected, waiting for the
  scheduled window).

For the S05 BEV use `--add-plan`:

```bash
.venv/bin/python tools/charge-schedule-probe/probe_charge_schedule.py \
  --entry-file /tmp/opencode/deepal_entry.json \
  --start 0000 --end 0100 --add-plan --apply --watch 60
```

The add-plan command creates a **new** plan id. The previous plan may remain in the app; delete
the test plan with `--delete-plan --plan-id <id>` or from the My Changan app after the test.

Do not enable the integration's schedule switch/time entities for the S05 BEV until the full
create/delete flow has been validated; the condition's `endTime`/`timeZone` fields are not stable.
