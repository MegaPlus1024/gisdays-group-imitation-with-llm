from __future__ import annotations

import json
import re
import time
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
    "wait_for_dependency",
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
    completion_requirements: tuple[Mapping[str, Any], ...] = ()
    dependencies: tuple[Mapping[str, Any], ...] = ()
    resource_affordances: Mapping[str, Any] = field(default_factory=dict)

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
        for requirement in self.completion_requirements:
            if not isinstance(requirement, Mapping) or not isinstance(requirement.get("id"), str):
                raise ValueError("completion requirements must have an id.")
        if len({item["id"] for item in self.completion_requirements}) != len(self.completion_requirements):
            raise ValueError("completion requirement ids must be unique.")

    def to_dict(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": _sanitize_text(self.role),
            "goal": _sanitize_text(self.goal),
            "allowed_tools": list(self.allowed_tools),
            "resource_constraints": _sanitize_value(self.resource_constraints),
            "behavior_constraints": _sanitize_value(self.behavior_constraints),
            "completion_requirements": _sanitize_value(self.completion_requirements),
            "dependencies": _sanitize_value(self.dependencies),
            "resource_affordances": _sanitize_value(self.resource_affordances),
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
    non_progress_failure_streak: int = 0
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
            "non_progress_failure_streak": self.non_progress_failure_streak,
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
    shared_fact_metadata: dict[str, dict[str, Any]] = field(default_factory=dict)
    operations: list[dict[str, Any]] = field(default_factory=list)
    resource_transitions: list[dict[str, Any]] = field(default_factory=list)
    article_catalog: dict[str, tuple[dict[str, str], ...]] = field(
        default_factory=dict
    )
    fact_contracts: dict[str, dict[str, Any]] = field(default_factory=dict)
    retention_contract: dict[str, Any] = field(default_factory=dict)
    known_files: set[str] = field(default_factory=set)

    def publish_fact(
        self,
        *,
        key: str,
        value: Any,
        agent_id: str,
        metadata: Mapping[str, Any] | None = None,
    ) -> None:
        _require_identifier(key, "shared fact key")
        self.facts[key] = _jsonable(value)
        self.shared_fact_metadata[key] = _sanitize_value(dict(metadata or {}))
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
            "fact_contracts": _sanitize_value(self.fact_contracts),
            "retention_contract": _sanitize_value(self.retention_contract),
            "shared_fact_metadata": _sanitize_value(self.shared_fact_metadata),
            "known_files": sorted(self.known_files),
            "resource_transitions": _sanitize_value(self.resource_transitions),
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
    disable_thinking: bool = True
    response_max_tokens: int | None = None
    temperature: float | None = None
    no_think_prefix: str = ""
    model_execution_attempted: bool = field(default=False, init=False)
    last_input_tokens: int | None = field(default=None, init=False)
    last_output_tokens: int | None = field(default=None, init=False)
    last_protocol_diagnostics: dict[str, Any] = field(default_factory=dict, init=False)

    def __post_init__(self) -> None:
        parsed = urlparse(self.client.base_url)
        if parsed.scheme not in {"http", "https"} or parsed.hostname not in LOCAL_MODEL_HOSTS:
            raise ValueError("Local model policy only accepts localhost endpoints.")
        if self.response_max_tokens is not None and self.response_max_tokens <= 0:
            raise ValueError("response_max_tokens must be greater than zero.")
        if self.temperature is not None and self.temperature < 0:
            raise ValueError("temperature must be non-negative.")

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
        self.last_input_tokens = None
        self.last_output_tokens = None
        self.last_protocol_diagnostics = {}
        try:
            next_action = self.client.generate_next_action(
                {
                "agent_id": agent_state.agent_id,
                "role": agent_state.profile.role,
                "goal": agent_state.profile.goal,
                "constraints": list(agent_state.profile.behavior_constraints),
                "resources": list(agent_state.profile.resource_constraints),
                "available_actions": [spec.to_dict() for spec in allowed_tools],
                "last_observation": observation.to_dict() if observation else None,
                "history": [event.to_dict() for event in agent_state.history[-8:]],
                "memory": _sanitize_value(agent_state.memory),
                "shared_facts": _sanitize_value(
                    agent_state.memory.get("shared_facts", {})
                ),
                "protocol": {
                    "disable_thinking": self.disable_thinking,
                    "response_max_tokens": self.response_max_tokens,
                    "temperature": self.temperature,
                    **({"no_think_prefix": self.no_think_prefix} if self.no_think_prefix else {}),
                },
                "action_schema": {
                    "action_name": "string",
                    "parameters": "object",
                },
                "instruction": (
                    "Return exactly one action object with only action_name and "
                    "parameters, never a workflow or actions array. If the previous own action failed, do not repeat it "
                    "unchanged. Publish shared facts only from your own observed "
                    "evidence and include the matching evidence_id; invented or "
                    "mismatched values will fail and finish remains blocked until "
                    "grounded requirements are complete."
                ),
                }
            )
        except Exception as exc:  # preserve structured local-client diagnostics.
            diagnostics = getattr(self.client, "last_diagnostics", {})
            usage = getattr(self.client, "last_usage", {})
            self.last_input_tokens = (
                usage.get("prompt_tokens") if isinstance(usage, Mapping) else None
            )
            self.last_output_tokens = (
                usage.get("completion_tokens") if isinstance(usage, Mapping) else None
            )
            self.last_protocol_diagnostics = self._protocol_diagnostics(diagnostics)
            raise PolicyError(str(exc), getattr(exc, "error_code", "policy_error")) from exc
        diagnostics = getattr(self.client, "last_diagnostics", {})
        self.last_protocol_diagnostics = self._protocol_diagnostics(diagnostics)
        if not isinstance(next_action, NextAction):
            raise PolicyError(
                "Local model client returned a non-NextAction result.",
                "invalid_model_action",
            )
        usage = getattr(self.client, "last_usage", {})
        self.last_input_tokens = (
            usage.get("prompt_tokens") if isinstance(usage, Mapping) else None
        )
        self.last_output_tokens = (
            usage.get("completion_tokens") if isinstance(usage, Mapping) else None
        )
        return Action(
            tool_name=next_action.action,
            parameters=dict(next_action.parameters),
            reason=next_action.reason,
            expected_result=next_action.expected_result,
        )

    def _protocol_diagnostics(self, diagnostics: Mapping[str, Any]) -> dict[str, Any]:
        protocol = {
            "disable_thinking": self.disable_thinking,
            "no_think_prefix_used": bool(diagnostics.get("no_think_prefix_used", False)),
            "content_length": diagnostics.get("content_length", 0),
            "reasoning_content_length": diagnostics.get("reasoning_content_length", 0),
            "finish_reason": diagnostics.get("finish_reason"),
            "response_id": diagnostics.get("response_id"),
        }
        for key in (
            "content_preview",
            "content_first_non_whitespace_character",
            "content_has_markdown_fence",
            "content_has_think_tag",
            "json_error_line",
            "json_error_column",
            "json_error_position",
        ):
            if key in diagnostics:
                protocol[key] = diagnostics.get(key)
        usage_diagnostics = getattr(self.client, "last_usage_diagnostics", {})
        if isinstance(usage_diagnostics, Mapping):
            for key in (
                "usage_present",
                "usage_prompt_tokens",
                "usage_completion_tokens",
                "usage_total_tokens",
                "usage_keys",
            ):
                if key in usage_diagnostics:
                    protocol[key] = usage_diagnostics.get(key)
        return protocol


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
    model_latency_ms: float = 0.0
    tool_latency_ms: float = 0.0
    input_tokens: int | None = None
    output_tokens: int | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "turn_index": self.turn_index,
            "agent_id": self.agent_id,
            "action": self.action.to_dict() if self.action else None,
            "observation": self.observation.to_dict() if self.observation else None,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "model_latency_ms": self.model_latency_ms,
            "tool_latency_ms": self.tool_latency_ms,
            "input_tokens": self.input_tokens,
            "output_tokens": self.output_tokens,
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
        self._refresh_agent_context(state)
        allowed_names = list(state.profile.allowed_tools)
        if "wait_for_dependency" in allowed_names and not state.memory["task_progress"]["pending_dependencies"]:
            allowed_names.remove("wait_for_dependency")
        allowed_tools = self.tool_registry.specs_for(tuple(allowed_names))
        policy = self.policies[state.agent_id]
        policy_started = time.perf_counter()

        try:
            action = policy.next_action(
                state,
                state.last_observation,
                allowed_tools,
            )
        except PolicyError as exc:
            model_latency_ms, input_tokens, output_tokens = _policy_telemetry(
                policy,
                policy_started,
            )
            observation = Observation(
                success=False,
                tool_name=None,
                error_code=exc.error_code,
                error_message=str(exc),
            )
            return self._record_failure(
                state,
                None,
                observation,
                validation=True,
                model_latency_ms=model_latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        except Exception as exc:  # noqa: BLE001 - policy failures become observations.
            model_latency_ms, input_tokens, output_tokens = _policy_telemetry(
                policy,
                policy_started,
            )
            observation = Observation(
                success=False,
                tool_name=None,
                error_code="policy_error",
                error_message=str(exc),
            )
            return self._record_failure(
                state,
                None,
                observation,
                validation=True,
                model_latency_ms=model_latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        model_latency_ms, input_tokens, output_tokens = _policy_telemetry(
            policy,
            policy_started,
        )

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
                model_latency_ms=model_latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
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
                model_latency_ms=model_latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        signature = self._repetition_signature(state, action)
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
                model_latency_ms=model_latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )

        context = ToolExecutionContext(
            runtime_id=self.runtime_id,
            turn_index=self.turn_count,
            agent_state=state,
            shared_environment=self.shared_environment,
        )
        tool_started = time.perf_counter()
        try:
            result = self.tool_registry.execute(action, context)
        except Exception as exc:  # noqa: BLE001 - tool failures are observations.
            result = ToolResult(
                success=False,
                error_code="tool_executor_error",
                error_message=str(exc),
            )
        tool_latency_ms = round((time.perf_counter() - tool_started) * 1000, 3)
        observation = result.to_observation(action.tool_name)
        if observation.success:
            previous_failed = (
                state.last_observation is not None
                and not state.last_observation.success
            )
            state.actions_succeeded += 1
            self.actions_succeeded += 1
            state.non_progress_failure_streak = 0
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
                model_latency_ms=model_latency_ms,
                tool_latency_ms=tool_latency_ms,
                input_tokens=input_tokens,
                output_tokens=output_tokens,
            )
        return self._record_failure(
            state,
            action,
            observation,
            validation=False,
            model_latency_ms=model_latency_ms,
            tool_latency_ms=tool_latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
        )

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
        if action.tool_name == "wait_for_dependency":
            progress = state.memory.get("task_progress", {})
            declared = {
                item.get("dependency_id")
                for item in state.profile.dependencies
                if isinstance(item.get("dependency_id"), str)
            }
            pending = {
                item.get("dependency_id")
                for item in progress.get("pending_dependencies", [])
                if isinstance(item.get("dependency_id"), str)
            }
            ready = {
                item.get("dependency_id")
                for item in progress.get("ready_dependencies", [])
                if isinstance(item.get("dependency_id"), str)
            }
            dependency_id = action.parameters.get("dependency_id")
            if (
                not isinstance(dependency_id, str)
                or dependency_id not in declared
            ):
                return Observation(
                    False,
                    action.tool_name,
                    error_code="undeclared_dependency",
                    error_message=(
                        "Dependency is not declared for this agent."
                    ),
                    metadata={
                        "dependency_id": dependency_id,
                        "declared_dependency_ids": sorted(declared),
                        "pending_dependency_ids": sorted(pending),
                        "ready_dependency_ids": sorted(ready),
                        "declared": False,
                        "pending": False,
                    },
                )
            if dependency_id not in pending:
                return Observation(
                    False,
                    action.tool_name,
                    error_code="dependency_not_pending",
                    error_message=(
                        "Dependency is declared but is not currently pending."
                    ),
                    metadata={
                        "dependency_id": dependency_id,
                        "declared_dependency_ids": sorted(declared),
                        "pending_dependency_ids": sorted(pending),
                        "ready_dependency_ids": sorted(ready),
                        "declared": True,
                        "pending": False,
                    },
                )
        if action.tool_name in {"read_file", "create_file", "append_file"}:
            path = action.parameters.get("path")
            advertised = state.memory.get("available_resources", {}).get("allowed_paths", [])
            if advertised and (not isinstance(path, str) or path not in advertised):
                return Observation(False, action.tool_name, error_code="path_not_advertised", error_message="Path is outside the advertised scenario contract.")
        return None

    def _repetition_signature(self, state: AgentState, action: Action) -> str:
        payload: dict[str, Any] = {
            "tool_name": action.tool_name,
            "parameters": _jsonable(action.parameters),
        }
        if action.tool_name == "shared_read_fact":
            key = action.parameters.get("key")
            if isinstance(key, str):
                payload["shared_fact_state"] = {
                    "key": key,
                    "readable_published": (
                        key in self.shared_environment.facts
                        and self._fact_readable_by(state.agent_id, key)
                    ),
                }
        if action.tool_name == "wait_for_dependency":
            dependency_id = action.parameters.get("dependency_id")
            if isinstance(dependency_id, str):
                payload["dependency_state"] = self._dependency_repetition_state(
                    state,
                    dependency_id,
                )
        return json.dumps(
            payload,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        )

    def _dependency_repetition_state(
        self,
        state: AgentState,
        dependency_id: str,
    ) -> dict[str, Any]:
        dependency = next(
            (
                item
                for item in state.profile.dependencies
                if item.get("dependency_id") == dependency_id
            ),
            None,
        )
        if not isinstance(dependency, Mapping):
            return {
                "dependency_id": dependency_id,
                "declared": False,
            }

        dependency_state: dict[str, Any] = {
            "dependency_id": dependency_id,
            "declared": True,
            "kind": dependency.get("kind"),
        }

        producer_agent = dependency.get("producer_agent")
        if isinstance(producer_agent, str):
            dependency_state["producer_agent"] = producer_agent
            producer_state = self.states.get(producer_agent)
            if producer_state is not None:
                producer_progress = producer_state.memory.get(
                    "task_progress",
                    {},
                )
                completed_requirements = producer_progress.get(
                    "completed_requirements",
                    [],
                )
                dependency_state["producer_status"] = producer_state.status
                dependency_state["producer_completed_requirements"] = sorted(
                    item
                    for item in completed_requirements
                    if isinstance(item, str)
                )

        kind = dependency.get("kind")
        if kind == "file":
            path = dependency.get("path")
            dependency_state["available"] = (
                isinstance(path, str)
                and path in self.shared_environment.known_files
            )
        elif kind == "shared_fact":
            key = dependency.get("key")
            dependency_state["available"] = (
                isinstance(key, str)
                and key in self.shared_environment.facts
                and self._fact_readable_by(state.agent_id, key)
            )
        else:
            dependency_state["available"] = False

        return dependency_state

    def _record_failure(
        self,
        state: AgentState,
        action: Action | None,
        observation: Observation,
        *,
        validation: bool,
        model_latency_ms: float = 0.0,
        tool_latency_ms: float = 0.0,
        input_tokens: int | None = None,
        output_tokens: int | None = None,
    ) -> RuntimeStepResult:
        completed_before = self._completed_requirement_ids(state)
        state.actions_failed += 1
        self.actions_failed += 1
        if validation:
            state.validation_rejections += 1
            self.validation_rejections += 1
        self._record_event(state, action, observation)
        completed_after = self._completed_requirement_ids(state)
        requirements_advanced = sorted(completed_after - completed_before)
        if requirements_advanced:
            state.non_progress_failure_streak = 0
        else:
            state.non_progress_failure_streak += 1
        if (
            state.non_progress_failure_streak >= self.limits.max_failures_per_agent
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
            model_latency_ms=model_latency_ms,
            tool_latency_ms=tool_latency_ms,
            input_tokens=input_tokens,
            output_tokens=output_tokens,
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
        if action and action.tool_name in {"read_file", "create_file", "append_file"}:
            self._record_file_resource_attempt(state, action, observation)
        if action and observation.success:
            self._record_observed_evidence(state, action, observation)
        if observation.success and action and action.tool_name in {"create_file", "append_file"}:
            path = action.parameters.get("path")
            if isinstance(path, str):
                previous_exists = path in self.shared_environment.known_files
                self.shared_environment.known_files.add(path)
                if not previous_exists:
                    self._record_resource_transition(
                        path=path,
                        producer_agent=state.agent_id,
                        event_index=len(self.group_history) - 1,
                        previous_exists=False,
                        current_exists=True,
                    )
        for candidate in self.states.values():
            self._refresh_agent_context(candidate)

    def _record_resource_transition(
        self,
        *,
        path: str,
        producer_agent: str,
        event_index: int,
        previous_exists: bool,
        current_exists: bool,
    ) -> None:
        dependencies_unblocked = [
            str(item.get("dependency_id"))
            for state in self.states.values()
            for item in state.profile.dependencies
            if item.get("kind") == "file" and item.get("path") == path
        ]
        self.shared_environment.resource_transitions.append(
            {
                "resource_id": self._resource_id_for_path_any(path),
                "path": path,
                "previous_exists": previous_exists,
                "current_exists": current_exists,
                "producer_agent": producer_agent,
                "event_index": event_index,
                "dependencies_unblocked": dependencies_unblocked,
            }
        )

    def _refresh_agent_context(self, state: AgentState) -> None:
        completed = sorted(self._completed_requirement_ids(state))
        completed_set = set(completed)
        historically_completed = {
            str(item)
            for item in state.memory.get(
                "historically_completed_requirements",
                [],
            )
            if isinstance(item, str)
        }
        lost_completed = sorted(
            historically_completed - completed_set
        )
        state.memory["historically_completed_requirements"] = sorted(
            historically_completed | completed_set
        )
        unmet = [item["id"] for item in state.profile.completion_requirements if item["id"] not in completed]
        requirement_contracts = [
            self._requirement_contract(state, item, item["id"] in completed)
            for item in state.profile.completion_requirements
        ]
        pending, ready = self._dependency_status(state)
        readable_facts = {
            key: _jsonable(value)
            for key, value in self.shared_environment.facts.items()
            if self._fact_readable_by(state.agent_id, key)
        }
        affordances = dict(state.profile.resource_affordances)
        allowed_paths = [
            item["path"] for item in affordances.get("paths", [])
            if item.get("access") in {"read", "write", "read_write"}
        ]
        facts = [
            {
                "key": key,
                "status": "published" if key in self.shared_environment.facts else "pending",
                "producer_agent": contract.get("producer_agent"),
                "grounded": self.shared_environment.shared_fact_metadata.get(key, {}).get("grounding_status") == "grounded",
                "evidence_source_type": self.shared_environment.shared_fact_metadata.get(key, {}).get("evidence_source_tool"),
                "published_event_index": self.shared_environment.shared_fact_metadata.get(key, {}).get("published_event_index"),
            }
            for key, contract in sorted(self.shared_environment.fact_contracts.items())
            if state.agent_id in contract.get("consumers", ()) or state.agent_id == contract.get("producer_agent")
        ]
        observed_evidence = list(state.memory.get("observed_evidence", []))
        source_conflicts = self._source_conflicts_for_prompt(state)
        state.memory["shared_facts"] = readable_facts
        state.memory["available_resources"] = {
            "article_urls": affordances.get("article_urls", []),
            "article_title_hints": affordances.get("article_title_hints", []),
            "recommended_start_url": affordances.get("recommended_start_url"),
            "office_fixture_fields": affordances.get("office_fixture_fields", []),
            "allowed_file_roots": affordances.get("allowed_file_roots", []),
            "known_readable_files": [path for path in allowed_paths if path in self.shared_environment.known_files],
            "writable_paths": [item["path"] for item in affordances.get("paths", []) if item.get("access") in {"write", "read_write"}],
            "allowed_paths": allowed_paths,
            "file_resources": self._file_resource_contracts(state),
            "shared_fact_inventory": facts,
            "observed_evidence": self._evidence_for_prompt(state),
            "publishable_facts": self._publishable_facts_for_prompt(state),
            "available_commands": affordances.get("available_commands", []),
            "command_parameters": _sanitize_value(
                affordances.get("command_parameters", {})
            ),
            "expected_shared_fact_keys": _sanitize_value(
                affordances.get("expected_shared_fact_keys", [])
            ),
            "recommended_actions": _sanitize_value(
                affordances.get("recommended_actions", [])
            ),
            "conflict_sources": affordances.get("conflict_sources", []),
            "authority_order": affordances.get("authority_order", []),
            "source_conflicts": source_conflicts,
            "guidance": [
                "Do not repeat an unchanged action against a resource that is still marked unavailable.",
                "Previously failed actions may be retried when the relevant resource state has changed.",
                "Use an advertised existing resource or another valid action that advances an unmet requirement.",
                "Publish shared facts only when they are grounded in your own successful observed evidence and include the evidence_id.",
            ],
        }
        unmet_contracts = [
            contract for contract in requirement_contracts if contract["status"] == "unmet"
        ]
        state.memory["task_progress"] = {
            "goal": state.profile.goal,
            "required_capabilities": sorted({item.get("kind", "tool") for item in state.profile.completion_requirements}),
            "completion_requirements": _sanitize_value(state.profile.completion_requirements),
            "requirement_contracts": _sanitize_value(requirement_contracts),
            "completed_requirements": completed,
            "historically_completed_requirements": list(
                state.memory.get(
                    "historically_completed_requirements",
                    [],
                )
            ),
            "lost_completed_requirements": lost_completed,
            "unmet_requirements": unmet,
            "unmet_requirement_contracts": _sanitize_value(unmet_contracts),
            "pending_dependencies": pending,
            "ready_dependencies": ready,
            "artifacts_created": sorted(self.shared_environment.known_files),
            "facts_published": sorted(self.shared_environment.facts),
            "facts_available": sorted(readable_facts),
            "observed_evidence_ids": [
                item.get("evidence_id")
                for item in observed_evidence
                if isinstance(item, Mapping)
            ],
            "terminal_allowed": not unmet,
            "required_recovery_evidence": self._required_recovery_evidence(state),
            "source_conflicts": source_conflicts,
            "unchanged_failed_actions": self._unchanged_failed_actions(state),
        }

    def _source_conflicts_for_prompt(
        self,
        state: AgentState,
    ) -> list[dict[str, Any]]:
        groups: dict[str, list[dict[str, Any]]] = {}
        for evidence in state.memory.get("observed_evidence", []):
            if not isinstance(evidence, Mapping):
                continue
            conflict_group = evidence.get("conflict_group")
            source_id = evidence.get("source_resource_id")
            if not isinstance(conflict_group, str) or not isinstance(
                source_id,
                str,
            ):
                continue
            groups.setdefault(conflict_group, []).append(
                {
                    "source_id": source_id,
                    "value": evidence.get("observed_value"),
                    "normalized_value": evidence.get("normalized_value"),
                    "authority": evidence.get("source_authority"),
                    "authority_rank": evidence.get("authority_rank"),
                    "evidence_id": evidence.get("evidence_id"),
                }
            )

        affordances = dict(state.profile.resource_affordances)
        expected_sources = {
            str(item.get("source_id"))
            for item in affordances.get("conflict_sources", [])
            if isinstance(item, Mapping)
            and isinstance(item.get("source_id"), str)
        }
        authority_order = [
            str(item)
            for item in affordances.get("authority_order", [])
            if isinstance(item, str)
        ]

        conflicts: list[dict[str, Any]] = []
        for conflict_group, entries in sorted(groups.items()):
            distinct_values = sorted(
                {
                    str(item.get("normalized_value"))
                    for item in entries
                    if item.get("normalized_value") is not None
                }
            )
            if len(distinct_values) < 2:
                continue
            ordered_entries = sorted(
                entries,
                key=lambda item: (
                    int(item.get("authority_rank"))
                    if isinstance(item.get("authority_rank"), int)
                    else -1,
                    str(item.get("source_id")),
                ),
                reverse=True,
            )
            observed_sources = {
                str(item.get("source_id")) for item in entries
            }
            highest = ordered_entries[0] if ordered_entries else {}
            conflicts.append(
                {
                    "conflict_group": conflict_group,
                    "status": (
                        "complete"
                        if expected_sources
                        and expected_sources.issubset(observed_sources)
                        else "detected"
                    ),
                    "source_count": len(observed_sources),
                    "distinct_value_count": len(distinct_values),
                    "distinct_values": distinct_values,
                    "sources": ordered_entries,
                    "authority_order": authority_order,
                    "highest_authority_source": highest.get("source_id"),
                    "highest_authority_value": highest.get("value"),
                    "highest_authority": highest.get("authority"),
                    "highest_authority_rank": highest.get("authority_rank"),
                }
            )
        return _sanitize_value(conflicts)

    def _evidence_for_prompt(
        self,
        state: AgentState,
    ) -> list[dict[str, Any]]:
        prompt_items: list[dict[str, Any]] = []
        for evidence in state.memory.get("observed_evidence", []):
            if not isinstance(evidence, Mapping):
                continue
            item: dict[str, Any] = {
                "evidence_id": evidence.get("evidence_id"),
                "source_tool": evidence.get("source_tool"),
                "source_field": evidence.get("source_field"),
                "safe_value_preview": _sanitize_text(
                    str(evidence.get("observed_value", "")),
                    limit=120,
                ),
                "compatible_fact_keys": self._compatible_fact_keys(
                    state,
                    evidence,
                ),
            }
            for key in (
                "source_resource_id",
                "source_authority",
                "authority_rank",
                "conflict_group",
                "authority_order",
            ):
                if key in evidence:
                    item[key] = evidence.get(key)
            prompt_items.append(item)
        return _sanitize_value(prompt_items)

    def _publishable_facts_for_prompt(
        self,
        state: AgentState,
    ) -> list[dict[str, Any]]:
        publishable: list[dict[str, Any]] = []
        for key, contract in sorted(
            self.shared_environment.fact_contracts.items()
        ):
            if contract.get("producer_agent") != state.agent_id:
                continue
            publishable.append(
                {
                    "key": key,
                    "required_source_type": contract.get(
                        "required_source_tool"
                    ),
                    "required_source_field": contract.get(
                        "required_source_field"
                    ),
                    "required_source_resource_id": contract.get(
                        "required_source_resource_id"
                    ),
                    "required_authority": contract.get(
                        "required_authority"
                    ),
                    "required_authority_rank": contract.get(
                        "required_authority_rank"
                    ),
                    "authority_order": list(
                        contract.get("authority_order", ())
                    ),
                    "required_conflict_sources": list(
                        contract.get("required_conflict_sources", ())
                    ),
                    "candidate_evidence_ids": [
                        item.get("evidence_id")
                        for item in state.memory.get("observed_evidence", [])
                        if isinstance(item, Mapping)
                        and self._evidence_matches_contract(item, contract)
                    ],
                    "grounding_required": bool(
                        contract.get("grounding_required", False)
                    ),
                    "published_status": (
                        "published"
                        if key in self.shared_environment.facts
                        else "pending"
                    ),
                }
            )
        return _sanitize_value(publishable)

    def _compatible_fact_keys(
        self,
        state: AgentState,
        evidence: Mapping[str, Any],
    ) -> list[str]:
        return [
            key
            for key, contract in sorted(self.shared_environment.fact_contracts.items())
            if contract.get("producer_agent") == state.agent_id
            and self._evidence_matches_contract(evidence, contract)
        ]

    def _evidence_matches_contract(
        self,
        evidence: Mapping[str, Any],
        contract: Mapping[str, Any],
    ) -> bool:
        return _evidence_matches_contract(evidence, contract)

    def _record_file_resource_attempt(
        self,
        state: AgentState,
        action: Action,
        observation: Observation,
    ) -> None:
        path = action.parameters.get("path")
        if not isinstance(path, str):
            return
        errors = dict(state.memory.get("resource_last_errors", {}))
        if not observation.success:
            errors[path] = {
                "last_failure_error_code": observation.error_code,
                "last_failure_event_index": len(state.history) - 1,
                "last_failure_action_name": action.tool_name,
                "last_failure_parameters": dict(action.parameters),
                "action_name": action.tool_name,
            }
        state.memory["resource_last_errors"] = errors

    def _record_observed_evidence(
        self,
        state: AgentState,
        action: Action,
        observation: Observation,
    ) -> None:
        event_index = len(state.history) - 1
        evidence_items = self._evidence_from_observation(
            state,
            action,
            observation,
            event_index,
        )
        if not evidence_items:
            return
        existing = list(state.memory.get("observed_evidence", []))
        existing.extend(evidence_items)
        state.memory["observed_evidence"] = _sanitize_value(existing)

    def _evidence_from_observation(
        self,
        state: AgentState,
        action: Action,
        observation: Observation,
        event_index: int,
    ) -> list[dict[str, Any]]:
        output = observation.output
        if action.tool_name in {
            "office_fixture_read",
            "source_record_read",
            "dependency_owner_extract",
            "retention_source_read",
        } and isinstance(output, Mapping):
            field = output.get("field")
            if isinstance(field, str) and "value" in output:
                return [
                    self._observed_evidence_record(
                        state,
                        action,
                        event_index,
                        source_field=field,
                        observed_value=output.get("value"),
                        source_resource_id="office_fixture",
                    )
                ]
            if all(isinstance(key, str) for key in output):
                return [
                    self._observed_evidence_record(
                        state,
                        action,
                        event_index,
                        source_field=str(key),
                        observed_value=value,
                        source_resource_id="office_fixture",
                    )
                    for key, value in output.items()
                    if isinstance(value, (str, int, float, bool))
                ]
        if (
            action.tool_name in {
                "conflict_source_read",
                "retention_conflict_read",
            }
            and isinstance(output, Mapping)
        ):
            source_id = output.get("source_id")
            field = output.get("field")
            if (
                isinstance(source_id, str)
                and isinstance(field, str)
                and "value" in output
            ):
                record = self._observed_evidence_record(
                    state,
                    action,
                    event_index,
                    source_field=field,
                    observed_value=output.get("value"),
                    source_resource_id=source_id,
                )
                if isinstance(output.get("authority"), str):
                    record["source_authority"] = output.get("authority")
                if isinstance(output.get("authority_rank"), int):
                    record["authority_rank"] = output.get("authority_rank")
                if isinstance(output.get("conflict_group"), str):
                    record["conflict_group"] = output.get("conflict_group")
                if isinstance(output.get("authority_order"), Sequence):
                    record["authority_order"] = [
                        str(item)
                        for item in output.get("authority_order", ())
                        if isinstance(item, str)
                    ]
                return [record]
        if action.tool_name == "browser_article_extract" and isinstance(output, Mapping):
            section = output.get("section")
            if isinstance(section, Mapping):
                heading = section.get("heading")
                text = section.get("text")
                if isinstance(heading, str) and isinstance(text, str):
                    return [
                        self._observed_evidence_record(
                            state,
                            action,
                            event_index,
                            source_field=heading,
                            observed_value=text,
                            source_resource_id=str(output.get("url", "article_fixture")),
                        )
                    ]
        if action.tool_name == "read_file":
            path = action.parameters.get("path")
            if isinstance(path, str):
                return [
                    self._observed_evidence_record(
                        state,
                        action,
                        event_index,
                        source_field="content",
                        observed_value=output,
                        source_resource_id=self._resource_id_for_path(state, path) or path,
                    )
                ]
        return []

    def _observed_evidence_record(
        self,
        state: AgentState,
        action: Action,
        event_index: int,
        *,
        source_field: str,
        observed_value: Any,
        source_resource_id: str,
    ) -> dict[str, Any]:
        normalized = _normalize_fact_value(observed_value, "trimmed_text")
        evidence_id = (
            f"ev_{state.agent_id}_{event_index}_{_safe_evidence_token(source_field)}"
        )
        return {
            "evidence_id": evidence_id,
            "agent_id": state.agent_id,
            "source_event_index": event_index,
            "source_tool": action.tool_name,
            "source_resource_id": source_resource_id,
            "source_field": source_field,
            "observed_value": _sanitize_text(str(observed_value), limit=500),
            "normalized_value": _sanitize_text(normalized, limit=500),
            "observed_at_step": self.turn_count,
            "trust_level": "fixture_observation",
            "visibility_scope": "agent_private",
        }

    def _file_resource_contracts(self, state: AgentState) -> list[dict[str, Any]]:
        affordances = dict(state.profile.resource_affordances)
        explicit = affordances.get("file_resources")
        if isinstance(explicit, Sequence) and not isinstance(explicit, (str, bytes)):
            descriptors = [dict(item) for item in explicit if isinstance(item, Mapping)]
        else:
            descriptors = []
            for item in affordances.get("paths", []):
                if not isinstance(item, Mapping):
                    continue
                path = item.get("path")
                if not isinstance(path, str):
                    continue
                descriptors.append(
                    {
                        "resource_id": item.get("resource_id", path.rsplit("/", 1)[-1].replace(".", "_")),
                        "path": path,
                        "exists": path in self.shared_environment.known_files,
                        "readable": item.get("access") in {"read", "read_write"},
                        "writable": item.get("access") in {"write", "read_write"},
                        "purpose": item.get("purpose", "advertised scenario file resource"),
                    }
                )
        errors = state.memory.get("resource_last_errors", {})
        resources: list[dict[str, Any]] = []
        for descriptor in descriptors:
            path = descriptor.get("path")
            if isinstance(path, str):
                descriptor["exists"] = path in self.shared_environment.known_files
            if isinstance(path, str) and path in errors and isinstance(errors[path], Mapping):
                historical = dict(errors[path])
                current_exists = bool(descriptor.get("exists", False))
                state_changed = (
                    historical.get("last_failure_error_code") == "file_not_found"
                    and current_exists
                )
                retry_now_valid = (
                    state_changed
                    and descriptor.get("readable") is True
                )
                unchanged_discouraged = (
                    historical.get("last_failure_error_code") == "file_not_found"
                    and not current_exists
                )
                descriptor.update(
                    {
                        **historical,
                        "last_error_code": historical.get("last_failure_error_code"),
                        "last_attempt_history_index": historical.get("last_failure_event_index"),
                        "state_changed_since_failure": state_changed,
                        "retry_now_valid": retry_now_valid,
                        "unchanged_retry_discouraged": unchanged_discouraged,
                    }
                )
            else:
                descriptor.setdefault("state_changed_since_failure", False)
                descriptor.setdefault("retry_now_valid", False)
                descriptor.setdefault("unchanged_retry_discouraged", False)
            resources.append(_sanitize_value(descriptor))
        return resources

    def _requirement_contract(
        self,
        state: AgentState,
        requirement: Mapping[str, Any],
        completed: bool,
    ) -> dict[str, Any]:
        requirement_id = str(requirement.get("id", ""))
        contract = {
            "requirement_id": requirement_id,
            "description": _sanitize_text(
                str(requirement.get("description") or _requirement_description(requirement))
            ),
            "status": "completed" if completed else "unmet",
            "evidence_type": requirement.get("evidence_type") or requirement.get("kind"),
            "dependency_ids": list(requirement.get("dependency_ids", ())),
            "required_action": requirement.get("required_action")
            or requirement.get("tool_name")
            or requirement.get("action_name"),
            "required_parameters": _sanitize_value(
                requirement.get("parameters", {})
                if isinstance(requirement.get("parameters"), Mapping)
                else {}
            ),
            "satisfied_by_outcome": _sanitize_text(
                str(requirement.get("satisfied_by_outcome") or _requirement_outcome(requirement))
            ),
            "related_resource_ids": list(requirement.get("related_resource_ids", ())),
            "last_progress_event_index": self._last_requirement_progress_index(state, requirement),
        }
        key = requirement.get("key")
        if isinstance(key, str):
            fact_contract = self.shared_environment.fact_contracts.get(key, {})
            metadata = self.shared_environment.shared_fact_metadata.get(key, {})
            contract.update(
                {
                    "fact_key": key,
                    "grounding_required": bool(
                        fact_contract.get("grounding_required", False)
                    ),
                    "grounding_status": metadata.get(
                        "grounding_status",
                        "pending" if key not in self.shared_environment.facts else "ungrounded",
                    ),
                    "grounding_error": metadata.get("grounding_error"),
                    "related_evidence_ids": [
                        item.get("evidence_id")
                        for item in state.memory.get("observed_evidence", [])
                        if isinstance(item, Mapping)
                        and self._evidence_matches_contract(item, fact_contract)
                    ],
                }
            )
        resource_ids = list(requirement.get("related_resource_ids", ()))
        if resource_ids:
            states = self._resource_states_for_ids(state, resource_ids)
            contract["resource_states"] = states
            if len(states) == 1:
                contract["resource_state"] = states[0]
        return contract

    def _last_requirement_progress_index(
        self,
        state: AgentState,
        requirement: Mapping[str, Any],
    ) -> int | None:
        for index in range(len(state.history) - 1, -1, -1):
            if self._event_satisfies_requirement(state, requirement, index):
                return index
        return None

    def _dependency_status(self, state: AgentState) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
        pending: list[dict[str, Any]] = []
        ready: list[dict[str, Any]] = []
        for dependency in state.profile.dependencies:
            item = dict(dependency)
            kind = item.get("kind")
            is_ready = (kind == "shared_fact" and item.get("key") in self.shared_environment.facts) or (kind == "file" and item.get("path") in self.shared_environment.known_files)
            (ready if is_ready else pending).append(item)
        return pending, ready

    def _fact_readable_by(self, agent_id: str, key: str) -> bool:
        contract = self.shared_environment.fact_contracts.get(key)
        return contract is None or agent_id == contract.get("producer_agent") or agent_id in contract.get("consumers", ())

    def _requirement_met(self, state: AgentState, requirement: Mapping[str, Any]) -> bool:
        return any(
            self._event_satisfies_requirement(state, requirement, index)
            for index in range(len(state.history))
        )

    def _completed_requirement_ids(self, state: AgentState) -> set[str]:
        return {
            str(requirement["id"])
            for requirement in state.profile.completion_requirements
            if self._requirement_met(state, requirement)
        }

    def _event_satisfies_requirement(
        self,
        state: AgentState,
        requirement: Mapping[str, Any],
        index: int,
    ) -> bool:
        if index < 0 or index >= len(state.history):
            return False
        event = state.history[index]
        kind = requirement.get("kind")
        if kind == "tool_succeeded":
            resource_id = requirement.get("resource_id")
            if isinstance(resource_id, str):
                return self._resource_bound_tool_succeeded(state, requirement, index)
            return bool(event.action and event.action.tool_name == requirement.get("tool_name") and event.observation.success and all(event.action.parameters.get(key) == value for key, value in dict(requirement.get("parameters", {})).items()))
        if kind == "file_written":
            return bool(event.action and event.action.tool_name in {"create_file", "append_file"} and event.observation.success and event.action.parameters.get("path") == requirement.get("path"))
        if kind == "fact_published":
            if not (event.action and event.action.tool_name == "shared_publish_fact" and event.observation.success and event.action.parameters.get("key") == requirement.get("key")):
                return False
            contract = self.shared_environment.fact_contracts.get(str(requirement.get("key")))
            if contract and contract.get("grounding_required"):
                return self.shared_environment.shared_fact_metadata.get(str(requirement.get("key")), {}).get("grounding_status") == "grounded"
            return True
        if kind == "fact_published_grounded":
            key = str(requirement.get("key"))
            return bool(
                event.action
                and event.action.tool_name == "shared_publish_fact"
                and event.observation.success
                and event.action.parameters.get("key") == key
                and self.shared_environment.shared_fact_metadata.get(key, {}).get("grounding_status") == "grounded"
            )
        if kind == "fact_read":
            return bool(event.action and event.action.tool_name == "shared_read_fact" and event.action.parameters.get("key") == requirement.get("key") and event.observation.success)
        if kind == "source_conflict_observed":
            return self._event_satisfies_source_conflict(
                state, requirement, index
            )
        if kind == "error_observed":
            return event.observation.error_code == requirement.get("error_code")
        if kind == "error_recovery_completed":
            return self._event_satisfies_error_recovery(
                state, requirement, index
            )
        if kind == "recovery_completed":
            return self._event_satisfies_required_recovery(state, requirement, index)
        return False

    def _event_satisfies_source_conflict(
        self,
        state: AgentState,
        requirement: Mapping[str, Any],
        index: int,
    ) -> bool:
        required_sources = {
            str(item)
            for item in requirement.get("sources", ())
            if isinstance(item, str)
        }
        required_field = requirement.get("field")
        authority_order = [
            str(item)
            for item in requirement.get("authority_order", ())
            if isinstance(item, str)
        ]
        required_tool_name = str(
            requirement.get("tool_name")
            or "conflict_source_read"
        )
        observed: dict[str, dict[str, Any]] = {}

        for event in state.history[: index + 1]:
            if (
                event.action is None
                or event.action.tool_name != required_tool_name
                or not event.observation.success
                or not isinstance(event.observation.output, Mapping)
            ):
                continue
            output = event.observation.output
            source_id = output.get("source_id")
            field = output.get("field")
            if not isinstance(source_id, str):
                continue
            if isinstance(required_field, str) and field != required_field:
                continue
            observed[source_id] = {
                "value": output.get("value"),
                "authority_rank": output.get("authority_rank"),
            }

        if required_sources and not required_sources.issubset(observed):
            return False
        values = {
            _normalize_fact_value(item.get("value"), "trimmed_text")
            for item in observed.values()
        }
        if len(values) < 2:
            return False
        if authority_order:
            ranked = sorted(
                observed.items(),
                key=lambda pair: (
                    int(pair[1].get("authority_rank"))
                    if isinstance(pair[1].get("authority_rank"), int)
                    else -1,
                    pair[0],
                ),
                reverse=True,
            )
            if not ranked or ranked[0][0] != authority_order[0]:
                return False
        return True

    def _event_satisfies_error_recovery(
        self,
        state: AgentState,
        requirement: Mapping[str, Any],
        index: int,
    ) -> bool:
        event = state.history[index]
        if not event.action or not event.observation.success:
            return False
        recovery_tool_name = requirement.get("recovery_tool_name")
        if (
            isinstance(recovery_tool_name, str)
            and event.action.tool_name != recovery_tool_name
        ):
            return False
        parameters = requirement.get("parameters", {})
        if not isinstance(parameters, Mapping):
            return False
        if any(
            event.action.parameters.get(key) != value
            for key, value in parameters.items()
        ):
            return False
        source_error_code = requirement.get("source_error_code")
        if not isinstance(source_error_code, str):
            return False
        source_action_name = requirement.get("source_action_name")
        return any(
            prior.observation.error_code == source_error_code
            and (
                not isinstance(source_action_name, str)
                or (
                    prior.action is not None
                    and prior.action.tool_name == source_action_name
                )
            )
            for prior in state.history[:index]
        )

    def _event_satisfies_required_recovery(
        self,
        state: AgentState,
        requirement: Mapping[str, Any],
        index: int,
    ) -> bool:
        event = state.history[index]
        if not event.action or not event.observation.success:
            return False
        if event.action.tool_name != requirement.get("tool_name"):
            return False
        recovery_resource_id = requirement.get("recovery_resource_id")
        recovery_path = self._resource_path(state, recovery_resource_id)
        if recovery_path is not None and event.action.parameters.get("path") != recovery_path:
            return False
        source_error_code = requirement.get("source_error_code", "file_not_found")
        source_resource_id = requirement.get("source_resource_id")
        source_path = self._resource_path(state, source_resource_id)
        for prior in state.history[:index]:
            if prior.observation.error_code != source_error_code or prior.action is None:
                continue
            if prior.action.tool_name != requirement.get("tool_name"):
                continue
            if source_path is not None and prior.action.parameters.get("path") != source_path:
                continue
            return prior.action.parameters.get("path") != event.action.parameters.get("path")
        return False

    def _required_recovery_evidence(
        self,
        state: AgentState,
    ) -> list[dict[str, Any]]:
        evidence: list[dict[str, Any]] = []
        for requirement in state.profile.completion_requirements:
            kind = requirement.get("kind")
            if kind == "error_recovery_completed":
                for index in range(len(state.history)):
                    if not self._event_satisfies_error_recovery(
                        state, requirement, index
                    ):
                        continue
                    source_error_code = requirement.get("source_error_code")
                    source_action_name = requirement.get("source_action_name")
                    source_index = None
                    for prior_index in range(index - 1, -1, -1):
                        prior = state.history[prior_index]
                        if prior.observation.error_code != source_error_code:
                            continue
                        if (
                            isinstance(source_action_name, str)
                            and (
                                prior.action is None
                                or prior.action.tool_name != source_action_name
                            )
                        ):
                            continue
                        source_index = prior_index
                        break
                    event = state.history[index]
                    evidence.append(
                        {
                            "requirement_id": requirement.get("id"),
                            "source_failure_event_index": source_index,
                            "recovery_event_index": index,
                            "source_error_code": source_error_code,
                            "failed_action_name": (
                                state.history[source_index].action.tool_name
                                if source_index is not None
                                and state.history[source_index].action is not None
                                else None
                            ),
                            "recovery_action_name": (
                                event.action.tool_name if event.action else None
                            ),
                            "recovery_parameters": (
                                dict(event.action.parameters)
                                if event.action is not None
                                else {}
                            ),
                        }
                    )
                    break
                continue
            if kind != "recovery_completed":
                continue
            for index in range(len(state.history)):
                if not self._event_satisfies_required_recovery(
                    state, requirement, index
                ):
                    continue
                source_error_code = requirement.get(
                    "source_error_code", "file_not_found"
                )
                source_resource_id = requirement.get("source_resource_id")
                source_path = self._resource_path(state, source_resource_id)
                source_index = None
                failed_resource_id = source_resource_id
                for prior_index, prior in enumerate(state.history[:index]):
                    if (
                        prior.observation.error_code != source_error_code
                        or prior.action is None
                    ):
                        continue
                    if prior.action.tool_name != requirement.get("tool_name"):
                        continue
                    if (
                        source_path is not None
                        and prior.action.parameters.get("path") != source_path
                    ):
                        continue
                    source_index = prior_index
                    break
                event = state.history[index]
                evidence.append(
                    {
                        "requirement_id": requirement.get("id"),
                        "source_failure_event_index": source_index,
                        "recovery_event_index": index,
                        "source_error_code": source_error_code,
                        "failed_resource_id": failed_resource_id,
                        "recovery_resource_id": requirement.get(
                            "recovery_resource_id"
                        ),
                        "recovery_action_name": (
                            event.action.tool_name if event.action else None
                        ),
                    }
                )
        return _sanitize_value(evidence)


    def _resource_bound_tool_succeeded(
        self,
        state: AgentState,
        requirement: Mapping[str, Any],
        index: int,
    ) -> bool:
        event = state.history[index]
        resource_id = requirement.get("resource_id")
        required_action = requirement.get("required_action") or requirement.get("tool_name")
        if not isinstance(resource_id, str):
            return False
        if not event.action or event.action.tool_name != required_action:
            return False
        if not event.observation.success:
            return False
        path = event.action.parameters.get("path")
        if not isinstance(path, str):
            return False
        if self._resource_id_for_path(state, path) != resource_id:
            return False
        return path in self.shared_environment.known_files

    def _unchanged_failed_actions(self, state: AgentState) -> list[dict[str, Any]]:
        return [
            {
                "action_name": resource.get("action_name"),
                "path": resource.get("path"),
                "last_error_code": resource.get("last_failure_error_code"),
                "last_attempt_history_index": resource.get("last_failure_event_index"),
                "unchanged_retry_discouraged": True,
            }
            for resource in self._file_resource_contracts(state)
            if resource.get("unchanged_retry_discouraged") is True
        ]

    def _resource_states_for_ids(
        self,
        state: AgentState,
        resource_ids: Sequence[Any],
    ) -> list[dict[str, Any]]:
        wanted = {str(item) for item in resource_ids if isinstance(item, str)}
        return [
            {
                "resource_id": resource.get("resource_id"),
                "path": resource.get("path"),
                "exists": resource.get("exists"),
                "readable": resource.get("readable"),
                "state_changed_since_failure": resource.get("state_changed_since_failure"),
                "retry_now_valid": resource.get("retry_now_valid"),
                "unchanged_retry_discouraged": resource.get("unchanged_retry_discouraged"),
                "last_failure_event_index": resource.get("last_failure_event_index"),
                "last_failure_error_code": resource.get("last_failure_error_code"),
            }
            for resource in self._file_resource_contracts(state)
            if resource.get("resource_id") in wanted
        ]

    def _resource_path(self, state: AgentState, resource_id: object) -> str | None:
        if not isinstance(resource_id, str):
            return None
        for resource in self._file_resource_contracts(state):
            if resource.get("resource_id") == resource_id and isinstance(resource.get("path"), str):
                return str(resource["path"])
        return None

    def _resource_id_for_path(self, state: AgentState, path: str) -> str | None:
        for resource in self._file_resource_contracts(state):
            if resource.get("path") == path and isinstance(resource.get("resource_id"), str):
                return str(resource["resource_id"])
        return None

    def _resource_id_for_path_any(self, path: str) -> str:
        for state in self.states.values():
            resource_id = self._resource_id_for_path(state, path)
            if resource_id is not None:
                return resource_id
        return path.rsplit("/", 1)[-1].replace(".", "_")

    def _resource_available_event_index(self, resource_id: str) -> int | None:
        indexes = [
            int(item["event_index"])
            for item in self.shared_environment.resource_transitions
            if item.get("resource_id") == resource_id
            and item.get("current_exists") is True
            and isinstance(item.get("event_index"), int)
        ]
        return min(indexes) if indexes else None

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
                action_name=action.tool_name,
                parameters=dict(action.parameters),
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
            parameter_names=("key", "value", "evidence_id"),
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
            name="wait_for_dependency",
            description="Yield until one declared dependency becomes available.",
            family="coordination",
            required_parameters=("dependency_id",),
            parameter_names=("dependency_id",),
            read_only=True,
        ),
        _wait_for_dependency,
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
    contract = context.shared_environment.fact_contracts.get(key)
    if context.shared_environment.fact_contracts and contract is None:
        return ToolResult(
            False,
            error_code="fact_key_not_allowed",
            error_message="Fact key is not declared in the scenario contract.",
            metadata={"key": key},
        )
    if contract and contract.get("producer_agent") != context.agent_state.agent_id:
        return ToolResult(False, error_code="shared_fact_publish_not_allowed", error_message="This agent is not the declared producer for the fact.")
    if (
        contract
        and contract.get("overwrite_policy") == "immutable"
        and key in context.shared_environment.facts
    ):
        policy = str(
            contract.get("normalization_policy", "trimmed_text")
        )
        existing_value = _normalize_fact_value(
            context.shared_environment.facts[key],
            policy,
        )
        attempted_value = _normalize_fact_value(
            action.parameters.get("value"),
            policy,
        )
        error_code = (
            "post_completion_drift"
            if existing_value == attempted_value
            else "fact_substitution"
        )
        return ToolResult(
            False,
            error_code=error_code,
            error_message=(
                "Immutable retained facts cannot be republished."
            ),
            metadata={
                "key": key,
                "existing_value": existing_value,
                "attempted_value": attempted_value,
                "overwrite_policy": "immutable",
            },
        )
    required_conflict_sources = {
        str(item)
        for item in (contract or {}).get("required_conflict_sources", ())
        if isinstance(item, str)
    }
    if required_conflict_sources:
        matching_evidence = [
            item
            for item in context.agent_state.memory.get("observed_evidence", [])
            if isinstance(item, Mapping)
            and item.get("source_tool") == contract.get("required_source_tool")
            and str(item.get("source_field", "")).casefold()
            == str(contract.get("required_source_field", "")).casefold()
        ]
        observed_sources = {
            str(item.get("source_resource_id"))
            for item in matching_evidence
            if isinstance(item.get("source_resource_id"), str)
        }
        observed_values = {
            _normalize_fact_value(item.get("observed_value"), "trimmed_text")
            for item in matching_evidence
        }
        if (
            not required_conflict_sources.issubset(observed_sources)
            or len(observed_values) < 2
        ):
            return ToolResult(
                False,
                error_code="source_conflict_unresolved",
                error_message="All declared contradictory sources must be observed before publication.",
                metadata={
                    "required_conflict_sources": sorted(required_conflict_sources),
                    "observed_conflict_sources": sorted(observed_sources),
                    "distinct_observed_values": len(observed_values),
                },
            )
    grounding = _validate_fact_grounding(action, context, contract)
    if not grounding["success"]:
        return ToolResult(
            False,
            error_code=str(grounding["error_code"]),
            error_message="Shared fact provenance validation failed.",
            metadata=dict(grounding["metadata"]),
        )
    try:
        context.shared_environment.publish_fact(
            key=key,
            value=action.parameters.get("value"),
            agent_id=context.agent_state.agent_id,
            metadata={
                "key": key,
                "value": action.parameters.get("value"),
                "normalized_value": grounding["metadata"].get("normalized_published_value"),
                "producer_agent": context.agent_state.agent_id,
                "published_event_index": context.turn_index,
                "evidence_id": grounding["metadata"].get("selected_evidence_id"),
                "evidence_source_tool": grounding["metadata"].get("evidence_source_tool"),
                "evidence_source_field": grounding["metadata"].get("evidence_source_field"),
                "evidence_source_event_index": grounding["metadata"].get("evidence_source_event_index"),
                "evidence_source_resource_id": grounding["metadata"].get("evidence_source_resource_id"),
                "evidence_source_authority": grounding["metadata"].get("evidence_source_authority"),
                "evidence_authority_rank": grounding["metadata"].get("evidence_authority_rank"),
                "authority_order": grounding["metadata"].get("authority_order", []),
                "grounding_required": grounding["metadata"].get("grounding_required", False),
                "grounding_status": "grounded" if grounding["metadata"].get("grounding_valid") else "not_required",
                "grounding_error": None,
            },
        )
    except ValueError as exc:
        return ToolResult(
            success=False,
            error_code="invalid_shared_fact",
            error_message=str(exc),
        )
    return ToolResult(
        success=True,
        output={"published_key": key, "grounded": grounding["metadata"].get("grounding_valid")},
        metadata=dict(grounding["metadata"]),
    )


def _read_fact(action: Action, context: ToolExecutionContext) -> ToolResult:
    key = action.parameters.get("key")
    if not isinstance(key, str):
        return ToolResult(
            success=False,
            error_code="invalid_parameter",
            error_message="key must be a string.",
        )
    contract = context.shared_environment.fact_contracts.get(key)
    if contract and context.agent_state.agent_id not in contract.get("consumers", ()) and context.agent_state.agent_id != contract.get("producer_agent"):
        return ToolResult(False, error_code="shared_fact_not_readable", error_message="This agent cannot read the declared fact.")
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
    metadata = context.shared_environment.shared_fact_metadata.get(key, {})
    return ToolResult(
        success=True,
        output={
            "key": key,
            "value": value,
            "grounded": metadata.get("grounding_status") == "grounded",
            "evidence_source_tool": metadata.get("evidence_source_tool"),
            "evidence_source_resource_id": metadata.get("evidence_source_resource_id"),
            "evidence_source_authority": metadata.get("evidence_source_authority"),
            "evidence_authority_rank": metadata.get("evidence_authority_rank"),
            "authority_order": metadata.get("authority_order", []),
            "published_event_index": metadata.get("published_event_index"),
        },
    )


def _wait_for_dependency(action: Action, context: ToolExecutionContext) -> ToolResult:
    dependency_id = action.parameters.get("dependency_id")
    if not isinstance(dependency_id, str):
        return ToolResult(False, error_code="invalid_parameter", error_message="dependency_id must be a string.")
    return ToolResult(success=True, output={"dependency_id": dependency_id, "status": "waiting"})


def _finish(action: Action, context: ToolExecutionContext) -> ToolResult:
    progress = context.agent_state.memory.get("task_progress", {})
    lost_completed = list(
        progress.get("lost_completed_requirements", [])
    )
    if lost_completed:
        return ToolResult(
            False,
            error_code="completed_requirement_lost",
            error_message=(
                "A previously completed requirement is no longer satisfied."
            ),
            metadata={
                "lost_completed_requirement_ids": lost_completed,
                "terminal_allowed": False,
            },
        )
    unmet = list(progress.get("unmet_requirements", []))
    if unmet:
        resources = context.agent_state.memory.get("available_resources", {})
        return ToolResult(
            False,
            error_code="completion_requirements_unmet",
            error_message="Completion requirements remain unmet.",
            metadata={
                "unmet_requirement_ids": unmet,
                "unmet_requirement_contracts": progress.get(
                    "unmet_requirement_contracts",
                    [],
                ),
                "related_available_resources": resources.get("file_resources", []),
                "unchanged_failed_actions": progress.get(
                    "unchanged_failed_actions",
                    [],
                ),
                "terminal_allowed": False,
            },
        )
    return ToolResult(
        success=True,
        output={"status": "goal_completed", "terminal_allowed": True},
        metadata={"agent_id": context.agent_state.agent_id, "terminal_allowed": True},
    )


def _validate_fact_grounding(
    action: Action,
    context: ToolExecutionContext,
    contract: Mapping[str, Any] | None,
) -> dict[str, Any]:
    grounding_required = bool(contract and contract.get("grounding_required", False))
    metadata: dict[str, Any] = {
        "grounding_required": grounding_required,
        "grounding_valid": not grounding_required,
        "grounding_error_code": None,
        "normalized_value_match": None,
    }
    if not grounding_required:
        return {"success": True, "metadata": metadata}
    evidence_id = action.parameters.get("evidence_id")
    metadata["selected_evidence_id"] = evidence_id
    metadata["expected_source_tool"] = contract.get("required_source_tool") if contract else None
    metadata["expected_source_field"] = contract.get("required_source_field") if contract else None
    if not isinstance(evidence_id, str) or not evidence_id.strip():
        return _grounding_failure("evidence_id_required", metadata)
    evidence = _find_observed_evidence(context.agent_state, evidence_id)
    if evidence is None:
        return _grounding_failure("evidence_not_found", metadata)
    if evidence.get("agent_id") != context.agent_state.agent_id:
        return _grounding_failure("evidence_not_owned", metadata, evidence)
    if contract:
        source_contract = {
            "required_source_tool": contract.get("required_source_tool"),
            "required_source_field": contract.get("required_source_field"),
        }
        if not _evidence_matches_contract(evidence, source_contract):
            return _grounding_failure(
                "evidence_source_mismatch", metadata, evidence
            )
        authority_contract = {
            "required_source_resource_id": contract.get(
                "required_source_resource_id"
            ),
            "required_authority": contract.get("required_authority"),
            "required_authority_rank": contract.get(
                "required_authority_rank"
            ),
        }
        if not _evidence_matches_contract(evidence, authority_contract):
            metadata.update(
                {
                    "expected_source_resource_id": contract.get(
                        "required_source_resource_id"
                    ),
                    "expected_authority": contract.get(
                        "required_authority"
                    ),
                    "expected_authority_rank": contract.get(
                        "required_authority_rank"
                    ),
                    "authority_order": list(
                        contract.get("authority_order", ())
                    ),
                }
            )
            return _grounding_failure(
                "wrong_authority_selected", metadata, evidence
            )
    policy = str(contract.get("normalization_policy", "trimmed_text")) if contract else "trimmed_text"
    observed = _normalize_fact_value(evidence.get("observed_value"), policy)
    published = _normalize_fact_value(action.parameters.get("value"), policy)
    metadata.update(
        {
            "evidence_source_tool": evidence.get("source_tool"),
            "evidence_source_field": evidence.get("source_field"),
            "evidence_source_event_index": evidence.get("source_event_index"),
            "evidence_source_resource_id": evidence.get("source_resource_id"),
            "evidence_source_authority": evidence.get("source_authority"),
            "evidence_authority_rank": evidence.get("authority_rank"),
            "authority_order": list(contract.get("authority_order", ())) if contract else [],
            "normalized_observed_value_preview": _sanitize_text(observed, limit=120),
            "normalized_published_value": published,
            "normalized_published_value_preview": _sanitize_text(published, limit=120),
            "normalized_value_match": observed == published,
        }
    )
    if observed != published:
        metadata["grounding_recovery"] = {
            "evidence_id": evidence_id,
            "fact_key": action.parameters.get("key"),
            "source_tool": evidence.get("source_tool"),
            "source_field": evidence.get("source_field"),
            "exact_evidence_value": _sanitize_text(observed, limit=500),
            "attempted_value": _sanitize_text(published, limit=500),
            "instruction": (
                "Use this exact evidence value for the selected evidence_id; "
                "do not shorten, extract, summarize, or paraphrase it."
            ),
        }
        return _grounding_failure("published_value_mismatch", metadata, evidence)
    metadata["grounding_valid"] = True
    return {"success": True, "metadata": metadata}


def _grounding_failure(
    error_code: str,
    metadata: Mapping[str, Any],
    evidence: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = dict(metadata)
    payload["grounding_error_code"] = error_code
    if evidence is not None:
        payload.update(
            {
                "evidence_source_tool": evidence.get("source_tool"),
                "evidence_source_field": evidence.get("source_field"),
                "evidence_source_event_index": evidence.get("source_event_index"),
                "evidence_source_resource_id": evidence.get("source_resource_id"),
                "evidence_source_authority": evidence.get("source_authority"),
                "evidence_authority_rank": evidence.get("authority_rank"),
            }
        )
    return {"success": False, "error_code": error_code, "metadata": _sanitize_value(payload)}


def _find_observed_evidence(
    state: AgentState,
    evidence_id: str,
) -> Mapping[str, Any] | None:
    for evidence in state.memory.get("observed_evidence", []):
        if isinstance(evidence, Mapping) and evidence.get("evidence_id") == evidence_id:
            return evidence
    return None


def _evidence_matches_contract(
    evidence: Mapping[str, Any],
    contract: Mapping[str, Any],
) -> bool:
    required_tool = contract.get("required_source_tool")
    required_field = contract.get("required_source_field")
    required_resource = contract.get("required_source_resource_id")
    required_authority = contract.get("required_authority")
    required_rank = contract.get("required_authority_rank")

    if required_tool and evidence.get("source_tool") != required_tool:
        return False
    if (
        required_field
        and str(evidence.get("source_field", "")).casefold()
        != str(required_field).casefold()
    ):
        return False
    if required_resource and evidence.get("source_resource_id") != required_resource:
        return False
    if required_authority and evidence.get("source_authority") != required_authority:
        return False
    if isinstance(required_rank, int) and evidence.get("authority_rank") != required_rank:
        return False
    return True


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


def _requirement_description(requirement: Mapping[str, Any]) -> str:
    kind = requirement.get("kind")
    if kind == "tool_succeeded":
        return f"Complete a successful {requirement.get('tool_name')} action matching the declared parameters."
    if kind == "file_written":
        return "Write the declared bounded repository-relative file."
    if kind == "fact_published":
        return "Publish the declared shared fact for authorized consumers."
    if kind == "fact_published_grounded":
        return "Publish the declared shared fact with provenance from a matching own observation."
    if kind == "fact_read":
        return "Read the declared shared fact after it is available."
    if kind == "source_conflict_observed":
        return "Observe all declared contradictory sources and identify the highest-authority source."
    if kind == "error_observed":
        return f"Observe the expected recoverable error {requirement.get('error_code')}."
    if kind == "recovery_completed":
        return "After the expected recoverable error, use an advertised recovery resource successfully."
    return "Satisfy the declared completion requirement."


def _requirement_outcome(requirement: Mapping[str, Any]) -> str:
    kind = requirement.get("kind")
    if kind == "tool_succeeded":
        return "tool action succeeds with the declared safe parameters"
    if kind == "file_written":
        return "declared file path is created or appended"
    if kind == "fact_published":
        return "declared shared fact key is published"
    if kind == "fact_published_grounded":
        return "declared shared fact key is published with valid evidence provenance"
    if kind == "fact_read":
        return "declared shared fact key is read successfully"
    if kind == "source_conflict_observed":
        return "all declared conflicting sources are observed and the authority order is represented"
    if kind == "error_observed":
        return "expected recoverable error is observed"
    if kind == "recovery_completed":
        return "successful recovery action uses a different advertised resource after the source failure"
    return "requirement-specific predicate becomes true"


def _normalize_fact_value(value: Any, policy: str) -> str:
    text = str(value).replace("\r\n", "\n").replace("\r", "\n")
    if policy == "exact_text":
        return text
    text = re.sub(r"\s+", " ", text).strip()
    if policy == "casefolded_text":
        return text.casefold()
    if policy == "trimmed_text":
        return text
    return text


def _safe_evidence_token(value: str) -> str:
    token = re.sub(r"[^A-Za-z0-9_.-]+", "_", value.strip())[:48].strip("_.-")
    return token or "value"


def sanitize_runtime_value(value: Any) -> Any:
    """Return a bounded, path-safe, secret-redacted JSON-compatible value."""
    return _sanitize_value(value)


def _policy_telemetry(
    policy: ModelPolicy,
    started_at: float,
) -> tuple[float, int | None, int | None]:
    if not bool(getattr(policy, "model_execution_attempted", False)):
        return 0.0, None, None
    latency_ms = round((time.perf_counter() - started_at) * 1000, 3)
    input_tokens = getattr(policy, "last_input_tokens", None)
    output_tokens = getattr(policy, "last_output_tokens", None)
    return (
        latency_ms,
        input_tokens if isinstance(input_tokens, int) else None,
        output_tokens if isinstance(output_tokens, int) else None,
    )


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
