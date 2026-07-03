from __future__ import annotations

import json
from pathlib import Path, PureWindowsPath

from src.agent.orchestrator_executor_pipeline import (
    OrchestratorExecutorRunConfig,
    OrchestratorExecutorRunner,
    OrchestratorExecutorScenario,
)
from src.agent.orchestrator_prompt_contract import parse_orchestrator_plan_text


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "configs/multi_agent_scenarios/office_developer_maintenance_group_heavy.json"


def _json(relative_path: str) -> dict[str, object]:
    return json.loads((PROJECT_ROOT / relative_path).read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, object]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_heavy_multi_agent_scenario_schema_and_paths_are_safe() -> None:
    payload = _json(SCENARIO)
    scenario = OrchestratorExecutorScenario.model_validate(payload)

    assert scenario.scenario_id == "office_developer_maintenance_group_heavy_v1"
    assert len(scenario.agents) == 4
    assert scenario.max_group_steps == 2
    assert scenario.max_steps_per_agent == 1
    assert scenario.metadata["network_required"] is False
    assert scenario.metadata["browser_real_automation_required"] is False
    assert scenario.metadata["office_real_automation_required"] is False
    assert scenario.metadata["agent_step_budget_scope"] == "per_group_step"
    assert scenario.metadata["write_path_policy"] == "artifact_workspace_only"

    agent_ids = [agent.agent_id for agent in scenario.agents]
    assert len(agent_ids) == len(set(agent_ids))
    for agent in scenario.agents:
        assert (PROJECT_ROOT / agent.role_template_path).exists()
        assert (PROJECT_ROOT / agent.activity_profile_path).exists()
        for value in [agent.role_template_path, agent.activity_profile_path, agent.assigned_goal]:
            assert not Path(value).is_absolute()
            assert not PureWindowsPath(value).is_absolute()
            assert "://" not in value

    for fixture_path in scenario.metadata["fixture_paths"]:
        assert isinstance(fixture_path, str)
        assert not Path(fixture_path).is_absolute()
        assert not PureWindowsPath(fixture_path).is_absolute()
        assert ".." not in Path(fixture_path).parts
        assert (PROJECT_ROOT / fixture_path).exists()


def test_heavy_multi_agent_scenario_uses_supported_actions_only() -> None:
    scenario = OrchestratorExecutorScenario.model_validate(_json(SCENARIO))
    registry = _json(scenario.registry_path)
    supported_actions = {item["name"] for item in registry["scripts"]}

    assert set(scenario.metadata["expected_safe_actions"]).issubset(supported_actions)
    assert "browser_open_url" not in scenario.metadata["expected_safe_actions"]
    assert "run_shell_command" not in scenario.metadata["expected_safe_actions"]


def test_orchestrator_plan_contract_accepts_four_known_agents() -> None:
    raw = json.dumps(
        {
            "tasks": [
                {
                    "task_id": "task_1",
                    "agent_id": "office_agent_1",
                    "goal": "Read local team brief.",
                    "allowed_action_focus": ["read_file"],
                    "success_criteria": "Team brief is inspected.",
                },
                {
                    "task_id": "task_2",
                    "agent_id": "office_agent_2",
                    "goal": "Review local notes.",
                    "allowed_action_focus": ["read_file"],
                    "success_criteria": "Maintenance notes are inspected.",
                },
                {
                    "task_id": "task_3",
                    "agent_id": "developer_agent_1",
                    "goal": "Inspect project context.",
                    "allowed_action_focus": ["read_file"],
                    "success_criteria": "Project context is inspected.",
                },
                {
                    "task_id": "task_4",
                    "agent_id": "developer_agent_2",
                    "goal": "Inspect pair matrix docs.",
                    "allowed_action_focus": ["read_file"],
                    "success_criteria": "Pair matrix docs are inspected.",
                },
            ],
            "coordination_notes": "Use local files only.",
            "expected_group_outcome": "All agents inspect safe local context.",
        }
    )

    plan = parse_orchestrator_plan_text(
        raw,
        known_agent_ids={"office_agent_1", "office_agent_2", "developer_agent_1", "developer_agent_2"},
        allowed_action_names_by_agent={
            "office_agent_1": {"read_file", "create_file"},
            "office_agent_2": {"read_file", "create_file"},
            "developer_agent_1": {"read_file", "create_file"},
            "developer_agent_2": {"read_file", "create_file"},
        },
    )

    assert len(plan.tasks) == 4


def test_fake_heavy_group_run_uses_two_group_steps(tmp_path: Path) -> None:
    out_dir = tmp_path / "fake_heavy_group"
    result = OrchestratorExecutorRunner(
        OrchestratorExecutorRunConfig(
            project_root=PROJECT_ROOT,
            mode="fake",
            models_config_path="configs/evaluation_models.json",
            scenario_path=SCENARIO,
            out_dir=str(out_dir),
            run_id="test_fake_heavy_group",
            orchestrator_model_id="second_model",
            executor_model_id="first_model",
            max_group_steps=2,
            max_steps_per_agent=1,
            orchestrator_repair_attempts=1,
            repair_attempts=1,
            execute_actions=False,
            force=True,
        )
    ).run()
    history = _jsonl(out_dir / "group_history.jsonl")

    assert result.status == "completed"
    assert result.success is True
    assert len({row["agent_id"] for row in history}) == 4
    assert {row["group_step_index"] for row in history} == {1, 2}
    assert len(history) == 8
