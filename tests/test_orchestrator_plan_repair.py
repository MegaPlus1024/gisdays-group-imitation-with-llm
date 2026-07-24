from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

from src.agent.orchestrator_executor_pipeline import (
    ExecutorProviderResult,
    OrchestratorExecutorRunConfig,
    OrchestratorExecutorRunner,
    OrchestratorProviderResult,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "configs/multi_agent_scenarios/office_developer_group_basic.json"


def _config(tmp_path: Path, **overrides: object) -> OrchestratorExecutorRunConfig:
    payload: dict[str, object] = {
        "project_root": PROJECT_ROOT,
        "mode": "fake",
        "models_config_path": "configs/evaluation_models.json",
        "scenario_path": SCENARIO,
        "out_dir": str(tmp_path / "repair_artifacts"),
        "run_id": "test_orchestrator_repair",
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
        "max_group_steps": 1,
        "max_steps_per_agent": 1,
        "repair_attempts": 1,
        "orchestrator_repair_attempts": 1,
        "execute_actions": False,
        "force": True,
    }
    payload.update(overrides)
    return OrchestratorExecutorRunConfig.model_validate(payload)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _valid_plan() -> str:
    return json.dumps(
        {
            "tasks": [
                {
                    "task_id": "t1",
                    "agent_id": "office_agent",
                    "goal": "Review local project notes.",
                    "allowed_action_focus": ["read_file"],
                    "success_criteria": "A safe local file action is selected.",
                },
                {
                    "task_id": "t2",
                    "agent_id": "developer_agent",
                    "goal": "Inspect safe project documentation.",
                    "allowed_action_focus": ["read_file"],
                    "success_criteria": "A safe documentation path is inspected.",
                },
            ],
            "coordination_notes": "Use local files only.",
            "expected_group_outcome": "Both agents perform one safe local action.",
        }
    )


class RepairingOrchestratorProvider:
    def create_plan(self, *, scenario, agents, agent_action_names):  # type: ignore[no-untyped-def]
        del scenario, agents, agent_action_names
        return OrchestratorProviderResult(
            raw_model_output='{"tasks": [',
            prompt_messages=[{"role": "user", "content": "initial"}],
            metadata={"provider": "test_initial"},
        )

    def repair_plan(self, *, scenario, agents, agent_action_names, previous_raw_output, error_message):  # type: ignore[no-untyped-def]
        del scenario, agents, agent_action_names, previous_raw_output, error_message
        return OrchestratorProviderResult(
            raw_model_output=_valid_plan(),
            prompt_messages=[{"role": "user", "content": "repair"}],
            metadata={"provider": "test_repair"},
        )


class FailingOrchestratorProvider:
    def create_plan(self, *, scenario, agents, agent_action_names):  # type: ignore[no-untyped-def]
        del scenario, agents, agent_action_names
        return OrchestratorProviderResult(
            raw_model_output='{"tasks": [',
            prompt_messages=[{"role": "user", "content": "initial"}],
            metadata={"provider": "test_initial"},
        )

    def repair_plan(self, *, scenario, agents, agent_action_names, previous_raw_output, error_message):  # type: ignore[no-untyped-def]
        del scenario, agents, agent_action_names, previous_raw_output, error_message
        return OrchestratorProviderResult(
            raw_model_output='{"tasks": [{"task_id": ',
            prompt_messages=[{"role": "user", "content": "repair"}],
            metadata={"provider": "test_repair"},
        )


class ValidExecutorProvider:
    def next_action(self, *, agent, task, state, group_step_index, agent_step_index, out_dir, project_root):  # type: ignore[no-untyped-def]
        del agent, task, state, group_step_index, agent_step_index, out_dir, project_root
        return ExecutorProviderResult(
            raw_model_output=json.dumps(
                {
                    "action_name": "read_file",
                    "parameters": {"path": "docs/ai/model_research_metadata.md"},
                }
            )
        )


def test_invalid_initial_orchestrator_json_followed_by_valid_repair_succeeds(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(
        _config(tmp_path),
        orchestrator_provider=RepairingOrchestratorProvider(),
        executor_provider=ValidExecutorProvider(),
    ).run()
    out_dir = Path(result.artifact_dir or "")
    attempts = _jsonl(out_dir / "orchestrator_attempts.jsonl")
    errors = _jsonl(out_dir / "errors.jsonl")
    actions = _jsonl(out_dir / "per_agent_actions.jsonl")

    assert result.status == "completed_with_failures"
    assert result.quality_metrics.orchestrator_plan_valid is True
    assert [row["attempt_type"] for row in attempts] == ["initial", "repair"]
    assert attempts[0]["parse_success"] is False
    assert attempts[1]["validation_success"] is True
    assert any(row["stage"] == "orchestrator" for row in errors)
    assert len(actions) >= 1


def test_invalid_initial_and_invalid_repair_fail_with_diagnostic_artifacts(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(
        _config(tmp_path),
        orchestrator_provider=FailingOrchestratorProvider(),
        executor_provider=ValidExecutorProvider(),
    ).run()
    out_dir = Path(result.artifact_dir or "")

    assert result.status == "failed"
    assert result.success is False
    for name in [
        "manifest.json",
        "orchestrator_prompt.json",
        "orchestrator_attempts.jsonl",
        "orchestrator_raw_output.json",
        "orchestrator_parse_error.json",
        "orchestrator_validation.json",
        "group_steps.jsonl",
        "agent_assignments.json",
        "per_agent_actions.jsonl",
        "per_agent_validation_results.jsonl",
        "per_agent_execution_results.jsonl",
        "group_history.jsonl",
        "errors.jsonl",
        "pair_quality_metrics.json",
        "pair_evaluation.json",
        "resource_summary.json",
        "README.md",
        "replay_commands.ps1",
    ]:
        assert (out_dir / name).exists(), name

    attempts = _jsonl(out_dir / "orchestrator_attempts.jsonl")
    metrics = _json(out_dir / "pair_quality_metrics.json")
    pair_eval = _json(out_dir / "pair_evaluation.json")
    assert len(attempts) == 2
    assert all(row["parse_success"] is False for row in attempts)
    assert metrics["orchestrator_plan_valid"] is False
    assert metrics["pair_quality_score"] == 0.0
    assert metrics["metadata"]["failure_stage"] == "orchestrator_plan"
    assert pair_eval["verdict"] == "failed"


def test_cli_accepts_orchestrator_repair_and_max_token_flags(tmp_path: Path) -> None:
    out_dir = tmp_path / "cli_flags"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_orchestrator_executor_group.py",
            "--mode",
            "fake",
            "--models-config",
            "configs/evaluation_models.json",
            "--scenario",
            SCENARIO,
            "--out-dir",
            str(out_dir),
            "--run-id",
            "cli_repair_flags",
            "--orchestrator-repair-attempts",
            "1",
            "--orchestrator-max-tokens",
            "768",
            "--max-group-steps",
            "1",
            "--max-steps-per-agent",
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
    manifest = _json(out_dir / "manifest.json")
    assert manifest["orchestrator_repair_attempts"] == 1
    assert manifest["orchestrator_max_tokens"] == 768


def test_fake_mode_remains_deterministic_with_repair_enabled(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(_config(tmp_path, mode="fake")).run()
    attempts = _jsonl(Path(result.artifact_dir or "") / "orchestrator_attempts.jsonl")

    assert result.status == "completed"
    assert len(attempts) == 1
    assert attempts[0]["attempt_type"] == "initial"
    assert attempts[0]["validation_success"] is True
