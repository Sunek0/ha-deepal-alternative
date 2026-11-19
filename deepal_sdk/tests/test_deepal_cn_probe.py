"""Tests for the Deepal app (China) car-data probe (``tools/deepal-cn-probe``).

The probe is tester tooling outside the SDK package, so it is imported with
``importlib`` and driven against ``httpx.MockTransport``. The guard keeps the
suite working from a plain SDK checkout where ``tools/`` is not published.
"""

from __future__ import annotations

import argparse
import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any

import httpx
import pytest

_PROBE = (
    Path(__file__).resolve().parents[2] / "tools" / "deepal-cn-probe" / "probe.py"
)

if not _PROBE.exists():  # pragma: no cover - a plain SDK checkout has no tools/
    pytest.skip(
        f"probe not present at {_PROBE} (tools/ is not published)",
        allow_module_level=True,
    )


def _load_probe() -> Any:
    """Import the probe module without running its CLI."""
    spec = importlib.util.spec_from_file_location("deepal_cn_probe", _PROBE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["deepal_cn_probe"] = module
    spec.loader.exec_module(module)
    return module


probe = _load_probe()

TOKEN = "test_token_123"
CAR_ID = "car-1"


def _args(**overrides: Any) -> argparse.Namespace:
    values = {
        "token": TOKEN,
        "car_id": CAR_ID,
        "base_url": "https://example.test",
        "keys": "*",
        "timeout": 5.0,
        "raw": False,
    }
    values.update(overrides)
    return argparse.Namespace(**values)


def _client(handler) -> httpx.AsyncClient:
    return httpx.AsyncClient(transport=httpx.MockTransport(handler))


@pytest.mark.asyncio
async def test_fetch_car_data_builds_the_request():
    seen: list[httpx.Request] = []

    def handler(request: httpx.Request) -> httpx.Response:
        seen.append(request)
        return httpx.Response(200, json={"code": 0, "data": {"soc": 82}})

    async with _client(handler) as client:
        payload = await probe.fetch_car_data(
            client,
            base_url="https://example.test/",
            token=TOKEN,
            car_id=CAR_ID,
        )

    request = seen[0]
    assert request.method == "POST"
    assert request.url.host == "example.test"
    assert request.url.path == "/app2/api/car/data"
    assert request.url.params["carId"] == CAR_ID
    assert request.url.params["keys"] == "*"
    assert request.url.params["token"] == TOKEN
    assert payload == {"code": 0, "data": {"soc": 82}}


def test_parser_reads_environment_defaults(monkeypatch):
    monkeypatch.setenv("DEEPAL_CN_TOKEN", "env-token")
    monkeypatch.setenv("DEEPAL_CN_CAR_ID", "env-car")

    args = probe.build_parser().parse_args([])

    assert args.token == "env-token"
    assert args.car_id == "env-car"
    assert args.base_url == "https://cy-m.shenlanche.com.cn"
    assert args.keys == "*"
    assert args.raw is False


def test_render_summary_lists_present_and_missing_fields():
    text = probe.render_summary({"soc": 82, "totalOdometer": 12450, "driverDoor": False})

    assert "Fields returned: 3" in text
    assert "SOC (%)" in text
    assert "82" in text
    assert "Odometer (totalOdometer)" in text
    assert "not present: remainedPowerMile" in text


def test_run_prints_the_summary_and_returns_zero(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 0, "data": {"soc": 82}})

    async def scenario() -> int:
        async with _client(handler) as client:
            return await probe.run(_args(), client=client)

    assert asyncio.run(scenario()) == 0
    output = capsys.readouterr().out
    assert "Fields returned: 1" in output
    assert "SOC (%)" in output
    assert TOKEN not in output


def test_run_returns_one_on_a_gateway_error(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 2, "msg": "token已过期"})

    async def scenario() -> int:
        async with _client(handler) as client:
            return await probe.run(_args(), client=client)

    assert asyncio.run(scenario()) == 1
    assert "gateway error 2" in capsys.readouterr().err


def test_run_returns_two_without_credentials(capsys):
    code = asyncio.run(probe.run(_args(token=None, car_id=None)))

    assert code == 2
    assert "Missing credentials" in capsys.readouterr().err


def test_run_returns_one_on_a_transport_error(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(500, text="boom")

    async def scenario() -> int:
        async with _client(handler) as client:
            return await probe.run(_args(), client=client)

    assert asyncio.run(scenario()) == 1
    assert "Request failed" in capsys.readouterr().err


def test_run_does_not_leak_the_token_on_an_http_error(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(401, text="unauthorized")

    async def scenario() -> int:
        async with _client(handler) as client:
            return await probe.run(_args(), client=client)

    assert asyncio.run(scenario()) == 1
    error = capsys.readouterr().err
    assert "HTTP 401" in error
    assert TOKEN not in error
    assert CAR_ID not in error
    assert "example.test" not in error


def test_run_rejects_a_non_https_base_url(capsys):
    def handler(request: httpx.Request) -> httpx.Response:  # pragma: no cover
        raise AssertionError("the probe must not send the token over HTTP")

    async def scenario() -> int:
        async with _client(handler) as client:
            return await probe.run(
                _args(base_url="http://example.test"), client=client
            )

    assert asyncio.run(scenario()) == 2
    assert "non-HTTPS" in capsys.readouterr().err


@pytest.mark.asyncio
async def test_fetch_car_data_rejects_a_non_object_payload():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=[])

    async with _client(handler) as client:
        with pytest.raises(ValueError, match="non-object"):
            await probe.fetch_car_data(
                client,
                base_url="https://example.test",
                token=TOKEN,
                car_id=CAR_ID,
            )


def test_run_treats_a_non_zero_code_as_an_error(capsys):
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json={"code": 200, "data": {}})

    async def scenario() -> int:
        async with _client(handler) as client:
            return await probe.run(_args(), client=client)

    assert asyncio.run(scenario()) == 1
    assert "gateway error 200" in capsys.readouterr().err


def test_raw_output_redacts_identifiers(capsys):
    payload = {
        "code": 0,
        "data": {
            "soc": 82,
            "vin": "VIN-SECRET",
            "carId": CAR_ID,
            "lat": 40.4168,
            "lng": -3.7038,
            "userId": "user-secret",
            "tuid": "tenant-secret-999",
            "token": TOKEN,
        },
    }

    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(200, json=payload)

    async def scenario() -> int:
        async with _client(handler) as client:
            return await probe.run(_args(raw=True), client=client)

    assert asyncio.run(scenario()) == 0
    output = capsys.readouterr().out
    for secret in (
        TOKEN,
        "VIN-SECRET",
        CAR_ID,
        "user-secret",
        "tenant-secret-999",
        "40.4168",
        "-3.7038",
    ):
        assert secret not in output
    assert output.count("[redacted]") >= 6
    assert json.loads(output[output.index("{") :])["data"]["soc"] == 82
