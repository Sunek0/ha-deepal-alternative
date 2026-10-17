# Remote commands guide

How to send signed remote commands with `DeepalIntlClient`: the prerequisites, the control PIN
exchange, every command family and how command results are polled.

> The full command reference — payloads, endpoints, serial-number family per command and the
> verified/recovered status of each one — lives in the
> [remote commands section](../reference/intl-api.md#10-remote-commands) of the reference.

## 1. Prerequisites

Three ingredients, in this order:

| Requirement | Where it comes from | What fails without it |
| --- | --- | --- |
| Login private key (`client.private_key_pem`) | The login keypair (see the [authentication guide](authentication.md#5-the-signing-keypair)) | `DeepalCommandNotReady` |
| Remote-control PIN (`client.control_pin`) | Created with the account in the official app | `DeepalCommandNotReady` on PIN-gated commands |
| Serial number | Fetched and decrypted by the SDK per command family | `DeepalCommandAuthError` when it cannot be fetched or decrypted |

Every command returns a **`commandId` string**; the vehicle executes asynchronously and the result
is polled (see [step 4](#4-poll-the-result)).

## 2. Provide the control PIN

```python
client.control_pin = "000000"  # the account's remote-control PIN
```

The PIN gates the door lock, the windows and the trunk. The SDK exchanges it automatically the
first time a PIN-gated command runs: it asks `get_security_code_status()` for the remaining
attempts, encrypts the PIN and stores the returned short-lived `rc_token` in `client.rc_token`.
When a command reuses a stale token the server rejects it once, and the SDK re-exchanges the PIN
and retries that command a single time.

You can also drive the exchange yourself:

```python
status = await client.get_security_code_status()   # retryQuantity and PIN state
await client.check_control_code("000000")           # stores and returns the rc_token
```

- No remaining attempts ⇒ `DeepalRateLimitError`, and no exchange is attempted.
- Expired (`HW_1_1_01_073`) or not-set (`HW_1_1_01_074`) PIN ⇒ `DeepalCommandAuthError`; create or
  reset the PIN in the app with the same account.

## 3. Send a command

```python
command_id = await client.control_air_conditioner(
    vehicle.car_id, enabled=True, target_temp_c=22.0
)
```

Families and entry points:

| Family | Methods | PIN |
| --- | --- | --- |
| Climate | `control_air_conditioner`, `control_defrost` | No |
| Refresh | `control_condition_inquiry` | No |
| Locks | `control_doors`, `control_windows`, `control_trunk` | **Yes** |
| Lights and horn | `control_flashing_honking` (`FLASH_HONK_FLASH`, `FLASH_HONK_BEE`, `FLASH_HONK_FLASH_BEE`, `FLASH_HONK_OFF`) | No |
| Seats and wheel | `control_seats_heat`, `control_seats_wind`, `control_steering_wheel_heat` | No (optional `require_rc_token`) |
| Charging | `control_charge_limit`, `control_charge_schedule` | No |
| Plans | `control_charge_plan_add/delete/validity`, `control_departure_plan_add/modify/delete/validity/enabled` | No |
| Vehicle | `control_fota_plan` | No |

Details that matter:

- Seat commands serialize only the positions you pass; turning a seat off sends `switch: 0`
  without a level because a zero level is rejected by the gateway.
- Flash and horn codes are the `FLASH_HONK_*` constants exported by the package.
- The optional families accept `serial_type` and `require_rc_token` overrides; the defaults come
  from the app constants and are pending full live validation.

## 4. Poll the result

```python
import asyncio

from deepal import CommandResultStatus

while True:
    result = await client.control_result_status(vehicle.car_id, command_id)
    if result.status is not CommandResultStatus.PENDING:
        break
    await asyncio.sleep(2)

print(result.status, result.error_message)
```

`control_result(vehicle_id, command_id)` returns the raw gateway dictionary;
`control_result_status(...)` classifies it into a `CommandResult`:

| `resultCode` | `status` | Meaning |
| --- | --- | --- |
| absent, `-100` | `pending` | The vehicle has not answered yet |
| `0`, `1201` | `success` | Executed |
| `1015` | `already_done` | The state was already the requested one |
| `-1`, `-2`, unknown | `failed` | Refused or failed; `error_message` carries `errorMsg` |

There is no SDK-side timeout: poll at your own cadence and stop when the status is no longer
`pending`.

## 5. Repeating physical commands

Flash and horn drive a real physical cycle on the car: a new request is refused until the cycle
finishes (about 30 seconds for flash and 6 seconds for horn). When you repeat one too soon, wait
for the cycle instead of hammering the gateway — the vehicle would reject the repeats anyway.

## 6. The signature (what the SDK does for you)

Every command body is signed with the login private key:

- `sign_payload(payload, omit_keys=None)` builds the canonical string (alphabetically sorted
  `key=value` pairs joined with `&`), signs it with RSA PKCS#1 v1.5 + SHA-256 and base64-MIME
  encodes it.
- The default `app` policy excludes exactly `sign`, `class` and `command`; per-command omission
  sets are only used by the `legacy` policy (`signing_policy="legacy"`).
- `rc_token` is serialized only by the PIN-gated commands; an empty token is rejected by the
  gateway with `COMMON_1_1_01_008`.

The construction is documented in detail in the
[signature section](../reference/intl-api.md#103-signature) of the reference.

## 7. Command-specific errors

| Situation | Exception |
| --- | --- |
| Signed command without a private key or required PIN | `DeepalCommandNotReady` |
| PIN expired or not set | `DeepalCommandAuthError` |
| Serial fetch/decrypt failure (`COMMON_1_1_01_001`) or rejected `rcToken` | `DeepalCommandAuthError` |
| PIN attempts exhausted (`HW_1_1_01_047`) | `DeepalRateLimitError` |
| Any other gateway code | `DeepalAPIError` with `code` |

## 8. End-to-end example

```python
import asyncio

from deepal import (
    CommandResultStatus,
    DeepalCommandAuthError,
    DeepalCommandNotReady,
    DeepalIntlClient,
)


async def main() -> None:
    async with DeepalIntlClient(country="ES", device_id="restored-device-id") as client:
        # ... restore the session (authentication guide, step 7) ...
        client.control_pin = "000000"

        try:
            command_id = await client.control_doors("CAR_ID", open_value=False)
        except DeepalCommandNotReady as err:
            print("Missing key or PIN:", err)
            return
        except DeepalCommandAuthError as err:
            print("PIN problem:", err)
            return

        while True:
            result = await client.control_result_status("CAR_ID", command_id)
            if result.status is not CommandResultStatus.PENDING:
                break
            await asyncio.sleep(2)
        print("Lock:", result.status, result.error_message)


asyncio.run(main())
```

## Next steps

- [Errors and diagnostics guide](errors-and-diagnostics.md): the complete failure taxonomy.
- [International platform reference](../reference/intl-api.md#10-remote-commands): endpoints,
  payloads and the verified/recovered status of every command.
