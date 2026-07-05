from __future__ import annotations

import json
import platform
import re
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

from .action_contract import (
    NextActionContractError,
    parse_next_action_text,
)
from .activity_evaluator import (
    ActivityTrajectoryEvaluator,
    ActivityTrajectoryStep,
)
from .activity_profile import load_activity_profile
from .evaluation_models import (
    EvaluationModelSpec,
    EvaluationModelsConfig,
    EvaluationModelRegistry,
    load_evaluation_models_config,
)
from .llm_client import LocalLLMClient
from .orchestrator_prompt_contract import (
    OrchestratorPlanJSONError,
    build_orchestrator_messages,
    build_orchestrator_repair_messages,
    parse_orchestrator_plan_text,
)
from .prompt_contract import PromptBuilder
from .role_template import (
    RoleTemplate,
    load_role_template,
    role_template_to_agent_state_defaults,
)
from .schemas import NextAction
from .script_execution_bridge import (
    ScriptExecutionBridge,
    ScriptExecutionBridgeConfig,
)
from .script_registry import (
    ScriptRegistry,
    load_script_registry,
    validate_next_action_against_registry,
)
from .state import (
    ActionHistoryEntry,
    ActionSpec,
    AgentState,
    load_agent_state,
)
from .virtual_network import (
    VirtualHostSpec,
    VirtualNetworkSpec,
    VirtualNetworkValidationError,
    load_virtual_network_spec,
)


GroupRunMode = Literal["fake", "local"]
GroupRunStatus = Literal["completed", "completed_with_failures", "failed"]
ModelRole = Literal["orchestrator", "executor"]


class OrchestratorModelConfig(BaseModel):
    model_id: str
    role: Literal["orchestrator"] = "orchestrator"
    base_url: str
    model_name: str
    temperature: float = 0.0
    max_tokens: int = 512
    timeout_seconds: float = 120.0


class ExecutorModelConfig(BaseModel):
    model_id: str
    role: Literal["executor"] = "executor"
    base_url: str
    model_name: str
    temperature: float = 0.0
    max_tokens: int = 512
    timeout_seconds: float = 120.0


class AgentAssignment(BaseModel):
    agent_id: str
    task_id: str
    assigned_goal: str
    executor_model_id: str
    success_criteria: str
    allowed_action_focus: list[str] = Field(default_factory=list)


class GroupAgentSpec(BaseModel):
    agent_id: str
    role_template_path: str
    activity_profile_path: str
    initial_state_path: str | None = None
    state_override: dict[str, Any] = Field(default_factory=dict)
    assigned_goal: str
    executor_model_id: str

    @field_validator("agent_id", "role_template_path", "activity_profile_path", "assigned_goal", "executor_model_id")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("GroupAgentSpec text fields must be non-empty.")
        return value


class ScenarioVirtualNetworkConfig(BaseModel):
    spec_path: str
    agent_host_map: dict[str, str] = Field(default_factory=dict)
    default_host_id: str | None = None

    @field_validator("spec_path")
    @classmethod
    def validate_spec_path(cls, value: str) -> str:
        return _safe_relative_config_reference(value, "virtual_network.spec_path")

    @field_validator("agent_host_map")
    @classmethod
    def validate_agent_host_map(cls, value: dict[str, str]) -> dict[str, str]:
        out: dict[str, str] = {}
        for agent_id, host_id in value.items():
            if not agent_id.strip() or not host_id.strip():
                raise ValueError("virtual_network.agent_host_map keys and values must be non-empty.")
            out[agent_id] = host_id
        return out

    @field_validator("default_host_id")
    @classmethod
    def validate_default_host_id(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("virtual_network.default_host_id must be non-empty when provided.")
        return value


@dataclass(frozen=True)
class LoadedVirtualNetworkBinding:
    config: ScenarioVirtualNetworkConfig
    spec: VirtualNetworkSpec
    agent_host_map: dict[str, str]


class OrchestratorPlanTask(BaseModel):
    task_id: str
    agent_id: str
    role_hint: str | None = None
    goal: str
    allowed_action_focus: list[str] = Field(default_factory=list)
    success_criteria: str
    dependencies: list[str] = Field(default_factory=list)


class OrchestratorPlan(BaseModel):
    plan_id: str
    scenario_id: str
    orchestrator_model_id: str
    tasks: list[OrchestratorPlanTask]
    coordination_notes: str
    expected_group_outcome: str


class ExecutorActionAttempt(BaseModel):
    group_step_index: int
    agent_step_index: int
    agent_id: str
    task_id: str
    attempt_index: int = 0
    attempt_type: Literal["initial", "repair"] = "initial"
    raw_model_output: str
    parse_success: bool = False
    action: str | None = None
    next_action: dict[str, Any] | None = None
    validation_accepted: bool | None = None
    validation_issues: list[dict[str, Any]] = Field(default_factory=list)
    execution_attempted: bool = False
    execution_success: bool | None = None
    execution_result: dict[str, Any] | None = None
    selection_latency_ms: float | None = None
    error_type: str | None = None
    error_message: str | None = None


class ExecutorAgentTrajectory(BaseModel):
    agent_id: str
    role_template_path: str
    activity_profile_path: str
    assigned_goal: str
    executor_model_id: str
    status: Literal["completed", "failed"] = "completed"
    success: bool = True
    attempts: list[ExecutorActionAttempt] = Field(default_factory=list)
    activity_evaluation: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class GroupHistoryRecord(BaseModel):
    group_step_index: int
    agent_id: str
    task_id: str
    action: str | None = None
    status: Literal["success", "failure", "skipped"] = "skipped"
    summary: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrchestratorPlanAttempt(BaseModel):
    attempt_index: int
    attempt_type: Literal["initial", "repair"]
    prompt: list[dict[str, str]] = Field(default_factory=list)
    raw_output: str = ""
    parse_success: bool = False
    validation_success: bool = False
    parse_error: str | None = None
    validation_errors: list[str] = Field(default_factory=list)
    latency_ms: float | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrchestratorExecutorQualityMetrics(BaseModel):
    orchestrator_plan_valid: bool
    task_assignment_valid_rate: float
    executor_initial_validation_rate: float
    executor_final_validation_rate: float
    execution_success_rate: float
    role_fit_mean: float
    diversity_mean: float
    repetition_mean: float
    history_usage_mean: float
    group_coordination_score: float
    task_completion_proxy_score: float
    safety_violation_count: int
    latency_mean_ms: float | None = None
    pair_quality_score: float
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrchestratorExecutorPairEvaluationResult(BaseModel):
    evaluation_id: str = "orchestrator_executor_pair_evaluation_v1"
    orchestrator_model_id: str
    executor_model_ids: list[str]
    metrics: OrchestratorExecutorQualityMetrics
    verdict: Literal["prototype_pass", "prototype_with_failures", "failed"]
    notes: list[str] = Field(default_factory=list)


class OrchestratorExecutorRunResult(BaseModel):
    run_id: str
    scenario_id: str
    orchestrator_model_id: str
    executor_model_ids: list[str]
    status: GroupRunStatus
    success: bool
    stopped_reason: str | None = None
    plan: OrchestratorPlan
    per_agent_results: list[ExecutorAgentTrajectory]
    group_history: list[GroupHistoryRecord]
    quality_metrics: OrchestratorExecutorQualityMetrics
    pair_evaluation: OrchestratorExecutorPairEvaluationResult
    virtual_network: dict[str, Any] | None = None
    artifact_dir: str | None = None
    warnings: list[str] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)


class OrchestratorExecutorScenario(BaseModel):
    scenario_id: str
    description: str
    orchestrator_model_id: str
    executor_model_id: str
    registry_path: str = "configs/script_registry.example.json"
    max_group_steps: int = 2
    max_steps_per_agent: int = 2
    execute_actions: bool = True
    expected_group_behavior: str
    agents: list[GroupAgentSpec]
    virtual_network: ScenarioVirtualNetworkConfig | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("scenario_id", "description", "orchestrator_model_id", "executor_model_id", "expected_group_behavior")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Scenario text fields must be non-empty.")
        return value

    @field_validator("max_group_steps", "max_steps_per_agent")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_group_steps and max_steps_per_agent must be >= 1.")
        return value

    @model_validator(mode="after")
    def validate_agents(self) -> OrchestratorExecutorScenario:
        if len(self.agents) < 2:
            raise ValueError("orchestrator/executor scenario requires at least two agents.")
        ids = [agent.agent_id for agent in self.agents]
        if len(ids) != len(set(ids)):
            raise ValueError("agent_id values must be unique.")
        return self


class OrchestratorExecutorRunConfig(BaseModel):
    project_root: Path = Path(".")
    mode: GroupRunMode = "fake"
    models_config_path: str = "configs/evaluation_models.json"
    scenario_path: str = "configs/multi_agent_scenarios/office_developer_group_basic.json"
    out_dir: str = "experiments/multi_agent/orchestrator_executor/default"
    run_id: str = "orchestrator_executor_group_run"
    orchestrator_model_id: str | None = None
    executor_model_id: str | None = None
    orchestrator_base_url: str | None = None
    executor_base_url: str | None = None
    orchestrator_model_name: str | None = None
    executor_model_name: str | None = None
    orchestrator_max_tokens: int | None = None
    orchestrator_temperature: float | None = None
    orchestrator_repair_attempts: int = 0
    max_group_steps: int | None = None
    max_steps_per_agent: int | None = None
    repair_attempts: int = 0
    execute_actions: bool | None = None
    force: bool = False

    @field_validator("project_root")
    @classmethod
    def resolve_project_root(cls, value: Path) -> Path:
        return value.resolve()

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("run_id must be non-empty.")
        return value

    @field_validator(
        "orchestrator_base_url",
        "executor_base_url",
        "orchestrator_model_name",
        "executor_model_name",
    )
    @classmethod
    def validate_optional_non_empty(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("Optional runtime override values must be non-empty when provided.")
        return value

    @field_validator("orchestrator_max_tokens")
    @classmethod
    def validate_optional_positive_int(cls, value: int | None) -> int | None:
        if value is not None and value <= 0:
            raise ValueError("orchestrator_max_tokens must be > 0 when provided.")
        return value

    @field_validator("orchestrator_temperature")
    @classmethod
    def validate_optional_temperature(cls, value: float | None) -> float | None:
        if value is not None and value < 0:
            raise ValueError("orchestrator_temperature must be >= 0 when provided.")
        return value

    @field_validator("repair_attempts", "orchestrator_repair_attempts")
    @classmethod
    def validate_repair_attempts(cls, value: int) -> int:
        if value < 0:
            raise ValueError("repair_attempts must be >= 0.")
        return value

    def project_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.project_root / path


class OrchestratorProviderResult(BaseModel):
    raw_model_output: str
    prompt_messages: list[dict[str, str]]
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExecutorProviderResult(BaseModel):
    raw_model_output: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class OrchestratorPlanProvider(Protocol):
    def create_plan(
        self,
        *,
        scenario: OrchestratorExecutorScenario,
        agents: list[GroupAgentSpec],
        agent_action_names: dict[str, set[str]],
    ) -> OrchestratorProviderResult:
        ...


class ExecutorActionProvider(Protocol):
    def next_action(
        self,
        *,
        agent: GroupAgentSpec,
        task: OrchestratorPlanTask,
        state: AgentState,
        group_step_index: int,
        agent_step_index: int,
        out_dir: Path,
        project_root: Path,
    ) -> ExecutorProviderResult:
        ...


class FakeOrchestratorPlanProvider:
    def create_plan(
        self,
        *,
        scenario: OrchestratorExecutorScenario,
        agents: list[GroupAgentSpec],
        agent_action_names: dict[str, set[str]],
    ) -> OrchestratorProviderResult:
        del agent_action_names
        tasks: list[dict[str, Any]] = []
        for index, agent in enumerate(agents, start=1):
            focus = ["read_file", "create_file"] if "office" in agent.agent_id else ["read_file"]
            tasks.append(
                {
                    "task_id": f"task_{index}",
                    "agent_id": agent.agent_id,
                    "goal": agent.assigned_goal,
                    "allowed_action_focus": focus,
                    "success_criteria": "Produce safe local evidence for the group objective.",
                    "role_hint": agent.agent_id,
                    "dependencies": [],
                }
            )
        raw = json.dumps(
            {
                "tasks": tasks,
                "coordination_notes": "Agents work independently and write/read only safe local project paths.",
                "expected_group_outcome": "Both agents perform safe local role-compatible actions.",
            },
            ensure_ascii=False,
            indent=2,
        )
        messages = build_orchestrator_messages(
            scenario_id=scenario.scenario_id,
            agents=[agent.model_dump(mode="json") for agent in agents],
            max_group_steps=scenario.max_group_steps,
        )
        return OrchestratorProviderResult(
            raw_model_output=raw,
            prompt_messages=messages,
            metadata={"provider": "fake_orchestrator"},
        )

    def repair_plan(
        self,
        *,
        scenario: OrchestratorExecutorScenario,
        agents: list[GroupAgentSpec],
        agent_action_names: dict[str, set[str]],
        previous_raw_output: str,
        error_message: str,
    ) -> OrchestratorProviderResult:
        del previous_raw_output, error_message
        return self.create_plan(scenario=scenario, agents=agents, agent_action_names=agent_action_names)


class FakeExecutorActionProvider:
    def next_action(
        self,
        *,
        agent: GroupAgentSpec,
        task: OrchestratorPlanTask,
        state: AgentState,
        group_step_index: int,
        agent_step_index: int,
        out_dir: Path,
        project_root: Path,
    ) -> ExecutorProviderResult:
        del task, state, group_step_index
        if "office" in agent.agent_id:
            if agent_step_index == 1:
                action = {
                    "action": "read_file",
                    "parameters": {"path": "docs/ai/model_research_metadata.md"},
                    "reason": "Inspect current model metadata before preparing a group note.",
                    "expected_result": "Research metadata is available for the office note.",
                }
            else:
                action = {
                    "action": "create_file",
                    "parameters": {
                        "path": _safe_relative_artifact_path(project_root, out_dir / "workspace" / "office_agent_summary.md"),
                        "content": "Office agent summary: model metadata was reviewed for the group run.\n",
                    },
                    "reason": "Use previous metadata review to create a concise safe local summary.",
                    "expected_result": "A local office summary note is created in the group artifact workspace.",
                }
        else:
            if agent_step_index == 1:
                action = {
                    "action": "read_file",
                    "parameters": {"path": "docs/ai/final_tz_readiness_audit.md"},
                    "reason": "Inspect the current readiness audit before developer follow-up.",
                    "expected_result": "Readiness gaps are available to guide the developer task.",
                }
            else:
                action = {
                    "action": "read_file",
                    "parameters": {"path": "docs/ai/orchestrator_executor_quality_spec.md"},
                    "reason": "Use previous readiness context and inspect the pair quality scoring draft.",
                    "expected_result": "Quality scoring context is available for the group history.",
                }
        return ExecutorProviderResult(
            raw_model_output=json.dumps(action, ensure_ascii=False, indent=2),
            metadata={"provider": "fake_executor", "agent_id": agent.agent_id},
        )


class LocalOrchestratorPlanProvider:
    def __init__(self, model: OrchestratorModelConfig) -> None:
        self.model = model

    def create_plan(
        self,
        *,
        scenario: OrchestratorExecutorScenario,
        agents: list[GroupAgentSpec],
        agent_action_names: dict[str, set[str]],
    ) -> OrchestratorProviderResult:
        messages = build_orchestrator_messages(
            scenario_id=scenario.scenario_id,
            agents=[
                {
                    **agent.model_dump(mode="json"),
                    "allowed_action_names": sorted(agent_action_names.get(agent.agent_id, set())),
                }
                for agent in agents
            ],
            max_group_steps=scenario.max_group_steps,
        )
        raw = self._chat(messages)
        return OrchestratorProviderResult(
            raw_model_output=raw,
            prompt_messages=messages,
            metadata={
                "provider": "local_orchestrator",
                "base_url": self.model.base_url,
                "max_tokens": self.model.max_tokens,
                "temperature": self.model.temperature,
            },
        )

    def repair_plan(
        self,
        *,
        scenario: OrchestratorExecutorScenario,
        agents: list[GroupAgentSpec],
        agent_action_names: dict[str, set[str]],
        previous_raw_output: str,
        error_message: str,
    ) -> OrchestratorProviderResult:
        messages = build_orchestrator_repair_messages(
            error_message=error_message,
            previous_raw_output=previous_raw_output,
            agents=[
                {
                    **agent.model_dump(mode="json"),
                    "allowed_action_names": sorted(agent_action_names.get(agent.agent_id, set())),
                }
                for agent in agents
            ],
            max_group_steps=scenario.max_group_steps,
        )
        raw = self._chat(messages)
        return OrchestratorProviderResult(
            raw_model_output=raw,
            prompt_messages=messages,
            metadata={
                "provider": "local_orchestrator_repair",
                "base_url": self.model.base_url,
                "max_tokens": self.model.max_tokens,
                "temperature": self.model.temperature,
            },
        )

    def _chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model.model_name,
            "messages": messages,
            "temperature": self.model.temperature,
            "max_tokens": self.model.max_tokens,
        }
        with httpx.Client(timeout=self.model.timeout_seconds, trust_env=False) as client:
            response = client.post(f"{self.model.base_url.rstrip('/')}/chat/completions", json=payload)
            response.raise_for_status()
            response_json = response.json()
        return LocalLLMClient.extract_assistant_content(response_json)


class LocalExecutorActionProvider:
    def __init__(self, model: ExecutorModelConfig) -> None:
        self.model = model
        self.prompt_builder = PromptBuilder()

    def next_action(
        self,
        *,
        agent: GroupAgentSpec,
        task: OrchestratorPlanTask,
        state: AgentState,
        group_step_index: int,
        agent_step_index: int,
        out_dir: Path,
        project_root: Path,
    ) -> ExecutorProviderResult:
        messages = self.prompt_builder.build_messages(state.to_prompt_context())
        raw = self._chat(messages)
        return ExecutorProviderResult(
            raw_model_output=raw,
            metadata={
                "provider": "local_executor",
                "base_url": self.model.base_url,
                "agent_id": agent.agent_id,
                "task_id": task.task_id,
                "attempt_type": "initial",
                "group_step_index": group_step_index,
                "agent_step_index": agent_step_index,
                "out_dir": str(out_dir),
                "project_root": str(project_root),
            },
        )

    def repair_action(
        self,
        *,
        agent: GroupAgentSpec,
        task: OrchestratorPlanTask,
        state: AgentState,
        group_step_index: int,
        agent_step_index: int,
        out_dir: Path,
        project_root: Path,
        previous_raw_output: str,
        validation_issues: list[dict[str, Any]],
        error_message: str,
    ) -> ExecutorProviderResult:
        messages = self.prompt_builder.build_messages(state.to_prompt_context())
        messages.append(
            {
                "role": "user",
                "content": _executor_repair_user_message(
                    agent=agent,
                    task=task,
                    state=state,
                    previous_raw_output=previous_raw_output,
                    validation_issues=validation_issues,
                    error_message=error_message,
                ),
            }
        )
        raw = self._chat(messages)
        return ExecutorProviderResult(
            raw_model_output=raw,
            metadata={
                "provider": "local_executor_repair",
                "base_url": self.model.base_url,
                "agent_id": agent.agent_id,
                "task_id": task.task_id,
                "attempt_type": "repair",
                "group_step_index": group_step_index,
                "agent_step_index": agent_step_index,
                "out_dir": str(out_dir),
                "project_root": str(project_root),
            },
        )

    def _chat(self, messages: list[dict[str, str]]) -> str:
        payload = {
            "model": self.model.model_name,
            "messages": messages,
            "temperature": self.model.temperature,
            "max_tokens": self.model.max_tokens,
        }
        with httpx.Client(timeout=self.model.timeout_seconds, trust_env=False) as client:
            response = client.post(f"{self.model.base_url.rstrip('/')}/chat/completions", json=payload)
            response.raise_for_status()
            response_json = response.json()
        return LocalLLMClient.extract_assistant_content(response_json)


class OrchestratorExecutorRunner:
    def __init__(
        self,
        config: OrchestratorExecutorRunConfig,
        *,
        orchestrator_provider: OrchestratorPlanProvider | None = None,
        executor_provider: ExecutorActionProvider | None = None,
    ) -> None:
        self.config = config
        self.orchestrator_provider = orchestrator_provider
        self.executor_provider = executor_provider

    def run(self) -> OrchestratorExecutorRunResult:
        started_at = _utc_now()
        perf_start = time.perf_counter()
        out_dir = self.config.project_path(self.config.out_dir)
        _prepare_output_dir(out_dir, force=self.config.force)

        scenario = load_orchestrator_executor_scenario(self.config.project_path(self.config.scenario_path))
        scenario = _apply_config_overrides(scenario, self.config)
        virtual_network_binding = _load_scenario_virtual_network(self.config, scenario)
        virtual_network_summary = _virtual_network_summary(virtual_network_binding)
        models_config = load_evaluation_models_config(self.config.project_path(self.config.models_config_path))
        registry = EvaluationModelRegistry(models_config)
        orchestrator_model = _orchestrator_model_config(registry.require(scenario.orchestrator_model_id))
        executor_model = _executor_model_config(registry.require(scenario.executor_model_id))
        orchestrator_model, executor_model = _apply_runtime_overrides(
            orchestrator_model,
            executor_model,
            self.config,
        )
        script_registry = load_script_registry(self.config.project_path(scenario.registry_path))

        role_templates = {
            agent.agent_id: load_role_template(self.config.project_path(agent.role_template_path))
            for agent in scenario.agents
        }
        agent_action_names = {
            agent.agent_id: _allowed_action_names(script_registry, role_templates[agent.agent_id])
            for agent in scenario.agents
        }

        orchestrator_provider = self.orchestrator_provider or (
            FakeOrchestratorPlanProvider()
            if self.config.mode == "fake"
            else LocalOrchestratorPlanProvider(orchestrator_model)
        )
        executor_provider = self.executor_provider or (
            FakeExecutorActionProvider()
            if self.config.mode == "fake"
            else LocalExecutorActionProvider(executor_model)
        )

        (
            provider_result,
            plan_payload,
            orchestrator_attempts,
            orchestrator_errors,
        ) = _run_orchestrator_plan_stage(
            orchestrator_provider=orchestrator_provider,
            scenario=scenario,
            agent_action_names=agent_action_names,
            repair_attempts=self.config.orchestrator_repair_attempts,
        )
        if provider_result is None or plan_payload is None:
            result = _failed_orchestrator_result(
                config=self.config,
                scenario=scenario,
                orchestrator_model=orchestrator_model,
                executor_model=executor_model,
                attempts=orchestrator_attempts,
                errors=orchestrator_errors,
                out_dir=out_dir,
                virtual_network_summary=virtual_network_summary,
            )
            _write_orchestrator_failure_artifacts(
                out_dir=out_dir,
                result=result,
                config=self.config,
                scenario=scenario,
                orchestrator_model=orchestrator_model,
                executor_model=executor_model,
                attempts=orchestrator_attempts,
                errors=orchestrator_errors,
                started_at=started_at,
                wall_time_seconds=time.perf_counter() - perf_start,
            )
            return result

        plan = OrchestratorPlan(
            plan_id=f"{self.config.run_id}_plan",
            scenario_id=scenario.scenario_id,
            orchestrator_model_id=scenario.orchestrator_model_id,
            tasks=[
                OrchestratorPlanTask.model_validate(task.model_dump(mode="json"))
                for task in plan_payload.tasks
            ],
            coordination_notes=plan_payload.coordination_notes,
            expected_group_outcome=plan_payload.expected_group_outcome,
        )

        assignments = _assignments_from_plan(plan, scenario)
        (out_dir / "workspace").mkdir(parents=True, exist_ok=True)
        states = {
            agent.agent_id: _build_agent_state(
                self.config.project_root,
                agent,
                role_templates[agent.agent_id],
                script_registry,
                assignments[agent.agent_id],
                out_dir,
                virtual_network_context=_agent_virtual_network_context(virtual_network_binding, agent.agent_id),
            )
            for agent in scenario.agents
        }
        bridge = ScriptExecutionBridge(
            ScriptExecutionBridgeConfig(
                project_root=self.config.project_root,
                registry_path=scenario.registry_path,
                validate_with_registry=True,
                normalize_result=True,
                write_history=False,
            ),
            registry=script_registry,
        )

        trajectories = {
            agent.agent_id: ExecutorAgentTrajectory(
                agent_id=agent.agent_id,
                role_template_path=agent.role_template_path,
                activity_profile_path=agent.activity_profile_path,
                assigned_goal=assignments[agent.agent_id].assigned_goal,
                executor_model_id=agent.executor_model_id,
            )
            for agent in scenario.agents
        }
        group_history: list[GroupHistoryRecord] = []
        errors: list[dict[str, Any]] = list(orchestrator_errors)

        task_by_agent = {task.agent_id: task for task in plan.tasks}
        per_group_step_budget = _uses_per_group_step_agent_budget(scenario)
        for group_step in range(1, scenario.max_group_steps + 1):
            for agent in scenario.agents:
                trajectory = trajectories[agent.agent_id]
                completed_agent_steps = sum(
                    1
                    for attempt in trajectory.attempts
                    if attempt.attempt_type == "initial"
                    and (not per_group_step_budget or attempt.group_step_index == group_step)
                )
                if completed_agent_steps >= scenario.max_steps_per_agent:
                    continue
                state = states[agent.agent_id]
                task = task_by_agent[agent.agent_id]
                attempts = _run_executor_step(
                    executor_provider=executor_provider,
                    scenario=scenario,
                    agent=agent,
                    task=task,
                    state=state,
                    role_template=role_templates[agent.agent_id],
                    registry=script_registry,
                    bridge=bridge,
                    group_step_index=group_step,
                    execute_actions=scenario.execute_actions,
                    out_dir=out_dir,
                    project_root=self.config.project_root,
                    repair_attempts=self.config.repair_attempts,
                )
                trajectory.attempts.extend(attempts)
                final_attempt = attempts[-1]
                _update_state_history(state, final_attempt)
                group_history.append(
                    _history_from_attempt(
                        final_attempt,
                        virtual_network_metadata=_agent_history_virtual_network_metadata(
                            virtual_network_binding,
                            agent.agent_id,
                        ),
                    )
                )
                for attempt in attempts:
                    if attempt.error_type:
                        errors.append(
                            {
                                "stage": "executor",
                                "agent_id": agent.agent_id,
                                "task_id": task.task_id,
                                "group_step_index": group_step,
                                "agent_step_index": attempt.agent_step_index,
                                "attempt_index": attempt.attempt_index,
                                "attempt_type": attempt.attempt_type,
                                "error_type": attempt.error_type,
                                "error_message": attempt.error_message,
                                "validation_issues": attempt.validation_issues,
                            }
                        )

        activity_profiles = {
            agent.agent_id: load_activity_profile(self.config.project_path(agent.activity_profile_path))
            for agent in scenario.agents
        }
        evaluator = ActivityTrajectoryEvaluator()
        for agent in scenario.agents:
            trajectory = trajectories[agent.agent_id]
            activity_steps = _activity_steps_from_attempts(trajectory.attempts)
            activity_result = evaluator.evaluate(activity_steps, activity_profiles[agent.agent_id])
            trajectory.activity_evaluation = activity_result.model_dump(mode="json")
            trajectory.success = bool(trajectory.attempts) and all(
                attempt.error_type is None for attempt in trajectory.attempts
            )
            trajectory.status = "completed" if trajectory.success else "failed"

        quality = _compute_quality_metrics(
            plan=plan,
            assignments=assignments,
            trajectories=list(trajectories.values()),
            scenario=scenario,
        )
        pair_eval = _pair_evaluation(scenario, quality)
        status: GroupRunStatus = "completed" if not errors else "completed_with_failures"
        success = not errors
        result = OrchestratorExecutorRunResult(
            run_id=self.config.run_id,
            scenario_id=scenario.scenario_id,
            orchestrator_model_id=scenario.orchestrator_model_id,
            executor_model_ids=sorted({agent.executor_model_id for agent in scenario.agents}),
            status=status,
            success=success,
            stopped_reason=None if success else "One or more executor steps failed.",
            plan=plan,
            per_agent_results=list(trajectories.values()),
            group_history=group_history,
            quality_metrics=quality,
            pair_evaluation=pair_eval,
            virtual_network=virtual_network_summary,
            artifact_dir=str(out_dir),
            warnings=_runtime_warnings(self.config.mode, orchestrator_model, executor_model),
            errors=errors,
        )
        result.quality_metrics.metadata.update(
            {
                "orchestrator_attempt_count": len(orchestrator_attempts),
                "orchestrator_repair_attempted": any(
                    attempt.attempt_type == "repair" for attempt in orchestrator_attempts
                ),
                "orchestrator_plan_initial_parse_success": (
                    orchestrator_attempts[0].parse_success if orchestrator_attempts else False
                ),
                "orchestrator_plan_final_validation_success": (
                    orchestrator_attempts[-1].validation_success if orchestrator_attempts else False
                ),
            }
        )
        _write_artifacts(
            out_dir=out_dir,
            result=result,
            config=self.config,
            scenario=scenario,
            orchestrator_model=orchestrator_model,
            executor_model=executor_model,
            provider_result=provider_result,
            orchestrator_attempts=orchestrator_attempts,
            assignments=assignments,
            started_at=started_at,
            wall_time_seconds=time.perf_counter() - perf_start,
        )
        return result


def _run_orchestrator_plan_stage(
    *,
    orchestrator_provider: OrchestratorPlanProvider,
    scenario: OrchestratorExecutorScenario,
    agent_action_names: dict[str, set[str]],
    repair_attempts: int,
) -> tuple[
    OrchestratorProviderResult | None,
    Any | None,
    list[OrchestratorPlanAttempt],
    list[dict[str, Any]],
]:
    attempts: list[OrchestratorPlanAttempt] = []
    errors: list[dict[str, Any]] = []
    previous_raw = ""
    previous_error = ""
    provider_result: OrchestratorProviderResult | None = None
    plan_payload: Any | None = None

    for attempt_index in range(0, repair_attempts + 1):
        attempt_type: Literal["initial", "repair"] = "initial" if attempt_index == 0 else "repair"
        started = time.perf_counter()
        if attempt_type == "initial":
            provider_result = orchestrator_provider.create_plan(
                scenario=scenario,
                agents=scenario.agents,
                agent_action_names=agent_action_names,
            )
        else:
            provider_result = _repair_orchestrator_plan(
                orchestrator_provider=orchestrator_provider,
                scenario=scenario,
                agent_action_names=agent_action_names,
                previous_raw_output=previous_raw,
                error_message=previous_error,
            )
        latency_ms = _elapsed_ms(started)
        attempt, maybe_plan = _orchestrator_attempt_from_result(
            attempt_index=attempt_index,
            attempt_type=attempt_type,
            provider_result=provider_result,
            latency_ms=latency_ms,
            known_agent_ids={agent.agent_id for agent in scenario.agents},
            allowed_action_names_by_agent=agent_action_names,
        )
        attempts.append(attempt)
        if maybe_plan is not None:
            plan_payload = maybe_plan
            break
        previous_raw = provider_result.raw_model_output
        previous_error = attempt.parse_error or "; ".join(attempt.validation_errors) or "Unknown orchestrator plan error."
        errors.append(
            {
                "stage": "orchestrator",
                "attempt_index": attempt.attempt_index,
                "attempt_type": attempt.attempt_type,
                "error_type": "orchestrator_plan_parse_failed"
                if not attempt.parse_success
                else "orchestrator_plan_validation_failed",
                "error_message": previous_error,
            }
        )

    return provider_result, plan_payload, attempts, errors


def _repair_orchestrator_plan(
    *,
    orchestrator_provider: OrchestratorPlanProvider,
    scenario: OrchestratorExecutorScenario,
    agent_action_names: dict[str, set[str]],
    previous_raw_output: str,
    error_message: str,
) -> OrchestratorProviderResult:
    repair_method = getattr(orchestrator_provider, "repair_plan", None)
    if callable(repair_method):
        return repair_method(
            scenario=scenario,
            agents=scenario.agents,
            agent_action_names=agent_action_names,
            previous_raw_output=previous_raw_output,
            error_message=error_message,
        )
    return orchestrator_provider.create_plan(
        scenario=scenario,
        agents=scenario.agents,
        agent_action_names=agent_action_names,
    )


def _orchestrator_attempt_from_result(
    *,
    attempt_index: int,
    attempt_type: Literal["initial", "repair"],
    provider_result: OrchestratorProviderResult,
    latency_ms: float,
    known_agent_ids: set[str],
    allowed_action_names_by_agent: dict[str, set[str]],
) -> tuple[OrchestratorPlanAttempt, Any | None]:
    parse_success = False
    parse_error: str | None = None
    validation_success = False
    validation_errors: list[str] = []
    plan_payload: Any | None = None

    try:
        json.loads(provider_result.raw_model_output)
        parse_success = True
    except json.JSONDecodeError as exc:
        parse_error = f"Invalid orchestrator JSON output: {exc}"

    if parse_success:
        try:
            plan_payload = parse_orchestrator_plan_text(
                provider_result.raw_model_output,
                known_agent_ids=known_agent_ids,
                allowed_action_names_by_agent=allowed_action_names_by_agent,
            )
            validation_success = True
        except OrchestratorPlanJSONError as exc:
            validation_errors = [str(exc)]

    return (
        OrchestratorPlanAttempt(
            attempt_index=attempt_index,
            attempt_type=attempt_type,
            prompt=provider_result.prompt_messages,
            raw_output=provider_result.raw_model_output,
            parse_success=parse_success,
            validation_success=validation_success,
            parse_error=parse_error,
            validation_errors=validation_errors,
            latency_ms=latency_ms,
            metadata=provider_result.metadata,
        ),
        plan_payload,
    )


def _failed_orchestrator_result(
    *,
    config: OrchestratorExecutorRunConfig,
    scenario: OrchestratorExecutorScenario,
    orchestrator_model: OrchestratorModelConfig,
    executor_model: ExecutorModelConfig,
    attempts: list[OrchestratorPlanAttempt],
    errors: list[dict[str, Any]],
    out_dir: Path,
    virtual_network_summary: dict[str, Any] | None,
) -> OrchestratorExecutorRunResult:
    reason = _final_orchestrator_error(attempts)
    plan = OrchestratorPlan(
        plan_id=f"{config.run_id}_plan_failed",
        scenario_id=scenario.scenario_id,
        orchestrator_model_id=scenario.orchestrator_model_id,
        tasks=[],
        coordination_notes="",
        expected_group_outcome="",
    )
    metrics = _failed_quality_metrics(reason=reason, attempts=attempts)
    pair_eval = OrchestratorExecutorPairEvaluationResult(
        orchestrator_model_id=orchestrator_model.model_id,
        executor_model_ids=[executor_model.model_id],
        metrics=metrics,
        verdict="failed",
        notes=[
            "Orchestrator plan was not valid; executor stage was not reached.",
            "Diagnostic artifacts preserve prompt, raw output, and parse/validation errors.",
        ],
    )
    return OrchestratorExecutorRunResult(
        run_id=config.run_id,
        scenario_id=scenario.scenario_id,
        orchestrator_model_id=scenario.orchestrator_model_id,
        executor_model_ids=[executor_model.model_id],
        status="failed",
        success=False,
        stopped_reason=reason,
        plan=plan,
        per_agent_results=[],
        group_history=[],
        quality_metrics=metrics,
        pair_evaluation=pair_eval,
        virtual_network=virtual_network_summary,
        artifact_dir=str(out_dir),
        warnings=_runtime_warnings(config.mode, orchestrator_model, executor_model),
        errors=errors,
    )


def load_orchestrator_executor_scenario(path: str | Path) -> OrchestratorExecutorScenario:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return OrchestratorExecutorScenario.model_validate(payload)


def _apply_config_overrides(
    scenario: OrchestratorExecutorScenario,
    config: OrchestratorExecutorRunConfig,
) -> OrchestratorExecutorScenario:
    payload = scenario.model_dump(mode="json")
    if config.orchestrator_model_id:
        payload["orchestrator_model_id"] = config.orchestrator_model_id
    if config.executor_model_id:
        payload["executor_model_id"] = config.executor_model_id
        for agent in payload["agents"]:
            agent["executor_model_id"] = config.executor_model_id
    if config.max_group_steps is not None:
        payload["max_group_steps"] = config.max_group_steps
    if config.max_steps_per_agent is not None:
        payload["max_steps_per_agent"] = config.max_steps_per_agent
    if config.execute_actions is not None:
        payload["execute_actions"] = config.execute_actions
    return OrchestratorExecutorScenario.model_validate(payload)


def _load_scenario_virtual_network(
    config: OrchestratorExecutorRunConfig,
    scenario: OrchestratorExecutorScenario,
) -> LoadedVirtualNetworkBinding | None:
    if scenario.virtual_network is None:
        return None

    spec = load_virtual_network_spec(config.project_path(scenario.virtual_network.spec_path))
    known_agent_ids = {agent.agent_id for agent in scenario.agents}
    agent_host_map = dict(scenario.virtual_network.agent_host_map)

    if scenario.virtual_network.default_host_id is not None:
        default_host_id = scenario.virtual_network.default_host_id
        if spec.get_host(default_host_id) is None:
            raise VirtualNetworkValidationError(
                f"virtual_network.default_host_id references unknown host_id '{default_host_id}'."
            )
        for agent_id in known_agent_ids:
            agent_host_map.setdefault(agent_id, default_host_id)

    for agent_id, host_id in agent_host_map.items():
        if agent_id not in known_agent_ids:
            raise VirtualNetworkValidationError(
                f"virtual_network.agent_host_map references unknown agent_id '{agent_id}'."
            )
        if spec.get_host(host_id) is None:
            raise VirtualNetworkValidationError(
                f"virtual_network.agent_host_map for agent_id '{agent_id}' references unknown host_id '{host_id}'."
            )

    return LoadedVirtualNetworkBinding(
        config=scenario.virtual_network,
        spec=spec,
        agent_host_map=agent_host_map,
    )


def _virtual_network_summary(binding: LoadedVirtualNetworkBinding | None) -> dict[str, Any] | None:
    if binding is None:
        return None
    used_host_ids = sorted(dict.fromkeys(binding.agent_host_map.values()))
    return {
        "network_id": binding.spec.network_id,
        "spec_path": binding.config.spec_path,
        "metadata_only": True,
        "real_network_actions_recorded": False,
        "agent_host_map": dict(sorted(binding.agent_host_map.items())),
        "hosts_used": [
            _virtual_host_summary(host)
            for host_id in used_host_ids
            if (host := binding.spec.get_host(host_id)) is not None
        ],
        "services_available": [
            {
                "service_id": service.service_id,
                "kind": service.kind,
                "display_name": service.display_name,
                "base_url": service.base_url,
                "root_path": service.root_path,
                "allowed_actions": list(service.allowed_actions),
            }
            for service in binding.spec.services
        ],
    }


def _agent_virtual_network_context(
    binding: LoadedVirtualNetworkBinding | None,
    agent_id: str,
) -> dict[str, Any] | None:
    if binding is None:
        return None
    host_id = binding.agent_host_map.get(agent_id)
    base = {
        "network_id": binding.spec.network_id,
        "spec_path": binding.config.spec_path,
        "metadata_only": True,
        "host_bound": host_id is not None,
    }
    if host_id is None:
        return base
    host = binding.spec.get_host(host_id)
    if host is None:
        return base
    return {
        **base,
        **_virtual_host_summary(host),
    }


def _agent_history_virtual_network_metadata(
    binding: LoadedVirtualNetworkBinding | None,
    agent_id: str,
) -> dict[str, Any] | None:
    context = _agent_virtual_network_context(binding, agent_id)
    if context is None:
        return None
    return {
        "network_id": context["network_id"],
        "host_id": context.get("host_id"),
        "host_bound": context.get("host_bound", False),
        "metadata_only": True,
    }


def _virtual_host_summary(host: VirtualHostSpec) -> dict[str, Any]:
    return {
        "host_id": host.host_id,
        "host_display_name": host.display_name,
        "host_role": host.role,
        "workspace_root": host.workspace_root,
        "allowed_service_ids": list(host.allowed_service_ids),
        "allowed_url_prefixes": list(host.allowed_url_prefixes),
    }


def _safe_relative_config_reference(value: str, field_name: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{field_name} must be non-empty.")
    raw = value.strip().replace("\\", "/")
    codex_fragment = "." + "codex"
    lowered = raw.lower()
    if "://" in raw:
        raise ValueError(f"{field_name} must be a relative local config path, not a URL.")
    if PureWindowsPath(value).is_absolute() or PurePosixPath(raw).is_absolute():
        raise ValueError(f"{field_name} must be relative.")
    if any(part == ".." for part in PurePosixPath(raw).parts):
        raise ValueError(f"{field_name} must not contain path traversal.")
    if "auth.json" in lowered or codex_fragment in lowered:
        raise ValueError(f"{field_name} must not reference private local files.")
    return raw


def _orchestrator_model_config(spec: EvaluationModelSpec) -> OrchestratorModelConfig:
    return OrchestratorModelConfig(
        model_id=spec.model_id,
        base_url=spec.base_url,
        model_name=spec.model_name,
        temperature=spec.temperature,
        max_tokens=spec.max_tokens,
        timeout_seconds=spec.timeout_seconds,
    )


def _executor_model_config(spec: EvaluationModelSpec) -> ExecutorModelConfig:
    return ExecutorModelConfig(
        model_id=spec.model_id,
        base_url=spec.base_url,
        model_name=spec.model_name,
        temperature=spec.temperature,
        max_tokens=spec.max_tokens,
        timeout_seconds=spec.timeout_seconds,
    )


def _apply_runtime_overrides(
    orchestrator_model: OrchestratorModelConfig,
    executor_model: ExecutorModelConfig,
    config: OrchestratorExecutorRunConfig,
) -> tuple[OrchestratorModelConfig, ExecutorModelConfig]:
    orchestrator_updates: dict[str, Any] = {}
    executor_updates: dict[str, Any] = {}
    if config.orchestrator_base_url:
        orchestrator_updates["base_url"] = config.orchestrator_base_url.rstrip("/")
    if config.executor_base_url:
        executor_updates["base_url"] = config.executor_base_url.rstrip("/")
    if config.orchestrator_model_name:
        orchestrator_updates["model_name"] = config.orchestrator_model_name
    if config.executor_model_name:
        executor_updates["model_name"] = config.executor_model_name
    if config.orchestrator_max_tokens is not None:
        orchestrator_updates["max_tokens"] = config.orchestrator_max_tokens
    if config.orchestrator_temperature is not None:
        orchestrator_updates["temperature"] = config.orchestrator_temperature
    return (
        orchestrator_model.model_copy(update=orchestrator_updates),
        executor_model.model_copy(update=executor_updates),
    )


def _allowed_action_names(registry: ScriptRegistry, role_template: RoleTemplate) -> set[str]:
    role_allowed = role_template.constraints.allowed_action_names
    if role_allowed:
        return set(role_allowed) & registry.script_names()
    return registry.script_names()


def _assignments_from_plan(
    plan: OrchestratorPlan,
    scenario: OrchestratorExecutorScenario,
) -> dict[str, AgentAssignment]:
    agents = {agent.agent_id: agent for agent in scenario.agents}
    out: dict[str, AgentAssignment] = {}
    for task in plan.tasks:
        agent = agents[task.agent_id]
        out[task.agent_id] = AgentAssignment(
            agent_id=task.agent_id,
            task_id=task.task_id,
            assigned_goal=task.goal,
            executor_model_id=agent.executor_model_id,
            success_criteria=task.success_criteria,
            allowed_action_focus=list(task.allowed_action_focus),
        )
    missing = sorted(set(agents) - set(out))
    if missing:
        raise OrchestratorPlanJSONError(f"Orchestrator plan did not assign all agents: {missing}")
    return out


def _uses_per_group_step_agent_budget(scenario: OrchestratorExecutorScenario) -> bool:
    return scenario.metadata.get("agent_step_budget_scope") == "per_group_step"


def _build_agent_state(
    project_root: Path,
    agent: GroupAgentSpec,
    role_template: RoleTemplate,
    registry: ScriptRegistry,
    assignment: AgentAssignment,
    out_dir: Path,
    *,
    virtual_network_context: dict[str, Any] | None = None,
) -> AgentState:
    if agent.initial_state_path:
        state = load_agent_state(project_root / agent.initial_state_path)
        payload = state.model_dump(mode="json")
    else:
        payload = role_template_to_agent_state_defaults(role_template)
        payload.update(
            {
                "agent_id": agent.agent_id,
                "environment": {
                    "os": platform.platform(),
                    "project_root": str(project_root),
                    "runtime": "orchestrator_executor_pipeline_v1",
                    "network_allowed": False,
                    "notes": ["No external network in group MVP."],
                },
                "available_actions": [
                    _action_spec_from_descriptor(registry.get_script(name)).model_dump(mode="json")
                    for name in sorted(_allowed_action_names(registry, role_template))
                    if registry.get_script(name) is not None
                ],
                "history": [],
                "current_step": 1,
            }
        )
    payload["agent_id"] = agent.agent_id
    payload["objective"]["primary"] = assignment.assigned_goal
    payload["objective"]["success_criteria"] = list(
        dict.fromkeys([*payload["objective"].get("success_criteria", []), assignment.success_criteria])
    )
    if virtual_network_context is not None:
        _attach_virtual_network_context(payload, virtual_network_context)
    payload["metadata"] = {
        **payload.get("metadata", {}),
        **agent.state_override,
        "assigned_goal": assignment.assigned_goal,
        "executor_model_id": assignment.executor_model_id,
        "orchestrator_task_id": assignment.task_id,
        "executor_prompt_hints": _executor_prompt_hints(
            project_root=project_root,
            agent=agent,
            role_template=role_template,
            registry=registry,
            assignment=assignment,
            out_dir=out_dir,
        ),
    }
    return AgentState.model_validate(payload)


def _attach_virtual_network_context(payload: dict[str, Any], context: dict[str, Any]) -> None:
    environment = dict(payload.get("environment") or {})
    resources = dict(payload.get("resources") or {})
    metadata = dict(payload.get("metadata") or {})

    environment["network_allowed"] = False
    environment["virtual_network"] = {
        "network_id": context.get("network_id"),
        "host_id": context.get("host_id"),
        "host_display_name": context.get("host_display_name"),
        "host_role": context.get("host_role"),
        "workspace_root": context.get("workspace_root"),
        "metadata_only": True,
    }
    environment["notes"] = _append_unique_text(
        environment.get("notes"),
        "Virtual network binding is metadata-only; no real services are started by this runner.",
    )

    allowed_url_prefixes = _string_values(context.get("allowed_url_prefixes"))
    resources["endpoints"] = sorted(dict.fromkeys([*_string_values(resources.get("endpoints")), *allowed_url_prefixes]))
    resources["virtual_network"] = {
        "network_id": context.get("network_id"),
        "host_id": context.get("host_id"),
        "allowed_service_ids": _string_values(context.get("allowed_service_ids")),
        "allowed_url_prefixes": allowed_url_prefixes,
        "workspace_root": context.get("workspace_root"),
        "metadata_only": True,
    }

    metadata["virtual_network"] = dict(context)
    payload["environment"] = environment
    payload["resources"] = resources
    payload["metadata"] = metadata


def _append_unique_text(value: Any, item: str) -> list[str]:
    values = _string_values(value)
    if item not in values:
        values.append(item)
    return values


def _string_values(value: Any) -> list[str]:
    if not isinstance(value, list):
        return []
    return [item for item in value if isinstance(item, str)]


def _action_spec_from_descriptor(descriptor: Any) -> ActionSpec:
    assert descriptor is not None
    return ActionSpec(
        name=descriptor.name,
        description=descriptor.description,
        parameters_schema={
            p.name: {
                "type": p.type,
                "required": p.required,
                "description": p.description,
            }
            for p in descriptor.parameters
        },
        safety_notes=list(descriptor.safety.notes),
    )


def _executor_prompt_hints(
    *,
    project_root: Path,
    agent: GroupAgentSpec,
    role_template: RoleTemplate,
    registry: ScriptRegistry,
    assignment: AgentAssignment,
    out_dir: Path,
) -> dict[str, Any]:
    allowed_actions = sorted(_allowed_action_names(registry, role_template))
    action_schemas: dict[str, Any] = {}
    safe_path_roots: set[str] = set()
    safe_existing_read_paths: set[str] = set()
    safe_write_path_examples: set[str] = set()

    for action_name in allowed_actions:
        descriptor = registry.get_script(action_name)
        if descriptor is None:
            continue
        roots = _effective_allowed_file_roots(descriptor, role_template)
        safe_path_roots.update(roots)
        examples = _safe_action_examples(
            project_root=project_root,
            descriptor=descriptor,
            roots=roots,
            agent_id=agent.agent_id,
            out_dir=out_dir,
        )
        for example in examples:
            path = example.get("path")
            if not isinstance(path, str):
                continue
            if descriptor.safety.read_only:
                safe_existing_read_paths.add(path)
            else:
                safe_write_path_examples.add(path)

        action_schemas[action_name] = {
            "description": descriptor.description,
            "required_parameters": sorted(descriptor.required_parameter_names()),
            "parameters": {
                parameter.name: {
                    "type": parameter.type,
                    "required": parameter.required,
                    "description": parameter.description,
                }
                for parameter in descriptor.parameters
            },
            "allowed_file_roots": roots,
            "forbidden_file_roots": sorted(
                set(_normalized_roots(descriptor.safety.forbidden_file_roots))
                | set(_normalized_roots(role_template.constraints.forbidden_file_roots))
            ),
            "allowed_shell_commands": list(descriptor.safety.allowed_shell_commands),
            "examples": examples[:3],
        }

    json_only_example = _next_action_json_example(action_schemas, safe_existing_read_paths, safe_write_path_examples)
    return {
        "agent_id": agent.agent_id,
        "role_id": role_template.role_id,
        "task_id": assignment.task_id,
        "assigned_goal": assignment.assigned_goal,
        "success_criteria": assignment.success_criteria,
        "allowed_action_focus": list(assignment.allowed_action_focus),
        "allowed_actions": allowed_actions,
        "action_schemas": action_schemas,
        "safe_path_roots": sorted(safe_path_roots),
        "safe_existing_read_paths": sorted(safe_existing_read_paths),
        "safe_write_path_examples": sorted(safe_write_path_examples),
        "path_rules": [
            "Use relative project paths only.",
            "Use forward slashes.",
            "Do not include drive letters such as C:/.",
            "Do not include leading slashes.",
            "Do not include '..' traversal.",
            "Do not touch models/gguf/, .venv/, or .git/.",
        ],
        "json_only_example": json_only_example,
    }


def _effective_allowed_file_roots(descriptor: Any, role_template: RoleTemplate) -> list[str]:
    registry_roots = _normalized_roots(descriptor.safety.allowed_file_roots)
    role_roots = _normalized_roots(role_template.constraints.allowed_file_roots)
    if not registry_roots:
        return role_roots
    if not role_roots:
        return registry_roots

    effective: set[str] = set()
    for registry_root in registry_roots:
        for role_root in role_roots:
            if registry_root == role_root:
                effective.add(registry_root)
            elif registry_root.startswith(role_root):
                effective.add(registry_root)
            elif role_root.startswith(registry_root):
                effective.add(role_root)
    return sorted(effective)


def _normalized_roots(roots: list[str]) -> list[str]:
    normalized: list[str] = []
    for root in roots:
        value = root.replace("\\", "/")
        if value and not value.endswith("/"):
            value += "/"
        if value:
            normalized.append(value)
    return sorted(dict.fromkeys(normalized))


def _safe_action_examples(
    *,
    project_root: Path,
    descriptor: Any,
    roots: list[str],
    agent_id: str,
    out_dir: Path,
) -> list[dict[str, Any]]:
    examples: list[dict[str, Any]] = []
    if any(parameter.name == "path" for parameter in descriptor.parameters):
        if descriptor.safety.read_only:
            for candidate in [
                "configs/multi_agent_fixtures/office_developer_maintenance/team_brief.md",
                "configs/multi_agent_fixtures/office_developer_maintenance/maintenance_notes.md",
                "configs/multi_agent_fixtures/office_developer_maintenance/project_context.md",
                "docs/ai/model_research_metadata.md",
                "docs/ai/final_tz_readiness_audit.md",
                "docs/ai/orchestrator_executor_quality_spec.md",
                "configs/evaluation_models.json",
            ]:
                if _path_allowed_by_roots(candidate, roots) and (project_root / candidate).exists():
                    examples.append({"path": candidate})
        else:
            safe_out = _safe_relative_artifact_path(
                project_root,
                out_dir / "workspace" / f"{agent_id}_executor_note.md",
            )
            if _path_allowed_by_roots(safe_out, roots):
                examples.append({"path": safe_out, "content": f"{agent_id} local group note.\n"})

    if descriptor.safety.read_only:
        for example in descriptor.examples:
            path = example.get("path")
            if isinstance(path, str) and roots and not _path_allowed_by_roots(path, roots):
                continue
            examples.append(dict(example))

    deduped: list[dict[str, Any]] = []
    seen: set[str] = set()
    for example in examples:
        key = json.dumps(example, ensure_ascii=False, sort_keys=True)
        if key in seen:
            continue
        seen.add(key)
        deduped.append(example)
    return deduped


def _path_allowed_by_roots(path: str, roots: list[str]) -> bool:
    normalized = path.replace("\\", "/")
    if not roots:
        return True
    return any(normalized.startswith(root) for root in roots)


def _next_action_json_example(
    action_schemas: dict[str, Any],
    safe_existing_read_paths: set[str],
    safe_write_path_examples: set[str],
) -> dict[str, Any]:
    if "read_file" in action_schemas:
        path = sorted(safe_existing_read_paths)[0] if safe_existing_read_paths else "docs/ai/model_research_metadata.md"
        return {
            "action": "read_file",
            "parameters": {"path": path},
            "reason": "Read a safe local project document for the assigned task.",
            "expected_result": "The local document content is available.",
        }
    if "create_file" in action_schemas:
        path = (
            sorted(safe_write_path_examples)[0]
            if safe_write_path_examples
            else "experiments/multi_agent/orchestrator_executor/workspace/executor_note.md"
        )
        return {
            "action": "create_file",
            "parameters": {"path": path, "content": "Local group note.\n"},
            "reason": "Create a safe local note for the assigned task.",
            "expected_result": "The note is written under an allowed project path.",
        }
    action_name = sorted(action_schemas)[0] if action_schemas else "read_file"
    return {
        "action": action_name,
        "parameters": {},
        "reason": "Select the safest available action for the assigned task.",
        "expected_result": "A valid local action is selected.",
    }


def _executor_repair_user_message(
    *,
    agent: GroupAgentSpec,
    task: OrchestratorPlanTask,
    state: AgentState,
    previous_raw_output: str,
    validation_issues: list[dict[str, Any]],
    error_message: str,
) -> str:
    prompt_context = state.to_prompt_context()
    metadata = prompt_context.get("metadata") if isinstance(prompt_context, dict) else {}
    guidance = metadata.get("executor_prompt_hints") if isinstance(metadata, dict) else {}
    payload = {
        "agent_id": agent.agent_id,
        "task_id": task.task_id,
        "assigned_goal": task.goal,
        "error_message": error_message,
        "previous_raw_output": previous_raw_output,
        "validation_issues": validation_issues,
        "missing_required_parameters": _issue_values(validation_issues, "missing_required_parameter"),
        "unsafe_or_disallowed_paths": _issue_values(
            validation_issues,
            "unsafe_path",
            "path_outside_allowed_roots",
            "forbidden_path",
        ),
        "allowed_roots": guidance.get("safe_path_roots") if isinstance(guidance, dict) else [],
        "required_action_schemas": guidance.get("action_schemas") if isinstance(guidance, dict) else {},
        "repair_rules": [
            "Return one raw JSON object only.",
            "Use one action from allowed_actions.",
            "Include every required parameter for that action.",
            "For path parameters, use only relative project paths under allowed_roots.",
            "Do not use absolute Windows paths, drive letters, leading slashes, or '..'.",
            "Prefer safe_existing_read_paths for read_file.",
        ],
    }
    return "\n".join(
        [
            "EXECUTOR_REPAIR_REQUEST:",
            "The previous NextAction failed parse or validation. Return a corrected NextAction JSON object.",
            "Do not explain the fix. Do not use Markdown.",
            "REPAIR_CONTEXT_JSON:",
            json.dumps(payload, ensure_ascii=False, sort_keys=True, indent=2),
        ]
    )


def _issue_values(validation_issues: list[dict[str, Any]], *codes: str) -> list[str]:
    wanted = set(codes)
    values: list[str] = []
    for issue in validation_issues:
        if issue.get("code") not in wanted:
            continue
        message = str(issue.get("message") or "")
        if "'" in message:
            parts = message.split("'")
            if len(parts) >= 2 and parts[1]:
                values.append(parts[1])
                continue
        values.append(message)
    return sorted(dict.fromkeys(values))


def _run_executor_step(
    *,
    executor_provider: ExecutorActionProvider,
    scenario: OrchestratorExecutorScenario,
    agent: GroupAgentSpec,
    task: OrchestratorPlanTask,
    state: AgentState,
    role_template: RoleTemplate,
    registry: ScriptRegistry,
    bridge: ScriptExecutionBridge,
    group_step_index: int,
    execute_actions: bool,
    out_dir: Path,
    project_root: Path,
    repair_attempts: int,
) -> list[ExecutorActionAttempt]:
    agent_step_index = state.current_step
    attempts: list[ExecutorActionAttempt] = []
    previous_raw_output = ""
    previous_issues: list[dict[str, Any]] = []
    previous_error = ""

    for attempt_index in range(0, repair_attempts + 1):
        attempt_type: Literal["initial", "repair"] = "initial" if attempt_index == 0 else "repair"
        started = time.perf_counter()
        try:
            if attempt_type == "initial":
                provider_result = executor_provider.next_action(
                    agent=agent,
                    task=task,
                    state=state,
                    group_step_index=group_step_index,
                    agent_step_index=agent_step_index,
                    out_dir=out_dir,
                    project_root=project_root,
                )
            else:
                provider_result = _repair_executor_action(
                    executor_provider=executor_provider,
                    agent=agent,
                    task=task,
                    state=state,
                    group_step_index=group_step_index,
                    agent_step_index=agent_step_index,
                    out_dir=out_dir,
                    project_root=project_root,
                    previous_raw_output=previous_raw_output,
                    validation_issues=previous_issues,
                    error_message=previous_error,
                )
        except Exception as exc:
            attempts.append(
                ExecutorActionAttempt(
                    group_step_index=group_step_index,
                    agent_step_index=agent_step_index,
                    agent_id=agent.agent_id,
                    task_id=task.task_id,
                    attempt_index=attempt_index,
                    attempt_type=attempt_type,
                    raw_model_output="",
                    selection_latency_ms=_elapsed_ms(started),
                    error_type=exc.__class__.__name__,
                    error_message=str(exc) or exc.__class__.__name__,
                )
            )
            break

        attempt = _executor_attempt_from_result(
            provider_result=provider_result,
            attempt_index=attempt_index,
            attempt_type=attempt_type,
            agent=agent,
            task=task,
            role_template=role_template,
            registry=registry,
            bridge=bridge,
            group_step_index=group_step_index,
            agent_step_index=agent_step_index,
            execute_actions=execute_actions,
            scenario=scenario,
            out_dir=out_dir,
            project_root=project_root,
            latency_ms=_elapsed_ms(started),
        )
        attempts.append(attempt)
        if attempt.error_type is None:
            break
        if attempt.parse_success and attempt.validation_accepted is not False:
            break
        previous_raw_output = provider_result.raw_model_output
        previous_issues = list(attempt.validation_issues)
        previous_error = attempt.error_message or attempt.error_type or "Executor action validation failed."

    return attempts


def _executor_attempt_from_result(
    *,
    provider_result: ExecutorProviderResult,
    attempt_index: int,
    attempt_type: Literal["initial", "repair"],
    agent: GroupAgentSpec,
    task: OrchestratorPlanTask,
    role_template: RoleTemplate,
    registry: ScriptRegistry,
    bridge: ScriptExecutionBridge,
    group_step_index: int,
    agent_step_index: int,
    execute_actions: bool,
    scenario: OrchestratorExecutorScenario,
    out_dir: Path,
    project_root: Path,
    latency_ms: float,
) -> ExecutorActionAttempt:
    attempt = ExecutorActionAttempt(
        group_step_index=group_step_index,
        agent_step_index=agent_step_index,
        agent_id=agent.agent_id,
        task_id=task.task_id,
        attempt_index=attempt_index,
        attempt_type=attempt_type,
        raw_model_output=provider_result.raw_model_output,
        selection_latency_ms=latency_ms,
    )
    try:
        next_action = parse_next_action_text(provider_result.raw_model_output)
        attempt.parse_success = True
        attempt.action = next_action.action
        attempt.next_action = next_action.model_dump(mode="json")
    except NextActionContractError as exc:
        attempt.error_type = exc.__class__.__name__
        attempt.error_message = str(exc)
        return attempt

    validation = validate_next_action_against_registry(next_action, registry, role_template)
    attempt.validation_accepted = validation.accepted
    attempt.validation_issues = [issue.model_dump(mode="json") for issue in validation.issues]
    if not validation.accepted:
        attempt.error_type = "validation_failed"
        attempt.error_message = ", ".join(issue.code for issue in validation.issues)
        return attempt

    scenario_issue = _scenario_action_constraint_issue(
        next_action=next_action,
        scenario=scenario,
        out_dir=out_dir,
        project_root=project_root,
    )
    if scenario_issue is not None:
        attempt.validation_accepted = False
        attempt.validation_issues.append(scenario_issue)
        attempt.error_type = "validation_failed"
        attempt.error_message = str(scenario_issue["code"])
        return attempt

    if execute_actions:
        output = bridge.execute_next_action(
            next_action,
            run_id=agent.agent_id,
            agent_id=agent.agent_id,
            step_index=agent_step_index,
        )
        attempt.execution_attempted = True
        attempt.execution_success = output.success
        attempt.execution_result = output.model_dump(mode="json")
        if not output.success:
            attempt.error_type = output.raw_result.error_type or "execution_failed"
            attempt.error_message = output.raw_result.error_message or "Execution failed."
    else:
        attempt.execution_attempted = False
        attempt.execution_success = None
    return attempt


def _scenario_action_constraint_issue(
    *,
    next_action: NextAction,
    scenario: OrchestratorExecutorScenario,
    out_dir: Path,
    project_root: Path,
) -> dict[str, Any] | None:
    if scenario.metadata.get("write_path_policy") != "artifact_workspace_only":
        return None
    if next_action.action not in {"create_file", "append_file", "office_create_document_stub"}:
        return None
    path = next_action.parameters.get("path")
    if not isinstance(path, str) or not path.strip():
        return {
            "code": "missing_write_path",
            "field": "parameters.path",
            "message": "Write actions must include a non-empty path.",
            "severity": "error",
        }
    workspace_root = _safe_relative_workspace_root(project_root, out_dir)
    if not workspace_root.endswith("/"):
        workspace_root += "/"
    normalized = path.replace("\\", "/")
    if normalized.startswith(workspace_root):
        return None
    return {
        "code": "write_path_outside_artifact_workspace",
        "field": "parameters.path",
        "message": f"Write path '{path}' must be under '{workspace_root}'.",
        "severity": "error",
        "allowed_root": workspace_root,
    }


_ARTIFACT_WORKSPACE_FALLBACK = "experiments/multi_agent/orchestrator_executor/workspace"
_SAFE_ARTIFACT_ROOTS = ("docs/", "configs/", "experiments/", "tests/")


def _safe_relative_workspace_root(project_root: Path, out_dir: Path) -> str:
    try:
        value = (out_dir / "workspace").resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        value = _ARTIFACT_WORKSPACE_FALLBACK
    if not _is_safe_relative_artifact_path(value):
        value = _ARTIFACT_WORKSPACE_FALLBACK
    if not value.endswith("/"):
        value += "/"
    return value


def _repair_executor_action(
    *,
    executor_provider: ExecutorActionProvider,
    agent: GroupAgentSpec,
    task: OrchestratorPlanTask,
    state: AgentState,
    group_step_index: int,
    agent_step_index: int,
    out_dir: Path,
    project_root: Path,
    previous_raw_output: str,
    validation_issues: list[dict[str, Any]],
    error_message: str,
) -> ExecutorProviderResult:
    repair_method = getattr(executor_provider, "repair_action", None)
    if callable(repair_method):
        return repair_method(
            agent=agent,
            task=task,
            state=state,
            group_step_index=group_step_index,
            agent_step_index=agent_step_index,
            out_dir=out_dir,
            project_root=project_root,
            previous_raw_output=previous_raw_output,
            validation_issues=validation_issues,
            error_message=error_message,
        )
    return executor_provider.next_action(
        agent=agent,
        task=task,
        state=state,
        group_step_index=group_step_index,
        agent_step_index=agent_step_index,
        out_dir=out_dir,
        project_root=project_root,
    )


def _update_state_history(state: AgentState, attempt: ExecutorActionAttempt) -> None:
    if attempt.next_action:
        action = attempt.next_action["action"]
        params = dict(attempt.next_action.get("parameters") or {})
    else:
        action = "invalid_or_missing_action"
        params = {}
    if attempt.error_type is None:
        status = "success"
        summary = f"Group step {attempt.group_step_index} action accepted."
        error = None
    else:
        status = "failure"
        summary = f"Group step {attempt.group_step_index} failed: {attempt.error_type}."
        error = attempt.error_message
    state.history.append(
        ActionHistoryEntry(
            step=state.current_step,
            action=action,
            parameters=params,
            status=status,
            summary=summary,
            error=error,
        )
    )
    state.current_step = max(entry.step for entry in state.history) + 1


def _history_from_attempt(
    attempt: ExecutorActionAttempt,
    *,
    virtual_network_metadata: dict[str, Any] | None = None,
) -> GroupHistoryRecord:
    status: Literal["success", "failure", "skipped"]
    if attempt.error_type is None:
        status = "success"
    elif attempt.parse_success:
        status = "failure"
    else:
        status = "skipped"
    metadata: dict[str, Any] = {
        "validation_accepted": attempt.validation_accepted,
        "execution_attempted": attempt.execution_attempted,
        "execution_success": attempt.execution_success,
    }
    if virtual_network_metadata is not None:
        metadata["virtual_network"] = virtual_network_metadata
    return GroupHistoryRecord(
        group_step_index=attempt.group_step_index,
        agent_id=attempt.agent_id,
        task_id=attempt.task_id,
        action=attempt.action,
        status=status,
        summary=attempt.error_message or "Executor step completed.",
        metadata=metadata,
    )


def _activity_steps_from_attempts(attempts: list[ExecutorActionAttempt]) -> list[ActivityTrajectoryStep]:
    steps: list[ActivityTrajectoryStep] = []
    for attempt in attempts:
        if not attempt.next_action:
            continue
        steps.append(
            ActivityTrajectoryStep(
                step_index=attempt.agent_step_index,
                action=str(attempt.next_action["action"]),
                parameters=dict(attempt.next_action.get("parameters") or {}),
                success=attempt.error_type is None,
                status="success" if attempt.error_type is None else "failure",
                issue_codes=sorted(
                    {str(issue.get("code")) for issue in attempt.validation_issues if issue.get("code")}
                ),
                reason=str(attempt.next_action.get("reason") or ""),
                expected_result=str(attempt.next_action.get("expected_result") or ""),
                used_history=attempt.agent_step_index > 1,
            )
        )
    return steps


def _compute_quality_metrics(
    *,
    plan: OrchestratorPlan,
    assignments: dict[str, AgentAssignment],
    trajectories: list[ExecutorAgentTrajectory],
    scenario: OrchestratorExecutorScenario,
) -> OrchestratorExecutorQualityMetrics:
    attempts = [attempt for trajectory in trajectories for attempt in trajectory.attempts]
    initial_attempts = [attempt for attempt in attempts if attempt.attempt_type == "initial"]
    repair_attempts = [attempt for attempt in attempts if attempt.attempt_type == "repair"]
    final_attempts = _final_executor_attempts(attempts)
    parsed_attempts = [attempt for attempt in attempts if attempt.parse_success]
    final_validation_ok = [attempt for attempt in final_attempts if attempt.validation_accepted is True]
    final_validation_rate = _rate(len(final_validation_ok), len(final_attempts))
    execution_attempts = [attempt for attempt in attempts if attempt.execution_attempted]
    execution_successes = [attempt for attempt in execution_attempts if attempt.execution_success is True]
    safety_violations = sum(
        1
        for attempt in attempts
        for issue in attempt.validation_issues
        if issue.get("layer") == "safety_policy" or str(issue.get("code", "")).startswith("unsafe")
    )
    activity_metrics = [
        trajectory.activity_evaluation["metrics"]
        for trajectory in trajectories
        if trajectory.activity_evaluation
    ]
    role_fit = _mean([m["role_fit_score"] for m in activity_metrics])
    diversity = _mean([m["diversity_score"] for m in activity_metrics])
    repetition = _mean([m["repetition_score"] for m in activity_metrics])
    history = _mean([m["history_usage_score"] for m in activity_metrics])
    coordination = 1.0 if set(assignments) == {agent.agent_id for agent in scenario.agents} and plan.tasks else 0.0
    task_completion = _rate(sum(1 for trajectory in trajectories if trajectory.success), len(trajectories))
    latency_values = [attempt.selection_latency_ms for attempt in attempts if attempt.selection_latency_ms is not None]
    latency_mean = _mean(latency_values) if latency_values else None
    latency_component = 1.0 if latency_mean is None else max(0.0, min(1.0, 1.0 - (latency_mean / 5000.0)))
    pair_quality = (
        0.20 * final_validation_rate
        + 0.20 * _rate(
            len(execution_successes),
            len(execution_attempts) if execution_attempts else len(final_validation_ok),
        )
        + 0.15 * role_fit
        + 0.10 * diversity
        + 0.10 * history
        + 0.10 * coordination
        + 0.10 * task_completion
        + 0.05 * latency_component
    )
    if safety_violations:
        pair_quality -= min(0.20, 0.05 * safety_violations)
    return OrchestratorExecutorQualityMetrics(
        orchestrator_plan_valid=True,
        task_assignment_valid_rate=_rate(len(assignments), len(scenario.agents)),
        executor_initial_validation_rate=_rate(
            sum(1 for attempt in initial_attempts if attempt.validation_accepted is True),
            len(initial_attempts),
        ),
        executor_final_validation_rate=final_validation_rate,
        execution_success_rate=_rate(len(execution_successes), len(execution_attempts)) if execution_attempts else 0.0,
        role_fit_mean=role_fit,
        diversity_mean=diversity,
        repetition_mean=repetition,
        history_usage_mean=history,
        group_coordination_score=coordination,
        task_completion_proxy_score=task_completion,
        safety_violation_count=safety_violations,
        latency_mean_ms=latency_mean,
        pair_quality_score=round(max(0.0, min(1.0, pair_quality)), 6),
        metadata={
            "attempt_count": len(attempts),
            "parsed_attempt_count": len(parsed_attempts),
            "initial_attempt_count": len(initial_attempts),
            "repair_attempt_count": len(repair_attempts),
            "initial_validation_success_count": sum(
                1 for attempt in initial_attempts if attempt.validation_accepted is True
            ),
            "final_attempt_count": len(final_attempts),
            "final_validation_success_count": len(final_validation_ok),
            "execution_success_count": len(execution_successes),
            "prototype_scoring": True,
        },
    )


def _final_executor_attempts(attempts: list[ExecutorActionAttempt]) -> list[ExecutorActionAttempt]:
    by_step: dict[tuple[str, int, int], ExecutorActionAttempt] = {}
    for attempt in attempts:
        by_step[(attempt.agent_id, attempt.group_step_index, attempt.agent_step_index)] = attempt
    return list(by_step.values())


def _pair_evaluation(
    scenario: OrchestratorExecutorScenario,
    metrics: OrchestratorExecutorQualityMetrics,
) -> OrchestratorExecutorPairEvaluationResult:
    if metrics.pair_quality_score >= 0.7 and metrics.safety_violation_count == 0:
        verdict: Literal["prototype_pass", "prototype_with_failures", "failed"] = "prototype_pass"
    elif metrics.executor_final_validation_rate > 0:
        verdict = "prototype_with_failures"
    else:
        verdict = "failed"
    return OrchestratorExecutorPairEvaluationResult(
        orchestrator_model_id=scenario.orchestrator_model_id,
        executor_model_ids=sorted({agent.executor_model_id for agent in scenario.agents}),
        metrics=metrics,
        verdict=verdict,
        notes=[
            "Prototype scoring only; not a final scientific metric.",
            "Fake mode does not prove local multi-model runtime capacity.",
        ],
    )


def _failed_quality_metrics(
    *,
    reason: str,
    attempts: list[OrchestratorPlanAttempt],
) -> OrchestratorExecutorQualityMetrics:
    return OrchestratorExecutorQualityMetrics(
        orchestrator_plan_valid=False,
        task_assignment_valid_rate=0.0,
        executor_initial_validation_rate=0.0,
        executor_final_validation_rate=0.0,
        execution_success_rate=0.0,
        role_fit_mean=0.0,
        diversity_mean=0.0,
        repetition_mean=0.0,
        history_usage_mean=0.0,
        group_coordination_score=0.0,
        task_completion_proxy_score=0.0,
        safety_violation_count=0,
        latency_mean_ms=_mean([a.latency_ms for a in attempts if a.latency_ms is not None]) if attempts else None,
        pair_quality_score=0.0,
        metadata={
            "status": "failed",
            "failure_stage": "orchestrator_plan",
            "failure_reason": reason,
            "orchestrator_attempt_count": len(attempts),
            "orchestrator_repair_attempted": any(attempt.attempt_type == "repair" for attempt in attempts),
            "prototype_scoring": True,
        },
    )


def _per_agent_attempt_rows(result: OrchestratorExecutorRunResult) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trajectory in result.per_agent_results:
        for attempt in trajectory.attempts:
            rows.append(
                {
                    "agent_id": trajectory.agent_id,
                    "group_step_index": attempt.group_step_index,
                    "agent_step_index": attempt.agent_step_index,
                    "task_id": attempt.task_id,
                    "attempt_index": attempt.attempt_index,
                    "attempt_type": attempt.attempt_type,
                    "raw_output": attempt.raw_model_output,
                    "parse_success": attempt.parse_success,
                    "parsed_action": attempt.next_action,
                    "validation_accepted": attempt.validation_accepted,
                    "validation_issues": attempt.validation_issues,
                    "execution_attempted": attempt.execution_attempted,
                    "execution_success": attempt.execution_success,
                    "execution_result": attempt.execution_result,
                    "error_type": attempt.error_type,
                    "error_message": attempt.error_message,
                    "latency_ms": attempt.selection_latency_ms,
                }
            )
    return rows


def _write_artifacts(
    *,
    out_dir: Path,
    result: OrchestratorExecutorRunResult,
    config: OrchestratorExecutorRunConfig,
    scenario: OrchestratorExecutorScenario,
    orchestrator_model: OrchestratorModelConfig,
    executor_model: ExecutorModelConfig,
    provider_result: OrchestratorProviderResult,
    orchestrator_attempts: list[OrchestratorPlanAttempt],
    assignments: dict[str, AgentAssignment],
    started_at: str,
    wall_time_seconds: float,
) -> None:
    _write_json(out_dir / "manifest.json", _manifest(result, config, scenario, orchestrator_model, executor_model, started_at))
    if result.virtual_network is not None:
        _write_json(out_dir / "virtual_network_summary.json", result.virtual_network)
    _write_json(out_dir / "orchestrator_prompt.json", {"messages": provider_result.prompt_messages})
    _write_json(out_dir / "orchestrator_raw_output.json", {"raw_model_output": provider_result.raw_model_output, "metadata": provider_result.metadata})
    _write_jsonl(
        out_dir / "orchestrator_attempts.jsonl",
        [attempt.model_dump(mode="json") for attempt in orchestrator_attempts],
    )
    _write_json(out_dir / "orchestrator_plan.json", result.plan.model_dump(mode="json"))
    _write_json(out_dir / "orchestrator_validation.json", {"valid": True, "warnings": result.warnings})
    _write_json(out_dir / "agent_assignments.json", {key: value.model_dump(mode="json") for key, value in assignments.items()})
    _write_json(out_dir / "pair_quality_metrics.json", result.quality_metrics.model_dump(mode="json"))
    _write_json(out_dir / "pair_evaluation.json", result.pair_evaluation.model_dump(mode="json"))
    _write_json(out_dir / "resource_summary.json", _resource_summary(started_at, wall_time_seconds))
    _write_jsonl(out_dir / "group_steps.jsonl", [item.model_dump(mode="json") for item in result.group_history])
    _write_jsonl(out_dir / "group_history.jsonl", [item.model_dump(mode="json") for item in result.group_history])
    _write_jsonl(
        out_dir / "per_agent_actions.jsonl",
        [
            {"agent_id": trajectory.agent_id, **attempt.model_dump(mode="json")}
            for trajectory in result.per_agent_results
            for attempt in trajectory.attempts
        ],
    )
    _write_jsonl(out_dir / "per_agent_attempts.jsonl", _per_agent_attempt_rows(result))
    _write_jsonl(
        out_dir / "per_agent_validation_results.jsonl",
        [
            {
                "agent_id": trajectory.agent_id,
                "group_step_index": attempt.group_step_index,
                "agent_step_index": attempt.agent_step_index,
                "attempt_index": attempt.attempt_index,
                "attempt_type": attempt.attempt_type,
                "validation_accepted": attempt.validation_accepted,
                "validation_issues": attempt.validation_issues,
            }
            for trajectory in result.per_agent_results
            for attempt in trajectory.attempts
        ],
    )
    _write_jsonl(
        out_dir / "per_agent_execution_results.jsonl",
        [
            {
                "agent_id": trajectory.agent_id,
                "group_step_index": attempt.group_step_index,
                "agent_step_index": attempt.agent_step_index,
                "execution_attempted": attempt.execution_attempted,
                "execution_success": attempt.execution_success,
                "execution_result": attempt.execution_result,
            }
            for trajectory in result.per_agent_results
            for attempt in trajectory.attempts
        ],
    )
    _write_jsonl(out_dir / "errors.jsonl", result.errors)
    (out_dir / "replay_commands.ps1").write_text(_replay_command(config) + "\n", encoding="utf-8")
    (out_dir / "README.md").write_text(_artifact_readme(result), encoding="utf-8")


def _write_orchestrator_failure_artifacts(
    *,
    out_dir: Path,
    result: OrchestratorExecutorRunResult,
    config: OrchestratorExecutorRunConfig,
    scenario: OrchestratorExecutorScenario,
    orchestrator_model: OrchestratorModelConfig,
    executor_model: ExecutorModelConfig,
    attempts: list[OrchestratorPlanAttempt],
    errors: list[dict[str, Any]],
    started_at: str,
    wall_time_seconds: float,
) -> None:
    latest = attempts[-1] if attempts else None
    _write_json(out_dir / "manifest.json", _manifest(result, config, scenario, orchestrator_model, executor_model, started_at))
    if result.virtual_network is not None:
        _write_json(out_dir / "virtual_network_summary.json", result.virtual_network)
    _write_json(out_dir / "orchestrator_prompt.json", {"messages": latest.prompt if latest else [], "attempt_count": len(attempts)})
    _write_json(
        out_dir / "orchestrator_raw_output.json",
        {
            "raw_model_output": latest.raw_output if latest else "",
            "metadata": latest.metadata if latest else {},
        },
    )
    _write_jsonl(out_dir / "orchestrator_attempts.jsonl", [attempt.model_dump(mode="json") for attempt in attempts])
    _write_json(
        out_dir / "orchestrator_parse_error.json",
        {
            "error": _final_orchestrator_error(attempts),
            "parse_success": latest.parse_success if latest else False,
            "validation_success": latest.validation_success if latest else False,
            "attempt_index": latest.attempt_index if latest else None,
            "attempt_type": latest.attempt_type if latest else None,
        },
    )
    _write_json(
        out_dir / "orchestrator_validation.json",
        {
            "valid": False,
            "final_error": _final_orchestrator_error(attempts),
            "attempt_count": len(attempts),
        },
    )
    _write_json(out_dir / "agent_assignments.json", {})
    _write_json(out_dir / "pair_quality_metrics.json", result.quality_metrics.model_dump(mode="json"))
    _write_json(out_dir / "pair_evaluation.json", result.pair_evaluation.model_dump(mode="json"))
    _write_json(out_dir / "resource_summary.json", _resource_summary(started_at, wall_time_seconds))
    _write_jsonl(out_dir / "group_steps.jsonl", [])
    _write_jsonl(out_dir / "group_history.jsonl", [])
    _write_jsonl(out_dir / "per_agent_actions.jsonl", [])
    _write_jsonl(out_dir / "per_agent_attempts.jsonl", [])
    _write_jsonl(out_dir / "per_agent_validation_results.jsonl", [])
    _write_jsonl(out_dir / "per_agent_execution_results.jsonl", [])
    _write_jsonl(out_dir / "errors.jsonl", errors)
    (out_dir / "replay_commands.ps1").write_text(_replay_command(config) + "\n", encoding="utf-8")
    (out_dir / "README.md").write_text(_artifact_readme(result), encoding="utf-8")


def _manifest(
    result: OrchestratorExecutorRunResult,
    config: OrchestratorExecutorRunConfig,
    scenario: OrchestratorExecutorScenario,
    orchestrator_model: OrchestratorModelConfig,
    executor_model: ExecutorModelConfig,
    started_at: str,
) -> dict[str, Any]:
    return {
        "runner_id": "orchestrator_executor_pipeline_v1",
        "run_id": result.run_id,
        "scenario_id": result.scenario_id,
        "scenario_path": config.scenario_path,
        "out_dir": config.out_dir,
        "workspace_path": str((config.project_path(config.out_dir) / "workspace").resolve()),
        "workspace_relative_path": _safe_relative_workspace_root(config.project_root, config.project_path(config.out_dir)),
        "workspace_policy": scenario.metadata.get("write_path_policy"),
        "fixture_strategy": "shared_read_only_project_root",
        "fixture_paths": list(scenario.metadata.get("fixture_paths") or []),
        "virtual_network": result.virtual_network,
        "mode": config.mode,
        "status": result.status,
        "success": result.success,
        "orchestrator_model_id": orchestrator_model.model_id,
        "executor_model_id": executor_model.model_id,
        "orchestrator_base_url": orchestrator_model.base_url,
        "executor_base_url": executor_model.base_url,
        "orchestrator_model_name": orchestrator_model.model_name,
        "executor_model_name": executor_model.model_name,
        "orchestrator_max_tokens": orchestrator_model.max_tokens,
        "orchestrator_temperature": orchestrator_model.temperature,
        "orchestrator_repair_attempts": config.orchestrator_repair_attempts,
        "executor_repair_attempts": config.repair_attempts,
        "orchestrator_model": orchestrator_model.model_dump(mode="json"),
        "executor_model": executor_model.model_dump(mode="json"),
        "runtime_overrides": {
            "orchestrator_base_url": config.orchestrator_base_url,
            "executor_base_url": config.executor_base_url,
            "orchestrator_model_name": config.orchestrator_model_name,
            "executor_model_name": config.executor_model_name,
            "orchestrator_max_tokens": config.orchestrator_max_tokens,
            "orchestrator_temperature": config.orchestrator_temperature,
        },
        "max_group_steps": scenario.max_group_steps,
        "max_steps_per_agent": scenario.max_steps_per_agent,
        "execute_actions": scenario.execute_actions,
        "started_at": started_at,
        "completed_at": _utc_now(),
        "limitations": [
            "MVP runner is sequential and not a production scheduler.",
            "Fake mode does not call llama-server.",
            "Local mode requires already available compatible runtime endpoint(s).",
        ],
    }


def _resource_summary(started_at: str, wall_time_seconds: float) -> dict[str, Any]:
    return {
        "started_at": started_at,
        "completed_at": _utc_now(),
        "wall_time_ms": round(wall_time_seconds * 1000.0, 3),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
    }


def _replay_command(config: OrchestratorExecutorRunConfig) -> str:
    action_flag = "--execute-actions" if config.execute_actions is not False else "--no-execute-actions"
    optional_flags = ""
    if config.orchestrator_base_url:
        optional_flags += f"--orchestrator-base-url {config.orchestrator_base_url} "
    if config.executor_base_url:
        optional_flags += f"--executor-base-url {config.executor_base_url} "
    if config.orchestrator_model_name:
        optional_flags += f"--orchestrator-model-name {config.orchestrator_model_name} "
    if config.executor_model_name:
        optional_flags += f"--executor-model-name {config.executor_model_name} "
    if config.orchestrator_max_tokens is not None:
        optional_flags += f"--orchestrator-max-tokens {config.orchestrator_max_tokens} "
    if config.orchestrator_temperature is not None:
        optional_flags += f"--orchestrator-temperature {config.orchestrator_temperature} "
    if config.orchestrator_repair_attempts:
        optional_flags += f"--orchestrator-repair-attempts {config.orchestrator_repair_attempts} "
    return (
        "python scripts\\run_orchestrator_executor_group.py "
        f"--mode {config.mode} "
        f"--models-config {config.models_config_path} "
        f"--scenario {config.scenario_path} "
        f"--out-dir {config.out_dir} "
        f"--run-id {config.run_id} "
        f"--orchestrator-model-id {config.orchestrator_model_id or 'second_model'} "
        f"--executor-model-id {config.executor_model_id or 'first_model'} "
        f"{optional_flags}"
        f"--max-group-steps {config.max_group_steps or 2} "
        f"--max-steps-per-agent {config.max_steps_per_agent or 2} "
        f"--repair-attempts {config.repair_attempts} "
        f"{action_flag} "
        "--force"
    )


def _artifact_readme(result: OrchestratorExecutorRunResult) -> str:
    return f"""# Orchestrator/Executor Group Run

Run id: `{result.run_id}`

Scenario: `{result.scenario_id}`

Status: `{result.status}`

Pair quality score: `{result.quality_metrics.pair_quality_score}`

This artifact was produced by the sequential MVP runner. It is useful as a structural group-agent prototype, not as a production scheduler or measured capacity result.
"""


def _final_orchestrator_error(attempts: list[OrchestratorPlanAttempt]) -> str:
    if not attempts:
        return "Orchestrator plan was not attempted."
    latest = attempts[-1]
    return latest.parse_error or "; ".join(latest.validation_errors) or "Orchestrator plan failed."


def _runtime_warnings(
    mode: GroupRunMode,
    orchestrator_model: OrchestratorModelConfig,
    executor_model: ExecutorModelConfig,
) -> list[str]:
    warnings = ["orchestrator_executor_mvp_is_sequential_not_production_scheduler"]
    if mode == "fake":
        warnings.append("fake_mode_does_not_call_llama_server")
    if mode == "local" and orchestrator_model.base_url == executor_model.base_url:
        warnings.append("local_mode_uses_same_base_url_for_orchestrator_and_executor; manual runtime coordination may be required")
    return warnings


def _safe_relative_artifact_path(project_root: Path, path: Path) -> str:
    try:
        value = path.resolve().relative_to(project_root.resolve()).as_posix()
    except ValueError:
        return f"{_ARTIFACT_WORKSPACE_FALLBACK}/office_agent_summary.md"
    if not _is_safe_relative_artifact_path(value):
        return f"{_ARTIFACT_WORKSPACE_FALLBACK}/office_agent_summary.md"
    return value


def _is_safe_relative_artifact_path(value: str) -> bool:
    normalized = value.replace("\\", "/")
    if not normalized or normalized.startswith("/") or ".." in normalized.split("/"):
        return False
    if re.match(r"^[a-zA-Z]:", normalized):
        return False
    return normalized.startswith(_SAFE_ARTIFACT_ROOTS)


def _prepare_output_dir(out_dir: Path, *, force: bool) -> None:
    if out_dir.exists() and not force:
        raise FileExistsError(f"Output directory already exists: {out_dir}")
    out_dir.mkdir(parents=True, exist_ok=True)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, separators=(",", ":")) + "\n" for row in rows),
        encoding="utf-8",
    )


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _mean(values: list[float | int]) -> float:
    if not values:
        return 0.0
    return round(sum(float(value) for value in values) / len(values), 6)
