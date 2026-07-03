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
        if "\n" in value or "\r" in value:
            raise ValueError("Plan text fields must be single-line strings.")
        return value

    @field_validator("goal", "success_criteria")
    @classmethod
    def validate_short_task_text(cls, value: str) -> str:
        if len(value) > 120:
            raise ValueError("goal and success_criteria must be <= 120 characters.")
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

    @field_validator("allowed_action_focus")
    @classmethod
    def validate_short_action_focus(cls, value: list[str]) -> list[str]:
        if len(value) > 3:
            raise ValueError("allowed_action_focus must contain at most 3 action names.")
        return value


class OrchestratorPlanPayload(BaseModel):
    tasks: list[OrchestratorPlanTaskPayload]
    coordination_notes: str
    expected_group_outcome: str

    @field_validator("tasks")
    @classmethod
    def validate_tasks(cls, value: list[OrchestratorPlanTaskPayload]) -> list[OrchestratorPlanTaskPayload]:
        if not value:
            raise ValueError("tasks must contain at least one task.")
        if len(value) > 2:
            raise ValueError("tasks must contain at most 2 tasks for the MVP local proof.")
        task_ids = [task.task_id for task in value]
        if len(task_ids) != len(set(task_ids)):
            raise ValueError("task_id values must be unique.")
        return value

    @field_validator("coordination_notes", "expected_group_outcome")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("coordination_notes and expected_group_outcome must be non-empty.")
        if "\n" in value or "\r" in value:
            raise ValueError("Plan text fields must be single-line strings.")
        if len(value) > 160:
            raise ValueError("coordination_notes and expected_group_outcome must be <= 160 characters.")
        return value


def build_orchestrator_messages(
    *,
    scenario_id: str,
    agents: list[dict[str, Any]],
    max_group_steps: int,
) -> list[dict[str, str]]:
    compact_agents = _compact_agents(agents)
    example = {
        "tasks": [
            {
                "task_id": "t1",
                "agent_id": "office_agent",
                "goal": "Review available project notes and summarize next action.",
                "allowed_action_focus": ["read_file", "list_directory"],
                "success_criteria": "A safe file or directory action is selected.",
            },
            {
                "task_id": "t2",
                "agent_id": "developer_agent",
                "goal": "Inspect safe project documentation for maintenance context.",
                "allowed_action_focus": ["read_file", "list_directory"],
                "success_criteria": "A safe project documentation path is inspected.",
            },
        ],
        "coordination_notes": "Agents should avoid external network and unsafe writes.",
        "expected_group_outcome": "Both agents perform one safe role-compatible action.",
    }
    return [
        {
            "role": "system",
            "content": (
                "Return only one compact JSON object for a local two-agent plan. "
                "No Markdown, no prose outside JSON, no multiline strings."
            ),
        },
        {
            "role": "user",
            "content": (
                "Create max 2 tasks for known agents only.\n"
                "Limits: goal<=120 chars; success_criteria<=120; coordination_notes<=160; "
                "expected_group_outcome<=160; allowed_action_focus<=3 names.\n"
                "Use only allowed actions. Do not request internet, downloads, external network, "
                "real browser automation, or unsafe writes.\n"
                f"scenario_id: {scenario_id}\n"
                f"max_group_steps: {min(max_group_steps, 2)}\n"
                "agents:\n"
                f"{json.dumps(compact_agents, ensure_ascii=False, separators=(',', ':'))}\n"
                "Output JSON shape example:\n"
                f"{json.dumps(example, ensure_ascii=False, separators=(',', ':'))}"
            ),
        },
    ]


def build_orchestrator_repair_messages(
    *,
    error_message: str,
    previous_raw_output: str,
    agents: list[dict[str, Any]],
    max_group_steps: int,
) -> list[dict[str, str]]:
    compact_agents = _compact_agents(agents)
    clipped_previous = previous_raw_output[:3000]
    return [
        {
            "role": "system",
            "content": (
                "Fix the previous orchestrator output. Return only one valid compact JSON object. "
                "No Markdown, no explanation, no multiline strings."
            ),
        },
        {
            "role": "user",
            "content": (
                f"Error: {error_message[:500]}\n"
                f"Previous output: {clipped_previous}\n"
                f"max_group_steps: {min(max_group_steps, 2)}\n"
                "Known agents and allowed actions:\n"
                f"{json.dumps(compact_agents, ensure_ascii=False, separators=(',', ':'))}\n"
                "Return JSON with keys: tasks, coordination_notes, expected_group_outcome. "
                "Use max 2 tasks, known agent_id values only, short single-line strings, "
                "and allowed_action_focus with max 3 allowed action names."
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


def _compact_agents(agents: list[dict[str, Any]]) -> list[dict[str, Any]]:
    compact: list[dict[str, Any]] = []
    for agent in agents[:2]:
        allowed_actions = agent.get("allowed_action_names") or agent.get("allowed_action_focus") or []
        compact.append(
            {
                "agent_id": agent.get("agent_id"),
                "goal": str(agent.get("assigned_goal") or agent.get("goal") or "")[:120],
                "allowed_actions": list(allowed_actions)[:6],
            }
        )
    return compact
