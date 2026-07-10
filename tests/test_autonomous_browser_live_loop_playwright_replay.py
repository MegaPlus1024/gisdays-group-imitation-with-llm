from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_live_loop_playwright_replay import (
    CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    load_autonomous_browser_live_loop_playwright_replay_config,
    run_autonomous_browser_live_loop_playwright_replay,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_live_loop_playwright_replay.example.json"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_live_loop_playwright_replay.py"


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _base_config() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _config_for_temp_inputs(
    *,
    trace_paths: list[str],
    output_dir: str = "artifacts/live_loop_playwright_replay_tests",
    replay_backend: str = "playwright",
) -> dict[str, Any]:
    payload = _base_config()
    payload["input_trace_paths"] = trace_paths
    payload["input_variance_suite_summary"] = None
    payload["input_trace_root"] = None
    payload["output_dir"] = output_dir
    payload["replay_backend"] = replay_backend
    return payload


def _open_entry(step_index: int, url: str, *, title: str, text_preview: str) -> dict[str, Any]:
    return {
        "step_index": step_index,
        "observation_id": f"observation_{step_index:04d}",
        "planner_action": {
            "step_id": f"step_{step_index:04d}",
            "action_name": "browser_open_url",
            "parameters": {"url": url},
            "expected_text": title,
        },
        "validation_status": "accepted",
        "fixture_execution_status": "succeeded",
        "action_result": {
            "success": True,
            "output": {"current_url": url, "title": title, "text_preview": text_preview},
            "observation": {"current_url": url, "title": title, "text_preview": text_preview},
        },
        "expected_result": {"passed": True, "reason": "browser_expectations_met", "metadata": {}},
        "metadata": {},
        "next_observation_id": f"observation_{step_index + 1:04d}",
    }


def _skipped_click_entry(step_index: int, target_text: str, *, current_url: str, scenario_id: str) -> dict[str, Any]:
    return {
        "step_index": step_index,
        "observation_id": f"observation_{step_index:04d}",
        "planner_action": {
            "step_id": f"step_{step_index:04d}",
            "action_name": "browser_click",
            "parameters": {"target_text": target_text},
            "expected_text": "ignored",
        },
        "validation_status": "rejected",
        "fixture_execution_status": "skipped",
        "action_result": None,
        "expected_result": {
            "passed": False,
            "reason": "model_output_irrelevant_click_target",
            "metadata": {
                "scenario_id": scenario_id,
                "current_url": current_url,
                "target_text": target_text,
            },
        },
        "metadata": {
            "scenario_id": scenario_id,
            "current_url": current_url,
            "target_text": target_text,
        },
        "next_observation_id": f"observation_{step_index + 1:04d}",
    }


def _click_entry(
    step_index: int,
    *,
    target_text: str,
    current_url: str,
    title: str,
    text_preview: str,
    expected_text: str,
    expected_url: str,
    goal_satisfied: bool = False,
    scenario_id: str = "hard_ticket_priority_crosscheck",
) -> dict[str, Any]:
    metadata = {
        "goal_satisfied": goal_satisfied,
        "matched_completion_criteria": {
            "scenario_id": scenario_id,
            "matched_url": current_url,
            "any_text": [expected_text],
            "matched_text_anchors": [expected_text],
            "url": expected_url,
        },
    }
    return {
        "step_index": step_index,
        "observation_id": f"observation_{step_index:04d}",
        "planner_action": {
            "step_id": f"step_{step_index:04d}",
            "action_name": "browser_click",
            "parameters": {"target_text": target_text},
            "expected_text": expected_text,
            "expected_url": expected_url,
        },
        "validation_status": "accepted",
        "fixture_execution_status": "succeeded",
        "action_result": {
            "success": True,
            "output": {"current_url": current_url, "title": title, "text_preview": text_preview},
            "observation": {"current_url": current_url, "title": title, "text_preview": text_preview},
        },
        "expected_result": {
            "passed": True,
            "reason": "browser_expectations_met",
            "metadata": {"resolved_destination_url": expected_url},
        },
        "metadata": metadata,
        "next_observation_id": f"observation_{step_index + 1:04d}",
    }


def _policy_trace(scenario_id: str, trial_label: str, *, include_skipped: bool = True) -> dict[str, Any]:
    entries = [
        _open_entry(
            1,
            "https://local.intranet/",
            title="Office Intranet Home",
            text_preview="Office Intranet Home Workspace policy Ticket board Approvals queue",
        ),
    ]
    if include_skipped:
        entries.append(_skipped_click_entry(2, "Ticket board", current_url="https://local.intranet/", scenario_id=scenario_id))
    entries.append(
        _click_entry(
            3 if include_skipped else 2,
            target_text="Workspace policy",
            current_url="https://local.intranet/docs/policy",
            title="Workspace Policy",
            text_preview="Workspace Policy Allowed activity Search marker: fixture-backed result for workspace policy review.",
            expected_text="Workspace Policy",
            expected_url="https://local.intranet/docs/policy",
            goal_satisfied=True,
            scenario_id=scenario_id,
        )
    )
    return {
        "schema_version": "autonomous_browser_live_loop_trace_v1",
        "scenario_id": scenario_id,
        "observations_total": len(entries) + 1,
        "trace": entries,
    }


def _ticket_trace(scenario_id: str, trial_label: str, *, include_skipped: bool = True) -> dict[str, Any]:
    entries = [
        _open_entry(
            1,
            "https://local.intranet/",
            title="Office Intranet Home",
            text_preview="Office Intranet Home Ticket board Workspace policy Team status",
        ),
    ]
    if include_skipped:
        entries.append(_skipped_click_entry(2, "Workspace policy", current_url="https://local.intranet/", scenario_id=scenario_id))
    entries.append(
        {
            "step_index": 3 if include_skipped else 2,
            "observation_id": "observation_0003",
            "planner_action": {
                "step_id": "step_0003",
                "action_name": "browser_click",
                "parameters": {"target_text": "Ticket board"},
                "expected_text": "Ticket Board",
                "expected_url": "https://local.intranet/tickets",
            },
            "validation_status": "accepted",
            "fixture_execution_status": "succeeded",
            "action_result": {
                "success": True,
                "output": {
                    "current_url": "https://local.intranet/tickets",
                    "title": "Ticket Board",
                    "text_preview": "Ticket Board Home Ticket 1 Team status Open tickets",
                },
                "observation": {
                    "current_url": "https://local.intranet/tickets",
                    "title": "Ticket Board",
                    "text_preview": "Ticket Board Home Ticket 1 Team status Open tickets",
                },
            },
            "expected_result": {
                "passed": True,
                "reason": "browser_expectations_met",
                "metadata": {"resolved_destination_url": "https://local.intranet/tickets"},
            },
            "metadata": {},
            "next_observation_id": "observation_0004",
        }
    )
    entries.append(
        {
            "step_index": 4 if include_skipped else 3,
            "observation_id": "observation_0004",
            "planner_action": {
                "step_id": "step_0004",
                "action_name": "browser_click",
                "parameters": {"target_text": "Ticket 1"},
                "expected_text": "Ticket 1 - Quarterly Access Review",
                "expected_url": "https://local.intranet/tickets/1",
            },
            "validation_status": "accepted",
            "fixture_execution_status": "succeeded",
            "action_result": {
                "success": True,
                "output": {
                    "current_url": "https://local.intranet/tickets/1",
                    "title": "Ticket 1 - Quarterly Access Review",
                    "text_preview": "Ticket 1 - Quarterly Access Review Priority: high Assigned role: office worker Quarterly Access Review",
                },
                "observation": {
                    "current_url": "https://local.intranet/tickets/1",
                    "title": "Ticket 1 - Quarterly Access Review",
                    "text_preview": "Ticket 1 - Quarterly Access Review Priority: high Assigned role: office worker Quarterly Access Review",
                },
            },
            "expected_result": {
                "passed": True,
                "reason": "browser_expectations_met",
                "metadata": {"resolved_destination_url": "https://local.intranet/tickets/1"},
            },
            "metadata": {
                "goal_satisfied": True,
                "matched_completion_criteria": {
                    "scenario_id": scenario_id,
                    "matched_url": "https://local.intranet/tickets/1",
                    "any_text": [
                        "Ticket 1 - Quarterly Access Review",
                        "Priority: high",
                        "Assigned role: office worker",
                        "Quarterly Access Review",
                    ],
                    "matched_text_anchors": [
                        "Ticket 1 - Quarterly Access Review",
                        "Priority: high",
                        "Assigned role: office worker",
                        "Quarterly Access Review",
                    ],
                    "url": "https://local.intranet/tickets/1",
                },
            },
            "next_observation_id": "observation_0005",
        }
    )
    return {
        "schema_version": "autonomous_browser_live_loop_trace_v1",
        "scenario_id": scenario_id,
        "observations_total": len(entries) + 1,
        "trace": entries,
    }


def _approval_trace(scenario_id: str, trial_label: str, *, include_skipped: bool = True) -> dict[str, Any]:
    entries = [
        _open_entry(
            1,
            "https://local.intranet/",
            title="Office Intranet Home",
            text_preview="Office Intranet Home Approvals queue Workspace policy Team status",
        ),
    ]
    if include_skipped:
        entries.append(_skipped_click_entry(2, "Workspace policy", current_url="https://local.intranet/", scenario_id=scenario_id))
    entries.append(
        {
            "step_index": 3 if include_skipped else 2,
            "observation_id": "observation_0003",
            "planner_action": {
                "step_id": "step_0003",
                "action_name": "browser_click",
                "parameters": {"target_text": "Approvals queue"},
                "expected_text": "Approvals Queue",
                "expected_url": "https://local.intranet/portal/approvals",
            },
            "validation_status": "accepted",
            "fixture_execution_status": "succeeded",
            "action_result": {
                "success": True,
                "output": {
                    "current_url": "https://local.intranet/portal/approvals",
                    "title": "Approvals Queue",
                    "text_preview": "Approvals Queue Portal home Approval status Pending approval check",
                },
                "observation": {
                    "current_url": "https://local.intranet/portal/approvals",
                    "title": "Approvals Queue",
                    "text_preview": "Approvals Queue Portal home Approval status Pending approval check",
                },
            },
            "expected_result": {
                "passed": True,
                "reason": "browser_expectations_met",
                "metadata": {"resolved_destination_url": "https://local.intranet/portal/approvals"},
            },
            "metadata": {},
            "next_observation_id": "observation_0004",
        }
    )
    entries.append(
        {
            "step_index": 4 if include_skipped else 3,
            "observation_id": "observation_0004",
            "planner_action": {
                "step_id": "step_0004",
                "action_name": "browser_click",
                "parameters": {"target_text": "Policy match review"},
                "expected_text": "Approval Policy Match",
                "expected_url": "https://local.intranet/portal/approval-match",
            },
            "validation_status": "accepted",
            "fixture_execution_status": "succeeded",
            "action_result": {
                "success": True,
                "output": {
                    "current_url": "https://local.intranet/portal/approval-match",
                    "title": "Approval Policy Match",
                    "text_preview": "Approval Policy Match Local-only approval review Policy match: confirmed.",
                },
                "observation": {
                    "current_url": "https://local.intranet/portal/approval-match",
                    "title": "Approval Policy Match",
                    "text_preview": "Approval Policy Match Local-only approval review Policy match: confirmed.",
                },
            },
            "expected_result": {
                "passed": True,
                "reason": "browser_expectations_met",
                "metadata": {"resolved_destination_url": "https://local.intranet/portal/approval-match"},
            },
            "metadata": {
                "goal_satisfied": True,
                "matched_completion_criteria": {
                    "scenario_id": scenario_id,
                    "matched_url": "https://local.intranet/portal/approval-match",
                    "any_text": [
                        "Approval Policy Match",
                        "Local-only approval review",
                        "Policy match: confirmed.",
                    ],
                    "matched_text_anchors": [
                        "Approval Policy Match",
                        "Local-only approval review",
                        "Policy match: confirmed.",
                    ],
                    "url": "https://local.intranet/portal/approval-match",
                },
            },
            "next_observation_id": "observation_0005",
        }
    )
    return {
        "schema_version": "autonomous_browser_live_loop_trace_v1",
        "scenario_id": scenario_id,
        "observations_total": len(entries) + 1,
        "trace": entries,
    }


def _variance_summary(trial_rows: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "schema_version": "autonomous_browser_live_loop_variance_suite_summary_v1",
        "suite_id": "phase_13c_guarded_local_model_live_loop_variance",
        "trial_summaries": trial_rows,
    }


def _trial_row(
    scenario_id: str,
    trial_index: int,
    trial_label: str,
    trace_path: str,
    *,
    status: str = "succeeded",
    matched_url: str | None = None,
) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "trial_index": trial_index,
        "trial_label": trial_label,
        "trace_path": trace_path,
        "status": status,
        "matched_url": matched_url,
    }


def test_example_config_loads_with_relative_paths() -> None:
    config = load_autonomous_browser_live_loop_playwright_replay_config(CONFIG_PATH)

    assert config.schema_version == CONFIG_SCHEMA_VERSION
    assert config.suite_id == "phase_13d_guarded_playwright_replay_live_loop_traces"
    assert config.input_variance_suite_summary == "artifacts/autonomous_runtime_summaries/live_loop_variance_suite.summary.json"
    assert config.input_trace_root == "artifacts/autonomous_runtime_summaries/live_loop_variance_suite"
    assert config.scenario_ids == (
        "hard_policy_disambiguation",
        "hard_ticket_priority_crosscheck",
        "hard_approval_policy_match",
    )
    assert config.trial_selection == "first_success_per_scenario"
    assert config.replay_backend == "playwright"
    assert config.fixture_only is True
    assert config.fixture_manifest_path == "tests/fixtures/local_intranet/office_site_v1/site_manifest.json"
    assert config.allowed_hosts == (
        "local.intranet",
        "local-intranet.test",
        "docs.local",
        "portal.local",
        "127.0.0.1",
        "localhost",
    )
    assert config.real_network_traffic_allowed is False
    assert config.headless is True
    assert config.timeout_ms == 30_000
    assert config.output_dir == "artifacts/autonomous_runtime_summaries/live_loop_playwright_replay"


def test_default_config_refuses_without_guards() -> None:
    summary = run_autonomous_browser_live_loop_playwright_replay(CONFIG_PATH, repo_root=PROJECT_ROOT)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "refused"
    assert summary["error_code"] == "allow_real_browser_required"
    assert summary["no_runtime_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False


def test_dry_run_discovers_traces_and_ignores_skipped_preflight_attempts(tmp_path: Path) -> None:
    trace_root = tmp_path / "live_loop_variance_suite"
    trace_paths = {
        "hard_policy_disambiguation": trace_root / "hard_policy_disambiguation" / "trial_01" / "autonomous_browser_live_loop_trace.json",
        "hard_ticket_priority_crosscheck": trace_root / "hard_ticket_priority_crosscheck" / "trial_01" / "autonomous_browser_live_loop_trace.json",
        "hard_approval_policy_match": trace_root / "hard_approval_policy_match" / "trial_01" / "autonomous_browser_live_loop_trace.json",
    }
    _write_json(trace_paths["hard_policy_disambiguation"], _policy_trace("hard_policy_disambiguation", "trial_01"))
    _write_json(trace_paths["hard_ticket_priority_crosscheck"], _ticket_trace("hard_ticket_priority_crosscheck", "trial_01"))
    _write_json(trace_paths["hard_approval_policy_match"], _approval_trace("hard_approval_policy_match", "trial_01"))

    variance_summary = _variance_summary(
        [
            _trial_row(
                "hard_policy_disambiguation",
                1,
                "trial_01",
                "live_loop_variance_suite/hard_policy_disambiguation/trial_01/autonomous_browser_live_loop_trace.json",
                matched_url="https://local.intranet/docs/policy",
            ),
            _trial_row(
                "hard_ticket_priority_crosscheck",
                1,
                "trial_01",
                "live_loop_variance_suite/hard_ticket_priority_crosscheck/trial_01/autonomous_browser_live_loop_trace.json",
                matched_url="https://local.intranet/tickets/1",
            ),
            _trial_row(
                "hard_approval_policy_match",
                1,
                "trial_01",
                "live_loop_variance_suite/hard_approval_policy_match/trial_01/autonomous_browser_live_loop_trace.json",
                matched_url="https://local.intranet/portal/approval-match",
            ),
        ]
    )
    summary_path = tmp_path / "live_loop_variance_suite.summary.json"
    _write_json(summary_path, variance_summary)

    config = _base_config()
    config["input_variance_suite_summary"] = "live_loop_variance_suite.summary.json"
    config["input_trace_root"] = "live_loop_variance_suite"
    config["output_dir"] = "artifacts/live_loop_playwright_replay_tests"
    config["allow_real_browser"] = False
    config["allow_playwright"] = False

    summary = run_autonomous_browser_live_loop_playwright_replay(config, repo_root=tmp_path, dry_run=True)
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["error_code"] is None
    assert summary["selected_trace_count"] == 3
    assert summary["traces_replayed"] == 3
    assert summary["traces_succeeded"] == 3
    assert summary["traces_failed"] == 0
    assert summary["traces_rejected"] == 0
    assert summary["actions_attempted_total"] == 8
    assert summary["actions_succeeded_total"] == 8
    assert summary["actions_failed_total"] == 0
    assert summary["expected_results_passed_total"] == 8
    assert summary["expected_results_failed_total"] == 0
    assert summary["real_browser_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["no_runtime_execution"] is True
    assert len(summary["replay_trace_summaries"]) == 3
    assert [item["selected_action_names"] for item in summary["replay_trace_summaries"]] == [
        ["browser_open_url", "browser_click"],
        ["browser_open_url", "browser_click", "browser_click"],
        ["browser_open_url", "browser_click", "browser_click"],
    ]
    assert all(item["source_trace_path"].startswith("live_loop_variance_suite/") for item in summary["replay_trace_summaries"])
    assert str(tmp_path) not in encoded
    assert "C:\\" not in encoded


def test_first_success_per_scenario_selects_first_successful_trial(tmp_path: Path) -> None:
    trace_root = tmp_path / "live_loop_variance_suite"
    failed_policy_trace = trace_root / "hard_policy_disambiguation" / "trial_01" / "autonomous_browser_live_loop_trace.json"
    success_policy_trace = trace_root / "hard_policy_disambiguation" / "trial_02" / "autonomous_browser_live_loop_trace.json"
    success_ticket_trace = trace_root / "hard_ticket_priority_crosscheck" / "trial_01" / "autonomous_browser_live_loop_trace.json"
    success_approval_trace = trace_root / "hard_approval_policy_match" / "trial_01" / "autonomous_browser_live_loop_trace.json"

    _write_json(
        failed_policy_trace,
        {
            "schema_version": "autonomous_browser_live_loop_trace_v1",
            "scenario_id": "hard_policy_disambiguation",
            "observations_total": 2,
            "trace": [
                _open_entry(
                    1,
                    "https://local.intranet/",
                    title="Office Intranet Home",
                    text_preview="Office Intranet Home Workspace policy Ticket board",
                ),
                {
                    "step_index": 2,
                    "observation_id": "observation_0002",
                    "planner_action": {
                        "step_id": "step_0002",
                        "action_name": "browser_click",
                        "parameters": {"target_text": "Workspace policy"},
                        "expected_text": "Workspace Policy",
                        "expected_url": "https://local.intranet/docs/policy",
                    },
                    "validation_status": "accepted",
                    "fixture_execution_status": "succeeded",
                    "action_result": {
                        "success": True,
                        "output": {
                            "current_url": "https://local.intranet/docs/policy",
                            "title": "Workspace Policy",
                            "text_preview": "Workspace Policy Allowed activity",
                        },
                        "observation": {
                            "current_url": "https://local.intranet/docs/policy",
                            "title": "Workspace Policy",
                            "text_preview": "Workspace Policy Allowed activity",
                        },
                    },
                    "expected_result": {"passed": True, "reason": "browser_expectations_met", "metadata": {}},
                    "metadata": {},
                    "next_observation_id": "observation_0003",
                },
            ],
        },
    )
    _write_json(success_policy_trace, _policy_trace("hard_policy_disambiguation", "trial_02", include_skipped=False))
    _write_json(success_ticket_trace, _ticket_trace("hard_ticket_priority_crosscheck", "trial_01", include_skipped=False))
    _write_json(success_approval_trace, _approval_trace("hard_approval_policy_match", "trial_01", include_skipped=False))

    variance_summary = _variance_summary(
        [
            _trial_row(
                "hard_policy_disambiguation",
                1,
                "trial_01",
                "live_loop_variance_suite/hard_policy_disambiguation/trial_01/autonomous_browser_live_loop_trace.json",
                status="failed",
            ),
            _trial_row(
                "hard_policy_disambiguation",
                2,
                "trial_02",
                "live_loop_variance_suite/hard_policy_disambiguation/trial_02/autonomous_browser_live_loop_trace.json",
                matched_url="https://local.intranet/docs/policy",
            ),
            _trial_row(
                "hard_ticket_priority_crosscheck",
                1,
                "trial_01",
                "live_loop_variance_suite/hard_ticket_priority_crosscheck/trial_01/autonomous_browser_live_loop_trace.json",
                matched_url="https://local.intranet/tickets/1",
            ),
            _trial_row(
                "hard_approval_policy_match",
                1,
                "trial_01",
                "live_loop_variance_suite/hard_approval_policy_match/trial_01/autonomous_browser_live_loop_trace.json",
                matched_url="https://local.intranet/portal/approval-match",
            ),
        ]
    )
    _write_json(tmp_path / "live_loop_variance_suite.summary.json", variance_summary)

    config = _base_config()
    config["input_variance_suite_summary"] = "live_loop_variance_suite.summary.json"
    config["input_trace_root"] = "live_loop_variance_suite"

    summary = run_autonomous_browser_live_loop_playwright_replay(config, repo_root=tmp_path, dry_run=True)

    assert summary["selected_trace_count"] == 3
    assert [item["trial_label"] for item in summary["replay_trace_summaries"]] == ["trial_02", "trial_01", "trial_01"]
    assert summary["replay_trace_summaries"][0]["source_trace_path"] == "live_loop_variance_suite/hard_policy_disambiguation/trial_02/autonomous_browser_live_loop_trace.json"


def test_explicit_trace_paths_are_supported_and_output_stays_relative(tmp_path: Path) -> None:
    trace_path = tmp_path / "explicit" / "trial_01" / "autonomous_browser_live_loop_trace.json"
    _write_json(trace_path, _ticket_trace("hard_ticket_priority_crosscheck", "trial_01"))

    config = _config_for_temp_inputs(
        trace_paths=["explicit/trial_01/autonomous_browser_live_loop_trace.json"],
        output_dir="artifacts/live_loop_playwright_replay_tests",
    )
    summary = run_autonomous_browser_live_loop_playwright_replay(config, repo_root=tmp_path, dry_run=True)
    payload = json.dumps(summary, ensure_ascii=False)

    assert summary["status"] == "succeeded"
    assert summary["selected_trace_count"] == 1
    assert summary["replay_trace_summaries"][0]["source_trace_path"] == "explicit/trial_01/autonomous_browser_live_loop_trace.json"
    assert str(tmp_path) not in payload


def test_missing_trace_file_is_reported_cleanly(tmp_path: Path) -> None:
    config = _config_for_temp_inputs(trace_paths=["missing/trial_01/autonomous_browser_live_loop_trace.json"])
    summary = run_autonomous_browser_live_loop_playwright_replay(config, repo_root=tmp_path, dry_run=True)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "trace_not_found"
    assert summary["no_runtime_execution"] is True


def test_unsafe_trace_url_is_rejected(tmp_path: Path) -> None:
    trace_path = tmp_path / "unsafe" / "trial_01" / "autonomous_browser_live_loop_trace.json"
    _write_json(
        trace_path,
        {
            "schema_version": "autonomous_browser_live_loop_trace_v1",
            "scenario_id": "hard_policy_disambiguation",
            "observations_total": 1,
            "trace": [
                _open_entry(
                    1,
                    "file:///C:/secrets/hidden.txt",
                    title="Unsafe page",
                    text_preview="Unsafe page",
                )
            ],
        },
    )

    config = _config_for_temp_inputs(trace_paths=["unsafe/trial_01/autonomous_browser_live_loop_trace.json"])
    summary = run_autonomous_browser_live_loop_playwright_replay(config, repo_root=tmp_path, dry_run=True)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "file_url_not_allowed"


def test_dry_run_does_not_import_playwright_or_browser_runtime(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    trace_path = tmp_path / "trace" / "trial_01" / "autonomous_browser_live_loop_trace.json"
    _write_json(trace_path, _policy_trace("hard_policy_disambiguation", "trial_01"))

    original_import = builtins.__import__
    forbidden = ("playwright", "http.server", "socketserver", "llama_cpp")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = run_autonomous_browser_live_loop_playwright_replay(
        _config_for_temp_inputs(trace_paths=["trace/trial_01/autonomous_browser_live_loop_trace.json"]),
        repo_root=tmp_path,
        dry_run=True,
    )

    assert summary["status"] == "succeeded"
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["no_runtime_execution"] is True


def test_cli_refuses_without_guards() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--config", str(CONFIG_PATH)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode != 0
    assert payload["status"] == "refused"
    assert payload["error_code"] == "allow_real_browser_required"


def test_cli_dry_run_succeeds_and_prints_compact_json(tmp_path: Path) -> None:
    artifacts_root = PROJECT_ROOT / "artifacts" / "live_loop_playwright_replay_cli_tests"
    trace_path = artifacts_root / "trace" / "trial_01" / "autonomous_browser_live_loop_trace.json"
    config_path = artifacts_root / "playwright_replay_config.json"
    try:
        _write_json(trace_path, _approval_trace("hard_approval_policy_match", "trial_01"))
        config = _config_for_temp_inputs(trace_paths=["artifacts/live_loop_playwright_replay_cli_tests/trace/trial_01/autonomous_browser_live_loop_trace.json"])
        config["output_dir"] = "artifacts/live_loop_playwright_replay_cli_tests/output"
        _write_json(config_path, config)

        completed = subprocess.run(
            [sys.executable, str(SCRIPT_PATH), "--config", str(config_path), "--dry-run"],
            cwd=PROJECT_ROOT,
            capture_output=True,
            text=True,
            check=False,
        )
        payload = json.loads(completed.stdout)

        assert completed.returncode == 0
        assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
        assert payload["status"] == "succeeded"
        assert completed.stdout.strip() == completed.stdout.strip().replace("\n", "")
    finally:
        if artifacts_root.exists():
            for child in sorted(artifacts_root.rglob("*"), reverse=True):
                if child.is_file():
                    child.unlink()
            for child in sorted(artifacts_root.rglob("*"), reverse=True):
                if child.is_dir():
                    try:
                        child.rmdir()
                    except OSError:
                        pass
            try:
                artifacts_root.rmdir()
            except OSError:
                pass
