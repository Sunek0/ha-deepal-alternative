"""Tests for the read-only SDA MQTT broker probe (``tools/sda-mqtt-probe``).

The probe is a tester-facing helper outside the SDK package, so it is imported
with mitmproxy-free stubs and driven against a fake broker, exactly like the
SDK's own MQTT tests. The whole file is skipped where ``tools/`` is not
published (the HACS mirror does not ship it... it does ship ``tools/`` since
1.4.0-beta.4, but keep the guard so the suite also works from a plain SDK copy).
"""

from __future__ import annotations

import asyncio
import importlib.util
import json
import sys
from pathlib import Path
from typing import Any, Optional

import pytest

from deepal.mqtt import (
    aes_cbc_encrypt,
    build_publish_packet,
    build_subscribe_packet,
)

_PROBE = Path(__file__).resolve().parents[2] / "tools" / "sda-mqtt-probe" / "probe.py"

if not _PROBE.exists():  # pragma: no cover - a plain SDK checkout has no tools/
    pytest.skip(
        f"probe not present at {_PROBE} (tools/ is not published)", allow_module_level=True
    )


def _load_probe() -> Any:
    """Import the probe module without running its CLI."""
    spec = importlib.util.spec_from_file_location("deepal_sda_mqtt_probe", _PROBE)
    module = importlib.util.module_from_spec(spec)
    sys.modules["deepal_sda_mqtt_probe"] = module
    spec.loader.exec_module(module)
    return module


probe = _load_probe()

SECRET_KEY = "0123456789abcdef"
AUTH_TOKEN = "auth-token-value-1234567890"
CAR_ID = "1987639064962777089"
DID = "1943772814528950273"

BROKER_CONFIG = {
    "code": "000000",
    "data": {
        "host": "prod-appmq.sda.changanauto.sg",
        "port": 8883,
        "clusterName": "APN1",
        "authType": 2,
        "userName": "broker-user",
        "password": "broker-password",
        "clientId": DID,
    },
}


class _FakeWriter:
    def __init__(self) -> None:
        self.writes: list[bytes] = []
        self.closed = False

    def write(self, data: bytes) -> None:
        self.writes.append(data)

    async def drain(self) -> None:
        pass

    def close(self) -> None:
        self.closed = True

    async def wait_closed(self) -> None:
        pass

    def publishes(self) -> list[tuple[str, dict[str, Any]]]:
        """Return ``(topic, payload)`` of every PUBLISH written to the broker."""
        from deepal.mqtt import parse_publish

        out: list[tuple[str, dict[str, Any]]] = []
        for packet in self.writes:
            if packet[0] >> 4 != 3:
                continue
            pos, multiplier, remaining = 1, 1, 0
            while True:
                byte = packet[pos]
                pos += 1
                remaining += (byte & 0x7F) * multiplier
                if not byte & 0x80:
                    break
                multiplier *= 128
            topic, payload, _ = parse_publish(packet[0], packet[pos : pos + remaining])
            out.append((topic, payload))
        return out


def _connack(reason: int) -> bytes:
    return bytes([0x20, 0x02, 0x00, reason])


def _suback(packet_id: int, reasons: list[int]) -> bytes:
    body = packet_id.to_bytes(2, "big") + bytes(reasons)
    return bytes([0x90, len(body)]) + body


class _Broker:
    """A scripted broker: whatever is pre-fed is consumed in order."""

    def __init__(self, script: bytes, secret_key: Optional[str] = None) -> None:
        self.reader = asyncio.StreamReader()
        self.writer = _FakeWriter()
        self.secret_key = secret_key
        self.reader.feed_data(script)

    @property
    def writes(self) -> list[bytes]:
        return self.writer.writes


def _install(monkeypatch: Any, broker: _Broker) -> dict[str, Any]:
    captured: dict[str, Any] = {}

    async def fake_open_connection(host, port, *, ssl=None, server_hostname=None):
        captured.update(host=host, port=port, ssl=ssl, server_hostname=server_hostname)
        return broker.reader, broker.writer

    monkeypatch.setattr(asyncio, "open_connection", fake_open_connection)
    return captured


def _command_script(service_code: str = "LockDoor") -> bytes:
    """CONNACK success, SUBACK granted, login response, then an encrypted command."""
    req_id = "req-lock-1"
    login_response = build_publish_packet(
        f"$vdp/{DID}/server/loginout",
        {"r": "login-1", "rs": [{"params": {"secretKey": SECRET_KEY}}]},
    )
    command = build_publish_packet(
        f"$vdp/{DID}/properties/set/req",
        {
            "did": DID,
            "r": req_id,
            "mt": "properties",
            "sers": aes_cbc_encrypt(
                [{"service_code": service_code, "command_code": "Lock_CMD"}],
                SECRET_KEY,
                req_id,
            ),
        },
    )
    subscribe = build_subscribe_packet(1, ["$vdp/%s/#" % DID])
    return (
        _connack(0x00)
        + _suback(1, [0x01] * (len(subscribe) and 1))
        + login_response
        + command
    )


@pytest.mark.asyncio
async def test_probe_connects_subscribes_and_decodes_a_received_command(
    monkeypatch, tmp_path
) -> None:
    broker = _Broker(_command_script())
    captured = _install(monkeypatch, broker)
    log_path = tmp_path / "probe.log"
    probe._LOG_FILE = log_path.open("w", encoding="utf-8")

    config = probe.parse_broker_config(BROKER_CONFIG)
    report = await probe.probe_broker(
        config,
        AUTH_TOKEN,
        DID,
        ["$vdp/%s/#" % DID],
        seconds=0.4,
        allow_login=False,
        timeout=5.0,
    )
    probe._LOG_FILE.close()

    assert report["connected"] is True
    assert captured["host"] == "prod-appmq.sda.changanauto.sg"
    assert captured["port"] == 8883
    assert captured["server_hostname"] == "prod-appmq.sda.changanauto.sg"
    assert report["secret_key_seen"] is True
    decoded = [
        message["payload"].get("sers_decoded")
        for message in report["messages"]
        if isinstance(message["payload"].get("sers_decoded"), list)
    ]
    assert decoded == [[{"service_code": "LockDoor", "command_code": "Lock_CMD"}]]

    log = log_path.read_text(encoding="utf-8")
    assert SECRET_KEY not in log
    assert AUTH_TOKEN not in log
    assert CAR_ID not in log
    assert DID not in log
    assert "Lock_CMD" in log  # the answer we are after stays readable


@pytest.mark.asyncio
async def test_probe_never_publishes_a_control_topic(monkeypatch, tmp_path) -> None:
    broker = _Broker(_connack(0x00) + _suback(1, [0x01]))
    _install(monkeypatch, broker)
    probe._LOG_FILE = (tmp_path / "probe.log").open("w", encoding="utf-8")

    await probe.probe_broker(
        probe.parse_broker_config(BROKER_CONFIG),
        AUTH_TOKEN,
        DID,
        ["$vdp/%s/#" % DID],
        seconds=0.3,
        allow_login=True,
        timeout=5.0,
    )
    probe._LOG_FILE.close()

    topics = [topic for topic, _ in broker.writer.publishes()]
    assert topics == ["$vdp/%s/client/loginout" % DID]
    for topic in topics:
        assert not any(marker in topic for marker in probe.CONTROL_TOPIC_MARKERS)


@pytest.mark.asyncio
async def test_probe_tries_the_next_identity_when_the_broker_rejects_one(
    monkeypatch, tmp_path
) -> None:
    broker = _Broker(_connack(0x86) + _connack(0x00) + _suback(1, [0x01]))
    _install(monkeypatch, broker)
    probe._LOG_FILE = (tmp_path / "probe.log").open("w", encoding="utf-8")

    report = await probe.probe_broker(
        probe.parse_broker_config(BROKER_CONFIG),
        AUTH_TOKEN,
        DID,
        ["$vdp/%s/#" % DID],
        seconds=0.3,
        allow_login=False,
        timeout=5.0,
    )
    probe._LOG_FILE.close()

    assert report["connected"] is True
    reasons = [attempt.get("reason_name") for attempt in report["attempts"]]
    assert reasons == ["bad user name or password", "success"]
    assert report["identity"] == "authToken as password"


def test_connect_candidates_start_with_the_reported_identity() -> None:
    config = probe.parse_broker_config(BROKER_CONFIG)

    candidates = probe.connect_candidates(config, AUTH_TOKEN, DID)

    assert candidates[0] == {
        "label": "config-reported identity",
        "client_id": DID,
        "username": "broker-user",
        "password": "broker-password",
    }
    labels = [candidate["label"] for candidate in candidates]
    assert "authToken as password" in labels
    assert len({(c["client_id"], c["username"], c["password"]) for c in candidates}) == len(
        candidates
    )


def test_broker_config_is_parsed_and_credentials_are_masked(tmp_path) -> None:
    config = probe.parse_broker_config(BROKER_CONFIG)

    assert config["host"] == "prod-appmq.sda.changanauto.sg"
    assert config["port"] == 8883
    assert config["cluster_name"] == "APN1"
    assert config["auth_type"] == 2

    rendered = json.dumps(probe.redact(BROKER_CONFIG), ensure_ascii=False)
    assert "broker-password" not in rendered
    assert "broker-user" not in rendered
    assert DID not in rendered
    assert "prod-appmq.sda.changanauto.sg" in rendered
    assert '"authType": 2' in rendered


def test_topic_masking_keeps_the_shape() -> None:
    assert probe.mask_topic(f"$vdp/{DID}/properties/set/req").endswith(
        "/properties/set/req"
    )
    assert DID not in probe.mask_topic(f"$vdp/{DID}/properties/set/req")
    assert probe.mask_topic("$SYS/broker/uptime") == "$SYS/broker/uptime"


def test_decode_sers_says_when_it_cannot_decode() -> None:
    encrypted = aes_cbc_encrypt([{"service_code": "LockDoor"}], SECRET_KEY, "r-1")

    without_key = probe.decode_sers({"r": "r-1", "sers": encrypted}, None)
    assert without_key["sers_decoded"] == "<unavailable: no secretKey yet>"
    assert without_key["sers_ciphertext_chars"] == len(encrypted)

    wrong_key = probe.decode_sers({"r": "r-1", "sers": encrypted}, "fedcba9876543210")
    assert wrong_key["sers_decoded"].startswith("<unavailable:")

    with_key = probe.decode_sers({"r": "r-1", "sers": encrypted}, SECRET_KEY)
    assert with_key["sers_decoded"] == [{"service_code": "LockDoor"}]
