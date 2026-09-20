"""Log redaction helpers for API payloads and headers."""

from __future__ import annotations

from typing import Any

_REDACTED = "[redacted]"
_MAX_STRING_LENGTH = 500
_SAFE_HEADER_KEYS = (
    "selectcountry",
    "appversion",
    "language",
    "x-os-version",
    "x-tsp-timestamp",
    "x-vcs-timestamp",
)

_SENSITIVE_EXACT_KEYS = {
    "access_token",
    "authcode",
    "authorization",
    "cactoken",
    "cac_token",
    "control_pin",
    "deviceid",
    "email",
    "mobile",
    "password",
    "phone",
    "private_key_pem",
    "pubkey",
    "rctoken",
    "refresh_token",
    "safecode",
    "seriralno",
    "sign",
    "token",
    "userid",
    "vehicleid",
    "vin",
}

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "bearer",
    "email",
    "key",
    "mobile",
    "password",
    "pem",
    "phone",
    "pin",
    "rctoken",
    "serial",
    "sms",
    "token",
    "vehicleid",
    "vin",
)


def is_sensitive_key(key: Any) -> bool:
    """Return whether a JSON/header key should never be logged raw."""
    normalized = str(key).lower().replace("-", "_")
    compact = normalized.replace("_", "")
    return (
        normalized in _SENSITIVE_EXACT_KEYS
        or compact in _SENSITIVE_EXACT_KEYS
        or any(part in compact for part in _SENSITIVE_KEY_PARTS)
    )


def redact_for_log(value: Any) -> Any:
    """Return a redacted, log-safe copy of an API payload."""
    if isinstance(value, dict):
        return {
            key: _REDACTED if is_sensitive_key(key) else redact_for_log(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_for_log(item) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_for_log(item) for item in value)
    if isinstance(value, str):
        if len(value) > _MAX_STRING_LENGTH:
            return (
                f"{value[:_MAX_STRING_LENGTH]}"
                f"...[truncated {len(value) - _MAX_STRING_LENGTH} chars]"
            )
        return value
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value


def safe_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return only the non-sensitive headers useful for debugging regions."""
    lookup = {str(key).lower(): value for key, value in headers.items()}
    return {key: lookup[key] for key in _SAFE_HEADER_KEYS if key in lookup}
