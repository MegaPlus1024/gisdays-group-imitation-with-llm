from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .action_selector import ActionSelectionResult, ActionSelector
from .schemas import NextAction
from .state import ActionHistoryEntry, AgentState

HistoryAwareSecondActionStatus = Literal[
    "second_action_selected",
    "first_action_failed",
    "second_action_failed",
    "repeated_action_detected",
    "validation_failed",
]


class HistoryAwareSelectionConfig(BaseModel):
    config_id: str = "history_aware_second_action_v1"
    require_first_action_success: bool = True
    second_step_index: int = 2
    prevent_exact_action_repeat: bool = True
    include_first_action_summary: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config_id")
    @classmethod
    def validate_config_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("config_id must be non-empty.")
        return value

    @field_validator("second_step_index")
    @classmethod
    def validate_second_step_index(cls, value: int) -> int:
        if value < 2:
            raise ValueError("second_step_index must be >= 2.")
        return value


class HistoryAwareSecondActionResult(BaseModel):
    config_id: str
    agent_id: str
    success: bool
    status: HistoryAwareSecondActionStatus
    first_selection: ActionSelectionResult | None = None
    second_selection: ActionSelectionResult | None = None
    updated_state: AgentState | None = None
    repeated_action: bool = False
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("config_id", "agent_id")
    @classmethod
    def validate_non_empty_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("config_id and agent_id must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> HistoryAwareSecondActionResult:
        if self.success and self.second_selection is None:
            raise ValueError("second_selection must be present when success=True.")
        if not self.success:
            if not self.error_type or not self.error_type.strip():
                raise ValueError("error_type must be non-empty when success=False.")
            if not self.error_message or not self.error_message.strip():
                raise ValueError("error_message must be non-empty when success=False.")
        if self.status == "repeated_action_detected" and not self.repeated_action:
            raise ValueError("repeated_action must be true for repeated_action_detected.")
        return self


def next_action_to_history_entry(
    next_action: NextAction,
    step_index: int,
    status: Literal["success", "failure", "skipped", "unknown"] = "success",
    summary: str | None = None,
    error: str | None = None,
) -> ActionHistoryEntry:
    entry_summary = summary
    if entry_summary is None:
        entry_summary = (
            f"Selected action '{next_action.action}' with expected result: "
            f"{next_action.expected_result}"
        )
    return ActionHistoryEntry(
        step=step_index,
        action=next_action.action,
        parameters=dict(next_action.parameters),
        status=status,
        summary=entry_summary,
        error=error,
    )


def build_state_with_history_entry(
    state: AgentState,
    history_entry: ActionHistoryEntry,
    next_step: int | None = None,
    include_existing_history: bool = True,
) -> AgentState:
    if include_existing_history:
        new_history = list(state.history) + [history_entry]
    else:
        new_history = [history_entry]
    new_current_step = next_step if next_step is not None else history_entry.step + 1
    payload = state.model_dump()
    payload["history"] = [entry.model_dump() for entry in new_history]
    payload["current_step"] = new_current_step
    return AgentState.model_validate(payload)


def actions_exactly_equal(a: NextAction, b: NextAction) -> bool:
    return a.action == b.action and a.parameters == b.parameters


class HistoryAwareSecondActionRunner:
    def __init__(
        self,
        selector: ActionSelector,
        config: HistoryAwareSelectionConfig | None = None,
    ) -> None:
        self.selector = selector
        self.config = config or HistoryAwareSelectionConfig()

    def select_second_action(
        self,
        initial_state: AgentState,
    ) -> HistoryAwareSecondActionResult:
        first_selection = self.selector.select_action(initial_state)
        agent_id = initial_state.agent_id

        if self.config.require_first_action_success and not first_selection.success:
            return HistoryAwareSecondActionResult(
                config_id=self.config.config_id,
                agent_id=agent_id,
                success=False,
                status="first_action_failed",
                first_selection=first_selection,
                error_type=first_selection.error_type or "first_action_failed",
                error_message=first_selection.error_message or "First action selection failed.",
                metadata={"stage": "first_selection"},
            )

        if first_selection.next_action is None:
            return HistoryAwareSecondActionResult(
                config_id=self.config.config_id,
                agent_id=agent_id,
                success=False,
                status="first_action_failed",
                first_selection=first_selection,
                error_type="first_action_missing",
                error_message="First selection did not include next_action.",
                metadata={"stage": "first_selection"},
            )

        first_history_entry = next_action_to_history_entry(
            first_selection.next_action,
            step_index=1,
            summary=(
                f"First selected action: {first_selection.next_action.action}"
                if self.config.include_first_action_summary
                else None
            ),
        )
        updated_state = build_state_with_history_entry(
            initial_state,
            first_history_entry,
            next_step=self.config.second_step_index,
            include_existing_history=False,
        )

        second_selection = self.selector.select_action(updated_state)
        if not second_selection.success:
            status: HistoryAwareSecondActionStatus = "second_action_failed"
            if second_selection.status == "validation_failed":
                status = "validation_failed"
            return HistoryAwareSecondActionResult(
                config_id=self.config.config_id,
                agent_id=agent_id,
                success=False,
                status=status,
                first_selection=first_selection,
                second_selection=second_selection,
                updated_state=updated_state,
                error_type=second_selection.error_type or "second_action_failed",
                error_message=second_selection.error_message or "Second action selection failed.",
                metadata={"stage": "second_selection"},
            )

        if second_selection.next_action is None:
            return HistoryAwareSecondActionResult(
                config_id=self.config.config_id,
                agent_id=agent_id,
                success=False,
                status="second_action_failed",
                first_selection=first_selection,
                second_selection=second_selection,
                updated_state=updated_state,
                error_type="second_action_missing",
                error_message="Second selection did not include next_action.",
                metadata={"stage": "second_selection"},
            )

        repeated = (
            self.config.prevent_exact_action_repeat
            and actions_exactly_equal(first_selection.next_action, second_selection.next_action)
        )
        if repeated:
            return HistoryAwareSecondActionResult(
                config_id=self.config.config_id,
                agent_id=agent_id,
                success=False,
                status="repeated_action_detected",
                first_selection=first_selection,
                second_selection=second_selection,
                updated_state=updated_state,
                repeated_action=True,
                error_type="repeated_action_detected",
                error_message="Second action exactly repeats the first action.",
                metadata={"stage": "repeat_check"},
            )

        return HistoryAwareSecondActionResult(
            config_id=self.config.config_id,
            agent_id=agent_id,
            success=True,
            status="second_action_selected",
            first_selection=first_selection,
            second_selection=second_selection,
            updated_state=updated_state,
            repeated_action=False,
            metadata={"stage": "completed"},
        )


def load_history_aware_selection_config(path: str | Path) -> HistoryAwareSelectionConfig:
    path_obj = Path(path)
    payload = json.loads(path_obj.read_text(encoding="utf-8"))
    return HistoryAwareSelectionConfig.model_validate(payload)
