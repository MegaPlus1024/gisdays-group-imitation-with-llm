from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_comparison_plan import MODEL_COMPARISON_PLAN_FILENAME
from src.agent.model_comparison_readiness import MODEL_COMPARISON_READINESS_REPORT_FILENAME
from src.agent.model_evaluation_scorecard import MODEL_EVALUATION_SCORECARD_FILENAME
from src.agent.model_evaluation_workflow_bundle import MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME
from src.agent.model_evaluation_workflow_runner import (
    MODEL_EVALUATION_WORKFLOW_RUN_SCHEMA_VERSION,
    WORKFLOW_RUN_MANIFEST_FILENAME,
    ModelEvaluationWorkflowRunConfig,
    run_offline_model_evaluation_workflow,
)
from src.agent.model_evaluation_workflow_runner_cli import main as workflow_runner_cli_main
from src.agent.model_pair_matrix_runner import MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME
from src.agent.model_resource_evaluation import MODEL_RESOURCE_SUMMARY_FILENAME
from src.agent.model_task_correctness_evaluation import TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME
from src.agent.normality_comparison import NORMALITY_COMPARISON_SUMMARY_FILENAME


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
RAW_MARKER = "RAW_FULL_WORKFLOW_RUNNER_TEST_MARKER"


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _config(tmp_path: Path, **overrides: object) -> ModelEvaluationWorkflowRunConfig:
    payload = {
        "workflow_id": "runner_test_workflow",
        "model_catalog_path": str(CATALOG_PATH),
        "scenario_paths": [SCENARIO_PATH],
        "output_dir": str(tmp_path / "workflow"),
        "repetitions_per_pair": 1,
        "include_self_pairs": True,
        "tags": ["runner_test"],
        **overrides,
    }
    return ModelEvaluationWorkflowRunConfig.model_validate(payload)


def _normality_batch_summary_path(tmp_path: Path) -> Path:
    entries = []
    for pair_id, executor, score in [
        ("second_model__to__first_model", "first_model", 0.88),
        ("second_model__to__second_model", "second_model", 0.91),
    ]:
        entries.append(
            {
                "scenario_id": "office_document_file_workflow_basic_v1",
                "trial_id": f"office_document_file_workflow_basic_v1__{pair_id}__normality",
                "model_pair": {
                    "orchestrator": "second_model",
                    "executor": executor,
                },
                "tags": ["runner_test", "normality"],
                "status": "ok",
                "label": "normal",
                "overall_score": score,
                "findings": [f"synthetic_normality_{executor}"],
                "warnings": [],
                "event_preview": [{"raw": RAW_MARKER}],
            }
        )
    return _write_json(
        tmp_path / "inputs" / "normality_batch.json",
        {
            "status": "ok",
            "batch_id": "runner_test_batch",
            "input_count": len(entries),
            "evaluated_count": len(entries),
            "failed_count": 0,
            "entries": entries,
        },
    )


def _resource_observation_path(tmp_path: Path) -> Path:
    observations = []
    for index, (pair_id, executor) in enumerate(
        [
            ("second_model__to__first_model", "first_model"),
            ("second_model__to__second_model", "second_model"),
        ],
        start=1,
    ):
        observations.append(
            {
                "observation_id": f"runner_resource_{index:02d}",
                "orchestrator_model_id": "second_model",
                "executor_model_id": executor,
                "pair_id": pair_id,
                "scenario_id": "office_document_file_workflow_basic_v1",
                "trial_id": f"office_document_file_workflow_basic_v1__{pair_id}__resource",
                "runtime_mode": "offline_fixture",
                "backend": "synthetic_fixture",
                "success": True,
                "wall_time_s": 1.0 + index / 10,
                "peak_ram_gb": 2.0 + index,
                "peak_vram_gb": 0.0,
                "notes": [RAW_MARKER],
                "tags": ["runner_test", "resource"],
            }
        )
    return _write_json(tmp_path / "inputs" / "resource_observations.json", observations)


def _task_correctness_summary_path(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "inputs" / TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME,
        {
            "schema_version": "task_correctness_batch_summary_v1",
            "summary_id": "runner_test_correctness",
            "input_count": 1,
            "evaluated_count": 1,
            "invalid_count": 0,
            "passed_count": 1,
            "failed_count": 0,
            "partial_count": 0,
            "skipped_count": 0,
            "mean_correctness_score": 1.0,
            "by_pair": {
                "second_model__to__first_model": {
                    "pair_id": "second_model__to__first_model",
                    "input_count": 1,
                    "evaluated_count": 1,
                    "invalid_count": 0,
                    "passed_count": 1,
                    "failed_count": 0,
                    "partial_count": 0,
                    "skipped_count": 0,
                    "mean_correctness_score": 1.0,
                    "failure_reasons": [],
                    "warnings": [],
                }
            },
            "by_scenario": {
                "office_document_file_workflow_basic_v1": {
                    "scenario_id": "office_document_file_workflow_basic_v1",
                    "input_count": 1,
                    "evaluated_count": 1,
                    "invalid_count": 0,
                    "passed_count": 1,
                    "failed_count": 0,
                    "partial_count": 0,
                    "skipped_count": 0,
                    "mean_correctness_score": 1.0,
                    "failure_reasons": [],
                    "warnings": [],
                }
            },
            "results": [
                {
                    "schema_version": "task_correctness_evaluation_result_v1",
                    "trial_id": "runner_correctness_trial",
                    "scenario_id": "office_document_file_workflow_basic_v1",
                    "pair_id": "second_model__to__first_model",
                    "status": "passed",
                    "task_success": True,
                    "correctness_score": 1.0,
                    "check_results": [],
                    "failure_reasons": [],
                    "warnings": [],
                    "notes": ["synthetic_runner_correctness"],
                    "no_runtime_execution": True,
                }
            ],
            "warnings": [],
            "notes": ["Synthetic runner correctness summary."],
            "no_runtime_execution": True,
        },
    )


def _matrix_run_summary_path(
    tmp_path: Path,
    *,
    task_success: bool = True,
    correctness_score: float | None = 0.94,
) -> Path:
    pair_id = "second_model__to__first_model"
    scenario_id = "office_document_file_workflow_basic_v1"
    trial_result: dict[str, Any] = {
        "trial_id": f"{scenario_id}__{pair_id}__r01",
        "scenario_id": scenario_id,
        "pair_id": pair_id,
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
        "status": "succeeded",
        "task_success": task_success,
        "warnings": [],
        "notes": ["synthetic_matrix_trial"],
        "no_runtime_execution": True,
        "execution_mode": "static_fixture",
    }
    if correctness_score is not None:
        trial_result["correctness_score"] = correctness_score
    return _write_json(
        tmp_path / "inputs" / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME,
        {
            "schema_version": "model_pair_matrix_run_summary_v1",
            "run_id": "runner_test_matrix",
            "plan_id": "runner_test_matrix_plan",
            "execution_mode": "static_fixture",
            "trial_count": 1,
            "succeeded_count": 1,
            "failed_count": 0,
            "skipped_count": 0,
            "dry_run_count": 0,
            "pair_summaries": [],
            "scenario_summaries": [],
            "trial_results": [trial_result],
            "warnings": [],
            "notes": ["Synthetic matrix run summary."],
            "no_runtime_execution": True,
        },
    )


def _assert_workflow_core_files(output_dir: Path) -> None:
    assert (output_dir / "plan" / MODEL_COMPARISON_PLAN_FILENAME).is_file()
    assert (output_dir / "readiness" / MODEL_COMPARISON_READINESS_REPORT_FILENAME).is_file()
    assert (output_dir / "scorecard" / MODEL_EVALUATION_SCORECARD_FILENAME).is_file()
    assert (output_dir / "bundle" / MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME).is_file()
    assert (output_dir / WORKFLOW_RUN_MANIFEST_FILENAME).is_file()


def _assert_no_tmp_path_leak(payload_text: str, tmp_path: Path) -> None:
    variants = {
        str(tmp_path),
        str(tmp_path).replace("\\", "/"),
        str(tmp_path).replace("\\", "\\\\"),
        tmp_path.as_posix(),
    }
    assert all(variant not in payload_text for variant in variants)


def test_runner_creates_required_artifacts_with_catalog_and_scenario_only(tmp_path: Path) -> None:
    result = run_offline_model_evaluation_workflow(_config(tmp_path))
    output_dir = tmp_path / "workflow"

    assert result.schema_version == MODEL_EVALUATION_WORKFLOW_RUN_SCHEMA_VERSION
    assert result.status == "partial"
    assert result.workflow_id == "runner_test_workflow"
    assert result.candidate_pair_count == 2
    assert result.trial_count == 2
    assert result.readiness_status == "ready"
    _assert_workflow_core_files(output_dir)


def test_status_is_partial_when_normality_and_resource_inputs_absent(tmp_path: Path) -> None:
    result = run_offline_model_evaluation_workflow(_config(tmp_path))

    assert result.status == "partial"
    assert "normality_inputs_not_provided" in result.warnings
    assert "resource_inputs_not_provided" in result.warnings
    assert result.artifact_paths["normality_comparison_summary"] is None
    assert result.artifact_paths["model_resource_summary"] is None


def test_runner_creates_normality_comparison_when_batch_summary_provided(tmp_path: Path) -> None:
    normality_input = _normality_batch_summary_path(tmp_path)

    result = run_offline_model_evaluation_workflow(
        _config(tmp_path, normality_batch_summary_paths=[str(normality_input)])
    )
    normality = _load_json(tmp_path / "workflow" / "normality" / NORMALITY_COMPARISON_SUMMARY_FILENAME)

    assert result.status == "partial"
    assert "resource_inputs_not_provided" in result.warnings
    assert result.artifact_paths["normality_comparison_summary"] == "normality/normality_comparison_summary.json"
    assert normality["status"] == "ok"
    assert normality["evaluated_entries"] == 2


def test_runner_creates_resource_summary_when_resource_observations_provided(tmp_path: Path) -> None:
    resource_input = _resource_observation_path(tmp_path)

    result = run_offline_model_evaluation_workflow(
        _config(tmp_path, resource_observation_paths=[str(resource_input)])
    )
    resource = _load_json(tmp_path / "workflow" / "resource" / MODEL_RESOURCE_SUMMARY_FILENAME)

    assert result.status == "partial"
    assert "normality_inputs_not_provided" in result.warnings
    assert result.artifact_paths["model_resource_summary"] == "resource/model_resource_summary.json"
    assert resource["status"] == "ok"
    assert resource["observation_count"] == 2


def test_runner_creates_full_ok_workflow_when_normality_and_resource_inputs_provided(tmp_path: Path) -> None:
    normality_input = _normality_batch_summary_path(tmp_path)
    resource_input = _resource_observation_path(tmp_path)

    result = run_offline_model_evaluation_workflow(
        _config(
            tmp_path,
            normality_batch_summary_paths=[str(normality_input)],
            resource_observation_paths=[str(resource_input)],
        )
    )
    bundle = _load_json(tmp_path / "workflow" / "bundle" / MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME)

    assert result.status == "ok"
    assert "normality_inputs_not_provided" not in result.warnings
    assert "resource_inputs_not_provided" not in result.warnings
    assert bundle["status"] == "complete"
    assert set(bundle["summary"]["optional_artifacts_present"]) == {
        "normality_comparison_summary",
        "model_resource_summary",
        "model_evaluation_scorecard",
    }


def test_artifact_files_are_written_under_expected_subdirectories(tmp_path: Path) -> None:
    normality_input = _normality_batch_summary_path(tmp_path)
    resource_input = _resource_observation_path(tmp_path)

    run_offline_model_evaluation_workflow(
        _config(
            tmp_path,
            normality_batch_summary_paths=[str(normality_input)],
            resource_observation_paths=[str(resource_input)],
        )
    )
    output_dir = tmp_path / "workflow"

    _assert_workflow_core_files(output_dir)
    assert (output_dir / "normality" / NORMALITY_COMPARISON_SUMMARY_FILENAME).is_file()
    assert (output_dir / "resource" / MODEL_RESOURCE_SUMMARY_FILENAME).is_file()


def test_workflow_run_manifest_is_written(tmp_path: Path) -> None:
    result = run_offline_model_evaluation_workflow(_config(tmp_path))
    manifest = _load_json(tmp_path / "workflow" / WORKFLOW_RUN_MANIFEST_FILENAME)

    assert result.manifest_path_relative == WORKFLOW_RUN_MANIFEST_FILENAME
    assert result.artifact_paths["workflow_run_manifest"] == WORKFLOW_RUN_MANIFEST_FILENAME
    assert manifest["schema_version"] == MODEL_EVALUATION_WORKFLOW_RUN_SCHEMA_VERSION
    assert manifest["workflow_id"] == "runner_test_workflow"
    assert manifest["artifact_paths"]["workflow_run_manifest"] == WORKFLOW_RUN_MANIFEST_FILENAME


def test_candidate_pair_and_trial_counts_match_plan(tmp_path: Path) -> None:
    result = run_offline_model_evaluation_workflow(_config(tmp_path))
    plan = _load_json(tmp_path / "workflow" / "plan" / MODEL_COMPARISON_PLAN_FILENAME)

    assert result.candidate_pair_count == len(plan["candidate_pairs"]) == 2
    assert result.trial_count == len(plan["trials"]) == 2
    assert result.model_count == 2


def test_readiness_report_path_and_counts_are_included(tmp_path: Path) -> None:
    result = run_offline_model_evaluation_workflow(_config(tmp_path))
    readiness = _load_json(tmp_path / "workflow" / "readiness" / MODEL_COMPARISON_READINESS_REPORT_FILENAME)

    assert result.artifact_paths["readiness_report"] == "readiness/model_comparison_readiness_report.json"
    assert readiness["status"] == "ready"
    assert result.readiness_error_count == 0
    assert result.readiness_warning_count == 0


def test_scorecard_and_bundle_reference_available_artifacts(tmp_path: Path) -> None:
    normality_input = _normality_batch_summary_path(tmp_path)
    resource_input = _resource_observation_path(tmp_path)

    run_offline_model_evaluation_workflow(
        _config(
            tmp_path,
            normality_batch_summary_paths=[str(normality_input)],
            resource_observation_paths=[str(resource_input)],
        )
    )
    scorecard = _load_json(tmp_path / "workflow" / "scorecard" / MODEL_EVALUATION_SCORECARD_FILENAME)
    bundle = _load_json(tmp_path / "workflow" / "bundle" / MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME)

    assert scorecard["plan_used"] is True
    assert scorecard["normality_summary_used"] is True
    assert scorecard["resource_summary_used"] is True
    assert bundle["artifacts"]["readiness_report"]["status"] == "ok"
    assert bundle["artifacts"]["model_evaluation_scorecard"]["status"] == "ok"


def test_runner_passes_explicit_task_correctness_summary_to_scorecard_and_manifest(tmp_path: Path) -> None:
    correctness_input = _task_correctness_summary_path(tmp_path)

    result = run_offline_model_evaluation_workflow(
        _config(tmp_path, task_correctness_summary_path=str(correctness_input))
    )
    scorecard = _load_json(tmp_path / "workflow" / "scorecard" / MODEL_EVALUATION_SCORECARD_FILENAME)
    bundle = _load_json(tmp_path / "workflow" / "bundle" / MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME)
    manifest = _load_json(tmp_path / "workflow" / WORKFLOW_RUN_MANIFEST_FILENAME)

    assert scorecard["task_correctness_summary_used"] is True
    assert scorecard["task_correctness_metrics"]["evaluated_count"] == 1
    assert bundle["artifacts"]["task_correctness_batch_summary"]["status"] == "ok"
    assert bundle["summary"]["task_correctness_evaluated_count"] == 1
    assert "task_correctness_batch_summary" in bundle["summary"]["optional_artifacts_present"]
    assert result.artifact_paths["task_correctness_batch_summary"] is not None
    assert manifest["artifact_paths"]["task_correctness_batch_summary"] is not None


def test_runner_auto_generates_task_correctness_summary_from_matrix_run(tmp_path: Path) -> None:
    matrix_summary = _matrix_run_summary_path(tmp_path)

    result = run_offline_model_evaluation_workflow(
        _config(
            tmp_path,
            matrix_run_summary_path=str(matrix_summary),
            auto_task_correctness_from_matrix=True,
        )
    )
    output_dir = tmp_path / "workflow"
    correctness_path = output_dir / "correctness" / TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME
    correctness = _load_json(correctness_path)
    scorecard = _load_json(output_dir / "scorecard" / MODEL_EVALUATION_SCORECARD_FILENAME)
    bundle = _load_json(output_dir / "bundle" / MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME)
    manifest = _load_json(output_dir / WORKFLOW_RUN_MANIFEST_FILENAME)

    assert result.status == "partial"
    assert correctness["input_count"] == 1
    assert correctness["evaluated_count"] == 1
    assert correctness["passed_count"] == 1
    assert result.correctness_input_count == 1
    assert result.correctness_evaluated_count == 1
    assert result.artifact_paths["task_correctness_batch_summary"] == (
        "correctness/task_correctness_batch_summary.json"
    )
    assert scorecard["task_correctness_summary_used"] is True
    assert scorecard["task_correctness_metrics"]["evaluated_count"] == 1
    assert scorecard["task_correctness_metrics"]["mean_correctness_score"] == pytest.approx(0.94)
    assert bundle["artifacts"]["task_correctness_batch_summary"]["status"] == "ok"
    assert "task_correctness_batch_summary" in bundle["summary"]["optional_artifacts_present"]
    assert manifest["artifact_paths"]["task_correctness_batch_summary"] == (
        "correctness/task_correctness_batch_summary.json"
    )
    assert manifest["correctness_input_count"] == 1
    assert manifest["correctness_evaluated_count"] == 1


def test_explicit_task_correctness_summary_overrides_auto_generation(tmp_path: Path) -> None:
    explicit_summary = _task_correctness_summary_path(tmp_path)
    matrix_summary = _matrix_run_summary_path(tmp_path, task_success=False, correctness_score=0.0)

    result = run_offline_model_evaluation_workflow(
        _config(
            tmp_path,
            task_correctness_summary_path=str(explicit_summary),
            matrix_run_summary_path=str(matrix_summary),
            auto_task_correctness_from_matrix=True,
        )
    )
    scorecard = _load_json(tmp_path / "workflow" / "scorecard" / MODEL_EVALUATION_SCORECARD_FILENAME)

    assert "explicit_task_correctness_summary_overrides_auto_generation" in result.warnings
    assert not (tmp_path / "workflow" / "correctness" / TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME).exists()
    assert scorecard["task_correctness_summary_used"] is True
    assert scorecard["task_correctness_metrics"]["mean_correctness_score"] == 1.0


def test_matrix_summary_without_auto_flag_warns_without_generating_correctness(tmp_path: Path) -> None:
    matrix_summary = _matrix_run_summary_path(tmp_path)

    result = run_offline_model_evaluation_workflow(
        _config(tmp_path, matrix_run_summary_path=str(matrix_summary))
    )

    assert "matrix_run_summary_provided_without_correctness_auto" in result.warnings
    assert result.artifact_paths["task_correctness_batch_summary"] is None
    assert result.correctness_input_count == 0
    assert not (tmp_path / "workflow" / "correctness" / TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME).exists()


def test_auto_correctness_without_matrix_summary_returns_controlled_invalid(tmp_path: Path) -> None:
    result = run_offline_model_evaluation_workflow(
        _config(tmp_path, auto_task_correctness_from_matrix=True)
    )
    manifest = _load_json(tmp_path / "workflow" / WORKFLOW_RUN_MANIFEST_FILENAME)

    assert result.status == "invalid"
    assert "matrix_run_summary_required_for_correctness_auto" in result.warnings
    assert manifest["status"] == "invalid"
    assert manifest["artifact_paths"]["task_correctness_batch_summary"] is None


def test_malformed_matrix_summary_returns_controlled_invalid_no_traceback(tmp_path: Path) -> None:
    matrix_summary = tmp_path / "inputs" / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME
    matrix_summary.parent.mkdir(parents=True, exist_ok=True)
    matrix_summary.write_text("{bad-json", encoding="utf-8")

    result = run_offline_model_evaluation_workflow(
        _config(
            tmp_path,
            matrix_run_summary_path=str(matrix_summary),
            auto_task_correctness_from_matrix=True,
        )
    )
    manifest = _load_json(tmp_path / "workflow" / WORKFLOW_RUN_MANIFEST_FILENAME)

    assert result.status == "invalid"
    assert any(
        warning.startswith("task_correctness_auto_generation_failed:matrix_summary_json_malformed")
        for warning in result.warnings
    )
    assert manifest["status"] == "invalid"
    assert manifest["artifact_paths"]["task_correctness_batch_summary"] is None


def test_disabled_correctness_evaluator_writes_skipped_auto_summary(tmp_path: Path) -> None:
    matrix_summary = _matrix_run_summary_path(tmp_path)

    result = run_offline_model_evaluation_workflow(
        _config(
            tmp_path,
            matrix_run_summary_path=str(matrix_summary),
            auto_task_correctness_from_matrix=True,
            task_correctness_evaluator="disabled",
        )
    )
    correctness = _load_json(
        tmp_path / "workflow" / "correctness" / TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME
    )

    assert result.correctness_input_count == 1
    assert result.correctness_evaluated_count == 1
    assert correctness["passed_count"] == 0
    assert correctness["skipped_count"] == 1
    assert "task_correctness_evaluator_disabled" in correctness["warnings"]


def test_cli_runs_workflow_and_prints_concise_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    normality_input = _normality_batch_summary_path(tmp_path)
    resource_input = _resource_observation_path(tmp_path)

    code = workflow_runner_cli_main(
        [
            "--model-catalog",
            str(CATALOG_PATH),
            "--scenario",
            SCENARIO_PATH,
            "--output-dir",
            str(tmp_path / "workflow"),
            "--normality-batch-summary",
            str(normality_input),
            "--resource-observation",
            str(resource_input),
            "--task-correctness-summary",
            str(_task_correctness_summary_path(tmp_path)),
            "--workflow-id",
            "cli_workflow",
            "--tag",
            "cli_test",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "ok"
    assert payload["workflow_id"] == "cli_workflow"
    assert payload["candidate_pair_count"] == 2
    assert payload["trial_count"] == 2
    assert payload["readiness_status"] == "ready"
    assert payload["scorecard_path"] == "scorecard/model_evaluation_scorecard.json"
    assert payload["bundle_path"] == "bundle/model_evaluation_workflow_bundle.json"
    assert payload["task_correctness_summary_path"] is not None


def test_cli_auto_task_correctness_from_matrix_works(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    matrix_summary = _matrix_run_summary_path(tmp_path)

    code = workflow_runner_cli_main(
        [
            "--model-catalog",
            str(CATALOG_PATH),
            "--scenario",
            SCENARIO_PATH,
            "--output-dir",
            str(tmp_path / "workflow"),
            "--matrix-run-summary",
            str(matrix_summary),
            "--auto-task-correctness-from-matrix",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "partial"
    assert payload["task_correctness_summary_path"] == "correctness/task_correctness_batch_summary.json"
    assert payload["correctness_input_count"] == 1
    assert payload["correctness_evaluated_count"] == 1
    assert (tmp_path / "workflow" / "correctness" / TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME).is_file()


def test_cli_explicit_task_correctness_summary_overrides_auto(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    explicit_summary = _task_correctness_summary_path(tmp_path)
    matrix_summary = _matrix_run_summary_path(tmp_path, task_success=False, correctness_score=0.0)

    code = workflow_runner_cli_main(
        [
            "--model-catalog",
            str(CATALOG_PATH),
            "--scenario",
            SCENARIO_PATH,
            "--output-dir",
            str(tmp_path / "workflow"),
            "--task-correctness-summary",
            str(explicit_summary),
            "--matrix-run-summary",
            str(matrix_summary),
            "--auto-task-correctness-from-matrix",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    scorecard = _load_json(tmp_path / "workflow" / "scorecard" / MODEL_EVALUATION_SCORECARD_FILENAME)

    assert code == 0
    assert payload["status"] == "partial"
    assert payload["task_correctness_summary_path"] is not None
    assert not (tmp_path / "workflow" / "correctness" / TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME).exists()
    assert scorecard["task_correctness_metrics"]["mean_correctness_score"] == 1.0


def test_cli_invalid_task_correctness_evaluator_rejected(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = workflow_runner_cli_main(
        [
            "--model-catalog",
            str(CATALOG_PATH),
            "--scenario",
            SCENARIO_PATH,
            "--output-dir",
            str(tmp_path / "workflow"),
            "--task-correctness-evaluator",
            "static",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "invalid_task_correctness_evaluator"
    assert "Traceback" not in captured.err


def test_cli_rejects_missing_model_catalog_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = workflow_runner_cli_main(
        [
            "--model-catalog",
            str(tmp_path / "missing_catalog.json"),
            "--scenario",
            SCENARIO_PATH,
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid"
    assert payload["candidate_pair_count"] == 0
    assert "Traceback" not in captured.err


def test_cli_rejects_no_scenario(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = workflow_runner_cli_main(
        [
            "--model-catalog",
            str(CATALOG_PATH),
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "scenario_required"


def test_cli_rejects_absolute_scenario_path(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    absolute_scenario = "\\".join(["C:", "Temp", "outside_workspace", "scenario.json"])

    code = workflow_runner_cli_main(
        [
            "--model-catalog",
            str(CATALOG_PATH),
            "--scenario",
            absolute_scenario,
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "ValidationError"


def test_no_reports_or_experiments_files_are_written(tmp_path: Path) -> None:
    run_offline_model_evaluation_workflow(_config(tmp_path))

    assert not (PROJECT_ROOT / "reports" / WORKFLOW_RUN_MANIFEST_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / WORKFLOW_RUN_MANIFEST_FILENAME).exists()


def test_no_gguf_model_probe_browser_office_calls_are_made(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    matrix_summary = _matrix_run_summary_path(tmp_path)
    original_exists = Path.exists
    original_read_text = Path.read_text
    original_import = __import__

    def forbid_gguf_exists(self: Path) -> bool:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("unexpected GGUF exists check")
        return original_exists(self)

    def forbid_gguf_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("unexpected GGUF read")
        return original_read_text(self, *args, **kwargs)

    def forbid_runtime_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("workflow runner must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    result = run_offline_model_evaluation_workflow(
        _config(
            tmp_path,
            matrix_run_summary_path=str(matrix_summary),
            auto_task_correctness_from_matrix=True,
        )
    )

    assert result.status == "partial"
    assert result.correctness_input_count == 1


def test_no_absolute_tmp_path_leak_in_main_json_artifacts(tmp_path: Path) -> None:
    normality_input = _normality_batch_summary_path(tmp_path)
    resource_input = _resource_observation_path(tmp_path)

    run_offline_model_evaluation_workflow(
        _config(
            tmp_path,
            normality_batch_summary_paths=[str(normality_input)],
            resource_observation_paths=[str(resource_input)],
        )
    )
    output_dir = tmp_path / "workflow"
    paths = [
        output_dir / "plan" / MODEL_COMPARISON_PLAN_FILENAME,
        output_dir / "readiness" / MODEL_COMPARISON_READINESS_REPORT_FILENAME,
        output_dir / "scorecard" / MODEL_EVALUATION_SCORECARD_FILENAME,
        output_dir / "bundle" / MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME,
        output_dir / WORKFLOW_RUN_MANIFEST_FILENAME,
    ]

    for path in paths:
        _assert_no_tmp_path_leak(path.read_text(encoding="utf-8"), tmp_path)
    manifest = _load_json(output_dir / WORKFLOW_RUN_MANIFEST_FILENAME)
    assert manifest["artifact_paths"]["model_comparison_plan"] == "plan/model_comparison_plan.json"
    assert manifest["artifact_paths"]["workflow_bundle"] == "bundle/model_evaluation_workflow_bundle.json"
