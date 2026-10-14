"""Charging session tracking for the Deepal Alternative integration.

Pure logic, with no Home Assistant imports, so the session rules can be
unit-tested on their own (``deepal_sdk/tests/test_charging.py``). The manager
receives a duck-typed store (``async_load``, ``async_delay_save``,
``async_remove``): the integration passes a
``homeassistant.helpers.storage.Store`` and the tests a fake.

Rules, mirroring upstream ``dec_deepal``'s ``charging.py`` (MIT):

- A session starts when the charging flag turns on, keeping the start time and
  the battery level and range of that moment. Values that arrive later in the
  same session fill the missing start fields.
- The session closes when the flag turns off. A session shorter than two
  minutes that gained no battery level is discarded as charger flapping; every
  other closed session becomes the last completed one.
- Unknown levels or ranges stay unknown instead of zero.
"""

from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Optional

from .deepal.mqtt import charge_is_active

CURRENT = "current"
LAST = "last"

#: A "charge" shorter than this that gained no battery is the car doubting
#: while plugging in, not a charge.
MIN_SECONDS = 120

_START_FIELDS = ("start", "start_level", "start_range")
_END_FIELDS = ("end", "end_level", "end_range")


def charging_flag(condition: Any) -> Optional[bool]:
    """Return whether a condition reports the car charging (``None`` = unknown).

    The S05 reports ``ChrgSts`` as a charging-state enum whose connected-only
    values (1 and 2) used to read as "charging": for those snapshots only the
    charging states 3 and 4 are on. Vehicles that do not report ``ChrgSts``
    (the SDA broker, the REST condition) keep the previous any-non-zero
    behaviour until their enum is confirmed.
    """
    status = condition.battery.charging_status
    if status is None:
        return None
    raw = getattr(condition, "mqtt_raw_data", None) or {}
    if "ChrgSts" in raw:
        return charge_is_active(status)
    return str(status) not in ("0", "None")


def _number(value: Any) -> Optional[float]:
    """Return a plain number or ``None`` (booleans do not count)."""
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        return None
    return value


def _session(raw: Any, fields: tuple[str, ...]) -> Optional[dict[str, Any]]:
    """Return one stored session, keeping only the fields that are understood."""
    if not isinstance(raw, Mapping):
        return None
    session: dict[str, Any] = {}
    for field in fields:
        value = raw.get(field)
        if field in ("start", "end"):
            if not isinstance(value, str):
                return None
            try:
                datetime.fromisoformat(value)
            except ValueError:
                return None
            session[field] = value
        else:
            session[field] = _number(value)
    return session


def clean(raw: Any) -> dict[str, Any]:
    """Return the sessions that validate; anything unreadable is discarded."""
    if not isinstance(raw, Mapping):
        return {}
    state: dict[str, Any] = {}
    if (current := _session(raw.get(CURRENT), _START_FIELDS)) is not None:
        state[CURRENT] = current
    if (last := _session(raw.get(LAST), _START_FIELDS + _END_FIELDS)) is not None:
        state[LAST] = last
    return state


def update(
    state: Optional[Mapping[str, Any]],
    charging: Optional[bool],
    level: Optional[float],
    range_km: Optional[float],
    now: datetime,
) -> tuple[dict[str, Any], bool]:
    """Advance one vehicle's sessions with a reading.

    Safe to call repeatedly with the same reading: only transitions change the
    state. Returns the new state and whether it changed.
    """
    result = clean(state)
    current = result.get(CURRENT)
    stamp = now.isoformat(timespec="seconds")
    level, range_km = _number(level), _number(range_km)

    if charging is True:
        if current is None:
            result[CURRENT] = {
                "start": stamp,
                "start_level": level,
                "start_range": range_km,
            }
            return result, True
        # The level can arrive a moment after the "charging" flag.
        changed = False
        for field, value in (("start_level", level), ("start_range", range_km)):
            if current.get(field) is None and value is not None:
                current[field] = value
                changed = True
        return result, changed

    if charging is False and current is not None:
        del result[CURRENT]
        seconds = (now - datetime.fromisoformat(current["start"])).total_seconds()
        gained = (
            level is not None
            and current.get("start_level") is not None
            and level > current["start_level"]
        )
        if seconds >= MIN_SECONDS or gained:
            result[LAST] = {
                **current,
                "end": stamp,
                "end_level": level,
                "end_range": range_km,
            }
        return result, True

    return result, False


def _known_fields(**fields: Any) -> dict[str, Any]:
    """Return the fields that are known, omitting unknown values."""
    return {key: value for key, value in fields.items() if value is not None}


def attributes(state: Optional[Mapping[str, Any]]) -> dict[str, Any]:
    """Return the session attributes the charging entity exposes."""
    state = state or {}
    result: dict[str, Any] = {}
    if current := state.get(CURRENT):
        result["current_charge"] = _known_fields(
            start=current["start"],
            start_level=current.get("start_level"),
            start_range=current.get("start_range"),
        )
    if last := state.get(LAST):
        result["last_charge"] = _known_fields(
            start=last["start"],
            end=last["end"],
            start_level=last.get("start_level"),
            end_level=last.get("end_level"),
            start_range=last.get("start_range"),
            end_range=last.get("end_range"),
        )
    return result


class ChargingSessionManager:
    """Track every vehicle's sessions and persist them through a store.

    The store is duck-typed (``async_load``, ``async_delay_save``,
    ``async_remove``) so this class stays importable without Home Assistant.
    """

    SAVE_DELAY = 5.0

    def __init__(self, store: Any) -> None:
        self._store = store
        self._sessions: dict[str, dict[str, Any]] = {}

    async def async_load(self) -> None:
        """Restore the stored sessions; an unreadable store starts empty."""
        try:
            raw = await self._store.async_load()
        except Exception:  # noqa: BLE001 - a broken store must not fail setup
            raw = None
        sessions: dict[str, dict[str, Any]] = {}
        if isinstance(raw, Mapping):
            for car_id, state in raw.items():
                cleaned = clean(state)
                if cleaned:
                    sessions[str(car_id)] = cleaned
        self._sessions = sessions

    def apply(
        self,
        car_id: str,
        charging: Optional[bool],
        level: Optional[float],
        range_km: Optional[float],
        now: datetime,
    ) -> None:
        """Feed one reading into a vehicle's sessions and save when it changed."""
        state, changed = update(
            self._sessions.get(car_id), charging, level, range_km, now
        )
        if not changed:
            return
        if state:
            self._sessions[car_id] = state
        else:
            self._sessions.pop(car_id, None)
        self._store.async_delay_save(self._snapshot, self.SAVE_DELAY)

    def attributes(self, car_id: str) -> dict[str, Any]:
        """Return the attributes for one vehicle's charging entity."""
        return attributes(self._sessions.get(car_id))

    async def async_remove(self) -> None:
        """Drop every session and remove the stored data."""
        self._sessions = {}
        await self._store.async_remove()

    def _snapshot(self) -> dict[str, Any]:
        return dict(self._sessions)
