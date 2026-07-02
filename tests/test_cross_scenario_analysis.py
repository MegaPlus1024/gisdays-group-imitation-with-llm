from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.agent.cross_scenario_analysis import (
    ScenarioAnalysisInput,
    build_cross_scenario_analysis,
    load_scenario_behavioral_analysis,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: dict[str, object] | list[object]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _scenario(
    root: Path,
    scenario_id: str,
    *,
    first_exec: float,
    qwen_failure: str,
) -> ScenarioAnalysisInput:
    analysis = root / "analysis" / scenario_id
    repeated = root / "repeated" / scenario_id
    first_failures = {"validation_failed_after_repair": 3}
    qwen_failures = {qwen_failure: 3}
    aggregate_metrics = {
        "first_model": _aggregate("first_model", 0.0, first_exec, 0.4 * first_exec, 0.5, 700.0, first_failures),
        "qwen2_5_3b_instruct_q4_k_m": _aggregate("qwen2_5_3b_instruct_q4_k_m", 1.0, 0.0, 0.0, 0.5, 500.0, qwen_failures),
    }
    _write_json(repeated / "aggregate_metrics.json", aggregate_metrics)
    _write_json(repeated / "failure_modes.json", {
        "first_model": {"common_failure_modes": first_failures, "most_common_action_parameters": []},
        "qwen2_5_3b_instruct_q4_k_m": {"common_failure_modes": qwen_failures, "most_common_action_parameters": []},
    })
    _write_json(repeated / "repeated_trials_comparison.json", {"status": "complete"})
    _write_json(repeated / "trial_index.json", [])
    _write_json(analysis / "consolidated_behavioral_analysis.json", {
        "analysis_id": f"{scenario_id}_analysis",
        "model_ids": ["first_model", "qwen2_5_3b_instruct_q4_k_m"],
        "role_compliance": {
            "first_model": {"verdict": "acceptable"},
            "qwen2_5_3b_instruct_q4_k_m": {"verdict": "strong"},
        },
        "coherence_history_usage": {
            "first_model": {"verdict": "failed"},
            "qwen2_5_3b_instruct_q4_k_m": {"verdict": "weak"},
        },
        "diversity_template_behavior": {
            "first_model": {"verdict": "template_like", "template_behavior_flags": ["repeated_same_action"]},
            "qwen2_5_3b_instruct_q4_k_m": {"verdict": "template_like", "template_behavior_flags": ["repeated_same_action"]},
        },
        "failure_modes": {
            "first_model": {"validation_failed_after_repair_count": 3, "repair_attempt_count": 3},
            "qwen2_5_3b_instruct_q4_k_m": {"execution_error_count": 3},
        },
    })
    return ScenarioAnalysisInput(
        scenario_id=scenario_id,
        analysis_path=str(analysis),
        repeated_trials_path=str(repeated),
    )


def _aggregate(
    model_id: str,
    validity: float,
    execution: float,
    normal: float,
    diversity: float,
    latency: float,
    failures: dict[str, int],
) -> dict[str, object]:
    return {
        "model_id": model_id,
        "trial_count": 3,
        "completed_trial_count": 3,
        "failed_trial_count": 0,
        "metrics": {
            "initial_validation_accept_rate": {"mean": validity},
            "final_validation_accept_rate": {"mean": validity},
            "execution_success_rate": {"mean": execution},
            "normal_activity_score": {"mean": normal},
            "diversity_score": {"mean": diversity},
            "repetition_score": {"mean": 0.7},
            "history_usage_score": {"mean": 0.5},
            "sequence_coherence_score": {"mean": 0.0},
            "average_selection_latency_ms": {"mean": latency},
            "average_total_step_latency_ms": {"mean": latency + 1.0},
        },
        "common_failure_modes": failures,
        "most_common_action_parameters": [{"action_parameters": "read_file:x", "count": 3}],
    }


def test_loading_two_scenario_summaries_from_temp_fixtures(tmp_path: Path) -> None:
    first = _scenario(tmp_path, "office", first_exec=1.0, qwen_failure="file_not_found")
    second = _scenario(tmp_path, "developer", first_exec=0.0, qwen_failure="unsafe_path")

    result = build_cross_scenario_analysis([first, second], analysis_id="test")

    assert len(result.scenario_model_summaries) == 4
    assert result.model_aggregates["first_model"].scenario_count == 2


def test_aggregate_metrics_across_scenarios(tmp_path: Path) -> None:
    first = _scenario(tmp_path, "office", first_exec=1.0, qwen_failure="file_not_found")
    second = _scenario(tmp_path, "developer", first_exec=0.0, qwen_failure="unsafe_path")

    result = build_cross_scenario_analysis([first, second])

    assert result.model_aggregates["first_model"].mean_execution_success_rate_across_scenarios == 0.5
    assert result.model_aggregates["qwen2_5_3b_instruct_q4_k_m"].mean_initial_validation_accept_rate_across_scenarios == 1.0


def test_metric_winners_computed(tmp_path: Path) -> None:
    result = build_cross_scenario_analysis([
        _scenario(tmp_path, "office", first_exec=1.0, qwen_failure="file_not_found"),
        _scenario(tmp_path, "developer", first_exec=0.0, qwen_failure="unsafe_path"),
    ])

    winners = {item.metric: item.winner for item in result.metric_winners}
    assert winners["contract_validity"] == "qwen2_5_3b_instruct_q4_k_m"
    assert winners["execution_success"] == "first_model"


def test_stable_and_scenario_specific_failure_patterns(tmp_path: Path) -> None:
    result = build_cross_scenario_analysis([
        _scenario(tmp_path, "office", first_exec=1.0, qwen_failure="file_not_found"),
        _scenario(tmp_path, "developer", first_exec=0.0, qwen_failure="unsafe_path"),
    ])

    assert result.failure_patterns["first_model"].stable_failure_patterns["validation_failed_after_repair"] == 6
    assert "office" in result.failure_patterns["qwen2_5_3b_instruct_q4_k_m"].scenario_specific_failure_patterns


def test_scenario_sensitivity_calculation(tmp_path: Path) -> None:
    result = build_cross_scenario_analysis([
        _scenario(tmp_path, "office", first_exec=1.0, qwen_failure="file_not_found"),
        _scenario(tmp_path, "developer", first_exec=0.0, qwen_failure="unsafe_path"),
    ])

    assert result.scenario_sensitivity_report["first_model"]["verdict"] == "high"
    assert result.scenario_sensitivity_report["qwen2_5_3b_instruct_q4_k_m"]["verdict"] == "medium"


def test_recommendation_readiness_not_ready(tmp_path: Path) -> None:
    result = build_cross_scenario_analysis([
        _scenario(tmp_path, "office", first_exec=1.0, qwen_failure="file_not_found"),
        _scenario(tmp_path, "developer", first_exec=0.0, qwen_failure="unsafe_path"),
    ])

    assert result.recommendation_readiness["recommendation_readiness_status"] == "not_ready_for_final_recommendation"
    assert result.recommendation_readiness["criteria"]["multi_agent_capacity_estimate"] is False


def test_missing_scenario_artifact_fails_clearly(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError):
        load_scenario_behavioral_analysis(tmp_path / "missing")


def test_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/compare_cross_scenario_behavior.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    assert completed.returncode == 0
    assert "--scenario-analysis" in completed.stdout


def test_cli_writes_cross_scenario_outputs(tmp_path: Path) -> None:
    office = _scenario(tmp_path, "office", first_exec=1.0, qwen_failure="file_not_found")
    developer = _scenario(tmp_path, "developer", first_exec=0.0, qwen_failure="unsafe_path")
    out = tmp_path / "out"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/compare_cross_scenario_behavior.py",
            "--scenario-analysis",
            f"{office.scenario_id}={office.analysis_path}={office.repeated_trials_path}",
            "--scenario-analysis",
            f"{developer.scenario_id}={developer.analysis_path}={developer.repeated_trials_path}",
            "--out-dir",
            str(out),
            "--label",
            "test_cross",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (out / "cross_scenario_analysis.json").exists()
    assert (out / "cross_scenario_analysis.md").exists()
