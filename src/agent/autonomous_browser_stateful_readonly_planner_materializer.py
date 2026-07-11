from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_stateful_readonly_planner_evaluator import (
    _extract_candidate_output,
    _failure_class_from_error_code,
    _load_packet_manifest,
    _safe_relative_path,
    _validate_stateful_output,
)
from .autonomous_browser_stateful_readonly_planner_packet import (
    DEFAULT_CAPTURED_OUTPUT_DIR,
    DEFAULT_OUTPUT_DIR,
    DEFAULT_RAW_OUTPUT_FILENAME,
    DEFAULT_REQUEST_FILENAME,
    DEFAULT_RESPONSE_FILENAME,
    DEFAULT_LIMITATIONS,
    SUMMARY_SCHEMA_VERSION as PACKET_SUMMARY_SCHEMA_VERSION,
    _scenario_prompt_hints,
)
from .autonomous_browser_stateful_readonly_workflow import (
    build_default_stateful_readonly_workflow_scenarios,
)


SUMMARY_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_materializer_summary_v1"
STATE_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_materialized_state_v1"
TRACE_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_materialized_trace_v1"
WORKFLOW_SUMMARY_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_materialized_workflow_summary_v1"
DEFAULT_PACKET_MANIFEST_FILENAME = "autonomous_browser_stateful_readonly_planner_packet.json"
DEFAULT_PACKET_SUMMARY_FILENAME = "autonomous_browser_stateful_readonly_planner_packet_summary.json"
DEFAULT_MATERIALIZED_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/stateful_readonly_planner_materialized"
DEFAULT_MATERIALIZED_STATE_FILENAME = "workflow_state.json"
DEFAULT_MATERIALIZED_TRACE_FILENAME = "workflow_trace.json"
DEFAULT_MATERIALIZED_WORKFLOW_SUMMARY_FILENAME = "workflow_summary.json"
DEFAULT_LIMITATIONS = (
    "offline stateful planner materializer only",
    "fixture-backed planner outputs only",
    "no model calls",
    "no real browser execution",
    "no Playwright execution",
    "not production browser automation",
)


@dataclass(frozen=True)
class StatefulReadonlyPlannerMaterializedState:
    schema_version: str
    packet_id: str
    model_alias: str
    scenario_id: str
    workflow_id: str
    goal: str
    status: str
    error_code: str | None
    failure_class: str
    visited_urls: tuple[str, ...]
    planned_actions: tuple[dict[str, Any], ...]
    facts: tuple[dict[str, Any], ...]
    evidence_items: tuple[dict[str, Any], ...]
    final_answer: Mapping[str, Any] | None
    done_reason: str | None
    source_output_path: str
    source_response_path: str | None = None
    model_execution: bool = False
    real_browser_execution: bool = False
    playwright_execution: bool = False
    browser_opened: bool = False
    real_network_traffic: bool = False
    fixture_only: bool = True
    no_runtime_execution: bool = True

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "model_alias": self.model_alias,
            "scenario_id": self.scenario_id,
            "workflow_id": self.workflow_id,
            "goal": self.goal,
            "status": self.status,
            "error_code": self.error_code,
            "failure_class": self.failure_class,
            "visited_urls": list(self.visited_urls),
            "planned_actions": [dict(item) for item in self.planned_actions],
            "facts": [dict(item) for item in self.facts],
            "evidence_items": [dict(item) for item in self.evidence_items],
            "final_answer": dict(self.final_answer) if isinstance(self.final_answer, Mapping) else self.final_answer,
            "done_reason": self.done_reason,
            "source_output_path": self.source_output_path,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "real_network_traffic": self.real_network_traffic,
            "fixture_only": self.fixture_only,
            "no_runtime_execution": self.no_runtime_execution,
        }
        if self.source_response_path is not None:
            payload["source_response_path"] = self.source_response_path
        return payload


@dataclass(frozen=True)
class StatefulReadonlyPlannerMaterializedTrace:
    schema_version: str
    packet_id: str
    model_alias: str
    scenario_id: str
    workflow_id: str
    status: str
    trace_entries: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "model_alias": self.model_alias,
            "scenario_id": self.scenario_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "trace_entries": [dict(item) for item in self.trace_entries],
        }


@dataclass(frozen=True)
class StatefulReadonlyPlannerMaterializedWorkflowSummary:
    schema_version: str
    packet_id: str
    model_alias: str
    scenario_id: str
    workflow_id: str
    status: str
    error_code: str | None
    failure_class: str
    actions_total: int
    facts_total: int
    evidence_items_total: int
    final_answer_present: bool
    state_path: str | None
    trace_path: str | None
    source_output_path: str
    model_execution: bool = False
    real_browser_execution: bool = False
    playwright_execution: bool = False
    browser_opened: bool = False
    real_network_traffic: bool = False
    fixture_only: bool = True
    no_runtime_execution: bool = True
    diagnostics: dict[str, Any] | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "model_alias": self.model_alias,
            "scenario_id": self.scenario_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "error_code": self.error_code,
            "failure_class": self.failure_class,
            "actions_total": self.actions_total,
            "facts_total": self.facts_total,
            "evidence_items_total": self.evidence_items_total,
            "final_answer_present": self.final_answer_present,
            "state_path": self.state_path,
            "trace_path": self.trace_path,
            "source_output_path": self.source_output_path,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "real_network_traffic": self.real_network_traffic,
            "fixture_only": self.fixture_only,
            "no_runtime_execution": self.no_runtime_execution,
        }
        if self.diagnostics is not None:
            payload["diagnostics"] = dict(self.diagnostics)
        return payload


@dataclass(frozen=True)
class StatefulReadonlyPlannerMaterializerSummary:
    schema_version: str
    packet_id: str | None
    status: str
    error_code: str | None
    outputs_total: int
    outputs_present: int
    outputs_missing: int
    outputs_accepted: int
    outputs_rejected: int
    workflows_materialized: int
    workflows_failed: int
    actions_total: int
    facts_total: int
    evidence_items_total: int
    final_answers_total: int
    failure_class_counts: dict[str, int]
    materialized_workflow_summaries: tuple[dict[str, Any], ...]
    output_dir: str | None
    model_execution: bool = False
    real_browser_execution: bool = False
    playwright_execution: bool = False
    browser_opened: bool = False
    real_network_traffic: bool = False
    fixture_only: bool = True
    no_runtime_execution: bool = True
    limitations: tuple[str, ...] = DEFAULT_LIMITATIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "status": self.status,
            "error_code": self.error_code,
            "outputs_total": self.outputs_total,
            "outputs_present": self.outputs_present,
            "outputs_missing": self.outputs_missing,
            "outputs_accepted": self.outputs_accepted,
            "outputs_rejected": self.outputs_rejected,
            "workflows_materialized": self.workflows_materialized,
            "workflows_failed": self.workflows_failed,
            "actions_total": self.actions_total,
            "facts_total": self.facts_total,
            "evidence_items_total": self.evidence_items_total,
            "final_answers_total": self.final_answers_total,
            "failure_class_counts": dict(self.failure_class_counts),
            "materialized_workflow_summaries": [dict(item) for item in self.materialized_workflow_summaries],
            "output_dir": self.output_dir,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "real_network_traffic": self.real_network_traffic,
            "fixture_only": self.fixture_only,
            "no_runtime_execution": self.no_runtime_execution,
            "limitations": list(self.limitations),
        }


def run_autonomous_browser_stateful_readonly_planner_materializer(
    packet_dir: str | Path,
    *,
    repo_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    packet_root = _resolve_repo_path(packet_dir, repo)
    manifest = _load_packet_manifest(packet_root / DEFAULT_PACKET_MANIFEST_FILENAME)
    summary = _load_packet_summary(packet_root / DEFAULT_PACKET_SUMMARY_FILENAME)
    if manifest.get("status") != "ok" or summary.get("status") != "ok":
        error_code = str(manifest.get("error_code") or summary.get("error_code") or "config_validation_failed")
        return _failure_summary(
            packet_id=manifest.get("packet_id") or summary.get("packet_id"),
            output_dir=_safe_relative_path(output_dir or DEFAULT_MATERIALIZED_OUTPUT_DIR, "output_dir"),
            error_code=error_code,
            limitations=tuple(manifest.get("limitations") or summary.get("limitations") or DEFAULT_LIMITATIONS),
        )

    packet = manifest["packet"]
    packet_summary = summary["packet"]
    packet_id = str(packet["packet_id"])
    if packet_id != str(packet_summary["packet_id"]):
        return _failure_summary(
            packet_id=packet_id,
            output_dir=_safe_relative_path(output_dir or DEFAULT_MATERIALIZED_OUTPUT_DIR, "output_dir"),
            error_code="config_validation_failed",
            limitations=tuple(packet.get("limitations") or DEFAULT_LIMITATIONS),
        )

    output_dir_value = _safe_relative_path(output_dir or DEFAULT_MATERIALIZED_OUTPUT_DIR, "output_dir")
    if output_dir_value is None:
        return _failure_summary(
            packet_id=packet_id,
            output_dir=None,
            error_code="config_validation_failed",
            limitations=tuple(packet.get("limitations") or DEFAULT_LIMITATIONS),
        )

    output_root = repo / output_dir_value
    output_root.mkdir(parents=True, exist_ok=True)

    scenario_defs = build_default_stateful_readonly_workflow_scenarios()
    scenario_hints = _scenario_prompt_hints()

    outputs_total = len(packet["request_records"])
    outputs_present = 0
    outputs_missing = 0
    outputs_accepted = 0
    outputs_rejected = 0
    workflows_materialized = 0
    workflows_failed = 0
    actions_total = 0
    facts_total = 0
    evidence_items_total = 0
    final_answers_total = 0
    failure_class_counts: Counter[str] = Counter()
    first_issue_code: str | None = None
    materialized_workflow_summaries: list[dict[str, Any]] = []

    for record in packet["request_records"]:
        scenario_id = str(record["scenario_id"])
        workflow_result = _materialize_request_record(
            record=record,
            repo=repo,
            output_root=output_root,
            output_dir_value=output_dir_value,
            packet_id=packet_id,
            scenario_defs=scenario_defs,
            scenario_hints=scenario_hints[scenario_id],
        )
        materialized_workflow_summaries.append(workflow_result["summary"])
        failure_class_counts.update([workflow_result["summary"]["failure_class"]])
        if workflow_result["present"]:
            outputs_present += 1
            if workflow_result["accepted"]:
                outputs_accepted += 1
                workflows_materialized += 1
                actions_total += workflow_result["summary"]["actions_total"]
                facts_total += workflow_result["summary"]["facts_total"]
                evidence_items_total += workflow_result["summary"]["evidence_items_total"]
                final_answers_total += 1 if workflow_result["summary"]["final_answer_present"] else 0
            else:
                outputs_rejected += 1
                workflows_failed += 1
                if first_issue_code is None and workflow_result["summary"]["error_code"] is not None:
                    first_issue_code = workflow_result["summary"]["error_code"]
        else:
            outputs_missing += 1
            workflows_failed += 1

    if outputs_rejected:
        status = "completed_with_failures"
        error_code = first_issue_code or "materialization_failed"
    elif outputs_missing:
        status = "completed_with_missing_outputs"
        error_code = "missing_captured_outputs"
    else:
        status = "succeeded"
        error_code = None

    suite_summary = StatefulReadonlyPlannerMaterializerSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        packet_id=packet_id,
        status=status,
        error_code=error_code,
        outputs_total=outputs_total,
        outputs_present=outputs_present,
        outputs_missing=outputs_missing,
        outputs_accepted=outputs_accepted,
        outputs_rejected=outputs_rejected,
        workflows_materialized=workflows_materialized,
        workflows_failed=workflows_failed,
        actions_total=actions_total,
        facts_total=facts_total,
        evidence_items_total=evidence_items_total,
        final_answers_total=final_answers_total,
        failure_class_counts=dict(sorted(failure_class_counts.items())),
        materialized_workflow_summaries=tuple(materialized_workflow_summaries),
        output_dir=output_dir_value,
        limitations=tuple(packet.get("limitations") or DEFAULT_LIMITATIONS),
    )
    payload = suite_summary.to_dict()
    _write_json(output_root / "autonomous_browser_stateful_readonly_planner_materializer_summary.json", payload)
    return payload


def write_autonomous_browser_stateful_readonly_planner_materializer_summary(
    summary: Mapping[str, Any],
    output_dir: str | Path,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "autonomous_browser_stateful_readonly_planner_materializer_summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _materialize_request_record(
    *,
    record: Mapping[str, Any],
    repo: Path,
    output_root: Path,
    output_dir_value: str,
    packet_id: str,
    scenario_defs,
    scenario_hints: Mapping[str, tuple[str, ...]],
) -> dict[str, Any]:
    model_alias = _safe_identifier(record.get("model_alias"))
    scenario_id = _safe_identifier(record.get("scenario_id"))
    workflow_id = _safe_identifier(record.get("workflow_id"))
    output_path_rel = _safe_relative_path(record.get("output_path"), "output_path")
    response_path_rel = _safe_relative_path(record.get("response_path"), "response_path")
    if model_alias is None or scenario_id is None or workflow_id is None or output_path_rel is None:
        summary = _build_workflow_summary(
            packet_id=packet_id,
            model_alias=model_alias or "unknown_model",
            scenario_id=scenario_id or "unknown_scenario",
            workflow_id=workflow_id or "unknown_workflow",
            status="failed",
            error_code="config_validation_failed",
            failure_class="config_error",
            actions_total=0,
            facts_total=0,
            evidence_items_total=0,
            final_answer_present=False,
            state_path=None,
            trace_path=None,
            source_output_path=output_path_rel or "unknown_output",
            diagnostics={"finding_type": "invalid_request_record"},
        )
        _write_json(output_root / (model_alias or "unknown_model") / (scenario_id or "unknown_scenario") / DEFAULT_MATERIALIZED_WORKFLOW_SUMMARY_FILENAME, summary)
        return {"summary": summary, "accepted": False, "present": False}

    scenario = scenario_defs.get(scenario_id)
    if scenario is None:
        summary = _build_workflow_summary(
            packet_id=packet_id,
            model_alias=model_alias,
            scenario_id=scenario_id,
            workflow_id=workflow_id,
            status="failed",
            error_code="unknown_scenario_id",
            failure_class="config_error",
            actions_total=0,
            facts_total=0,
            evidence_items_total=0,
            final_answer_present=False,
            state_path=None,
            trace_path=None,
            source_output_path=output_path_rel,
            diagnostics={"finding_type": "unknown_scenario_id"},
        )
        workflow_dir = output_root / model_alias / scenario_id
        _write_json(workflow_dir / DEFAULT_MATERIALIZED_WORKFLOW_SUMMARY_FILENAME, summary)
        return {"summary": summary, "accepted": False, "present": False}

    raw_path = repo / output_path_rel
    workflow_dir = output_root / model_alias / scenario_id
    workflow_dir.mkdir(parents=True, exist_ok=True)
    summary_path = workflow_dir / DEFAULT_MATERIALIZED_WORKFLOW_SUMMARY_FILENAME
    state_path = workflow_dir / DEFAULT_MATERIALIZED_STATE_FILENAME
    trace_path = workflow_dir / DEFAULT_MATERIALIZED_TRACE_FILENAME

    if not raw_path.exists():
        summary = _build_workflow_summary(
            packet_id=packet_id,
            model_alias=model_alias,
            scenario_id=scenario_id,
            workflow_id=workflow_id,
            status="missing",
            error_code="missing_captured_output_file",
            failure_class="missing_output",
            actions_total=0,
            facts_total=0,
            evidence_items_total=0,
            final_answer_present=False,
            state_path=None,
            trace_path=None,
            source_output_path=output_path_rel,
            source_response_path=response_path_rel,
            diagnostics={"source_output_path": output_path_rel},
        )
        _write_json(summary_path, summary)
        return {"summary": summary, "accepted": False, "present": False}

    try:
        raw_text = raw_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        summary = _build_workflow_summary(
            packet_id=packet_id,
            model_alias=model_alias,
            scenario_id=scenario_id,
            workflow_id=workflow_id,
            status="failed",
            error_code="source_output_read_failed",
            failure_class="fixture_error",
            actions_total=0,
            facts_total=0,
            evidence_items_total=0,
            final_answer_present=False,
            state_path=None,
            trace_path=None,
            source_output_path=output_path_rel,
            source_response_path=response_path_rel,
            diagnostics={"source_output_path": output_path_rel, "error_message": str(exc)},
        )
        _write_json(summary_path, summary)
        return {"summary": summary, "accepted": False, "present": True}

    extracted = _extract_candidate_output(raw_text)
    if extracted["status"] != "accepted":
        error_code = str(extracted["error_code"] or "model_failed_task")
        summary = _build_workflow_summary(
            packet_id=packet_id,
            model_alias=model_alias,
            scenario_id=scenario_id,
            workflow_id=workflow_id,
            status="rejected",
            error_code=error_code,
            failure_class=_failure_class_from_error_code(error_code),
            actions_total=0,
            facts_total=0,
            evidence_items_total=0,
            final_answer_present=False,
            state_path=None,
            trace_path=None,
            source_output_path=output_path_rel,
            source_response_path=response_path_rel,
            diagnostics=dict(extracted.get("diagnostics", {})),
        )
        _write_json(summary_path, summary)
        return {"summary": summary, "accepted": False, "present": True}

    validation = _validate_stateful_output(
        extracted["candidate_output"],
        scenario=scenario,
        scenario_hints=scenario_hints,
    )
    if validation["status"] != "accepted":
        error_code = str(validation["error_code"] or "model_failed_task")
        summary = _build_workflow_summary(
            packet_id=packet_id,
            model_alias=model_alias,
            scenario_id=scenario_id,
            workflow_id=workflow_id,
            status="rejected",
            error_code=error_code,
            failure_class=_failure_class_from_error_code(error_code),
            actions_total=0,
            facts_total=0,
            evidence_items_total=0,
            final_answer_present=False,
            state_path=None,
            trace_path=None,
            source_output_path=output_path_rel,
            source_response_path=response_path_rel,
            diagnostics=_jsonable(validation.get("diagnostics")),
        )
        _write_json(summary_path, summary)
        return {"summary": summary, "accepted": False, "present": True}

    normalized_output = validation["normalized_output"]
    state_payload = _build_state_payload(
        packet_id=packet_id,
        model_alias=model_alias,
        scenario_id=scenario_id,
        workflow_id=workflow_id,
        source_output_path=output_path_rel,
        source_response_path=response_path_rel if response_path_rel and (repo / response_path_rel).exists() else None,
        normalized_output=normalized_output,
    )
    trace_payload = _build_trace_payload(
        packet_id=packet_id,
        model_alias=model_alias,
        scenario_id=scenario_id,
        workflow_id=workflow_id,
        source_output_path=output_path_rel,
        normalized_output=normalized_output,
    )
    _write_json(state_path, state_payload)
    _write_json(trace_path, trace_payload)
    summary = _build_workflow_summary(
        packet_id=packet_id,
        model_alias=model_alias,
        scenario_id=scenario_id,
        workflow_id=workflow_id,
        status="succeeded",
        error_code=None,
        failure_class="none",
        actions_total=len(normalized_output["actions"]),
        facts_total=len(normalized_output["facts"]),
        evidence_items_total=len(normalized_output["evidence_items"]),
        final_answer_present=True,
        state_path=f"{output_dir_value}/{model_alias}/{scenario_id}/{DEFAULT_MATERIALIZED_STATE_FILENAME}",
        trace_path=f"{output_dir_value}/{model_alias}/{scenario_id}/{DEFAULT_MATERIALIZED_TRACE_FILENAME}",
        source_output_path=output_path_rel,
        source_response_path=response_path_rel if response_path_rel and (repo / response_path_rel).exists() else None,
        diagnostics={"source_output_path": output_path_rel},
    )
    _write_json(summary_path, summary)
    return {"summary": summary, "accepted": True, "present": True}


def _build_state_payload(
    *,
    packet_id: str,
    model_alias: str,
    scenario_id: str,
    workflow_id: str,
    source_output_path: str,
    source_response_path: str | None,
    normalized_output: Mapping[str, Any],
) -> dict[str, Any]:
    visited_urls: list[str] = []
    for action in normalized_output["actions"]:
        parameters = action.get("parameters", {})
        if isinstance(parameters, Mapping):
            url = parameters.get("url")
            if isinstance(url, str) and url not in visited_urls:
                visited_urls.append(url)
        expected_url = action.get("expected_url")
        if isinstance(expected_url, str) and expected_url not in visited_urls:
            visited_urls.append(expected_url)
    for fact in normalized_output["facts"]:
        source_url = fact.get("source_url")
        if isinstance(source_url, str) and source_url not in visited_urls:
            visited_urls.append(source_url)
    for evidence in normalized_output["evidence_items"]:
        source_url = evidence.get("source_url")
        if isinstance(source_url, str) and source_url not in visited_urls:
            visited_urls.append(source_url)

    payload = StatefulReadonlyPlannerMaterializedState(
        schema_version=STATE_SCHEMA_VERSION,
        packet_id=packet_id,
        model_alias=model_alias,
        scenario_id=scenario_id,
        workflow_id=workflow_id,
        goal=str(normalized_output["goal"]),
        status="succeeded",
        error_code=None,
        failure_class="none",
        visited_urls=tuple(visited_urls),
        planned_actions=tuple(dict(item) for item in normalized_output["actions"]),
        facts=tuple(dict(item) for item in normalized_output["facts"]),
        evidence_items=tuple(dict(item) for item in normalized_output["evidence_items"]),
        final_answer=normalized_output["final_answer"],
        done_reason=str(normalized_output.get("done_reason")) if normalized_output.get("done_reason") is not None else None,
        source_output_path=source_output_path,
        source_response_path=source_response_path,
    )
    return payload.to_dict()


def _build_trace_payload(
    *,
    packet_id: str,
    model_alias: str,
    scenario_id: str,
    workflow_id: str,
    source_output_path: str,
    normalized_output: Mapping[str, Any],
) -> dict[str, Any]:
    trace_entries: list[dict[str, Any]] = []
    for step_index, action in enumerate(normalized_output["actions"], start=1):
        trace_entry: dict[str, Any] = {
            "step_index": step_index,
            "step_id": action["step_id"],
            "action_name": action["action_name"],
            "action_parameters": dict(action["parameters"]),
            "status": "planned",
            "error_code": None,
            "no_runtime_execution": True,
            "source_output_path": source_output_path,
        }
        if action.get("expected_text") is not None:
            trace_entry["expected_text"] = action["expected_text"]
        if action.get("expected_url") is not None:
            trace_entry["expected_url"] = action["expected_url"]
        if action.get("collect_fact_keys"):
            trace_entry["collect_fact_keys"] = list(action["collect_fact_keys"])
        trace_entries.append(trace_entry)
    payload = StatefulReadonlyPlannerMaterializedTrace(
        schema_version=TRACE_SCHEMA_VERSION,
        packet_id=packet_id,
        model_alias=model_alias,
        scenario_id=scenario_id,
        workflow_id=workflow_id,
        status="planned",
        trace_entries=tuple(trace_entries),
    )
    return payload.to_dict()


def _build_workflow_summary(
    *,
    packet_id: str,
    model_alias: str,
    scenario_id: str,
    workflow_id: str,
    status: str,
    error_code: str | None,
    failure_class: str,
    actions_total: int,
    facts_total: int,
    evidence_items_total: int,
    final_answer_present: bool,
    state_path: str | None,
    trace_path: str | None,
    source_output_path: str,
    source_response_path: str | None = None,
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    summary = StatefulReadonlyPlannerMaterializedWorkflowSummary(
        schema_version=WORKFLOW_SUMMARY_SCHEMA_VERSION,
        packet_id=packet_id,
        model_alias=model_alias,
        scenario_id=scenario_id,
        workflow_id=workflow_id,
        status=status,
        error_code=error_code,
        failure_class=failure_class,
        actions_total=actions_total,
        facts_total=facts_total,
        evidence_items_total=evidence_items_total,
        final_answer_present=final_answer_present,
        state_path=state_path,
        trace_path=trace_path,
        source_output_path=source_output_path,
        diagnostics=dict(diagnostics) if diagnostics is not None else None,
    )
    return summary.to_dict()


def _load_packet_summary(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": None,
            "limitations": DEFAULT_LIMITATIONS,
            "diagnostics": {"config_error": str(exc)},
        }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": None,
            "limitations": DEFAULT_LIMITATIONS,
            "diagnostics": {"finding_type": "packet_summary_root_must_be_object"},
        }
    if str(payload.get("schema_version", "")).strip() != PACKET_SUMMARY_SCHEMA_VERSION:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": _safe_text(payload.get("packet_id")),
            "limitations": DEFAULT_LIMITATIONS,
            "diagnostics": {"finding_type": "packet_summary_schema_version_mismatch"},
        }
    packet_id = _safe_text(payload.get("packet_id"))
    if packet_id is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": None,
            "limitations": DEFAULT_LIMITATIONS,
            "diagnostics": {"finding_type": "packet_summary_missing_packet_id"},
        }
    return {
        "status": "ok",
        "packet": {
            "packet_id": packet_id,
            "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
        },
    }


def _failure_summary(
    *,
    packet_id: str | None,
    output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = StatefulReadonlyPlannerMaterializerSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        packet_id=packet_id,
        status="failed",
        error_code=error_code,
        outputs_total=0,
        outputs_present=0,
        outputs_missing=0,
        outputs_accepted=0,
        outputs_rejected=0,
        workflows_materialized=0,
        workflows_failed=0,
        actions_total=0,
        facts_total=0,
        evidence_items_total=0,
        final_answers_total=0,
        failure_class_counts={},
        materialized_workflow_summaries=(),
        output_dir=output_dir,
        limitations=limitations,
    )
    return summary.to_dict()


def _resolve_repo_path(value: str | Path, repo: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo / path


def _safe_identifier(value: Any) -> str | None:
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


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
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
