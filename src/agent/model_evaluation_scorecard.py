from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .model_catalog import (
    ModelCatalog,
    ModelCatalogEntry,
    build_candidate_pairs,
    get_model_entry,
    load_model_catalog,
    model_catalog_entry_metadata,
)


MODEL_EVALUATION_SCORECARD_SCHEMA_VERSION = "model_evaluation_scorecard_v1"
MODEL_EVALUATION_SCORECARD_FILENAME = "model_evaluation_scorecard.json"
MODEL_EVALUATION_SCORECARD_PREVIEW_FILENAME = "model_evaluation_scorecard_preview.md"
MODEL_EVALUATION_SCORECARD_CREATED_BY = "offline_model_evaluation_scorecard"
MODEL_EVALUATION_SCORECARD_NOTES = [
    "Offline scorecard only; no model execution performed.",
    "Prototype evidence synthesis only; not a production recommendation.",
]
MAX_TOP_FINDINGS = 5
MAX_TOP_CORRECTNESS_FAILURE_REASONS = 5
MAX_SCORECARD_SCENARIO_METRICS = 50
TASK_CORRECTNESS_BATCH_SUMMARY_SCHEMA_VERSION = "task_correctness_batch_summary_v1"


class JSONSummaryLoadResult(BaseModel):
    status: Literal["ok", "input_missing", "invalid_input"]
    payload: dict[str, Any] | None = None
    input_path_display: str | None = None
    warnings: list[str] = Field(default_factory=list)


class ModelEvaluationScorecard(BaseModel):
    status: str
    scorecard_id: str = "model_evaluation_scorecard"
    model_count: int = 0
    model_pair_count: int = 0
    models: list[dict[str, Any]] = Field(default_factory=list)
    model_pairs: list[dict[str, Any]] = Field(default_factory=list)
    overall: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)
    notes: list[str] = Field(default_factory=lambda: list(MODEL_EVALUATION_SCORECARD_NOTES))
    catalog_used: bool = True
    plan_used: bool = False
    normality_summary_used: bool = False
    resource_summary_used: bool = False
    task_correctness_summary_used: bool = False
    task_correctness_metrics: dict[str, Any] | None = None
    no_runtime_execution: bool = True
    created_by: str = MODEL_EVALUATION_SCORECARD_CREATED_BY
    scorecard_path_relative: str | None = None
    markdown_preview_path_relative: str | None = None
    schema_version: str = MODEL_EVALUATION_SCORECARD_SCHEMA_VERSION


def load_json_summary(
    path: str | Path,
    *,
    project_root: str | Path = Path("."),
    max_input_bytes: int = 1_000_000,
) -> JSONSummaryLoadResult:
    root = Path(project_root)
    candidate = _resolve_path(path, root)
    display = _path_display(candidate, root)
    if not candidate.exists() or not candidate.is_file():
        return JSONSummaryLoadResult(
            status="input_missing",
            input_path_display=display,
            warnings=["summary_file_missing"],
        )
    try:
        if candidate.stat().st_size > max_input_bytes:
            return JSONSummaryLoadResult(
                status="invalid_input",
                input_path_display=display,
                warnings=["summary_file_too_large"],
            )
        text = candidate.read_text(encoding="utf-8")
    except OSError:
        return JSONSummaryLoadResult(
            status="invalid_input",
            input_path_display=display,
            warnings=["summary_file_unreadable"],
        )
    except UnicodeDecodeError:
        return JSONSummaryLoadResult(
            status="invalid_input",
            input_path_display=display,
            warnings=["summary_file_not_utf8_text"],
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return JSONSummaryLoadResult(
            status="invalid_input",
            input_path_display=display,
            warnings=["summary_json_decode_error"],
        )
    if not isinstance(payload, dict):
        return JSONSummaryLoadResult(
            status="invalid_input",
            input_path_display=display,
            warnings=["summary_payload_not_object"],
        )
    return JSONSummaryLoadResult(
        status="ok",
        payload=payload,
        input_path_display=display,
    )


def build_model_evaluation_scorecard(
    model_catalog: ModelCatalog | str | Path,
    *,
    model_comparison_plan_path: str | Path | None = None,
    normality_comparison_summary_path: str | Path | None = None,
    model_resource_summary_path: str | Path | None = None,
    task_correctness_summary_path: str | Path | None = None,
    task_correctness_summary: dict[str, Any] | None = None,
    scorecard_id: str = "model_evaluation_scorecard",
    project_root: str | Path = Path("."),
    max_input_bytes: int = 1_000_000,
) -> ModelEvaluationScorecard:
    root = Path(project_root)
    catalog = _coerce_catalog(model_catalog, project_root=root)
    warnings: list[str] = []
    pair_records: dict[str, dict[str, Any]] = {}

    for pair in build_candidate_pairs(catalog):
        _ensure_pair_record(
            pair_records,
            catalog,
            pair.get("orchestrator_model_id"),
            pair.get("executor_model_id"),
            source="catalog_candidate",
            tags=pair.get("tags"),
            notes=pair.get("known_notes"),
        )

    plan_payload = _load_optional_summary(
        model_comparison_plan_path,
        label="model_comparison_plan",
        warnings=warnings,
        project_root=root,
        max_input_bytes=max_input_bytes,
    )
    normality_payload = _load_optional_summary(
        normality_comparison_summary_path,
        label="normality_comparison_summary",
        warnings=warnings,
        project_root=root,
        max_input_bytes=max_input_bytes,
    )
    resource_payload = _load_optional_summary(
        model_resource_summary_path,
        label="model_resource_summary",
        warnings=warnings,
        project_root=root,
        max_input_bytes=max_input_bytes,
    )
    task_correctness_payload = task_correctness_summary
    if task_correctness_payload is None:
        task_correctness_payload = _load_optional_summary(
            task_correctness_summary_path,
            label="task_correctness_summary",
            warnings=warnings,
            project_root=root,
            max_input_bytes=max_input_bytes,
        )

    if plan_payload is not None:
        _merge_plan(pair_records, catalog, plan_payload, warnings)
    if normality_payload is not None:
        _merge_normality_summary(pair_records, catalog, normality_payload, warnings)
    if resource_payload is not None:
        _merge_resource_summary(pair_records, catalog, resource_payload, warnings)
    if task_correctness_payload is not None:
        _merge_task_correctness_summary(pair_records, catalog, task_correctness_payload, warnings)
    else:
        warnings.append("missing_task_correctness_metrics")

    model_entries = _model_entries(catalog, pair_records, resource_payload)
    pair_entries = _final_pair_entries(
        pair_records,
        task_correctness_summary_used=task_correctness_payload is not None,
    )
    if not pair_entries:
        warnings.append("no_model_pairs")

    return ModelEvaluationScorecard(
        status="ok" if model_entries else "invalid_input",
        scorecard_id=_safe_text(scorecard_id),
        model_count=len(model_entries),
        model_pair_count=len(pair_entries),
        models=model_entries,
        model_pairs=pair_entries,
        overall=_overall_summary(model_entries, pair_entries),
        warnings=sorted(set(_safe_text(warning) for warning in warnings)),
        plan_used=plan_payload is not None,
        normality_summary_used=normality_payload is not None,
        resource_summary_used=resource_payload is not None,
        task_correctness_summary_used=task_correctness_payload is not None,
        task_correctness_metrics=(
            _task_correctness_global_metrics(task_correctness_payload)
            if task_correctness_payload is not None
            else None
        ),
    )


def write_model_evaluation_scorecard(
    scorecard: ModelEvaluationScorecard,
    output_dir: str | Path,
    *,
    write_markdown_preview: bool = False,
) -> tuple[Path, Path | None]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    scorecard.scorecard_path_relative = MODEL_EVALUATION_SCORECARD_FILENAME
    markdown_path: Path | None = None
    if write_markdown_preview:
        scorecard.markdown_preview_path_relative = MODEL_EVALUATION_SCORECARD_PREVIEW_FILENAME
    scorecard_path = out_dir / MODEL_EVALUATION_SCORECARD_FILENAME
    scorecard_path.write_text(
        json.dumps(scorecard.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if write_markdown_preview:
        markdown_path = out_dir / MODEL_EVALUATION_SCORECARD_PREVIEW_FILENAME
        markdown_path.write_text(_markdown_preview(scorecard), encoding="utf-8")
    return scorecard_path, markdown_path


def run_model_evaluation_scorecard(
    model_catalog: ModelCatalog | str | Path,
    output_dir: str | Path,
    *,
    model_comparison_plan_path: str | Path | None = None,
    normality_comparison_summary_path: str | Path | None = None,
    model_resource_summary_path: str | Path | None = None,
    task_correctness_summary_path: str | Path | None = None,
    task_correctness_summary: dict[str, Any] | None = None,
    scorecard_id: str = "model_evaluation_scorecard",
    project_root: str | Path = Path("."),
    write_markdown_preview: bool = False,
) -> ModelEvaluationScorecard:
    scorecard = build_model_evaluation_scorecard(
        model_catalog,
        model_comparison_plan_path=model_comparison_plan_path,
        normality_comparison_summary_path=normality_comparison_summary_path,
        model_resource_summary_path=model_resource_summary_path,
        task_correctness_summary_path=task_correctness_summary_path,
        task_correctness_summary=task_correctness_summary,
        scorecard_id=scorecard_id,
        project_root=project_root,
    )
    write_model_evaluation_scorecard(
        scorecard,
        output_dir,
        write_markdown_preview=write_markdown_preview,
    )
    return scorecard


def _coerce_catalog(model_catalog: ModelCatalog | str | Path, *, project_root: Path) -> ModelCatalog:
    if isinstance(model_catalog, ModelCatalog):
        return model_catalog
    return load_model_catalog(_resolve_path(model_catalog, project_root))


def _load_optional_summary(
    path: str | Path | None,
    *,
    label: str,
    warnings: list[str],
    project_root: Path,
    max_input_bytes: int,
) -> dict[str, Any] | None:
    if path is None:
        return None
    loaded = load_json_summary(path, project_root=project_root, max_input_bytes=max_input_bytes)
    if loaded.status != "ok" or loaded.payload is None:
        if loaded.status == "input_missing":
            warnings.append(f"{label}_missing")
        else:
            warnings.append(f"{label}_invalid_input")
        warnings.extend(f"{label}:{warning}" for warning in loaded.warnings)
        return None
    return loaded.payload


def _merge_plan(
    pair_records: dict[str, dict[str, Any]],
    catalog: ModelCatalog,
    payload: dict[str, Any],
    warnings: list[str],
) -> None:
    for warning in _string_list(payload.get("warnings")):
        warnings.append(f"model_comparison_plan:{warning}")

    candidate_pairs = payload.get("candidate_pairs")
    if isinstance(candidate_pairs, list):
        for pair in candidate_pairs:
            if not isinstance(pair, dict):
                continue
            record = _ensure_pair_record(
                pair_records,
                catalog,
                pair.get("orchestrator_model_id") or _nested_model_id(pair.get("orchestrator")),
                pair.get("executor_model_id") or _nested_model_id(pair.get("executor")),
                source="model_comparison_plan",
                tags=pair.get("tags"),
                notes=pair.get("notes"),
                warnings=pair.get("warnings"),
            )
            metadata = record.setdefault("plan_metadata", {})
            metadata["planned_pair"] = True
            metadata["plan_pair_id"] = _safe_text(str(pair.get("pair_id") or record["pair_id"]))
            metadata["plan_pair_label"] = _safe_text(str(pair.get("pair_label") or record["pair_label"]))
            metadata["no_runtime_execution"] = bool(pair.get("no_runtime_execution", True))

    trial_groups: dict[str, dict[str, Any]] = {}
    trials = payload.get("trials")
    if isinstance(trials, list):
        for trial in trials:
            if not isinstance(trial, dict):
                continue
            orchestrator = trial.get("orchestrator_model_id")
            executor = trial.get("executor_model_id")
            pair_id = _pair_id_from_values(orchestrator, executor, trial.get("pair_id"))
            stats = trial_groups.setdefault(
                pair_id,
                {
                    "planned_trial_count": 0,
                    "scenario_ids": set(),
                    "scenario_paths": set(),
                    "tags": set(),
                    "repeat_indices": set(),
                },
            )
            stats["planned_trial_count"] += 1
            _add_optional_set(stats["scenario_ids"], trial.get("scenario_id"))
            _add_optional_set(stats["scenario_paths"], trial.get("scenario_path"))
            for tag in _string_list(trial.get("tags")):
                stats["tags"].add(tag)
            repeat_index = trial.get("repeat_index")
            if isinstance(repeat_index, int):
                stats["repeat_indices"].add(repeat_index)
            _ensure_pair_record(
                pair_records,
                catalog,
                orchestrator,
                executor,
                source="model_comparison_plan",
                tags=trial.get("tags"),
                warnings=trial.get("warnings"),
            )
    for pair_id, stats in trial_groups.items():
        if pair_id not in pair_records:
            continue
        metadata = pair_records[pair_id].setdefault("plan_metadata", {})
        metadata["planned_trial_count"] = stats["planned_trial_count"]
        metadata["scenario_ids"] = sorted(stats["scenario_ids"])
        metadata["scenario_paths"] = sorted(stats["scenario_paths"])
        metadata["tags"] = sorted(stats["tags"])
        metadata["repeat_indices"] = sorted(stats["repeat_indices"])


def _merge_normality_summary(
    pair_records: dict[str, dict[str, Any]],
    catalog: ModelCatalog,
    payload: dict[str, Any],
    warnings: list[str],
) -> None:
    for warning in _string_list(payload.get("warnings")):
        warnings.append(f"normality_comparison_summary:{warning}")

    ranked_pairs = _normality_ranks(payload)
    groups = _model_pair_groups(payload)
    if not groups:
        warnings.append("normality_comparison_summary_has_no_model_pair_groups")
    for group_label, group in groups.items():
        orchestrator, executor = _normality_group_pair(group_label, group)
        record = _ensure_pair_record(
            pair_records,
            catalog,
            orchestrator,
            executor,
            source="normality_comparison_summary",
            tags=group.get("tags"),
        )
        metrics = _normality_metrics(group_label, group)
        record["normality_metrics"] = metrics
        rank = ranked_pairs.get(record["pair_id"])
        if rank is not None:
            record["normality_rank"] = rank
        for warning in _string_list(group.get("warnings")):
            record.setdefault("warnings", set()).add(f"normality:{warning}")


def _merge_resource_summary(
    pair_records: dict[str, dict[str, Any]],
    catalog: ModelCatalog,
    payload: dict[str, Any],
    warnings: list[str],
) -> None:
    for warning in _string_list(payload.get("warnings")):
        warnings.append(f"model_resource_summary:{warning}")

    groups = payload.get("groups") if isinstance(payload.get("groups"), dict) else {}
    by_pair = groups.get("by_pair") if isinstance(groups.get("by_pair"), dict) else {}
    if not by_pair:
        warnings.append("model_resource_summary_has_no_pair_groups")
    for group_label, group in by_pair.items():
        if not isinstance(group, dict):
            continue
        orchestrator, executor = _resource_group_pair(str(group_label), group)
        record = _ensure_pair_record(
            pair_records,
            catalog,
            orchestrator,
            executor,
            source="model_resource_summary",
            tags=group.get("tags"),
            warnings=group.get("warnings"),
        )
        record["resource_metrics"] = _resource_metrics(group)


def _merge_task_correctness_summary(
    pair_records: dict[str, dict[str, Any]],
    catalog: ModelCatalog,
    payload: dict[str, Any],
    warnings: list[str],
) -> None:
    if payload.get("schema_version") != TASK_CORRECTNESS_BATCH_SUMMARY_SCHEMA_VERSION:
        warnings.append("task_correctness_summary_schema_unexpected")
    for warning in _string_list(payload.get("warnings")):
        warnings.append(f"task_correctness_summary:{warning}")

    by_pair = payload.get("by_pair") if isinstance(payload.get("by_pair"), dict) else {}
    if not by_pair:
        warnings.append("task_correctness_summary_has_no_pair_groups")
        return

    result_failure_reasons = _correctness_failure_reason_counts_by_pair(payload)
    result_warnings = _correctness_warning_counts_by_pair(payload)
    for group_label, group in by_pair.items():
        if not isinstance(group, dict):
            continue
        raw_pair_id = _optional_text(group.get("pair_id")) or _optional_text(group_label)
        orchestrator, executor = _correctness_group_pair(raw_pair_id, group)
        record = _ensure_pair_record(
            pair_records,
            catalog,
            orchestrator,
            executor,
            source="task_correctness_summary",
        )
        failure_reasons = Counter()
        if raw_pair_id:
            failure_reasons.update(result_failure_reasons.get(raw_pair_id, Counter()))
        failure_reasons.update(_failure_reason_counter(group.get("failure_reasons")))
        warning_count = sum(result_warnings.get(raw_pair_id or "", Counter()).values())
        if warning_count == 0:
            warning_count = len(_string_list(group.get("warnings")))
        record["correctness_metrics"] = _task_correctness_pair_metrics(
            raw_pair_id or record["pair_id"],
            group,
            failure_reasons=failure_reasons,
            warning_count=warning_count,
        )


def _model_entries(
    catalog: ModelCatalog,
    pair_records: dict[str, dict[str, Any]],
    resource_payload: dict[str, Any] | None,
) -> list[dict[str, Any]]:
    by_model_resource = _resource_groups_by_model(resource_payload)
    by_model_correctness = _correctness_metrics_by_model(pair_records)
    appearances: dict[str, dict[str, int]] = {}
    for record in pair_records.values():
        orchestrator = record["orchestrator_model_id"]
        executor = record["executor_model_id"]
        appearances.setdefault(orchestrator, {"as_orchestrator": 0, "as_executor": 0})
        appearances.setdefault(executor, {"as_orchestrator": 0, "as_executor": 0})
        appearances[orchestrator]["as_orchestrator"] += 1
        appearances[executor]["as_executor"] += 1

    rows: list[dict[str, Any]] = []
    for entry in sorted(catalog.models, key=lambda item: item.model_id):
        resource_group = by_model_resource.get(entry.model_id)
        rows.append(
            {
                "model_id": _safe_text(entry.model_id),
                "catalog_metadata": _catalog_entry_metadata(entry),
                "appearances": appearances.get(entry.model_id, {"as_orchestrator": 0, "as_executor": 0}),
                "resource_metrics": _resource_metrics(resource_group) if resource_group else None,
                "correctness_metrics": by_model_correctness.get(entry.model_id),
                "warnings": _model_warnings(entry),
            }
        )
    return rows


def _final_pair_entries(
    pair_records: dict[str, dict[str, Any]],
    *,
    task_correctness_summary_used: bool = False,
) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for record in pair_records.values():
        warnings = set(record.get("warnings", set()))
        if "normality_metrics" not in record:
            warnings.add("missing_normality_metrics")
        if "resource_metrics" not in record:
            warnings.add("missing_resource_metrics")
        if task_correctness_summary_used and "correctness_metrics" not in record:
            warnings.add("missing_task_correctness_metrics")
        row = {
            "pair_id": record["pair_id"],
            "pair_label": record["pair_label"],
            "orchestrator_model_id": record["orchestrator_model_id"],
            "executor_model_id": record["executor_model_id"],
            "catalog_metadata": record["catalog_metadata"],
            "sources": sorted(record.get("sources", set())),
            "tags": sorted(record.get("tags", set())),
            "notes": sorted(record.get("notes", set())),
            "plan_metadata": record.get("plan_metadata"),
            "normality_rank": record.get("normality_rank"),
            "normality_metrics": record.get("normality_metrics"),
            "resource_metrics": record.get("resource_metrics"),
            "correctness_metrics": record.get("correctness_metrics"),
            "sort_key_preview": _sort_key_preview(record),
            "warnings": sorted(warnings),
        }
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: (
            row["normality_rank"] is None,
            row["normality_rank"] or 999_999,
            row["pair_id"],
        ),
    )


def _ensure_pair_record(
    pair_records: dict[str, dict[str, Any]],
    catalog: ModelCatalog,
    orchestrator: Any,
    executor: Any,
    *,
    source: str,
    tags: Any = None,
    notes: Any = None,
    warnings: Any = None,
) -> dict[str, Any]:
    orchestrator_id, orchestrator_meta, orchestrator_warnings = _catalog_role_metadata(
        catalog,
        _optional_text(orchestrator) or "unknown_orchestrator",
        role_name="orchestrator",
    )
    executor_id, executor_meta, executor_warnings = _catalog_role_metadata(
        catalog,
        _optional_text(executor) or "unknown_executor",
        role_name="executor",
    )
    pair_id = f"{orchestrator_id}__to__{executor_id}"
    record = pair_records.setdefault(
        pair_id,
        {
            "pair_id": pair_id,
            "pair_label": f"{orchestrator_id}->{executor_id}",
            "orchestrator_model_id": orchestrator_id,
            "executor_model_id": executor_id,
            "catalog_metadata": {
                "known_catalog_pair": orchestrator_meta is not None and executor_meta is not None,
                "orchestrator": orchestrator_meta,
                "executor": executor_meta,
            },
            "sources": set(),
            "tags": set(),
            "notes": set(),
            "warnings": set(),
        },
    )
    record["sources"].add(source)
    _merge_alias_metadata(record, "orchestrator", orchestrator_meta)
    _merge_alias_metadata(record, "executor", executor_meta)
    for tag in _string_list(tags):
        record["tags"].add(tag)
    for note in _string_list(notes):
        record["notes"].add(note)
    for warning in [*orchestrator_warnings, *executor_warnings, *_string_list(warnings)]:
        record["warnings"].add(warning)
    return record


def _merge_alias_metadata(
    record: dict[str, Any],
    role_name: Literal["orchestrator", "executor"],
    metadata: dict[str, Any] | None,
) -> None:
    if not metadata or "resolved_from_alias" not in metadata:
        return
    catalog = record.get("catalog_metadata") if isinstance(record.get("catalog_metadata"), dict) else {}
    existing = catalog.get(role_name) if isinstance(catalog.get(role_name), dict) else None
    if existing is None:
        catalog[role_name] = metadata
        return
    existing["requested_model_id"] = metadata.get("requested_model_id")
    existing["resolved_from_alias"] = metadata.get("resolved_from_alias")


def _catalog_role_metadata(
    catalog: ModelCatalog,
    requested_model_id: str,
    *,
    role_name: Literal["orchestrator", "executor"],
) -> tuple[str, dict[str, Any] | None, list[str]]:
    try:
        entry = get_model_entry(catalog, requested_model_id)
    except KeyError:
        safe_id = _safe_text(requested_model_id)
        return safe_id, None, [f"model_catalog_entry_missing:{safe_id}"]

    warnings: list[str] = []
    if role_name == "orchestrator" and not entry.roles.orchestrator_candidate:
        warnings.append("orchestrator_role_not_catalog_candidate")
    if role_name == "executor" and not entry.roles.executor_candidate:
        warnings.append("executor_role_not_catalog_candidate")
    metadata = _catalog_entry_metadata(entry, requested_model_id=requested_model_id)
    return entry.model_id, metadata, warnings


def _catalog_entry_metadata(
    entry: ModelCatalogEntry,
    *,
    requested_model_id: str | None = None,
) -> dict[str, Any]:
    metadata = model_catalog_entry_metadata(entry)
    metadata["local_path"] = entry.local_path
    metadata["resource_profile"] = entry.resource_profile.model_dump(mode="json")
    metadata["historical_observations"] = list(entry.historical_observations)
    if requested_model_id is not None:
        metadata["requested_model_id"] = requested_model_id
        if requested_model_id != entry.model_id:
            metadata["resolved_from_alias"] = requested_model_id
    return _safe_value(metadata)


def _model_warnings(entry: ModelCatalogEntry) -> list[str]:
    warnings: list[str] = []
    if not entry.enabled:
        warnings.append("model_catalog_entry_disabled")
    return warnings


def _normality_ranks(payload: dict[str, Any]) -> dict[str, int]:
    ranks: dict[str, int] = {}
    leaderboard = payload.get("leaderboard")
    if not isinstance(leaderboard, list):
        return ranks
    for index, row in enumerate(leaderboard, start=1):
        if not isinstance(row, dict):
            continue
        orchestrator = row.get("orchestrator")
        executor = row.get("executor")
        if not orchestrator or not executor:
            pair_label = row.get("pair_label")
            orchestrator, executor = _pair_parts(str(pair_label)) if pair_label else (None, None)
        if orchestrator and executor:
            ranks[f"{_safe_text(str(orchestrator))}__to__{_safe_text(str(executor))}"] = index
    return ranks


def _model_pair_groups(payload: dict[str, Any]) -> dict[str, dict[str, Any]]:
    groups = payload.get("groups") if isinstance(payload.get("groups"), dict) else {}
    by_model_pair = groups.get("by_model_pair") if isinstance(groups.get("by_model_pair"), dict) else {}
    return {
        str(label): group
        for label, group in by_model_pair.items()
        if isinstance(group, dict)
    }


def _normality_group_pair(group_label: str, group: dict[str, Any]) -> tuple[str | None, str | None]:
    group_key = group.get("group_key") if isinstance(group.get("group_key"), dict) else {}
    orchestrator = _optional_text(group_key.get("orchestrator") or group.get("orchestrator"))
    executor = _optional_text(group_key.get("executor") or group.get("executor"))
    if not orchestrator or not executor:
        parsed_orchestrator, parsed_executor = _pair_parts(group_label)
        orchestrator = orchestrator or parsed_orchestrator
        executor = executor or parsed_executor
    return orchestrator, executor


def _resource_group_pair(group_label: str, group: dict[str, Any]) -> tuple[str | None, str | None]:
    group_key = _optional_text(group.get("group_key")) or group_label
    orchestrator, executor = _pair_parts(group_key)
    catalog = group.get("catalog_metadata") if isinstance(group.get("catalog_metadata"), dict) else {}
    if not orchestrator:
        orchestrator = _nested_model_id(catalog.get("orchestrator"))
    if not executor:
        executor = _nested_model_id(catalog.get("executor"))
    return orchestrator, executor


def _normality_metrics(group_label: str, group: dict[str, Any]) -> dict[str, Any]:
    return {
        "source_group_label": _safe_text(group_label),
        "entry_count": _optional_int(group.get("entry_count")),
        "evaluated_count": _optional_int(group.get("evaluated_count")),
        "failed_count": _optional_int(group.get("failed_count")),
        "mean_overall_score": _optional_float(group.get("mean_overall_score")),
        "min_overall_score": _optional_float(group.get("min_overall_score")),
        "max_overall_score": _optional_float(group.get("max_overall_score")),
        "label_counts": _safe_value(group.get("label_counts") if isinstance(group.get("label_counts"), dict) else {}),
        "status_counts": _safe_value(group.get("status_counts") if isinstance(group.get("status_counts"), dict) else {}),
        "scenario_ids": sorted(_string_list(group.get("scenario_ids"))),
        "tags": sorted(_string_list(group.get("tags"))),
        "top_findings": _safe_value(_list_of_dicts(group.get("top_findings"), limit=MAX_TOP_FINDINGS)),
    }


def _resource_metrics(group: dict[str, Any] | None) -> dict[str, Any]:
    group = group or {}
    return {
        "observation_count": _optional_int(group.get("observation_count")),
        "success_count": _optional_int(group.get("success_count")),
        "failure_count": _optional_int(group.get("failure_count")),
        "success_rate": _optional_float(group.get("success_rate")),
        "mean_wall_time_s": _optional_float(group.get("mean_wall_time_s")),
        "min_wall_time_s": _optional_float(group.get("min_wall_time_s")),
        "max_wall_time_s": _optional_float(group.get("max_wall_time_s")),
        "mean_peak_ram_gb": _optional_float(group.get("mean_peak_ram_gb")),
        "max_peak_ram_gb": _optional_float(group.get("max_peak_ram_gb")),
        "mean_peak_vram_gb": _optional_float(group.get("mean_peak_vram_gb")),
        "max_peak_vram_gb": _optional_float(group.get("max_peak_vram_gb")),
        "runtime_modes": sorted(_string_list(group.get("runtime_modes"))),
        "scenario_ids": sorted(_string_list(group.get("scenario_ids"))),
        "tags": sorted(_string_list(group.get("tags"))),
        "error_counts": _safe_value(group.get("error_counts") if isinstance(group.get("error_counts"), dict) else {}),
    }


def _resource_groups_by_model(resource_payload: dict[str, Any] | None) -> dict[str, dict[str, Any]]:
    if not resource_payload:
        return {}
    groups = resource_payload.get("groups") if isinstance(resource_payload.get("groups"), dict) else {}
    by_model = groups.get("by_model") if isinstance(groups.get("by_model"), dict) else {}
    return {
        _safe_text(str(model_id)): group
        for model_id, group in by_model.items()
        if isinstance(group, dict)
    }


def _task_correctness_global_metrics(payload: dict[str, Any]) -> dict[str, Any]:
    failure_reasons = Counter()
    for row in _correctness_result_rows(payload):
        failure_reasons.update(_failure_reason_counter(row.get("failure_reasons")))
    if not failure_reasons:
        for group in _correctness_group_rows(payload.get("by_pair")):
            failure_reasons.update(_failure_reason_counter(group.get("failure_reasons")))
    warnings = _string_list(payload.get("warnings"))
    return {
        "input_count": _optional_int(payload.get("input_count")),
        "evaluated_count": _optional_int(payload.get("evaluated_count")),
        "passed_count": _optional_int(payload.get("passed_count")),
        "failed_count": _optional_int(payload.get("failed_count")),
        "partial_count": _optional_int(payload.get("partial_count")),
        "skipped_count": _optional_int(payload.get("skipped_count")),
        "mean_correctness_score": _optional_float(payload.get("mean_correctness_score")),
        "pair_count": len(_correctness_group_rows(payload.get("by_pair"))),
        "scenario_count": len(_correctness_group_rows(payload.get("by_scenario"))),
        "by_scenario": _task_correctness_scenario_metrics(payload),
        "top_failure_reasons": _bounded_counter(
            failure_reasons,
            key_name="reason",
            limit=MAX_TOP_CORRECTNESS_FAILURE_REASONS,
        ),
        "warning_count": len(warnings),
    }


def _task_correctness_scenario_metrics(payload: dict[str, Any]) -> list[dict[str, Any]]:
    by_scenario = payload.get("by_scenario") if isinstance(payload.get("by_scenario"), dict) else {}
    rows: list[dict[str, Any]] = []
    for label, group in sorted(by_scenario.items(), key=lambda item: str(item[0])):
        if not isinstance(group, dict):
            continue
        scenario_id = _optional_text(group.get("scenario_id")) or _safe_text(str(label))
        rows.append(
            {
                "scenario_id": scenario_id,
                "input_count": _optional_int(group.get("input_count")),
                "evaluated_count": _optional_int(group.get("evaluated_count")),
                "passed_count": _optional_int(group.get("passed_count")),
                "failed_count": _optional_int(group.get("failed_count")),
                "partial_count": _optional_int(group.get("partial_count")),
                "skipped_count": _optional_int(group.get("skipped_count")),
                "pass_rate": _pass_rate(group),
                "mean_correctness_score": _optional_float(group.get("mean_correctness_score")),
                "top_failure_reasons": _bounded_counter(
                    _failure_reason_counter(group.get("failure_reasons")),
                    key_name="reason",
                    limit=MAX_TOP_CORRECTNESS_FAILURE_REASONS,
                ),
                "warning_count": len(_string_list(group.get("warnings"))),
            }
        )
        if len(rows) >= MAX_SCORECARD_SCENARIO_METRICS:
            break
    return rows


def _task_correctness_pair_metrics(
    pair_id: str,
    group: dict[str, Any],
    *,
    failure_reasons: Counter[str],
    warning_count: int,
) -> dict[str, Any]:
    return {
        "pair_id": _safe_text(pair_id),
        "evaluated_count": _optional_int(group.get("evaluated_count")),
        "passed_count": _optional_int(group.get("passed_count")),
        "failed_count": _optional_int(group.get("failed_count")),
        "partial_count": _optional_int(group.get("partial_count")),
        "skipped_count": _optional_int(group.get("skipped_count")),
        "pass_rate": _pass_rate(group),
        "mean_correctness_score": _optional_float(group.get("mean_correctness_score")),
        "top_failure_reasons": _bounded_counter(
            failure_reasons,
            key_name="reason",
            limit=MAX_TOP_CORRECTNESS_FAILURE_REASONS,
        ),
        "warning_count": max(0, warning_count),
    }


def _correctness_metrics_by_model(pair_records: dict[str, dict[str, Any]]) -> dict[str, dict[str, Any]]:
    buckets: dict[str, dict[str, Any]] = {}
    for record in pair_records.values():
        metrics = record.get("correctness_metrics")
        if not isinstance(metrics, dict):
            continue
        evaluated_count = _optional_int(metrics.get("evaluated_count")) or 0
        score = _optional_float(metrics.get("mean_correctness_score"))
        weight = evaluated_count if evaluated_count > 0 else (1 if score is not None else 0)
        for role_key, metric_key in (
            ("orchestrator_model_id", "as_orchestrator"),
            ("executor_model_id", "as_executor"),
        ):
            model_id = record.get(role_key)
            if not isinstance(model_id, str):
                continue
            bucket = buckets.setdefault(
                model_id,
                {
                    "as_orchestrator_scores": [],
                    "as_executor_scores": [],
                    "correctness_observation_count": 0,
                },
            )
            bucket["correctness_observation_count"] += evaluated_count
            if score is not None and weight > 0:
                bucket[f"{metric_key}_scores"].append((score, weight))
    return {
        model_id: {
            "as_orchestrator_correctness_mean": _weighted_mean(bucket["as_orchestrator_scores"]),
            "as_executor_correctness_mean": _weighted_mean(bucket["as_executor_scores"]),
            "correctness_observation_count": bucket["correctness_observation_count"],
        }
        for model_id, bucket in buckets.items()
    }


def _correctness_group_pair(raw_pair_id: str | None, group: dict[str, Any]) -> tuple[str | None, str | None]:
    orchestrator = _optional_text(group.get("orchestrator_model_id") or group.get("orchestrator"))
    executor = _optional_text(group.get("executor_model_id") or group.get("executor"))
    group_key = group.get("group_key") if isinstance(group.get("group_key"), dict) else {}
    orchestrator = orchestrator or _optional_text(group_key.get("orchestrator"))
    executor = executor or _optional_text(group_key.get("executor"))
    if (not orchestrator or not executor) and raw_pair_id:
        parsed_orchestrator, parsed_executor = _pair_parts(raw_pair_id)
        orchestrator = orchestrator or parsed_orchestrator
        executor = executor or parsed_executor
    return orchestrator, executor


def _correctness_failure_reason_counts_by_pair(payload: dict[str, Any]) -> dict[str, Counter[str]]:
    by_pair: dict[str, Counter[str]] = {}
    for row in _correctness_result_rows(payload):
        pair_id = _optional_text(row.get("pair_id"))
        if not pair_id:
            continue
        by_pair.setdefault(pair_id, Counter()).update(_failure_reason_counter(row.get("failure_reasons")))
    return by_pair


def _correctness_warning_counts_by_pair(payload: dict[str, Any]) -> dict[str, Counter[str]]:
    by_pair: dict[str, Counter[str]] = {}
    for row in _correctness_result_rows(payload):
        pair_id = _optional_text(row.get("pair_id"))
        if not pair_id:
            continue
        by_pair.setdefault(pair_id, Counter()).update(_string_list(row.get("warnings")))
    return by_pair


def _correctness_result_rows(payload: dict[str, Any]) -> list[dict[str, Any]]:
    results = payload.get("results")
    return [row for row in results if isinstance(row, dict)] if isinstance(results, list) else []


def _correctness_group_rows(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, dict):
        return []
    return [group for group in value.values() if isinstance(group, dict)]


def _failure_reason_counter(value: Any) -> Counter[str]:
    reasons: Counter[str] = Counter()
    if isinstance(value, dict):
        for reason, count in value.items():
            text = _optional_text(reason)
            safe_count = _optional_int(count)
            if text and safe_count is not None and safe_count > 0:
                reasons[text] += safe_count
        return reasons
    if not isinstance(value, list):
        return reasons
    for item in value:
        if isinstance(item, dict):
            reason = _optional_text(item.get("reason") or item.get("failure_reason") or item.get("message"))
            count = _optional_int(item.get("count")) or 1
        else:
            reason = _optional_text(item)
            count = 1
        if reason:
            reasons[reason] += count
    return reasons


def _bounded_counter(counter: Counter[str], *, key_name: str, limit: int) -> list[dict[str, Any]]:
    return [
        {key_name: _safe_text(name), "count": count}
        for name, count in counter.most_common(limit)
        if name
    ]


def _pass_rate(group: dict[str, Any]) -> float | None:
    explicit = _optional_float(group.get("pass_rate"))
    if explicit is not None:
        return explicit
    explicit = _optional_float(group.get("success_rate"))
    if explicit is not None:
        return explicit
    passed_count = _optional_int(group.get("passed_count"))
    evaluated_count = _optional_int(group.get("evaluated_count"))
    if passed_count is None or evaluated_count is None or evaluated_count <= 0:
        return None
    return round(passed_count / evaluated_count, 6)


def _weighted_mean(values: list[tuple[float, int]]) -> float | None:
    total_weight = sum(weight for _, weight in values)
    if total_weight <= 0:
        return None
    return round(sum(score * weight for score, weight in values) / total_weight, 6)


def _overall_summary(models: list[dict[str, Any]], pairs: list[dict[str, Any]]) -> dict[str, Any]:
    return {
        "model_count": len(models),
        "model_pair_count": len(pairs),
        "pairs_with_plan_metadata": sum(1 for pair in pairs if pair.get("plan_metadata")),
        "pairs_with_normality_metrics": sum(1 for pair in pairs if pair.get("normality_metrics")),
        "pairs_with_resource_metrics": sum(1 for pair in pairs if pair.get("resource_metrics")),
        "pairs_with_correctness_metrics": sum(1 for pair in pairs if pair.get("correctness_metrics")),
        "no_runtime_execution": True,
        "production_recommendation": False,
    }


def _sort_key_preview(record: dict[str, Any]) -> dict[str, Any]:
    normality = record.get("normality_metrics") if isinstance(record.get("normality_metrics"), dict) else {}
    resource = record.get("resource_metrics") if isinstance(record.get("resource_metrics"), dict) else {}
    correctness = record.get("correctness_metrics") if isinstance(record.get("correctness_metrics"), dict) else {}
    return {
        "normality_rank": record.get("normality_rank"),
        "normality_mean_overall_score": normality.get("mean_overall_score"),
        "resource_success_rate": resource.get("success_rate"),
        "correctness_pass_rate": correctness.get("pass_rate"),
        "correctness_mean_score": correctness.get("mean_correctness_score"),
        "not_a_production_recommendation": True,
    }


def _markdown_preview(scorecard: ModelEvaluationScorecard) -> str:
    lines = [
        "# Offline Model Evaluation Scorecard",
        "",
        "Offline synthesis of catalog, planning, normality, and resource summaries. No model execution was performed.",
        "",
        f"- status: {scorecard.status}",
        f"- models: {scorecard.model_count}",
        f"- model pairs: {scorecard.model_pair_count}",
        f"- warnings: {len(scorecard.warnings)}",
        "",
        "## Model Pairs",
        "",
        "| pair | sources | normality mean | resource success | warnings |",
        "|---|---|---:|---:|---:|",
    ]
    for pair in scorecard.model_pairs:
        normality = pair.get("normality_metrics") if isinstance(pair.get("normality_metrics"), dict) else {}
        resource = pair.get("resource_metrics") if isinstance(pair.get("resource_metrics"), dict) else {}
        lines.append(
            "| "
            f"{pair['pair_label']} | "
            f"{', '.join(pair['sources']) or 'n/a'} | "
            f"{normality.get('mean_overall_score')} | "
            f"{resource.get('success_rate')} | "
            f"{len(pair['warnings'])} |"
        )
    lines.extend(
        [
            "",
            "Prototype scorecard only; not a production recommendation.",
        ]
    )
    return "\n".join(lines) + "\n"


def _nested_model_id(value: Any) -> str | None:
    if isinstance(value, dict):
        return _optional_text(value.get("model_id"))
    return _optional_text(value)


def _pair_id_from_values(orchestrator: Any, executor: Any, pair_id: Any = None) -> str:
    orchestrator_text = _optional_text(orchestrator)
    executor_text = _optional_text(executor)
    if orchestrator_text and executor_text:
        return f"{orchestrator_text}__to__{executor_text}"
    pair_text = _optional_text(pair_id)
    if pair_text:
        left, right = _pair_parts(pair_text)
        if left and right:
            return f"{left}__to__{right}"
    return "unknown_orchestrator__to__unknown_executor"


def _pair_parts(pair_id: str | None) -> tuple[str | None, str | None]:
    if not pair_id:
        return None, None
    if "__to__" in pair_id:
        left, right = pair_id.split("__to__", 1)
        return _optional_text(left), _optional_text(right)
    if "->" in pair_id:
        left, right = pair_id.split("->", 1)
        return _optional_text(left), _optional_text(right)
    if "__" in pair_id:
        left, right = pair_id.split("__", 1)
        return _optional_text(left), _optional_text(right)
    return None, None


def _add_optional_set(items: set[str], value: Any) -> None:
    text = _optional_text(value)
    if text:
        items.add(text)


def _list_of_dicts(value: Any, *, limit: int) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [item for item in value[:limit] if isinstance(item, dict)]


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_safe_text(value)]
    if isinstance(value, list | tuple | set):
        return [_safe_text(str(item)) for item in value if item is not None]
    return [_safe_text(str(value))]


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _safe_text(str(value)).strip()
    return text or None


def _optional_float(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _optional_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _resolve_path(path: str | Path, root: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def _path_display(path: Path, root: Path) -> str | None:
    relative = _safe_relative(path, root)
    if relative is not None:
        return relative
    if _is_absolute_path(str(path)):
        return "<absolute_path>"
    return str(path)


def _safe_relative(path: Path, root: Path) -> str | None:
    try:
        return path.resolve(strict=False).relative_to(root.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return None


def _is_absolute_path(path: str) -> bool:
    return bool(
        re.match(r"^[A-Za-z]:[\\/]", path)
        or path.startswith("/")
        or path.startswith("\\\\")
    )


def _safe_value(value: Any) -> Any:
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, dict):
        return {
            _safe_text(str(key)): _safe_value(item)
            for key, item in value.items()
        }
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    return value


def _safe_text(value: str, max_chars: int = 500) -> str:
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<absolute_path>", value)
    text = re.sub(r"(?<!\w)/(?:[^\s\"']+/)+[^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"\\\\[^\s\"']+", "<absolute_path>", text)
    if len(text) > max_chars:
        return text[:max_chars] + "...[truncated]"
    return text
