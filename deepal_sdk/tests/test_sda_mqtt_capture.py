"""Tests for the SDA MQTT capture helper (``tools/sda-mqtt-capture``).

The helper is a tester-facing mitmproxy addon, so it is not part of the SDK
package: it lives in ``tools/`` and the HACS mirror does not publish that tree.
The module is imported here with mitmproxy stubbed so the redaction and the
``sers`` decoding are covered by the normal test run, and the whole file is
skipped where the tool is not present.
"""

from __future__ import annotations

import importlib.util
import json
import sys
import types
from io import StringIO
from pathlib import Path
from typing import Any

import pytest

from deepal.mqtt import aes_cbc_decrypt, aes_cbc_encrypt, build_connect_packet, build_publish_packet

_TOOL = Path(__file__).resolve().parents[2] / "tools" / "sda-mqtt-capture" / "mqtt_dump.py"

if not _TOOL.exists():  # pragma: no cover - the mirror only ships the integration
    pytest.skip(
        f"capture helper not present at {_TOOL} (tools/ is not published)",
        allow_module_level=True,
    )

SECRET_KEY = "0123456789abcdef"
SECRET_KEY_2 = "fedcba9876543210"
LOGIN_RESPONSE = {
    "rs": [{"service_code": "login", "params": {"secretKey": SECRET_KEY, "cid": "1987639064962777089"}}]
}


def _load_addon() -> Any:
    """Import the capture addon with mitmproxy stubbed out, no network involved."""
    names = ("mitmproxy", "mitmproxy.ctx", "mitmproxy.http", "mitmproxy.tcp")
    saved = {name: sys.modules.get(name) for name in names}

    mitmproxy = types.ModuleType("mitmproxy")
    ctx = types.ModuleType("mitmproxy.ctx")
    ctx.options = types.SimpleNamespace(
        mqtt_dump_dir="/tmp/never", mqtt_dump_raw=False, mqtt_dump_http=True
    )
    ctx.log = types.SimpleNamespace(info=lambda *args, **kwargs: None)
    http = types.ModuleType("mitmproxy.http")
    http.HTTPFlow = object
    tcp = types.ModuleType("mitmproxy.tcp")
    tcp.TCPFlow = object
    mitmproxy.ctx = ctx
    mitmproxy.http = http
    mitmproxy.tcp = tcp
    sys.modules.update(
        {
            "mitmproxy": mitmproxy,
            "mitmproxy.ctx": ctx,
            "mitmproxy.http": http,
            "mitmproxy.tcp": tcp,
        }
    )
    try:
        spec = importlib.util.spec_from_file_location("deepal_sda_mqtt_capture", _TOOL)
        module = importlib.util.module_from_spec(spec)
        spec.loader.exec_module(module)
    finally:
        for name, previous in saved.items():
            if previous is None:
                sys.modules.pop(name, None)
            else:
                sys.modules[name] = previous
    return module


addon_module = _load_addon()
HOST = "prod-appmq.sda.changanauto.sg"


def _addon(raw_enabled: bool = False) -> tuple[Any, StringIO, StringIO, StringIO]:
    addon = addon_module.MqttDump()
    transcript, raw, http_log = StringIO(), StringIO(), StringIO()
    addon.transcript = transcript
    addon.raw_enabled = raw_enabled
    addon.raw = raw if raw_enabled else None
    addon.http_enabled = True
    addon.http_transcript = http_log
    return addon, transcript, raw, http_log


def _tcp_flow(*packets: bytes, from_client: bool = True) -> Any:
    message = types.SimpleNamespace(content=b"".join(packets), from_client=from_client)
    return types.SimpleNamespace(
        server_conn=types.SimpleNamespace(address=(HOST, 8883)),
        messages=[message],
    )


def _http_flow(
    host: str, path: str, body: Any, response: Any = None
) -> Any:
    request = types.SimpleNamespace(
        pretty_host=host,
        host=host,
        method="POST",
        path=path,
        headers={
            "Authorization": "Bearer leaked",
            "Cookie": "HWWAFSESID=leaked",
            "selectcountry": "AU",
            "appversion": "1.12.0",
        },
        get_text=lambda: json.dumps(body) if body is not None else "",
    )
    fake_response = None
    if response is not None:
        fake_response = types.SimpleNamespace(
            status_code=200, get_text=lambda: json.dumps(response)
        )
    return types.SimpleNamespace(request=request, response=fake_response)


def test_connect_credentials_never_reach_a_log() -> None:
    """The CONNECT frame carries the broker credentials: neither log may keep them."""
    password = "eyJhbGciOiJIUzUxMiJ9.eyJzdWIiOiIxMjM0NTY3ODkwIn0.AAAAbbbbCCCCddddEEEE"
    client_id = "1987639064962777089"
    packet = build_connect_packet(client_id, client_id, password)

    addon, transcript, raw, _ = _addon(raw_enabled=True)
    addon.tcp_message(_tcp_flow(packet))

    assert "CONNECT" in transcript.getvalue()
    assert password not in transcript.getvalue()
    assert client_id not in transcript.getvalue()
    assert "<CONNECT omitted: it carries the broker credentials>" in raw.getvalue()
    assert password not in raw.getvalue()
    assert password.encode().hex() not in raw.getvalue()


def test_transcript_masks_location_plate_and_identifiers() -> None:
    """The shareable transcript keeps service codes but never the plate or the location."""
    did = "did-abcdef123456"
    payload = {
        "did": did,
        "r": "req-1",
        "mt": "properties",
        "Lat": 38.912345,
        "Lng": -0.371234,
        "licensePlate": "TEST-PLATE-1",
        "plateNumber": "TEST-PLATE-1",
        "carId": "1987639064962777089",
        "vehicleId": "1987639064962777089",
        "soc": 80,
        "BcuChrgtSts": 1,
    }
    packet = build_publish_packet(f"$vdp/{did}/properties/report", payload)

    addon, transcript, _, _ = _addon()
    addon.tcp_message(_tcp_flow(packet, from_client=False))
    text = transcript.getvalue()

    assert "38.912345" not in text
    assert "-0.371234" not in text
    assert "TEST-PLATE-1" not in text
    assert "1987639064962777089" not in text
    assert did not in text
    assert "$vdp/<id:" in text
    # The telemetry the maintainer needs to debug stays readable.
    assert '"soc": 80' in text
    assert '"BcuChrgtSts": 1' in text


def test_sers_is_decoded_with_the_captured_secret_key() -> None:
    """The command codes live inside ``sers``: the transcript must show them decoded."""
    did = "did-abcdef123456"
    req_id = "req-lock-1"
    services = [
        {
            "service_code": "LockDoor",
            "command_code": "Lock_CMD",
            "params": {"strategy_code": "STRAT-1"},
        }
    ]
    login = build_publish_packet(f"$vdp/{did}/server/loginout", LOGIN_RESPONSE)
    encrypted = aes_cbc_encrypt(services, SECRET_KEY, req_id)
    command = build_publish_packet(
        "$vdp/{}/properties/set/req".format(did),
        {"did": did, "r": req_id, "mt": "properties", "sers": encrypted},
    )

    addon, transcript, raw, _ = _addon(raw_enabled=True)
    addon.tcp_message(_tcp_flow(login, from_client=False))
    addon.tcp_message(_tcp_flow(command))
    text = transcript.getvalue()

    assert "secretKey captured" in text
    assert SECRET_KEY not in text
    assert '"sers_decoded"' in text
    assert '"service_code": "LockDoor"' in text
    assert '"command_code": "Lock_CMD"' in text
    assert '"strategy_code": "STRAT-1"' in text
    assert encrypted not in text
    # The login response is never written in raw form either.
    assert "<login response omitted: it carries the secretKey>" in raw.getvalue()
    assert SECRET_KEY.encode().hex() not in raw.getvalue()


def test_sers_without_the_secret_key_says_so_instead_of_guessing() -> None:
    """Without the login response the transcript must admit it cannot decode."""
    encrypted = aes_cbc_encrypt([{"service_code": "LockDoor"}], SECRET_KEY, "req-1")
    packet = build_publish_packet(
        "$vdp/did-abcdef123456/properties/set/req",
        {"did": "did-abcdef123456", "r": "req-1", "sers": encrypted},
    )

    addon, transcript, _, _ = _addon()
    addon.tcp_message(_tcp_flow(packet))
    text = transcript.getvalue()

    assert "<unavailable: no secretKey captured yet>" in text
    assert "sers_ciphertext_chars" in text


def test_decode_matches_the_sdk_implementation() -> None:
    """Keep the vendored decoder in step with ``deepal_sdk/deepal/mqtt.py``."""
    services = [{"service_code": "LockDoor", "params": {"a": 1}}, {"service_code": "UnLockDoor"}]
    encrypted = aes_cbc_encrypt(services, SECRET_KEY_2, "req-9")

    decoded, error = addon_module.decrypt_sers(encrypted, SECRET_KEY_2, "req-9")

    assert error == ""
    assert decoded == services
    assert decoded == aes_cbc_decrypt(encrypted, SECRET_KEY_2, "req-9")


def test_raw_log_is_off_by_default() -> None:
    """A tester must opt in before any byte-level log is written."""
    addon = addon_module.MqttDump()

    assert addon.raw_enabled is False
    assert addon.raw is None
    assert addon.secret_key is None


def test_http_dump_ignores_other_apps_and_masks_the_config() -> None:
    """Only the allowlisted Deepal paths are logged, and their secrets are masked."""
    addon, _, _, http_log = _addon()

    addon.http(
        _http_flow(
            "bank.example.com",
            "/app-apigw/sda-app-control/api/v1/sda-app/car-ctrl/get-mqtt-server-config",
            {"password": "leaked"},
        )
    )
    assert http_log.getvalue() == ""

    addon.http(
        _http_flow(
            "prod-m.sda.changanauto.sg",
            "/app-apigw/sda-app-control/api/v1/sda-app/car-ctrl/get-mqtt-server-config"
            "?carId=1987639064962777089",
            {"carId": "1987639064962777089", "authType": 2, "password": "broker-pass"},
            {"host": "prod-appmq.sda.changanauto.sg", "port": 8883, "authType": 2},
        )
    )
    text = http_log.getvalue()

    assert "carId=<carid:" in text
    assert "1987639064962777089" not in text
    assert "broker-pass" not in text
    assert '"authType": 2' in text
    assert "prod-appmq.sda.changanauto.sg" in text
    assert "leaked" not in text
    assert "Authorization" not in text
    assert "Cookie" not in text
    assert '"selectcountry": "AU"' in text
