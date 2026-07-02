from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .agent import Agent, AgentStepRequest, AgentStepResult
from .role_template import RoleTemplate, load_role_template
from .schemas import NextAction
from .script_registry import (
    ScriptRegistry,
    ScriptValidationResult,
    load_script_registry,
    validate_next_action_against_registry,
)
from .state import AgentState

RunnerStepStatus = Literal[
    "decision_succeeded",
    "decision_failed",
    "validation_succeeded",
    "validation_failed",
    "pending_execution",
    "skipped",
    "stopped",
]


class AgentRunnerConfig(BaseModel):
    runner_id: str = "agent_runner_v1"
    max_steps: int = 1
    validate_actions: bool = True
    execute_actions: bool = False
    stop_on_agent_failure: bool = True
    stop_on_validation_failure: bool = True
    registry_path: str | None = "configs/script_registry.example.json"
    role_template_path: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("runner_id")
    @classmethod
    def validate_runner_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("runner_id must be non-empty.")
        return value

    @field_validator("max_steps")
    @classmethod
    def validate_max_steps(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_steps must be >= 1.")
        return value

    @model_validator(mode="after")
    def validate_execute_actions_disabled(self) -> AgentRunnerConfig:
        if self.execute_actions:
            raise ValueError("AgentRunner v1 must not execute actions (execute_actions must be false).")
        return self


class RunnerStepResult(BaseModel):
    runner_id: str
    run_id: str
    agent_id: str
    step_index: int
    status: RunnerStepStatus
    success: bool
    agent_step_result: AgentStepResult | None = None
    validation_result: ScriptValidationResult | None = None
    next_action: NextAction | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("runner_id", "run_id", "agent_id")
    @classmethod
    def validate_non_empty_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("runner_id, run_id, and agent_id must be non-empty.")
        return value

    @field_validator("step_index")
    @classmethod
    def validate_step_index(cls, value: int) -> int:
        if value < 1:
            raise ValueError("step_index must be >= 1.")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> RunnerStepResult:
        if not self.success:
            if not self.error_type or not self.error_type.strip():
                raise ValueError("error_type is required when success=False.")
            if not self.error_message or not self.error_message.strip():
                raise ValueError("error_message is required when success=False.")
        if self.status == "validation_failed" and self.validation_result is None:
            raise ValueError("validation_result is required when status=validation_failed.")
        if self.status == "pending_execution" and self.next_action is None:
            raise ValueError("next_action is required when status=pending_execution.")
        return self


class RunnerRunResult(BaseModel):
    runner_id: str
    run_id: str
    agent_id: str
    success: bool
    steps: list[RunnerStepResult]
    stopped_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("runner_id", "run_id", "agent_id")
    @classmethod
    def validate_non_empty_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("runner_id, run_id, and agent_id must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_steps_non_empty(self) -> RunnerRunResult:
        if not self.steps:
            raise ValueError("steps must not be empty.")
        return self

    def successful_steps_count(self) -> int:
        return sum(1 for step in self.steps if step.success)

    def failed_steps_count(self) -> int:
        return sum(1 for step in self.steps if not step.success)


class AgentRunner:
    def __init__(
        self,
        agent: Agent,
        config: AgentRunnerConfig | None = None,
        registry: ScriptRegistry | None = None,
        role_template: RoleTemplate | None = None,
    ) -> None:
        self.agent = agent
        self.config = config or AgentRunnerConfig()
        self.role_template = role_template

        if self.config.validate_actions:
            if registry is not None:
                self.registry = registry
            elif self.config.registry_path is not None:
                self.registry = load_script_registry(self.config.registry_path)
            else:
                self.registry = None
        else:
            self.registry = registry

        if self.role_template is None and self.config.role_template_path is not None:
            self.role_template = load_role_template(self.config.role_template_path)

    def run_one_step(
        self,
        agent_state: AgentState,
        run_id: str,
        step_index: int | None = None,
    ) -> RunnerStepResult:
        effective_step = agent_state.current_step if step_index is None else step_index
        request = AgentStepRequest(
            run_id=run_id,
            agent_state=agent_state,
            step_index=effective_step,
        )
        agent_result = self.agent.decide_next_action(request)

        if not agent_result.success:
            return RunnerStepResult(
                runner_id=self.config.runner_id,
                run_id=run_id,
                agent_id=agent_state.agent_id,
                step_index=effective_step,
                status="decision_failed",
                success=False,
                agent_step_result=agent_result,
                error_type=agent_result.error_type or "decision_failed",
                error_message=agent_result.error_message or "Agent decision failed.",
            )

        if agent_result.next_action is None:
            return RunnerStepResult(
                runner_id=self.config.runner_id,
                run_id=run_id,
                agent_id=agent_state.agent_id,
                step_index=effective_step,
                status="decision_failed",
                success=False,
                agent_step_result=agent_result,
                error_type="missing_next_action",
                error_message="Agent returned success without next_action.",
            )

        next_action = agent_result.next_action

        if not self.config.validate_actions:
            return RunnerStepResult(
                runner_id=self.config.runner_id,
                run_id=run_id,
                agent_id=agent_state.agent_id,
                step_index=effective_step,
                status="pending_execution",
                success=True,
                agent_step_result=agent_result,
                next_action=next_action,
            )

        if self.registry is None:
            return RunnerStepResult(
                runner_id=self.config.runner_id,
                run_id=run_id,
                agent_id=agent_state.agent_id,
                step_index=effective_step,
                status="validation_failed",
                success=False,
                agent_step_result=agent_result,
                next_action=next_action,
                error_type="validation_failed",
                error_message="Action validation is enabled but script registry is unavailable.",
            )

        validation_result = validate_next_action_against_registry(
            next_action=next_action,
            registry=self.registry,
            role_template=self.role_template,
        )

        if validation_result.accepted:
            return RunnerStepResult(
                runner_id=self.config.runner_id,
                run_id=run_id,
                agent_id=agent_state.agent_id,
                step_index=effective_step,
                status="pending_execution",
                success=True,
                agent_step_result=agent_result,
                validation_result=validation_result,
                next_action=next_action,
            )

        issue_codes = [issue.code for issue in validation_result.issues]
        return RunnerStepResult(
            runner_id=self.config.runner_id,
            run_id=run_id,
            agent_id=agent_state.agent_id,
            step_index=effective_step,
            status="validation_failed",
            success=False,
            agent_step_result=agent_result,
            validation_result=validation_result,
            next_action=next_action,
            error_type="validation_failed",
            error_message=f"Action validation rejected: {', '.join(issue_codes)}",
        )

    def run(self, initial_state: AgentState, run_id: str) -> RunnerRunResult:
        step_result = self.run_one_step(initial_state, run_id=run_id, step_index=initial_state.current_step)

        if step_result.success:
            stopped_reason = "pending_execution"
        elif step_result.status == "validation_failed":
            stopped_reason = "validation_failed"
        else:
            stopped_reason = "decision_failed"

        return RunnerRunResult(
            runner_id=self.config.runner_id,
            run_id=run_id,
            agent_id=initial_state.agent_id,
            success=step_result.success,
            steps=[step_result],
            stopped_reason=stopped_reason,
        )


def load_agent_runner_config(path: str | Path) -> AgentRunnerConfig:
    path_obj = Path(path)
    payload = json.loads(path_obj.read_text(encoding="utf-8"))
    return AgentRunnerConfig.model_validate(payload)
