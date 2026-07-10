from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any
from urllib.parse import urlparse

from .autonomous_browser_runtime import (
    BrowserRuntimeAction,
    BrowserRuntimePolicy,
    BrowserRuntimeSession,
    BrowserRuntimeVerifier,
    FixtureBackedBrowserRuntimeExecutor,
)
from .autonomous_browser_stateful_readonly_planner_packet import (
    DEFAULT_SCENARIO_IDS,
    OUTPUT_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    _scenario_prompt_hints,
)
from .autonomous_browser_stateful_readonly_workflow import (
    StatefulReadonlyWorkflowStep,
    build_default_stateful_readonly_workflow_scenarios,
)


DEFAULT_PACKET_MANIFEST_FILENAME = "autonomous_browser_stateful_readonly_planner_packet.json"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/stateful_readonly_planner_evaluator"
DEFAULT_SUMMARY_FILENAME = "autonomous_browser_stateful_readonly_planner_evaluator_summary.json"
DEFAULT_FIXTURE_MANIFEST_PATH = "tests/fixtures/local_intranet/office_site_v1/site_manifest.json"
DEFAULT_ALLOWED_ACTIONS = (
    "browser_open_url",
    "browser_click",
    "browser_extract_text",
    "browser_snapshot",
)
ALLOWED_DONE_REASONS = (
    "task_completed",
    "insufficient_evidence",
    "model_failed_task",
    "policy_rejected",
)
ALLOWED_LOCAL_HOSTS = (
    "local.intranet",
    "local-intranet.test",
    "docs.local",
    "portal.local",
    "localhost",
    "127.0.0.1",
)
DEFAULT_LIMITATIONS = (
    "offline stateful planner evaluator only",
    "local fixture-backed replay only",
    "no model calls",
    "no real browser execution",
    "no Playwright execution",
    "not production browser automation",
)


@dataclass(frozen=True)
class StatefulReadonlyPlannerEvaluatorSummary:
    schema_version: str
    status: str
    error_code: str | None
    packet_id: str | None
    packet_dir: str | None
    output_dir: str | None
    captured_output_dir: str | None
    models_total: int
    scenarios_total: int
    workflows_total: int
    outputs_total: int
    outputs_present: int
    outputs_missing: int
    outputs_ingested: int
    outputs_rejected: int
    validation_accepted: int
    validation_rejected: int
    dry_runs_succeeded: int
    dry_runs_failed: int
    fixture_runs_succeeded: int
    fixture_runs_failed: int
    workflows_succeeded: int
    workflows_failed: int
    actions_attempted_total: int
    actions_succeeded_total: int
    actions_failed_total: int
    expected_results_total: int
    expected_results_passed_total: int
    expected_results_failed_total: int
    no_runtime_execution: bool
    model_execution: bool
    real_browser_execution: bool
    playwright_execution: bool
    browser_opened: bool
    real_network_traffic: bool
    fixture_only: bool
    fixture_execution_requested: bool
    model_aliases: tuple[str, ...] = ()
    scenario_ids: tuple[str, ...] = ()
    failure_class_counts: dict[str, int] = field(default_factory=dict)
    output_summaries: tuple[dict[str, Any], ...] = ()
    scenario_summaries: tuple[dict[str, Any], ...] = ()
    limitations: tuple[str, ...] = DEFAULT_LIMITATIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "packet_id": self.packet_id,
            "packet_dir": self.packet_dir,
            "output_dir": self.output_dir,
            "captured_output_dir": self.captured_output_dir,
            "models_total": self.models_total,
            "scenarios_total": self.scenarios_total,
            "workflows_total": self.workflows_total,
            "outputs_total": self.outputs_total,
            "outputs_present": self.outputs_present,
            "outputs_missing": self.outputs_missing,
            "outputs_ingested": self.outputs_ingested,
            "outputs_rejected": self.outputs_rejected,
            "validation_accepted": self.validation_accepted,
            "validation_rejected": self.validation_rejected,
            "dry_runs_succeeded": self.dry_runs_succeeded,
            "dry_runs_failed": self.dry_runs_failed,
            "fixture_runs_succeeded": self.fixture_runs_succeeded,
            "fixture_runs_failed": self.fixture_runs_failed,
            "workflows_succeeded": self.workflows_succeeded,
            "workflows_failed": self.workflows_failed,
            "actions_attempted_total": self.actions_attempted_total,
            "actions_succeeded_total": self.actions_succeeded_total,
            "actions_failed_total": self.actions_failed_total,
            "expected_results_total": self.expected_results_total,
            "expected_results_passed_total": self.expected_results_passed_total,
            "expected_results_failed_total": self.expected_results_failed_total,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "real_network_traffic": self.real_network_traffic,
            "fixture_only": self.fixture_only,
            "fixture_execution_requested": self.fixture_execution_requested,
            "model_aliases": list(self.model_aliases),
            "scenario_ids": list(self.scenario_ids),
            "failure_class_counts": dict(self.failure_class_counts),
            "output_summaries": [_jsonable(item) for item in self.output_summaries],
            "scenario_summaries": [_jsonable(item) for item in self.scenario_summaries],
            "limitations": list(self.limitations),
        }


def run_autonomous_browser_stateful_readonly_planner_evaluator(
    packet_dir: str | Path,
    *,
    repo_root: str | Path | None = None,
    output_dir: str | Path | None = None,
    execute_fixture: bool = False,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    packet_root = _resolve_repo_path(packet_dir, repo)
    manifest_path = packet_root / DEFAULT_PACKET_MANIFEST_FILENAME
    manifest = _load_packet_manifest(manifest_path)
    if manifest.get("status") != "ok":
        return _failure_summary(
            packet_id=manifest.get("packet_id"),
            packet_dir=manifest.get("packet_dir") or _relative_path(repo, packet_root),
            output_dir=_safe_relative_path(output_dir or DEFAULT_OUTPUT_DIR, "output_dir"),
            captured_output_dir=manifest.get("captured_output_dir"),
            error_code=str(manifest.get("error_code") or "config_validation_failed"),
            limitations=tuple(manifest.get("limitations") or DEFAULT_LIMITATIONS),
        )

    packet = manifest["packet"]
    packet_id = str(packet["packet_id"])
    packet_dir_rel = str(packet["output_dir"])
    packet_output_dir = str(packet["output_dir"])
    captured_output_dir = str(packet["captured_output_dir"])
    model_aliases = tuple(packet["model_aliases"])
    scenario_ids = tuple(packet["scenario_ids"])
    request_records = tuple(packet["request_records"])
    limitations = tuple(packet.get("limitations") or DEFAULT_LIMITATIONS)

    scenario_defs = build_default_stateful_readonly_workflow_scenarios()
    scenario_hints = _scenario_prompt_hints()

    output_dir_value = _safe_relative_path(output_dir or DEFAULT_OUTPUT_DIR, "output_dir")
    if output_dir_value is None:
        return _failure_summary(
            packet_id=packet_id,
            packet_dir=packet_dir_rel,
            output_dir=None,
            captured_output_dir=captured_output_dir,
            error_code="config_validation_failed",
            limitations=limitations,
        )

    output_root = repo / output_dir_value
    output_root.mkdir(parents=True, exist_ok=True)

    output_summaries: list[dict[str, Any]] = []
    scenario_summary_map: dict[str, dict[str, Any]] = {
        scenario_id: {
            "scenario_id": scenario_id,
            "outputs_total": 0,
            "outputs_present": 0,
            "outputs_missing": 0,
            "outputs_ingested": 0,
            "outputs_rejected": 0,
            "validation_accepted": 0,
            "validation_rejected": 0,
            "dry_runs_succeeded": 0,
            "dry_runs_failed": 0,
            "fixture_runs_succeeded": 0,
            "fixture_runs_failed": 0,
            "workflows_succeeded": 0,
            "workflows_failed": 0,
            "actions_attempted_total": 0,
            "actions_succeeded_total": 0,
            "actions_failed_total": 0,
            "expected_results_total": 0,
            "expected_results_passed_total": 0,
            "expected_results_failed_total": 0,
            "unique_matched_urls": set(),
            "unique_source_output_paths": set(),
            "route_stable": False,
            "limitations": limitations,
        }
        for scenario_id in scenario_ids
    }

    outputs_present = 0
    outputs_missing = 0
    outputs_ingested = 0
    outputs_rejected = 0
    validation_accepted = 0
    validation_rejected = 0
    dry_runs_succeeded = 0
    dry_runs_failed = 0
    fixture_runs_succeeded = 0
    fixture_runs_failed = 0
    workflows_succeeded = 0
    workflows_failed = 0
    actions_attempted_total = 0
    actions_succeeded_total = 0
    actions_failed_total = 0
    expected_results_total = 0
    expected_results_passed_total = 0
    expected_results_failed_total = 0
    failure_class_counts: Counter[str] = Counter()
    first_issue_code: str | None = None

    for record in request_records:
        scenario_id = str(record["scenario_id"])
        scenario = scenario_defs.get(scenario_id)
        if scenario is None:
            return _failure_summary(
                packet_id=packet_id,
                packet_dir=packet_dir_rel,
                output_dir=output_dir_value,
                captured_output_dir=captured_output_dir,
                error_code="unknown_scenario_id",
                limitations=limitations,
            )

        scenario_summary = scenario_summary_map[scenario_id]
        scenario_summary["outputs_total"] += 1

        result = _evaluate_output_record(
            repo_root=repo,
            packet_id=packet_id,
            record=record,
            scenario=scenario,
            scenario_hints=scenario_hints[scenario_id],
            execute_fixture=execute_fixture,
            packet_output_dir=packet_output_dir,
        )
        output_summaries.append(result)
        failure_class_counts.update([str(result.get("failure_class") or "none")])
        scenario_summary["unique_source_output_paths"].add(str(result.get("source_output_path") or ""))
        if result.get("matched_url"):
            scenario_summary["unique_matched_urls"].add(str(result["matched_url"]))

        if str(result.get("status")) == "missing":
            outputs_missing += 1
            scenario_summary["outputs_missing"] += 1
            scenario_summary["workflows_failed"] += 1
            workflows_failed += 1
            if first_issue_code is None:
                first_issue_code = str(result.get("error_code") or "missing_captured_output_file")
            continue

        outputs_present += 1
        scenario_summary["outputs_present"] += 1

        if str(result.get("validation_status")) == "accepted":
            validation_accepted += 1
            dry_runs_succeeded += 1
            scenario_summary["validation_accepted"] += 1
            scenario_summary["dry_runs_succeeded"] += 1
        else:
            validation_rejected += 1
            dry_runs_failed += 1
            scenario_summary["validation_rejected"] += 1
            scenario_summary["dry_runs_failed"] += 1

        if str(result.get("status")) == "succeeded":
            outputs_ingested += 1
            fixture_runs_succeeded += 1
            workflows_succeeded += 1
            scenario_summary["outputs_ingested"] += 1
            scenario_summary["fixture_runs_succeeded"] += 1
            scenario_summary["workflows_succeeded"] += 1
        else:
            outputs_rejected += 1
            fixture_runs_failed += 1
            workflows_failed += 1
            scenario_summary["outputs_rejected"] += 1
            scenario_summary["fixture_runs_failed"] += 1
            scenario_summary["workflows_failed"] += 1
            if first_issue_code is None:
                first_issue_code = str(result.get("error_code") or "stateful_planner_output_failed")

        actions_attempted_total += _int(result.get("actions_attempted"))
        actions_succeeded_total += _int(result.get("actions_succeeded"))
        actions_failed_total += _int(result.get("actions_failed"))
        expected_results_total += _int(result.get("expected_results_total"))
        expected_results_passed_total += _int(result.get("expected_results_passed"))
        expected_results_failed_total += _int(result.get("expected_results_failed"))

        scenario_summary["actions_attempted_total"] += _int(result.get("actions_attempted"))
        scenario_summary["actions_succeeded_total"] += _int(result.get("actions_succeeded"))
        scenario_summary["actions_failed_total"] += _int(result.get("actions_failed"))
        scenario_summary["expected_results_total"] += _int(result.get("expected_results_total"))
        scenario_summary["expected_results_passed_total"] += _int(result.get("expected_results_passed"))
        scenario_summary["expected_results_failed_total"] += _int(result.get("expected_results_failed"))

    if outputs_missing > 0:
        status = "completed_with_missing_outputs"
        error_code = "missing_captured_outputs"
    elif outputs_rejected > 0:
        status = "completed_with_failures"
        error_code = first_issue_code or "stateful_planner_outputs_rejected"
    else:
        status = "succeeded"
        error_code = None

    finalized_summaries: list[dict[str, Any]] = []
    for scenario_id, scenario_summary in scenario_summary_map.items():
        scenario_summary["unique_matched_urls"] = sorted(url for url in scenario_summary["unique_matched_urls"] if url)
        scenario_summary["unique_source_output_paths"] = sorted(
            path for path in scenario_summary["unique_source_output_paths"] if path
        )
        scenario_summary["route_stable"] = len(scenario_summary["unique_matched_urls"]) <= 1
        finalized_summaries.append(scenario_summary)

    summary = StatefulReadonlyPlannerEvaluatorSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        packet_id=packet_id,
        packet_dir=packet_dir_rel,
        output_dir=output_dir_value,
        captured_output_dir=captured_output_dir,
        models_total=len(model_aliases),
        scenarios_total=len(scenario_ids),
        workflows_total=len(request_records),
        outputs_total=len(request_records),
        outputs_present=outputs_present,
        outputs_missing=outputs_missing,
        outputs_ingested=outputs_ingested,
        outputs_rejected=outputs_rejected,
        validation_accepted=validation_accepted,
        validation_rejected=validation_rejected,
        dry_runs_succeeded=dry_runs_succeeded,
        dry_runs_failed=dry_runs_failed,
        fixture_runs_succeeded=fixture_runs_succeeded,
        fixture_runs_failed=fixture_runs_failed,
        workflows_succeeded=workflows_succeeded,
        workflows_failed=workflows_failed,
        actions_attempted_total=actions_attempted_total,
        actions_succeeded_total=actions_succeeded_total,
        actions_failed_total=actions_failed_total,
        expected_results_total=expected_results_total,
        expected_results_passed_total=expected_results_passed_total,
        expected_results_failed_total=expected_results_failed_total,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        real_network_traffic=False,
        fixture_only=True,
        fixture_execution_requested=execute_fixture,
        model_aliases=model_aliases,
        scenario_ids=scenario_ids,
        failure_class_counts=dict(sorted(failure_class_counts.items())),
        output_summaries=tuple(output_summaries),
        scenario_summaries=tuple(finalized_summaries),
        limitations=limitations,
    )
    payload = summary.to_dict()
    _write_json(output_root / DEFAULT_SUMMARY_FILENAME, payload)
    return payload


def write_autonomous_browser_stateful_readonly_planner_evaluator_summary(
    summary: Mapping[str, Any],
    output_dir: str | Path,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / DEFAULT_SUMMARY_FILENAME
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _evaluate_output_record(
    *,
    repo_root: Path,
    packet_id: str,
    record: Mapping[str, Any],
    scenario,
    scenario_hints: Mapping[str, tuple[str, ...]],
    execute_fixture: bool,
    packet_output_dir: str,
) -> dict[str, Any]:
    source_output_path = _safe_relative_path(record.get("output_path"), "output_path")
    model_alias = _safe_text(record.get("model_alias"))
    workflow_id = _safe_text(record.get("workflow_id"))
    trial_label = _safe_text(record.get("trial_id"))
    if source_output_path is None or model_alias is None or workflow_id is None or trial_label is None:
        return {
            "packet_id": packet_id,
            "model_alias": model_alias,
            "scenario_id": getattr(scenario, "scenario_id", None),
            "workflow_id": workflow_id,
            "trial_id": trial_label,
            "source_output_path": source_output_path,
            "status": "rejected",
            "error_code": "config_validation_failed",
            "failure_class": "config_error",
            "captured_output_present": False,
            "validation_status": "skipped",
            "dry_run_status": "skipped",
            "fixture_execution_status": "skipped",
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "actions_total": 0,
            "actions_attempted": 0,
            "actions_succeeded": 0,
            "actions_failed": 0,
            "expected_results_total": 0,
            "expected_results_passed": 0,
            "expected_results_failed": 0,
            "matched_url": None,
            "final_url": None,
            "diagnostics": {"finding_type": "invalid_record_shape"},
        }

    raw_path = repo_root / source_output_path
    if not raw_path.exists():
        return {
            "packet_id": packet_id,
            "model_alias": model_alias,
            "scenario_id": scenario.scenario_id,
            "workflow_id": workflow_id,
            "trial_id": trial_label,
            "source_output_path": source_output_path,
            "status": "missing",
            "error_code": "missing_captured_output_file",
            "failure_class": "missing_output",
            "captured_output_present": False,
            "validation_status": "skipped",
            "dry_run_status": "skipped",
            "fixture_execution_status": "skipped",
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "actions_total": 0,
            "actions_attempted": 0,
            "actions_succeeded": 0,
            "actions_failed": 0,
            "expected_results_total": 0,
            "expected_results_passed": 0,
            "expected_results_failed": 0,
            "matched_url": None,
            "final_url": None,
            "diagnostics": {
                "source_output": {
                    "finding_type": "missing_captured_output_file",
                    "path": "output_path",
                }
            },
        }

    try:
        raw_text = raw_path.read_text(encoding="utf-8-sig")
    except OSError:
        return {
            "packet_id": packet_id,
            "model_alias": model_alias,
            "scenario_id": scenario.scenario_id,
            "workflow_id": workflow_id,
            "trial_id": trial_label,
            "source_output_path": source_output_path,
            "status": "rejected",
            "error_code": "source_output_read_failed",
            "failure_class": "fixture_error",
            "captured_output_present": False,
            "validation_status": "skipped",
            "dry_run_status": "skipped",
            "fixture_execution_status": "skipped",
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "actions_total": 0,
            "actions_attempted": 0,
            "actions_succeeded": 0,
            "actions_failed": 0,
            "expected_results_total": 0,
            "expected_results_passed": 0,
            "expected_results_failed": 0,
            "matched_url": None,
            "final_url": None,
            "diagnostics": {
                "source_output": {
                    "finding_type": "source_output_read_failed",
                    "path": "output_path",
                }
            },
        }

    extraction = _extract_candidate_output(raw_text)
    if extraction["status"] != "accepted" or not isinstance(extraction.get("candidate_output"), Mapping):
        return {
            "packet_id": packet_id,
            "model_alias": model_alias,
            "scenario_id": scenario.scenario_id,
            "workflow_id": workflow_id,
            "trial_id": trial_label,
            "source_output_path": source_output_path,
            "status": "rejected",
            "error_code": str(extraction.get("error_code") or "output_extraction_failed"),
            "failure_class": "model_failed_task",
            "captured_output_present": True,
            "validation_status": "rejected",
            "dry_run_status": "rejected",
            "fixture_execution_status": "skipped",
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "actions_total": 0,
            "actions_attempted": 0,
            "actions_succeeded": 0,
            "actions_failed": 0,
            "expected_results_total": 0,
            "expected_results_passed": 0,
            "expected_results_failed": 0,
            "matched_url": None,
            "final_url": None,
            "diagnostics": {
                "extraction": extraction.get("diagnostics", {}),
                "source_output_path": source_output_path,
            },
        }

    candidate_output = dict(extraction["candidate_output"])
    validation = _validate_stateful_output(
        candidate_output,
        scenario=scenario,
        scenario_hints=scenario_hints,
    )
    if validation["status"] != "accepted":
        failure_class = _failure_class_from_error_code(str(validation.get("error_code") or "model_failed_task"))
        return {
            "packet_id": packet_id,
            "model_alias": model_alias,
            "scenario_id": scenario.scenario_id,
            "workflow_id": workflow_id,
            "trial_id": trial_label,
            "source_output_path": source_output_path,
            "status": "rejected",
            "error_code": str(validation.get("error_code") or "model_failed_task"),
            "failure_class": failure_class,
            "captured_output_present": True,
            "validation_status": "rejected",
            "dry_run_status": "rejected",
            "fixture_execution_status": "skipped",
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "actions_total": _int(validation.get("actions_total")),
            "actions_attempted": 0,
            "actions_succeeded": 0,
            "actions_failed": 0,
            "expected_results_total": 0,
            "expected_results_passed": 0,
            "expected_results_failed": 0,
            "matched_url": None,
            "final_url": None,
            "diagnostics": validation.get("diagnostics", {}),
        }

    normalized = validation["normalized_output"]
    actions = tuple(normalized["actions"])
    facts = tuple(normalized["facts"])
    evidence_items = tuple(normalized["evidence_items"])
    final_answer = dict(normalized["final_answer"])

    if not execute_fixture:
        return {
            "packet_id": packet_id,
            "model_alias": model_alias,
            "scenario_id": scenario.scenario_id,
            "workflow_id": workflow_id,
            "trial_id": trial_label,
            "source_output_path": source_output_path,
            "status": "succeeded",
            "error_code": None,
            "failure_class": "none",
            "captured_output_present": True,
            "validation_status": "accepted",
            "dry_run_status": "accepted",
            "fixture_execution_status": "skipped",
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "actions_total": len(actions),
            "actions_attempted": 0,
            "actions_succeeded": 0,
            "actions_failed": 0,
            "expected_results_total": 0,
            "expected_results_passed": 0,
            "expected_results_failed": 0,
            "matched_url": None,
            "final_url": None,
            "diagnostics": {
                "validation": validation["diagnostics"],
                "source_output_path": source_output_path,
            },
        }

    fixture = _execute_fixture_plan(
        scenario=scenario,
        actions=actions,
        facts=facts,
        evidence_items=evidence_items,
        final_answer=final_answer,
    )
    if fixture["status"] != "succeeded":
        failure_class = fixture.get("failure_class") or _failure_class_from_error_code(str(fixture.get("error_code") or "fixture_error"))
        return {
            "packet_id": packet_id,
            "model_alias": model_alias,
            "scenario_id": scenario.scenario_id,
            "workflow_id": workflow_id,
            "trial_id": trial_label,
            "source_output_path": source_output_path,
            "status": "failed",
            "error_code": fixture.get("error_code"),
            "failure_class": failure_class,
            "captured_output_present": True,
            "validation_status": "accepted",
            "dry_run_status": "accepted",
            "fixture_execution_status": "failed",
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "actions_total": len(actions),
            "actions_attempted": fixture["actions_attempted"],
            "actions_succeeded": fixture["actions_succeeded"],
            "actions_failed": fixture["actions_failed"],
            "expected_results_total": fixture["expected_results_total"],
            "expected_results_passed": fixture["expected_results_passed"],
            "expected_results_failed": fixture["expected_results_failed"],
            "matched_url": fixture.get("matched_url"),
            "final_url": fixture.get("final_url"),
            "diagnostics": {
                "validation": validation["diagnostics"],
                "fixture": fixture.get("diagnostics", {}),
                "source_output_path": source_output_path,
            },
        }

    return {
        "packet_id": packet_id,
        "model_alias": model_alias,
        "scenario_id": scenario.scenario_id,
        "workflow_id": workflow_id,
        "trial_id": trial_label,
        "source_output_path": source_output_path,
        "status": "succeeded",
        "error_code": None,
        "failure_class": "none",
        "captured_output_present": True,
        "validation_status": "accepted",
        "dry_run_status": "accepted",
        "fixture_execution_status": "succeeded",
        "no_runtime_execution": True,
        "model_execution": False,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
        "actions_total": len(actions),
        "actions_attempted": fixture["actions_attempted"],
        "actions_succeeded": fixture["actions_succeeded"],
        "actions_failed": fixture["actions_failed"],
        "expected_results_total": fixture["expected_results_total"],
        "expected_results_passed": fixture["expected_results_passed"],
        "expected_results_failed": fixture["expected_results_failed"],
        "matched_url": fixture.get("matched_url"),
        "final_url": fixture.get("final_url"),
        "diagnostics": {
            "validation": validation["diagnostics"],
            "fixture": fixture.get("diagnostics", {}),
            "source_output_path": source_output_path,
        },
    }


def _validate_stateful_output(
    payload: Mapping[str, Any],
    *,
    scenario,
    scenario_hints: Mapping[str, tuple[str, ...]],
) -> dict[str, Any]:
    diagnostics: list[dict[str, Any]] = []
    required_keys = (
        "schema_version",
        "scenario_id",
        "workflow_id",
        "goal",
        "actions",
        "facts",
        "evidence_items",
        "final_answer",
        "done_reason",
    )
    for key in required_keys:
        if key not in payload:
            diagnostics.append({"finding_type": "missing_required_field", "path": key})
            return _validation_failure("missing_required_field", diagnostics, 0)

    if str(payload.get("schema_version", "")).strip() != OUTPUT_SCHEMA_VERSION:
        diagnostics.append(
            {
                "finding_type": "schema_version_mismatch",
                "path": "schema_version",
                "expected_schema_version": OUTPUT_SCHEMA_VERSION,
            }
        )
        return _validation_failure("schema_version_mismatch", diagnostics, 0)

    scenario_id = _safe_text(payload.get("scenario_id"))
    workflow_id = _safe_text(payload.get("workflow_id"))
    goal = _safe_text(payload.get("goal"))
    done_reason = _safe_text(payload.get("done_reason"))
    if scenario_id != scenario.scenario_id:
        diagnostics.append({"finding_type": "scenario_id_mismatch", "path": "scenario_id"})
        return _validation_failure("scenario_id_mismatch", diagnostics, 0)
    if workflow_id != scenario.workflow_id:
        diagnostics.append({"finding_type": "workflow_id_mismatch", "path": "workflow_id"})
        return _validation_failure("workflow_id_mismatch", diagnostics, 0)
    if goal != scenario.objective:
        diagnostics.append({"finding_type": "goal_mismatch", "path": "goal"})
        return _validation_failure("goal_mismatch", diagnostics, 0)
    if done_reason not in ALLOWED_DONE_REASONS:
        diagnostics.append({"finding_type": "invalid_done_reason", "path": "done_reason"})
        return _validation_failure("invalid_done_reason", diagnostics, 0)
    if done_reason != "task_completed":
        diagnostics.append({"finding_type": "plan_not_marked_complete", "path": "done_reason"})
        return _validation_failure("model_failed_task", diagnostics, 0)

    actions_payload = payload.get("actions")
    if not isinstance(actions_payload, list) or not actions_payload:
        diagnostics.append(
            {
                "finding_type": "invalid_actions_collection",
                "path": "actions",
                "expected_type": "array",
                "actions_type": type(actions_payload).__name__,
            }
        )
        return _validation_failure("invalid_actions_collection", diagnostics, 0)

    normalized_actions: list[dict[str, Any]] = []
    seen_step_ids: set[str] = set()
    for index, action in enumerate(actions_payload):
        if not isinstance(action, Mapping):
            diagnostics.append(
                {
                    "finding_type": "invalid_action_shape",
                    "path": f"actions[{index}]",
                    "action_index": index,
                    "present_fields": [],
                    "expected_field": "action_name",
                    "hint": "use action_name, not action",
                }
            )
            return _validation_failure("invalid_action_shape", diagnostics, len(normalized_actions))
        step_id = _safe_identifier(action.get("step_id"), f"actions[{index}].step_id")
        action_name = _safe_identifier(action.get("action_name"), f"actions[{index}].action_name")
        if step_id is None or action_name is None:
            diagnostics.append(
                {
                    "finding_type": "missing_action_field",
                    "path": f"actions[{index}]",
                    "action_index": index,
                    "present_fields": sorted(str(key) for key in action.keys()),
                    "expected_field": "action_name",
                    "hint": "use action_name, not action",
                }
            )
            return _validation_failure("missing_action_field", diagnostics, len(normalized_actions))
        if step_id in seen_step_ids:
            diagnostics.append({"finding_type": "duplicate_step_id", "path": f"actions[{index}].step_id"})
            return _validation_failure("duplicate_step_id", diagnostics, len(normalized_actions))
        seen_step_ids.add(step_id)
        if action_name not in DEFAULT_ALLOWED_ACTIONS:
            diagnostics.append({"finding_type": "unsupported_action_name", "path": f"actions[{index}].action_name"})
            return _validation_failure("model_output_unsupported_action", diagnostics, len(normalized_actions))
        parameters = action.get("parameters")
        if not isinstance(parameters, Mapping):
            diagnostics.append({"finding_type": "invalid_parameters_shape", "path": f"actions[{index}].parameters"})
            return _validation_failure("invalid_parameters_shape", diagnostics, len(normalized_actions))
        normalized_parameters, parameter_issue = _normalize_value(parameters, f"actions[{index}].parameters")
        if parameter_issue is not None:
            diagnostics.append(parameter_issue)
            return _validation_failure(
                _map_finding_to_error_code(parameter_issue["finding_type"]),
                diagnostics,
                len(normalized_actions),
            )
        expected_text = _optional_safe_text(action.get("expected_text"), f"actions[{index}].expected_text")
        if expected_text is False:
            diagnostics.append({"finding_type": "invalid_expected_text", "path": f"actions[{index}].expected_text"})
            return _validation_failure("invalid_expected_text", diagnostics, len(normalized_actions))
        expected_url = _optional_safe_url(action.get("expected_url"), f"actions[{index}].expected_url")
        if expected_url is False:
            diagnostics.append({"finding_type": "invalid_expected_url", "path": f"actions[{index}].expected_url"})
            return _validation_failure("invalid_expected_url", diagnostics, len(normalized_actions))
        collect_fact_keys = action.get("collect_fact_keys", [])
        if not isinstance(collect_fact_keys, list):
            diagnostics.append({"finding_type": "invalid_collect_fact_keys", "path": f"actions[{index}].collect_fact_keys"})
            return _validation_failure("invalid_collect_fact_keys", diagnostics, len(normalized_actions))
        normalized_collect_fact_keys: list[str] = []
        for key_index, candidate in enumerate(collect_fact_keys):
            identifier = _safe_identifier(candidate, f"actions[{index}].collect_fact_keys[{key_index}]")
            if identifier is None:
                diagnostics.append({"finding_type": "invalid_collect_fact_key", "path": f"actions[{index}].collect_fact_keys[{key_index}]"})
                return _validation_failure("invalid_collect_fact_keys", diagnostics, len(normalized_actions))
            normalized_collect_fact_keys.append(identifier)
        normalized_action = {
            "step_id": step_id,
            "action_name": action_name,
            "parameters": normalized_parameters,
        }
        if expected_text is not None:
            normalized_action["expected_text"] = expected_text
        if expected_url is not None:
            normalized_action["expected_url"] = expected_url
        if normalized_collect_fact_keys:
            normalized_action["collect_fact_keys"] = normalized_collect_fact_keys
        normalized_actions.append(normalized_action)

    facts_payload = payload.get("facts")
    if not isinstance(facts_payload, list) or not facts_payload:
        diagnostics.append(
            {
                "finding_type": "invalid_facts_collection",
                "path": "facts",
                "expected_type": "array",
                "facts_type": type(facts_payload).__name__,
            }
        )
        return _validation_failure("invalid_facts_collection", diagnostics, len(normalized_actions))

    normalized_facts: list[dict[str, Any]] = []
    fact_ids: set[str] = set()
    fact_keys: set[str] = set()
    for index, fact in enumerate(facts_payload):
        if not isinstance(fact, Mapping):
            diagnostics.append(
                {
                    "finding_type": "invalid_fact_shape",
                    "path": f"facts[{index}]",
                    "fact_index": index,
                    "present_fields": [],
                    "expected_type": "object",
                }
            )
            return _validation_failure("invalid_fact_shape", diagnostics, len(normalized_actions))
        fact_id = _safe_identifier(fact.get("fact_id"), f"facts[{index}].fact_id")
        key = _safe_identifier(fact.get("key"), f"facts[{index}].key")
        source_step_id = _safe_identifier(fact.get("source_step_id"), f"facts[{index}].source_step_id")
        if fact_id is None or key is None or source_step_id is None:
            diagnostics.append({"finding_type": "missing_fact_field", "path": f"facts[{index}]"})
            return _validation_failure("missing_fact_field", diagnostics, len(normalized_actions))
        if fact_id in fact_ids:
            diagnostics.append({"finding_type": "duplicate_fact_id", "path": f"facts[{index}].fact_id"})
            return _validation_failure("duplicate_fact_id", diagnostics, len(normalized_actions))
        if source_step_id not in seen_step_ids:
            diagnostics.append({"finding_type": "invalid_fact_reference", "path": f"facts[{index}].source_step_id"})
            return _validation_failure("invalid_fact_reference", diagnostics, len(normalized_actions))
        value, value_issue = _normalize_value(fact.get("value"), f"facts[{index}].value")
        if value_issue is not None:
            diagnostics.append(value_issue)
            return _validation_failure(
                _map_finding_to_error_code(value_issue["finding_type"]),
                diagnostics,
                len(normalized_actions),
            )
        source_url = fact.get("source_url")
        if source_url is not None:
            safe_source_url = _optional_safe_url(source_url, f"facts[{index}].source_url")
            if safe_source_url is False:
                diagnostics.append({"finding_type": "invalid_fact_source_url", "path": f"facts[{index}].source_url"})
                return _validation_failure("invalid_fact_source_url", diagnostics, len(normalized_actions))
        else:
            safe_source_url = None
        evidence_item_id = fact.get("evidence_item_id")
        if evidence_item_id is not None:
            evidence_identifier = _safe_identifier(evidence_item_id, f"facts[{index}].evidence_item_id")
            if evidence_identifier is None:
                diagnostics.append({"finding_type": "invalid_fact_evidence_ref", "path": f"facts[{index}].evidence_item_id"})
                return _validation_failure("invalid_fact_evidence_ref", diagnostics, len(normalized_actions))
            evidence_item_id = evidence_identifier
        normalized_facts.append(
            {
                "fact_id": fact_id,
                "key": key,
                "value": value,
                "source_step_id": source_step_id,
                **({"source_url": safe_source_url} if safe_source_url is not None else {}),
                **({"evidence_item_id": evidence_item_id} if evidence_item_id is not None else {}),
            }
        )
        fact_ids.add(fact_id)
        fact_keys.add(key)

    evidence_payload = payload.get("evidence_items")
    if not isinstance(evidence_payload, list) or not evidence_payload:
        diagnostics.append(
            {
                "finding_type": "invalid_evidence_collection",
                "path": "evidence_items",
                "expected_type": "array",
                "evidence_items_type": type(evidence_payload).__name__,
            }
        )
        return _validation_failure("invalid_evidence_collection", diagnostics, len(normalized_actions))

    normalized_evidence: list[dict[str, Any]] = []
    evidence_ids: set[str] = set()
    for index, evidence in enumerate(evidence_payload):
        if not isinstance(evidence, Mapping):
            diagnostics.append(
                {
                    "finding_type": "invalid_evidence_item_shape",
                    "path": f"evidence_items[{index}]",
                    "evidence_item_index": index,
                    "present_fields": [],
                    "expected_id_field": "evidence_item_id",
                }
            )
            return _validation_failure("invalid_evidence_item_shape", diagnostics, len(normalized_actions))
        evidence_id = _safe_identifier(evidence.get("evidence_item_id"), f"evidence_items[{index}].evidence_item_id")
        source_step_id = _safe_identifier(evidence.get("source_step_id"), f"evidence_items[{index}].source_step_id")
        if evidence_id is None or source_step_id is None:
            diagnostics.append(
                {
                    "finding_type": "missing_evidence_field",
                    "path": f"evidence_items[{index}]",
                    "evidence_item_index": index,
                    "present_fields": sorted(str(key) for key in evidence.keys()),
                    "expected_id_field": "evidence_item_id",
                    "hint": "use evidence_item_id, not id",
                }
            )
            return _validation_failure("missing_evidence_field", diagnostics, len(normalized_actions))
        if evidence_id in evidence_ids:
            diagnostics.append({"finding_type": "duplicate_evidence_item_id", "path": f"evidence_items[{index}].evidence_item_id"})
            return _validation_failure("duplicate_evidence_item_id", diagnostics, len(normalized_actions))
        if source_step_id not in seen_step_ids:
            diagnostics.append({"finding_type": "invalid_evidence_reference", "path": f"evidence_items[{index}].source_step_id"})
            return _validation_failure("invalid_evidence_reference", diagnostics, len(normalized_actions))
        text_quote = evidence.get("text_quote")
        text_preview = evidence.get("text_preview")
        if text_quote is None and text_preview is None:
            diagnostics.append({"finding_type": "missing_evidence_text", "path": f"evidence_items[{index}]"})
            return _validation_failure("missing_evidence_text", diagnostics, len(normalized_actions))
        if text_quote is not None:
            safe_text_quote = _optional_safe_text(text_quote, f"evidence_items[{index}].text_quote")
            if safe_text_quote is False:
                diagnostics.append({"finding_type": "invalid_evidence_text", "path": f"evidence_items[{index}].text_quote"})
                return _validation_failure("invalid_evidence_text", diagnostics, len(normalized_actions))
        else:
            safe_text_quote = None
        if text_preview is not None:
            safe_text_preview = _optional_safe_text(text_preview, f"evidence_items[{index}].text_preview")
            if safe_text_preview is False:
                diagnostics.append({"finding_type": "invalid_evidence_text", "path": f"evidence_items[{index}].text_preview"})
                return _validation_failure("invalid_evidence_text", diagnostics, len(normalized_actions))
        else:
            safe_text_preview = None
        fact_ids_ref = evidence.get("fact_ids", [])
        if not isinstance(fact_ids_ref, list):
            diagnostics.append({"finding_type": "invalid_fact_ids", "path": f"evidence_items[{index}].fact_ids"})
            return _validation_failure("invalid_fact_ids", diagnostics, len(normalized_actions))
        normalized_fact_ids: list[str] = []
        for key_index, candidate in enumerate(fact_ids_ref):
            identifier = _safe_identifier(candidate, f"evidence_items[{index}].fact_ids[{key_index}]")
            if identifier is None:
                diagnostics.append({"finding_type": "invalid_fact_id_reference", "path": f"evidence_items[{index}].fact_ids[{key_index}]"})
                return _validation_failure("invalid_fact_id_reference", diagnostics, len(normalized_actions))
            if identifier not in fact_ids:
                diagnostics.append({"finding_type": "invalid_fact_reference", "path": f"evidence_items[{index}].fact_ids[{key_index}]"})
                return _validation_failure("invalid_fact_reference", diagnostics, len(normalized_actions))
            normalized_fact_ids.append(identifier)
        source_url = evidence.get("source_url")
        if source_url is not None:
            safe_source_url = _optional_safe_url(source_url, f"evidence_items[{index}].source_url")
            if safe_source_url is False:
                diagnostics.append({"finding_type": "invalid_evidence_source_url", "path": f"evidence_items[{index}].source_url"})
                return _validation_failure("invalid_evidence_source_url", diagnostics, len(normalized_actions))
        else:
            safe_source_url = None
        normalized_evidence.append(
            {
                "evidence_item_id": evidence_id,
                "source_step_id": source_step_id,
                **({"source_url": safe_source_url} if safe_source_url is not None else {}),
                **({"text_quote": safe_text_quote} if safe_text_quote is not None else {}),
                **({"text_preview": safe_text_preview} if safe_text_preview is not None else {}),
                **({"fact_ids": normalized_fact_ids} if normalized_fact_ids else {}),
            }
        )
        evidence_ids.add(evidence_id)

    final_answer_payload = payload.get("final_answer")
    if not isinstance(final_answer_payload, Mapping):
        diagnostics.append(
            {
                "finding_type": "invalid_final_answer_shape",
                "path": "final_answer",
                "present_fields": [],
                "expected_fields": ["answer_text", "cited_fact_ids", "cited_evidence_item_ids"],
            }
        )
        return _validation_failure("invalid_final_answer_shape", diagnostics, len(normalized_actions))

    answer_text = _optional_safe_text(final_answer_payload.get("answer_text"), "final_answer.answer_text")
    if answer_text is False or answer_text is None:
        diagnostics.append({"finding_type": "missing_final_answer_text", "path": "final_answer.answer_text"})
        return _validation_failure("missing_final_answer_text", diagnostics, len(normalized_actions))
    cited_fact_ids_payload = final_answer_payload.get("cited_fact_ids")
    cited_evidence_ids_payload = final_answer_payload.get("cited_evidence_item_ids")
    missing_fields: list[str] = []
    if not isinstance(cited_fact_ids_payload, list) or not cited_fact_ids_payload:
        missing_fields.append("cited_fact_ids")
    if not isinstance(cited_evidence_ids_payload, list) or not cited_evidence_ids_payload:
        missing_fields.append("cited_evidence_item_ids")
    if missing_fields:
        diagnostics.append(
            {
                "finding_type": "invalid_final_answer_citations",
                "path": "final_answer",
                "missing_fields": missing_fields,
            }
        )
        return _validation_failure("invalid_final_answer_citations", diagnostics, len(normalized_actions))
    cited_fact_ids: list[str] = []
    for index, candidate in enumerate(cited_fact_ids_payload):
        identifier = _safe_identifier(candidate, f"final_answer.cited_fact_ids[{index}]")
        if identifier is None or identifier not in fact_ids:
            diagnostics.append({"finding_type": "invalid_fact_reference", "path": f"final_answer.cited_fact_ids[{index}]"})
            return _validation_failure("invalid_fact_reference", diagnostics, len(normalized_actions))
        cited_fact_ids.append(identifier)
    cited_evidence_ids: list[str] = []
    for index, candidate in enumerate(cited_evidence_ids_payload):
        identifier = _safe_identifier(candidate, f"final_answer.cited_evidence_item_ids[{index}]")
        if identifier is None or identifier not in evidence_ids:
            diagnostics.append({"finding_type": "invalid_evidence_reference", "path": f"final_answer.cited_evidence_item_ids[{index}]"})
            return _validation_failure("invalid_evidence_reference", diagnostics, len(normalized_actions))
        cited_evidence_ids.append(identifier)
    confidence = final_answer_payload.get("confidence")
    if confidence is not None and (not isinstance(confidence, (int, float)) or isinstance(confidence, bool)):
        diagnostics.append({"finding_type": "invalid_confidence", "path": "final_answer.confidence"})
        return _validation_failure("invalid_confidence", diagnostics, len(normalized_actions))
    if isinstance(confidence, (int, float)) and not (0.0 <= float(confidence) <= 1.0):
        diagnostics.append({"finding_type": "invalid_confidence", "path": "final_answer.confidence"})
        return _validation_failure("invalid_confidence", diagnostics, len(normalized_actions))

    required_keys = set(scenario_hints["required_fact_keys"])
    output_fact_map = {str(item["key"]): item["value"] for item in normalized_facts}
    missing_required_keys = sorted(key for key in required_keys if key not in output_fact_map)
    if missing_required_keys:
        diagnostics.append({"finding_type": "missing_required_fact_keys", "path": "facts"})
        return _validation_failure("missing_required_fact_keys", diagnostics, len(normalized_actions))

    if not normalized_evidence:
        diagnostics.append({"finding_type": "missing_evidence_items", "path": "evidence_items"})
        return _validation_failure("missing_evidence_items", diagnostics, len(normalized_actions))

    normalized_output = {
        "schema_version": OUTPUT_SCHEMA_VERSION,
        "scenario_id": scenario.scenario_id,
        "workflow_id": scenario.workflow_id,
        "goal": scenario.objective,
        "actions": normalized_actions,
        "facts": normalized_facts,
        "evidence_items": normalized_evidence,
        "final_answer": {
            "answer_text": answer_text,
            "cited_fact_ids": cited_fact_ids,
            "cited_evidence_item_ids": cited_evidence_ids,
            **({"confidence": float(confidence)} if confidence is not None else {}),
        },
        "done_reason": done_reason,
    }
    return {
        "status": "accepted",
        "error_code": None,
        "actions_total": len(normalized_actions),
        "normalized_output": normalized_output,
        "diagnostics": (),
    }


def _execute_fixture_plan(
    *,
    scenario,
    actions: tuple[dict[str, Any], ...],
    facts: tuple[dict[str, Any], ...],
    evidence_items: tuple[dict[str, Any], ...],
    final_answer: Mapping[str, Any],
) -> dict[str, Any]:
    state_facts: dict[str, Any] = {}
    state_evidence_items: list[dict[str, Any]] = []
    session = BrowserRuntimeSession(
        session_id=f"{scenario.workflow_id}_evaluator_session",
        agent_id="stateful_readonly_planner_evaluator",
        workspace_id="stateful_readonly_workspace",
        environment_id="stateful_readonly_environment",
        allowed_domains=ALLOWED_LOCAL_HOSTS,
        start_url=scenario.start_url,
        policy_flags=BrowserRuntimePolicy().to_flags(),
    )
    executor = FixtureBackedBrowserRuntimeExecutor(
        fixture_manifest_path=DEFAULT_FIXTURE_MANIFEST_PATH,
        project_root=Path("."),
        policy=BrowserRuntimePolicy(),
    )
    verifier = BrowserRuntimeVerifier()

    actions_attempted = 0
    actions_succeeded = 0
    actions_failed = 0
    expected_results_total = 0
    expected_results_passed = 0
    expected_results_failed = 0
    matched_url: str | None = None
    final_url: str | None = None
    diagnostics: dict[str, Any] = {
        "action_results": [],
        "actual_facts": [],
        "actual_evidence_items": [],
    }

    for action_payload in actions:
        step = StatefulReadonlyWorkflowStep(
            step_id=str(action_payload["step_id"]),
            action_name=str(action_payload["action_name"]),
            parameters=dict(action_payload["parameters"]),
            expected_text=str(action_payload.get("expected_text") or ""),
            expected_url=str(action_payload.get("expected_url")) if action_payload.get("expected_url") is not None else None,
            collect_fact_keys=tuple(str(item) for item in action_payload.get("collect_fact_keys", [])),
        )
        action = BrowserRuntimeAction(
            agent_id=session.agent_id,
            action_type="browser",
            action_name=step.action_name,
            parameters=dict(step.parameters),
            session_id=session.session_id,
            task_id=scenario.scenario_id,
        )
        result = executor.execute(action, session)
        verification = verifier.verify(
            result,
            expected_text=step.expected_text or None,
            expected_url=step.expected_url,
        )
        actions_attempted += 1
        expected_results_total += 1
        diagnostics["action_results"].append(
            {
                "step_id": step.step_id,
                "action_name": step.action_name,
                "expected_text": step.expected_text or None,
                "expected_url": step.expected_url,
                "status": "succeeded" if result.success and verification.passed else "failed",
                "error_code": None if result.success and verification.passed else (verification.reason or result.error_type),
                "observed_url": result.observation.current_url if result.observation else session.current_url,
                "text_preview": result.observation.text_preview if result.observation else "",
            }
        )
        if not result.success:
            actions_failed += 1
            expected_results_failed += 1
            return {
                "status": "failed",
                "error_code": result.error_type or "fixture_error",
                "failure_class": _failure_class_from_error_code(result.error_type or "fixture_error"),
                "actions_attempted": actions_attempted,
                "actions_succeeded": actions_succeeded,
                "actions_failed": actions_failed,
                "expected_results_total": expected_results_total,
                "expected_results_passed": expected_results_passed,
                "expected_results_failed": expected_results_failed,
                "matched_url": matched_url,
                "final_url": final_url or session.current_url,
                "diagnostics": diagnostics,
            }
        if not verification.passed:
            actions_failed += 1
            expected_results_failed += 1
            return {
                "status": "failed",
                "error_code": verification.reason or "validation_error",
                "failure_class": _failure_class_from_error_code(verification.reason or "validation_error"),
                "actions_attempted": actions_attempted,
                "actions_succeeded": actions_succeeded,
                "actions_failed": actions_failed,
                "expected_results_total": expected_results_total,
                "expected_results_passed": expected_results_passed,
                "expected_results_failed": expected_results_failed,
                "matched_url": matched_url,
                "final_url": final_url or session.current_url,
                "diagnostics": diagnostics,
            }
        actions_succeeded += 1
        expected_results_passed += 1
        observation = result.observation or session.last_observation
        if observation is not None:
            final_url = observation.current_url
            matched_url = observation.current_url
            extracted = scenario.fact_extractor(observation, step, None)
            if extracted:
                evidence_item_id = f"{scenario.workflow_id}-evidence-{len(state_evidence_items) + 1}"
                state_evidence_items.append(
                    {
                        "evidence_item_id": evidence_item_id,
                        "source_step_id": step.step_id,
                        "source_url": observation.current_url,
                        "text_preview": observation.text_preview[:300],
                        "fact_keys": sorted(str(key) for key in extracted.keys()),
                    }
                )
                for key, value in extracted.items():
                    state_facts[key] = value

    provided_fact_map = {str(item["key"]): item["value"] for item in facts}
    expected_fact_keys = set(_scenario_prompt_hints()[scenario.scenario_id]["required_fact_keys"])
    missing_required = sorted(key for key in expected_fact_keys if key not in provided_fact_map)
    if missing_required:
        return {
            "status": "failed",
            "error_code": "missing_required_fact_keys",
            "failure_class": "model_failed_task",
            "actions_attempted": actions_attempted,
            "actions_succeeded": actions_succeeded,
            "actions_failed": actions_failed,
            "expected_results_total": expected_results_total,
            "expected_results_passed": expected_results_passed,
            "expected_results_failed": expected_results_failed,
            "matched_url": matched_url,
            "final_url": final_url,
            "diagnostics": {
                **diagnostics,
                "missing_required_fact_keys": missing_required,
            },
        }

    for key in expected_fact_keys:
        if key in state_facts and provided_fact_map.get(key) != state_facts.get(key):
            return {
                "status": "failed",
                "error_code": "fact_value_mismatch",
                "failure_class": "model_failed_task",
                "actions_attempted": actions_attempted,
                "actions_succeeded": actions_succeeded,
                "actions_failed": actions_failed,
                "expected_results_total": expected_results_total,
                "expected_results_passed": expected_results_passed,
                "expected_results_failed": expected_results_failed,
                "matched_url": matched_url,
                "final_url": final_url,
                "diagnostics": {
                    **diagnostics,
                    "fact_value_mismatch": {"key": key},
                },
            }

    evidence_ids = {item["evidence_item_id"] for item in state_evidence_items}
    fact_ids = {item["fact_id"] for item in facts}
    cited_fact_ids = {str(item) for item in final_answer.get("cited_fact_ids", [])}
    cited_evidence_item_ids = {str(item) for item in final_answer.get("cited_evidence_item_ids", [])}
    if not cited_fact_ids or not cited_fact_ids.issubset(fact_ids):
        return {
            "status": "failed",
            "error_code": "final_answer_citation_missing",
            "failure_class": "model_failed_task",
            "actions_attempted": actions_attempted,
            "actions_succeeded": actions_succeeded,
            "actions_failed": actions_failed,
            "expected_results_total": expected_results_total,
            "expected_results_passed": expected_results_passed,
            "expected_results_failed": expected_results_failed,
            "matched_url": matched_url,
            "final_url": final_url,
            "diagnostics": diagnostics,
        }
    if not cited_evidence_item_ids or not cited_evidence_item_ids.issubset(evidence_ids):
        return {
            "status": "failed",
            "error_code": "final_answer_citation_missing",
            "failure_class": "model_failed_task",
            "actions_attempted": actions_attempted,
            "actions_succeeded": actions_succeeded,
            "actions_failed": actions_failed,
            "expected_results_total": expected_results_total,
            "expected_results_passed": expected_results_passed,
            "expected_results_failed": expected_results_failed,
            "matched_url": matched_url,
            "final_url": final_url,
            "diagnostics": diagnostics,
        }

    diagnostics["actual_facts"] = [
        {"key": key, "value": value}
        for key, value in sorted(state_facts.items(), key=lambda item: item[0])
    ]
    diagnostics["actual_evidence_items"] = list(state_evidence_items)
    return {
        "status": "succeeded",
        "error_code": None,
        "failure_class": "none",
        "actions_attempted": actions_attempted,
        "actions_succeeded": actions_succeeded,
        "actions_failed": actions_failed,
        "expected_results_total": expected_results_total,
        "expected_results_passed": expected_results_passed,
        "expected_results_failed": expected_results_failed,
        "matched_url": matched_url,
        "final_url": final_url,
        "diagnostics": diagnostics,
    }


def _load_packet_manifest(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except OSError as exc:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": None,
            "packet_dir": None,
            "captured_output_dir": None,
            "limitations": DEFAULT_LIMITATIONS,
            "diagnostics": {"config_error": str(exc)},
        }
    except json.JSONDecodeError as exc:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": None,
            "packet_dir": None,
            "captured_output_dir": None,
            "limitations": DEFAULT_LIMITATIONS,
            "diagnostics": {"config_error": str(exc)},
        }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": None,
            "packet_dir": None,
            "captured_output_dir": None,
            "limitations": DEFAULT_LIMITATIONS,
            "diagnostics": {"finding_type": "config_root_must_be_object"},
        }

    schema_version = _safe_text(payload.get("schema_version"))
    if schema_version != "autonomous_browser_stateful_readonly_planner_packet_v1":
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": _safe_text(payload.get("packet_id")),
            "packet_dir": _safe_relative_path(payload.get("output_dir"), "output_dir"),
            "captured_output_dir": _safe_relative_path(payload.get("captured_output_dir"), "captured_output_dir"),
            "limitations": DEFAULT_LIMITATIONS,
            "diagnostics": {"finding_type": "schema_version_mismatch", "path": "schema_version"},
        }

    output_dir = _safe_relative_path(payload.get("output_dir"), "output_dir")
    captured_output_dir = _safe_relative_path(payload.get("captured_output_dir"), "captured_output_dir")
    packet_id = _safe_text(payload.get("packet_id"))
    request_records = payload.get("request_records")
    model_aliases = payload.get("model_aliases", [])
    scenario_ids = payload.get("scenarios", [])
    if (
        packet_id is None
        or output_dir is None
        or captured_output_dir is None
        or not isinstance(request_records, list)
        or not isinstance(model_aliases, list)
        or not isinstance(scenario_ids, list)
    ):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "packet_dir": output_dir,
            "captured_output_dir": captured_output_dir,
            "limitations": DEFAULT_LIMITATIONS,
            "diagnostics": {"finding_type": "invalid_packet_manifest"},
        }

    return {
        "status": "ok",
        "packet": {
            "packet_id": packet_id,
            "packet_dir": path.parent.as_posix(),
            "output_dir": output_dir,
            "captured_output_dir": captured_output_dir,
            "model_aliases": tuple(str(item) for item in model_aliases if isinstance(item, str) and item.strip()),
            "scenario_ids": tuple(str(item) for item in scenario_ids if isinstance(item, str) and item.strip()),
            "request_records": tuple(request_records),
            "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
        },
    }


def _extract_candidate_output(raw_text: str) -> dict[str, Any]:
    spans = _find_top_level_object_spans(raw_text)
    diagnostics = {
        "object_count": len(spans),
        "findings": [],
    }
    if not spans:
        diagnostics["findings"].append({"finding_type": "no_json_object_found"})
        return {
            "status": "rejected",
            "error_code": "no_json_object_found",
            "candidate_output": None,
            "diagnostics": diagnostics,
        }
    if len(spans) > 1:
        diagnostics["findings"].append({"finding_type": "multiple_json_objects_found", "object_count": len(spans)})
        return {
            "status": "rejected",
            "error_code": "multiple_json_objects_found",
            "candidate_output": None,
            "diagnostics": diagnostics,
        }
    try:
        candidate = json.loads(spans[0])
    except json.JSONDecodeError:
        diagnostics["findings"].append({"finding_type": "json_parse_failed", "path": "extracted_json"})
        return {
            "status": "rejected",
            "error_code": "json_parse_failed",
            "candidate_output": None,
            "diagnostics": diagnostics,
        }
    if not isinstance(candidate, dict):
        diagnostics["findings"].append({"finding_type": "invalid_json_root", "path": "extracted_json"})
        return {
            "status": "rejected",
            "error_code": "invalid_json_root",
            "candidate_output": None,
            "diagnostics": diagnostics,
        }
    return {
        "status": "accepted",
        "error_code": None,
        "candidate_output": candidate,
        "diagnostics": diagnostics,
    }


def _find_top_level_object_spans(text: str) -> list[str]:
    spans: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(text):
        if start is None:
            if char == "{":
                start = index
                depth = 1
                in_string = False
                escape = False
            continue

        if in_string:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                spans.append(text[start : index + 1])
                start = None

    return spans


def _validation_failure(error_code: str, diagnostics: list[dict[str, Any]], actions_total: int) -> dict[str, Any]:
    return {
        "status": "rejected",
        "error_code": error_code,
        "actions_total": actions_total,
        "normalized_output": None,
        "diagnostics": tuple(diagnostics),
    }


def _failure_summary(
    *,
    packet_id: str | None,
    packet_dir: str | None,
    output_dir: str | None,
    captured_output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = StatefulReadonlyPlannerEvaluatorSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        packet_id=packet_id,
        packet_dir=packet_dir,
        output_dir=output_dir,
        captured_output_dir=captured_output_dir,
        models_total=0,
        scenarios_total=0,
        workflows_total=0,
        outputs_total=0,
        outputs_present=0,
        outputs_missing=0,
        outputs_ingested=0,
        outputs_rejected=0,
        validation_accepted=0,
        validation_rejected=0,
        dry_runs_succeeded=0,
        dry_runs_failed=0,
        fixture_runs_succeeded=0,
        fixture_runs_failed=0,
        workflows_succeeded=0,
        workflows_failed=0,
        actions_attempted_total=0,
        actions_succeeded_total=0,
        actions_failed_total=0,
        expected_results_total=0,
        expected_results_passed_total=0,
        expected_results_failed_total=0,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        real_network_traffic=False,
        fixture_only=True,
        fixture_execution_requested=False,
        limitations=limitations,
    )
    return summary.to_dict()


def _map_finding_to_error_code(finding_type: str) -> str:
    if finding_type in {
        "absolute_path_not_allowed",
        "external_url_not_allowed",
        "file_url_not_allowed",
        "url_credentials_not_allowed",
        "unsupported_action_name",
    }:
        return "model_output_policy_rejected"
    return "model_failed_task"


def _failure_class_from_error_code(error_code: str) -> str:
    if error_code in {
        "config_validation_failed",
        "invalid_packet_manifest",
        "unknown_scenario_id",
    }:
        return "config_error"
    if error_code in {
        "model_output_policy_rejected",
        "missing_required_fact_keys",
        "invalid_done_reason",
        "missing_evidence_items",
        "final_answer_citation_missing",
        "fact_value_mismatch",
        "model_output_unsupported_action",
    }:
        return "model_failed_task"
    if error_code in {
        "missing_captured_output_file",
        "source_output_read_failed",
    }:
        return "fixture_error"
    if error_code in {
        "absolute_path_not_allowed",
        "external_url_not_allowed",
        "file_url_not_allowed",
        "url_credentials_not_allowed",
    }:
        return "scenario_policy_rejected"
    return "model_failed_task"


def _optional_safe_text(value: Any, path: str) -> str | None | bool:
    if value is None:
        return None
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    issue = _reject_path_or_url(text, path)
    if issue is not None:
        return False
    return text


def _optional_safe_url(value: Any, path: str) -> str | None | bool:
    if value is None:
        return None
    if not isinstance(value, str):
        return False
    text = value.strip()
    if not text:
        return False
    issue = _reject_path_or_url(text, path)
    if issue is not None:
        return False
    return text


def _safe_identifier(value: Any, path: str) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if any(ch.isspace() for ch in text):
        return None
    if any(sep in text for sep in ("/", "\\", ":", "..")):
        return None
    return text


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _normalize_value(value: Any, path: str) -> tuple[Any, dict[str, Any] | None]:
    if value is None or isinstance(value, bool) or isinstance(value, int) or isinstance(value, float):
        return value, None
    if isinstance(value, str):
        text = value.strip()
        issue = _reject_path_or_url(text, path)
        if issue is not None:
            return None, issue
        return text, None
    if isinstance(value, Mapping):
        normalized: dict[str, Any] = {}
        for key, item in value.items():
            if not isinstance(key, str) or not key.strip():
                return None, {"finding_type": "invalid_parameter_key", "path": f"{path}.[key]"}
            clean_key = key.strip()
            normalized_item, issue = _normalize_value(item, f"{path}.{clean_key}")
            if issue is not None:
                return None, issue
            normalized[clean_key] = normalized_item
        return normalized, None
    if isinstance(value, list):
        normalized_items: list[Any] = []
        for index, item in enumerate(value):
            normalized_item, issue = _normalize_value(item, f"{path}[{index}]")
            if issue is not None:
                return None, issue
            normalized_items.append(normalized_item)
        return normalized_items, None
    return None, {"finding_type": "unsupported_parameter_type", "path": path, "type": type(value).__name__}


def _reject_path_or_url(text: str, path: str) -> dict[str, Any] | None:
    normalized = text.strip()
    if not normalized:
        return None
    if normalized.startswith("file://"):
        return {"finding_type": "file_url_not_allowed", "path": path}
    if normalized.startswith("\\\\") or normalized.startswith("/") or (
        len(normalized) >= 3 and normalized[1] == ":" and normalized[2] in {"\\", "/"}
    ):
        return {"finding_type": "absolute_path_not_allowed", "path": path}
    if "://" not in normalized:
        return None
    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        return {"finding_type": "external_url_not_allowed", "path": path}
    host = (parsed.hostname or "").lower()
    if host not in ALLOWED_LOCAL_HOSTS:
        return {"finding_type": "external_url_not_allowed", "path": path}
    return None


def _resolve_repo_path(value: str | Path, repo: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo / path


def _relative_path(repo: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return path.name


def _safe_relative_path(value: Any, label: str) -> str | None:
    del label
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return None
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        return None
    return path.as_posix()


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set):
        return [_jsonable(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
