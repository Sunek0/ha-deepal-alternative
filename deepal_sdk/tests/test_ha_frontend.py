"""Tests for the bundled vehicle panel registration.

The tests exercise the static-path and panel registration without starting a
Home Assistant runtime: a fake hass records the static paths and the
``panel_custom`` call, and the unregistration rules are checked with fake
config entries.
"""

import json
import sys
from pathlib import Path
from types import SimpleNamespace

import pytest

pytest.importorskip("homeassistant")

REPO_ROOT = Path(__file__).resolve().parents[2]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

from custom_components.deepal import config_flow as config_flow_module
from custom_components.deepal import frontend as frontend_module
from custom_components.deepal import panel as panel_module
from custom_components.deepal.const import (
    CONF_SHOW_PANEL,
    DOMAIN,
    FRONTEND_ASSETS_URL,
    FRONTEND_JS_URL,
    PANEL_ELEMENT,
    PANEL_URL_PATH,
    VERSION,
)

from homeassistant.components.lovelace.const import LOVELACE_DATA

MANIFEST = (
    REPO_ROOT / "custom_components" / "deepal" / "manifest.json"
)


class FakeHttp:
    """Records the static paths the integration registers."""

    def __init__(self, error: Exception | None = None) -> None:
        self.registered: list[list] = []
        self.attempts = 0
        self.error = error

    async def async_register_static_paths(self, configs) -> None:
        self.attempts += 1
        if self.error is not None:
            raise self.error
        self.registered.append(list(configs))


class FakeConfigEntries:
    """Returns every entry regardless of domain, like the real registry."""

    def __init__(self, entries) -> None:
        self._entries = list(entries)

    def async_entries(self, domain: str):
        return list(self._entries)

    def remove(self, entry) -> None:
        self._entries.remove(entry)


class FakeResources:
    """Records the Lovelace resource calls made by the integration."""

    def __init__(self, items=None) -> None:
        self.items = list(items or [])
        self.created: list[dict] = []
        self.deleted: list[str] = []

    async def async_get_info(self) -> None:
        return None

    def async_items(self):
        return list(self.items)

    async def async_create_item(self, data):
        self.created.append(data)
        item = {"id": f"item-{len(self.created)}", **data}
        self.items.append(item)
        return item

    async def async_delete_item(self, item_id) -> None:
        self.deleted.append(item_id)
        self.items = [item for item in self.items if item.get("id") != item_id]


def _fake_hass(entries=(), http_error: Exception | None = None) -> SimpleNamespace:
    hass = SimpleNamespace(
        data={},
        http=FakeHttp(http_error),
        config_entries=FakeConfigEntries(entries),
    )
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=FakeResources())
    return hass


def _entry(entry_id: str, options: dict | None = None) -> SimpleNamespace:
    return SimpleNamespace(entry_id=entry_id, options=dict(options or {}))


def test_version_matches_the_manifest() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert VERSION == manifest["version"]
    assert VERSION != "0"


@pytest.mark.asyncio
async def test_static_paths_are_registered_once_per_run() -> None:
    hass = _fake_hass()

    await frontend_module.async_register_frontend(hass)
    await frontend_module.async_register_frontend(hass)

    assert hass.http.attempts == 1
    configs = hass.http.registered[0]
    urls = {config.url_path for config in configs}
    assert urls == {FRONTEND_JS_URL, FRONTEND_ASSETS_URL}
    assert all(config.cache_headers is False for config in configs)


@pytest.mark.asyncio
async def test_bundle_is_auto_loaded_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    loaded: list[str] = []
    monkeypatch.setattr(
        frontend_module, "add_extra_js_url", lambda hass, url: loaded.append(url)
    )
    hass = _fake_hass()

    await frontend_module.async_register_frontend(hass)
    await frontend_module.async_register_frontend(hass)

    assert loaded == [f"{FRONTEND_JS_URL}?v={VERSION}"]


@pytest.mark.asyncio
async def test_auto_load_failure_is_contained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def boom(hass, url) -> None:
        raise RuntimeError("no frontend here")

    monkeypatch.setattr(frontend_module, "add_extra_js_url", boom)
    hass = _fake_hass()

    await frontend_module.async_register_frontend(hass)

    assert hass.data[DOMAIN].get(frontend_module.DATA_FRONTEND_REGISTERED)


@pytest.mark.asyncio
async def test_bundle_resource_is_registered_once() -> None:
    hass = _fake_hass()

    await frontend_module.async_register_frontend(hass)
    await frontend_module.async_register_frontend(hass)

    resources = hass.data[LOVELACE_DATA].resources
    assert resources.created == [{"res_type": "module", "url": FRONTEND_JS_URL}]


@pytest.mark.asyncio
async def test_existing_bundle_resource_is_not_duplicated() -> None:
    hass = _fake_hass()
    resources = hass.data[LOVELACE_DATA].resources
    resources.items.append(
        {"id": "old", "url": f"{FRONTEND_JS_URL}?v=1.0.0", "res_type": "module"}
    )

    await frontend_module.async_register_frontend(hass)

    assert resources.created == []


@pytest.mark.asyncio
async def test_resource_registration_is_skipped_without_resources() -> None:
    hass = _fake_hass()
    # YAML-mode resources expose no collection to write to.
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=SimpleNamespace())

    await frontend_module.async_register_frontend(hass)

    assert hass.data[DOMAIN].get(frontend_module.DATA_FRONTEND_REGISTERED)


@pytest.mark.asyncio
async def test_resource_failure_is_contained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    hass = _fake_hass()

    async def boom(data) -> None:
        raise RuntimeError("no lovelace here")

    monkeypatch.setattr(
        hass.data[LOVELACE_DATA].resources, "async_create_item", boom
    )

    await frontend_module.async_register_frontend(hass)

    assert hass.data[DOMAIN].get(frontend_module.DATA_FRONTEND_REGISTERED)


@pytest.mark.asyncio
async def test_unregister_removes_only_our_resource() -> None:
    hass = _fake_hass()
    resources = hass.data[LOVELACE_DATA].resources
    resources.items.extend(
        [
            {"id": "ours", "url": f"{FRONTEND_JS_URL}?v=1.0.0", "res_type": "module"},
            {"id": "other", "url": "/hacsfiles/other/other.js", "res_type": "module"},
        ]
    )

    await frontend_module.async_unregister_frontend(hass)

    assert resources.deleted == ["ours"]
    assert [item["id"] for item in resources.items] == ["other"]


@pytest.mark.asyncio
async def test_already_registered_path_is_not_an_error() -> None:
    hass = _fake_hass(http_error=RuntimeError("already registered"))

    await frontend_module.async_register_frontend(hass)
    await frontend_module.async_register_frontend(hass)

    # The first attempt raised the runtime error; the second one is skipped.
    assert hass.http.attempts == 1


@pytest.mark.asyncio
async def test_static_path_failure_is_contained_and_retried() -> None:
    hass = _fake_hass(http_error=ValueError("boom"))

    await frontend_module.async_register_frontend(hass)
    await frontend_module.async_register_frontend(hass)

    # No exception escaped and the failed flag was not kept, so a later
    # setup can try again.
    assert hass.http.attempts == 2


@pytest.mark.asyncio
async def test_panel_is_registered_once_with_the_expected_options(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    async def fake_register_panel(hass, **kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(
        panel_module.panel_custom, "async_register_panel", fake_register_panel
    )
    hass = _fake_hass()

    await panel_module.async_register_panel(hass)
    await panel_module.async_register_panel(hass)

    assert len(calls) == 1
    kwargs = calls[0]
    assert kwargs["frontend_url_path"] == PANEL_URL_PATH
    assert kwargs["webcomponent_name"] == PANEL_ELEMENT
    assert kwargs["require_admin"] is False
    assert "config_panel_domain" not in kwargs
    assert kwargs["sidebar_title"] == "Deepal"
    assert kwargs["sidebar_icon"] == "mdi:car-electric"
    assert kwargs["module_url"] == f"{FRONTEND_JS_URL}?v={VERSION}"


@pytest.mark.asyncio
async def test_panel_registration_failure_is_contained(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = 0

    async def fake_register_panel(hass, **kwargs) -> None:
        nonlocal calls
        calls += 1
        raise RuntimeError("no panel_custom here")

    monkeypatch.setattr(
        panel_module.panel_custom, "async_register_panel", fake_register_panel
    )
    hass = _fake_hass()

    await panel_module.async_register_panel(hass)
    assert calls == 1
    assert not hass.data[DOMAIN].get(panel_module.DATA_PANEL_REGISTERED)

    # The flag was not kept, so a later setup can try again.
    await panel_module.async_register_panel(hass)
    assert calls == 2


@pytest.mark.asyncio
async def test_unregister_removes_the_panel_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_register_panel(hass, **kwargs) -> None:
        return None

    removed: list[str] = []

    def fake_remove_panel(hass, url_path) -> None:
        removed.append(url_path)

    monkeypatch.setattr(
        panel_module.panel_custom, "async_register_panel", fake_register_panel
    )
    monkeypatch.setattr(panel_module.frontend, "async_remove_panel", fake_remove_panel)
    hass = _fake_hass()

    await panel_module.async_register_panel(hass)
    panel_module.async_unregister_panel(hass)
    panel_module.async_unregister_panel(hass)

    assert removed == [PANEL_URL_PATH]


@pytest.mark.asyncio
async def test_panel_survives_while_other_entries_remain(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    async def fake_register_panel(hass, **kwargs) -> None:
        return None

    removed: list[str] = []

    def fake_remove_panel(hass, url_path) -> None:
        removed.append(url_path)

    monkeypatch.setattr(
        panel_module.panel_custom, "async_register_panel", fake_register_panel
    )
    monkeypatch.setattr(panel_module.frontend, "async_remove_panel", fake_remove_panel)

    first = _entry("entry-1")
    second = _entry("entry-2")
    hass = _fake_hass(entries=[first, second])
    await panel_module.async_register_panel(hass)

    panel_module.async_unregister_panel_if_unwanted(hass, first)
    assert removed == []

    # The first entry is gone from the registry when the second is removed.
    hass.config_entries.remove(first)
    panel_module.async_unregister_panel_if_unwanted(hass, second)
    assert removed == [PANEL_URL_PATH]


@pytest.mark.asyncio
async def test_panel_sync_registers_when_any_account_wants_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls: list[dict] = []

    async def fake_register_panel(hass, **kwargs) -> None:
        calls.append(kwargs)

    monkeypatch.setattr(
        panel_module.panel_custom, "async_register_panel", fake_register_panel
    )
    hass = _fake_hass(
        entries=[
            _entry("opt-out", {CONF_SHOW_PANEL: False}),
            _entry("opt-in", {CONF_SHOW_PANEL: True}),
        ]
    )

    await panel_module.async_sync_panel(hass)

    assert len(calls) == 1


@pytest.mark.asyncio
async def test_panel_sync_skips_it_when_everyone_opts_out(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: list[dict] = []
    removed: list[str] = []

    async def fake_register_panel(hass, **kwargs) -> None:
        registered.append(kwargs)

    def fake_remove_panel(hass, url_path) -> None:
        removed.append(url_path)

    monkeypatch.setattr(
        panel_module.panel_custom, "async_register_panel", fake_register_panel
    )
    monkeypatch.setattr(panel_module.frontend, "async_remove_panel", fake_remove_panel)
    hass = _fake_hass(entries=[_entry("opt-out", {CONF_SHOW_PANEL: False})])

    await panel_module.async_sync_panel(hass)

    assert registered == []
    assert removed == []


@pytest.mark.asyncio
async def test_panel_sync_removes_it_when_everyone_opts_out_later(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: list[dict] = []
    removed: list[str] = []

    async def fake_register_panel(hass, **kwargs) -> None:
        registered.append(kwargs)

    def fake_remove_panel(hass, url_path) -> None:
        removed.append(url_path)

    monkeypatch.setattr(
        panel_module.panel_custom, "async_register_panel", fake_register_panel
    )
    monkeypatch.setattr(panel_module.frontend, "async_remove_panel", fake_remove_panel)
    hass = _fake_hass(entries=[_entry("account", {CONF_SHOW_PANEL: True})])

    await panel_module.async_sync_panel(hass)
    assert len(registered) == 1

    hass.config_entries._entries = [_entry("account", {CONF_SHOW_PANEL: False})]
    await panel_module.async_sync_panel(hass)

    assert removed == [PANEL_URL_PATH]


@pytest.mark.asyncio
async def test_legacy_entries_keep_the_panel(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    registered: list[dict] = []

    async def fake_register_panel(hass, **kwargs) -> None:
        registered.append(kwargs)

    monkeypatch.setattr(
        panel_module.panel_custom, "async_register_panel", fake_register_panel
    )
    hass = _fake_hass(entries=[_entry("legacy")])

    await panel_module.async_sync_panel(hass)

    assert len(registered) == 1


def test_panel_step_defaults_to_disabled() -> None:
    marker = next(iter(config_flow_module._panel_schema().schema))

    assert marker.default() is False


@pytest.mark.asyncio
async def test_panel_step_stores_the_choice() -> None:
    flow = config_flow_module.DeepalConfigFlow()
    flow._pending_title = "Deepal Account"
    flow._pending_data = {"platform": "intl"}

    enabled = await flow.async_step_panel({CONF_SHOW_PANEL: True})

    assert enabled["type"].value == "create_entry"
    assert enabled["options"] == {CONF_SHOW_PANEL: True}
    assert enabled["data"] == {"platform": "intl"}

    disabled = await flow.async_step_panel({})

    assert disabled["options"] == {CONF_SHOW_PANEL: False}
