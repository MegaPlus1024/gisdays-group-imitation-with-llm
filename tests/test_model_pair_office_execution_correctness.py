from __future__ import annotations

import builtins
import json
from pathlib import Path
from typing import Any

import pytest

from scripts.score_office_execution_correctness import main as score_cli_main
from src.agent.model_pair_office_execution_correctness import (
    OFFICE_EXECUTION_CORRECTNESS_SUMMARY_SCHEMA_VERSION,
    score_office_execution_correctness,
)


def _trial(*, execution_success: bool = True, path: str | None = None) -> dict[str, Any]:
    output_path = path or "artifacts/single_trial_runs/phase_test/pipeline/workspace/office_outputs/report.docx"
    return {
        "trial_id": "trial_001",
        "scenario_id": "office_document_file_workflow_basic_v1",
        "pair_id": "second_model__to__first_model",
        "status": "succeeded",
        "task_success": True,
        "artifact_refs": ["artifacts/single_trial_runs/phase_test/pipeline"],
        "group_history": [
            {
                "task_id": "t1",
                "agent_id": "document_summary_agent",
                "action": "office_append_docx_section",
                "metadata": {
                    "validation_accepted": True,
                    "execution_attempted": True,
                    "execution_success": execution_success,
                    "precreate_metadata": {
                        "path": output_path,
                    },
                },
            },
            {
                "task_id": "t2",
                "agent_id": "document_tracker_agent",
                "action": "office_append_docx_section",
                "metadata": {
                    "validation_accepted": True,
                    "execution_attempted": True,
                    "execution_success": execution_success,
                    "precreate_metadata": {
                        "path": output_path.replace("report.docx", "tracker.docx"),
                    },
                },
            },
        ],
    }


def _office_summary(*, exists: bool = True, readable: bool = True, path: str | None = None) -> dict[str, Any]:
    first_path = path or "artifacts/single_trial_runs/phase_test/pipeline/workspace/office_outputs/report.docx"
    second_path = first_path.replace("report.docx", "tracker.docx")
    artifacts = [
        {"path": first_path, "exists": exists, "readable": readable, "extension": ".docx"},
        {"path": second_path, "exists": exists, "readable": readable, "extension": ".docx"},
    ]
    return {
        "schema_version": "office_execution_artifact_summary_v1",
        "run_id": "phase_test",
        "trial_id": "trial_001",
        "artifact_count": 2,
        "readable_count": sum(1 for row in artifacts if row["readable"]),
        "missing_count": sum(1 for row in artifacts if not row["exists"]),
        "artifacts": artifacts,
        "no_runtime_execution": True,
    }


def test_scores_successful_office_execution_with_readable_artifacts() -> None:
    summary = score_office_execution_correctness(_trial(), _office_summary())

    assert summary["schema_version"] == OFFICE_EXECUTION_CORRECTNESS_SUMMARY_SCHEMA_VERSION
    assert summary["correctness_score"] == 1.0
    assert summary["execution_correctness_pass"] is True
    assert summary["artifact_correctness_pass"] is True
    assert summary["criteria"] == {
        "trial_succeeded": True,
        "all_steps_validated": True,
        "all_execution_attempted": True,
        "all_execution_succeeded": True,
        "all_office_artifacts_exist": True,
        "all_office_artifacts_readable": True,
    }
    assert "semantic_document_quality_not_scored" in summary["notes"]


def test_scores_lower_when_artifact_is_missing() -> None:
    summary = score_office_execution_correctness(_trial(), _office_summary(exists=False, readable=False))

    assert 0 <= summary["correctness_score"] < 1.0
    assert summary["artifact_correctness_pass"] is False
    assert summary["criteria"]["all_office_artifacts_exist"] is False
    assert summary["criteria"]["all_office_artifacts_readable"] is False


def test_scores_lower_when_execution_failed() -> None:
    summary = score_office_execution_correctness(_trial(execution_success=False), _office_summary())

    assert 0 <= summary["correctness_score"] < 1.0
    assert summary["execution_correctness_pass"] is False
    assert summary["criteria"]["all_execution_succeeded"] is False


def test_scoring_script_writes_summary_without_absolute_paths(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    trial_path = tmp_path / "model_pair_single_trial_result.json"
    office_summary_path = tmp_path / "office_execution_artifact_summary.json"
    output_path = tmp_path / "office_execution_correctness_summary.json"
    trial_path.write_text(json.dumps(_trial(), ensure_ascii=False), encoding="utf-8")
    office_summary_path.write_text(json.dumps(_office_summary(), ensure_ascii=False), encoding="utf-8")

    code = score_cli_main(
        [
            "--trial-result",
            str(trial_path),
            "--office-artifact-summary",
            str(office_summary_path),
            "--output",
            str(output_path),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)
    summary = json.loads(output_path.read_text(encoding="utf-8"))
    encoded = json.dumps(summary, ensure_ascii=False)

    assert code == 0
    assert stdout["status"] == "ok"
    assert stdout["correctness_score"] == 1.0
    assert summary["correctness_score"] == 1.0
    assert str(tmp_path) not in encoded
    assert ":\\" not in encoded


def test_scoring_script_invalid_input_returns_controlled_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_path = tmp_path / "office_execution_correctness_summary.json"

    code = score_cli_main(
        [
            "--trial-result",
            str(tmp_path / "missing.json"),
            "--office-artifact-summary",
            str(tmp_path / "office_execution_artifact_summary.json"),
            "--output",
            str(output_path),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)

    assert code == 2
    assert stdout["status"] == "invalid_input"
    assert stdout["error"] == "trial_result_file_missing"
    assert not output_path.exists()


def test_scoring_does_not_import_runtime_clients(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden_prefixes = ("httpx", "openai", "playwright", "win32com", "pythoncom", "uno", "llama_cpp")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden_prefixes):
            raise AssertionError(f"Forbidden runtime import attempted: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = score_office_execution_correctness(_trial(), _office_summary())

    assert summary["no_runtime_execution"] is True
