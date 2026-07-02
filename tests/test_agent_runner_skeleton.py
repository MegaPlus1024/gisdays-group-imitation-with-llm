from __future__ import annotations

import copy
import json
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.agent import AgentStepResult
from agent.runner import (
    AgentRunner,
    AgentRunnerConfig,
    RunnerRunResult,
    RunnerStepResult,
    load_agent_runner_config,
)
from agent.schemas import NextAction
from agent.script_registry import ScriptValidationResult, load_script_registry
from agent.state import AgentState, load_agent_state


class FakeSuccessAgent:
    def __init__(self, action: NextAction) -> None:
        self.action = action

    def decide_next_action(self, request: Any) -> AgentStepResult:
        return AgentStepResult(
            run_id=request.run_id,
            agent_id=request.agent_state.agent_id,
            step_index=request.step_index,
            success=True,
            next_action=self.action,
        )


class FakeFailedAgent:
    def decide_next_action(self, request: Any) -> AgentStepResult:
        return AgentStepResult(
            run_id=request.run_id,
            agent_id=request.agent_state.agent_id,
            step_index=request.step_index,
            success=False,
            error_type="LocalLLMRequestError",
            error_message="connection refused",
        )


def load_example_state() -> AgentState:
    return load_agent_state("configs/agent_state.example.json")


def load_fixture_next_action(name: str) -> NextAction:
    path = Path("tests/fixtures/registry/next_actions") / name
    payload = json.loads(path.read_text(encoding="utf-8"))
    return NextAction.model_validate(payload)


def test_agent_runner_config_defaults_valid() -> None:
    cfg = AgentRunnerConfig()
    assert cfg.runner_id == "agent_runner_v1"
    assert cfg.max_steps == 1


def test_agent_runner_config_rejects_max_steps_below_1() -> None:
    with pytest.raises(ValidationError):
        AgentRunnerConfig(max_steps=0)


def test_agent_runner_config_rejects_execute_actions_true() -> None:
    with pytest.raises(ValidationError):
        AgentRunnerConfig(execute_actions=True)


def test_load_agent_runner_config_loads_example() -> None:
    cfg = load_agent_runner_config("configs/agent_runner.example.json")
    assert cfg.runner_id == "agent_runner_v1"
    assert cfg.execute_actions is False


def test_runner_step_result_failure_requires_error_fields() -> None:
    with pytest.raises(ValidationError):
        RunnerStepResult(
            runner_id="r1",
            run_id="run1",
            agent_id="a1",
            step_index=1,
            status="decision_failed",
            success=False,
        )


def test_runner_step_result_pending_execution_requires_next_action() -> None:
    with pytest.raises(ValidationError):
        RunnerStepResult(
            runner_id="r1",
            run_id="run1",
            agent_id="a1",
            step_index=1,
            status="pending_execution",
            success=True,
        )


def test_runner_run_result_counts_steps() -> None:
    action = NextAction(
        action="read_file",
        parameters={"path": "docs/ai/model_registry.md"},
        reason="Need context",
        expected_result="content",
    )
    steps = [
        RunnerStepResult(
            runner_id="r1",
            run_id="run1",
            agent_id="a1",
            step_index=1,
            status="pending_execution",
            success=True,
            next_action=action,
        ),
        RunnerStepResult(
            runner_id="r1",
            run_id="run1",
            agent_id="a1",
            step_index=2,
            status="validation_failed",
            success=False,
            validation_result=ScriptValidationResult(
                accepted=False,
                action="read_file",
                issues=[
                    {
                        "code": "forbidden_path",
                        "message": "forbidden",
                        "layer": "safety_policy",
                    }
                ],
            ),
            error_type="validation_failed",
            error_message="forbidden_path",
        ),
    ]
    run = RunnerRunResult(
        runner_id="r1",
        run_id="run1",
        agent_id="a1",
        success=False,
        steps=steps,
    )
    assert run.successful_steps_count() == 1
    assert run.failed_steps_count() == 1


def test_run_one_step_pending_execution_for_valid_action() -> None:
    registry = load_script_registry("configs/script_registry.example.json")
    action = load_fixture_next_action("valid_read_file.json")
    runner = AgentRunner(
        agent=FakeSuccessAgent(action),  # type: ignore[arg-type]
        config=AgentRunnerConfig(validate_actions=True),
        registry=registry,
    )
    state = load_example_state()
    result = runner.run_one_step(state, run_id="run1")
    assert result.success is True
    assert result.status == "pending_execution"
    assert result.validation_result is not None
    assert result.validation_result.accepted is True


def test_run_one_step_validation_failed_for_unknown_action() -> None:
    registry = load_script_registry("configs/script_registry.example.json")
    action = NextAction(
        action="non_existing_action",
        parameters={},
        reason="x",
        expected_result="y",
    )
    runner = AgentRunner(
        agent=FakeSuccessAgent(action),  # type: ignore[arg-type]
        config=AgentRunnerConfig(validate_actions=True),
        registry=registry,
    )
    result = runner.run_one_step(load_example_state(), run_id="run1")
    assert result.success is False
    assert result.status == "validation_failed"
    assert result.error_type == "validation_failed"


def test_run_one_step_validation_failed_for_forbidden_path() -> None:
    registry = load_script_registry("configs/script_registry.example.json")
    action = NextAction(
        action="read_file",
        parameters={"path": "models/gguf/first_model.gguf"},
        reason="x",
        expected_result="y",
    )
    runner = AgentRunner(
        agent=FakeSuccessAgent(action),  # type: ignore[arg-type]
        config=AgentRunnerConfig(validate_actions=True),
        registry=registry,
    )
    result = runner.run_one_step(load_example_state(), run_id="run1")
    assert result.success is False
    assert result.status == "validation_failed"
    assert result.validation_result is not None


def test_run_one_step_decision_failed_when_agent_fails() -> None:
    registry = load_script_registry("configs/script_registry.example.json")
    runner = AgentRunner(
        agent=FakeFailedAgent(),  # type: ignore[arg-type]
        config=AgentRunnerConfig(validate_actions=True),
        registry=registry,
    )
    result = runner.run_one_step(load_example_state(), run_id="run1")
    assert result.success is False
    assert result.status == "decision_failed"
    assert result.error_type == "LocalLLMRequestError"


def test_run_one_step_does_not_mutate_history() -> None:
    registry = load_script_registry("configs/script_registry.example.json")
    action = load_fixture_next_action("valid_read_file.json")
    runner = AgentRunner(
        agent=FakeSuccessAgent(action),  # type: ignore[arg-type]
        config=AgentRunnerConfig(validate_actions=True),
        registry=registry,
    )
    state = load_example_state()
    before = copy.deepcopy(state.history)
    _ = runner.run_one_step(state, run_id="run1")
    assert state.history == before


def test_run_one_step_uses_current_step_when_none() -> None:
    registry = load_script_registry("configs/script_registry.example.json")
    action = load_fixture_next_action("valid_read_file.json")
    runner = AgentRunner(
        agent=FakeSuccessAgent(action),  # type: ignore[arg-type]
        config=AgentRunnerConfig(validate_actions=True),
        registry=registry,
    )
    state = load_example_state()
    result = runner.run_one_step(state, run_id="run1", step_index=None)
    assert result.step_index == state.current_step


def test_run_one_step_accepts_explicit_step_index() -> None:
    registry = load_script_registry("configs/script_registry.example.json")
    action = load_fixture_next_action("valid_read_file.json")
    runner = AgentRunner(
        agent=FakeSuccessAgent(action),  # type: ignore[arg-type]
        config=AgentRunnerConfig(validate_actions=True),
        registry=registry,
    )
    result = runner.run_one_step(load_example_state(), run_id="run1", step_index=10)
    assert result.step_index == 10


def test_validate_actions_false_returns_pending_execution_without_registry() -> None:
    action = NextAction(
        action="non_existing_action",
        parameters={},
        reason="x",
        expected_result="y",
    )
    runner = AgentRunner(
        agent=FakeSuccessAgent(action),  # type: ignore[arg-type]
        config=AgentRunnerConfig(validate_actions=False, registry_path=None),
        registry=None,
    )
    result = runner.run_one_step(load_example_state(), run_id="run1")
    assert result.success is True
    assert result.status == "pending_execution"


def test_run_returns_pending_execution_on_valid_action() -> None:
    registry = load_script_registry("configs/script_registry.example.json")
    action = load_fixture_next_action("valid_read_file.json")
    runner = AgentRunner(
        agent=FakeSuccessAgent(action),  # type: ignore[arg-type]
        config=AgentRunnerConfig(validate_actions=True),
        registry=registry,
    )
    result = runner.run(load_example_state(), run_id="run1")
    assert result.stopped_reason == "pending_execution"
    assert result.steps[0].status == "pending_execution"


def test_run_returns_validation_failed_on_invalid_action() -> None:
    registry = load_script_registry("configs/script_registry.example.json")
    action = NextAction(
        action="read_file",
        parameters={"path": "models/gguf/second_model.gguf"},
        reason="x",
        expected_result="y",
    )
    runner = AgentRunner(
        agent=FakeSuccessAgent(action),  # type: ignore[arg-type]
        config=AgentRunnerConfig(validate_actions=True),
        registry=registry,
    )
    result = runner.run(load_example_state(), run_id="run1")
    assert result.stopped_reason == "validation_failed"
    assert result.steps[0].status == "validation_failed"
