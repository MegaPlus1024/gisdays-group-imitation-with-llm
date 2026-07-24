from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.agent.experiment_scenario_runner import (
    ExperimentScenarioRunner,
    ExperimentScenarioRunnerConfig,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "configs/evaluation_scenarios/office_worker_basic_session.json"


def _read_file_action() -> dict[str, object]:
    return {
        "action_name": "read_file",
        "parameters": {"path": "docs/ai/model_registry.md"},
    }


def _read_file_action_missing_path() -> dict[str, object]:
    return {
        "action_name": "read_file",
        "parameters": {},
    }


def _config(tmp_path: Path, **overrides: object) -> ExperimentScenarioRunnerConfig:
    payload: dict[str, object] = {
        "project_root": PROJECT_ROOT,
        "scenario_path": SCENARIO,
        "out_dir": str(tmp_path / "scenario_artifacts"),
        "run_id": "test_fake_run",
        "mode": "fake",
        "max_steps": 1,
        "force": True,
        "scripted_actions": [_read_file_action()],
    }
    payload.update(overrides)
    return ExperimentScenarioRunnerConfig.model_validate(payload)


def _jsonl(path: Path) -> list[dict[str, object]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_fake_runner_creates_artifact_folder(tmp_path: Path) -> None:
    result = ExperimentScenarioRunner(_config(tmp_path)).run()
    out_dir = Path(result.out_dir)

    assert result.status in {"completed", "stopped"}
    assert out_dir.exists()
    for name in [
        "manifest.json",
        "steps.jsonl",
        "raw_model_outputs.jsonl",
        "attempts.jsonl",
        "selected_actions.jsonl",
        "validation_results.jsonl",
        "execution_results.jsonl",
        "history.jsonl",
        "errors.jsonl",
        "activity_evaluation.json",
        "model_behavior_result.json",
        "resource_summary.json",
        "replay_commands.ps1",
        "README.md",
    ]:
        assert (out_dir / name).exists(), name


def test_replay_command_records_execute_actions_flag(tmp_path: Path) -> None:
    result = ExperimentScenarioRunner(_config(tmp_path, execute_actions=True)).run()
    replay = (Path(result.out_dir) / "replay_commands.ps1").read_text(encoding="utf-8")

    assert "--execute-actions" in replay
    assert "--no-execute-actions" not in replay


def test_fake_runner_executes_safe_read_file_action(tmp_path: Path) -> None:
    result = ExperimentScenarioRunner(_config(tmp_path)).run()
    step = result.steps[0]

    assert step.parse_success is True
    assert step.registry_accepted is True
    assert step.role_compliant is True
    assert step.execution_attempted is True
    assert step.execution_success is True
    assert step.normalized_execution_result is not None
    assert step.normalized_execution_result["success"] is True


def test_invalid_json_is_recorded_as_error(tmp_path: Path) -> None:
    result = ExperimentScenarioRunner(
        _config(tmp_path, scripted_actions=["not json"], max_steps=1)
    ).run()
    out_dir = Path(result.out_dir)

    assert result.steps[0].parse_success is False
    assert result.steps[0].error_type == "NextActionJSONError"
    errors = _jsonl(out_dir / "errors.jsonl")
    assert errors
    assert errors[0]["error_type"] == "NextActionJSONError"
    model_behavior = json.loads((out_dir / "model_behavior_result.json").read_text(encoding="utf-8"))
    assert model_behavior["validation_metrics"]["total_steps"] == 1
    assert model_behavior["validation_metrics"]["json_valid_count"] == 0


def test_unknown_action_is_validation_failure(tmp_path: Path) -> None:
    result = ExperimentScenarioRunner(
        _config(
            tmp_path,
            scripted_actions=[
                {
                    "action_name": "unknown_action",
                    "parameters": {},
                }
            ],
        )
    ).run()
    step = result.steps[0]

    assert step.parse_success is True
    assert step.registry_accepted is False
    assert step.execution_attempted is False
    assert step.error_type == "validation_failed"
    issue_codes = [issue["code"] for issue in step.validation_result["issues"]]
    assert "unknown_action" in issue_codes


def test_repair_disabled_preserves_old_validation_failure_behavior(tmp_path: Path) -> None:
    result = ExperimentScenarioRunner(
        _config(tmp_path, scripted_actions=[_read_file_action_missing_path()])
    ).run()
    out_dir = Path(result.out_dir)

    assert result.steps[0].error_type == "validation_failed"
    assert result.steps[0].repair_attempt_count == 0
    assert len(_jsonl(out_dir / "attempts.jsonl")) == 1


def test_validation_failure_followed_by_valid_repair_executes_action(tmp_path: Path) -> None:
    result = ExperimentScenarioRunner(
        _config(
            tmp_path,
            scripted_actions=[_read_file_action_missing_path(), _read_file_action()],
            repair_attempts_per_step=1,
        )
    ).run()
    out_dir = Path(result.out_dir)

    step = result.steps[0]
    assert step.repaired is True
    assert step.initial_failure_preserved is True
    assert step.registry_accepted is True
    assert step.execution_attempted is True
    assert step.execution_success is True
    attempts = _jsonl(out_dir / "attempts.jsonl")
    assert [a["attempt_type"] for a in attempts] == ["initial", "repair"]
    errors = _jsonl(out_dir / "errors.jsonl")
    assert any(e["metadata"].get("attempt_type") == "initial" for e in errors)
    selected = _jsonl(out_dir / "selected_actions.jsonl")
    assert selected[0]["next_action"]["parameters"]["path"] == "docs/ai/model_registry.md"
    model_behavior = json.loads((out_dir / "model_behavior_result.json").read_text(encoding="utf-8"))
    summary = model_behavior["metadata"]["repair_summary"]
    assert summary["initial_validation_accept_count"] == 0
    assert summary["repair_validation_accept_count"] == 1
    assert summary["final_validation_accept_count"] == 1


def test_malformed_json_followed_by_valid_repair_executes_action(tmp_path: Path) -> None:
    result = ExperimentScenarioRunner(
        _config(
            tmp_path,
            scripted_actions=["not json", _read_file_action()],
            repair_attempts_per_step=1,
        )
    ).run()

    step = result.steps[0]
    assert step.repaired is True
    assert step.parse_success is True
    assert step.registry_accepted is True
    assert step.execution_success is True


def test_validation_failure_followed_by_invalid_repair_stops(tmp_path: Path) -> None:
    result = ExperimentScenarioRunner(
        _config(
            tmp_path,
            scripted_actions=[_read_file_action_missing_path(), _read_file_action_missing_path()],
            repair_attempts_per_step=1,
        )
    ).run()

    step = result.steps[0]
    assert step.error_type == "validation_failed_after_repair"
    assert result.stopped_reason == "validation_failed_after_repair"
    assert step.repair_attempt_count == 1
    assert step.registry_accepted is False


def test_write_action_outside_workspace_is_rejected_without_writing_docs(tmp_path: Path) -> None:
    forbidden_doc = PROJECT_ROOT / "docs" / "ai" / "should_not_be_written_by_runner.md"
    if forbidden_doc.exists():
        forbidden_doc.unlink()

    result = ExperimentScenarioRunner(
        _config(
            tmp_path,
            scripted_actions=[
                {
                    "action_name": "create_file",
                    "parameters": {
                        "path": "docs/ai/should_not_be_written_by_runner.md",
                        "content": "This should be blocked by workspace policy.",
                    },
                }
            ],
        )
    ).run()

    step = result.steps[0]
    issue_codes = [issue["code"] for issue in step.validation_result["issues"]]
    assert step.error_type == "validation_failed"
    assert step.execution_attempted is False
    assert "write_path_outside_workspace" in issue_codes
    assert not forbidden_doc.exists()


def test_duplicate_validation_issue_codes_do_not_crash_stop_summary(tmp_path: Path) -> None:
    action = {
        "action_name": "create_file",
        "parameters": {
            "path": "docs/ai/model_registry.md",
            "content": "This should be blocked by workspace policy.",
        },
    }
    result = ExperimentScenarioRunner(
        _config(
            tmp_path,
            scenario_path="configs/evaluation_scenarios/developer_project_maintenance.json",
            scripted_actions=[action, action],
            repair_attempts_per_step=1,
        )
    ).run()

    step = result.steps[0]
    assert step.error_type == "validation_failed_after_repair"
    assert result.stopped_reason == "validation_failed_after_repair"
    assert step.attempts[-1]["validation_issues"]


def test_no_execute_actions_saves_selection_without_bridge_execution(tmp_path: Path) -> None:
    result = ExperimentScenarioRunner(_config(tmp_path, execute_actions=False)).run()
    out_dir = Path(result.out_dir)
    selected = _jsonl(out_dir / "selected_actions.jsonl")
    execution_results = _jsonl(out_dir / "execution_results.jsonl")

    assert result.steps[0].parse_success is True
    assert result.steps[0].execution_attempted is False
    assert selected[0]["next_action"]["action_name"] == "read_file"
    assert execution_results == []


def test_max_steps_stop_is_recorded(tmp_path: Path) -> None:
    result = ExperimentScenarioRunner(
        _config(tmp_path, max_steps=2, scripted_actions=[_read_file_action(), _read_file_action()])
    ).run()

    assert len(result.steps) == 2
    assert result.stopped_reason == "Reached max_steps limit."
    assert result.steps[-1].stop_reason == "Reached max_steps limit."


def test_activity_evaluation_json_is_created(tmp_path: Path) -> None:
    result = ExperimentScenarioRunner(_config(tmp_path)).run()
    payload = json.loads(Path(result.activity_evaluation_path).read_text(encoding="utf-8"))

    assert payload["evaluator_id"] == "normal_activity_trajectory_evaluator_v1"
    assert "metrics" in payload
    assert "normal_activity_score" in payload["metrics"]


def test_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/run_agent_scenario.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--scenario" in completed.stdout
    assert "--mode" in completed.stdout


def test_cli_fake_run_creates_temp_artifacts(tmp_path: Path) -> None:
    actions_path = tmp_path / "actions.json"
    actions_path.write_text(json.dumps([_read_file_action()]), encoding="utf-8")
    out_dir = tmp_path / "cli_artifacts"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_agent_scenario.py",
            "--scenario",
            SCENARIO,
            "--mode",
            "fake",
            "--scripted-actions",
            str(actions_path),
            "--out-dir",
            str(out_dir),
            "--run-id",
            "cli_fake_test",
            "--max-steps",
            "1",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "artifact_dir:" in completed.stdout
    assert (out_dir / "manifest.json").exists()


def test_cli_fake_repair_attempts_work(tmp_path: Path) -> None:
    actions_path = tmp_path / "repair_actions.json"
    actions_path.write_text(
        json.dumps([_read_file_action_missing_path(), _read_file_action()]),
        encoding="utf-8",
    )
    out_dir = tmp_path / "cli_repair_artifacts"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_agent_scenario.py",
            "--scenario",
            SCENARIO,
            "--mode",
            "fake",
            "--scripted-actions",
            str(actions_path),
            "--out-dir",
            str(out_dir),
            "--run-id",
            "cli_fake_repair_test",
            "--max-steps",
            "1",
            "--repair-attempts",
            "1",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    attempts = _jsonl(out_dir / "attempts.jsonl")
    assert [attempt["attempt_type"] for attempt in attempts] == ["initial", "repair"]
