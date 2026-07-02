from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.agent.repeated_model_trials import (
    RepeatedTrialResult,
    RepeatedTrialSpec,
    aggregate_trials_for_model,
    build_repeated_trials_comparison,
    compare_repeated_trial_groups,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _artifact(
    root: Path,
    *,
    model_id: str,
    scenario_path: str = "configs/evaluation_scenarios/office_worker_basic_session.json",
    execution_success: bool = True,
    action_path: str = "docs/ai/model_registry.md",
) -> Path:
    root.mkdir(parents=True)
    error_type = None if execution_success else "file_not_found"
    steps = [
        {
            "step_index": 1,
            "registry_accepted": True,
            "role_compliant": True,
            "execution_attempted": True,
            "execution_success": execution_success,
            "error_type": error_type,
            "next_action": {
                "action": "read_file",
                "parameters": {"path": action_path},
                "reason": "Read a file.",
                "expected_result": "File is read.",
            },
        },
        {
            "step_index": 2,
            "registry_accepted": True,
            "role_compliant": True,
            "execution_attempted": True,
            "execution_success": execution_success,
            "error_type": error_type,
            "next_action": {
                "action": "read_file",
                "parameters": {"path": action_path},
                "reason": "Read the same file again.",
                "expected_result": "File is read.",
            },
        },
    ]
    attempts = [
        {
            "step_index": 1,
            "attempt_index": 0,
            "attempt_type": "initial",
            "parse_success": True,
            "parsed_action": steps[0]["next_action"],
            "validation_accepted": True,
            "validation_issues": [],
        },
        {
            "step_index": 2,
            "attempt_index": 0,
            "attempt_type": "initial",
            "parse_success": True,
            "parsed_action": steps[1]["next_action"],
            "validation_accepted": True,
            "validation_issues": [],
        },
    ]
    selected = [
        {"step_index": 1, "next_action": steps[0]["next_action"]},
        {"step_index": 2, "next_action": steps[1]["next_action"]},
    ]
    manifest = {
        "run_id": root.name,
        "scenario_id": "office_worker_basic_session_v1",
        "scenario_path": scenario_path,
        "model_id": model_id,
        "model_name": f"{model_id}.gguf",
        "model": {"model_id": model_id, "model_name": f"{model_id}.gguf"},
        "execute_actions": True,
        "repair": {"repair_enabled": True, "repair_attempts_per_step": 1},
        "step_count": 2,
        "stopped_reason": None if execution_success else "Reached max_consecutive_failures limit.",
    }
    activity = {
        "evaluator_id": "normal_activity_trajectory_evaluator_v1",
        "profile_id": "office_worker_normal_activity_v1",
        "score": 0.5 if execution_success else 0.0,
        "metrics": {
            "normal_activity_score": 0.5 if execution_success else 0.0,
            "diversity_score": 0.5,
            "repetition_score": 0.725,
            "sequence_coherence_score": 0.0,
            "history_usage_score": 1.0,
            "role_fit_score": 1.0,
            "repeated_action_count": 1,
            "repeated_same_parameters_count": 1,
        },
    }
    model_behavior = {
        "run_id": root.name,
        "scenario_id": "office_worker_basic_session_v1",
        "validation_metrics": {
            "total_steps": 2,
            "validation_failure_count": 0,
            "metadata": {
                "repair_summary": {
                    "initial_parse_success_count": 2,
                    "initial_validation_accept_count": 2,
                    "repair_attempt_count": 0,
                    "repair_validation_accept_count": 0,
                    "final_validation_accept_count": 2,
                    "unrecovered_failure_count": 0 if execution_success else 2,
                    "execution_success_count": 2 if execution_success else 0,
                }
            },
        },
        "behavioral_evaluation": activity,
    }
    resource = {
        "wall_time_ms": 1000.0,
        "per_step_latency_ms": [
            {"step_index": 1, "selection_latency_ms": 100.0, "total_step_latency_ms": 101.0},
            {"step_index": 2, "selection_latency_ms": 200.0, "total_step_latency_ms": 201.0},
        ],
    }
    _write_json(root / "manifest.json", manifest)
    _write_json(root / "activity_evaluation.json", activity)
    _write_json(root / "model_behavior_result.json", model_behavior)
    _write_json(root / "resource_summary.json", resource)
    _write_jsonl(root / "steps.jsonl", steps)
    _write_jsonl(root / "attempts.jsonl", attempts)
    _write_jsonl(root / "raw_model_outputs.jsonl", [{"step_index": 1}, {"step_index": 2}])
    _write_jsonl(root / "selected_actions.jsonl", selected)
    _write_jsonl(root / "validation_results.jsonl", [{"step_index": 1}, {"step_index": 2}])
    _write_jsonl(root / "execution_results.jsonl", [{"step_index": 1}, {"step_index": 2}])
    _write_jsonl(root / "history.jsonl", [{"step_index": 1}, {"step_index": 2}])
    _write_jsonl(root / "errors.jsonl", [] if execution_success else [{"error_type": "file_not_found"}])
    (root / "replay_commands.ps1").write_text(
        "python scripts\\run_agent_scenario.py --max-steps 5 --execute-actions\n",
        encoding="utf-8",
    )
    return root


def test_aggregate_metrics_compute_mean_std_correctly(tmp_path: Path) -> None:
    run_a = _artifact(tmp_path / "run_a", model_id="model_a", execution_success=True)
    run_b = _artifact(tmp_path / "run_b", model_id="model_a", execution_success=False)

    aggregate = aggregate_trials_for_model([run_a, run_b], model_id="model_a")

    assert aggregate.trial_count == 2
    assert aggregate.metrics["execution_success_rate"]["mean"] == 0.5
    assert aggregate.metrics["execution_success_rate"]["std"] == 0.5


def test_failed_trial_is_recorded_not_hidden(tmp_path: Path) -> None:
    failed = RepeatedTrialResult(
        spec=RepeatedTrialSpec(
            model_id="model_a",
            trial_id="trial_001",
            run_id="failed_run",
            artifact_path=str(tmp_path / "missing"),
        ),
        status="failed",
        error_message="runtime_not_ready",
    )
    comparison = build_repeated_trials_comparison(
        [
            type("Series", (), {"model_id": "model_a", "trials": [failed], "aggregate": None})(),
        ],
        comparison_id="failed_only",
    )

    assert comparison.status == "partial"
    assert comparison.trial_index[0]["status"] == "failed"
    assert comparison.trial_index[0]["error_message"] == "runtime_not_ready"


def test_common_failure_modes_aggregate_correctly(tmp_path: Path) -> None:
    run_a = _artifact(tmp_path / "run_a", model_id="model_a", execution_success=False)
    run_b = _artifact(tmp_path / "run_b", model_id="model_a", execution_success=False)

    aggregate = aggregate_trials_for_model([run_a, run_b], model_id="model_a")

    assert aggregate.common_failure_modes["file_not_found"] == 4


def test_protocol_mismatch_detected_if_artifacts_differ(tmp_path: Path) -> None:
    first = _artifact(tmp_path / "first", model_id="first")
    second = _artifact(tmp_path / "second", model_id="second", scenario_path="configs/other.json")

    comparison = compare_repeated_trial_groups([first], [second], comparison_id="mismatch")

    assert comparison.protocol_compatible is False


def test_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/run_repeated_model_trials.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--model-ids" in completed.stdout


def test_repeated_trial_cli_fake_mode_writes_root_artifacts(tmp_path: Path) -> None:
    out_root = tmp_path / "fake_repeated"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_repeated_model_trials.py",
            "--mode",
            "fake",
            "--models-config",
            "configs/evaluation_models.json",
            "--model-ids",
            "first_model,qwen2_5_3b_instruct_q4_k_m",
            "--scenario",
            "configs/evaluation_scenarios/office_worker_basic_session.json",
            "--out-root",
            str(out_root),
            "--label",
            "fake_repeated_test",
            "--trials",
            "1",
            "--max-steps",
            "1",
            "--repair-attempts",
            "1",
            "--execute-actions",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (out_root / "trial_index.json").exists()
    assert (out_root / "aggregate_metrics.json").exists()
    assert (out_root / "repeated_trials_comparison.md").exists()
    assert (out_root / "runs" / "first_model" / "trial_001" / "manifest.json").exists()
