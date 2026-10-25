"""Tests for the Deepal full diagnostics capture."""

from __future__ import annotations

import asyncio
import json
from pathlib import Path
from types import SimpleNamespace

import pytest

from custom_components.deepal import diagnostics_capture
from aiohttp import web
from homeassistant.data_entry_flow import FlowResultType

from custom_components.deepal import config_flow
from custom_components.deepal.const import DOMAIN
from custom_components.deepal.diagnostics_capture import (
    DiagnosticsCapture,
    DiagnosticsDownloadView,
    async_capture_summary,
    redact_event,
)


class _FakeHass:
    def __init__(self, base: Path) -> None:
        self.base = base
        self.config = SimpleNamespace(
            path=lambda *parts: str(base.joinpath(*parts)),
            version="2026.9.0",
        )
        self.data: dict = {}
        self.tasks: list[asyncio.Task] = []
        self.background_tasks: list[asyncio.Task] = []
        self.reloaded: list[str] = []
        self.entry = _FakeEntry()
        self.config_entries = SimpleNamespace(
            async_get_entry=self._async_get_entry,
            async_get_known_entry=self._async_get_entry,
            async_update_entry=self._async_update_entry,
            async_reload=self._async_reload,
        )

    def _async_get_entry(self, entry_id):
        return self.entry if entry_id == self.entry.entry_id else None

    def _async_update_entry(self, entry, *, data=None, options=None, **kwargs):
        if data is not None:
            entry.data = dict(data)
        if options is not None:
            entry.options = dict(options)

    async def _async_reload(self, entry_id):
        self.reloaded.append(entry_id)
        return True

    def localize(self, key):
        return key.rsplit(".", 1)[-1]

    def async_create_task(self, coro, name=None):
        task = asyncio.create_task(coro, name=name)
        self.tasks.append(task)
        return task

    def async_create_background_task(self, coro, name, eager_start=True):
        task = asyncio.create_task(coro, name=name)
        self.background_tasks.append(task)
        return task


class _FakeEntry:
    def __init__(self) -> None:
        self.entry_id = "entry-1"
        self.title = "Deepal S05"
        self.data = {
            "access_token": "test_token_123",
            "vin": "VIN-PLACEHOLDER-1",
            "private_key": "test_private_key",
        }
        self.options = {"control_pin": "1234"}
        self.runtime_data = SimpleNamespace(
            coordinator=SimpleNamespace(
                vehicles=[SimpleNamespace(car_id="car-1", vin="VIN-PLACEHOLDER-1")]
            )
        )

    def async_create_background_task(self, hass, coro, name, eager_start=True):
        return hass.async_create_background_task(coro, name, eager_start)


def _event(**extra):
    return {
        "kind": "rest",
        "event": "response",
        "request": {"access_token": "test_token_123", "vin": "VIN-PLACEHOLDER-1"},
        "headers": {"authorization": "Bearer test_token_123"},
        "response": {"soc": 71, "vehicleId": "car-1"},
        **extra,
    }


@pytest.mark.asyncio
async def test_capture_writer_is_a_background_task(tmp_path):
    """The writer must not block Home Assistant startup or async_block_till_done."""
    hass = _FakeHass(tmp_path)
    entry = _FakeEntry()
    entry.options["enable_diagnostics_capture"] = True
    capture = DiagnosticsCapture(hass, entry, enabled=True)

    await capture.async_start()
    try:
        assert hass.background_tasks
        assert not hass.tasks
    finally:
        await capture.async_stop()


@pytest.mark.asyncio
async def test_capture_writes_header_and_redacted_events(tmp_path):
    hass = _FakeHass(tmp_path)
    entry = _FakeEntry()
    entry.options["enable_diagnostics_capture"] = True
    capture = DiagnosticsCapture(hass, entry, enabled=True)
    await capture.async_start()
    capture.record(
        _event(
            url="https://example.test/path?carId=car-1&ok=1",
            topic="$vdp/device-did/properties/get/res",
            r="device-did_1720000000000000",
            note="eyJhbGciOiJIUzI1NiJ9.eyJzdWIiOiIxMjMifQ.signature",
        )
    )
    await capture.async_flush()
    status = await capture.async_status()
    await capture.async_stop()

    assert status["files"]
    path = Path(status["directory"]) / status["files"][0]["name"]
    content = path.read_text(encoding="utf-8")
    lines = [json.loads(line) for line in content.splitlines()]

    assert lines[0]["type"] == "header"
    assert lines[0]["integration_version"]
    assert "test_token_123" not in content
    assert "VIN-PLACEHOLDER-1" not in content
    assert "car-1" not in content
    assert "device-did" not in content
    assert "eyJhbGci" not in content
    assert "[redacted]" in content
    assert lines[1]["response"]["soc"] == 71


@pytest.mark.asyncio
async def test_capture_rotates_and_retains_a_bounded_number_of_files(
    tmp_path, monkeypatch
):
    monkeypatch.setattr(diagnostics_capture, "DIAGNOSTICS_MAX_FILE_BYTES", 2000)
    monkeypatch.setattr(diagnostics_capture, "DIAGNOSTICS_MAX_FILES", 2)
    hass = _FakeHass(tmp_path)
    capture = DiagnosticsCapture(hass, _FakeEntry(), enabled=True)
    await capture.async_start()

    for index in range(20):
        capture.record(_event(note=f"event-{index}-" + "x" * 400))
    await capture.async_flush()
    status = await capture.async_status()
    await capture.async_stop()

    assert 1 < len(status["files"]) <= 2
    assert status["total_bytes"] <= 2000 * 2 + 2000


@pytest.mark.asyncio
async def test_new_segment_and_delete_all(tmp_path):
    hass = _FakeHass(tmp_path)
    capture = DiagnosticsCapture(hass, _FakeEntry(), enabled=True)
    await capture.async_start()
    capture.record(_event(note="first"))
    await capture.async_flush()
    first_files = (await capture.async_status())["files"]
    assert first_files

    await capture.async_new_segment()
    capture.record(_event(note="second"))
    await capture.async_flush()
    assert len((await capture.async_status())["files"]) == 2

    await capture.async_delete_all()
    files = (await capture.async_status())["files"]
    await capture.async_stop()

    assert len(files) == 1
    assert all(path["name"] != first_files[0]["name"] for path in files)


@pytest.mark.asyncio
async def test_capture_ignores_events_after_stop(tmp_path):
    hass = _FakeHass(tmp_path)
    capture = DiagnosticsCapture(hass, _FakeEntry(), enabled=True)
    await capture.async_start()
    capture.record(_event(note="before"))
    await capture.async_flush()
    await capture.async_stop()
    capture.record(_event(note="after"))
    await asyncio.sleep(0)

    content = "\n".join(
        path.read_text(encoding="utf-8")
        for path in (tmp_path / "deepal_diagnostics" / "entry-1").glob("*.jsonl")
    )
    assert "before" in content
    assert "after" not in content


@pytest.mark.asyncio
async def test_capture_write_failure_does_not_raise(tmp_path):
    hass = _FakeHass(tmp_path)
    capture = DiagnosticsCapture(hass, _FakeEntry(), enabled=True)
    await capture.async_start()
    capture._write_event = lambda event: (_ for _ in ()).throw(RuntimeError("disk full"))
    capture.record(_event(note="boom"))
    await capture.async_flush()
    status = await capture.async_status()
    await capture.async_stop()

    assert status["last_error"] == "disk full"


@pytest.mark.asyncio
async def test_new_segment_without_a_writer_creates_a_file(tmp_path):
    hass = _FakeHass(tmp_path)
    capture = DiagnosticsCapture(hass, _FakeEntry(), enabled=False)
    await capture.async_new_segment()
    status = await capture.async_status()

    assert len(status["files"]) == 1
    header = json.loads(
        (Path(status["directory"]) / status["files"][0]["name"]).read_text(
            encoding="utf-8"
        )
    )
    assert header["type"] == "header"


def test_redact_event_masks_nested_values_and_urls():
    event = _event(
        url="https://example.test/path?carId=car-1&ok=1",
        topic="$vdp/did-1/properties/get/res",
        request_id="did-1_1720000000000000",
        service_req_id="did-1_1720000000000001",
        nested={"lat": 38.9, "soc": 71},
    )

    result = redact_event(event)

    assert result["url"] == "https://example.test/path?carId=%5Bredacted%5D&ok=1"
    assert result["topic"] == "$vdp/[redacted]/properties/get/res"
    assert result["request_id"] == "[redacted]_1720000000000000"
    assert result["service_req_id"] == "[redacted]_1720000000000001"
    assert result["nested"] == {"lat": "[redacted]", "soc": 71}


@pytest.mark.asyncio
async def test_capture_summary_reads_the_registered_manager(tmp_path):
    hass = _FakeHass(tmp_path)
    entry = _FakeEntry()
    entry.options["enable_diagnostics_capture"] = True
    capture = DiagnosticsCapture(hass, entry, enabled=True)
    hass.data.setdefault(DOMAIN, {})["diagnostics_captures"] = {
        entry.entry_id: capture
    }
    await capture.async_start()
    capture.record(_event(note="summary"))
    await capture.async_flush()

    summary = await async_capture_summary(hass, entry)

    await capture.async_stop()
    assert summary["enabled"] is True
    assert summary["files"]
    assert summary["recent_events"]


@pytest.mark.asyncio
async def test_download_view_serves_a_single_jsonl_file(tmp_path):
    hass = _FakeHass(tmp_path)
    capture = DiagnosticsCapture(hass, hass.entry, enabled=True)
    await capture.async_start()
    capture.record(_event(note="download"))
    await capture.async_flush()

    response = await DiagnosticsDownloadView(hass).get(None, hass.entry.entry_id)
    await capture.async_stop()

    assert response.headers["Content-Disposition"].startswith(
        'attachment; filename="deepal_'
    )
    assert response.headers["Content-Type"] == "application/x-ndjson; charset=utf-8"


@pytest.mark.asyncio
async def test_download_view_zips_multiple_files(tmp_path):
    import io
    import zipfile

    hass = _FakeHass(tmp_path)
    capture = DiagnosticsCapture(hass, hass.entry, enabled=True)
    await capture.async_start()
    capture.record(_event(note="first"))
    await capture.async_flush()
    await capture.async_new_segment()
    capture.record(_event(note="second"))
    await capture.async_flush()

    response = await DiagnosticsDownloadView(hass).get(None, hass.entry.entry_id)
    await capture.async_stop()

    assert response.headers["Content-Type"] == "application/zip"
    with zipfile.ZipFile(io.BytesIO(response.body)) as archive:
        names = archive.namelist()
        assert "manifest.json" in names
        assert any(name.endswith(".jsonl") for name in names)


@pytest.mark.asyncio
async def test_download_view_rejects_an_unknown_entry(tmp_path):
    from aiohttp import web

    hass = _FakeHass(tmp_path)
    with pytest.raises(web.HTTPNotFound):
        await DiagnosticsDownloadView(hass).get(None, "unknown-entry")


@pytest.mark.asyncio
async def test_options_flow_new_file_action_saves_and_returns_the_form(tmp_path):
    hass = _FakeHass(tmp_path)
    capture = DiagnosticsCapture(
        hass, hass.entry, enabled=False, base_dir=tmp_path
    )
    hass.entry.runtime_data = SimpleNamespace(
        capture=capture,
        coordinator=SimpleNamespace(vehicles=[]),
    )
    flow = object.__new__(config_flow.DeepalOptionsFlow)
    flow.handler = hass.entry.entry_id
    flow.hass = hass

    result = await flow.async_step_init(
        {
            "scan_interval": 60,
            config_flow.DIAGNOSTICS_SECTION: {
                "enable_diagnostics_capture": True,
                "diagnostics_action": "new",
                "diagnostics_confirm_delete": False,
            },
        }
    )

    assert result["type"] is FlowResultType.FORM
    assert hass.entry.options["enable_diagnostics_capture"] is True
    assert hass.reloaded == [hass.entry.entry_id]
    assert "enabled" in result["description_placeholders"]["diagnostics_status"]
    assert "download" in result["description_placeholders"]["diagnostics_status"]
    assert (await capture.async_status())["files"]


@pytest.mark.asyncio
async def test_options_flow_delete_requires_confirmation(tmp_path):
    hass = _FakeHass(tmp_path)
    capture = DiagnosticsCapture(
        hass, hass.entry, enabled=False, base_dir=tmp_path
    )
    hass.entry.runtime_data = SimpleNamespace(
        capture=capture,
        coordinator=SimpleNamespace(vehicles=[]),
    )
    flow = object.__new__(config_flow.DeepalOptionsFlow)
    flow.handler = hass.entry.entry_id
    flow.hass = hass

    result = await flow.async_step_init(
        {
            config_flow.DIAGNOSTICS_SECTION: {
                "enable_diagnostics_capture": True,
                "diagnostics_action": "delete",
                "diagnostics_confirm_delete": False,
            },
        }
    )

    assert result["type"] is FlowResultType.FORM
    assert result["errors"] == {"base": "confirm_delete"}
    assert hass.reloaded == []


def test_download_url_uses_the_signed_path(monkeypatch):
    from custom_components.deepal import diagnostics_capture

    monkeypatch.setattr(
        diagnostics_capture,
        "async_sign_path",
        lambda hass, path, ttl: f"{path}?authSig=test",
    )
    hass = SimpleNamespace(data={})

    url = diagnostics_capture.async_download_url(hass, "entry-1")

    assert url == "/api/deepal/diagnostics/entry-1?authSig=test"


def test_download_url_falls_back_when_signing_is_unavailable(monkeypatch):
    from custom_components.deepal import diagnostics_capture

    def broken_sign(hass, path, ttl):
        raise KeyError("no auth store")

    monkeypatch.setattr(diagnostics_capture, "async_sign_path", broken_sign)
    hass = SimpleNamespace(data={})

    url = diagnostics_capture.async_download_url(hass, "entry-1")

    assert url == "/api/deepal/diagnostics/entry-1"
