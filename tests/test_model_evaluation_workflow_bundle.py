from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_evaluation_workflow_bundle import (
    MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME,
    MODEL_EVALUATION_WORKFLOW_BUNDLE_PREVIEW_FILENAME,
    MODEL_EVALUATION_WORKFLOW_BUNDLE_SCHEMA_VERSION,
    build_model_evaluation_workflow_bundle,
    load_workflow_artifact_summary,
    write_model_evaluation_workflow_bundle,
)
from src.agent.model_evaluation_workflow_bundle_cli import main as bundle_cli_main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_MARKER = "RAW_FULL_WORKFLOW_BUNDLE_TEST_MARKER"


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _catalog_payload() -> dict[str, Any]:
    return {
        "schema_version": "model_catalog_v1",
        "models": [
            {
                "model_id": "first_model",
                "display_name": "First",
                "enabled": True,
            },
            {
                "model_id": "second_model",
                "display_name": "Second",
                "enabled": True,
            },
        ],
    }


def _plan_payload(*, plan_id: str = "workflow_plan") -> dict[str, Any]:
    return {
        "schema_version": "model_comparison_plan_v1",
        "plan_id": plan_id,
        "candidate_pairs": [
            {
                "pair_id": "second_model__to__first_model",
                "orchestrator_model_id": "second_model",
                "executor_model_id": "first_model",
                "no_runtime_execution": True,
            },
            {
                "pair_id": "second_model__to__second_model",
                "orchestrator_model_id": "second_model",
                "executor_model_id": "second_model",
                "no_runtime_execution": True,
            },
        ],
        "scenarios": [
            {"scenario_id": "office_document_file_workflow_basic_v1"},
        ],
        "trials": [
            {
                "trial_id": "trial_1",
                "pair_id": "second_model__to__first_model",
                "scenario_id": "office_document_file_workflow_basic_v1",
            },
            {
                "trial_id": "trial_2",
                "pair_id": "second_model__to__second_model",
                "scenario_id": "office_document_file_workflow_basic_v1",
            },
        ],
        "no_runtime_execution": True,
        "raw_notes": RAW_MARKER,
    }


def _readiness_payload() -> dict[str, Any]:
    return {
        "schema_version": "model_comparison_readiness_v1",
        "status": "ready",
        "trial_count": 2,
        "candidate_pair_count": 2,
        "scenario_count": 1,
        "summary": {
            "error_count": 0,
            "warning_count": 0,
            "info_count": 4,
            "issue_count": 4,
        },
        "issues": [
            {"severity": "info", "code": "scenario_execute_actions_disabled"},
            {"severity": "info", "code": "evaluator_importable"},
        ],
        "debug_raw": RAW_MARKER,
    }


def _normality_payload(*, top_pair: str = "second_model->first_model") -> dict[str, Any]:
    return {
        "schema_version": "normality_comparison_v1",
        "status": "ok",
        "input_summary_count": 1,
        "total_entries": 2,
        "evaluated_entries": 2,
        "failed_entries": 0,
        "overall": {"label_counts": {"normal": 2}},
        "leaderboard": [{"pair_label": top_pair, "mean_overall_score": 0.91}],
        "groups": {
            "by_model_pair": {
                "second_model->first_model": {
                    "label_counts": {"normal": 2},
                    "top_findings": [{"finding": RAW_MARKER, "count": 1}],
                }
            }
        },
    }


def _resource_payload() -> dict[str, Any]:
    return {
        "schema_version": "model_resource_summary_v1",
        "status": "ok",
        "observation_count": 2,
        "invalid_count": 0,
        "groups": {
            "by_pair": {
                "second_model__to__first_model": {"observation_count": 1},
                "second_model__to__second_model": {"observation_count": 1},
            },
            "by_model": {
                "first_model": {"observation_count": 1},
                "second_model": {"observation_count": 2},
            },
            "by_runtime_mode": {
                "offline_fixture": {"observation_count": 2},
            },
        },
        "raw_notes": [RAW_MARKER],
    }


def _task_correctness_payload() -> dict[str, Any]:
    return {
        "schema_version": "task_correctness_batch_summary_v1",
        "summary_id": "workflow_correctness",
        "input_count": 2,
        "evaluated_count": 2,
        "invalid_count": 0,
        "passed_count": 1,
        "failed_count": 1,
        "partial_count": 0,
        "skipped_count": 0,
        "mean_correctness_score": 0.5,
        "by_pair": {
            "second_model__to__first_model": {"evaluated_count": 2},
        },
        "by_scenario": {
            "office_document_file_workflow_basic_v1": {"evaluated_count": 2},
        },
        "results": [{"trial_id": "raw_result_not_copied"}],
        "warnings": ["synthetic_warning"],
        "notes": ["Synthetic correctness summary."],
        "no_runtime_execution": True,
    }


def _scorecard_payload(*, scorecard_id: str = "workflow_scorecard") -> dict[str, Any]:
    return {
        "schema_version": "model_evaluation_scorecard_v1",
        "status": "ok",
        "scorecard_id": scorecard_id,
        "model_count": 2,
        "model_pair_count": 2,
        "warnings": ["synthetic_warning"],
        "model_pairs": [{"pair_id": "second_model__to__first_model", "raw": RAW_MARKER}],
    }


def _artifact_paths(tmp_path: Path) -> dict[str, Path]:
    return {
        "model_catalog": _write_json(tmp_path / "catalog.json", _catalog_payload()),
        "model_comparison_plan": _write_json(tmp_path / "plan.json", _plan_payload()),
        "readiness_report": _write_json(tmp_path / "readiness.json", _readiness_payload()),
        "normality_comparison_summary": _write_json(tmp_path / "normality.json", _normality_payload()),
        "model_resource_summary": _write_json(tmp_path / "resource.json", _resource_payload()),
        "task_correctness_batch_summary": _write_json(tmp_path / "correctness.json", _task_correctness_payload()),
        "model_evaluation_scorecard": _write_json(tmp_path / "scorecard.json", _scorecard_payload()),
    }


def _complete_bundle(tmp_path: Path):
    paths = _artifact_paths(tmp_path)
    return build_model_evaluation_workflow_bundle(
        model_catalog_path=paths["model_catalog"],
        model_comparison_plan_path=paths["model_comparison_plan"],
        readiness_report_path=paths["readiness_report"],
        normality_comparison_summary_path=paths["normality_comparison_summary"],
        model_resource_summary_path=paths["model_resource_summary"],
        model_evaluation_scorecard_path=paths["model_evaluation_scorecard"],
        bundle_id="complete_bundle",
        base_dir=tmp_path,
    )


def test_builds_complete_bundle_from_synthetic_valid_artifacts(tmp_path: Path) -> None:
    bundle = _complete_bundle(tmp_path)

    assert bundle.schema_version == MODEL_EVALUATION_WORKFLOW_BUNDLE_SCHEMA_VERSION
    assert bundle.status == "complete"
    assert bundle.bundle_id == "complete_bundle"
    assert bundle.summary["model_count"] == 2
    assert bundle.summary["candidate_pair_count"] == 2
    assert bundle.summary["trial_count"] == 2
    assert bundle.summary["readiness_status"] == "ready"
    assert bundle.summary["scorecard_pair_count"] == 2
    assert bundle.summary["normality_evaluated_entries"] == 2
    assert bundle.summary["resource_observation_count"] == 2
    assert bundle.summary["required_artifacts_ok"] is True
    assert set(bundle.summary["optional_artifacts_present"]) == {
        "normality_comparison_summary",
        "model_resource_summary",
        "model_evaluation_scorecard",
    }


def test_builds_partial_bundle_when_optional_artifacts_missing(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)

    bundle = build_model_evaluation_workflow_bundle(
        model_catalog_path=paths["model_catalog"],
        model_comparison_plan_path=paths["model_comparison_plan"],
        readiness_report_path=paths["readiness_report"],
        bundle_id="partial_bundle",
        base_dir=tmp_path,
    )

    assert bundle.status == "partial"
    assert bundle.summary["required_artifacts_ok"] is True
    assert bundle.summary["optional_artifacts_present"] == []
    assert bundle.artifacts["normality_comparison_summary"].status == "not_provided"
    assert "optional_artifact_not_provided:normality_comparison_summary" in bundle.warnings


def test_invalid_when_required_catalog_missing(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)

    bundle = build_model_evaluation_workflow_bundle(
        model_catalog_path=tmp_path / "missing_catalog.json",
        model_comparison_plan_path=paths["model_comparison_plan"],
        readiness_report_path=paths["readiness_report"],
        base_dir=tmp_path,
    )

    assert bundle.status == "invalid"
    assert bundle.artifacts["model_catalog"].status == "missing"
    assert bundle.summary["required_artifacts_ok"] is False


def test_invalid_when_required_plan_malformed(tmp_path: Path) -> None:
    paths = _artifact_paths(tmp_path)
    bad_plan = tmp_path / "bad_plan.json"
    bad_plan.write_text("{not-json", encoding="utf-8")

    bundle = build_model_evaluation_workflow_bundle(
        model_catalog_path=paths["model_catalog"],
        model_comparison_plan_path=bad_plan,
        readiness_report_path=paths["readiness_report"],
        base_dir=tmp_path,
    )

    assert bundle.status == "invalid"
    assert bundle.artifacts["model_comparison_plan"].status == "invalid_input"
    assert "model_comparison_plan:artifact_json_decode_error" in bundle.warnings


def test_extracts_catalog_summary(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "catalog.json", _catalog_payload())

    artifact = load_workflow_artifact_summary(path, "model_catalog", base_dir=tmp_path)

    assert artifact.status == "ok"
    assert artifact.summary == {
        "schema_version": "model_catalog_v1",
        "model_count": 2,
        "model_ids": ["first_model", "second_model"],
        "enabled_count": 2,
    }


def test_extracts_plan_summary(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "plan.json", _plan_payload())

    artifact = load_workflow_artifact_summary(path, "model_comparison_plan", base_dir=tmp_path)

    assert artifact.summary["plan_id"] == "workflow_plan"
    assert artifact.summary["candidate_pair_count"] == 2
    assert artifact.summary["trial_count"] == 2
    assert artifact.summary["scenario_count"] == 1
    assert artifact.summary["no_runtime_execution"] is True


def test_extracts_readiness_summary(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "readiness.json", _readiness_payload())

    artifact = load_workflow_artifact_summary(path, "readiness_report", base_dir=tmp_path)

    assert artifact.summary["readiness_status"] == "ready"
    assert artifact.summary["error_count"] == 0
    assert artifact.summary["warning_count"] == 0
    assert artifact.summary["info_count"] == 4
    assert artifact.summary["issue_count"] == 4
    assert artifact.summary["trial_count"] == 2
    assert artifact.summary["candidate_pair_count"] == 2


def test_extracts_normality_summary(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "normality.json", _normality_payload())

    artifact = load_workflow_artifact_summary(path, "normality_comparison_summary", base_dir=tmp_path)

    assert artifact.summary["input_summary_count"] == 1
    assert artifact.summary["total_entries"] == 2
    assert artifact.summary["evaluated_entries"] == 2
    assert artifact.summary["failed_entries"] == 0
    assert artifact.summary["top_model_pair"] == "second_model->first_model"
    assert artifact.summary["label_counts"] == {"normal": 2}


def test_extracts_resource_summary(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "resource.json", _resource_payload())

    artifact = load_workflow_artifact_summary(path, "model_resource_summary", base_dir=tmp_path)

    assert artifact.summary["observation_count"] == 2
    assert artifact.summary["invalid_count"] == 0
    assert artifact.summary["group_counts"] == {
        "by_model": 2,
        "by_pair": 2,
        "by_runtime_mode": 1,
    }
    assert artifact.summary["runtime_modes"] == ["offline_fixture"]


def test_extracts_task_correctness_summary(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "correctness.json", _task_correctness_payload())

    artifact = load_workflow_artifact_summary(path, "task_correctness_batch_summary", base_dir=tmp_path)

    assert artifact.summary["evaluated_count"] == 2
    assert artifact.summary["passed_count"] == 1
    assert artifact.summary["failed_count"] == 1
    assert artifact.summary["pair_count"] == 1
    assert artifact.summary["scenario_count"] == 1
    assert artifact.summary["warning_count"] == 1


def test_extracts_scorecard_summary(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "scorecard.json", _scorecard_payload())

    artifact = load_workflow_artifact_summary(path, "model_evaluation_scorecard", base_dir=tmp_path)

    assert artifact.summary["scorecard_id"] == "workflow_scorecard"
    assert artifact.summary["model_pair_count"] == 2
    assert artifact.summary["model_count"] == 2
    assert artifact.summary["warnings_count"] == 1


def test_bundle_does_not_include_raw_full_artifact_contents(tmp_path: Path) -> None:
    bundle = _complete_bundle(tmp_path)
    text = json.dumps(bundle.model_dump(mode="json"), ensure_ascii=False)

    assert RAW_MARKER not in text
    assert "model_pairs" not in text
    assert "top_findings" not in text


def test_redacts_absolute_windows_paths(tmp_path: Path) -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "plan.json"])
    path = _write_json(tmp_path / "plan.json", _plan_payload(plan_id=f"plan {windows_path}"))

    artifact = load_workflow_artifact_summary(path, "model_comparison_plan", base_dir=tmp_path)
    text = json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False)

    assert windows_path not in text
    assert "<absolute_path>" in text


def test_redacts_absolute_posix_paths(tmp_path: Path) -> None:
    posix_path = "/home/example/outside_workspace/scorecard.json"
    path = _write_json(tmp_path / "scorecard.json", _scorecard_payload(scorecard_id=f"scorecard {posix_path}"))

    artifact = load_workflow_artifact_summary(path, "model_evaluation_scorecard", base_dir=tmp_path)
    text = json.dumps(artifact.model_dump(mode="json"), ensure_ascii=False)

    assert posix_path not in text
    assert "<absolute_path>" in text


def test_uses_relative_or_sanitized_display_paths(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "nested" / "catalog.json", _catalog_payload())
    external_display = load_workflow_artifact_summary(path, "model_catalog", base_dir=tmp_path / "other")
    relative_display = load_workflow_artifact_summary(path, "model_catalog", base_dir=tmp_path)

    assert relative_display.path == "nested/catalog.json"
    assert external_display.path is not None
    assert str(tmp_path) not in external_display.path
    assert external_display.path.startswith("<absolute_path>/")


def test_cli_writes_bundle_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = _artifact_paths(tmp_path)

    code = bundle_cli_main(
        [
            "--model-catalog",
            str(paths["model_catalog"]),
            "--model-comparison-plan",
            str(paths["model_comparison_plan"]),
            "--readiness-report",
            str(paths["readiness_report"]),
            "--normality-comparison-summary",
            str(paths["normality_comparison_summary"]),
            "--model-resource-summary",
            str(paths["model_resource_summary"]),
            "--task-correctness-summary",
            str(paths["task_correctness_batch_summary"]),
            "--model-evaluation-scorecard",
            str(paths["model_evaluation_scorecard"]),
            "--output-dir",
            str(tmp_path / "bundle_out"),
            "--bundle-id",
            "cli_bundle",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    bundle_payload = _load_json(tmp_path / "bundle_out" / MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME)

    assert code == 0
    assert payload["status"] == "complete"
    assert payload["bundle_id"] == "cli_bundle"
    assert payload["required_artifacts_ok"] is True
    assert set(payload["optional_artifacts_present"]) == {
        "normality_comparison_summary",
        "model_resource_summary",
        "task_correctness_batch_summary",
        "model_evaluation_scorecard",
    }
    assert payload["bundle_path"] == MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME
    assert bundle_payload["bundle_id"] == "cli_bundle"


def test_cli_writes_optional_markdown_preview(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    paths = _artifact_paths(tmp_path)

    code = bundle_cli_main(
        [
            "--model-catalog",
            str(paths["model_catalog"]),
            "--model-comparison-plan",
            str(paths["model_comparison_plan"]),
            "--readiness-report",
            str(paths["readiness_report"]),
            "--output-dir",
            str(tmp_path / "bundle_out"),
            "--write-markdown-preview",
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    bundle_payload = _load_json(tmp_path / "bundle_out" / MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME)

    assert code == 0
    assert payload["status"] == "partial"
    assert (tmp_path / "bundle_out" / MODEL_EVALUATION_WORKFLOW_BUNDLE_PREVIEW_FILENAME).is_file()
    assert bundle_payload["markdown_preview_path_relative"] == MODEL_EVALUATION_WORKFLOW_BUNDLE_PREVIEW_FILENAME


def test_cli_missing_required_artifact_returns_nonzero_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    paths = _artifact_paths(tmp_path)

    code = bundle_cli_main(
        [
            "--model-catalog",
            str(tmp_path / "missing_catalog.json"),
            "--model-comparison-plan",
            str(paths["model_comparison_plan"]),
            "--readiness-report",
            str(paths["readiness_report"]),
            "--output-dir",
            str(tmp_path / "bundle_out"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid"
    assert payload["required_artifacts_ok"] is False
    assert payload["bundle_path"] == MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME
    assert "Traceback" not in captured.err


def test_no_reports_or_experiments_files_are_written(tmp_path: Path) -> None:
    bundle = _complete_bundle(tmp_path)

    write_model_evaluation_workflow_bundle(bundle, tmp_path / "bundle_out")

    assert not (PROJECT_ROOT / "reports" / MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME).exists()


def test_no_gguf_model_browser_office_or_probe_calls_are_made(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    paths = _artifact_paths(tmp_path)
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
            raise AssertionError("workflow bundle must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    bundle = build_model_evaluation_workflow_bundle(
        model_catalog_path=paths["model_catalog"],
        model_comparison_plan_path=paths["model_comparison_plan"],
        readiness_report_path=paths["readiness_report"],
        normality_comparison_summary_path=paths["normality_comparison_summary"],
        model_resource_summary_path=paths["model_resource_summary"],
        model_evaluation_scorecard_path=paths["model_evaluation_scorecard"],
        base_dir=tmp_path,
    )

    assert bundle.status == "complete"
