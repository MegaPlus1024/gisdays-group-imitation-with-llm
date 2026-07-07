from __future__ import annotations

from collections.abc import Mapping, Sequence
from typing import Any


BROWSER_SCENARIO_COVERAGE_SCHEMA_VERSION = "autonomous_browser_scenario_coverage_v1"


def build_browser_scenario_coverage(scenario: Any, scenario_summary: Mapping[str, Any]) -> dict[str, Any]:
    """Build deterministic offline browser coverage from scripted scenario/runtime summary data."""
    required_actions = sorted(
        {
            str(getattr(step, "action_name", ""))
            for step in getattr(scenario, "scripted_steps", ())
            if str(getattr(step, "action_name", "")).strip()
        }
    )
    events = _events(scenario_summary)
    succeeded_events = [
        event
        for event in events
        if event.get("event_type") == "action_succeeded"
        and _metadata_action_name(event) in required_actions
    ]
    failed_events = [
        event
        for event in events
        if event.get("event_type") == "action_failed"
        and _metadata_action_name(event) in required_actions
    ]
    observed_events = [event for event in events if event.get("event_type") == "browser_action_observed"]
    executed_actions = sorted(
        {
            action_name
            for action_name in (_metadata_action_name(event) for event in succeeded_events + failed_events)
            if action_name
        }
    )
    required_set = set(required_actions)
    covered_actions = required_set.intersection(executed_actions)

    sessions = _browser_sessions(scenario_summary)
    expected_results = scenario_summary.get("expected_results", [])
    passed = 0
    failed = 0
    if isinstance(expected_results, list):
        for result in expected_results:
            if not isinstance(result, dict):
                continue
            if result.get("passed") is True:
                passed += 1
            else:
                failed += 1

    return {
        "schema_version": BROWSER_SCENARIO_COVERAGE_SCHEMA_VERSION,
        "scenario_id": str(getattr(scenario, "scenario_id", scenario_summary.get("scenario_id", ""))),
        "actions_required": required_actions,
        "actions_executed": executed_actions,
        "actions_succeeded": len(succeeded_events),
        "actions_failed": len(failed_events),
        "action_coverage_ratio": (len(covered_actions) / len(required_set)) if required_set else 1.0,
        "agents_covered": sorted({str(event.get("agent_id")) for event in succeeded_events if event.get("agent_id")}),
        "tasks_covered": sorted({str(event.get("task_id")) for event in succeeded_events if event.get("task_id")}),
        "browser_sessions_covered": sorted(
            {
                session_id
                for session_id, session in sessions.items()
                if _int(session.get("actions_attempted", 0)) > 0
            }
        ),
        "policy_denial_count": _policy_denial_count(events, sessions),
        "expected_results_passed": passed,
        "expected_results_failed": failed,
        "browser_observation_count": len(observed_events),
    }


def _events(summary: Mapping[str, Any]) -> list[dict[str, Any]]:
    runtime_summary = summary.get("runtime_summary")
    events = runtime_summary.get("events") if isinstance(runtime_summary, dict) else []
    if not isinstance(events, list):
        return []
    return [event for event in events if isinstance(event, dict)]


def _browser_sessions(summary: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    sessions = summary.get("browser_session_summaries")
    if not isinstance(sessions, dict):
        return {}
    return {
        str(session_id): session
        for session_id, session in sessions.items()
        if isinstance(session, dict)
    }


def _metadata_action_name(event: Mapping[str, Any]) -> str:
    metadata = event.get("metadata")
    if not isinstance(metadata, dict):
        return ""
    action_name = metadata.get("action_name")
    return str(action_name) if isinstance(action_name, str) else ""


def _policy_denial_count(events: Sequence[Mapping[str, Any]], sessions: Mapping[str, Mapping[str, Any]]) -> int:
    event_denials = sum(1 for event in events if event.get("event_type") == "browser_policy_denied")
    session_denials = sum(_int(session.get("policy_denials", 0)) for session in sessions.values())
    return max(event_denials, session_denials)


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0
