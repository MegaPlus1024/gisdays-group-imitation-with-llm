from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.agent.orchestrator_executor_pipeline import (
    OrchestratorExecutorRunConfig,
    OrchestratorExecutorRunner,
)
from src.agent.orchestrator_prompt_contract import (
    OrchestratorPlanJSONError,
    parse_orchestrator_plan_text,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "configs/multi_agent_scenarios/office_developer_group_basic.json"


def _config(tmp_path: Path, **overrides: object) -> OrchestratorExecutorRunConfig:
    payload: dict[str, object] = {
        "project_root": PROJECT_ROOT,
        "mode": "fake",
        "models_config_path": "configs/evaluation_models.json",
        "scenario_path": SCENARIO,
        "out_dir": str(tmp_path / "group_artifacts"),
        "run_id": "test_orchestrator_executor_fake",
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
        "max_group_steps": 2,
        "max_steps_per_agent": 2,
        "repair_attempts": 1,
        "execute_actions": False,
        "force": True,
    }
    payload.update(overrides)
    return OrchestratorExecutorRunConfig.model_validate(payload)


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_parse_valid_orchestrator_plan_json() -> None:
    raw = json.dumps(
        {
            "tasks": [
                {
                    "task_id": "task_1",
                    "agent_id": "office_agent",
                    "goal": "Read local metadata.",
                    "allowed_action_focus": ["read_file"],
                    "success_criteria": "Local metadata was reviewed.",
                }
            ],
            "coordination_notes": "Use local files only.",
            "expected_group_outcome": "A local-only group run completes.",
        }
    )

    plan = parse_orchestrator_plan_text(
        raw,
        known_agent_ids={"office_agent"},
        allowed_action_names_by_agent={"office_agent": {"read_file", "create_file"}},
    )

    assert plan.tasks[0].task_id == "task_1"
    assert plan.tasks[0].agent_id == "office_agent"


def test_parse_orchestrator_plan_rejects_unknown_agent() -> None:
    raw = json.dumps(
        {
            "tasks": [
                {
                    "task_id": "task_1",
                    "agent_id": "missing_agent",
                    "goal": "Read local metadata.",
                    "allowed_action_focus": ["read_file"],
                    "success_criteria": "Local metadata was reviewed.",
                }
            ],
            "coordination_notes": "Use local files only.",
            "expected_group_outcome": "A local-only group run completes.",
        }
    )

    with pytest.raises(OrchestratorPlanJSONError, match="Unknown agent_id"):
        parse_orchestrator_plan_text(raw, known_agent_ids={"office_agent"})


def test_fake_group_run_completes_and_writes_artifacts(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(_config(tmp_path)).run()
    out_dir = Path(result.artifact_dir or "")

    assert result.status == "completed"
    assert result.success is True
    assert result.orchestrator_model_id == "second_model"
    assert result.executor_model_ids == ["first_model"]
    assert 0.0 <= result.quality_metrics.pair_quality_score <= 1.0

    for name in [
        "manifest.json",
        "orchestrator_prompt.json",
        "orchestrator_raw_output.json",
        "orchestrator_plan.json",
        "orchestrator_validation.json",
        "agent_assignments.json",
        "group_steps.jsonl",
        "group_history.jsonl",
        "per_agent_actions.jsonl",
        "per_agent_validation_results.jsonl",
        "per_agent_execution_results.jsonl",
        "errors.jsonl",
        "pair_quality_metrics.json",
        "pair_evaluation.json",
        "resource_summary.json",
        "README.md",
        "replay_commands.ps1",
    ]:
        assert (out_dir / name).exists(), name


def test_fake_group_run_logs_per_agent_actions_and_group_history(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(_config(tmp_path)).run()
    out_dir = Path(result.artifact_dir or "")

    actions = _jsonl(out_dir / "per_agent_actions.jsonl")
    group_history = _jsonl(out_dir / "group_history.jsonl")

    assert len(actions) == 4
    assert len(group_history) == 4
    assert {row["agent_id"] for row in actions} == {"office_agent", "developer_agent"}
    assert {row["agent_id"] for row in group_history} == {"office_agent", "developer_agent"}
    assert all(row["validation_accepted"] is True for row in actions)


def test_pair_quality_score_is_persisted_in_range(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(_config(tmp_path)).run()
    metrics = _json(Path(result.artifact_dir or "") / "pair_quality_metrics.json")

    assert metrics["orchestrator_plan_valid"] is True
    assert 0.0 <= metrics["pair_quality_score"] <= 1.0
    assert metrics["metadata"]["prototype_scoring"] is True
    assert result.pair_evaluation.verdict in {"prototype_pass", "prototype_with_failures", "failed"}


def test_fake_mode_does_not_call_http_client(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agent.orchestrator_executor_pipeline as pipeline

    def fail_http_client(*args: object, **kwargs: object) -> object:
        raise AssertionError("fake mode must not create an HTTP client")

    monkeypatch.setattr(pipeline.httpx, "Client", fail_http_client)

    result = OrchestratorExecutorRunner(_config(tmp_path)).run()

    assert result.status == "completed"


def test_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/run_orchestrator_executor_group.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--scenario" in completed.stdout
    assert "--orchestrator-model-id" in completed.stdout


def test_cli_fake_run_writes_manifest_and_pair_evaluation(tmp_path: Path) -> None:
    out_dir = tmp_path / "cli_group_artifacts"
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
            "cli_orchestrator_executor_fake",
            "--orchestrator-model-id",
            "second_model",
            "--executor-model-id",
            "first_model",
            "--max-group-steps",
            "2",
            "--max-steps-per-agent",
            "2",
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
    assert "pair_quality_score:" in completed.stdout
    assert _json(out_dir / "manifest.json")["run_id"] == "cli_orchestrator_executor_fake"
    assert _json(out_dir / "pair_evaluation.json")["orchestrator_model_id"] == "second_model"
