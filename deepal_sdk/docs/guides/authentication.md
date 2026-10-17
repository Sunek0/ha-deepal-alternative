# Authentication guide

How to establish and keep a `DeepalIntlClient` session: the email and SMS code logins, the
signing keypair, the values to persist, and how to restore, refresh or end a session.

> Protocol detail (endpoints, headers, encryption) lives in the
> [international platform reference](../reference/intl-api.md#5-authentication).
> The China SDA client uses a plain access token instead: see the
> [SDA platform reference](../reference/sda-api.md#3-authentication).

## 1. Create the client

The client is an async context manager and creates its HTTP client lazily, so constructing one per
process is cheap:

```python
import asyncio

from deepal import DeepalIntlClient


async def main() -> None:
    async with DeepalIntlClient(country="ES", language="es_ES") as client:
        ...  # log in, then read telemetry or send commands
```

- `country` is the sales country sent as `selectcountry` and used by the login flows.
- `environment` selects the regional gateway set (`release_eu` for Europe, `release_znm` for Latin
  America; see [Environments](../reference/intl-api.md#2-environments)).
- `device_id` is a persistent client fingerprint. When you omit it, the SDK generates a random one;
  persist it and reuse it across restarts so the account sees a stable device.

## 2. Log in with an email code

Two calls: request the code, then exchange it.

```python
await client.request_email_code("you@example.com")
code = input("Verification code: ").strip()
token = await client.login_with_email_code("you@example.com", code)
print("Logged in:", bool(token.access_token))
```

The email address is RSA-encrypted with the app's public key before it leaves the process. The
login stores the session on the client (`access_token`, `refresh_token`, `cac_token`, `user_id`,
`ca_user_id`, `cac_user_id`) and returns the same values as an `AuthToken`.

Both calls accept optional arguments:

| Argument | Effect |
| --- | --- |
| `sales_country="ES"` | Overrides the client `country` for this call |
| `pub_key="..."` | Registers an explicit public key instead of the stored or generated one |

Wrong or expired codes raise `DeepalAuthError`; rate limits raise `DeepalRateLimitError` with the
gateway wait when it is known.

## 3. Log in with an SMS code

The SMS flow is equivalent, with local input validation before any HTTP call:

```python
await client.request_sms_code("600000000", "34")   # national number + dial code
token = await client.login_with_sms_code("600000000", code, "34")
```

- `phone` is the **national** number without the `+` prefix; a leading `+` raises `ValueError`.
- `country_code` is digits only; a leading `+` is stripped (`+34` becomes `34`).
- Empty values raise `ValueError`.

## 4. Password logins (unverified)

`login_with_email_password(email, password)` and
`login_with_password(phone, password, country_code)` exist and follow the app's recovered routes,
but their field names were extracted from the app without live traffic and are **not verified**.
Prefer the verification-code flows.

## 5. The signing keypair

Remote commands are signed with the RSA keypair the login registers as `pubKey`. Treat it as part
of the account identity:

- A login without key material generates a pair and exposes it as `client.private_key_pem` and
  `client.public_key`.
- A stored pair is never replaced, and a login never registers a second public key while one is
  available.
- If only `pub_key` is provided (no private key), signed commands raise `DeepalCommandNotReady`.

Utilities:

```python
private_key_pem, public_key = DeepalIntlClient.generate_login_keypair()  # once, then persist
body = DeepalIntlClient.public_key_body_from_private(private_key_pem)    # derive the pubKey body
client.set_login_keypair(private_key_pem, public_key)                    # restore a persisted pair
```

## 6. What to persist

Store these values as secrets (OS keyring or the password manager of your application), never in
source control:

| Value | Attribute | Why |
| --- | --- | --- |
| Access token | `client.access_token` | Authenticates every request |
| Refresh token | `client.refresh_token` | Required by `refresh_tokens()` |
| CAC token | `client.cac_token` | Appended to `authorization` and used by the CA/MQTT path |
| Account user id | `client.user_id` | Required by MQTT telemetry and the digital-key checks |
| CA / CAC user ids | `client.ca_user_id`, `client.cac_user_id` | Kept for completeness and diagnostics |
| Device id | `client.device_id` | Stable client fingerprint |
| Private key | `client.private_key_pem` | Signs remote commands |
| Public key | `client.public_key` | Registered at login, reused on restore |

The remote-control PIN is a separate secret: set `client.control_pin = "000000"` (your own 6-digit
PIN) before sending PIN-gated commands; see the [remote commands guide](remote-commands.md).

## 7. Restore a session

A restored client skips the login and keeps signing commands:

```python
client = DeepalIntlClient(
    country="ES",
    device_id=device_id,
    private_key_pem=private_key_pem,
    public_key=public_key,
)
client.access_token = access_token
client.refresh_token = refresh_token
client.cac_token = cac_token
client.user_id = user_id
client.ca_user_id = ca_user_id
client.cac_user_id = cac_user_id
```

`set_login_keypair(private_key_pem)` is the alternative when you did not persist the public half;
it derives it from the private key.

## 8. Keep the session fresh

```python
if client.access_token_expires_soon():          # JWT exp within five minutes
    await client.refresh_tokens()
await client.refresh_tokens(force=True)         # after an authentication rejection
```

- `access_token_expires_soon(margin_seconds=300)` parses the JWT exp claim lazily, so it works on
  restored sessions.
- `refresh_tokens()` is throttled with a monotonic 30-minute window matching the app: a throttled
  call returns the current session without sending a request or raising.
- A refresh is single-flight (concurrent callers share one outcome) and runs proactively when the
  access token is about to expire.
- `force=True` bypasses the window after a `DeepalAuthError`.
- Omitted fields in the refresh response keep their previous values; when the response carries no
  new CAC token the SDK logs a warning and the CA/MQTT path keeps the old one.

## 9. Log out

```python
await client.logout()
```

The local session (`access_token`, `refresh_token`, `cac_token`, `rc_token`, expiry) is cleared
even when the remote call fails. Without an access token the call is a no-op. The logout body is
recovered from the app and **not verified live**.

## 10. When things fail

| Symptom | Exception | Action |
| --- | --- | --- |
| Missing, expired or rejected session | `DeepalAuthError` | Restore or re-run a login; refresh if you have `refresh_token` |
| Gateway rate limit | `DeepalRateLimitError` | Wait `retry_after` seconds when set, then retry |
| Transport failure or timeout | `DeepalConnectionError` | Retry later; the request never reached the gateway |

The complete mapping is in the [errors guide](errors-and-diagnostics.md) and the
[error section](../reference/intl-api.md#11-errors) of the reference.

## Next steps

- [Telemetry guide](telemetry.md): list vehicles and read their condition.
- [Remote commands guide](remote-commands.md): use the session to control the car.
- [Errors and diagnostics guide](errors-and-diagnostics.md): handle failures and log safely.
