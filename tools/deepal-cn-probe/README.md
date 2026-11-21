# Deepal app (China) car-data probe

Read-only probe for the telemetry endpoint the **Deepal app (深蓝汽车)** uses. It is not the SDA
platform: the app calls

```text
POST https://cy-m.shenlanche.com.cn/app2/api/car/data?carId=...&keys=*&token=...
```

and returns `{"code":0,"data":{...196 fields...}}`. The probe validates that endpoint with your own
token and prints a redacted field summary, so the field mapping can be designed without sharing
credentials.

## What it does

1. Reads `DEEPAL_CN_TOKEN` and `DEEPAL_CN_CAR_ID` from the environment (or `--token`/`--car-id`).
2. Sends one `POST` to `app2/api/car/data` with `carId`, `keys=*` and `token`.
3. Prints the number of returned fields and a curated summary (SOC, range, odometer, charge,
   doors, locks, climate, speed, shift).
4. With `--raw`, prints the full payload with tokens, VIN, car id, coordinates, user identifiers
   and similar keys redacted.

It **never** logs in, requests an SMS, sends a control command or writes anything to disk.

## What it answers

- Whether the token is accepted (`code: 0` vs `token已过期`).
- How many fields the car returns and which of the curated fields are present.
- The exact field names available for the read-only telemetry client in issue #5.

## What it does not answer

- The login flow. `appapi/v2/auth/login` encrypts its request and response with an RSA `encStr`, so
  the plaintext fields need DEX analysis or app hooking.
- Remote controls. Their paths and signing scheme are unknown.
- The captcha. The app's Tencent slider is app-side risk control; the send-code endpoint does not
  require it.

## Requirements

From the repository root:

```bash
.venv/bin/pip install -e "deepal_sdk[dev]"
```

The script adds `deepal_sdk/` to `sys.path`, so a checkout without an editable install also works.

## Usage

```bash
DEEPAL_CN_TOKEN="<your token>" DEEPAL_CN_CAR_ID="<your car id>" \
  .venv/bin/python tools/deepal-cn-probe/probe.py
```

Full redacted payload for field mapping:

```bash
DEEPAL_CN_TOKEN="<your token>" DEEPAL_CN_CAR_ID="<your car id>" \
  .venv/bin/python tools/deepal-cn-probe/probe.py --raw
```

Another host or timeout:

```bash
.venv/bin/python tools/deepal-cn-probe/probe.py \
  --token "<your token>" --car-id "<your car id>" \
  --base-url https://cy-m.shenlanche.com.cn --timeout 20
```

`--keys` overrides the `keys=*` query parameter when a smaller response is useful.

## Offline mode (captured payload)

If you do not have a live token, run the probe against a captured JSON payload. File mode makes no
network request and needs no credentials:

```bash
.venv/bin/python tools/deepal-cn-probe/probe.py --payload-file capture.json --raw
```

The file can be either the full gateway envelope (`{"code":0,"data":{...}}`) or the bare `data`
object. Redact tokens, VIN, car id, coordinates and user identifiers before sharing the file; the
`--raw` output applies the probe's own redaction on top.

Example output (values are illustrative):

```text
Fields returned: 196
  SOC (%)                                82
  Remaining range (remainedPowerMile)    410
  Odometer (totalOdometer)               12450
  Charge status                          1
  Driver door                            False
  AC target temperature                  22.5
```

The summary also lists any curated fields that are absent from the payload. The list above is
illustrative: the exact values and the missing set depend on the car.

## Exit codes

| Code | Meaning |
| --- | --- |
| `0` | The token was accepted and the summary was printed |
| `1` | Transport error, HTTP error, invalid JSON from the gateway, or a gateway error (`code` != `0`) |
| `2` | Missing `DEEPAL_CN_TOKEN`/`DEEPAL_CN_CAR_ID`, a non-HTTPS `--base-url`, or an unreadable/invalid `--payload-file` |

## Security notes

- The token travels as a **query parameter** because that is the app's contract. The probe refuses
  non-HTTPS hosts, never prints the request URL or the raw HTTP exception, and `--raw` redacts the
  payload, but a proxy or TLS-inspection log outside the tool could still record the URL. Run it on
  your own machine.
- Do not paste the token in the issue. Report the exit code, the summary and, if useful, the redacted
  `--raw` output after checking that your VIN, car id and identifiers show as `[redacted]`.
- The probe is read-only. It cannot change the car.
