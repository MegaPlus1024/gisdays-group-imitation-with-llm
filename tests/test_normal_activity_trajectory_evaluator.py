from __future__ import annotations

from pathlib import Path

from src.agent.activity_evaluator import (
    ActivityEvaluationConfig,
    ActivityTrajectoryEvaluator,
    ActivityTrajectoryStep,
    action_family,
    action_fingerprint,
    count_repeated_actions,
    count_repeated_same_parameters,
    find_expected_sequence_matches,
    load_activity_evaluation_config,
    trajectory_steps_from_next_actions,
)
from src.agent.activity_profile import load_activity_profile
from src.agent.schemas import NextAction


def _steps(items):
    out = []
    for i, item in enumerate(items, start=1):
        out.append(ActivityTrajectoryStep(step_index=i, **item))
    return out


def test_config_defaults_valid() -> None:
    cfg = ActivityEvaluationConfig()
    assert cfg.evaluator_id == "normal_activity_trajectory_evaluator_v1"


def test_load_activity_evaluation_config() -> None:
    cfg = load_activity_evaluation_config("configs/activity_evaluator.example.json")
    assert cfg.normal_score_threshold == 0.8


def test_action_family_file() -> None:
    assert action_family("read_file") == "file"


def test_action_family_browser() -> None:
    assert action_family("browser_open_url") == "browser"


def test_action_family_office() -> None:
    assert action_family("office_create_document_stub") == "office"


def test_action_family_shell() -> None:
    assert action_family("run_shell_command") == "shell"


def test_action_fingerprint_deterministic() -> None:
    a = action_fingerprint("read_file", {"b": 2, "a": 1})
    b = action_fingerprint("read_file", {"a": 1, "b": 2})
    assert a == b


def test_count_repeated_actions() -> None:
    steps = _steps(
        [
            {"action": "read_file"},
            {"action": "create_file"},
            {"action": "read_file"},
            {"action": "read_file"},
        ]
    )
    assert count_repeated_actions(steps) == 2


def test_count_repeated_same_parameters() -> None:
    steps = _steps(
        [
            {"action": "read_file", "parameters": {"path": "a"}},
            {"action": "read_file", "parameters": {"path": "a"}},
            {"action": "read_file", "parameters": {"path": "b"}},
            {"action": "read_file", "parameters": {"path": "a"}},
        ]
    )
    assert count_repeated_same_parameters(steps) == 2


def test_find_expected_sequence_matches_ordered_subsequence() -> None:
    profile = load_activity_profile("configs/activity_profiles/developer.json")
    steps = _steps(
        [
            {"action": "read_file"},
            {"action": "list_directory"},
            {"action": "create_file"},
            {"action": "run_shell_command"},
        ]
    )
    matches = find_expected_sequence_matches(steps, profile)
    assert "inspect_update_test" in matches


def test_trajectory_steps_from_next_actions() -> None:
    actions = [
        NextAction(action="read_file", parameters={"path": "a"}, reason="r1", expected_result="e1"),
        NextAction(action="create_file", parameters={"path": "b", "content": "x"}, reason="r2", expected_result="e2"),
    ]
    steps = trajectory_steps_from_next_actions(actions)
    assert len(steps) == 2
    assert steps[0].step_index == 1
    assert steps[1].action == "create_file"


def test_evaluate_insufficient_data() -> None:
    profile = load_activity_profile("configs/activity_profiles/office_worker.json")
    result = ActivityTrajectoryEvaluator().evaluate([], profile)
    assert result.verdict == "insufficient_data"
    assert result.score == 0


def test_evaluate_normal_office_worker_sequence() -> None:
    profile = load_activity_profile("configs/activity_profiles/office_worker.json")
    steps = _steps(
        [
            {"action": "read_file", "reason": "review previous note"},
            {"action": "office_create_document_stub"},
            {"action": "append_file", "used_history": True},
        ]
    )
    result = ActivityTrajectoryEvaluator().evaluate(steps, profile)
    assert result.score >= 0.7
    assert result.verdict in {"normal", "suspicious"}


def test_evaluate_flags_forbidden_for_office_worker_shell() -> None:
    profile = load_activity_profile("configs/activity_profiles/office_worker.json")
    steps = _steps([{"action": "run_shell_command", "parameters": {"command": "python -m pytest -q"}}])
    result = ActivityTrajectoryEvaluator().evaluate(steps, profile)
    assert "forbidden_for_normality_action" in result.metrics.flags


def test_evaluate_developer_shell_typical() -> None:
    profile = load_activity_profile("configs/activity_profiles/developer.json")
    steps = _steps([{"action": "run_shell_command", "parameters": {"command": "python -m pytest -q"}}])
    result = ActivityTrajectoryEvaluator().evaluate(steps, profile)
    assert result.metrics.typical_action_count == 1


def test_evaluate_penalizes_repeated_same_parameters() -> None:
    profile = load_activity_profile("configs/activity_profiles/student_researcher.json")
    steps = _steps(
        [
            {"action": "read_file", "parameters": {"path": "docs/a.md"}},
            {"action": "read_file", "parameters": {"path": "docs/a.md"}},
            {"action": "read_file", "parameters": {"path": "docs/a.md"}},
        ]
    )
    result = ActivityTrajectoryEvaluator().evaluate(steps, profile)
    assert result.metrics.repeated_same_parameters_count > 0
    assert "repeated_same_parameters" in result.metrics.flags


def test_evaluate_penalizes_low_diversity() -> None:
    profile = load_activity_profile("configs/activity_profiles/developer.json")
    steps = _steps([{"action": "read_file"}, {"action": "read_file"}, {"action": "read_file"}])
    result = ActivityTrajectoryEvaluator().evaluate(steps, profile)
    assert result.metrics.diversity_score < 0.5
    assert "low_diversity" in result.metrics.flags


def test_evaluate_rewards_expected_sequence_match() -> None:
    profile = load_activity_profile("configs/activity_profiles/office_worker.json")
    steps = _steps(
        [
            {"action": "read_file"},
            {"action": "office_create_document_stub"},
            {"action": "append_file"},
        ]
    )
    result = ActivityTrajectoryEvaluator().evaluate(steps, profile)
    assert result.metrics.expected_sequence_matches >= 1


def test_evaluate_detects_history_usage_boolean() -> None:
    profile = load_activity_profile("configs/activity_profiles/student_researcher.json")
    steps = _steps(
        [
            {"action": "read_file"},
            {"action": "create_file", "used_history": True},
        ]
    )
    result = ActivityTrajectoryEvaluator().evaluate(steps, profile)
    assert result.metrics.history_usage_count >= 1


def test_evaluate_detects_history_usage_reason_text() -> None:
    profile = load_activity_profile("configs/activity_profiles/student_researcher.json")
    steps = _steps(
        [
            {"action": "read_file"},
            {"action": "append_file", "reason": "Based on previous step findings."},
        ]
    )
    result = ActivityTrajectoryEvaluator().evaluate(steps, profile)
    assert result.metrics.history_usage_count >= 1


def test_evaluate_penalizes_failed_steps() -> None:
    profile = load_activity_profile("configs/activity_profiles/developer.json")
    steps = _steps(
        [
            {"action": "read_file", "success": True},
            {"action": "create_file", "success": False},
        ]
    )
    result = ActivityTrajectoryEvaluator().evaluate(steps, profile)
    assert "failed_steps_present" in result.metrics.flags
    assert result.metrics.failed_steps == 1


def test_evaluate_does_not_mutate_input_steps() -> None:
    profile = load_activity_profile("configs/activity_profiles/developer.json")
    steps = _steps([{"action": "read_file", "parameters": {"path": "a"}}])
    before = [s.model_dump() for s in steps]
    _ = ActivityTrajectoryEvaluator().evaluate(steps, profile)
    after = [s.model_dump() for s in steps]
    assert before == after


def test_result_score_between_zero_and_one() -> None:
    profile = load_activity_profile("configs/activity_profiles/developer.json")
    steps = _steps([{"action": "read_file"}])
    result = ActivityTrajectoryEvaluator().evaluate(steps, profile)
    assert 0.0 <= result.score <= 1.0


def test_doc_exists_mentions_behavioral_normality_and_curator_spec() -> None:
    path = Path("docs/ai/normal_activity_trajectory_evaluator_v1.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8").lower()
    assert "behavioral normality" in text
    assert "curator specification" in text or "original curator specification" in text
