from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.orchestrator_executor_pipeline import (
    ExecutorProviderResult,
    GroupAgentSpec,
    OrchestratorExecutorRunConfig,
    OrchestratorExecutorRunner,
    OrchestratorPlanTask,
    load_orchestrator_executor_scenario,
)
from src.agent.state import AgentState
from src.agent.virtual_network import VirtualNetworkValidationError, load_virtual_network_spec


PROJECT_ROOT = Path(__file__).resolve().parents[1]
BASELINE_SCENARIO = "configs/multi_agent_scenarios/office_developer_group_basic.json"
VIRTUAL_NETWORK_SCENARIO = (
    "configs/multi_agent_scenarios/office_developer_group_basic_virtual_network_v1.json"
)
INTRANET_BROWSER_POLICY_SCENARIO = (
    "configs/multi_agent_scenarios/office_intranet_browser_policy_v1.json"
)


def _config(
    tmp_path: Path,
    scenario_path: str | Path = VIRTUAL_NETWORK_SCENARIO,
    **overrides: Any,
) -> OrchestratorExecutorRunConfig:
    payload: dict[str, Any] = {
        "project_root": PROJECT_ROOT,
        "mode": "fake",
        "models_config_path": "configs/evaluation_models.json",
        "scenario_path": str(scenario_path),
        "out_dir": str(tmp_path / "group_artifacts"),
        "run_id": "test_virtual_network_group",
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
        "max_group_steps": 2,
        "max_steps_per_agent": 2,
        "repair_attempts": 1,
        "execute_actions": False,
        "force": True,
    }
    payload.update(overrides)
    return OrchestratorExecutorRunConfig.model_validate(payload)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


class CapturingExecutorProvider:
    def __init__(self) -> None:
        self.states: dict[str, dict[str, Any]] = {}

    def next_action(
        self,
        *,
        agent: GroupAgentSpec,
        task: OrchestratorPlanTask,
        state: AgentState,
        group_step_index: int,
        agent_step_index: int,
        out_dir: Path,
        project_root: Path,
    ) -> ExecutorProviderResult:
        del task, group_step_index, agent_step_index, out_dir, project_root
        self.states.setdefault(agent.agent_id, state.to_prompt_context())
        action = {
            "action": "read_file",
            "parameters": {"path": "docs/ai/model_research_metadata.md"},
            "reason": "Read safe local metadata while preserving virtual network context.",
            "expected_result": "The local metadata is available for the assigned task.",
        }
        return ExecutorProviderResult(
            raw_model_output=json.dumps(action, ensure_ascii=False),
            metadata={"provider": "capturing_executor"},
        )


class StaticBrowserActionExecutorProvider:
    def __init__(self, office_url: str) -> None:
        self.office_url = office_url

    def next_action(
        self,
        *,
        agent: GroupAgentSpec,
        task: OrchestratorPlanTask,
        state: AgentState,
        group_step_index: int,
        agent_step_index: int,
        out_dir: Path,
        project_root: Path,
    ) -> ExecutorProviderResult:
        del task, state, group_step_index, agent_step_index, out_dir, project_root
        if agent.agent_id == "office_agent":
            action = {
                "action": "browser_open_url",
                "parameters": {"url": self.office_url},
                "reason": "Validate a URL-bearing action against virtual network policy.",
                "expected_result": "The URL action is accepted or denied by metadata policy.",
            }
        else:
            action = {
                "action": "read_file",
                "parameters": {"path": "docs/ai/model_research_metadata.md"},
                "reason": "Read safe local metadata for the developer task.",
                "expected_result": "The local metadata is available.",
            }
        return ExecutorProviderResult(
            raw_model_output=json.dumps(action, ensure_ascii=False),
            metadata={"provider": "static_browser_action_executor"},
        )


def test_virtual_network_scenario_loads_spec_and_agent_host_map() -> None:
    scenario = load_orchestrator_executor_scenario(PROJECT_ROOT / VIRTUAL_NETWORK_SCENARIO)

    assert scenario.virtual_network is not None
    assert scenario.virtual_network.spec_path == "configs/virtual_networks/local_office_network_v1.json"
    assert scenario.virtual_network.agent_host_map == {
        "office_agent": "office_user_host",
        "developer_agent": "developer_host",
    }

    spec = load_virtual_network_spec(PROJECT_ROOT / scenario.virtual_network.spec_path)

    assert spec.network_id == "local_office_network_v1"
    assert spec.get_host("office_user_host") is not None
    assert spec.get_host("developer_host") is not None


def test_intranet_browser_policy_scenario_is_offline_and_network_aware() -> None:
    scenario = load_orchestrator_executor_scenario(PROJECT_ROOT / INTRANET_BROWSER_POLICY_SCENARIO)

    assert scenario.scenario_id == "office_intranet_browser_policy_v1"
    assert scenario.virtual_network is not None
    assert scenario.virtual_network.spec_path == "configs/virtual_networks/local_office_network_v1.json"
    assert scenario.virtual_network.agent_host_map["office_agent"] == "office_user_host"
    assert scenario.metadata["virtual_network_metadata_only"] is True
    assert scenario.metadata["browser_real_automation_required"] is False
    assert scenario.metadata["external_network_required"] is False
    assert "browser_open_url" in scenario.metadata["expected_safe_actions"]
    assert scenario.agents[0].role_template_path == "configs/roles/office_intranet_browser_worker.example.json"


def test_fake_group_run_writes_virtual_network_artifacts_and_history(tmp_path: Path) -> None:
    result = OrchestratorExecutorRunner(_config(tmp_path)).run()
    out_dir = Path(result.artifact_dir or "")

    assert result.status == "completed"
    assert result.success is True
    assert result.virtual_network is not None
    assert result.virtual_network["network_id"] == "local_office_network_v1"
    assert result.virtual_network["agent_host_map"] == {
        "developer_agent": "developer_host",
        "office_agent": "office_user_host",
    }

    manifest = _json(out_dir / "manifest.json")
    summary = _json(out_dir / "virtual_network_summary.json")
    history = _jsonl(out_dir / "group_history.jsonl")
    actions = _jsonl(out_dir / "per_agent_actions.jsonl")

    assert manifest["virtual_network"]["network_id"] == "local_office_network_v1"
    assert summary["metadata_only"] is True
    assert summary["real_network_actions_recorded"] is False
    assert summary["agent_host_map"]["office_agent"] == "office_user_host"
    assert summary["agent_host_map"]["developer_agent"] == "developer_host"
    assert {row["agent_id"] for row in history} == {"office_agent", "developer_agent"}
    assert all(row["metadata"]["virtual_network"]["network_id"] == "local_office_network_v1" for row in history)
    assert all(row["validation_accepted"] is True for row in actions)


def test_virtual_network_invalid_host_reference_fails_before_fake_run(tmp_path: Path) -> None:
    payload = _json(PROJECT_ROOT / VIRTUAL_NETWORK_SCENARIO)
    payload["virtual_network"]["agent_host_map"]["office_agent"] = "missing_host"
    scenario_path = tmp_path / "invalid_virtual_network_scenario.json"
    scenario_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    with pytest.raises(VirtualNetworkValidationError, match="unknown host_id"):
        OrchestratorExecutorRunner(_config(tmp_path, scenario_path=scenario_path)).run()


def test_baseline_scenario_without_virtual_network_remains_backward_compatible(tmp_path: Path) -> None:
    scenario = load_orchestrator_executor_scenario(PROJECT_ROOT / BASELINE_SCENARIO)

    assert scenario.virtual_network is None

    result = OrchestratorExecutorRunner(_config(tmp_path, scenario_path=BASELINE_SCENARIO)).run()
    out_dir = Path(result.artifact_dir or "")
    manifest = _json(out_dir / "manifest.json")

    assert result.status == "completed"
    assert result.virtual_network is None
    assert manifest["virtual_network"] is None
    assert not (out_dir / "virtual_network_summary.json").exists()


def test_agent_state_contains_virtual_network_metadata_when_bound(tmp_path: Path) -> None:
    executor_provider = CapturingExecutorProvider()

    result = OrchestratorExecutorRunner(
        _config(tmp_path),
        executor_provider=executor_provider,
    ).run()

    assert result.status == "completed"
    office_state = executor_provider.states["office_agent"]
    developer_state = executor_provider.states["developer_agent"]

    office_metadata = office_state["metadata"]["virtual_network"]
    office_environment = office_state["environment"]["virtual_network"]
    office_resources = office_state["resources"]["virtual_network"]

    assert office_metadata["network_id"] == "local_office_network_v1"
    assert office_metadata["host_id"] == "office_user_host"
    assert office_metadata["host_display_name"] == "Office user workstation"
    assert office_metadata["host_role"] == "office_worker"
    assert office_metadata["workspace_root"].endswith("/office_user_host")
    assert "shared_docs" in office_metadata["allowed_service_ids"]
    assert "http://localhost" in office_metadata["allowed_url_prefixes"]
    assert office_environment["metadata_only"] is True
    assert office_resources["host_id"] == "office_user_host"
    assert developer_state["metadata"]["virtual_network"]["host_id"] == "developer_host"


def test_fake_group_run_with_allowed_url_writes_network_policy_metadata(tmp_path: Path) -> None:
    executor_provider = StaticBrowserActionExecutorProvider("http://localhost:8088/tickets/1")

    result = OrchestratorExecutorRunner(
        _config(
            tmp_path,
            scenario_path=INTRANET_BROWSER_POLICY_SCENARIO,
            repair_attempts=0,
            execute_actions=True,
        ),
        executor_provider=executor_provider,
    ).run()
    out_dir = Path(result.artifact_dir or "")
    history = _jsonl(out_dir / "group_history.jsonl")
    network_events = _jsonl(out_dir / "network_events.jsonl")
    actions = _jsonl(out_dir / "per_agent_actions.jsonl")

    office_history = next(row for row in history if row["agent_id"] == "office_agent")
    office_action = next(row for row in actions if row["agent_id"] == "office_agent")

    assert result.status == "completed"
    assert result.success is True
    assert office_history["metadata"]["virtual_network_policy"]["allowed"] is True
    assert office_history["metadata"]["virtual_network_policy"]["code"] == "virtual_network_policy_allowed"
    assert office_action["execution_attempted"] is True
    assert office_action["execution_success"] is True
    assert network_events[0]["status"] == "policy_allowed"
    assert network_events[0]["target_url"] == "http://localhost:8088"
    assert network_events[0]["real_network_traffic"] is False


def test_fake_group_run_with_denied_url_records_policy_denial(tmp_path: Path) -> None:
    executor_provider = StaticBrowserActionExecutorProvider("https://example.com/report")

    result = OrchestratorExecutorRunner(
        _config(
            tmp_path,
            scenario_path=INTRANET_BROWSER_POLICY_SCENARIO,
            repair_attempts=0,
            execute_actions=True,
        ),
        executor_provider=executor_provider,
    ).run()
    out_dir = Path(result.artifact_dir or "")
    history = _jsonl(out_dir / "group_history.jsonl")
    network_events = _jsonl(out_dir / "network_events.jsonl")
    errors = _jsonl(out_dir / "errors.jsonl")
    actions = _jsonl(out_dir / "per_agent_actions.jsonl")

    office_history = next(row for row in history if row["agent_id"] == "office_agent")
    office_action = next(row for row in actions if row["agent_id"] == "office_agent")

    assert result.status == "completed_with_failures"
    assert result.success is False
    assert office_history["status"] == "failure"
    assert office_history["metadata"]["virtual_network_policy"]["allowed"] is False
    assert office_history["metadata"]["virtual_network_policy"]["code"] == "virtual_network_url_denied"
    assert office_action["error_type"] == "virtual_network_policy_denied"
    assert office_action["execution_attempted"] is False
    assert any(row["error_type"] == "virtual_network_policy_denied" for row in errors)
    assert network_events[0]["status"] == "policy_denied"
    assert network_events[0]["target_url"] == "https://example.com"
    assert network_events[0]["real_network_traffic"] is False
