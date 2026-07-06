from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent import model_evaluation_artifact_contracts as contracts
from src.agent import model_evaluation_artifact_registry as registry
from src.agent.model_evaluation_artifact_validator import (
    validate_model_evaluation_artifacts,
    validate_model_evaluation_workflow_output_dir,
)
from src.agent.model_evaluation_cli import main as model_evaluation_cli_main
from src.agent.model_evaluation_workflow_runner import (
    ModelEvaluationWorkflowRunConfig,
    run_offline_model_evaluation_workflow,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _plan_payload() -> dict[str, Any]:
    return {
        "schema_version": "model_comparison_plan_v1",
        "plan_id": "contract_plan",
        "candidate_pairs": [{"pair_id": "second_model__to__first_model"}],
        "scenarios": [{"scenario_id": "office_document_file_workflow_basic_v1"}],
        "trials": [
            {
                "trial_id": "trial_1",
                "pair_id": "second_model__to__first_model",
                "scenario_id": "office_document_file_workflow_basic_v1",
            }
        ],
        "no_runtime_execution": True,
    }


def _readiness_payload(**overrides: object) -> dict[str, Any]:
    payload = {
        "schema_version": "model_comparison_readiness_v1",
        "status": "ready",
        "plan_id": "contract_plan",
        "trial_count": 1,
        "candidate_pair_count": 1,
        "issues": [],
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _model_pair_matrix_run_summary_payload(**overrides: object) -> dict[str, Any]:
    payload = {
        "schema_version": "model_pair_matrix_run_summary_v1",
        "run_id": "contract_matrix_run",
        "plan_id": "contract_plan",
        "execution_mode": "dry_run",
        "trial_count": 1,
        "succeeded_count": 0,
        "failed_count": 0,
        "skipped_count": 0,
        "dry_run_count": 1,
        "pair_summaries": [],
        "scenario_summaries": [],
        "trial_results": [
            {
                "trial_id": "trial_1",
                "scenario_id": "office_document_file_workflow_basic_v1",
                "pair_id": "second_model__to__first_model",
                "orchestrator_model_id": "second_model",
                "executor_model_id": "first_model",
                "status": "dry_run",
                "task_success": None,
                "correctness_score": None,
                "warnings": [],
                "notes": ["dry_run_no_runtime_execution"],
                "no_runtime_execution": True,
                "execution_mode": "dry_run",
            }
        ],
        "warnings": [],
        "notes": ["Offline matrix scaffold only; no model execution performed."],
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _matrix_run_adapter_summary_payload(**overrides: object) -> dict[str, Any]:
    payload = {
        "schema_version": "matrix_run_adapter_summary_v1",
        "adapter_id": "contract_adapter",
        "source_run_id": "contract_matrix_run",
        "trial_count": 1,
        "resource_observation_count": 1,
        "normality_input_count": 1,
        "normality_missing_trace_count": 0,
        "output_paths": {
            "resource_observations": "model_resource_observations.jsonl",
            "normality_inputs": "normality_judge_inputs.jsonl",
            "adapter_summary": "matrix_run_adapter_summary.json",
        },
        "warnings": [],
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _prepared_prompt_pack_summary_payload(**overrides: object) -> dict[str, Any]:
    payload = {
        "schema_version": "prepared_normality_judge_prompt_pack_v1",
        "pack_id": "contract_prompt_pack",
        "input_count": 1,
        "prompt_count": 1,
        "skipped_count": 0,
        "prompts": [
            {
                "prompt_id": "contract_prompt_pack__trial_1",
                "trial_id": "trial_1",
                "scenario_id": "office_document_file_workflow_basic_v1",
                "pair_id": "second_model__to__first_model",
                "status": "ok",
                "warning_count": 0,
                "prompt_char_count": 1024,
            }
        ],
        "warnings": [],
        "notes": ["Offline prompt pack only; no model execution performed."],
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _task_correctness_result_payload(**overrides: object) -> dict[str, Any]:
    payload = {
        "schema_version": "task_correctness_evaluation_result_v1",
        "trial_id": "trial_1",
        "scenario_id": "office_document_file_workflow_basic_v1",
        "pair_id": "second_model__to__first_model",
        "status": "passed",
        "task_success": True,
        "correctness_score": 1.0,
        "check_results": [],
        "failure_reasons": [],
        "warnings": [],
        "notes": ["Offline task correctness evaluation only; no runtime execution performed."],
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _task_correctness_batch_summary_payload(**overrides: object) -> dict[str, Any]:
    payload = {
        "schema_version": "task_correctness_batch_summary_v1",
        "summary_id": "contract_correctness_summary",
        "input_count": 1,
        "evaluated_count": 1,
        "invalid_count": 0,
        "passed_count": 1,
        "failed_count": 0,
        "partial_count": 0,
        "skipped_count": 0,
        "mean_correctness_score": 1.0,
        "by_pair": {},
        "by_scenario": {},
        "results": [_task_correctness_result_payload()],
        "warnings": [],
        "notes": ["Offline task correctness batch summary only; no model execution performed."],
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _bundle_payload(**overrides: object) -> dict[str, Any]:
    payload = {
        "schema_version": "model_evaluation_workflow_bundle_v1",
        "status": "partial",
        "bundle_id": "contract_bundle",
        "artifacts": {},
        "summary": {},
        "warnings": [],
        "notes": ["Offline workflow bundle only; no model execution performed."],
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _compatibility_report_payload(**overrides: object) -> dict[str, Any]:
    payload = {
        "schema_version": "model_evaluation_compatibility_report_v1",
        "status": "compatible",
        "compatibility_id": "contract_compatibility",
        "checked_artifact_count": 9,
        "issue_count": 0,
        "warning_count": 0,
        "error_count": 0,
        "issues": [],
        "notes": ["Offline compatibility validation only; no model execution performed."],
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _workflow_config(tmp_path: Path) -> ModelEvaluationWorkflowRunConfig:
    return ModelEvaluationWorkflowRunConfig.model_validate(
        {
            "workflow_id": "contract_complete_workflow",
            "model_catalog_path": str(CATALOG_PATH),
            "scenario_paths": [SCENARIO_PATH],
            "output_dir": str(tmp_path / "workflow"),
            "repetitions_per_pair": 1,
            "include_self_pairs": True,
            "normality_batch_summary_paths": [str(_normality_batch_summary_path(tmp_path))],
            "resource_observation_paths": [str(_resource_observation_path(tmp_path))],
            "tags": ["contract_test"],
        }
    )


def _normality_batch_summary_path(tmp_path: Path) -> Path:
    entries = [
        {
            "scenario_id": "office_document_file_workflow_basic_v1",
            "trial_id": "trial_normality",
            "model_pair": {"orchestrator": "second_model", "executor": "first_model"},
            "tags": ["contract_test"],
            "status": "ok",
            "label": "normal",
            "overall_score": 0.9,
            "findings": [],
            "warnings": [],
        }
    ]
    return _write_json(
        tmp_path / "inputs" / "normality_batch.json",
        {
            "status": "ok",
            "batch_id": "contract_batch",
            "input_count": 1,
            "evaluated_count": 1,
            "failed_count": 0,
            "entries": entries,
        },
    )


def _resource_observation_path(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "inputs" / "resource_observations.json",
        [
            {
                "observation_id": "contract_resource_1",
                "orchestrator_model_id": "second_model",
                "executor_model_id": "first_model",
                "pair_id": "second_model__to__first_model",
                "scenario_id": "office_document_file_workflow_basic_v1",
                "trial_id": "trial_resource",
                "runtime_mode": "offline_fixture",
                "backend": "synthetic_fixture",
                "success": True,
                "wall_time_s": 1.0,
                "peak_ram_gb": 2.0,
                "peak_vram_gb": 0.0,
                "tags": ["contract_test"],
            }
        ],
    )


def _issue_codes(issues: list[contracts.ArtifactContractIssue]) -> set[str]:
    return {issue.code for issue in issues}


def test_contracts_exist_for_required_workflow_artifact_types() -> None:
    for artifact_type in registry.get_required_workflow_output_artifact_types():
        assert contracts.get_artifact_schema_contract(artifact_type).artifact_type == artifact_type


def test_each_contract_schema_version_matches_registry_schema_version() -> None:
    for contract in contracts.list_artifact_schema_contracts():
        assert contract.schema_version == registry.get_artifact_schema_info(contract.artifact_type).schema_version


def test_export_returns_json_serializable_object() -> None:
    payload = contracts.export_artifact_schema_contracts()

    assert payload["status"] == "ok"
    assert payload["contract_version"] == "artifact_contract_v1"
    assert payload["artifact_count"] == len(registry.list_artifact_schema_infos())
    json.dumps(payload, ensure_ascii=False)


def test_valid_synthetic_model_comparison_plan_passes_contract_validation() -> None:
    issues = contracts.validate_artifact_against_contract(
        _plan_payload(),
        registry.MODEL_COMPARISON_PLAN,
    )

    assert issues == []


def test_valid_model_pair_matrix_run_summary_passes_contract_validation() -> None:
    issues = contracts.validate_artifact_against_contract(
        _model_pair_matrix_run_summary_payload(),
        registry.MODEL_PAIR_MATRIX_RUN_SUMMARY,
    )

    assert issues == []


def test_valid_matrix_run_adapter_summary_passes_contract_validation() -> None:
    issues = contracts.validate_artifact_against_contract(
        _matrix_run_adapter_summary_payload(),
        registry.MATRIX_RUN_ADAPTER_SUMMARY,
    )

    assert issues == []


def test_valid_prepared_prompt_pack_summary_passes_contract_validation() -> None:
    issues = contracts.validate_artifact_against_contract(
        _prepared_prompt_pack_summary_payload(),
        registry.PREPARED_NORMALITY_JUDGE_PROMPT_PACK_SUMMARY,
    )

    assert issues == []


def test_valid_task_correctness_result_passes_contract_validation() -> None:
    issues = contracts.validate_artifact_against_contract(
        _task_correctness_result_payload(),
        registry.TASK_CORRECTNESS_EVALUATION_RESULT,
    )

    assert issues == []


def test_valid_task_correctness_batch_summary_passes_contract_validation() -> None:
    issues = contracts.validate_artifact_against_contract(
        _task_correctness_batch_summary_payload(),
        registry.TASK_CORRECTNESS_BATCH_SUMMARY,
    )

    assert issues == []


def test_missing_required_plan_field_fails_with_error() -> None:
    payload = _plan_payload()
    payload.pop("plan_id")

    issues = contracts.validate_artifact_against_contract(payload, registry.MODEL_COMPARISON_PLAN)

    assert "contract_required_field_missing" in _issue_codes(issues)
    assert any(issue.field == "plan_id" and issue.severity == "error" for issue in issues)


def test_wrong_schema_version_fails_with_error() -> None:
    payload = _plan_payload()
    payload["schema_version"] = "wrong_schema"

    issues = contracts.validate_artifact_against_contract(payload, registry.MODEL_COMPARISON_PLAN)

    assert "contract_schema_version_mismatch" in _issue_codes(issues)


def test_invalid_readiness_status_fails_with_error() -> None:
    issues = contracts.validate_artifact_against_contract(
        _readiness_payload(status="done"),
        registry.READINESS_REPORT,
    )

    assert "contract_field_value_not_allowed" in _issue_codes(issues)
    assert "contract_status_not_allowed" in _issue_codes(issues)


def test_valid_workflow_bundle_passes_contract_validation() -> None:
    issues = contracts.validate_artifact_against_contract(
        _bundle_payload(),
        registry.WORKFLOW_BUNDLE,
    )

    assert issues == []


def test_invalid_workflow_bundle_status_fails() -> None:
    issues = contracts.validate_artifact_against_contract(
        _bundle_payload(status="finished"),
        registry.WORKFLOW_BUNDLE,
    )

    assert "contract_field_value_not_allowed" in _issue_codes(issues)
    assert "contract_status_not_allowed" in _issue_codes(issues)


def test_valid_compatibility_report_passes_contract_validation() -> None:
    issues = contracts.validate_artifact_against_contract(
        _compatibility_report_payload(),
        registry.MODEL_EVALUATION_COMPATIBILITY_REPORT,
    )

    assert issues == []


def test_invalid_compatibility_report_status_fails() -> None:
    issues = contracts.validate_artifact_against_contract(
        _compatibility_report_payload(status="finished"),
        registry.MODEL_EVALUATION_COMPATIBILITY_REPORT,
    )

    assert "contract_field_value_not_allowed" in _issue_codes(issues)
    assert "contract_status_not_allowed" in _issue_codes(issues)


def test_artifact_validator_reports_contract_issue_for_missing_required_field(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "plan.json", {key: value for key, value in _plan_payload().items() if key != "plan_id"})

    report = validate_model_evaluation_artifacts(plan_path=path, base_dir=tmp_path)

    assert report.status == "invalid"
    assert "contract_required_field_missing" in {issue.code for issue in report.issues}


def test_artifact_validator_still_validates_complete_runner_output(tmp_path: Path) -> None:
    result = run_offline_model_evaluation_workflow(_workflow_config(tmp_path))

    report = validate_model_evaluation_workflow_output_dir(tmp_path / "workflow")

    assert result.status == "ok"
    assert report.status == "valid"
    assert report.error_count == 0


def test_unified_cli_schema_returns_compact_json(capsys: pytest.CaptureFixture[str]) -> None:
    code = model_evaluation_cli_main(["schema"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "ok"
    assert payload["contract_version"] == "artifact_contract_v1"
    assert payload["artifact_count"] == len(registry.list_artifact_schema_infos())
    assert "required_fields" not in payload["artifacts"][0]


def test_unified_cli_schema_full_single_artifact(capsys: pytest.CaptureFixture[str]) -> None:
    code = model_evaluation_cli_main(
        ["schema", "--artifact-type", registry.MODEL_COMPARISON_PLAN, "--full"]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["artifact_count"] == 1
    assert payload["artifacts"][0]["artifact_type"] == registry.MODEL_COMPARISON_PLAN
    assert payload["artifacts"][0]["required_fields"]


def test_unified_cli_version_includes_schema_subcommand(capsys: pytest.CaptureFixture[str]) -> None:
    code = model_evaluation_cli_main(["version"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert "schema" in payload["supported_subcommands"]
    assert payload["artifact_contract_version"] == "artifact_contract_v1"


def test_contracts_import_has_no_file_reads_model_imports_or_gguf_checks(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_exists = Path.exists
    original_read_text = Path.read_text
    original_import = __import__

    def forbid_exists(self: Path) -> bool:
        raise AssertionError("contracts import must not touch filesystem")

    def forbid_read_text(self: Path, *args: object, **kwargs: object) -> str:
        raise AssertionError("contracts import must not read files")

    def forbid_runtime_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("contracts must not import runtime backends")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_exists)
    monkeypatch.setattr(Path, "read_text", forbid_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    reloaded = importlib.reload(contracts)

    assert reloaded.get_artifact_schema_contract(registry.MODEL_COMPARISON_PLAN).schema_version
    monkeypatch.setattr(Path, "exists", original_exists)
    monkeypatch.setattr(Path, "read_text", original_read_text)
