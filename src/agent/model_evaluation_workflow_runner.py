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
from .model_evaluation_workflow_bundle import (
    build_model_evaluation_workflow_bundle,
    write_model_evaluation_workflow_bundle,
)
from .model_resource_evaluation import run_model_resource_evaluation
from .normality_comparison import (
    compare_normality_batch_summaries,
    write_normality_comparison_summary,
)


MODEL_EVALUATION_WORKFLOW_RUN_SCHEMA_VERSION = "model_evaluation_workflow_run_v1"
WORKFLOW_RUN_MANIFEST_FILENAME = "workflow_run_manifest.json"
DEFAULT_WORKFLOW_ID = "offline_model_evaluation_workflow"

WorkflowRunStatus = Literal["ok", "partial", "invalid", "write_failed"]


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
    tags: list[str] = Field(default_factory=list)
    write_markdown_previews: bool = False

    @field_validator("workflow_id", "resource_summary_path")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("optional workflow text fields must be non-empty when provided.")
        return _safe_text(cleaned)

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

    @field_validator("normality_batch_summary_paths", "resource_observation_paths", "tags")
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

    @field_validator("include_self_pairs", "include_role_mismatch_pairs", "write_markdown_previews", mode="before")
    @classmethod
    def validate_flags(cls, value: object) -> object:
        if not isinstance(value, bool):
            raise ValueError("workflow flags must be booleans.")
        return value

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
    warnings: list[str] = Field(default_factory=list)
    no_runtime_execution: bool = True
    manifest_path_relative: str | None = None


def run_offline_model_evaluation_workflow(
    config: ModelEvaluationWorkflowRunConfig | dict[str, Any],
) -> ModelEvaluationWorkflowRunResult:
    cfg = _coerce_config(config)
    workflow_id = cfg.workflow_id or DEFAULT_WORKFLOW_ID
    output_dir = Path(cfg.output_dir)
    output_display = _display_path(output_dir, base_dir=output_dir.parent)
    artifact_paths: dict[str, str | None] = {
        "model_catalog": _display_path(cfg.model_catalog_path, base_dir=output_dir),
        "model_comparison_plan": None,
        "readiness_report": None,
        "normality_comparison_summary": None,
        "model_resource_summary": None,
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
        )

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
        resource_path = output_dir / "resource" / "model_resource_summary.json"
        artifact_paths["model_resource_summary"] = _display_path(resource_path, base_dir=output_dir)
        if resource.status != "ok":
            warnings.append(f"model_resource_summary_status:{resource.status}")
    elif cfg.resource_summary_path:
        resource_path = cfg.resource_summary_path
        artifact_paths["model_resource_summary"] = _display_path(resource_path, base_dir=output_dir)
    else:
        warnings.append("resource_inputs_not_provided")

    try:
        scorecard = build_model_evaluation_scorecard(
            catalog,
            model_comparison_plan_path=plan_path,
            normality_comparison_summary_path=normality_path,
            model_resource_summary_path=resource_path,
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
            warnings=[*warnings, f"final_artifact_build_failed:{exc.__class__.__name__}"],
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
        warnings=warnings,
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
    warnings: list[str] | None = None,
) -> ModelEvaluationWorkflowRunResult:
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
        warnings=sorted(set(_safe_text(warning) for warning in (warnings or []))),
    )


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
