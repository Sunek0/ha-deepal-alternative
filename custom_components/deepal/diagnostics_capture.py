"""Full diagnostics capture for the Deepal integration.

The integration records every REST and MQTT exchange in a per-entry JSONL file.
The SDK calls :meth:`DiagnosticsCapture.record` synchronously; this module only
redacts and enqueues the event, and a background writer performs the disk I/O.
"""

from __future__ import annotations

import asyncio
import io
import json
import logging
import re
import zipfile
from collections import deque
from collections.abc import Mapping
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

from aiohttp import web
from homeassistant.components.http import HomeAssistantView
from homeassistant.components.http.auth import async_sign_path
from homeassistant.const import __version__ as HA_VERSION
from homeassistant.core import HomeAssistant, callback

from .const import (
    CONF_ENABLE_DIAGNOSTICS_CAPTURE,
    CONF_ENVIRONMENT,
    CONF_PLATFORM,
    DIAGNOSTICS_DIR,
    DIAGNOSTICS_DOWNLOAD_TTL_MINUTES,
    DIAGNOSTICS_DOWNLOAD_URL,
    DIAGNOSTICS_MAX_EVENT_BYTES,
    DIAGNOSTICS_MAX_FILES,
    DIAGNOSTICS_MAX_FILE_BYTES,
    DIAGNOSTICS_MAX_STRING_LENGTH,
    DIAGNOSTICS_RECENT_EVENTS,
    DIAGNOSTICS_SCHEMA_VERSION,
    DOMAIN,
    VERSION,
)
from .deepal.redact import (
    is_sensitive_key,
    redact_mqtt_request_id,
    redact_topic,
)

_LOGGER = logging.getLogger(__name__)

DATA_CAPTURES = "diagnostics_captures"
DATA_VIEW_REGISTERED = "diagnostics_view_registered"

REDACTED = "[redacted]"
# MQTT ``sers``/``rs`` are the encrypted request/response service blobs. They
# are opaque without the redacted secret key and request id, so the capture
# masks them; the decoded ``services``/``params``/``decoded`` fields remain
# available for diagnostics.
_DIAGNOSTICS_REDACTED_KEYS = frozenset({"sers", "rs"})
_REQUEST_ID_KEYS = frozenset(
    {"r", "request_id", "requestid", "reqid", "service_req_id"}
)
_JWT = re.compile(r"^eyJ[\w-]+\.[\w-]+\.[\w-]+$")
_SAFE_FILENAME = re.compile(r"[^A-Za-z0-9._-]+")


def capture_directory(hass: HomeAssistant, entry_id: str) -> Path:
    """Return the per-entry capture directory."""
    return Path(hass.config.path(DIAGNOSTICS_DIR)) / entry_id


def _json_default(value: Any) -> str:
    """Serialize values the SDK may include that standard JSON cannot."""
    return str(value)


def _redact_url(value: str) -> str:
    """Mask sensitive query parameters in an URL."""
    parsed = urlsplit(value)
    if not parsed.query:
        return value
    query = [
        (key, REDACTED if is_sensitive_key(key) else item)
        for key, item in parse_qsl(parsed.query, keep_blank_values=True)
    ]
    return urlunsplit(
        (parsed.scheme, parsed.netloc, parsed.path, urlencode(query), parsed.fragment)
    )


def redact_event(value: Any, key: str | None = None) -> Any:
    """Return a capture-safe copy of one exchange event.

    Sensitive keys are masked at any depth. The encrypted MQTT ``sers`` and
    ``rs`` service blobs are masked too; their decoded ``services``,
    ``params`` and ``decoded`` counterparts stay available for diagnostics.
    MQTT ``$vdp/<did>/...`` topics, request-id device prefixes and JWT-like
    values are masked even when their key looks innocent.
    """
    if isinstance(value, Mapping):
        result: dict[str, Any] = {}
        for item_key, item in value.items():
            if (
                is_sensitive_key(item_key)
                or str(item_key).lower() in _DIAGNOSTICS_REDACTED_KEYS
            ):
                result[str(item_key)] = REDACTED
            else:
                result[str(item_key)] = redact_event(item, str(item_key))
        return result
    if isinstance(value, (list, tuple)):
        return [redact_event(item, key) for item in value]
    if isinstance(value, str):
        if key is not None and key.lower() in _REQUEST_ID_KEYS:
            value = redact_mqtt_request_id(value)
        if value.startswith("$vdp/"):
            value = redact_topic(value)
        elif value.startswith(("http://", "https://")):
            value = _redact_url(value)
        if _JWT.match(value):
            return REDACTED
        if len(value) > DIAGNOSTICS_MAX_STRING_LENGTH:
            return (
                f"{value[:DIAGNOSTICS_MAX_STRING_LENGTH]}"
                f"...[truncated {len(value) - DIAGNOSTICS_MAX_STRING_LENGTH} chars]"
            )
        return value
    if isinstance(value, bytes):
        return f"<{len(value)} bytes>"
    return value


def _event_size(event: dict[str, Any]) -> int:
    """Return the serialized byte size of one event."""
    try:
        return len(
            json.dumps(
                event, ensure_ascii=False, separators=(",", ":"), default=_json_default
            ).encode()
        )
    except (TypeError, ValueError):
        return DIAGNOSTICS_MAX_EVENT_BYTES + 1


def _bounded_event(event: dict[str, Any]) -> dict[str, Any]:
    """Replace an oversized event with a small summary."""
    if _event_size(event) <= DIAGNOSTICS_MAX_EVENT_BYTES:
        return event
    return {
        "ts": event.get("ts") or datetime.now(UTC).isoformat(),
        "kind": event.get("kind") or "event",
        "event": "truncated",
        "original_kind": event.get("kind"),
        "original_event": event.get("event"),
        "bytes": _event_size(event),
    }


class DiagnosticsCapture:
    """Per-entry JSONL diagnostics recorder."""

    def __init__(
        self,
        hass: HomeAssistant,
        entry: Any,
        *,
        enabled: bool = False,
        base_dir: Path | None = None,
    ) -> None:
        self.hass = hass
        self.entry = entry
        self.entry_id = entry.entry_id
        self.enabled = enabled
        self._directory = (
            Path(base_dir) / entry.entry_id
            if base_dir is not None
            else capture_directory(hass, entry.entry_id)
        )
        self._active_path: Path | None = None
        self._queue: asyncio.Queue[
            tuple[dict[str, Any] | None, asyncio.Future[Any] | None]
        ] = asyncio.Queue(maxsize=2000)
        self._writer_task: asyncio.Task[None] | None = None
        self._recent: deque[dict[str, Any]] = deque(maxlen=DIAGNOSTICS_RECENT_EVENTS)
        self._dropped = 0
        self._last_error: str | None = None
        self._logged_error = False
        self._started = False

    @property
    def started(self) -> bool:
        """Return whether the background writer is running."""
        return self._started

    @property
    def active_path(self) -> Path | None:
        """Return the active segment path, when one exists."""
        return self._active_path

    def _header(self) -> dict[str, Any]:
        """Build the header written at the top of every segment."""
        entry_data = getattr(self.entry, "data", {}) or {}
        options = getattr(self.entry, "options", {}) or {}
        coordinator = getattr(
            getattr(self.entry, "runtime_data", None), "coordinator", None
        )
        vehicles = []
        for vehicle in getattr(coordinator, "vehicles", []) or []:
            vehicles.append(
                {
                    "car_id": getattr(vehicle, "car_id", None),
                    "vin": getattr(vehicle, "vin", None),
                    "series_name": getattr(vehicle, "series_name", None),
                    "model_name": getattr(vehicle, "model_name", None),
                    "model_code": getattr(vehicle, "model_code", None),
                    "series_code": getattr(vehicle, "series_code", None),
                    "car_platform": getattr(vehicle, "car_platform", None),
                    "protocol_type": getattr(vehicle, "protocol_type", None),
                }
            )
        return {
            "schema_version": DIAGNOSTICS_SCHEMA_VERSION,
            "type": "header",
            "created_at": datetime.now(UTC).isoformat(),
            "integration_version": VERSION,
            "ha_version": (
                getattr(getattr(self.hass, "config", None), "version", "")
                or HA_VERSION
            ),
            "entry_id": self.entry_id,
            "entry_title": getattr(self.entry, "title", ""),
            "platform": entry_data.get(CONF_PLATFORM, "sda"),
            "environment": (
                options.get(CONF_ENVIRONMENT)
                or entry_data.get(CONF_ENVIRONMENT)
                or ""
            ),
            "entry_data": entry_data,
            "options": options,
            "vehicles": vehicles,
            "limits": {
                "max_file_bytes": DIAGNOSTICS_MAX_FILE_BYTES,
                "max_files": DIAGNOSTICS_MAX_FILES,
            },
        }

    def _ensure_directory(self) -> None:
        """Create the capture directory with private permissions."""
        self._directory.mkdir(parents=True, exist_ok=True)
        try:
            self._directory.chmod(0o700)
        except OSError:
            pass

    def _new_path(self) -> Path:
        """Return a unique timestamped segment path."""
        self._ensure_directory()
        stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S-%f")
        path = self._directory / f"deepal_{stamp}.jsonl"
        counter = 1
        while path.exists():
            path = self._directory / f"deepal_{stamp}_{counter}.jsonl"
            counter += 1
        return path

    def _files(self) -> list[Path]:
        """Return the capture segments, oldest first."""
        if not self._directory.is_dir():
            return []
        return sorted(self._directory.glob("deepal_*.jsonl"))

    def _latest_path(self) -> Path | None:
        files = self._files()
        return files[-1] if files else None

    def _write_header(self, path: Path) -> None:
        """Write the header if the segment is new or empty."""
        if path.exists() and path.stat().st_size > 0:
            return
        header = _bounded_event(redact_event(self._header()))
        with path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(header, ensure_ascii=False, default=_json_default))
            handle.write("\n")
        try:
            path.chmod(0o600)
        except OSError:
            pass

    def _prune(self) -> None:
        """Remove the oldest segments beyond the retention count."""
        files = self._files()
        while len(files) > DIAGNOSTICS_MAX_FILES:
            oldest = files.pop(0)
            if oldest == self._active_path:
                continue
            try:
                oldest.unlink()
            except OSError as err:
                _LOGGER.debug("Deepal diagnostics could not remove %s: %s", oldest, err)

    def _write_event(self, event: dict[str, Any]) -> None:
        """Append one event, rotating the segment when it is full."""
        self._ensure_directory()
        if self._active_path is None:
            self._active_path = self._new_path()
        self._write_header(self._active_path)
        with self._active_path.open("a", encoding="utf-8") as handle:
            handle.write(json.dumps(event, ensure_ascii=False, default=_json_default))
            handle.write("\n")
        try:
            self._active_path.chmod(0o600)
        except OSError:
            pass
        if self._active_path.stat().st_size >= DIAGNOSTICS_MAX_FILE_BYTES:
            self._rotate()

    def _rotate(self) -> None:
        """Close the active segment and start a new one."""
        self._active_path = self._new_path()
        self._write_header(self._active_path)
        self._prune()

    def _delete(self) -> None:
        """Delete every segment for the entry."""
        for path in self._files():
            try:
                path.unlink()
            except OSError as err:
                _LOGGER.debug("Deepal diagnostics could not delete %s: %s", path, err)
        self._active_path = None
        try:
            self._directory.rmdir()
        except OSError:
            pass

    async def _handle_control(self, control: str) -> None:
        """Apply a file-management command in the writer task."""
        if control == "new":
            await asyncio.to_thread(self._rotate)
        elif control == "delete":
            await asyncio.to_thread(self._delete)
            self._recent.clear()
            self._dropped = 0
            if self.enabled:
                await asyncio.to_thread(self._rotate)
        elif control == "flush":
            return

    async def _writer_loop(self) -> None:
        """Consume the queue and persist events."""
        try:
            while True:
                event, future = await self._queue.get()
                if event is None:
                    break
                control = event.get("_control")
                try:
                    if control:
                        await self._handle_control(str(control))
                    else:
                        await asyncio.to_thread(self._write_event, event)
                except Exception as err:  # noqa: BLE001 - capture must never break HA
                    self._record_error(err)
                    if future is not None and not future.done():
                        future.set_exception(err)
                else:
                    if future is not None and not future.done():
                        future.set_result(None)
        finally:
            self._started = False

    def _record_error(self, err: Exception) -> None:
        """Keep the last capture error and log it once."""
        self._last_error = str(err)
        if not self._logged_error:
            self._logged_error = True
            _LOGGER.warning("Deepal diagnostics capture failed: %s", err)

    def record(self, event: dict[str, Any]) -> None:
        """Queue one exchange event without blocking the caller."""
        if not self._started:
            return
        try:
            safe = _bounded_event(redact_event(event))
            if "ts" not in safe:
                safe["ts"] = datetime.now(UTC).isoformat()
            self._recent.append(safe)
            try:
                self._queue.put_nowait((safe, None))
            except asyncio.QueueFull:
                self._dropped += 1
        except Exception as err:  # noqa: BLE001 - never break an API call
            self._record_error(err)

    async def async_start(self) -> None:
        """Start the background writer and open the current segment."""
        if self._started or not self.enabled:
            return
        try:
            await asyncio.to_thread(self._ensure_directory)
            self._active_path = await asyncio.to_thread(self._latest_path)
            if self._active_path is None:
                self._active_path = await asyncio.to_thread(self._new_path)
            await asyncio.to_thread(self._write_header, self._active_path)
        except Exception as err:  # noqa: BLE001 - setup must not fail
            self._record_error(err)
            return
        self._last_error = None
        self._logged_error = False
        self._started = True
        self._writer_task = self.entry.async_create_background_task(
            self.hass,
            self._writer_loop(),
            f"{DOMAIN}_diagnostics_{self.entry_id}",
        )

    async def async_stop(self) -> None:
        """Flush the queue and stop the writer."""
        if not self._started:
            return
        self._started = False
        await self._queue.put((None, None))
        if self._writer_task is not None:
            try:
                await self._writer_task
            except asyncio.CancelledError:
                pass
            except Exception as err:  # noqa: BLE001 - unload must not fail
                self._record_error(err)
            self._writer_task = None

    async def _control(self, control: str) -> None:
        """Send a control command through the writer task."""
        if not self._started:
            await asyncio.to_thread(self._handle_control_sync, control)
            return
        future: asyncio.Future[Any] = asyncio.get_running_loop().create_future()
        await self._queue.put(({"_control": control}, future))
        await future

    def _handle_control_sync(self, control: str) -> None:
        """Apply a control command when no writer is running."""
        if control == "new":
            self._rotate()
        elif control == "delete":
            self._delete()
            self._recent.clear()
            self._dropped = 0
            if self.enabled:
                self._rotate()
        elif control == "flush":
            return

    async def async_new_segment(self) -> None:
        """Close the current segment and start a new one."""
        await self._control("new")

    async def async_delete_all(self) -> None:
        """Delete every capture segment for the entry."""
        await self._control("delete")

    async def async_flush(self) -> None:
        """Wait until the queued events have been written."""
        await self._control("flush")

    async def async_status(self) -> dict[str, Any]:
        """Return the capture state for the options form and diagnostics."""
        files = await asyncio.to_thread(self._files)
        listing = []
        total = 0
        for path in files:
            try:
                stat = path.stat()
            except OSError:
                continue
            total += stat.st_size
            listing.append(
                {
                    "name": path.name,
                    "size": stat.st_size,
                    "modified": datetime.fromtimestamp(
                        stat.st_mtime, UTC
                    ).isoformat(),
                }
            )
        return {
            "enabled": self.enabled,
            "started": self._started,
            "directory": str(self._directory),
            "active_file": self._active_path.name if self._active_path else None,
            "files": listing,
            "total_bytes": total,
            "dropped_events": self._dropped,
            "last_error": self._last_error,
            "recent_events": list(self._recent),
        }

    async def async_remove(self) -> None:
        """Stop the writer and delete every segment for the entry."""
        await self.async_stop()
        try:
            await asyncio.to_thread(self._delete)
        except Exception as err:  # noqa: BLE001 - removal must not fail
            self._record_error(err)


def async_get_capture_manager(
    hass: HomeAssistant, entry: Any, *, create: bool = True
) -> DiagnosticsCapture:
    """Return the entry's capture manager, creating an idle one if needed."""
    runtime = getattr(entry, "runtime_data", None)
    capture = getattr(runtime, "capture", None)
    if capture is not None:
        capture.enabled = bool(
            (getattr(entry, "options", {}) or {}).get(
                CONF_ENABLE_DIAGNOSTICS_CAPTURE, False
            )
        )
        return capture
    data = getattr(hass, "data", None)
    if data is None:
        data = {}
        hass.data = data
    registry = data.setdefault(DOMAIN, {}).setdefault(DATA_CAPTURES, {})
    capture = registry.get(entry.entry_id)
    if capture is None and create:
        capture = DiagnosticsCapture(
            hass,
            entry,
            enabled=bool(
                (getattr(entry, "options", {}) or {}).get(
                    CONF_ENABLE_DIAGNOSTICS_CAPTURE, False
                )
            ),
        )
        registry[entry.entry_id] = capture
    if isinstance(capture, DiagnosticsCapture):
        capture.enabled = bool(
            (getattr(entry, "options", {}) or {}).get(
                CONF_ENABLE_DIAGNOSTICS_CAPTURE, False
            )
        )
    return capture


async def async_shutdown_capture(hass: HomeAssistant, entry: Any) -> None:
    """Stop the writer while keeping the files available for download."""
    runtime = getattr(entry, "runtime_data", None)
    capture = getattr(runtime, "capture", None)
    if capture is None:
        capture = (
            (getattr(hass, "data", None) or {})
            .get(DOMAIN, {})
            .get(DATA_CAPTURES, {})
            .get(entry.entry_id)
        )
    if isinstance(capture, DiagnosticsCapture):
        await capture.async_stop()


async def async_remove_capture(hass: HomeAssistant, entry: Any) -> None:
    """Delete the entry's capture files and forget its manager."""
    registry = (
        (getattr(hass, "data", None) or {})
        .get(DOMAIN, {})
        .get(DATA_CAPTURES, {})
    )
    capture = registry.pop(entry.entry_id, None)
    if capture is None:
        capture = getattr(getattr(entry, "runtime_data", None), "capture", None)
    if isinstance(capture, DiagnosticsCapture):
        await capture.async_remove()


def async_download_url(hass: HomeAssistant, entry_id: str) -> str:
    """Return a short-lived signed path for the entry capture bundle."""
    path = f"{DIAGNOSTICS_DOWNLOAD_URL}/{entry_id}"
    try:
        return async_sign_path(
            hass, path, timedelta(minutes=DIAGNOSTICS_DOWNLOAD_TTL_MINUTES)
        )
    except (KeyError, RuntimeError):
        return path


async def async_capture_summary(
    hass: HomeAssistant, entry: Any, *, recent_limit: int = 50
) -> dict[str, Any]:
    """Return the capture summary included in the standard diagnostics."""
    if hass is None:
        return {
            "enabled": bool(
                (getattr(entry, "options", {}) or {}).get(
                    CONF_ENABLE_DIAGNOSTICS_CAPTURE, False
                )
            ),
            "files": [],
            "recent_events": [],
        }
    capture = async_get_capture_manager(hass, entry, create=True)
    status = await capture.async_status()
    status["recent_events"] = status["recent_events"][-recent_limit:]
    return redact_event(status)


def _archive_name(entry: Any) -> str:
    """Return a safe attachment name for the capture bundle."""
    title = _SAFE_FILENAME.sub("_", str(getattr(entry, "title", "") or "deepal"))
    stamp = datetime.now(UTC).strftime("%Y%m%d-%H%M%S")
    return f"deepal_diagnostics_{title[:40]}_{stamp}"


class DiagnosticsDownloadView(HomeAssistantView):
    """Authenticated download endpoint for one entry's capture files."""

    url = f"{DIAGNOSTICS_DOWNLOAD_URL}/{{entry_id}}"
    name = "api:deepal:diagnostics"

    def __init__(self, hass: HomeAssistant) -> None:
        self.hass = hass

    async def get(self, request: web.Request, entry_id: str) -> web.StreamResponse:
        """Serve the active JSONL segment or a ZIP of all segments."""
        entry = self.hass.config_entries.async_get_entry(entry_id)
        if entry is None:
            raise web.HTTPNotFound()
        directory = capture_directory(self.hass, entry_id)
        files = await asyncio.to_thread(
            lambda: sorted(directory.glob("deepal_*.jsonl"))
        )
        if not files:
            raise web.HTTPNotFound()
        headers = {
            "Cache-Control": "no-store",
            "X-Content-Type-Options": "nosniff",
        }
        if len(files) == 1:
            path = files[0]
            return web.FileResponse(
                path,
                headers={
                    **headers,
                    "Content-Disposition": f'attachment; filename="{path.name}"',
                    "Content-Type": "application/x-ndjson; charset=utf-8",
                },
            )
        buffer = io.BytesIO()
        with zipfile.ZipFile(buffer, "w", zipfile.ZIP_DEFLATED) as archive:
            manifest = {
                "entry_id": entry_id,
                "entry_title": getattr(entry, "title", ""),
                "created_at": datetime.now(UTC).isoformat(),
                "files": [path.name for path in files],
            }
            archive.writestr(
                "manifest.json",
                json.dumps(manifest, ensure_ascii=False, indent=2),
            )
            for path in files:
                archive.write(path, arcname=path.name)
        name = f"{_archive_name(entry)}.zip"
        return web.Response(
            body=buffer.getvalue(),
            content_type="application/zip",
            headers={
                **headers,
                "Content-Disposition": f'attachment; filename="{name}"',
            },
        )


@callback
def async_register_diagnostics_view(hass: HomeAssistant) -> bool:
    """Register the download view once per Home Assistant run."""
    domain_data = getattr(hass, "data", None)
    if domain_data is None or not hasattr(hass, "http"):
        return False
    domain = domain_data.setdefault(DOMAIN, {})
    if domain.get(DATA_VIEW_REGISTERED):
        return True
    try:
        hass.http.register_view(DiagnosticsDownloadView(hass))
    except Exception as err:  # noqa: BLE001 - the view must never break setup
        _LOGGER.warning("Deepal diagnostics download view failed: %s", err)
        return False
    domain[DATA_VIEW_REGISTERED] = True
    return True
