from __future__ import annotations

import copy
import sys
from pathlib import Path
from typing import Any

import pytest
from pydantic import ValidationError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "src"))

from agent.agent import Agent, AgentStepRequest, AgentStepResult
from agent.llm_client import LocalLLMClientError
from agent.orchestrator import Orchestrator
from agent.schemas import NextAction
from agent.state import AgentState, load_agent_state


class FakeSuccessClient:
    def generate_next_action(self, agent_state: dict[str, Any]) -> NextAction:
        return NextAction(
            action="read_file",
            parameters={"path": "docs/ai/model_registry.md"},
            reason="Need model metadata context.",
            expected_result="Model registry content is available.",
        )


class FakeFailure(LocalLLMClientError):
    pass


class FakeFailureClient:
    def generate_next_action(self, agent_state: dict[str, Any]) -> NextAction:
        raise FakeFailure("mocked client failure")


def load_example_state() -> AgentState:
    return load_agent_state("configs/agent_state.example.json")


def test_agent_step_request_rejects_empty_run_id() -> None:
    with pytest.raises(ValidationError):
        AgentStepRequest(run_id="", agent_state=load_example_state(), step_index=1)


def test_agent_step_request_rejects_step_index_below_1() -> None:
    with pytest.raises(ValidationError):
        AgentStepRequest(run_id="run1", agent_state=load_example_state(), step_index=0)


def test_agent_step_result_success_requires_next_action() -> None:
    with pytest.raises(ValidationError):
        AgentStepResult(run_id="run1", agent_id="a1", step_index=1, success=True)


def test_agent_step_result_failure_requires_error_fields() -> None:
    with pytest.raises(ValidationError):
        AgentStepResult(
            run_id="run1",
            agent_id="a1",
            step_index=1,
            success=False,
            error_type="",
            error_message="",
        )


def test_agent_decide_next_action_success() -> None:
    agent = Agent(llm_client=FakeSuccessClient())  # type: ignore[arg-type]
    state = load_example_state()
    req = AgentStepRequest(run_id="run1", agent_state=state, step_index=state.current_step)
    result = agent.decide_next_action(req)
    assert result.success is True
    assert result.next_action is not None
    assert result.error_type is None


def test_agent_decide_next_action_failure_on_client_error() -> None:
    agent = Agent(llm_client=FakeFailureClient())  # type: ignore[arg-type]
    state = load_example_state()
    req = AgentStepRequest(run_id="run1", agent_state=state, step_index=state.current_step)
    result = agent.decide_next_action(req)
    assert result.success is False
    assert result.next_action is None
    assert result.error_type == "FakeFailure"
    assert "mocked client failure" in (result.error_message or "")


def test_agent_does_not_mutate_history() -> None:
    agent = Agent(llm_client=FakeSuccessClient())  # type: ignore[arg-type]
    state = load_example_state()
    before = copy.deepcopy(state.history)
    req = AgentStepRequest(run_id="run1", agent_state=state, step_index=state.current_step)
    _ = agent.decide_next_action(req)
    assert state.history == before


def test_orchestrator_uses_current_step_when_step_index_missing() -> None:
    state = load_example_state()
    orchestrator = Orchestrator(agent=Agent(FakeSuccessClient()), run_id="demo")  # type: ignore[arg-type]
    result = orchestrator.run_agent_step(state)
    assert result.step_index == state.current_step


def test_orchestrator_accepts_explicit_step_index() -> None:
    state = load_example_state()
    orchestrator = Orchestrator(agent=Agent(FakeSuccessClient()), run_id="demo")  # type: ignore[arg-type]
    result = orchestrator.run_agent_step(state, step_index=10)
    assert result.step_index == 10


def test_orchestrator_run_agent_steps_sequential() -> None:
    s1 = load_example_state()
    s2 = load_example_state().model_copy(update={"agent_id": "student_researcher_002"})
    orchestrator = Orchestrator(agent=Agent(FakeSuccessClient()), run_id="demo")  # type: ignore[arg-type]
    results = orchestrator.run_agent_steps([s1, s2])
    assert len(results) == 2
    assert results[0].agent_id == "student_researcher_001"
    assert results[1].agent_id == "student_researcher_002"


def test_orchestrator_rejects_empty_run_id() -> None:
    with pytest.raises(ValueError):
        Orchestrator(agent=Agent(FakeSuccessClient()), run_id="")  # type: ignore[arg-type]
