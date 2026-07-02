from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .action_selector import ActionSelectionResult, ActionSelector
from .execution_history import ExecutionHistoryLogger, history_from_action_selection
from .history_aware_selection import build_state_with_history_entry, next_action_to_history_entry
from .role_template import RoleTemplate, load_role_template
from .schemas import NextAction
from .state import AgentState

TrajectoryStepStatus = Literal[
    "selected",
    "validation_failed",
    "selection_failed",
    "repeated_action_detected",
    "stopped",
]

TrajectoryRunStatus = Literal[
    "completed",
    "stopped_on_validation_failure",
    "stopped_on_selection_failure",
    "stopped_on_repeated_action",
    "stopped_on_max_steps",
    "failed",
]


class RoleConstrainedTrajectoryConfig(BaseModel):
    trajectory_id: str = "role_constrained_trajectory_v1"
    max_steps: int = 3
    stop_on_validation_failure: bool = True
    stop_on_selection_failure: bool = True
    stop_on_repeated_action: bool = True
    prevent_exact_action_repeat: bool = True
    write_history_logs: bool = False
    registry_path: str | None = "configs/script_registry.example.json"
    role_template_path: str | None = "configs/roles/office_worker.example.json"
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("trajectory_id")
    @classmethod
    def validate_trajectory_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("trajectory_id must be non-empty.")
        return value

    @field_validator("max_steps")
    @classmethod
    def validate_max_steps(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_steps must be >= 1.")
        return value

    @model_validator(mode="after")
    def validate_no_execution_toggle(self) -> RoleConstrainedTrajectoryConfig:
        # This config is selection-only by contract.
        if self.metadata.get("execute_actions") is True:
            raise ValueError("RoleConstrainedTrajectoryConfig must not enable action execution.")
        return self


class TrajectoryStepResult(BaseModel):
    trajectory_id: str
    run_id: str
    agent_id: str
    step_index: int
    status: TrajectoryStepStatus
    success: bool
    selection_result: ActionSelectionResult | None = None
    next_action: NextAction | None = None
    repeated_action: bool = False
    history_length_after_step: int | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("trajectory_id", "run_id", "agent_id")
    @classmethod
    def validate_non_empty_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("trajectory_id, run_id, and agent_id must be non-empty.")
        return value

    @field_validator("step_index")
    @classmethod
    def validate_step_index(cls, value: int) -> int:
        if value < 1:
            raise ValueError("step_index must be >= 1.")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> TrajectoryStepResult:
        if self.success and self.next_action is None:
            raise ValueError("next_action should be present when success=True.")
        if not self.success:
            if not self.error_type or not self.error_type.strip():
                raise ValueError("error_type should be non-empty when success=False.")
            if not self.error_message or not self.error_message.strip():
                raise ValueError("error_message should be non-empty when success=False.")
        if self.status == "repeated_action_detected" and not self.repeated_action:
            raise ValueError("repeated_action must be true for repeated_action_detected.")
        return self


class TrajectoryRunResult(BaseModel):
    trajectory_id: str
    run_id: str
    agent_id: str
    status: TrajectoryRunStatus
    success: bool
    steps: list[TrajectoryStepResult]
    final_state: AgentState | None = None
    stopped_reason: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("trajectory_id", "run_id", "agent_id")
    @classmethod
    def validate_non_empty_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("trajectory_id, run_id, and agent_id must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> TrajectoryRunResult:
        if not self.steps:
            raise ValueError("steps must not be empty.")
        if not self.success and (self.stopped_reason is None or not self.stopped_reason.strip()):
            raise ValueError("stopped_reason should be non-empty when success=False.")
        return self

    def successful_steps_count(self) -> int:
        return sum(1 for step in self.steps if step.success)

    def failed_steps_count(self) -> int:
        return sum(1 for step in self.steps if not step.success)

    def selected_actions(self) -> list[str]:
        actions: list[str] = []
        for step in self.steps:
            if step.next_action is not None:
                actions.append(step.next_action.action)
        return actions


def next_action_repeated(next_action: NextAction, previous_actions: list[NextAction]) -> bool:
    for prev in previous_actions:
        if prev.action == next_action.action and prev.parameters == next_action.parameters:
            return True
    return False


class RoleConstrainedTrajectoryRunner:
    def __init__(
        self,
        selector: ActionSelector,
        config: RoleConstrainedTrajectoryConfig | None = None,
        role_template: RoleTemplate | None = None,
        history_logger: ExecutionHistoryLogger | None = None,
    ) -> None:
        self.selector = selector
        self.config = config or RoleConstrainedTrajectoryConfig()
        self.history_logger = history_logger
        self.role_template = role_template
        if self.role_template is None and self.config.role_template_path is not None:
            self.role_template = load_role_template(self.config.role_template_path)

    def _append_log_if_enabled(
        self,
        run_id: str,
        step_index: int,
        selection_result: ActionSelectionResult,
    ) -> None:
        if not self.config.write_history_logs or self.history_logger is None:
            return
        history_record, error_record = history_from_action_selection(
            selection_result, run_id=run_id, step_index=step_index
        )
        self.history_logger.append_history_and_error(history_record, error_record)

    def run_trajectory(self, initial_state: AgentState, run_id: str) -> TrajectoryRunResult:
        if not run_id.strip():
            raise ValueError("run_id must be non-empty.")
        base_state = AgentState.model_validate(initial_state.model_dump())
        current_state = base_state
        selected_actions: list[NextAction] = []
        steps: list[TrajectoryStepResult] = []
        saw_failure = False

        start_step = current_state.current_step
        for offset in range(self.config.max_steps):
            step_index = start_step + offset
            selection_result = self.selector.select_action(current_state)
            self._append_log_if_enabled(run_id, step_index, selection_result)

            if not selection_result.success:
                status: TrajectoryStepStatus
                run_status: TrajectoryRunStatus
                should_stop = False
                if selection_result.status == "validation_failed":
                    status = "validation_failed"
                    run_status = "stopped_on_validation_failure"
                    should_stop = self.config.stop_on_validation_failure
                else:
                    status = "selection_failed"
                    run_status = "stopped_on_selection_failure"
                    should_stop = self.config.stop_on_selection_failure

                step = TrajectoryStepResult(
                    trajectory_id=self.config.trajectory_id,
                    run_id=run_id,
                    agent_id=current_state.agent_id,
                    step_index=step_index,
                    status=status,
                    success=False,
                    selection_result=selection_result,
                    next_action=selection_result.next_action,
                    repeated_action=False,
                    history_length_after_step=len(current_state.history),
                    error_type=selection_result.error_type or status,
                    error_message=selection_result.error_message or "Action selection failed.",
                )
                steps.append(step)
                saw_failure = True
                if should_stop:
                    return TrajectoryRunResult(
                        trajectory_id=self.config.trajectory_id,
                        run_id=run_id,
                        agent_id=current_state.agent_id,
                        status=run_status,
                        success=False,
                        steps=steps,
                        final_state=current_state,
                        stopped_reason=step.error_message,
                    )
                continue

            if selection_result.next_action is None:
                step = TrajectoryStepResult(
                    trajectory_id=self.config.trajectory_id,
                    run_id=run_id,
                    agent_id=current_state.agent_id,
                    step_index=step_index,
                    status="selection_failed",
                    success=False,
                    selection_result=selection_result,
                    next_action=None,
                    error_type="missing_next_action",
                    error_message="Selection succeeded but next_action is missing.",
                    history_length_after_step=len(current_state.history),
                )
                steps.append(step)
                saw_failure = True
                return TrajectoryRunResult(
                    trajectory_id=self.config.trajectory_id,
                    run_id=run_id,
                    agent_id=current_state.agent_id,
                    status="failed",
                    success=False,
                    steps=steps,
                    final_state=current_state,
                    stopped_reason=step.error_message,
                )

            next_action = selection_result.next_action
            repeated = False
            if self.config.prevent_exact_action_repeat:
                repeated = next_action_repeated(next_action, selected_actions)

            if repeated:
                step = TrajectoryStepResult(
                    trajectory_id=self.config.trajectory_id,
                    run_id=run_id,
                    agent_id=current_state.agent_id,
                    step_index=step_index,
                    status="repeated_action_detected",
                    success=False,
                    selection_result=selection_result,
                    next_action=next_action,
                    repeated_action=True,
                    history_length_after_step=len(current_state.history),
                    error_type="repeated_action_detected",
                    error_message="Next action exactly repeats a previous selected action.",
                )
                steps.append(step)
                saw_failure = True
                if self.config.stop_on_repeated_action:
                    return TrajectoryRunResult(
                        trajectory_id=self.config.trajectory_id,
                        run_id=run_id,
                        agent_id=current_state.agent_id,
                        status="stopped_on_repeated_action",
                        success=False,
                        steps=steps,
                        final_state=current_state,
                        stopped_reason=step.error_message,
                    )
                continue

            selected_actions.append(next_action)
            history_entry = next_action_to_history_entry(
                next_action=next_action,
                step_index=step_index,
                status="success",
                summary=f"Trajectory selected action '{next_action.action}'.",
            )
            current_state = build_state_with_history_entry(
                current_state,
                history_entry,
                next_step=step_index + 1,
                include_existing_history=True,
            )
            step = TrajectoryStepResult(
                trajectory_id=self.config.trajectory_id,
                run_id=run_id,
                agent_id=current_state.agent_id,
                step_index=step_index,
                status="selected",
                success=True,
                selection_result=selection_result,
                next_action=next_action,
                history_length_after_step=len(current_state.history),
            )
            steps.append(step)

        if saw_failure:
            return TrajectoryRunResult(
                trajectory_id=self.config.trajectory_id,
                run_id=run_id,
                agent_id=current_state.agent_id,
                status="stopped_on_max_steps",
                success=False,
                steps=steps,
                final_state=current_state,
                stopped_reason="Reached max_steps with one or more failed trajectory steps.",
            )

        return TrajectoryRunResult(
            trajectory_id=self.config.trajectory_id,
            run_id=run_id,
            agent_id=current_state.agent_id,
            status="completed",
            success=True,
            steps=steps,
            final_state=current_state,
        )


def load_role_constrained_trajectory_config(
    path: str | Path,
) -> RoleConstrainedTrajectoryConfig:
    path_obj = Path(path)
    payload = json.loads(path_obj.read_text(encoding="utf-8"))
    return RoleConstrainedTrajectoryConfig.model_validate(payload)
