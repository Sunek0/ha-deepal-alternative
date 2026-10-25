"""Log redaction helpers for API payloads and headers."""

from __future__ import annotations

import re
from typing import Any

_REDACTED = "[redacted]"
_MAX_STRING_LENGTH = 500
_VDP_TOPIC_PREFIX = "$vdp/"
_JWT = re.compile(r"^eyJ[\w-]+\.[\w-]+\.[\w-]+$")
_SAFE_HEADER_KEYS = (
    "selectcountry",
    "appversion",
    "language",
    "x-os-version",
    "x-tsp-timestamp",
    "x-vcs-timestamp",
)

#: Shared sensitive-key model: the SDK log redaction and the Home Assistant
#: diagnostics report both decide with this list through ``is_sensitive_key``.
_SENSITIVE_EXACT_KEYS = {
    "access_token",
    "address",
    "authcode",
    "authorization",
    "brokerurl",
    "cac_token",
    "cactoken",
    "car_id",
    "carid",
    "cid",
    "clientid",
    "control_pin",
    "credential",
    "device_id",
    "devicedid",
    "deviceid",
    "did",
    "email",
    "gps",
    "imageurl",
    "imgurl",
    "lat",
    "latitude",
    "licenseplate",
    "lng",
    "lon",
    "longitude",
    "mobile",
    "otp",
    "passwd",
    "password",
    "phone",
    "platenumber",
    "position",
    "private_key",
    "private_key_pem",
    "privatekey",
    "pubkey",
    "public_key",
    "publickey",
    "rctoken",
    "refresh_token",
    "ruid",
    "safecode",
    "secretkey",
    "serialno",
    "seriralno",
    "sign",
    "smscode",
    "thumbnailurl",
    "token",
    "uid",
    "user_id",
    "userid",
    "username",
    "vehicleid",
    "vehiclevin",
    "vin",
    "vincode",
}

_SENSITIVE_KEY_PARTS = (
    "authorization",
    "bearer",
    "credential",
    "email",
    "latitude",
    "longitude",
    "mobile",
    "password",
    "passwd",
    "pem",
    "phone",
    "pin",
    "plate",
    "private",
    "rctoken",
    "secret",
    "serial",
    "signature",
    "sms",
    "token",
    "vehicleid",
    # "key" tampoco: "unlockKeyDrivingStatus" lo contiene. Las claves que lo
    # llevan quedan cubiertas por nombre exacto ("pubkey", "secretkey") o por
    # otras partes ("secret" en secretKey).
    # "vin" NO va aquí: "driving" lo contiene y ocultaba claves inocentes como
    # "unlockKeyDrivingStatus". El VIN se oculta por nombre exacto (EXACT_KEYS).
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


def redact_for_log(value: Any, max_string_length: int = _MAX_STRING_LENGTH) -> Any:
    """Return a redacted, log-safe copy of an API payload.

    ``max_string_length`` bounds every string in the copy. The log default is
    deliberately small; diagnostics capture can pass a larger bound.
    """
    if isinstance(value, dict):
        return {
            key: _REDACTED if is_sensitive_key(key) else redact_for_log(
                item, max_string_length
            )
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [redact_for_log(item, max_string_length) for item in value]
    if isinstance(value, tuple):
        return tuple(redact_for_log(item, max_string_length) for item in value)
    if isinstance(value, str):
        if _JWT.match(value):
            return _REDACTED
        if len(value) > max_string_length:
            return (
                f"{value[:max_string_length]}"
                f"...[truncated {len(value) - max_string_length} chars]"
            )
        return value
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value


def redact_topic(topic: str) -> str:
    """Mask the device segment of a ``$vdp/<did>/...`` MQTT topic."""
    if not isinstance(topic, str) or not topic.startswith(_VDP_TOPIC_PREFIX):
        return topic
    parts = topic.split("/")
    if len(parts) > 1:
        parts[1] = _REDACTED
    return "/".join(parts)


def redact_mqtt_request_id(value: Any) -> Any:
    """Mask the device prefix of an MQTT ``<did>_<timestamp>`` request id."""
    if not isinstance(value, str):
        return value
    prefix, separator, suffix = value.rpartition("_")
    if separator and prefix and suffix.isdigit():
        return f"{_REDACTED}_{suffix}"
    return value


def safe_headers(headers: dict[str, str]) -> dict[str, str]:
    """Return only the non-sensitive headers useful for debugging regions."""
    lookup = {str(key).lower(): value for key, value in headers.items()}
    return {key: lookup[key] for key in _SAFE_HEADER_KEYS if key in lookup}
