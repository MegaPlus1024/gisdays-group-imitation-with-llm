from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.evaluation_scenarios import (
    EvaluationScenario,
    EvaluationScenarioAgentSpec,
    EvaluationScenarioExpectedBehavior,
    EvaluationScenarioStopPolicy,
    evaluation_scenario_summary,
    load_evaluation_scenario,
    load_evaluation_scenarios_from_dir,
    verify_evaluation_scenario_references,
)


def test_load_office_worker_scenario() -> None:
    s = load_evaluation_scenario("configs/evaluation_scenarios/office_worker_basic_session.json")
    assert s.scenario_id == "office_worker_basic_session_v1"


def test_load_developer_scenario() -> None:
    s = load_evaluation_scenario("configs/evaluation_scenarios/developer_project_maintenance.json")
    assert s.scenario_id == "developer_project_maintenance_v1"


def test_load_student_researcher_scenario() -> None:
    s = load_evaluation_scenario("configs/evaluation_scenarios/student_researcher_experiment_report.json")
    assert s.scenario_id == "student_researcher_experiment_report_v1"


def test_load_mixed_roles_scenario() -> None:
    s = load_evaluation_scenario("configs/evaluation_scenarios/mixed_roles_multi_agent_session.json")
    assert s.scenario_id == "mixed_roles_multi_agent_session_v1"


def test_load_all_scenarios_sorted() -> None:
    scenarios = load_evaluation_scenarios_from_dir("configs/evaluation_scenarios")
    ids = [s.scenario_id for s in scenarios]
    assert ids == sorted(ids)
    assert len(scenarios) == 4


def test_scenario_id_cannot_be_empty() -> None:
    with pytest.raises(ValueError):
        EvaluationScenario.model_validate(
            {
                "scenario_id": "",
                "name": "x",
                "description": "x",
                "mode": "single_agent",
                "agents": [
                    {
                        "agent_id": "a1",
                        "role_id": "r1",
                        "role_template_path": "x",
                        "activity_profile_path": "y",
                        "available_actions": ["read_file"],
                    }
                ],
                "metrics": ["normal_activity_score"],
            }
        )


def test_single_agent_rejects_multiple_agents() -> None:
    with pytest.raises(ValueError):
        EvaluationScenario.model_validate(
            {
                "scenario_id": "x",
                "name": "x",
                "description": "x",
                "mode": "single_agent",
                "agents": [
                    {
                        "agent_id": "a1",
                        "role_id": "r1",
                        "role_template_path": "x",
                        "activity_profile_path": "y",
                        "available_actions": ["read_file"],
                    },
                    {
                        "agent_id": "a2",
                        "role_id": "r2",
                        "role_template_path": "x",
                        "activity_profile_path": "y",
                        "available_actions": ["read_file"],
                    },
                ],
                "metrics": ["normal_activity_score"],
            }
        )


def test_multi_agent_rejects_one_agent() -> None:
    with pytest.raises(ValueError):
        EvaluationScenario.model_validate(
            {
                "scenario_id": "x",
                "name": "x",
                "description": "x",
                "mode": "multi_agent",
                "agents": [
                    {
                        "agent_id": "a1",
                        "role_id": "r1",
                        "role_template_path": "x",
                        "activity_profile_path": "y",
                        "available_actions": ["read_file"],
                    }
                ],
                "metrics": ["normal_activity_score"],
            }
        )


def test_duplicate_agent_id_rejected() -> None:
    with pytest.raises(ValueError):
        EvaluationScenario.model_validate(
            {
                "scenario_id": "x",
                "name": "x",
                "description": "x",
                "mode": "multi_agent",
                "agents": [
                    {
                        "agent_id": "a1",
                        "role_id": "r1",
                        "role_template_path": "x",
                        "activity_profile_path": "y",
                        "available_actions": ["read_file"],
                    },
                    {
                        "agent_id": "a1",
                        "role_id": "r2",
                        "role_template_path": "x",
                        "activity_profile_path": "y",
                        "available_actions": ["read_file"],
                    },
                ],
                "metrics": ["normal_activity_score"],
            }
        )


def test_duplicate_metrics_rejected() -> None:
    with pytest.raises(ValueError):
        EvaluationScenario.model_validate(
            {
                "scenario_id": "x",
                "name": "x",
                "description": "x",
                "mode": "single_agent",
                "agents": [
                    {
                        "agent_id": "a1",
                        "role_id": "r1",
                        "role_template_path": "x",
                        "activity_profile_path": "y",
                        "available_actions": ["read_file"],
                    }
                ],
                "metrics": ["normal_activity_score", "normal_activity_score"],
            }
        )


def test_duplicate_available_actions_rejected() -> None:
    with pytest.raises(ValueError):
        EvaluationScenarioAgentSpec(
            agent_id="a1",
            role_id="r1",
            role_template_path="x",
            activity_profile_path="y",
            available_actions=["read_file", "read_file"],
        )


def test_duplicate_expected_action_families_rejected() -> None:
    with pytest.raises(ValueError):
        EvaluationScenarioAgentSpec(
            agent_id="a1",
            role_id="r1",
            role_template_path="x",
            activity_profile_path="y",
            available_actions=["read_file"],
            expected_action_families=["file", "file"],
        )


def test_stop_policy_rejects_bad_max_steps() -> None:
    with pytest.raises(ValueError):
        EvaluationScenarioStopPolicy(max_steps=0)


def test_expected_behavior_rejects_bad_score() -> None:
    with pytest.raises(ValueError):
        EvaluationScenarioExpectedBehavior(min_normal_activity_score=1.2)


def test_office_worker_scenario_core_fields() -> None:
    s = load_evaluation_scenario("configs/evaluation_scenarios/office_worker_basic_session.json")
    assert s.agents[0].role_id == "office_worker"
    assert s.agents[0].activity_profile_path == "configs/activity_profiles/office_worker.json"


def test_developer_scenario_includes_shell() -> None:
    s = load_evaluation_scenario("configs/evaluation_scenarios/developer_project_maintenance.json")
    assert "run_shell_command" in s.agents[0].available_actions


def test_office_worker_scenario_excludes_shell() -> None:
    s = load_evaluation_scenario("configs/evaluation_scenarios/office_worker_basic_session.json")
    assert "run_shell_command" not in s.agents[0].available_actions


def test_mixed_roles_properties() -> None:
    s = load_evaluation_scenario("configs/evaluation_scenarios/mixed_roles_multi_agent_session.json")
    assert s.agent_count() == 3
    assert s.is_multi_agent() is True


def test_verify_references_no_missing_for_scenarios() -> None:
    scenarios = load_evaluation_scenarios_from_dir("configs/evaluation_scenarios")
    for s in scenarios:
        assert verify_evaluation_scenario_references(s) == []


def test_scenario_summary_json_serializable() -> None:
    s = load_evaluation_scenario("configs/evaluation_scenarios/office_worker_basic_session.json")
    summary = evaluation_scenario_summary(s)
    json.dumps(summary)
    assert summary["scenario_id"] == "office_worker_basic_session_v1"


def test_doc_exists_and_mentions_normal_activity_and_model_comparison() -> None:
    path = Path("docs/ai/evaluation_scenario_v1.md")
    assert path.exists()
    text = path.read_text(encoding="utf-8").lower()
    assert "normal user activity simulation" in text
    assert "future model comparison" in text
