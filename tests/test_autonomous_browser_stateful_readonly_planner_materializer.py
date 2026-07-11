from __future__ import annotations

import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_stateful_readonly_planner_materializer import (
    DEFAULT_MATERIALIZED_OUTPUT_DIR,
    DEFAULT_MATERIALIZED_STATE_FILENAME,
    DEFAULT_MATERIALIZED_TRACE_FILENAME,
    DEFAULT_MATERIALIZED_WORKFLOW_SUMMARY_FILENAME,
    STATE_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    TRACE_SCHEMA_VERSION,
    WORKFLOW_SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_stateful_readonly_planner_materializer,
)
from src.agent.autonomous_browser_stateful_readonly_planner_packet import (
    build_autonomous_browser_stateful_readonly_planner_packet,
)
from src.agent.autonomous_browser_stateful_readonly_workflow import build_default_stateful_readonly_workflow_scenarios

from tests import test_autonomous_browser_stateful_readonly_planner_evaluator as planner_evaluator_tests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_stateful_readonly_planner_packet.example.json"
CLI_PATH = PROJECT_ROOT / "scripts" / "materialize_autonomous_browser_stateful_readonly_planner_outputs.py"
PACKET_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_packets/stateful_readonly_planner"
MATERIALIZED_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/stateful_readonly_planner_materialized"


def _config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_cli_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_packet(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    summary = build_autonomous_browser_stateful_readonly_planner_packet(_config(), repo_root=tmp_path)
    return summary, tmp_path / PACKET_OUTPUT_DIR


def _write_outputs(packet_summary: dict[str, Any], repo_root: Path, *, missing_scenarios: set[str] | None = None) -> None:
    missing_scenarios = missing_scenarios or set()
    scenarios = build_default_stateful_readonly_workflow_scenarios()
    for record in packet_summary["request_records"]:
        scenario_id = str(record["scenario_id"])
        if scenario_id in missing_scenarios:
            continue
        payload = planner_evaluator_tests._output_for_scenario(scenarios[scenario_id])
        raw_output_path = repo_root / str(record["raw_output_path"])
        raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def test_materializer_materializes_accepted_outputs_and_artifacts(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    _write_outputs(packet_summary, tmp_path)

    summary = run_autonomous_browser_stateful_readonly_planner_materializer(packet_dir, repo_root=tmp_path)
    materialized_root = tmp_path / MATERIALIZED_OUTPUT_DIR

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["error_code"] is None
    assert summary["packet_id"] == "phase_13e2_stateful_readonly_local_planner"
    assert summary["outputs_total"] == 5
    assert summary["outputs_present"] == 5
    assert summary["outputs_missing"] == 0
    assert summary["outputs_accepted"] == 5
    assert summary["outputs_rejected"] == 0
    assert summary["workflows_materialized"] == 5
    assert summary["workflows_failed"] == 0
    assert summary["actions_total"] > 0
    assert summary["facts_total"] > 0
    assert summary["evidence_items_total"] > 0
    assert summary["final_answers_total"] == 5
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["real_network_traffic"] is False
    assert summary["fixture_only"] is True
    assert summary["no_runtime_execution"] is True
    assert summary["output_dir"] == MATERIALIZED_OUTPUT_DIR
    assert len(summary["materialized_workflow_summaries"]) == 5
    assert all(not Path(item).is_absolute() for item in [summary["output_dir"]])

    summary_path = materialized_root / "autonomous_browser_stateful_readonly_planner_materializer_summary.json"
    assert summary_path.exists()

    first_workflow = summary["materialized_workflow_summaries"][0]
    assert first_workflow["schema_version"] == WORKFLOW_SUMMARY_SCHEMA_VERSION
    assert first_workflow["status"] == "succeeded"
    assert first_workflow["error_code"] is None
    assert first_workflow["failure_class"] == "none"
    assert first_workflow["model_execution"] is False
    assert first_workflow["real_browser_execution"] is False
    assert first_workflow["playwright_execution"] is False
    assert first_workflow["browser_opened"] is False
    assert first_workflow["no_runtime_execution"] is True
    assert "source_response_path" not in first_workflow

    state_path = materialized_root / "third_model" / "stateful_policy_ticket_crosscheck" / DEFAULT_MATERIALIZED_STATE_FILENAME
    trace_path = materialized_root / "third_model" / "stateful_policy_ticket_crosscheck" / DEFAULT_MATERIALIZED_TRACE_FILENAME
    workflow_summary_path = materialized_root / "third_model" / "stateful_policy_ticket_crosscheck" / DEFAULT_MATERIALIZED_WORKFLOW_SUMMARY_FILENAME
    state_payload = json.loads(state_path.read_text(encoding="utf-8"))
    trace_payload = json.loads(trace_path.read_text(encoding="utf-8"))
    workflow_summary_payload = json.loads(workflow_summary_path.read_text(encoding="utf-8"))

    assert state_path.exists()
    assert trace_path.exists()
    assert workflow_summary_path.exists()
    assert state_payload["schema_version"] == STATE_SCHEMA_VERSION
    assert state_payload["workflow_id"] == "stateful_policy_ticket_crosscheck"
    assert state_payload["model_execution"] is False
    assert state_payload["real_browser_execution"] is False
    assert state_payload["playwright_execution"] is False
    assert state_payload["browser_opened"] is False
    assert state_payload["fixture_only"] is True
    assert state_payload["no_runtime_execution"] is True
    assert trace_payload["schema_version"] == TRACE_SCHEMA_VERSION
    assert trace_payload["status"] == "planned"
    assert trace_payload["trace_entries"]
    assert trace_payload["trace_entries"][0]["step_index"] == 1
    assert trace_payload["trace_entries"][0]["status"] == "planned"
    assert workflow_summary_payload["schema_version"] == WORKFLOW_SUMMARY_SCHEMA_VERSION
    assert workflow_summary_payload["status"] == "succeeded"
    assert "source_response_path" not in workflow_summary_payload


def test_materializer_reports_missing_outputs_without_counting_them_as_rejected(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    _write_outputs(packet_summary, tmp_path, missing_scenarios={"stateful_approval_policy_crosscheck"})

    summary = run_autonomous_browser_stateful_readonly_planner_materializer(packet_dir, repo_root=tmp_path)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "completed_with_missing_outputs"
    assert summary["error_code"] == "missing_captured_outputs"
    assert summary["outputs_total"] == 5
    assert summary["outputs_present"] == 4
    assert summary["outputs_missing"] == 1
    assert summary["outputs_accepted"] == 4
    assert summary["outputs_rejected"] == 0
    assert summary["workflows_materialized"] == 4
    assert summary["workflows_failed"] == 1
    assert summary["failure_class_counts"]["missing_output"] == 1
    assert any(item["status"] == "missing" for item in summary["materialized_workflow_summaries"])


def test_materializer_rejects_invalid_packet_config_without_crash(tmp_path: Path) -> None:
    summary = run_autonomous_browser_stateful_readonly_planner_materializer(tmp_path / "missing_packet_dir", repo_root=tmp_path)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "failed"
    assert summary["error_code"] == "config_validation_failed"
    assert summary["outputs_total"] == 0
    assert summary["outputs_present"] == 0
    assert summary["outputs_missing"] == 0
    assert summary["outputs_accepted"] == 0
    assert summary["outputs_rejected"] == 0
    assert summary["workflows_materialized"] == 0
    assert summary["workflows_failed"] == 0
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["no_runtime_execution"] is True


def test_cli_smoke_succeeds_and_writes_summary_file(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    _write_outputs(packet_summary, tmp_path)
    module = _load_cli_module(CLI_PATH)
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = tmp_path
    try:
        exit_code = module.main(
            [
                "--packet-dir",
                PACKET_OUTPUT_DIR,
                "--output-dir",
                MATERIALIZED_OUTPUT_DIR,
            ]
        )
    finally:
        module.PROJECT_ROOT = original_project_root

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert payload["status"] == "succeeded"
    assert payload["output_dir"] == MATERIALIZED_OUTPUT_DIR
    assert payload["no_runtime_execution"] is True
    assert payload["real_browser_execution"] is False
    assert payload["playwright_execution"] is False
    assert payload["browser_opened"] is False
    assert (tmp_path / MATERIALIZED_OUTPUT_DIR / "autonomous_browser_stateful_readonly_planner_materializer_summary.json").exists()


def test_cli_smoke_reports_missing_outputs_with_nonzero_exit_code(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    _write_outputs(packet_summary, tmp_path, missing_scenarios={"stateful_ticket_priority_digest"})
    module = _load_cli_module(CLI_PATH)
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = tmp_path
    try:
        exit_code = module.main(
            [
                "--packet-dir",
                PACKET_OUTPUT_DIR,
                "--output-dir",
                MATERIALIZED_OUTPUT_DIR,
            ]
        )
    finally:
        module.PROJECT_ROOT = original_project_root

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert payload["status"] == "completed_with_missing_outputs"
    assert payload["error_code"] == "missing_captured_outputs"
    assert payload["outputs_missing"] == 1
    assert payload["outputs_rejected"] == 0

