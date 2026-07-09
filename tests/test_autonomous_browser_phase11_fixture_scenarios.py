from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.autonomous_browser_scenario_suite import load_autonomous_browser_scenario_suite, run_autonomous_browser_scenario_suite
from src.agent.autonomous_runtime_scenarios import load_autonomous_runtime_scenario, run_autonomous_runtime_scenario


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TICKET_SCENARIO_PATH = PROJECT_ROOT / "configs/autonomous_runtime/browser_ticket_triage_review.example.json"
APPROVAL_SCENARIO_PATH = PROJECT_ROOT / "configs/autonomous_runtime/browser_approval_form_review.example.json"
PHASE11_SUITE_PATH = PROJECT_ROOT / "configs/autonomous_runtime/browser_phase11_fixture_suite.example.json"


def test_ticket_triage_review_config_loads_and_contains_expected_markers() -> None:
    scenario = load_autonomous_runtime_scenario(TICKET_SCENARIO_PATH)

    assert scenario.scenario_id == "browser_ticket_triage_review"
    assert [step.action_name for step in scenario.scripted_steps] == [
        "browser_open_url",
        "browser_click",
        "browser_extract_text",
        "browser_snapshot",
    ]
    assert scenario.scripted_steps[2].expected_text == "Priority: high. Local fixture only."


def test_approval_form_review_config_loads_and_contains_expected_markers() -> None:
    scenario = load_autonomous_runtime_scenario(APPROVAL_SCENARIO_PATH)

    assert scenario.scenario_id == "browser_approval_form_review"
    assert [step.action_name for step in scenario.scripted_steps] == [
        "browser_open_url",
        "browser_click",
        "browser_open_url",
        "browser_snapshot",
        "browser_open_url",
        "browser_extract_text",
        "browser_snapshot",
    ]
    assert scenario.scripted_steps[2].expected_text == "Approval request"
    assert scenario.scripted_steps[5].expected_text == "fixture-backed"


def test_phase11_fixture_suite_runs_two_scenarios_with_full_offline_coverage() -> None:
    suite = load_autonomous_browser_scenario_suite(PHASE11_SUITE_PATH)
    summary = run_autonomous_browser_scenario_suite(suite, repo_root=PROJECT_ROOT).to_summary()

    assert summary["suite_id"] == "browser_phase11_fixture_suite_v1"
    assert summary["scenario_count"] == 2
    assert summary["scenarios_passed"] == 2
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
    assert "supersecret" not in json.dumps(summary)

    scenario_summaries = {item["scenario_id"]: item for item in summary["scenario_summaries"]}
    assert scenario_summaries["browser_ticket_triage_review"]["status"] == "passed"
    assert scenario_summaries["browser_approval_form_review"]["status"] == "passed"
    assert scenario_summaries["browser_ticket_triage_review"]["browser_coverage"]["action_coverage_ratio"] == 1.0
    assert scenario_summaries["browser_approval_form_review"]["browser_coverage"]["action_coverage_ratio"] == 1.0


def test_phase11_fixture_suite_outputs_only_relative_paths_and_local_urls() -> None:
    suite = load_autonomous_browser_scenario_suite(PHASE11_SUITE_PATH)
    summary = run_autonomous_browser_scenario_suite(suite, repo_root=PROJECT_ROOT).to_summary()
    payload = json.dumps(summary)

    assert all(not Path(path).is_absolute() for path in suite.scenario_paths)
    assert "http://example.com" not in payload
    assert "https://example.com" not in payload
    assert "C:\\" not in payload
    assert "fixtures/local_intranet/office_site_v1/site_manifest.json" not in payload
    assert summary["no_runtime_execution"] is True
    for scenario in summary["scenario_summaries"]:
        assert scenario["no_runtime_execution"] is True
        for session in scenario["browser_sessions"].values():
            assert session["policy_flags"]["fixture_mode"] is True
            assert session["policy_flags"]["playwright_enabled"] is False
            assert session["policy_denials"] == 0
