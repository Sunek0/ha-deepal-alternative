"""Tests for the vehicle-model asset verifier script."""

import importlib.util
import io
import json
import sys
import zipfile
from pathlib import Path

import pytest
from PIL import Image

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "verify_vehicle_model_assets.py"

pytestmark = pytest.mark.skipif(
    not SCRIPT.exists(),
    reason="the asset verifier script is only present in the monorepo",
)


def _load_script():
    spec = importlib.util.spec_from_file_location(
        "verify_vehicle_model_assets", SCRIPT
    )
    module = importlib.util.module_from_spec(spec)
    assert spec.loader is not None
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


def test_layout_parser_maps_panel_paths() -> None:
    module = _load_script()
    assets = module.parse_layout_assets()

    by_profile_and_path = {
        (asset.profile, asset.category, asset.api_rel) for asset in assets
    }
    assert ("s07", "status", "overlook/Ocar1.png") in by_profile_and_path
    assert ("s07", "hero", "side/carDefault.png") in by_profile_and_path
    assert ("s07", "climate", "ac/carAc.png") in by_profile_and_path
    assert ("s07", "charging", "battery/carBattery.png") in by_profile_and_path
    assert ("s07", "seats", "seat/carSeat.png") in by_profile_and_path
    assert ("s05", "status", "overlook/Ocar1.png") in by_profile_and_path
    assert ("s05", "climate", "ac/carAc.png") in by_profile_and_path
    assert ("s05", "charging", "battery/carBattery.png") in by_profile_and_path
    assert not any(
        asset.profile == "s05" and asset.category == "seats" for asset in assets
    )


def test_normalize_member_aliases_and_orientation() -> None:
    module = _load_script()

    assert module.normalize_member("carModel/left/overlook/Ocar1.png") == (
        "overlook/Ocar1.png",
        None,
    )
    assert module.normalize_member("aa/carAc.png") == ("ac/carAc.png", None)
    assert module.normalize_member("bateria/chargingLineOn.png") == (
        "battery/chargingLineOn.png",
        None,
    )
    assert module.normalize_member("carSeat1.png") == ("seat/carSeat.png", None)
    assert module.normalize_member("Ocar1.png") == ("overlook/Ocar1.png", None)
    assert module.normalize_member("carDefault.png") == ("side/carDefault.png", None)
    assert module.normalize_member("right/overlook/Ocar1.png", "left")[0] is None
    assert module.normalize_member("../../etc/passwd")[0] is None


def test_self_check_passes(tmp_path: Path) -> None:
    module = _load_script()

    assert module.main(["--self-check", "--out", str(tmp_path)]) == 0
    report = json.loads((tmp_path / "report.json").read_text(encoding="utf-8"))
    assert report["packs"]["s07"]["geometry_ok"] is True
    assert report["packs"]["s05_bev"]["geometry_ok"] is True


def test_wrong_dimension_and_missing_files_fail(tmp_path: Path) -> None:
    module = _load_script()
    archive = tmp_path / "bad.zip"
    buffer = io.BytesIO()
    Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(buffer, "PNG")
    with zipfile.ZipFile(archive, "w") as bundle:
        bundle.writestr("overlook/Ocar1.png", buffer.getvalue())

    out = tmp_path / "report"
    assert module.main(["--s07-zip", str(archive), "--out", str(out)]) == 1
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    status = report["packs"]["s07"]["categories"]["status"]
    assert status["status"] == "missing"
    checks = {check["path"]: check for check in status["checks"]}
    assert checks["overlook/Ocar1.png"]["present"] is True
    assert checks["overlook/Ocar1.png"]["expected_size"] != checks["overlook/Ocar1.png"]["actual_size"]


def test_bev_and_phev_packs_are_compared(tmp_path: Path) -> None:
    module = _load_script()
    buffer = io.BytesIO()
    Image.new("RGBA", (4, 4), (0, 0, 255, 255)).save(buffer, "PNG")
    data = buffer.getvalue()
    for name in ("bev.zip", "phev.zip"):
        with zipfile.ZipFile(tmp_path / name, "w") as bundle:
            bundle.writestr("overlook/Ocar1.png", data)

    out = tmp_path / "report"
    assert (
        module.main(
            [
                "--s05-bev-zip",
                str(tmp_path / "bev.zip"),
                "--s05-phev-zip",
                str(tmp_path / "phev.zip"),
                "--out",
                str(out),
                "--allow-partial",
            ]
        )
        == 0
    )
    report = json.loads((out / "report.json").read_text(encoding="utf-8"))
    assert report["s05_bev_vs_phev"]["conclusion"] == "identical"
