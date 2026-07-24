from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.activity_profile import load_activity_profile
from src.agent.autonomous_stop_criteria import (
    AutonomousSessionStepSummary,
    AutonomousSessionSummary,
    AutonomousStopCriteriaConfig,
    AutonomousStopCriteriaEvaluator,
    AutonomousStopDecision,
    load_autonomous_stop_criteria_config,
    make_action_fingerprint,
    step_from_next_action,
)
from src.agent.schemas import NextAction


def _step(
    i: int,
    success: bool,
    action: str | None = "read_file",
    parameters: dict | None = None,
    status: str | None = None,
    error_type: str | None = None,
    issue_codes: list[str] | None = None,
    recovery_action: str | None = None,
    progress_signal: bool | None = None,
) -> AutonomousSessionStepSummary:
    return AutonomousSessionStepSummary(
        step_index=i,
        success=success,
        action=action,
        parameters=parameters or {},
        status=status,
        error_type=error_type,
        issue_codes=issue_codes or [],
        recovery_action=recovery_action,
        progress_signal=progress_signal,
    )


def _summary(steps: list[AutonomousSessionStepSummary] | None = None) -> AutonomousSessionSummary:
    return AutonomousSessionSummary(
        session_id="s1",
        agent_id="a1",
        steps=steps or [],
    )


def test_config_defaults_valid() -> None:
    cfg = AutonomousStopCriteriaConfig()
    assert cfg.criteria_id == "autonomous_stop_criteria_v1"
    assert cfg.max_steps == 10


def test_config_rejects_max_steps_lt_1() -> None:
    with pytest.raises(ValueError):
        AutonomousStopCriteriaConfig(max_steps=0)


def test_load_config() -> None:
    cfg = load_autonomous_stop_criteria_config("configs/autonomous_stop_criteria.example.json")
    assert cfg.max_total_failures == 3
    assert cfg.max_atypical_action_count == 2


def test_summary_count_methods() -> None:
    summary = _summary(
        [
            _step(1, True, "read_file"),
            _step(2, False, "create_file"),
            _step(3, False, "append_file"),
        ]
    )
    assert summary.step_count() == 3
    assert summary.failure_count() == 2
    assert summary.consecutive_failure_count() == 2


def test_selected_actions_returns_actions() -> None:
    summary = _summary([_step(1, True, "read_file"), _step(2, True, "create_file")])
    assert summary.selected_actions() == ["read_file", "create_file"]


def test_summary_action_count_method() -> None:
    summary = _summary([_step(1, True, "read_file"), _step(2, True, "read_file")])
    assert summary.action_count("read_file") == 2


def test_action_fingerprint_deterministic() -> None:
    a = make_action_fingerprint("x", {"b": 2, "a": 1})
    b = make_action_fingerprint("x", {"a": 1, "b": 2})
    assert a == b


def test_evaluator_continue_on_empty_summary() -> None:
    decision = AutonomousStopCriteriaEvaluator().evaluate(_summary())
    assert decision.should_stop is False
    assert decision.action == "continue_session"


def test_evaluator_stop_success() -> None:
    s = _summary([_step(1, True)])
    s.goal_satisfied = True
    decision = AutonomousStopCriteriaEvaluator().evaluate(s)
    assert decision.action == "stop_success"


def test_evaluator_stop_mark_for_review() -> None:
    s = _summary([_step(1, True)])
    s.marked_for_review = True
    decision = AutonomousStopCriteriaEvaluator().evaluate(s)
    assert decision.action == "stop_mark_for_review"


def test_evaluator_stop_recovery_abort_run() -> None:
    s = _summary([_step(1, False, recovery_action="abort_run")])
    decision = AutonomousStopCriteriaEvaluator().evaluate(s)
    assert decision.action == "stop_recovery_abort_run"


def test_evaluator_stop_recovery_skip_agent() -> None:
    s = _summary([_step(1, False, recovery_action="skip_agent")])
    decision = AutonomousStopCriteriaEvaluator().evaluate(s)
    assert decision.action == "stop_recovery_skip_agent"


def test_evaluator_stop_unsafe_from_issue_code() -> None:
    s = _summary([_step(1, False, issue_codes=["unsafe_action"])])
    decision = AutonomousStopCriteriaEvaluator().evaluate(s)
    assert decision.action == "stop_unsafe_action"


def test_evaluator_stop_unsafe_from_error_type() -> None:
    s = _summary([_step(1, False, error_type="unsafe_command")])
    decision = AutonomousStopCriteriaEvaluator().evaluate(s)
    assert decision.action == "stop_unsafe_action"


def test_evaluator_stop_validation_failure() -> None:
    s = _summary([_step(1, False, status="validation_failed")])
    decision = AutonomousStopCriteriaEvaluator().evaluate(s)
    assert decision.action == "stop_validation_failure"


def test_evaluator_stop_max_steps() -> None:
    cfg = AutonomousStopCriteriaConfig(max_steps=2)
    s = _summary([_step(1, True), _step(2, True)])
    decision = AutonomousStopCriteriaEvaluator(cfg).evaluate(s)
    assert decision.action == "stop_max_steps"


def test_evaluator_stop_consecutive_failures() -> None:
    cfg = AutonomousStopCriteriaConfig(max_consecutive_failures=2, max_steps=10)
    s = _summary([_step(1, True), _step(2, False), _step(3, False)])
    decision = AutonomousStopCriteriaEvaluator(cfg).evaluate(s)
    assert decision.action == "stop_consecutive_failures"


def test_evaluator_stop_total_failures() -> None:
    cfg = AutonomousStopCriteriaConfig(max_total_failures=2, max_consecutive_failures=10, max_steps=10)
    s = _summary([_step(1, False), _step(2, True), _step(3, False)])
    decision = AutonomousStopCriteriaEvaluator(cfg).evaluate(s)
    assert decision.action == "stop_total_failures"


def test_evaluator_stop_repeated_action() -> None:
    cfg = AutonomousStopCriteriaConfig(
        max_repeated_action_count=2,
        max_steps=10,
        max_consecutive_failures=10,
        max_total_failures=10,
    )
    s = _summary(
        [
            _step(1, True, "read_file", {"path": "docs/a.md"}),
            _step(2, True, "read_file", {"path": "docs/a.md"}),
            _step(3, True, "read_file", {"path": "docs/a.md"}),
        ]
    )
    decision = AutonomousStopCriteriaEvaluator(cfg).evaluate(s)
    assert decision.action == "stop_repeated_action"


def test_evaluator_not_stop_for_same_action_different_parameters() -> None:
    cfg = AutonomousStopCriteriaConfig(
        max_repeated_action_count=2,
        max_steps=10,
        max_consecutive_failures=10,
        max_total_failures=10,
    )
    s = _summary(
        [
            _step(1, True, "read_file", {"path": "docs/a.md"}),
            _step(2, True, "read_file", {"path": "docs/b.md"}),
            _step(3, True, "read_file", {"path": "docs/c.md"}),
        ]
    )
    decision = AutonomousStopCriteriaEvaluator(cfg).evaluate(s)
    assert decision.action == "continue_session"


def test_evaluator_stop_no_progress() -> None:
    cfg = AutonomousStopCriteriaConfig(
        require_progress_signal=True,
        max_steps=10,
        max_consecutive_failures=10,
        max_total_failures=10,
    )
    s = _summary([_step(1, True, progress_signal=False)])
    decision = AutonomousStopCriteriaEvaluator(cfg).evaluate(s)
    assert decision.action == "stop_no_progress"


def test_evaluator_with_office_profile_stops_for_forbidden_for_normality() -> None:
    profile = load_activity_profile("configs/activity_profiles/office_worker.json")
    s = _summary([_step(1, True, action="run_shell_command", parameters={"command": "python -m pytest -q"})])
    decision = AutonomousStopCriteriaEvaluator(activity_profile=profile).evaluate(s)
    assert decision.action == "stop_forbidden_for_normality"


def test_evaluator_with_office_profile_stops_for_excessive_atypical_actions() -> None:
    profile = load_activity_profile("configs/activity_profiles/office_worker.json")
    cfg = AutonomousStopCriteriaConfig(
        max_atypical_action_count=2,
        max_steps=10,
        max_consecutive_failures=10,
        max_total_failures=10,
        stop_on_forbidden_for_normality=False,
    )
    s = _summary(
        [
            _step(1, True, action="browser_open_url", parameters={"url": "http://localhost:8080"}),
            _step(2, True, action="browser_open_url", parameters={"url": "http://localhost:8080/docs"}),
            _step(3, True, action="browser_open_url", parameters={"url": "http://localhost:8080/help"}),
        ]
    )
    decision = AutonomousStopCriteriaEvaluator(cfg, activity_profile=profile).evaluate(s)
    assert decision.action == "stop_excessive_atypical_actions"


def test_evaluator_with_developer_profile_does_not_stop_shell_as_forbidden() -> None:
    profile = load_activity_profile("configs/activity_profiles/developer.json")
    cfg = AutonomousStopCriteriaConfig(
        max_steps=10,
        max_consecutive_failures=10,
        max_total_failures=10,
        max_repeated_action_count=10,
        max_atypical_action_count=10,
    )
    s = _summary([_step(1, True, action="run_shell_command", parameters={"command": "python -m pytest -q"})])
    decision = AutonomousStopCriteriaEvaluator(cfg, activity_profile=profile).evaluate(s)
    assert decision.action == "continue_session"


def test_session_atypical_and_forbidden_count_methods() -> None:
    office_profile = load_activity_profile("configs/activity_profiles/office_worker.json")
    s = _summary(
        [
            _step(1, True, action="browser_open_url", parameters={"url": "http://localhost:8080"}),
            _step(2, True, action="run_shell_command", parameters={"command": "python -m pytest -q"}),
        ]
    )
    assert s.atypical_action_count(office_profile) == 1
    assert s.forbidden_for_normality_count(office_profile) == 1


def test_step_from_next_action_builds_summary() -> None:
    action = NextAction(
        action_name="read_file",
        parameters={"path": "docs/x.md"},
    )
    step = step_from_next_action(1, action)
    assert step.action == "read_file"
    assert step.parameters["path"] == "docs/x.md"


def test_evaluate_does_not_mutate_summary() -> None:
    s = _summary([_step(1, True, "read_file", {"path": "docs/x.md"})])
    before = s.model_dump()
    _ = AutonomousStopCriteriaEvaluator().evaluate(s)
    assert s.model_dump() == before


def test_decision_continue_shape_validation() -> None:
    with pytest.raises(ValueError):
        AutonomousStopDecision(
            criteria_id="x",
            should_stop=False,
            action="stop_success",
            reason_category="success",
            reason="bad",
        )


def test_docs_mention_profile_and_curator_specification() -> None:
    text = Path("docs/ai/autonomous_session_stop_criteria_v1.md").read_text(encoding="utf-8").lower()
    assert "normalactivityprofile" in text
    assert "curator specification" in text or "original curator specification" in text
