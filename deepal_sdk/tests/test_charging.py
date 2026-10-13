"""Tests for the charging-session tracker."""

from datetime import UTC, datetime, timedelta
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

from custom_components.deepal.charging import (
    ChargingSessionManager,
    attributes,
    charging_flag,
    clean,
    update,
)

START = datetime(2026, 10, 13, 12, 0, 0, tzinfo=UTC)
START_STAMP = START.isoformat(timespec="seconds")


def _condition(charging_status):
    return SimpleNamespace(battery=SimpleNamespace(charging_status=charging_status))


def test_charging_flag_reads_the_status():
    assert charging_flag(_condition("2")) is True
    assert charging_flag(_condition("0")) is False
    assert charging_flag(_condition(None)) is None


def test_session_starts_with_the_current_values():
    state, changed = update(None, True, 40, 210, START)

    assert changed is True
    assert state["current"] == {
        "start": START_STAMP,
        "start_level": 40,
        "start_range": 210,
    }


def test_late_values_fill_the_start():
    state, _ = update(None, True, None, None, START)
    state, changed = update(state, True, 42, 215, START + timedelta(minutes=1))

    assert changed is True
    assert state["current"]["start"] == START_STAMP
    assert state["current"]["start_level"] == 42
    assert state["current"]["start_range"] == 215


def test_unknown_values_stay_unknown():
    state, _ = update(None, True, None, None, START)

    assert state["current"]["start_level"] is None
    assert state["current"]["start_range"] is None
    assert attributes(state)["current_charge"] == {"start": START_STAMP}


def test_repeating_a_reading_changes_nothing():
    state, _ = update(None, True, 40, 210, START)
    same, changed = update(state, True, 40, 210, START + timedelta(seconds=30))

    assert changed is False
    assert same == state


def test_unknown_charging_leaves_the_state_alone():
    state, _ = update(None, True, 40, 210, START)
    same, changed = update(state, None, 40, 210, START + timedelta(minutes=1))

    assert changed is False
    assert same == state


def test_short_flap_is_discarded():
    state, _ = update(None, True, 40, 200, START)
    state, changed = update(state, False, 40, 200, START + timedelta(seconds=30))

    assert changed is True
    assert "current" not in state
    assert "last" not in state


def test_short_session_with_gain_is_kept():
    state, _ = update(None, True, 40, 200, START)
    state, _ = update(state, False, 41, 205, START + timedelta(seconds=30))

    assert state["last"]["end"] == (START + timedelta(seconds=30)).isoformat(
        timespec="seconds"
    )
    assert state["last"]["start_level"] == 40
    assert state["last"]["end_level"] == 41


def test_long_session_is_kept_without_gain():
    state, _ = update(None, True, 40, 200, START)
    state, _ = update(state, False, 40, 200, START + timedelta(minutes=5))

    assert state["last"]["start_level"] == 40
    assert state["last"]["end_level"] == 40


def test_attributes_omit_unknown_fields():
    state, _ = update(None, True, 40, None, START)

    assert attributes(state)["current_charge"] == {
        "start": START_STAMP,
        "start_level": 40,
    }


def test_clean_discards_malformed_sessions():
    assert clean("not-a-mapping") == {}
    assert clean({"current": {"start": "not-a-date"}}) == {}
    assert clean({"last": {"start": START_STAMP, "start_level": 1}}) == {}

    kept = clean({"current": {"start": START_STAMP, "start_level": 40}})
    assert kept["current"]["start_level"] == 40


class _FakeStore:
    """Store double recording what the manager persists."""

    def __init__(self, raw=None) -> None:
        self.raw = raw
        self.saved: list[dict] = []
        self.removed = 0

    async def async_load(self):
        return self.raw

    def async_delay_save(self, data, delay):
        self.saved.append(data())

    async def async_remove(self):
        self.removed += 1


@pytest.mark.asyncio
async def test_manager_restores_sessions_from_the_store():
    stored = {
        "car-1": {
            "last": {
                "start": START_STAMP,
                "end": (START + timedelta(hours=1)).isoformat(timespec="seconds"),
                "start_level": 40,
                "end_level": 80,
                "start_range": 210,
                "end_range": 380,
            }
        }
    }
    manager = ChargingSessionManager(_FakeStore(stored))

    await manager.async_load()

    assert manager.attributes("car-1")["last_charge"]["end_level"] == 80
    assert manager.attributes("car-2") == {}


@pytest.mark.asyncio
async def test_manager_tolerates_a_broken_store():
    class _BrokenStore:
        async def async_load(self):
            raise RuntimeError("boom")

        def async_delay_save(self, data, delay):
            raise AssertionError("must not save")

        async def async_remove(self):
            raise AssertionError("must not be called")

    manager = ChargingSessionManager(_BrokenStore())

    await manager.async_load()

    assert manager.attributes("car-1") == {}


@pytest.mark.asyncio
async def test_manager_saves_only_when_a_session_changes():
    store = _FakeStore()
    manager = ChargingSessionManager(store)
    await manager.async_load()

    manager.apply("car-1", True, 40, 200, START)
    assert len(store.saved) == 1
    assert store.saved[0]["car-1"]["current"]["start_level"] == 40

    manager.apply("car-1", True, 40, 200, START + timedelta(seconds=30))
    assert len(store.saved) == 1


@pytest.mark.asyncio
async def test_manager_removes_the_store():
    store = _FakeStore({"car-1": {"current": {"start": START_STAMP}}})
    manager = ChargingSessionManager(store)
    await manager.async_load()

    await manager.async_remove()

    assert store.removed == 1
    assert manager.attributes("car-1") == {}
