from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.agent.model_behavior_comparison import (
    compare_model_runs,
    load_model_run_artifact,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _make_artifact(
    root: Path,
    *,
    model_id: str,
    scenario_path: str = "configs/evaluation_scenarios/office_worker_basic_session.json",
    max_steps: int = 5,
    execute_actions: bool = True,
    repair_attempts: int = 1,
    action_path: str = "docs/notes.txt",
    execution_success: bool = False,
) -> Path:
    root.mkdir(parents=True)
    steps = [
        {
            "step_index": 1,
            "registry_accepted": True,
            "role_compliant": True,
            "execution_attempted": execute_actions,
            "execution_success": execution_success,
            "error_type": None if execution_success else "file_not_found",
            "error_message": None if execution_success else f"File not found: {action_path}",
            "next_action": {
                "action": "read_file",
                "parameters": {"path": action_path},
                "reason": "Read notes.",
                "expected_result": "Notes are available.",
            },
        },
        {
            "step_index": 2,
            "registry_accepted": True,
            "role_compliant": True,
            "execution_attempted": execute_actions,
            "execution_success": execution_success,
            "error_type": None if execution_success else "file_not_found",
            "error_message": None if execution_success else f"File not found: {action_path}",
            "next_action": {
                "action": "read_file",
                "parameters": {"path": action_path},
                "reason": "Read notes again.",
                "expected_result": "Notes are available.",
            },
            "stop_reason": None if execution_success else "Reached max_consecutive_failures limit.",
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
        {
            "step_index": 1,
            "agent_id": "office_agent_1",
            "final_attempt_index": 0,
            "repaired": False,
            "next_action": steps[0]["next_action"],
        },
        {
            "step_index": 2,
            "agent_id": "office_agent_1",
            "final_attempt_index": 0,
            "repaired": False,
            "next_action": steps[1]["next_action"],
        },
    ]
    manifest = {
        "run_id": f"{model_id}_run",
        "scenario_id": "office_worker_basic_session_v1",
        "scenario_path": scenario_path,
        "mode": "local",
        "model_id": model_id,
        "model_name": f"{model_id}.gguf",
        "model": {
            "model_id": model_id,
            "model_name": f"{model_id}.gguf",
            "parameter_size": "test",
        },
        "execute_actions": execute_actions,
        "repair": {
            "repair_enabled": repair_attempts > 0,
            "repair_attempts_per_step": repair_attempts,
        },
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
        "run_id": f"{model_id}_run",
        "scenario_id": "office_worker_basic_session_v1",
        "model": {"model_id": model_id, "model_name": f"{model_id}.gguf"},
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
        "resource_start": {"process_rss_mb": 100.0, "system_cpu_percent": 10.0},
        "resource_end": {"process_rss_mb": 110.0, "system_cpu_percent": 15.0},
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
    _write_jsonl(
        root / "errors.jsonl",
        [] if execution_success else [{"step_index": 1, "error_type": "file_not_found"}],
    )
    (root / "replay_commands.ps1").write_text(
        f"python scripts\\run_agent_scenario.py --max-steps {max_steps} --execute-actions\n",
        encoding="utf-8",
    )
    return root


def test_load_complete_run_artifact(tmp_path: Path) -> None:
    artifact_path = _make_artifact(tmp_path / "run_a", model_id="model_a", execution_success=True)
    artifact = load_model_run_artifact(artifact_path)

    assert artifact.status == "complete"
    assert artifact.metrics["model_id"] == "model_a"
    assert artifact.metrics["execution_success_rate"] == 1.0


def test_missing_artifact_file_produces_warning_not_crash(tmp_path: Path) -> None:
    artifact_path = _make_artifact(tmp_path / "run_a", model_id="model_a")
    (artifact_path / "attempts.jsonl").unlink()

    artifact = load_model_run_artifact(artifact_path)

    assert artifact.status == "incomplete"
    assert any("missing_artifact: attempts.jsonl" in warning for warning in artifact.warnings)


def test_comparison_detects_compatible_protocols(tmp_path: Path) -> None:
    first = _make_artifact(tmp_path / "first", model_id="first")
    second = _make_artifact(tmp_path / "second", model_id="second")

    comparison = compare_model_runs(first, second)

    assert comparison.protocol_compatible is True


def test_comparison_detects_incompatible_protocols(tmp_path: Path) -> None:
    first = _make_artifact(tmp_path / "first", model_id="first")
    second = _make_artifact(tmp_path / "second", model_id="second", scenario_path="configs/other.json")

    comparison = compare_model_runs(first, second)

    assert comparison.protocol_compatible is False
    assert any(check["name"] == "scenario_path" and not check["compatible"] for check in comparison.protocol_checks)


def test_metrics_include_initial_and_final_validation_rates(tmp_path: Path) -> None:
    artifact_path = _make_artifact(tmp_path / "run_a", model_id="model_a")
    artifact = load_model_run_artifact(artifact_path)

    assert artifact.metrics["initial_validation_accept_rate"] == 1.0
    assert artifact.metrics["final_validation_accept_rate"] == 1.0


def test_execution_success_rate_computed_correctly(tmp_path: Path) -> None:
    failed = load_model_run_artifact(_make_artifact(tmp_path / "failed", model_id="failed", execution_success=False))
    passed = load_model_run_artifact(_make_artifact(tmp_path / "passed", model_id="passed", execution_success=True))

    assert failed.metrics["execution_success_rate"] == 0.0
    assert passed.metrics["execution_success_rate"] == 1.0


def test_repeated_same_action_parameters_counted_correctly(tmp_path: Path) -> None:
    artifact = load_model_run_artifact(_make_artifact(tmp_path / "run_a", model_id="model_a"))

    assert artifact.metrics["repeated_action_count"] == 1
    assert artifact.metrics["repeated_same_parameters_count"] == 1


def test_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/compare_model_behavior.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--first-run" in completed.stdout


def test_cli_writes_comparison_artifacts(tmp_path: Path) -> None:
    first = _make_artifact(tmp_path / "first", model_id="first", execution_success=True)
    second = _make_artifact(tmp_path / "second", model_id="second", execution_success=False)
    out_dir = tmp_path / "comparison"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/compare_model_behavior.py",
            "--first-run",
            str(first),
            "--second-run",
            str(second),
            "--out-dir",
            str(out_dir),
            "--label",
            "test_comparison",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (out_dir / "comparison.json").exists()
    assert (out_dir / "comparison.md").exists()
    payload = json.loads((out_dir / "comparison.json").read_text(encoding="utf-8"))
    assert payload["per_model"]["first"]["initial_validation_accept_rate"] == 1.0
