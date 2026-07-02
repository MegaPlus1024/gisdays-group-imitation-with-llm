from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.agent.consolidated_behavioral_analysis import (
    analyze_coherence_history_usage,
    analyze_diversity_template_behavior,
    analyze_failure_modes,
    analyze_resource_latency,
    analyze_role_compliance,
    build_consolidated_behavioral_analysis,
    load_repeated_trials_root,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict[str, object]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _trial(root: Path, model_id: str, trial_id: str, *, failure: str) -> Path:
    path = root / "runs" / model_id / trial_id
    path.mkdir(parents=True)
    if failure == "file_not_found":
        action = {"action": "read_file", "parameters": {"path": "docs/notes.txt"}, "reason": "Try again after previous failure."}
        steps = [
            {"step_index": 1, "next_action": action, "registry_accepted": True, "role_compliant": True, "execution_attempted": True, "execution_success": False, "error_type": "file_not_found", "error_message": "File not found"},
            {"step_index": 2, "next_action": action, "registry_accepted": True, "role_compliant": True, "execution_attempted": True, "execution_success": False, "error_type": "file_not_found", "error_message": "File not found", "stop_reason": "Reached max_consecutive_failures limit."},
        ]
        attempts = [
            {"step_index": 1, "attempt_index": 0, "attempt_type": "initial", "parse_success": True, "parsed_action": action, "validation_accepted": True, "validation_issues": []},
            {"step_index": 2, "attempt_index": 0, "attempt_type": "initial", "parse_success": True, "parsed_action": action, "validation_accepted": True, "validation_issues": []},
        ]
        score = 0.0
        stop = "Reached max_consecutive_failures limit."
        repair = {"initial_parse_success_count": 2, "initial_validation_accept_count": 2, "repair_attempt_count": 0, "repair_validation_accept_count": 0, "final_validation_accept_count": 2, "unrecovered_failure_count": 2, "execution_success_count": 0}
    else:
        good = {"action": "read_file", "parameters": {"path": "docs/ai/model_registry.md"}, "reason": "Read registry."}
        bad = {"action": "create_file", "parameters": {"path": "docs/ai/model_registry.md"}, "reason": "Write outside workspace."}
        steps = [
            {"step_index": 1, "next_action": good, "registry_accepted": True, "role_compliant": True, "execution_attempted": True, "execution_success": True, "error_type": None},
            {"step_index": 2, "next_action": bad, "registry_accepted": False, "role_compliant": True, "execution_attempted": False, "execution_success": None, "error_type": "validation_failed_after_repair", "stop_reason": "validation_failed_after_repair"},
        ]
        attempts = [
            {"step_index": 1, "attempt_index": 0, "attempt_type": "initial", "parse_success": True, "parsed_action": {"action": "read_file", "parameters": {}}, "validation_accepted": False, "validation_issues": [{"code": "missing_required_parameter"}]},
            {"step_index": 1, "attempt_index": 1, "attempt_type": "repair", "parse_success": True, "parsed_action": good, "validation_accepted": True, "validation_issues": []},
            {"step_index": 2, "attempt_index": 0, "attempt_type": "initial", "parse_success": True, "parsed_action": bad, "validation_accepted": False, "validation_issues": [{"code": "write_path_outside_workspace"}]},
            {"step_index": 2, "attempt_index": 1, "attempt_type": "repair", "parse_success": True, "parsed_action": bad, "validation_accepted": False, "validation_issues": [{"code": "write_path_outside_workspace"}]},
        ]
        score = 0.43
        stop = "validation_failed_after_repair"
        repair = {"initial_parse_success_count": 2, "initial_validation_accept_count": 0, "repair_attempt_count": 2, "repair_validation_accept_count": 1, "final_validation_accept_count": 1, "unrecovered_failure_count": 1, "execution_success_count": 1}

    selected = [{"step_index": i + 1, "next_action": step["next_action"]} for i, step in enumerate(steps) if step.get("registry_accepted")]
    _write_json(path / "manifest.json", {
        "run_id": f"{model_id}_{trial_id}",
        "scenario_path": "configs/evaluation_scenarios/office_worker_basic_session.json",
        "model": {"model_id": model_id, "model_name": f"{model_id}.gguf"},
        "execute_actions": True,
        "repair": {"repair_enabled": True, "repair_attempts_per_step": 1},
        "step_count": len(steps),
        "stopped_reason": stop,
    })
    _write_json(path / "activity_evaluation.json", {"evaluator_id": "normal_activity_trajectory_evaluator_v1", "profile_id": "office_worker_normal_activity_v1", "score": score, "metrics": {"normal_activity_score": score, "role_fit_score": 1.0, "diversity_score": 0.5, "repetition_score": 0.725, "sequence_coherence_score": 0.0, "history_usage_score": 1.0 if failure == "file_not_found" else 0.0, "repeated_action_count": 1, "repeated_same_parameters_count": 1, "atypical_action_count": 0, "forbidden_for_normality_count": 0}})
    _write_json(path / "model_behavior_result.json", {"validation_metrics": {"total_steps": len(steps), "validation_failure_count": 0, "metadata": {"repair_summary": repair}}, "selected_actions": []})
    _write_json(path / "resource_summary.json", {"wall_time_ms": 1000.0, "resource_start": {"process_rss_mb": 100.0, "system_cpu_percent": 1.0}, "resource_end": {"process_rss_mb": 110.0, "system_cpu_percent": 2.0}, "per_step_latency_ms": [{"selection_latency_ms": 100.0, "total_step_latency_ms": 101.0}, {"selection_latency_ms": 200.0, "total_step_latency_ms": 201.0}]})
    _write_jsonl(path / "steps.jsonl", steps)
    _write_jsonl(path / "attempts.jsonl", attempts)
    _write_jsonl(path / "selected_actions.jsonl", selected)
    for name in ["raw_model_outputs.jsonl", "validation_results.jsonl", "execution_results.jsonl", "history.jsonl", "errors.jsonl"]:
        _write_jsonl(path / name, [])
    (path / "replay_commands.ps1").write_text("python scripts\\run_agent_scenario.py --max-steps 5\n", encoding="utf-8")
    return path


def _root(tmp_path: Path) -> Path:
    root = tmp_path / "repeated"
    _trial(root, "first_model", "trial_001", failure="validation_failed_after_repair")
    _trial(root, "second_model", "trial_001", failure="file_not_found")
    return root


def test_load_repeated_trials_root_from_temp_fixture(tmp_path: Path) -> None:
    root = _root(tmp_path)
    loaded = load_repeated_trials_root(root)
    assert sorted(loaded) == ["first_model", "second_model"]


def test_role_compliance_analysis_computes_action_family_distribution(tmp_path: Path) -> None:
    trials = load_repeated_trials_root(_root(tmp_path))["first_model"].trials
    analysis = analyze_role_compliance(trials)
    assert analysis.action_family_distribution["file"] >= 1


def test_coherence_analysis_detects_repeated_failed_action_parameters(tmp_path: Path) -> None:
    trials = load_repeated_trials_root(_root(tmp_path))["second_model"].trials
    analysis = analyze_coherence_history_usage(trials)
    assert analysis.repeated_failed_action_count == 1
    assert analysis.repeats_previous_failed_path_count == 1


def test_diversity_analysis_detects_template_like_behavior(tmp_path: Path) -> None:
    trials = load_repeated_trials_root(_root(tmp_path))["second_model"].trials
    analysis = analyze_diversity_template_behavior(trials)
    assert "repeated_same_action" in analysis.template_behavior_flags


def test_failure_mode_analysis_aggregates_file_not_found_and_repair_failure(tmp_path: Path) -> None:
    loaded = load_repeated_trials_root(_root(tmp_path))
    second = analyze_failure_modes(loaded["second_model"].trials)
    first = analyze_failure_modes(loaded["first_model"].trials)
    assert second.file_not_found_count == 2
    assert first.validation_failed_after_repair_count == 1


def test_resource_analysis_computes_mean_latency(tmp_path: Path) -> None:
    trials = load_repeated_trials_root(_root(tmp_path))["second_model"].trials
    analysis = analyze_resource_latency(trials)
    assert analysis.selection_latency_ms["mean"] == 150.0


def test_missing_optional_artifact_produces_warning_not_crash(tmp_path: Path) -> None:
    root = _root(tmp_path)
    (root / "runs" / "first_model" / "trial_001" / "attempts.jsonl").unlink()
    analysis = build_consolidated_behavioral_analysis(root)
    assert analysis.warnings


def test_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/analyze_behavioral_trials.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "--trials-root" in completed.stdout


def test_cli_writes_consolidated_outputs(tmp_path: Path) -> None:
    root = _root(tmp_path)
    out = tmp_path / "analysis"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/analyze_behavioral_trials.py",
            "--trials-root",
            str(root),
            "--out-dir",
            str(out),
            "--label",
            "analysis_test",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0, completed.stderr
    assert (out / "consolidated_behavioral_analysis.json").exists()
    assert (out / "consolidated_behavioral_analysis.md").exists()
