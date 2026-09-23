"""Digital key support and authorization models.

The authorization payload shape has not been observed live: the European SDA
gateway does not deploy the ``car-permission-api`` service, so parsing accepts
the common list keys and keeps any unknown codes. The support contract was
verified live on the SDA gateway (``query-supported-featured``).
"""

from typing import Any, Literal, Optional

from pydantic import BaseModel, Field

DIGITAL_KEY_FUNCTION_CODE = "DigitalKey"

# Phone support protocol returned by query-supported-featured, recovered from
# DigitalInnerConstantsKt (PHONE_SUPPORT_*). The value selects which key scheme
# the phone should use, not a ROM/client limitation.
PHONE_SUPPORT_CA_KEY = 0
PHONE_SUPPORT_ICCE_KEY = 1
PHONE_SUPPORT_HONOR_KEY = 2

DigitalKeyKeyType = Literal["ca", "icce", "honor", "unknown"]

_AUTHORIZATION_LIST_KEYS = (
    "authList",
    "carAuthList",
    "functionList",
    "functionCodes",
    "list",
    "records",
    "data",
)

_AUTHORIZATION_CODE_KEYS = ("functionCode", "code", "authCode", "function")


def _extract_codes(payload: Any) -> list[str]:
    """Extract function codes from a tolerant set of possible payload shapes."""
    if isinstance(payload, list):
        items: Any = payload
    elif isinstance(payload, dict):
        items = None
        for key in _AUTHORIZATION_LIST_KEYS:
            value = payload.get(key)
            if isinstance(value, list):
                items = value
                break
    else:
        items = None

    if not isinstance(items, list):
        return []

    codes: list[str] = []
    for item in items:
        if isinstance(item, str):
            codes.append(item)
        elif isinstance(item, dict):
            for key in _AUTHORIZATION_CODE_KEYS:
                value = item.get(key)
                if isinstance(value, str):
                    codes.append(value)
                    break
    return codes


class DigitalKeySupport(BaseModel):
    """Phone-side digital key scheme reported by the gateway."""

    flag: int = Field(description="Raw flag returned by query-supported-featured")
    key_type: DigitalKeyKeyType = Field(
        description="Key scheme the phone should use: ca, icce, honor or unknown"
    )
    raw: dict[str, Any] = Field(
        default_factory=dict, description="Raw response data for diagnostics"
    )

    @property
    def supported(self) -> bool:
        """Return whether the gateway reported a known key scheme."""
        return self.key_type != "unknown"

    @classmethod
    def from_flag(
        cls, flag: int, raw: Optional[dict[str, Any]] = None
    ) -> "DigitalKeySupport":
        """Build the typed support result from the gateway flag."""
        if flag == PHONE_SUPPORT_CA_KEY:
            key_type: DigitalKeyKeyType = "ca"
        elif flag == PHONE_SUPPORT_ICCE_KEY:
            key_type = "icce"
        elif flag == PHONE_SUPPORT_HONOR_KEY:
            key_type = "honor"
        else:
            key_type = "unknown"
        return cls(flag=flag, key_type=key_type, raw=raw or {})


class VehicleAuthorizations(BaseModel):
    """Per-vehicle function authorization list reported by the app backend."""

    raw_codes: list[str] = Field(
        default_factory=list, description="Raw function codes"
    )
    digital_key: bool = Field(
        default=False,
        description="Whether the DigitalKey function code is authorized",
    )
    raw: dict[str, Any] = Field(
        default_factory=dict, description="Raw response data for diagnostics"
    )

    def has_code(self, code: str) -> bool:
        """Return whether the raw list contains the given function code."""
        return code in self.raw_codes

    @classmethod
    def from_payload(cls, payload: Any) -> "VehicleAuthorizations":
        """Build the typed authorization from a tolerant payload parse."""
        codes = _extract_codes(payload)
        return cls(
            raw_codes=codes,
            digital_key=DIGITAL_KEY_FUNCTION_CODE in codes,
            raw=payload if isinstance(payload, dict) else {"data": payload},
        )
