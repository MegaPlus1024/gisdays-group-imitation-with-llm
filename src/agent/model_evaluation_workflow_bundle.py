from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


MODEL_EVALUATION_WORKFLOW_BUNDLE_SCHEMA_VERSION = "model_evaluation_workflow_bundle_v1"
MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME = "model_evaluation_workflow_bundle.json"
MODEL_EVALUATION_WORKFLOW_BUNDLE_PREVIEW_FILENAME = "model_evaluation_workflow_bundle_preview.md"
MODEL_EVALUATION_WORKFLOW_BUNDLE_NOTES = [
    "Offline workflow bundle only; no model execution performed.",
    "Not a production recommendation.",
]

WorkflowArtifactType = Literal[
    "model_catalog",
    "model_comparison_plan",
    "readiness_report",
    "normality_comparison_summary",
    "model_resource_summary",
    "model_evaluation_scorecard",
]
WorkflowArtifactStatus = Literal["ok", "not_provided", "missing", "invalid_input"]
WorkflowBundleStatus = Literal["complete", "partial", "invalid"]

REQUIRED_WORKFLOW_ARTIFACTS: tuple[WorkflowArtifactType, ...] = (
    "model_catalog",
    "model_comparison_plan",
    "readiness_report",
)
OPTIONAL_WORKFLOW_ARTIFACTS: tuple[WorkflowArtifactType, ...] = (
    "normality_comparison_summary",
    "model_resource_summary",
    "model_evaluation_scorecard",
)
ALL_WORKFLOW_ARTIFACTS: tuple[WorkflowArtifactType, ...] = (
    *REQUIRED_WORKFLOW_ARTIFACTS,
    *OPTIONAL_WORKFLOW_ARTIFACTS,
)

_MAX_INPUT_BYTES = 1_000_000
_MAX_TEXT_CHARS = 200
_MAX_LIST_ITEMS = 50


class WorkflowArtifactSummary(BaseModel):
    path: str | None = None
    present: bool = False
    status: WorkflowArtifactStatus
    summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ModelEvaluationWorkflowBundle(BaseModel):
    schema_version: str = MODEL_EVALUATION_WORKFLOW_BUNDLE_SCHEMA_VERSION
    status: WorkflowBundleStatus
    bundle_id: str
    artifacts: dict[WorkflowArtifactType, WorkflowArtifactSummary]
    summary: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=lambda: list(MODEL_EVALUATION_WORKFLOW_BUNDLE_NOTES))
    no_runtime_execution: bool = True
    bundle_path_relative: str | None = None
    markdown_preview_path_relative: str | None = None

    @field_validator("bundle_id")
    @classmethod
    def validate_bundle_id(cls, value: str) -> str:
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("bundle_id must be non-empty.")
        return _safe_text(cleaned)


def load_workflow_artifact_summary(
    path: str | Path | None,
    artifact_type: WorkflowArtifactType,
    *,
    base_dir: str | Path | None = None,
    max_input_bytes: int = _MAX_INPUT_BYTES,
) -> WorkflowArtifactSummary:
    _validate_artifact_type(artifact_type)
    display_path = _display_path(path, base_dir=base_dir)
    if path is None:
        return WorkflowArtifactSummary(
            path=display_path,
            present=False,
            status="not_provided",
            warnings=["artifact_not_provided"],
        )

    path_obj = Path(path)
    if not path_obj.exists() or not path_obj.is_file():
        return WorkflowArtifactSummary(
            path=display_path,
            present=False,
            status="missing",
            warnings=["artifact_missing"],
        )
    try:
        if path_obj.stat().st_size > max_input_bytes:
            return WorkflowArtifactSummary(
                path=display_path,
                present=True,
                status="invalid_input",
                warnings=["artifact_too_large"],
            )
        raw_text = path_obj.read_text(encoding="utf-8")
    except OSError:
        return WorkflowArtifactSummary(
            path=display_path,
            present=True,
            status="invalid_input",
            warnings=["artifact_unreadable"],
        )
    except UnicodeDecodeError:
        return WorkflowArtifactSummary(
            path=display_path,
            present=True,
            status="invalid_input",
            warnings=["artifact_not_utf8_text"],
        )

    try:
        payload = json.loads(raw_text)
    except json.JSONDecodeError:
        return WorkflowArtifactSummary(
            path=display_path,
            present=True,
            status="invalid_input",
            warnings=["artifact_json_decode_error"],
        )
    if not isinstance(payload, dict):
        return WorkflowArtifactSummary(
            path=display_path,
            present=True,
            status="invalid_input",
            warnings=["artifact_payload_not_object"],
        )

    return WorkflowArtifactSummary(
        path=display_path,
        present=True,
        status="ok",
        summary=_summary_for_artifact(payload, artifact_type),
    )


def build_model_evaluation_workflow_bundle(
    *,
    model_catalog_path: str | Path,
    model_comparison_plan_path: str | Path,
    readiness_report_path: str | Path,
    normality_comparison_summary_path: str | Path | None = None,
    model_resource_summary_path: str | Path | None = None,
    model_evaluation_scorecard_path: str | Path | None = None,
    bundle_id: str = "model_evaluation_workflow_bundle",
    base_dir: str | Path | None = None,
    max_input_bytes: int = _MAX_INPUT_BYTES,
) -> ModelEvaluationWorkflowBundle:
    artifact_paths: dict[WorkflowArtifactType, str | Path | None] = {
        "model_catalog": model_catalog_path,
        "model_comparison_plan": model_comparison_plan_path,
        "readiness_report": readiness_report_path,
        "normality_comparison_summary": normality_comparison_summary_path,
        "model_resource_summary": model_resource_summary_path,
        "model_evaluation_scorecard": model_evaluation_scorecard_path,
    }
    artifacts = {
        artifact_type: load_workflow_artifact_summary(
            artifact_path,
            artifact_type,
            base_dir=base_dir,
            max_input_bytes=max_input_bytes,
        )
        for artifact_type, artifact_path in artifact_paths.items()
    }
    warnings = _bundle_warnings(artifacts)
    status = _bundle_status(artifacts)
    return ModelEvaluationWorkflowBundle(
        status=status,
        bundle_id=bundle_id,
        artifacts=artifacts,
        summary=_bundle_summary(artifacts),
        warnings=warnings,
    )


def write_model_evaluation_workflow_bundle(
    bundle: ModelEvaluationWorkflowBundle,
    output_dir: str | Path,
    *,
    write_markdown_preview: bool = False,
) -> tuple[Path, Path | None]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    bundle_path = out_dir / MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME
    preview_path = out_dir / MODEL_EVALUATION_WORKFLOW_BUNDLE_PREVIEW_FILENAME
    bundle_to_write = bundle.model_copy(
        update={
            "bundle_path_relative": MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME,
            "markdown_preview_path_relative": (
                MODEL_EVALUATION_WORKFLOW_BUNDLE_PREVIEW_FILENAME
                if write_markdown_preview
                else None
            ),
        }
    )
    bundle_path.write_text(
        json.dumps(bundle_to_write.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if write_markdown_preview:
        preview_path.write_text(_markdown_preview(bundle_to_write), encoding="utf-8")
        return bundle_path, preview_path
    return bundle_path, None


def _summary_for_artifact(payload: dict[str, Any], artifact_type: WorkflowArtifactType) -> dict[str, Any]:
    extractors = {
        "model_catalog": _model_catalog_summary,
        "model_comparison_plan": _model_comparison_plan_summary,
        "readiness_report": _readiness_report_summary,
        "normality_comparison_summary": _normality_comparison_summary,
        "model_resource_summary": _model_resource_summary,
        "model_evaluation_scorecard": _model_evaluation_scorecard_summary,
    }
    return _safe_value(extractors[artifact_type](payload))


def _model_catalog_summary(payload: dict[str, Any]) -> dict[str, Any]:
    models = _dict_rows(payload.get("models"))
    enabled = [model for model in models if model.get("enabled", True) is not False]
    return {
        "schema_version": _safe_text(str(payload.get("schema_version") or "")) or None,
        "model_count": len(models),
        "model_ids": _safe_string_list(model.get("model_id") for model in models),
        "enabled_count": len(enabled),
    }


def _model_comparison_plan_summary(payload: dict[str, Any]) -> dict[str, Any]:
    return {
        "plan_id": _safe_optional_text(payload.get("plan_id")),
        "candidate_pair_count": len(_list_value(payload.get("candidate_pairs"))),
        "trial_count": len(_list_value(payload.get("trials"))),
        "scenario_count": len(_list_value(payload.get("scenarios"))),
        "no_runtime_execution": payload.get("no_runtime_execution") is True,
    }


def _readiness_report_summary(payload: dict[str, Any]) -> dict[str, Any]:
    issues = _dict_rows(payload.get("issues"))
    severity_counts = Counter(
        str(issue.get("severity"))
        for issue in issues
        if issue.get("severity") in {"info", "warning", "error"}
    )
    summary = payload.get("summary") if isinstance(payload.get("summary"), dict) else {}
    return {
        "readiness_status": _safe_optional_text(payload.get("status")),
        "error_count": _int_or_count(summary.get("error_count"), severity_counts.get("error", 0)),
        "warning_count": _int_or_count(summary.get("warning_count"), severity_counts.get("warning", 0)),
        "info_count": _int_or_count(summary.get("info_count"), severity_counts.get("info", 0)),
        "issue_count": _int_or_count(summary.get("issue_count"), len(issues)),
        "trial_count": _int_or_count(payload.get("trial_count"), 0),
        "candidate_pair_count": _int_or_count(payload.get("candidate_pair_count"), 0),
    }


def _normality_comparison_summary(payload: dict[str, Any]) -> dict[str, Any]:
    leaderboard = _dict_rows(payload.get("leaderboard"))
    top_model_pair = None
    if leaderboard:
        top_model_pair = _safe_optional_text(
            leaderboard[0].get("pair_label")
            or leaderboard[0].get("model_pair")
            or leaderboard[0].get("group_label")
        )
    overall = payload.get("overall") if isinstance(payload.get("overall"), dict) else {}
    label_counts = overall.get("label_counts")
    if not isinstance(label_counts, dict):
        label_counts = _label_counts_from_groups(payload)
    return {
        "input_summary_count": _int_or_count(payload.get("input_summary_count"), 0),
        "total_entries": _int_or_count(payload.get("total_entries"), 0),
        "evaluated_entries": _int_or_count(payload.get("evaluated_entries"), 0),
        "failed_entries": _int_or_count(payload.get("failed_entries"), 0),
        "top_model_pair": top_model_pair,
        "label_counts": _safe_counter_dict(label_counts),
    }


def _model_resource_summary(payload: dict[str, Any]) -> dict[str, Any]:
    groups = payload.get("groups") if isinstance(payload.get("groups"), dict) else {}
    group_counts = {
        _safe_text(str(group_name)): len(group_rows)
        for group_name, group_rows in groups.items()
        if isinstance(group_rows, dict)
    }
    runtime_modes = []
    by_runtime_mode = groups.get("by_runtime_mode") if isinstance(groups.get("by_runtime_mode"), dict) else {}
    if by_runtime_mode:
        runtime_modes = sorted(_safe_text(str(item)) for item in by_runtime_mode.keys())
    return {
        "observation_count": _int_or_count(payload.get("observation_count"), 0),
        "invalid_count": _int_or_count(payload.get("invalid_count"), 0),
        "group_counts": group_counts,
        "runtime_modes": runtime_modes[:_MAX_LIST_ITEMS],
    }


def _model_evaluation_scorecard_summary(payload: dict[str, Any]) -> dict[str, Any]:
    warnings = payload.get("warnings")
    return {
        "scorecard_id": _safe_optional_text(payload.get("scorecard_id")),
        "model_pair_count": _int_or_count(payload.get("model_pair_count"), 0),
        "model_count": _int_or_count(payload.get("model_count"), 0),
        "warnings_count": len(warnings) if isinstance(warnings, list) else 0,
    }


def _bundle_summary(artifacts: dict[WorkflowArtifactType, WorkflowArtifactSummary]) -> dict[str, Any]:
    catalog = artifacts["model_catalog"].summary
    plan = artifacts["model_comparison_plan"].summary
    readiness = artifacts["readiness_report"].summary
    normality = artifacts["normality_comparison_summary"].summary
    resource = artifacts["model_resource_summary"].summary
    scorecard = artifacts["model_evaluation_scorecard"].summary
    return {
        "model_count": catalog.get("model_count", 0),
        "candidate_pair_count": plan.get("candidate_pair_count", readiness.get("candidate_pair_count", 0)),
        "trial_count": plan.get("trial_count", readiness.get("trial_count", 0)),
        "readiness_status": readiness.get("readiness_status"),
        "scorecard_pair_count": scorecard.get("model_pair_count", 0),
        "normality_evaluated_entries": normality.get("evaluated_entries", 0),
        "resource_observation_count": resource.get("observation_count", 0),
        "required_artifacts_ok": all(artifacts[item].status == "ok" for item in REQUIRED_WORKFLOW_ARTIFACTS),
        "optional_artifacts_present": [
            artifact_type
            for artifact_type in OPTIONAL_WORKFLOW_ARTIFACTS
            if artifacts[artifact_type].status == "ok"
        ],
        "no_runtime_execution": True,
    }


def _bundle_status(artifacts: dict[WorkflowArtifactType, WorkflowArtifactSummary]) -> WorkflowBundleStatus:
    if any(artifacts[artifact_type].status != "ok" for artifact_type in REQUIRED_WORKFLOW_ARTIFACTS):
        return "invalid"
    if any(artifacts[artifact_type].status != "ok" for artifact_type in OPTIONAL_WORKFLOW_ARTIFACTS):
        return "partial"
    return "complete"


def _bundle_warnings(artifacts: dict[WorkflowArtifactType, WorkflowArtifactSummary]) -> list[str]:
    warnings: list[str] = []
    for artifact_type, artifact in artifacts.items():
        if artifact.status == "ok":
            continue
        prefix = "required" if artifact_type in REQUIRED_WORKFLOW_ARTIFACTS else "optional"
        warnings.append(f"{prefix}_artifact_{artifact.status}:{artifact_type}")
        warnings.extend(
            f"{artifact_type}:{warning}"
            for warning in artifact.warnings
        )
    return sorted(set(_safe_text(warning) for warning in warnings))


def _label_counts_from_groups(payload: dict[str, Any]) -> dict[str, Any]:
    groups = payload.get("groups") if isinstance(payload.get("groups"), dict) else {}
    by_model_pair = groups.get("by_model_pair") if isinstance(groups.get("by_model_pair"), dict) else {}
    labels: Counter[str] = Counter()
    for group in by_model_pair.values():
        if not isinstance(group, dict):
            continue
        counts = group.get("label_counts")
        if isinstance(counts, dict):
            for label, count in counts.items():
                if isinstance(count, int):
                    labels[str(label)] += count
    return dict(labels)


def _dict_rows(value: Any) -> list[dict[str, Any]]:
    return [item for item in value if isinstance(item, dict)] if isinstance(value, list) else []


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int_or_count(value: Any, fallback: int) -> int:
    return value if isinstance(value, int) and value >= 0 else fallback


def _safe_counter_dict(value: Any) -> dict[str, int]:
    if not isinstance(value, dict):
        return {}
    result: dict[str, int] = {}
    for key, count in value.items():
        if isinstance(count, int) and count >= 0:
            result[_safe_text(str(key))] = count
    return result


def _safe_string_list(values: Any) -> list[str]:
    cleaned: list[str] = []
    for value in values:
        if isinstance(value, str) and value.strip():
            cleaned.append(_safe_text(value))
    return sorted(set(cleaned))[:_MAX_LIST_ITEMS]


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, dict):
        return {
            _safe_text(str(key)): _safe_value(child)
            for key, child in value.items()
        }
    if isinstance(value, list):
        return [_safe_value(child) for child in value[:_MAX_LIST_ITEMS]]
    return value


def _safe_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _safe_text(str(value))
    return text or None


def _safe_text(value: str, max_chars: int = _MAX_TEXT_CHARS) -> str:
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<absolute_path>", value)
    text = re.sub(r"(?<!\w)/(?:[^\s\"']+/)+[^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"\\\\[^\s\"']+", "<absolute_path>", text)
    text = text.strip()
    if len(text) <= max_chars:
        return text
    return text[: max_chars - 3].rstrip() + "..."


def _display_path(path: str | Path | None, *, base_dir: str | Path | None) -> str | None:
    if path is None:
        return None
    path_obj = Path(path)
    path_text = str(path)
    base = Path(base_dir) if base_dir is not None else None
    if base is not None:
        try:
            rel = path_obj.resolve().relative_to(base.resolve())
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


def _validate_artifact_type(artifact_type: str) -> None:
    if artifact_type not in ALL_WORKFLOW_ARTIFACTS:
        raise ValueError(f"Unknown workflow artifact type: {artifact_type}")


def _markdown_preview(bundle: ModelEvaluationWorkflowBundle) -> str:
    lines = [
        "# Model Evaluation Workflow Bundle",
        "",
        f"- status: `{bundle.status}`",
        f"- bundle_id: `{bundle.bundle_id}`",
        f"- no runtime execution: `{str(bundle.no_runtime_execution).lower()}`",
        "",
        "## Artifacts",
        "",
    ]
    for artifact_type in ALL_WORKFLOW_ARTIFACTS:
        artifact = bundle.artifacts[artifact_type]
        lines.append(
            f"- `{artifact_type}`: `{artifact.status}`"
            f" ({artifact.path or 'not provided'})"
        )
    lines.extend(
        [
            "",
            "## Summary",
            "",
            f"- model_count: `{bundle.summary.get('model_count', 0)}`",
            f"- candidate_pair_count: `{bundle.summary.get('candidate_pair_count', 0)}`",
            f"- trial_count: `{bundle.summary.get('trial_count', 0)}`",
            f"- readiness_status: `{bundle.summary.get('readiness_status')}`",
            f"- scorecard_pair_count: `{bundle.summary.get('scorecard_pair_count', 0)}`",
            f"- normality_evaluated_entries: `{bundle.summary.get('normality_evaluated_entries', 0)}`",
            f"- resource_observation_count: `{bundle.summary.get('resource_observation_count', 0)}`",
        ]
    )
    if bundle.warnings:
        lines.extend(["", "## Warnings", ""])
        lines.extend(f"- `{warning}`" for warning in bundle.warnings)
    return "\n".join(lines) + "\n"
