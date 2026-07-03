from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.agent.repeated_orchestrator_executor_trials import (
    RepeatedGroupRunConfig,
    aggregate_group_trials,
    run_repeated_group_trials,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "configs/multi_agent_scenarios/office_developer_group_basic.json"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _json_list(path: Path) -> list[dict[str, object]]:
    return json.loads(path.read_text(encoding="utf-8"))


def _config(tmp_path: Path, **overrides: object) -> RepeatedGroupRunConfig:
    payload: dict[str, object] = {
        "project_root": PROJECT_ROOT,
        "mode": "fake",
        "models_config_path": "configs/evaluation_models.json",
        "scenario_path": SCENARIO,
        "out_root": str(tmp_path / "repeated_group"),
        "label": "test_repeated_group",
        "trials": 2,
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
        "max_group_steps": 1,
        "max_steps_per_agent": 1,
        "orchestrator_repair_attempts": 1,
        "repair_attempts": 1,
        "execute_actions": False,
        "continue_on_trial_failure": False,
        "force": True,
    }
    payload.update(overrides)
    return RepeatedGroupRunConfig.model_validate(payload)


def test_fake_repeated_group_trials_create_trial_folders_and_reports(tmp_path: Path) -> None:
    result = run_repeated_group_trials(_config(tmp_path))
    out_root = tmp_path / "repeated_group"

    assert result.status == "complete"
    assert result.aggregate.trial_count == 2
    assert result.aggregate.failed_trial_count == 0
    for index in [1, 2]:
        trial_dir = out_root / "runs" / f"trial_{index:03d}"
        assert (trial_dir / "manifest.json").exists()
        assert (trial_dir / "per_agent_attempts.jsonl").exists()
        assert (trial_dir / "pair_quality_metrics.json").exists()
    for name in [
        "trial_index.json",
        "trial_index.csv",
        "aggregate_group_metrics.json",
        "aggregate_group_metrics.csv",
        "failure_modes.json",
        "action_patterns.json",
        "repeated_group_trials_report.md",
        "README.md",
        "replay_commands.ps1",
    ]:
        assert (out_root / name).exists(), name


def test_aggregate_group_trials_computes_mean_and_std_pair_quality(tmp_path: Path) -> None:
    result = run_repeated_group_trials(_config(tmp_path))
    out_root = tmp_path / "repeated_group"

    aggregate = aggregate_group_trials([out_root / "runs" / "trial_001", out_root / "runs" / "trial_002"])

    assert aggregate.trial_count == 2
    assert aggregate.mean_pair_quality_score == result.aggregate.mean_pair_quality_score
    assert aggregate.std_pair_quality_score == 0.0
    assert aggregate.mean_execution_success_rate == 0.0


def test_failed_trial_is_recorded_and_does_not_disappear_with_continue(tmp_path: Path) -> None:
    result = run_repeated_group_trials(
        _config(
            tmp_path,
            scenario_path="configs/multi_agent_scenarios/does_not_exist.json",
            continue_on_trial_failure=True,
        )
    )
    out_root = tmp_path / "repeated_group"
    trial_index = _json_list(out_root / "trial_index.json")

    assert result.status == "partial"
    assert result.aggregate.trial_count == 2
    assert result.aggregate.failed_trial_count == 2
    assert len(trial_index) == 2
    assert all(row["trial_status"] == "failed" for row in trial_index)
    assert (out_root / "runs" / "trial_001" / "trial_error.json").exists()


def test_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/run_repeated_orchestrator_executor_trials.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--orchestrator-port" in completed.stdout
    assert "--manage-servers" in completed.stdout


def test_cli_fake_repeated_group_trials_remain_offline_and_write_server_run(tmp_path: Path) -> None:
    out_root = tmp_path / "cli_fake_repeated"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_repeated_orchestrator_executor_trials.py",
            "--mode",
            "fake",
            "--models-config",
            "configs/evaluation_models.json",
            "--scenario",
            SCENARIO,
            "--out-root",
            str(out_root),
            "--label",
            "cli_fake_repeated",
            "--trials",
            "2",
            "--orchestrator-model-id",
            "second_model",
            "--executor-model-id",
            "first_model",
            "--max-group-steps",
            "1",
            "--max-steps-per-agent",
            "1",
            "--repair-attempts",
            "1",
            "--no-execute-actions",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "completed_trial_count: 2" in completed.stdout
    assert _json(out_root / "server_run.json")["servers"] == []
    assert (out_root / "runs" / "trial_001" / "manifest.json").exists()
