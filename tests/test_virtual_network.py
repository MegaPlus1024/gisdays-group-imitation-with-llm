from __future__ import annotations

import copy
import json
import sys
from pathlib import Path

import pytest

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.virtual_network import (  # noqa: E402
    NetworkEvent,
    VirtualNetworkSpec,
    VirtualNetworkValidationError,
    append_network_event_jsonl,
    load_virtual_network_spec,
    read_network_events_jsonl,
    write_network_event_jsonl,
)


CONFIG_PATH = Path("configs/virtual_networks/local_office_network_v1.json")


def _payload() -> dict:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def test_load_virtual_network_config_success() -> None:
    spec = load_virtual_network_spec(CONFIG_PATH)

    assert spec.network_id == "local_office_network_v1"
    assert spec.get_host("office_user_host") is not None
    assert spec.get_service("local_intranet") is not None
    assert len(spec.hosts) >= 3


def test_virtual_network_to_dict_from_dict_roundtrip() -> None:
    spec = load_virtual_network_spec(CONFIG_PATH)

    roundtrip = VirtualNetworkSpec.from_dict(spec.to_dict())

    assert roundtrip.to_dict() == spec.to_dict()


def test_duplicate_host_id_rejected() -> None:
    payload = _payload()
    duplicate = copy.deepcopy(payload["hosts"][0])
    payload["hosts"].append(duplicate)

    with pytest.raises(VirtualNetworkValidationError, match="host_id"):
        VirtualNetworkSpec.from_dict(payload)


def test_duplicate_service_id_rejected() -> None:
    payload = _payload()
    duplicate = copy.deepcopy(payload["services"][0])
    payload["services"].append(duplicate)

    with pytest.raises(VirtualNetworkValidationError, match="service_id"):
        VirtualNetworkSpec.from_dict(payload)


def test_unknown_service_reference_rejected() -> None:
    payload = _payload()
    payload["hosts"][0]["allowed_service_ids"].append("missing_service")

    with pytest.raises(VirtualNetworkValidationError, match="unknown service_id"):
        VirtualNetworkSpec.from_dict(payload)


def test_allowed_localhost_url_is_accepted() -> None:
    spec = load_virtual_network_spec(CONFIG_PATH)

    assert spec.is_url_allowed("office_user_host", "http://localhost:8088/tickets/1") is True
    assert spec.is_url_allowed("office_user_host", "http://127.0.0.1:8088/tickets/1") is True


def test_external_url_is_rejected() -> None:
    spec = load_virtual_network_spec(CONFIG_PATH)

    assert spec.is_url_allowed("office_user_host", "https://example.com/report") is False


def test_file_url_is_rejected() -> None:
    spec = load_virtual_network_spec(CONFIG_PATH)

    assert spec.is_url_allowed("office_user_host", "file:///tmp/report.html") is False


def test_service_allowlist_works() -> None:
    spec = load_virtual_network_spec(CONFIG_PATH)

    assert spec.is_service_allowed("office_user_host", "ticket_board") is True
    assert spec.is_service_allowed("maintenance_host", "ticket_board") is False
    assert spec.is_service_allowed("missing_host", "shared_docs") is False


def test_network_events_jsonl_roundtrip(tmp_path: Path) -> None:
    path = tmp_path / "network_events.jsonl"
    first = NetworkEvent(
        timestamp_utc="2026-01-01T00:00:00+00:00",
        agent_id="office_agent",
        host_id="office_user_host",
        action="browser_navigate",
        target_service_id="local_intranet",
        target_url="http://localhost:8088",
        target_path=None,
        allowed=True,
        status="success",
        details={"note": "offline fixture"},
    )
    second = NetworkEvent(
        timestamp_utc="2026-01-01T00:00:01+00:00",
        agent_id="developer_agent",
        host_id="developer_host",
        action="read_file",
        target_service_id="shared_docs",
        target_url=None,
        target_path="experiments/virtual_network/local_office_network_v1/shared_docs/note.md",
        allowed=True,
        status="success",
        details={},
    )

    write_network_event_jsonl(first, path)
    append_network_event_jsonl(second, path)
    events = read_network_events_jsonl(path)

    assert [event.to_dict() for event in events] == [first.to_dict(), second.to_dict()]


def test_invalid_workspace_mode_rejected() -> None:
    payload = _payload()
    payload["shared_workspaces"][0]["mode"] = "admin"

    with pytest.raises(VirtualNetworkValidationError, match="invalid mode"):
        VirtualNetworkSpec.from_dict(payload)


def test_sample_config_does_not_contain_private_windows_user_path() -> None:
    text = CONFIG_PATH.read_text(encoding="utf-8")
    windows_user_path = "C:" + "\\Users\\"
    slash_user_path = "C:" + "/Users/"
    telegram_path = "Downloads" + "\\Telegram Desktop"
    codex_path = "." + "codex"

    assert windows_user_path not in text
    assert slash_user_path not in text
    assert telegram_path not in text
    assert codex_path not in text
