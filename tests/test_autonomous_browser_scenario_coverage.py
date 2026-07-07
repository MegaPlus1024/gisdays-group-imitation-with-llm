from __future__ import annotations

from pathlib import Path

from src.agent.autonomous_runtime_scenarios import load_autonomous_runtime_scenario, run_autonomous_runtime_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXTENDED_SCENARIO_PATH = PROJECT_ROOT / "configs/autonomous_runtime/browser_intranet_form_workflow_extended.example.json"


def test_browser_coverage_summary_counts_extended_offline_actions() -> None:
    scenario = load_autonomous_runtime_scenario(EXTENDED_SCENARIO_PATH)
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)
    coverage = summary["browser_coverage"]

    assert coverage["schema_version"] == "autonomous_browser_scenario_coverage_v1"
    assert coverage["scenario_id"] == "browser_intranet_form_workflow_extended"
    assert set(coverage["actions_required"]) == {
        "browser_click",
        "browser_fill",
        "browser_open_url",
        "browser_snapshot",
        "browser_submit",
        "browser_wait",
    }
    assert coverage["actions_succeeded"] == 8
    assert coverage["actions_failed"] == 0
    assert coverage["action_coverage_ratio"] == 1.0
    assert coverage["agents_covered"] == ["policy_checker", "portal_operator", "research_reader"]
    assert coverage["tasks_covered"] == [
        "checker_01_open_policy",
        "checker_02_wait_on_policy",
        "portal_01_open_request_form",
        "portal_02_fill_request_form",
        "portal_03_submit_request_form",
        "reader_01_open_home",
        "reader_02_click_ticket_board",
        "reader_03_snapshot_ticket_board",
    ]
    assert coverage["browser_sessions_covered"] == ["checker_session", "portal_session", "reader_session"]
    assert coverage["policy_denial_count"] == 0
    assert coverage["expected_results_passed"] == 5
    assert coverage["expected_results_failed"] == 0


def test_dependency_block_event_is_reflected_in_scripted_provider_summary() -> None:
    scenario = load_autonomous_runtime_scenario(EXTENDED_SCENARIO_PATH)
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)

    events = summary["scripted_provider"]["dependency_block_events"]
    assert events
    assert events[0]["task_id"] == "portal_01_open_request_form"
    assert events[0]["unmet_dependencies"] == ["reader_02_click_ticket_board"]
