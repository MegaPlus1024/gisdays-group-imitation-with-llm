from __future__ import annotations

import json

from src.agent.autonomous_multi_agent_runtime import (
    AutonomousMultiAgentRuntime,
    RuntimeActionDecision,
    RuntimeActionResult,
    RuntimeAgentSpec,
    RuntimePolicy,
    RuntimeSharedState,
    RuntimeStopReason,
    RuntimeTask,
    RuntimeVirtualEnvironment,
    RuntimeWorkspace,
)


def _decision(agent_id: str, *, task_id: str | None = None, action_type: str = "files") -> RuntimeActionDecision:
    return RuntimeActionDecision(
        agent_id=agent_id,
        action_type=action_type,
        action_name="read_file",
        task_id=task_id,
    )


def _success_executor(decision: RuntimeActionDecision, state: RuntimeSharedState) -> RuntimeActionResult:
    return RuntimeActionResult(success=True, artifact_refs=(f"{decision.agent_id}.txt",))


def test_round_robin_scheduler_selects_agents_deterministically() -> None:
    order: list[str] = []

    def provider(agent: RuntimeAgentSpec, state: RuntimeSharedState) -> RuntimeActionDecision:
        order.append(agent.agent_id)
        return _decision(agent.agent_id)

    runtime = AutonomousMultiAgentRuntime(
        runtime_id="rr",
        agents=[RuntimeAgentSpec("a"), RuntimeAgentSpec("b")],
        policy=RuntimePolicy(stop_when_all_tasks_terminal=False, idle_tick_limit=10),
        decision_provider=provider,
        action_executor=_success_executor,
    )

    runtime.step()
    runtime.step()
    runtime.step()

    assert order == ["a", "b", "a"]


def test_priority_then_round_robin_scheduler_prefers_high_priority_agents() -> None:
    order: list[str] = []

    def provider(agent: RuntimeAgentSpec, state: RuntimeSharedState) -> RuntimeActionDecision:
        order.append(agent.agent_id)
        return _decision(agent.agent_id)

    runtime = AutonomousMultiAgentRuntime(
        runtime_id="priority",
        agents=[
            RuntimeAgentSpec("low", priority=1),
            RuntimeAgentSpec("high_a", priority=5),
            RuntimeAgentSpec("high_b", priority=5),
        ],
        policy=RuntimePolicy(
            scheduler="priority_then_round_robin",
            stop_when_all_tasks_terminal=False,
            idle_tick_limit=10,
        ),
        decision_provider=provider,
        action_executor=_success_executor,
    )

    runtime.step()
    runtime.step()
    runtime.step()

    assert order == ["high_a", "high_b", "high_a"]


def test_completed_blocked_and_quarantined_agents_are_skipped() -> None:
    selected: list[str] = []
    state = RuntimeSharedState.from_specs(
        [
            RuntimeAgentSpec("done", status="completed"),
            RuntimeAgentSpec("blocked", status="blocked"),
            RuntimeAgentSpec("ok"),
            RuntimeAgentSpec("bad"),
        ],
        [],
    )
    state.quarantined_agents.add("bad")

    def provider(agent: RuntimeAgentSpec, shared: RuntimeSharedState) -> RuntimeActionDecision:
        selected.append(agent.agent_id)
        return _decision(agent.agent_id)

    runtime = AutonomousMultiAgentRuntime(
        runtime_id="skip",
        shared_state=state,
        policy=RuntimePolicy(stop_when_all_tasks_terminal=False),
        decision_provider=provider,
        action_executor=_success_executor,
    )

    runtime.step()

    assert selected == ["ok"]


def test_shared_task_board_assign_complete_fail_and_facts_work() -> None:
    state = RuntimeSharedState.from_specs(
        [RuntimeAgentSpec("a")],
        [RuntimeTask("t1"), RuntimeTask("t2")],
    )

    assigned = state.assign_task("a", "t1")
    state.add_fact("doc", "ready", "a")
    completed = state.complete_task("t1", ["artifact.docx"])
    failed = state.fail_task("t2", "bad output")
    event = state.record_event("note", "recorded", agent_id="a", task_id="t2")

    assert assigned.assigned_agent_id == "a"
    assert completed.status == "completed"
    assert completed.artifact_refs == ["artifact.docx"]
    assert failed.status == "failed"
    assert state.shared_facts["doc"]["source_agent_id"] == "a"
    assert state.group_event_log == [event]
    assert state.per_agent_history["a"] == [event]


def test_runtime_step_calls_decision_executor_and_verifier() -> None:
    calls: list[str] = []

    def provider(agent: RuntimeAgentSpec, state: RuntimeSharedState) -> RuntimeActionDecision:
        calls.append("decision")
        return _decision(agent.agent_id, task_id="t1")

    def executor(decision: RuntimeActionDecision, state: RuntimeSharedState) -> RuntimeActionResult:
        calls.append("executor")
        return RuntimeActionResult(success=True)

    def verifier(
        decision: RuntimeActionDecision,
        result: RuntimeActionResult,
        state: RuntimeSharedState,
    ) -> bool:
        calls.append("verifier")
        return True

    runtime = AutonomousMultiAgentRuntime(
        runtime_id="step",
        agents=[RuntimeAgentSpec("a")],
        tasks=[RuntimeTask("t1")],
        decision_provider=provider,
        action_executor=executor,
        verifier=verifier,
    )

    result = runtime.step()

    assert result.status == "success"
    assert calls == ["decision", "executor", "verifier"]
    assert runtime.shared_state.tasks["t1"].status == "completed"


def test_runtime_run_stops_when_all_tasks_terminal() -> None:
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="all_done",
        agents=[RuntimeAgentSpec("a")],
        tasks=[RuntimeTask("t1")],
        decision_provider=lambda agent, state: _decision(agent.agent_id, task_id="t1"),
        action_executor=_success_executor,
    )

    summary = runtime.run().to_dict()

    assert summary["stop_reason"] == RuntimeStopReason.ALL_TASKS_TERMINAL.value
    assert summary["task_counts"]["completed"] == 1


def test_max_ticks_stop_works() -> None:
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="max_ticks",
        agents=[RuntimeAgentSpec("a")],
        policy=RuntimePolicy(max_ticks=2, idle_tick_limit=10, stop_when_all_tasks_terminal=False),
        decision_provider=lambda agent, state: None,
    )

    summary = runtime.run().to_dict()

    assert summary["tick_count"] == 2
    assert summary["stop_reason"] == RuntimeStopReason.MAX_TICKS_REACHED.value


def test_max_actions_total_stop_works() -> None:
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="max_actions",
        agents=[RuntimeAgentSpec("a")],
        policy=RuntimePolicy(max_actions_total=2, max_ticks=10, stop_when_all_tasks_terminal=False),
        decision_provider=lambda agent, state: _decision(agent.agent_id),
        action_executor=_success_executor,
    )

    summary = runtime.run().to_dict()

    assert summary["action_count"] == 2
    assert summary["stop_reason"] == RuntimeStopReason.MAX_ACTIONS_TOTAL_REACHED.value


def test_idle_tick_limit_stop_works() -> None:
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="idle",
        agents=[RuntimeAgentSpec("a")],
        policy=RuntimePolicy(idle_tick_limit=2, max_ticks=10, stop_when_all_tasks_terminal=False),
        decision_provider=lambda agent, state: None,
    )

    summary = runtime.run().to_dict()

    assert summary["tick_count"] == 2
    assert summary["stop_reason"] == RuntimeStopReason.IDLE_LIMIT_REACHED.value


def test_task_retry_works() -> None:
    attempts = 0

    def executor(decision: RuntimeActionDecision, state: RuntimeSharedState) -> RuntimeActionResult:
        nonlocal attempts
        attempts += 1
        if attempts == 1:
            return RuntimeActionResult(success=False, error_type="temporary", error_message="try again")
        return RuntimeActionResult(success=True)

    runtime = AutonomousMultiAgentRuntime(
        runtime_id="retry",
        agents=[RuntimeAgentSpec("a")],
        tasks=[RuntimeTask("t1")],
        policy=RuntimePolicy(max_retries_per_task=1),
        decision_provider=lambda agent, state: _decision(agent.agent_id, task_id="t1"),
        action_executor=executor,
    )

    first = runtime.step()
    second = runtime.step()

    assert first.status == "failed"
    assert second.status == "success"
    assert runtime.shared_state.retry_counters["t1"] == 1
    assert runtime.shared_state.tasks["t1"].status == "completed"


def test_task_fails_after_retries_exhausted() -> None:
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="fail",
        agents=[RuntimeAgentSpec("a")],
        tasks=[RuntimeTask("t1")],
        policy=RuntimePolicy(max_retries_per_task=0),
        decision_provider=lambda agent, state: _decision(agent.agent_id, task_id="t1"),
        action_executor=lambda decision, state: RuntimeActionResult(
            success=False,
            error_type="bad_action",
            error_message="nope",
        ),
    )

    result = runtime.step()

    assert result.status == "failed"
    assert runtime.shared_state.tasks["t1"].status == "failed"
    assert runtime.shared_state.tasks["t1"].failure_reason == "nope"


def test_agent_quarantine_after_repeated_failures() -> None:
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="quarantine",
        agents=[RuntimeAgentSpec("a")],
        tasks=[RuntimeTask("t1")],
        policy=RuntimePolicy(max_retries_per_task=5, max_agent_failures=2),
        decision_provider=lambda agent, state: _decision(agent.agent_id, task_id="t1"),
        action_executor=lambda decision, state: RuntimeActionResult(
            success=False,
            error_type="bad_action",
            error_message="nope",
        ),
    )

    runtime.step()
    runtime.step()

    assert "a" in runtime.shared_state.quarantined_agents
    assert runtime.shared_state.agents["a"].status == "quarantined"


def test_resource_lock_acquire_and_release_work() -> None:
    state = RuntimeSharedState.from_specs([RuntimeAgentSpec("a"), RuntimeAgentSpec("b")], [])

    assert state.acquire_lock("doc", "a") is True
    assert state.acquire_lock("doc", "b") is False
    assert state.release_lock("doc", "b") is False
    assert state.release_lock("doc", "a") is True
    assert state.acquire_lock("doc", "b") is True


def test_unavailable_lock_blocks_action_without_executor_call() -> None:
    state = RuntimeSharedState.from_specs([RuntimeAgentSpec("a"), RuntimeAgentSpec("b")], [RuntimeTask("t1")])
    assert state.acquire_lock("doc", "b") is True
    executor_called = False

    def executor(decision: RuntimeActionDecision, shared: RuntimeSharedState) -> RuntimeActionResult:
        nonlocal executor_called
        executor_called = True
        return RuntimeActionResult(success=True)

    runtime = AutonomousMultiAgentRuntime(
        runtime_id="blocked_lock",
        shared_state=state,
        policy=RuntimePolicy(idle_tick_limit=5),
        decision_provider=lambda agent, shared: RuntimeActionDecision(
            agent_id=agent.agent_id,
            task_id="t1",
            action_type="files",
            action_name="append_file",
            resource_locks=("doc",),
        ),
        action_executor=executor,
    )

    result = runtime.step()

    assert result.status == "blocked"
    assert executor_called is False
    assert state.resource_locks == {"doc": "b"}
    assert state.tasks["t1"].status == "running"


def test_virtual_environment_metadata_appears_in_summary() -> None:
    env = RuntimeVirtualEnvironment(
        environment_id="env1",
        workspace=RuntimeWorkspace(
            workspace_root="artifacts/runtime_workspace",
            per_agent_workspaces={"a": "artifacts/runtime_workspace/a"},
            reset_policy="per_run",
        ),
        allowed_resource_namespaces=("files", "browser"),
        metadata={"scenario": "fake"},
    )
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="env_summary",
        agents=[RuntimeAgentSpec("a")],
        virtual_environment=env,
    )

    summary = runtime.to_summary()

    assert summary["virtual_environment"]["environment_id"] == "env1"
    assert summary["virtual_environment"]["workspace"]["reset_policy"] == "per_run"
    assert summary["virtual_environment"]["allowed_resource_namespaces"] == ["files", "browser"]


def test_browser_action_rejected_when_browser_namespace_disabled() -> None:
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="browser_reject",
        agents=[RuntimeAgentSpec("a")],
        tasks=[RuntimeTask("t1")],
        policy=RuntimePolicy(max_retries_per_task=0),
        virtual_environment=RuntimeVirtualEnvironment(
            environment_id="env",
            workspace=RuntimeWorkspace("runtime/workspace"),
            allowed_resource_namespaces=("files",),
        ),
        decision_provider=lambda agent, state: RuntimeActionDecision(
            agent_id=agent.agent_id,
            task_id="t1",
            action_type="browser",
            action_name="browser_open_url",
        ),
    )

    result = runtime.step()

    assert result.status == "failed"
    assert result.action_result is not None
    assert result.action_result.error_type == "browser_namespace_disabled"
    assert runtime.shared_state.tasks["t1"].status == "failed"


def test_browser_action_accepted_when_namespace_enabled_and_fake_executor_succeeds() -> None:
    executor_calls: list[str] = []
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="browser_accept",
        agents=[RuntimeAgentSpec("a")],
        tasks=[RuntimeTask("t1")],
        virtual_environment=RuntimeVirtualEnvironment(
            environment_id="env",
            workspace=RuntimeWorkspace("runtime/workspace"),
            allowed_resource_namespaces=("files", "browser"),
        ),
        decision_provider=lambda agent, state: RuntimeActionDecision(
            agent_id=agent.agent_id,
            task_id="t1",
            action_type="browser",
            action_name="browser_open_url",
            parameters={"url": "http://localhost:8080"},
        ),
        action_executor=lambda decision, state: executor_calls.append(decision.action_name)
        or RuntimeActionResult(success=True),
    )

    result = runtime.step()

    assert result.status == "success"
    assert executor_calls == ["browser_open_url"]
    assert runtime.shared_state.tasks["t1"].status == "completed"


def test_summary_is_json_serializable() -> None:
    runtime = AutonomousMultiAgentRuntime(
        runtime_id="json",
        agents=[RuntimeAgentSpec("a")],
        tasks=[RuntimeTask("t1")],
        decision_provider=lambda agent, state: _decision(agent.agent_id, task_id="t1"),
        action_executor=_success_executor,
    )

    summary = runtime.run().to_dict()

    assert json.loads(json.dumps(summary))["schema_version"] == "autonomous_multi_agent_runtime_summary_v1"


def test_runtime_uses_injected_fakes_and_does_not_launch_real_runtime() -> None:
    calls = {"decision": 0, "executor": 0}

    def provider(agent: RuntimeAgentSpec, state: RuntimeSharedState) -> RuntimeActionDecision:
        calls["decision"] += 1
        return _decision(agent.agent_id, task_id="t1")

    def executor(decision: RuntimeActionDecision, state: RuntimeSharedState) -> RuntimeActionResult:
        calls["executor"] += 1
        return RuntimeActionResult(success=True, metadata={"fake_executor": True})

    runtime = AutonomousMultiAgentRuntime(
        runtime_id="fake_only",
        agents=[RuntimeAgentSpec("a")],
        tasks=[RuntimeTask("t1")],
        decision_provider=provider,
        action_executor=executor,
    )

    result = runtime.step()

    assert result.action_result is not None
    assert result.action_result.metadata == {"fake_executor": True}
    assert calls == {"decision": 1, "executor": 1}
