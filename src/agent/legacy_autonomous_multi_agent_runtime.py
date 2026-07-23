from __future__ import annotations

from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from enum import StrEnum
from pathlib import PurePosixPath
from typing import Any, Literal


TaskStatus = Literal["pending", "running", "completed", "failed", "blocked"]
AgentStatus = Literal["ready", "blocked", "completed", "quarantined"]
SchedulerMode = Literal["round_robin", "priority_then_round_robin"]
ResetPolicy = Literal["never", "per_run", "per_agent"]

TERMINAL_TASK_STATUSES = {"completed", "failed", "blocked"}
BROWSER_RUNTIME_ACTION_NAMES = {
    "browser_open_url",
    "browser_search",
    "browser_click",
    "browser_extract_text",
    "browser_fill",
    "browser_submit",
    "browser_wait",
    "browser_snapshot",
    "open_url",
    "search_web",
    "read_page_summary",
    "capture_page_snapshot",
}


class RuntimeStopReason(StrEnum):
    ALL_TASKS_TERMINAL = "all_tasks_terminal"
    MAX_TICKS_REACHED = "max_ticks_reached"
    MAX_ACTIONS_TOTAL_REACHED = "max_actions_total_reached"
    IDLE_LIMIT_REACHED = "idle_limit_reached"
    FAILURE_LIMIT_REACHED = "failure_limit_reached"
    NO_RUNNABLE_AGENTS = "no_runnable_agents"
    MANUAL_STOP_REQUESTED = "manual_stop_requested"


@dataclass
class RuntimeAgentSpec:
    agent_id: str
    role: str = ""
    priority: int = 0
    status: AgentStatus = "ready"
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass
class RuntimeTask:
    task_id: str
    description: str = ""
    status: TaskStatus = "pending"
    priority: int = 0
    assigned_agent_id: str | None = None
    artifact_refs: list[str] = field(default_factory=list)
    failure_reason: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def is_terminal(self) -> bool:
        return self.status in TERMINAL_TASK_STATUSES


@dataclass(frozen=True)
class RuntimeActionDecision:
    agent_id: str
    action_type: str
    action_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    task_id: str | None = None
    resource_locks: tuple[str, ...] = ()
    release_locks_on_completion: bool = True
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeActionResult:
    success: bool
    output: Any | None = None
    error_type: str | None = None
    error_message: str | None = None
    artifact_refs: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class RuntimeEvent:
    tick: int
    event_type: str
    message: str
    agent_id: str | None = None
    task_id: str | None = None
    severity: str = "info"
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "event_type": self.event_type,
            "message": self.message,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "severity": self.severity,
            "metadata": _jsonable(self.metadata),
        }


@dataclass
class RuntimeWorkspace:
    workspace_root: str
    per_agent_workspaces: dict[str, str] = field(default_factory=dict)
    reset_policy: ResetPolicy = "never"

    def __post_init__(self) -> None:
        self.workspace_root = _safe_relative_path(self.workspace_root, "workspace_root")
        self.per_agent_workspaces = {
            str(agent_id): _safe_relative_path(path, f"workspace for {agent_id}")
            for agent_id, path in self.per_agent_workspaces.items()
        }
        if self.reset_policy not in {"never", "per_run", "per_agent"}:
            raise ValueError(f"Invalid reset_policy: {self.reset_policy}")

    def to_dict(self) -> dict[str, Any]:
        return {
            "workspace_root": self.workspace_root,
            "per_agent_workspaces": dict(self.per_agent_workspaces),
            "reset_policy": self.reset_policy,
        }


@dataclass
class RuntimeVirtualEnvironment:
    environment_id: str
    workspace: RuntimeWorkspace
    allowed_resource_namespaces: tuple[str, ...] = ("files", "office", "network")
    metadata: dict[str, Any] = field(default_factory=dict)

    def snapshot_manifest(self) -> dict[str, Any]:
        return {
            "schema_version": "runtime_virtual_environment_manifest_v1",
            "environment_id": self.environment_id,
            "workspace": self.workspace.to_dict(),
            "allowed_resource_namespaces": list(self.allowed_resource_namespaces),
            "metadata": _jsonable(self.metadata),
        }


@dataclass
class RuntimePolicy:
    scheduler: SchedulerMode = "round_robin"
    max_ticks: int = 100
    max_actions_total: int = 100
    max_actions_per_agent: int = 20
    idle_tick_limit: int = 5
    max_failures_total: int = 10
    max_retries_per_task: int = 1
    max_agent_failures: int = 3
    stop_when_all_tasks_terminal: bool = True
    stop_when_no_runnable_agents: bool = True

    def __post_init__(self) -> None:
        if self.scheduler not in {"round_robin", "priority_then_round_robin"}:
            raise ValueError(f"Invalid scheduler: {self.scheduler}")
        for name in (
            "max_ticks",
            "max_actions_total",
            "max_actions_per_agent",
            "idle_tick_limit",
            "max_failures_total",
            "max_retries_per_task",
            "max_agent_failures",
        ):
            if getattr(self, name) < 0:
                raise ValueError(f"{name} must be >= 0.")


@dataclass
class RuntimeSharedState:
    agents: dict[str, RuntimeAgentSpec] = field(default_factory=dict)
    tasks: dict[str, RuntimeTask] = field(default_factory=dict)
    shared_facts: dict[str, Any] = field(default_factory=dict)
    produced_artifacts: list[str] = field(default_factory=list)
    per_agent_history: dict[str, list[RuntimeEvent]] = field(default_factory=dict)
    group_event_log: list[RuntimeEvent] = field(default_factory=list)
    resource_locks: dict[str, str] = field(default_factory=dict)
    retry_counters: dict[str, int] = field(default_factory=dict)
    quarantined_agents: set[str] = field(default_factory=set)
    agent_failure_counts: dict[str, int] = field(default_factory=dict)
    agent_action_counts: dict[str, int] = field(default_factory=dict)
    task_assignments: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_specs(
        cls,
        agents: list[RuntimeAgentSpec] | dict[str, RuntimeAgentSpec],
        tasks: list[RuntimeTask] | dict[str, RuntimeTask],
    ) -> RuntimeSharedState:
        agent_map = agents if isinstance(agents, dict) else {a.agent_id: a for a in agents}
        task_map = tasks if isinstance(tasks, dict) else {t.task_id: t for t in tasks}
        return cls(agents=dict(agent_map), tasks=dict(task_map))

    def assign_task(self, agent_id: str, task_id: str) -> RuntimeTask:
        self._require_agent(agent_id)
        task = self._require_task(task_id)
        task.status = "running"
        task.assigned_agent_id = agent_id
        self.task_assignments[agent_id] = task_id
        return task

    def complete_task(self, task_id: str, artifact_refs: list[str] | tuple[str, ...] = ()) -> RuntimeTask:
        task = self._require_task(task_id)
        task.status = "completed"
        task.failure_reason = None
        task.artifact_refs.extend(str(ref) for ref in artifact_refs)
        for ref in artifact_refs:
            if ref not in self.produced_artifacts:
                self.produced_artifacts.append(str(ref))
        if task.assigned_agent_id:
            self.task_assignments.pop(task.assigned_agent_id, None)
        return task

    def fail_task(self, task_id: str, reason: str) -> RuntimeTask:
        task = self._require_task(task_id)
        task.status = "failed"
        task.failure_reason = reason
        if task.assigned_agent_id:
            self.task_assignments.pop(task.assigned_agent_id, None)
        return task

    def add_fact(self, key: str, value: Any, source_agent_id: str | None = None) -> None:
        self.shared_facts[key] = {
            "value": _jsonable(value),
            "source_agent_id": source_agent_id,
        }

    def record_event(
        self,
        event_type: str,
        message: str,
        *,
        tick: int = 0,
        agent_id: str | None = None,
        task_id: str | None = None,
        severity: str = "info",
        metadata: Mapping[str, Any] | None = None,
    ) -> RuntimeEvent:
        event = RuntimeEvent(
            tick=tick,
            event_type=event_type,
            message=message,
            agent_id=agent_id,
            task_id=task_id,
            severity=severity,
            metadata=dict(metadata or {}),
        )
        self.group_event_log.append(event)
        if agent_id:
            self.per_agent_history.setdefault(agent_id, []).append(event)
        return event

    def acquire_lock(self, resource_id: str, agent_id: str) -> bool:
        self._require_agent(agent_id)
        owner = self.resource_locks.get(resource_id)
        if owner is not None and owner != agent_id:
            return False
        self.resource_locks[resource_id] = agent_id
        return True

    def release_lock(self, resource_id: str, agent_id: str) -> bool:
        if self.resource_locks.get(resource_id) != agent_id:
            return False
        del self.resource_locks[resource_id]
        return True

    def _require_agent(self, agent_id: str) -> RuntimeAgentSpec:
        try:
            return self.agents[agent_id]
        except KeyError as exc:
            raise ValueError(f"Unknown runtime agent: {agent_id}") from exc

    def _require_task(self, task_id: str) -> RuntimeTask:
        try:
            return self.tasks[task_id]
        except KeyError as exc:
            raise ValueError(f"Unknown runtime task: {task_id}") from exc


@dataclass(frozen=True)
class RuntimeStepResult:
    tick: int
    status: str
    agent_id: str | None = None
    task_id: str | None = None
    decision: RuntimeActionDecision | None = None
    action_result: RuntimeActionResult | None = None
    events: tuple[RuntimeEvent, ...] = ()
    stop_reason: RuntimeStopReason | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "tick": self.tick,
            "status": self.status,
            "agent_id": self.agent_id,
            "task_id": self.task_id,
            "decision": _dataclass_to_dict(self.decision),
            "action_result": _dataclass_to_dict(self.action_result),
            "events": [event.to_dict() for event in self.events],
            "stop_reason": self.stop_reason.value if self.stop_reason else None,
        }


@dataclass(frozen=True)
class RuntimeSummary:
    payload: dict[str, Any]

    def to_dict(self) -> dict[str, Any]:
        return dict(self.payload)


DecisionProvider = Callable[[RuntimeAgentSpec, RuntimeSharedState], RuntimeActionDecision | None]
ActionExecutor = Callable[[RuntimeActionDecision, RuntimeSharedState], RuntimeActionResult]
ActionVerifier = Callable[[RuntimeActionDecision, RuntimeActionResult, RuntimeSharedState], bool]


class AutonomousMultiAgentRuntime:
    def __init__(
        self,
        *,
        runtime_id: str,
        agents: list[RuntimeAgentSpec] | dict[str, RuntimeAgentSpec] | None = None,
        tasks: list[RuntimeTask] | dict[str, RuntimeTask] | None = None,
        shared_state: RuntimeSharedState | None = None,
        policy: RuntimePolicy | None = None,
        virtual_environment: RuntimeVirtualEnvironment | None = None,
        decision_provider: DecisionProvider | None = None,
        action_executor: ActionExecutor | None = None,
        verifier: ActionVerifier | None = None,
    ) -> None:
        self.runtime_id = runtime_id
        self.policy = policy or RuntimePolicy()
        self.shared_state = shared_state or RuntimeSharedState.from_specs(agents or [], tasks or [])
        self.virtual_environment = virtual_environment or RuntimeVirtualEnvironment(
            environment_id=f"{runtime_id}_environment",
            workspace=RuntimeWorkspace(workspace_root="artifacts/runtime_workspace"),
        )
        self.decision_provider = decision_provider or _no_decision_provider
        self.action_executor = action_executor or _no_op_executor
        self.verifier = verifier or _default_verifier
        self.tick_count = 0
        self.action_count = 0
        self.failure_count = 0
        self.idle_tick_count = 0
        self.stop_reason: RuntimeStopReason | None = None
        self.manual_stop_requested = False
        self._round_robin_cursor = 0

    def request_stop(self) -> None:
        self.manual_stop_requested = True

    def step(self) -> RuntimeStepResult:
        pre_stop = self._pre_step_stop_reason()
        if pre_stop is not None:
            return self._stop(pre_stop, status="stopped")

        self.tick_count += 1
        agent = self._choose_next_agent()
        if agent is None:
            event = self.shared_state.record_event(
                "runtime_idle",
                "No runnable agent was available.",
                tick=self.tick_count,
                severity="warning",
            )
            if self.policy.stop_when_no_runnable_agents:
                return self._stop(RuntimeStopReason.NO_RUNNABLE_AGENTS, status="idle", events=(event,))
            return self._idle_result((event,))

        task = self._ensure_agent_task(agent)
        if task is None and self.shared_state.tasks:
            event = self.shared_state.record_event(
                "runtime_idle",
                "Runnable agent had no available task.",
                tick=self.tick_count,
                agent_id=agent.agent_id,
            )
            return self._idle_result((event,), agent_id=agent.agent_id)

        try:
            decision = self.decision_provider(agent, self.shared_state)
        except Exception as exc:  # noqa: BLE001 - provider failures are runtime data.
            result = RuntimeActionResult(
                success=False,
                error_type="decision_provider_error",
                error_message=str(exc),
            )
            events = self._handle_failure(agent, task, result, decision=None)
            return self._post_action_result(
                RuntimeStepResult(
                    tick=self.tick_count,
                    status="failed",
                    agent_id=agent.agent_id,
                    task_id=task.task_id if task else None,
                    action_result=result,
                    events=tuple(events),
                )
            )

        if decision is None:
            event = self.shared_state.record_event(
                "runtime_idle",
                "Decision provider returned no action.",
                tick=self.tick_count,
                agent_id=agent.agent_id,
                task_id=task.task_id if task else None,
            )
            return self._idle_result((event,), agent_id=agent.agent_id, task_id=task.task_id if task else None)

        validation_failure = self._validate_decision(decision, agent, task)
        if validation_failure is not None:
            events = self._handle_failure(agent, task, validation_failure, decision=decision)
            return self._post_action_result(
                RuntimeStepResult(
                    tick=self.tick_count,
                    status="failed",
                    agent_id=agent.agent_id,
                    task_id=decision.task_id or (task.task_id if task else None),
                    decision=decision,
                    action_result=validation_failure,
                    events=tuple(events),
                )
            )

        acquired_locks: list[str] = []
        unavailable = self._acquire_decision_locks(decision, acquired_locks)
        if unavailable is not None:
            event = self.shared_state.record_event(
                "action_blocked",
                f"Resource lock is unavailable: {unavailable}",
                tick=self.tick_count,
                agent_id=agent.agent_id,
                task_id=decision.task_id or (task.task_id if task else None),
                severity="warning",
                metadata={"resource_id": unavailable},
            )
            for resource_id in acquired_locks:
                self.shared_state.release_lock(resource_id, agent.agent_id)
            return self._idle_result(
                (event,),
                agent_id=agent.agent_id,
                task_id=decision.task_id or (task.task_id if task else None),
                status="blocked",
            )

        try:
            result = self.action_executor(decision, self.shared_state)
        except Exception as exc:  # noqa: BLE001 - executor failures are runtime data.
            result = RuntimeActionResult(
                success=False,
                error_type="action_executor_error",
                error_message=str(exc),
            )
        finally:
            if decision.release_locks_on_completion:
                for resource_id in acquired_locks:
                    self.shared_state.release_lock(resource_id, agent.agent_id)

        self.action_count += 1
        self.shared_state.agent_action_counts[agent.agent_id] = (
            self.shared_state.agent_action_counts.get(agent.agent_id, 0) + 1
        )

        verified = False
        if result.success:
            try:
                verified = bool(self.verifier(decision, result, self.shared_state))
            except Exception as exc:  # noqa: BLE001 - verifier failures are runtime data.
                result = RuntimeActionResult(
                    success=False,
                    error_type="verifier_error",
                    error_message=str(exc),
                    artifact_refs=result.artifact_refs,
                    metadata=result.metadata,
                )
        if result.success and not verified:
            result = RuntimeActionResult(
                success=False,
                error_type="verification_failed",
                error_message="Runtime verifier rejected the action result.",
                artifact_refs=result.artifact_refs,
                metadata=result.metadata,
            )

        if result.success:
            events = self._handle_success(agent, task, result, decision)
            status = "success"
        else:
            events = self._handle_failure(agent, task, result, decision=decision)
            status = "failed"

        return self._post_action_result(
            RuntimeStepResult(
                tick=self.tick_count,
                status=status,
                agent_id=agent.agent_id,
                task_id=decision.task_id or (task.task_id if task else None),
                decision=decision,
                action_result=result,
                events=tuple(events),
            )
        )

    def run(self) -> RuntimeSummary:
        while self.stop_reason is None:
            self.step()
        return RuntimeSummary(self.to_summary())

    def to_summary(self) -> dict[str, Any]:
        return {
            "schema_version": "autonomous_multi_agent_runtime_summary_v1",
            "runtime_id": self.runtime_id,
            "status": "stopped" if self.stop_reason else "running",
            "stop_reason": self.stop_reason.value if self.stop_reason else None,
            "tick_count": self.tick_count,
            "action_count": self.action_count,
            "task_counts": _counts(task.status for task in self.shared_state.tasks.values()),
            "agent_counts": self._agent_counts(),
            "failure_counts": {
                "total": self.failure_count,
                "by_agent": dict(self.shared_state.agent_failure_counts),
                "by_task": dict(self.shared_state.retry_counters),
            },
            "events": [event.to_dict() for event in self.shared_state.group_event_log],
            "artifacts": list(self.shared_state.produced_artifacts),
            "resource_locks_final": dict(self.shared_state.resource_locks),
            "virtual_environment": self.virtual_environment.snapshot_manifest(),
        }

    def _pre_step_stop_reason(self) -> RuntimeStopReason | None:
        if self.manual_stop_requested:
            return RuntimeStopReason.MANUAL_STOP_REQUESTED
        if self.policy.stop_when_all_tasks_terminal and self._all_tasks_terminal():
            return RuntimeStopReason.ALL_TASKS_TERMINAL
        if self.tick_count >= self.policy.max_ticks:
            return RuntimeStopReason.MAX_TICKS_REACHED
        if self.action_count >= self.policy.max_actions_total:
            return RuntimeStopReason.MAX_ACTIONS_TOTAL_REACHED
        if self.failure_count >= self.policy.max_failures_total:
            return RuntimeStopReason.FAILURE_LIMIT_REACHED
        if self.idle_tick_count >= self.policy.idle_tick_limit:
            return RuntimeStopReason.IDLE_LIMIT_REACHED
        return None

    def _post_action_result(self, result: RuntimeStepResult) -> RuntimeStepResult:
        stop_reason = self._pre_step_stop_reason()
        if stop_reason is not None:
            self.stop_reason = stop_reason
            return RuntimeStepResult(
                tick=result.tick,
                status=result.status,
                agent_id=result.agent_id,
                task_id=result.task_id,
                decision=result.decision,
                action_result=result.action_result,
                events=result.events,
                stop_reason=stop_reason,
            )
        return result

    def _stop(
        self,
        reason: RuntimeStopReason,
        *,
        status: str,
        events: tuple[RuntimeEvent, ...] = (),
    ) -> RuntimeStepResult:
        self.stop_reason = reason
        if not events:
            event = self.shared_state.record_event(
                "runtime_stopped",
                f"Runtime stopped: {reason.value}",
                tick=self.tick_count,
                metadata={"stop_reason": reason.value},
            )
            events = (event,)
        return RuntimeStepResult(
            tick=self.tick_count,
            status=status,
            events=events,
            stop_reason=reason,
        )

    def _idle_result(
        self,
        events: tuple[RuntimeEvent, ...],
        *,
        agent_id: str | None = None,
        task_id: str | None = None,
        status: str = "idle",
    ) -> RuntimeStepResult:
        self.idle_tick_count += 1
        stop_reason = self._pre_step_stop_reason()
        if stop_reason is not None:
            self.stop_reason = stop_reason
        return RuntimeStepResult(
            tick=self.tick_count,
            status=status,
            agent_id=agent_id,
            task_id=task_id,
            events=events,
            stop_reason=stop_reason,
        )

    def _choose_next_agent(self) -> RuntimeAgentSpec | None:
        agents = [agent for agent in self.shared_state.agents.values() if self._is_agent_runnable(agent)]
        if not agents:
            return None
        ordered_ids = list(self.shared_state.agents)
        if self.policy.scheduler == "priority_then_round_robin":
            max_priority = max(agent.priority for agent in agents)
            eligible = [agent for agent in agents if agent.priority == max_priority]
        else:
            eligible = agents
        eligible_ids = {agent.agent_id for agent in eligible}
        for offset in range(len(ordered_ids)):
            index = (self._round_robin_cursor + offset) % len(ordered_ids)
            agent_id = ordered_ids[index]
            if agent_id in eligible_ids:
                self._round_robin_cursor = (index + 1) % len(ordered_ids)
                return self.shared_state.agents[agent_id]
        return eligible[0]

    def _is_agent_runnable(self, agent: RuntimeAgentSpec) -> bool:
        if agent.status in {"blocked", "completed", "quarantined"}:
            return False
        if agent.agent_id in self.shared_state.quarantined_agents:
            return False
        return self.shared_state.agent_action_counts.get(agent.agent_id, 0) < self.policy.max_actions_per_agent

    def _ensure_agent_task(self, agent: RuntimeAgentSpec) -> RuntimeTask | None:
        current_id = self.shared_state.task_assignments.get(agent.agent_id)
        if current_id:
            current = self.shared_state.tasks.get(current_id)
            if current is not None and current.status == "running":
                return current
        pending = [
            task
            for task in self.shared_state.tasks.values()
            if task.status == "pending" and task.assigned_agent_id in {None, agent.agent_id}
        ]
        if not pending:
            return None
        task = sorted(pending, key=lambda item: (-item.priority, item.task_id))[0]
        return self.shared_state.assign_task(agent.agent_id, task.task_id)

    def _validate_decision(
        self,
        decision: RuntimeActionDecision,
        agent: RuntimeAgentSpec,
        task: RuntimeTask | None,
    ) -> RuntimeActionResult | None:
        if decision.agent_id != agent.agent_id:
            return _failure(
                "invalid_action_agent",
                f"Decision agent_id '{decision.agent_id}' does not match scheduled agent '{agent.agent_id}'.",
            )
        if decision.task_id is not None and decision.task_id not in self.shared_state.tasks:
            return _failure("unknown_task", f"Decision referenced unknown task '{decision.task_id}'.")
        if task is not None and decision.task_id is not None and decision.task_id != task.task_id:
            return _failure(
                "task_mismatch",
                f"Decision task_id '{decision.task_id}' does not match assigned task '{task.task_id}'.",
            )
        if decision.action_type == "browser":
            namespaces = set(self.virtual_environment.allowed_resource_namespaces)
            if "browser" not in namespaces:
                return _failure(
                    "browser_namespace_disabled",
                    "Browser runtime namespace is not enabled for this virtual environment.",
                )
            if decision.action_name not in BROWSER_RUNTIME_ACTION_NAMES:
                return _failure(
                    "unknown_browser_action",
                    f"Browser action is not registered for runtime scheduling: {decision.action_name}",
                )
        return None

    def _acquire_decision_locks(self, decision: RuntimeActionDecision, acquired_locks: list[str]) -> str | None:
        for resource_id in decision.resource_locks:
            if not self.shared_state.acquire_lock(resource_id, decision.agent_id):
                return resource_id
            acquired_locks.append(resource_id)
        return None

    def _handle_success(
        self,
        agent: RuntimeAgentSpec,
        task: RuntimeTask | None,
        result: RuntimeActionResult,
        decision: RuntimeActionDecision,
    ) -> list[RuntimeEvent]:
        self.idle_tick_count = 0
        task_id = decision.task_id or (task.task_id if task else None)
        if task_id:
            self.shared_state.complete_task(task_id, result.artifact_refs)
        for artifact_ref in result.artifact_refs:
            if artifact_ref not in self.shared_state.produced_artifacts:
                self.shared_state.produced_artifacts.append(artifact_ref)
        event = self.shared_state.record_event(
            "action_succeeded",
            "Runtime action completed successfully.",
            tick=self.tick_count,
            agent_id=agent.agent_id,
            task_id=task_id,
            metadata={
                "action_type": decision.action_type,
                "action_name": decision.action_name,
                "artifact_refs": list(result.artifact_refs),
            },
        )
        return [event]

    def _handle_failure(
        self,
        agent: RuntimeAgentSpec,
        task: RuntimeTask | None,
        result: RuntimeActionResult,
        *,
        decision: RuntimeActionDecision | None,
    ) -> list[RuntimeEvent]:
        self.idle_tick_count = 0
        self.failure_count += 1
        self.shared_state.agent_failure_counts[agent.agent_id] = (
            self.shared_state.agent_failure_counts.get(agent.agent_id, 0) + 1
        )
        if self.shared_state.agent_failure_counts[agent.agent_id] >= self.policy.max_agent_failures:
            self.shared_state.quarantined_agents.add(agent.agent_id)
            agent.status = "quarantined"

        task_id = (decision.task_id if decision else None) or (task.task_id if task else None)
        if task_id:
            retries = self.shared_state.retry_counters.get(task_id, 0) + 1
            self.shared_state.retry_counters[task_id] = retries
            if retries <= self.policy.max_retries_per_task:
                retry_task = self.shared_state.tasks[task_id]
                retry_task.status = "pending"
                retry_task.assigned_agent_id = None
                self.shared_state.task_assignments.pop(agent.agent_id, None)
                task_status = "pending_retry"
            else:
                reason = result.error_message or result.error_type or "runtime_action_failed"
                self.shared_state.fail_task(task_id, reason)
                task_status = "failed"
        else:
            task_status = "none"

        event = self.shared_state.record_event(
            "action_failed",
            result.error_message or result.error_type or "Runtime action failed.",
            tick=self.tick_count,
            agent_id=agent.agent_id,
            task_id=task_id,
            severity="error",
            metadata={
                "action_type": decision.action_type if decision else None,
                "action_name": decision.action_name if decision else None,
                "error_type": result.error_type,
                "task_status": task_status,
                "agent_quarantined": agent.agent_id in self.shared_state.quarantined_agents,
            },
        )
        return [event]

    def _all_tasks_terminal(self) -> bool:
        return bool(self.shared_state.tasks) and all(task.is_terminal() for task in self.shared_state.tasks.values())

    def _agent_counts(self) -> dict[str, int]:
        statuses = _counts(agent.status for agent in self.shared_state.agents.values())
        statuses["total"] = len(self.shared_state.agents)
        statuses["quarantined"] = len(self.shared_state.quarantined_agents)
        statuses["runnable"] = sum(1 for agent in self.shared_state.agents.values() if self._is_agent_runnable(agent))
        return statuses


def _no_decision_provider(agent: RuntimeAgentSpec, state: RuntimeSharedState) -> RuntimeActionDecision | None:
    return None


def _no_op_executor(decision: RuntimeActionDecision, state: RuntimeSharedState) -> RuntimeActionResult:
    return RuntimeActionResult(success=True)


def _default_verifier(
    decision: RuntimeActionDecision,
    result: RuntimeActionResult,
    state: RuntimeSharedState,
) -> bool:
    return result.success


def _failure(error_type: str, error_message: str) -> RuntimeActionResult:
    return RuntimeActionResult(success=False, error_type=error_type, error_message=error_message)


def _safe_relative_path(value: str, label: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        raise ValueError(f"{label} must be non-empty.")
    path = PurePosixPath(normalized)
    if path.is_absolute() or path.drive or ".." in path.parts:
        raise ValueError(f"{label} must be a safe relative path.")
    return path.as_posix()


def _counts(values: Any) -> dict[str, int]:
    counts: dict[str, int] = {}
    for value in values:
        key = str(value)
        counts[key] = counts.get(key, 0) + 1
    return counts


def _dataclass_to_dict(value: Any) -> Any:
    if value is None:
        return None
    if isinstance(value, RuntimeActionDecision):
        return {
            "agent_id": value.agent_id,
            "action_type": value.action_type,
            "action_name": value.action_name,
            "parameters": _jsonable(value.parameters),
            "task_id": value.task_id,
            "resource_locks": list(value.resource_locks),
            "release_locks_on_completion": value.release_locks_on_completion,
            "metadata": _jsonable(value.metadata),
        }
    if isinstance(value, RuntimeActionResult):
        return {
            "success": value.success,
            "output": _jsonable(value.output),
            "error_type": value.error_type,
            "error_message": value.error_message,
            "artifact_refs": list(value.artifact_refs),
            "metadata": _jsonable(value.metadata),
        }
    return _jsonable(value)


def _jsonable(value: Any) -> Any:
    if isinstance(value, StrEnum):
        return value.value
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set):
        return [_jsonable(item) for item in value]
    if hasattr(value, "to_dict") and callable(value.to_dict):
        return value.to_dict()
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
