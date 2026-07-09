from __future__ import annotations

from pathlib import Path

from src.agent.autonomous_browser_live_planner import (
    CAPTURED_PLAN_PLANNER_KIND,
    SCRIPTED_PLANNER_KIND,
    CapturedPlanStepPlanner,
    ScriptedLivePlanner,
    load_live_planner_backend,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
PLAN_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_plan.example.json"


def test_scripted_live_planner_returns_steps_and_done() -> None:
    backend = load_live_planner_backend(
        {
            "kind": SCRIPTED_PLANNER_KIND,
            "planner_id": "scripted_live_planner_test",
            "scripted_steps": [
                {"step_id": "open_home", "action_name": "browser_open_url", "parameters": {"url": "https://local.intranet/"}, "expected_text": "Office Intranet"},
                {"step_id": "done", "action_name": "done", "parameters": {}, "expected_text": "", "done": True},
            ],
        }
    )

    assert isinstance(backend, ScriptedLivePlanner)
    first = backend.next_step({"observation_id": "observation_0001"})
    second = backend.next_step({"observation_id": "observation_0002"})
    third = backend.next_step({"observation_id": "observation_0003"})

    assert first is not None and first.step_id == "open_home"
    assert second is not None and second.done is True
    assert third is None
    assert backend.to_summary()["kind"] == SCRIPTED_PLANNER_KIND
    assert backend.to_summary()["scripted_steps_total"] == 2


def test_captured_plan_step_planner_loads_from_valid_plan() -> None:
    backend = load_live_planner_backend(
        {
            "kind": CAPTURED_PLAN_PLANNER_KIND,
            "planner_id": "captured_plan_test",
            "captured_plan_path": "configs/autonomous_runtime/browser_plan.example.json",
        },
        repo_root=PROJECT_ROOT,
    )

    assert isinstance(backend, CapturedPlanStepPlanner)
    assert backend.plan_id == "browser_policy_research_plan_v1"
    first = backend.next_step({"observation_id": "observation_0001"})
    second = backend.next_step({"observation_id": "observation_0002"})
    third = backend.next_step({"observation_id": "observation_0003"})
    fourth = backend.next_step({"observation_id": "observation_0004"})

    assert first is not None and first.step_id == "open_home"
    assert second is not None and second.step_id == "open_policy"
    assert third is not None and third.step_id == "search_policy"
    assert fourth is None
    assert backend.to_summary()["kind"] == CAPTURED_PLAN_PLANNER_KIND
    assert backend.to_summary()["captured_steps_total"] == 3
