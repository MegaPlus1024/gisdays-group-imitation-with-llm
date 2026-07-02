from __future__ import annotations

import pytest

from src.agent.multi_agent_orchestrator import (
    MultiAgentAgentResult,
    MultiAgentOrchestratorSmoke,
    MultiAgentOrchestratorSmokeConfig,
    MultiAgentOrchestratorSmokeResult,
    MultiAgentRunSpec,
    load_multi_agent_orchestrator_smoke_config,
)
from src.agent.state import load_agent_state


class FakeTrajectoryResult:
    def __init__(self, success=True, actions=None, status="completed", stopped_reason=None):
        self.success = success
        self.status = status
        self.stopped_reason = stopped_reason
        self._actions = actions or []
        self.steps = [object()] * len(self._actions)

    def selected_actions(self):
        return list(self._actions)


class FakeRunner:
    def __init__(self, result=None, exc=None):
        self.result = result
        self.exc = exc
        self.calls = []

    def run_trajectory(self, state, run_id):
        self.calls.append((state, run_id))
        if self.exc:
            raise self.exc
        return self.result


def _spec(agent_id: str) -> MultiAgentRunSpec:
    state = load_agent_state("configs/agent_state.example.json")
    state.agent_id = agent_id
    return MultiAgentRunSpec(agent_id=agent_id, agent_state=state)


def test_config_defaults_valid() -> None:
    cfg = MultiAgentOrchestratorSmokeConfig()
    assert cfg.orchestrator_id == "multi_agent_orchestrator_smoke_v1"
    assert cfg.execution_mode == "sequential"


def test_config_rejects_max_agents_lt_1() -> None:
    with pytest.raises(ValueError):
        MultiAgentOrchestratorSmokeConfig(max_agents=0)


def test_config_rejects_max_steps_lt_1() -> None:
    with pytest.raises(ValueError):
        MultiAgentOrchestratorSmokeConfig(max_steps_per_agent=0)


def test_load_example_config() -> None:
    cfg = load_multi_agent_orchestrator_smoke_config(
        "configs/multi_agent_orchestrator_smoke.example.json"
    )
    assert cfg.orchestrator_id == "multi_agent_orchestrator_smoke_v1"


def test_result_count_helpers() -> None:
    result = MultiAgentOrchestratorSmokeResult(
        orchestrator_id="o",
        run_id="r",
        status="completed_with_failures",
        success=False,
        stopped_reason="failed",
        agent_results=[
            MultiAgentAgentResult(
                orchestrator_id="o",
                run_id="r",
                agent_id="a1",
                status="succeeded",
                success=True,
                selected_actions=["read_file"],
            ),
            MultiAgentAgentResult(
                orchestrator_id="o",
                run_id="r",
                agent_id="a2",
                status="failed",
                success=False,
                error_type="x",
                error_message="y",
            ),
        ],
    )
    assert result.total_agents() == 2
    assert result.successful_agents_count() == 1
    assert result.failed_agents_count() == 1
    assert result.selected_actions_by_agent()["a1"] == ["read_file"]


def test_run_smoke_rejects_empty_specs() -> None:
    orch = MultiAgentOrchestratorSmoke(runner_factory=lambda spec: None)
    with pytest.raises(ValueError):
        orch.run_smoke([])


def test_run_smoke_rejects_specs_gt_max_agents() -> None:
    orch = MultiAgentOrchestratorSmoke(
        config=MultiAgentOrchestratorSmokeConfig(max_agents=1),
        runner_factory=lambda spec: FakeRunner(FakeTrajectoryResult()),
    )
    with pytest.raises(ValueError):
        orch.run_smoke([_spec("a1"), _spec("a2")])


def test_run_smoke_requires_runner_factory() -> None:
    orch = MultiAgentOrchestratorSmoke()
    with pytest.raises(ValueError):
        orch.run_smoke([_spec("a1")])


def test_run_smoke_sequential_order() -> None:
    order = []
    runners = {
        "a1": FakeRunner(FakeTrajectoryResult(actions=["x1"])),
        "a2": FakeRunner(FakeTrajectoryResult(actions=["x2"])),
    }

    def factory(spec):
        order.append(spec.agent_id)
        return runners[spec.agent_id]

    orch = MultiAgentOrchestratorSmoke(runner_factory=factory)
    res = orch.run_smoke([_spec("a1"), _spec("a2")], run_id="r1")
    assert res.status == "completed"
    assert order == ["a1", "a2"]


def test_run_smoke_completed_when_all_succeed() -> None:
    def factory(spec):
        return FakeRunner(FakeTrajectoryResult(success=True, actions=["read_file"]))

    orch = MultiAgentOrchestratorSmoke(runner_factory=factory)
    res = orch.run_smoke([_spec("a1"), _spec("a2")])
    assert res.success is True
    assert res.status == "completed"


def test_run_smoke_completed_with_failures_when_one_fails() -> None:
    def factory(spec):
        if spec.agent_id == "a1":
            return FakeRunner(FakeTrajectoryResult(success=False, actions=["read_file"], stopped_reason="boom"))
        return FakeRunner(FakeTrajectoryResult(success=True, actions=["read_file"]))

    orch = MultiAgentOrchestratorSmoke(runner_factory=factory)
    res = orch.run_smoke([_spec("a1"), _spec("a2")])
    assert res.success is False
    assert res.status == "completed_with_failures"
    assert res.total_agents() == 2


def test_run_smoke_continues_after_failure_with_isolation() -> None:
    seen = []

    def factory(spec):
        seen.append(spec.agent_id)
        if spec.agent_id == "a1":
            return FakeRunner(exc=RuntimeError("fail"))
        return FakeRunner(FakeTrajectoryResult(success=True))

    orch = MultiAgentOrchestratorSmoke(
        config=MultiAgentOrchestratorSmokeConfig(
            isolate_agent_failures=True, stop_on_first_agent_failure=False
        ),
        runner_factory=factory,
    )
    res = orch.run_smoke([_spec("a1"), _spec("a2")])
    assert res.status == "completed_with_failures"
    assert seen == ["a1", "a2"]


def test_run_smoke_stops_on_first_failure() -> None:
    seen = []

    def factory(spec):
        seen.append(spec.agent_id)
        if spec.agent_id == "a1":
            return FakeRunner(exc=RuntimeError("fail"))
        return FakeRunner(FakeTrajectoryResult(success=True))

    orch = MultiAgentOrchestratorSmoke(
        config=MultiAgentOrchestratorSmokeConfig(stop_on_first_agent_failure=True),
        runner_factory=factory,
    )
    res = orch.run_smoke([_spec("a1"), _spec("a2")])
    assert res.status == "stopped_on_agent_failure"
    assert seen == ["a1"]


def test_runner_exception_becomes_failed_agent_result() -> None:
    def factory(spec):
        return FakeRunner(exc=ValueError("bad runner"))

    orch = MultiAgentOrchestratorSmoke(runner_factory=factory)
    res = orch.run_smoke([_spec("a1")])
    assert res.agent_results[0].success is False
    assert res.agent_results[0].error_type == "ValueError"


def test_input_agent_state_not_mutated() -> None:
    spec = _spec("a1")
    before = spec.agent_state.model_dump()

    def factory(spec):
        return FakeRunner(FakeTrajectoryResult(success=True, actions=["read_file"]))

    orch = MultiAgentOrchestratorSmoke(runner_factory=factory)
    orch.run_smoke([spec])
    assert spec.agent_state.model_dump() == before
