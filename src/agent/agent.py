from __future__ import annotations

from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .llm_client import LocalLLMClient, LocalLLMClientError
from .schemas import NextAction
from .state import AgentState


class AgentStepRequest(BaseModel):
    run_id: str
    agent_state: AgentState
    step_index: int
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("run_id")
    @classmethod
    def validate_run_id(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("run_id must be non-empty.")
        return value

    @field_validator("step_index")
    @classmethod
    def validate_step_index(cls, value: int) -> int:
        if value < 1:
            raise ValueError("step_index must be >= 1.")
        return value


class AgentStepResult(BaseModel):
    run_id: str
    agent_id: str
    step_index: int
    success: bool
    next_action: NextAction | None = None
    error_type: str | None = None
    error_message: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("run_id", "agent_id")
    @classmethod
    def validate_non_empty_ids(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("run_id and agent_id must be non-empty.")
        return value

    @field_validator("step_index")
    @classmethod
    def validate_step_index(cls, value: int) -> int:
        if value < 1:
            raise ValueError("step_index must be >= 1.")
        return value

    @model_validator(mode="after")
    def validate_success_error_shape(self) -> AgentStepResult:
        if self.success:
            if self.next_action is None:
                raise ValueError("next_action is required when success=True.")
        else:
            if not self.error_type or not self.error_type.strip():
                raise ValueError("error_type is required when success=False.")
            if not self.error_message or not self.error_message.strip():
                raise ValueError("error_message is required when success=False.")
        return self


class Agent:
    def __init__(self, llm_client: LocalLLMClient) -> None:
        self.llm_client = llm_client

    def decide_next_action(self, request: AgentStepRequest) -> AgentStepResult:
        state = request.agent_state
        try:
            next_action = self.llm_client.generate_next_action(state.to_prompt_context())
            return AgentStepResult(
                run_id=request.run_id,
                agent_id=state.agent_id,
                step_index=request.step_index,
                success=True,
                next_action=next_action,
                metadata=dict(request.metadata),
            )
        except LocalLLMClientError as exc:
            return AgentStepResult(
                run_id=request.run_id,
                agent_id=state.agent_id,
                step_index=request.step_index,
                success=False,
                error_type=exc.__class__.__name__,
                error_message=str(exc),
                metadata=dict(request.metadata),
            )
