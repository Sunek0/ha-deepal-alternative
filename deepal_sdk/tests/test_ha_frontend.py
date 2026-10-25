"""Tests for the bundled vehicle panel registration.

The tests exercise the static-path and panel registration without starting a
Home Assistant runtime: a fake hass records the static paths and the
``panel_custom`` call, and the unregistration rules are checked with fake
config entries.
"""

import json
import re
import shutil
import subprocess
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
        self.updated: list[tuple[str, dict]] = []
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

    async def async_update_item(self, item_id, updates):
        self.updated.append((item_id, updates))
        for item in self.items:
            if item.get("id") == item_id:
                item.update(updates)
        return next(item for item in self.items if item.get("id") == item_id)

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
    assert resources.created == [
        {"res_type": "module", "url": f"{FRONTEND_JS_URL}?v={VERSION}"}
    ]


@pytest.mark.asyncio
async def test_existing_bundle_resource_is_moved_to_the_current_version() -> None:
    hass = _fake_hass()
    resources = hass.data[LOVELACE_DATA].resources
    resources.items.append(
        {"id": "old", "url": f"{FRONTEND_JS_URL}?v=1.0.0", "res_type": "module"}
    )

    await frontend_module.async_register_frontend(hass)

    assert resources.created == []
    assert resources.updated == [
        ("old", {"url": f"{FRONTEND_JS_URL}?v={VERSION}"})
    ]


@pytest.mark.asyncio
async def test_unversioned_bundle_resource_is_moved_to_the_current_version() -> None:
    hass = _fake_hass()
    resources = hass.data[LOVELACE_DATA].resources
    resources.items.append(
        {"id": "legacy", "url": FRONTEND_JS_URL, "res_type": "module"}
    )

    await frontend_module.async_register_frontend(hass)

    assert resources.created == []
    assert resources.updated == [
        ("legacy", {"url": f"{FRONTEND_JS_URL}?v={VERSION}"})
    ]


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


# --- Profile layout assets -------------------------------------------------

PANEL_SRC = (
    REPO_ROOT / "custom_components" / "deepal" / "frontend" / "panel" / "src"
)
PANEL_ASSETS = REPO_ROOT / "custom_components" / "deepal" / "frontend" / "assets"


def _layout_referenced_assets() -> list[str]:
    """Every asset path quoted by the per-model layout constants."""
    source = (PANEL_SRC / "10_constants.js").read_text(encoding="utf-8")
    return sorted(set(re.findall(r'"((?:s05|s07)/[^"]+\.(?:png|webm))"', source)))


def test_profile_layout_assets_ship_on_disk() -> None:
    """Every file a model layout references must exist under frontend/assets."""
    assets = _layout_referenced_assets()

    assert len(assets) >= 55  # a broken pattern must never pass silently
    assert any(path.startswith("s05/") for path in assets)
    assert any(path.startswith("s07/") for path in assets)
    assert any(path.endswith(".webm") for path in assets)
    missing = [path for path in assets if not (PANEL_ASSETS / path).is_file()]
    assert missing == []


def test_asset_url_prefers_the_dynamic_pack_and_falls_back(tmp_path: Path) -> None:
    """The built asset resolver maps panel paths to the official pack."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    constants = (PANEL_SRC / "10_constants.js").read_text(encoding="utf-8")
    helpers = (PANEL_SRC / "40_helpers.js").read_text(encoding="utf-8")
    script = f"""
const vm = require("vm");
const source = {json.dumps(constants + "\n" + helpers)};
const sandbox = {{ PANEL_VERSION: "1" }};
vm.createContext(sandbox);
vm.runInContext(
  source + "\\n;globalThis.__assetUrl = assetUrl; globalThis.__discoverVehicles = discoverVehicles;",
  sandbox,
);
const vehicle = {{
  modelAssets: {{
    base: "/deepal/vehicle_model/car-1",
    categories: ["status", "hero", "climate", "charging", "seats"],
    md5: "abc123",
  }},
}};
const cases = [
  ["s05/estado_planta/Ocar1.png", "/deepal/vehicle_model/car-1/overlook/Ocar1.png?v=abc123"],
  ["s07/aa/carAc.png", "/deepal/vehicle_model/car-1/ac/carAc.png?v=abc123"],
  ["s07/bateria/carBattery.png", "/deepal/vehicle_model/car-1/battery/carBattery.png?v=abc123"],
  ["s07/asientos/carSeat.png", "/deepal/vehicle_model/car-1/seat/carSeat.png?v=abc123"],
  ["s07/anim/anim_air_start_left.webm", "/deepal/frontend/assets/s07/anim/anim_air_start_left.webm?v=1"],
];
for (const [path, expected] of cases) {{
  const actual = sandbox.__assetUrl(path, vehicle);
  if (actual !== expected) {{
    console.error(path, "->", actual, "expected", expected);
    process.exit(1);
  }}
}}
const fallback = sandbox.__assetUrl("s07/aa/carAc.png", {{ modelAssets: null }});
if (fallback !== "/deepal/frontend/assets/s07/aa/carAc.png?v=1") process.exit(1);

const hass = {{
  entities: {{
    "image.car-1": {{
      platform: "deepal",
      device_id: "dev-1",
      translation_key: "vehicle_image",
      entity_id: "image.car-1",
    }},
  }},
  devices: {{ "dev-1": {{ name: "My S05", model: "Deepal S05" }} }},
  states: {{
    "image.car-1": {{
      attributes: {{
        model_assets_base: "/deepal/vehicle_model/car-1",
        model_assets_categories: ["status", "hero"],
        model_assets_md5: "abc123",
      }},
    }},
  }},
}};
const [discovered] = sandbox.__discoverVehicles(hass);
if (!discovered || discovered.modelAssets.base !== "/deepal/vehicle_model/car-1") {{
  process.exit(1);
}}
if (discovered.profile !== "s05_ev") process.exit(1);
"""
    result = subprocess.run(
        [node, "-e", script], capture_output=True, text=True, check=False
    )
    assert result.returncode == 0, result.stderr
COMPACT_ASSETS = [
    "s05/estado_isometrico/car1.png",
    "s05/estado_isometrico/hood0.png",
    "s05/estado_isometrico/hood1.png",
    "s05/estado_isometrico/trunk0.png",
    "s05/estado_isometrico/trunk1.png",
    "s05/estado_isometrico/LF0.png",
    "s05/estado_isometrico/LF1.png",
    "s05/estado_isometrico/RF0.png",
    "s05/estado_isometrico/RF1.png",
    "s05/estado_isometrico/LB0.png",
    "s05/estado_isometrico/LB1.png",
    "s05/estado_isometrico/RB0.png",
    "s05/estado_isometrico/RB1.png",
    "s05/estado_isometrico/LF0-outline.png",
    "s05/estado_isometrico/RF0-outline.png",
    "s05/estado_isometrico/LB0-outline.png",
    "s05/estado_isometrico/RB0-outline.png",
    "s05/estado_isometrico/windowsLF0.png",
    "s05/estado_isometrico/openDoor-windowsLF0.png",
    "s05/estado_isometrico/windowsRF0.png",
    "s05/estado_isometrico/openDoor-windowsRF0.png",
    "s05/estado_isometrico/windowsLB0.png",
    "s05/estado_isometrico/openDoor-windowsLB0.png",
    "s05/estado_isometrico/windowsRB0.png",
    "s05/estado_isometrico/openDoor-windowsRB0.png",
    "s05/estado_isometrico/lowBeam1.png",
]

COMPACT_LAYER_KEYS = [
    "hood_closed",
    "hood_open",
    "trunk_closed",
    "trunk_open",
    "door_front_left_closed",
    "door_front_left_open",
    "door_front_left_outline",
    "door_front_right_closed",
    "door_front_right_open",
    "door_front_right_outline",
    "door_rear_left_closed",
    "door_rear_left_open",
    "door_rear_left_outline",
    "door_rear_right_closed",
    "door_rear_right_open",
    "door_rear_right_outline",
    "window_front_left_closed",
    "window_front_left_closed_door_open",
    "window_front_right_closed",
    "window_front_right_closed_door_open",
    "window_rear_left_closed",
    "window_rear_left_closed_door_open",
    "window_rear_right_closed",
    "window_rear_right_closed_door_open",
    "lights_on",
]


def test_compact_layout_ships_every_state_layer() -> None:
    """The S05 compact block references all isometric state pieces."""
    source = (PANEL_SRC / "10_constants.js").read_text(encoding="utf-8")
    start = source.index("compact: {")
    end = source.index("climate: {", start)
    compact = source[start:end]

    assert "base: \"s05/estado_isometrico/car1.png\"" in compact
    for key in COMPACT_LAYER_KEYS:
        assert f"{key}:" in compact, key
    for path in COMPACT_ASSETS:
        assert f'"{path}"' in compact, path


def test_compact_assets_share_the_isometric_canvas() -> None:
    """Every compact layer must align on the 750x500 isometric canvas."""
    from PIL import Image

    for path in COMPACT_ASSETS:
        asset = PANEL_ASSETS / path
        assert asset.is_file(), path
        with Image.open(asset) as image:
            assert image.size == (750, 500), path
            assert image.convert("RGBA").getchannel("A").getbbox() is not None, path


def test_compact_card_prefers_state_artwork() -> None:
    """The compact card must try the layered picture before the API image."""
    source = (PANEL_SRC / "70_card.js").read_text(encoding="utf-8")
    compact = "vehicleCompactStageHtml(this._hass, vehicle)"
    photo = "vehiclePhotoHtml(this._hass, vehicle)"

    assert compact in source
    assert photo in source
    assert source.index(compact) < source.index(photo)


def test_compact_renderer_keeps_the_documented_layer_order() -> None:
    """The isometric layers must stay in their staged behind/front order."""
    source = (PANEL_SRC / "45_vehicle.js").read_text(encoding="utf-8")
    markers = [
        'side("rear_right");',
        'side("front_right");',
        "add(layers.trunk_closed);",
        "add(layout.base);",
        "add(layers.trunk_open);",
        'add(on("hood") ? layers.hood_open : layers.hood_closed);',
        'side("rear_left");',
        'side("front_left");',
        "open-door-outline",
    ]
    positions = [source.index(marker) for marker in markers]

    assert positions == sorted(positions)
    assert "outlines.push(layers[`door_${position}_outline`]);" in source


def test_status_view_rotates_the_stage_and_keeps_only_the_lock_chip() -> None:
    """The complete card and panel share the rotated, lock-only status view."""
    source = (PANEL_SRC / "60_status.js").read_text(encoding="utf-8")

    assert "vehicleStageHtml(hass, vehicle, { rotate: true })" in source
    assert "vehicleLockChipHtml(hass, vehicle, t)" in source
    assert "vehicleChipsHtml" not in source


def test_stage_rotation_is_limited_to_the_status_class() -> None:
    """Rotation and the 750:550 crop are a status-only class."""
    source = (PANEL_SRC / "30_styles.js").read_text(encoding="utf-8")

    assert ".stage-status.stage-rotated { aspect-ratio: 750 / 550; }" in source
    assert "transform: translateY(-50%) rotate(-90deg);" in source
    assert ".stage-status { aspect-ratio: 1 / 1; }" in source


def test_status_uses_the_lock_chip_helper_without_the_old_chip_row() -> None:
    """The shared chip helper is only the central-locking chip now."""
    source = (PANEL_SRC / "45_vehicle.js").read_text(encoding="utf-8")

    assert "function vehicleLockChipHtml(hass, vehicle, t)" in source
    assert "vehicleChipsHtml" not in source
    assert "anyDoorOpen" not in source


def test_compact_card_has_no_chips_under_the_picture() -> None:
    """The compact card keeps the state in the picture, not in a chip row."""
    source = (PANEL_SRC / "70_card.js").read_text(encoding="utf-8")

    assert "vehicleCompactStageHtml(this._hass, vehicle)" in source
    assert "vehicleChipsHtml" not in source
    assert '<div class="chips">' not in source


def test_spanish_lock_label_is_centralizado() -> None:
    """The Spanish vitals label reads 'Cierre centralizado'."""
    texts = json.loads(
        (PANEL_SRC.parent / "texts" / "es.json").read_text(encoding="utf-8")
    )

    assert texts["central_lock"] == "Cierre centralizado"


# --- Dashboard strategies --------------------------------------------------

BUNDLE = (
    REPO_ROOT
    / "custom_components"
    / "deepal"
    / "frontend"
    / "panel"
    / "deepal-frontend.js"
)


def test_bundle_registers_the_dashboard_strategies() -> None:
    """The built bundle must define and advertise the dashboard strategies."""
    bundle = BUNDLE.read_text(encoding="utf-8")

    assert "class DeepalDashboardStrategy" in bundle
    assert "class DeepalVehicleViewStrategy" in bundle
    assert '"ll-strategy-dashboard-deepal"' in bundle
    assert '"ll-strategy-view-deepal-vehicle"' in bundle
    assert "window.customStrategies" in bundle
    assert 'strategyType: "dashboard"' in bundle
