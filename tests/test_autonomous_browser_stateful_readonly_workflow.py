from __future__ import annotations

import json
import shutil
from pathlib import Path
from typing import Any

from src.agent.autonomous_browser_stateful_readonly_workflow import (
    StatefulReadonlyWorkflowPolicy,
    StatefulReadonlyWorkflowScenarioDefinition,
    StatefulReadonlyWorkflowState,
    StatefulReadonlyWorkflowStep,
    build_default_stateful_readonly_workflow_scenarios,
    run_autonomous_browser_stateful_readonly_workflow,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
TEST_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/stateful_readonly_workflow_tests"


def _cleanup() -> None:
    shutil.rmtree(PROJECT_ROOT / TEST_OUTPUT_DIR, ignore_errors=True)


def _no_facts(*_args: Any, **_kwargs: Any) -> dict[str, Any]:
    return {}


def _workflow_path(path: str) -> Path:
    return PROJECT_ROOT / path


def test_state_serializes_to_json() -> None:
    state = StatefulReadonlyWorkflowState(
        workflow_id="wf_001",
        scenario_id="stateful_policy_search_marker_review",
        current_observation={"current_url": "https://local.intranet/docs/policy"},
        visited_urls=["https://local.intranet/"],
        facts={"policy_marker": "fixture-backed result for workspace policy review"},
        evidence_items=[
            {
                "evidence_item_id": "wf_001-evidence-1",
                "source_step_id": "inspect_policy",
                "source_url": "https://local.intranet/docs/policy",
                "text_preview": "Workspace Policy ...",
                "fact_keys": ["policy_marker"],
            }
        ],
        pending_objectives=["Find the workspace policy search marker."],
        final_answer="Workspace policy evidence marker: fixture-backed result for workspace policy review.",
        final_status="succeeded",
        trace_entries=[{"step_index": 1, "action_name": "browser_open_url"}],
    )

    encoded = json.dumps(state.to_dict(), ensure_ascii=False)

    assert json.loads(encoded)["workflow_id"] == "wf_001"


def test_scripted_stateful_scenario_succeeds_and_collects_facts() -> None:
    scenario = build_default_stateful_readonly_workflow_scenarios()["stateful_policy_ticket_crosscheck"]
    try:
        summary = run_autonomous_browser_stateful_readonly_workflow(
            scenario,
            repo_root=PROJECT_ROOT,
            output_dir=TEST_OUTPUT_DIR,
        )
        encoded = json.dumps(summary, ensure_ascii=False)

        assert summary["schema_version"] == "autonomous_browser_stateful_readonly_workflow_summary_v1"
        assert summary["status"] == "succeeded"
        assert summary["error_code"] is None
        assert summary["failure_class"] == "none"
        assert summary["steps_attempted"] == 6
        assert summary["steps_succeeded"] == 6
        assert summary["steps_failed"] == 0
        assert summary["actions_attempted"] == 6
        assert summary["actions_succeeded"] == 6
        assert summary["actions_failed"] == 0
        assert summary["facts_collected_total"] >= 4
        assert summary["evidence_items_total"] >= 2
        assert summary["final_answer"]
        assert summary["real_browser_execution"] is False
        assert summary["playwright_execution"] is False
        assert summary["browser_opened"] is True
        assert summary["real_network_traffic"] is False
        assert summary["fixture_only"] is True
        assert summary["no_runtime_execution"] is True
        assert not Path(summary["state_path"]).is_absolute()
        assert not Path(summary["trace_path"]).is_absolute()
        assert not Path(summary["summary_path"]).is_absolute()
        assert "C:\\" not in encoded
        assert str(PROJECT_ROOT) not in encoded

        state_payload = json.loads(_workflow_path(summary["state_path"]).read_text(encoding="utf-8"))
        assert state_payload["workflow_id"] == "stateful_policy_ticket_crosscheck"
        assert state_payload["evidence_items"]
        first_evidence = state_payload["evidence_items"][0]
        assert first_evidence["source_step_id"]
        assert first_evidence["source_url"]
        assert first_evidence["text_preview"]
    finally:
        _cleanup()


def test_read_only_policy_rejects_disallowed_action_without_crash() -> None:
    scenario = StatefulReadonlyWorkflowScenarioDefinition(
        scenario_id="stateful_policy_search_marker_review",
        workflow_id="wf_policy_reject",
        start_url="https://local.intranet/",
        objective="Reject a disallowed action.",
        steps=(
            StatefulReadonlyWorkflowStep(
                step_id="attempt_submit",
                action_name="browser_submit_form",
                parameters={"form_id": "local_form"},
                expected_text="",
            ),
        ),
        final_answer_builder=lambda state: "unreachable",  # pragma: no cover - not reached on rejection.
        fact_extractor=lambda observation, step, state: {},  # pragma: no cover - not reached on rejection.
        read_only_policy=StatefulReadonlyWorkflowPolicy(),
    )
    try:
        summary = run_autonomous_browser_stateful_readonly_workflow(
            scenario,
            repo_root=PROJECT_ROOT,
            output_dir=TEST_OUTPUT_DIR,
        )

        assert summary["status"] == "rejected"
        assert summary["error_code"] == "action_not_allowed_by_scenario_policy"
        assert summary["failure_class"] == "scenario_policy_rejected"
        assert summary["steps_attempted"] == 1
        assert summary["steps_failed"] == 1
        assert summary["actions_attempted"] == 0
        assert summary["actions_succeeded"] == 0
        assert summary["browser_opened"] is False
        assert summary["no_runtime_execution"] is True
    finally:
        _cleanup()


def test_failure_class_distinguishes_script_error() -> None:
    scenario = StatefulReadonlyWorkflowScenarioDefinition(
        scenario_id="stateful_policy_search_marker_review",
        workflow_id="wf_script_error",
        start_url="https://local.intranet/",
        objective="Reject a malformed scripted step.",
        steps=(
            StatefulReadonlyWorkflowStep(
                step_id="",
                action_name="browser_open_url",
                parameters={"url": "https://local.intranet/"},
                expected_text="Office Intranet",
            ),
        ),
        final_answer_builder=lambda state: "unreachable",  # pragma: no cover - not reached on failure.
        fact_extractor=_no_facts,  # pragma: no cover - not reached on failure.
    )
    try:
        summary = run_autonomous_browser_stateful_readonly_workflow(
            scenario,
            repo_root=PROJECT_ROOT,
            output_dir=TEST_OUTPUT_DIR,
        )

        assert summary["status"] == "failed"
        assert summary["error_code"] == "script_error"
        assert summary["failure_class"] == "script_error"
        assert summary["steps_attempted"] == 1
        assert summary["steps_failed"] == 1
        assert summary["actions_attempted"] == 0
        assert summary["browser_opened"] is False
    finally:
        _cleanup()

