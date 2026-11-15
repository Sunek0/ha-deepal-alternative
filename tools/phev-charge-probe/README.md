# PHEV charge-schedule probe

Diagnostic kit for the VOT/MQTT charge-plan flow used by the **My Changan**
1.12.0 Android app. It is intended for the owner of an **S05 PHEV** (or any
vehicle whose app exposes "Scheduled Charging" / "Reservar carga") and for the
maintainer investigating why `charge/add-plan` fails.

The kit has two scripts:

| File | Purpose |
| --- | --- |
| `login_email.py` | Email verification-code login; stores the tokens **and the login private key** in a local JSON file. |
| `probe_charge_plan.py` | Reads the current charge strategy, builds the signed `charge/add-plan` body, and optionally sends it. |

> **Safety first**
>
> * `probe_charge_plan.py` is **dry-run by default**. It prints the signed body
>   but does not send anything.
> * `--apply` sends a real command to the car and can create a charging plan.
>   Only run it on a car you own, with the owner's consent, while the car is
>   parked, and delete the test plan afterwards.
> * The token file contains an access token, a refresh token and a **private
>   key that can sign remote commands**. Treat it like a password. It is
>   written with mode `0600` and is ignored by git. The `.device_id` sidecar is
>   an account/device identifier; keep it private too.
> * The S05 **BEV** does not support a charge plan. Running `--apply` against a
>   BEV is expected to return an unsupported/TBOX error; that is still useful
>   for validating the request shape, but it does not prove the PHEV flow.

## 1. Requirements

From the repository root:

```bash
.venv/bin/pip install -e "deepal_sdk[dev]"
```

The scripts add `deepal_sdk/` to `sys.path`, so they also work from a checkout
without installing the package. Use the repository virtualenv:

```bash
cd /path/to/changan
.venv/bin/python tools/phev-charge-probe/login_email.py --help
.venv/bin/python tools/phev-charge-probe/probe_charge_plan.py --help
```

## Quick start

```bash
# 1. Request and exchange an email code (the account owner does this).
.venv/bin/python tools/phev-charge-probe/login_email.py send-code --email owner@example.com --country ES
.venv/bin/python tools/phev-charge-probe/login_email.py login --email owner@example.com --code 123456 --country ES

# 2. Read the current plan (no changes).
.venv/bin/python tools/phev-charge-probe/probe_charge_plan.py --token-file .token.json --list

# 3. Build the request and inspect it (no changes).
.venv/bin/python tools/phev-charge-probe/probe_charge_plan.py --token-file .token.json --start 0100 --end 0200

# 4. Send it only after the owner approves the dry-run body.
.venv/bin/python tools/phev-charge-probe/probe_charge_plan.py --token-file .token.json --start 0100 --end 0200 --apply

# 5. Delete the test schedule in the My Changan app.
```

## 2. Log in and obtain the token

The normal app login is the **email verification code** flow. Two commands:

```bash
# 1. Ask the backend to send a code to the account email.
.venv/bin/python tools/phev-charge-probe/login_email.py send-code \
  --email owner@example.com --country ES

# 2. Exchange the code for tokens. The output file also stores the login
#    private key, which is required to sign remote commands.
.venv/bin/python tools/phev-charge-probe/login_email.py login \
  --email owner@example.com --code 123456 --country ES \
  --token-file .token.json
```

The experimental email/password route is also available, but the app's real
flow is the code flow and the password body is not live-verified:

```bash
.venv/bin/python tools/phev-charge-probe/login_email.py password \
  --email owner@example.com --password '...' --country ES
```

Inspect the saved session without printing secrets:

```bash
.venv/bin/python tools/phev-charge-probe/login_email.py show --token-file .token.json
```

The token file has this shape (values are private):

```json
{
  "access_token": "...",
  "refresh_token": "...",
  "cac_token": "...",
  "user_id": "...",
  "ca_user_id": "...",
  "cac_user_id": "...",
  "expires_at": 1234567890,
  "private_key_pem": "-----BEGIN PRIVATE KEY-----...",
  "public_key": "...",
  "device_id": "..."
}
```

`send-code` and `login` share a stable `.device_id` file. Keep it with the
token file: the backend may bind the verification code to the device id, and
changing it between the two steps can invalidate the code.

If the file has no `private_key_pem`, the probe refuses to run: the app's
signed commands cannot be reproduced without it.

## 3. Read the current strategy (read-only)

```bash
.venv/bin/python tools/phev-charge-probe/probe_charge_plan.py \
  --token-file .token.json --list
```

The probe tries the two URLs recovered from the APK:

```text
POST /intl-app-gw/vot-api-server/api/strategy/getStrategy
POST /intl-app-gw/vot-vrtm-car-condition-write/api/strategy/getStrategy
```

and three body variants (`strategyCode` + `vehicleId`, `strategyCode` +
`carId`, `strategyCode` only). It prints every response. This call does not
change the car.

What to look for in the response:

* `strategyId` / `strategyCode`: the identifier the app uses for the plan.
* `content.orderStartTime` / `orderEndTime`: current plan times.
* `content.repetitionCycle`: current weekly mask.
* `status` / `isValid`: whether the plan is active.

## 4. Dry-run a new plan

```bash
.venv/bin/python tools/phev-charge-probe/probe_charge_plan.py \
  --token-file .token.json \
  --start 0100 --end 0200 \
  --repetition-field repetitionCycle --weeks 1111111 \
  --end-switch 0 --time-zone "GMT+01:00"
```

The probe:

1. Calls `POST /intl-app-gw/intl-car-control/api/control/create-serial-no`
   with a `type: "2"` body (variant selectable with `--serial-body`).
2. Decrypts the serial number with the login private key.
3. Builds the body and signs it with the same canonical string as the SDK.
4. Prints the body and exits **without sending** the plan.

Example body:

```json
{
  "vehicleId": "<carId>",
  "planType": 1,
  "timeFormat": 1,
  "startTime": "0100",
  "endTime": "0200",
  "repetitionCycle": "1111111",
  "endSwitch": 0,
  "timeZone": "GMT+01:00",
  "seriralNo": "<serial>",
  "sign": "<signature>"
}
```

Note the `seriralNo` spelling: it is an errata in the app/SDK payload, not a
typo in this document.

## 5. Send the plan (`--apply`)

Only after checking the dry-run body:

```bash
.venv/bin/python tools/phev-charge-probe/probe_charge_plan.py \
  --token-file .token.json \
  --start 0100 --end 0200 \
  --repetition-field repetitionCycle --weeks 1111111 \
  --end-switch 0 --time-zone "GMT+01:00" \
  --apply
```

The endpoint is:

```text
POST /intl-app-gw/intl-car-control/api/charge/add-plan
```

A successful response normally contains a `commandId`. The app then polls
`control/control-result` and may also refresh the strategy list.

**Cleanup:** open the My Changan app, go to the battery screen, disable/delete
the test schedule. The probe intentionally does not implement delete/validity:
the `planId`/`strategyId` semantics differ between the REST and VOT models and
a wrong delete could remove a real user plan.

## 6. Test matrix

Run the cases in order. Keep a copy of every command and output.

| # | Goal | Command / variation | What it proves |
| --- | --- | --- | --- |
| T0 | Login works | `login_email.py send-code` + `login` | The account, country and email flow are correct. |
| T1 | Token file is complete | `login_email.py show` | `access_token` and `private_key_pem` are present. |
| T2 | Strategy endpoint works | `probe_charge_plan.py --list` | Which of the two strategy URLs and which body variant the backend accepts. |
| T3 | Serial endpoint works | dry-run with default `--serial-body both` | `create-serial-no` accepts the VOT path/body and the key decrypts. |
| T4 | Request shape is accepted | dry-run with `--repetition-field repetitionCycle` | The backend/model uses `repetitionCycle`, not `weeks`. |
| T5 | Alternative field name | dry-run with `--repetition-field weeks` | Use this if T4 returns a missing-field/parameter error. |
| T6 | Create a plan | `--apply` with the T4 body | The PHEV accepts the add-plan command. The response is the reference success case. |
| T7 | Day mask | `--weeks 1000000`, then `0100000`, ... one bit at a time | Determines the day order (Sunday-first vs Monday-first). Do one dry-run per mask, then one `--apply` if needed. |
| T8 | `endSwitch` meaning | `--end-switch 1` dry-run/apply | Tests whether `endSwitch` is the "end at preset SOC" flag. Only relevant if the car reports `maxSocPercent`. |
| T9 | Timezone format | `--time-zone "GMT+02:00"` (or the car's local zone) | Confirms whether the backend expects `GMT+HH:MM` rather than an IANA name. |
| T10 | Optional command field | add `--command add_charge_plan` | Some gateways require the command literal in the body/signature; compare with T4. |
| T11 | Serial body variants | `--serial-body carId`, `vehicleId`, `type-only` | Finds the exact `create-serial-no` body if T3 fails. |
| T12 | Signing policy | `--signing-policy legacy` | Fallback only if `app` signing is rejected; do not use unless needed. |
| T13 | Optional strategy id | add `--strategy-id <id from --list>` | Checks whether `add-plan` expects the current strategy id (the VOT model has the field, the ViewModel does not expose it). |
| T14 | Cleanup | My Changan app → battery → disable/delete schedule | Confirms the plan is removed and no test schedule remains. |

### Interpreting the results

* **`--list` returns a plan list**: use the returned `strategyId`/`content` to
  compare with the created plan.
* **`--list` returns empty**: the car has no plan; that is expected before T6.
* **`add-plan` returns `commandId`**: request accepted; wait for the car and
  refresh the strategy list.
* **`TBOX_2001` / offline / busy**: the car did not accept the command; wake it
  (drive or use the app) and retry.
* **Unsupported/model error on a BEV**: expected; the BEV has no charge plan.
  The request shape is still validated, but the PHEV is the real target.
* **Auth error**: re-run `login_email.py login`; the access token is expired or
  the private key is missing.
* **Serial/sign error**: try the other `--serial-body` variant and make sure
  the token file contains the private key from the same login.

## 7. Option reference

### `login_email.py`

| Option | Meaning |
| --- | --- |
| `send-code` | Requests an email verification code. No token is produced. |
| `login` | Exchanges `--code` for tokens and writes the token file. |
| `password` | Experimental email/password login; not the app's normal flow. |
| `show` | Prints a masked summary of a token file. |
| `--email` | Account email address. |
| `--code` | Code received by email. |
| `--password` | Account password (only for `password`). |
| `--country` | Sales country code sent at login and in headers; default `ES`. Use the account's market (e.g. `ES`, `GB`, `PT`, `GR`). |
| `--environment` | `release_eu` (production EU, default) or `preprod_eu`. The base URLs change; do not mix environments with a token from another one. |
| `--token-file` | Output file; default `.token.json`, mode `0600`. |
| `--device-id-file` | Stable device id shared by `send-code` and `login`; default `.device_id`. Keep it with the token file. |

### `probe_charge_plan.py`

| Option | Meaning |
| --- | --- |
| `--token-file` | JSON file produced by `login_email.py`. Default `.token.json`. |
| `--token` | Access-token override; useful for CI, but the private key still has to be in the token file. |
| `--country` | Sales country code for headers; default `ES`. |
| `--environment` | `release_eu` (default) or `preprod_eu`. |
| `--car-id` | Vehicle id. If omitted, the first vehicle on the account is used. |
| `--start` | Start time as `HHMM` in the vehicle's local time; default `0100`. |
| `--end` | End time as `HHMM`; default `0200`. Keep it different from `--start`. |
| `--weeks` | Seven-character day mask; default `1111111` (all days). `0000000` means no days. The exact bit order is what T7 determines. |
| `--repetition-field` | `repetitionCycle` (VOT model, default) or `weeks` (ViewModel parameter). Try `repetitionCycle` first. |
| `--end-switch` | `0` or `1`. Most likely the "end at preset charge value" flag, not the enable switch. Default `0`. |
| `--time-zone` | Timezone string in `GMT+HH:MM` form; default `GMT+01:00`. Use the car's local offset. |
| `--plan-type` | Integer plan type; default `1`. Leave at `1` unless the backend asks otherwise. |
| `--time-format` | Integer time format; default `1` (HHMM). |
| `--strategy-id` | Optional `strategyId` copied from `--list`; adds it to the body. Use it only if the backend says the field is required. |
| `--command` | Optional `add_charge_plan` literal. Default empty; compare T4/T10. |
| `--signing-policy` | `app` (default; omits `sign`, `class`, `command`) or `legacy` (per-command omissions). Fallback only. |
| `--serial-body` | `both` (default), `carId`, `vehicleId`, `type-only`. Controls the `create-serial-no` body. |
| `--list` | Read-only strategy query; no command is sent. |
| `--apply` | Actually POST `charge/add-plan`. Without it, the script stops after printing the signed body. |
| `--debug` | Enables the SDK's redacted API log. Tokens and payloads are masked by the SDK. |

## 8. Troubleshooting

| Symptom | Likely cause / action |
| --- | --- |
| `DeepalAuthError`, `APP_1_1_02_004`, `APIGW_1_7_02_001` | Access token expired or malformed. Re-run `login_email.py login`; keep the same `.device_id`. |
| `DeepalCommandNotReady` / “private key is required” | The token file has no `private_key_pem`. Re-run the login; do not copy only the access token. |
| `create-serial-no` returns an error | Try `--serial-body carId`, then `vehicleId`, then `type-only`. |
| `add-plan` returns a missing field/parameter error | Try `--repetition-field weeks`; if it still fails, add `--strategy-id` from `--list` or `--command add_charge_plan`. |
| `TBOX_2001` | The car did not accept the command: offline, asleep or busy. Wake it (drive it or use the app) and retry. |
| `1032` (“Power is not off”) | The car must be powered off for this command. |
| `COMMON_1_1_01_005` | One field/value is rejected. Check the time format, timezone, day mask and `endSwitch`. |
| `--list` returns an empty list | No plan is configured; that is normal before T6. |
| `--apply` returns a `commandId` but no plan appears | Wait for the car, run `--list` again, and check `control-result` in the app/SDK. |
| Unsupported/model error on an S05 BEV | Expected: the BEV has no charge-plan capability. Use the PHEV for T6. |
| Verification code rejected | The code expired or the `.device_id` changed between `send-code` and `login`. Use the same sidecar file and request a new code. |
| Rate-limited login | Wait before requesting another code; the backend limits repeated email codes. |

## 9. What to send back

For a PHEV report, include:

1. The `--list` output for both URLs (redact VIN/tokens if needed).
2. The dry-run body for `repetitionCycle` and `weeks`.
3. The `--apply` response for the accepted variant, including `commandId`,
   `resultCode` and `errorMsg`.
4. The strategy list after the command, so we can compare `content` and
   `isValid`.
5. Whether the car is a PHEV, the model code, and the market/country.

Do not send the token file, the private key, the VIN, or the raw serial number.
