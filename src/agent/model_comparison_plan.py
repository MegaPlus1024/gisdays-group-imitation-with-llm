from __future__ import annotations

import json
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from pydantic import BaseModel, Field, field_validator

from .model_catalog import (
    MODEL_CATALOG_SCHEMA_VERSION,
    ModelCatalog,
    ModelCatalogEntry,
    build_candidate_pairs,
    list_models_for_role,
    model_catalog_entry_metadata,
)


MODEL_COMPARISON_PLAN_SCHEMA_VERSION = "model_comparison_plan_v1"
MODEL_COMPARISON_PLAN_FILENAME = "model_comparison_plan.json"
MODEL_COMPARISON_PLAN_NOTE = "Planning artifact only; no model execution performed."
MODEL_COMPARISON_PLAN_CREATED_BY = "offline_planner"
DEFAULT_INTENDED_EVALUATORS = [
    "normality_deterministic",
    "resource_profile_metadata",
]


class ModelComparisonScenarioRef(BaseModel):
    scenario_id: str
    scenario_path: str
    task_family: str | None = None
    tags: list[str] = Field(default_factory=list)
    enabled: bool = True

    @field_validator("scenario_id", "scenario_path")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("scenario refs require non-empty scenario_id and scenario_path.")
        return cleaned

    @field_validator("scenario_path")
    @classmethod
    def validate_scenario_path(cls, value: str) -> str:
        _validate_safe_relative_path(value, field_name="scenario_path")
        return value

    @field_validator("task_family")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is not None and not value.strip():
            raise ValueError("task_family must be non-empty when provided.")
        return value

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, value: list[str]) -> list[str]:
        return _clean_unique_text_list(value, field_name="scenario tags")

    @field_validator("enabled", mode="before")
    @classmethod
    def validate_enabled_bool(cls, value: object) -> object:
        if not isinstance(value, bool):
            raise ValueError("scenario enabled must be a boolean.")
        return value


class ModelComparisonTrialSpec(BaseModel):
    trial_id: str
    scenario_id: str
    scenario_path: str
    orchestrator_model_id: str
    executor_model_id: str
    pair_id: str
    repeat_index: int
    tags: list[str] = Field(default_factory=list)
    execute_actions: bool = False
    no_runtime_execution: bool = True
    intended_evaluators: list[str] = Field(default_factory=lambda: list(DEFAULT_INTENDED_EVALUATORS))
    expected_outputs: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ModelComparisonPlanConfig(BaseModel):
    plan_id: str = "model_comparison_plan"
    schema_version: str = MODEL_COMPARISON_PLAN_SCHEMA_VERSION
    catalog_path: str | None = None
    scenario_refs: list[ModelComparisonScenarioRef] = Field(default_factory=list)
    repetitions_per_pair: int = 1
    enabled_only: bool = True
    include_self_pairs: bool = True
    include_role_mismatch_pairs: bool = False
    tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=lambda: [MODEL_COMPARISON_PLAN_NOTE])

    @field_validator("plan_id", "schema_version")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("plan_id and schema_version must be non-empty.")
        return cleaned

    @field_validator("schema_version")
    @classmethod
    def validate_schema_version(cls, value: str) -> str:
        if value != MODEL_COMPARISON_PLAN_SCHEMA_VERSION:
            raise ValueError(f"schema_version must be {MODEL_COMPARISON_PLAN_SCHEMA_VERSION}.")
        return value

    @field_validator("catalog_path")
    @classmethod
    def validate_catalog_path(cls, value: str | None) -> str | None:
        if value is None:
            return None
        if not value.strip():
            raise ValueError("catalog_path must be non-empty when provided.")
        return value

    @field_validator("repetitions_per_pair")
    @classmethod
    def validate_repetitions(cls, value: int) -> int:
        if value < 1:
            raise ValueError("repetitions_per_pair must be >= 1.")
        return value

    @field_validator("enabled_only", "include_self_pairs", "include_role_mismatch_pairs", mode="before")
    @classmethod
    def validate_flags(cls, value: object) -> object:
        if not isinstance(value, bool):
            raise ValueError("model comparison plan flags must be booleans.")
        return value

    @field_validator("tags", "notes")
    @classmethod
    def validate_text_lists(cls, value: list[str]) -> list[str]:
        return _clean_unique_text_list(value, field_name="plan list")


class ModelComparisonPlan(BaseModel):
    plan_id: str
    schema_version: str = MODEL_COMPARISON_PLAN_SCHEMA_VERSION
    model_catalog_summary: dict[str, Any]
    candidate_pairs: list[dict[str, Any]] = Field(default_factory=list)
    scenarios: list[dict[str, Any]] = Field(default_factory=list)
    trials: list[ModelComparisonTrialSpec] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)
    created_by: str = MODEL_COMPARISON_PLAN_CREATED_BY
    no_runtime_execution: bool = True


def build_model_comparison_plan(
    catalog: ModelCatalog,
    scenarios: list[ModelComparisonScenarioRef | dict[str, Any] | str | Path],
    config: ModelComparisonPlanConfig | dict[str, Any] | None = None,
    *,
    project_root: str | Path = Path("."),
) -> ModelComparisonPlan:
    scenario_refs = [
        _coerce_scenario_ref(scenario, project_root=Path(project_root))
        for scenario in scenarios
    ]
    base_config = _coerce_plan_config(config, scenario_refs=scenario_refs)
    warnings: list[str] = []
    candidate_pairs = _candidate_pairs_from_catalog(catalog, base_config, warnings)
    scenario_rows = [_scenario_row(ref) for ref in scenario_refs]
    for ref in scenario_refs:
        if not ref.enabled:
            warnings.append(f"scenario_disabled:{ref.scenario_id}")

    trials = _trial_specs(
        candidate_pairs=candidate_pairs,
        scenario_refs=scenario_refs,
        config=base_config,
    )
    if not candidate_pairs:
        warnings.append("no_candidate_pairs")
    if not [scenario for scenario in scenario_refs if scenario.enabled]:
        warnings.append("no_enabled_scenarios")
    return ModelComparisonPlan(
        plan_id=base_config.plan_id,
        schema_version=base_config.schema_version,
        model_catalog_summary=_model_catalog_summary(catalog, base_config),
        candidate_pairs=candidate_pairs,
        scenarios=scenario_rows,
        trials=trials,
        warnings=sorted(set(warnings)),
        tags=list(base_config.tags),
        notes=list(base_config.notes),
    )


def write_model_comparison_plan(
    plan: ModelComparisonPlan,
    output_dir: str | Path,
) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / MODEL_COMPARISON_PLAN_FILENAME
    path.write_text(
        json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def load_model_comparison_plan(path: str | Path) -> ModelComparisonPlan:
    payload = json.loads(Path(path).read_text(encoding="utf-8"))
    return ModelComparisonPlan.model_validate(payload)


def _coerce_plan_config(
    config: ModelComparisonPlanConfig | dict[str, Any] | None,
    *,
    scenario_refs: list[ModelComparisonScenarioRef],
) -> ModelComparisonPlanConfig:
    if isinstance(config, ModelComparisonPlanConfig):
        if not config.scenario_refs:
            return config.model_copy(update={"scenario_refs": scenario_refs})
        return config
    payload = dict(config or {})
    payload.setdefault("scenario_refs", scenario_refs)
    return ModelComparisonPlanConfig.model_validate(payload)


def _coerce_scenario_ref(
    value: ModelComparisonScenarioRef | dict[str, Any] | str | Path,
    *,
    project_root: Path,
) -> ModelComparisonScenarioRef:
    if isinstance(value, ModelComparisonScenarioRef):
        return value
    if isinstance(value, dict):
        payload = dict(value)
        if "scenario_path" in payload:
            _validate_safe_relative_path(str(payload["scenario_path"]), field_name="scenario_path")
            payload.setdefault(
                "scenario_id",
                _read_scenario_id(payload["scenario_path"], project_root=project_root),
            )
        return ModelComparisonScenarioRef.model_validate(payload)
    return _scenario_ref_from_path(value, project_root=project_root)


def _scenario_ref_from_path(
    path: str | Path,
    *,
    project_root: Path,
) -> ModelComparisonScenarioRef:
    path_text = str(path)
    _validate_safe_relative_path(path_text, field_name="scenario_path")
    scenario_id = _read_scenario_id(path_text, project_root=project_root)
    return ModelComparisonScenarioRef(
        scenario_id=scenario_id,
        scenario_path=path_text.replace("\\", "/"),
    )


def _read_scenario_id(path: str | Path, *, project_root: Path) -> str:
    scenario_path = _resolve_project_path(path, project_root)
    payload = json.loads(scenario_path.read_text(encoding="utf-8"))
    scenario_id = payload.get("scenario_id") if isinstance(payload, dict) else None
    if not isinstance(scenario_id, str) or not scenario_id.strip():
        raise ValueError("scenario config must contain non-empty scenario_id.")
    return scenario_id.strip()


def _candidate_pairs_from_catalog(
    catalog: ModelCatalog,
    config: ModelComparisonPlanConfig,
    warnings: list[str],
) -> list[dict[str, Any]]:
    if config.include_role_mismatch_pairs:
        pairs = _all_catalog_pairs(catalog, config)
    else:
        pairs = build_candidate_pairs(catalog, enabled_only=config.enabled_only)
        pairs = [_plan_pair_from_catalog_pair(pair, warnings=[]) for pair in pairs]
        if not list_models_for_role(catalog, "orchestrator", enabled_only=config.enabled_only):
            warnings.append("no_orchestrator_candidates")
        if not list_models_for_role(catalog, "executor", enabled_only=config.enabled_only):
            warnings.append("no_executor_candidates")
    if not config.include_self_pairs:
        pairs = [
            pair for pair in pairs
            if pair["orchestrator_model_id"] != pair["executor_model_id"]
        ]
    return sorted(pairs, key=lambda pair: pair["pair_id"])


def _all_catalog_pairs(catalog: ModelCatalog, config: ModelComparisonPlanConfig) -> list[dict[str, Any]]:
    entries = [entry for entry in catalog.models if entry.enabled or not config.enabled_only]
    pairs: list[dict[str, Any]] = []
    for orchestrator in entries:
        for executor in entries:
            warnings: list[str] = []
            if not orchestrator.roles.orchestrator_candidate:
                warnings.append("orchestrator_role_not_catalog_candidate")
            if not executor.roles.executor_candidate:
                warnings.append("executor_role_not_catalog_candidate")
            pairs.append(_pair_row(orchestrator, executor, warnings=warnings))
    return pairs


def _plan_pair_from_catalog_pair(pair: dict[str, Any], *, warnings: list[str]) -> dict[str, Any]:
    metadata = pair.get("metadata") if isinstance(pair.get("metadata"), dict) else {}
    orchestrator = metadata.get("orchestrator") if isinstance(metadata.get("orchestrator"), dict) else {}
    executor = metadata.get("executor") if isinstance(metadata.get("executor"), dict) else {}
    return {
        "pair_id": pair["pair_id"],
        "pair_label": pair["pair_label"],
        "orchestrator_model_id": pair["orchestrator_model_id"],
        "executor_model_id": pair["executor_model_id"],
        "orchestrator": orchestrator,
        "executor": executor,
        "tags": sorted(pair.get("tags") or []),
        "notes": list(pair.get("known_notes") or []),
        "warnings": warnings,
        "no_runtime_execution": True,
    }


def _pair_row(
    orchestrator: ModelCatalogEntry,
    executor: ModelCatalogEntry,
    *,
    warnings: list[str],
) -> dict[str, Any]:
    tags = sorted({*orchestrator.tags, *executor.tags})
    notes = [
        *(f"orchestrator:{note}" for note in orchestrator.historical_observations),
        *(f"executor:{note}" for note in executor.historical_observations),
    ]
    return {
        "pair_id": f"{orchestrator.model_id}__to__{executor.model_id}",
        "pair_label": f"{orchestrator.model_id}->{executor.model_id}",
        "orchestrator_model_id": orchestrator.model_id,
        "executor_model_id": executor.model_id,
        "orchestrator": _plan_model_metadata(orchestrator),
        "executor": _plan_model_metadata(executor),
        "tags": tags,
        "notes": notes,
        "warnings": sorted(set(warnings)),
        "no_runtime_execution": True,
    }


def _trial_specs(
    *,
    candidate_pairs: list[dict[str, Any]],
    scenario_refs: list[ModelComparisonScenarioRef],
    config: ModelComparisonPlanConfig,
) -> list[ModelComparisonTrialSpec]:
    trials: list[ModelComparisonTrialSpec] = []
    for scenario in scenario_refs:
        if not scenario.enabled:
            continue
        for pair in candidate_pairs:
            for repeat_index in range(1, config.repetitions_per_pair + 1):
                trial_id = f"{scenario.scenario_id}__{pair['pair_id']}__r{repeat_index:02d}"
                trials.append(
                    ModelComparisonTrialSpec(
                        trial_id=trial_id,
                        scenario_id=scenario.scenario_id,
                        scenario_path=scenario.scenario_path,
                        orchestrator_model_id=pair["orchestrator_model_id"],
                        executor_model_id=pair["executor_model_id"],
                        pair_id=pair["pair_id"],
                        repeat_index=repeat_index,
                        tags=sorted({*config.tags, *scenario.tags, *pair.get("tags", [])}),
                        expected_outputs=[
                            "normality_judge_batch_summary.json",
                            "normality_comparison_summary.json",
                            "resource_profile_metadata",
                        ],
                        notes=[MODEL_COMPARISON_PLAN_NOTE],
                        warnings=list(pair.get("warnings", [])),
                    )
                )
    return trials


def _model_catalog_summary(
    catalog: ModelCatalog,
    config: ModelComparisonPlanConfig,
) -> dict[str, Any]:
    entries = [entry for entry in catalog.models if entry.enabled or not config.enabled_only]
    return {
        "schema_version": catalog.schema_version,
        "expected_schema_version": MODEL_CATALOG_SCHEMA_VERSION,
        "catalog_path": config.catalog_path,
        "model_count": len(entries),
        "enabled_only": config.enabled_only,
        "models": [_plan_model_metadata(entry) for entry in entries],
    }


def _plan_model_metadata(entry: ModelCatalogEntry | dict[str, Any]) -> dict[str, Any]:
    if isinstance(entry, dict):
        raw = dict(entry)
    else:
        raw = model_catalog_entry_metadata(entry)
    return {
        "model_id": raw.get("model_id"),
        "family": raw.get("family"),
        "parameter_count_b": raw.get("parameter_count_b"),
        "quantization": raw.get("quantization"),
        "roles": raw.get("roles", {}),
        "tags": list(raw.get("tags") or []),
        "enabled": raw.get("enabled", True),
    }


def _scenario_row(ref: ModelComparisonScenarioRef) -> dict[str, Any]:
    row = ref.model_dump(mode="json")
    row["warnings"] = ["scenario_disabled"] if not ref.enabled else []
    row["no_runtime_execution"] = True
    return row


def _validate_safe_relative_path(value: str, *, field_name: str) -> None:
    if PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute():
        raise ValueError(f"{field_name} must be a relative path.")
    path = PureWindowsPath(value) if "\\" in value else PurePosixPath(value)
    parts = [part.strip() for part in path.parts if part.strip()]
    if ".." in parts:
        raise ValueError(f"{field_name} must not contain parent directory traversal.")
    if not parts:
        raise ValueError(f"{field_name} must be non-empty.")


def _resolve_project_path(path: str | Path, project_root: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return project_root / candidate


def _clean_unique_text_list(value: list[str], *, field_name: str) -> list[str]:
    cleaned = [item.strip() for item in value]
    if any(not item for item in cleaned):
        raise ValueError(f"{field_name} must not contain empty values.")
    if len(cleaned) != len(set(cleaned)):
        raise ValueError(f"{field_name} must not contain duplicates.")
    return cleaned

