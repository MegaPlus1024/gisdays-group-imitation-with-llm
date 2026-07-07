from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_pair_mini_matrix_aggregation import aggregate_mini_matrix_results


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _repeat(run_dir: Path, *, run_id: str, score: float | None = 1.0) -> None:
    _write_json(
        run_dir / "model_pair_single_trial_result.json",
        {
            "trial_id": f"office_document_file_workflow_basic_v1__second_model__to__first_model__{run_id[-2:]}",
            "scenario_id": "office_document_file_workflow_basic_v1",
            "pair_id": "second_model__to__first_model",
            "status": "succeeded",
            "task_success": True,
            "group_history": [
                {"metadata": {"execution_attempted": True, "execution_success": True}},
                {"metadata": {"execution_attempted": True, "execution_success": True}},
            ],
            "warnings": [],
        },
    )
    _write_json(
        run_dir / "model_pair_single_trial_matrix_summary.json",
        {
            "run_id": run_id,
            "warnings": [],
        },
    )
    _write_json(
        run_dir / "office_execution_artifact_summary.json",
        {
            "run_id": run_id,
            "artifact_count": 2,
            "readable_count": 2,
            "warnings": [],
        },
    )
    _write_json(
        run_dir / "matrix_adapters" / "matrix_run_adapter_summary.json",
        {
            "normality_input_count": 1,
            "resource_observation_count": 1,
            "warnings": [],
        },
    )
    if score is not None:
        _write_json(
            run_dir / "office_execution_correctness_summary.json",
            {
                "schema_version": "office_execution_correctness_summary_v1",
                "run_id": run_id,
                "correctness_score": score,
                "criteria": {
                    "trial_succeeded": True,
                    "all_steps_validated": True,
                    "all_execution_attempted": True,
                    "all_execution_succeeded": score == 1.0,
                    "all_office_artifacts_exist": True,
                    "all_office_artifacts_readable": True,
                },
                "execution_correctness_pass": score == 1.0,
                "artifact_correctness_pass": True,
                "no_runtime_execution": True,
            },
        )


def test_aggregates_office_execution_correctness_summaries(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    first = Path("artifacts/single_trial_runs/phase_8_26_mini_matrix_r1")
    second = Path("artifacts/single_trial_runs/phase_8_26_mini_matrix_r2")
    _repeat(first, run_id="phase_8_26_mini_matrix_r1", score=1.0)
    _repeat(second, run_id="phase_8_26_mini_matrix_r2", score=0.5)

    summary = aggregate_mini_matrix_results([first, second], summary_id="phase_8_26_mini_matrix_r2")
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["correctness_score_count"] == 2
    assert summary["mean_correctness_score"] == 0.75
    assert summary["execution_correctness_pass_count"] == 1
    assert summary["artifact_correctness_pass_count"] == 2
    assert summary["repeats"][0]["correctness_score"] == 1.0
    assert summary["repeats"][0]["correctness_summary_path"].endswith(
        "office_execution_correctness_summary.json"
    )
    assert summary["repeats"][0]["correctness_criteria"]["all_office_artifacts_readable"] is True
    assert str(tmp_path) not in encoded


def test_aggregate_remains_backward_compatible_without_correctness_summary(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = Path("artifacts/single_trial_runs/phase_8_26_mini_matrix_r1")
    _repeat(run_dir, run_id="phase_8_26_mini_matrix_r1", score=None)

    summary = aggregate_mini_matrix_results([run_dir])

    assert summary["correctness_score_count"] == 0
    assert "mean_correctness_score" not in summary
    assert "correctness_summary_path" not in summary["repeats"][0]
    assert summary["succeeded_count"] == 1
    assert summary["office_artifact_count"] == 2
