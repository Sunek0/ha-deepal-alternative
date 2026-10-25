"""Download, cache and serve the official layered vehicle-model images."""

from __future__ import annotations

import asyncio
import hashlib
import hmac
import io
import json
import logging
import re
import secrets
import shutil
import stat
import zipfile
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path
from typing import Callable, Iterable

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.core import HomeAssistant

from .const import DOMAIN
from .deepal import DeepalError, DeepalIntlClient, Vehicle

_LOGGER = logging.getLogger(__name__)

CACHE_DIR = ".storage/deepal_vehicle_model"
VIEW_URL = "/deepal/vehicle_model"
DATA_MODEL_MANAGERS = "vehicle_model_managers"
DATA_MODEL_ENTRIES = "vehicle_model_entries"
DATA_VIEW_REGISTERED = "vehicle_model_view_registered"

#: The panel expects the complete set before a category can be used. A partial
#: pack falls back to the bundled art instead of rendering missing layers.
REQUIRED_FILES: dict[str, tuple[str, ...]] = {
    "status": (
        "overlook/Ocar1.png",
        "overlook/Ohood0.png",
        "overlook/Ohood1.png",
        "overlook/Otrunk0.png",
        "overlook/Otrunk1.png",
        "overlook/OLF0.png",
        "overlook/OLF1.png",
        "overlook/ORF0.png",
        "overlook/ORF1.png",
        "overlook/OLB0.png",
        "overlook/OLB1.png",
        "overlook/ORB0.png",
        "overlook/ORB1.png",
        "overlook/OwindowsLF1.png",
        "overlook/OwindowsRF1.png",
        "overlook/OwindowsLB1.png",
        "overlook/OwindowsRB1.png",
        "overlook/OopenDoor-windowsLF1.png",
        "overlook/OopenDoor-windowsRF1.png",
        "overlook/OopenDoor-windowsLB1.png",
        "overlook/OopenDoor-windowsRB1.png",
        "overlook/OlowBeam1.png",
    ),
    "hero": ("side/carDefault.png",),
    "climate": ("ac/carAc.png", "ac/carAcOpen.png"),
    "charging": (
        "battery/carBattery.png",
        "battery/chargingLineOff.png",
        "battery/chargingLineOn.png",
    ),
    "seats": ("seat/carSeat.png",),
}
CATEGORY_DIRS = {"overlook", "side", "ac", "battery", "seat"}
ALLOWED_IMAGE_TYPES = {".png": "image/png", ".webp": "image/webp"}
MAX_FILE_BYTES = 20 * 1024 * 1024
MAX_TOTAL_BYTES = 100 * 1024 * 1024
ORIENTATION = "left"


@dataclass(frozen=True)
class ModelAssetStatus:
    """Availability of the extracted model pack for one vehicle."""

    car_id: str
    md5: str
    version_dir: Path
    categories: tuple[str, ...]
    base_url: str


def _cache_root(hass: HomeAssistant, override: Path | None) -> Path:
    """Return the model-asset cache root."""
    if override is not None:
        return Path(override)
    return Path(hass.config.path(CACHE_DIR))


class VehicleModelAssetManager:
    """Per-entry manager for the official layered model packs."""

    def __init__(
        self,
        hass: HomeAssistant,
        client: DeepalIntlClient,
        cache_root: Path | None = None,
    ) -> None:
        self.hass = hass
        self.client = client
        self.cache_root = _cache_root(hass, cache_root)
        self._status: dict[str, ModelAssetStatus] = {}
        self._locks: dict[str, asyncio.Lock] = {}
        self._listeners: set[Callable[[], None]] = set()
        self._registered: set[str] = set()
        self._closed = False
        # The browser loads these images with <img>, so it cannot attach an
        # Authorization header. A per-manager unguessable token protects the
        # public view without requiring the HA session cookie.
        self.token = secrets.token_urlsafe(24)

    async def async_load(self, vehicles: Iterable[Vehicle]) -> None:
        """Advertise cached packs before the background refresh starts."""
        for vehicle in vehicles:
            if re.fullmatch(r"[A-Za-z0-9_-]+", vehicle.car_id) is None:
                continue
            status = await asyncio.to_thread(self._load_cached_status, vehicle.car_id)
            if status is not None:
                self._status[vehicle.car_id] = status
                self._register_vehicle(vehicle.car_id)

    async def async_prefetch_vehicles(self, vehicles: Iterable[Vehicle]) -> None:
        """Refresh every vehicle pack without blocking setup or polling."""
        for vehicle in vehicles:
            if self._closed:
                return
            try:
                await self.async_prefetch(vehicle)
            except asyncio.CancelledError:
                raise
            except Exception as err:  # noqa: BLE001 - starts a static fallback
                _LOGGER.debug(
                    "Deepal model-asset refresh failed for %s: %s",
                    vehicle.car_id,
                    err,
                )

    async def async_prefetch(self, vehicle: Vehicle) -> None:
        """Fetch the descriptor and download a changed pack for one vehicle."""
        car_id = vehicle.car_id
        platform = vehicle.car_platform
        if (
            self._closed
            or platform is None
            or re.fullmatch(r"[A-Za-z0-9_-]+", car_id) is None
        ):
            return
        lock = self._locks.setdefault(car_id, asyncio.Lock())
        async with lock:
            if self._closed:
                return
            try:
                descriptor = await self.client.get_vehicle_model(car_id, platform)
            except DeepalError as err:
                _LOGGER.debug(
                    "Deepal model descriptor unavailable for %s: %s", car_id, err
                )
                return

            cached = self._status.get(car_id)
            if (
                cached is not None
                and descriptor.md5
                and cached.md5.lower() == descriptor.md5.lower()
            ):
                refreshed = await asyncio.to_thread(
                    self._status_from_dir, car_id, cached.version_dir
                )
                if refreshed is not None:
                    self._status[car_id] = refreshed
                    self._register_vehicle(car_id)
                    return

            try:
                content = await self.client.download_vehicle_model_archive(
                    car_id, platform
                )
            except DeepalError as err:
                _LOGGER.debug(
                    "Deepal model archive unavailable for %s: %s", car_id, err
                )
                return

            if self._closed:
                return
            digest = (descriptor.md5 or "").lower()
            if re.fullmatch(r"[0-9a-f]{32}", digest) is None:
                digest = hashlib.md5(content).hexdigest()
            if cached is not None and cached.md5 == digest:
                self._register_vehicle(car_id)
                return

            try:
                status = await asyncio.to_thread(
                    self._extract, car_id, digest, content
                )
            except Exception as err:  # noqa: BLE001 - untrusted archive
                _LOGGER.warning(
                    "Deepal model archive for %s was rejected: %s", car_id, err
                )
                return

            if self._closed:
                return
            self._status[car_id] = status
            self._register_vehicle(car_id)
            await asyncio.to_thread(self._cleanup_old_versions, car_id, status)
            self._notify()

    def status(self, car_id: str) -> ModelAssetStatus | None:
        """Return the current pack status of a vehicle."""
        return self._status.get(car_id)

    def add_listener(self, listener: Callable[[], None]) -> None:
        """Register a callback fired when a pack becomes available or changes."""
        self._listeners.add(listener)

    def remove_listener(self, listener: Callable[[], None]) -> None:
        """Remove a previously registered callback."""
        self._listeners.discard(listener)

    async def async_shutdown(self) -> None:
        """Stop accepting work and remove the view registry entries."""
        self._closed = True
        managers = self.hass.data.get(DOMAIN, {}).get(DATA_MODEL_MANAGERS, {})
        for car_id in self._registered:
            managers.pop(car_id, None)
        self._registered.clear()
        self._listeners.clear()

    async def async_remove_cache(self) -> None:
        """Remove every cached version owned by this entry."""
        car_ids = set(self._status) | set(self._registered)
        for car_id in car_ids:
            await asyncio.to_thread(
                shutil.rmtree, self.cache_root / car_id, ignore_errors=True
            )
        self._status.clear()
        await self.async_shutdown()

    async def async_read_file(
        self, car_id: str, relative_path: str
    ) -> tuple[bytes, str] | None:
        """Read one cached image, rejecting traversal and non-image files."""
        status = self._status.get(car_id)
        if status is None:
            return None
        cleaned = relative_path.replace("\\", "/")
        parts = [part for part in cleaned.split("/") if part not in ("", ".")]
        if not parts or ".." in parts or cleaned.startswith("/"):
            return None
        suffix = Path(cleaned).suffix.lower()
        content_type = ALLOWED_IMAGE_TYPES.get(suffix)
        if content_type is None:
            return None
        version_root = status.version_dir.resolve()
        target = (status.version_dir / cleaned).resolve()
        if target == version_root or version_root not in target.parents:
            return None
        if not await asyncio.to_thread(target.is_file):
            return None
        try:
            data = await asyncio.to_thread(target.read_bytes)
        except OSError:
            return None
        return data, content_type

    def base_url(self, car_id: str) -> str:
        """Return the token-protected base URL of a vehicle's pack."""
        return f"{VIEW_URL}/{car_id}/{self.token}"

    def _register_vehicle(self, car_id: str) -> None:
        """Make the manager discoverable by the authenticated view."""
        managers = self.hass.data.setdefault(DOMAIN, {}).setdefault(
            DATA_MODEL_MANAGERS, {}
        )
        managers[car_id] = self
        self._registered.add(car_id)

    def _notify(self) -> None:
        """Notify image entities that the pack availability changed."""
        for listener in list(self._listeners):
            try:
                listener()
            except Exception as err:  # noqa: BLE001 - a listener must not break the task
                _LOGGER.debug("Deepal model-asset listener failed: %s", err)

    def _load_cached_status(self, car_id: str) -> ModelAssetStatus | None:
        """Return the newest valid cache of one vehicle, if any."""
        car_root = self.cache_root / car_id
        if not car_root.is_dir():
            return None
        candidates = sorted(
            (path for path in car_root.iterdir() if path.is_dir()),
            key=lambda path: path.stat().st_mtime,
            reverse=True,
        )
        for version_dir in candidates:
            status = self._status_from_dir(car_id, version_dir)
            if status is not None:
                return status
        return None

    def _status_from_dir(
        self, car_id: str, version_dir: Path
    ) -> ModelAssetStatus | None:
        """Read and validate one version directory."""
        meta_path = version_dir / "meta.json"
        if not meta_path.is_file():
            return None
        try:
            meta = json.loads(meta_path.read_text(encoding="utf-8"))
        except (OSError, ValueError):
            return None
        md5 = str(meta.get("md5") or "")
        if not md5:
            return None
        categories = tuple(
            category
            for category in meta.get("categories", [])
            if category in REQUIRED_FILES
            and all((version_dir / name).is_file() for name in REQUIRED_FILES[category])
        )
        if not categories:
            return None
        return ModelAssetStatus(
            car_id=car_id,
            md5=md5,
            version_dir=version_dir,
            categories=categories,
            base_url=self.base_url(car_id),
        )

    def _extract(self, car_id: str, md5: str, content: bytes) -> ModelAssetStatus:
        """Safely extract the left-hand image tree into a versioned directory."""
        car_root = self.cache_root / car_id
        version_dir = car_root / md5
        existing = self._status_from_dir(car_id, version_dir)
        if existing is not None:
            return existing

        tmp_dir = car_root / f".{md5}.tmp"
        shutil.rmtree(tmp_dir, ignore_errors=True)
        tmp_dir.mkdir(parents=True, exist_ok=True)
        try:
            with zipfile.ZipFile(io.BytesIO(content)) as archive:
                prefix = self._choose_prefix(archive.infolist())
                total = 0
                for info in archive.infolist():
                    if info.is_dir():
                        continue
                    if stat.S_ISLNK(info.external_attr >> 16):
                        continue
                    name = info.filename.replace("\\", "/")
                    if "__MACOSX/" in name:
                        continue
                    base_name = name.rsplit("/", 1)[-1]
                    if base_name == ".DS_Store" or base_name.startswith("._"):
                        continue
                    if prefix:
                        if not name.startswith(prefix):
                            continue
                        name = name[len(prefix) :]
                    parts = [part for part in name.split("/") if part not in ("", ".")]
                    if not parts or ".." in parts:
                        continue
                    if len(parts) < 2:
                        continue
                    try:
                        category_index = next(
                            index
                            for index, part in enumerate(parts)
                            if part in CATEGORY_DIRS
                        )
                    except StopIteration:
                        continue
                    category = parts[category_index]
                    filename = parts[-1]
                    if filename == "carSeat1.png":
                        filename = "carSeat.png"
                    suffix = Path(filename).suffix.lower()
                    if suffix not in ALLOWED_IMAGE_TYPES:
                        continue
                    if info.file_size > MAX_FILE_BYTES:
                        continue
                    data = archive.read(info)
                    if len(data) > MAX_FILE_BYTES:
                        continue
                    total += len(data)
                    if total > MAX_TOTAL_BYTES:
                        raise ValueError("archive exceeds the uncompressed size limit")
                    if not self._is_valid_image(suffix, data):
                        continue
                    target = tmp_dir / category / filename
                    target.parent.mkdir(parents=True, exist_ok=True)
                    target.write_bytes(data)

            categories = tuple(
                category
                for category, names in REQUIRED_FILES.items()
                if all((tmp_dir / name).is_file() for name in names)
            )
            if not categories:
                raise ValueError("archive has no complete panel category")
            meta = {
                "md5": md5,
                "categories": list(categories),
                "extracted_at": datetime.now(UTC).isoformat(),
            }
            (tmp_dir / "meta.json").write_text(json.dumps(meta), encoding="utf-8")
            if version_dir.exists():
                shutil.rmtree(version_dir)
            tmp_dir.rename(version_dir)
        except Exception:
            shutil.rmtree(tmp_dir, ignore_errors=True)
            try:
                if not any(car_root.iterdir()):
                    car_root.rmdir()
            except OSError:
                pass
            raise

        return ModelAssetStatus(
            car_id=car_id,
            md5=md5,
            version_dir=version_dir,
            categories=categories,
            base_url=self.base_url(car_id),
        )

    @staticmethod
    def _is_valid_image(suffix: str, data: bytes) -> bool:
        """Reject a non-image payload even when its extension is an image one."""
        if suffix == ".png":
            return data.startswith(b"\x89PNG\r\n\x1a\n")
        if suffix == ".webp":
            return (
                len(data) >= 12
                and data.startswith(b"RIFF")
                and data[8:12] == b"WEBP"
            )
        return False

    @staticmethod
    def _choose_prefix(members: list[zipfile.ZipInfo]) -> str:
        """Select the left-hand tree, or the only tree in the archive."""
        names = [
            member.filename.replace("\\", "/")
            for member in members
            if "__MACOSX/" not in member.filename
        ]
        for candidate in (f"{ORIENTATION}/", "right/"):
            for name in names:
                index = name.find(candidate)
                if index >= 0:
                    return name[:index] + candidate
        return ""

    def _cleanup_old_versions(self, car_id: str, current: ModelAssetStatus) -> None:
        """Remove older versions and temporary directories after a refresh."""
        car_root = self.cache_root / car_id
        if not car_root.is_dir():
            return
        for child in car_root.iterdir():
            if child == current.version_dir or not child.is_dir():
                continue
            shutil.rmtree(child, ignore_errors=True)


class VehicleModelAssetView(HomeAssistantView):
    """Authenticated endpoint for cached model images."""

    url = f"{VIEW_URL}/{{car_id}}/{{token}}/{{path:.+}}"
    name = "deepal:vehicle_model"
    requires_auth = False

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(
        self, request: web.Request, car_id: str, token: str, path: str
    ) -> web.Response:
        """Serve one image from the current cache of a known vehicle."""
        if re.fullmatch(r"[A-Za-z0-9_-]+", car_id) is None:
            raise web.HTTPNotFound()
        manager = (
            self.hass.data.get(DOMAIN, {})
            .get(DATA_MODEL_MANAGERS, {})
            .get(car_id)
        )
        if manager is None or not hmac.compare_digest(manager.token, token):
            raise web.HTTPNotFound()
        result = await manager.async_read_file(car_id, path)
        if result is None:
            raise web.HTTPNotFound()
        body, content_type = result
        return web.Response(
            body=body,
            content_type=content_type,
            headers={"Cache-Control": "private, max-age=31536000, immutable"},
        )


def async_register_vehicle_model_view(hass: HomeAssistant) -> bool:
    """Register the authenticated model-asset view once per HA run."""
    domain_data = hass.data.setdefault(DOMAIN, {})
    if domain_data.get(DATA_VIEW_REGISTERED):
        return True
    try:
        hass.http.register_view(VehicleModelAssetView(hass))
    except Exception as err:  # noqa: BLE001 - the panel must never break setup
        _LOGGER.warning("Deepal model-asset view registration failed: %s", err)
        return False
    domain_data[DATA_VIEW_REGISTERED] = True
    return True
