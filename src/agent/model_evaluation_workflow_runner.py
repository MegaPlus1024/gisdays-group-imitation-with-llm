from __future__ import annotations

import json
import re
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator, model_validator

from .model_catalog import load_model_catalog
from .model_comparison_plan import (
    ModelComparisonPlanConfig,
    build_model_comparison_plan,
    write_model_comparison_plan,
)
from .model_comparison_readiness import (
    validate_model_comparison_readiness,
    write_model_comparison_readiness_report,
)
from .model_evaluation_scorecard import (
    build_model_evaluation_scorecard,
    write_model_evaluation_scorecard,
)
from .model_evaluation_artifact_registry import (
    MODEL_RESOURCE_SUMMARY,
    WORKFLOW_CONFIG,
    WORKFLOW_RUN_MANIFEST,
    get_artifact_schema_info,
    get_default_artifact_filename,
)
from .model_evaluation_workflow_bundle import (
    build_model_evaluation_workflow_bundle,
    write_model_evaluation_workflow_bundle,
)
from .model_resource_evaluation import run_model_resource_evaluation
from .model_task_correctness_evaluation import (
    DisabledTaskCorrectnessEvaluator,
    RuleBasedTaskCorrectnessEvaluator,
    TaskCorrectnessInputLoadError,
    build_correctness_inputs_from_matrix_run_summary,
    evaluate_task_correctness_batch,
    write_task_correctness_batch_summary,
)
from .normality_comparison import (
    compare_normality_batch_summaries,
    write_normality_comparison_summary,
)


MODEL_EVALUATION_WORKFLOW_RUN_SCHEMA_VERSION = get_artifact_schema_info(
    WORKFLOW_RUN_MANIFEST
).schema_version
MODEL_EVALUATION_WORKFLOW_CONFIG_SCHEMA_VERSION = get_artifact_schema_info(
    WORKFLOW_CONFIG
).schema_version
WORKFLOW_RUN_MANIFEST_FILENAME = get_default_artifact_filename(WORKFLOW_RUN_MANIFEST)
DEFAULT_WORKFLOW_ID = "offline_model_evaluation_workflow"

WorkflowRunStatus = Literal["ok", "partial", "invalid", "write_failed"]
TaskCorrectnessEvaluatorName = Literal["rule_based", "disabled"]

_WORKFLOW_CONFIG_ALLOWED_KEYS = {
    "schema_version",
    "workflow_id",
    "model_catalog_path",
    "scenario_paths",
    "output_dir",
    "repetitions_per_pair",
    "include_self_pairs",
    "include_role_mismatch_pairs",
    "normality_batch_summary_paths",
    "resource_observation_paths",
    "resource_summary_path",
    "matrix_run_summary_path",
    "auto_task_correctness_from_matrix",
    "task_correctness_evaluator",
    "task_correctness_summary_path",
    "tags",
    "write_markdown_previews",
    "notes",
}


class ModelEvaluationWorkflowConfigError(ValueError):
    """Controlled config-loading error without local path or secret disclosure."""


class ModelEvaluationWorkflowRunConfig(BaseModel):
    workflow_id: str | None = None
    model_catalog_path: str
    scenario_paths: list[str]
    output_dir: str
    repetitions_per_pair: int = 1
    include_self_pairs: bool = True
    include_role_mismatch_pairs: bool = False
    normality_batch_summary_paths: list[str] = Field(default_factory=list)
    resource_observation_paths: list[str] = Field(default_factory=list)
    resource_summary_path: str | None = None
    matrix_run_summary_path: str | None = None
    auto_task_correctness_from_matrix: bool = False
    task_correctness_evaluator: TaskCorrectnessEvaluatorName = "rule_based"
    task_correctness_summary_path: str | None = None
    tags: list[str] = Field(default_factory=list)
    write_markdown_previews: bool = False
    notes: list[str] = Field(default_factory=list)
    config_used: bool = False
    config_schema_version: str | None = None
    config_display_path: str | None = None
    output_dir_overridden: bool = False

    @field_validator(
        "workflow_id",
        "resource_summary_path",
        "config_schema_version",
        "config_display_path",
    )
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("optional workflow text fields must be non-empty when provided.")
        return _safe_text(cleaned)

    @field_validator("matrix_run_summary_path", "task_correctness_summary_path")
    @classmethod
    def validate_optional_input_path_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("optional workflow input path fields must be non-empty when provided.")
        return cleaned

    @field_validator("model_catalog_path", "output_dir")
    @classmethod
    def validate_required_text(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("model_catalog_path and output_dir must be non-empty.")
        return cleaned

    @field_validator("scenario_paths")
    @classmethod
    def validate_scenario_paths(cls, value: list[str]) -> list[str]:
        cleaned = [_clean_text(item) for item in value]
        if not cleaned:
            raise ValueError("at least one scenario path is required.")
        for scenario_path in cleaned:
            _validate_safe_relative_path(scenario_path, field_name="scenario_path")
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("scenario paths must not contain duplicates.")
        return cleaned

    @field_validator("normality_batch_summary_paths", "resource_observation_paths", "tags", "notes")
    @classmethod
    def validate_text_lists(cls, value: list[str]) -> list[str]:
        cleaned = [_clean_text(item) for item in value]
        if len(cleaned) != len(set(cleaned)):
            raise ValueError("workflow list fields must not contain duplicates.")
        return cleaned

    @field_validator("repetitions_per_pair")
    @classmethod
    def validate_repetitions(cls, value: int) -> int:
        if value < 1:
            raise ValueError("repetitions_per_pair must be >= 1.")
        return value

    @field_validator(
        "include_self_pairs",
        "include_role_mismatch_pairs",
        "auto_task_correctness_from_matrix",
        "write_markdown_previews",
        "config_used",
        "output_dir_overridden",
        mode="before",
    )
    @classmethod
    def validate_flags(cls, value: object) -> object:
        if not isinstance(value, bool):
            raise ValueError("workflow flags must be booleans.")
        return value

    @field_validator("task_correctness_evaluator")
    @classmethod
    def validate_task_correctness_evaluator(cls, value: str) -> str:
        cleaned = value.strip()
        if cleaned not in {"rule_based", "disabled"}:
            raise ValueError("task_correctness_evaluator must be rule_based or disabled.")
        return cleaned

    @model_validator(mode="after")
    def validate_resource_input_choice(self) -> "ModelEvaluationWorkflowRunConfig":
        if self.resource_observation_paths and self.resource_summary_path:
            raise ValueError("provide resource observations or resource summary, not both.")
        return self


class ModelEvaluationWorkflowRunResult(BaseModel):
    schema_version: str = MODEL_EVALUATION_WORKFLOW_RUN_SCHEMA_VERSION
    status: WorkflowRunStatus
    workflow_id: str
    output_dir_relative: str | None = None
    artifact_paths: dict[str, str | None] = Field(default_factory=dict)
    model_count: int = 0
    candidate_pair_count: int = 0
    trial_count: int = 0
    readiness_status: str | None = None
    readiness_error_count: int = 0
    readiness_warning_count: int = 0
    correctness_input_count: int = 0
    correctness_evaluated_count: int = 0
    warnings: list[str] = Field(default_factory=list)
    no_runtime_execution: bool = True
    manifest_path_relative: str | None = None
    config_used: bool = False
    config_schema_version: str | None = None
    config_display_path: str | None = None
    output_dir_overridden: bool = False
    tags: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=list)


def load_model_evaluation_workflow_config(
    path: str | Path,
    *,
    output_dir_override: str | Path | None = None,
) -> ModelEvaluationWorkflowRunConfig:
    config_path = Path(path)
    try:
        payload = json.loads(config_path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelEvaluationWorkflowConfigError("config_file_missing") from exc
    except OSError as exc:
        raise ModelEvaluationWorkflowConfigError("config_file_unreadable") from exc
    except json.JSONDecodeError as exc:
        raise ModelEvaluationWorkflowConfigError("config_json_malformed") from exc

    config = workflow_run_config_from_dict(
        payload,
        config_dir=config_path.parent,
        output_dir_override=output_dir_override,
    )
    config.config_display_path = _display_path(config_path, base_dir=Path.cwd())
    return config


def workflow_run_config_from_dict(
    data: dict[str, Any],
    *,
    config_dir: str | Path | None = None,
    output_dir_override: str | Path | None = None,
) -> ModelEvaluationWorkflowRunConfig:
    if not isinstance(data, dict):
        raise ModelEvaluationWorkflowConfigError("config_payload_not_object")

    unknown_keys = sorted(set(data) - _WORKFLOW_CONFIG_ALLOWED_KEYS)
    if unknown_keys:
        keys = ",".join(_safe_text(key, max_chars=80) for key in unknown_keys[:8])
        raise ModelEvaluationWorkflowConfigError(f"config_unknown_keys:{keys}")

    schema_version = data.get("schema_version")
    if schema_version != MODEL_EVALUATION_WORKFLOW_CONFIG_SCHEMA_VERSION:
        raise ModelEvaluationWorkflowConfigError("config_schema_version_unsupported")

    output_dir = (
        _config_output_path(str(output_dir_override), field_name="output_dir")
        if output_dir_override is not None
        else _required_config_output_path(data, "output_dir")
    )

    payload = {
        "workflow_id": _optional_config_text(data.get("workflow_id"), "workflow_id"),
        "model_catalog_path": _config_input_path(
            _required_config_text(data, "model_catalog_path"),
            field_name="model_catalog_path",
            config_dir=config_dir,
        ),
        "scenario_paths": _config_relative_path_list(data.get("scenario_paths"), "scenario_paths"),
        "output_dir": output_dir,
        "repetitions_per_pair": data.get("repetitions_per_pair", 1),
        "include_self_pairs": data.get("include_self_pairs", True),
        "include_role_mismatch_pairs": data.get("include_role_mismatch_pairs", False),
        "normality_batch_summary_paths": [
            _config_input_path(path, field_name="normality_batch_summary_path", config_dir=config_dir)
            for path in _config_string_list(
                data.get("normality_batch_summary_paths", []),
                "normality_batch_summary_paths",
            )
        ],
        "resource_observation_paths": [
            _config_input_path(path, field_name="resource_observation_path", config_dir=config_dir)
            for path in _config_string_list(
                data.get("resource_observation_paths", []),
                "resource_observation_paths",
            )
        ],
        "resource_summary_path": _config_optional_input_path(
            data.get("resource_summary_path"),
            field_name="resource_summary_path",
            config_dir=config_dir,
        ),
        "matrix_run_summary_path": _config_optional_input_path(
            data.get("matrix_run_summary_path"),
            field_name="matrix_run_summary_path",
            config_dir=config_dir,
        ),
        "auto_task_correctness_from_matrix": data.get("auto_task_correctness_from_matrix", False),
        "task_correctness_evaluator": _optional_config_text(
            data.get("task_correctness_evaluator", "rule_based"),
            "task_correctness_evaluator",
        ),
        "task_correctness_summary_path": _config_optional_input_path(
            data.get("task_correctness_summary_path"),
            field_name="task_correctness_summary_path",
            config_dir=config_dir,
        ),
        "tags": _config_string_list(data.get("tags", []), "tags"),
        "write_markdown_previews": data.get("write_markdown_previews", False),
        "notes": _config_string_list(data.get("notes", []), "notes"),
        "config_used": True,
        "config_schema_version": MODEL_EVALUATION_WORKFLOW_CONFIG_SCHEMA_VERSION,
        "output_dir_overridden": output_dir_override is not None,
    }
    try:
        return ModelEvaluationWorkflowRunConfig.model_validate(payload)
    except ValueError as exc:
        raise ModelEvaluationWorkflowConfigError("config_validation_failed") from exc


def run_offline_model_evaluation_workflow(
    config: ModelEvaluationWorkflowRunConfig | dict[str, Any],
) -> ModelEvaluationWorkflowRunResult:
    cfg = _coerce_config(config)
    workflow_id = cfg.workflow_id or DEFAULT_WORKFLOW_ID
    output_dir = Path(cfg.output_dir)
    output_display = _display_path(output_dir, base_dir=output_dir.parent)
    config_metadata = _config_metadata_from_config(cfg)
    artifact_paths: dict[str, str | None] = {
        "model_catalog": _display_path(cfg.model_catalog_path, base_dir=output_dir),
        "model_comparison_plan": None,
        "readiness_report": None,
        "normality_comparison_summary": None,
        "model_resource_summary": None,
        "task_correctness_batch_summary": None,
        "model_evaluation_scorecard": None,
        "workflow_bundle": None,
        "workflow_run_manifest": None,
    }
    warnings: list[str] = []
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
    except OSError:
        return _result(
            status="write_failed",
            workflow_id=workflow_id,
            output_display=output_display,
            artifact_paths=artifact_paths,
            warnings=["output_dir_write_failed"],
            config_metadata=config_metadata,
        )

    if cfg.task_correctness_summary_path and cfg.auto_task_correctness_from_matrix:
        warnings.append("explicit_task_correctness_summary_overrides_auto_generation")
    if (
        cfg.matrix_run_summary_path
        and not cfg.auto_task_correctness_from_matrix
    ):
        warnings.append("matrix_run_summary_provided_without_correctness_auto")
    if (
        cfg.auto_task_correctness_from_matrix
        and not cfg.task_correctness_summary_path
        and not cfg.matrix_run_summary_path
    ):
        result = _result(
            status="invalid",
            workflow_id=workflow_id,
            output_display=output_display,
            artifact_paths=artifact_paths,
            warnings=[*warnings, "matrix_run_summary_required_for_correctness_auto"],
            config_metadata=config_metadata,
        )
        return _write_manifest_or_write_failed(result, output_dir)

    try:
        catalog = load_model_catalog(cfg.model_catalog_path)
        plan = build_model_comparison_plan(
            catalog,
            cfg.scenario_paths,
            ModelComparisonPlanConfig(
                plan_id=f"{workflow_id}_plan",
                catalog_path=_display_path(cfg.model_catalog_path, base_dir=Path.cwd()),
                repetitions_per_pair=cfg.repetitions_per_pair,
                include_self_pairs=cfg.include_self_pairs,
                include_role_mismatch_pairs=cfg.include_role_mismatch_pairs,
                tags=cfg.tags,
            ),
            project_root=Path.cwd(),
        )
        plan_path = write_model_comparison_plan(plan, output_dir / "plan")
        artifact_paths["model_comparison_plan"] = _display_path(plan_path, base_dir=output_dir)

        readiness = validate_model_comparison_readiness(
            plan,
            model_catalog=catalog,
            registry_path="configs/script_registry.example.json",
            scenario_root=Path.cwd(),
        )
        readiness_path, _ = write_model_comparison_readiness_report(
            readiness,
            output_dir / "readiness",
            write_markdown_preview=cfg.write_markdown_previews,
        )
        artifact_paths["readiness_report"] = _display_path(readiness_path, base_dir=output_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = _result(
            status="invalid",
            workflow_id=workflow_id,
            output_display=output_display,
            artifact_paths=artifact_paths,
            warnings=[f"required_artifact_build_failed:{exc.__class__.__name__}"],
            config_metadata=config_metadata,
        )
        return _write_manifest_or_write_failed(result, output_dir)

    readiness_error_count = int(readiness.summary.get("error_count", 0))
    readiness_warning_count = int(readiness.summary.get("warning_count", 0))
    if readiness.status != "ready":
        warnings.append(f"readiness_status:{readiness.status}")

    normality_path: Path | None = None
    if cfg.normality_batch_summary_paths:
        normality = compare_normality_batch_summaries(
            cfg.normality_batch_summary_paths,
            project_root=Path.cwd(),
            model_catalog=catalog,
        )
        normality_path, _ = write_normality_comparison_summary(
            normality,
            output_dir / "normality",
            write_markdown=cfg.write_markdown_previews,
        )
        artifact_paths["normality_comparison_summary"] = _display_path(normality_path, base_dir=output_dir)
        if normality.status != "ok":
            warnings.append(f"normality_comparison_status:{normality.status}")
    else:
        warnings.append("normality_inputs_not_provided")

    resource_path: Path | str | None = None
    if cfg.resource_observation_paths:
        resource = run_model_resource_evaluation(
            cfg.resource_observation_paths,
            output_dir / "resource",
            model_catalog=catalog,
            summary_id=f"{workflow_id}_resource",
            tags=cfg.tags,
            project_root=Path.cwd(),
        )
        resource_path = output_dir / "resource" / get_default_artifact_filename(MODEL_RESOURCE_SUMMARY)
        artifact_paths["model_resource_summary"] = _display_path(resource_path, base_dir=output_dir)
        if resource.status != "ok":
            warnings.append(f"model_resource_summary_status:{resource.status}")
    elif cfg.resource_summary_path:
        resource_path = cfg.resource_summary_path
        artifact_paths["model_resource_summary"] = _display_path(resource_path, base_dir=output_dir)
    else:
        warnings.append("resource_inputs_not_provided")

    task_correctness_path: str | Path | None = None
    correctness_input_count = 0
    correctness_evaluated_count = 0
    if cfg.task_correctness_summary_path:
        task_correctness_path = cfg.task_correctness_summary_path
        artifact_paths["task_correctness_batch_summary"] = _display_path(
            task_correctness_path,
            base_dir=output_dir,
        )
    elif cfg.auto_task_correctness_from_matrix and cfg.matrix_run_summary_path:
        try:
            task_correctness_summary = _build_task_correctness_summary_from_matrix(
                cfg.matrix_run_summary_path,
                evaluator_name=cfg.task_correctness_evaluator,
                summary_id=f"{workflow_id}_task_correctness",
                tags=cfg.tags,
            )
            correctness_input_count = task_correctness_summary.input_count
            correctness_evaluated_count = task_correctness_summary.evaluated_count
            task_correctness_path = write_task_correctness_batch_summary(
                task_correctness_summary,
                output_dir / "correctness",
            )
            artifact_paths["task_correctness_batch_summary"] = _display_path(
                task_correctness_path,
                base_dir=output_dir,
            )
        except (TaskCorrectnessInputLoadError, OSError, ValueError, json.JSONDecodeError) as exc:
            result = _result(
                status="invalid",
                workflow_id=workflow_id,
                output_display=output_display,
                artifact_paths=artifact_paths,
                model_count=len(catalog.models),
                candidate_pair_count=len(plan.candidate_pairs),
                trial_count=len(plan.trials),
                readiness_status=readiness.status,
                readiness_error_count=readiness_error_count,
                readiness_warning_count=readiness_warning_count,
                warnings=[*warnings, f"task_correctness_auto_generation_failed:{_safe_text(str(exc))}"],
                config_metadata=config_metadata,
            )
            return _write_manifest_or_write_failed(result, output_dir)

    try:
        scorecard = build_model_evaluation_scorecard(
            catalog,
            model_comparison_plan_path=plan_path,
            normality_comparison_summary_path=normality_path,
            model_resource_summary_path=resource_path,
            task_correctness_summary_path=task_correctness_path,
            scorecard_id=f"{workflow_id}_scorecard",
            project_root=Path.cwd(),
        )
        scorecard_path, _ = write_model_evaluation_scorecard(
            scorecard,
            output_dir / "scorecard",
            write_markdown_preview=cfg.write_markdown_previews,
        )
        artifact_paths["model_evaluation_scorecard"] = _display_path(scorecard_path, base_dir=output_dir)
        if scorecard.status != "ok":
            warnings.append(f"model_evaluation_scorecard_status:{scorecard.status}")

        bundle = build_model_evaluation_workflow_bundle(
            model_catalog_path=cfg.model_catalog_path,
            model_comparison_plan_path=plan_path,
            readiness_report_path=readiness_path,
            normality_comparison_summary_path=normality_path,
            model_resource_summary_path=resource_path,
            task_correctness_summary_path=task_correctness_path,
            model_evaluation_scorecard_path=scorecard_path,
            bundle_id=f"{workflow_id}_bundle",
            base_dir=output_dir,
        )
        bundle_path, _ = write_model_evaluation_workflow_bundle(
            bundle,
            output_dir / "bundle",
            write_markdown_preview=cfg.write_markdown_previews,
        )
        artifact_paths["workflow_bundle"] = _display_path(bundle_path, base_dir=output_dir)
        if bundle.status == "invalid":
            warnings.append("workflow_bundle_invalid")
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        result = _result(
            status="invalid",
            workflow_id=workflow_id,
            output_display=output_display,
            artifact_paths=artifact_paths,
            model_count=len(catalog.models),
            candidate_pair_count=len(plan.candidate_pairs),
            trial_count=len(plan.trials),
            readiness_status=readiness.status,
            readiness_error_count=readiness_error_count,
            readiness_warning_count=readiness_warning_count,
            correctness_input_count=correctness_input_count,
            correctness_evaluated_count=correctness_evaluated_count,
            warnings=[*warnings, f"final_artifact_build_failed:{exc.__class__.__name__}"],
            config_metadata=config_metadata,
        )
        return _write_manifest_or_write_failed(result, output_dir)

    status = _workflow_status(
        warnings=warnings,
        readiness_error_count=readiness_error_count,
        scorecard_status=scorecard.status,
        bundle_status=bundle.status,
    )
    result = _result(
        status=status,
        workflow_id=workflow_id,
        output_display=output_display,
        artifact_paths=artifact_paths,
        model_count=len(catalog.models),
        candidate_pair_count=len(plan.candidate_pairs),
        trial_count=len(plan.trials),
        readiness_status=readiness.status,
        readiness_error_count=readiness_error_count,
        readiness_warning_count=readiness_warning_count,
        correctness_input_count=correctness_input_count,
        correctness_evaluated_count=correctness_evaluated_count,
        warnings=warnings,
        config_metadata=config_metadata,
    )
    return _write_manifest_or_write_failed(result, output_dir)


def write_workflow_run_manifest(
    result: ModelEvaluationWorkflowRunResult,
    output_dir: str | Path,
) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result.manifest_path_relative = WORKFLOW_RUN_MANIFEST_FILENAME
    result.artifact_paths["workflow_run_manifest"] = WORKFLOW_RUN_MANIFEST_FILENAME
    path = out_dir / WORKFLOW_RUN_MANIFEST_FILENAME
    path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _coerce_config(
    config: ModelEvaluationWorkflowRunConfig | dict[str, Any],
) -> ModelEvaluationWorkflowRunConfig:
    if isinstance(config, ModelEvaluationWorkflowRunConfig):
        return config
    return ModelEvaluationWorkflowRunConfig.model_validate(config)


def _required_config_text(data: dict[str, Any], field_name: str) -> str:
    if field_name not in data:
        raise ModelEvaluationWorkflowConfigError(f"{field_name}_required")
    return _config_text(data[field_name], field_name)


def _required_config_output_path(data: dict[str, Any], field_name: str) -> str:
    if field_name not in data:
        raise ModelEvaluationWorkflowConfigError(f"{field_name}_required")
    return _config_output_path(data[field_name], field_name=field_name)


def _optional_config_text(value: Any, field_name: str) -> str | None:
    if value is None:
        return None
    return _safe_text(_config_text(value, field_name))


def _config_string_list(value: Any, field_name: str) -> list[str]:
    if not isinstance(value, list):
        raise ModelEvaluationWorkflowConfigError(f"{field_name}_must_be_list")
    return [_config_text(item, field_name) for item in value]


def _config_relative_path_list(value: Any, field_name: str) -> list[str]:
    items = _config_string_list(value, field_name)
    if not items:
        raise ModelEvaluationWorkflowConfigError(f"{field_name}_required")
    return [
        _config_relative_input_path(item, field_name=f"{field_name}_item")
        for item in items
    ]


def _config_optional_input_path(
    value: Any,
    *,
    field_name: str,
    config_dir: str | Path | None,
) -> str | None:
    if value is None:
        return None
    return _config_input_path(_config_text(value, field_name), field_name=field_name, config_dir=config_dir)


def _config_input_path(
    value: str,
    *,
    field_name: str,
    config_dir: str | Path | None,
) -> str:
    path_text = _config_relative_input_path(value, field_name=field_name)
    if config_dir is None:
        return path_text
    repo_candidate = Path.cwd() / path_text
    if repo_candidate.exists():
        return path_text
    config_candidate = Path(config_dir) / path_text
    if config_candidate.exists():
        return str(config_candidate.resolve(strict=False))
    return path_text


def _config_relative_input_path(value: str, *, field_name: str) -> str:
    text = _config_text(value, field_name).replace("\\", "/")
    _reject_config_path_expansion(text, field_name=field_name)
    try:
        _validate_safe_relative_path(text, field_name=field_name)
    except ValueError as exc:
        raise ModelEvaluationWorkflowConfigError(f"{field_name}_unsafe") from exc
    return text


def _config_output_path(value: Any, *, field_name: str) -> str:
    text = _config_text(value, field_name)
    _reject_config_path_expansion(text, field_name=field_name)
    return text


def _config_text(value: Any, field_name: str) -> str:
    if not isinstance(value, str):
        raise ModelEvaluationWorkflowConfigError(f"{field_name}_must_be_string")
    cleaned = value.strip()
    if not cleaned:
        raise ModelEvaluationWorkflowConfigError(f"{field_name}_required")
    return cleaned


def _reject_config_path_expansion(value: str, *, field_name: str) -> None:
    if value.startswith("~") or "$" in value or "%" in value:
        raise ModelEvaluationWorkflowConfigError(f"{field_name}_path_expansion_not_allowed")


def _workflow_status(
    *,
    warnings: list[str],
    readiness_error_count: int,
    scorecard_status: str,
    bundle_status: str,
) -> WorkflowRunStatus:
    if scorecard_status != "ok" or bundle_status == "invalid":
        return "invalid"
    if readiness_error_count > 0:
        return "partial"
    if warnings:
        return "partial"
    if bundle_status == "partial":
        return "partial"
    return "ok"


def _build_task_correctness_summary_from_matrix(
    matrix_run_summary_path: str | Path,
    *,
    evaluator_name: TaskCorrectnessEvaluatorName,
    summary_id: str,
    tags: list[str],
):
    inputs = build_correctness_inputs_from_matrix_run_summary(matrix_run_summary_path)
    evaluator = _task_correctness_evaluator(evaluator_name)
    return evaluate_task_correctness_batch(
        inputs,
        evaluator,
        summary_id=summary_id,
        tags=tags,
    )


def _task_correctness_evaluator(
    evaluator_name: TaskCorrectnessEvaluatorName,
) -> RuleBasedTaskCorrectnessEvaluator | DisabledTaskCorrectnessEvaluator:
    if evaluator_name == "disabled":
        return DisabledTaskCorrectnessEvaluator()
    return RuleBasedTaskCorrectnessEvaluator()


def _write_manifest_or_write_failed(
    result: ModelEvaluationWorkflowRunResult,
    output_dir: Path,
) -> ModelEvaluationWorkflowRunResult:
    try:
        manifest_path = write_workflow_run_manifest(result, output_dir)
    except OSError:
        return result.model_copy(
            update={
                "status": "write_failed",
                "warnings": sorted({*result.warnings, "workflow_manifest_write_failed"}),
            }
        )
    result.artifact_paths["workflow_run_manifest"] = _display_path(manifest_path, base_dir=output_dir)
    return result


def _result(
    *,
    status: WorkflowRunStatus,
    workflow_id: str,
    output_display: str | None,
    artifact_paths: dict[str, str | None],
    model_count: int = 0,
    candidate_pair_count: int = 0,
    trial_count: int = 0,
    readiness_status: str | None = None,
    readiness_error_count: int = 0,
    readiness_warning_count: int = 0,
    correctness_input_count: int = 0,
    correctness_evaluated_count: int = 0,
    warnings: list[str] | None = None,
    config_metadata: dict[str, Any] | None = None,
) -> ModelEvaluationWorkflowRunResult:
    metadata = config_metadata or {}
    return ModelEvaluationWorkflowRunResult(
        status=status,
        workflow_id=_safe_text(workflow_id),
        output_dir_relative=output_display,
        artifact_paths={key: _safe_optional_text(value) for key, value in artifact_paths.items()},
        model_count=model_count,
        candidate_pair_count=candidate_pair_count,
        trial_count=trial_count,
        readiness_status=_safe_optional_text(readiness_status),
        readiness_error_count=readiness_error_count,
        readiness_warning_count=readiness_warning_count,
        correctness_input_count=correctness_input_count,
        correctness_evaluated_count=correctness_evaluated_count,
        warnings=sorted(set(_safe_text(warning) for warning in (warnings or []))),
        config_used=bool(metadata.get("config_used", False)),
        config_schema_version=_safe_optional_text(metadata.get("config_schema_version")),
        config_display_path=_safe_optional_text(metadata.get("config_display_path")),
        output_dir_overridden=bool(metadata.get("output_dir_overridden", False)),
        tags=[_safe_text(tag) for tag in metadata.get("tags", [])],
        notes=[_safe_text(note) for note in metadata.get("notes", [])],
    )


def _config_metadata_from_config(config: ModelEvaluationWorkflowRunConfig) -> dict[str, Any]:
    return {
        "config_used": config.config_used,
        "config_schema_version": config.config_schema_version,
        "config_display_path": config.config_display_path,
        "output_dir_overridden": config.output_dir_overridden,
        "tags": list(config.tags),
        "notes": list(config.notes),
    }


def _clean_text(value: str) -> str:
    if not isinstance(value, str):
        raise ValueError("workflow text list items must be strings.")
    cleaned = value.strip()
    if not cleaned:
        raise ValueError("workflow text list items must be non-empty.")
    return cleaned


def _validate_safe_relative_path(value: str, *, field_name: str) -> None:
    if PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute():
        raise ValueError(f"{field_name} must be a relative path.")
    if re.match(r"^[A-Za-z]:", value):
        raise ValueError(f"{field_name} must be a relative path.")
    normalized = value.replace("\\", "/")
    parts = [part for part in normalized.split("/") if part]
    if not parts:
        raise ValueError(f"{field_name} must be non-empty.")
    if ".." in parts:
        raise ValueError(f"{field_name} must not contain parent directory traversal.")


def _display_path(path: str | Path | None, *, base_dir: str | Path | None) -> str | None:
    if path is None:
        return None
    path_obj = Path(path)
    path_text = str(path)
    base = Path(base_dir) if base_dir is not None else None
    if base is not None:
        try:
            rel = path_obj.resolve(strict=False).relative_to(base.resolve(strict=False))
        except (OSError, ValueError):
            rel = None
        if rel is not None:
            return _safe_text(rel.as_posix())
    if not _is_absolute_path(path_text):
        return _safe_text(path_text.replace("\\", "/"))
    name = path_obj.name or PureWindowsPath(path_text).name or PurePosixPath(path_text).name or "artifact.json"
    return f"<absolute_path>/{_safe_text(name)}"


def _is_absolute_path(path: str) -> bool:
    return (
        PureWindowsPath(path).is_absolute()
        or PurePosixPath(path).is_absolute()
        or re.match(r"^[A-Za-z]:[\\/]", path) is not None
    )


def _safe_optional_text(value: str | None) -> str | None:
    if value is None:
        return None
    return _safe_text(value)


def _safe_text(value: str, max_chars: int = 200) -> str:
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<absolute_path>", value)
    text = re.sub(r"(?<!\w)/(?:[^\s\"']+/)+[^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"\\\\[^\s\"']+", "<absolute_path>", text)
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."
