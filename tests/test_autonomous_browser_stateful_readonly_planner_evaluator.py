from __future__ import annotations

import builtins
import importlib.util
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_stateful_readonly_planner_evaluator import (
    SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_stateful_readonly_planner_evaluator,
)
from src.agent.autonomous_browser_stateful_readonly_planner_packet import (
    build_autonomous_browser_stateful_readonly_planner_packet,
)
from src.agent.autonomous_browser_stateful_readonly_workflow import build_default_stateful_readonly_workflow_scenarios


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_stateful_readonly_planner_packet.example.json"
CLI_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_stateful_readonly_planner_evaluator.py"
PACKET_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_packets/stateful_readonly_planner"
EVALUATOR_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_summaries/stateful_readonly_planner_evaluator"


def _packet_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _load_cli_module(path: Path):
    spec = importlib.util.spec_from_file_location(path.stem, path)
    assert spec is not None and spec.loader is not None
    module = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(module)
    return module


def _build_packet(tmp_path: Path) -> tuple[dict[str, Any], Path]:
    summary = build_autonomous_browser_stateful_readonly_planner_packet(_packet_config(), repo_root=tmp_path)
    return summary, tmp_path / PACKET_OUTPUT_DIR


def _workflow_steps(scenario) -> list[dict[str, Any]]:
    steps: list[dict[str, Any]] = []
    for step in scenario.steps:
        item: dict[str, Any] = {
            "step_id": step.step_id,
            "action_name": step.action_name,
            "parameters": dict(step.parameters),
        }
        if step.expected_text:
            item["expected_text"] = step.expected_text
        if step.expected_url is not None:
            item["expected_url"] = step.expected_url
        if step.collect_fact_keys:
            item["collect_fact_keys"] = list(step.collect_fact_keys)
        steps.append(item)
    return steps


def _policy_ticket_output(scenario) -> dict[str, Any]:
    actions = _workflow_steps(scenario)
    facts = [
        {
            "fact_id": "policy_ticket_fact_1",
            "key": "ticket_id",
            "value": "Ticket 1",
            "source_step_id": "inspect_ticket",
            "source_url": "https://local.intranet/tickets/1",
            "evidence_item_id": "stateful_policy_ticket_crosscheck-evidence-1",
        },
        {
            "fact_id": "policy_ticket_fact_2",
            "key": "ticket_topic",
            "value": "Quarterly Access Review",
            "source_step_id": "inspect_ticket",
            "source_url": "https://local.intranet/tickets/1",
            "evidence_item_id": "stateful_policy_ticket_crosscheck-evidence-1",
        },
        {
            "fact_id": "policy_ticket_fact_3",
            "key": "ticket_priority",
            "value": "high",
            "source_step_id": "inspect_ticket",
            "source_url": "https://local.intranet/tickets/1",
            "evidence_item_id": "stateful_policy_ticket_crosscheck-evidence-1",
        },
        {
            "fact_id": "policy_ticket_fact_4",
            "key": "ticket_role",
            "value": "office worker",
            "source_step_id": "inspect_ticket",
            "source_url": "https://local.intranet/tickets/1",
            "evidence_item_id": "stateful_policy_ticket_crosscheck-evidence-1",
        },
        {
            "fact_id": "policy_ticket_fact_5",
            "key": "ticket_status",
            "value": "open",
            "source_step_id": "inspect_ticket",
            "source_url": "https://local.intranet/tickets/1",
            "evidence_item_id": "stateful_policy_ticket_crosscheck-evidence-1",
        },
        {
            "fact_id": "policy_ticket_fact_6",
            "key": "policy_anchor",
            "value": "Workspace Policy",
            "source_step_id": "inspect_policy",
            "source_url": "https://local.intranet/docs/policy",
            "evidence_item_id": "stateful_policy_ticket_crosscheck-evidence-2",
        },
        {
            "fact_id": "policy_ticket_fact_7",
            "key": "policy_marker",
            "value": "fixture-backed result for workspace policy review",
            "source_step_id": "inspect_policy",
            "source_url": "https://local.intranet/docs/policy",
            "evidence_item_id": "stateful_policy_ticket_crosscheck-evidence-2",
        },
    ]
    evidence_items = [
        {
            "evidence_item_id": "stateful_policy_ticket_crosscheck-evidence-1",
            "source_step_id": "inspect_ticket",
            "source_url": "https://local.intranet/tickets/1",
            "text_preview": "Ticket 1 - Quarterly Access Review | Priority: high. | Assigned role: office worker.",
            "fact_ids": [
                "policy_ticket_fact_1",
                "policy_ticket_fact_2",
                "policy_ticket_fact_3",
                "policy_ticket_fact_4",
                "policy_ticket_fact_5",
            ],
        },
        {
            "evidence_item_id": "stateful_policy_ticket_crosscheck-evidence-2",
            "source_step_id": "inspect_policy",
            "source_url": "https://local.intranet/docs/policy",
            "text_preview": "Workspace Policy | fixture-backed result for workspace policy review.",
            "fact_ids": [
                "policy_ticket_fact_6",
                "policy_ticket_fact_7",
            ],
        },
    ]
    final_answer = {
        "answer_text": "Ticket 1 is high priority for an office worker, and the workspace policy marker matches the fixture-backed review.",
        "cited_fact_ids": ["policy_ticket_fact_1", "policy_ticket_fact_3", "policy_ticket_fact_6"],
        "cited_evidence_item_ids": [
            "stateful_policy_ticket_crosscheck-evidence-1",
            "stateful_policy_ticket_crosscheck-evidence-2",
        ],
        "confidence": "medium",
    }
    return {
        "schema_version": "autonomous_browser_stateful_readonly_planner_output_v1",
        "scenario_id": scenario.scenario_id,
        "workflow_id": scenario.workflow_id,
        "goal": scenario.objective,
        "actions": actions,
        "facts": facts,
        "evidence_items": evidence_items,
        "final_answer": final_answer,
        "done_reason": "task_completed",
    }


def _approval_output(scenario) -> dict[str, Any]:
    actions = _workflow_steps(scenario)
    facts = [
        {
            "fact_id": "approval_fact_1",
            "key": "approval_request",
            "value": "APR-51",
            "source_step_id": "inspect_approval_match",
            "source_url": "https://local.intranet/portal/approval-match",
            "evidence_item_id": "stateful_approval_policy_crosscheck-evidence-1",
        },
        {
            "fact_id": "approval_fact_2",
            "key": "approval_policy_anchor",
            "value": "Approval Policy Match",
            "source_step_id": "inspect_approval_match",
            "source_url": "https://local.intranet/portal/approval-match",
            "evidence_item_id": "stateful_approval_policy_crosscheck-evidence-1",
        },
        {
            "fact_id": "approval_fact_3",
            "key": "approval_policy_marker",
            "value": "Policy match: confirmed.",
            "source_step_id": "inspect_approval_match",
            "source_url": "https://local.intranet/portal/approval-match",
            "evidence_item_id": "stateful_approval_policy_crosscheck-evidence-1",
        },
        {
            "fact_id": "approval_fact_4",
            "key": "approval_decision_note",
            "value": "local fixtures only",
            "source_step_id": "inspect_approval_match",
            "source_url": "https://local.intranet/portal/approval-match",
            "evidence_item_id": "stateful_approval_policy_crosscheck-evidence-1",
        },
        {
            "fact_id": "approval_fact_5",
            "key": "policy_anchor",
            "value": "Workspace Policy",
            "source_step_id": "inspect_policy",
            "source_url": "https://local.intranet/docs/policy",
            "evidence_item_id": "stateful_approval_policy_crosscheck-evidence-2",
        },
        {
            "fact_id": "approval_fact_6",
            "key": "policy_marker",
            "value": "fixture-backed result for workspace policy review",
            "source_step_id": "inspect_policy",
            "source_url": "https://local.intranet/docs/policy",
            "evidence_item_id": "stateful_approval_policy_crosscheck-evidence-2",
        },
    ]
    evidence_items = [
        {
            "evidence_item_id": "stateful_approval_policy_crosscheck-evidence-1",
            "source_step_id": "inspect_approval_match",
            "source_url": "https://local.intranet/portal/approval-match",
            "text_preview": "Approval Policy Match | Request id: APR-51. | Policy match: confirmed. | Decision note: local fixtures only.",
            "fact_ids": [
                "approval_fact_1",
                "approval_fact_2",
                "approval_fact_3",
                "approval_fact_4",
            ],
        },
        {
            "evidence_item_id": "stateful_approval_policy_crosscheck-evidence-2",
            "source_step_id": "inspect_policy",
            "source_url": "https://local.intranet/docs/policy",
            "text_preview": "Workspace Policy | fixture-backed result for workspace policy review.",
            "fact_ids": [
                "approval_fact_5",
                "approval_fact_6",
            ],
        },
    ]
    final_answer = {
        "answer_text": "APR-51 matches the approval policy review, and the workspace policy marker confirms the fixture-backed local path.",
        "cited_fact_ids": ["approval_fact_1", "approval_fact_2", "approval_fact_3"],
        "cited_evidence_item_ids": [
            "stateful_approval_policy_crosscheck-evidence-1",
            "stateful_approval_policy_crosscheck-evidence-2",
        ],
        "confidence": "high",
    }
    return {
        "schema_version": "autonomous_browser_stateful_readonly_planner_output_v1",
        "scenario_id": scenario.scenario_id,
        "workflow_id": scenario.workflow_id,
        "goal": scenario.objective,
        "actions": actions,
        "facts": facts,
        "evidence_items": evidence_items,
        "final_answer": final_answer,
        "done_reason": "task_completed",
    }


def _overview_output(scenario) -> dict[str, Any]:
    actions = _workflow_steps(scenario)
    facts = [
        {
            "fact_id": "overview_fact_1",
            "key": "home_anchor",
            "value": "Office Intranet",
            "source_step_id": "open_home",
            "source_url": "https://local.intranet/",
            "evidence_item_id": "stateful_intranet_overview_digest-evidence-1",
        },
        {
            "fact_id": "overview_fact_2",
            "key": "ticket_board_anchor",
            "value": "Ticket Board",
            "source_step_id": "click_ticket_board",
            "source_url": "https://local.intranet/tickets",
            "evidence_item_id": "stateful_intranet_overview_digest-evidence-2",
        },
        {
            "fact_id": "overview_fact_3",
            "key": "policy_anchor",
            "value": "Workspace Policy",
            "source_step_id": "open_policy",
            "source_url": "https://local.intranet/docs/policy",
            "evidence_item_id": "stateful_intranet_overview_digest-evidence-3",
        },
        {
            "fact_id": "overview_fact_4",
            "key": "team_status_anchor",
            "value": "Team Status",
            "source_step_id": "open_team_status",
            "source_url": "https://local.intranet/team/status",
            "evidence_item_id": "stateful_intranet_overview_digest-evidence-4",
        },
    ]
    evidence_items = [
        {
            "evidence_item_id": "stateful_intranet_overview_digest-evidence-1",
            "source_step_id": "open_home",
            "source_url": "https://local.intranet/",
            "text_preview": "Office Intranet | Ticket board | Workspace policy | Team status | Approvals queue.",
            "fact_ids": ["overview_fact_1"],
        },
        {
            "evidence_item_id": "stateful_intranet_overview_digest-evidence-2",
            "source_step_id": "click_ticket_board",
            "source_url": "https://local.intranet/tickets",
            "text_preview": "Ticket Board | Home | Ticket 1 | Team status | Open tickets.",
            "fact_ids": ["overview_fact_2"],
        },
        {
            "evidence_item_id": "stateful_intranet_overview_digest-evidence-3",
            "source_step_id": "open_policy",
            "source_url": "https://local.intranet/docs/policy",
            "text_preview": "Workspace Policy | Search marker: fixture-backed result for workspace policy review.",
            "fact_ids": ["overview_fact_3"],
        },
        {
            "evidence_item_id": "stateful_intranet_overview_digest-evidence-4",
            "source_step_id": "open_team_status",
            "source_url": "https://local.intranet/team/status",
            "text_preview": "Team Status | Office worker: reviewing ticket updates.",
            "fact_ids": ["overview_fact_4"],
        },
    ]
    final_answer = {
        "answer_text": "The intranet home, ticket board, policy, and team status pages all present the local fixture paths and anchors.",
        "cited_fact_ids": ["overview_fact_1", "overview_fact_2", "overview_fact_3", "overview_fact_4"],
        "cited_evidence_item_ids": [
            "stateful_intranet_overview_digest-evidence-1",
            "stateful_intranet_overview_digest-evidence-2",
            "stateful_intranet_overview_digest-evidence-3",
            "stateful_intranet_overview_digest-evidence-4",
        ],
        "confidence": "low",
    }
    return {
        "schema_version": "autonomous_browser_stateful_readonly_planner_output_v1",
        "scenario_id": scenario.scenario_id,
        "workflow_id": scenario.workflow_id,
        "goal": scenario.objective,
        "actions": actions,
        "facts": facts,
        "evidence_items": evidence_items,
        "final_answer": final_answer,
        "done_reason": "task_completed",
    }


def _ticket_priority_output(scenario) -> dict[str, Any]:
    actions = _workflow_steps(scenario)
    facts = [
        {
            "fact_id": "ticket_priority_fact_1",
            "key": "ticket_7_id",
            "value": "Ticket 7",
            "source_step_id": "inspect_ticket_7",
            "source_url": "https://local.intranet/tickets/7",
            "evidence_item_id": "stateful_ticket_priority_digest-evidence-1",
        },
        {
            "fact_id": "ticket_priority_fact_2",
            "key": "ticket_7_topic",
            "value": "Escalation Review",
            "source_step_id": "inspect_ticket_7",
            "source_url": "https://local.intranet/tickets/7",
            "evidence_item_id": "stateful_ticket_priority_digest-evidence-1",
        },
        {
            "fact_id": "ticket_priority_fact_3",
            "key": "ticket_7_priority",
            "value": "urgent",
            "source_step_id": "inspect_ticket_7",
            "source_url": "https://local.intranet/tickets/7",
            "evidence_item_id": "stateful_ticket_priority_digest-evidence-1",
        },
        {
            "fact_id": "ticket_priority_fact_4",
            "key": "ticket_7_requester_tier",
            "value": "facilities",
            "source_step_id": "inspect_ticket_7",
            "source_url": "https://local.intranet/tickets/7",
            "evidence_item_id": "stateful_ticket_priority_digest-evidence-1",
        },
        {
            "fact_id": "ticket_priority_fact_5",
            "key": "ticket_7_marker",
            "value": "the escalation ticket is the urgent one",
            "source_step_id": "inspect_ticket_7",
            "source_url": "https://local.intranet/tickets/7",
            "evidence_item_id": "stateful_ticket_priority_digest-evidence-1",
        },
        {
            "fact_id": "ticket_priority_fact_6",
            "key": "ticket_8_id",
            "value": "Ticket 8",
            "source_step_id": "inspect_ticket_8",
            "source_url": "https://local.intranet/tickets/8",
            "evidence_item_id": "stateful_ticket_priority_digest-evidence-2",
        },
        {
            "fact_id": "ticket_priority_fact_7",
            "key": "ticket_8_topic",
            "value": "Follow-up Note",
            "source_step_id": "inspect_ticket_8",
            "source_url": "https://local.intranet/tickets/8",
            "evidence_item_id": "stateful_ticket_priority_digest-evidence-2",
        },
        {
            "fact_id": "ticket_priority_fact_8",
            "key": "ticket_8_priority",
            "value": "low",
            "source_step_id": "inspect_ticket_8",
            "source_url": "https://local.intranet/tickets/8",
            "evidence_item_id": "stateful_ticket_priority_digest-evidence-2",
        },
        {
            "fact_id": "ticket_priority_fact_9",
            "key": "ticket_8_requester_tier",
            "value": "office worker",
            "source_step_id": "inspect_ticket_8",
            "source_url": "https://local.intranet/tickets/8",
            "evidence_item_id": "stateful_ticket_priority_digest-evidence-2",
        },
        {
            "fact_id": "ticket_priority_fact_10",
            "key": "ticket_8_marker",
            "value": "decoy for the priority cross-check",
            "source_step_id": "inspect_ticket_8",
            "source_url": "https://local.intranet/tickets/8",
            "evidence_item_id": "stateful_ticket_priority_digest-evidence-2",
        },
    ]
    evidence_items = [
        {
            "evidence_item_id": "stateful_ticket_priority_digest-evidence-1",
            "source_step_id": "inspect_ticket_7",
            "source_url": "https://local.intranet/tickets/7",
            "text_preview": "Ticket 7 - Escalation Review | Priority: urgent. | Requester tier: facilities.",
            "fact_ids": [
                "ticket_priority_fact_1",
                "ticket_priority_fact_2",
                "ticket_priority_fact_3",
                "ticket_priority_fact_4",
                "ticket_priority_fact_5",
            ],
        },
        {
            "evidence_item_id": "stateful_ticket_priority_digest-evidence-2",
            "source_step_id": "inspect_ticket_8",
            "source_url": "https://local.intranet/tickets/8",
            "text_preview": "Ticket 8 - Follow-up Note | Priority: low. | Search marker: this page is the decoy for the priority cross-check.",
            "fact_ids": [
                "ticket_priority_fact_6",
                "ticket_priority_fact_7",
                "ticket_priority_fact_8",
                "ticket_priority_fact_9",
                "ticket_priority_fact_10",
            ],
        },
    ]
    final_answer = {
        "answer_text": "Ticket 7 is the urgent escalation review and Ticket 8 is the decoy.",
        "cited_fact_ids": ["ticket_priority_fact_3", "ticket_priority_fact_4", "ticket_priority_fact_8"],
        "cited_evidence_item_ids": [
            "stateful_ticket_priority_digest-evidence-1",
            "stateful_ticket_priority_digest-evidence-2",
        ],
        "confidence": "medium",
    }
    return {
        "schema_version": "autonomous_browser_stateful_readonly_planner_output_v1",
        "scenario_id": scenario.scenario_id,
        "workflow_id": scenario.workflow_id,
        "goal": scenario.objective,
        "actions": actions,
        "facts": facts,
        "evidence_items": evidence_items,
        "final_answer": final_answer,
        "done_reason": "task_completed",
    }


def _policy_marker_output(scenario) -> dict[str, Any]:
    actions = _workflow_steps(scenario)
    facts = [
        {
            "fact_id": "policy_marker_fact_1",
            "key": "policy_anchor",
            "value": "Workspace Policy",
            "source_step_id": "inspect_policy",
            "source_url": "https://local.intranet/docs/policy",
            "evidence_item_id": "stateful_policy_search_marker_review-evidence-1",
        },
        {
            "fact_id": "policy_marker_fact_2",
            "key": "policy_marker",
            "value": "fixture-backed result for workspace policy review",
            "source_step_id": "inspect_policy",
            "source_url": "https://local.intranet/docs/policy",
            "evidence_item_id": "stateful_policy_search_marker_review-evidence-1",
        },
    ]
    evidence_items = [
        {
            "evidence_item_id": "stateful_policy_search_marker_review-evidence-1",
            "source_step_id": "inspect_policy",
            "source_url": "https://local.intranet/docs/policy",
            "text_preview": "Workspace Policy | fixture-backed result for workspace policy review.",
            "fact_ids": ["policy_marker_fact_1", "policy_marker_fact_2"],
        },
    ]
    final_answer = {
        "answer_text": "The workspace policy marker is the fixture-backed review result.",
        "cited_fact_ids": ["policy_marker_fact_1", "policy_marker_fact_2"],
        "cited_evidence_item_ids": ["stateful_policy_search_marker_review-evidence-1"],
        "confidence": "medium",
    }
    return {
        "schema_version": "autonomous_browser_stateful_readonly_planner_output_v1",
        "scenario_id": scenario.scenario_id,
        "workflow_id": scenario.workflow_id,
        "goal": scenario.objective,
        "actions": actions,
        "facts": facts,
        "evidence_items": evidence_items,
        "final_answer": final_answer,
        "done_reason": "task_completed",
    }


def _output_for_scenario(scenario) -> dict[str, Any]:
    if scenario.scenario_id == "stateful_policy_ticket_crosscheck":
        return _policy_ticket_output(scenario)
    if scenario.scenario_id == "stateful_approval_policy_crosscheck":
        return _approval_output(scenario)
    if scenario.scenario_id == "stateful_intranet_overview_digest":
        return _overview_output(scenario)
    if scenario.scenario_id == "stateful_ticket_priority_digest":
        return _ticket_priority_output(scenario)
    if scenario.scenario_id == "stateful_policy_search_marker_review":
        return _policy_marker_output(scenario)
    raise AssertionError(f"unexpected scenario id: {scenario.scenario_id}")


def _write_valid_outputs(packet_summary: dict[str, Any], repo_root: Path) -> None:
    _write_outputs(packet_summary, repo_root)


def _write_outputs(
    packet_summary: dict[str, Any],
    repo_root: Path,
    *,
    overrides: dict[str, dict[str, Any]] | None = None,
) -> None:
    overrides = overrides or {}
    for record in packet_summary["request_records"]:
        scenario_id = str(record["scenario_id"])
        scenario = build_default_stateful_readonly_workflow_scenarios()[scenario_id]
        payload = overrides.get(scenario_id) or _output_for_scenario(scenario)
        raw_output_path = repo_root / str(record["raw_output_path"])
        raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _output_copy(scenario_id: str) -> dict[str, Any]:
    scenario = build_default_stateful_readonly_workflow_scenarios()[scenario_id]
    return json.loads(json.dumps(_output_for_scenario(scenario)))


def _approval_output_missing_required_fact() -> dict[str, Any]:
    payload = _output_copy("stateful_approval_policy_crosscheck")
    facts = [fact for fact in payload["facts"] if fact["key"] != "approval_decision_note"]
    payload["facts"] = facts
    payload["final_answer"]["cited_fact_ids"] = [fact["fact_id"] for fact in facts]
    for evidence_item in payload["evidence_items"]:
        evidence_item["fact_ids"] = [fact_id for fact_id in evidence_item["fact_ids"] if fact_id != "approval_fact_4"]
    return payload


def _write_response_metadata(packet_summary: dict[str, Any], repo_root: Path, *, scenario_id: str, finish_reason: str) -> None:
    record = next(item for item in packet_summary["request_records"] if str(item["scenario_id"]) == scenario_id)
    response_path = repo_root / str(record["response_path"])
    response_path.parent.mkdir(parents=True, exist_ok=True)
    response_path.write_text(
        json.dumps(
            {
                "choices": [
                    {
                        "finish_reason": finish_reason,
                        "message": {"content": ""},
                    }
                ]
            },
            ensure_ascii=False,
            indent=2,
        ),
        encoding="utf-8",
    )


def test_dry_run_accepts_valid_outputs_without_fixture_execution(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    _write_valid_outputs(packet_summary, tmp_path)

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path)
    encoded = json.dumps(evaluation, ensure_ascii=False)

    assert evaluation["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert evaluation["status"] == "succeeded"
    assert evaluation["error_code"] is None
    assert evaluation["packet_id"] == "phase_13e2_stateful_readonly_local_planner"
    assert evaluation["outputs_total"] == 5
    assert evaluation["outputs_present"] == 5
    assert evaluation["outputs_missing"] == 0
    assert evaluation["outputs_ingested"] == 5
    assert evaluation["validation_accepted"] == 5
    assert evaluation["dry_runs_succeeded"] == 5
    assert evaluation["fixture_execution_requested"] is False
    assert evaluation["fixture_runs_succeeded"] == 5
    assert evaluation["actions_attempted_total"] == 0
    assert evaluation["expected_results_passed_total"] == 0
    assert evaluation["no_runtime_execution"] is True
    assert evaluation["model_execution"] is False
    assert evaluation["real_browser_execution"] is False
    assert evaluation["playwright_execution"] is False
    assert evaluation["browser_opened"] is False
    assert "C:\\" not in encoded
    assert str(tmp_path) not in encoded


def test_dry_run_accepts_outputs_without_confidence(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    overrides = {"stateful_policy_ticket_crosscheck": _output_copy("stateful_policy_ticket_crosscheck")}
    del overrides["stateful_policy_ticket_crosscheck"]["final_answer"]["confidence"]
    _write_outputs(packet_summary, tmp_path, overrides=overrides)

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path)

    assert evaluation["status"] == "succeeded"
    assert evaluation["validation_accepted"] == 5
    assert evaluation["dry_runs_succeeded"] == 5
    policy_summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_policy_ticket_crosscheck")
    assert policy_summary["status"] == "succeeded"
    assert policy_summary["validation_status"] == "accepted"
    assert policy_summary["dry_run_status"] == "accepted"


@pytest.mark.parametrize("confidence_value", ["certain", 2])
def test_invalid_confidence_rejected_with_allowed_values_and_field_path(
    tmp_path: Path,
    confidence_value: Any,
) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    payload = _output_copy("stateful_approval_policy_crosscheck")
    payload["final_answer"]["confidence"] = confidence_value
    _write_outputs(packet_summary, tmp_path, overrides={"stateful_approval_policy_crosscheck": payload})

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path, execute_fixture=True)
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_approval_policy_crosscheck")
    diagnostics = summary["diagnostics"]

    assert evaluation["status"] == "completed_with_failures"
    assert evaluation["error_code"] == "invalid_confidence"
    assert summary["status"] == "rejected"
    assert summary["failure_class"] == "model_failed_task"
    assert diagnostics[0]["finding_type"] == "invalid_confidence"
    assert diagnostics[0]["field_path"] == "final_answer.confidence"
    assert diagnostics[0]["path"] == "final_answer.confidence"
    assert diagnostics[0]["allowed_values"] == ["low", "medium", "high"]
    assert diagnostics[0]["present_value"] == confidence_value


def test_missing_required_fact_keys_diagnostics_include_required_present_missing_and_hint(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    payload = _approval_output_missing_required_fact()
    _write_outputs(packet_summary, tmp_path, overrides={"stateful_approval_policy_crosscheck": payload})

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path, execute_fixture=True)
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_approval_policy_crosscheck")
    diagnostics = summary["diagnostics"]

    assert evaluation["status"] == "completed_with_failures"
    assert evaluation["error_code"] == "missing_required_fact_keys"
    assert summary["status"] == "rejected"
    assert summary["failure_class"] == "model_failed_task"
    assert diagnostics[0]["finding_type"] == "missing_required_fact_keys"
    assert diagnostics[0]["path"] == "facts"
    assert diagnostics[0]["scenario_id"] == "stateful_approval_policy_crosscheck"
    assert diagnostics[0]["required_keys"] == [
        "approval_decision_note",
        "approval_policy_anchor",
        "approval_policy_marker",
        "approval_request",
    ]
    assert diagnostics[0]["present_keys"] == [
        "approval_policy_anchor",
        "approval_policy_marker",
        "approval_request",
        "policy_anchor",
        "policy_marker",
    ]
    assert diagnostics[0]["missing_keys"] == ["approval_decision_note"]
    assert diagnostics[0]["hint"] == "include every required fact key as a separate facts[] item"


def test_valid_approval_output_with_all_required_fact_keys_passes(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    _write_outputs(packet_summary, tmp_path, overrides={"stateful_approval_policy_crosscheck": _output_copy("stateful_approval_policy_crosscheck")})

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path, execute_fixture=True)
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_approval_policy_crosscheck")

    assert evaluation["status"] == "succeeded"
    assert summary["status"] == "succeeded"
    assert summary["validation_status"] == "accepted"
    assert summary["dry_run_status"] == "accepted"
    assert summary["fixture_execution_status"] == "succeeded"


def test_policy_ticket_prompt_marker_exact_value_passes(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    payload = _output_copy("stateful_policy_ticket_crosscheck")
    payload["facts"][6]["value"] = "fixture-backed result for workspace policy review"
    _write_outputs(packet_summary, tmp_path, overrides={"stateful_policy_ticket_crosscheck": payload})

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path, execute_fixture=True)
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_policy_ticket_crosscheck")

    assert evaluation["status"] == "succeeded"
    assert summary["status"] == "succeeded"
    assert summary["validation_status"] == "accepted"
    assert summary["dry_run_status"] == "accepted"
    assert summary["fixture_execution_status"] == "succeeded"


def test_policy_ticket_prompt_hallucinated_policy_marker_is_rejected(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    payload = _output_copy("stateful_policy_ticket_crosscheck")
    payload["facts"][6]["value"] = "High priority tickets require admin approval"
    payload["evidence_items"][1]["text_preview"] = "Section 4.2.1: High priority tickets require admin approval"
    _write_outputs(packet_summary, tmp_path, overrides={"stateful_policy_ticket_crosscheck": payload})

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path, execute_fixture=True)
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_policy_ticket_crosscheck")
    diagnostics = summary["diagnostics"]

    assert evaluation["status"] == "completed_with_failures"
    assert evaluation["error_code"] == "fact_value_mismatch"
    assert summary["status"] == "failed"
    assert summary["failure_class"] == "model_failed_task"
    fact_diag = diagnostics["fixture"]["fact_value_mismatch"]
    assert fact_diag["key"] == "policy_marker"
    assert fact_diag["expected_value"] == "fixture-backed result for workspace policy review"
    assert fact_diag["model_value"] == "High priority tickets require admin approval"


def test_text_span_fact_values_are_accepted(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    payload = _output_copy("stateful_ticket_priority_digest")
    payload["facts"][1]["value"] = "Escalation Review for the urgent ticket"
    payload["facts"][2]["value"] = "Urgent"
    _write_outputs(packet_summary, tmp_path, overrides={"stateful_ticket_priority_digest": payload})

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path, execute_fixture=True)
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_ticket_priority_digest")

    assert evaluation["status"] == "succeeded"
    assert summary["status"] == "succeeded"
    assert summary["validation_status"] == "accepted"
    assert summary["dry_run_status"] == "accepted"
    assert summary["fixture_execution_status"] == "succeeded"


def test_ticket_priority_digest_ticket_8_requester_tier_exact_value_passes(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    payload = _output_copy("stateful_ticket_priority_digest")
    payload["facts"][8]["value"] = "office worker"
    _write_outputs(packet_summary, tmp_path, overrides={"stateful_ticket_priority_digest": payload})

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path, execute_fixture=True)
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_ticket_priority_digest")

    assert evaluation["status"] == "succeeded"
    assert summary["status"] == "succeeded"
    assert summary["validation_status"] == "accepted"
    assert summary["dry_run_status"] == "accepted"
    assert summary["fixture_execution_status"] == "succeeded"


def test_ticket_priority_digest_ticket_8_requester_tier_hallucinated_general_is_rejected(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    payload = _output_copy("stateful_ticket_priority_digest")
    payload["facts"][8]["value"] = "general"
    payload["evidence_items"][1]["text_preview"] = "Ticket 8 - Follow-up Note | Requester tier: general. | Priority: low."
    _write_outputs(packet_summary, tmp_path, overrides={"stateful_ticket_priority_digest": payload})

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path, execute_fixture=True)
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_ticket_priority_digest")
    diagnostics = summary["diagnostics"]

    assert evaluation["status"] == "completed_with_failures"
    assert evaluation["error_code"] == "fact_value_mismatch"
    assert summary["status"] == "failed"
    assert summary["failure_class"] == "model_failed_task"
    fact_diag = diagnostics["fixture"]["fact_value_mismatch"]
    assert fact_diag["key"] == "ticket_8_requester_tier"
    assert fact_diag["expected_value"] == "office worker"
    assert fact_diag["model_value"] == "general"


def test_fact_value_mismatch_diagnostics_include_span_context(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    payload = _output_copy("stateful_ticket_priority_digest")
    payload["facts"][1]["value"] = "Wrong topic"
    _write_outputs(packet_summary, tmp_path, overrides={"stateful_ticket_priority_digest": payload})

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path, execute_fixture=True)
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_ticket_priority_digest")
    diagnostics = summary["diagnostics"]

    assert evaluation["status"] == "completed_with_failures"
    assert evaluation["error_code"] == "fact_value_mismatch"
    assert summary["status"] == "failed"
    assert summary["failure_class"] == "model_failed_task"
    fact_diag = diagnostics["fixture"]["fact_value_mismatch"]
    assert fact_diag["scenario_id"] == "stateful_ticket_priority_digest"
    assert fact_diag["trial_label"] == "stateful_ticket_priority_digest"
    assert fact_diag["key"] == "ticket_7_topic"
    assert fact_diag["expected_value"] == "Escalation Review"
    assert fact_diag["model_value"] == "Wrong topic"
    assert fact_diag["normalized_expected_value"] == "escalation review"
    assert fact_diag["normalized_model_value"] == "wrong topic"
    assert fact_diag["source_fact_id"] == "ticket_priority_fact_2"
    assert fact_diag["source_step_id"] == "inspect_ticket_7"
    assert fact_diag["source_output_path"].endswith("stateful_ticket_priority_digest/raw_planner_output.txt")
    assert "fixture evidence" in fact_diag["hint"]


def test_fixture_execution_succeeds_for_valid_outputs(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    _write_valid_outputs(packet_summary, tmp_path)

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(
        packet_dir,
        repo_root=tmp_path,
        execute_fixture=True,
    )

    assert evaluation["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert evaluation["status"] == "succeeded"
    assert evaluation["error_code"] is None
    assert evaluation["outputs_total"] == 5
    assert evaluation["outputs_present"] == 5
    assert evaluation["outputs_missing"] == 0
    assert evaluation["outputs_ingested"] == 5
    assert evaluation["validation_accepted"] == 5
    assert evaluation["dry_runs_succeeded"] == 5
    assert evaluation["fixture_execution_requested"] is True
    assert evaluation["fixture_runs_succeeded"] == 5
    assert evaluation["fixture_runs_failed"] == 0
    assert evaluation["workflows_succeeded"] == 5
    assert evaluation["workflows_failed"] == 0
    assert evaluation["actions_attempted_total"] == 26
    assert evaluation["actions_succeeded_total"] == 26
    assert evaluation["actions_failed_total"] == 0
    assert evaluation["expected_results_total"] == 26
    assert evaluation["expected_results_passed_total"] == 26
    assert evaluation["expected_results_failed_total"] == 0
    assert evaluation["real_browser_execution"] is False
    assert evaluation["playwright_execution"] is False
    assert evaluation["browser_opened"] is False
    assert evaluation["real_network_traffic"] is False
    assert evaluation["fixture_only"] is True
    assert evaluation["scenario_summaries"][0]["scenario_id"] == "stateful_policy_ticket_crosscheck"
    assert evaluation["scenario_summaries"][0]["route_stable"] is True
    assert evaluation["scenario_summaries"][0]["unique_matched_urls"] == ["https://local.intranet/docs/policy"]
    assert evaluation["scenario_summaries"][1]["scenario_id"] == "stateful_approval_policy_crosscheck"
    assert evaluation["scenario_summaries"][1]["route_stable"] is True
    assert evaluation["scenario_summaries"][1]["unique_matched_urls"] == ["https://local.intranet/docs/policy"]


def test_truncated_response_json_is_reported_before_raw_output_parsing(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    _write_valid_outputs(packet_summary, tmp_path)
    _write_response_metadata(
        packet_summary,
        tmp_path,
        scenario_id="stateful_ticket_priority_digest",
        finish_reason="length",
    )

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(
        packet_dir,
        repo_root=tmp_path,
        execute_fixture=True,
    )
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_ticket_priority_digest")
    diagnostics = summary["diagnostics"]

    assert evaluation["status"] == "completed_with_failures"
    assert evaluation["error_code"] == "truncated_model_output"
    assert summary["status"] == "rejected"
    assert summary["failure_class"] == "model_failed_task"
    assert summary["validation_status"] == "rejected"
    assert summary["dry_run_status"] == "rejected"
    assert summary["fixture_execution_status"] == "skipped"
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert diagnostics["source_output"]["finding_type"] == "truncated_model_output"
    assert diagnostics["source_output"]["finish_reason"] == "length"
    assert diagnostics["source_output"]["response_path"] == "artifacts/autonomous_runtime_planner_outputs/stateful_readonly_planner/third_model/stateful_ticket_priority_digest/response.json"
    assert diagnostics["source_output"]["raw_output_path"] == "artifacts/autonomous_runtime_planner_outputs/stateful_readonly_planner/third_model/stateful_ticket_priority_digest/raw_planner_output.txt"
    assert "increase max_tokens or reduce prompt/output length" in diagnostics["source_output"]["hint"]


def test_missing_action_field_diagnostics_include_index_and_present_fields(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    overrides = {
        "stateful_policy_ticket_crosscheck": {
            **_output_copy("stateful_policy_ticket_crosscheck"),
            "actions": [
                {
                    "step_id": "step_1",
                    "action": "browser_open_url",
                    "parameters": {"url": "https://local.intranet/"},
                }
            ],
        }
    }
    _write_outputs(packet_summary, tmp_path, overrides=overrides)

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path, execute_fixture=True)
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_policy_ticket_crosscheck")
    diagnostics = summary["diagnostics"]

    assert evaluation["status"] == "completed_with_failures"
    assert evaluation["error_code"] == "missing_action_field"
    assert summary["status"] == "rejected"
    assert summary["failure_class"] == "model_failed_task"
    assert diagnostics[0]["finding_type"] == "missing_action_field"
    assert diagnostics[0]["action_index"] == 0
    assert diagnostics[0]["present_fields"] == ["action", "parameters", "step_id"]
    assert diagnostics[0]["expected_field"] == "action_name"
    assert diagnostics[0]["hint"] == "use action_name, not action"


def test_facts_object_is_rejected_with_array_diagnostics(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    payload = _output_copy("stateful_policy_ticket_crosscheck")
    payload["facts"] = {"fact_id": "bad"}
    _write_outputs(packet_summary, tmp_path, overrides={"stateful_policy_ticket_crosscheck": payload})

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path, execute_fixture=True)
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_policy_ticket_crosscheck")
    diagnostics = summary["diagnostics"]

    assert evaluation["status"] == "completed_with_failures"
    assert evaluation["error_code"] == "invalid_facts_collection"
    assert summary["failure_class"] == "model_failed_task"
    assert diagnostics[0]["finding_type"] == "invalid_facts_collection"
    assert diagnostics[0]["facts_type"] == "dict"
    assert diagnostics[0]["expected_type"] == "array"


def test_evidence_item_id_alias_is_rejected_with_clear_diagnostics(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    payload = _output_copy("stateful_approval_policy_crosscheck")
    payload["evidence_items"][0] = {
        "id": "evidence_1",
        "source_step_id": "inspect_approval_match",
        "source_url": "https://local.intranet/portal/approval-match",
        "text_preview": "Approval Policy Match | Request id: APR-51.",
        "fact_ids": ["approval_fact_1"],
    }
    _write_outputs(packet_summary, tmp_path, overrides={"stateful_approval_policy_crosscheck": payload})

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path, execute_fixture=True)
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_approval_policy_crosscheck")
    diagnostics = summary["diagnostics"]

    assert evaluation["status"] == "completed_with_failures"
    assert evaluation["error_code"] == "missing_evidence_field"
    assert summary["failure_class"] == "model_failed_task"
    assert diagnostics[0]["finding_type"] == "missing_evidence_field"
    assert diagnostics[0]["evidence_item_index"] == 0
    assert diagnostics[0]["present_fields"] == ["fact_ids", "id", "source_step_id", "source_url", "text_preview"]
    assert diagnostics[0]["expected_id_field"] == "evidence_item_id"
    assert diagnostics[0]["hint"] == "use evidence_item_id, not id"


def test_final_answer_missing_citations_has_clear_diagnostics(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    payload = _output_copy("stateful_ticket_priority_digest")
    del payload["final_answer"]["cited_fact_ids"]
    del payload["final_answer"]["cited_evidence_item_ids"]
    _write_outputs(packet_summary, tmp_path, overrides={"stateful_ticket_priority_digest": payload})

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path, execute_fixture=True)
    summary = next(item for item in evaluation["output_summaries"] if item["scenario_id"] == "stateful_ticket_priority_digest")
    diagnostics = summary["diagnostics"]

    assert evaluation["status"] == "completed_with_failures"
    assert evaluation["error_code"] == "invalid_final_answer_citations"
    assert summary["failure_class"] == "model_failed_task"
    assert diagnostics[0]["finding_type"] == "invalid_final_answer_citations"
    assert diagnostics[0]["missing_fields"] == ["cited_fact_ids", "cited_evidence_item_ids"]
    assert diagnostics[0]["scenario_id"] == "stateful_ticket_priority_digest"
    assert diagnostics[0]["trial_label"] == "stateful_ticket_priority_digest"
    assert diagnostics[0]["path"] == "final_answer"
    assert diagnostics[0]["available_fact_ids"] == [
        "ticket_priority_fact_1",
        "ticket_priority_fact_2",
        "ticket_priority_fact_3",
        "ticket_priority_fact_4",
        "ticket_priority_fact_5",
        "ticket_priority_fact_6",
        "ticket_priority_fact_7",
        "ticket_priority_fact_8",
        "ticket_priority_fact_9",
        "ticket_priority_fact_10",
    ]
    assert diagnostics[0]["available_evidence_item_ids"] == [
        "stateful_ticket_priority_digest-evidence-1",
        "stateful_ticket_priority_digest-evidence-2",
    ]
    assert diagnostics[0]["missing_cited_fact_ids"] == diagnostics[0]["available_fact_ids"]
    assert diagnostics[0]["missing_cited_evidence_item_ids"] == diagnostics[0]["available_evidence_item_ids"]
    assert diagnostics[0]["hint"] == "include cited_fact_ids and cited_evidence_item_ids that reference existing facts and evidence items"


def test_missing_captured_output_returns_safe_failure(tmp_path: Path) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    request_records = packet_summary["request_records"]
    for record in request_records[:-1]:
        scenario = build_default_stateful_readonly_workflow_scenarios()[str(record["scenario_id"])]
        payload = _output_for_scenario(scenario)
        raw_output_path = tmp_path / str(record["raw_output_path"])
        raw_output_path.parent.mkdir(parents=True, exist_ok=True)
        raw_output_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")

    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(
        packet_dir,
        repo_root=tmp_path,
        execute_fixture=True,
    )
    encoded = json.dumps(evaluation, ensure_ascii=False)

    assert evaluation["status"] == "completed_with_missing_outputs"
    assert evaluation["error_code"] == "missing_captured_outputs"
    assert evaluation["outputs_total"] == 5
    assert evaluation["outputs_present"] == 4
    assert evaluation["outputs_missing"] == 1
    assert evaluation["outputs_ingested"] == 4
    assert evaluation["outputs_rejected"] == 0
    assert evaluation["fixture_runs_succeeded"] == 4
    assert evaluation["fixture_runs_failed"] == 0
    assert evaluation["no_runtime_execution"] is True
    assert evaluation["model_execution"] is False
    assert evaluation["real_browser_execution"] is False
    assert evaluation["playwright_execution"] is False
    assert evaluation["browser_opened"] is False
    assert "C:\\" not in encoded
    assert str(tmp_path) not in encoded


def test_cli_fixture_execution_succeeds_and_missing_outputs_fail(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    packet_summary, packet_dir = _build_packet(tmp_path)
    _write_valid_outputs(packet_summary, tmp_path)
    output_dir_rel = "cli-output"
    output_dir = tmp_path / output_dir_rel

    module = _load_cli_module(CLI_PATH)
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = tmp_path
    try:
        exit_code = module.main(["--packet-dir", str(packet_dir), "--output-dir", output_dir_rel, "--execute-fixture"])
    finally:
        module.PROJECT_ROOT = original_project_root

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 0
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert payload["status"] == "succeeded"
    assert payload["fixture_execution_requested"] is True
    assert payload["fixture_runs_succeeded"] == 5
    assert (output_dir / "autonomous_browser_stateful_readonly_planner_evaluator_summary.json").exists()

    missing_output_path = tmp_path / str(packet_summary["request_records"][-1]["raw_output_path"])
    missing_output_path.unlink()
    module = _load_cli_module(CLI_PATH)
    original_project_root = module.PROJECT_ROOT
    module.PROJECT_ROOT = tmp_path
    try:
        exit_code = module.main(["--packet-dir", str(packet_dir), "--output-dir", output_dir_rel, "--execute-fixture"])
    finally:
        module.PROJECT_ROOT = original_project_root

    payload = json.loads(capsys.readouterr().out)
    assert exit_code == 1
    assert payload["status"] == "completed_with_missing_outputs"
    assert payload["error_code"] == "missing_captured_outputs"


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    packet_summary, packet_dir = _build_packet(tmp_path)
    _write_valid_outputs(packet_summary, tmp_path)
    evaluation = run_autonomous_browser_stateful_readonly_planner_evaluator(packet_dir, repo_root=tmp_path)

    assert evaluation["status"] == "succeeded"
