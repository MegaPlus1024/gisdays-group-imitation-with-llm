from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

import pytest

from src.agent import model_evaluation_artifact_registry as registry
from src.agent.model_evaluation_artifact_contracts import validate_artifact_against_contract
from src.agent.model_evaluation_cli import main as model_evaluation_cli_main
from src.agent.model_evaluation_compatibility_gate import (
    MODEL_EVALUATION_COMPATIBILITY_PREVIEW_FILENAME,
    MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME,
    compare_workflow_output_to_golden_expectations,
    run_model_evaluation_compatibility_gate,
    validate_golden_fixture_pack,
    write_model_evaluation_compatibility_report,
)
from src.agent.model_evaluation_compatibility_gate_cli import main as compatibility_gate_cli_main
from src.agent.model_evaluation_workflow_runner import (
    ModelEvaluationWorkflowRunConfig,
    run_offline_model_evaluation_workflow,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = PROJECT_ROOT / "tests" / "fixtures" / "model_evaluation_workflow_golden"
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
PLAN_PATH = Path("plan") / "model_comparison_plan.json"
NORMALITY_PATH = Path("normality") / "normality_comparison_summary.json"
RESOURCE_PATH = Path("resource") / "model_resource_summary.json"


def _copy_golden_pack(tmp_path: Path) -> Path:
    target = tmp_path / "golden_workflow"
    shutil.copytree(GOLDEN_DIR, target)
    return target


def _load_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _issue_codes(report) -> set[str]:
    return {issue.code for issue in report.issues}


def _normality_batch_summary_path(tmp_path: Path) -> Path:
    entries = []
    for pair_id, executor, score in [
        ("second_model__to__first_model", "first_model", 0.88),
        ("second_model__to__second_model", "second_model", 0.91),
    ]:
        entries.append(
            {
                "scenario_id": "office_document_file_workflow_basic_v1",
                "trial_id": f"compatibility_{pair_id}_normality",
                "model_pair": {"orchestrator": "second_model", "executor": executor},
                "tags": ["compatibility_gate_test"],
                "status": "ok",
                "label": "normal",
                "overall_score": score,
                "findings": ["synthetic_fixture_normality"],
                "warnings": [],
            }
        )
    return _write_json(
        tmp_path / "inputs" / "normality_batch.json",
        {
            "status": "ok",
            "batch_id": "compatibility_gate_batch",
            "input_count": len(entries),
            "evaluated_count": len(entries),
            "failed_count": 0,
            "entries": entries,
        },
    )


def _resource_observation_path(tmp_path: Path) -> Path:
    rows = []
    for index, (pair_id, executor) in enumerate(
        [
            ("second_model__to__first_model", "first_model"),
            ("second_model__to__second_model", "second_model"),
        ],
        start=1,
    ):
        rows.append(
            {
                "observation_id": f"compatibility_resource_{index}",
                "orchestrator_model_id": "second_model",
                "executor_model_id": executor,
                "pair_id": pair_id,
                "scenario_id": "office_document_file_workflow_basic_v1",
                "trial_id": f"compatibility_{pair_id}_resource",
                "runtime_mode": "offline_fixture",
                "backend": "synthetic_fixture",
                "success": True,
                "wall_time_s": 1.0 + index / 10,
                "peak_ram_gb": 2.0 + index / 10,
                "peak_vram_gb": 0.0,
                "tags": ["compatibility_gate_test"],
            }
        )
    return _write_json(tmp_path / "inputs" / "resource_observations.json", rows)


def _workflow_config(tmp_path: Path, *, include_optional: bool) -> ModelEvaluationWorkflowRunConfig:
    payload: dict[str, Any] = {
        "workflow_id": "compatibility_gate_workflow",
        "model_catalog_path": str(CATALOG_PATH),
        "scenario_paths": [SCENARIO_PATH],
        "output_dir": str(tmp_path / "workflow"),
        "repetitions_per_pair": 1,
        "include_self_pairs": True,
        "tags": ["compatibility_gate_test"],
    }
    if include_optional:
        payload["normality_batch_summary_paths"] = [str(_normality_batch_summary_path(tmp_path))]
        payload["resource_observation_paths"] = [str(_resource_observation_path(tmp_path))]
    return ModelEvaluationWorkflowRunConfig.model_validate(payload)


def _workflow_output(tmp_path: Path, *, include_optional: bool = True) -> Path:
    result = run_offline_model_evaluation_workflow(_workflow_config(tmp_path, include_optional=include_optional))
    assert result.status in {"ok", "partial"}
    return tmp_path / "workflow"


def test_golden_fixture_pack_validates_as_compatible() -> None:
    report = validate_golden_fixture_pack(GOLDEN_DIR)

    assert report.status == "compatible"
    assert report.error_count == 0
    assert report.checked_artifact_count == 9
    assert report.no_runtime_execution is True


def test_missing_golden_fixture_file_produces_incompatible_report(tmp_path: Path) -> None:
    golden_dir = _copy_golden_pack(tmp_path)
    (golden_dir / PLAN_PATH).unlink()

    report = validate_golden_fixture_pack(golden_dir)

    assert report.status == "incompatible"
    assert "artifact_missing" in _issue_codes(report)


def test_malformed_golden_json_produces_incompatible_report(tmp_path: Path) -> None:
    golden_dir = _copy_golden_pack(tmp_path)
    (golden_dir / PLAN_PATH).write_text("{not-json", encoding="utf-8")

    report = validate_golden_fixture_pack(golden_dir)

    assert report.status == "incompatible"
    assert "artifact_json_decode_error" in _issue_codes(report)


def test_contract_violation_in_golden_fixture_produces_incompatible_report(tmp_path: Path) -> None:
    golden_dir = _copy_golden_pack(tmp_path)
    plan_path = golden_dir / PLAN_PATH
    plan = _load_json(plan_path)
    plan.pop("plan_id")
    _write_json(plan_path, plan)

    report = validate_golden_fixture_pack(golden_dir)

    assert report.status == "incompatible"
    assert "contract_required_field_missing" in _issue_codes(report)


def test_golden_fixture_absolute_windows_path_is_flagged_and_redacted(tmp_path: Path) -> None:
    golden_dir = _copy_golden_pack(tmp_path)
    plan_path = golden_dir / PLAN_PATH
    plan = _load_json(plan_path)
    windows_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "trace.txt"])
    plan["notes"].append(f"leaky path {windows_path}")
    _write_json(plan_path, plan)

    report = validate_golden_fixture_pack(golden_dir)
    report_path, _ = write_model_evaluation_compatibility_report(report, tmp_path / "compatibility")
    text = report_path.read_text(encoding="utf-8")

    assert report.status == "incompatible"
    assert "absolute_path_leak_detected" in _issue_codes(report)
    assert windows_path not in text
    assert "<absolute_path>" in text


def test_golden_fixture_absolute_posix_path_is_flagged_and_redacted(tmp_path: Path) -> None:
    golden_dir = _copy_golden_pack(tmp_path)
    plan_path = golden_dir / PLAN_PATH
    plan = _load_json(plan_path)
    posix_path = "/home/example/outside_workspace/trace.txt"
    plan["notes"].append(f"leaky path {posix_path}")
    _write_json(plan_path, plan)

    report = validate_golden_fixture_pack(golden_dir)
    report_path, _ = write_model_evaluation_compatibility_report(report, tmp_path / "compatibility")
    text = report_path.read_text(encoding="utf-8")

    assert report.status == "incompatible"
    assert "absolute_path_leak_detected" in _issue_codes(report)
    assert posix_path not in text
    assert "<absolute_path>" in text


def test_secret_like_field_is_flagged_without_printing_value(tmp_path: Path) -> None:
    golden_dir = _copy_golden_pack(tmp_path)
    plan_path = golden_dir / PLAN_PATH
    plan = _load_json(plan_path)
    secret_value = "example-secret-value"
    plan["api_key"] = secret_value
    _write_json(plan_path, plan)

    report = validate_golden_fixture_pack(golden_dir)
    text = json.dumps(report.model_dump(mode="json"), ensure_ascii=False)

    assert report.status == "incompatible"
    assert "suspicious_secret_or_raw_field" in _issue_codes(report)
    assert secret_value not in text


def test_production_recommendation_wording_is_flagged(tmp_path: Path) -> None:
    golden_dir = _copy_golden_pack(tmp_path)
    plan_path = golden_dir / PLAN_PATH
    plan = _load_json(plan_path)
    plan["notes"].append("Recommended for production deployment.")
    _write_json(plan_path, plan)

    report = validate_golden_fixture_pack(golden_dir)

    assert report.status == "incompatible"
    assert "production_recommendation_wording_detected" in _issue_codes(report)


def test_workflow_output_generated_by_runner_compares_compatible(tmp_path: Path) -> None:
    workflow_dir = _workflow_output(tmp_path, include_optional=True)

    report = run_model_evaluation_compatibility_gate(
        golden_fixture_dir=GOLDEN_DIR,
        workflow_output_dir=workflow_dir,
    )

    assert report.status == "compatible"
    assert report.error_count == 0


def test_workflow_output_missing_required_plan_is_incompatible(tmp_path: Path) -> None:
    workflow_dir = _workflow_output(tmp_path, include_optional=True)
    (workflow_dir / PLAN_PATH).unlink()

    report = compare_workflow_output_to_golden_expectations(workflow_dir, GOLDEN_DIR)

    assert report.status == "incompatible"
    assert "workflow_required_artifact_missing" in _issue_codes(report)


def test_optional_normality_and_resource_absence_is_warning_not_crash(tmp_path: Path) -> None:
    workflow_dir = _workflow_output(tmp_path, include_optional=False)

    report = run_model_evaluation_compatibility_gate(
        golden_fixture_dir=GOLDEN_DIR,
        workflow_output_dir=workflow_dir,
    )

    assert report.status == "compatible_with_warnings"
    assert report.error_count == 0
    assert "workflow_optional_artifact_missing" in _issue_codes(report)
    assert not (workflow_dir / NORMALITY_PATH).exists()
    assert not (workflow_dir / RESOURCE_PATH).exists()


def test_compatibility_report_validates_against_contract() -> None:
    report = validate_golden_fixture_pack(GOLDEN_DIR)

    issues = validate_artifact_against_contract(
        report.model_dump(mode="json"),
        registry.MODEL_EVALUATION_COMPATIBILITY_REPORT,
    )

    assert issues == []


def test_dedicated_cli_writes_report(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = compatibility_gate_cli_main(
        [
            "--golden-fixture-dir",
            str(GOLDEN_DIR),
            "--output-dir",
            str(tmp_path / "compatibility"),
            "--compatibility-id",
            "dedicated_cli_compatibility",
            "--write-markdown-preview",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "compatible"
    assert payload["compatibility_id"] == "dedicated_cli_compatibility"
    assert payload["report_path"] == MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME
    assert (tmp_path / "compatibility" / MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME).is_file()
    assert (tmp_path / "compatibility" / MODEL_EVALUATION_COMPATIBILITY_PREVIEW_FILENAME).is_file()


def test_dedicated_cli_strict_returns_nonzero_on_warnings(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow_dir = _workflow_output(tmp_path, include_optional=False)
    capsys.readouterr()

    code = compatibility_gate_cli_main(
        [
            "--golden-fixture-dir",
            str(GOLDEN_DIR),
            "--workflow-output-dir",
            str(workflow_dir),
            "--output-dir",
            str(tmp_path / "compatibility"),
            "--strict",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 2
    assert payload["status"] == "compatible_with_warnings"
    assert payload["warning_count"] > 0


def test_unified_cli_compatibility_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = model_evaluation_cli_main(
        [
            "compatibility",
            "--golden-fixture-dir",
            str(GOLDEN_DIR),
            "--output-dir",
            str(tmp_path / "compatibility"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "compatible"
    assert payload["report_path"] == MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME


def test_unified_cli_version_includes_compatibility(capsys: pytest.CaptureFixture[str]) -> None:
    code = model_evaluation_cli_main(["version"])
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert "compatibility" in payload["supported_subcommands"]
    assert "model_evaluation_compatibility_report_v1" in payload["supported_schema_versions"]


def test_unified_cli_schema_full_for_compatibility_report(capsys: pytest.CaptureFixture[str]) -> None:
    code = model_evaluation_cli_main(
        [
            "schema",
            "--artifact-type",
            registry.MODEL_EVALUATION_COMPATIBILITY_REPORT,
            "--full",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["artifact_count"] == 1
    assert payload["artifacts"][0]["artifact_type"] == registry.MODEL_EVALUATION_COMPATIBILITY_REPORT
    assert payload["artifacts"][0]["required_fields"]


def test_no_reports_or_experiments_files_are_written(tmp_path: Path) -> None:
    code = compatibility_gate_cli_main(
        [
            "--golden-fixture-dir",
            str(GOLDEN_DIR),
            "--output-dir",
            str(tmp_path / "compatibility"),
        ]
    )

    assert code == 0
    assert not (PROJECT_ROOT / "reports" / MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME).exists()


def test_no_runtime_model_gguf_probe_browser_or_office_calls_are_made(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_text = Path.read_text
    original_import = __import__

    def forbid_gguf_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("unexpected GGUF read")
        return original_read_text(self, *args, **kwargs)

    def forbid_runtime_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("compatibility gate must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    report = validate_golden_fixture_pack(GOLDEN_DIR)

    assert report.status == "compatible"
