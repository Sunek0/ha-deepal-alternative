"""Tests for the bundled dashboard card and its static delivery.

The tests exercise the static-path and Lovelace-resource registration without
starting a Home Assistant runtime: a fake hass records the static paths and the
resource calls. The card itself is checked through the generated bundle and its
source modules; no browser is required.
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
from custom_components.deepal.const import (
    DOMAIN,
    FRONTEND_ASSETS_URL,
    FRONTEND_JS_URL,
    VERSION,
)

from homeassistant.components.lovelace.const import LOVELACE_DATA

MANIFEST = REPO_ROOT / "custom_components" / "deepal" / "manifest.json"


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
        config_entries=SimpleNamespace(async_entries=lambda domain: list(entries)),
    )
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=FakeResources())
    return hass


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
    paths = [config.url_path for config in hass.http.registered[0]]
    assert paths == [FRONTEND_JS_URL, FRONTEND_ASSETS_URL]


@pytest.mark.asyncio
async def test_bundle_is_auto_loaded_once(monkeypatch: pytest.MonkeyPatch) -> None:
    loaded: list[str] = []
    monkeypatch.setattr(
        frontend_module, "add_extra_js_url", lambda hass, url: loaded.append(url)
    )
    hass = _fake_hass()

    await frontend_module.async_register_frontend(hass)
    await frontend_module.async_register_frontend(hass)

    assert loaded == [f"{FRONTEND_JS_URL}?v={VERSION}"]


@pytest.mark.asyncio
async def test_auto_load_failure_is_contained(monkeypatch: pytest.MonkeyPatch) -> None:
    def boom(hass, url):
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
    resources.items = [
        {"id": "ours", "url": f"{FRONTEND_JS_URL}?v=1.0.0", "res_type": "module"}
    ]

    await frontend_module.async_register_frontend(hass)

    assert resources.updated == [
        ("ours", {"url": f"{FRONTEND_JS_URL}?v={VERSION}"})
    ]
    assert resources.deleted == []


@pytest.mark.asyncio
async def test_unversioned_bundle_resource_is_moved_to_the_current_version() -> None:
    hass = _fake_hass()
    resources = hass.data[LOVELACE_DATA].resources
    resources.items = [{"id": "ours", "url": FRONTEND_JS_URL, "res_type": "module"}]

    await frontend_module.async_register_frontend(hass)

    assert resources.updated == [
        ("ours", {"url": f"{FRONTEND_JS_URL}?v={VERSION}"})
    ]


@pytest.mark.asyncio
async def test_resource_registration_is_skipped_without_resources() -> None:
    hass = _fake_hass()
    hass.data[LOVELACE_DATA] = SimpleNamespace(resources=None)

    await frontend_module.async_register_frontend(hass)

    assert hass.data[DOMAIN].get(frontend_module.DATA_FRONTEND_REGISTERED)


@pytest.mark.asyncio
async def test_unregister_removes_only_our_resource() -> None:
    hass = _fake_hass()
    resources = hass.data[LOVELACE_DATA].resources
    resources.items = [
        {"id": "ours", "url": f"{FRONTEND_JS_URL}?v=1.0.0", "res_type": "module"},
        {"id": "other", "url": "/hacsfiles/other/other.js", "res_type": "module"},
    ]

    await frontend_module.async_unregister_frontend(hass)

    assert resources.deleted == ["ours"]
    assert [item["id"] for item in resources.items] == ["other"]


@pytest.mark.asyncio
async def test_already_registered_path_is_not_an_error() -> None:
    hass = _fake_hass(http_error=RuntimeError("already registered"))

    await frontend_module.async_register_frontend(hass)
    await frontend_module.async_register_frontend(hass)

    assert hass.http.attempts == 1


@pytest.mark.asyncio
async def test_static_path_failure_is_contained_and_retried() -> None:
    hass = _fake_hass(http_error=ValueError("boom"))

    await frontend_module.async_register_frontend(hass)
    await frontend_module.async_register_frontend(hass)

    assert hass.http.attempts == 2


# --- Removed panel and strategy -------------------------------------------


def test_panel_module_is_gone() -> None:
    assert not (REPO_ROOT / "custom_components" / "deepal" / "panel.py").exists()
    assert not (REPO_ROOT / "custom_components" / "deepal" / "frontend" / "panel" / "src" / "80_strategy.js").exists()


def test_manifest_does_not_depend_on_panel_custom() -> None:
    manifest = json.loads(MANIFEST.read_text(encoding="utf-8"))
    assert "panel_custom" not in manifest.get("dependencies", [])
    assert "panel_custom" not in manifest.get("after_dependencies", [])


def test_panel_option_is_gone_from_config_flow() -> None:
    assert not hasattr(config_flow_module.DeepalConfigFlow, "async_step_panel")
    assert not hasattr(config_flow_module, "_panel_schema")
    assert "show_panel" not in (
        REPO_ROOT / "custom_components" / "deepal" / "config_flow.py"
    ).read_text(encoding="utf-8")


def test_panel_translations_are_gone() -> None:
    files = [
        REPO_ROOT / "custom_components" / "deepal" / "strings.json",
        *sorted((REPO_ROOT / "custom_components" / "deepal" / "translations").glob("*.json")),
    ]
    for path in files:
        data = json.loads(path.read_text(encoding="utf-8"))
        assert "panel" not in data.get("config", {}).get("step", {}), path
        assert "show_panel" not in (
            data.get("options", {}).get("step", {}).get("init", {}).get("data", {})
        ), path


# --- Generated card bundle ------------------------------------------------


SRC = REPO_ROOT / "custom_components" / "deepal" / "frontend" / "panel" / "src"
BUNDLE = SRC.parent / "deepal-frontend.js"
ASSETS = REPO_ROOT / "custom_components" / "deepal" / "frontend" / "assets"


def test_bundle_registers_one_card_and_its_editor() -> None:
    bundle = BUNDLE.read_text(encoding="utf-8")

    assert 'const CARD_TAG = "deepal-card";' in bundle
    assert "class DeepalCard extends DeepalCardBase" in bundle
    assert "class DeepalCardSettings" in bundle
    assert "class DeepalCardEditor" in bundle
    assert '"deepal-card-settings"' in bundle
    assert '"deepal-card-editor"' in bundle


def test_bundle_does_not_register_removed_surfaces() -> None:
    bundle = BUNDLE.read_text(encoding="utf-8")

    assert 'custom:deepal-compact-card' not in bundle
    assert 'const PANEL_TAG = "deepal-panel"' not in bundle
    assert "DeepalDashboardStrategy" not in bundle
    assert "DeepalVehicleViewStrategy" not in bundle
    assert "window.customStrategies" not in bundle
    assert "ll-strategy-dashboard-deepal" not in bundle


def test_bundle_has_the_configurable_hero_and_sections() -> None:
    source = (SRC / "70_card.js").read_text(encoding="utf-8")

    for marker in [
        "_renderHero",
        "_sectionActions",
        "_sectionStatus",
        "_sectionInfo",
        "_sectionDiagnostics",
        "hero_style",
        "hero_show",
        "CARD_SECTIONS",
        "settings-change",
    ]:
        assert marker in source, marker


def test_bundle_has_no_panel_selector_or_tabs() -> None:
    source = (SRC / "50_card.js").read_text(encoding="utf-8")

    assert "data-action=\"select-vehicle\"" not in source
    assert "role=\"tablist\"" not in source
    assert "PANEL_TABS" not in source


# --- Profile layouts and assets ------------------------------------------


def _layout_referenced_assets() -> list[str]:
    """Every asset path quoted by the per-model layout constants."""
    source = (SRC / "10_constants.js").read_text(encoding="utf-8")
    return sorted(set(re.findall(r'"((?:s05|s07)/[^"]+\.(?:png|webm))"', source)))


def test_profile_layout_assets_ship_on_disk() -> None:
    """Every file a model layout references must exist under frontend/assets."""
    assets = _layout_referenced_assets()

    assert len(assets) >= 55
    assert any(path.startswith("s05/") for path in assets)
    assert any(path.startswith("s07/") for path in assets)
    assert any(path.endswith(".webm") for path in assets)
    missing = [path for path in assets if not (ASSETS / path).is_file()]
    assert missing == []


def test_asset_url_prefers_the_dynamic_pack_and_falls_back() -> None:
    """The built asset resolver maps panel paths to the official pack."""
    node = shutil.which("node")
    if node is None:
        pytest.skip("node is not installed")

    constants = (SRC / "10_constants.js").read_text(encoding="utf-8")
    helpers = (SRC / "40_helpers.js").read_text(encoding="utf-8")
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
    """The S05 isometric block references all state pieces."""
    source = (SRC / "10_constants.js").read_text(encoding="utf-8")
    start = source.index("compact: {")
    end = source.index("climate: {", start)
    compact = source[start:end]

    assert 'base: "s05/estado_isometrico/car1.png"' in compact
    for key in COMPACT_LAYER_KEYS:
        assert f"{key}:" in compact, key
    for path in COMPACT_ASSETS:
        assert f'"{path}"' in compact, path


def test_compact_assets_share_the_isometric_canvas() -> None:
    """Every compact layer must align on the 750x500 isometric canvas."""
    from PIL import Image

    for path in COMPACT_ASSETS:
        asset = ASSETS / path
        assert asset.is_file(), path
        with Image.open(asset) as image:
            assert image.size == (750, 500), path
            assert image.convert("RGBA").getchannel("A").getbbox() is not None, path


def test_card_prefers_state_artwork_and_falls_back() -> None:
    """The hero tries the state artwork before the API image."""
    source = (SRC / "70_card.js").read_text(encoding="utf-8")
    compact = "vehicleCompactStageHtml(hass, vehicle)"
    photo = "vehiclePhotoHtml(hass, vehicle)"

    assert compact in source
    assert photo in source
    assert source.index(compact) < source.index(photo)


def test_card_renderer_keeps_the_documented_layer_order() -> None:
    """The isometric layers must stay in their staged behind/front order."""
    source = (SRC / "45_vehicle.js").read_text(encoding="utf-8")
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


def test_spanish_lock_label_is_centralizado() -> None:
    """The Spanish vitals label reads 'Cierre centralizado'."""
    texts = json.loads(
        (SRC.parent / "texts" / "es.json").read_text(encoding="utf-8")
    )

    assert texts["central_lock"] == "Cierre centralizado"


def test_card_texts_cover_the_integration_languages() -> None:
    """Every language the integration ships has a complete card text file."""
    texts_dir = SRC.parent / "texts"
    texts = {
        path.stem: json.loads(path.read_text(encoding="utf-8"))
        for path in texts_dir.glob("*.json")
    }
    integration_languages = {
        path.stem
        for path in (
            REPO_ROOT / "custom_components" / "deepal" / "translations"
        ).glob("*.json")
    }

    assert set(texts) == integration_languages
    reference = set(texts["en"])
    for code, values in texts.items():
        assert set(values) == reference, code
        assert all(isinstance(value, str) and value for value in values.values()), code


def test_language_selector_lists_every_shipped_language() -> None:
    """The selector is built from the shipped texts, not a hardcoded pair."""
    source = (SRC / "70_card.js").read_text(encoding="utf-8")
    constants = (SRC / "10_constants.js").read_text(encoding="utf-8")
    bundle = BUNDLE.read_text(encoding="utf-8")

    assert source.index('["auto", "automatic"]') < source.index(
        "Object.keys(PANEL_TEXTS)"
    )
    for name in ("English", "Español", "Deutsch", "Français", "Italiano", "Português"):
        assert f'"{name}"' in constants, name
    for code in ("de", "en", "es", "fr", "it", "pt"):
        assert f'  "{code}": {{' in bundle, code
