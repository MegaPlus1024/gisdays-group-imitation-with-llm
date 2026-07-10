from __future__ import annotations

import hashlib
import json
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_live_loop import (
    AutonomousBrowserLiveLoopConfigError,
    _optional_text,
    _required_identifier,
    _safe_endpoint_base_url,
    _safe_relative_path,
    _string_list,
    load_autonomous_browser_live_loop_config,
    run_autonomous_browser_live_loop,
    write_autonomous_browser_live_loop_trace,
)


CONFIG_SCHEMA_VERSION = "autonomous_browser_live_loop_variance_suite_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_live_loop_variance_suite_summary_v1"
DEFAULT_SUITE_ID = "phase_13c_guarded_local_model_live_loop_variance"
DEFAULT_BASE_LIVE_LOOP_CONFIG = "configs/autonomous_runtime/browser_live_loop_local_model.example.json"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/live_loop_variance_suite"
DEFAULT_PLANNER_BACKEND = "local_model"
DEFAULT_MODEL_ALIAS = "third_model"
DEFAULT_MODEL_ENDPOINT = "http://127.0.0.1:8082/v1/chat/completions"
DEFAULT_TRIAL_COUNT_PER_SCENARIO = 3
DEFAULT_TRIAL_LABEL_PREFIX = "trial"
DEFAULT_SCENARIO_IDS = (
    "hard_policy_disambiguation",
    "hard_ticket_priority_crosscheck",
    "hard_approval_policy_match",
)
ALLOWED_PLANNER_BACKENDS = ("local_model",)


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopVarianceSuiteConfig:
    schema_version: str
    suite_id: str
    base_live_loop_config: str
    planner_backend: str
    model_alias: str
    model_endpoint: str
    trial_count_per_scenario: int
    scenario_ids: tuple[str, ...]
    output_dir: str
    allow_model_calls: bool
    require_explicit_allow_model_calls: bool
    no_real_browser: bool
    no_playwright: bool
    trial_label_prefix: str = DEFAULT_TRIAL_LABEL_PREFIX
    limitations: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AutonomousBrowserLiveLoopVarianceSuiteConfig:
        schema_version = str(payload.get("schema_version", "")).strip()
        suite_id = _required_identifier(payload.get("suite_id"), "suite_id")
        base_live_loop_config = _safe_relative_path(
            payload.get("base_live_loop_config", DEFAULT_BASE_LIVE_LOOP_CONFIG),
            "base_live_loop_config",
        )
        if base_live_loop_config is None:
            raise AutonomousBrowserLiveLoopConfigError("base_live_loop_config must be a safe relative path.")
        planner_backend = str(payload.get("planner_backend", DEFAULT_PLANNER_BACKEND)).strip().lower() or DEFAULT_PLANNER_BACKEND
        model_alias = _required_identifier(payload.get("model_alias", DEFAULT_MODEL_ALIAS), "model_alias")
        model_endpoint = _safe_endpoint_base_url(payload.get("model_endpoint", DEFAULT_MODEL_ENDPOINT))
        if model_endpoint is None:
            raise AutonomousBrowserLiveLoopConfigError("model_endpoint must be a safe endpoint URL.")
        trial_count_per_scenario = _int(payload.get("trial_count_per_scenario", DEFAULT_TRIAL_COUNT_PER_SCENARIO))
        if trial_count_per_scenario <= 0:
            raise AutonomousBrowserLiveLoopConfigError("trial_count_per_scenario must be a positive integer.")
        scenario_ids = tuple(_string_list(payload.get("scenario_ids", list(DEFAULT_SCENARIO_IDS)), "scenario_ids"))
        if not scenario_ids:
            raise AutonomousBrowserLiveLoopConfigError("scenario_ids must be a non-empty list.")
        if len(set(scenario_ids)) != len(scenario_ids):
            raise AutonomousBrowserLiveLoopConfigError("scenario_ids must not contain duplicates.")
        output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir")
        if output_dir is None:
            raise AutonomousBrowserLiveLoopConfigError("output_dir must be a safe relative path.")
        allow_model_calls = payload.get("allow_model_calls", False)
        require_explicit_allow_model_calls = payload.get("require_explicit_allow_model_calls", True)
        no_real_browser = payload.get("no_real_browser", True)
        no_playwright = payload.get("no_playwright", True)
        if not isinstance(allow_model_calls, bool):
            raise AutonomousBrowserLiveLoopConfigError("allow_model_calls must be a boolean.")
        if not isinstance(require_explicit_allow_model_calls, bool):
            raise AutonomousBrowserLiveLoopConfigError("require_explicit_allow_model_calls must be a boolean.")
        if not isinstance(no_real_browser, bool):
            raise AutonomousBrowserLiveLoopConfigError("no_real_browser must be a boolean.")
        if not isinstance(no_playwright, bool):
            raise AutonomousBrowserLiveLoopConfigError("no_playwright must be a boolean.")
        trial_label_prefix = _required_identifier(payload.get("trial_label_prefix", DEFAULT_TRIAL_LABEL_PREFIX), "trial_label_prefix")
        limitations = tuple(
            str(item).strip()
            for item in payload.get("limitations", [])
            if isinstance(item, str) and item.strip()
        )
        metadata = _dict(payload.get("metadata", {}), "metadata")
        if planner_backend not in ALLOWED_PLANNER_BACKENDS:
            raise AutonomousBrowserLiveLoopConfigError(
                f"planner_backend must be one of: {', '.join(ALLOWED_PLANNER_BACKENDS)}."
            )
        return cls(
            schema_version=schema_version,
            suite_id=suite_id,
            base_live_loop_config=base_live_loop_config,
            planner_backend=planner_backend,
            model_alias=model_alias,
            model_endpoint=model_endpoint,
            trial_count_per_scenario=trial_count_per_scenario,
            scenario_ids=scenario_ids,
            output_dir=output_dir,
            allow_model_calls=allow_model_calls,
            require_explicit_allow_model_calls=require_explicit_allow_model_calls,
            no_real_browser=no_real_browser,
            no_playwright=no_playwright,
            trial_label_prefix=trial_label_prefix,
            limitations=limitations,
            metadata=metadata,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "suite_id": self.suite_id,
            "base_live_loop_config": self.base_live_loop_config,
            "planner_backend": self.planner_backend,
            "model_alias": self.model_alias,
            "model_endpoint": self.model_endpoint,
            "trial_count_per_scenario": self.trial_count_per_scenario,
            "scenario_ids": list(self.scenario_ids),
            "output_dir": self.output_dir,
            "allow_model_calls": self.allow_model_calls,
            "require_explicit_allow_model_calls": self.require_explicit_allow_model_calls,
            "no_real_browser": self.no_real_browser,
            "no_playwright": self.no_playwright,
            "trial_label_prefix": self.trial_label_prefix,
            "limitations": list(self.limitations),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopVarianceTrialSummary:
    scenario_id: str
    trial_index: int
    trial_label: str
    status: str
    stop_reason: str | None
    error_code: str | None
    actions_succeeded: int
    actions_attempted: int
    actions_failed: int
    expected_results_passed: int
    expected_results_failed: int
    repair_attempts_total: int
    repair_attempts_succeeded_total: int
    repair_attempts_failed_total: int
    original_error_code: str | None
    last_error_code: str | None
    matched_url: str | None
    matched_completion_criteria_scenario: str | None
    goal_satisfied: bool
    route_sequence: tuple[str, ...] = ()
    route_fingerprint: str | None = None
    trace_path: str | None = None
    model_execution: bool = False
    real_browser_execution: bool = False
    playwright_execution: bool = False
    browser_opened: bool = False
    no_runtime_execution: bool = True
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "trial_index": self.trial_index,
            "trial_label": self.trial_label,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "error_code": self.error_code,
            "actions_succeeded": self.actions_succeeded,
            "actions_attempted": self.actions_attempted,
            "actions_failed": self.actions_failed,
            "expected_results_passed": self.expected_results_passed,
            "expected_results_failed": self.expected_results_failed,
            "repair_attempts_total": self.repair_attempts_total,
            "repair_attempts_succeeded_total": self.repair_attempts_succeeded_total,
            "repair_attempts_failed_total": self.repair_attempts_failed_total,
            "original_error_code": self.original_error_code,
            "last_error_code": self.last_error_code,
            "matched_url": self.matched_url,
            "matched_completion_criteria_scenario": self.matched_completion_criteria_scenario,
            "goal_satisfied": self.goal_satisfied,
            "route_sequence": list(self.route_sequence),
            "route_fingerprint": self.route_fingerprint,
            "trace_path": self.trace_path,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "no_runtime_execution": self.no_runtime_execution,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopVarianceScenarioSummary:
    scenario_id: str
    trials_total: int
    trials_succeeded: int
    trials_failed: int
    trials_rejected: int
    pass_rate: float
    actions_attempted_total: int
    actions_succeeded_total: int
    actions_failed_total: int
    expected_results_passed_total: int
    expected_results_failed_total: int
    repair_attempts_total: int
    repair_attempts_succeeded_total: int
    repair_attempts_failed_total: int
    matched_urls: tuple[str, ...] = ()
    error_codes: tuple[str, ...] = ()
    stop_reasons: tuple[str, ...] = ()
    unique_route_fingerprints: tuple[str, ...] = ()
    unique_matched_urls: tuple[str, ...] = ()
    route_stable: bool = False
    matched_url_stable: bool = False
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "trials_total": self.trials_total,
            "trials_succeeded": self.trials_succeeded,
            "trials_failed": self.trials_failed,
            "trials_rejected": self.trials_rejected,
            "pass_rate": self.pass_rate,
            "actions_attempted_total": self.actions_attempted_total,
            "actions_succeeded_total": self.actions_succeeded_total,
            "actions_failed_total": self.actions_failed_total,
            "expected_results_passed_total": self.expected_results_passed_total,
            "expected_results_failed_total": self.expected_results_failed_total,
            "repair_attempts_total": self.repair_attempts_total,
            "repair_attempts_succeeded_total": self.repair_attempts_succeeded_total,
            "repair_attempts_failed_total": self.repair_attempts_failed_total,
            "matched_urls": list(self.matched_urls),
            "error_codes": list(self.error_codes),
            "stop_reasons": list(self.stop_reasons),
            "unique_route_fingerprints": list(self.unique_route_fingerprints),
            "unique_matched_urls": list(self.unique_matched_urls),
            "route_stable": self.route_stable,
            "matched_url_stable": self.matched_url_stable,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class AutonomousBrowserLiveLoopVarianceSuiteSummary:
    schema_version: str
    status: str
    error_code: str | None
    suite_id: str
    model_alias: str
    planner_backend: str
    trial_count_per_scenario: int
    scenarios_total: int
    trials_total: int
    trials_succeeded: int
    trials_failed: int
    trials_rejected: int
    pass_rate_overall: float
    model_execution_attempted: bool
    model_execution_completed: bool
    real_browser_execution: bool
    playwright_execution: bool
    browser_opened: bool
    no_runtime_execution: bool
    allow_model_calls: bool
    limitations: tuple[str, ...] = ()
    scenario_summaries: tuple[dict[str, Any], ...] = ()
    trial_summaries: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "suite_id": self.suite_id,
            "model_alias": self.model_alias,
            "planner_backend": self.planner_backend,
            "trial_count_per_scenario": self.trial_count_per_scenario,
            "scenarios_total": self.scenarios_total,
            "trials_total": self.trials_total,
            "trials_succeeded": self.trials_succeeded,
            "trials_failed": self.trials_failed,
            "trials_rejected": self.trials_rejected,
            "pass_rate_overall": self.pass_rate_overall,
            "model_execution_attempted": self.model_execution_attempted,
            "model_execution_completed": self.model_execution_completed,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "no_runtime_execution": self.no_runtime_execution,
            "allow_model_calls": self.allow_model_calls,
            "limitations": list(self.limitations),
            "scenario_summaries": [dict(item) for item in self.scenario_summaries],
            "trial_summaries": [dict(item) for item in self.trial_summaries],
        }


def load_autonomous_browser_live_loop_variance_suite_config(
    config_artifact: str | Path | Mapping[str, Any],
) -> AutonomousBrowserLiveLoopVarianceSuiteConfig:
    try:
        payload = _load_json_payload(config_artifact)
    except OSError as exc:
        raise AutonomousBrowserLiveLoopConfigError("live loop variance suite config could not be read.") from exc
    except json.JSONDecodeError as exc:
        raise AutonomousBrowserLiveLoopConfigError("live loop variance suite config JSON is malformed.") from exc
    if not isinstance(payload, dict):
        raise AutonomousBrowserLiveLoopConfigError("live loop variance suite config root must be a JSON object.")
    return AutonomousBrowserLiveLoopVarianceSuiteConfig.from_dict(payload)


def run_autonomous_browser_live_loop_variance_suite(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    model_client_factory: Callable[[str, int, Mapping[str, Any]], Any] | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    try:
        config = load_autonomous_browser_live_loop_variance_suite_config(config_artifact)
    except AutonomousBrowserLiveLoopConfigError as exc:
        return _suite_failure(
            suite_id=None,
            model_alias=None,
            planner_backend=DEFAULT_PLANNER_BACKEND,
            trial_count_per_scenario=DEFAULT_TRIAL_COUNT_PER_SCENARIO,
            scenarios_total=0,
            error_code="config_validation_failed",
            error_message=str(exc),
            allow_model_calls=False,
            limitations=(),
        )

    base_config_path = _resolve_repo_path(config.base_live_loop_config, repo)
    try:
        base_live_loop_config = load_autonomous_browser_live_loop_config(base_config_path)
    except AutonomousBrowserLiveLoopConfigError as exc:
        return _suite_failure(
            suite_id=config.suite_id,
            model_alias=config.model_alias,
            planner_backend=config.planner_backend,
            trial_count_per_scenario=config.trial_count_per_scenario,
            scenarios_total=len(config.scenario_ids),
            error_code="config_validation_failed",
            error_message=str(exc),
            allow_model_calls=config.allow_model_calls,
            limitations=config.limitations or _limitations(),
        )

    if config.planner_backend == "local_model" and not config.allow_model_calls:
        return _suite_refusal(
            suite_id=config.suite_id,
            model_alias=config.model_alias,
            planner_backend=config.planner_backend,
            trial_count_per_scenario=config.trial_count_per_scenario,
            scenarios_total=len(config.scenario_ids),
            allow_model_calls=config.allow_model_calls,
            limitations=config.limitations or _limitations(),
        )

    trial_summaries: list[dict[str, Any]] = []
    scenario_groups: dict[str, dict[str, Any]] = {}
    any_trial_executed = False

    for scenario_id in config.scenario_ids:
        scenario_groups[scenario_id] = _empty_scenario_group(scenario_id, config.limitations or _limitations())
        for trial_index in range(1, config.trial_count_per_scenario + 1):
            trial_label = f"{config.trial_label_prefix}_{trial_index:02d}"
            trial_output_dir = f"{config.output_dir}/{scenario_id}/{trial_label}"
            trial_config = dict(base_live_loop_config.to_dict())
            trial_config["scenario_id"] = scenario_id
            trial_config["output_dir"] = trial_output_dir
            trial_config.setdefault("planner_backend", {})
            trial_planner_backend = dict(trial_config["planner_backend"])
            trial_planner_backend["kind"] = config.planner_backend
            trial_planner_backend["model_alias"] = config.model_alias
            trial_planner_backend["model_endpoint"] = config.model_endpoint
            trial_planner_backend["allow_model_calls"] = config.allow_model_calls
            trial_config["planner_backend"] = trial_planner_backend

            model_client = None
            if model_client_factory is not None:
                model_client = model_client_factory(scenario_id, trial_index, trial_config)

            trial_result = run_autonomous_browser_live_loop(
                trial_config,
                repo_root=repo,
                model_client=model_client,
            )
            any_trial_executed = True
            write_autonomous_browser_live_loop_trace(trial_result, repo / trial_output_dir)
            trial_summary = _normalize_trial_summary(
                trial_result,
                scenario_id=scenario_id,
                trial_index=trial_index,
                trial_label=trial_label,
                limitations=config.limitations or _limitations(),
            )
            trial_summaries.append(trial_summary)
            _update_scenario_group(scenario_groups[scenario_id], trial_summary)

    scenario_summaries = tuple(
        _finalize_scenario_summary(group, limitations=config.limitations or _limitations()).to_dict()
        for group in scenario_groups.values()
    )

    status, error_code = _finalize_suite_status(trial_summaries)
    summary = AutonomousBrowserLiveLoopVarianceSuiteSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        suite_id=config.suite_id,
        model_alias=config.model_alias,
        planner_backend=config.planner_backend,
        trial_count_per_scenario=config.trial_count_per_scenario,
        scenarios_total=len(config.scenario_ids),
        trials_total=len(trial_summaries),
        trials_succeeded=sum(1 for item in trial_summaries if item["status"] == "succeeded"),
        trials_failed=sum(1 for item in trial_summaries if item["status"] == "failed"),
        trials_rejected=sum(1 for item in trial_summaries if item["status"] in {"rejected", "refused"}),
        pass_rate_overall=_safe_ratio(
            sum(1 for item in trial_summaries if item["status"] == "succeeded"),
            len(trial_summaries),
        ),
        model_execution_attempted=any_trial_executed and any(bool(item.get("model_execution")) for item in trial_summaries),
        model_execution_completed=any_trial_executed and any(bool(item.get("model_execution")) for item in trial_summaries),
        real_browser_execution=any(bool(item.get("real_browser_execution")) for item in trial_summaries),
        playwright_execution=any(bool(item.get("playwright_execution")) for item in trial_summaries),
        browser_opened=any(bool(item.get("browser_opened")) for item in trial_summaries),
        no_runtime_execution=True,
        allow_model_calls=config.allow_model_calls,
        limitations=config.limitations or _limitations(),
        scenario_summaries=scenario_summaries,
        trial_summaries=tuple(trial_summaries),
    )
    payload = summary.to_dict()
    if status != "refused":
        write_autonomous_browser_live_loop_variance_suite_summary(payload, repo / config.output_dir)
    return payload


def write_autonomous_browser_live_loop_variance_suite_summary(summary: Mapping[str, Any], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_live_loop_variance_suite_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _normalize_trial_summary(
    trial_result: Mapping[str, Any],
    *,
    scenario_id: str,
    trial_index: int,
    trial_label: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    runtime_trace = trial_result.get("runtime_trace")
    route_sequence = _route_sequence_from_trace(runtime_trace if isinstance(runtime_trace, list) else [])
    route_fingerprint = _route_fingerprint(scenario_id, route_sequence)
    matched_completion_criteria = _matched_completion_criteria(trial_result)
    matched_completion_criteria_scenario = None
    matched_url = None
    goal_satisfied = bool(trial_result.get("stop_reason") == "goal_satisfied")
    if isinstance(matched_completion_criteria, Mapping):
        matched_completion_criteria_scenario = _optional_text(matched_completion_criteria.get("scenario_id"))
        matched_url = _optional_text(matched_completion_criteria.get("matched_url"))
    elif goal_satisfied:
        matched_url = _optional_text(trial_result.get("matched_url"))
    last_error_code = _last_trace_error_code(runtime_trace)
    original_error_code, repair_attempts_total, repair_attempts_succeeded_total, repair_attempts_failed_total = _repair_stats_from_trial(trial_result)
    return AutonomousBrowserLiveLoopVarianceTrialSummary(
        scenario_id=scenario_id,
        trial_index=trial_index,
        trial_label=trial_label,
        status=str(trial_result.get("status") or "failed"),
        stop_reason=_optional_text(trial_result.get("stop_reason")),
        error_code=_optional_text(trial_result.get("error_code")),
        actions_succeeded=_int(trial_result.get("actions_succeeded")),
        actions_attempted=_int(trial_result.get("actions_attempted")),
        actions_failed=_int(trial_result.get("actions_failed")),
        expected_results_passed=_int(trial_result.get("expected_results_passed")),
        expected_results_failed=_int(trial_result.get("expected_results_failed")),
        repair_attempts_total=repair_attempts_total,
        repair_attempts_succeeded_total=repair_attempts_succeeded_total,
        repair_attempts_failed_total=repair_attempts_failed_total,
        original_error_code=original_error_code,
        last_error_code=last_error_code,
        matched_url=matched_url,
        matched_completion_criteria_scenario=matched_completion_criteria_scenario,
        goal_satisfied=goal_satisfied,
        route_sequence=route_sequence,
        route_fingerprint=route_fingerprint,
        trace_path=_optional_text(trial_result.get("trace_path")),
        model_execution=bool(trial_result.get("model_execution")),
        real_browser_execution=bool(trial_result.get("real_browser_execution")),
        playwright_execution=bool(trial_result.get("playwright_execution")),
        browser_opened=bool(trial_result.get("browser_opened")),
        no_runtime_execution=bool(trial_result.get("no_runtime_execution", True)),
        limitations=limitations,
    ).to_dict()


def _route_sequence_from_trace(runtime_trace: list[Any]) -> tuple[str, ...]:
    sequence: list[str] = []
    for entry in runtime_trace:
        if not isinstance(entry, Mapping):
            continue
        planner_action = entry.get("planner_action")
        if not isinstance(planner_action, Mapping):
            continue
        action_name = _optional_text(planner_action.get("action_name")) or "unknown"
        parameters = planner_action.get("parameters")
        target_text = None
        if isinstance(parameters, Mapping):
            target_text = _optional_text(parameters.get("target_text")) or _optional_text(parameters.get("text"))
            url = _optional_text(parameters.get("url"))
        else:
            url = None
        action_result = entry.get("action_result")
        current_url = None
        if isinstance(action_result, Mapping):
            observation = action_result.get("observation")
            if isinstance(observation, Mapping):
                current_url = _optional_text(observation.get("current_url"))
        if action_name == "browser_click":
            sequence.append(f"{action_name}:{target_text or ''}->{current_url or ''}")
        elif action_name == "browser_open_url":
            sequence.append(f"{action_name}:{url or ''}->{current_url or ''}")
        else:
            sequence.append(f"{action_name}:{current_url or target_text or url or ''}")
    return tuple(sequence)


def _route_fingerprint(scenario_id: str, route_sequence: tuple[str, ...]) -> str | None:
    if not route_sequence:
        return None
    payload = json.dumps([scenario_id, *route_sequence], ensure_ascii=False, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _matched_completion_criteria(trial_result: Mapping[str, Any]) -> Mapping[str, Any] | None:
    trace = trial_result.get("runtime_trace")
    if not isinstance(trace, list) or not trace:
        return None
    last = trace[-1]
    if not isinstance(last, Mapping):
        return None
    metadata = last.get("metadata")
    if not isinstance(metadata, Mapping):
        return None
    matched = metadata.get("matched_completion_criteria")
    return matched if isinstance(matched, Mapping) else None


def _last_trace_error_code(runtime_trace: Any) -> str | None:
    if not isinstance(runtime_trace, list) or not runtime_trace:
        return None
    last = runtime_trace[-1]
    if not isinstance(last, Mapping):
        return None
    return _optional_text(last.get("error_code"))


def _repair_stats_from_trial(trial_result: Mapping[str, Any]) -> tuple[str | None, int, int, int]:
    planner_backend = trial_result.get("planner_backend")
    if not isinstance(planner_backend, Mapping):
        return None, 0, 0, 0
    original_error_code = _optional_text(planner_backend.get("original_error_code"))
    repair_attempts_total = _int(planner_backend.get("repair_attempts_total"))
    repair_attempts_succeeded_total = _int(planner_backend.get("repair_attempts_succeeded_total"))
    repair_attempts_failed_total = _int(planner_backend.get("repair_attempts_failed_total"))
    return original_error_code, repair_attempts_total, repair_attempts_succeeded_total, repair_attempts_failed_total


def _empty_scenario_group(scenario_id: str, limitations: tuple[str, ...]) -> dict[str, Any]:
    return {
        "scenario_id": scenario_id,
        "trials_total": 0,
        "trials_succeeded": 0,
        "trials_failed": 0,
        "trials_rejected": 0,
        "actions_attempted_total": 0,
        "actions_succeeded_total": 0,
        "actions_failed_total": 0,
        "expected_results_passed_total": 0,
        "expected_results_failed_total": 0,
        "repair_attempts_total": 0,
        "repair_attempts_succeeded_total": 0,
        "repair_attempts_failed_total": 0,
        "_matched_urls": set(),
        "_error_codes": set(),
        "_stop_reasons": set(),
        "_route_fingerprints": set(),
        "_successful_route_fingerprints": set(),
        "_successful_matched_urls": set(),
        "limitations": limitations,
    }


def _update_scenario_group(group: dict[str, Any], trial_summary: Mapping[str, Any]) -> None:
    group["trials_total"] += 1
    status = _optional_text(trial_summary.get("status"))
    if status == "succeeded":
        group["trials_succeeded"] += 1
        if _optional_text(trial_summary.get("route_fingerprint")):
            group["_successful_route_fingerprints"].add(str(trial_summary["route_fingerprint"]))
        if _optional_text(trial_summary.get("matched_url")):
            group["_successful_matched_urls"].add(str(trial_summary["matched_url"]))
    elif status == "rejected":
        group["trials_rejected"] += 1
    else:
        group["trials_failed"] += 1
    group["actions_attempted_total"] += _int(trial_summary.get("actions_attempted"))
    group["actions_succeeded_total"] += _int(trial_summary.get("actions_succeeded"))
    group["actions_failed_total"] += _int(trial_summary.get("actions_failed"))
    group["expected_results_passed_total"] += _int(trial_summary.get("expected_results_passed"))
    group["expected_results_failed_total"] += _int(trial_summary.get("expected_results_failed"))
    group["repair_attempts_total"] += _int(trial_summary.get("repair_attempts_total"))
    group["repair_attempts_succeeded_total"] += _int(trial_summary.get("repair_attempts_succeeded_total"))
    group["repair_attempts_failed_total"] += _int(trial_summary.get("repair_attempts_failed_total"))
    matched_url = _optional_text(trial_summary.get("matched_url"))
    if matched_url:
        group["_matched_urls"].add(matched_url)
    error_code = _optional_text(trial_summary.get("error_code"))
    if error_code:
        group["_error_codes"].add(error_code)
    stop_reason = _optional_text(trial_summary.get("stop_reason"))
    if stop_reason:
        group["_stop_reasons"].add(stop_reason)
    route_fingerprint = _optional_text(trial_summary.get("route_fingerprint"))
    if route_fingerprint:
        group["_route_fingerprints"].add(route_fingerprint)


def _finalize_scenario_summary(group: dict[str, Any], *, limitations: tuple[str, ...]) -> AutonomousBrowserLiveLoopVarianceScenarioSummary:
    trials_total = _int(group.get("trials_total"))
    trials_succeeded = _int(group.get("trials_succeeded"))
    trials_failed = _int(group.get("trials_failed"))
    trials_rejected = _int(group.get("trials_rejected"))
    successful_route_fingerprints = tuple(sorted(group.pop("_successful_route_fingerprints")))
    successful_matched_urls = tuple(sorted(group.pop("_successful_matched_urls")))
    route_fingerprints = tuple(sorted(group.pop("_route_fingerprints")))
    matched_urls = tuple(sorted(group.pop("_matched_urls")))
    error_codes = tuple(sorted(group.pop("_error_codes")))
    stop_reasons = tuple(sorted(group.pop("_stop_reasons")))
    pass_rate = _safe_ratio(trials_succeeded, trials_total)
    route_stable = len(successful_route_fingerprints) == 1
    matched_url_stable = len(successful_matched_urls) == 1
    return AutonomousBrowserLiveLoopVarianceScenarioSummary(
        scenario_id=str(group["scenario_id"]),
        trials_total=trials_total,
        trials_succeeded=trials_succeeded,
        trials_failed=trials_failed,
        trials_rejected=trials_rejected,
        pass_rate=pass_rate,
        actions_attempted_total=_int(group.get("actions_attempted_total")),
        actions_succeeded_total=_int(group.get("actions_succeeded_total")),
        actions_failed_total=_int(group.get("actions_failed_total")),
        expected_results_passed_total=_int(group.get("expected_results_passed_total")),
        expected_results_failed_total=_int(group.get("expected_results_failed_total")),
        repair_attempts_total=_int(group.get("repair_attempts_total")),
        repair_attempts_succeeded_total=_int(group.get("repair_attempts_succeeded_total")),
        repair_attempts_failed_total=_int(group.get("repair_attempts_failed_total")),
        matched_urls=matched_urls,
        error_codes=error_codes,
        stop_reasons=stop_reasons,
        unique_route_fingerprints=successful_route_fingerprints or route_fingerprints,
        unique_matched_urls=successful_matched_urls or matched_urls,
        route_stable=route_stable,
        matched_url_stable=matched_url_stable,
        limitations=limitations,
    )


def _finalize_suite_status(trial_summaries: list[dict[str, Any]]) -> tuple[str, str | None]:
    if not trial_summaries:
        return "failed", "suite_outputs_failed"
    statuses = [str(item.get("status") or "failed") for item in trial_summaries]
    if all(status == "succeeded" for status in statuses):
        return "succeeded", None
    if any(status == "succeeded" for status in statuses):
        first_issue = next((item.get("error_code") for item in trial_summaries if item.get("status") != "succeeded"), None)
        return "completed_with_failures", _optional_text(first_issue) or "suite_completed_with_failures"
    first_issue = next((item.get("error_code") for item in trial_summaries if _optional_text(item.get("error_code"))), None)
    return "failed", _optional_text(first_issue) or "suite_outputs_failed"


def _suite_failure(
    *,
    suite_id: str | None,
    model_alias: str | None,
    planner_backend: str,
    trial_count_per_scenario: int,
    scenarios_total: int,
    error_code: str,
    error_message: str,
    allow_model_calls: bool,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = AutonomousBrowserLiveLoopVarianceSuiteSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        suite_id=suite_id or DEFAULT_SUITE_ID,
        model_alias=model_alias or DEFAULT_MODEL_ALIAS,
        planner_backend=planner_backend,
        trial_count_per_scenario=trial_count_per_scenario,
        scenarios_total=scenarios_total,
        trials_total=0,
        trials_succeeded=0,
        trials_failed=0,
        trials_rejected=0,
        pass_rate_overall=0.0,
        model_execution_attempted=False,
        model_execution_completed=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        no_runtime_execution=True,
        allow_model_calls=allow_model_calls,
        limitations=limitations,
        scenario_summaries=(),
        trial_summaries=(),
    )
    payload = summary.to_dict()
    payload["error_message"] = error_message
    return payload


def _suite_refusal(
    *,
    suite_id: str,
    model_alias: str,
    planner_backend: str,
    trial_count_per_scenario: int,
    scenarios_total: int,
    allow_model_calls: bool,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = AutonomousBrowserLiveLoopVarianceSuiteSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="refused",
        error_code="allow_model_calls_required",
        suite_id=suite_id,
        model_alias=model_alias,
        planner_backend=planner_backend,
        trial_count_per_scenario=trial_count_per_scenario,
        scenarios_total=scenarios_total,
        trials_total=0,
        trials_succeeded=0,
        trials_failed=0,
        trials_rejected=0,
        pass_rate_overall=0.0,
        model_execution_attempted=False,
        model_execution_completed=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        no_runtime_execution=True,
        allow_model_calls=allow_model_calls,
        limitations=limitations,
        scenario_summaries=(),
        trial_summaries=(),
    )
    return summary.to_dict()


def _limitations() -> tuple[str, ...]:
    return (
        "offline fixture-only live loop variance suite",
        "no real browser execution",
        "no Playwright import",
        "no model calls unless allow_model_calls is explicitly enabled",
    )


def _load_json_payload(config_artifact: str | Path | Mapping[str, Any]) -> Any:
    if isinstance(config_artifact, Mapping):
        return dict(config_artifact)
    return json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))


def _resolve_repo_path(value: str, repo_root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float) and value.is_integer():
        return int(value)
    return 0


def _dict(value: Any, label: str) -> dict[str, Any]:
    if value is None:
        return {}
    if not isinstance(value, dict):
        raise AutonomousBrowserLiveLoopConfigError(f"{label} must be an object.")
    return dict(value)
