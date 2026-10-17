# Errors and diagnostics guide

How the SDK reports failures, how to react to each class and how to log traffic without leaking
credentials.

> The exact gateway code lists live in the [error section](../reference/intl-api.md#11-errors) of
> the reference; this guide is about handling them in an application.

## 1. The taxonomy

```
DeepalError
├── DeepalAuthError
│   ├── DeepalCommandAuthError    # signing material rejected, PIN expired or not set
│   └── DeepalCommandNotReady     # private key or PIN missing before signing
├── DeepalAPIError                # any other gateway or HTTP failure (code, status_code)
│   └── DeepalRateLimitError      # 429 or business rate limit (retry_after)
└── DeepalConnectionError         # transport failure (httpx.RequestError)
```

Every error derives from `DeepalError`, so one `except` can cover the SDK. The SDA (China) client
raises only `DeepalAuthError`, `DeepalAPIError` and `DeepalConnectionError`
([SDA errors](../reference/sda-api.md#7-errors)).

## 2. React to each class

| Situation | Exception | What to do |
| --- | --- | --- |
| HTTP 401/403 or an app kick-out code | `DeepalAuthError` | Restore or re-login; `refresh_tokens(force=True)` first when you have a refresh token |
| HTTP 429 or a business rate limit | `DeepalRateLimitError` | Wait `retry_after` seconds when set, then retry |
| PIN attempts exhausted (`HW_1_1_01_047`) | `DeepalRateLimitError` | Reset the PIN in the app; there is no SDK-side unlock |
| PIN expired (`HW_1_1_01_073`) or not set (`HW_1_1_01_074`) | `DeepalCommandAuthError` | Create or reset the PIN with the account used by your application |
| Serial fetch/decrypt failure, rejected `rcToken` | `DeepalCommandAuthError` | Check the keypair and retry; the SDK re-exchanges the PIN once automatically |
| Signed command without key or PIN | `DeepalCommandNotReady` | Fix the prerequisites before retrying (see the [commands guide](remote-commands.md#1-prerequisites)) |
| Any other `success: false` code or non-2xx HTTP status | `DeepalAPIError` | Inspect `code` / `status_code`; usually not retryable without a change |
| Transport failure or timeout | `DeepalConnectionError` | Retry later; the request never reached the gateway |

## 3. Retry pattern

```python
import asyncio

from deepal import DeepalAuthError, DeepalConnectionError, DeepalRateLimitError

async def read_condition(client, car_id):
    try:
        return await client.get_vehicle_condition(car_id)
    except DeepalRateLimitError as err:
        await asyncio.sleep(err.retry_after or 60)
        return await client.get_vehicle_condition(car_id)
    except DeepalAuthError:
        await client.refresh_tokens(force=True)
        return await client.get_vehicle_condition(car_id)
    except DeepalConnectionError:
        raise  # let the caller decide how to back off
```

- `retry_after` carries the gateway's `Retry-After` value when it sent a positive one, and is
  `None` for business rate limits without a wait.
- A forced refresh is single-flight, so concurrent failures do not storm the gateway.
- Avoid unbounded retry loops: a second `DeepalAuthError` after a refresh means the session is
  gone and a new login is required.

## 4. Redacted diagnostics

Pass `enable_api_logging=True` to log every request and response at `WARNING` level:

```python
client = DeepalIntlClient(country="ES", enable_api_logging=True)
```

- Tokens, keys, VINs, emails, phones, PINs, serial numbers and user ids are masked; strings longer
  than 500 characters are truncated (`deepal/redact.py`).
- Only non-sensitive headers are logged as-is: `selectcountry`, `appversion`, `language`,
  `x-os-version`, `x-tsp-timestamp`, `x-vcs-timestamp`.
- Logins and refreshes log **booleans** for whether `cacToken`, `userId`, `caUserId` and
  `cacUserId` arrived, never the values.
- Unmapped MQTT parameters can be surfaced by enabling `DEBUG` on the `deepal_sdk` logger:

```python
import logging

logging.getLogger("deepal_sdk").setLevel(logging.DEBUG)
```

## 5. Keeping secrets out of your logs

- The SDK never logs credential values itself, but your application can: catch the exceptions and
  log `err.code` / `err.status_code`, not the payloads you passed in.
- Store tokens, the signing keypair and the control PIN in a secret store; never in source control
  or plain-text config files (see [what to persist](authentication.md#6-what-to-persist)).

## Next steps

- [International platform reference](../reference/intl-api.md#11-errors): the complete
  code-to-exception mapping.
- [Remote commands guide](remote-commands.md#7-command-specific-errors): command-specific failures.
