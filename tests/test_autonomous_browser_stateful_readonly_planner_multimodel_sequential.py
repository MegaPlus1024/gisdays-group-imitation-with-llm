from __future__ import annotations

import json
import urllib.error
from pathlib import Path
from typing import Any

from src.agent.autonomous_browser_stateful_readonly_planner_multimodel_benchmark import (
    build_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_packet,
)
from src.agent.autonomous_browser_stateful_readonly_planner_multimodel_sequential import (
    CONFIG_SCHEMA_VERSION,
    StartedServer,
    SequentialHttpResponse,
    run_autonomous_browser_stateful_readonly_planner_multimodel_sequential,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BENCHMARK_CONFIG_PATH = (
    PROJECT_ROOT
    / "configs"
    / "autonomous_runtime"
    / "browser_stateful_readonly_planner_frozen_raw_benchmark.example.json"
)
RUN_CONFIG_PATH = (
    PROJECT_ROOT
    / "configs"
    / "autonomous_runtime"
    / "browser_stateful_readonly_planner_sequential_run.example.json"
)
BASE_PACKET_CONFIG = (
    PROJECT_ROOT
    / "configs"
    / "autonomous_runtime"
    / "browser_stateful_readonly_planner_packet.example.json"
)
EVALUATION_MODELS_CONFIG = PROJECT_ROOT / "configs" / "evaluation_models.json"


def _benchmark_config() -> dict[str, Any]:
    return json.loads(BENCHMARK_CONFIG_PATH.read_text(encoding="utf-8"))


def _run_config() -> dict[str, Any]:
    return json.loads(RUN_CONFIG_PATH.read_text(encoding="utf-8"))


def _stage_support_files(repo_root: Path) -> None:
    packet_destination = repo_root / "configs" / "autonomous_runtime" / BASE_PACKET_CONFIG.name
    packet_destination.parent.mkdir(parents=True, exist_ok=True)
    packet_destination.write_text(BASE_PACKET_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")

    eval_destination = repo_root / "configs" / EVALUATION_MODELS_CONFIG.name
    eval_destination.parent.mkdir(parents=True, exist_ok=True)
    eval_destination.write_text(EVALUATION_MODELS_CONFIG.read_text(encoding="utf-8"), encoding="utf-8")

    benchmark_destination = repo_root / "configs" / "autonomous_runtime" / BENCHMARK_CONFIG_PATH.name
    benchmark_destination.parent.mkdir(parents=True, exist_ok=True)
    benchmark_destination.write_text(BENCHMARK_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")

    run_destination = repo_root / "configs" / "autonomous_runtime" / RUN_CONFIG_PATH.name
    run_destination.parent.mkdir(parents=True, exist_ok=True)
    run_destination.write_text(RUN_CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8")


def _build_packet(repo_root: Path) -> Path:
    _stage_support_files(repo_root)
    summary = build_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_packet(
        _benchmark_config(),
        repo_root=repo_root,
    )
    assert summary["status"] == "succeeded"
    return repo_root / str(summary["output_dir"])


def _fake_success_transport(method: str, url: str, body: bytes | None, timeout_sec: float) -> SequentialHttpResponse:
    del timeout_sec
    if method == "GET" and url.endswith("/v1/models"):
        port = url.split(":")[2].split("/")[0]
        model_id = {
            "8082": "third_model",
            "8083": "fourth_model",
            "8084": "fifth_model",
        }[port]
        return SequentialHttpResponse(
            status_code=200,
            body=json.dumps({"data": [{"id": model_id}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
    if method == "POST":
        payload = json.loads((body or b"{}").decode("utf-8"))
        scenario_id = payload["metadata"]["scenario_id"]
        model = payload["model"]
        content = json.dumps(
            {"schema_version": "fake", "model": model, "scenario_id": scenario_id},
            ensure_ascii=False,
        )
        response = {
            "choices": [{"finish_reason": "stop", "message": {"content": content}}],
        }
        return SequentialHttpResponse(
            status_code=200,
            body=json.dumps(response).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
    raise AssertionError(f"unexpected transport call: {method} {url}")


def _inspector_empty(ports: tuple[int, ...]) -> list[dict[str, Any]]:
    del ports
    return []


def test_run_config_loads_with_disabled_fifth_model() -> None:
    config = _run_config()

    assert config["schema_version"] == CONFIG_SCHEMA_VERSION
    aliases = [item["model_alias"] for item in config["model_profiles"]]
    enabled = {item["model_alias"]: item["enabled"] for item in config["model_profiles"]}
    assert aliases == ["third_model", "fourth_model", "fifth_model"]
    assert enabled["third_model"] is True
    assert enabled["fourth_model"] is True
    assert enabled["fifth_model"] is False


def test_sequential_runner_dry_run_reports_selected_models_and_request_count(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model", "fourth_model"),
        dry_run=True,
        transport=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("transport should not run")),
        server_start_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("starter should not run")),
    )

    assert summary["status"] == "succeeded"
    assert summary["models_total"] == 2
    assert summary["requests_total"] == 16
    assert summary["requests_completed"] == 0
    assert summary["requests_failed"] == 0
    assert summary["selected_models"] == ["third_model", "fourth_model"]
    assert summary["dry_run"] is True
    assert summary["start_servers"] is False
    assert summary["server_mode"] == "dry_run"
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert all(item["status"] == "dry_run" for item in summary["request_results"])


def test_sequential_runner_respects_models_filter(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        dry_run=True,
    )

    assert summary["models_total"] == 1
    assert summary["selected_models"] == ["third_model"]
    assert summary["requests_total"] == 8
    assert {item["model_alias"] for item in summary["request_results"]} == {"third_model"}


def test_sequential_runner_default_real_mode_starts_servers_and_records_lifecycle(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)
    started: list[str] = []
    stopped: list[str] = []

    def fake_start(profile, repo_root, output_root):
        del repo_root, output_root
        started.append(profile.model_alias)
        return StartedServer(
            model_alias=profile.model_alias,
            pid=123,
            started_by_script=True,
            log_dir="artifacts/autonomous_runtime_summaries/stateful_readonly_planner_multimodel_sequential/server_logs",
        )

    def fake_stop(server: StartedServer) -> None:
        stopped.append(server.model_alias)

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        transport=_fake_success_transport,
        server_start_fn=fake_start,
        server_stop_fn=fake_stop,
        port_inspector_fn=_inspector_empty,
    )

    assert summary["status"] == "succeeded"
    assert summary["start_servers"] is True
    assert summary["server_mode"] == "started_by_runner"
    assert summary["requests_completed"] == 8
    assert summary["model_execution"] is True
    assert started == ["third_model"]
    assert stopped == ["third_model"]
    model_result = summary["model_results"][0]
    assert model_result["server_started_by_runner"] is True
    assert model_result["endpoint_ready"] is True
    assert model_result["shutdown_attempted"] is True
    assert model_result["shutdown_succeeded"] is True


def test_no_start_servers_uses_existing_servers_mode_and_does_not_call_starter(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        start_servers=False,
        transport=_fake_success_transport,
        server_start_fn=lambda *args, **kwargs: (_ for _ in ()).throw(AssertionError("starter should not run")),
    )

    assert summary["status"] == "succeeded"
    assert summary["start_servers"] is False
    assert summary["server_mode"] == "existing_servers"
    assert summary["model_results"][0]["server_started_by_runner"] is False


def test_sequential_runner_skip_existing_does_not_overwrite_outputs(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)
    existing_response_path = (
        tmp_path
        / "artifacts"
        / "autonomous_runtime_planner_outputs"
        / "stateful_readonly_planner_frozen_raw_benchmark"
        / "third_model"
        / "stateful_policy_ticket_crosscheck"
        / "trial_01"
        / "response.json"
    )
    existing_raw_path = existing_response_path.parent / "raw_planner_output.txt"
    existing_response_path.parent.mkdir(parents=True, exist_ok=True)
    existing_response_path.write_text('{"saved": true}', encoding="utf-8")
    existing_raw_path.write_text("kept-existing-output", encoding="utf-8")

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        start_servers=False,
        skip_existing=True,
        transport=_fake_success_transport,
    )

    assert summary["status"] == "succeeded"
    assert summary["requests_total"] == 8
    assert summary["requests_skipped_existing"] == 1
    assert existing_response_path.read_text(encoding="utf-8") == '{"saved": true}'
    assert existing_raw_path.read_text(encoding="utf-8") == "kept-existing-output"
    skipped = [item for item in summary["request_results"] if item["status"] == "skipped_existing"]
    assert len(skipped) == 1
    assert skipped[0]["skipped_existing"] is True


def test_timeout_error_produces_structured_failed_request(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)

    def transport(method: str, url: str, body: bytes | None, timeout_sec: float) -> SequentialHttpResponse:
        if method == "GET":
            return _fake_success_transport(method, url, body, timeout_sec)
        raise TimeoutError("timed out")

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        start_servers=False,
        transport=transport,
    )

    assert summary["status"] == "completed_with_failures"
    failed = summary["request_results"][0]
    assert failed["status"] == "failed"
    assert failed["error_type"] == "timeout_error"
    assert failed["error_code"] == "endpoint_request_timeout"
    assert failed["finish_reason"] is None
    assert failed["content_length"] == 0
    assert failed["skipped_existing"] is False


def test_connection_failure_produces_structured_failed_request(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)

    def transport(method: str, url: str, body: bytes | None, timeout_sec: float) -> SequentialHttpResponse:
        if method == "GET":
            return _fake_success_transport(method, url, body, timeout_sec)
        raise ConnectionRefusedError("connection refused")

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        start_servers=False,
        transport=transport,
    )

    failed = summary["request_results"][0]
    assert failed["status"] == "failed"
    assert failed["error_type"] == "connection_refused"
    assert failed["error_code"] == "endpoint_connection_failed"


def test_http_error_produces_structured_failed_request(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)

    def transport(method: str, url: str, body: bytes | None, timeout_sec: float) -> SequentialHttpResponse:
        if method == "GET":
            return _fake_success_transport(method, url, body, timeout_sec)
        return SequentialHttpResponse(status_code=503, body=b"unavailable", headers={})

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        start_servers=False,
        transport=transport,
    )

    failed = summary["request_results"][0]
    assert failed["status"] == "failed"
    assert failed["error_type"] == "http_error"
    assert failed["error_code"] == "endpoint_request_failed"


def test_malformed_json_response_produces_structured_failed_request(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)

    def transport(method: str, url: str, body: bytes | None, timeout_sec: float) -> SequentialHttpResponse:
        if method == "GET":
            return _fake_success_transport(method, url, body, timeout_sec)
        return SequentialHttpResponse(status_code=200, body=b"{not-json", headers={})

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        start_servers=False,
        transport=transport,
    )

    failed = summary["request_results"][0]
    assert failed["status"] == "failed"
    assert failed["error_type"] == "response_parse_failed"
    assert failed["error_code"] == "response_parse_failed"


def test_malformed_response_shape_produces_structured_failed_request(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)

    def transport(method: str, url: str, body: bytes | None, timeout_sec: float) -> SequentialHttpResponse:
        if method == "GET":
            return _fake_success_transport(method, url, body, timeout_sec)
        return SequentialHttpResponse(
            status_code=200,
            body=json.dumps({"choices": [{"finish_reason": "stop", "message": {}}]}).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        start_servers=False,
        transport=transport,
    )

    failed = summary["request_results"][0]
    assert failed["status"] == "failed"
    assert failed["error_type"] == "response_shape_invalid"
    assert failed["error_code"] == "response_shape_invalid"


def test_preflight_detects_occupied_selected_port(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)

    def inspector(ports: tuple[int, ...]) -> list[dict[str, Any]]:
        assert 8082 in ports
        return [{"port": 8082, "pid": 4242}]

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        transport=_fake_success_transport,
        port_inspector_fn=inspector,
    )

    assert summary["status"] == "failed"
    assert summary["error_code"] == "selected_benchmark_port_occupied"
    assert summary["server_mode"] == "started_by_runner"


def test_allow_existing_benchmark_servers_bypasses_preflight(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)
    started: list[str] = []

    def fake_start(profile, repo_root, output_root):
        del repo_root, output_root
        started.append(profile.model_alias)
        return StartedServer(model_alias=profile.model_alias, pid=321, started_by_script=True)

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        allow_existing_benchmark_servers=True,
        transport=_fake_success_transport,
        server_start_fn=fake_start,
        port_inspector_fn=lambda ports: (_ for _ in ()).throw(AssertionError("inspector should not run")),
    )

    assert summary["status"] == "succeeded"
    assert summary["preflight_bypassed"] is True
    assert started == ["third_model"]


def test_stop_existing_benchmark_servers_uses_fake_stopper(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)
    stop_calls: list[list[dict[str, Any]]] = []

    def inspector(ports: tuple[int, ...]) -> list[dict[str, Any]]:
        if stop_calls:
            return []
        return [{"port": 8082, "pid": 9911}]

    def stopper(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
        stop_calls.append(bindings)
        return [{"port": 8082, "pid": 9911, "stop_attempted": True, "stop_succeeded": True}]

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        transport=_fake_success_transport,
        port_inspector_fn=inspector,
        port_stopper_fn=stopper,
        stop_existing_benchmark_servers=True,
        server_start_fn=lambda profile, repo_root, output_root: StartedServer(
            model_alias=profile.model_alias,
            pid=123,
            started_by_script=True,
        ),
    )

    assert summary["status"] == "succeeded"
    assert len(stop_calls) == 1
    assert stop_calls[0] == [{"port": 8082, "pid": 9911}]
    assert summary["port_preflight"]["stopped_bindings"][0]["port"] == 8082


def test_fail_fast_stops_after_first_request_failure(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)
    post_count = 0

    def transport(method: str, url: str, body: bytes | None, timeout_sec: float) -> SequentialHttpResponse:
        nonlocal post_count
        if method == "GET":
            return _fake_success_transport(method, url, body, timeout_sec)
        post_count += 1
        raise TimeoutError("timed out")

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        start_servers=False,
        fail_fast=True,
        transport=transport,
    )

    assert summary["status"] == "completed_with_failures"
    assert post_count == 1
    assert len(summary["request_results"]) == 1


def test_runner_never_enables_browser_flags(tmp_path: Path) -> None:
    packet_dir = _build_packet(tmp_path)

    summary = run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
        packet_dir=packet_dir,
        run_config_artifact=_run_config(),
        repo_root=tmp_path,
        selected_models=("third_model",),
        start_servers=False,
        transport=_fake_success_transport,
    )

    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
