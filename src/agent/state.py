from __future__ import annotations

import json
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator


class AgentRole(BaseModel):
    name: str
    description: str
    constraints: list[str] = Field(default_factory=list)

    @field_validator("name", "description")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be empty.")
        return value


class AgentObjective(BaseModel):
    primary: str
    success_criteria: list[str] = Field(default_factory=list)

    @field_validator("primary")
    @classmethod
    def validate_primary_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Primary objective must not be empty.")
        return value


class AgentEnvironment(BaseModel):
    os: str | None = None
    project_root: str | None = None
    runtime: str | None = None
    network_allowed: bool = False
    notes: list[str] = Field(default_factory=list)


class AgentResources(BaseModel):
    files: list[str] = Field(default_factory=list)
    directories: list[str] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class AgentConstraints(BaseModel):
    no_internet: bool = True
    no_model_download: bool = True
    no_full_agent_loop: bool = False
    allowed_file_roots: list[str] = Field(default_factory=list)
    forbidden_file_roots: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class ActionSpec(BaseModel):
    name: str
    description: str
    parameters_schema: dict[str, Any] = Field(default_factory=dict)
    safety_notes: list[str] = Field(default_factory=list)

    @field_validator("name", "description")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Value must not be empty.")
        return value


class ActionHistoryEntry(BaseModel):
    step: int
    action: str
    parameters: dict[str, Any] = Field(default_factory=dict)
    status: Literal["success", "failure", "skipped", "unknown"] = "unknown"
    summary: str | None = None
    error: str | None = None

    @field_validator("step")
    @classmethod
    def validate_step(cls, value: int) -> int:
        if value < 1:
            raise ValueError("Step must be >= 1.")
        return value

    @field_validator("action")
    @classmethod
    def validate_action_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Action must not be empty.")
        return value


class AgentState(BaseModel):
    agent_id: str
    role: AgentRole
    objective: AgentObjective
    environment: AgentEnvironment = Field(default_factory=AgentEnvironment)
    resources: AgentResources = Field(default_factory=AgentResources)
    constraints: AgentConstraints = Field(default_factory=AgentConstraints)
    available_actions: list[ActionSpec] = Field(default_factory=list)
    history: list[ActionHistoryEntry] = Field(default_factory=list)
    current_step: int = 1
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("agent_id")
    @classmethod
    def validate_agent_id_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("agent_id must not be empty.")
        return value

    @field_validator("current_step")
    @classmethod
    def validate_current_step_min(cls, value: int) -> int:
        if value < 1:
            raise ValueError("current_step must be >= 1.")
        return value

    @model_validator(mode="after")
    def validate_structure(self) -> AgentState:
        action_names = [action.name for action in self.available_actions]
        if len(action_names) != len(set(action_names)):
            raise ValueError("available_actions contains duplicate action names.")

        history_steps = [entry.step for entry in self.history]
        if len(history_steps) != len(set(history_steps)):
            raise ValueError("history contains duplicate step values.")

        if self.history:
            max_step = max(history_steps)
            if self.current_step < max_step + 1:
                raise ValueError(
                    "current_step must be >= max(history.step) + 1 when history exists."
                )
        elif self.current_step != 1:
            raise ValueError("current_step must be 1 when history is empty.")
        return self

    def to_prompt_context(self) -> dict[str, Any]:
        return {
            "agent_id": self.agent_id,
            "role": self.role.model_dump(),
            "objective": self.objective.model_dump(),
            "environment": self.environment.model_dump(),
            "resources": self.resources.model_dump(),
            "constraints": self.constraints.model_dump(),
            "available_actions": [action.model_dump() for action in self.available_actions],
            "history": [entry.model_dump() for entry in self.history],
            "current_step": self.current_step,
            "metadata": dict(self.metadata),
        }

    def available_action_names(self) -> set[str]:
        return {action.name for action in self.available_actions}

    def has_action(self, name: str) -> bool:
        return name in self.available_action_names()


def load_agent_state(path: str | Path) -> AgentState:
    path_obj = Path(path)
    raw_text = path_obj.read_text(encoding="utf-8")
    payload = json.loads(raw_text)
    return AgentState.model_validate(payload)
