from __future__ import annotations

import json
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
        "out_dir": str(tmp_path / "executor_repair_artifacts"),
        "run_id": "test_executor_repair",
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
        "max_group_steps": 1,
        "max_steps_per_agent": 1,
        "repair_attempts": 1,
        "execute_actions": False,
        "force": True,
    }
    payload.update(overrides)
    return OrchestratorExecutorRunConfig.model_validate(payload)


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


def _read_file(path: str) -> str:
    return json.dumps(
        {
            "action": "read_file",
            "parameters": {"path": path},
            "reason": "Read a safe local project file.",
            "expected_result": "The local file content is available.",
        }
    )


class StaticOrchestratorProvider:
    def create_plan(self, *, scenario, agents, agent_action_names):  # type: ignore[no-untyped-def]
        del scenario, agents, agent_action_names
        return OrchestratorProviderResult(
            raw_model_output=_valid_plan(),
            prompt_messages=[{"role": "user", "content": "valid plan"}],
            metadata={"provider": "static_test_orchestrator"},
        )


class MissingPathThenRepairExecutor:
    def __init__(self) -> None:
        self.repair_calls: list[dict[str, Any]] = []

    def next_action(self, *, agent, task, state, group_step_index, agent_step_index, out_dir, project_root):  # type: ignore[no-untyped-def]
        del task, state, group_step_index, agent_step_index, out_dir, project_root
        if agent.agent_id == "office_agent":
            return ExecutorProviderResult(
                raw_model_output=json.dumps(
                    {
                        "action": "read_file",
                        "parameters": {},
                        "reason": "Read a local office summary file.",
                        "expected_result": "A local office summary file.",
                    }
                )
            )
        return ExecutorProviderResult(raw_model_output=_read_file("docs/ai/final_tz_readiness_audit.md"))

    def repair_action(
        self,
        *,
        agent,
        task,
        state,
        group_step_index,
        agent_step_index,
        out_dir,
        project_root,
        previous_raw_output,
        validation_issues,
        error_message,
    ):  # type: ignore[no-untyped-def]
        del task, group_step_index, agent_step_index, out_dir, project_root
        self.repair_calls.append(
            {
                "agent_id": agent.agent_id,
                "previous_raw_output": previous_raw_output,
                "validation_issues": validation_issues,
                "error_message": error_message,
                "hints": state.metadata["executor_prompt_hints"],
            }
        )
        return ExecutorProviderResult(raw_model_output=_read_file("docs/ai/model_research_metadata.md"))


class AbsolutePathThenRepairExecutor:
    def __init__(self) -> None:
        self.repair_calls: list[dict[str, Any]] = []

    def next_action(self, *, agent, task, state, group_step_index, agent_step_index, out_dir, project_root):  # type: ignore[no-untyped-def]
        del task, state, group_step_index, agent_step_index, out_dir, project_root
        if agent.agent_id == "developer_agent":
            return ExecutorProviderResult(
                raw_model_output=json.dumps(
                    {
                        "action": "create_file",
                        "parameters": {
                            "path": "C:\\Users\\m\\Documents\\local-llm-test-gisdays\\local-llm-agent-lab\\docs\\ai\\bad.txt",
                            "content": "unsafe absolute path",
                        },
                        "reason": "Create a file with a Windows path.",
                        "expected_result": "A file is written.",
                    }
                )
            )
        return ExecutorProviderResult(raw_model_output=_read_file("docs/ai/model_research_metadata.md"))

    def repair_action(
        self,
        *,
        agent,
        task,
        state,
        group_step_index,
        agent_step_index,
        out_dir,
        project_root,
        previous_raw_output,
        validation_issues,
        error_message,
    ):  # type: ignore[no-untyped-def]
        del task, group_step_index, agent_step_index, out_dir, project_root, error_message
        self.repair_calls.append(
            {
                "agent_id": agent.agent_id,
                "previous_raw_output": previous_raw_output,
                "validation_issues": validation_issues,
                "hints": state.metadata["executor_prompt_hints"],
            }
        )
        return ExecutorProviderResult(raw_model_output=_read_file("docs/ai/orchestrator_executor_quality_spec.md"))


def test_executor_missing_required_path_is_repaired_and_attempts_are_logged(tmp_path: Path) -> None:
    executor = MissingPathThenRepairExecutor()
    result = OrchestratorExecutorRunner(
        _config(tmp_path),
        orchestrator_provider=StaticOrchestratorProvider(),
        executor_provider=executor,
    ).run()
    attempts = _jsonl(Path(result.artifact_dir or "") / "per_agent_attempts.jsonl")
    office_attempts = [row for row in attempts if row["agent_id"] == "office_agent"]

    assert result.status == "completed_with_failures"
    assert [row["attempt_type"] for row in office_attempts] == ["initial", "repair"]
    assert office_attempts[0]["validation_accepted"] is False
    assert office_attempts[1]["validation_accepted"] is True
    assert office_attempts[1]["parsed_action"]["parameters"]["path"] == "docs/ai/model_research_metadata.md"
    assert any(issue["code"] == "missing_required_parameter" for issue in office_attempts[0]["validation_issues"])
    assert result.quality_metrics.metadata["repair_attempt_count"] == 1
    assert result.quality_metrics.metadata["final_validation_success_count"] == 2

    repair_call = executor.repair_calls[0]
    assert any(issue["code"] == "missing_required_parameter" for issue in repair_call["validation_issues"])
    assert "path" in repair_call["hints"]["action_schemas"]["read_file"]["required_parameters"]
    assert "docs/" in repair_call["hints"]["safe_path_roots"]


def test_executor_absolute_windows_path_is_repaired_to_relative_safe_path(tmp_path: Path) -> None:
    executor = AbsolutePathThenRepairExecutor()
    result = OrchestratorExecutorRunner(
        _config(tmp_path),
        orchestrator_provider=StaticOrchestratorProvider(),
        executor_provider=executor,
    ).run()
    attempts = _jsonl(Path(result.artifact_dir or "") / "per_agent_attempts.jsonl")
    developer_attempts = [row for row in attempts if row["agent_id"] == "developer_agent"]

    assert result.status == "completed_with_failures"
    assert [row["attempt_type"] for row in developer_attempts] == ["initial", "repair"]
    assert developer_attempts[0]["validation_accepted"] is False
    assert developer_attempts[1]["validation_accepted"] is True
    assert developer_attempts[1]["parsed_action"]["parameters"]["path"] == "docs/ai/orchestrator_executor_quality_spec.md"
    assert any(issue["code"] == "unsafe_path" for issue in developer_attempts[0]["validation_issues"])
    assert any(issue["code"] == "path_outside_allowed_roots" for issue in developer_attempts[0]["validation_issues"])

    repair_call = executor.repair_calls[0]
    assert "C:" in repair_call["previous_raw_output"]
    assert "Users" in repair_call["previous_raw_output"]
    assert "docs/" in repair_call["hints"]["safe_path_roots"]
    assert all(not path.startswith("C:") for path in repair_call["hints"]["safe_existing_read_paths"])
