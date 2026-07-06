from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_evaluation_artifact_validator import (
    MODEL_EVALUATION_ARTIFACT_VALIDATION_PREVIEW_FILENAME,
    MODEL_EVALUATION_ARTIFACT_VALIDATION_REPORT_FILENAME,
    MODEL_EVALUATION_ARTIFACT_VALIDATION_SCHEMA_VERSION,
    validate_model_evaluation_artifacts,
    validate_model_evaluation_workflow_output_dir,
    write_model_evaluation_artifact_validation_report,
)
from src.agent.model_evaluation_artifact_validator_cli import main as validator_cli_main
from src.agent.model_evaluation_workflow_runner import (
    ModelEvaluationWorkflowRunConfig,
    run_offline_model_evaluation_workflow,
)
from src.agent.model_task_correctness_evaluation import TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
PLAN_PATH = Path("plan") / "model_comparison_plan.json"
READINESS_PATH = Path("readiness") / "model_comparison_readiness_report.json"
NORMALITY_PATH = Path("normality") / "normality_comparison_summary.json"
RESOURCE_PATH = Path("resource") / "model_resource_summary.json"
SCORECARD_PATH = Path("scorecard") / "model_evaluation_scorecard.json"
BUNDLE_PATH = Path("bundle") / "model_evaluation_workflow_bundle.json"
MANIFEST_PATH = Path("workflow_run_manifest.json")


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _workflow_config(tmp_path: Path, **overrides: object) -> ModelEvaluationWorkflowRunConfig:
    payload = {
        "workflow_id": "artifact_validator_workflow",
        "model_catalog_path": str(CATALOG_PATH),
        "scenario_paths": [SCENARIO_PATH],
        "output_dir": str(tmp_path / "workflow"),
        "repetitions_per_pair": 1,
        "include_self_pairs": True,
        "tags": ["artifact_validator_test"],
        **overrides,
    }
    return ModelEvaluationWorkflowRunConfig.model_validate(payload)


def _normality_batch_summary_path(tmp_path: Path) -> Path:
    entries = []
    for pair_id, executor, score in [
        ("second_model__to__first_model", "first_model", 0.89),
        ("second_model__to__second_model", "second_model", 0.91),
    ]:
        entries.append(
            {
                "scenario_id": "office_document_file_workflow_basic_v1",
                "trial_id": f"office_document_file_workflow_basic_v1__{pair_id}__normality",
                "model_pair": {"orchestrator": "second_model", "executor": executor},
                "tags": ["artifact_validator_test", "normality"],
                "status": "ok",
                "label": "normal",
                "overall_score": score,
                "findings": [f"synthetic_ok_{executor}"],
                "warnings": [],
            }
        )
    return _write_json(
        tmp_path / "inputs" / "normality_batch.json",
        {
            "status": "ok",
            "batch_id": "artifact_validator_batch",
            "input_count": 1,
            "evaluated_count": len(entries),
            "failed_count": 0,
            "entries": entries,
        },
    )


def _resource_observation_path(tmp_path: Path) -> Path:
    rows = []
    for index, executor in enumerate(["first_model", "second_model"], start=1):
        pair_id = f"second_model__to__{executor}"
        rows.append(
            {
                "observation_id": f"artifact_validator_resource_{index}",
                "orchestrator_model_id": "second_model",
                "executor_model_id": executor,
                "pair_id": pair_id,
                "scenario_id": "office_document_file_workflow_basic_v1",
                "trial_id": f"office_document_file_workflow_basic_v1__{pair_id}__resource",
                "runtime_mode": "offline_fixture",
                "backend": "synthetic_fixture",
                "success": True,
                "wall_time_s": 1.0,
                "peak_ram_gb": 2.0,
                "peak_vram_gb": 0.0,
                "tags": ["artifact_validator_test", "resource"],
            }
        )
    return _write_json(tmp_path / "inputs" / "resource_observations.json", rows)


def _task_correctness_summary_path(tmp_path: Path) -> Path:
    return _write_json(
        tmp_path / "inputs" / TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME,
        {
            "schema_version": "task_correctness_batch_summary_v1",
            "summary_id": "artifact_validator_correctness",
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
                    "trial_id": "artifact_validator_correctness_trial",
                    "scenario_id": "office_document_file_workflow_basic_v1",
                    "pair_id": "second_model__to__first_model",
                    "status": "passed",
                    "task_success": True,
                    "correctness_score": 1.0,
                    "check_results": [],
                    "failure_reasons": [],
                    "warnings": [],
                    "notes": ["synthetic_validator_correctness"],
                    "no_runtime_execution": True,
                }
            ],
            "warnings": [],
            "notes": ["Synthetic validator correctness summary."],
            "no_runtime_execution": True,
        },
    )


def _complete_workflow(tmp_path: Path) -> Path:
    normality_input = _normality_batch_summary_path(tmp_path)
    resource_input = _resource_observation_path(tmp_path)
    run_offline_model_evaluation_workflow(
        _workflow_config(
            tmp_path,
            normality_batch_summary_paths=[str(normality_input)],
            resource_observation_paths=[str(resource_input)],
        )
    )
    return tmp_path / "workflow"


def _complete_workflow_with_task_correctness(tmp_path: Path) -> tuple[Path, Path]:
    normality_input = _normality_batch_summary_path(tmp_path)
    resource_input = _resource_observation_path(tmp_path)
    correctness_input = _task_correctness_summary_path(tmp_path)
    run_offline_model_evaluation_workflow(
        _workflow_config(
            tmp_path,
            normality_batch_summary_paths=[str(normality_input)],
            resource_observation_paths=[str(resource_input)],
            task_correctness_summary_path=str(correctness_input),
        )
    )
    return tmp_path / "workflow", correctness_input


def _partial_workflow(tmp_path: Path) -> Path:
    run_offline_model_evaluation_workflow(_workflow_config(tmp_path))
    return tmp_path / "workflow"


def _issue_codes(report) -> set[str]:
    return {issue.code for issue in report.issues}


def _explicit_paths(workflow_dir: Path) -> list[str]:
    return [
        "--plan",
        str(workflow_dir / PLAN_PATH),
        "--readiness-report",
        str(workflow_dir / READINESS_PATH),
        "--normality-comparison-summary",
        str(workflow_dir / NORMALITY_PATH),
        "--model-resource-summary",
        str(workflow_dir / RESOURCE_PATH),
        "--scorecard",
        str(workflow_dir / SCORECARD_PATH),
        "--workflow-bundle",
        str(workflow_dir / BUNDLE_PATH),
        "--workflow-run-manifest",
        str(workflow_dir / MANIFEST_PATH),
    ]


def test_validates_complete_workflow_output_generated_from_runner_inputs(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)

    report = validate_model_evaluation_workflow_output_dir(workflow_dir)

    assert report.schema_version == MODEL_EVALUATION_ARTIFACT_VALIDATION_SCHEMA_VERSION
    assert report.status == "valid"
    assert report.error_count == 0
    assert report.warning_count == 0
    assert report.cross_link_summary["plan_pair_count"] == 2
    assert report.cross_link_summary["scorecard_pair_count"] == 2


def test_validates_explicit_task_correctness_artifact_from_runner(tmp_path: Path) -> None:
    workflow_dir, correctness_path = _complete_workflow_with_task_correctness(tmp_path)

    report = validate_model_evaluation_artifacts(
        plan_path=workflow_dir / PLAN_PATH,
        readiness_report_path=workflow_dir / READINESS_PATH,
        normality_comparison_summary_path=workflow_dir / NORMALITY_PATH,
        model_resource_summary_path=workflow_dir / RESOURCE_PATH,
        task_correctness_summary_path=correctness_path,
        scorecard_path=workflow_dir / SCORECARD_PATH,
        workflow_bundle_path=workflow_dir / BUNDLE_PATH,
        workflow_run_manifest_path=workflow_dir / MANIFEST_PATH,
        base_dir=workflow_dir,
    )

    assert report.status == "valid"
    assert report.error_count == 0
    assert report.cross_link_summary["task_correctness_pair_count"] == 1
    assert report.checked_artifacts["task_correctness_batch_summary"]["status"] == "ok"


def test_validates_partial_workflow_output_with_optional_missing_as_warning(tmp_path: Path) -> None:
    workflow_dir = _partial_workflow(tmp_path)

    report = validate_model_evaluation_workflow_output_dir(workflow_dir)

    assert report.status == "valid_with_warnings"
    assert report.error_count == 0
    assert "artifact_missing" in _issue_codes(report)
    assert report.checked_artifacts["normality_comparison_summary"]["status"] == "missing"
    assert report.checked_artifacts["model_resource_summary"]["status"] == "missing"


def test_invalid_plan_json_produces_invalid_report(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)
    (workflow_dir / PLAN_PATH).write_text("{not-json", encoding="utf-8")

    report = validate_model_evaluation_workflow_output_dir(workflow_dir)

    assert report.status == "invalid"
    assert "artifact_json_decode_error" in _issue_codes(report)


def test_missing_required_plan_in_workflow_output_dir_is_invalid(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)
    (workflow_dir / PLAN_PATH).unlink()

    report = validate_model_evaluation_workflow_output_dir(workflow_dir)

    assert report.status == "invalid"
    assert report.checked_artifacts["model_comparison_plan"]["status"] == "missing"


def test_duplicate_trial_ids_produce_error(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)
    plan_path = workflow_dir / PLAN_PATH
    plan = _load_json(plan_path)
    plan["trials"][1]["trial_id"] = plan["trials"][0]["trial_id"]
    _write_json(plan_path, plan)

    report = validate_model_evaluation_workflow_output_dir(workflow_dir)

    assert report.status == "invalid"
    assert "duplicate_trial_id" in _issue_codes(report)


def test_trial_references_missing_pair_produces_error(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)
    plan_path = workflow_dir / PLAN_PATH
    plan = _load_json(plan_path)
    plan["trials"][0]["pair_id"] = "missing_pair"
    _write_json(plan_path, plan)

    report = validate_model_evaluation_workflow_output_dir(workflow_dir)

    assert report.status == "invalid"
    assert "trial_references_missing_pair" in _issue_codes(report)


def test_readiness_trial_count_mismatch_produces_error(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)
    readiness_path = workflow_dir / READINESS_PATH
    readiness = _load_json(readiness_path)
    readiness["trial_count"] = 999
    _write_json(readiness_path, readiness)

    report = validate_model_evaluation_workflow_output_dir(workflow_dir)

    assert report.status == "invalid"
    assert "readiness_trial_count_mismatch" in _issue_codes(report)


def test_scorecard_missing_planned_pair_produces_warning(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)
    scorecard_path = workflow_dir / SCORECARD_PATH
    scorecard = _load_json(scorecard_path)
    scorecard["model_pairs"] = scorecard["model_pairs"][:1]
    scorecard["model_pair_count"] = 1
    _write_json(scorecard_path, scorecard)

    report = validate_model_evaluation_workflow_output_dir(workflow_dir)

    assert report.status == "valid_with_warnings"
    assert "scorecard_missing_planned_pair" in _issue_codes(report)


def test_bundle_required_artifact_marked_present_but_actual_file_missing_is_error(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)
    (workflow_dir / READINESS_PATH).unlink()

    report = validate_model_evaluation_workflow_output_dir(workflow_dir)

    assert report.status == "invalid"
    assert "bundle_marks_missing_artifact_present" in _issue_codes(report)


def test_manifest_absolute_path_leak_is_flagged_and_redacted(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)
    manifest_path = workflow_dir / MANIFEST_PATH
    manifest = _load_json(manifest_path)
    windows_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "plan.json"])
    manifest["artifact_paths"]["model_comparison_plan"] = windows_path
    _write_json(manifest_path, manifest)

    report = validate_model_evaluation_workflow_output_dir(workflow_dir)
    report_path, _ = write_model_evaluation_artifact_validation_report(report, tmp_path / "validation")
    report_text = report_path.read_text(encoding="utf-8")

    assert report.status == "invalid"
    assert "manifest_absolute_path_leak" in _issue_codes(report)
    assert "absolute_path_leak_detected" in _issue_codes(report)
    assert windows_path not in report_text
    assert "<absolute_path>" in report_text


def test_artifact_string_with_windows_absolute_path_is_flagged_and_redacted(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)
    plan_path = workflow_dir / PLAN_PATH
    plan = _load_json(plan_path)
    windows_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "trace.txt"])
    plan["plan_id"] = f"leaky {windows_path}"
    _write_json(plan_path, plan)

    report = validate_model_evaluation_artifacts(plan_path=plan_path, base_dir=workflow_dir)
    text = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)

    assert report.status == "invalid"
    assert "absolute_path_leak_detected" in _issue_codes(report)
    assert windows_path not in text


def test_artifact_string_with_posix_absolute_path_is_flagged_and_redacted(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)
    plan_path = workflow_dir / PLAN_PATH
    plan = _load_json(plan_path)
    posix_path = "/home/example/outside_workspace/trace.txt"
    plan["plan_id"] = f"leaky {posix_path}"
    _write_json(plan_path, plan)

    report = validate_model_evaluation_artifacts(plan_path=plan_path, base_dir=workflow_dir)
    text = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)

    assert report.status == "invalid"
    assert "absolute_path_leak_detected" in _issue_codes(report)
    assert posix_path not in text


def test_suspicious_secret_like_field_is_flagged_without_value(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)
    plan_path = workflow_dir / PLAN_PATH
    plan = _load_json(plan_path)
    secret_value = "example-secret-value"
    plan["api_key"] = secret_value
    _write_json(plan_path, plan)

    report = validate_model_evaluation_artifacts(plan_path=plan_path, base_dir=workflow_dir)
    text = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)

    assert report.status == "invalid"
    assert "suspicious_secret_or_raw_field" in _issue_codes(report)
    assert secret_value not in text


def test_cli_validates_workflow_output_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    workflow_dir = _complete_workflow(tmp_path)

    code = validator_cli_main(
        [
            "--workflow-output-dir",
            str(workflow_dir),
            "--output-dir",
            str(tmp_path / "validation"),
            "--validation-id",
            "cli_workflow_validation",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "valid"
    assert payload["validation_id"] == "cli_workflow_validation"
    assert payload["checked_artifact_count"] == 7
    assert payload["report_path"] == MODEL_EVALUATION_ARTIFACT_VALIDATION_REPORT_FILENAME


def test_cli_validates_explicit_artifact_paths(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    workflow_dir = _complete_workflow(tmp_path)

    code = validator_cli_main(
        [
            *_explicit_paths(workflow_dir),
            "--output-dir",
            str(tmp_path / "validation"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "valid"
    assert payload["checked_artifact_count"] == 7


def test_cli_validates_explicit_task_correctness_artifact(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow_dir, correctness_path = _complete_workflow_with_task_correctness(tmp_path)

    code = validator_cli_main(
        [
            *_explicit_paths(workflow_dir),
            "--task-correctness-summary",
            str(correctness_path),
            "--output-dir",
            str(tmp_path / "validation"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "valid"
    assert payload["checked_artifact_count"] == 8


def test_cli_strict_returns_nonzero_on_warnings(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    workflow_dir = _partial_workflow(tmp_path)

    code = validator_cli_main(
        [
            "--workflow-output-dir",
            str(workflow_dir),
            "--output-dir",
            str(tmp_path / "validation"),
            "--strict",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 2
    assert payload["status"] == "valid_with_warnings"
    assert payload["warning_count"] > 0


def test_cli_missing_or_malformed_input_returns_nonzero_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    bad_plan = tmp_path / "bad_plan.json"
    bad_plan.write_text("{not-json", encoding="utf-8")

    code = validator_cli_main(
        [
            "--plan",
            str(bad_plan),
            "--output-dir",
            str(tmp_path / "validation"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid"
    assert "Traceback" not in captured.err


def test_validation_report_written_only_to_tmp_output_dir(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)
    report = validate_model_evaluation_workflow_output_dir(workflow_dir)

    report_path, preview_path = write_model_evaluation_artifact_validation_report(
        report,
        tmp_path / "validation",
        write_markdown_preview=True,
    )

    assert report_path == tmp_path / "validation" / MODEL_EVALUATION_ARTIFACT_VALIDATION_REPORT_FILENAME
    assert preview_path == tmp_path / "validation" / MODEL_EVALUATION_ARTIFACT_VALIDATION_PREVIEW_FILENAME
    assert report_path.is_file()
    assert preview_path is not None and preview_path.is_file()


def test_no_reports_or_experiments_files_are_written(tmp_path: Path) -> None:
    workflow_dir = _complete_workflow(tmp_path)
    report = validate_model_evaluation_workflow_output_dir(workflow_dir)

    write_model_evaluation_artifact_validation_report(report, tmp_path / "validation")

    assert not (PROJECT_ROOT / "reports" / MODEL_EVALUATION_ARTIFACT_VALIDATION_REPORT_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / MODEL_EVALUATION_ARTIFACT_VALIDATION_REPORT_FILENAME).exists()


def test_no_gguf_model_probe_browser_or_office_calls_are_made(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    workflow_dir = _complete_workflow(tmp_path)
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
            raise AssertionError("artifact validator must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    report = validate_model_evaluation_workflow_output_dir(workflow_dir)

    assert report.status == "valid"
