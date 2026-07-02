from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from pydantic import BaseModel, Field, field_validator, model_validator

from .state import AgentConstraints, AgentRole


class RoleResourceProfile(BaseModel):
    files: list[str] = Field(default_factory=list)
    directories: list[str] = Field(default_factory=list)
    endpoints: list[str] = Field(default_factory=list)
    tools: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


class RoleConstraintProfile(BaseModel):
    no_internet: bool = True
    no_model_download: bool = True
    no_action_execution: bool = False
    allowed_file_roots: list[str] = Field(default_factory=list)
    forbidden_file_roots: list[str] = Field(default_factory=list)
    allowed_action_names: list[str] = Field(default_factory=list)
    forbidden_action_names: list[str] = Field(default_factory=list)
    forbidden_behaviors: list[str] = Field(default_factory=list)
    safety_notes: list[str] = Field(default_factory=list)

    @model_validator(mode="after")
    def validate_constraints(self) -> RoleConstraintProfile:
        if len(self.allowed_action_names) != len(set(self.allowed_action_names)):
            raise ValueError("allowed_action_names must not contain duplicates.")
        if len(self.forbidden_action_names) != len(set(self.forbidden_action_names)):
            raise ValueError("forbidden_action_names must not contain duplicates.")

        overlap = set(self.allowed_action_names) & set(self.forbidden_action_names)
        if overlap:
            raise ValueError(
                f"Action names cannot be both allowed and forbidden: {sorted(overlap)}"
            )

        if len(self.allowed_file_roots) != len(set(self.allowed_file_roots)):
            raise ValueError("allowed_file_roots must not contain duplicates.")
        if len(self.forbidden_file_roots) != len(set(self.forbidden_file_roots)):
            raise ValueError("forbidden_file_roots must not contain duplicates.")
        return self


class RoleActivityScenario(BaseModel):
    name: str
    description: str
    examples: list[str] = Field(default_factory=list)
    non_examples: list[str] = Field(default_factory=list)

    @field_validator("name", "description")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("Scenario name and description must be non-empty.")
        return value


class RoleTemplate(BaseModel):
    role_id: str
    name: str
    description: str
    primary_goals: list[str] = Field(default_factory=list)
    success_criteria: list[str] = Field(default_factory=list)
    resources: RoleResourceProfile = Field(default_factory=RoleResourceProfile)
    constraints: RoleConstraintProfile = Field(default_factory=RoleConstraintProfile)
    allowed_activity_scenarios: list[RoleActivityScenario] = Field(default_factory=list)
    environment_assumptions: list[str] = Field(default_factory=list)
    prompt_notes: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("role_id", "name", "description")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("role_id, name, and description must be non-empty.")
        return value

    @model_validator(mode="after")
    def validate_role_template(self) -> RoleTemplate:
        if not self.primary_goals:
            raise ValueError("primary_goals must contain at least one item.")

        scenario_names = [s.name for s in self.allowed_activity_scenarios]
        if len(scenario_names) != len(set(scenario_names)):
            raise ValueError("allowed_activity_scenarios must not contain duplicate names.")
        return self

    def to_agent_role(self) -> AgentRole:
        constraint_lines = [
            f"no_internet={self.constraints.no_internet}",
            f"no_model_download={self.constraints.no_model_download}",
            f"no_action_execution={self.constraints.no_action_execution}",
            f"allowed_action_names={self.constraints.allowed_action_names}",
            f"forbidden_action_names={self.constraints.forbidden_action_names}",
            f"forbidden_behaviors={self.constraints.forbidden_behaviors}",
        ]
        return AgentRole(
            name=self.name,
            description=self.description,
            constraints=constraint_lines,
        )

    def to_agent_constraints(self) -> AgentConstraints:
        notes = list(self.constraints.safety_notes) + list(self.constraints.forbidden_behaviors)
        return AgentConstraints(
            no_internet=self.constraints.no_internet,
            no_model_download=self.constraints.no_model_download,
            no_full_agent_loop=self.constraints.no_action_execution,
            allowed_file_roots=list(self.constraints.allowed_file_roots),
            forbidden_file_roots=list(self.constraints.forbidden_file_roots),
            notes=notes,
        )

    def default_objective_primary(self) -> str:
        return self.primary_goals[0]

    def allowed_action_set(self) -> set[str]:
        return set(self.constraints.allowed_action_names)


def load_role_template(path: str | Path) -> RoleTemplate:
    path_obj = Path(path)
    payload = json.loads(path_obj.read_text(encoding="utf-8"))
    return RoleTemplate.model_validate(payload)


def role_template_to_agent_state_defaults(template: RoleTemplate) -> dict[str, Any]:
    return {
        "role": template.to_agent_role().model_dump(),
        "objective": {
            "primary": template.default_objective_primary(),
            "success_criteria": list(template.success_criteria),
        },
        "resources": template.resources.model_dump(),
        "constraints": template.to_agent_constraints().model_dump(),
        "metadata": {
            "role_template_id": template.role_id,
            "role_template_metadata": template.metadata,
        },
    }
