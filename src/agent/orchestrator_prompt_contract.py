from __future__ import annotations

import json
from typing import Any

from pydantic import BaseModel, Field, ValidationError, field_validator


class OrchestratorPlanJSONError(Exception):
    """Raised when orchestrator output cannot be parsed as a valid group plan."""


class OrchestratorPlanTaskPayload(BaseModel):
    task_id: str
    agent_id: str
    goal: str
    allowed_action_focus: list[str] = Field(default_factory=list)
    success_criteria: str
    role_hint: str | None = None
    dependencies: list[str] = Field(default_factory=list)

    @field_validator("task_id", "agent_id", "goal", "success_criteria")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("task_id, agent_id, goal, and success_criteria must be non-empty.")
        return value

    @field_validator("allowed_action_focus", "dependencies")
    @classmethod
    def validate_unique_text_list(cls, value: list[str]) -> list[str]:
        cleaned = [item.strip() for item in value]
        if any(not item for item in cleaned):
            raise ValueError("List values must be non-empty strings.")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("List values must be unique.")
        return cleaned


class OrchestratorPlanPayload(BaseModel):
    tasks: list[OrchestratorPlanTaskPayload]
    coordination_notes: str
    expected_group_outcome: str

    @field_validator("tasks")
    @classmethod
    def validate_tasks(cls, value: list[OrchestratorPlanTaskPayload]) -> list[OrchestratorPlanTaskPayload]:
        if not value:
            raise ValueError("tasks must contain at least one task.")
        task_ids = [task.task_id for task in value]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("task_id values must be unique.")
        return value

    @field_validator("coordination_notes", "expected_group_outcome")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("coordination_notes and expected_group_outcome must be non-empty.")
        return value


def build_orchestrator_messages(
    *,
    scenario_id: str,
    agents: list[dict[str, Any]],
    max_group_steps: int,
) -> list[dict[str, str]]:
    return [
        {
            "role": "system",
            "content": (
                "You are an orchestrator model for a controlled local multi-agent experiment. "
                "Create a concise JSON-only plan. Do not request internet, downloads, external network, "
                "real browser automation, or actions outside the provided agents and action focus."
            ),
        },
        {
            "role": "user",
            "content": json.dumps(
                {
                    "output_contract": {
                        "tasks": [
                            {
                                "task_id": "string",
                                "agent_id": "known agent id",
                                "goal": "string",
                                "allowed_action_focus": ["action_name"],
                                "success_criteria": "string",
                            }
                        ],
                        "coordination_notes": "string",
                        "expected_group_outcome": "string",
                    },
                    "scenario_id": scenario_id,
                    "max_group_steps": max_group_steps,
                    "agents": agents,
                    "rules": [
                        "Return exactly one JSON object.",
                        "No Markdown.",
                        "No prose outside JSON.",
                        "Use only known agent ids.",
                        "Do not require external network access.",
                    ],
                },
                ensure_ascii=False,
                indent=2,
            ),
        },
    ]


def parse_orchestrator_plan_text(
    text: str,
    *,
    known_agent_ids: set[str],
    allowed_action_names_by_agent: dict[str, set[str]] | None = None,
) -> OrchestratorPlanPayload:
    if not isinstance(text, str) or not text.strip():
        raise OrchestratorPlanJSONError("Orchestrator plan output must be non-empty text.")
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise OrchestratorPlanJSONError(f"Invalid orchestrator JSON output: {exc}") from exc
    if not isinstance(payload, dict):
        raise OrchestratorPlanJSONError("Orchestrator plan JSON must be an object.")
    try:
        plan = OrchestratorPlanPayload.model_validate(payload)
    except ValidationError as exc:
        raise OrchestratorPlanJSONError(f"Orchestrator plan failed schema validation: {exc}") from exc

    _validate_plan_references(plan, known_agent_ids, allowed_action_names_by_agent or {})
    _validate_no_external_network_requirement(plan)
    return plan


def _validate_plan_references(
    plan: OrchestratorPlanPayload,
    known_agent_ids: set[str],
    allowed_action_names_by_agent: dict[str, set[str]],
) -> None:
    for task in plan.tasks:
        if task.agent_id not in known_agent_ids:
            raise OrchestratorPlanJSONError(f"Unknown agent_id in orchestrator plan: {task.agent_id}")
        allowed_actions = allowed_action_names_by_agent.get(task.agent_id)
        if allowed_actions:
            unknown_actions = sorted(set(task.allowed_action_focus) - allowed_actions)
            if unknown_actions:
                raise OrchestratorPlanJSONError(
                    f"Task {task.task_id} references forbidden/unknown action focus for {task.agent_id}: {unknown_actions}"
                )
        unknown_dependencies = sorted(set(task.dependencies) - {item.task_id for item in plan.tasks})
        if unknown_dependencies:
            raise OrchestratorPlanJSONError(
                f"Task {task.task_id} references unknown dependencies: {unknown_dependencies}"
            )


def _validate_no_external_network_requirement(plan: OrchestratorPlanPayload) -> None:
    forbidden_phrases = [
        "use internet",
        "requires internet",
        "external network access",
        "download model",
        "download file",
        "web search",
        "real browser automation",
    ]
    haystack = " ".join(
        [
            plan.coordination_notes,
            plan.expected_group_outcome,
            *[task.goal for task in plan.tasks],
            *[task.success_criteria for task in plan.tasks],
        ]
    ).lower()
    for phrase in forbidden_phrases:
        if phrase in haystack and f"no {phrase}" not in haystack and f"not {phrase}" not in haystack:
            raise OrchestratorPlanJSONError(
                f"Orchestrator plan appears to require forbidden external capability: {phrase}"
            )
