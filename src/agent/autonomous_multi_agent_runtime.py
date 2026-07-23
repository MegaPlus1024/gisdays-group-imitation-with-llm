from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Protocol
from urllib.parse import urlparse

from .llm_client import LocalLLMClient
from .schemas import NextAction
from .script_execution_bridge import (
    ScriptExecutionBridge,
    ScriptExecutionBridgeConfig,
)
from .script_registry import ScriptDescriptor, load_script_registry


AgentStatus = Literal["ready", "completed", "stopped", "quarantined"]
RuntimeStatus = Literal["running", "succeeded", "failed"]

CANONICAL_RUNTIME_SCHEMA_VERSION = "canonical_multi_agent_runtime_summary_v1"
CANONICAL_CONFIG_SCHEMA_VERSION = "canonical_multi_agent_runtime_config_v1"
CANONICAL_ARTICLE_TOOL_NAMES = (
    "browser_article_open",
    "browser_article_read",
    "browser_article_scroll",
    "browser_article_find",
    "browser_article_extract",
)
CANONICAL_COORDINATION_TOOL_NAMES = (
    "shared_publish_fact",
    "shared_read_fact",
    "finish",
)
LOCAL_MODEL_HOSTS = {"127.0.0.1", "localhost"}
_SAFE_IDENTIFIER_RE = re.compile(r"^[A-Za-z0-9][A-Za-z0-9_.-]{0,127}$")
_SENSITIVE_KEY_RE = re.compile(
    r"(?i)(?:^|[_-])(?:api[_-]?key|access[_-]?token|refresh[_-]?token|"
    r"auth(?:orization)?|password|passwd|secret|credential)(?:$|[_-])"
)
_SENSITIVE_ASSIGNMENT_RE = re.compile(
    r"(?i)\b(api[_-]?key|access[_-]?token|refresh[_-]?token|auth_token|"
    r"authorization|password|passwd|secret|credential)\b"
    r"(\s*[:=]\s*)([^\s,;]+)"
)
_BEARER_TOKEN_RE = re.compile(r"(?i)\b(Bearer)\s+[^\s,;]+")


@dataclass(frozen=True)
class AgentProfile:
    agent_id: str
    role: str
    goal: str
    allowed_tools: tuple[str, ...]
    resource_constraints: tuple[str, ...] = ()
    behavior_constraints: tuple[str, ...] = ()

    def __post_init__(self) -> None:
        _require_identifier(self.agent_id, "agent_id")
        _require_text(self.role, "role")
        _require_text(self.goal, "goal")
        if not self.allowed_tools:
            raise ValueError("allowed_tools must not be empty.")
        if len(self.allowed_tools) != len(set(self.allowed_tools)):
            raise ValueError("allowed_tools must not contain duplicates.")
        for tool_name in self.allowed_tools:
            _require_identifier(tool_name, "allowed tool")
        if "browser_click" in self.allowed_tools:
            raise ValueError("browser_click is not part of the canonical runtime.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": _sanitize_text(self.role),
            "goal": _sanitize_text(self.goal),
            "allowed_tools": list(self.allowed_tools),
            "resource_constraints": _sanitize_value(self.resource_constraints),
            "behavior_constraints": _sanitize_value(self.behavior_constraints),
        }


@dataclass(frozen=True)
class Action:
    tool_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    reason: str = ""
    expected_result: str = ""

    def __post_init__(self) -> None:
        _require_identifier(self.tool_name, "tool_name")
        if self.tool_name == "browser_click":
            raise ValueError("browser_click is not part of the canonical runtime.")
        if not isinstance(self.parameters, dict):
            raise ValueError("parameters must be an object.")

    def signature(self) -> str:
        return json.dumps(
            {
                "tool_name": self.tool_name,
                "parameters": _jsonable(self.parameters),
            },
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_name": self.tool_name,
            "parameters": _sanitize_value(self.parameters),
            "reason": _sanitize_text(self.reason),
            "expected_result": _sanitize_text(self.expected_result),
        }


@dataclass(frozen=True)
class Observation:
    success: bool
    tool_name: str | None
    output: Any | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "success": self.success,
            "tool_name": self.tool_name,
            "output": _sanitize_value(self.output),
            "error_code": self.error_code,
            "error_message": _safe_message(self.error_message),
            "metadata": _sanitize_value(self.metadata),
        }


@dataclass(frozen=True)
class HistoryEvent:
    turn_index: int
    agent_id: str
    action: Action | None
    observation: Observation

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "agent_id": self.agent_id,
            "action": self.action.to_dict() if self.action else None,
            "observation": self.observation.to_dict(),
        }


@dataclass
class AgentState:
    profile: AgentProfile
    status: AgentStatus = "ready"
    turn_count: int = 0
    policy_call_count: int = 0
    actions_attempted: int = 0
    actions_succeeded: int = 0
    actions_failed: int = 0
    validation_rejections: int = 0
    recovered_failures: int = 0
    history: list[HistoryEvent] = field(default_factory=list)
    last_observation: Observation | None = None
    memory: dict[str, Any] = field(default_factory=dict)
    stop_reason: str | None = None
    _last_action_signature: str | None = None
    _same_action_count: int = 0

    @property
    def agent_id(self) -> str:
        return self.profile.agent_id

    def to_dict(self) -> dict[str, Any]:
        return {
            "profile": self.profile.to_dict(),
            "status": self.status,
            "turn_count": self.turn_count,
            "policy_call_count": self.policy_call_count,
            "actions_attempted": self.actions_attempted,
            "actions_succeeded": self.actions_succeeded,
            "actions_failed": self.actions_failed,
            "validation_rejections": self.validation_rejections,
            "recovered_failures": self.recovered_failures,
            "history": [event.to_dict() for event in self.history],
            "last_observation": (
                self.last_observation.to_dict() if self.last_observation else None
            ),
            "memory": _sanitize_value(self.memory),
            "stop_reason": self.stop_reason,
        }


@dataclass(frozen=True)
class ToolSpec:
    name: str
    description: str
    family: str
    required_parameters: tuple[str, ...] = ()
    parameter_names: tuple[str, ...] = ()
    read_only: bool = True

    def __post_init__(self) -> None:
        _require_identifier(self.name, "tool name")
        _require_text(self.description, "tool description")
        _require_identifier(self.family, "tool family")
        if self.name == "browser_click":
            raise ValueError("browser_click is not part of the canonical runtime.")
        if not set(self.required_parameters).issubset(set(self.parameter_names)):
            raise ValueError("required_parameters must be included in parameter_names.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "name": self.name,
            "description": self.description,
            "family": self.family,
            "required_parameters": list(self.required_parameters),
            "parameter_names": list(self.parameter_names),
            "read_only": self.read_only,
        }


@dataclass
class SharedEnvironment:
    facts: dict[str, Any] = field(default_factory=dict)
    operations: list[dict[str, Any]] = field(default_factory=list)
    article_catalog: dict[str, tuple[dict[str, str], ...]] = field(
        default_factory=dict
    )

    def publish_fact(self, *, key: str, value: Any, agent_id: str) -> None:
        _require_identifier(key, "shared fact key")
        self.facts[key] = _jsonable(value)
        self.operations.append(
            {
                "operation": "publish",
                "key": key,
                "agent_id": agent_id,
            }
        )

    def read_fact(self, *, key: str, agent_id: str) -> tuple[bool, Any | None]:
        _require_identifier(key, "shared fact key")
        found = key in self.facts
        self.operations.append(
            {
                "operation": "read",
                "key": key,
                "agent_id": agent_id,
                "found": found,
            }
        )
        return found, self.facts.get(key)

    def to_dict(self) -> dict[str, Any]:
        return {
            "fact_keys": sorted(self.facts),
            "facts": _sanitize_value(self.facts),
            "operations": _sanitize_value(self.operations),
            "article_urls": sorted(self.article_catalog),
        }


@dataclass(frozen=True)
class ToolExecutionContext:
    runtime_id: str
    turn_index: int
    agent_state: AgentState
    shared_environment: SharedEnvironment


@dataclass(frozen=True)
class ToolResult:
    success: bool
    output: Any | None = None
    error_code: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_observation(self, tool_name: str) -> Observation:
        return Observation(
            success=self.success,
            tool_name=tool_name,
            output=_sanitize_value(self.output),
            error_code=self.error_code,
            error_message=_safe_message(self.error_message),
            metadata=_sanitize_value(self.metadata),
        )


class ToolExecutor(Protocol):
    def execute(
        self,
        spec: ToolSpec,
        action: Action,
        context: ToolExecutionContext,
    ) -> ToolResult:
        ...


ToolHandler = Callable[[Action, ToolExecutionContext], ToolResult]


class ToolRegistry:
    def __init__(self) -> None:
        self._specs: dict[str, ToolSpec] = {}
        self._executors: dict[str, ToolExecutor | ToolHandler] = {}

    def register(
        self,
        spec: ToolSpec,
        executor: ToolExecutor | ToolHandler,
    ) -> None:
        if spec.name in self._specs:
            raise ValueError(f"Tool is already registered: {spec.name}")
        self._specs[spec.name] = spec
        self._executors[spec.name] = executor

    def names(self) -> tuple[str, ...]:
        return tuple(self._specs)

    def get(self, name: str) -> ToolSpec | None:
        return self._specs.get(name)

    def specs_for(self, names: Sequence[str]) -> tuple[ToolSpec, ...]:
        return tuple(self._specs[name] for name in names if name in self._specs)

    def execute(self, action: Action, context: ToolExecutionContext) -> ToolResult:
        spec = self._specs.get(action.tool_name)
        executor = self._executors.get(action.tool_name)
        if spec is None or executor is None:
            return ToolResult(
                success=False,
                error_code="unknown_tool",
                error_message=f"Tool is not registered: {action.tool_name}",
            )
        missing = [
            name
            for name in spec.required_parameters
            if name not in action.parameters
        ]
        unknown = sorted(set(action.parameters) - set(spec.parameter_names))
        if missing:
            return ToolResult(
                success=False,
                error_code="missing_required_parameter",
                error_message="Required tool parameters are missing.",
                metadata={"missing_parameters": missing},
            )
        if unknown:
            return ToolResult(
                success=False,
                error_code="unknown_parameter",
                error_message="Tool parameters contain unknown keys.",
                metadata={"unknown_parameters": unknown},
            )
        if hasattr(executor, "execute"):
            return executor.execute(spec, action, context)  # type: ignore[union-attr]
        return executor(action, context)  # type: ignore[operator]

    def to_dict(self) -> dict[str, Any]:
        return {
            "tool_count": len(self._specs),
            "tool_names": list(self._specs),
            "tools": [spec.to_dict() for spec in self._specs.values()],
        }


class ModelPolicy(Protocol):
    model_execution_attempted: bool

    def next_action(
        self,
        agent_state: AgentState,
        observation: Observation | None,
        allowed_tools: tuple[ToolSpec, ...],
    ) -> Action | None:
        ...


class PolicyError(RuntimeError):
    def __init__(self, message: str, error_code: str) -> None:
        super().__init__(message)
        self.error_code = error_code


@dataclass
class PerfectFakePolicy:
    steps: tuple[Action, ...]
    model_execution_attempted: bool = field(default=False, init=False)

    def next_action(
        self,
        agent_state: AgentState,
        observation: Observation | None,
        allowed_tools: tuple[ToolSpec, ...],
    ) -> Action | None:
        index = int(agent_state.memory.get("perfect_policy_index", 0))
        if index >= len(self.steps):
            return None
        agent_state.memory["perfect_policy_index"] = index + 1
        return self.steps[index]


@dataclass
class RecoveringFakePolicy:
    steps: tuple[Action, ...]
    recovery_action: Action
    model_execution_attempted: bool = field(default=False, init=False)

    def next_action(
        self,
        agent_state: AgentState,
        observation: Observation | None,
        allowed_tools: tuple[ToolSpec, ...],
    ) -> Action | None:
        if observation is not None and not observation.success:
            last_repaired_turn = int(agent_state.memory.get("last_repaired_turn", -1))
            if last_repaired_turn != agent_state.turn_count - 1:
                agent_state.memory["last_repaired_turn"] = agent_state.turn_count - 1
                return self.recovery_action
        index = int(agent_state.memory.get("recovering_policy_index", 0))
        if index >= len(self.steps):
            return None
        agent_state.memory["recovering_policy_index"] = index + 1
        return self.steps[index]


@dataclass
class RepeatingFakePolicy:
    action: Action
    model_execution_attempted: bool = field(default=False, init=False)

    def next_action(
        self,
        agent_state: AgentState,
        observation: Observation | None,
        allowed_tools: tuple[ToolSpec, ...],
    ) -> Action:
        return self.action


@dataclass
class RoleViolatingFakePolicy:
    action: Action
    model_execution_attempted: bool = field(default=False, init=False)

    def next_action(
        self,
        agent_state: AgentState,
        observation: Observation | None,
        allowed_tools: tuple[ToolSpec, ...],
    ) -> Action:
        return self.action


@dataclass
class EarlyStopFakePolicy:
    model_execution_attempted: bool = field(default=False, init=False)

    def next_action(
        self,
        agent_state: AgentState,
        observation: Observation | None,
        allowed_tools: tuple[ToolSpec, ...],
    ) -> None:
        return None


@dataclass
class LocalOpenAIModelPolicy:
    client: LocalLLMClient
    allow_model_calls: bool = False
    model_execution_attempted: bool = field(default=False, init=False)

    def __post_init__(self) -> None:
        parsed = urlparse(self.client.base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOCAL_MODEL_HOSTS:
            raise ValueError("Local model policy only accepts localhost endpoints.")

    def next_action(
        self,
        agent_state: AgentState,
        observation: Observation | None,
        allowed_tools: tuple[ToolSpec, ...],
    ) -> Action:
        if not self.allow_model_calls:
            raise PolicyError(
                "Local model calls require explicit opt-in.",
                "allow_model_calls_required",
            )
        self.model_execution_attempted = True
        next_action = self.client.generate_next_action(
            {
                "agent_id": agent_state.agent_id,
                "role": agent_state.profile.role,
                "goal": agent_state.profile.goal,
                "constraints": list(agent_state.profile.behavior_constraints),
                "allowed_actions": [spec.to_dict() for spec in allowed_tools],
                "last_observation": observation.to_dict() if observation else None,
                "history": [event.to_dict() for event in agent_state.history[-8:]],
                "instruction": "Return exactly one action object, never a workflow or actions array.",
            }
        )
        return Action(
            tool_name=next_action.action,
            parameters=dict(next_action.parameters),
            reason=next_action.reason,
            expected_result=next_action.expected_result,
        )


@dataclass(frozen=True)
class RuntimeLimits:
    max_turns_total: int = 50
    max_turns_per_agent: int = 20
    max_failures_per_agent: int = 3
    max_identical_actions: int = 2

    def __post_init__(self) -> None:
        for name in (
            "max_turns_total",
            "max_turns_per_agent",
            "max_failures_per_agent",
            "max_identical_actions",
        ):
            if getattr(self, name) <= 0:
                raise ValueError(f"{name} must be greater than zero.")


@dataclass(frozen=True)
class RuntimeStepResult:
    turn_index: int
    agent_id: str | None
    action: Action | None
    observation: Observation | None
    status: str
    stop_reason: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "agent_id": self.agent_id,
            "action": self.action.to_dict() if self.action else None,
            "observation": self.observation.to_dict() if self.observation else None,
            "status": self.status,
            "stop_reason": self.stop_reason,
        }


class AutonomousMultiAgentRuntime:
    def __init__(
        self,
        *,
        runtime_id: str,
        profiles: Sequence[AgentProfile],
        policies: Mapping[str, ModelPolicy],
        tool_registry: ToolRegistry,
        limits: RuntimeLimits | None = None,
        shared_environment: SharedEnvironment | None = None,
    ) -> None:
        _require_identifier(runtime_id, "runtime_id")
        if len(profiles) < 2:
            raise ValueError("Canonical multi-agent runtime requires at least two agents.")
        profile_map = {profile.agent_id: profile for profile in profiles}
        if len(profile_map) != len(profiles):
            raise ValueError("Agent ids must be unique.")
        if set(profile_map) != set(policies):
            raise ValueError("Policies must be provided for exactly the configured agents.")
        unknown_tools = {
            tool_name
            for profile in profiles
            for tool_name in profile.allowed_tools
            if tool_registry.get(tool_name) is None
        }
        if unknown_tools:
            raise ValueError(
                f"Agent profiles reference unknown tools: {sorted(unknown_tools)}"
            )
        self.runtime_id = runtime_id
        self.profiles = profile_map
        self.states = {
            profile.agent_id: AgentState(profile=profile) for profile in profiles
        }
        self.policies = dict(policies)
        self.tool_registry = tool_registry
        self.limits = limits or RuntimeLimits()
        self.shared_environment = shared_environment or SharedEnvironment()
        self.turn_count = 0
        self.actions_attempted = 0
        self.actions_succeeded = 0
        self.actions_failed = 0
        self.validation_rejections = 0
        self.recovered_failures = 0
        self.stop_reason: str | None = None
        self.status: RuntimeStatus = "running"
        self.group_history: list[HistoryEvent] = []
        self.scheduler_trace: list[str] = []
        self._cursor = 0

    def step(self) -> RuntimeStepResult:
        pre_stop = self._stop_if_needed()
        if pre_stop is not None:
            return RuntimeStepResult(
                turn_index=self.turn_count,
                agent_id=None,
                action=None,
                observation=None,
                status="stopped",
                stop_reason=pre_stop,
            )

        state = self._next_state()
        if state is None:
            self._finalize("no_runnable_agents")
            return RuntimeStepResult(
                turn_index=self.turn_count,
                agent_id=None,
                action=None,
                observation=None,
                status="stopped",
                stop_reason=self.stop_reason,
            )

        self.turn_count += 1
        state.turn_count += 1
        state.policy_call_count += 1
        self.scheduler_trace.append(state.agent_id)
        allowed_tools = self.tool_registry.specs_for(state.profile.allowed_tools)

        try:
            action = self.policies[state.agent_id].next_action(
                state,
                state.last_observation,
                allowed_tools,
            )
        except PolicyError as exc:
            observation = Observation(
                success=False,
                tool_name=None,
                error_code=exc.error_code,
                error_message=str(exc),
            )
            return self._record_failure(state, None, observation, validation=True)
        except Exception as exc:  # noqa: BLE001 - policy failures become observations.
            observation = Observation(
                success=False,
                tool_name=None,
                error_code="policy_error",
                error_message=str(exc),
            )
            return self._record_failure(state, None, observation, validation=True)

        if action is None:
            state.status = "stopped"
            state.stop_reason = "policy_stopped"
            observation = Observation(
                success=True,
                tool_name=None,
                output={"status": "policy_stopped"},
            )
            self._record_event(state, None, observation)
            stop_reason = self._stop_if_needed()
            return RuntimeStepResult(
                turn_index=self.turn_count,
                agent_id=state.agent_id,
                action=None,
                observation=observation,
                status="policy_stopped",
                stop_reason=stop_reason,
            )

        self.actions_attempted += 1
        state.actions_attempted += 1
        validation_error = self._validate_action(state, action)
        if validation_error is not None:
            return self._record_failure(
                state,
                action,
                validation_error,
                validation=True,
            )

        signature = action.signature()
        if signature == state._last_action_signature:
            state._same_action_count += 1
        else:
            state._last_action_signature = signature
            state._same_action_count = 1
        if state._same_action_count > self.limits.max_identical_actions:
            state.status = "stopped"
            state.stop_reason = "repetition_guard"
            observation = Observation(
                success=False,
                tool_name=action.tool_name,
                error_code="repeated_action_detected",
                error_message="Identical action repetition limit reached.",
                metadata={
                    "max_identical_actions": self.limits.max_identical_actions
                },
            )
            return self._record_failure(
                state,
                action,
                observation,
                validation=True,
            )

        context = ToolExecutionContext(
            runtime_id=self.runtime_id,
            turn_index=self.turn_count,
            agent_state=state,
            shared_environment=self.shared_environment,
        )
        try:
            result = self.tool_registry.execute(action, context)
        except Exception as exc:  # noqa: BLE001 - tool failures are observations.
            result = ToolResult(
                success=False,
                error_code="tool_executor_error",
                error_message=str(exc),
            )
        observation = result.to_observation(action.tool_name)
        if observation.success:
            previous_failed = (
                state.last_observation is not None
                and not state.last_observation.success
            )
            state.actions_succeeded += 1
            self.actions_succeeded += 1
            if previous_failed:
                state.recovered_failures += 1
                self.recovered_failures += 1
            if action.tool_name == "finish":
                state.status = "completed"
                state.stop_reason = "goal_completed"
            self._record_event(state, action, observation)
            stop_reason = self._stop_if_needed()
            return RuntimeStepResult(
                turn_index=self.turn_count,
                agent_id=state.agent_id,
                action=action,
                observation=observation,
                status="success",
                stop_reason=stop_reason,
            )
        return self._record_failure(state, action, observation, validation=False)

    def run(self) -> dict[str, Any]:
        while self.status == "running":
            self.step()
        return self.to_summary()

    def to_summary(self) -> dict[str, Any]:
        model_execution = any(
            bool(getattr(policy, "model_execution_attempted", False))
            for policy in self.policies.values()
        )
        return {
            "schema_version": CANONICAL_RUNTIME_SCHEMA_VERSION,
            "runtime_id": self.runtime_id,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "policy_contract": "one_action_per_turn",
            "scheduler": "round_robin",
            "turn_count": self.turn_count,
            "scheduler_trace": list(self.scheduler_trace),
            "tool_registry": self.tool_registry.to_dict(),
            "per_agent": {
                agent_id: state.to_dict()
                for agent_id, state in self.states.items()
            },
            "group_metrics": {
                "agents_total": len(self.states),
                "agents_completed": sum(
                    state.status == "completed" for state in self.states.values()
                ),
                "agents_stopped": sum(
                    state.status == "stopped" for state in self.states.values()
                ),
                "agents_quarantined": sum(
                    state.status == "quarantined" for state in self.states.values()
                ),
                "policy_calls_total": sum(
                    state.policy_call_count for state in self.states.values()
                ),
                "actions_attempted": self.actions_attempted,
                "actions_succeeded": self.actions_succeeded,
                "actions_failed": self.actions_failed,
                "validation_rejections": self.validation_rejections,
                "recovered_failures": self.recovered_failures,
                "history_events_total": len(self.group_history),
            },
            "group_history": [event.to_dict() for event in self.group_history],
            "shared_environment": self.shared_environment.to_dict(),
            "model_execution": model_execution,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "external_network": False,
            "limitations": [
                "fixture_and_local_tool_runtime_only",
                "deterministic_round_robin_not_parallel_execution",
                "not_production_ready",
            ],
        }

    def _next_state(self) -> AgentState | None:
        agent_ids = list(self.states)
        for offset in range(len(agent_ids)):
            index = (self._cursor + offset) % len(agent_ids)
            state = self.states[agent_ids[index]]
            if state.status != "ready":
                continue
            if state.turn_count >= self.limits.max_turns_per_agent:
                state.status = "stopped"
                state.stop_reason = "max_turns_per_agent"
                continue
            self._cursor = (index + 1) % len(agent_ids)
            return state
        return None

    def _validate_action(
        self,
        state: AgentState,
        action: Action,
    ) -> Observation | None:
        if action.tool_name == "browser_click":
            return Observation(
                success=False,
                tool_name=action.tool_name,
                error_code="tool_not_allowed",
                error_message="browser_click is outside the canonical tool surface.",
            )
        if self.tool_registry.get(action.tool_name) is None:
            return Observation(
                success=False,
                tool_name=action.tool_name,
                error_code="unknown_tool",
                error_message=f"Tool is not registered: {action.tool_name}",
            )
        if action.tool_name not in state.profile.allowed_tools:
            return Observation(
                success=False,
                tool_name=action.tool_name,
                error_code="tool_not_allowed",
                error_message="Tool is not allowed for this agent role.",
                metadata={
                    "agent_id": state.agent_id,
                    "allowed_tools": list(state.profile.allowed_tools),
                },
            )
        return None

    def _record_failure(
        self,
        state: AgentState,
        action: Action | None,
        observation: Observation,
        *,
        validation: bool,
    ) -> RuntimeStepResult:
        state.actions_failed += 1
        self.actions_failed += 1
        if validation:
            state.validation_rejections += 1
            self.validation_rejections += 1
        self._record_event(state, action, observation)
        if (
            state.actions_failed >= self.limits.max_failures_per_agent
            and state.status == "ready"
        ):
            state.status = "quarantined"
            state.stop_reason = "failure_limit"
        stop_reason = self._stop_if_needed()
        return RuntimeStepResult(
            turn_index=self.turn_count,
            agent_id=state.agent_id,
            action=action,
            observation=observation,
            status="failed",
            stop_reason=stop_reason,
        )

    def _record_event(
        self,
        state: AgentState,
        action: Action | None,
        observation: Observation,
    ) -> None:
        event = HistoryEvent(
            turn_index=self.turn_count,
            agent_id=state.agent_id,
            action=action,
            observation=observation,
        )
        state.history.append(event)
        state.last_observation = observation
        self.group_history.append(event)

    def _stop_if_needed(self) -> str | None:
        if self.status != "running":
            return self.stop_reason
        if all(state.status != "ready" for state in self.states.values()):
            self._finalize("all_agents_terminal")
            return self.stop_reason
        if self.turn_count >= self.limits.max_turns_total:
            for state in self.states.values():
                if state.status == "ready":
                    state.status = "stopped"
                    state.stop_reason = "max_turns_total"
            self._finalize("max_turns_total")
            return self.stop_reason
        return None

    def _finalize(self, reason: str) -> None:
        self.stop_reason = reason
        self.status = (
            "succeeded"
            if all(state.status == "completed" for state in self.states.values())
            else "failed"
        )


class ScriptBridgeToolExecutor:
    def __init__(self, bridge: ScriptExecutionBridge) -> None:
        self.bridge = bridge

    def execute(
        self,
        spec: ToolSpec,
        action: Action,
        context: ToolExecutionContext,
    ) -> ToolResult:
        output = self.bridge.execute_next_action(
            NextAction(
                action=action.tool_name,
                parameters=dict(action.parameters),
                reason=action.reason or "Canonical runtime tool call.",
                expected_result=action.expected_result or "Bounded tool result.",
            ),
            run_id=context.runtime_id,
            agent_id=context.agent_state.agent_id,
            step_index=context.turn_index,
        )
        raw = output.raw_result
        return ToolResult(
            success=output.success,
            output=_sanitize_value(raw.output),
            error_code=raw.error_type,
            error_message=raw.error_message,
            metadata=_sanitize_value(
                {
                    "dispatched": output.dispatched,
                    "validation_passed": output.validation_passed,
                    **dict(raw.metadata),
                }
            ),
        )


def build_default_tool_registry(
    *,
    project_root: str | Path = ".",
    article_catalog: Mapping[str, Sequence[Mapping[str, str]]] | None = None,
) -> tuple[ToolRegistry, SharedEnvironment]:
    root = Path(project_root)
    script_registry = load_script_registry(
        root / "configs" / "script_registry.example.json"
    )
    bridge = ScriptExecutionBridge(
        ScriptExecutionBridgeConfig(
            project_root=root,
            registry_path="configs/script_registry.example.json",
            validate_with_registry=True,
            normalize_result=True,
            write_history=False,
        ),
        registry=script_registry,
    )
    bridge_executor = ScriptBridgeToolExecutor(bridge)
    registry = ToolRegistry()

    for descriptor in script_registry.scripts:
        if descriptor.name == "browser_open_url":
            continue
        registry.register(_tool_spec_from_script(descriptor), bridge_executor)

    registry.register(
        ToolSpec(
            name="shared_publish_fact",
            description="Publish one explicit JSON-safe fact to the shared environment.",
            family="coordination",
            required_parameters=("key", "value"),
            parameter_names=("key", "value"),
            read_only=False,
        ),
        _publish_fact,
    )
    registry.register(
        ToolSpec(
            name="shared_read_fact",
            description="Read one explicitly named fact from the shared environment.",
            family="coordination",
            required_parameters=("key",),
            parameter_names=("key",),
            read_only=True,
        ),
        _read_fact,
    )
    registry.register(
        ToolSpec(
            name="finish",
            description="Mark the current agent goal complete.",
            family="control",
            parameter_names=(),
            read_only=True,
        ),
        _finish,
    )

    article_specs = (
        ToolSpec(
            name="browser_article_open",
            description="Open a fixture article by logical URL.",
            family="browser_article_read",
            required_parameters=("url",),
            parameter_names=("url",),
        ),
        ToolSpec(
            name="browser_article_read",
            description="Read the currently visible fixture article section.",
            family="browser_article_read",
        ),
        ToolSpec(
            name="browser_article_scroll",
            description="Move forward through fixture article sections.",
            family="browser_article_read",
            parameter_names=("pages",),
        ),
        ToolSpec(
            name="browser_article_find",
            description="Find text in the opened fixture article.",
            family="browser_article_read",
            required_parameters=("query",),
            parameter_names=("query",),
        ),
        ToolSpec(
            name="browser_article_extract",
            description="Extract a named fixture article section.",
            family="browser_article_read",
            required_parameters=("heading",),
            parameter_names=("heading",),
        ),
    )
    article_handlers: dict[str, ToolHandler] = {
        "browser_article_open": _article_open,
        "browser_article_read": _article_read,
        "browser_article_scroll": _article_scroll,
        "browser_article_find": _article_find,
        "browser_article_extract": _article_extract,
    }
    for spec in article_specs:
        registry.register(spec, article_handlers[spec.name])

    normalized_catalog = {
        str(url): tuple(
            {
                "heading": str(section.get("heading", "")),
                "text": str(section.get("text", "")),
            }
            for section in sections
        )
        for url, sections in (article_catalog or _default_article_catalog()).items()
    }
    environment = SharedEnvironment(article_catalog=normalized_catalog)
    return registry, environment


def load_runtime_from_config(
    config_path: str | Path,
    *,
    project_root: str | Path = ".",
) -> AutonomousMultiAgentRuntime:
    payload = json.loads(Path(config_path).read_text(encoding="utf-8-sig"))
    if payload.get("schema_version") != CANONICAL_CONFIG_SCHEMA_VERSION:
        raise ValueError("Unsupported canonical runtime config schema.")
    runtime_id = _required_mapping_text(payload, "runtime_id")
    raw_agents = payload.get("agents")
    if not isinstance(raw_agents, list) or len(raw_agents) < 2:
        raise ValueError("agents must contain at least two entries.")

    registry, environment = build_default_tool_registry(project_root=project_root)
    profiles: list[AgentProfile] = []
    policies: dict[str, ModelPolicy] = {}
    for raw_agent in raw_agents:
        if not isinstance(raw_agent, Mapping):
            raise ValueError("Each agent config must be an object.")
        profile = AgentProfile(
            agent_id=_required_mapping_text(raw_agent, "agent_id"),
            role=_required_mapping_text(raw_agent, "role"),
            goal=_required_mapping_text(raw_agent, "goal"),
            allowed_tools=_string_tuple(raw_agent.get("allowed_tools")),
            resource_constraints=_string_tuple(
                raw_agent.get("resource_constraints", [])
            ),
            behavior_constraints=_string_tuple(
                raw_agent.get("behavior_constraints", [])
            ),
        )
        policy_payload = raw_agent.get("policy")
        if not isinstance(policy_payload, Mapping):
            raise ValueError("Each agent must define a policy object.")
        profiles.append(profile)
        policies[profile.agent_id] = _fake_policy_from_config(policy_payload)

    limits_payload = payload.get("limits", {})
    if not isinstance(limits_payload, Mapping):
        raise ValueError("limits must be an object.")
    limits = RuntimeLimits(
        max_turns_total=int(limits_payload.get("max_turns_total", 50)),
        max_turns_per_agent=int(limits_payload.get("max_turns_per_agent", 20)),
        max_failures_per_agent=int(
            limits_payload.get("max_failures_per_agent", 3)
        ),
        max_identical_actions=int(
            limits_payload.get("max_identical_actions", 2)
        ),
    )
    return AutonomousMultiAgentRuntime(
        runtime_id=runtime_id,
        profiles=profiles,
        policies=policies,
        tool_registry=registry,
        limits=limits,
        shared_environment=environment,
    )


def _fake_policy_from_config(payload: Mapping[str, Any]) -> ModelPolicy:
    policy_type = _required_mapping_text(payload, "type")
    steps = tuple(
        _action_from_mapping(item)
        for item in _mapping_sequence(payload.get("steps", []), "policy steps")
    )
    if policy_type == "perfect":
        return PerfectFakePolicy(steps=steps)
    if policy_type == "recovering":
        recovery = payload.get("recovery_action")
        if not isinstance(recovery, Mapping):
            raise ValueError("recovering policy requires recovery_action.")
        return RecoveringFakePolicy(
            steps=steps,
            recovery_action=_action_from_mapping(recovery),
        )
    if policy_type == "repeating":
        if len(steps) != 1:
            raise ValueError("repeating policy requires exactly one step.")
        return RepeatingFakePolicy(action=steps[0])
    if policy_type == "role_violating":
        if len(steps) != 1:
            raise ValueError("role_violating policy requires exactly one step.")
        return RoleViolatingFakePolicy(action=steps[0])
    if policy_type == "early_stop":
        if steps:
            raise ValueError("early_stop policy must not define steps.")
        return EarlyStopFakePolicy()
    raise ValueError(f"Unknown fake policy type: {policy_type}")


def _action_from_mapping(payload: Mapping[str, Any]) -> Action:
    parameters = payload.get("parameters", {})
    if not isinstance(parameters, dict):
        raise ValueError("Action parameters must be an object.")
    return Action(
        tool_name=_required_mapping_text(payload, "tool_name"),
        parameters=dict(parameters),
        reason=str(payload.get("reason", "")),
        expected_result=str(payload.get("expected_result", "")),
    )


def _tool_spec_from_script(descriptor: ScriptDescriptor) -> ToolSpec:
    parameter_names = tuple(parameter.name for parameter in descriptor.parameters)
    required = tuple(
        parameter.name for parameter in descriptor.parameters if parameter.required
    )
    tags = set(descriptor.tags)
    if "office" in tags:
        family = "office_documents"
    elif "shell" in tags:
        family = "simple_commands"
    else:
        family = "files"
    return ToolSpec(
        name=descriptor.name,
        description=descriptor.description,
        family=family,
        required_parameters=required,
        parameter_names=parameter_names,
        read_only=descriptor.safety.read_only,
    )


def _publish_fact(action: Action, context: ToolExecutionContext) -> ToolResult:
    key = action.parameters.get("key")
    if not isinstance(key, str):
        return ToolResult(
            success=False,
            error_code="invalid_parameter",
            error_message="key must be a string.",
        )
    try:
        context.shared_environment.publish_fact(
            key=key,
            value=action.parameters.get("value"),
            agent_id=context.agent_state.agent_id,
        )
    except ValueError as exc:
        return ToolResult(
            success=False,
            error_code="invalid_shared_fact",
            error_message=str(exc),
        )
    return ToolResult(success=True, output={"published_key": key})


def _read_fact(action: Action, context: ToolExecutionContext) -> ToolResult:
    key = action.parameters.get("key")
    if not isinstance(key, str):
        return ToolResult(
            success=False,
            error_code="invalid_parameter",
            error_message="key must be a string.",
        )
    try:
        found, value = context.shared_environment.read_fact(
            key=key,
            agent_id=context.agent_state.agent_id,
        )
    except ValueError as exc:
        return ToolResult(
            success=False,
            error_code="invalid_shared_fact",
            error_message=str(exc),
        )
    if not found:
        return ToolResult(
            success=False,
            error_code="shared_fact_not_found",
            error_message=f"Shared fact was not found: {key}",
        )
    return ToolResult(success=True, output={"key": key, "value": value})


def _finish(action: Action, context: ToolExecutionContext) -> ToolResult:
    return ToolResult(
        success=True,
        output={"status": "goal_completed"},
        metadata={"agent_id": context.agent_state.agent_id},
    )


def _article_open(action: Action, context: ToolExecutionContext) -> ToolResult:
    url = action.parameters.get("url")
    if not isinstance(url, str) or url not in context.shared_environment.article_catalog:
        return ToolResult(
            success=False,
            error_code="article_not_found",
            error_message="Fixture article URL was not found.",
        )
    context.agent_state.memory["article_url"] = url
    context.agent_state.memory["article_index"] = 0
    sections = context.shared_environment.article_catalog[url]
    return ToolResult(
        success=True,
        output={
            "url": url,
            "section_count": len(sections),
            "visible_section": sections[0] if sections else None,
        },
    )


def _article_read(action: Action, context: ToolExecutionContext) -> ToolResult:
    article = _current_article(context)
    if isinstance(article, ToolResult):
        return article
    _, sections, index = article
    return ToolResult(success=True, output={"visible_section": sections[index]})


def _article_scroll(action: Action, context: ToolExecutionContext) -> ToolResult:
    article = _current_article(context)
    if isinstance(article, ToolResult):
        return article
    url, sections, index = article
    pages = action.parameters.get("pages", 1)
    if not isinstance(pages, int) or pages < 1:
        return ToolResult(
            success=False,
            error_code="invalid_parameter",
            error_message="pages must be a positive integer.",
        )
    new_index = min(index + pages, len(sections) - 1)
    context.agent_state.memory["article_index"] = new_index
    return ToolResult(
        success=True,
        output={
            "url": url,
            "visible_section": sections[new_index],
            "end_reached": new_index == len(sections) - 1,
        },
    )


def _article_find(action: Action, context: ToolExecutionContext) -> ToolResult:
    article = _current_article(context)
    if isinstance(article, ToolResult):
        return article
    url, sections, _ = article
    query = action.parameters.get("query")
    if not isinstance(query, str) or not query.strip():
        return ToolResult(
            success=False,
            error_code="invalid_parameter",
            error_message="query must be a non-empty string.",
        )
    needle = query.casefold()
    matches = [
        index
        for index, section in enumerate(sections)
        if needle in f"{section['heading']} {section['text']}".casefold()
    ]
    if not matches:
        return ToolResult(
            success=False,
            error_code="text_not_found",
            error_message="Query was not found in the fixture article.",
        )
    context.agent_state.memory["article_index"] = matches[0]
    return ToolResult(
        success=True,
        output={
            "url": url,
            "match_count": len(matches),
            "visible_section": sections[matches[0]],
        },
    )


def _article_extract(action: Action, context: ToolExecutionContext) -> ToolResult:
    article = _current_article(context)
    if isinstance(article, ToolResult):
        return article
    url, sections, _ = article
    heading = action.parameters.get("heading")
    if not isinstance(heading, str) or not heading.strip():
        return ToolResult(
            success=False,
            error_code="invalid_parameter",
            error_message="heading must be a non-empty string.",
        )
    for index, section in enumerate(sections):
        if section["heading"].casefold() == heading.casefold():
            context.agent_state.memory["article_index"] = index
            return ToolResult(
                success=True,
                output={"url": url, "section": section},
            )
    return ToolResult(
        success=False,
        error_code="section_not_found",
        error_message="Requested fixture article section was not found.",
    )


def _current_article(
    context: ToolExecutionContext,
) -> tuple[str, tuple[dict[str, str], ...], int] | ToolResult:
    url = context.agent_state.memory.get("article_url")
    if not isinstance(url, str):
        return ToolResult(
            success=False,
            error_code="article_not_open",
            error_message="Open a fixture article before reading it.",
        )
    sections = context.shared_environment.article_catalog.get(url)
    if not sections:
        return ToolResult(
            success=False,
            error_code="article_not_found",
            error_message="Opened fixture article is unavailable.",
        )
    index = int(context.agent_state.memory.get("article_index", 0))
    index = min(max(index, 0), len(sections) - 1)
    return url, sections, index


def _default_article_catalog() -> dict[str, tuple[dict[str, str], ...]]:
    return {
        "https://fixture.local/articles/runtime": (
            {
                "heading": "Overview",
                "text": "A bounded stepwise agent chooses one action per turn.",
            },
            {
                "heading": "Safety",
                "text": "The fixture article tool performs no external network request.",
            },
        )
    }


def _required_mapping_text(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{key} must be a non-empty string.")
    return value.strip()


def _string_tuple(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, str) or not item.strip() for item in value
    ):
        raise ValueError("Expected a list of non-empty strings.")
    return tuple(item.strip() for item in value)


def _mapping_sequence(value: Any, label: str) -> tuple[Mapping[str, Any], ...]:
    if not isinstance(value, list) or any(
        not isinstance(item, Mapping) for item in value
    ):
        raise ValueError(f"{label} must be a list of objects.")
    return tuple(value)


def _require_identifier(value: str, label: str) -> None:
    if not isinstance(value, str) or _SAFE_IDENTIFIER_RE.fullmatch(value) is None:
        raise ValueError(f"{label} must be a safe identifier.")


def _require_text(value: str, label: str) -> None:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be non-empty.")


def _safe_message(value: str | None) -> str | None:
    if value is None:
        return None
    return _sanitize_text(value, limit=500)


def _sanitize_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        sanitized = {
            str(key): (
                "<redacted>"
                if _SENSITIVE_KEY_RE.search(str(key))
                else _sanitize_value(item)
            )
            for key, item in value.items()
            if str(key).casefold()
            not in {
                "resolved_path",
                "absolute_path",
                "raw_response",
                "secret",
                "token",
            }
        }
        named_key = value.get("key")
        if (
            isinstance(named_key, str)
            and _SENSITIVE_KEY_RE.search(named_key)
            and "value" in sanitized
        ):
            sanitized["value"] = "<redacted>"
        return sanitized
    if isinstance(value, (list, tuple, set)):
        return [_sanitize_value(item) for item in value]
    if isinstance(value, Path):
        return "<local-path>" if value.is_absolute() else value.as_posix()
    if isinstance(value, str):
        return _sanitize_text(value)
    if value is None or isinstance(value, (bool, int, float)):
        return value
    return str(value)


def _sanitize_text(value: str, *, limit: int = 20_000) -> str:
    text = value[:limit]
    text = _SENSITIVE_ASSIGNMENT_RE.sub(r"\1\2<redacted>", text)
    text = _BEARER_TOKEN_RE.sub(r"\1 <redacted>", text)
    text = re.sub(
        r"(?i)\b[A-Z]:[\\/](?:[^\\/\r\n]+[\\/])*[^\\/\r\n]*",
        "<local-path>",
        text,
    )
    return text


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple, set)):
        return [_jsonable(item) for item in value]
    if value is None or isinstance(value, (str, bool, int, float)):
        return value
    return str(value)
