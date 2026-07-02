from __future__ import annotations

from pathlib import Path

import pytest

from src.agent.activity_evaluator import ActivityTrajectoryEvaluator
from src.agent.behavioral_fixtures import (
    BEHAVIORAL_FIXTURE_ROOT,
    behavioral_fixture_path,
    evaluate_behavioral_fixture,
    load_behavioral_expectations,
    load_behavioral_trajectory_fixture,
    load_multi_agent_behavioral_fixture,
)


REQUIRED_TRAJECTORIES = [
    "office_worker_normal.json",
    "office_worker_shell_abnormal.json",
    "office_worker_repetitive_read.json",
    "office_worker_low_diversity.json",
    "developer_normal.json",
    "developer_repetitive_pytest.json",
    "student_researcher_normal.json",
    "student_researcher_incoherent.json",
    "history_aware_normal.json",
    "mixed_roles_multi_agent.json",
]


def test_fixture_root_exists() -> None:
    assert BEHAVIORAL_FIXTURE_ROOT.exists()


def test_fixture_readme_exists() -> None:
    assert (BEHAVIORAL_FIXTURE_ROOT / "README.md").exists()


def test_required_trajectory_files_exist() -> None:
    base = BEHAVIORAL_FIXTURE_ROOT / "trajectories"
    for name in REQUIRED_TRAJECTORIES:
        assert (base / name).exists(), name


def test_expected_results_exists() -> None:
    assert (BEHAVIORAL_FIXTURE_ROOT / "expected_results/behavioral_expectations.json").exists()


def test_load_single_role_fixtures() -> None:
    assert load_behavioral_trajectory_fixture("trajectories/office_worker_normal.json").trajectory_id == "office_worker_normal"
    assert load_behavioral_trajectory_fixture("trajectories/developer_normal.json").trajectory_id == "developer_normal"
    assert load_behavioral_trajectory_fixture("trajectories/student_researcher_normal.json").trajectory_id == "student_researcher_normal"


def test_load_multi_agent_fixture() -> None:
    fixture = load_multi_agent_behavioral_fixture("trajectories/mixed_roles_multi_agent.json")
    assert fixture.fixture_id == "mixed_roles_multi_agent"
    assert len(fixture.agent_trajectories) >= 2


def test_load_expectation_suite_unique_case_ids() -> None:
    suite = load_behavioral_expectations()
    case_ids = [item.case_id for item in suite.expectations]
    assert len(case_ids) == len(set(case_ids))


def test_expectations_reference_existing_files() -> None:
    suite = load_behavioral_expectations()
    for item in suite.expectations:
        assert Path(item.trajectory_path).exists()
        assert Path(item.activity_profile_path).exists()


def test_single_role_expectations_against_evaluator() -> None:
    suite = load_behavioral_expectations()
    evaluator = ActivityTrajectoryEvaluator()
    by_case = {}

    for item in suite.expectations:
        fixture = load_behavioral_trajectory_fixture(
            Path(item.trajectory_path).relative_to(BEHAVIORAL_FIXTURE_ROOT)
        )
        result = evaluate_behavioral_fixture(fixture, evaluator=evaluator)
        by_case[item.case_id] = result

        assert result.verdict in item.expected_verdicts
        assert item.min_score <= result.score <= item.max_score
        for flag in item.required_flags:
            assert flag in result.metrics.flags
        for flag in item.forbidden_flags:
            assert flag not in result.metrics.flags
        if item.min_history_usage_score is not None:
            assert result.metrics.history_usage_score >= item.min_history_usage_score

    for item in suite.expectations:
        if item.score_should_exceed_case:
            assert by_case[item.case_id].score > by_case[item.score_should_exceed_case].score


def test_office_shell_has_forbidden_for_normality_flag() -> None:
    fixture = load_behavioral_trajectory_fixture("trajectories/office_worker_shell_abnormal.json")
    result = evaluate_behavioral_fixture(fixture)
    assert "forbidden_for_normality_action" in result.metrics.flags


def test_developer_normal_shell_not_forbidden() -> None:
    fixture = load_behavioral_trajectory_fixture("trajectories/developer_normal.json")
    result = evaluate_behavioral_fixture(fixture)
    assert "forbidden_for_normality_action" not in result.metrics.flags


def test_developer_repetitive_pytest_flags() -> None:
    fixture = load_behavioral_trajectory_fixture("trajectories/developer_repetitive_pytest.json")
    result = evaluate_behavioral_fixture(fixture)
    assert "repeated_same_parameters" in result.metrics.flags
    assert "forbidden_for_normality_action" not in result.metrics.flags


def test_mixed_roles_multi_agent_evaluate_independently() -> None:
    fixture = load_multi_agent_behavioral_fixture("trajectories/mixed_roles_multi_agent.json")
    results = [evaluate_behavioral_fixture(agent_fixture) for agent_fixture in fixture.agent_trajectories]
    assert len(results) == len(fixture.agent_trajectories)
    office_result = next(r for r in results if r.role_id == "office_worker")
    developer_result = next(r for r in results if r.role_id == "developer")
    assert "forbidden_for_normality_action" in office_result.metrics.flags
    assert "forbidden_for_normality_action" not in developer_result.metrics.flags


def test_behavioral_fixture_path_rejects_traversal() -> None:
    with pytest.raises(ValueError):
        behavioral_fixture_path("../README.md")


def test_no_destructive_commands_in_fixtures() -> None:
    forbidden_tokens = ["rm -rf", "remove-item", "del /s", "format ", "shutdown "]
    traj_dir = BEHAVIORAL_FIXTURE_ROOT / "trajectories"
    for path in traj_dir.glob("*.json"):
        text = path.read_text(encoding="utf-8").lower()
        for token in forbidden_tokens:
            assert token not in text
