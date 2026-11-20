# MQTT live probe

Read-only probe for an international Deepal vehicle with `protocolType: MQTT` (S05 family). It
reuses the integration's CA/MQTT bootstrap, keeps **one** MQTT connection open for a few minutes and
prints the unsolicited messages the broker sends to that session.

It is the first validation step of `rework-s05-mqtt-session-lifecycle`: it answers whether the
vehicle publishes changes in real time, which topics carry them and whether a second client
(the phone app) can stay connected at the same time.

## What it does

1. Reads the Deepal entry from Home Assistant's `.storage/core.config_entries` (or a token file).
2. Builds the international client with the stored `user_id`, tokens and `device_id`.
3. Selects the first `protocolType: MQTT` vehicle, or the one passed with `--vehicle`.
4. Opens one MQTT session with the integration's own identity resolution, subscribes and logs in.
5. Listens. It **never** publishes a condition request, a wake or a command. The only writes are
   the MQTT login, the logout, PUBACKs and PINGREQs.
6. Prints each received message with a redacted summary and a final counter summary.

`SDA-MQTT` vehicles are excluded; the probe refuses to run for them.

## Safety

- Read-only: no commands, no wake, no condition requests.
- It does not refresh the account session, so it cannot rotate the refresh token and log the
  integration out. If the access token is expired, let the integration refresh it and run the probe
  again.
- The output redacts tokens, client id, DID, VIN, `cid`, `uid`, location and the encrypted
  `sers`/`rs` blobs. The raw parameters are only printed with `--dump-params` and are redacted too.
- Do not leave it running for hours. A few minutes are enough for the validation.
- The broker may close the probe if another client uses the same identity. That is exactly the
  conflict signal the probe is meant to detect; the app should stay connected in the expected
  different-account setup.

## Permissions

Reading `/mnt/ha-config/.storage/core.config_entries` may require elevated permissions. Either run
the script with `sudo`, or copy the Deepal entry to a private file and pass `--entry-file`. A token
file with the entry `data` (`access_token`, `refresh_token`, `cac_token`, `user_id`, `device_id`,
`country`, `environment`) also works.

## Usage

```bash
# Listen for five minutes
python tools/mqtt-live-probe/probe.py --seconds 300

# Listen for ten minutes and write redacted JSONL for later analysis
python tools/mqtt-live-probe/probe.py --seconds 600 \
  --jsonl /tmp/deepal-mqtt-live.jsonl

# Show every decoded report's redacted parameters
python tools/mqtt-live-probe/probe.py --seconds 300 --dump-params

# Choose a vehicle by car id or VIN
python tools/mqtt-live-probe/probe.py --seconds 300 --vehicle <car-id-or-vin>

# Use a copied entry or token file
python tools/mqtt-live-probe/probe.py --entry-file ~/deepal-entry.json --seconds 300
```

Useful output lines:

- `client_id_is_login_did` / `username_is_login_did`: whether the resolved MQTT identity is the
  login DID. These are booleans; the values are never printed.
- `/properties/report`: an unsolicited report from the vehicle.
- `/properties/get/res`: a response to a request. The probe does not send requests, so a report
  here during a quiet run is unexpected.
- `/events/up`, `/msg/up`, `/strategy/res`: event traffic.
- `chargePlanList seen over MQTT`: expected to be `False`; the plan is a REST-only field.
- `pings`: PINGRESP packets received while the session was idle.

## What to do during the run

Keep the phone app open and make changes from it, one at a time, leaving a few seconds between
them:

1. Lock and unlock the doors.
2. Open and close a window.
3. Turn the climate on/off or change the target temperature.
4. Change the charge schedule (start/end or enable/disable).
5. If someone is with the car, open/close a door or the trunk physically.

Write down the time of each action. The probe prints the receive time, so you can compare the
latency. Also watch the app: it should not disconnect while the probe is connected.

## How to read the result

- If `properties/report` arrives within seconds of an app or car change, the live session is the
  right transport for that field.
- If a change only appears in `/vehicle/condition` (the REST condition) and never in the probe,
  that field needs the REST overlay/poll; the charge plan is the known case.
- If the app disconnects when the probe connects, the two clients share the MQTT identity. Record
  the exact sequence and stop the probe; the change must use the conflict backoff/opt-out.
- If no report arrives at all, confirm the car is awake and reporting (the app can show a recent
  update) and repeat the run.

Record the observations in the private investigation notes. They decide whether the live-session
design needs any adjustment before implementation.
