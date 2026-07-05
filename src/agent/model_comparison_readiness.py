from __future__ import annotations

import importlib
import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .model_catalog import ModelCatalog, ModelCatalogEntry, get_model_entry, load_model_catalog
from .model_comparison_plan import (
    MODEL_COMPARISON_PLAN_SCHEMA_VERSION,
    ModelComparisonPlan,
    load_model_comparison_plan,
)
from .script_registry import (
    ScriptRegistry,
    ScriptRegistryError,
    load_script_registry,
)


MODEL_COMPARISON_READINESS_SCHEMA_VERSION = "model_comparison_readiness_v1"
MODEL_COMPARISON_READINESS_REPORT_FILENAME = "model_comparison_readiness_report.json"
MODEL_COMPARISON_READINESS_PREVIEW_FILENAME = "model_comparison_readiness_preview.md"

ReadinessSeverity = Literal["info", "warning", "error"]
ReadinessScope = Literal[
    "catalog",
    "scenario",
    "pair",
    "trial",
    "registry",
    "evaluator",
]
ReadinessStatus = Literal["ready", "ready_with_warnings", "not_ready"]

_BROAD_ACTION_PATTERNS = (
    "shell",
    "command",
    "browser",
    "network",
    "http",
    "url",
)
_EXTERNAL_URL_RE = re.compile(r"https?://(?!localhost\b|127\.0\.0\.1\b|0\.0\.0\.0\b)", re.I)


class ModelComparisonReadinessIssue(BaseModel):
    severity: ReadinessSeverity
    code: str
    message: str
    scope: ReadinessScope | None = None
    reference: str | None = None
    metadata: dict[str, Any] = Field(default_factory=dict)

    @field_validator("code", "message")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("readiness issue code and message must be non-empty.")
        return cleaned


class ModelComparisonReadinessReport(BaseModel):
    schema_version: str = MODEL_COMPARISON_READINESS_SCHEMA_VERSION
    status: ReadinessStatus
    plan_id: str
    trial_count: int
    candidate_pair_count: int
    scenario_count: int
    checked_catalog: bool = False
    checked_scenarios: bool = False
    checked_registry: bool = False
    checked_evaluators: bool = False
    issues: list[ModelComparisonReadinessIssue] = Field(default_factory=list)
    summary: dict[str, Any] = Field(default_factory=dict)
    no_runtime_execution: bool = True
    report_path_relative: str | None = None
    markdown_preview_path_relative: str | None = None


def load_model_comparison_plan_for_readiness(path: str | Path) -> ModelComparisonPlan:
    """Load a model comparison plan without executing models or checking GGUF files."""

    return load_model_comparison_plan(path)


def validate_model_comparison_readiness(
    plan: ModelComparisonPlan | dict[str, Any],
    model_catalog: ModelCatalog | str | Path | None = None,
    registry_path: str | Path | None = None,
    scenario_root: str | Path | None = None,
) -> ModelComparisonReadinessReport:
    """Validate whether an offline model-comparison plan is ready to be evaluated.

    The validator is intentionally static: it reads JSON/configuration files and imports
    evaluator modules, but it never starts model servers, browsers, office software, or
    other runtime backends.
    """

    plan_obj = _coerce_plan(plan)
    root = Path(scenario_root or Path("."))
    catalog = _coerce_catalog(model_catalog)
    issues: list[ModelComparisonReadinessIssue] = []

    _validate_plan_shape(plan_obj, issues)
    if catalog is not None:
        _validate_catalog_readiness(plan_obj, catalog, issues)

    checked_scenarios = _validate_scenarios(plan_obj, root, registry_path, issues)
    checked_registry = _validate_registry_and_roles(plan_obj, root, registry_path, issues)
    checked_evaluators = _validate_evaluator_imports(issues)

    severity_counts = Counter(issue.severity for issue in issues)
    status = _status_from_issues(issues)
    summary = {
        "error_count": severity_counts.get("error", 0),
        "warning_count": severity_counts.get("warning", 0),
        "info_count": severity_counts.get("info", 0),
        "issue_count": len(issues),
        "candidate_pair_ids": sorted(_pair_ids(plan_obj)),
        "scenario_ids": sorted(_scenario_ids(plan_obj)),
        "trial_ids_checked": len(plan_obj.trials),
        "no_runtime_execution": plan_obj.no_runtime_execution is True,
        "offline_plan_readiness_only": True,
    }

    return ModelComparisonReadinessReport(
        status=status,
        plan_id=plan_obj.plan_id,
        trial_count=len(plan_obj.trials),
        candidate_pair_count=len(plan_obj.candidate_pairs),
        scenario_count=len(plan_obj.scenarios),
        checked_catalog=catalog is not None,
        checked_scenarios=checked_scenarios,
        checked_registry=checked_registry,
        checked_evaluators=checked_evaluators,
        issues=issues,
        summary=summary,
    )


def write_model_comparison_readiness_report(
    report: ModelComparisonReadinessReport,
    output_dir: str | Path,
    write_markdown_preview: bool = False,
) -> tuple[Path, Path | None]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    report_path = out_dir / MODEL_COMPARISON_READINESS_REPORT_FILENAME
    preview_path = out_dir / MODEL_COMPARISON_READINESS_PREVIEW_FILENAME
    report_to_write = report.model_copy(
        update={
            "report_path_relative": MODEL_COMPARISON_READINESS_REPORT_FILENAME,
            "markdown_preview_path_relative": (
                MODEL_COMPARISON_READINESS_PREVIEW_FILENAME
                if write_markdown_preview
                else None
            ),
        }
    )
    report_path.write_text(
        json.dumps(report_to_write.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if write_markdown_preview:
        preview_path.write_text(_markdown_preview(report_to_write), encoding="utf-8")
        return report_path, preview_path
    return report_path, None


def _coerce_plan(plan: ModelComparisonPlan | dict[str, Any]) -> ModelComparisonPlan:
    if isinstance(plan, ModelComparisonPlan):
        return plan
    return ModelComparisonPlan.model_validate(plan)


def _coerce_catalog(model_catalog: ModelCatalog | str | Path | None) -> ModelCatalog | None:
    if model_catalog is None:
        return None
    if isinstance(model_catalog, ModelCatalog):
        return model_catalog
    return load_model_catalog(model_catalog)


def _validate_plan_shape(
    plan: ModelComparisonPlan,
    issues: list[ModelComparisonReadinessIssue],
) -> None:
    if plan.schema_version != MODEL_COMPARISON_PLAN_SCHEMA_VERSION:
        _add(
            issues,
            "error",
            "plan_schema_version_unexpected",
            f"Plan schema_version must be {MODEL_COMPARISON_PLAN_SCHEMA_VERSION}.",
            scope="trial",
            reference=plan.plan_id,
            metadata={"schema_version": plan.schema_version},
        )
    if plan.no_runtime_execution is not True:
        _add(
            issues,
            "error",
            "plan_runtime_execution_enabled",
            "Plan must declare no_runtime_execution=true for offline readiness.",
            scope="trial",
            reference=plan.plan_id,
        )
    if not plan.candidate_pairs:
        _add(
            issues,
            "error",
            "candidate_pairs_missing",
            "Plan has no candidate_pairs.",
            scope="pair",
            reference=plan.plan_id,
        )
    if not plan.trials:
        _add(
            issues,
            "error",
            "trials_missing",
            "Plan has no trials.",
            scope="trial",
            reference=plan.plan_id,
        )

    _validate_unique_ids(
        values=_pair_ids(plan),
        label="pair_id",
        duplicate_code="duplicate_pair_id",
        scope="pair",
        issues=issues,
    )
    _validate_unique_ids(
        values=[trial.trial_id for trial in plan.trials],
        label="trial_id",
        duplicate_code="duplicate_trial_id",
        scope="trial",
        issues=issues,
    )

    pair_ids = set(_pair_ids(plan))
    scenario_ids = set(_scenario_ids(plan))
    for pair in plan.candidate_pairs:
        pair_id = _text(pair.get("pair_id"))
        if not pair_id:
            _add(
                issues,
                "error",
                "pair_id_missing",
                "Candidate pair is missing pair_id.",
                scope="pair",
            )
        if pair.get("no_runtime_execution") is not True:
            _add(
                issues,
                "error",
                "pair_runtime_execution_enabled",
                "Candidate pair must declare no_runtime_execution=true.",
                scope="pair",
                reference=pair_id or None,
            )

    for trial in plan.trials:
        if trial.pair_id not in pair_ids:
            _add(
                issues,
                "error",
                "trial_unknown_pair",
                "Trial references a pair_id absent from candidate_pairs.",
                scope="trial",
                reference=trial.trial_id,
                metadata={"pair_id": trial.pair_id},
            )
        if trial.scenario_id not in scenario_ids:
            _add(
                issues,
                "error",
                "trial_unknown_scenario",
                "Trial references a scenario_id absent from scenarios.",
                scope="trial",
                reference=trial.trial_id,
                metadata={"scenario_id": trial.scenario_id},
            )
        if trial.no_runtime_execution is not True:
            _add(
                issues,
                "error",
                "trial_runtime_execution_enabled",
                "Trial must declare no_runtime_execution=true.",
                scope="trial",
                reference=trial.trial_id,
            )


def _validate_catalog_readiness(
    plan: ModelComparisonPlan,
    catalog: ModelCatalog,
    issues: list[ModelComparisonReadinessIssue],
) -> None:
    for model_id in sorted(_referenced_model_ids(plan)):
        try:
            entry = get_model_entry(catalog, model_id)
        except KeyError:
            _add(
                issues,
                "error",
                "catalog_model_missing",
                "Referenced model is absent from the model catalog.",
                scope="catalog",
                reference=model_id,
            )
            continue
        if entry.model_id != model_id:
            _add(
                issues,
                "info",
                "catalog_alias_resolved",
                "Referenced model alias resolved to a catalog model_id.",
                scope="catalog",
                reference=model_id,
                metadata={"resolved_model_id": entry.model_id},
            )
        _validate_catalog_local_path(entry, issues)

    for pair in plan.candidate_pairs:
        pair_id = _text(pair.get("pair_id"))
        orchestrator_id = _text(pair.get("orchestrator_model_id"))
        executor_id = _text(pair.get("executor_model_id"))
        if orchestrator_id:
            _validate_pair_role(
                catalog,
                model_id=orchestrator_id,
                pair=pair,
                pair_id=pair_id,
                role_field="orchestrator_candidate",
                code="orchestrator_role_not_catalog_candidate",
                message="Orchestrator model is not marked as orchestrator_candidate in the catalog.",
                issues=issues,
            )
        if executor_id:
            _validate_pair_role(
                catalog,
                model_id=executor_id,
                pair=pair,
                pair_id=pair_id,
                role_field="executor_candidate",
                code="executor_role_not_catalog_candidate",
                message="Executor model is not marked as executor_candidate in the catalog.",
                issues=issues,
            )


def _validate_pair_role(
    catalog: ModelCatalog,
    *,
    model_id: str,
    pair: dict[str, Any],
    pair_id: str,
    role_field: str,
    code: str,
    message: str,
    issues: list[ModelComparisonReadinessIssue],
) -> None:
    try:
        entry = get_model_entry(catalog, model_id)
    except KeyError:
        return
    if getattr(entry.roles, role_field):
        return

    explicit_mismatch = code in {str(item) for item in pair.get("warnings", [])}
    _add(
        issues,
        "warning" if explicit_mismatch else "error",
        code,
        message,
        scope="pair",
        reference=pair_id or model_id,
        metadata={
            "model_id": model_id,
            "explicit_mismatch_in_plan": explicit_mismatch,
        },
    )


def _validate_catalog_local_path(
    entry: ModelCatalogEntry,
    issues: list[ModelComparisonReadinessIssue],
) -> None:
    if not _is_safe_relative_path(entry.local_path):
        _add(
            issues,
            "error",
            "catalog_local_path_unsafe",
            "Catalog local_path must be a safe relative path.",
            scope="catalog",
            reference=entry.model_id,
        )


def _validate_scenarios(
    plan: ModelComparisonPlan,
    scenario_root: Path,
    registry_path: str | Path | None,
    issues: list[ModelComparisonReadinessIssue],
) -> bool:
    checked = False
    for scenario in plan.scenarios:
        checked = True
        scenario_id = _text(scenario.get("scenario_id"))
        scenario_path = _text(scenario.get("scenario_path"))
        if not scenario_path:
            _add(
                issues,
                "error",
                "scenario_path_missing",
                "Scenario row is missing scenario_path.",
                scope="scenario",
                reference=scenario_id or None,
            )
            continue
        if not _is_safe_relative_path(scenario_path):
            _add(
                issues,
                "error",
                "scenario_path_unsafe",
                "Scenario path must be a safe relative path.",
                scope="scenario",
                reference=scenario_id or scenario_path,
            )
            continue

        path = scenario_root / scenario_path
        if not path.exists():
            _add(
                issues,
                "warning",
                "scenario_config_missing",
                "Scenario config path does not exist; static scenario checks were skipped.",
                scope="scenario",
                reference=scenario_id or scenario_path,
            )
            continue
        payload = _load_json_file(path, issues, scope="scenario", reference=scenario_id or scenario_path)
        if payload is None:
            continue
        _add(
            issues,
            "info",
            "scenario_config_loaded",
            "Scenario config loaded for offline readiness checks.",
            scope="scenario",
            reference=scenario_id or _text(payload.get("scenario_id")) or scenario_path,
        )
        _validate_scenario_payload(payload, issues, reference=scenario_id or scenario_path)
        _validate_role_template_payloads(
            scenario_payload=payload,
            scenario_root=scenario_root,
            scenario_file=path,
            registry_path=registry_path,
            issues=issues,
        )
    return checked


def _validate_scenario_payload(
    payload: dict[str, Any],
    issues: list[ModelComparisonReadinessIssue],
    *,
    reference: str,
) -> None:
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    if metadata.get("offline_fake_compatible") is True:
        _add(
            issues,
            "info",
            "scenario_offline_fake_compatible",
            "Scenario metadata declares offline/fake compatibility.",
            scope="scenario",
            reference=reference,
        )
    else:
        _add(
            issues,
            "warning",
            "scenario_offline_fake_compatibility_unknown",
            "Scenario does not explicitly declare offline/fake compatibility.",
            scope="scenario",
            reference=reference,
        )

    execute_actions = payload.get("execute_actions")
    write_policy = _first_text(
        payload.get("write_path_policy"),
        metadata.get("write_path_policy"),
        _nested(payload, "execution", "write_path_policy"),
        _nested(payload, "policy", "write_path_policy"),
    )
    if execute_actions is False:
        _add(
            issues,
            "info",
            "scenario_execute_actions_disabled",
            "Scenario declares execute_actions=false.",
            scope="scenario",
            reference=reference,
        )
    elif write_policy == "artifact_workspace_only":
        _add(
            issues,
            "warning",
            "scenario_execute_actions_safe_policy_only",
            "Scenario may execute actions, but uses artifact_workspace_only write policy.",
            scope="scenario",
            reference=reference,
        )
    else:
        _add(
            issues,
            "warning",
            "scenario_execute_actions_not_offline_disabled",
            "Scenario does not disable execution and no safe write policy was detected.",
            scope="scenario",
            reference=reference,
        )

    if write_policy == "artifact_workspace_only":
        _add(
            issues,
            "info",
            "scenario_artifact_workspace_policy",
            "Scenario declares artifact_workspace_only write policy.",
            scope="scenario",
            reference=reference,
        )
    elif write_policy:
        _add(
            issues,
            "warning",
            "scenario_write_policy_unrecognized",
            "Scenario write_path_policy is not artifact_workspace_only.",
            scope="scenario",
            reference=reference,
            metadata={"write_path_policy": write_policy},
        )

    if _contains_external_url(payload):
        _add(
            issues,
            "warning",
            "scenario_external_url_detected",
            "Scenario contains an external URL reference.",
            scope="scenario",
            reference=reference,
        )
    else:
        _add(
            issues,
            "info",
            "scenario_no_external_url_detected",
            "No external URL requirement was detected in the scenario config.",
            scope="scenario",
            reference=reference,
        )

    if _requires_real_office(payload):
        _add(
            issues,
            "warning",
            "scenario_real_office_requirement_detected",
            "Scenario appears to require a real office backend/application.",
            scope="scenario",
            reference=reference,
        )
    else:
        _add(
            issues,
            "info",
            "scenario_no_real_office_requirement_detected",
            "No real MS Office/LibreOffice requirement was detected in the scenario config.",
            scope="scenario",
            reference=reference,
        )


def _validate_registry_and_roles(
    plan: ModelComparisonPlan,
    scenario_root: Path,
    registry_path: str | Path | None,
    issues: list[ModelComparisonReadinessIssue],
) -> bool:
    registry = _load_registry(registry_path, scenario_root, issues)
    if registry is None:
        return registry_path is not None

    registry_actions = registry.script_names()
    _add(
        issues,
        "info",
        "registry_loaded",
        "Script registry loaded for static action checks.",
        scope="registry",
        metadata={"script_count": len(registry_actions)},
    )

    for scenario in plan.scenarios:
        scenario_path = _text(scenario.get("scenario_path"))
        if not scenario_path or not _is_safe_relative_path(scenario_path):
            continue
        path = scenario_root / scenario_path
        if not path.exists():
            continue
        payload = _load_json_file(
            path,
            issues,
            scope="registry",
            reference=_text(scenario.get("scenario_id")) or scenario_path,
        )
        if payload is None:
            continue
        action_names = _collect_scenario_action_names(payload)
        _validate_action_names(
            action_names,
            registry_actions,
            issues,
            reference=_text(payload.get("scenario_id")) or scenario_path,
        )
    return True


def _validate_role_template_payloads(
    *,
    scenario_payload: dict[str, Any],
    scenario_root: Path,
    scenario_file: Path,
    registry_path: str | Path | None,
    issues: list[ModelComparisonReadinessIssue],
) -> None:
    registry = _load_registry(registry_path, scenario_root, issues, quiet=True)
    registry_actions = registry.script_names() if registry is not None else set()
    for role_path_text in _iter_role_template_paths(scenario_payload):
        if not _is_safe_relative_path(role_path_text):
            _add(
                issues,
                "error",
                "role_template_path_unsafe",
                "Role template path must be a safe relative path.",
                scope="registry",
                reference=role_path_text,
            )
            continue
        role_path = _resolve_existing_role_path(role_path_text, scenario_root, scenario_file)
        if role_path is None:
            _add(
                issues,
                "warning",
                "role_template_missing",
                "Role template path does not exist; role action checks were skipped.",
                scope="registry",
                reference=role_path_text,
            )
            continue
        role_payload = _load_json_file(role_path, issues, scope="registry", reference=role_path_text)
        if role_payload is None:
            continue
        action_names = _collect_role_action_names(role_payload)
        if registry_actions:
            _validate_action_names(action_names, registry_actions, issues, reference=role_path_text)
        if _is_office_document_context(scenario_payload, role_payload):
            for action_name in sorted(action_names):
                if _is_broad_action(action_name):
                    _add(
                        issues,
                        "warning",
                        "broad_action_in_office_role",
                        "Office document role includes a broad shell/network/browser action.",
                        scope="registry",
                        reference=role_path_text,
                        metadata={"action": action_name},
                    )


def _load_registry(
    registry_path: str | Path | None,
    scenario_root: Path,
    issues: list[ModelComparisonReadinessIssue],
    *,
    quiet: bool = False,
) -> ScriptRegistry | None:
    if registry_path is None:
        if not quiet:
            _add(
                issues,
                "warning",
                "registry_not_provided",
                "No script registry path was provided; registry checks were skipped.",
                scope="registry",
            )
        return None
    path = Path(registry_path)
    if not path.is_absolute():
        path = scenario_root / path
    try:
        return load_script_registry(path)
    except ScriptRegistryError:
        if not quiet:
            _add(
                issues,
                "warning",
                "registry_unavailable",
                "Script registry could not be loaded; registry checks were skipped.",
                scope="registry",
                reference=str(registry_path),
            )
        return None


def _validate_action_names(
    action_names: set[str],
    registry_actions: set[str],
    issues: list[ModelComparisonReadinessIssue],
    *,
    reference: str,
) -> None:
    missing = sorted(action_names - registry_actions)
    if missing:
        for action_name in missing:
            _add(
                issues,
                "error",
                "registry_action_missing",
                "Role or scenario references an action absent from the script registry.",
                scope="registry",
                reference=reference,
                metadata={"action": action_name},
            )
        return
    if action_names:
        _add(
            issues,
            "info",
            "registry_actions_available",
            "Referenced role/scenario actions are present in the script registry.",
            scope="registry",
            reference=reference,
            metadata={"action_count": len(action_names)},
        )


def _validate_evaluator_imports(issues: list[ModelComparisonReadinessIssue]) -> bool:
    modules = {
        "normality_evaluation_runner": "src.agent.normality_evaluation_runner",
        "model_resource_evaluation": "src.agent.model_resource_evaluation",
        "model_evaluation_scorecard": "src.agent.model_evaluation_scorecard",
    }
    ok = True
    for name, module_path in modules.items():
        try:
            importlib.import_module(module_path)
        except Exception:
            ok = False
            _add(
                issues,
                "error",
                "evaluator_import_failed",
                "Offline evaluator module is not importable.",
                scope="evaluator",
                reference=name,
            )
        else:
            _add(
                issues,
                "info",
                "evaluator_importable",
                "Offline evaluator module is importable.",
                scope="evaluator",
                reference=name,
            )
    return ok


def _validate_unique_ids(
    *,
    values: list[str],
    label: str,
    duplicate_code: str,
    scope: ReadinessScope,
    issues: list[ModelComparisonReadinessIssue],
) -> None:
    counts = Counter(values)
    for value, count in sorted(counts.items()):
        if count > 1:
            _add(
                issues,
                "error",
                duplicate_code,
                f"Duplicate {label} value found.",
                scope=scope,
                reference=value,
                metadata={"count": count},
            )


def _pair_ids(plan: ModelComparisonPlan) -> list[str]:
    return [_text(pair.get("pair_id")) for pair in plan.candidate_pairs if _text(pair.get("pair_id"))]


def _scenario_ids(plan: ModelComparisonPlan) -> list[str]:
    return [_text(scenario.get("scenario_id")) for scenario in plan.scenarios if _text(scenario.get("scenario_id"))]


def _referenced_model_ids(plan: ModelComparisonPlan) -> set[str]:
    ids: set[str] = set()
    for pair in plan.candidate_pairs:
        ids.update(
            item
            for item in [
                _text(pair.get("orchestrator_model_id")),
                _text(pair.get("executor_model_id")),
            ]
            if item
        )
    for trial in plan.trials:
        ids.add(trial.orchestrator_model_id)
        ids.add(trial.executor_model_id)
    return ids


def _iter_role_template_paths(payload: dict[str, Any]) -> list[str]:
    paths: list[str] = []
    for agent in payload.get("agents", []):
        if isinstance(agent, dict):
            path = _text(agent.get("role_template_path"))
            if path:
                paths.append(path)
    return sorted(set(paths))


def _resolve_existing_role_path(role_path_text: str, scenario_root: Path, scenario_file: Path) -> Path | None:
    candidates = [
        scenario_root / role_path_text,
        scenario_file.parent / role_path_text,
    ]
    for candidate in candidates:
        if candidate.exists():
            return candidate
    return None


def _collect_scenario_action_names(payload: dict[str, Any]) -> set[str]:
    names: set[str] = set()
    metadata = payload.get("metadata") if isinstance(payload.get("metadata"), dict) else {}
    names.update(_strings_from_known_action_keys(metadata))
    for agent in payload.get("agents", []):
        if isinstance(agent, dict):
            names.update(_strings_from_known_action_keys(agent))
            state_override = agent.get("state_override")
            if isinstance(state_override, dict):
                names.update(_strings_from_known_action_keys(state_override))
    return _clean_action_names(names)


def _collect_role_action_names(payload: dict[str, Any]) -> set[str]:
    names = _strings_from_known_action_keys(payload)
    resources = payload.get("resources")
    constraints = payload.get("constraints")
    metadata = payload.get("metadata")
    if isinstance(resources, dict):
        names.update(_strings_from_known_action_keys(resources))
    if isinstance(constraints, dict):
        for key in ("allowed_action_names", "allowed_actions", "available_scripts", "script_names"):
            value = constraints.get(key)
            if isinstance(value, list):
                names.update(item for item in value if isinstance(item, str))
    if isinstance(metadata, dict):
        names.update(_strings_from_known_action_keys(metadata))
    return _clean_action_names(names)


def _strings_from_known_action_keys(payload: dict[str, Any]) -> set[str]:
    keys = {
        "allowed_action_names",
        "allowed_actions",
        "available_scripts",
        "expected_safe_actions",
        "planned_action_sequence",
        "script_names",
        "scripts",
        "tools",
    }
    names: set[str] = set()
    for key in keys:
        value = payload.get(key)
        if isinstance(value, list):
            names.update(item for item in value if isinstance(item, str))
    return names


def _clean_action_names(values: set[str]) -> set[str]:
    return {
        value.strip()
        for value in values
        if value.strip() and ("_" in value or value.startswith(("office", "browser", "run")))
    }


def _is_office_document_context(scenario_payload: dict[str, Any], role_payload: dict[str, Any]) -> bool:
    text = json.dumps(
        {
            "scenario_id": scenario_payload.get("scenario_id"),
            "scenario_metadata": scenario_payload.get("metadata"),
            "role_id": role_payload.get("role_id"),
            "role_metadata": role_payload.get("metadata"),
        },
        ensure_ascii=False,
    ).lower()
    return "office_document" in text or "document-file" in text or "office document" in text


def _is_broad_action(action_name: str) -> bool:
    lowered = action_name.lower()
    return any(pattern in lowered for pattern in _BROAD_ACTION_PATTERNS)


def _load_json_file(
    path: Path,
    issues: list[ModelComparisonReadinessIssue],
    *,
    scope: ReadinessScope,
    reference: str,
) -> dict[str, Any] | None:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError):
        _add(
            issues,
            "error",
            f"{scope}_json_load_failed",
            "JSON file could not be loaded for readiness checks.",
            scope=scope,
            reference=reference,
        )
        return None
    if not isinstance(payload, dict):
        _add(
            issues,
            "error",
            f"{scope}_json_not_object",
            "JSON file must contain an object.",
            scope=scope,
            reference=reference,
        )
        return None
    return payload


def _is_safe_relative_path(value: str) -> bool:
    if not value.strip():
        return False
    if PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute():
        return False
    if re.match(r"^[a-zA-Z]:", value):
        return False
    normalized = value.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    return ".." not in parts


def _contains_external_url(value: Any) -> bool:
    if isinstance(value, str):
        return _EXTERNAL_URL_RE.search(value) is not None
    if isinstance(value, dict):
        return any(_contains_external_url(item) for item in value.values())
    if isinstance(value, list):
        return any(_contains_external_url(item) for item in value)
    return False


def _requires_real_office(payload: dict[str, Any]) -> bool:
    truthy_keys = {
        "desktop_office_required",
        "office_real_automation_required",
        "office_real_document_backend_required",
        "optional_office_dependencies_required",
        "requires_ms_office",
        "requires_libreoffice",
    }
    for key, value in _walk_key_values(payload):
        if key in truthy_keys and value is True:
            return True
    return False


def _walk_key_values(value: Any) -> list[tuple[str, Any]]:
    pairs: list[tuple[str, Any]] = []
    if isinstance(value, dict):
        for key, child in value.items():
            pairs.append((str(key), child))
            pairs.extend(_walk_key_values(child))
    elif isinstance(value, list):
        for child in value:
            pairs.extend(_walk_key_values(child))
    return pairs


def _nested(payload: dict[str, Any], *keys: str) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _first_text(*values: Any) -> str:
    for value in values:
        text = _text(value)
        if text:
            return text
    return ""


def _text(value: Any) -> str:
    return value.strip() if isinstance(value, str) else ""


def _status_from_issues(issues: list[ModelComparisonReadinessIssue]) -> ReadinessStatus:
    if any(issue.severity == "error" for issue in issues):
        return "not_ready"
    if any(issue.severity == "warning" for issue in issues):
        return "ready_with_warnings"
    return "ready"


def _add(
    issues: list[ModelComparisonReadinessIssue],
    severity: ReadinessSeverity,
    code: str,
    message: str,
    *,
    scope: ReadinessScope | None = None,
    reference: str | None = None,
    metadata: dict[str, Any] | None = None,
) -> None:
    issues.append(
        ModelComparisonReadinessIssue(
            severity=severity,
            code=code,
            message=message,
            scope=scope,
            reference=reference,
            metadata=metadata or {},
        )
    )


def _markdown_preview(report: ModelComparisonReadinessReport) -> str:
    lines = [
        "# Model Comparison Readiness Preview",
        "",
        f"- status: `{report.status}`",
        f"- plan_id: `{report.plan_id}`",
        f"- trials: `{report.trial_count}`",
        f"- candidate pairs: `{report.candidate_pair_count}`",
        f"- scenarios: `{report.scenario_count}`",
        f"- no runtime execution: `{str(report.no_runtime_execution).lower()}`",
        "",
        "## Issue Counts",
        "",
        f"- errors: `{report.summary.get('error_count', 0)}`",
        f"- warnings: `{report.summary.get('warning_count', 0)}`",
        f"- info: `{report.summary.get('info_count', 0)}`",
    ]
    if report.issues:
        lines.extend(["", "## Issues", ""])
        for issue in report.issues:
            reference = f" ({issue.reference})" if issue.reference else ""
            lines.append(f"- `{issue.severity}` `{issue.code}`{reference}: {issue.message}")
    return "\n".join(lines) + "\n"
