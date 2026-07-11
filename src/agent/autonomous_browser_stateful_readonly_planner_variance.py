from __future__ import annotations

import os
import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_stateful_readonly_planner_evaluator import (
    _extract_candidate_output,
    _failure_class_from_error_code,
    _int as _evaluator_int,
    _load_packet_manifest as _load_packet_manifest_from_evaluator,
    _safe_relative_path,
    _validate_stateful_output,
    build_default_stateful_readonly_workflow_scenarios,
)
from .autonomous_browser_stateful_readonly_planner_packet import (
    DEFAULT_ALLOWED_ACTIONS,
    DEFAULT_CAPTURED_OUTPUT_DIR,
    DEFAULT_DISALLOWED_ACTIONS,
    DEFAULT_MODEL_ALIASES,
    DEFAULT_OUTPUT_DIR as DEFAULT_PACKET_OUTPUT_DIR,
    DEFAULT_PROMPT_FILENAME,
    DEFAULT_RAW_OUTPUT_FILENAME,
    DEFAULT_REQUEST_FILENAME,
    DEFAULT_REQUEST_MODEL_PATH,
    DEFAULT_RESPONSE_FILENAME,
    DEFAULT_SCENARIO_IDS,
    DEFAULT_LIMITATIONS as BASE_LIMITATIONS,
    DEFAULT_TEMPERATURE,
    DEFAULT_MAX_TOKENS,
    OUTPUT_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION as BASE_PACKET_SUMMARY_SCHEMA_VERSION,
    _build_expected_output_schema_doc,
    _build_request_payload,
    _build_scenario_prompt_text,
    _load_config as _load_base_packet_config,
    _scenario_prompt_hints,
)
from .autonomous_browser_stateful_readonly_planner_materializer import (
    DEFAULT_MATERIALIZED_OUTPUT_DIR as DEFAULT_VARIANCE_MATERIALIZED_OUTPUT_DIR,
)


BUILD_CONFIG_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_variance_config_v1"
PACKET_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_variance_packet_v1"
PACKET_SUMMARY_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_variance_packet_summary_v1"
RUNTIME_CONFIG_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_variance_evaluator_config_v1"
EVALUATOR_SUMMARY_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_variance_evaluator_summary_v1"
MATERIALIZER_SUMMARY_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_variance_materializer_summary_v1"
MATERIALIZED_STATE_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_variance_materialized_state_v1"
MATERIALIZED_TRACE_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_variance_materialized_trace_v1"
MATERIALIZED_WORKFLOW_SUMMARY_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_variance_materialized_workflow_summary_v1"

DEFAULT_PACKET_ID = "phase_13e4_stateful_readonly_planner_variance"
DEFAULT_BASE_PACKET_CONFIG = "configs/autonomous_runtime/browser_stateful_readonly_planner_packet.example.json"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_packets/stateful_readonly_planner_variance"
DEFAULT_CAPTURED_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_outputs/stateful_readonly_planner_variance"
DEFAULT_EVALUATOR_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_summaries/stateful_readonly_planner_variance_evaluator"
DEFAULT_MATERIALIZED_OUTPUT_DIR = DEFAULT_VARIANCE_MATERIALIZED_OUTPUT_DIR
DEFAULT_RUNTIME_CONFIG_FILENAME = "variance_config.local.json"
DEFAULT_PACKET_SUMMARY_FILENAME = "autonomous_browser_stateful_readonly_planner_variance_packet_summary.json"
DEFAULT_PACKET_MANIFEST_FILENAME = "autonomous_browser_stateful_readonly_planner_variance_packet.json"
DEFAULT_REQUEST_RECORDS_FILENAME = "request_records.json"
DEFAULT_REQUEST_PATHS_FILENAME = "request_paths.json"
DEFAULT_OUTPUT_PATHS_FILENAME = "output_paths.json"
DEFAULT_COMMANDS_FILENAME = "commands.json"
DEFAULT_COMMANDS_MD_FILENAME = "commands.md"
DEFAULT_README_FILENAME = "README.md"
DEFAULT_EXPECTED_OUTPUT_SCHEMA_FILENAME = "expected_output_schema.md"
DEFAULT_TRIAL_COUNT = 3
DEFAULT_TRIAL_IDS = tuple(f"trial_{index:02d}" for index in range(1, DEFAULT_TRIAL_COUNT + 1))
DEFAULT_TRIAL_LABEL_PREFIX = "trial"
DEFAULT_MODEL_ALIAS = "third_model"
DEFAULT_LIMITATIONS = (
    "offline repeated stateful planner variance only",
    "manual third_model runs only",
    "no model calls by Codex",
    "no real browser execution",
    "fixture-backed replay remains offline only",
    "not production browser automation",
)


@dataclass(frozen=True)
class StatefulReadonlyPlannerVarianceBuildConfig:
    schema_version: str
    packet_id: str
    base_packet_config: str
    model_aliases: tuple[str, ...]
    scenarios: tuple[str, ...]
    trials_per_scenario: int
    output_dir: str
    captured_output_dir: str
    materialized_output_dir: str
    fixture_only: bool
    external_network_allowed: bool
    writes_allowed: bool
    model_execution: bool
    real_browser_execution: bool
    playwright_execution: bool
    browser_opened: bool
    limitations: tuple[str, ...] = DEFAULT_LIMITATIONS

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "StatefulReadonlyPlannerVarianceBuildConfig":
        schema_version = str(payload.get("schema_version", "")).strip()
        packet_id = _safe_identifier(payload.get("packet_id"), "packet_id")
        base_packet_config = _safe_relative_path(payload.get("base_packet_config", DEFAULT_BASE_PACKET_CONFIG), "base_packet_config")
        model_aliases = tuple(_required_identifier_list(payload.get("model_aliases"), "model_aliases"))
        scenarios = tuple(_required_identifier_list(payload.get("scenarios"), "scenarios"))
        trials_per_scenario = _required_int(payload.get("trials_per_scenario", DEFAULT_TRIAL_COUNT), "trials_per_scenario")
        output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir")
        captured_output_dir = _safe_relative_path(payload.get("captured_output_dir", DEFAULT_CAPTURED_OUTPUT_DIR), "captured_output_dir")
        materialized_output_dir = _safe_relative_path(payload.get("materialized_output_dir", DEFAULT_MATERIALIZED_OUTPUT_DIR), "materialized_output_dir")
        fixture_only = _required_bool(payload.get("fixture_only", True), "fixture_only")
        external_network_allowed = _required_bool(payload.get("external_network_allowed", False), "external_network_allowed")
        writes_allowed = _required_bool(payload.get("writes_allowed", False), "writes_allowed")
        model_execution = _required_bool(payload.get("model_execution", False), "model_execution")
        real_browser_execution = _required_bool(payload.get("real_browser_execution", False), "real_browser_execution")
        playwright_execution = _required_bool(payload.get("playwright_execution", False), "playwright_execution")
        browser_opened = _required_bool(payload.get("browser_opened", False), "browser_opened")
        limitations = tuple(
            str(item).strip()
            for item in payload.get("limitations", [])
            if isinstance(item, str) and item.strip()
        )

        if schema_version != BUILD_CONFIG_SCHEMA_VERSION:
            raise ValueError("schema_version must match autonomous_browser_stateful_readonly_planner_variance_config_v1.")
        if packet_id is None:
            raise ValueError("packet_id must be a safe identifier.")
        if base_packet_config is None:
            raise ValueError("base_packet_config must be a safe relative path.")
        if list(model_aliases) != list(DEFAULT_MODEL_ALIASES):
            raise ValueError("model_aliases must match the default stateful variance alias set.")
        if list(scenarios) != list(DEFAULT_SCENARIO_IDS):
            raise ValueError("scenarios must match the five stateful read-only workflow scenarios.")
        if trials_per_scenario != DEFAULT_TRIAL_COUNT:
            raise ValueError("trials_per_scenario must be exactly 3.")
        if output_dir is None or captured_output_dir is None or materialized_output_dir is None:
            raise ValueError("output_dir, captured_output_dir, and materialized_output_dir must be safe relative paths.")
        if not fixture_only:
            raise ValueError("fixture_only must be true.")
        if external_network_allowed:
            raise ValueError("external_network_allowed must be false.")
        if writes_allowed:
            raise ValueError("writes_allowed must be false.")
        if model_execution:
            raise ValueError("model_execution must be false.")
        if real_browser_execution:
            raise ValueError("real_browser_execution must be false.")
        if playwright_execution:
            raise ValueError("playwright_execution must be false.")
        if browser_opened:
            raise ValueError("browser_opened must be false.")

        return cls(
            schema_version=schema_version,
            packet_id=packet_id,
            base_packet_config=base_packet_config,
            model_aliases=model_aliases,
            scenarios=scenarios,
            trials_per_scenario=trials_per_scenario,
            output_dir=output_dir,
            captured_output_dir=captured_output_dir,
            materialized_output_dir=materialized_output_dir,
            fixture_only=fixture_only,
            external_network_allowed=external_network_allowed,
            writes_allowed=writes_allowed,
            model_execution=model_execution,
            real_browser_execution=real_browser_execution,
            playwright_execution=playwright_execution,
            browser_opened=browser_opened,
            limitations=limitations or DEFAULT_LIMITATIONS,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "base_packet_config": self.base_packet_config,
            "model_aliases": list(self.model_aliases),
            "scenarios": list(self.scenarios),
            "trials_per_scenario": self.trials_per_scenario,
            "output_dir": self.output_dir,
            "captured_output_dir": self.captured_output_dir,
            "materialized_output_dir": self.materialized_output_dir,
            "fixture_only": self.fixture_only,
            "external_network_allowed": self.external_network_allowed,
            "writes_allowed": self.writes_allowed,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class StatefulReadonlyPlannerVariancePacketSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    model_execution: bool
    real_browser_execution: bool
    playwright_execution: bool
    browser_opened: bool
    packet_id: str | None
    base_packet_config: str | None
    output_dir: str | None
    captured_output_dir: str | None
    materialized_output_dir: str | None
    models_total: int
    scenarios_total: int
    trials_per_scenario: int
    trials_total: int
    requests_total: int
    fixture_only: bool
    model_aliases: tuple[str, ...] = ()
    scenario_ids: tuple[str, ...] = ()
    trial_ids: tuple[str, ...] = ()
    request_records: tuple[dict[str, Any], ...] = ()
    packet_files: tuple[str, ...] = ()
    request_records_path: str | None = None
    request_paths_path: str | None = None
    output_paths_path: str | None = None
    variance_config_path: str | None = None
    expected_output_schema_path: str | None = None
    commands_count: int = 0
    limitations: tuple[str, ...] = DEFAULT_LIMITATIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "packet_id": self.packet_id,
            "base_packet_config": self.base_packet_config,
            "output_dir": self.output_dir,
            "captured_output_dir": self.captured_output_dir,
            "materialized_output_dir": self.materialized_output_dir,
            "models_total": self.models_total,
            "scenarios_total": self.scenarios_total,
            "trials_per_scenario": self.trials_per_scenario,
            "trials_total": self.trials_total,
            "requests_total": self.requests_total,
            "fixture_only": self.fixture_only,
            "model_aliases": list(self.model_aliases),
            "scenario_ids": list(self.scenario_ids),
            "trial_ids": list(self.trial_ids),
            "request_records": [_jsonable(item) for item in self.request_records],
            "packet_files": list(self.packet_files),
            "request_records_path": self.request_records_path,
            "request_paths_path": self.request_paths_path,
            "output_paths_path": self.output_paths_path,
            "variance_config_path": self.variance_config_path,
            "expected_output_schema_path": self.expected_output_schema_path,
            "commands_count": self.commands_count,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class StatefulReadonlyPlannerVarianceTrialSummary:
    model_alias: str
    scenario_id: str
    trial_id: str
    trial_label: str
    status: str
    error_code: str | None
    failure_class: str
    finish_reason: str | None
    validation_status: str
    workflow_status: str
    actions_total: int
    facts_total: int
    evidence_items_total: int
    final_answer_present: bool
    source_output_path: str
    captured_output_present: bool = False
    no_runtime_execution: bool = True
    model_execution: bool = False
    real_browser_execution: bool = False
    playwright_execution: bool = False
    browser_opened: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_alias": self.model_alias,
            "scenario_id": self.scenario_id,
            "trial_id": self.trial_id,
            "trial_label": self.trial_label,
            "status": self.status,
            "error_code": self.error_code,
            "failure_class": self.failure_class,
            "finish_reason": self.finish_reason,
            "validation_status": self.validation_status,
            "workflow_status": self.workflow_status,
            "actions_total": self.actions_total,
            "facts_total": self.facts_total,
            "evidence_items_total": self.evidence_items_total,
            "final_answer_present": self.final_answer_present,
            "source_output_path": self.source_output_path,
            "captured_output_present": self.captured_output_present,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
        }


@dataclass(frozen=True)
class StatefulReadonlyPlannerVarianceScenarioSummary:
    scenario_id: str
    outputs_total: int
    outputs_present: int
    outputs_missing: int
    outputs_ingested: int
    outputs_rejected: int
    validation_accepted: int
    validation_rejected: int
    workflows_succeeded: int
    workflows_failed: int
    pass_rate: float
    validation_acceptance_rate: float
    finish_reason_counts: dict[str, int]
    failure_class_counts: dict[str, int]
    action_count_values: tuple[int, ...]
    facts_count_values: tuple[int, ...]
    evidence_count_values: tuple[int, ...]
    final_answer_present_count: int
    route_stable: bool = False
    action_sequence_stable: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "outputs_total": self.outputs_total,
            "outputs_present": self.outputs_present,
            "outputs_missing": self.outputs_missing,
            "outputs_ingested": self.outputs_ingested,
            "outputs_rejected": self.outputs_rejected,
            "validation_accepted": self.validation_accepted,
            "validation_rejected": self.validation_rejected,
            "workflows_succeeded": self.workflows_succeeded,
            "workflows_failed": self.workflows_failed,
            "pass_rate": self.pass_rate,
            "validation_acceptance_rate": self.validation_acceptance_rate,
            "finish_reason_counts": dict(self.finish_reason_counts),
            "failure_class_counts": dict(self.failure_class_counts),
            "action_count_values": list(self.action_count_values),
            "facts_count_values": list(self.facts_count_values),
            "evidence_count_values": list(self.evidence_count_values),
            "final_answer_present_count": self.final_answer_present_count,
            "route_stable": self.route_stable,
            "action_sequence_stable": self.action_sequence_stable,
        }


@dataclass(frozen=True)
class StatefulReadonlyPlannerVarianceEvaluatorSummary:
    schema_version: str
    packet_id: str | None
    status: str
    error_code: str | None
    models_total: int
    scenarios_total: int
    trials_per_scenario: int
    outputs_total: int
    outputs_present: int
    outputs_missing: int
    outputs_ingested: int
    outputs_rejected: int
    validation_accepted: int
    validation_rejected: int
    workflows_succeeded: int
    workflows_failed: int
    finish_reason_counts: dict[str, int]
    failure_class_counts: dict[str, int]
    scenario_summaries: tuple[dict[str, Any], ...]
    trial_summaries: tuple[dict[str, Any], ...]
    output_summaries: tuple[dict[str, Any], ...]
    pass_rate_overall: float
    validation_acceptance_rate: float
    packet_output_dir: str | None
    output_dir: str | None
    materialized_output_dir: str | None
    model_aliases: tuple[str, ...] = ()
    scenario_ids: tuple[str, ...] = ()
    trial_ids: tuple[str, ...] = ()
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
            "models_total": self.models_total,
            "scenarios_total": self.scenarios_total,
            "trials_per_scenario": self.trials_per_scenario,
            "outputs_total": self.outputs_total,
            "outputs_present": self.outputs_present,
            "outputs_missing": self.outputs_missing,
            "outputs_ingested": self.outputs_ingested,
            "outputs_rejected": self.outputs_rejected,
            "validation_accepted": self.validation_accepted,
            "validation_rejected": self.validation_rejected,
            "workflows_succeeded": self.workflows_succeeded,
            "workflows_failed": self.workflows_failed,
            "finish_reason_counts": dict(self.finish_reason_counts),
            "failure_class_counts": dict(self.failure_class_counts),
            "scenario_summaries": [_jsonable(item) for item in self.scenario_summaries],
            "trial_summaries": [_jsonable(item) for item in self.trial_summaries],
            "output_summaries": [_jsonable(item) for item in self.output_summaries],
            "pass_rate_overall": self.pass_rate_overall,
            "validation_acceptance_rate": self.validation_acceptance_rate,
            "packet_output_dir": self.packet_output_dir,
            "output_dir": self.output_dir,
            "materialized_output_dir": self.materialized_output_dir,
            "model_aliases": list(self.model_aliases),
            "scenario_ids": list(self.scenario_ids),
            "trial_ids": list(self.trial_ids),
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "real_network_traffic": self.real_network_traffic,
            "fixture_only": self.fixture_only,
            "no_runtime_execution": self.no_runtime_execution,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class StatefulReadonlyPlannerVarianceMaterializedState:
    schema_version: str
    packet_id: str
    model_alias: str
    scenario_id: str
    trial_id: str
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
            "trial_id": self.trial_id,
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
class StatefulReadonlyPlannerVarianceMaterializedTrace:
    schema_version: str
    packet_id: str
    model_alias: str
    scenario_id: str
    trial_id: str
    workflow_id: str
    status: str
    trace_entries: tuple[dict[str, Any], ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "model_alias": self.model_alias,
            "scenario_id": self.scenario_id,
            "trial_id": self.trial_id,
            "workflow_id": self.workflow_id,
            "status": self.status,
            "trace_entries": [dict(item) for item in self.trace_entries],
        }


@dataclass(frozen=True)
class StatefulReadonlyPlannerVarianceMaterializedWorkflowSummary:
    schema_version: str
    packet_id: str
    model_alias: str
    scenario_id: str
    trial_id: str
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
    source_response_path: str | None = None
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
            "trial_id": self.trial_id,
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
        if self.source_response_path is not None:
            payload["source_response_path"] = self.source_response_path
        if self.diagnostics is not None:
            payload["diagnostics"] = dict(self.diagnostics)
        return payload


@dataclass(frozen=True)
class StatefulReadonlyPlannerVarianceMaterializerSummary:
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
    scenario_summaries: tuple[dict[str, Any], ...]
    trial_summaries: tuple[dict[str, Any], ...]
    output_summaries: tuple[dict[str, Any], ...]
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
            "scenario_summaries": [_jsonable(item) for item in self.scenario_summaries],
            "trial_summaries": [_jsonable(item) for item in self.trial_summaries],
            "output_summaries": [_jsonable(item) for item in self.output_summaries],
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


def build_autonomous_browser_stateful_readonly_planner_variance_packet(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    config = _load_build_config(config_artifact)
    if config["status"] != "ok":
        return _build_failure_summary(
            schema_version=PACKET_SUMMARY_SCHEMA_VERSION,
            packet_id=config.get("packet_id"),
            output_dir=config.get("output_dir"),
            captured_output_dir=config.get("captured_output_dir"),
            materialized_output_dir=config.get("materialized_output_dir"),
            error_code=str(config.get("error_code") or "config_validation_failed"),
            limitations=tuple(config.get("limitations") or DEFAULT_LIMITATIONS),
        )

    build_config = StatefulReadonlyPlannerVarianceBuildConfig.from_dict(config["config"])
    base_packet_path = repo / build_config.base_packet_config
    base_packet = _load_base_packet_config(base_packet_path)
    if base_packet["status"] != "ok":
        return _build_failure_summary(
            schema_version=PACKET_SUMMARY_SCHEMA_VERSION,
            packet_id=build_config.packet_id,
            output_dir=build_config.output_dir,
            captured_output_dir=build_config.captured_output_dir,
            materialized_output_dir=build_config.materialized_output_dir,
            error_code=str(base_packet.get("error_code") or "config_validation_failed"),
            limitations=build_config.limitations,
        )

    base_config = base_packet["config"]
    if list(base_config["model_aliases"]) != list(build_config.model_aliases):
        return _build_failure_summary(
            schema_version=PACKET_SUMMARY_SCHEMA_VERSION,
            packet_id=build_config.packet_id,
            output_dir=build_config.output_dir,
            captured_output_dir=build_config.captured_output_dir,
            materialized_output_dir=build_config.materialized_output_dir,
            error_code="config_validation_failed",
            limitations=build_config.limitations,
        )
    if list(base_config["scenarios"]) != list(build_config.scenarios):
        return _build_failure_summary(
            schema_version=PACKET_SUMMARY_SCHEMA_VERSION,
            packet_id=build_config.packet_id,
            output_dir=build_config.output_dir,
            captured_output_dir=build_config.captured_output_dir,
            materialized_output_dir=build_config.materialized_output_dir,
            error_code="config_validation_failed",
            limitations=build_config.limitations,
        )

    packet_dir = repo / build_config.output_dir
    packet_dir.mkdir(parents=True, exist_ok=True)
    captured_output_dir = repo / build_config.captured_output_dir
    captured_output_dir.mkdir(parents=True, exist_ok=True)
    materialized_output_dir = repo / build_config.materialized_output_dir
    materialized_output_dir.mkdir(parents=True, exist_ok=True)

    scenarios = build_default_stateful_readonly_workflow_scenarios()
    request_paths: dict[str, dict[str, dict[str, str]]] = {}
    output_paths: dict[str, dict[str, dict[str, str]]] = {}
    trial_records: list[dict[str, Any]] = []
    packet_files: list[str] = []
    model_aliases = list(build_config.model_aliases)
    scenario_ids = list(build_config.scenarios)
    trial_ids = list(DEFAULT_TRIAL_IDS)

    expected_output_schema_rel = f"{build_config.output_dir}/{DEFAULT_EXPECTED_OUTPUT_SCHEMA_FILENAME}"
    _write_text(packet_dir / DEFAULT_EXPECTED_OUTPUT_SCHEMA_FILENAME, _build_expected_output_schema_doc())
    packet_files.append(expected_output_schema_rel)

    prompt_paths: dict[str, str] = {}
    for scenario_id in scenario_ids:
        scenario = scenarios[scenario_id]
        prompt_dir = packet_dir / "prompts" / scenario_id
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = prompt_dir / DEFAULT_PROMPT_FILENAME
        prompt_text = _build_scenario_prompt_text(scenario_id=scenario_id, scenario=scenario)
        _write_text(prompt_path, prompt_text)
        prompt_rel = f"{build_config.output_dir}/prompts/{scenario_id}/{DEFAULT_PROMPT_FILENAME}"
        prompt_paths[scenario_id] = prompt_rel
        packet_files.append(prompt_rel)

    for model_alias in model_aliases:
        request_paths[model_alias] = {}
        output_paths[model_alias] = {}
        captured_model_dir = captured_output_dir / model_alias
        captured_model_dir.mkdir(parents=True, exist_ok=True)
        model_dir = packet_dir / model_alias
        model_dir.mkdir(parents=True, exist_ok=True)
        for scenario_id in scenario_ids:
            scenario = scenarios[scenario_id]
            request_paths[model_alias][scenario_id] = {}
            output_paths[model_alias][scenario_id] = {}
            scenario_dir = model_dir / scenario_id
            captured_scenario_dir = captured_model_dir / scenario_id
            scenario_dir.mkdir(parents=True, exist_ok=True)
            captured_scenario_dir.mkdir(parents=True, exist_ok=True)
            prompt_rel = prompt_paths[scenario_id]
            for trial_index, trial_label in enumerate(trial_ids, start=1):
                trial_id = f"{scenario_id}__{trial_label}"
                trial_dir = scenario_dir / trial_label
                captured_trial_dir = captured_scenario_dir / trial_label
                trial_dir.mkdir(parents=True, exist_ok=True)
                captured_trial_dir.mkdir(parents=True, exist_ok=True)
                request_rel = f"{build_config.output_dir}/{model_alias}/{scenario_id}/{trial_label}/{DEFAULT_REQUEST_FILENAME}"
                response_rel = f"{build_config.captured_output_dir}/{model_alias}/{scenario_id}/{trial_label}/{DEFAULT_RESPONSE_FILENAME}"
                raw_output_rel = f"{build_config.captured_output_dir}/{model_alias}/{scenario_id}/{trial_label}/{DEFAULT_RAW_OUTPUT_FILENAME}"
                request_path = trial_dir / DEFAULT_REQUEST_FILENAME
                request_payload = _build_request_payload(
                    packet_id=build_config.packet_id,
                    model_alias=model_alias,
                    prompt_prefix=base_config["prompt_prefixes"].get(model_alias),
                    scenario=scenario,
                    trial_id=trial_id,
                    prompt_path=prompt_rel,
                    request_path=request_rel,
                    response_path=response_rel,
                    raw_output_path=raw_output_rel,
                    max_tokens=int(base_config.get("max_tokens", DEFAULT_MAX_TOKENS)),
                    temperature=float(base_config.get("temperature", DEFAULT_TEMPERATURE)),
                    prompt_filename=DEFAULT_PROMPT_FILENAME,
                )
                request_payload["metadata"]["trial_label"] = trial_label
                request_payload["metadata"]["trial_index"] = trial_index
                request_payload["metadata"]["trials_per_scenario"] = build_config.trials_per_scenario
                request_payload["metadata"]["base_packet_config"] = build_config.base_packet_config
                trial_note = _trial_note(trial_label)
                request_payload["messages"][1]["content"] = f"{request_payload['messages'][1]['content']}\n{trial_note}".rstrip()
                _write_json(request_path, request_payload)
                request_paths[model_alias][scenario_id][trial_label] = request_rel
                output_paths[model_alias][scenario_id][trial_label] = raw_output_rel
                trial_records.append(
                    {
                        "model_alias": model_alias,
                        "model_path": DEFAULT_REQUEST_MODEL_PATH,
                        "scenario_id": scenario_id,
                        "trial_id": trial_id,
                        "trial_label": trial_label,
                        "trial_index": trial_index,
                        "workflow_id": scenario.workflow_id,
                        "request_path": request_rel,
                        "prompt_path": prompt_rel,
                        "response_path": response_rel,
                        "output_path": raw_output_rel,
                        "raw_output_path": raw_output_rel,
                        "prompt_prefix": base_config["prompt_prefixes"].get(model_alias),
                        "max_tokens": int(base_config.get("max_tokens", DEFAULT_MAX_TOKENS)),
                    }
                )
                packet_files.extend([request_rel, response_rel, raw_output_rel])

    request_paths_path = packet_dir / DEFAULT_REQUEST_PATHS_FILENAME
    _write_json(request_paths_path, request_paths)
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_REQUEST_PATHS_FILENAME}")

    output_paths_path = packet_dir / DEFAULT_OUTPUT_PATHS_FILENAME
    _write_json(output_paths_path, output_paths)
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_OUTPUT_PATHS_FILENAME}")

    trial_records_path = packet_dir / DEFAULT_REQUEST_RECORDS_FILENAME
    _write_json(trial_records_path, trial_records)
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_REQUEST_RECORDS_FILENAME}")

    variance_config = _build_runtime_config(
        packet_id=build_config.packet_id,
        packet_output_dir=build_config.output_dir,
        evaluation_output_dir=DEFAULT_EVALUATOR_OUTPUT_DIR,
        materialized_output_dir=build_config.materialized_output_dir,
        model_aliases=model_aliases,
        scenario_ids=scenario_ids,
        trial_ids=trial_ids,
        trial_records=trial_records,
        limitations=build_config.limitations,
    )
    variance_config_path = packet_dir / DEFAULT_RUNTIME_CONFIG_FILENAME
    _write_json(variance_config_path, variance_config)
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_RUNTIME_CONFIG_FILENAME}")

    commands = _build_commands(
        packet_id=build_config.packet_id,
        output_dir=build_config.output_dir,
        captured_output_dir=build_config.captured_output_dir,
        evaluation_output_dir=DEFAULT_EVALUATOR_OUTPUT_DIR,
        materialized_output_dir=build_config.materialized_output_dir,
        model_aliases=model_aliases,
        scenario_ids=scenario_ids,
        trial_ids=trial_ids,
    )
    _write_json(packet_dir / DEFAULT_COMMANDS_FILENAME, {"commands": commands})
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_COMMANDS_FILENAME}")

    commands_md = _build_commands_markdown(
        packet_id=build_config.packet_id,
        output_dir=build_config.output_dir,
        captured_output_dir=build_config.captured_output_dir,
        evaluation_output_dir=DEFAULT_EVALUATOR_OUTPUT_DIR,
        materialized_output_dir=build_config.materialized_output_dir,
        model_aliases=model_aliases,
        scenario_ids=scenario_ids,
        trial_ids=trial_ids,
    )
    _write_text(packet_dir / DEFAULT_COMMANDS_MD_FILENAME, commands_md)
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_COMMANDS_MD_FILENAME}")

    readme_text = _build_readme(
        packet_id=build_config.packet_id,
        output_dir=build_config.output_dir,
        captured_output_dir=build_config.captured_output_dir,
        materialized_output_dir=build_config.materialized_output_dir,
        evaluation_output_dir=DEFAULT_EVALUATOR_OUTPUT_DIR,
        model_aliases=model_aliases,
        scenario_ids=scenario_ids,
        trial_ids=trial_ids,
        request_paths=request_paths,
        output_paths=output_paths,
    )
    _write_text(packet_dir / DEFAULT_README_FILENAME, readme_text)
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_README_FILENAME}")

    manifest = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "packet_id": build_config.packet_id,
        "base_packet_config": build_config.base_packet_config,
        "model_aliases": model_aliases,
        "scenarios": scenario_ids,
        "trial_ids": trial_ids,
        "trials_per_scenario": build_config.trials_per_scenario,
        "request_records": trial_records,
        "request_count": len(trial_records),
        "requests_total": len(trial_records),
        "output_dir": build_config.output_dir,
        "captured_output_dir": build_config.captured_output_dir,
        "materialized_output_dir": build_config.materialized_output_dir,
        "expected_output_schema_path": expected_output_schema_rel,
        "request_paths_path": f"{build_config.output_dir}/{DEFAULT_REQUEST_PATHS_FILENAME}",
        "output_paths_path": f"{build_config.output_dir}/{DEFAULT_OUTPUT_PATHS_FILENAME}",
        "request_records_path": f"{build_config.output_dir}/{DEFAULT_REQUEST_RECORDS_FILENAME}",
        "variance_config_path": f"{build_config.output_dir}/{DEFAULT_RUNTIME_CONFIG_FILENAME}",
        "commands_path": f"{build_config.output_dir}/{DEFAULT_COMMANDS_FILENAME}",
        "commands_md_path": f"{build_config.output_dir}/{DEFAULT_COMMANDS_MD_FILENAME}",
        "no_runtime_execution": True,
        "model_execution": False,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
        "fixture_only": build_config.fixture_only,
        "external_network_allowed": build_config.external_network_allowed,
        "writes_allowed": build_config.writes_allowed,
        "limitations": list(build_config.limitations),
    }
    _write_json(packet_dir / "autonomous_browser_stateful_readonly_planner_variance_packet.json", manifest)
    packet_files.append(f"{build_config.output_dir}/autonomous_browser_stateful_readonly_planner_variance_packet.json")

    summary_payload = StatefulReadonlyPlannerVariancePacketSummary(
        schema_version=PACKET_SUMMARY_SCHEMA_VERSION,
        status="succeeded",
        error_code=None,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        packet_id=build_config.packet_id,
        base_packet_config=build_config.base_packet_config,
        output_dir=build_config.output_dir,
        captured_output_dir=build_config.captured_output_dir,
        materialized_output_dir=build_config.materialized_output_dir,
        models_total=len(model_aliases),
        scenarios_total=len(scenario_ids),
        trials_per_scenario=build_config.trials_per_scenario,
        trials_total=len(trial_records),
        requests_total=len(trial_records),
        fixture_only=build_config.fixture_only,
        model_aliases=tuple(model_aliases),
        scenario_ids=tuple(scenario_ids),
        trial_ids=tuple(trial_ids),
        request_records=tuple(trial_records),
        packet_files=tuple(packet_files + [f"{build_config.output_dir}/autonomous_browser_stateful_readonly_planner_variance_packet.json"]),
        request_records_path=f"{build_config.output_dir}/{DEFAULT_REQUEST_RECORDS_FILENAME}",
        request_paths_path=f"{build_config.output_dir}/{DEFAULT_REQUEST_PATHS_FILENAME}",
        output_paths_path=f"{build_config.output_dir}/{DEFAULT_OUTPUT_PATHS_FILENAME}",
        variance_config_path=f"{build_config.output_dir}/{DEFAULT_RUNTIME_CONFIG_FILENAME}",
        expected_output_schema_path=expected_output_schema_rel,
        commands_count=len(commands),
        limitations=build_config.limitations,
    )
    payload = summary_payload.to_dict()
    _write_json(packet_dir / "autonomous_browser_stateful_readonly_planner_variance_packet_summary.json", payload)
    return payload


def run_autonomous_browser_stateful_readonly_planner_variance_evaluator(
    config_artifact: str | Path | Mapping[str, Any] | None = None,
    *,
    packet_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    packet_context = (
        _load_packet_context(packet_dir, repo_root=repo)
        if packet_dir is not None
        else _load_packet_context_from_build_config(config_artifact, repo_root=repo)
    )
    if packet_context["status"] != "ok":
        return _evaluator_failure_summary(
            packet_id=packet_context.get("packet_id"),
            packet_output_dir=packet_context.get("packet_dir") or packet_context.get("packet_output_dir"),
            output_dir=packet_context.get("packet_output_dir") or packet_context.get("packet_dir"),
            materialized_output_dir=packet_context.get("materialized_output_dir"),
            error_code=str(packet_context.get("error_code") or "config_validation_failed"),
            limitations=tuple(packet_context.get("limitations") or DEFAULT_LIMITATIONS),
            diagnostics=_jsonable({key: value for key, value in packet_context.items() if key not in {"status", "limitations"}}),
        )

    packet_output_dir = str(packet_context["packet_output_dir"])
    output_dir = packet_output_dir
    materialized_output_dir = str(packet_context["materialized_output_dir"])
    packet_id = str(packet_context["packet_id"])
    model_aliases = tuple(packet_context["model_aliases"])
    scenario_ids = tuple(packet_context["scenario_ids"])
    trial_ids = tuple(packet_context["trial_ids"])
    trial_records = tuple(packet_context["request_records"])
    limitations = tuple(packet_context.get("limitations") or DEFAULT_LIMITATIONS)

    output_root = repo / output_dir
    output_root.mkdir(parents=True, exist_ok=True)

    scenario_defs = build_default_stateful_readonly_workflow_scenarios()
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
            "workflows_succeeded": 0,
            "workflows_failed": 0,
            "pass_rate": 0.0,
            "validation_acceptance_rate": 0.0,
            "finish_reason_counts": Counter(),
            "failure_class_counts": Counter(),
            "action_count_values": set(),
            "facts_count_values": set(),
            "evidence_count_values": set(),
            "final_answer_present_count": 0,
        }
        for scenario_id in scenario_ids
    }
    trial_summaries: list[dict[str, Any]] = []
    output_summaries: list[dict[str, Any]] = []
    finish_reason_counts: Counter[str] = Counter()
    failure_class_counts: Counter[str] = Counter()

    outputs_total = len(trial_records)
    outputs_present = 0
    outputs_missing = 0
    outputs_ingested = 0
    outputs_rejected = 0
    validation_accepted = 0
    validation_rejected = 0
    workflows_succeeded = 0
    workflows_failed = 0
    first_issue_code: str | None = None

    for record in trial_records:
        scenario_id = str(record["scenario_id"])
        scenario = scenario_defs[scenario_id]
        trial_result = _evaluate_trial_record(
            repo_root=repo,
            packet_id=packet_id,
            packet_output_dir=packet_output_dir,
            record=record,
            scenario=scenario,
            execute_fixture=True,
        )
        actions_total_value = _evaluator_int(trial_result.get("actions_total"))
        facts_total_value = _evaluator_int(trial_result.get("facts_total"))
        evidence_items_total_value = _evaluator_int(trial_result.get("evidence_items_total"))
        final_answer_present_value = bool(trial_result.get("final_answer_present"))
        output_summaries.append(trial_result)
        trial_summaries.append(
            {
                "model_alias": trial_result["model_alias"],
                "scenario_id": trial_result["scenario_id"],
                "trial_id": trial_result["trial_id"],
                "trial_label": trial_result["trial_label"],
                "status": trial_result["status"],
                "error_code": trial_result["error_code"],
                "failure_class": trial_result["failure_class"],
                "finish_reason": trial_result["finish_reason"],
                "validation_status": trial_result["validation_status"],
                "workflow_status": trial_result["workflow_status"],
                "actions_total": actions_total_value,
                "facts_total": facts_total_value,
                "evidence_items_total": evidence_items_total_value,
                "final_answer_present": final_answer_present_value,
                "source_output_path": trial_result["source_output_path"],
                "captured_output_present": trial_result["captured_output_present"],
                "no_runtime_execution": True,
                "model_execution": False,
                "real_browser_execution": False,
                "playwright_execution": False,
                "browser_opened": False,
            }
        )

        scenario_summary = scenario_summary_map[scenario_id]
        scenario_summary["outputs_total"] += 1
        failure_class_counts.update([trial_result["failure_class"]])
        scenario_summary["failure_class_counts"].update([trial_result["failure_class"]])
        if trial_result["finish_reason"] is not None:
            finish_reason_counts.update([trial_result["finish_reason"]])
            scenario_summary["finish_reason_counts"].update([trial_result["finish_reason"]])

        if trial_result["captured_output_present"]:
            outputs_present += 1
            scenario_summary["outputs_present"] += 1
            if trial_result["validation_status"] == "accepted":
                validation_accepted += 1
                outputs_ingested += 1
                workflows_succeeded += 1
                scenario_summary["validation_accepted"] += 1
                scenario_summary["outputs_ingested"] += 1
                scenario_summary["workflows_succeeded"] += 1
                scenario_summary["action_count_values"].add(actions_total_value)
                scenario_summary["facts_count_values"].add(facts_total_value)
                scenario_summary["evidence_count_values"].add(evidence_items_total_value)
                if final_answer_present_value:
                    scenario_summary["final_answer_present_count"] += 1
            else:
                validation_rejected += 1
                outputs_rejected += 1
                workflows_failed += 1
                scenario_summary["validation_rejected"] += 1
                scenario_summary["outputs_rejected"] += 1
                scenario_summary["workflows_failed"] += 1
                if first_issue_code is None:
                    first_issue_code = str(trial_result.get("error_code") or "variance_output_failed")
        else:
            outputs_missing += 1
            workflows_failed += 1
            scenario_summary["outputs_missing"] += 1
            scenario_summary["workflows_failed"] += 1
            if first_issue_code is None:
                first_issue_code = str(trial_result.get("error_code") or "missing_captured_output_file")

    scenario_summaries: list[dict[str, Any]] = []
    for scenario_id, summary in scenario_summary_map.items():
        outputs_present_for_scenario = summary["outputs_present"]
        summary["pass_rate"] = _safe_ratio(summary["workflows_succeeded"], summary["outputs_total"])
        summary["validation_acceptance_rate"] = _safe_ratio(summary["validation_accepted"], outputs_present_for_scenario)
        summary["action_count_values"] = sorted(summary["action_count_values"])
        summary["facts_count_values"] = sorted(summary["facts_count_values"])
        summary["evidence_count_values"] = sorted(summary["evidence_count_values"])
        summary["finish_reason_counts"] = dict(sorted(summary["finish_reason_counts"].items()))
        summary["failure_class_counts"] = dict(sorted(summary["failure_class_counts"].items()))
        scenario_summaries.append(summary)

    if outputs_missing > 0:
        status = "completed_with_missing_outputs"
        error_code = "missing_captured_outputs"
    elif outputs_rejected > 0:
        status = "completed_with_failures"
        error_code = first_issue_code or "variance_output_failed"
    else:
        status = "succeeded"
        error_code = None

    evaluator_summary = StatefulReadonlyPlannerVarianceEvaluatorSummary(
        schema_version=EVALUATOR_SUMMARY_SCHEMA_VERSION,
        packet_id=packet_id,
        status=status,
        error_code=error_code,
        models_total=len(model_aliases),
        scenarios_total=len(scenario_ids),
        trials_per_scenario=len(trial_ids),
        outputs_total=outputs_total,
        outputs_present=outputs_present,
        outputs_missing=outputs_missing,
        outputs_ingested=outputs_ingested,
        outputs_rejected=outputs_rejected,
        validation_accepted=validation_accepted,
        validation_rejected=validation_rejected,
        workflows_succeeded=workflows_succeeded,
        workflows_failed=workflows_failed,
        finish_reason_counts=dict(sorted(finish_reason_counts.items())),
        failure_class_counts=dict(sorted(failure_class_counts.items())),
        scenario_summaries=tuple(scenario_summaries),
        trial_summaries=tuple(trial_summaries),
        output_summaries=tuple(output_summaries),
        pass_rate_overall=_safe_ratio(workflows_succeeded, outputs_total),
        validation_acceptance_rate=_safe_ratio(validation_accepted, outputs_present),
        packet_output_dir=packet_output_dir,
        output_dir=output_dir,
        materialized_output_dir=materialized_output_dir,
        model_aliases=model_aliases,
        scenario_ids=scenario_ids,
        trial_ids=trial_ids,
        model_execution=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        real_network_traffic=False,
        fixture_only=True,
        no_runtime_execution=True,
        limitations=limitations,
    )
    payload = evaluator_summary.to_dict()
    _write_json(output_root / "autonomous_browser_stateful_readonly_planner_variance_evaluator_summary.json", payload)
    return payload


def run_autonomous_browser_stateful_readonly_planner_variance_materializer(
    config_artifact: str | Path | Mapping[str, Any] | None = None,
    *,
    packet_dir: str | Path | None = None,
    output_dir: str | Path | None = None,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    packet_context = (
        _load_packet_context(packet_dir, repo_root=repo)
        if packet_dir is not None
        else _load_packet_context_from_build_config(config_artifact, repo_root=repo)
    )
    if packet_context["status"] != "ok":
        return _materializer_failure_summary(
            packet_id=packet_context.get("packet_id"),
            output_dir=packet_context.get("materialized_output_dir") or packet_context.get("packet_dir"),
            error_code=str(packet_context.get("error_code") or "config_validation_failed"),
            limitations=tuple(packet_context.get("limitations") or DEFAULT_LIMITATIONS),
            diagnostics=_jsonable({key: value for key, value in packet_context.items() if key not in {"status", "limitations"}}),
        )

    packet_id = str(packet_context["packet_id"])
    packet_output_dir = str(packet_context["packet_output_dir"])
    output_dir_path = Path(output_dir) if output_dir is not None else Path(str(packet_context["materialized_output_dir"]))
    if not output_dir_path.is_absolute():
        output_dir_path = repo / output_dir_path
    output_dir = _repo_relative_path(repo, output_dir_path)
    model_aliases = tuple(packet_context["model_aliases"])
    scenario_ids = tuple(packet_context["scenario_ids"])
    trial_ids = tuple(packet_context["trial_ids"])
    trial_records = tuple(packet_context["request_records"])
    limitations = tuple(packet_context.get("limitations") or DEFAULT_LIMITATIONS)

    output_root = output_dir_path
    output_root.mkdir(parents=True, exist_ok=True)

    scenario_defs = build_default_stateful_readonly_workflow_scenarios()
    scenario_summary_map: dict[str, dict[str, Any]] = {
        scenario_id: {
            "scenario_id": scenario_id,
            "outputs_total": 0,
            "outputs_present": 0,
            "outputs_missing": 0,
            "outputs_accepted": 0,
            "outputs_rejected": 0,
            "workflows_materialized": 0,
            "workflows_failed": 0,
            "failure_class_counts": Counter(),
            "actions_total": 0,
            "facts_total": 0,
            "evidence_items_total": 0,
            "final_answers_total": 0,
        }
        for scenario_id in scenario_ids
    }

    trial_summaries: list[dict[str, Any]] = []
    output_summaries: list[dict[str, Any]] = []
    outputs_total = len(trial_records)
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

    for record in trial_records:
        scenario_id = str(record["scenario_id"])
        scenario = scenario_defs[scenario_id]
        trial_result = _materialize_trial_record(
            repo_root=repo,
            packet_id=packet_id,
            packet_output_dir=packet_output_dir,
            materialized_output_dir=output_dir,
            record=record,
            scenario=scenario,
        )
        actions_total_value = _evaluator_int(trial_result.get("actions_total"))
        facts_total_value = _evaluator_int(trial_result.get("facts_total"))
        evidence_items_total_value = _evaluator_int(trial_result.get("evidence_items_total"))
        final_answer_present_value = bool(trial_result.get("final_answer_present"))
        output_summaries.append(trial_result)
        trial_summaries.append(
            {
                "model_alias": trial_result["model_alias"],
                "scenario_id": trial_result["scenario_id"],
                "trial_id": trial_result["trial_id"],
                "trial_label": trial_result["trial_label"],
                "status": trial_result["status"],
                "error_code": trial_result["error_code"],
                "failure_class": trial_result["failure_class"],
                "actions_total": actions_total_value,
                "facts_total": facts_total_value,
                "evidence_items_total": evidence_items_total_value,
                "final_answer_present": final_answer_present_value,
                "state_path": trial_result["state_path"],
                "trace_path": trial_result["trace_path"],
                "workflow_summary_path": trial_result["workflow_summary_path"],
                "source_output_path": trial_result["source_output_path"],
                "captured_output_present": trial_result["captured_output_present"],
                "no_runtime_execution": True,
                "model_execution": False,
                "real_browser_execution": False,
                "playwright_execution": False,
                "browser_opened": False,
            }
        )
        scenario_summary = scenario_summary_map[scenario_id]
        scenario_summary["outputs_total"] += 1
        failure_class_counts.update([trial_result["failure_class"]])
        scenario_summary["failure_class_counts"].update([trial_result["failure_class"]])
        if trial_result["captured_output_present"]:
            outputs_present += 1
            scenario_summary["outputs_present"] += 1
            if trial_result["status"] == "succeeded":
                outputs_accepted += 1
                workflows_materialized += 1
                actions_total += actions_total_value
                facts_total += facts_total_value
                evidence_items_total += evidence_items_total_value
                final_answers_total += 1 if final_answer_present_value else 0
                scenario_summary["outputs_accepted"] += 1
                scenario_summary["workflows_materialized"] += 1
                scenario_summary["actions_total"] += actions_total_value
                scenario_summary["facts_total"] += facts_total_value
                scenario_summary["evidence_items_total"] += evidence_items_total_value
                scenario_summary["final_answers_total"] += 1 if final_answer_present_value else 0
            else:
                outputs_rejected += 1
                workflows_failed += 1
                scenario_summary["outputs_rejected"] += 1
                scenario_summary["workflows_failed"] += 1
                if first_issue_code is None:
                    first_issue_code = str(trial_result.get("error_code") or "variance_materialization_failed")
        else:
            outputs_missing += 1
            workflows_failed += 1
            scenario_summary["outputs_missing"] += 1
            scenario_summary["workflows_failed"] += 1
            if first_issue_code is None:
                first_issue_code = str(trial_result.get("error_code") or "missing_captured_output_file")

    scenario_summaries: list[dict[str, Any]] = []
    for scenario_id, summary in scenario_summary_map.items():
        summary["failure_class_counts"] = dict(sorted(summary["failure_class_counts"].items()))
        summary["pass_rate"] = _safe_ratio(summary["workflows_materialized"], summary["outputs_total"])
        scenario_summaries.append(summary)

    if outputs_rejected:
        status = "completed_with_failures"
        error_code = first_issue_code or "variance_materialization_failed"
    elif outputs_missing:
        status = "completed_with_missing_outputs"
        error_code = "missing_captured_outputs"
    else:
        status = "succeeded"
        error_code = None

    materializer_summary = StatefulReadonlyPlannerVarianceMaterializerSummary(
        schema_version=MATERIALIZER_SUMMARY_SCHEMA_VERSION,
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
        scenario_summaries=tuple(scenario_summaries),
        trial_summaries=tuple(trial_summaries),
        output_summaries=tuple(output_summaries),
        output_dir=output_dir,
        model_execution=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        real_network_traffic=False,
        fixture_only=True,
        no_runtime_execution=True,
        limitations=limitations,
    )
    payload = materializer_summary.to_dict()
    _write_json(output_root / "autonomous_browser_stateful_readonly_planner_variance_materializer_summary.json", payload)
    return payload


def _evaluate_trial_record(
    *,
    repo_root: Path,
    packet_id: str,
    packet_output_dir: str,
    record: Mapping[str, Any],
    scenario,
    execute_fixture: bool,
) -> dict[str, Any]:
    trial_result = _evaluate_stateful_output_record(
        repo_root=repo_root,
        packet_id=packet_id,
        record=record,
        scenario=scenario,
        scenario_hints=_scenario_prompt_hints()[str(record["scenario_id"])],
        execute_fixture=execute_fixture,
        packet_output_dir=packet_output_dir,
    )
    response_path = repo_root / str(record["response_path"])
    finish_reason = _response_finish_reason(response_path)
    trial_result["finish_reason"] = finish_reason
    trial_result["workflow_status"] = _workflow_status_for_result(trial_result["status"])
    trial_result["trial_label"] = str(record.get("trial_label") or str(record.get("trial_id")).split("__")[-1])
    trial_result["captured_output_present"] = bool(trial_result.get("captured_output_present"))
    if "facts_total" not in trial_result or "evidence_items_total" not in trial_result or "final_answer_present" not in trial_result:
        raw_path = repo_root / str(record["raw_output_path"])
        if raw_path.exists():
            try:
                raw_text = raw_path.read_text(encoding="utf-8-sig")
                extracted = _extract_candidate_output(raw_text)
                if extracted["status"] == "accepted":
                    validation = _validate_stateful_output(
                        extracted["candidate_output"],
                        scenario=scenario,
                        scenario_hints=_scenario_prompt_hints()[str(record["scenario_id"])],
                    )
                    if validation["status"] == "accepted":
                        normalized = validation["normalized_output"]
                        trial_result.setdefault("actions_total", len(normalized["actions"]))
                        trial_result.setdefault("facts_total", len(normalized["facts"]))
                        trial_result.setdefault("evidence_items_total", len(normalized["evidence_items"]))
                        trial_result.setdefault("final_answer_present", normalized.get("final_answer") is not None)
            except (OSError, json.JSONDecodeError, KeyError, TypeError):
                pass
    return trial_result


def _evaluate_stateful_output_record(
    *,
    repo_root: Path,
    packet_id: str,
    record: Mapping[str, Any],
    scenario,
    scenario_hints: Mapping[str, tuple[str, ...]],
    execute_fixture: bool,
    packet_output_dir: str,
) -> dict[str, Any]:
    # We reuse the strict stateful evaluator logic by reconstructing the record shape.
    from .autonomous_browser_stateful_readonly_planner_evaluator import _evaluate_output_record

    return _evaluate_output_record(
        repo_root=repo_root,
        packet_id=packet_id,
        record=record,
        scenario=scenario,
        scenario_hints=scenario_hints,
        execute_fixture=execute_fixture,
        packet_output_dir=packet_output_dir,
    )


def _materialize_trial_record(
    *,
    repo_root: Path,
    packet_id: str,
    packet_output_dir: str,
    materialized_output_dir: str,
    record: Mapping[str, Any],
    scenario,
) -> dict[str, Any]:
    model_alias = _safe_text(record.get("model_alias"))
    scenario_id = _safe_text(record.get("scenario_id"))
    trial_id = _safe_text(record.get("trial_id"))
    trial_label = _safe_text(record.get("trial_label")) or (trial_id.split("__")[-1] if trial_id else None)
    workflow_id = _safe_text(record.get("workflow_id"))
    source_output_path = _safe_relative_path(record.get("raw_output_path") or record.get("output_path"), "output_path")
    source_response_path = _safe_relative_path(record.get("response_path"), "response_path")
    if model_alias is None or scenario_id is None or trial_id is None or trial_label is None or workflow_id is None or source_output_path is None:
        invalid_workflow_dir = repo_root / materialized_output_dir / (model_alias or "unknown_model") / (scenario_id or "unknown_scenario") / (trial_label or "unknown_trial")
        invalid_workflow_dir.mkdir(parents=True, exist_ok=True)
        summary = _materialized_workflow_summary(
            packet_id=packet_id,
            model_alias=model_alias or "unknown_model",
            scenario_id=scenario_id or "unknown_scenario",
            trial_id=trial_id or "unknown_trial",
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
            source_output_path=source_output_path or "unknown_output",
            source_response_path=source_response_path,
            diagnostics={"finding_type": "invalid_request_record"},
        )
        _write_json(invalid_workflow_dir / "materialized_workflow_summary.json", summary)
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "failure_class": "config_error",
            "captured_output_present": False,
            "actions_total": 0,
            "facts_total": 0,
            "evidence_items_total": 0,
            "final_answer_present": False,
            "state_path": None,
            "trace_path": None,
            "workflow_summary_path": None,
            "source_output_path": source_output_path or "unknown_output",
            "model_alias": model_alias or "unknown_model",
            "scenario_id": scenario_id or "unknown_scenario",
            "trial_id": trial_id or "unknown_trial",
            "trial_label": trial_label or "unknown_trial",
        }

    workflow_dir = repo_root / materialized_output_dir / model_alias / scenario_id / trial_label
    workflow_dir.mkdir(parents=True, exist_ok=True)
    state_path = workflow_dir / "materialized_state.json"
    trace_path = workflow_dir / "materialized_trace.json"
    summary_path = workflow_dir / "materialized_workflow_summary.json"

    raw_path = repo_root / source_output_path
    if not raw_path.exists():
        summary = _materialized_workflow_summary(
            packet_id=packet_id,
            model_alias=model_alias,
            scenario_id=scenario_id,
            trial_id=trial_id,
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
            source_output_path=source_output_path,
            source_response_path=source_response_path,
            diagnostics={"source_output_path": source_output_path},
        )
        _write_json(summary_path, summary)
        return {
            "status": "missing",
            "error_code": "missing_captured_output_file",
            "failure_class": "missing_output",
            "captured_output_present": False,
            "actions_total": 0,
            "facts_total": 0,
            "evidence_items_total": 0,
            "final_answer_present": False,
            "state_path": None,
            "trace_path": None,
            "workflow_summary_path": f"{materialized_output_dir}/{model_alias}/{scenario_id}/{trial_label}/materialized_workflow_summary.json",
            "source_output_path": source_output_path,
            "model_alias": model_alias,
            "scenario_id": scenario_id,
            "trial_id": trial_id,
            "trial_label": trial_label,
        }

    try:
        raw_text = raw_path.read_text(encoding="utf-8-sig")
    except OSError as exc:
        summary = _materialized_workflow_summary(
            packet_id=packet_id,
            model_alias=model_alias,
            scenario_id=scenario_id,
            trial_id=trial_id,
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
            source_output_path=source_output_path,
            source_response_path=source_response_path,
            diagnostics={"source_output_path": source_output_path, "error_message": str(exc)},
        )
        _write_json(summary_path, summary)
        return {
            "status": "failed",
            "error_code": "source_output_read_failed",
            "failure_class": "fixture_error",
            "captured_output_present": True,
            "actions_total": 0,
            "facts_total": 0,
            "evidence_items_total": 0,
            "final_answer_present": False,
            "state_path": None,
            "trace_path": None,
            "workflow_summary_path": f"{materialized_output_dir}/{model_alias}/{scenario_id}/{trial_label}/materialized_workflow_summary.json",
            "source_output_path": source_output_path,
            "model_alias": model_alias,
            "scenario_id": scenario_id,
            "trial_id": trial_id,
            "trial_label": trial_label,
        }

    extracted = _extract_candidate_output(raw_text)
    if extracted["status"] != "accepted":
        error_code = str(extracted.get("error_code") or "output_extraction_failed")
        summary = _materialized_workflow_summary(
            packet_id=packet_id,
            model_alias=model_alias,
            scenario_id=scenario_id,
            trial_id=trial_id,
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
            source_output_path=source_output_path,
            source_response_path=source_response_path,
            diagnostics=_jsonable(extracted.get("diagnostics")),
        )
        _write_json(summary_path, summary)
        return {
            "status": "rejected",
            "error_code": error_code,
            "failure_class": _failure_class_from_error_code(error_code),
            "captured_output_present": True,
            "actions_total": 0,
            "facts_total": 0,
            "evidence_items_total": 0,
            "final_answer_present": False,
            "state_path": None,
            "trace_path": None,
            "workflow_summary_path": f"{materialized_output_dir}/{model_alias}/{scenario_id}/{trial_label}/materialized_workflow_summary.json",
            "source_output_path": source_output_path,
            "model_alias": model_alias,
            "scenario_id": scenario_id,
            "trial_id": trial_id,
            "trial_label": trial_label,
        }

    validation = _validate_stateful_output(
        extracted["candidate_output"],
        scenario=scenario,
        scenario_hints=_scenario_prompt_hints()[scenario_id],
    )
    if validation["status"] != "accepted":
        error_code = str(validation.get("error_code") or "model_failed_task")
        summary = _materialized_workflow_summary(
            packet_id=packet_id,
            model_alias=model_alias,
            scenario_id=scenario_id,
            trial_id=trial_id,
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
            source_output_path=source_output_path,
            source_response_path=source_response_path,
            diagnostics=_jsonable(validation.get("diagnostics")),
        )
        _write_json(summary_path, summary)
        return {
            "status": "rejected",
            "error_code": error_code,
            "failure_class": _failure_class_from_error_code(error_code),
            "captured_output_present": True,
            "actions_total": 0,
            "facts_total": 0,
            "evidence_items_total": 0,
            "final_answer_present": False,
            "state_path": None,
            "trace_path": None,
            "workflow_summary_path": f"{materialized_output_dir}/{model_alias}/{scenario_id}/{trial_label}/materialized_workflow_summary.json",
            "source_output_path": source_output_path,
            "model_alias": model_alias,
            "scenario_id": scenario_id,
            "trial_id": trial_id,
            "trial_label": trial_label,
        }

    normalized = validation["normalized_output"]
    state_payload = _build_materialized_state_payload(
        packet_id=packet_id,
        model_alias=model_alias,
        scenario_id=scenario_id,
        trial_id=trial_id,
        workflow_id=workflow_id,
        source_output_path=source_output_path,
        source_response_path=source_response_path if source_response_path and (repo_root / source_response_path).exists() else None,
        normalized_output=normalized,
    )
    trace_payload = _build_materialized_trace_payload(
        packet_id=packet_id,
        model_alias=model_alias,
        scenario_id=scenario_id,
        trial_id=trial_id,
        workflow_id=workflow_id,
        source_output_path=source_output_path,
        normalized_output=normalized,
    )
    _write_json(state_path, state_payload)
    _write_json(trace_path, trace_payload)
    summary = _materialized_workflow_summary(
        packet_id=packet_id,
        model_alias=model_alias,
        scenario_id=scenario_id,
        trial_id=trial_id,
        workflow_id=workflow_id,
        status="succeeded",
        error_code=None,
        failure_class="none",
        actions_total=len(normalized["actions"]),
        facts_total=len(normalized["facts"]),
        evidence_items_total=len(normalized["evidence_items"]),
        final_answer_present=True,
        state_path=f"{materialized_output_dir}/{model_alias}/{scenario_id}/{trial_label}/materialized_state.json",
        trace_path=f"{materialized_output_dir}/{model_alias}/{scenario_id}/{trial_label}/materialized_trace.json",
        source_output_path=source_output_path,
        source_response_path=source_response_path if source_response_path and (repo_root / source_response_path).exists() else None,
        diagnostics={"source_output_path": source_output_path},
    )
    _write_json(summary_path, summary)
    return {
        "status": "succeeded",
        "error_code": None,
        "failure_class": "none",
        "captured_output_present": True,
        "actions_total": len(normalized["actions"]),
        "facts_total": len(normalized["facts"]),
        "evidence_items_total": len(normalized["evidence_items"]),
        "final_answer_present": True,
        "state_path": f"{materialized_output_dir}/{model_alias}/{scenario_id}/{trial_label}/materialized_state.json",
        "trace_path": f"{materialized_output_dir}/{model_alias}/{scenario_id}/{trial_label}/materialized_trace.json",
        "workflow_summary_path": f"{materialized_output_dir}/{model_alias}/{scenario_id}/{trial_label}/materialized_workflow_summary.json",
        "source_output_path": source_output_path,
        "model_alias": model_alias,
        "scenario_id": scenario_id,
        "trial_id": trial_id,
        "trial_label": trial_label,
    }


def _build_materialized_state_payload(
    *,
    packet_id: str,
    model_alias: str,
    scenario_id: str,
    trial_id: str,
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
    payload = StatefulReadonlyPlannerVarianceMaterializedState(
        schema_version=MATERIALIZED_STATE_SCHEMA_VERSION,
        packet_id=packet_id,
        model_alias=model_alias,
        scenario_id=scenario_id,
        trial_id=trial_id,
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


def _build_materialized_trace_payload(
    *,
    packet_id: str,
    model_alias: str,
    scenario_id: str,
    trial_id: str,
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
    payload = StatefulReadonlyPlannerVarianceMaterializedTrace(
        schema_version=MATERIALIZED_TRACE_SCHEMA_VERSION,
        packet_id=packet_id,
        model_alias=model_alias,
        scenario_id=scenario_id,
        trial_id=trial_id,
        workflow_id=workflow_id,
        status="planned",
        trace_entries=tuple(trace_entries),
    )
    return payload.to_dict()


def _materialized_workflow_summary(
    *,
    packet_id: str,
    model_alias: str,
    scenario_id: str,
    trial_id: str,
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
    source_response_path: str | None,
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = StatefulReadonlyPlannerVarianceMaterializedWorkflowSummary(
        schema_version=MATERIALIZED_WORKFLOW_SUMMARY_SCHEMA_VERSION,
        packet_id=packet_id,
        model_alias=model_alias,
        scenario_id=scenario_id,
        trial_id=trial_id,
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
        source_response_path=source_response_path,
        diagnostics=diagnostics,
    )
    return payload.to_dict()


def _build_runtime_config(
    *,
    packet_id: str,
    packet_output_dir: str,
    evaluation_output_dir: str,
    materialized_output_dir: str,
    model_aliases: list[str],
    scenario_ids: list[str],
    trial_ids: list[str],
    trial_records: list[dict[str, Any]],
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": RUNTIME_CONFIG_SCHEMA_VERSION,
        "packet_id": packet_id,
        "packet_output_dir": packet_output_dir,
        "output_dir": evaluation_output_dir,
        "materialized_output_dir": materialized_output_dir,
        "no_runtime_execution": True,
        "model_execution": False,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
        "real_network_traffic": False,
        "fixture_only": True,
        "models": [
            {
                "alias": alias,
                "model_path": DEFAULT_REQUEST_MODEL_PATH,
                "prompt_prefix": "/no_think" if alias == DEFAULT_MODEL_ALIAS else None,
            }
            for alias in model_aliases
        ],
        "scenarios": [
            {
                "scenario_id": scenario_id,
                "scenario_label": scenario_id,
                "prompt_filename": DEFAULT_PROMPT_FILENAME,
                "max_tokens": DEFAULT_MAX_TOKENS,
            }
            for scenario_id in scenario_ids
        ],
        "trial_ids": trial_ids,
        "trial_records": trial_records,
        "captured_outputs": [record["output_path"] for record in trial_records],
        "request_paths": _nested_paths_by_trial(trial_records, "request_path"),
        "output_paths": _nested_paths_by_trial(trial_records, "output_path"),
        "response_metadata_paths": _nested_paths_by_trial(trial_records, "response_path"),
        "limitations": list(limitations),
    }


def _build_commands(
    *,
    packet_id: str,
    output_dir: str,
    captured_output_dir: str,
    evaluation_output_dir: str,
    materialized_output_dir: str,
    model_aliases: list[str],
    scenario_ids: list[str],
    trial_ids: list[str],
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = [
        {
            "id": "build_stateful_readonly_planner_variance_packet",
            "manual_only": False,
            "description": "Build the repeated stateful read-only planner variance packet.",
            "command": r".\.venv\Scripts\python.exe scripts\build_autonomous_browser_stateful_readonly_planner_variance_packet.py --config configs\autonomous_runtime\browser_stateful_readonly_planner_variance.example.json",
        }
    ]
    for scenario_id in scenario_ids:
        prompt_path = _windows_path(f"{output_dir}/prompts/{scenario_id}/{DEFAULT_PROMPT_FILENAME}")
        commands.append(
            {
                "id": f"read_{scenario_id}_prompt",
                "manual_only": True,
                "description": f"Read the compact prompt for {scenario_id}.",
                "command": f'Get-Content "{prompt_path}" -Raw',
            }
        )
    for model_alias in model_aliases:
        for scenario_id in scenario_ids:
            for trial_label in trial_ids:
                request_path = _windows_path(f"{output_dir}/{model_alias}/{scenario_id}/{trial_label}/{DEFAULT_REQUEST_FILENAME}")
                response_path = _windows_path(f"{captured_output_dir}/{model_alias}/{scenario_id}/{trial_label}/{DEFAULT_RESPONSE_FILENAME}")
                raw_output_path = _windows_path(f"{captured_output_dir}/{model_alias}/{scenario_id}/{trial_label}/{DEFAULT_RAW_OUTPUT_FILENAME}")
                commands.extend(
                    [
                        {
                            "id": f"{model_alias}_{scenario_id}_{trial_label}_curl_request",
                            "manual_only": True,
                            "description": f"Run the manual third_model request for {scenario_id} / {trial_label} and save the response JSON.",
                            "command": (
                                "# Manual operator only. Codex must not launch models.\n"
                                "Do not use Invoke-RestMethod for planner generation.\n"
                                f"curl.exe --max-time 90 -sS -X POST http://127.0.0.1:8082/v1/chat/completions -H \"Content-Type: application/json\" --data-binary \"@{request_path}\" --output \"{response_path}\""
                            ),
                        },
                        {
                            "id": f"{model_alias}_{scenario_id}_{trial_label}_extract_output",
                            "manual_only": True,
                            "description": f"Extract response.choices[0].message.content into raw_planner_output.txt for {scenario_id} / {trial_label}.",
                            "command": (
                                f"$response = Get-Content \"{response_path}\" -Raw | ConvertFrom-Json\n"
                                f"$response.choices[0].message.content | Set-Content \"{raw_output_path}\" -Encoding utf8"
                            ),
                        },
                    ]
                )
    commands.extend(
        [
            {
                "id": "inspect_finish_reason_counts",
                "manual_only": True,
                "description": "Inspect response.json finish_reason counts before running the evaluator.",
                "command": (
                    f'Get-ChildItem "{_windows_path(f"{captured_output_dir}/third_model")}" -Recurse -Filter response.json | '
                    'ForEach-Object { (Get-Content $_ -Raw | ConvertFrom-Json).choices[0].finish_reason } | '
                    'Group-Object | Sort-Object Name'
                ),
            },
            {
                "id": "run_stateful_readonly_planner_variance_evaluator",
                "manual_only": False,
                "description": "Run the variance evaluator after the captured outputs exist.",
                "command": rf".\.venv\Scripts\python.exe scripts\run_autonomous_browser_stateful_readonly_planner_variance_evaluator.py --config {output_dir}/{DEFAULT_RUNTIME_CONFIG_FILENAME}",
            },
            {
                "id": "run_stateful_readonly_planner_variance_materializer",
                "manual_only": False,
                "description": "Materialize accepted variance outputs into workflow artifacts.",
                "command": rf".\.venv\Scripts\python.exe scripts\materialize_autonomous_browser_stateful_readonly_planner_variance_outputs.py --config {output_dir}/{DEFAULT_RUNTIME_CONFIG_FILENAME}",
            },
            {
                "id": "run_pytest",
                "manual_only": False,
                "description": "Run the offline test suite.",
                "command": r".\.venv\Scripts\python.exe -m pytest",
            },
        ]
    )
    return commands


def _build_commands_markdown(
    *,
    packet_id: str,
    output_dir: str,
    captured_output_dir: str,
    evaluation_output_dir: str,
    materialized_output_dir: str,
    model_aliases: list[str],
    scenario_ids: list[str],
    trial_ids: list[str],
) -> str:
    model_alias_list = ", ".join(f"`{alias}`" for alias in model_aliases)
    lines = [
        "# Stateful Read-Only Planner Variance Packet Commands",
        "",
        "Codex must not launch models.",
        f"Packet id: `{packet_id}`.",
        f"The packet prepares repeated manual local-model requests for {model_alias_list}.",
        "Use `planner_prompt.compact.txt` as the prompt source for each trial.",
        "The `third_model` path is documented as `models/gguf/third_model.gguf` and is not accessed by Codex.",
        "",
        "## Manual trial loop",
        "",
        "```powershell",
        f"$packetRoot = \"{output_dir}\"",
        f"$capturedRoot = \"{captured_output_dir}\"",
        'Get-ChildItem "$packetRoot\\third_model" -Recurse -Filter request.json | ForEach-Object {',
        '  $responsePath = $_.FullName -replace \'request\\.json$\', \'response.json\'',
        '  $rawOutputPath = $_.FullName -replace \'request\\.json$\', \'raw_planner_output.txt\'',
        '  curl.exe --max-time 90 -sS -X POST http://127.0.0.1:8082/v1/chat/completions -H "Content-Type: application/json" --data-binary "@$($_.FullName)" --output "$responsePath"',
        '  $response = Get-Content "$responsePath" -Raw | ConvertFrom-Json',
        '  $response.choices[0].message.content | Set-Content "$rawOutputPath" -Encoding utf8',
        "}",
        "```",
        "",
        "## Finish reasons",
        "",
        "```powershell",
        f'Get-ChildItem "{captured_output_dir}\\third_model" -Recurse -Filter response.json | ForEach-Object {{ (Get-Content $_ -Raw | ConvertFrom-Json).choices[0].finish_reason }} | Group-Object | Sort-Object Name',
        "```",
        "",
    ]
    for scenario_id in scenario_ids:
        prompt_path = _windows_path(f"{output_dir}/prompts/{scenario_id}/{DEFAULT_PROMPT_FILENAME}")
        lines.extend(
            [
                f"## Read {scenario_id} Prompt",
                "```powershell",
                f"Get-Content \"{prompt_path}\" -Raw",
                "```",
                "",
            ]
        )
    for model_alias in model_aliases:
        for scenario_id in scenario_ids:
            for trial_label in trial_ids:
                request_path = _windows_path(f"{output_dir}/{model_alias}/{scenario_id}/{trial_label}/{DEFAULT_REQUEST_FILENAME}")
                response_path = _windows_path(f"{captured_output_dir}/{model_alias}/{scenario_id}/{trial_label}/{DEFAULT_RESPONSE_FILENAME}")
                raw_output_path = _windows_path(f"{captured_output_dir}/{model_alias}/{scenario_id}/{trial_label}/{DEFAULT_RAW_OUTPUT_FILENAME}")
                lines.extend(
                    [
                        f"## {model_alias} {scenario_id} {trial_label}",
                        "```powershell",
                        (
                            f"curl.exe --max-time 90 -sS -X POST http://127.0.0.1:8082/v1/chat/completions -H \"Content-Type: application/json\" "
                            f"--data-binary \"@{request_path}\" --output \"{response_path}\""
                        ),
                        "```",
                        "```powershell",
                        f"$response.choices[0].message.content | Set-Content \"{raw_output_path}\" -Encoding utf8",
                        "```",
                        "",
                    ]
                )
    lines.extend(
        [
            "## Evaluation",
            "```powershell",
            rf".\.venv\Scripts\python.exe scripts\run_autonomous_browser_stateful_readonly_planner_variance_evaluator.py --config {output_dir}/{DEFAULT_RUNTIME_CONFIG_FILENAME}",
            "```",
            "",
            "## Materialization",
            "```powershell",
            rf".\.venv\Scripts\python.exe scripts\materialize_autonomous_browser_stateful_readonly_planner_variance_outputs.py --config {output_dir}/{DEFAULT_RUNTIME_CONFIG_FILENAME}",
            "```",
            "",
            "## Offline checks",
            "```powershell",
            r".\.venv\Scripts\python.exe -m pytest",
            "```",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _build_readme(
    *,
    packet_id: str,
    output_dir: str,
    captured_output_dir: str,
    materialized_output_dir: str,
    evaluation_output_dir: str,
    model_aliases: list[str],
    scenario_ids: list[str],
    trial_ids: list[str],
    request_paths: Mapping[str, Mapping[str, Mapping[str, str]]],
    output_paths: Mapping[str, Mapping[str, Mapping[str, str]]],
) -> str:
    model_alias_list = ", ".join(f"`{alias}`" for alias in model_aliases)
    lines = [
        "# Stateful Read-Only Planner Variance Packet",
        "",
        f"Packet id: `{packet_id}`.",
        "",
        "## Scope",
        "",
        "- Offline repeated-trials packet only.",
        f"- Prepares repeated hard-plan requests for {model_alias_list}.",
        "- Reuses the calibrated compact stateful prompts from the base packet.",
        "- No model execution by Codex.",
        "- No browser execution by Codex.",
        "- The `third_model` path is a documentation/config expectation only.",
        "",
        "## Paths",
        "",
        f"- Packet output: `{output_dir}`",
        f"- Captured outputs: `{captured_output_dir}`",
        f"- Materialized outputs: `{materialized_output_dir}`",
        f"- Evaluator output: `{evaluation_output_dir}`",
        "",
        "## Models",
        "",
    ]
    for alias in model_aliases:
        lines.append(f"- `{alias}` -> `models/gguf/third_model.gguf`")
    lines.extend(
        [
            "",
            "## Scenarios",
            "",
        ]
    )
    for scenario_id in scenario_ids:
        sample_request = request_paths[model_aliases[0]][scenario_id][trial_ids[0]]
        sample_output = output_paths[model_aliases[0]][scenario_id][trial_ids[0]]
        lines.append(f"- `{scenario_id}` -> `{sample_request}` / `{sample_output}`")
    lines.extend(
        [
            "",
            "## Operator Flow",
            "",
            f"1. Build the packet into `{output_dir}`.",
            "2. Read the scenario prompt files.",
            "3. Manually run each model request and save `response.json` and `raw_planner_output.txt` for each trial.",
            f"4. Run the variance evaluator into `{evaluation_output_dir}`.",
            f"5. Materialize accepted outputs into `{materialized_output_dir}`.",
            "6. Run pytest.",
            "",
            "## Trial Layout",
            "",
            f"- Trial ids: {', '.join(f'`{trial_id}`' for trial_id in trial_ids)}.",
            "- Every trial is offline until the operator fills the captured output files.",
            "",
        ]
    )
    return "\n".join(lines)


def _load_build_config(config_artifact: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config_artifact, Mapping):
        payload = dict(config_artifact)
    else:
        try:
            payload = json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "packet_id": None,
                "output_dir": None,
                "captured_output_dir": None,
                "materialized_output_dir": None,
                "limitations": DEFAULT_LIMITATIONS,
            }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": None,
            "output_dir": None,
            "captured_output_dir": None,
            "materialized_output_dir": None,
            "limitations": DEFAULT_LIMITATIONS,
        }
    try:
        config = StatefulReadonlyPlannerVarianceBuildConfig.from_dict(payload)
    except ValueError:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": _safe_text(payload.get("packet_id")),
            "output_dir": _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir"),
            "captured_output_dir": _safe_relative_path(payload.get("captured_output_dir", DEFAULT_CAPTURED_OUTPUT_DIR), "captured_output_dir"),
            "materialized_output_dir": _safe_relative_path(payload.get("materialized_output_dir", DEFAULT_MATERIALIZED_OUTPUT_DIR), "materialized_output_dir"),
            "limitations": DEFAULT_LIMITATIONS,
        }
    return {"status": "ok", "config": config.to_dict(), "limitations": config.limitations}


def _load_runtime_config(config_artifact: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config_artifact, Mapping):
        payload = dict(config_artifact)
    else:
        try:
            payload = json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "packet_id": None,
                "output_dir": None,
                "packet_output_dir": None,
                "materialized_output_dir": None,
                "limitations": DEFAULT_LIMITATIONS,
            }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": None,
            "output_dir": None,
            "packet_output_dir": None,
            "materialized_output_dir": None,
            "limitations": DEFAULT_LIMITATIONS,
        }
    packet_id = _safe_text(payload.get("packet_id"))
    output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_EVALUATOR_OUTPUT_DIR), "output_dir")
    packet_output_dir = _safe_relative_path(payload.get("packet_output_dir", DEFAULT_OUTPUT_DIR), "packet_output_dir")
    materialized_output_dir = _safe_relative_path(payload.get("materialized_output_dir", DEFAULT_MATERIALIZED_OUTPUT_DIR), "materialized_output_dir")
    models = _safe_runtime_models(payload.get("models"))
    scenarios = _safe_runtime_scenarios(payload.get("scenarios"))
    trial_ids = _safe_string_list(payload.get("trial_ids"), "trial_ids")
    trial_records = _safe_runtime_trial_records(payload.get("trial_records"))
    if (
        packet_id is None
        or output_dir is None
        or packet_output_dir is None
        or materialized_output_dir is None
        or models is None
        or scenarios is None
        or trial_ids is None
        or trial_records is None
    ):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "packet_output_dir": packet_output_dir,
            "materialized_output_dir": materialized_output_dir,
            "limitations": DEFAULT_LIMITATIONS,
        }
    if str(payload.get("schema_version", "")) != RUNTIME_CONFIG_SCHEMA_VERSION:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "packet_output_dir": packet_output_dir,
            "materialized_output_dir": materialized_output_dir,
            "limitations": DEFAULT_LIMITATIONS,
        }
    return {
        "status": "ok",
        "config": {
            "schema_version": RUNTIME_CONFIG_SCHEMA_VERSION,
            "packet_id": packet_id,
            "output_dir": output_dir,
            "packet_output_dir": packet_output_dir,
            "materialized_output_dir": materialized_output_dir,
            "model_aliases": [item["alias"] for item in models],
            "scenario_ids": [item["scenario_id"] for item in scenarios],
            "models": models,
            "scenarios": scenarios,
            "trial_ids": trial_ids,
            "trial_records": trial_records,
            "captured_outputs": _safe_string_list(payload.get("captured_outputs"), "captured_outputs") or [],
            "request_paths": payload.get("request_paths", {}),
            "output_paths": payload.get("output_paths", {}),
            "response_metadata_paths": payload.get("response_metadata_paths", {}),
            "no_runtime_execution": bool(payload.get("no_runtime_execution", True)),
            "model_execution": bool(payload.get("model_execution", False)),
            "real_browser_execution": bool(payload.get("real_browser_execution", False)),
            "playwright_execution": bool(payload.get("playwright_execution", False)),
            "browser_opened": bool(payload.get("browser_opened", False)),
            "real_network_traffic": bool(payload.get("real_network_traffic", False)),
            "fixture_only": bool(payload.get("fixture_only", True)),
            "limitations": tuple(str(item).strip() for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
        },
        "limitations": tuple(str(item).strip() for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()) or DEFAULT_LIMITATIONS,
    }


def _load_packet_context(packet_dir_artifact: str | Path, *, repo_root: Path) -> dict[str, Any]:
    packet_dir_path = Path(packet_dir_artifact)
    if not packet_dir_path.is_absolute():
        packet_dir_path = repo_root / packet_dir_path
    packet_dir_display = _repo_relative_path(repo_root, packet_dir_path)
    summary_files = (
        DEFAULT_PACKET_SUMMARY_FILENAME,
        DEFAULT_PACKET_MANIFEST_FILENAME,
    )
    checked_files = [f"{packet_dir_display}/{filename}" for filename in summary_files]
    first_issue = "missing_packet_summary"
    for filename in summary_files:
        summary_path = packet_dir_path / filename
        if not summary_path.exists():
            continue
        try:
            payload = json.loads(summary_path.read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            first_issue = "packet_summary_unreadable"
            continue
        if not isinstance(payload, Mapping):
            first_issue = "packet_summary_invalid"
            continue
        request_records = _safe_runtime_trial_records(payload.get("request_records"))
        if request_records is None:
            first_issue = "packet_summary_missing_request_records"
            continue
        packet_id = _safe_text(payload.get("packet_id"))
        if packet_id is None:
            first_issue = "packet_summary_missing_packet_id"
            continue
        model_aliases = _safe_string_list(payload.get("model_aliases"), "model_aliases")
        if model_aliases is None:
            model_aliases = _unique_values(request_records, "model_alias")
        scenario_ids = _safe_string_list(payload.get("scenario_ids"), "scenario_ids")
        if scenario_ids is None:
            scenario_ids = _unique_values(request_records, "scenario_id")
        trial_ids = _safe_string_list(payload.get("trial_ids"), "trial_ids")
        if trial_ids is None:
            trial_ids = _unique_values(request_records, "trial_label")
        trials_per_scenario = payload.get("trials_per_scenario")
        if not isinstance(trials_per_scenario, int) or isinstance(trials_per_scenario, bool) or trials_per_scenario <= 0:
            trials_per_scenario = len(trial_ids)
        packet_output_dir = _safe_relative_path(payload.get("output_dir", packet_dir_display), "output_dir") or packet_dir_display
        captured_output_dir = _safe_relative_path(payload.get("captured_output_dir", DEFAULT_CAPTURED_OUTPUT_DIR), "captured_output_dir") or DEFAULT_CAPTURED_OUTPUT_DIR
        materialized_output_dir = _safe_relative_path(payload.get("materialized_output_dir", DEFAULT_MATERIALIZED_OUTPUT_DIR), "materialized_output_dir") or DEFAULT_MATERIALIZED_OUTPUT_DIR
        limitations = tuple(str(item).strip() for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()) or DEFAULT_LIMITATIONS
        return {
            "status": "ok",
            "packet_id": packet_id,
            "packet_dir": packet_dir_display,
            "packet_output_dir": packet_output_dir,
            "captured_output_dir": captured_output_dir,
            "materialized_output_dir": materialized_output_dir,
            "models_total": len(model_aliases),
            "scenarios_total": len(scenario_ids),
            "trials_per_scenario": trials_per_scenario,
            "requests_total": len(request_records),
            "model_aliases": tuple(model_aliases),
            "scenario_ids": tuple(scenario_ids),
            "trial_ids": tuple(trial_ids),
            "request_records": request_records,
            "limitations": limitations,
            "summary_file": f"{packet_dir_display}/{filename}",
        }
    return {
        "status": "failed",
        "error_code": "config_validation_failed",
        "packet_id": None,
        "packet_dir": packet_dir_display,
        "expected_summary_files": checked_files,
        "finding_type": first_issue,
        "hint": "build variance packet first or pass --packet-dir to the generated packet directory",
        "limitations": DEFAULT_LIMITATIONS,
    }


def _load_packet_context_from_build_config(config_artifact: str | Path | Mapping[str, Any], *, repo_root: Path) -> dict[str, Any]:
    config = _load_build_config(config_artifact)
    if config["status"] != "ok":
        return {
            "status": "failed",
            "error_code": str(config.get("error_code") or "config_validation_failed"),
            "packet_id": config.get("packet_id"),
            "packet_dir": config.get("output_dir"),
            "packet_output_dir": config.get("output_dir"),
            "materialized_output_dir": config.get("materialized_output_dir"),
            "expected_summary_files": [],
            "finding_type": "invalid_build_config",
            "hint": "build variance packet first or pass --packet-dir to the generated packet directory",
            "limitations": tuple(config.get("limitations") or DEFAULT_LIMITATIONS),
        }

    build_config = config["config"]
    packet_context = _load_packet_context(str(build_config["output_dir"]), repo_root=repo_root)
    if packet_context["status"] != "ok":
        packet_context = dict(packet_context)
        packet_context["packet_id"] = build_config["packet_id"]
        packet_context["packet_output_dir"] = build_config["output_dir"]
        packet_context["materialized_output_dir"] = build_config["materialized_output_dir"]
        packet_context["limitations"] = tuple(config.get("limitations") or DEFAULT_LIMITATIONS)
        return packet_context

    packet_context = dict(packet_context)
    packet_context["packet_id"] = build_config["packet_id"]
    packet_context["packet_output_dir"] = build_config["output_dir"]
    packet_context["materialized_output_dir"] = build_config["materialized_output_dir"]
    packet_context["captured_output_dir"] = build_config["captured_output_dir"]
    packet_context["limitations"] = tuple(config.get("limitations") or DEFAULT_LIMITATIONS)
    return packet_context


def _unique_values(records: tuple[dict[str, Any], ...], key: str) -> list[str]:
    values: list[str] = []
    seen: set[str] = set()
    for record in records:
        text = _safe_text(record.get(key))
        if text is not None and text not in seen:
            seen.add(text)
            values.append(text)
    return values


def _repo_relative_path(repo_root: Path, value: Path) -> str:
    try:
        return value.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return value.name


def _safe_runtime_models(value: Any) -> tuple[dict[str, Any], ...] | None:
    if not isinstance(value, list) or not value:
        return None
    models: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        alias = _safe_identifier(item.get("alias"), "alias")
        model_path = _safe_relative_path(item.get("model_path"), "model_path")
        if alias is None or model_path is None:
            return None
        model = {"alias": alias, "model_path": model_path}
        prompt_prefix = item.get("prompt_prefix")
        if prompt_prefix is not None:
            prompt_prefix_text = _safe_text(prompt_prefix)
            if prompt_prefix_text is None:
                return None
            model["prompt_prefix"] = prompt_prefix_text
        models.append(model)
    return tuple(models)


def _safe_runtime_scenarios(value: Any) -> tuple[dict[str, Any], ...] | None:
    if not isinstance(value, list) or not value:
        return None
    scenarios: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        scenario_id = _safe_identifier(item.get("scenario_id"), "scenario_id")
        scenario_label = _safe_identifier(item.get("scenario_label"), "scenario_label")
        prompt_filename = _safe_identifier(item.get("prompt_filename", DEFAULT_PROMPT_FILENAME), "prompt_filename")
        max_tokens = _required_int(item.get("max_tokens", DEFAULT_MAX_TOKENS), "max_tokens")
        if scenario_id is None or scenario_label is None or prompt_filename is None or max_tokens <= 0:
            return None
        scenarios.append(
            {
                "scenario_id": scenario_id,
                "scenario_label": scenario_label,
                "prompt_filename": prompt_filename,
                "max_tokens": max_tokens,
            }
        )
    return tuple(scenarios)


def _safe_runtime_trial_records(value: Any) -> tuple[dict[str, Any], ...] | None:
    if not isinstance(value, list) or not value:
        return None
    records: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        model_alias = _safe_identifier(item.get("model_alias"), "model_alias")
        scenario_id = _safe_identifier(item.get("scenario_id"), "scenario_id")
        trial_id = _safe_identifier(item.get("trial_id"), "trial_id")
        trial_label = _safe_identifier(item.get("trial_label"), "trial_label")
        workflow_id = _safe_identifier(item.get("workflow_id"), "workflow_id")
        request_path = _safe_relative_path(item.get("request_path"), "request_path")
        prompt_path = _safe_relative_path(item.get("prompt_path"), "prompt_path")
        response_path = _safe_relative_path(item.get("response_path"), "response_path")
        output_path = _safe_relative_path(item.get("output_path"), "output_path")
        raw_output_path = _safe_relative_path(item.get("raw_output_path"), "raw_output_path")
        if None in (model_alias, scenario_id, trial_id, trial_label, workflow_id, request_path, prompt_path, response_path, output_path, raw_output_path):
            return None
        record = {
            "model_alias": model_alias,
            "model_path": _safe_relative_path(item.get("model_path", DEFAULT_REQUEST_MODEL_PATH), "model_path") or DEFAULT_REQUEST_MODEL_PATH,
            "scenario_id": scenario_id,
            "trial_id": trial_id,
            "trial_label": trial_label,
            "workflow_id": workflow_id,
            "request_path": request_path,
            "prompt_path": prompt_path,
            "response_path": response_path,
            "output_path": output_path,
            "raw_output_path": raw_output_path,
        }
        trial_index = item.get("trial_index")
        if isinstance(trial_index, int) and not isinstance(trial_index, bool):
            record["trial_index"] = trial_index
        prompt_prefix = item.get("prompt_prefix")
        if prompt_prefix is not None:
            prompt_prefix_text = _safe_text(prompt_prefix)
            if prompt_prefix_text is None:
                return None
            record["prompt_prefix"] = prompt_prefix_text
        max_tokens = item.get("max_tokens")
        if isinstance(max_tokens, int) and not isinstance(max_tokens, bool):
            record["max_tokens"] = max_tokens
        records.append(record)
    return tuple(records)


def _nested_paths_by_trial(records: list[dict[str, Any]], key: str) -> dict[str, dict[str, dict[str, str]]]:
    nested: dict[str, dict[str, dict[str, str]]] = {}
    for record in records:
        model_alias = str(record["model_alias"])
        scenario_id = str(record["scenario_id"])
        trial_label = str(record["trial_label"])
        nested.setdefault(model_alias, {}).setdefault(scenario_id, {})[trial_label] = str(record[key])
    return nested


def _response_finish_reason(response_path: Path) -> str | None:
    if not response_path.exists():
        return None
    try:
        payload = json.loads(response_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return None
    if not isinstance(payload, Mapping):
        return None
    choices = payload.get("choices")
    if not isinstance(choices, list) or not choices:
        return None
    first_choice = choices[0]
    if not isinstance(first_choice, Mapping):
        return None
    finish_reason = first_choice.get("finish_reason")
    return str(finish_reason) if finish_reason is not None else None


def _workflow_status_for_result(status: str) -> str:
    if status == "succeeded":
        return "succeeded"
    if status == "missing":
        return "missing"
    return "failed"


def _trial_note(trial_label: str) -> str:
    return (
        f"This is independent trial {trial_label}.\n"
        "Return a fresh valid JSON object.\n"
        "Keep the same strict schema."
    )


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _safe_identifier(value: Any, label: str = "identifier") -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or any(ch.isspace() for ch in text):
        return None
    if any(sep in text for sep in ("/", "\\", ":", "..")):
        return None
    return text


def _required_identifier_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list.")
    items: list[str] = []
    for candidate in value:
        identifier = _safe_identifier(candidate, label)
        if identifier is None:
            raise ValueError(f"{label} contains an unsafe identifier.")
        items.append(identifier)
    return items


def _required_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean.")
    return value


def _required_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be an integer.")
    return value


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _safe_string_list(value: Any, label: str) -> list[str] | None:
    if not isinstance(value, list) or not value:
        return None
    items: list[str] = []
    for item in value:
        text = _safe_text(item)
        if text is None:
            return None
        items.append(text)
    return items


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {key: _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple):
        return [_jsonable(item) for item in value]
    if isinstance(value, list):
        return [_jsonable(item) for item in value]
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    safe_path = _windows_safe_path(path)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    safe_path = _windows_safe_path(path)
    safe_path.parent.mkdir(parents=True, exist_ok=True)
    safe_path.write_text(text, encoding="utf-8")


def _windows_safe_path(path: Path) -> Path:
    if os.name == "nt":
        path_text = str(path)
        if len(path_text) >= 248 and not path_text.startswith("\\\\?\\") and path.is_absolute():
            return Path("\\\\?\\" + path_text)
    return path


def _windows_path(value: str) -> str:
    return value.replace("/", "\\")


def _build_failure_summary(
    *,
    schema_version: str,
    packet_id: str | None,
    output_dir: str | None,
    captured_output_dir: str | None,
    materialized_output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": schema_version,
        "status": "failed",
        "error_code": error_code,
        "no_runtime_execution": True,
        "model_execution": False,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
        "packet_id": packet_id,
        "output_dir": output_dir,
        "captured_output_dir": captured_output_dir,
        "materialized_output_dir": materialized_output_dir,
        "limitations": list(limitations),
    }


def _evaluator_failure_summary(
    *,
    packet_id: str | None,
    packet_output_dir: str | None,
    output_dir: str | None,
    materialized_output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {
        "schema_version": EVALUATOR_SUMMARY_SCHEMA_VERSION,
        "packet_id": packet_id,
        "status": "failed",
        "error_code": error_code,
        "models_total": 0,
        "scenarios_total": 0,
        "trials_per_scenario": DEFAULT_TRIAL_COUNT,
        "outputs_total": 0,
        "outputs_present": 0,
        "outputs_missing": 0,
        "outputs_ingested": 0,
        "outputs_rejected": 0,
        "validation_accepted": 0,
        "validation_rejected": 0,
        "workflows_succeeded": 0,
        "workflows_failed": 0,
        "finish_reason_counts": {},
        "failure_class_counts": {},
        "scenario_summaries": [],
        "trial_summaries": [],
        "output_summaries": [],
        "pass_rate_overall": 0.0,
        "validation_acceptance_rate": 0.0,
        "packet_output_dir": packet_output_dir,
        "output_dir": output_dir,
        "materialized_output_dir": materialized_output_dir,
        "model_execution": False,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
        "real_network_traffic": False,
        "fixture_only": True,
        "no_runtime_execution": True,
        "limitations": list(limitations),
    }
    if diagnostics is not None:
        summary["diagnostics"] = diagnostics
    return summary


def _materializer_failure_summary(
    *,
    packet_id: str | None,
    output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    summary = {
        "schema_version": MATERIALIZER_SUMMARY_SCHEMA_VERSION,
        "packet_id": packet_id,
        "status": "failed",
        "error_code": error_code,
        "outputs_total": 0,
        "outputs_present": 0,
        "outputs_missing": 0,
        "outputs_accepted": 0,
        "outputs_rejected": 0,
        "workflows_materialized": 0,
        "workflows_failed": 0,
        "actions_total": 0,
        "facts_total": 0,
        "evidence_items_total": 0,
        "final_answers_total": 0,
        "failure_class_counts": {},
        "scenario_summaries": [],
        "trial_summaries": [],
        "output_summaries": [],
        "output_dir": output_dir,
        "model_execution": False,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
        "real_network_traffic": False,
        "fixture_only": True,
        "no_runtime_execution": True,
        "limitations": list(limitations),
    }
    if diagnostics is not None:
        summary["diagnostics"] = diagnostics
    return summary
