from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_runtime import BROWSER_RUNTIME_ACTION_NAMES
from src.agent.autonomous_runtime_scenarios import (
    AutonomousRuntimeScenarioValidationError,
    ScriptedRuntimeDecisionProvider,
    build_autonomous_runtime_from_scenario,
    build_autonomous_runtime_scenario_summary,
    load_autonomous_runtime_scenario,
    run_autonomous_runtime_scenario,
    write_autonomous_runtime_scenario_summary,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO_PATH = PROJECT_ROOT / "configs/autonomous_runtime/browser_intranet_research_group_basic.example.json"
EXTENDED_SCENARIO_PATH = PROJECT_ROOT / "configs/autonomous_runtime/browser_intranet_form_workflow_extended.example.json"
RUNNER_PATH = PROJECT_ROOT / "scripts/run_autonomous_runtime_scenario.py"


def _payload() -> dict[str, Any]:
    return json.loads(SCENARIO_PATH.read_text(encoding="utf-8"))


def _write_payload(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "scenario.json"
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return path


def test_example_config_loads() -> None:
    scenario = load_autonomous_runtime_scenario(SCENARIO_PATH)

    assert scenario.scenario_id == "browser_intranet_research_group_basic"
    assert len(scenario.agents) == 2
    assert scenario.browser_sessions[0].fixture_manifest_path.endswith("site_manifest.json")


def test_extended_form_workflow_config_loads() -> None:
    scenario = load_autonomous_runtime_scenario(EXTENDED_SCENARIO_PATH)

    assert scenario.scenario_id == "browser_intranet_form_workflow_extended"
    assert len(scenario.agents) == 3
    assert any(task.depends_on for task in scenario.tasks)
    assert {step.action_name for step in scenario.scripted_steps}.issuperset(
        {"browser_click", "browser_fill", "browser_submit", "browser_wait", "browser_snapshot"}
    )


def test_policy_and_portal_expected_markers_match_fixture_text() -> None:
    policy = load_autonomous_runtime_scenario(PROJECT_ROOT / "configs/autonomous_runtime/browser_intranet_policy_research.example.json")
    portal = load_autonomous_runtime_scenario(PROJECT_ROOT / "configs/autonomous_runtime/browser_portal_approval_check.example.json")
    policy_steps = {step.step_id: step for step in policy.scripted_steps}
    portal_steps = {step.step_id: step for step in portal.scripted_steps}

    assert policy_steps["reader_search_policy"].expected_text == "fixture-backed result"
    assert portal_steps["reader_open_portal"].expected_text == "Search marker: fixture-backed result for local policy review"
    assert portal_steps["checker_open_status"].expected_text == "Approval status: ready for fixture-backed review"


def test_home_fixture_keeps_workspace_policy_click_target_unambiguous() -> None:
    home_html = (PROJECT_ROOT / "tests/fixtures/local_intranet/office_site_v1/index.html").read_text(encoding="utf-8")

    assert home_html.count("Workspace policy") == 1
    assert "fixture-backed result for local policy review" in home_html


def test_loader_rejects_missing_agents(tmp_path: Path) -> None:
    payload = _payload()
    payload["agents"] = []

    with pytest.raises(AutonomousRuntimeScenarioValidationError, match="agents"):
        load_autonomous_runtime_scenario(_write_payload(tmp_path, payload))


def test_loader_rejects_unknown_browser_session_reference(tmp_path: Path) -> None:
    payload = _payload()
    payload["scripted_steps"][0]["browser_session_id"] = "missing_session"

    with pytest.raises(AutonomousRuntimeScenarioValidationError, match="unknown browser session"):
        load_autonomous_runtime_scenario(_write_payload(tmp_path, payload))


def test_loader_rejects_mail_git_action_names(tmp_path: Path) -> None:
    payload = _payload()
    payload["scripted_steps"][0]["action_name"] = "git_commit"

    with pytest.raises(AutonomousRuntimeScenarioValidationError, match="Forbidden external action"):
        load_autonomous_runtime_scenario(_write_payload(tmp_path, payload))


def test_loader_rejects_external_non_allowed_domain(tmp_path: Path) -> None:
    payload = _payload()
    payload["scripted_steps"][0]["parameters"]["url"] = "https://example.com/report"

    with pytest.raises(AutonomousRuntimeScenarioValidationError, match="outside allowed_domains"):
        load_autonomous_runtime_scenario(_write_payload(tmp_path, payload))


def test_builder_creates_runtime_with_browser_namespace() -> None:
    scenario = load_autonomous_runtime_scenario(SCENARIO_PATH)
    built = build_autonomous_runtime_from_scenario(scenario, fixture_root=PROJECT_ROOT)

    assert "browser" in built.runtime.virtual_environment.allowed_resource_namespaces
    assert set(built.browser_sessions) == {"reader_session", "checker_session"}


def test_scripted_provider_emits_deterministic_decisions() -> None:
    scenario = load_autonomous_runtime_scenario(SCENARIO_PATH)
    built = build_autonomous_runtime_from_scenario(scenario, fixture_root=PROJECT_ROOT)
    agent = built.shared_state.agents["research_reader"]
    built.shared_state.assign_task("research_reader", "reader_01_open_ticket")

    decision = built.decision_provider(agent, built.shared_state)

    assert decision is not None
    assert decision.agent_id == "research_reader"
    assert decision.action_name == "browser_open_url"
    assert decision.parameters["session_id"] == "reader_session"
    assert decision.resource_locks == ("browser:reader_session",)


def test_scenario_run_completes_all_tasks() -> None:
    scenario = load_autonomous_runtime_scenario(SCENARIO_PATH)
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)

    assert summary["task_counts"]["completed"] == 6
    assert summary["expected_results_passed"] is True
    assert summary["stop_reason"] == "all_tasks_terminal"


def test_extended_scenario_run_covers_form_navigation_wait_and_dependencies() -> None:
    scenario = load_autonomous_runtime_scenario(EXTENDED_SCENARIO_PATH)
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)

    assert summary["task_counts"]["completed"] == 8
    assert summary["expected_results_passed"] is True
    assert summary["browser_session_summaries"]["portal_session"]["current_url"] == "https://local-intranet.test/portal/submitted"
    assert summary["browser_session_summaries"]["portal_session"]["form_state"]["local-request"]["_submitted"] == "true"
    assert summary["browser_coverage"]["schema_version"] == "autonomous_browser_scenario_coverage_v1"
    assert summary["browser_coverage"]["action_coverage_ratio"] == 1.0
    assert summary["browser_coverage"]["expected_results_failed"] == 0
    dependency_status = {item["task_id"]: item for item in summary["task_dependency_status"]}
    assert dependency_status["portal_01_open_request_form"]["dependencies_satisfied"] is True


def test_runtime_summary_includes_browser_session_summaries() -> None:
    scenario = load_autonomous_runtime_scenario(SCENARIO_PATH)
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)

    sessions = summary["browser_session_summaries"]
    assert sessions["reader_session"]["snapshot_count"] == 1
    assert sessions["checker_session"]["snapshot_count"] == 1
    assert "Quarterly Access Review" in sessions["reader_session"]["last_observation"]["text_preview"]


def test_expected_result_passes_when_expected_text_found() -> None:
    scenario = load_autonomous_runtime_scenario(SCENARIO_PATH)
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)

    expected = {item["result_id"]: item for item in summary["expected_results"]}
    assert expected["reader_text_seen"]["passed"] is True


def test_expected_result_fails_when_text_missing(tmp_path: Path) -> None:
    payload = _payload()
    payload["expected_results"] = [
        {
            "result_id": "missing_text",
            "kind": "browser_session_text",
            "session_id": "reader_session",
            "expected_text": "not in fixture",
        }
    ]
    scenario = load_autonomous_runtime_scenario(_write_payload(tmp_path, payload))
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)

    assert summary["expected_results_passed"] is False
    assert summary["expected_results"][0]["passed"] is False


def test_per_task_expected_result_fails_on_wrong_url(tmp_path: Path) -> None:
    payload = json.loads(EXTENDED_SCENARIO_PATH.read_text(encoding="utf-8"))
    payload["expected_results"] = [
        {
            "result_id": "wrong_task_url",
            "kind": "task_browser_expected_result",
            "task_id": "portal_03_submit_request_form",
            "expected_current_url": "https://local-intranet.test/not-submitted",
        }
    ]
    scenario = load_autonomous_runtime_scenario(_write_payload(tmp_path, payload))
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)

    assert summary["expected_results_passed"] is False
    assert summary["expected_results"][0]["details"]["checks"]["expected_current_url"] is False


def test_loader_rejects_unknown_task_dependency(tmp_path: Path) -> None:
    payload = json.loads(EXTENDED_SCENARIO_PATH.read_text(encoding="utf-8"))
    payload["tasks"][1]["depends_on"] = ["missing_task"]

    with pytest.raises(AutonomousRuntimeScenarioValidationError, match="unknown dependency"):
        load_autonomous_runtime_scenario(_write_payload(tmp_path, payload))


def test_scripted_provider_blocks_then_runs_dependency_task() -> None:
    scenario = load_autonomous_runtime_scenario(EXTENDED_SCENARIO_PATH)
    built = build_autonomous_runtime_from_scenario(scenario, fixture_root=PROJECT_ROOT)
    agent = built.shared_state.agents["portal_operator"]
    built.shared_state.assign_task("portal_operator", "portal_01_open_request_form")

    blocked = built.decision_provider(agent, built.shared_state)

    assert blocked is None
    assert built.decision_provider.dependency_block_events[-1]["unmet_dependencies"] == ["reader_02_click_ticket_board"]

    built.shared_state.complete_task("reader_02_click_ticket_board")
    decision = built.decision_provider(agent, built.shared_state)

    assert decision is not None
    assert decision.action_name == "browser_open_url"
    assert decision.task_id == "portal_01_open_request_form"


def test_noop_idle_behavior_is_controlled_when_scripted_steps_exhausted() -> None:
    scenario = load_autonomous_runtime_scenario(SCENARIO_PATH)
    provider = ScriptedRuntimeDecisionProvider(())
    built = build_autonomous_runtime_from_scenario(scenario, fixture_root=PROJECT_ROOT)
    agent = built.shared_state.agents["research_reader"]
    built.shared_state.assign_task("research_reader", "reader_01_open_ticket")

    decision = provider(agent, built.shared_state)

    assert decision is None
    assert provider.exhausted_events == [
        {
            "agent_id": "research_reader",
            "task_id": "reader_01_open_ticket",
            "reason": "scripted_steps_exhausted",
        }
    ]


def test_output_summary_is_json_serializable() -> None:
    scenario = load_autonomous_runtime_scenario(SCENARIO_PATH)
    built = build_autonomous_runtime_from_scenario(scenario, fixture_root=PROJECT_ROOT)
    built.runtime.run()

    summary = build_autonomous_runtime_scenario_summary(built)

    assert json.loads(json.dumps(summary))["schema_version"] == "autonomous_runtime_scenario_summary_v1"


def test_cli_dry_run_writes_summary_to_temp_output(tmp_path: Path) -> None:
    output_name = "scenario.summary.json"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--scenario",
            str(SCENARIO_PATH),
            "--output",
            output_name,
            "--dry-run",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    output = tmp_path / output_name
    assert output.exists()
    summary = json.loads(output.read_text(encoding="utf-8"))
    assert summary["expected_results_passed"] is True
    assert summary["no_runtime_execution"] is True


def test_cli_dry_run_extended_scenario_includes_browser_coverage(tmp_path: Path) -> None:
    output_name = "extended.summary.json"
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--scenario",
            str(EXTENDED_SCENARIO_PATH),
            "--output",
            output_name,
            "--dry-run",
        ],
        cwd=tmp_path,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 0
    summary = json.loads((tmp_path / output_name).read_text(encoding="utf-8"))
    assert summary["browser_coverage"]["actions_succeeded"] == 8
    assert summary["browser_coverage"]["policy_denial_count"] == 0


def test_cli_refuses_unsafe_output_path(tmp_path: Path) -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--scenario",
            str(SCENARIO_PATH),
            "--output",
            str(tmp_path / "absolute.summary.json"),
            "--dry-run",
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )

    assert result.returncode == 2
    assert "output path must be a safe relative path" in result.stdout


def test_write_summary_rejects_traversal_output_path() -> None:
    with pytest.raises(AutonomousRuntimeScenarioValidationError, match="traversal"):
        write_autonomous_runtime_scenario_summary({"ok": True}, "../summary.json")


def test_no_real_browser_playwright_http_api_or_model_call_is_made() -> None:
    scenario = load_autonomous_runtime_scenario(SCENARIO_PATH)
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)

    assert summary["no_runtime_execution"] is True
    for session in summary["browser_session_summaries"].values():
        assert session["policy_flags"]["fixture_mode"] is True
        assert session["policy_flags"]["playwright_enabled"] is False
        assert session["policy_denials"] == 0


def test_no_mail_git_calendar_action_support_added() -> None:
    names = set(BROWSER_RUNTIME_ACTION_NAMES)

    assert not any(name.startswith(("mail_", "git_", "calendar_", "email_")) for name in names)
    assert "browser_open_url" in names
