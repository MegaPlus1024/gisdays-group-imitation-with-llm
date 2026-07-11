from __future__ import annotations

import builtins
import importlib.util
import json
import shutil
import tempfile
from pathlib import Path
from typing import Any, Mapping

import pytest

import src.agent.autonomous_browser_stateful_readonly_planner_variance as variance_module
from src.agent.autonomous_browser_stateful_readonly_planner_variance import (
    EVALUATOR_SUMMARY_SCHEMA_VERSION,
    MATERIALIZER_SUMMARY_SCHEMA_VERSION,
    PACKET_SCHEMA_VERSION,
    PACKET_SUMMARY_SCHEMA_VERSION,
    RUNTIME_CONFIG_SCHEMA_VERSION,
    build_autonomous_browser_stateful_readonly_planner_variance_packet,
    run_autonomous_browser_stateful_readonly_planner_variance_evaluator,
    run_autonomous_browser_stateful_readonly_planner_variance_materializer,
)
from src.agent.autonomous_browser_stateful_readonly_workflow import build_default_stateful_readonly_workflow_scenarios

from tests import test_autonomous_browser_stateful_readonly_planner_evaluator as planner_evaluator_tests


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_stateful_readonly_planner_variance.example.json"
PACKET_CLI_PATH = PROJECT_ROOT / "scripts" / "build_autonomous_browser_stateful_readonly_planner_variance_packet.py"
EVALUATOR_CLI_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_stateful_readonly_planner_variance_evaluator.py"
MATERIALIZER_CLI_PATH = PROJECT_ROOT / "scripts" / "materialize_autonomous_browser_stateful_readonly_planner_variance_outputs.py"
PACKET_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_packets/stateful_readonly_planner_variance"
MATERIALIZED_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/stateful_readonly_planner_variance_materialized"
BASE_PACKET_CONFIG_RELATIVE = Path("configs/autonomous_runtime/browser_stateful_readonly_planner_packet.example.json")
VARIANCE_CONFIG_RELATIVE = Path("configs/autonomous_runtime/browser_stateful_readonly_planner_variance.example.json")
VARIANCE_SCENARIO_IDS = [
    "stateful_policy_ticket_crosscheck",
    "stateful_approval_policy_crosscheck",
    "stateful_intranet_overview_digest",
    "stateful_ticket_priority_digest",
    "stateful_policy_search_marker_review",
]


def _config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_cli_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _stage_base_packet_config(repo_root: Path) -> None:
    destination = repo_root / BASE_PACKET_CONFIG_RELATIVE
    destination.parent.mkdir(parents=True, exist_ok=True)
    shutil.copyfile(PROJECT_ROOT / BASE_PACKET_CONFIG_RELATIVE, destination)


def _stage_variance_config(repo_root: Path, *, bom: bool = False) -> Path:
    destination = repo_root / VARIANCE_CONFIG_RELATIVE
    destination.parent.mkdir(parents=True, exist_ok=True)
    text = CONFIG_PATH.read_text(encoding="utf-8")
    destination.write_text(text, encoding="utf-8-sig" if bom else "utf-8")
    return destination


def _build_packet(tmp_path: Path, config: dict[str, Any] | None = None) -> tuple[dict[str, Any], Path]:
    _stage_base_packet_config(tmp_path)
    summary = build_autonomous_browser_stateful_readonly_planner_variance_packet(config or _config(), repo_root=tmp_path)
    return summary, tmp_path / PACKET_OUTPUT_DIR


def _write_outputs(packet_summary: dict[str, Any], repo_root: Path) -> None:
    scenarios = build_default_stateful_readonly_workflow_scenarios()
    for record in packet_summary["request_records"]:
        scenario = scenarios[str(record["scenario_id"])]
        payload = planner_evaluator_tests._output_for_scenario(scenario)
        raw_output_path = repo_root / str(record["raw_output_path"])
        response_path = repo_root / str(record["response_path"])
        raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_output = json.dumps(payload, ensure_ascii=False, indent=2)
        raw_output_path.write_text(raw_output, encoding="utf-8")
        _write_json(
            response_path,
            {
                "choices": [
                    {
                        "finish_reason": "stop",
                        "message": {"content": raw_output},
                    }
                ],
                "usage": {"prompt_tokens": 312, "completion_tokens": 185, "total_tokens": 497},
            },
        )


def _fake_variance_request_records(
    scenario_ids: list[str],
    *,
    trial_labels: tuple[str, ...] = ("trial_01", "trial_02", "trial_03"),
) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for scenario_id in scenario_ids:
        for index, trial_label in enumerate(trial_labels, start=1):
            trial_id = f"{scenario_id}__{trial_label}"
            records.append(
                {
                    "model_alias": "third_model",
                    "scenario_id": scenario_id,
                    "trial_id": trial_id,
                    "trial_label": trial_label,
                    "workflow_id": scenario_id,
                    "raw_output_path": f"artifacts/autonomous_runtime_planner_outputs/stateful_readonly_planner_variance/third_model/{scenario_id}/{trial_label}/raw_planner_output.txt",
                    "response_path": f"artifacts/autonomous_runtime_planner_outputs/stateful_readonly_planner_variance/third_model/{scenario_id}/{trial_label}/response.json",
                    "request_path": f"artifacts/autonomous_runtime_planner_packets/stateful_readonly_planner_variance/third_model/{scenario_id}/{trial_label}/request.json",
                    "output_path": f"artifacts/autonomous_runtime_planner_outputs/stateful_readonly_planner_variance/third_model/{scenario_id}/{trial_label}/raw_planner_output.txt",
                    "trial_index": index,
                }
            )
    return records


def _fake_variance_packet_context(
    records: list[dict[str, Any]],
    *,
    scenario_ids: list[str] | None = None,
) -> dict[str, Any]:
    return {
        "status": "ok",
        "packet_id": "phase_13e4_stateful_readonly_planner_variance",
        "packet_output_dir": PACKET_OUTPUT_DIR,
        "materialized_output_dir": MATERIALIZED_OUTPUT_DIR,
        "model_aliases": ["third_model"],
        "scenario_ids": scenario_ids or VARIANCE_SCENARIO_IDS,
        "trial_ids": ["trial_01", "trial_02", "trial_03"],
        "request_records": records,
        "limitations": [
            "offline repeated stateful planner variance only",
            "manual third_model runs only",
            "no model calls by Codex",
            "no real browser execution",
            "fixture-backed replay remains offline only",
            "not production browser automation",
        ],
    }


def _fake_variance_trial_result(
    record: Mapping[str, Any],
    *,
    status: str,
    validation_status: str,
    workflow_status: str,
    error_code: str | None,
    failure_class: str,
    actions_total: int,
    facts_total: int,
    evidence_items_total: int,
    final_answer_present: bool,
    finish_reason: str = "stop",
) -> dict[str, Any]:
    scenario_id = str(record["scenario_id"])
    trial_id = str(record["trial_id"])
    trial_label = str(record.get("trial_label") or trial_id.split("__")[-1])
    base_output_path = f"artifacts/autonomous_runtime_planner_outputs/stateful_readonly_planner_variance/third_model/{scenario_id}/{trial_label}/raw_planner_output.txt"
    base_materialized_dir = f"artifacts/autonomous_runtime_summaries/stateful_readonly_planner_variance_materialized/third_model/{scenario_id}/{trial_label}"
    return {
        "model_alias": "third_model",
        "scenario_id": scenario_id,
        "trial_id": trial_id,
        "trial_label": trial_label,
        "status": status,
        "error_code": error_code,
        "failure_class": failure_class,
        "finish_reason": finish_reason,
        "validation_status": validation_status,
        "workflow_status": workflow_status,
        "actions_total": actions_total,
        "facts_total": facts_total,
        "evidence_items_total": evidence_items_total,
        "final_answer_present": final_answer_present,
        "source_output_path": base_output_path,
        "captured_output_present": True,
        "no_runtime_execution": True,
        "model_execution": False,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
        "state_path": f"{base_materialized_dir}/materialized_state.json" if status == "succeeded" else None,
        "trace_path": f"{base_materialized_dir}/materialized_trace.json" if status == "succeeded" else None,
        "workflow_summary_path": f"{base_materialized_dir}/materialized_workflow_summary.json",
    }


def _fake_variance_failure_result(record: Mapping[str, Any]) -> dict[str, Any]:
    scenario_id = str(record["scenario_id"])
    if scenario_id in {"stateful_policy_ticket_crosscheck", "stateful_approval_policy_crosscheck"}:
        error_code = "fact_value_mismatch"
        actions_total = 7 if scenario_id == "stateful_approval_policy_crosscheck" else 4
        facts_total = 4 if scenario_id == "stateful_approval_policy_crosscheck" else 6
        evidence_items_total = 4 if scenario_id == "stateful_approval_policy_crosscheck" else 2
    elif scenario_id == "stateful_intranet_overview_digest":
        error_code = "browser_click_target_not_found"
        actions_total = 4
        facts_total = 4
        evidence_items_total = 4
    elif scenario_id == "stateful_ticket_priority_digest":
        error_code = "browser_click_target_not_found"
        actions_total = 5
        facts_total = 10
        evidence_items_total = 2
    else:
        error_code = "final_answer_citation_missing"
        actions_total = 2
        facts_total = 2
        evidence_items_total = 2
    return _fake_variance_trial_result(
        record,
        status="failed",
        validation_status="accepted",
        workflow_status="failed",
        error_code=error_code,
        failure_class="model_failed_task",
        actions_total=actions_total,
        facts_total=facts_total,
        evidence_items_total=evidence_items_total,
        final_answer_present=True,
    )


def _fake_variance_success_result(record: Mapping[str, Any]) -> dict[str, Any]:
    return _fake_variance_trial_result(
        record,
        status="succeeded",
        validation_status="accepted",
        workflow_status="succeeded",
        error_code=None,
        failure_class="none",
        actions_total=4,
        facts_total=6,
        evidence_items_total=2,
        final_answer_present=True,
    )


def _fake_variance_rejected_result(record: Mapping[str, Any]) -> dict[str, Any]:
    return _fake_variance_trial_result(
        record,
        status="failed",
        validation_status="rejected",
        workflow_status="failed",
        error_code="output_schema_invalid",
        failure_class="validation_error",
        actions_total=0,
        facts_total=0,
        evidence_items_total=0,
        final_answer_present=False,
    )


def _patch_fake_packet_context(monkeypatch: pytest.MonkeyPatch, context: dict[str, Any]) -> None:
    monkeypatch.setattr(variance_module, "_load_packet_context", lambda packet_dir, *, repo_root: context)


def test_packet_builder_writes_expected_files_and_summary(tmp_path: Path) -> None:
    _stage_base_packet_config(tmp_path)
    summary = build_autonomous_browser_stateful_readonly_planner_variance_packet(_config(), repo_root=tmp_path)
    output_dir = tmp_path / PACKET_OUTPUT_DIR

    assert summary["schema_version"] == PACKET_SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["packet_id"] == "phase_13e4_stateful_readonly_planner_variance"
    assert summary["models_total"] == 1
    assert summary["scenarios_total"] == 5
    assert summary["trials_per_scenario"] == 3
    assert summary["trials_total"] == 15
    assert summary["model_aliases"] == ["third_model"]
    assert summary["scenario_ids"] == [
        "stateful_policy_ticket_crosscheck",
        "stateful_approval_policy_crosscheck",
        "stateful_intranet_overview_digest",
        "stateful_ticket_priority_digest",
        "stateful_policy_search_marker_review",
    ]
    assert summary["trial_ids"] == ["trial_01", "trial_02", "trial_03"]
    assert summary["commands_count"] == 40
    assert len(summary["request_records"]) == 15
    assert len(summary["packet_files"]) >= 12
    assert all(not Path(item).is_absolute() for item in summary["packet_files"])

    packet_path = output_dir / "autonomous_browser_stateful_readonly_planner_variance_packet.json"
    summary_path = output_dir / "autonomous_browser_stateful_readonly_planner_variance_packet_summary.json"
    commands_path = output_dir / "commands.json"
    commands_md_path = output_dir / "commands.md"
    request_paths_path = output_dir / "request_paths.json"
    output_paths_path = output_dir / "output_paths.json"
    trial_records_path = output_dir / "request_records.json"
    runtime_config_path = output_dir / "variance_config.local.json"
    schema_doc_path = output_dir / "expected_output_schema.md"
    prompt_path = output_dir / "prompts" / "stateful_policy_ticket_crosscheck" / "planner_prompt.compact.txt"
    ticket_priority_prompt_path = output_dir / "prompts" / "stateful_ticket_priority_digest" / "planner_prompt.compact.txt"

    for path in (
        packet_path,
        summary_path,
        commands_path,
        commands_md_path,
        request_paths_path,
        output_paths_path,
        trial_records_path,
        runtime_config_path,
        schema_doc_path,
        prompt_path,
        ticket_priority_prompt_path,
    ):
        assert path.exists()

    packet_json = json.loads(packet_path.read_text(encoding="utf-8"))
    commands = json.loads(commands_path.read_text(encoding="utf-8"))
    commands_md = commands_md_path.read_text(encoding="utf-8")
    request_paths = json.loads(request_paths_path.read_text(encoding="utf-8"))
    output_paths = json.loads(output_paths_path.read_text(encoding="utf-8"))
    trial_records = json.loads(trial_records_path.read_text(encoding="utf-8"))
    runtime_config = json.loads(runtime_config_path.read_text(encoding="utf-8"))
    prompt_text = prompt_path.read_text(encoding="utf-8")
    ticket_priority_prompt_text = ticket_priority_prompt_path.read_text(encoding="utf-8")

    assert packet_json["schema_version"] == PACKET_SCHEMA_VERSION
    assert packet_json["packet_id"] == "phase_13e4_stateful_readonly_planner_variance"
    assert packet_json["model_aliases"] == ["third_model"]
    assert packet_json["trials_per_scenario"] == 3
    assert packet_json["request_count"] == 15
    assert packet_json["requests_total"] == 15
    assert summary["requests_total"] == 15
    assert summary["fixture_only"] is True
    assert request_paths["third_model"]["stateful_ticket_priority_digest"]["trial_03"].endswith(
        "third_model/stateful_ticket_priority_digest/trial_03/request.json"
    )
    assert output_paths["third_model"]["stateful_approval_policy_crosscheck"]["trial_02"].endswith(
        "third_model/stateful_approval_policy_crosscheck/trial_02/raw_planner_output.txt"
    )
    assert len(trial_records) == 15
    assert runtime_config["schema_version"] == RUNTIME_CONFIG_SCHEMA_VERSION
    assert runtime_config["packet_id"] == "phase_13e4_stateful_readonly_planner_variance"
    assert len(runtime_config["trial_records"]) == 15
    assert len(runtime_config["captured_outputs"]) == 15
    assert runtime_config["models"][0]["alias"] == "third_model"
    assert runtime_config["models"][0]["model_path"] == "models/gguf/third_model.gguf"
    assert runtime_config["models"][0]["prompt_prefix"] == "/no_think"
    assert "planner_prompt.compact.txt" in commands_md
    assert "Use `planner_prompt.compact.txt` as the prompt source for each trial." in commands_md
    assert "models/gguf/third_model.gguf" in commands_md
    assert "run_autonomous_browser_stateful_readonly_planner_variance_evaluator.py" in commands_md
    assert "materialize_autonomous_browser_stateful_readonly_planner_variance_outputs.py" in commands_md
    assert "Get-Content" in commands_md
    assert "trial_03" in commands_md
    assert any(command["id"] == "build_stateful_readonly_planner_variance_packet" for command in commands["commands"])
    assert any(command["id"] == "run_stateful_readonly_planner_variance_evaluator" for command in commands["commands"])
    assert any(command["id"] == "run_stateful_readonly_planner_variance_materializer" for command in commands["commands"])
    assert any(command["id"] == "run_pytest" for command in commands["commands"])
    assert "Return exactly one JSON object" in prompt_text
    assert "Ticket board" in prompt_text
    assert "Workspace Policy" in prompt_text
    assert "Cite the collected fact ids and evidence item ids." in prompt_text
    assert "final_answer.answer_text" in prompt_text
    assert "https://local.intranet/tickets/hardboard" in ticket_priority_prompt_text
    assert "Priority cross-check board" in ticket_priority_prompt_text
    assert "Requester tier: facilities." in ticket_priority_prompt_text
    assert "The required ticket_8_requester_tier value is exactly office worker." in ticket_priority_prompt_text
    assert 'Do not use general unless the Ticket 8 page visibly shows general.' in ticket_priority_prompt_text
    assert "The required ticket_8_marker value is exactly decoy for the priority cross-check." in ticket_priority_prompt_text
    assert 'Do not use none for ticket_8_marker because Ticket 8 visibly shows a search marker.' in ticket_priority_prompt_text
    assert "Copy the phrase after Search marker: this page is the ... from the visible Ticket 8 page." in ticket_priority_prompt_text
    assert "Ticket 8 is the decoy; still copy its actual visible facts exactly." in ticket_priority_prompt_text
    assert "Cite the collected fact ids and evidence item ids." in ticket_priority_prompt_text


def test_build_cli_accepts_bom_config_and_prints_compact_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "browser_stateful_readonly_planner_variance.example.json"
    config_path.write_text(CONFIG_PATH.read_text(encoding="utf-8"), encoding="utf-8-sig")
    _stage_base_packet_config(tmp_path)

    module = _load_cli_module(PACKET_CLI_PATH)
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = tmp_path
    try:
        exit_code = module.main(["--config", str(config_path)])
    finally:
        module.PROJECT_ROOT = original_project_root

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["schema_version"] == PACKET_SUMMARY_SCHEMA_VERSION
    assert payload["status"] == "succeeded"
    assert payload["no_runtime_execution"] is True
    assert payload["model_execution"] is False
    assert payload["real_browser_execution"] is False


def test_evaluator_and_materializer_accept_packet_dir_and_replay() -> None:
    short_root = Path("C:/tmp")
    short_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="variance_", dir=short_root) as temp_dir:
        repo_root = Path(temp_dir)
        packet_summary, packet_dir = _build_packet(repo_root)
        _write_outputs(packet_summary, repo_root)

        evaluation = run_autonomous_browser_stateful_readonly_planner_variance_evaluator(packet_dir=packet_dir, repo_root=repo_root)
        materialized = run_autonomous_browser_stateful_readonly_planner_variance_materializer(
            packet_dir=packet_dir,
            output_dir=repo_root / "artifacts" / "autonomous_runtime_summaries" / "stateful_readonly_planner_variance_materialized",
            repo_root=repo_root,
        )

        assert evaluation["schema_version"] == EVALUATOR_SUMMARY_SCHEMA_VERSION
        assert evaluation["status"] == "succeeded"
        assert evaluation["error_code"] is None
        assert evaluation["outputs_total"] == 15
        assert evaluation["outputs_present"] == 15
        assert evaluation["outputs_missing"] == 0
        assert evaluation["outputs_ingested"] == 15
        assert evaluation["outputs_rejected"] == 0
        assert evaluation["validation_accepted"] == 15
        assert evaluation["validation_rejected"] == 0
        assert evaluation["workflows_succeeded"] == 15
        assert evaluation["workflows_failed"] == 0
        assert evaluation["pass_rate_overall"] == 1.0
        assert evaluation["validation_acceptance_rate"] == 1.0
        assert evaluation["failure_class_counts"] == {"none": 15}
        assert evaluation["finish_reason_counts"] == {"stop": 15}
        assert evaluation["no_runtime_execution"] is True
        assert evaluation["model_execution"] is False
        assert evaluation["real_browser_execution"] is False
        assert evaluation["playwright_execution"] is False
        assert evaluation["browser_opened"] is False
        assert evaluation["real_network_traffic"] is False
        assert evaluation["fixture_only"] is True
        assert len(evaluation["scenario_summaries"]) == 5
        assert all(item["pass_rate"] == 1.0 for item in evaluation["scenario_summaries"])
        assert all(item["validation_acceptance_rate"] == 1.0 for item in evaluation["scenario_summaries"])
        assert all(item["workflows_succeeded"] == 3 for item in evaluation["scenario_summaries"])
        assert all(item["workflows_failed"] == 0 for item in evaluation["scenario_summaries"])
        assert len(evaluation["trial_summaries"]) == 15
        assert len(evaluation["output_summaries"]) == 15

        assert materialized["schema_version"] == MATERIALIZER_SUMMARY_SCHEMA_VERSION
        assert materialized["status"] == "succeeded"
        assert materialized["error_code"] is None
        assert materialized["outputs_total"] == 15
        assert materialized["outputs_present"] == 15
        assert materialized["outputs_missing"] == 0
        assert materialized["outputs_accepted"] == 15
        assert materialized["outputs_rejected"] == 0
        assert materialized["workflows_materialized"] == 15
        assert materialized["workflows_failed"] == 0
        assert materialized["actions_total"] > 0
        assert materialized["facts_total"] > 0
        assert materialized["evidence_items_total"] > 0
        assert materialized["final_answers_total"] == 15
        assert materialized["no_runtime_execution"] is True
        assert materialized["model_execution"] is False
        assert materialized["real_browser_execution"] is False
        assert materialized["playwright_execution"] is False
        assert materialized["browser_opened"] is False
        assert materialized["real_network_traffic"] is False
        assert materialized["fixture_only"] is True
        assert len(materialized["scenario_summaries"]) == 5
        assert all(item["pass_rate"] == 1.0 for item in materialized["scenario_summaries"])
        assert len(materialized["trial_summaries"]) == 15
        assert len(materialized["output_summaries"]) == 15

        first_output = materialized["output_summaries"][0]
        assert not Path(first_output["state_path"]).is_absolute()
        assert not Path(first_output["trace_path"]).is_absolute()
        assert not Path(first_output["workflow_summary_path"]).is_absolute()
        assert first_output["state_path"].endswith("materialized_state.json")
        assert first_output["trace_path"].endswith("materialized_trace.json")
        assert first_output["workflow_summary_path"].endswith("materialized_workflow_summary.json")


def test_evaluator_and_materializer_accept_config_and_replay(tmp_path: Path) -> None:
    short_root = Path("C:/tmp")
    short_root.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory(prefix="variance_cfg_", dir=short_root) as temp_dir:
        repo_root = Path(temp_dir)
        _stage_base_packet_config(repo_root)
        _stage_variance_config(repo_root, bom=True)
        packet_summary, packet_dir = _build_packet(repo_root)
        _write_outputs(packet_summary, repo_root)

        config_path = repo_root / VARIANCE_CONFIG_RELATIVE
        evaluation = run_autonomous_browser_stateful_readonly_planner_variance_evaluator(config_path, repo_root=repo_root)
        materialized = run_autonomous_browser_stateful_readonly_planner_variance_materializer(config_path, repo_root=repo_root)

        assert evaluation["status"] == "succeeded"
        assert evaluation["outputs_total"] == 15
        assert evaluation["validation_accepted"] == 15
        assert evaluation["workflows_succeeded"] == 15
        assert evaluation["workflows_failed"] == 0
        assert evaluation["pass_rate_overall"] == 1.0
        assert materialized["status"] == "succeeded"
        assert materialized["outputs_accepted"] == 15
        assert materialized["outputs_rejected"] == 0
        assert materialized["workflows_materialized"] == 15
        assert materialized["workflows_failed"] == 0


def test_evaluator_aggregates_validation_and_workflow_failures(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    records = _fake_variance_request_records(VARIANCE_SCENARIO_IDS)
    packet_context = _fake_variance_packet_context(records)
    _patch_fake_packet_context(monkeypatch, packet_context)
    fake_results = {str(record["trial_id"]): _fake_variance_failure_result(record) for record in records}
    monkeypatch.setattr(
        variance_module,
        "_evaluate_trial_record",
        lambda **kwargs: fake_results[str(kwargs["record"]["trial_id"])],
    )

    evaluation = run_autonomous_browser_stateful_readonly_planner_variance_evaluator(packet_dir=Path("packet-dir"), repo_root=tmp_path)

    assert evaluation["status"] == "completed_with_failures"
    assert evaluation["error_code"] in {"fact_value_mismatch", "browser_click_target_not_found", "final_answer_citation_missing"}
    assert evaluation["outputs_total"] == 15
    assert evaluation["outputs_present"] == 15
    assert evaluation["outputs_missing"] == 0
    assert evaluation["outputs_ingested"] == 15
    assert evaluation["outputs_rejected"] == 0
    assert evaluation["validation_accepted"] == 15
    assert evaluation["validation_rejected"] == 0
    assert evaluation["workflows_succeeded"] == 0
    assert evaluation["workflows_failed"] == 15
    assert evaluation["pass_rate_overall"] == 0.0
    assert evaluation["validation_acceptance_rate"] == 1.0
    assert evaluation["failure_class_counts"] == {"model_failed_task": 15}
    assert len(evaluation["scenario_summaries"]) == 5
    assert all(item["pass_rate"] == 0.0 for item in evaluation["scenario_summaries"])
    assert all(item["validation_acceptance_rate"] == 1.0 for item in evaluation["scenario_summaries"])
    assert all(item["workflows_succeeded"] == 0 for item in evaluation["scenario_summaries"])
    assert all(item["workflows_failed"] == 3 for item in evaluation["scenario_summaries"])


def test_evaluator_aggregates_mixed_validation_and_workflow_outcomes(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    records = _fake_variance_request_records(["stateful_policy_ticket_crosscheck"], trial_labels=("trial_01", "trial_02", "trial_03"))
    packet_context = _fake_variance_packet_context(records, scenario_ids=["stateful_policy_ticket_crosscheck"])
    _patch_fake_packet_context(monkeypatch, packet_context)
    mixed_results = {
        "stateful_policy_ticket_crosscheck__trial_01": _fake_variance_rejected_result(records[0]),
        "stateful_policy_ticket_crosscheck__trial_02": _fake_variance_trial_result(
            records[1],
            status="failed",
            validation_status="accepted",
            workflow_status="failed",
            error_code="fact_value_mismatch",
            failure_class="model_failed_task",
            actions_total=4,
            facts_total=6,
            evidence_items_total=2,
            final_answer_present=True,
        ),
        "stateful_policy_ticket_crosscheck__trial_03": _fake_variance_success_result(records[2]),
    }
    monkeypatch.setattr(
        variance_module,
        "_evaluate_trial_record",
        lambda **kwargs: mixed_results[str(kwargs["record"]["trial_id"])],
    )

    evaluation = run_autonomous_browser_stateful_readonly_planner_variance_evaluator(packet_dir=Path("packet-dir"), repo_root=tmp_path)

    assert evaluation["status"] == "completed_with_failures"
    assert evaluation["outputs_total"] == 3
    assert evaluation["outputs_present"] == 3
    assert evaluation["outputs_missing"] == 0
    assert evaluation["outputs_ingested"] == 2
    assert evaluation["outputs_rejected"] == 1
    assert evaluation["validation_accepted"] == 2
    assert evaluation["validation_rejected"] == 1
    assert evaluation["workflows_succeeded"] == 1
    assert evaluation["workflows_failed"] == 2
    assert evaluation["pass_rate_overall"] == pytest.approx(1 / 3, abs=0.001)
    assert evaluation["validation_acceptance_rate"] == pytest.approx(2 / 3, abs=0.001)
    assert evaluation["failure_class_counts"] == {"model_failed_task": 1, "none": 1, "validation_error": 1}
    assert evaluation["scenario_summaries"][0]["pass_rate"] == pytest.approx(1 / 3, abs=0.001)
    assert evaluation["scenario_summaries"][0]["validation_acceptance_rate"] == pytest.approx(2 / 3, abs=0.001)
    assert evaluation["scenario_summaries"][0]["workflows_succeeded"] == 1
    assert evaluation["scenario_summaries"][0]["workflows_failed"] == 2


def test_materializer_counts_only_successful_materializations_for_accepted_outputs(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    records = _fake_variance_request_records(["stateful_policy_ticket_crosscheck"], trial_labels=("trial_01", "trial_02", "trial_03"))
    packet_context = _fake_variance_packet_context(records, scenario_ids=["stateful_policy_ticket_crosscheck"])
    _patch_fake_packet_context(monkeypatch, packet_context)
    mixed_results = {
        "stateful_policy_ticket_crosscheck__trial_01": _fake_variance_trial_result(
            records[0],
            status="failed",
            validation_status="accepted",
            workflow_status="failed",
            error_code="fact_value_mismatch",
            failure_class="model_failed_task",
            actions_total=4,
            facts_total=6,
            evidence_items_total=2,
            final_answer_present=True,
        ),
        "stateful_policy_ticket_crosscheck__trial_02": _fake_variance_trial_result(
            records[1],
            status="failed",
            validation_status="accepted",
            workflow_status="failed",
            error_code="browser_click_target_not_found",
            failure_class="model_failed_task",
            actions_total=4,
            facts_total=6,
            evidence_items_total=2,
            final_answer_present=True,
        ),
        "stateful_policy_ticket_crosscheck__trial_03": _fake_variance_success_result(records[2]),
    }
    monkeypatch.setattr(
        variance_module,
        "_materialize_trial_record",
        lambda **kwargs: mixed_results[str(kwargs["record"]["trial_id"])],
    )

    materialized = run_autonomous_browser_stateful_readonly_planner_variance_materializer(
        packet_dir=Path("packet-dir"),
        output_dir=tmp_path / MATERIALIZED_OUTPUT_DIR,
        repo_root=tmp_path,
    )

    assert materialized["status"] == "completed_with_failures"
    assert materialized["outputs_total"] == 3
    assert materialized["outputs_present"] == 3
    assert materialized["outputs_missing"] == 0
    assert materialized["outputs_accepted"] == 3
    assert materialized["outputs_rejected"] == 0
    assert materialized["workflows_materialized"] == 1
    assert materialized["workflows_failed"] == 2
    assert materialized["actions_total"] == 4
    assert materialized["facts_total"] == 6
    assert materialized["evidence_items_total"] == 2
    assert materialized["final_answers_total"] == 1
    assert materialized["scenario_summaries"][0]["pass_rate"] == pytest.approx(1 / 3, abs=0.001)
    assert materialized["failure_class_counts"] == {"model_failed_task": 2, "none": 1}


def test_fake_variance_all_success_still_succeeds(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    records = _fake_variance_request_records(["stateful_policy_ticket_crosscheck"], trial_labels=("trial_01", "trial_02", "trial_03"))
    packet_context = _fake_variance_packet_context(records, scenario_ids=["stateful_policy_ticket_crosscheck"])
    _patch_fake_packet_context(monkeypatch, packet_context)
    success_results = {str(record["trial_id"]): _fake_variance_success_result(record) for record in records}
    monkeypatch.setattr(
        variance_module,
        "_evaluate_trial_record",
        lambda **kwargs: success_results[str(kwargs["record"]["trial_id"])],
    )
    monkeypatch.setattr(
        variance_module,
        "_materialize_trial_record",
        lambda **kwargs: success_results[str(kwargs["record"]["trial_id"])],
    )

    evaluation = run_autonomous_browser_stateful_readonly_planner_variance_evaluator(packet_dir=Path("packet-dir"), repo_root=tmp_path)
    materialized = run_autonomous_browser_stateful_readonly_planner_variance_materializer(
        packet_dir=Path("packet-dir"),
        output_dir=tmp_path / MATERIALIZED_OUTPUT_DIR,
        repo_root=tmp_path,
    )

    assert evaluation["status"] == "succeeded"
    assert evaluation["workflows_succeeded"] == 3
    assert evaluation["workflows_failed"] == 0
    assert evaluation["validation_accepted"] == 3
    assert materialized["status"] == "succeeded"
    assert materialized["workflows_materialized"] == 3
    assert materialized["workflows_failed"] == 0
    assert materialized["outputs_accepted"] == 3


def test_evaluator_config_loads_generated_packet_and_reports_missing_packet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _stage_base_packet_config(tmp_path)
    _stage_variance_config(tmp_path, bom=True)
    module = _load_cli_module(EVALUATOR_CLI_PATH)
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = tmp_path
    try:
        exit_code = module.main(["--config", "configs/autonomous_runtime/browser_stateful_readonly_planner_variance.example.json"])
    finally:
        module.PROJECT_ROOT = original_project_root

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "failed"
    assert payload["error_code"] == "config_validation_failed"
    assert payload["diagnostics"]["finding_type"] == "missing_packet_summary"
    assert payload["diagnostics"]["packet_dir"] == PACKET_OUTPUT_DIR
    assert payload["diagnostics"]["expected_summary_files"]
    assert "build variance packet first" in payload["diagnostics"]["hint"]


def test_materializer_config_loads_generated_packet_and_reports_missing_packet(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _stage_base_packet_config(tmp_path)
    _stage_variance_config(tmp_path)
    module = _load_cli_module(MATERIALIZER_CLI_PATH)
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = tmp_path
    try:
        exit_code = module.main(["--config", "configs/autonomous_runtime/browser_stateful_readonly_planner_variance.example.json"])
    finally:
        module.PROJECT_ROOT = original_project_root

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "failed"
    assert payload["error_code"] == "config_validation_failed"
    assert payload["diagnostics"]["finding_type"] == "missing_packet_summary"
    assert payload["diagnostics"]["packet_dir"] == PACKET_OUTPUT_DIR
    assert payload["diagnostics"]["expected_summary_files"]


def test_cli_help_mentions_packet_dir(capsys: pytest.CaptureFixture[str]) -> None:
    evaluator_module = _load_cli_module(EVALUATOR_CLI_PATH)
    materializer_module = _load_cli_module(MATERIALIZER_CLI_PATH)

    with pytest.raises(SystemExit):
        evaluator_module.main(["--help"])
    evaluator_help = capsys.readouterr().out
    assert "--packet-dir" in evaluator_help

    with pytest.raises(SystemExit):
        materializer_module.main(["--help"])
    materializer_help = capsys.readouterr().out
    assert "--packet-dir" in materializer_help
    assert "--output-dir" in materializer_help


def test_packet_dir_smoke_returns_missing_output_summary(tmp_path: Path) -> None:
    _stage_base_packet_config(tmp_path)
    packet_summary, packet_dir = _build_packet(tmp_path)

    evaluation = run_autonomous_browser_stateful_readonly_planner_variance_evaluator(packet_dir=packet_dir, repo_root=tmp_path)
    materialized = run_autonomous_browser_stateful_readonly_planner_variance_materializer(
        packet_dir=packet_dir,
        output_dir=tmp_path / MATERIALIZED_OUTPUT_DIR,
        repo_root=tmp_path,
    )

    assert evaluation["status"] == "completed_with_missing_outputs"
    assert evaluation["error_code"] == "missing_captured_outputs"
    assert materialized["status"] == "completed_with_missing_outputs"
    assert materialized["error_code"] == "missing_captured_outputs"
    encoded = json.dumps({"evaluation": evaluation, "materialized": materialized}, ensure_ascii=False)
    assert "C:\\" not in encoded
    assert str(tmp_path) not in encoded


def test_cli_invalid_config_returns_structured_failure(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    config_path = tmp_path / "invalid_variance.json"
    _write_json(config_path, {"schema_version": "wrong"})

    module = _load_cli_module(PACKET_CLI_PATH)
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = tmp_path
    try:
        exit_code = module.main(["--config", str(config_path)])
    finally:
        module.PROJECT_ROOT = original_project_root

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 2
    assert payload["schema_version"] == "autonomous_browser_stateful_readonly_planner_variance_packet_summary_v1"
    assert payload["status"] == "failed"
    assert payload["error_code"] == "config_validation_failed"


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    _stage_base_packet_config(tmp_path)
    summary = build_autonomous_browser_stateful_readonly_planner_variance_packet(_config(), repo_root=tmp_path)

    assert summary["status"] == "succeeded"
