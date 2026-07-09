from __future__ import annotations

import json
from pathlib import Path

from src.agent.autonomous_browser_scenario_suite import load_autonomous_browser_scenario_suite, run_autonomous_browser_scenario_suite
from src.agent.autonomous_runtime_scenarios import load_autonomous_runtime_scenario, run_autonomous_runtime_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[1]
POLICY_SCENARIO_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_hard_policy_disambiguation.example.json"
TICKET_SCENARIO_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_hard_ticket_priority_crosscheck.example.json"
APPROVAL_SCENARIO_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_hard_approval_policy_match.example.json"
PHASE12D_SUITE_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_phase12d_hard_fixture_suite.example.json"


def test_hard_policy_disambiguation_scenario_loads_and_completes() -> None:
    scenario = load_autonomous_runtime_scenario(POLICY_SCENARIO_PATH)
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)

    assert scenario.scenario_id == "hard_policy_disambiguation"
    assert summary["expected_results_passed"] is True
    assert summary["task_counts"]["completed"] == 4
    assert summary["browser_session_summaries"]["policy_session"]["current_url"] == "https://docs.local/docs/policy"
    assert "Workspace Policy" in json.dumps(summary)
    assert "Choose the live source" in json.dumps(summary)


def test_hard_ticket_priority_crosscheck_scenario_loads_and_completes() -> None:
    scenario = load_autonomous_runtime_scenario(TICKET_SCENARIO_PATH)
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)

    assert scenario.scenario_id == "hard_ticket_priority_crosscheck"
    assert summary["expected_results_passed"] is True
    assert summary["task_counts"]["completed"] == 4
    assert summary["browser_session_summaries"]["ticket_session"]["current_url"] == "https://local.intranet/tickets/7"
    assert "Escalation Review" in json.dumps(summary)
    assert "Priority: urgent." in json.dumps(summary)


def test_hard_approval_policy_match_scenario_loads_and_completes() -> None:
    scenario = load_autonomous_runtime_scenario(APPROVAL_SCENARIO_PATH)
    summary = run_autonomous_runtime_scenario(scenario, fixture_root=PROJECT_ROOT)

    assert scenario.scenario_id == "hard_approval_policy_match"
    assert summary["expected_results_passed"] is True
    assert summary["task_counts"]["completed"] == 5
    assert summary["browser_session_summaries"]["approval_session"]["current_url"] == "https://portal.local/portal/approval-match"
    assert "Policy match: confirmed." in json.dumps(summary)


def test_phase12d_hard_fixture_suite_runs_three_scenarios_with_full_offline_coverage() -> None:
    suite = load_autonomous_browser_scenario_suite(PHASE12D_SUITE_PATH)
    summary = run_autonomous_browser_scenario_suite(suite, repo_root=PROJECT_ROOT).to_summary()

    assert summary["suite_id"] == "browser_phase12d_hard_fixture_suite_v1"
    assert summary["scenario_count"] == 3
    assert summary["scenarios_passed"] == 3
    assert summary["scenarios_failed"] == 0
    assert summary["expected_min_passed_scenarios_met"] is True
    assert set(summary["required_actions_covered"]) == {
        "browser_click",
        "browser_extract_text",
        "browser_open_url",
        "browser_snapshot",
    }
    assert summary["required_actions_missing"] == []
    assert summary["overall_action_coverage_ratio"] == 1.0
    assert summary["no_runtime_execution"] is True
    assert "C:\\" not in json.dumps(summary)

    scenario_summaries = {item["scenario_id"]: item for item in summary["scenario_summaries"]}
    assert scenario_summaries["hard_policy_disambiguation"]["status"] == "passed"
    assert scenario_summaries["hard_ticket_priority_crosscheck"]["status"] == "passed"
    assert scenario_summaries["hard_approval_policy_match"]["status"] == "passed"
