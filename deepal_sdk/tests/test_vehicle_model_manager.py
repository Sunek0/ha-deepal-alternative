"""Tests for the official vehicle-model asset manager and view."""

from __future__ import annotations

import hashlib
import io
import json
import zipfile
from pathlib import Path

import pytest
from PIL import Image
from aiohttp import web

from custom_components.deepal.deepal import DeepalAPIError, Vehicle, VehicleModelAsset
from custom_components.deepal.model_assets import (
    DATA_MODEL_MANAGERS,
    REQUIRED_FILES,
    VehicleModelAssetManager,
    VehicleModelAssetView,
)
from custom_components.deepal.const import DOMAIN


class FakeHass:
    """Minimal Home Assistant object with the data registry."""

    def __init__(self) -> None:
        self.data: dict = {}


class FakeClient:
    """Client double that returns a prepared archive descriptor."""

    def __init__(self, content: bytes, md5: str | None = None) -> None:
        self.content = content
        self.md5 = md5
        self.get_calls = 0
        self.download_calls = 0
        self.get_error: Exception | None = None
        self.download_error: Exception | None = None

    async def get_vehicle_model(self, car_id: str, car_platform: int):
        self.get_calls += 1
        if self.get_error is not None:
            raise self.get_error
        return VehicleModelAsset(
            model_url="https://cdn.example/model.zip",
            md5=self.md5 or hashlib.md5(self.content).hexdigest(),
        )

    async def download_vehicle_model_archive(self, car_id: str, car_platform: int):
        self.download_calls += 1
        if self.download_error is not None:
            raise self.download_error
        return self.content


def _png_bytes() -> bytes:
    """Return a tiny valid PNG for the extraction tests."""
    buffer = io.BytesIO()
    Image.new("RGBA", (1, 1), (255, 0, 0, 255)).save(buffer, "PNG")
    return buffer.getvalue()


def _vehicle(car_id: str = "car-1") -> Vehicle:
    return Vehicle(car_id=car_id, vin="VIN-TEST", car_platform=2)


def _pack_bytes(
    *,
    prefix: str = "left/",
    seat_name: str = "carSeat.png",
    omit: set[str] | None = None,
    extra_metadata: bool = True,
) -> bytes:
    """Build a ZIP with every required file and optional metadata noise."""
    omit = omit or set()
    buffer = io.BytesIO()
    png = _png_bytes()
    with zipfile.ZipFile(buffer, "w") as archive:
        for names in REQUIRED_FILES.values():
            for name in names:
                if name in omit:
                    continue
                member = name
                if name == "seat/carSeat.png":
                    member = f"seat/{seat_name}"
                archive.writestr(prefix + member, png)
        if extra_metadata:
            archive.writestr(prefix + ".DS_Store", b"metadata")
            archive.writestr("__MACOSX/" + prefix + "._overlook/Ocar1.png", b"x")
    return buffer.getvalue()


def _manager(tmp_path: Path, content: bytes, md5: str | None = None):
    hass = FakeHass()
    client = FakeClient(content, md5=md5)
    return hass, client, VehicleModelAssetManager(hass, client, tmp_path)


@pytest.mark.asyncio
async def test_prefetch_extracts_and_advertises_categories(tmp_path: Path) -> None:
    hass, client, manager = _manager(tmp_path, _pack_bytes())
    notified: list[bool] = []
    manager.add_listener(lambda: notified.append(True))

    await manager.async_prefetch(_vehicle())

    status = manager.status("car-1")
    assert status is not None
    assert status.md5 == hashlib.md5(client.content).hexdigest()
    assert status.base_url == f"/deepal/vehicle_model/car-1/{manager.token}"
    assert set(status.categories) == set(REQUIRED_FILES)
    assert notified == [True]
    assert (status.version_dir / "overlook/Ocar1.png").is_file()
    assert (status.version_dir / "seat/carSeat.png").is_file()

    served = await manager.async_read_file("car-1", "overlook/Ocar1.png")
    assert served is not None
    assert served[0].startswith(b"\x89PNG")
    assert served[1] == "image/png"


@pytest.mark.asyncio
async def test_nested_archive_root_is_supported(tmp_path: Path) -> None:
    hass, client, manager = _manager(
        tmp_path, _pack_bytes(prefix="carModel/left/")
    )
    await manager.async_prefetch(_vehicle())

    status = manager.status("car-1")
    assert status is not None
    assert "status" in status.categories
    assert (status.version_dir / "overlook/Ocar1.png").is_file()


@pytest.mark.asyncio
async def test_cached_md5_skips_archive_download(tmp_path: Path) -> None:
    hass, client, manager = _manager(tmp_path, _pack_bytes())
    vehicle = _vehicle()

    await manager.async_prefetch(vehicle)
    assert client.download_calls == 1
    await manager.async_prefetch(vehicle)

    assert client.get_calls == 2
    assert client.download_calls == 1


@pytest.mark.asyncio
async def test_changed_md5_replaces_old_version(tmp_path: Path) -> None:
    hass, client, manager = _manager(tmp_path, _pack_bytes(), md5="a" * 32)
    vehicle = _vehicle()
    await manager.async_prefetch(vehicle)
    old_dir = manager.status("car-1").version_dir

    client.content = _pack_bytes(seat_name="carSeat1.png")
    client.md5 = "b" * 32
    await manager.async_prefetch(vehicle)

    status = manager.status("car-1")
    assert status is not None
    assert status.md5 == "b" * 32
    assert status.version_dir != old_dir
    assert not old_dir.exists()
    assert (status.version_dir / "seat/carSeat.png").is_file()


@pytest.mark.asyncio
async def test_download_failure_keeps_previous_version(tmp_path: Path) -> None:
    hass, client, manager = _manager(tmp_path, _pack_bytes(), md5="a" * 32)
    vehicle = _vehicle()
    await manager.async_prefetch(vehicle)
    previous = manager.status("car-1")

    client.md5 = "b" * 32
    client.download_error = DeepalAPIError("network down")
    await manager.async_prefetch(vehicle)

    assert manager.status("car-1") is previous
    assert previous is not None and previous.version_dir.is_dir()


@pytest.mark.asyncio
async def test_incomplete_pack_is_not_advertised(tmp_path: Path) -> None:
    hass, client, manager = _manager(
        tmp_path, _pack_bytes(omit={"battery/carBattery.png"})
    )
    await manager.async_prefetch(_vehicle())

    status = manager.status("car-1")
    assert status is not None
    assert "charging" not in status.categories
    assert "status" in status.categories


@pytest.mark.asyncio
async def test_unsafe_or_invalid_archive_is_rejected(tmp_path: Path) -> None:
    buffer = io.BytesIO()
    with zipfile.ZipFile(buffer, "w") as archive:
        archive.writestr("../evil.png", _png_bytes())
        archive.writestr("left/overlook/Ocar1.png", b"not a png")
    hass, client, manager = _manager(tmp_path, buffer.getvalue())

    await manager.async_prefetch(_vehicle())

    assert manager.status("car-1") is None
    assert not (tmp_path / "car-1").exists()


@pytest.mark.asyncio
async def test_cached_status_loads_without_network(tmp_path: Path) -> None:
    hass, client, manager = _manager(tmp_path, _pack_bytes())
    vehicle = _vehicle()
    await manager.async_prefetch(vehicle)

    second_hass = FakeHass()
    second_client = FakeClient(_pack_bytes())
    second = VehicleModelAssetManager(second_hass, second_client, tmp_path)
    await second.async_load([vehicle])

    assert second.status("car-1") is not None
    assert second_client.get_calls == 0
    assert second_client.download_calls == 0


@pytest.mark.asyncio
async def test_view_serves_cached_image_and_rejects_bad_paths(tmp_path: Path) -> None:
    hass, client, manager = _manager(tmp_path, _pack_bytes())
    await manager.async_prefetch(_vehicle())
    view = VehicleModelAssetView(hass)
    assert VehicleModelAssetView.requires_auth is False

    response = await view.get(None, "car-1", manager.token, "overlook/Ocar1.png")
    assert response.status == 200
    assert response.body.startswith(b"\x89PNG")
    assert response.content_type == "image/png"

    for car_id, token, path in (
        ("unknown", manager.token, "overlook/Ocar1.png"),
        ("car-1", "wrong-token", "overlook/Ocar1.png"),
        ("car-1", manager.token, "../meta.json"),
        ("car-1", manager.token, "overlook/Ocar1.txt"),
        ("car-1", manager.token, "meta.json"),
    ):
        with pytest.raises(web.HTTPNotFound):
            await view.get(None, car_id, token, path)


@pytest.mark.asyncio
async def test_shutdown_unregisters_vehicle(tmp_path: Path) -> None:
    hass, client, manager = _manager(tmp_path, _pack_bytes())
    await manager.async_prefetch(_vehicle())
    assert "car-1" in hass.data[DOMAIN][DATA_MODEL_MANAGERS]

    await manager.async_shutdown()

    assert "car-1" not in hass.data[DOMAIN][DATA_MODEL_MANAGERS]


@pytest.mark.asyncio
async def test_remove_cache_deletes_versions_and_status(tmp_path: Path) -> None:
    hass, client, manager = _manager(tmp_path, _pack_bytes())
    await manager.async_prefetch(_vehicle())
    assert (tmp_path / "car-1").is_dir()

    await manager.async_remove_cache()

    assert manager.status("car-1") is None
    assert not (tmp_path / "car-1").exists()
