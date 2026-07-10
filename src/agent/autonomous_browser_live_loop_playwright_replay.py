from __future__ import annotations

import json
from collections import defaultdict
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_plan_playwright_replay_operator import (
    CONFIG_SCHEMA_VERSION as PLAYWRIGHT_OPERATOR_CONFIG_SCHEMA_VERSION,
    AutonomousBrowserPlanPlaywrightReplayOperatorConfigError,
    REQUIRED_CONFIRM_VALUE,
    load_autonomous_browser_plan_playwright_replay_operator_config,
    run_autonomous_browser_plan_playwright_replay_operator,
    ALLOWED_BROWSER_HOSTS as PLAYWRIGHT_ALLOWED_BROWSER_HOSTS,
)
from .autonomous_browser_plan_validation import validate_autonomous_browser_plan
from .browser_fixture_resolver import resolve_browser_fixture_url
from urllib.parse import urlparse


CONFIG_SCHEMA_VERSION = "autonomous_browser_live_loop_playwright_replay_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_live_loop_playwright_replay_summary_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/live_loop_playwright_replay"
DEFAULT_VARIANCE_SUITE_SUMMARY = "artifacts/autonomous_runtime_summaries/live_loop_variance_suite.summary.json"
DEFAULT_TRACE_ROOT = "artifacts/autonomous_runtime_summaries/live_loop_variance_suite"
DEFAULT_FIXTURE_MANIFEST_PATH = "tests/fixtures/local_intranet/office_site_v1/site_manifest.json"
SUPPORTED_REPLAY_BACKENDS = ("fixture", "playwright")
SUPPORTED_TRIAL_SELECTIONS = ("first_success_per_scenario", "all_successful_trials")
SUPPORTED_REPLAY_ACTIONS = (
    "browser_open_url",
    "browser_click",
    "browser_extract_text",
    "browser_snapshot",
)
DEFAULT_ALLOWED_HOSTS = (
    "local.intranet",
    "local-intranet.test",
    "docs.local",
    "portal.local",
    "127.0.0.1",
    "localhost",
)


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopPlaywrightReplayConfig:
    schema_version: str
    suite_id: str
    input_variance_suite_summary: str | None
    input_trace_root: str | None
    input_trace_paths: tuple[str, ...]
    scenario_ids: tuple[str, ...]
    trial_selection: str
    replay_backend: str
    allow_real_browser: bool
    allow_playwright: bool
    require_explicit_allow_real_browser: bool
    require_explicit_allow_playwright: bool
    fixture_only: bool
    fixture_manifest_path: str
    allowed_hosts: tuple[str, ...]
    real_network_traffic_allowed: bool
    headless: bool
    timeout_ms: int
    output_dir: str
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "suite_id": self.suite_id,
            "input_variance_suite_summary": self.input_variance_suite_summary,
            "input_trace_root": self.input_trace_root,
            "input_trace_paths": list(self.input_trace_paths),
            "scenario_ids": list(self.scenario_ids),
            "trial_selection": self.trial_selection,
            "replay_backend": self.replay_backend,
            "allow_real_browser": self.allow_real_browser,
            "allow_playwright": self.allow_playwright,
            "require_explicit_allow_real_browser": self.require_explicit_allow_real_browser,
            "require_explicit_allow_playwright": self.require_explicit_allow_playwright,
            "fixture_only": self.fixture_only,
            "fixture_manifest_path": self.fixture_manifest_path,
            "allowed_hosts": list(self.allowed_hosts),
            "real_network_traffic_allowed": self.real_network_traffic_allowed,
            "headless": self.headless,
            "timeout_ms": self.timeout_ms,
            "output_dir": self.output_dir,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopPlaywrightReplayTraceSummary:
    scenario_id: str | None
    trial_label: str | None
    trial_index: int | None
    source_trace_path: str | None
    status: str
    error_code: str | None
    actions_attempted: int
    actions_succeeded: int
    actions_failed: int
    expected_results_passed: int
    expected_results_failed: int
    matched_url: str | None
    replay_final_url: str | None
    fixture_only: bool
    real_browser_execution: bool
    real_network_traffic: bool
    browser_opened: bool
    playwright_execution: bool
    no_runtime_execution: bool
    model_execution: bool = False
    limitations: tuple[str, ...] = ()
    selected_action_names: tuple[str, ...] = ()
    replay_plan_path: str | None = None
    backend_config_path: str | None = None
    backend_config_schema_version: str | None = None
    diagnostics: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "trial_label": self.trial_label,
            "trial_index": self.trial_index,
            "source_trace_path": self.source_trace_path,
            "status": self.status,
            "error_code": self.error_code,
            "actions_attempted": self.actions_attempted,
            "actions_succeeded": self.actions_succeeded,
            "actions_failed": self.actions_failed,
            "expected_results_passed": self.expected_results_passed,
            "expected_results_failed": self.expected_results_failed,
            "matched_url": self.matched_url,
            "replay_final_url": self.replay_final_url,
            "fixture_only": self.fixture_only,
            "real_browser_execution": self.real_browser_execution,
            "real_network_traffic": self.real_network_traffic,
            "browser_opened": self.browser_opened,
            "playwright_execution": self.playwright_execution,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "limitations": list(self.limitations),
            "selected_action_names": list(self.selected_action_names),
            "replay_plan_path": self.replay_plan_path,
            "backend_config_path": self.backend_config_path,
            "backend_config_schema_version": self.backend_config_schema_version,
            "diagnostics": _jsonable(self.diagnostics),
        }


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopPlaywrightReplayScenarioSummary:
    scenario_id: str
    selected_trace_count: int
    traces_succeeded: int
    traces_failed: int
    traces_rejected: int
    actions_attempted_total: int
    actions_succeeded_total: int
    actions_failed_total: int
    expected_results_passed_total: int
    expected_results_failed_total: int
    unique_matched_urls: tuple[str, ...]
    unique_replay_final_urls: tuple[str, ...]
    unique_source_trace_paths: tuple[str, ...]
    route_stable: bool
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "selected_trace_count": self.selected_trace_count,
            "traces_succeeded": self.traces_succeeded,
            "traces_failed": self.traces_failed,
            "traces_rejected": self.traces_rejected,
            "actions_attempted_total": self.actions_attempted_total,
            "actions_succeeded_total": self.actions_succeeded_total,
            "actions_failed_total": self.actions_failed_total,
            "expected_results_passed_total": self.expected_results_passed_total,
            "expected_results_failed_total": self.expected_results_failed_total,
            "unique_matched_urls": list(self.unique_matched_urls),
            "unique_replay_final_urls": list(self.unique_replay_final_urls),
            "unique_source_trace_paths": list(self.unique_source_trace_paths),
            "route_stable": self.route_stable,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopPlaywrightReplaySummary:
    schema_version: str
    suite_id: str | None
    status: str
    error_code: str | None
    replay_backend: str | None
    input_trace_count: int
    selected_trace_count: int
    scenarios_total: int
    traces_replayed: int
    traces_succeeded: int
    traces_failed: int
    traces_rejected: int
    actions_attempted_total: int
    actions_succeeded_total: int
    actions_failed_total: int
    expected_results_passed_total: int
    expected_results_failed_total: int
    real_browser_execution: bool
    playwright_execution: bool
    browser_opened: bool
    real_network_traffic: bool
    fixture_only: bool
    allow_real_browser: bool
    allow_playwright: bool
    no_runtime_execution: bool
    model_execution: bool
    output_dir: str | None
    limitations: tuple[str, ...] = ()
    scenario_summaries: tuple[dict[str, Any], ...] = ()
    replay_trace_summaries: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "suite_id": self.suite_id,
            "status": self.status,
            "error_code": self.error_code,
            "replay_backend": self.replay_backend,
            "input_trace_count": self.input_trace_count,
            "selected_trace_count": self.selected_trace_count,
            "scenarios_total": self.scenarios_total,
            "traces_replayed": self.traces_replayed,
            "traces_succeeded": self.traces_succeeded,
            "traces_failed": self.traces_failed,
            "traces_rejected": self.traces_rejected,
            "actions_attempted_total": self.actions_attempted_total,
            "actions_succeeded_total": self.actions_succeeded_total,
            "actions_failed_total": self.actions_failed_total,
            "expected_results_passed_total": self.expected_results_passed_total,
            "expected_results_failed_total": self.expected_results_failed_total,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "real_network_traffic": self.real_network_traffic,
            "fixture_only": self.fixture_only,
            "allow_real_browser": self.allow_real_browser,
            "allow_playwright": self.allow_playwright,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "output_dir": self.output_dir,
            "limitations": list(self.limitations),
            "scenario_summaries": [_jsonable(item) for item in self.scenario_summaries],
            "replay_trace_summaries": [_jsonable(item) for item in self.replay_trace_summaries],
        }


def load_autonomous_browser_live_loop_playwright_replay_config(
    config_artifact: str | Path | Mapping[str, Any],
) -> AutonomousBrowserLiveLoopPlaywrightReplayConfig:
    try:
        payload = _load_json_payload(config_artifact)
    except OSError as exc:
        raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError("playwright replay config could not be read.") from exc
    except json.JSONDecodeError as exc:
        raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError("playwright replay config JSON is malformed.") from exc
    if not isinstance(payload, dict):
        raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError("playwright replay config root must be an object.")
    return _config_from_mapping(payload)


def run_autonomous_browser_live_loop_playwright_replay(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    dry_run: bool = False,
    allow_real_browser: bool = False,
    allow_playwright: bool = False,
    replay_backend: str | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    try:
        config = load_autonomous_browser_live_loop_playwright_replay_config(config_artifact)
    except AutonomousBrowserLiveLoopPlaywrightReplayConfigError as exc:
        return _failure_summary(
            status="failed",
            error_code="config_validation_failed",
            suite_id=None,
            replay_backend=_safe_backend_value(replay_backend),
            input_trace_count=0,
            limitations=tuple(),
            diagnostics={"config_error": str(exc)},
        )

    requested_backend = _resolve_replay_backend(config.replay_backend, replay_backend)
    if requested_backend is None:
        return _failure_summary(
            status="failed",
            error_code="unknown_replay_backend",
            suite_id=config.suite_id,
            replay_backend=_safe_backend_value(replay_backend) or config.replay_backend,
            input_trace_count=0,
            limitations=config.limitations,
            diagnostics={"config": _jsonable(config.to_dict())},
        )

    config_error = _validate_config(config, replay_backend=requested_backend)
    if config_error is not None:
        return _failure_summary(
            status="failed",
            error_code=config_error,
            suite_id=config.suite_id,
            replay_backend=requested_backend,
            input_trace_count=0,
            limitations=config.limitations,
            diagnostics={"config": _jsonable(config.to_dict())},
        )

    if not dry_run:
        if config.require_explicit_allow_real_browser and not allow_real_browser:
            return _refused_summary(
                error_code="allow_real_browser_required",
                config=config,
                replay_backend=requested_backend,
                input_trace_count=0,
            )
        if config.require_explicit_allow_playwright and not allow_playwright:
            return _refused_summary(
                error_code="allow_playwright_required",
                config=config,
                replay_backend=requested_backend,
                input_trace_count=0,
            )

    trace_selections, trace_error = _discover_trace_selections(config, repo)
    if trace_error is not None:
        return _failure_summary(
            status="failed",
            error_code=trace_error["error_code"],
            suite_id=config.suite_id,
            replay_backend=requested_backend,
            input_trace_count=_int(trace_error.get("input_trace_count")),
            limitations=config.limitations,
            diagnostics=trace_error.get("diagnostics", {}),
        )

    if not trace_selections:
        return _failure_summary(
            status="failed",
            error_code="no_selected_traces",
            suite_id=config.suite_id,
            replay_backend=requested_backend,
            input_trace_count=0,
            limitations=config.limitations,
            diagnostics={"selection": "no traces matched the configured selection mode."},
        )

    if dry_run:
        trace_summaries, scenario_summaries, top_level = _summaries_for_dry_run(
            trace_selections,
            repo_root=repo,
            config=config,
        )
        summary = AutonomousBrowserLiveLoopPlaywrightReplaySummary(
            schema_version=SUMMARY_SCHEMA_VERSION,
            suite_id=config.suite_id,
            status="succeeded" if top_level["error_code"] is None else "failed",
            error_code=top_level["error_code"],
            replay_backend=requested_backend,
            input_trace_count=top_level["input_trace_count"],
            selected_trace_count=top_level["selected_trace_count"],
            scenarios_total=top_level["scenarios_total"],
            traces_replayed=top_level["traces_replayed"],
            traces_succeeded=top_level["traces_succeeded"],
            traces_failed=top_level["traces_failed"],
            traces_rejected=top_level["traces_rejected"],
            actions_attempted_total=top_level["actions_attempted_total"],
            actions_succeeded_total=top_level["actions_succeeded_total"],
            actions_failed_total=top_level["actions_failed_total"],
            expected_results_passed_total=top_level["expected_results_passed_total"],
            expected_results_failed_total=top_level["expected_results_failed_total"],
            real_browser_execution=False,
            playwright_execution=False,
            browser_opened=False,
            real_network_traffic=False,
            fixture_only=config.fixture_only,
            allow_real_browser=allow_real_browser,
            allow_playwright=allow_playwright,
            no_runtime_execution=True,
            model_execution=False,
            output_dir=config.output_dir,
            limitations=config.limitations,
            scenario_summaries=tuple(scenario_summaries),
            replay_trace_summaries=tuple(trace_summaries),
        )
        payload = summary.to_dict()
        _write_summary_if_needed(payload, repo, config.output_dir, should_write=True)
        return payload

    if requested_backend != "playwright" and not config.fixture_only:
        return _failure_summary(
            status="failed",
            error_code="unsupported_replay_backend",
            suite_id=config.suite_id,
            replay_backend=requested_backend,
            input_trace_count=len(trace_selections),
            limitations=config.limitations,
            diagnostics={"replay_backend": requested_backend},
        )

    trace_summaries: list[dict[str, Any]] = []
    scenario_groups: dict[str, dict[str, Any]] = {}
    input_trace_count = len(trace_selections)
    actions_attempted_total = 0
    actions_succeeded_total = 0
    actions_failed_total = 0
    expected_results_passed_total = 0
    expected_results_failed_total = 0
    traces_succeeded = 0
    traces_failed = 0
    traces_rejected = 0
    any_real_browser_execution = False
    any_playwright_execution = False
    any_browser_opened = False
    any_real_network_traffic = False
    no_runtime_execution = True
    first_issue_code: str | None = None

    for index, selection in enumerate(trace_selections):
        trace_payload, trace_error = _load_trace_payload(repo / selection.source_trace_path, display_path=selection.source_trace_path)
        if trace_error is not None:
            trace_summary = _trace_failure_summary(selection, trace_error["error_code"], limitations=config.limitations)
            trace_summaries.append(trace_summary)
            traces_failed += 1
            if first_issue_code is None:
                first_issue_code = trace_error["error_code"]
            continue

        plan_payload, plan_error = _build_replay_plan(
            selection,
            trace_payload,
            limitations=config.limitations,
            fixture_manifest_path=config.fixture_manifest_path,
            repo_root=repo_root,
        )
        if plan_error is not None:
            trace_summary = _trace_failure_summary(selection, plan_error["error_code"], limitations=config.limitations)
            trace_summaries.append(trace_summary)
            traces_failed += 1
            if first_issue_code is None:
                first_issue_code = plan_error["error_code"]
            continue

        plan_validation = validate_autonomous_browser_plan(plan_payload)
        validation_status = str(plan_validation.get("status") or "rejected")
        if validation_status != "accepted":
            error_code = str(plan_validation.get("error_code") or "replay_plan_validation_failed")
            trace_summary = _trace_failure_summary(
                selection,
                error_code,
                limitations=config.limitations,
                plan_validation=plan_validation,
                replay_plan_path=None,
                selected_action_names=_selected_action_names_from_actions(plan_payload.get("actions") if isinstance(plan_payload, Mapping) else None),
            )
            trace_summaries.append(trace_summary)
            traces_failed += 1
            if first_issue_code is None:
                first_issue_code = error_code
            continue

        replay_plan_path = _write_replay_plan(repo, config.output_dir, selection, plan_payload)
        operator_config_path, operator_config_payload = _write_operator_config_from_selection(
            repo,
            config.output_dir,
            selection,
            config,
            replay_plan_path,
        )
        try:
            backend_config = load_autonomous_browser_plan_playwright_replay_operator_config(repo / operator_config_path)
        except AutonomousBrowserPlanPlaywrightReplayOperatorConfigError as exc:
            trace_summary = _trace_failure_summary(
                selection,
                "config_validation_failed",
                limitations=config.limitations,
                replay_plan_path=replay_plan_path,
                selected_action_names=_selected_action_names_from_actions(plan_payload.get("actions") if isinstance(plan_payload, Mapping) else None),
                diagnostics={
                    "backend_config_path": operator_config_path,
                    "backend_config_schema_version": PLAYWRIGHT_OPERATOR_CONFIG_SCHEMA_VERSION,
                    "validation_error_code": "config_validation_failed",
                    "validation_error_message": str(exc),
                },
            )
            trace_summaries.append(trace_summary)
            traces_failed += 1
            if first_issue_code is None:
                first_issue_code = "config_validation_failed"
            continue

        operator_summary = run_autonomous_browser_plan_playwright_replay_operator(
            operator_config_path,
            repo_root=repo,
            allow_real_browser=allow_real_browser,
            confirm_real_browser=REQUIRED_CONFIRM_VALUE if allow_real_browser else None,
            dry_run=False,
            replay_backend=requested_backend,
        )
        operator_summary = _jsonable(operator_summary)
        trace_summary = _trace_summary_from_operator(
            selection,
            operator_summary,
            limitations=config.limitations,
            replay_plan_path=replay_plan_path,
            backend_config_path=operator_config_path,
            backend_config_payload=backend_config.to_dict() if hasattr(backend_config, "to_dict") else _jsonable(backend_config),
            replay_plan_payload=plan_payload,
        )
        trace_summaries.append(trace_summary)
        status = str(trace_summary["status"])
        if status == "succeeded":
            traces_succeeded += 1
        elif status == "refused":
            traces_rejected += 1
        else:
            traces_failed += 1
            if first_issue_code is None:
                first_issue_code = str(trace_summary.get("error_code") or "replay_trace_failed")

        actions_attempted_total += _int(trace_summary.get("actions_attempted"))
        actions_succeeded_total += _int(trace_summary.get("actions_succeeded"))
        actions_failed_total += _int(trace_summary.get("actions_failed"))
        expected_results_passed_total += _int(trace_summary.get("expected_results_passed"))
        expected_results_failed_total += _int(trace_summary.get("expected_results_failed"))
        no_runtime_execution = no_runtime_execution and bool(trace_summary.get("no_runtime_execution", False))
        any_real_browser_execution = any_real_browser_execution or bool(trace_summary.get("real_browser_execution", False))
        any_playwright_execution = any_playwright_execution or bool(trace_summary.get("playwright_execution", False))
        any_browser_opened = any_browser_opened or bool(trace_summary.get("browser_opened", False))
        any_real_network_traffic = any_real_network_traffic or bool(trace_summary.get("real_network_traffic", False))

        scenario_groups.setdefault(selection.scenario_id or "unknown", _scenario_accumulator(selection.scenario_id or "unknown", config.limitations))
        _update_scenario_accumulator(scenario_groups[selection.scenario_id or "unknown"], trace_summary)

    if not scenario_groups:
        for trace_summary in trace_summaries:
            scenario_id = str(trace_summary.get("scenario_id") or "unknown")
            scenario_groups.setdefault(scenario_id, _scenario_accumulator(scenario_id, config.limitations))
            _update_scenario_accumulator(scenario_groups[scenario_id], trace_summary)

    scenario_summaries = tuple(
        _finalize_scenario_accumulator(group).to_dict()
        for group in scenario_groups.values()
    )

    status = "succeeded" if traces_failed == 0 and traces_rejected == 0 else "failed"
    error_code = None if status == "succeeded" else first_issue_code or "playwright_replay_failed"
    summary = AutonomousBrowserLiveLoopPlaywrightReplaySummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        suite_id=config.suite_id,
        status=status,
        error_code=error_code,
        replay_backend=requested_backend,
        input_trace_count=input_trace_count,
        selected_trace_count=len(trace_selections),
        scenarios_total=len(scenario_summaries),
        traces_replayed=len(trace_selections),
        traces_succeeded=traces_succeeded,
        traces_failed=traces_failed,
        traces_rejected=traces_rejected,
        actions_attempted_total=actions_attempted_total,
        actions_succeeded_total=actions_succeeded_total,
        actions_failed_total=actions_failed_total,
        expected_results_passed_total=expected_results_passed_total,
        expected_results_failed_total=expected_results_failed_total,
        real_browser_execution=any_real_browser_execution,
        playwright_execution=any_playwright_execution,
        browser_opened=any_browser_opened,
        real_network_traffic=any_real_network_traffic,
        fixture_only=config.fixture_only,
        allow_real_browser=allow_real_browser,
        allow_playwright=allow_playwright,
        no_runtime_execution=no_runtime_execution,
        model_execution=False,
        output_dir=config.output_dir,
        limitations=config.limitations,
        scenario_summaries=scenario_summaries,
        replay_trace_summaries=tuple(trace_summaries),
    )
    payload = summary.to_dict()
    _write_summary_if_needed(payload, repo, config.output_dir, should_write=True)
    return payload


def write_autonomous_browser_live_loop_playwright_replay_summary(summary: Mapping[str, Any], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_live_loop_playwright_replay_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _summaries_for_dry_run(
    trace_selections: list["_ReplayTraceSelection"],
    *,
    repo_root: Path,
    config: AutonomousBrowserLiveLoopPlaywrightReplayConfig,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]], dict[str, int | str | None]]:
    trace_summaries: list[dict[str, Any]] = []
    scenario_groups: dict[str, _ScenarioAccumulator] = {}
    input_trace_count = len(trace_selections)
    selected_trace_count = len(trace_selections)
    actions_attempted_total = 0
    actions_succeeded_total = 0
    actions_failed_total = 0
    expected_results_passed_total = 0
    expected_results_failed_total = 0
    traces_succeeded = 0
    traces_failed = 0
    traces_rejected = 0
    first_issue_code: str | None = None

    for selection in trace_selections:
        trace_payload, trace_error = _load_trace_payload(repo_root / selection.source_trace_path, display_path=selection.source_trace_path)
        if trace_error is not None:
            trace_summary = _trace_failure_summary(selection, trace_error["error_code"], limitations=config.limitations)
            trace_summaries.append(trace_summary)
            traces_failed += 1
            if first_issue_code is None:
                first_issue_code = trace_error["error_code"]
            continue

        plan_payload, plan_error = _build_replay_plan(
            selection,
            trace_payload,
            limitations=config.limitations,
            fixture_manifest_path=config.fixture_manifest_path,
            repo_root=repo_root,
        )
        if plan_error is not None:
            trace_summary = _trace_failure_summary(selection, plan_error["error_code"], limitations=config.limitations)
            trace_summaries.append(trace_summary)
            traces_failed += 1
            if first_issue_code is None:
                first_issue_code = plan_error["error_code"]
            continue

        plan_validation = validate_autonomous_browser_plan(plan_payload)
        validation_status = str(plan_validation.get("status") or "rejected")
        if validation_status != "accepted":
            error_code = str(plan_validation.get("error_code") or "replay_plan_validation_failed")
            trace_summary = _trace_failure_summary(
                selection,
                error_code,
                limitations=config.limitations,
                plan_validation=plan_validation,
                replay_plan_path=None,
                selected_action_names=_selected_action_names_from_actions(plan_payload.get("actions") if isinstance(plan_payload, Mapping) else None),
            )
            trace_summaries.append(trace_summary)
            traces_failed += 1
            if first_issue_code is None:
                first_issue_code = error_code
            continue

        trace_summary = _trace_summary_from_plan(
            selection,
            plan_payload,
            plan_validation,
            limitations=config.limitations,
        )
        trace_summaries.append(trace_summary)
        traces_succeeded += 1
        actions_attempted_total += _int(trace_summary["actions_attempted"])
        actions_succeeded_total += _int(trace_summary["actions_succeeded"])
        actions_failed_total += _int(trace_summary["actions_failed"])
        expected_results_passed_total += _int(trace_summary["expected_results_passed"])
        expected_results_failed_total += _int(trace_summary["expected_results_failed"])

        scenario_groups.setdefault(selection.scenario_id or "unknown", _scenario_accumulator(selection.scenario_id or "unknown", config.limitations))
        _update_scenario_accumulator(scenario_groups[selection.scenario_id or "unknown"], trace_summary)

    scenario_summaries = tuple(
        _finalize_scenario_accumulator(group).to_dict()
        for group in scenario_groups.values()
    )
    return (
        trace_summaries,
        list(scenario_summaries),
        {
            "input_trace_count": input_trace_count,
            "selected_trace_count": selected_trace_count,
            "scenarios_total": len(scenario_summaries),
            "traces_replayed": selected_trace_count,
            "traces_succeeded": traces_succeeded,
            "traces_failed": traces_failed,
            "traces_rejected": traces_rejected,
            "actions_attempted_total": actions_attempted_total,
            "actions_succeeded_total": actions_succeeded_total,
            "actions_failed_total": actions_failed_total,
            "expected_results_passed_total": expected_results_passed_total,
            "expected_results_failed_total": expected_results_failed_total,
            "error_code": first_issue_code,
        },
    )


def _trace_summary_from_plan(
    selection: "_ReplayTraceSelection",
    plan_payload: Mapping[str, Any],
    plan_validation: Mapping[str, Any],
    *,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    actions = plan_payload.get("actions") if isinstance(plan_payload, Mapping) else []
    replay_final_url = _final_trace_url(selection.trace_payload)
    matched_url = selection.matched_url or replay_final_url
    selected_action_names = _selected_action_names_from_actions(actions)
    actions_attempted = len([item for item in actions if isinstance(item, Mapping)])
    expected_results_passed = _expected_results_passed_from_trace(selection.trace_payload)
    expected_results_failed = _expected_results_failed_from_trace(selection.trace_payload)
    return AutonomousBrowserLiveLoopPlaywrightReplayTraceSummary(
        scenario_id=selection.scenario_id,
        trial_label=selection.trial_label,
        trial_index=selection.trial_index,
        source_trace_path=selection.source_trace_path,
        status="succeeded",
        error_code=None,
        actions_attempted=actions_attempted,
        actions_succeeded=actions_attempted,
        actions_failed=0,
        expected_results_passed=expected_results_passed,
        expected_results_failed=expected_results_failed,
        matched_url=matched_url,
        replay_final_url=replay_final_url,
        fixture_only=True,
        real_browser_execution=False,
        real_network_traffic=False,
        browser_opened=False,
        playwright_execution=False,
        no_runtime_execution=True,
        limitations=limitations,
        selected_action_names=selected_action_names,
        diagnostics={
            "replay_plan_path": None,
            "selected_action_names": list(selected_action_names),
        },
    ).to_dict()


def _selected_action_names_from_actions(actions: Any) -> tuple[str, ...]:
    if not isinstance(actions, list):
        return tuple()
    names: list[str] = []
    for item in actions:
        if not isinstance(item, Mapping):
            continue
        action_name = _action_name_from_mapping(item)
        if action_name:
            names.append(action_name)
    return tuple(names)


def _trace_summary_from_operator(
    selection: "_ReplayTraceSelection",
    operator_summary: Mapping[str, Any],
    *,
    limitations: tuple[str, ...],
    replay_plan_path: str,
    backend_config_path: str | None = None,
    backend_config_payload: Mapping[str, Any] | None = None,
    replay_plan_payload: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    replay_final_url = _operator_replay_final_url(operator_summary)
    matched_url = selection.matched_url or replay_final_url
    status = str(operator_summary.get("status") or "failed")
    error_code = operator_summary.get("error_code")
    if error_code is not None:
        error_code = str(error_code)
    actions_attempted = _int(operator_summary.get("actions_attempted"))
    actions_succeeded = _int(operator_summary.get("actions_succeeded"))
    actions_failed = _int(operator_summary.get("actions_failed"))
    expected_passed = _int(operator_summary.get("expected_results_passed"))
    expected_failed = _int(operator_summary.get("expected_results_failed"))
    selected_action_names = _selected_action_names_from_actions(
        replay_plan_payload.get("actions") if isinstance(replay_plan_payload, Mapping) else None
    )
    diagnostics: dict[str, Any] = {
        "replay_plan_path": replay_plan_path,
        "selected_action_names": list(selected_action_names),
    }
    if backend_config_path is not None:
        diagnostics["backend_config_path"] = backend_config_path
    if isinstance(backend_config_payload, Mapping):
        schema_version = _optional_text(backend_config_payload.get("schema_version"))
        if schema_version:
            diagnostics["backend_config_schema_version"] = schema_version
    operator_diagnostics = operator_summary.get("diagnostics")
    if isinstance(operator_diagnostics, Mapping):
        validation_result = operator_diagnostics.get("validation")
        if isinstance(validation_result, Mapping):
            diagnostics["validation_error_code"] = _optional_text(validation_result.get("error_code"))
            diagnostics["validation_error_message"] = _optional_text(validation_result.get("message"))
            diagnostics["validation_errors"] = _safe_validation_diagnostics(validation_result)
        replay_result = operator_diagnostics.get("replay_result")
        if isinstance(replay_result, Mapping):
            diagnostics["replay_result"] = {
                "status": _optional_text(replay_result.get("status")),
                "error_code": _optional_text(replay_result.get("error_code")),
                "final_url": _optional_text(replay_result.get("final_url")),
                "actions_attempted": _int(replay_result.get("actions_attempted")),
                "actions_succeeded": _int(replay_result.get("actions_succeeded")),
                "actions_failed": _int(replay_result.get("actions_failed")),
                "expected_results_passed": _int(replay_result.get("expected_results_passed")),
                "expected_results_failed": _int(replay_result.get("expected_results_failed")),
            }
        replayed_actions = operator_diagnostics.get("replayed_actions")
        if isinstance(replayed_actions, list):
            diagnostics["replayed_actions"] = [_safe_replayed_action_diagnostic(item) for item in replayed_actions if isinstance(item, Mapping)]
        if isinstance(operator_diagnostics.get("config_error"), str):
            diagnostics["validation_error_message"] = str(operator_diagnostics["config_error"])
        if isinstance(operator_diagnostics.get("replay_plan_error"), str):
            diagnostics["validation_error_message"] = str(operator_diagnostics["replay_plan_error"])
        nested_backend_config_path = operator_diagnostics.get("backend_config_path")
        if nested_backend_config_path is not None:
            diagnostics["backend_config_path"] = _safe_relative_path(nested_backend_config_path, "backend_config_path")
        missing_required_fields = operator_diagnostics.get("missing_required_fields")
        if isinstance(missing_required_fields, list):
            diagnostics["missing_required_fields"] = [str(item) for item in missing_required_fields if isinstance(item, str) and item.strip()]
        invalid_field_paths = operator_diagnostics.get("invalid_field_paths")
        if isinstance(invalid_field_paths, list):
            diagnostics["invalid_field_paths"] = [str(item) for item in invalid_field_paths if isinstance(item, str) and item.strip()]
    if "validation_error_code" not in diagnostics and status != "succeeded" and error_code:
        diagnostics["validation_error_code"] = error_code
    return AutonomousBrowserLiveLoopPlaywrightReplayTraceSummary(
        scenario_id=selection.scenario_id,
        trial_label=selection.trial_label,
        trial_index=selection.trial_index,
        source_trace_path=selection.source_trace_path,
        status=status,
        error_code=error_code,
        actions_attempted=actions_attempted,
        actions_succeeded=actions_succeeded,
        actions_failed=actions_failed,
        expected_results_passed=expected_passed,
        expected_results_failed=expected_failed,
        matched_url=matched_url,
        replay_final_url=replay_final_url,
        fixture_only=True,
        real_browser_execution=bool(operator_summary.get("real_browser_execution", False)),
        real_network_traffic=bool(operator_summary.get("real_network_traffic", False)),
        browser_opened=bool(operator_summary.get("browser_opened", False)),
        playwright_execution=bool(operator_summary.get("playwright_execution", False)),
        no_runtime_execution=bool(operator_summary.get("no_runtime_execution", False)),
        model_execution=False,
        limitations=limitations,
        selected_action_names=selected_action_names,
        replay_plan_path=replay_plan_path,
        backend_config_path=backend_config_path,
        backend_config_schema_version=_optional_text(backend_config_payload.get("schema_version")) if isinstance(backend_config_payload, Mapping) else None,
        diagnostics=diagnostics,
    ).to_dict()


def _operator_replay_final_url(operator_summary: Mapping[str, Any]) -> str | None:
    diagnostics = operator_summary.get("diagnostics")
    if not isinstance(diagnostics, Mapping):
        return None
    replay_result = diagnostics.get("replay_result")
    if not isinstance(replay_result, Mapping):
        return None
    final_url = replay_result.get("final_url")
    return _optional_text(final_url)


def _trace_failure_summary(
    selection: "_ReplayTraceSelection",
    error_code: str,
    *,
    limitations: tuple[str, ...],
    plan_validation: Mapping[str, Any] | None = None,
    replay_plan_path: str | None = None,
    selected_action_names: tuple[str, ...] = (),
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    trace_diagnostics: dict[str, Any] = dict(_jsonable(diagnostics or {}))
    if plan_validation is not None:
        trace_diagnostics.setdefault("validation_error_code", _optional_text(plan_validation.get("error_code")))
        trace_diagnostics.setdefault("validation_errors", _safe_validation_diagnostics(plan_validation))
    return AutonomousBrowserLiveLoopPlaywrightReplayTraceSummary(
        scenario_id=selection.scenario_id,
        trial_label=selection.trial_label,
        trial_index=selection.trial_index,
        source_trace_path=selection.source_trace_path,
        status="failed",
        error_code=error_code,
        actions_attempted=0,
        actions_succeeded=0,
        actions_failed=0,
        expected_results_passed=0,
        expected_results_failed=0,
        matched_url=selection.matched_url,
        replay_final_url=_final_trace_url(selection.trace_payload),
        fixture_only=True,
        real_browser_execution=False,
        real_network_traffic=False,
        browser_opened=False,
        playwright_execution=False,
        no_runtime_execution=True,
        limitations=limitations,
        selected_action_names=selected_action_names,
        replay_plan_path=replay_plan_path,
        diagnostics=trace_diagnostics,
    ).to_dict()


def _action_name_from_mapping(action: Mapping[str, Any]) -> str | None:
    value = action.get("action_name")
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    value = action.get("name")
    if isinstance(value, str):
        text = value.strip()
        if text:
            return text
    return None


def _action_parameters_from_mapping(action: Mapping[str, Any]) -> dict[str, Any]:
    parameters = action.get("parameters")
    if isinstance(parameters, Mapping):
        return dict(parameters)
    return {}


def _trace_action_record(entry: Mapping[str, Any]) -> Mapping[str, Any] | None:
    planner_action = entry.get("planner_action")
    if isinstance(planner_action, Mapping):
        return planner_action
    if _action_name_from_mapping(entry) is not None:
        return entry
    return None


def _safe_validation_diagnostics(validation_result: Mapping[str, Any]) -> dict[str, Any]:
    safe_keys = ("finding_type", "path", "json_path", "key", "parameter_key", "error_code", "status", "type", "actions_total")
    diagnostics: dict[str, Any] = {}
    for key in safe_keys:
        if key in validation_result and validation_result[key] is not None:
            diagnostics[key] = _jsonable(validation_result[key])
    return diagnostics


def _safe_replayed_action_diagnostic(item: Mapping[str, Any]) -> dict[str, Any]:
    safe_keys = (
        "step_id",
        "action_name",
        "logical_url",
        "served_url",
        "target_text",
        "expected_text",
        "expected_text_found",
        "success",
        "error_code",
        "text_preview",
        "navigation_changed",
        "selector",
        "selector_kind",
        "clickable",
        "artifact_ref",
    )
    safe_item = {key: _jsonable(item[key]) for key in safe_keys if key in item and item[key] is not None}
    diagnostics = item.get("diagnostics")
    if isinstance(diagnostics, Mapping):
        safe_item["diagnostics"] = {
            key: _jsonable(value)
            for key, value in diagnostics.items()
            if key
            in {
                "before_url",
                "current_url",
                "after_url",
                "expected_text",
                "expected_text_found",
                "navigation_changed",
                "selector",
                "selector_kind",
                "clickable",
                "text_preview",
                "page_title",
            }
            and value is not None
        }
    return safe_item


def _scenario_accumulator(scenario_id: str, limitations: tuple[str, ...]) -> "_ScenarioAccumulator":
    return _ScenarioAccumulator(
        scenario_id=scenario_id,
        selected_trace_count=0,
        traces_succeeded=0,
        traces_failed=0,
        traces_rejected=0,
        actions_attempted_total=0,
        actions_succeeded_total=0,
        actions_failed_total=0,
        expected_results_passed_total=0,
        expected_results_failed_total=0,
        unique_matched_urls=tuple(),
        unique_replay_final_urls=tuple(),
        unique_source_trace_paths=tuple(),
        route_stable=True,
        limitations=limitations,
    )


@dataclass
class _ScenarioAccumulator:
    scenario_id: str
    selected_trace_count: int
    traces_succeeded: int
    traces_failed: int
    traces_rejected: int
    actions_attempted_total: int
    actions_succeeded_total: int
    actions_failed_total: int
    expected_results_passed_total: int
    expected_results_failed_total: int
    unique_matched_urls: tuple[str, ...]
    unique_replay_final_urls: tuple[str, ...]
    unique_source_trace_paths: tuple[str, ...]
    route_stable: bool
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "selected_trace_count": self.selected_trace_count,
            "traces_succeeded": self.traces_succeeded,
            "traces_failed": self.traces_failed,
            "traces_rejected": self.traces_rejected,
            "actions_attempted_total": self.actions_attempted_total,
            "actions_succeeded_total": self.actions_succeeded_total,
            "actions_failed_total": self.actions_failed_total,
            "expected_results_passed_total": self.expected_results_passed_total,
            "expected_results_failed_total": self.expected_results_failed_total,
            "unique_matched_urls": list(self.unique_matched_urls),
            "unique_replay_final_urls": list(self.unique_replay_final_urls),
            "unique_source_trace_paths": list(self.unique_source_trace_paths),
            "route_stable": self.route_stable,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class _ReplayTraceSelection:
    scenario_id: str | None
    trial_label: str | None
    trial_index: int | None
    source_trace_path: str
    matched_url: str | None
    trace_payload: dict[str, Any]


def _update_scenario_accumulator(accumulator: _ScenarioAccumulator, trace_summary: Mapping[str, Any]) -> None:
    accumulator.selected_trace_count += 1
    status = str(trace_summary.get("status") or "failed")
    if status == "succeeded":
        accumulator.traces_succeeded += 1
    elif status == "refused":
        accumulator.traces_rejected += 1
    else:
        accumulator.traces_failed += 1
    accumulator.actions_attempted_total += _int(trace_summary.get("actions_attempted"))
    accumulator.actions_succeeded_total += _int(trace_summary.get("actions_succeeded"))
    accumulator.actions_failed_total += _int(trace_summary.get("actions_failed"))
    accumulator.expected_results_passed_total += _int(trace_summary.get("expected_results_passed"))
    accumulator.expected_results_failed_total += _int(trace_summary.get("expected_results_failed"))
    matched_url = _optional_text(trace_summary.get("matched_url"))
    replay_final_url = _optional_text(trace_summary.get("replay_final_url"))
    source_trace_path = _optional_text(trace_summary.get("source_trace_path"))
    accumulator.unique_matched_urls = _unique_append(accumulator.unique_matched_urls, matched_url)
    accumulator.unique_replay_final_urls = _unique_append(accumulator.unique_replay_final_urls, replay_final_url)
    accumulator.unique_source_trace_paths = _unique_append(accumulator.unique_source_trace_paths, source_trace_path)
    accumulator.route_stable = len(accumulator.unique_matched_urls) <= 1


def _finalize_scenario_accumulator(accumulator: _ScenarioAccumulator) -> AutonomousBrowserLiveLoopPlaywrightReplayScenarioSummary:
    return AutonomousBrowserLiveLoopPlaywrightReplayScenarioSummary(
        scenario_id=accumulator.scenario_id,
        selected_trace_count=accumulator.selected_trace_count,
        traces_succeeded=accumulator.traces_succeeded,
        traces_failed=accumulator.traces_failed,
        traces_rejected=accumulator.traces_rejected,
        actions_attempted_total=accumulator.actions_attempted_total,
        actions_succeeded_total=accumulator.actions_succeeded_total,
        actions_failed_total=accumulator.actions_failed_total,
        expected_results_passed_total=accumulator.expected_results_passed_total,
        expected_results_failed_total=accumulator.expected_results_failed_total,
        unique_matched_urls=accumulator.unique_matched_urls,
        unique_replay_final_urls=accumulator.unique_replay_final_urls,
        unique_source_trace_paths=accumulator.unique_source_trace_paths,
        route_stable=accumulator.route_stable,
        limitations=accumulator.limitations,
    )


def _discover_trace_selections(
    config: AutonomousBrowserLiveLoopPlaywrightReplayConfig,
    repo_root: Path,
) -> tuple[list[_ReplayTraceSelection], dict[str, Any] | None]:
    if config.input_trace_paths:
        selections: list[_ReplayTraceSelection] = []
        for relative_path in config.input_trace_paths:
            path = _safe_relative_path(relative_path, "input_trace_paths")
            if path is None:
                return [], {"error_code": "unsafe_trace_path", "diagnostics": {"trace_path": relative_path}}
            trace_payload, trace_error = _load_trace_payload(repo_root / path, display_path=path)
            if trace_error is not None:
                return [], trace_error
            selection = _selection_from_trace_payload(path, trace_payload)
            selections.append(selection)
        return selections, None

    if config.input_variance_suite_summary:
        selections, trace_error = _discover_from_variance_suite_summary(config, repo_root)
        if trace_error is not None:
            return [], trace_error
        if selections:
            return selections, None

    if config.input_trace_root:
        selections, trace_error = _discover_from_trace_root(config, repo_root)
        if trace_error is not None:
            return [], trace_error
        if selections:
            return selections, None

    return [], {"error_code": "no_selected_traces", "diagnostics": {"selection": "no trace inputs were available."}}


def _discover_from_variance_suite_summary(
    config: AutonomousBrowserLiveLoopPlaywrightReplayConfig,
    repo_root: Path,
) -> tuple[list[_ReplayTraceSelection], dict[str, Any] | None]:
    if not config.input_variance_suite_summary:
        return [], None
    summary_path = repo_root / config.input_variance_suite_summary
    try:
        summary_payload = _load_json_payload(summary_path)
    except OSError:
        return [], {"error_code": "variance_suite_summary_read_failed", "diagnostics": {"summary_path": _safe_relative_path(config.input_variance_suite_summary, "input_variance_suite_summary")}}
    except json.JSONDecodeError:
        return [], {"error_code": "variance_suite_summary_malformed", "diagnostics": {"summary_path": _safe_relative_path(config.input_variance_suite_summary, "input_variance_suite_summary")}}
    if not isinstance(summary_payload, dict):
        return [], {"error_code": "variance_suite_summary_invalid", "diagnostics": {"summary_path": _safe_relative_path(config.input_variance_suite_summary, "input_variance_suite_summary")}}

    trial_summaries = summary_payload.get("trial_summaries")
    if not isinstance(trial_summaries, list):
        return [], {"error_code": "variance_suite_summary_invalid", "diagnostics": {"summary_path": _safe_relative_path(config.input_variance_suite_summary, "input_variance_suite_summary")}}

    selected: list[_ReplayTraceSelection] = []
    seen_scenarios: set[str] = set()
    for item in trial_summaries:
        if not isinstance(item, Mapping):
            continue
        scenario_id = _optional_text(item.get("scenario_id"))
        if not scenario_id or (config.scenario_ids and scenario_id not in config.scenario_ids):
            continue
        trace_path = _optional_text(item.get("trace_path"))
        if not trace_path:
            continue
        status = _optional_text(item.get("status"))
        if status != "succeeded":
            continue
        if config.trial_selection == "first_success_per_scenario" and scenario_id in seen_scenarios:
            continue
        trace_payload, trace_error = _load_trace_payload(repo_root / trace_path, display_path=trace_path)
        if trace_error is not None:
            return [], trace_error
        selection = _selection_from_trace_payload(trace_path, trace_payload, item)
        selected.append(selection)
        seen_scenarios.add(scenario_id)
    return selected, None


def _discover_from_trace_root(
    config: AutonomousBrowserLiveLoopPlaywrightReplayConfig,
    repo_root: Path,
) -> tuple[list[_ReplayTraceSelection], dict[str, Any] | None]:
    if not config.input_trace_root:
        return [], None
    root = repo_root / config.input_trace_root
    if not root.exists():
        return [], {"error_code": "trace_root_missing", "diagnostics": {"trace_root": _safe_relative_path(config.input_trace_root, "input_trace_root")}}

    selected: list[_ReplayTraceSelection] = []
    for scenario_id in config.scenario_ids:
        scenario_dir = root / scenario_id
        if not scenario_dir.exists():
            continue
        trial_dirs = sorted(path for path in scenario_dir.iterdir() if path.is_dir() and path.name.startswith("trial_"))
        for trial_dir in trial_dirs:
            trace_path = trial_dir / "autonomous_browser_live_loop_trace.json"
            if not trace_path.exists():
                continue
            trace_payload, trace_error = _load_trace_payload(trace_path, display_path=_safe_relative_path(trace_path.relative_to(repo_root), "trace_path") or str(trace_path.relative_to(repo_root)))
            if trace_error is not None:
                return [], trace_error
            if not _trace_is_successful(trace_payload):
                if config.trial_selection == "all_successful_trials":
                    continue
                continue
            selection = _selection_from_trace_payload(
                _safe_relative_path(trace_path.relative_to(repo_root), "trace_path") or str(trace_path.relative_to(repo_root)),
                trace_payload,
            )
            selected.append(selection)
            if config.trial_selection == "first_success_per_scenario":
                break
    return selected, None


def _selection_from_trace_payload(
    source_trace_path: str,
    trace_payload: Mapping[str, Any],
    source_summary: Mapping[str, Any] | None = None,
) -> _ReplayTraceSelection:
    scenario_id = _optional_text(trace_payload.get("scenario_id"))
    if source_summary is not None and not scenario_id:
        scenario_id = _optional_text(source_summary.get("scenario_id"))
    trial_label = _optional_text(source_summary.get("trial_label")) if source_summary is not None else None
    trial_index = _int(source_summary.get("trial_index")) if source_summary is not None and isinstance(source_summary.get("trial_index"), int) else None
    if trial_label is None:
        trial_label = _trial_label_from_path(source_trace_path)
    if trial_index is None:
        trial_index = _trial_index_from_path(source_trace_path)
    matched_url = None
    if source_summary is not None:
        matched_url = _optional_text(source_summary.get("matched_url"))
    if matched_url is None:
        matched_url = _matched_url_from_trace(trace_payload)
    return _ReplayTraceSelection(
        scenario_id=scenario_id,
        trial_label=trial_label,
        trial_index=trial_index,
        source_trace_path=source_trace_path,
        matched_url=matched_url,
        trace_payload=dict(trace_payload),
    )


def _build_replay_plan(
    selection: _ReplayTraceSelection,
    trace_payload: Mapping[str, Any],
    *,
    limitations: tuple[str, ...],
    fixture_manifest_path: str,
    repo_root: Path,
) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    replay_actions = _selected_trace_actions(trace_payload)
    if not replay_actions:
        return None, {"error_code": "no_replay_actions", "diagnostics": {"source_trace_path": selection.source_trace_path}}

    actions: list[dict[str, Any]] = []
    for index, entry in enumerate(replay_actions):
        if not isinstance(entry, Mapping):
            return None, {"error_code": "replay_action_missing", "diagnostics": {"path": f"trace[{index}]"}}
        planner_action = _trace_action_record(entry)
        if not isinstance(planner_action, Mapping):
            return None, {"error_code": "replay_action_missing", "diagnostics": {"path": f"trace[{index}].planner_action"}}
        action_name = _action_name_from_mapping(planner_action)
        if action_name not in SUPPORTED_REPLAY_ACTIONS:
            return None, {"error_code": "unsupported_replay_action", "diagnostics": {"action_name": action_name}}
        parameters = _action_parameters_from_mapping(planner_action)
        if not parameters:
            return None, {"error_code": "replay_action_invalid_parameters", "diagnostics": {"path": f"trace[{index}].planner_action.parameters"}}
        action: dict[str, Any] = {
            "step_id": _optional_text(planner_action.get("step_id")) or f"replay_step_{index + 1:02d}",
            "action_name": action_name,
            "parameters": parameters,
        }
        expected_text = _replay_expected_text(
            planner_action,
            current_url=_optional_text(entry.get("current_url")),
            fallback_expected_text=_optional_text(planner_action.get("expected_text")),
            fixture_manifest_path=fixture_manifest_path,
            repo_root=repo_root,
        )
        if expected_text:
            action["expected_text"] = expected_text
        expected_url = _optional_text(planner_action.get("expected_url"))
        if expected_url:
            action["expected_url"] = expected_url
        actions.append(action)

    plan_id = _plan_id_for_selection(selection)
    plan_payload = {
        "schema_version": "autonomous_browser_plan_v1",
        "plan_id": plan_id,
        "goal": f"Replay successful live-loop trace for {selection.scenario_id or 'unknown'}",
        "scenario_id": selection.scenario_id or "unknown",
        "max_actions": len(actions),
        "actions": actions,
    }
    validation_result = validate_autonomous_browser_plan(plan_payload)
    if str(validation_result.get("status")) != "accepted":
        return None, {
            "error_code": str(validation_result.get("error_code") or "replay_plan_validation_failed"),
            "diagnostics": {"validation_result": _jsonable(validation_result)},
        }
    return plan_payload, None


def _replay_expected_text(
    planner_action: Mapping[str, Any],
    *,
    current_url: str | None,
    fallback_expected_text: str | None,
    fixture_manifest_path: str,
    repo_root: Path,
) -> str | None:
    candidate_urls: list[str] = []
    for value in (
        _optional_text(planner_action.get("expected_url")),
        _optional_text(_action_parameters_from_mapping(planner_action).get("url")),
        current_url,
    ):
        if value and value not in candidate_urls:
            candidate_urls.append(value)
    for candidate_url in candidate_urls:
        if not candidate_url:
            continue
        try:
            resolution = resolve_browser_fixture_url(
                candidate_url,
                fixture_manifest_path,
                project_root=repo_root,
            )
        except Exception:
            route_anchor = _default_visible_anchor_for_url(candidate_url)
            if route_anchor:
                return route_anchor
            continue
        visible_anchor = _preferred_visible_anchor(resolution.route, resolution.extracted_text, resolution.title)
        if visible_anchor:
            if fallback_expected_text and fallback_expected_text != resolution.title and fallback_expected_text in resolution.extracted_text:
                return fallback_expected_text
            return visible_anchor
    return fallback_expected_text


def _preferred_visible_anchor(route: str, extracted_text: str, title: str | None) -> str | None:
    route_candidates: dict[str, tuple[str, ...]] = {
        "/": ("Office Intranet", "Search marker: fixture-backed result for local policy review.", "Today"),
        "/docs/policy": ("Workspace Policy", "Allowed activity", "Search marker: fixture-backed result for workspace policy review."),
        "/tickets": ("Ticket Board", "Open tickets", "Ticket 1: Quarterly Access Review requires an office-worker status note."),
        "/tickets/1": ("Quarterly Access Review", "Priority: high", "Assigned role: office worker"),
        "/portal/approvals": ("Approvals Queue", "Pending approval check", "Approval item APR-42 is waiting for local policy verification."),
        "/portal/approval-match": ("Approval Policy Match", "Local-only approval review", "Policy match: confirmed."),
    }
    candidates = list(route_candidates.get(route, ()))
    if title and title not in candidates:
        candidates.append(title)
    for candidate in candidates:
        if candidate and candidate in extracted_text:
            return candidate
    if extracted_text:
        return extracted_text.split(" ", 1)[0].strip() or None
    return title


def _default_visible_anchor_for_url(url: str) -> str | None:
    parsed = urlparse(url)
    route = parsed.path or "/"
    if route.endswith("/"):
        route = route.rstrip("/") or "/"
    route_anchor_map = {
        "/": "Office Intranet",
        "/docs/policy": "Workspace Policy",
        "/tickets": "Ticket Board",
        "/tickets/1": "Quarterly Access Review",
        "/portal/approvals": "Approvals Queue",
        "/portal/approval-match": "Approval Policy Match",
    }
    return route_anchor_map.get(route)


def _write_replay_plan(repo_root: Path, output_dir: str, selection: _ReplayTraceSelection, plan_payload: Mapping[str, Any]) -> str:
    relative_path = (
        Path(output_dir)
        / "selected_traces"
        / (selection.scenario_id or "unknown")
        / (selection.trial_label or "trace")
        / "playwright_replay_plan.json"
    )
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(plan_payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return relative_path.as_posix()


def _operator_config_from_selection(
    config: AutonomousBrowserLiveLoopPlaywrightReplayConfig,
    selection: _ReplayTraceSelection,
    replay_plan_path: str,
) -> dict[str, Any]:
    return {
        "schema_version": PLAYWRIGHT_OPERATOR_CONFIG_SCHEMA_VERSION,
        "replay_backend": config.replay_backend,
        "replay_plan_path": replay_plan_path,
        "output_dir": f"{config.output_dir}/selected_traces/{selection.scenario_id or 'unknown'}/{selection.trial_label or 'trace'}",
        "allowed_hosts": [host for host in config.allowed_hosts if host in PLAYWRIGHT_ALLOWED_BROWSER_HOSTS],
        "fixture_scope": "local_only",
        "headless": config.headless,
        "timeout_ms": config.timeout_ms,
        "limitations": list(config.limitations),
    }


def _write_operator_config(
    repo_root: Path,
    output_dir: str,
    selection: _ReplayTraceSelection,
    config_payload: Mapping[str, Any],
) -> str:
    relative_path = (
        Path(output_dir)
        / "selected_traces"
        / (selection.scenario_id or "unknown")
        / (selection.trial_label or "trace")
        / "playwright_replay_operator_config.json"
    )
    path = repo_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(config_payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return relative_path.as_posix()


def _write_operator_config_from_selection(
    repo_root: Path,
    output_dir: str,
    selection: _ReplayTraceSelection,
    config: AutonomousBrowserLiveLoopPlaywrightReplayConfig,
    replay_plan_path: str,
) -> tuple[str, dict[str, Any]]:
    config_payload = _operator_config_from_selection(config, selection, replay_plan_path)
    relative_path = _write_operator_config(repo_root, output_dir, selection, config_payload)
    return relative_path, config_payload


def _trace_is_successful(trace_payload: Mapping[str, Any]) -> bool:
    trace_entries = _trace_entries(trace_payload)
    if not trace_entries:
        return False
    last = trace_entries[-1]
    if not isinstance(last, Mapping):
        return False
    metadata = last.get("metadata")
    if isinstance(metadata, Mapping) and bool(metadata.get("goal_satisfied")):
        return True
    expected_result = last.get("expected_result")
    if isinstance(expected_result, Mapping) and bool(expected_result.get("passed")):
        return True
    return False


def _trace_entries(trace_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    trace = trace_payload.get("trace")
    if isinstance(trace, list):
        return [dict(item) for item in trace if isinstance(item, Mapping)]
    runtime_trace = trace_payload.get("runtime_trace")
    if isinstance(runtime_trace, list):
        return [dict(item) for item in runtime_trace if isinstance(item, Mapping)]
    return []


def _selected_trace_actions(trace_payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for entry in _trace_entries(trace_payload):
        if str(entry.get("fixture_execution_status")) != "succeeded":
            continue
        if str(entry.get("validation_status")) not in {"accepted", "skipped"}:
            continue
        planner_action = _trace_action_record(entry)
        if not isinstance(planner_action, Mapping):
            continue
        action_name = _action_name_from_mapping(planner_action)
        if action_name not in SUPPORTED_REPLAY_ACTIONS:
            continue
        action_result = entry.get("action_result")
        if isinstance(action_result, Mapping):
            output = action_result.get("output")
            observation = action_result.get("observation")
            if isinstance(observation, Mapping):
                current_url = _optional_text(observation.get("current_url"))
            else:
                current_url = None
            if isinstance(output, Mapping):
                output_url = _optional_text(output.get("current_url"))
            else:
                output_url = None
        else:
            current_url = None
            output_url = None
        if current_url is None and output_url is None and action_name == "browser_open_url":
            current_url = _optional_text(_action_parameters_from_mapping(planner_action).get("url"))
        actions.append(
            {
                "action_name": action_name,
                "parameters": _action_parameters_from_mapping(planner_action),
                "planner_action": dict(planner_action),
                "action_result": dict(action_result) if isinstance(action_result, Mapping) else {},
                "current_url": current_url or output_url,
                "expected_result": dict(entry.get("expected_result")) if isinstance(entry.get("expected_result"), Mapping) else {},
                "metadata": dict(entry.get("metadata")) if isinstance(entry.get("metadata"), Mapping) else {},
            }
        )
    return actions


def _expected_results_passed_from_trace(trace_payload: Mapping[str, Any]) -> int:
    return sum(1 for entry in _selected_trace_actions(trace_payload) if bool(entry.get("expected_result", {}).get("passed", True)))


def _expected_results_failed_from_trace(trace_payload: Mapping[str, Any]) -> int:
    return sum(1 for entry in _selected_trace_actions(trace_payload) if not bool(entry.get("expected_result", {}).get("passed", True)))


def _final_trace_url(trace_payload: Mapping[str, Any]) -> str | None:
    actions = _selected_trace_actions(trace_payload)
    if not actions:
        return None
    return _optional_text(actions[-1].get("current_url"))


def _matched_url_from_trace(trace_payload: Mapping[str, Any]) -> str | None:
    trace_entries = _trace_entries(trace_payload)
    if not trace_entries:
        return None
    last = trace_entries[-1]
    metadata = last.get("metadata")
    if isinstance(metadata, Mapping):
        matched = metadata.get("matched_completion_criteria")
        if isinstance(matched, Mapping):
            matched_url = _optional_text(matched.get("matched_url"))
            if matched_url:
                return matched_url
    return _final_trace_url(trace_payload)


def _load_trace_payload(path: Path, *, display_path: str | None = None) -> tuple[dict[str, Any] | None, dict[str, Any] | None]:
    try:
        payload = _load_json_payload(path)
    except OSError:
        return None, {"error_code": "trace_not_found", "diagnostics": {"source_trace_path": display_path or _safe_relative_path(path, "source_trace_path")}}
    except json.JSONDecodeError:
        return None, {"error_code": "trace_json_malformed", "diagnostics": {"source_trace_path": display_path or _safe_relative_path(path, "source_trace_path")}}
    if not isinstance(payload, dict):
        return None, {"error_code": "trace_root_invalid", "diagnostics": {"source_trace_path": display_path or _safe_relative_path(path, "source_trace_path")}}
    return dict(payload), None


def _load_json_payload(config_artifact: str | Path | Mapping[str, Any]) -> Any:
    if isinstance(config_artifact, Mapping):
        return dict(config_artifact)
    path = Path(config_artifact)
    return _json_loads_with_common_encodings(path.read_bytes(), source=path.as_posix())


_COMMON_JSON_ENCODINGS = ("utf-8-sig", "utf-8", "utf-16", "utf-16-le", "utf-16-be")


def _json_loads_with_common_encodings(data: bytes, *, source: str) -> Any:
    last_error: Exception | None = None
    for encoding in _COMMON_JSON_ENCODINGS:
        try:
            text = data.decode(encoding)
        except UnicodeDecodeError as exc:
            last_error = exc
            continue
        try:
            return json.loads(text)
        except json.JSONDecodeError as exc:
            last_error = exc
            continue
    if isinstance(last_error, json.JSONDecodeError):
        raise last_error
    if isinstance(last_error, UnicodeDecodeError):
        raise json.JSONDecodeError(f"{source} JSON is not encoded as a supported UTF-8/UTF-16 text file.", "", 0)
    raise json.JSONDecodeError(f"{source} JSON could not be parsed.", "", 0)


def _config_from_mapping(payload: Mapping[str, Any]) -> AutonomousBrowserLiveLoopPlaywrightReplayConfig:
    schema_version = _optional_text(payload.get("schema_version"))
    suite_id = _safe_identifier(payload.get("suite_id"), "suite_id")
    input_variance_suite_summary = _safe_relative_path(payload.get("input_variance_suite_summary"), "input_variance_suite_summary")
    input_trace_root = _safe_relative_path(payload.get("input_trace_root"), "input_trace_root")
    input_trace_paths_value = payload.get("input_trace_paths", [])
    scenario_ids_value = payload.get("scenario_ids", [])
    trial_selection = _optional_text(payload.get("trial_selection")) or "first_success_per_scenario"
    replay_backend = str(payload.get("replay_backend", "playwright")).strip().lower() or "playwright"
    allow_real_browser = bool(payload.get("allow_real_browser", False))
    allow_playwright = bool(payload.get("allow_playwright", False))
    require_explicit_allow_real_browser = bool(payload.get("require_explicit_allow_real_browser", True))
    require_explicit_allow_playwright = bool(payload.get("require_explicit_allow_playwright", True))
    fixture_only = bool(payload.get("fixture_only", True))
    fixture_manifest_path = _safe_relative_path(payload.get("fixture_manifest_path", DEFAULT_FIXTURE_MANIFEST_PATH), "fixture_manifest_path")
    allowed_hosts = _safe_host_list(payload.get("allowed_hosts", list(DEFAULT_ALLOWED_HOSTS)))
    real_network_traffic_allowed = bool(payload.get("real_network_traffic_allowed", False))
    headless = bool(payload.get("headless", True))
    timeout_ms = payload.get("timeout_ms", 30_000)
    output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir")
    limitations = tuple(
        str(item).strip()
        for item in payload.get("limitations", [])
        if isinstance(item, str) and item.strip()
    )

    if schema_version != CONFIG_SCHEMA_VERSION or suite_id is None or fixture_manifest_path is None or output_dir is None:
        raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError("playwright replay config validation failed.")
    if replay_backend not in SUPPORTED_REPLAY_BACKENDS:
        raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError("replay_backend must be fixture or playwright.")
    if trial_selection not in SUPPORTED_TRIAL_SELECTIONS:
        raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError("trial_selection must be first_success_per_scenario or all_successful_trials.")
    if not isinstance(timeout_ms, int) or isinstance(timeout_ms, bool) or timeout_ms <= 0:
        raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError("timeout_ms must be a positive integer.")
    if not isinstance(input_trace_paths_value, list):
        raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError("input_trace_paths must be a list.")
    if not isinstance(scenario_ids_value, list) or not scenario_ids_value:
        raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError("scenario_ids must be a non-empty list.")

    input_trace_paths: list[str] = []
    for index, item in enumerate(input_trace_paths_value):
        relative = _safe_relative_path(item, f"input_trace_paths[{index}]")
        if relative is None:
            raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError(
                f"input_trace_paths[{index}] must be a safe relative path."
            )
        input_trace_paths.append(relative)

    scenario_ids: list[str] = []
    for index, item in enumerate(scenario_ids_value):
        identifier = _safe_identifier(item, f"scenario_ids[{index}]")
        if identifier is None:
            raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError(
                f"scenario_ids[{index}] must be a safe identifier."
            )
        scenario_ids.append(identifier)

    return AutonomousBrowserLiveLoopPlaywrightReplayConfig(
        schema_version=schema_version or "",
        suite_id=suite_id,
        input_variance_suite_summary=input_variance_suite_summary,
        input_trace_root=input_trace_root,
        input_trace_paths=tuple(input_trace_paths),
        scenario_ids=tuple(scenario_ids),
        trial_selection=trial_selection,
        replay_backend=replay_backend,
        allow_real_browser=allow_real_browser,
        allow_playwright=allow_playwright,
        require_explicit_allow_real_browser=require_explicit_allow_real_browser,
        require_explicit_allow_playwright=require_explicit_allow_playwright,
        fixture_only=fixture_only,
        fixture_manifest_path=fixture_manifest_path,
        allowed_hosts=allowed_hosts,
        real_network_traffic_allowed=real_network_traffic_allowed,
        headless=headless,
        timeout_ms=timeout_ms,
        output_dir=output_dir,
        limitations=limitations,
    )


def _validate_config(
    config: AutonomousBrowserLiveLoopPlaywrightReplayConfig,
    *,
    replay_backend: str,
) -> str | None:
    if config.schema_version != CONFIG_SCHEMA_VERSION:
        return "config_validation_failed"
    if replay_backend not in SUPPORTED_REPLAY_BACKENDS:
        return "unknown_replay_backend"
    if config.trial_selection not in SUPPORTED_TRIAL_SELECTIONS:
        return "config_validation_failed"
    if not config.suite_id:
        return "config_validation_failed"
    if not config.scenario_ids:
        return "config_validation_failed"
    if not config.allowed_hosts:
        return "config_validation_failed"
    if not config.fixture_manifest_path:
        return "config_validation_failed"
    if not config.output_dir:
        return "config_validation_failed"
    if config.timeout_ms <= 0:
        return "config_validation_failed"
    if replay_backend == "playwright" and config.fixture_only and not config.allow_playwright:
        return None
    return None


def _resolve_replay_backend(config_backend: str, override_backend: str | None) -> str | None:
    if override_backend is not None:
        backend = _safe_backend_value(override_backend)
        if backend not in SUPPORTED_REPLAY_BACKENDS:
            return None
        return backend
    backend = _safe_backend_value(config_backend)
    if backend is None:
        return None
    if backend not in SUPPORTED_REPLAY_BACKENDS:
        return None
    return backend


def _failure_summary(
    *,
    status: str,
    error_code: str,
    suite_id: str | None,
    replay_backend: str | None,
    input_trace_count: int,
    limitations: tuple[str, ...],
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    summary = AutonomousBrowserLiveLoopPlaywrightReplaySummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        suite_id=suite_id,
        status=status,
        error_code=error_code,
        replay_backend=replay_backend,
        input_trace_count=input_trace_count,
        selected_trace_count=0,
        scenarios_total=0,
        traces_replayed=0,
        traces_succeeded=0,
        traces_failed=0,
        traces_rejected=0,
        actions_attempted_total=0,
        actions_succeeded_total=0,
        actions_failed_total=0,
        expected_results_passed_total=0,
        expected_results_failed_total=0,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        real_network_traffic=False,
        fixture_only=True,
        allow_real_browser=False,
        allow_playwright=False,
        no_runtime_execution=True,
        model_execution=False,
        output_dir=None,
        limitations=limitations,
        scenario_summaries=(),
        replay_trace_summaries=(),
    )
    payload = summary.to_dict()
    if diagnostics is not None:
        payload["diagnostics"] = _jsonable(diagnostics)
    return payload


def _refused_summary(
    *,
    error_code: str,
    config: AutonomousBrowserLiveLoopPlaywrightReplayConfig,
    replay_backend: str,
    input_trace_count: int,
) -> dict[str, Any]:
    return _failure_summary(
        status="refused",
        error_code=error_code,
        suite_id=config.suite_id,
        replay_backend=replay_backend,
        input_trace_count=input_trace_count,
        limitations=config.limitations,
    )


def _write_summary_if_needed(summary: Mapping[str, Any], repo_root: Path, output_dir: str, *, should_write: bool) -> None:
    if not should_write:
        return
    write_autonomous_browser_live_loop_playwright_replay_summary(summary, repo_root / output_dir)


def _safe_backend_value(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    backend = value.strip().lower()
    return backend or None


def _safe_relative_path(value: Any, label: str) -> str | None:
    if value is None:
        return None
    if isinstance(value, Path):
        text = value.as_posix()
    else:
        text = str(value).strip()
    if not text:
        return None
    path = Path(text)
    if path.is_absolute() or text.startswith("..") or "\\.." in text or "/.." in text or text.startswith("\\\\"):
        return None
    if text.startswith("file://"):
        return None
    return path.as_posix()


def _safe_identifier(value: Any, label: str) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if any(ch in text for ch in ("\\", "/", ":", "\0")):
        return None
    return text


def _safe_host_list(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list):
        raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError("allowed_hosts must be a list.")
    hosts: list[str] = []
    for item in value:
        if not isinstance(item, str):
            raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError("allowed_hosts must contain strings.")
        host = item.strip().lower()
        if not host:
            raise AutonomousBrowserLiveLoopPlaywrightReplayConfigError("allowed_hosts must contain non-empty strings.")
        hosts.append(host)
    return tuple(hosts)


def _optional_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set):
        return [_jsonable(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _unique_append(values: tuple[str, ...], candidate: str | None) -> tuple[str, ...]:
    if candidate is None:
        return values
    if candidate in values:
        return values
    return values + (candidate,)


def _plan_id_for_selection(selection: _ReplayTraceSelection) -> str:
    scenario = selection.scenario_id or "unknown"
    trial = selection.trial_label or "trace"
    return f"live_loop_playwright_replay_{scenario}_{trial}"


def _trial_label_from_path(relative_path: str) -> str | None:
    path = Path(relative_path)
    parent = path.parent.name
    if parent.startswith("trial_"):
        return parent
    return None


def _trial_index_from_path(relative_path: str) -> int | None:
    label = _trial_label_from_path(relative_path)
    if label is None:
        return None
    try:
        return int(label.removeprefix("trial_"))
    except ValueError:
        return None


class AutonomousBrowserLiveLoopPlaywrightReplayConfigError(ValueError):
    pass
