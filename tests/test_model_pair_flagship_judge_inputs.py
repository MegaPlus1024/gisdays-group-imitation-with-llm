from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.model_pair_flagship_judge_inputs import (
    FLAGSHIP_JUDGE_INPUT_SCHEMA_VERSION,
    build_flagship_judge_input_records,
)


def _write_json(path: Path, payload: dict[str, Any]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_repeat(root: Path, run_id: str, repeat: int, *, excerpt: str | None = None) -> Path:
    run_dir = root / "artifacts" / "single_trial_runs" / run_id
    artifact_path = f"artifacts/single_trial_runs/{run_id}/pipeline/workspace/office_outputs/report.docx"
    _write_json(
        run_dir / "model_pair_single_trial_result.json",
        {
            "trial_id": f"office_document_file_workflow_basic_v1__second_model__to__first_model__r{repeat:02d}",
            "scenario_id": "office_document_file_workflow_basic_v1",
            "pair_id": "second_model__to__first_model",
            "orchestrator_model_id": "second_model",
            "executor_model_id": "first_model",
            "status": "succeeded",
            "task_success": True,
            "group_history": [
                {
                    "task_id": "t1",
                    "agent_id": "document_summary_agent",
                    "action": "office_append_docx_section",
                    "status": "success",
                    "metadata": {
                        "validation_accepted": True,
                        "execution_attempted": True,
                        "execution_success": True,
                        "precreate_metadata": {"path": artifact_path, "precreate_success": True},
                    },
                }
            ],
            "warnings": [],
        },
    )
    _write_json(
        run_dir / "office_execution_artifact_summary.json",
        {
            "run_id": run_id,
            "trial_id": f"office_document_file_workflow_basic_v1__second_model__to__first_model__r{repeat:02d}",
            "artifact_count": 1,
            "readable_count": 1,
            "artifacts": [
                {
                    "task_id": "t1",
                    "agent_id": "document_summary_agent",
                    "action": "office_append_docx_section",
                    "extension": ".docx",
                    "path": artifact_path,
                    "exists": True,
                    "readable": True,
                    "paragraph_count": 2,
                    "safe_text_excerpt": excerpt or "Short safe excerpt.",
                }
            ],
            "warnings": [],
            "no_runtime_execution": True,
        },
    )
    _write_json(
        run_dir / "office_execution_correctness_summary.json",
        {
            "run_id": run_id,
            "correctness_score": 1.0,
            "execution_correctness_pass": True,
            "artifact_correctness_pass": True,
            "warnings": [],
            "no_runtime_execution": True,
        },
    )
    _write_json(
        run_dir / "matrix_adapters" / "matrix_run_adapter_summary.json",
        {
            "normality_input_count": 1,
            "resource_observation_count": 1,
            "warnings": [],
            "no_runtime_execution": True,
        },
    )
    return run_dir


def test_judge_input_builder_creates_one_record_per_repeat(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dirs = [
        _write_repeat(tmp_path, "phase_8_26_mini_matrix_r1", 1),
        _write_repeat(tmp_path, "phase_8_26_mini_matrix_r2", 2),
    ]

    records = build_flagship_judge_input_records(run_dirs, summary_id="phase_8_26_mini_matrix_r2")

    assert [record["schema_version"] for record in records] == [FLAGSHIP_JUDGE_INPUT_SCHEMA_VERSION] * 2
    assert [record["repeat_index"] for record in records] == [1, 2]
    assert records[0]["judge_role"] == "external_measurement_instrument"
    assert records[0]["evaluated_models"] == {
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
    }


def test_judge_input_includes_deterministic_metrics_without_rescoring_target(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = _write_repeat(tmp_path, "phase_8_26_mini_matrix_r1", 1)

    record = build_flagship_judge_input_records([run_dir], summary_id="phase_8_26_mini_matrix_r1")[0]

    assert record["deterministic_metrics"]["trial_status"] == "succeeded"
    assert record["deterministic_metrics"]["execution_success_count"] == 1
    assert record["deterministic_metrics"]["execution_correctness_score"] == 1.0
    assert "judge_should_score_semantic_quality_and_normality_only" in record["notes"]
    assert "execution_correctness" not in record["judge_dimensions"]


def test_judge_input_includes_bounded_artifact_excerpts_and_relative_paths_only(
    tmp_path: Path,
    monkeypatch,
) -> None:
    monkeypatch.chdir(tmp_path)
    long_excerpt = "A" * 700
    run_dir = _write_repeat(tmp_path, "phase_8_26_mini_matrix_r1", 1, excerpt=long_excerpt)

    record = build_flagship_judge_input_records([run_dir], summary_id="phase_8_26_mini_matrix_r1")[0]
    encoded = json.dumps(record, ensure_ascii=False)

    assert record["artifacts"][0]["safe_text_excerpt"].endswith("...[truncated]")
    assert len(record["artifacts"][0]["safe_text_excerpt"]) < len(long_excerpt)
    assert record["artifacts"][0]["path"].startswith("artifacts/single_trial_runs/")
    assert str(tmp_path) not in encoded
    assert ":\\" not in encoded


def test_judge_input_excludes_raw_prompts_and_responses(tmp_path: Path, monkeypatch) -> None:
    monkeypatch.chdir(tmp_path)
    run_dir = _write_repeat(tmp_path, "phase_8_26_mini_matrix_r1", 1)

    record = build_flagship_judge_input_records([run_dir], summary_id="phase_8_26_mini_matrix_r1")[0]
    encoded = json.dumps(record, ensure_ascii=False).lower()

    assert "raw_prompt" not in encoded
    assert "raw_response" not in encoded
    assert "prompt_text" not in encoded
