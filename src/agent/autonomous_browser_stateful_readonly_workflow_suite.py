from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_live_loop import _safe_relative_path
from .autonomous_browser_stateful_readonly_workflow import (
    DEFAULT_ALLOWED_ACTIONS,
    DEFAULT_DISALLOWED_ACTIONS,
    DEFAULT_LIMITATIONS,
    DEFAULT_WORKFLOW_OUTPUT_DIR,
    StatefulReadonlyWorkflowPolicy,
    build_default_stateful_readonly_workflow_scenarios,
    run_autonomous_browser_stateful_readonly_workflow,
)


CONFIG_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_workflow_suite_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_workflow_suite_summary_v1"
DEFAULT_SUITE_ID = "phase_13e_readonly_stateful_workflows"
DEFAULT_OUTPUT_DIR = DEFAULT_WORKFLOW_OUTPUT_DIR
DEFAULT_FIXTURE_MANIFEST_PATH = "tests/fixtures/local_intranet/office_site_v1/site_manifest.json"
DEFAULT_SCENARIO_IDS = (
    "stateful_policy_ticket_crosscheck",
    "stateful_approval_policy_crosscheck",
    "stateful_intranet_overview_digest",
    "stateful_ticket_priority_digest",
    "stateful_policy_search_marker_review",
)


@dataclass(frozen=True)
class StatefulReadonlyWorkflowSuiteConfig:
    schema_version: str
    suite_id: str
    planner_backend: str
    fixture_only: bool
    real_browser_execution: bool
    playwright_execution: bool
    browser_opened: bool
    external_network_allowed: bool
    writes_allowed: bool
    output_dir: str
    max_steps_per_scenario: int
    scenario_ids: tuple[str, ...]
    fixture_manifest_path: str
    read_only_policy: StatefulReadonlyWorkflowPolicy = field(default_factory=StatefulReadonlyWorkflowPolicy)
    limitations: tuple[str, ...] = DEFAULT_LIMITATIONS

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> StatefulReadonlyWorkflowSuiteConfig:
        schema_version = str(payload.get("schema_version", "")).strip()
        suite_id = _required_text(payload.get("suite_id"), "suite_id")
        planner_backend = str(payload.get("planner_backend", "scripted")).strip().lower() or "scripted"
        fixture_only = _required_bool(payload.get("fixture_only", True), "fixture_only")
        real_browser_execution = _required_bool(payload.get("real_browser_execution", False), "real_browser_execution")
        playwright_execution = _required_bool(payload.get("playwright_execution", False), "playwright_execution")
        browser_opened = _required_bool(payload.get("browser_opened", False), "browser_opened")
        external_network_allowed = _required_bool(payload.get("external_network_allowed", False), "external_network_allowed")
        writes_allowed = _required_bool(payload.get("writes_allowed", False), "writes_allowed")
        output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir")
        if output_dir is None:
            raise ValueError("output_dir must be a safe relative path.")
        max_steps_per_scenario = _required_int(payload.get("max_steps_per_scenario", 12), "max_steps_per_scenario")
        if max_steps_per_scenario <= 0:
            raise ValueError("max_steps_per_scenario must be a positive integer.")
        scenario_ids = tuple(_required_text_list(payload.get("scenario_ids", list(DEFAULT_SCENARIO_IDS)), "scenario_ids"))
        if not scenario_ids:
            raise ValueError("scenario_ids must be a non-empty list.")
        if len(set(scenario_ids)) != len(scenario_ids):
            raise ValueError("scenario_ids must not contain duplicates.")
        fixture_manifest_path = _safe_relative_path(payload.get("fixture_manifest_path", DEFAULT_FIXTURE_MANIFEST_PATH), "fixture_manifest_path")
        if fixture_manifest_path is None:
            raise ValueError("fixture_manifest_path must be a safe relative path.")
        policy_payload = payload.get("read_only_policy", {})
        if not isinstance(policy_payload, Mapping):
            raise ValueError("read_only_policy must be an object.")
        policy = StatefulReadonlyWorkflowPolicy(
            allowed_actions=tuple(_required_text_list(policy_payload.get("allowed_actions", list(DEFAULT_ALLOWED_ACTIONS)), "read_only_policy.allowed_actions")),
            disallowed_actions=tuple(_required_text_list(policy_payload.get("disallowed_actions", list(DEFAULT_DISALLOWED_ACTIONS)), "read_only_policy.disallowed_actions")),
            external_network_allowed=_required_bool(policy_payload.get("external_network_allowed", False), "read_only_policy.external_network_allowed"),
            writes_allowed=_required_bool(policy_payload.get("writes_allowed", False), "read_only_policy.writes_allowed"),
        )
        limitations = tuple(
            str(item).strip()
            for item in payload.get("limitations", [])
            if isinstance(item, str) and item.strip()
        )
        if planner_backend != "scripted":
            raise ValueError("planner_backend must be scripted.")
        if not fixture_only:
            raise ValueError("fixture_only must be true.")
        if real_browser_execution or playwright_execution or browser_opened:
            raise ValueError("real browser flags must be false.")
        if external_network_allowed:
            raise ValueError("external_network_allowed must be false.")
        if writes_allowed:
            raise ValueError("writes_allowed must be false.")
        return cls(
            schema_version=schema_version,
            suite_id=suite_id,
            planner_backend=planner_backend,
            fixture_only=fixture_only,
            real_browser_execution=real_browser_execution,
            playwright_execution=playwright_execution,
            browser_opened=browser_opened,
            external_network_allowed=external_network_allowed,
            writes_allowed=writes_allowed,
            output_dir=output_dir,
            max_steps_per_scenario=max_steps_per_scenario,
            scenario_ids=scenario_ids,
            fixture_manifest_path=fixture_manifest_path,
            read_only_policy=policy,
            limitations=limitations,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "suite_id": self.suite_id,
            "planner_backend": self.planner_backend,
            "fixture_only": self.fixture_only,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "external_network_allowed": self.external_network_allowed,
            "writes_allowed": self.writes_allowed,
            "output_dir": self.output_dir,
            "max_steps_per_scenario": self.max_steps_per_scenario,
            "scenario_ids": list(self.scenario_ids),
            "fixture_manifest_path": self.fixture_manifest_path,
            "read_only_policy": self.read_only_policy.to_dict(),
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class StatefulReadonlyWorkflowSuiteSummary:
    schema_version: str
    suite_id: str
    status: str
    error_code: str | None
    scenarios_total: int
    scenarios_succeeded: int
    scenarios_failed: int
    scenarios_rejected: int
    workflows_total: int
    workflows_succeeded: int
    actions_attempted_total: int
    actions_succeeded_total: int
    actions_failed_total: int
    facts_collected_total: int
    evidence_items_total: int
    failure_class_counts: dict[str, int]
    scenario_summaries: tuple[dict[str, Any], ...] = ()
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
            "suite_id": self.suite_id,
            "status": self.status,
            "error_code": self.error_code,
            "scenarios_total": self.scenarios_total,
            "scenarios_succeeded": self.scenarios_succeeded,
            "scenarios_failed": self.scenarios_failed,
            "scenarios_rejected": self.scenarios_rejected,
            "workflows_total": self.workflows_total,
            "workflows_succeeded": self.workflows_succeeded,
            "actions_attempted_total": self.actions_attempted_total,
            "actions_succeeded_total": self.actions_succeeded_total,
            "actions_failed_total": self.actions_failed_total,
            "facts_collected_total": self.facts_collected_total,
            "evidence_items_total": self.evidence_items_total,
            "failure_class_counts": dict(self.failure_class_counts),
            "scenario_summaries": [dict(item) for item in self.scenario_summaries],
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "real_network_traffic": self.real_network_traffic,
            "fixture_only": self.fixture_only,
            "no_runtime_execution": self.no_runtime_execution,
            "limitations": list(self.limitations),
        }


def load_autonomous_browser_stateful_readonly_workflow_suite_config(
    config_artifact: str | Path | Mapping[str, Any],
) -> StatefulReadonlyWorkflowSuiteConfig:
    try:
        payload = _load_json_payload(config_artifact)
    except OSError as exc:
        raise ValueError("stateful readonly workflow suite config could not be read.") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("stateful readonly workflow suite config JSON is malformed.") from exc
    if not isinstance(payload, dict):
        raise ValueError("stateful readonly workflow suite config root must be a JSON object.")
    return StatefulReadonlyWorkflowSuiteConfig.from_dict(payload)


def run_autonomous_browser_stateful_readonly_workflow_suite(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    try:
        config = load_autonomous_browser_stateful_readonly_workflow_suite_config(config_artifact)
    except ValueError as exc:
        payload = _suite_failure(
            suite_id=None,
            error_code="config_validation_failed",
            error_message=str(exc),
            scenarios_total=0,
            limitations=(),
        )
        return payload

    scenario_registry = build_default_stateful_readonly_workflow_scenarios(config.read_only_policy)
    unknown = [scenario_id for scenario_id in config.scenario_ids if scenario_id not in scenario_registry]
    if unknown:
        return _suite_failure(
            suite_id=config.suite_id,
            error_code="config_validation_failed",
            error_message=f"Unknown scenario_id(s): {', '.join(unknown)}",
            scenarios_total=len(config.scenario_ids),
            limitations=config.limitations,
        )

    scenario_summaries: list[dict[str, Any]] = []
    failure_class_counts: dict[str, int] = {}
    actions_attempted_total = 0
    actions_succeeded_total = 0
    actions_failed_total = 0
    facts_collected_total = 0
    evidence_items_total = 0
    scenarios_succeeded = 0
    scenarios_failed = 0
    scenarios_rejected = 0

    for scenario_id in config.scenario_ids:
        scenario = scenario_registry[scenario_id]
        if len(scenario.steps) > config.max_steps_per_scenario:
            return _suite_failure(
                suite_id=config.suite_id,
                error_code="config_validation_failed",
                error_message=f"{scenario_id} exceeds max_steps_per_scenario.",
                scenarios_total=len(config.scenario_ids),
                limitations=config.limitations,
            )
        scenario_result = run_autonomous_browser_stateful_readonly_workflow(
            scenario,
            repo_root=repo,
            output_dir=config.output_dir,
            fixture_manifest_path=config.fixture_manifest_path,
        )
        scenario_summaries.append(scenario_result)
        actions_attempted_total += int(scenario_result.get("actions_attempted", 0))
        actions_succeeded_total += int(scenario_result.get("actions_succeeded", 0))
        actions_failed_total += int(scenario_result.get("actions_failed", 0))
        facts_collected_total += int(scenario_result.get("facts_collected_total", 0))
        evidence_items_total += int(scenario_result.get("evidence_items_total", 0))
        failure_class = str(scenario_result.get("failure_class") or "none")
        failure_class_counts[failure_class] = failure_class_counts.get(failure_class, 0) + 1
        status = str(scenario_result.get("status") or "failed")
        if status == "succeeded":
            scenarios_succeeded += 1
        elif status == "rejected":
            scenarios_rejected += 1
        else:
            scenarios_failed += 1

    status, error_code = _suite_status(scenarios_succeeded, scenarios_failed, scenarios_rejected, len(config.scenario_ids))
    summary = StatefulReadonlyWorkflowSuiteSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        suite_id=config.suite_id,
        status=status,
        error_code=error_code,
        scenarios_total=len(config.scenario_ids),
        scenarios_succeeded=scenarios_succeeded,
        scenarios_failed=scenarios_failed,
        scenarios_rejected=scenarios_rejected,
        workflows_total=len(config.scenario_ids),
        workflows_succeeded=scenarios_succeeded,
        actions_attempted_total=actions_attempted_total,
        actions_succeeded_total=actions_succeeded_total,
        actions_failed_total=actions_failed_total,
        facts_collected_total=facts_collected_total,
        evidence_items_total=evidence_items_total,
        failure_class_counts=failure_class_counts,
        scenario_summaries=tuple(scenario_summaries),
        model_execution=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        real_network_traffic=False,
        fixture_only=True,
        no_runtime_execution=True,
        limitations=config.limitations,
    )
    payload = summary.to_dict()
    if status != "refused":
        _write_json(repo / config.output_dir / "autonomous_browser_stateful_readonly_workflow_suite_summary.json", payload)
    return payload


def write_autonomous_browser_stateful_readonly_workflow_suite_summary(summary: Mapping[str, Any], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    path = out / "autonomous_browser_stateful_readonly_workflow_suite_summary.json"
    path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _suite_status(
    scenarios_succeeded: int,
    scenarios_failed: int,
    scenarios_rejected: int,
    scenarios_total: int,
) -> tuple[str, str | None]:
    if scenarios_failed == 0 and scenarios_rejected == 0 and scenarios_succeeded == scenarios_total:
        return "succeeded", None
    if scenarios_succeeded > 0:
        return "completed_with_failures", "suite_completed_with_failures"
    return "failed", "suite_failed"


def _suite_failure(
    *,
    suite_id: str | None,
    error_code: str,
    error_message: str,
    scenarios_total: int,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = StatefulReadonlyWorkflowSuiteSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        suite_id=suite_id or DEFAULT_SUITE_ID,
        status="failed",
        error_code=error_code,
        scenarios_total=scenarios_total,
        scenarios_succeeded=0,
        scenarios_failed=0,
        scenarios_rejected=0,
        workflows_total=0,
        workflows_succeeded=0,
        actions_attempted_total=0,
        actions_succeeded_total=0,
        actions_failed_total=0,
        facts_collected_total=0,
        evidence_items_total=0,
        failure_class_counts={},
        scenario_summaries=(),
        model_execution=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        real_network_traffic=False,
        fixture_only=True,
        no_runtime_execution=True,
        limitations=limitations,
    )
    payload = summary.to_dict()
    payload["error_message"] = error_message
    return payload


def _load_json_payload(config_artifact: str | Path | Mapping[str, Any]) -> Any:
    if isinstance(config_artifact, Mapping):
        return dict(config_artifact)
    path = Path(config_artifact)
    text = path.read_text(encoding="utf-8-sig")
    return json.loads(text)


def _required_text(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    return value.strip()


def _required_text_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list.")
    items = [str(item).strip() for item in value if isinstance(item, str) and item.strip()]
    if len(items) != len(value):
        raise ValueError(f"{label} entries must be non-empty strings.")
    return items


def _required_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean.")
    return value


def _required_int(value: Any, label: str) -> int:
    if not isinstance(value, int):
        raise ValueError(f"{label} must be an integer.")
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
