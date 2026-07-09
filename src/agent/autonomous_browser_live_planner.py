from __future__ import annotations

import json
from collections.abc import Mapping, Sequence
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_plan_validation import PLAN_SCHEMA_VERSION, validate_autonomous_browser_plan


LIVE_PLANNER_SCHEMA_VERSION = "autonomous_browser_live_planner_v1"
SCRIPTED_PLANNER_KIND = "scripted"
CAPTURED_PLAN_PLANNER_KIND = "captured_plan"
PLANNER_DONE_ACTION_NAME = "done"


@dataclass(frozen=True)
class AutonomousBrowserLivePlannerStep:
    step_id: str
    action_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    expected_text: str = ""
    expected_url: str | None = None
    done: bool = False
    metadata: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "step_id": self.step_id,
            "action_name": self.action_name,
            "parameters": dict(self.parameters),
            "expected_text": self.expected_text,
            "done": self.done,
            "metadata": dict(self.metadata),
        }
        if self.expected_url is not None:
            payload["expected_url"] = self.expected_url
        return payload


@dataclass
class ScriptedLivePlanner:
    scripted_steps: tuple[AutonomousBrowserLivePlannerStep, ...]
    planner_id: str = "scripted_live_planner"
    cursor: int = field(default=0, init=False, repr=False)

    def next_step(self, observation: Mapping[str, Any] | None = None) -> AutonomousBrowserLivePlannerStep | None:
        del observation
        if self.cursor >= len(self.scripted_steps):
            return None
        step = self.scripted_steps[self.cursor]
        self.cursor += 1
        return step

    def to_summary(self) -> dict[str, Any]:
        return {
            "kind": SCRIPTED_PLANNER_KIND,
            "planner_id": self.planner_id,
            "scripted_steps_total": len(self.scripted_steps),
            "remaining_steps": max(0, len(self.scripted_steps) - self.cursor),
        }


@dataclass
class CapturedPlanStepPlanner:
    plan_id: str | None
    captured_plan_path: str | None
    captured_steps: tuple[AutonomousBrowserLivePlannerStep, ...]
    planner_id: str = "captured_plan_step_planner"
    cursor: int = field(default=0, init=False, repr=False)

    @classmethod
    def from_plan(
        cls,
        plan_artifact: str | Path | Mapping[str, Any],
        *,
        captured_plan_path: str | None = None,
        planner_id: str = "captured_plan_step_planner",
    ) -> CapturedPlanStepPlanner:
        validation_result = validate_autonomous_browser_plan(plan_artifact)
        if str(validation_result.get("status")) != "accepted":
            raise ValueError(str(validation_result.get("error_code") or "browser_plan_validation_failed"))
        normalized_plan = validation_result.get("normalized_plan")
        if not isinstance(normalized_plan, Mapping):
            raise ValueError("normalized_plan_missing")
        actions = normalized_plan.get("actions")
        if not isinstance(actions, list):
            raise ValueError("normalized_actions_missing")
        steps: list[AutonomousBrowserLivePlannerStep] = []
        for action in actions:
            if not isinstance(action, Mapping):
                continue
            steps.append(
                AutonomousBrowserLivePlannerStep(
                    step_id=str(action.get("step_id", "")),
                    action_name=str(action.get("action_name", "")),
                    parameters=_copy_mapping(action.get("parameters", {})),
                    expected_text=str(action.get("expected_text", "")) if isinstance(action.get("expected_text"), str) else "",
                    expected_url=str(action.get("expected_url")) if isinstance(action.get("expected_url"), str) else None,
                    done=False,
                )
            )
        return cls(
            plan_id=str(validation_result.get("plan_id")) if validation_result.get("plan_id") else None,
            captured_plan_path=captured_plan_path,
            captured_steps=tuple(steps),
            planner_id=planner_id,
        )

    def next_step(self, observation: Mapping[str, Any] | None = None) -> AutonomousBrowserLivePlannerStep | None:
        del observation
        if self.cursor >= len(self.captured_steps):
            return None
        step = self.captured_steps[self.cursor]
        self.cursor += 1
        return step

    def to_summary(self) -> dict[str, Any]:
        return {
            "kind": CAPTURED_PLAN_PLANNER_KIND,
            "planner_id": self.planner_id,
            "plan_id": self.plan_id,
            "captured_plan_path": self.captured_plan_path,
            "captured_steps_total": len(self.captured_steps),
            "remaining_steps": max(0, len(self.captured_steps) - self.cursor),
        }


def load_live_planner_backend(config: Mapping[str, Any], *, repo_root: str | Path | None = None) -> ScriptedLivePlanner | CapturedPlanStepPlanner:
    backend_kind = str(config.get("kind", "")).strip().lower()
    planner_id = str(config.get("planner_id", "")).strip() or (
        "scripted_live_planner" if backend_kind == SCRIPTED_PLANNER_KIND else "captured_plan_step_planner"
    )
    if backend_kind == SCRIPTED_PLANNER_KIND:
        steps_value = config.get("scripted_steps", [])
        if not isinstance(steps_value, list):
            raise ValueError("scripted_steps must be a list.")
        steps = tuple(_step_from_mapping(item, index) for index, item in enumerate(steps_value))
        return ScriptedLivePlanner(steps, planner_id=planner_id)
    if backend_kind == CAPTURED_PLAN_PLANNER_KIND:
        captured_plan_path = _safe_relative_path(config.get("captured_plan_path"), "captured_plan_path")
        if captured_plan_path is None:
            raise ValueError("captured_plan_path must be a safe relative path.")
        repo = Path(repo_root) if repo_root is not None else Path(".")
        plan_path = repo / captured_plan_path
        return CapturedPlanStepPlanner.from_plan(plan_path, captured_plan_path=captured_plan_path, planner_id=planner_id)
    raise ValueError("planner_backend.kind must be scripted or captured_plan.")


def _step_from_mapping(item: Any, index: int) -> AutonomousBrowserLivePlannerStep:
    if not isinstance(item, Mapping):
        raise ValueError(f"scripted_steps[{index}] must be an object.")
    step_id = _required_text(item.get("step_id"), f"scripted_steps[{index}].step_id")
    action_name = _required_text(item.get("action_name"), f"scripted_steps[{index}].action_name")
    parameters = _copy_mapping(item.get("parameters", {}))
    expected_text = str(item.get("expected_text", "")) if isinstance(item.get("expected_text"), str) else ""
    expected_url = str(item.get("expected_url")) if isinstance(item.get("expected_url"), str) else None
    done = bool(item.get("done", False))
    metadata = _copy_mapping(item.get("metadata", {}))
    return AutonomousBrowserLivePlannerStep(
        step_id=step_id,
        action_name=action_name,
        parameters=parameters,
        expected_text=expected_text,
        expected_url=expected_url,
        done=done,
        metadata=metadata,
    )


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    return value.strip()


def _copy_mapping(value: Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return dict(value)

def _safe_relative_path(value: Any, label: str) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return None
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        return None
    return path.as_posix()
