from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .role_template import RoleTemplate, load_role_template
from .schemas import NextAction
from .script_registry import (
    ScriptRegistry,
    ScriptValidationIssue,
    ScriptValidationResult,
    load_script_registry,
    validate_next_action_against_registry,
)
from .state import AgentState

ActionSelectionStatus = Literal[
    "selected",
    "selection_failed",
    "validation_failed",
    "validation_skipped",
]


class ActionSelectorConfig(BaseModel):
    selector_id: str = "action_selector_v1"
    validate_actions: bool = True
    registry_path: str | None = "configs/script_registry.example.json"
    role_template_path: str | None = None
    require_validation_for_success: bool = True
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("selector_id")
    @classmethod
    def validate_selector_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("selector_id must be non-empty.")
        return value


class ActionSelectionResult(BaseModel):
    selector_id: str
    agent_id: str
    success: bool
    status: ActionSelectionStatus
    next_action: NextAction | None = None
    validation_result: ScriptValidationResult | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("selector_id", "agent_id")
    @classmethod
    def validate_non_empty_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("selector_id and agent_id must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_shape(self) -> ActionSelectionResult:
        if self.success and self.next_action is None:
            raise ValueError("next_action must be present when success=True.")
        if not self.success:
            if not self.error_type or not self.error_type.strip():
                raise ValueError("error_type must be present when success=False.")
            if not self.error_message or not self.error_message.strip():
                raise ValueError("error_message must be present when success=False.")
        if self.status == "validation_failed" and self.validation_result is None:
            raise ValueError("validation_result must be present for validation_failed status.")
        if self.status == "selected" and self.next_action is None:
            raise ValueError("next_action must be present for selected status.")
        return self


class ActionSelector:
    def __init__(
        self,
        llm_client: Any,
        config: ActionSelectorConfig | None = None,
        registry: ScriptRegistry | None = None,
        role_template: RoleTemplate | None = None,
    ) -> None:
        self.llm_client = llm_client
        self.config = config or ActionSelectorConfig()
        self.registry = registry
        self.role_template = role_template

        if self.config.validate_actions:
            if self.registry is None and self.config.registry_path is not None:
                self.registry = load_script_registry(self.config.registry_path)
            if self.role_template is None and self.config.role_template_path is not None:
                self.role_template = load_role_template(self.config.role_template_path)

    def _to_next_action(self, model_output: Any) -> NextAction:
        if isinstance(model_output, NextAction):
            return model_output
        if isinstance(model_output, dict):
            return NextAction.model_validate(model_output)
        raise TypeError("Model output is not NextAction or dict.")

    @staticmethod
    def _issue_code_summary(validation_result: ScriptValidationResult) -> str:
        issue_codes = sorted({issue.code for issue in validation_result.issues})
        if not issue_codes:
            return "validation failed with unknown issue codes"
        return "validation failed: " + ", ".join(issue_codes)

    def select_action(self, agent_state: AgentState) -> ActionSelectionResult:
        agent_id = agent_state.agent_id
        try:
            raw_output = self.llm_client.generate_next_action(agent_state.to_prompt_context())
            next_action = self._to_next_action(raw_output)
        except Exception as exc:
            return ActionSelectionResult(
                selector_id=self.config.selector_id,
                agent_id=agent_id,
                success=False,
                status="selection_failed",
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                metadata={},
            )

        if not self.config.validate_actions:
            return ActionSelectionResult(
                selector_id=self.config.selector_id,
                agent_id=agent_id,
                success=True,
                status="validation_skipped",
                next_action=next_action,
                metadata={},
            )

        if self.registry is None:
            validation_result = ScriptValidationResult(
                accepted=False,
                action=next_action.action,
                issues=[
                    ScriptValidationIssue(
                        code="registry_missing",
                        message="Script registry was not available for action validation.",
                        layer="script_registry",
                    )
                ],
                metadata={},
            )
            return ActionSelectionResult(
                selector_id=self.config.selector_id,
                agent_id=agent_id,
                success=False,
                status="validation_failed",
                next_action=next_action,
                validation_result=validation_result,
                error_type="registry_missing",
                error_message="ScriptRegistry is required for validation but was not available.",
                metadata={},
            )

        validation_result = validate_next_action_against_registry(
            next_action, self.registry, self.role_template
        )
        if validation_result.accepted:
            return ActionSelectionResult(
                selector_id=self.config.selector_id,
                agent_id=agent_id,
                success=True,
                status="selected",
                next_action=next_action,
                validation_result=validation_result,
                metadata={},
            )

        if self.config.require_validation_for_success:
            return ActionSelectionResult(
                selector_id=self.config.selector_id,
                agent_id=agent_id,
                success=False,
                status="validation_failed",
                next_action=next_action,
                validation_result=validation_result,
                error_type="validation_failed",
                error_message=self._issue_code_summary(validation_result),
                metadata={},
            )

        return ActionSelectionResult(
            selector_id=self.config.selector_id,
            agent_id=agent_id,
            success=True,
            status="selected",
            next_action=next_action,
            validation_result=validation_result,
            metadata={
                "validation_warning": self._issue_code_summary(validation_result),
                "validation_accepted": False,
            },
        )


def load_action_selector_config(path: str | Path) -> ActionSelectorConfig:
    path_obj = Path(path)
    payload = json.loads(path_obj.read_text(encoding="utf-8"))
    return ActionSelectorConfig.model_validate(payload)
