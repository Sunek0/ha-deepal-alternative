"""Persistence helpers for the last known vehicle condition.

After a Home Assistant restart the coordinator has no previous condition, so
every value the car did not report in the first poll (dashboard warning
lights, the last position, ...) would be unknown until the car wakes up again.
The last published condition is stored and used only as the *previous* state
of the existing merge rules, so a value is kept until the car reports a new
one and is never presented as a fresh report.

The module has no Home Assistant imports so it can be tested on its own.
"""

from __future__ import annotations

import logging
from typing import Any

_LOGGER = logging.getLogger(__name__)

#: Fields that are not state: identifiers and bulky diagnostics payloads.
SNAPSHOT_EXCLUDE = frozenset(
    {"car_id", "vin", "raw_data", "mqtt_raw_data", "mqtt_variants", "sda_plan"}
)

SNAPSHOT_VERSION = 1


def conditions_to_snapshot(conditions: dict[str, Any] | None) -> dict[str, Any]:
    """Return the JSON-serializable snapshot of the published conditions."""
    return {
        "conditions": {
            car_id: condition.model_dump(mode="json", exclude=SNAPSHOT_EXCLUDE)
            for car_id, condition in (conditions or {}).items()
        }
    }


def conditions_from_snapshot(model: Any, stored: Any) -> dict[str, Any]:
    """Rebuild the stored conditions; an unreadable entry is skipped."""
    restored: dict[str, Any] = {}
    if not isinstance(stored, dict):
        return restored
    conditions = stored.get("conditions")
    if not isinstance(conditions, dict):
        return restored
    for car_id, payload in conditions.items():
        if not isinstance(payload, dict):
            continue
        try:
            restored[car_id] = model(
                **{
                    key: value
                    for key, value in payload.items()
                    if key not in SNAPSHOT_EXCLUDE
                },
                car_id=car_id,
                vin="",
            )
        except (ValueError, TypeError) as err:
            _LOGGER.debug("Deepal stored condition for a vehicle ignored: %s", err)
    return restored
