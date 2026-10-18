"""Vehicle position extraction from condition payloads.

Ported from dec_deepal v2.5.1 (MIT, https://github.com/manuelem1984/dec_deepal):
the position keys are searched case-insensitively at any nesting depth, the
latitude is paired with the longitude of the same object, and `(0, 0)` or
out-of-range readings are discarded.
"""

from __future__ import annotations

from typing import Any, Optional

_LATITUDE_KEYS = frozenset({"lat", "latitude"})
_LONGITUDE_KEYS = frozenset({"lng", "lon", "longitude"})
_MAX_DEPTH = 6


def find_location(*sources: Any) -> Optional[tuple[float, float]]:
    """Return the first valid ``(latitude, longitude)`` found in the sources."""
    for source in sources:
        found = _search(source, _MAX_DEPTH)
        if found is not None:
            return found
    return None


def _search(node: Any, depth: int) -> Optional[tuple[float, float]]:
    if depth < 0:
        return None
    if isinstance(node, dict):
        latitude = None
        longitude = None
        for key, value in node.items():
            name = str(key).lower()
            if name in _LATITUDE_KEYS:
                latitude = _coerce(value)
            elif name in _LONGITUDE_KEYS:
                longitude = _coerce(value)
        if (
            latitude is not None
            and longitude is not None
            and _valid(latitude, longitude)
        ):
            return (latitude, longitude)
        for value in node.values():
            found = _search(value, depth - 1)
            if found is not None:
                return found
    elif isinstance(node, (list, tuple)):
        for item in node:
            found = _search(item, depth - 1)
            if found is not None:
                return found
    return None


def _coerce(value: Any) -> Optional[float]:
    if value is None or isinstance(value, bool):
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _valid(latitude: float, longitude: float) -> bool:
    if not (-90.0 <= latitude <= 90.0 and -180.0 <= longitude <= 180.0):
        return False
    return not (latitude == 0.0 and longitude == 0.0)
