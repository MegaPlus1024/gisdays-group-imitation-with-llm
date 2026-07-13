from __future__ import annotations

import json
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


def _fake_transport(method: str, url: str, body: bytes | None, timeout_sec: float) -> SequentialHttpResponse:
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
            {
                "schema_version": "fake",
                "model": model,
                "scenario_id": scenario_id,
            },
            ensure_ascii=False,
        )
        response = {
            "choices": [
                {
                    "finish_reason": "stop",
                    "message": {"content": content},
                }
            ]
        }
        return SequentialHttpResponse(
            status_code=200,
            body=json.dumps(response).encode("utf-8"),
            headers={"Content-Type": "application/json"},
        )
    raise AssertionError(f"unexpected transport call: {method} {url}")


def test_run_config_loads_with_disabled_fifth_model() -> None:
    config = _run_config()

    assert config["schema_version"] == CONFIG_SCHEMA_VERSION
    aliases = [item["model_alias"] for item in config["model_profiles"]]
    enabled = {
        item["model_alias"]: item["enabled"]
        for item in config["model_profiles"]
    }
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
        start_servers=False,
        dry_run=True,
    )

    assert summary["status"] == "succeeded"
    assert summary["models_total"] == 2
    assert summary["requests_total"] == 16
    assert summary["requests_completed"] == 0
    assert summary["requests_failed"] == 0
    assert summary["selected_models"] == ["third_model", "fourth_model"]
    assert summary["dry_run"] is True
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
        start_servers=False,
        dry_run=True,
    )

    assert summary["models_total"] == 1
    assert summary["selected_models"] == ["third_model"]
    assert summary["requests_total"] == 8
    assert {item["model_alias"] for item in summary["request_results"]} == {"third_model"}


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
        dry_run=False,
        skip_existing=True,
        transport=_fake_transport,
    )

    assert summary["status"] == "succeeded"
    assert summary["requests_total"] == 8
    assert summary["requests_skipped_existing"] == 1
    assert existing_response_path.read_text(encoding="utf-8") == '{"saved": true}'
    assert existing_raw_path.read_text(encoding="utf-8") == "kept-existing-output"
    skipped = [
        item
        for item in summary["request_results"]
        if item["status"] == "skipped_existing"
    ]
    assert len(skipped) == 1


def test_sequential_runner_fake_transport_and_injected_server_lifecycle(tmp_path: Path) -> None:
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
        start_servers=True,
        dry_run=False,
        skip_existing=False,
        transport=_fake_transport,
        server_start_fn=fake_start,
        server_stop_fn=fake_stop,
    )

    assert summary["status"] == "succeeded"
    assert summary["models_total"] == 1
    assert summary["requests_total"] == 8
    assert summary["requests_completed"] == 8
    assert summary["model_execution"] is True
    assert started == ["third_model"]
    assert stopped == ["third_model"]
    assert summary["model_results"][0]["server_started_by_script"] is True
