from __future__ import annotations

import json
import platform
import shutil
import sys
import time
from datetime import datetime, timezone
from pathlib import Path, PurePosixPath
from typing import Any, Literal, Protocol

import httpx
from pydantic import BaseModel, Field, field_validator, model_validator

from .action_contract import (
    NextActionContractError,
    parse_next_action_text,
)
from .activity_evaluator import ActivityTrajectoryEvaluator, ActivityTrajectoryStep
from .activity_profile import NormalActivityProfile, load_activity_profile
from .autonomous_stop_criteria import (
    AutonomousSessionStepSummary,
    AutonomousSessionSummary,
    AutonomousStopCriteriaConfig,
    AutonomousStopCriteriaEvaluator,
)
from .evaluation_scenarios import EvaluationScenario, load_evaluation_scenario
from .execution_history import (
    ExecutionErrorRecord,
    ExecutionHistoryConfig,
    ExecutionHistoryLogger,
    ExecutionHistoryRecord,
    stable_record_id,
    utc_now_iso,
)
from .llm_client import LocalLLMClient
from .model_behavior_evaluation import (
    ModelBehaviorEvaluationResult,
    ModelBehaviorModelSpec,
    ModelBehaviorResourceMetrics,
    ModelBehaviorSelectedAction,
    ModelBehaviorValidationMetrics,
    derive_model_behavior_verdict,
)
from .role_template import RoleTemplate, load_role_template, role_template_to_agent_state_defaults
from .schemas import NextAction
from .script_execution_bridge import (
    ScriptExecutionBridge,
    ScriptExecutionBridgeConfig,
    ScriptExecutionBridgeOutput,
)
from .script_registry import (
    ScriptRegistry,
    ScriptValidationIssue,
    ScriptValidationResult,
    load_script_registry,
    validate_next_action_against_registry,
)
from .state import ActionHistoryEntry, ActionSpec, AgentState, load_agent_state

ExperimentRunnerMode = Literal["fake", "local"]
ExperimentRunStatus = Literal[
    "completed",
    "stopped",
    "failed",
]
WRITE_ACTIONS = {"append_file", "create_file", "office_create_document_stub"}


class ActionProviderResult(BaseModel):
    raw_model_output: str
    metadata: dict[str, Any] = Field(default_factory=dict)


class ActionProvider(Protocol):
    def next_action_text(
        self,
        *,
        agent_state: AgentState,
        prompt_messages: list[dict[str, str]],
        step_index: int,
    ) -> ActionProviderResult:
        ...


class ScriptedActionProvider:
    """Offline action provider for deterministic fake-mode runs."""

    def __init__(self, actions: list[str | dict[str, Any] | NextAction], repeat_last: bool = True) -> None:
        if not actions:
            raise ValueError("ScriptedActionProvider requires at least one action.")
        self.actions = list(actions)
        self.repeat_last = repeat_last
        self.index = 0

    @staticmethod
    def _to_raw(action: str | dict[str, Any] | NextAction) -> str:
        if isinstance(action, str):
            return action
        if isinstance(action, NextAction):
            return action.model_dump_json()
        if isinstance(action, dict):
            return json.dumps(action, ensure_ascii=False, separators=(",", ":"))
        raise TypeError("Scripted action must be raw JSON text, dict, or NextAction.")

    def next_action_text(
        self,
        *,
        agent_state: AgentState,
        prompt_messages: list[dict[str, str]],
        step_index: int,
    ) -> ActionProviderResult:
        if self.index < len(self.actions):
            item = self.actions[self.index]
            self.index += 1
        elif self.repeat_last:
            item = self.actions[-1]
        else:
            raise RuntimeError("scripted_actions_exhausted")

        return ActionProviderResult(
            raw_model_output=self._to_raw(item),
            metadata={
                "provider": "scripted",
                "scripted_index": min(self.index, len(self.actions)),
                "repeat_last": self.repeat_last,
                "agent_id": agent_state.agent_id,
                "prompt_message_count": len(prompt_messages),
                "step_index": step_index,
            },
        )


FakeActionProvider = ScriptedActionProvider


class LocalModelActionProvider:
    """Future local-mode provider. Tests must not exercise this provider."""

    def __init__(
        self,
        *,
        base_url: str,
        model_name: str,
        timeout_seconds: float = 120.0,
        temperature: float = 0.0,
        max_tokens: int = 512,
    ) -> None:
        self.client = LocalLLMClient(
            base_url=base_url,
            model_name=model_name,
            timeout_seconds=timeout_seconds,
            temperature=temperature,
            max_tokens=max_tokens,
        )

    def next_action_text(
        self,
        *,
        agent_state: AgentState,
        prompt_messages: list[dict[str, str]],
        step_index: int,
    ) -> ActionProviderResult:
        payload = {
            "model": self.client.model_name,
            "messages": prompt_messages,
            "temperature": self.client.temperature,
            "max_tokens": self.client.max_tokens,
        }
        with httpx.Client(timeout=self.client.timeout_seconds, trust_env=False) as client:
            response = client.post(self.client.endpoint, json=payload)
            response.raise_for_status()
            response_json = response.json()
        return ActionProviderResult(
            raw_model_output=LocalLLMClient.extract_assistant_content(response_json),
            metadata={
                "provider": "local_model",
                "base_url": self.client.base_url,
                "model_name": self.client.model_name,
                "step_index": step_index,
            },
        )


class ExperimentScenarioRunnerConfig(BaseModel):
    project_root: Path = Path(".")
    mode: ExperimentRunnerMode = "fake"
    scenario_path: str = "configs/evaluation_scenarios/office_worker_basic_session.json"
    registry_path: str = "configs/script_registry.example.json"
    out_dir: str = "experiments/scenario_runs/default"
    run_id: str = "scenario_run"
    model_id: str = "fake_model"
    model_name: str = "fake-scripted-provider"
    base_url: str | None = None
    models_config_path: str | None = None
    model_registry_spec: dict[str, Any] | None = None
    model_preflight_result: dict[str, Any] | None = None
    model_cli_overrides: dict[str, Any] = Field(default_factory=dict)
    timeout_seconds: float = 120.0
    temperature: float = 0.0
    max_tokens: int = 512
    max_steps: int | None = None
    execute_actions: bool = True
    force: bool = False
    write_history_logs: bool = True
    reset_initial_history: bool = True
    stop_on_parse_error: bool = True
    enforce_write_workspace: bool = True
    write_workspace_path: str | None = None
    repair_attempts_per_step: int = 0
    repair_on_parse_failure: bool = True
    repair_on_validation_failure: bool = True
    repair_prompt_include_allowed_actions: bool = True
    repair_prompt_include_role_constraints: bool = True
    repair_prompt_include_previous_raw_output: bool = True
    scripted_actions: list[str | dict[str, Any] | NextAction] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("project_root")
    @classmethod
    def resolve_project_root(cls, value: Path) -> Path:
        return value.resolve()

    @field_validator("run_id", "model_id", "model_name")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("run_id/model_id/model_name must be non-empty.")
        return value

    @field_validator("max_steps")
    @classmethod
    def validate_max_steps(cls, value: int | None) -> int | None:
        if value is not None and value < 1:
            raise ValueError("max_steps must be >= 1 when provided.")
        return value

    @field_validator("timeout_seconds")
    @classmethod
    def validate_timeout_seconds(cls, value: float) -> float:
        if value <= 0:
            raise ValueError("timeout_seconds must be > 0.")
        return value

    @field_validator("temperature")
    @classmethod
    def validate_temperature(cls, value: float) -> float:
        if value < 0:
            raise ValueError("temperature must be >= 0.")
        return value

    @field_validator("max_tokens")
    @classmethod
    def validate_max_tokens(cls, value: int) -> int:
        if value <= 0:
            raise ValueError("max_tokens must be > 0.")
        return value

    @field_validator("repair_attempts_per_step")
    @classmethod
    def validate_repair_attempts_per_step(cls, value: int) -> int:
        if value < 0:
            raise ValueError("repair_attempts_per_step must be >= 0.")
        return value

    @model_validator(mode="after")
    def validate_local_mode(self) -> ExperimentScenarioRunnerConfig:
        if self.mode == "local":
            if not self.base_url or not self.base_url.strip():
                raise ValueError("mode=local requires base_url.")
            if self.model_name == "fake-scripted-provider":
                raise ValueError("mode=local requires an explicit model_name.")
        return self

    def project_path(self, relative_or_absolute: str | Path) -> Path:
        path = Path(relative_or_absolute)
        if path.is_absolute():
            return path
        return self.project_root / path


class ExperimentStepRecord(BaseModel):
    step_index: int
    timestamp: str
    agent_id: str
    prompt_messages: list[dict[str, str]] = Field(default_factory=list)
    prompt_summary: dict[str, Any] = Field(default_factory=dict)
    raw_model_output: str | None = None
    parse_success: bool = False
    next_action: dict[str, Any] | None = None
    validation_result: dict[str, Any] | None = None
    registry_accepted: bool | None = None
    role_compliant: bool | None = None
    execution_attempted: bool = False
    execution_success: bool | None = None
    raw_execution_result: dict[str, Any] | None = None
    normalized_execution_result: dict[str, Any] | None = None
    selection_latency_ms: float | None = None
    execution_latency_ms: float | None = None
    total_step_latency_ms: float | None = None
    error_type: str | None = None
    error_message: str | None = None
    stop_reason: str | None = None
    initial_attempt_count: int = 1
    repair_attempt_count: int = 0
    final_attempt_index: int = 0
    repaired: bool = False
    initial_failure_preserved: bool = False
    attempts: list[dict[str, Any]] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)


class ExperimentAttemptRecord(BaseModel):
    step_index: int
    attempt_index: int
    attempt_type: Literal["initial", "repair"]
    prompt_kind: Literal["initial", "repair"]
    timestamp: str
    prompt_messages: list[dict[str, str]] = Field(default_factory=list)
    raw_model_output: str | None = None
    parse_success: bool = False
    parsed_action: dict[str, Any] | None = None
    validation_accepted: bool | None = None
    validation_result: dict[str, Any] | None = None
    validation_issues: list[dict[str, Any]] = Field(default_factory=list)
    role_compliant: bool | None = None
    selection_latency_ms: float | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def issue_codes(self) -> list[str]:
        codes: list[str] = []
        seen: set[str] = set()
        for issue in self.validation_issues:
            code = issue.get("code")
            if not code:
                continue
            code_text = str(code)
            if code_text in seen:
                continue
            seen.add(code_text)
            codes.append(code_text)
        return codes


class ExperimentRunResult(BaseModel):
    run_id: str
    scenario_id: str
    status: ExperimentRunStatus
    success: bool
    out_dir: str
    steps: list[ExperimentStepRecord]
    stopped_reason: str | None = None
    activity_evaluation_path: str | None = None
    model_behavior_result_path: str | None = None
    resource_summary_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    def selected_action_names(self) -> list[str]:
        names: list[str] = []
        for step in self.steps:
            if step.next_action and isinstance(step.next_action.get("action"), str):
                names.append(step.next_action["action"])
        return names


def default_fake_actions() -> list[dict[str, Any]]:
    return [
        {
            "action": "read_file",
            "parameters": {"path": "docs/ai/model_registry.md"},
            "reason": "Inspect existing model registry documentation.",
            "expected_result": "The registry document is available for the next step.",
        }
    ]


def load_scripted_actions(path_or_json: str | None) -> list[str | dict[str, Any]]:
    if not path_or_json:
        return default_fake_actions()
    candidate = Path(path_or_json)
    if candidate.exists():
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    else:
        payload = json.loads(path_or_json)
    if isinstance(payload, list):
        return payload
    if isinstance(payload, dict) and isinstance(payload.get("actions"), list):
        return payload["actions"]
    raise ValueError("--scripted-actions must be a JSON list or an object with an 'actions' list.")


class ExperimentScenarioRunner:
    def __init__(
        self,
        config: ExperimentScenarioRunnerConfig,
        provider: ActionProvider | None = None,
    ) -> None:
        self.config = config
        self.provider = provider

    def run(self) -> ExperimentRunResult:
        start_perf = time.perf_counter()
        started_at = utc_now_iso()
        out_dir = self.config.project_path(self.config.out_dir)
        self._prepare_out_dir(out_dir)

        scenario = load_evaluation_scenario(self.config.project_path(self.config.scenario_path))
        if scenario.is_multi_agent():
            raise ValueError(
                "ExperimentScenarioRunner v1 supports one agent per run. "
                "Use a single_agent scenario or split multi-agent scenarios into separate runs."
            )
        agent_spec = scenario.agents[0]
        role_template = load_role_template(self.config.project_path(agent_spec.role_template_path))
        activity_profile = load_activity_profile(self.config.project_path(agent_spec.activity_profile_path))
        registry = load_script_registry(self.config.project_path(self.config.registry_path))
        state = self._load_initial_state(agent_spec, role_template, registry)
        max_steps = self.config.max_steps or scenario.stop_policy.max_steps
        write_workspace_path = self._prepare_write_workspace(out_dir)

        history_logger = ExecutionHistoryLogger(
            config=ExecutionHistoryConfig(log_root=str(out_dir), create_parent_dirs=True)
        )
        provider = self.provider or self._make_provider()
        bridge = ScriptExecutionBridge(
            ScriptExecutionBridgeConfig(
                project_root=self.config.project_root,
                registry_path=self.config.registry_path,
                validate_with_registry=True,
                normalize_result=True,
                write_history=False,
            ),
            registry=registry,
        )

        stop_evaluator = self._make_stop_evaluator(scenario, activity_profile)
        session_summary = AutonomousSessionSummary(session_id=self.config.run_id, agent_id=state.agent_id)

        resource_start = _resource_snapshot()
        steps: list[ExperimentStepRecord] = []
        selected_actions: list[ModelBehaviorSelectedAction] = []
        stopped_reason: str | None = None

        writers = _ArtifactWriters(out_dir)
        writers.open()
        try:
            for _ in range(max_steps):
                step_index = state.current_step
                step, state, model_action, session_step = self._run_step(
                    state=state,
                    step_index=step_index,
                    provider=provider,
                    registry=registry,
                    role_template=role_template,
                    bridge=bridge,
                    history_logger=history_logger,
                    write_workspace_path=write_workspace_path,
                )
                steps.append(step)
                if model_action is not None:
                    selected_actions.append(model_action)
                if session_step is not None:
                    session_summary.steps.append(session_step)

                if step.error_type == "provider_error":
                    stopped_reason = step.error_message
                    step.stop_reason = stopped_reason
                elif step.error_type in {"validation_failed_after_repair", "parse_failed_after_repair"}:
                    stopped_reason = step.error_type
                    step.stop_reason = stopped_reason
                elif step.error_type and not step.parse_success and self.config.stop_on_parse_error:
                    stopped_reason = "parse_failed"
                    step.stop_reason = stopped_reason

                if stopped_reason is None:
                    stop_decision = stop_evaluator.evaluate(session_summary)
                    if stop_decision.should_stop:
                        stopped_reason = stop_decision.reason
                        step.stop_reason = stopped_reason

                writers.write_step(step)

                if stopped_reason is not None:
                    break

            if stopped_reason is None and len(steps) >= max_steps:
                stopped_reason = "Reached max_steps limit."
                if steps:
                    steps[-1].stop_reason = stopped_reason
                    writers.rewrite_steps(steps)
        finally:
            writers.close()

        _ensure_artifact_files(out_dir, ["history.jsonl", "errors.jsonl"])

        activity_result = self._evaluate_activity(selected_actions, activity_profile)
        model_behavior_result = self._build_model_behavior_result(
            scenario=scenario,
            steps=steps,
            selected_actions=selected_actions,
            activity_result=activity_result,
            started_at=started_at,
            completed_at=utc_now_iso(),
            wall_time_seconds=time.perf_counter() - start_perf,
        )
        resource_summary = self._build_resource_summary(
            started_at=started_at,
            resource_start=resource_start,
            steps=steps,
            wall_time_seconds=time.perf_counter() - start_perf,
        )

        self._write_json(out_dir / "activity_evaluation.json", activity_result.model_dump(mode="json"))
        self._write_json(out_dir / "model_behavior_result.json", model_behavior_result.model_dump(mode="json"))
        self._write_json(out_dir / "resource_summary.json", resource_summary)
        self._write_manifest(out_dir, scenario, agent_spec, started_at, steps, stopped_reason, write_workspace_path)
        self._write_replay_commands(out_dir)
        self._write_readme(out_dir, scenario, stopped_reason)

        status: ExperimentRunStatus = "completed" if stopped_reason == "Reached max_steps limit." else "stopped"
        success = not any(step.error_type for step in steps)
        if not steps:
            status = "failed"
            success = False
        elif any(step.error_type == "provider_error" for step in steps):
            status = "failed"
            success = False

        return ExperimentRunResult(
            run_id=self.config.run_id,
            scenario_id=scenario.scenario_id,
            status=status,
            success=success,
            out_dir=str(out_dir),
            steps=steps,
            stopped_reason=stopped_reason,
            activity_evaluation_path=str(out_dir / "activity_evaluation.json"),
            model_behavior_result_path=str(out_dir / "model_behavior_result.json"),
            resource_summary_path=str(out_dir / "resource_summary.json"),
            metadata={
                "mode": self.config.mode,
                "execute_actions": self.config.execute_actions,
                "agent_id": agent_spec.agent_id,
            },
        )

    def _make_provider(self) -> ActionProvider:
        if self.config.mode == "fake":
            actions = self.config.scripted_actions or default_fake_actions()
            return ScriptedActionProvider(actions)
        assert self.config.base_url is not None
        return LocalModelActionProvider(
            base_url=self.config.base_url,
            model_name=self.config.model_name,
            timeout_seconds=self.config.timeout_seconds,
            temperature=self.config.temperature,
            max_tokens=self.config.max_tokens,
        )

    def _prepare_out_dir(self, out_dir: Path) -> None:
        if out_dir.exists() and not self.config.force:
            raise FileExistsError(f"Output directory already exists: {out_dir}. Use --force to overwrite.")
        if out_dir.exists() and self.config.force:
            _clear_artifact_dir_preserving_runtime_logs(out_dir)
        out_dir.mkdir(parents=True, exist_ok=True)

    def _load_initial_state(
        self,
        agent_spec: Any,
        role_template: RoleTemplate,
        registry: ScriptRegistry,
    ) -> AgentState:
        state_path = agent_spec.initial_state_path or "configs/agent_state.example.json"
        state = load_agent_state(self.config.project_path(state_path))
        payload = state.model_dump()
        payload.update(role_template_to_agent_state_defaults(role_template))
        payload["agent_id"] = agent_spec.agent_id
        payload["available_actions"] = [
            _action_spec_from_registry(action_name, registry).model_dump()
            for action_name in agent_spec.available_actions
            if registry.has_script(action_name)
        ]
        if self.config.reset_initial_history:
            payload["history"] = []
            payload["current_step"] = 1
        return AgentState.model_validate(payload)

    def _prepare_write_workspace(self, out_dir: Path) -> str | None:
        if not self.config.enforce_write_workspace:
            return None
        if self.config.write_workspace_path:
            workspace_relative = _normalize_relative_path(self.config.write_workspace_path)
        else:
            try:
                workspace_relative = _normalize_relative_path(str(out_dir.relative_to(self.config.project_root) / "workspace"))
            except ValueError:
                workspace_relative = f"experiments/scenario_runs/{_safe_path_token(self.config.run_id)}/workspace"
        workspace_abs = (self.config.project_root / workspace_relative).resolve()
        workspace_abs.mkdir(parents=True, exist_ok=True)
        return workspace_relative.rstrip("/") + "/"

    def _run_step(
        self,
        *,
        state: AgentState,
        step_index: int,
        provider: ActionProvider,
        registry: ScriptRegistry,
        role_template: RoleTemplate,
        bridge: ScriptExecutionBridge,
        history_logger: ExecutionHistoryLogger,
        write_workspace_path: str | None,
    ) -> tuple[ExperimentStepRecord, AgentState, ModelBehaviorSelectedAction | None, AutonomousSessionStepSummary | None]:
        step_start = time.perf_counter()
        prompt_messages = LocalLLMClient().prompt_builder.build_messages(state)
        prompt_summary = {
            "message_count": len(prompt_messages),
            "roles": [m.get("role") for m in prompt_messages],
            "history_count": len(state.history),
            "available_action_count": len(state.available_actions),
        }
        step = ExperimentStepRecord(
            step_index=step_index,
            timestamp=utc_now_iso(),
            agent_id=state.agent_id,
            prompt_messages=prompt_messages,
            prompt_summary=prompt_summary,
        )
        attempts: list[ExperimentAttemptRecord] = []
        initial_attempt = self._run_action_attempt(
            state=state,
            step_index=step_index,
            attempt_index=0,
            attempt_type="initial",
            prompt_messages=prompt_messages,
            provider=provider,
            registry=registry,
            role_template=role_template,
            write_workspace_path=write_workspace_path,
        )
        attempts.append(initial_attempt)

        if self._should_attempt_repair(initial_attempt):
            self._log_attempt_error(history_logger, initial_attempt, state.agent_id)
            for repair_offset in range(self.config.repair_attempts_per_step):
                repair_prompt = self._build_repair_prompt_messages(
                    state=state,
                    registry=registry,
                    role_template=role_template,
                    previous_attempt=attempts[-1],
                )
                repair_attempt = self._run_action_attempt(
                    state=state,
                    step_index=step_index,
                    attempt_index=repair_offset + 1,
                    attempt_type="repair",
                    prompt_messages=repair_prompt,
                    provider=provider,
                    registry=registry,
                    role_template=role_template,
                    write_workspace_path=write_workspace_path,
                )
                attempts.append(repair_attempt)
                if repair_attempt.error_type is not None:
                    self._log_attempt_error(history_logger, repair_attempt, state.agent_id)
                if repair_attempt.parse_success and repair_attempt.validation_accepted is True:
                    break

        final_attempt = _final_attempt(attempts)
        step.attempts = [attempt.model_dump(mode="json") for attempt in attempts]
        step.initial_attempt_count = 1
        step.repair_attempt_count = sum(1 for attempt in attempts if attempt.attempt_type == "repair")
        step.final_attempt_index = final_attempt.attempt_index
        step.repaired = final_attempt.attempt_type == "repair" and final_attempt.validation_accepted is True
        step.initial_failure_preserved = (
            len(attempts) > 1 and attempts[0].error_type is not None
        )
        step.raw_model_output = final_attempt.raw_model_output
        step.parse_success = final_attempt.parse_success
        step.next_action = final_attempt.parsed_action
        step.validation_result = final_attempt.validation_result
        step.registry_accepted = final_attempt.validation_accepted
        step.role_compliant = final_attempt.role_compliant
        step.selection_latency_ms = round(
            sum(attempt.selection_latency_ms or 0.0 for attempt in attempts),
            3,
        )
        step.metadata.update(
            {
                "attempt_count": len(attempts),
                "repair_attempt_count": step.repair_attempt_count,
                "final_attempt_type": final_attempt.attempt_type,
            }
        )

        if final_attempt.error_type is not None:
            if final_attempt.attempt_type == "repair":
                if final_attempt.parse_success:
                    step.error_type = "validation_failed_after_repair"
                    step.error_message = final_attempt.error_message or "Validation failed after repair."
                else:
                    step.error_type = "parse_failed_after_repair"
                    step.error_message = final_attempt.error_message or "Parse failed after repair."
            else:
                step.error_type = final_attempt.error_type
                step.error_message = final_attempt.error_message

        next_action: NextAction | None = None
        if final_attempt.parsed_action is not None:
            next_action = NextAction.model_validate(final_attempt.parsed_action)

        execution_output: ScriptExecutionBridgeOutput | None = None
        if next_action is not None and self.config.execute_actions and final_attempt.validation_accepted:
            execution_start = time.perf_counter()
            execution_output = bridge.execute_next_action(
                next_action,
                run_id=self.config.run_id,
                agent_id=state.agent_id,
                step_index=step_index,
            )
            step.execution_latency_ms = _elapsed_ms(execution_start)
            step.execution_attempted = True
            step.execution_success = execution_output.success
            step.raw_execution_result = execution_output.raw_result.model_dump(mode="json")
            if execution_output.normalized_result is not None:
                step.normalized_execution_result = execution_output.normalized_result.model_dump(mode="json")
            if not execution_output.success:
                step.error_type = execution_output.raw_result.error_type or "execution_failed"
                step.error_message = execution_output.raw_result.error_message or "Execution failed."
        elif final_attempt.validation_accepted is False and step.error_type is None:
            issue_codes = ", ".join(final_attempt.issue_codes())
            step.error_type = "validation_failed"
            step.error_message = f"Action validation rejected: {issue_codes}"
        elif next_action is not None:
            step.execution_attempted = False
            step.execution_success = None

        step.total_step_latency_ms = _elapsed_ms(step_start)
        if next_action is not None:
            updated_state = self._state_with_history(state, next_action, step_index, step, execution_output)
        else:
            updated_state = state
        self._log_step(history_logger, step, state.agent_id)

        issue_codes = final_attempt.issue_codes()
        session_step = AutonomousSessionStepSummary(
            step_index=step_index,
            success=step.error_type is None,
            action=next_action.action if next_action is not None else None,
            parameters=dict(next_action.parameters) if next_action is not None else {},
            status=(
                "success"
                if step.error_type is None
                else "validation_failed"
                if step.error_type in {"validation_failed_after_repair", "validation_failed"}
                else step.error_type
            ),
            error_type=step.error_type,
            issue_codes=issue_codes,
        )
        model_action: ModelBehaviorSelectedAction | None = None
        if next_action is not None:
            model_action = ModelBehaviorSelectedAction(
                step_index=step_index,
                action=next_action.action,
                parameters=dict(next_action.parameters),
                reason=next_action.reason,
                expected_result=next_action.expected_result,
                registry_accepted=final_attempt.validation_accepted,
                role_compliant=step.role_compliant,
                executed=step.execution_attempted,
                success=step.error_type is None,
                issue_codes=issue_codes,
                metadata={
                    "final_attempt_index": final_attempt.attempt_index,
                    "repaired": step.repaired,
                    "initial_failure_preserved": step.initial_failure_preserved,
                },
            )
        return step, updated_state, model_action, session_step

    def _run_action_attempt(
        self,
        *,
        state: AgentState,
        step_index: int,
        attempt_index: int,
        attempt_type: Literal["initial", "repair"],
        prompt_messages: list[dict[str, str]],
        provider: ActionProvider,
        registry: ScriptRegistry,
        role_template: RoleTemplate,
        write_workspace_path: str | None,
    ) -> ExperimentAttemptRecord:
        attempt = ExperimentAttemptRecord(
            step_index=step_index,
            attempt_index=attempt_index,
            attempt_type=attempt_type,
            prompt_kind=attempt_type,
            timestamp=utc_now_iso(),
            prompt_messages=prompt_messages,
        )
        selection_start = time.perf_counter()
        try:
            provider_result = provider.next_action_text(
                agent_state=state,
                prompt_messages=prompt_messages,
                step_index=step_index,
            )
            attempt.raw_model_output = provider_result.raw_model_output
            attempt.metadata.update(provider_result.metadata)
        except Exception as exc:
            attempt.selection_latency_ms = _elapsed_ms(selection_start)
            attempt.error_type = "provider_error"
            attempt.error_message = str(exc) if str(exc).strip() else exc.__class__.__name__
            return attempt

        try:
            next_action = parse_next_action_text(provider_result.raw_model_output)
            attempt.parse_success = True
            attempt.parsed_action = next_action.model_dump(mode="json")
        except NextActionContractError as exc:
            attempt.selection_latency_ms = _elapsed_ms(selection_start)
            attempt.error_type = exc.__class__.__name__
            attempt.error_message = str(exc)
            return attempt

        validation = validate_next_action_against_registry(next_action, registry, role_template)
        validation = self._apply_write_workspace_policy(
            next_action,
            validation,
            write_workspace_path=write_workspace_path,
        )
        attempt.selection_latency_ms = _elapsed_ms(selection_start)
        attempt.validation_accepted = validation.accepted
        attempt.validation_result = validation.model_dump(mode="json")
        attempt.validation_issues = [issue.model_dump(mode="json") for issue in validation.issues]
        attempt.role_compliant = _role_compliant(next_action, validation, role_template)
        if not validation.accepted:
            issue_codes = ", ".join(issue.code for issue in validation.issues)
            attempt.error_type = "validation_failed"
            attempt.error_message = f"Action validation rejected: {issue_codes}"
        return attempt

    def _should_attempt_repair(self, attempt: ExperimentAttemptRecord) -> bool:
        if self.config.repair_attempts_per_step <= 0:
            return False
        if attempt.error_type is None:
            return False
        if attempt.error_type == "provider_error":
            return False
        if not attempt.parse_success:
            return self.config.repair_on_parse_failure
        if attempt.validation_accepted is False:
            return self.config.repair_on_validation_failure
        return False

    def _build_repair_prompt_messages(
        self,
        *,
        state: AgentState,
        registry: ScriptRegistry,
        role_template: RoleTemplate,
        previous_attempt: ExperimentAttemptRecord,
    ) -> list[dict[str, str]]:
        lines = [
            "Previous response was rejected by the action validator.",
            "Return a corrected NextAction JSON object only.",
            "Do not include Markdown.",
            "Do not include comments.",
            "Do not include prose before or after JSON.",
            "Required shape:",
            '{ "action": "...", "parameters": {...}, "reason": "...", "expected_result": "..." }',
            "",
            "Reason:",
        ]
        if previous_attempt.validation_issues:
            for issue in previous_attempt.validation_issues:
                lines.append(f"- {issue.get('code')}: {issue.get('message')}")
        elif previous_attempt.error_type:
            lines.append(f"- {previous_attempt.error_type}: {previous_attempt.error_message}")
        else:
            lines.append("- unknown_error: previous attempt was rejected.")

        if self.config.repair_prompt_include_previous_raw_output:
            lines.extend(
                [
                    "",
                    "Previous raw output:",
                    previous_attempt.raw_model_output or "<empty>",
                ]
            )

        if self.config.repair_prompt_include_allowed_actions:
            lines.extend(["", "Allowed action schemas:"])
            allowed = state.available_action_names()
            for descriptor in registry.scripts:
                if descriptor.name not in allowed:
                    continue
                required = sorted(descriptor.required_parameter_names())
                params = [
                    {
                        "name": p.name,
                        "type": p.type,
                        "required": p.required,
                        "description": p.description,
                    }
                    for p in descriptor.parameters
                ]
                lines.append(
                    json.dumps(
                        {
                            "action": descriptor.name,
                            "required_parameters": required,
                            "parameters": params,
                            "example": descriptor.examples[0] if descriptor.examples else {},
                        },
                        ensure_ascii=False,
                        sort_keys=True,
                    )
                )

        if self.config.repair_prompt_include_role_constraints:
            lines.extend(
                [
                    "",
                    "Role constraints:",
                    json.dumps(role_template.constraints.model_dump(), ensure_ascii=False, sort_keys=True),
                ]
            )

        lines.extend(
            [
                "",
                "Final response rule:",
                "Return exactly one raw JSON object matching the NextAction contract.",
            ]
        )

        return [
            {
                "role": "system",
                "content": (
                    "You are repairing one invalid action selection for a controlled local LLM agent. "
                    "You must return only valid raw JSON."
                ),
            },
            {"role": "user", "content": "\n".join(lines)},
        ]

    def _state_with_history(
        self,
        state: AgentState,
        next_action: NextAction,
        step_index: int,
        step: ExperimentStepRecord,
        execution_output: ScriptExecutionBridgeOutput | None,
    ) -> AgentState:
        status = "success" if step.error_type is None else "failure"
        summary = f"Selected action '{next_action.action}'."
        if execution_output is not None:
            if execution_output.success:
                summary = f"Executed action '{next_action.action}' successfully."
            else:
                summary = f"Execution failed for action '{next_action.action}'."
        elif not self.config.execute_actions:
            summary = f"Selected action '{next_action.action}' without execution."
        entry = ActionHistoryEntry(
            step=step_index,
            action=next_action.action,
            parameters=dict(next_action.parameters),
            status=status,
            summary=summary,
            error=step.error_message,
        )
        payload = state.model_dump()
        payload["history"] = [item.model_dump() for item in state.history] + [entry.model_dump()]
        payload["current_step"] = step_index + 1
        return AgentState.model_validate(payload)

    def _make_stop_evaluator(
        self,
        scenario: EvaluationScenario,
        activity_profile: NormalActivityProfile,
    ) -> AutonomousStopCriteriaEvaluator:
        cfg = AutonomousStopCriteriaConfig(
            max_steps=self.config.max_steps or scenario.stop_policy.max_steps,
            stop_on_validation_failure=scenario.stop_policy.stop_on_validation_failure,
            stop_on_unsafe_action=scenario.stop_policy.stop_on_unsafe_action,
            stop_on_repeated_action=scenario.stop_policy.stop_on_repeated_action,
            stop_on_forbidden_for_normality=scenario.stop_policy.stop_on_forbidden_for_normality,
            stop_on_excessive_atypical_actions=scenario.stop_policy.stop_on_excessive_atypical_actions,
            require_progress_signal=scenario.stop_policy.stop_on_no_progress,
        )
        return AutonomousStopCriteriaEvaluator(config=cfg, activity_profile=activity_profile)

    def _apply_write_workspace_policy(
        self,
        next_action: NextAction,
        validation: ScriptValidationResult,
        *,
        write_workspace_path: str | None,
    ) -> ScriptValidationResult:
        if not self.config.enforce_write_workspace or write_workspace_path is None:
            return validation
        if next_action.action not in WRITE_ACTIONS:
            return validation

        raw_path = next_action.parameters.get("path")
        if not isinstance(raw_path, str):
            return validation
        normalized_path = _normalize_relative_path(raw_path)
        if normalized_path.startswith(write_workspace_path):
            return validation

        issue = ScriptValidationIssue(
            code="write_path_outside_workspace",
            message=(
                f"Write action '{next_action.action}' must target experiment workspace "
                f"'{write_workspace_path}', got '{normalized_path}'."
            ),
            layer="safety_policy",
            metadata={
                "workspace": write_workspace_path,
                "requested_path": normalized_path,
            },
        )
        return ScriptValidationResult(
            accepted=False,
            action=next_action.action,
            issues=list(validation.issues) + [issue],
            metadata={
                **validation.metadata,
                "write_workspace_enforced": True,
                "write_workspace_path": write_workspace_path,
            },
        )

    def _evaluate_activity(
        self,
        selected_actions: list[ModelBehaviorSelectedAction],
        activity_profile: NormalActivityProfile,
    ) -> Any:
        steps = [
            ActivityTrajectoryStep(
                step_index=action.step_index,
                action=action.action,
                parameters=dict(action.parameters),
                success=bool(action.success),
                issue_codes=list(action.issue_codes),
                reason=action.reason,
                expected_result=action.expected_result,
            )
            for action in selected_actions
        ]
        return ActivityTrajectoryEvaluator().evaluate(steps, activity_profile)

    def _build_model_behavior_result(
        self,
        *,
        scenario: EvaluationScenario,
        steps: list[ExperimentStepRecord],
        selected_actions: list[ModelBehaviorSelectedAction],
        activity_result: Any,
        started_at: str,
        completed_at: str,
        wall_time_seconds: float,
    ) -> ModelBehaviorEvaluationResult:
        total_steps = len(steps)
        parse_success_count = sum(1 for step in steps if step.parse_success)
        initial_attempts = [
            attempt
            for step in steps
            for attempt in step.attempts
            if attempt.get("attempt_type") == "initial"
        ]
        repair_attempts = [
            attempt
            for step in steps
            for attempt in step.attempts
            if attempt.get("attempt_type") == "repair"
        ]
        repair_summary = {
            "initial_parse_success_count": sum(1 for attempt in initial_attempts if attempt.get("parse_success") is True),
            "initial_validation_accept_count": sum(1 for attempt in initial_attempts if attempt.get("validation_accepted") is True),
            "repair_attempt_count": len(repair_attempts),
            "repair_parse_success_count": sum(1 for attempt in repair_attempts if attempt.get("parse_success") is True),
            "repair_validation_accept_count": sum(1 for attempt in repair_attempts if attempt.get("validation_accepted") is True),
            "repaired_step_count": sum(1 for step in steps if step.repaired),
            "unrecovered_failure_count": sum(1 for step in steps if step.error_type is not None and not step.repaired),
            "final_validation_accept_count": sum(1 for step in steps if step.registry_accepted is True),
            "execution_success_count": sum(1 for step in steps if step.execution_success is True),
        }
        registry_accepted_count = sum(1 for action in selected_actions if action.registry_accepted is True)
        role_compliant_count = sum(1 for action in selected_actions if action.role_compliant is True)
        validation_failure_count = sum(
            1 for action in selected_actions if action.registry_accepted is False or action.role_compliant is False
        ) + sum(1 for step in steps if not step.parse_success)
        unsafe_action_count = sum(
            1
            for action in selected_actions
            if any(code in {"unsafe_action", "unsafe_path", "unsafe_url", "unsafe_command"} for code in action.issue_codes)
        )
        validation_metrics = ModelBehaviorValidationMetrics(
            total_steps=total_steps,
            json_valid_count=parse_success_count,
            next_action_parse_success_count=parse_success_count,
            registry_accepted_count=registry_accepted_count,
            role_compliant_count=role_compliant_count,
            validation_failure_count=validation_failure_count,
            unsafe_action_count=unsafe_action_count,
            execution_success_count=sum(1 for action in selected_actions if action.executed and action.success is True),
            execution_failure_count=sum(1 for action in selected_actions if action.executed and action.success is False),
            metadata={"repair_summary": repair_summary},
        )
        verdict = derive_model_behavior_verdict(validation_metrics, activity_result)
        return ModelBehaviorEvaluationResult(
            evaluation_id="experiment_scenario_runner_v1",
            run_id=self.config.run_id,
            scenario_id=scenario.scenario_id,
            model=ModelBehaviorModelSpec(
                model_id=self.config.model_id,
                model_name=self.config.model_name,
                model_path=(self.config.model_preflight_result or {}).get("resolved_model_path"),
                model_family=(self.config.model_registry_spec or {}).get("display_name"),
                size_class=(self.config.model_registry_spec or {}).get("parameter_size"),
                quantization=(self.config.model_registry_spec or {}).get("quantization"),
                cpu_only=scenario.resource_plan.cpu_only,
                metadata={
                    "registry_spec": self.config.model_registry_spec,
                    "preflight": self.config.model_preflight_result,
                    "cli_overrides": self.config.model_cli_overrides,
                },
            ),
            run_mode="dry_run" if self.config.mode == "fake" else "local_model",
            verdict=verdict,
            selected_actions=selected_actions,
            validation_metrics=validation_metrics,
            behavioral_evaluation=activity_result,
            resource_metrics=ModelBehaviorResourceMetrics(wall_time_seconds_avg=wall_time_seconds),
            started_at=started_at,
            completed_at=completed_at,
            notes=["Fake/scripted mode: no local model was called."] if self.config.mode == "fake" else [],
            metadata={"repair_summary": repair_summary},
        )

    def _build_resource_summary(
        self,
        *,
        started_at: str,
        resource_start: dict[str, Any],
        steps: list[ExperimentStepRecord],
        wall_time_seconds: float,
    ) -> dict[str, Any]:
        resource_end = _resource_snapshot()
        return {
            "python_version": sys.version,
            "platform": platform.platform(),
            "process_id": resource_end.get("process_id"),
            "start_time": started_at,
            "end_time": utc_now_iso(),
            "wall_time_ms": round(wall_time_seconds * 1000.0, 3),
            "resource_start": resource_start,
            "resource_end": resource_end,
            "per_step_latency_ms": [
                {
                    "step_index": step.step_index,
                    "selection_latency_ms": step.selection_latency_ms,
                    "execution_latency_ms": step.execution_latency_ms,
                    "total_step_latency_ms": step.total_step_latency_ms,
                }
                for step in steps
            ],
        }

    def _log_step(
        self,
        logger: ExecutionHistoryLogger,
        step: ExperimentStepRecord,
        agent_id: str,
    ) -> None:
        if not self.config.write_history_logs:
            return
        error_record: ExecutionErrorRecord | None = None
        error_id: str | None = None
        status = "success" if step.error_type is None else "failure"
        if step.error_type is not None:
            error_id = stable_record_id("error", self.config.run_id, agent_id, step.step_index, step.error_type)
            error_record = ExecutionErrorRecord(
                error_id=error_id,
                created_at=utc_now_iso(),
                run_id=self.config.run_id,
                agent_id=agent_id,
                step_index=step.step_index,
                action=step.next_action.get("action") if step.next_action else None,
                error_type=step.error_type,
                error_message=step.error_message or step.error_type,
                source="ExperimentScenarioRunner",
                details={"step": step.model_dump(mode="json")},
            )
        history = ExecutionHistoryRecord(
            record_id=stable_record_id("scenario_step", self.config.run_id, agent_id, step.step_index, status),
            record_type="runner_step",
            status="success" if step.error_type is None else "failure",
            created_at=utc_now_iso(),
            run_id=self.config.run_id,
            agent_id=agent_id,
            step_index=step.step_index,
            action=step.next_action.get("action") if step.next_action else None,
            next_action=step.next_action,
            summary=step.error_message or f"Scenario step {step.step_index} completed.",
            details={
                "parse_success": step.parse_success,
                "registry_accepted": step.registry_accepted,
                "role_compliant": step.role_compliant,
                "execution_attempted": step.execution_attempted,
                "execution_success": step.execution_success,
            },
            error_id=error_id,
        )
        logger.append_history_and_error(history, error_record)

    def _log_attempt_error(
        self,
        logger: ExecutionHistoryLogger,
        attempt: ExperimentAttemptRecord,
        agent_id: str,
    ) -> None:
        if not self.config.write_history_logs or attempt.error_type is None:
            return
        action = None
        if attempt.parsed_action is not None:
            action = attempt.parsed_action.get("action")
        suffix = f"{attempt.attempt_type}_attempt{attempt.attempt_index}_{attempt.error_type}"
        error_id = stable_record_id("error", self.config.run_id, agent_id, attempt.step_index, suffix)
        error_record = ExecutionErrorRecord(
            error_id=error_id,
            created_at=utc_now_iso(),
            run_id=self.config.run_id,
            agent_id=agent_id,
            step_index=attempt.step_index,
            action=action,
            error_type=attempt.error_type,
            error_message=attempt.error_message or attempt.error_type,
            source="ExperimentScenarioRunner",
            details={"attempt": attempt.model_dump(mode="json")},
            metadata={
                "attempt_index": attempt.attempt_index,
                "attempt_type": attempt.attempt_type,
                "prompt_kind": attempt.prompt_kind,
            },
        )
        history_record = ExecutionHistoryRecord(
            record_id=stable_record_id(
                "attempt",
                self.config.run_id,
                agent_id,
                attempt.step_index,
                f"{attempt.attempt_type}_attempt{attempt.attempt_index}_failed",
            ),
            record_type="error",
            status="validation_failed" if attempt.parse_success else "decision_failed",
            created_at=utc_now_iso(),
            run_id=self.config.run_id,
            agent_id=agent_id,
            step_index=attempt.step_index,
            action=action,
            next_action=attempt.parsed_action,
            summary=attempt.error_message or f"{attempt.attempt_type} attempt failed.",
            details={
                "attempt_index": attempt.attempt_index,
                "attempt_type": attempt.attempt_type,
                "parse_success": attempt.parse_success,
                "validation_accepted": attempt.validation_accepted,
                "issue_codes": attempt.issue_codes(),
            },
            error_id=error_id,
        )
        logger.append_history_and_error(history_record, error_record)

    def _write_manifest(
        self,
        out_dir: Path,
        scenario: EvaluationScenario,
        agent_spec: Any,
        started_at: str,
        steps: list[ExperimentStepRecord],
        stopped_reason: str | None,
        write_workspace_path: str | None,
    ) -> None:
        self._write_json(
            out_dir / "manifest.json",
            {
                "runner_id": "experiment_scenario_runner_v1",
                "run_id": self.config.run_id,
                "scenario_id": scenario.scenario_id,
                "scenario_path": self.config.scenario_path,
                "agent_id": agent_spec.agent_id,
                "mode": self.config.mode,
                "model_id": self.config.model_id,
                "model_name": self.config.model_name,
                "base_url": self.config.base_url,
                "model": self._manifest_model_section(),
                "execute_actions": self.config.execute_actions,
                "repair": {
                    "repair_enabled": self.config.repair_attempts_per_step > 0,
                    "repair_attempts_per_step": self.config.repair_attempts_per_step,
                    "repair_on_parse_failure": self.config.repair_on_parse_failure,
                    "repair_on_validation_failure": self.config.repair_on_validation_failure,
                    "repair_prompt_include_allowed_actions": self.config.repair_prompt_include_allowed_actions,
                    "repair_prompt_include_role_constraints": self.config.repair_prompt_include_role_constraints,
                    "repair_prompt_include_previous_raw_output": self.config.repair_prompt_include_previous_raw_output,
                },
                "safety_workspace": {
                    "enforce_write_workspace": self.config.enforce_write_workspace,
                    "write_workspace_path": write_workspace_path,
                    "policy": "write actions are rejected unless their path is inside write_workspace_path",
                    "write_actions": sorted(WRITE_ACTIONS),
                },
                "started_at": started_at,
                "completed_at": utc_now_iso(),
                "step_count": len(steps),
                "stopped_reason": stopped_reason,
                "artifacts": _artifact_names(),
                "limitations": [
                    "Runner v1 supports one agent per run.",
                    "Fake mode does not call a local model.",
                    "Local mode is implemented structurally but was not exercised by offline tests.",
                ],
            },
        )

    def _write_replay_commands(self, out_dir: Path) -> None:
        command = (
            "python scripts\\run_agent_scenario.py "
            f"--scenario {self.config.scenario_path} "
            f"--mode {self.config.mode} "
            f"--out-dir {self.config.out_dir} "
            f"--run-id {self.config.run_id} "
            f"--model-id {self.config.model_id} "
            f"--max-steps {self.config.max_steps or 1} "
            "--force"
        )
        if self.config.repair_attempts_per_step:
            command += f" --repair-attempts {self.config.repair_attempts_per_step}"
        if self.config.models_config_path:
            command += f" --models-config {self.config.models_config_path}"
        elif self.config.model_name != "fake-scripted-provider":
            command += f" --model-name {self.config.model_name}"
        if self.config.base_url:
            command += f" --base-url {self.config.base_url}"
        if self.config.execute_actions:
            command += " --execute-actions"
        else:
            command += " --no-execute-actions"
        (out_dir / "replay_commands.ps1").write_text(command + "\n", encoding="utf-8")

    def _write_readme(self, out_dir: Path, scenario: EvaluationScenario, stopped_reason: str | None) -> None:
        text = f"""# Experiment scenario run

## Summary

- runner: `experiment_scenario_runner_v1`
- run_id: `{self.config.run_id}`
- scenario_id: `{scenario.scenario_id}`
- mode: `{self.config.mode}`
- execute_actions: `{self.config.execute_actions}`
- stopped_reason: `{stopped_reason}`

## Artifact files

{chr(10).join(f"- `{name}`" for name in _artifact_names())}

## Notes

Fake mode uses scripted actions and does not call `llama-server`.
Local mode is available for future dry runs but was not used to create this artifact unless `mode=local`.
"""
        (out_dir / "README.md").write_text(text, encoding="utf-8")

    @staticmethod
    def _write_json(path: Path, payload: dict[str, Any]) -> None:
        path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    def _manifest_model_section(self) -> dict[str, Any]:
        spec = self.config.model_registry_spec or {}
        preflight = self.config.model_preflight_result or {}
        return {
            "model_id": self.config.model_id,
            "model_name": self.config.model_name,
            "gguf_path": spec.get("gguf_path"),
            "resolved_model_path": preflight.get("resolved_model_path"),
            "runtime": spec.get("runtime", "llama.cpp / llama-server"),
            "base_url": self.config.base_url or spec.get("base_url"),
            "quantization": spec.get("quantization"),
            "parameter_size": spec.get("parameter_size"),
            "expected_cpu_only": spec.get("expected_cpu_only"),
            "preflight_status": preflight.get("status", "not_available"),
            "preflight_issues": preflight.get("issues", []),
            "preflight_warnings": preflight.get("warnings", []),
            "can_attempt_local_run": preflight.get("can_attempt_local_run"),
            "cli_overrides": self.config.model_cli_overrides,
            "models_config_path": self.config.models_config_path,
        }


class _ArtifactWriters:
    def __init__(self, out_dir: Path) -> None:
        self.out_dir = out_dir
        self.handles: dict[str, Any] = {}

    def open(self) -> None:
        for name in [
            "attempts.jsonl",
            "steps.jsonl",
            "raw_model_outputs.jsonl",
            "selected_actions.jsonl",
            "validation_results.jsonl",
            "execution_results.jsonl",
        ]:
            self.handles[name] = (self.out_dir / name).open("w", encoding="utf-8")

    def close(self) -> None:
        for handle in self.handles.values():
            handle.close()

    def rewrite_steps(self, steps: list[ExperimentStepRecord]) -> None:
        handle = self.handles["steps.jsonl"]
        handle.seek(0)
        handle.truncate()
        for step in steps:
            self._write("steps.jsonl", step.model_dump(mode="json"))
        handle.flush()

    def write_step(self, step: ExperimentStepRecord) -> None:
        self._write("steps.jsonl", step.model_dump(mode="json"))
        for attempt in step.attempts:
            self._write("attempts.jsonl", attempt)
            self._write(
                "raw_model_outputs.jsonl",
                {
                    "step_index": step.step_index,
                    "agent_id": step.agent_id,
                    "attempt_index": attempt.get("attempt_index"),
                    "attempt_type": attempt.get("attempt_type"),
                    "raw_model_output": attempt.get("raw_model_output"),
                    "parse_success": attempt.get("parse_success"),
                    "error_type": attempt.get("error_type") if not attempt.get("parse_success") else None,
                    "error_message": attempt.get("error_message") if not attempt.get("parse_success") else None,
                },
            )
            if attempt.get("validation_result") is not None:
                self._write(
                    "validation_results.jsonl",
                    {
                        "step_index": step.step_index,
                        "agent_id": step.agent_id,
                        "attempt_index": attempt.get("attempt_index"),
                        "attempt_type": attempt.get("attempt_type"),
                        "validation_result": attempt.get("validation_result"),
                    },
                )
        if step.next_action is not None and step.registry_accepted is True:
            self._write(
                "selected_actions.jsonl",
                {
                    "step_index": step.step_index,
                    "agent_id": step.agent_id,
                    "final_attempt_index": step.final_attempt_index,
                    "repaired": step.repaired,
                    "next_action": step.next_action,
                },
            )
        if step.execution_attempted:
            self._write(
                "execution_results.jsonl",
                {
                    "step_index": step.step_index,
                    "agent_id": step.agent_id,
                    "raw_execution_result": step.raw_execution_result,
                    "normalized_execution_result": step.normalized_execution_result,
                },
            )

    def _write(self, name: str, payload: dict[str, Any]) -> None:
        self.handles[name].write(json.dumps(payload, ensure_ascii=False, separators=(",", ":")) + "\n")


def _action_spec_from_registry(action_name: str, registry: ScriptRegistry) -> ActionSpec:
    descriptor = registry.get_script(action_name)
    if descriptor is None:
        return ActionSpec(name=action_name, description="Action not present in registry.")
    schema = {
        p.name: {
            "type": p.type,
            "required": p.required,
            "description": p.description,
        }
        for p in descriptor.parameters
    }
    return ActionSpec(
        name=descriptor.name,
        description=descriptor.description,
        parameters_schema=schema,
        safety_notes=list(descriptor.safety.notes),
    )


def _role_compliant(
    next_action: NextAction,
    validation: ScriptValidationResult,
    role_template: RoleTemplate,
) -> bool:
    if any(issue.layer == "role_constraints" for issue in validation.issues):
        return False
    constraints = role_template.constraints
    if next_action.action in constraints.forbidden_action_names:
        return False
    if constraints.allowed_action_names and next_action.action not in constraints.allowed_action_names:
        return False
    return True


def _final_attempt(attempts: list[ExperimentAttemptRecord]) -> ExperimentAttemptRecord:
    for attempt in attempts:
        if attempt.parse_success and attempt.validation_accepted is True:
            return attempt
    return attempts[-1]


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 3)


def _resource_snapshot() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "process_id": None,
        "process_rss_mb": None,
        "system_cpu_percent": None,
        "system_ram_used_mb": None,
        "psutil_available": False,
    }
    try:
        import os
        import psutil

        process = psutil.Process(os.getpid())
        snapshot.update(
            {
                "process_id": process.pid,
                "process_rss_mb": round(process.memory_info().rss / (1024 * 1024), 3),
                "system_cpu_percent": psutil.cpu_percent(interval=None),
                "system_ram_used_mb": round(psutil.virtual_memory().used / (1024 * 1024), 3),
                "psutil_available": True,
            }
        )
    except Exception as exc:  # pragma: no cover - defensive for missing psutil
        snapshot["psutil_error"] = str(exc)
    return snapshot


def _artifact_names() -> list[str]:
    return [
        "manifest.json",
        "attempts.jsonl",
        "steps.jsonl",
        "raw_model_outputs.jsonl",
        "selected_actions.jsonl",
        "validation_results.jsonl",
        "execution_results.jsonl",
        "history.jsonl",
        "errors.jsonl",
        "activity_evaluation.json",
        "model_behavior_result.json",
        "resource_summary.json",
        "replay_commands.ps1",
        "README.md",
    ]


def _ensure_artifact_files(out_dir: Path, names: list[str]) -> None:
    for name in names:
        path = out_dir / name
        if not path.exists():
            path.write_text("", encoding="utf-8")


def _clear_artifact_dir_preserving_runtime_logs(out_dir: Path) -> None:
    preserve_names = {
        "codex_started_powershell_pid.txt",
        "llama_server_stderr.log",
        "llama_server_stdout.log",
    }
    for child in out_dir.iterdir():
        if child.name in preserve_names:
            continue
        if child.is_dir():
            shutil.rmtree(child)
        else:
            child.unlink()


def _normalize_relative_path(value: str) -> str:
    normalized = str(PurePosixPath(value.strip().replace("\\", "/")))
    if normalized in {"", "."}:
        return ""
    return normalized.rstrip("/")


def _safe_path_token(value: str) -> str:
    return "".join(ch if ch.isalnum() or ch in {"-", "_"} else "_" for ch in value).strip("_") or "run"
