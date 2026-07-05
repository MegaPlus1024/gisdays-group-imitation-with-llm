from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from pydantic import BaseModel, Field

from .model_catalog import ModelCatalog, ModelCatalogEntry, get_model_entry, load_model_catalog


NORMALITY_COMPARISON_SCHEMA_VERSION = "normality_comparison_v1"
NORMALITY_COMPARISON_SUMMARY_FILENAME = "normality_comparison_summary.json"
NORMALITY_COMPARISON_PREVIEW_FILENAME = "normality_comparison_preview.md"


class NormalityBatchSummaryLoadResult(BaseModel):
    status: Literal["ok", "input_missing", "invalid_input"]
    summary: dict[str, Any] | None = None
    input_path_display: str | None = None
    warnings: list[str] = Field(default_factory=list)


class NormalityComparisonResult(BaseModel):
    status: str
    input_summary_count: int
    valid_summary_count: int = 0
    total_entries: int = 0
    evaluated_entries: int = 0
    failed_entries: int = 0
    group_by: list[str] = Field(default_factory=lambda: ["model_pair", "scenario_id", "tag"])
    groups: dict[str, Any] = Field(default_factory=dict)
    overall: dict[str, Any] = Field(default_factory=dict)
    leaderboard: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    model_catalog_used: bool = False
    comparison_summary_path_relative: str | None = None
    markdown_preview_path_relative: str | None = None
    schema_version: str = NORMALITY_COMPARISON_SCHEMA_VERSION


def load_normality_batch_summary(
    path: str | Path,
    *,
    project_root: str | Path = Path("."),
    max_input_bytes: int = 1_000_000,
    redact_paths: bool = True,
) -> NormalityBatchSummaryLoadResult:
    root = Path(project_root)
    candidate = _resolve_path(path, root)
    display = _path_display(candidate, root, redact_paths=redact_paths)
    if not candidate.exists() or not candidate.is_file():
        return NormalityBatchSummaryLoadResult(
            status="input_missing",
            input_path_display=display,
            warnings=["summary_file_missing"],
        )
    try:
        if candidate.stat().st_size > max_input_bytes:
            return NormalityBatchSummaryLoadResult(
                status="invalid_input",
                input_path_display=display,
                warnings=["summary_file_too_large"],
            )
        text = candidate.read_text(encoding="utf-8")
    except OSError:
        return NormalityBatchSummaryLoadResult(
            status="invalid_input",
            input_path_display=display,
            warnings=["summary_file_unreadable"],
        )
    except UnicodeDecodeError:
        return NormalityBatchSummaryLoadResult(
            status="invalid_input",
            input_path_display=display,
            warnings=["summary_file_not_utf8_text"],
        )
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return NormalityBatchSummaryLoadResult(
            status="invalid_input",
            input_path_display=display,
            warnings=["summary_json_decode_error"],
        )
    if not isinstance(payload, dict):
        return NormalityBatchSummaryLoadResult(
            status="invalid_input",
            input_path_display=display,
            warnings=["summary_payload_not_object"],
        )
    entries = payload.get("entries")
    if not isinstance(entries, list):
        return NormalityBatchSummaryLoadResult(
            status="invalid_input",
            input_path_display=display,
            warnings=["summary_entries_not_list"],
        )
    return NormalityBatchSummaryLoadResult(
        status="ok",
        summary=payload,
        input_path_display=display,
    )


def compare_normality_batch_summaries(
    paths: list[str | Path],
    *,
    project_root: str | Path = Path("."),
    max_input_bytes: int = 1_000_000,
    redact_paths: bool = True,
    model_catalog: ModelCatalog | str | Path | None = None,
) -> NormalityComparisonResult:
    root = Path(project_root)
    catalog = _load_optional_model_catalog(model_catalog, project_root=root)
    valid_summaries: list[dict[str, Any]] = []
    warnings: list[str] = []
    for path in paths:
        loaded = load_normality_batch_summary(
            path,
            project_root=root,
            max_input_bytes=max_input_bytes,
            redact_paths=redact_paths,
        )
        if loaded.status != "ok" or loaded.summary is None:
            display = loaded.input_path_display or "<unknown_summary>"
            for warning in loaded.warnings:
                warnings.append(f"summary_load_failed:{display}:{warning}")
            continue
        valid_summaries.append(loaded.summary)

    entries = [_safe_entry(row) for summary in valid_summaries for row in _entry_rows(summary)]
    evaluated_entries = [entry for entry in entries if _is_evaluated_entry(entry)]
    failed_entries = len(entries) - len(evaluated_entries)
    groups = {
        "by_model_pair": _groups_by_model_pair(entries),
        "by_scenario_id": _groups_by_scenario_id(entries),
        "by_tag": _groups_by_tag(entries),
    }
    if catalog is not None:
        warnings.extend(_enrich_model_pair_groups_with_catalog(groups["by_model_pair"], catalog))
    leaderboard = _leaderboard(groups["by_model_pair"])
    status = "ok" if valid_summaries and evaluated_entries else "invalid_input"
    return NormalityComparisonResult(
        status=status,
        input_summary_count=len(paths),
        valid_summary_count=len(valid_summaries),
        total_entries=len(entries),
        evaluated_entries=len(evaluated_entries),
        failed_entries=failed_entries,
        groups=groups,
        overall=_group_metrics("overall", entries),
        leaderboard=leaderboard,
        warnings=sorted(set(warnings)),
        model_catalog_used=catalog is not None,
    )


def write_normality_comparison_summary(
    result: NormalityComparisonResult,
    output_dir: str | Path,
    *,
    write_markdown: bool = False,
) -> tuple[Path, Path | None]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    result.comparison_summary_path_relative = NORMALITY_COMPARISON_SUMMARY_FILENAME
    markdown_path: Path | None = None
    if write_markdown:
        result.markdown_preview_path_relative = NORMALITY_COMPARISON_PREVIEW_FILENAME
    summary_path = out_dir / NORMALITY_COMPARISON_SUMMARY_FILENAME
    summary_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    if write_markdown:
        markdown_path = out_dir / NORMALITY_COMPARISON_PREVIEW_FILENAME
        markdown_path.write_text(_markdown_preview(result), encoding="utf-8")
    return summary_path, markdown_path


def _entry_rows(summary: dict[str, Any]) -> list[dict[str, Any]]:
    entries = summary.get("entries")
    return [entry for entry in entries if isinstance(entry, dict)] if isinstance(entries, list) else []


def _safe_entry(entry: dict[str, Any]) -> dict[str, Any]:
    model_pair = entry.get("model_pair") if isinstance(entry.get("model_pair"), dict) else {}
    return {
        "scenario_id": _optional_text(entry.get("scenario_id")),
        "trial_id": _optional_text(entry.get("trial_id")),
        "model_pair": {
            "orchestrator": _optional_text(model_pair.get("orchestrator")),
            "executor": _optional_text(model_pair.get("executor")),
        },
        "tags": _string_list(entry.get("tags")),
        "status": _optional_text(entry.get("status")) or "unknown",
        "label": _optional_text(entry.get("label")),
        "overall_score": _optional_score(entry.get("overall_score")),
        "findings": _string_list(entry.get("findings")),
        "warnings": _string_list(entry.get("warnings")),
    }


def _groups_by_model_pair(entries: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        pair = _model_pair_key(entry)
        buckets.setdefault(pair["pair_label"], []).append(entry)
    return {
        label: _group_metrics(label, rows, group_key=_model_pair_key(rows[0]))
        for label, rows in sorted(buckets.items())
    }


def _groups_by_scenario_id(entries: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        label = entry.get("scenario_id") or "unknown_scenario"
        buckets.setdefault(label, []).append(entry)
    return {
        label: _group_metrics(label, rows, group_key={"scenario_id": label})
        for label, rows in sorted(buckets.items())
    }


def _groups_by_tag(entries: list[dict[str, Any]]) -> dict[str, Any]:
    buckets: dict[str, list[dict[str, Any]]] = {}
    for entry in entries:
        tags = entry.get("tags") or ["untagged"]
        for tag in tags:
            buckets.setdefault(tag, []).append(entry)
    return {
        label: _group_metrics(label, rows, group_key={"tag": label})
        for label, rows in sorted(buckets.items())
    }


def _group_metrics(
    label: str,
    entries: list[dict[str, Any]],
    *,
    group_key: dict[str, Any] | None = None,
) -> dict[str, Any]:
    scores = [entry["overall_score"] for entry in entries if _is_evaluated_entry(entry)]
    labels = Counter(entry["label"] for entry in entries if entry.get("label"))
    statuses = Counter(entry["status"] for entry in entries)
    findings: Counter[str] = Counter()
    trial_ids: set[str] = set()
    scenario_ids: set[str] = set()
    tags: set[str] = set()
    model_pairs: set[str] = set()
    for entry in entries:
        findings.update(entry.get("findings") or [])
        if entry.get("trial_id"):
            trial_ids.add(entry["trial_id"])
        if entry.get("scenario_id"):
            scenario_ids.add(entry["scenario_id"])
        tags.update(entry.get("tags") or [])
        model_pairs.add(_model_pair_key(entry)["pair_label"])
    evaluated_count = len(scores)
    return {
        "group_label": label,
        "group_key": group_key or {"label": label},
        "entry_count": len(entries),
        "evaluated_count": evaluated_count,
        "failed_count": len(entries) - evaluated_count,
        "mean_overall_score": mean(scores) if scores else None,
        "min_overall_score": min(scores) if scores else None,
        "max_overall_score": max(scores) if scores else None,
        "label_counts": dict(labels),
        "status_counts": dict(statuses),
        "top_findings": _top_counts(findings),
        "trial_ids": sorted(trial_ids),
        "scenario_ids": sorted(scenario_ids),
        "tags": sorted(tags),
        "model_pairs": sorted(model_pairs),
    }


def _leaderboard(model_pair_groups: dict[str, Any]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for label, group in model_pair_groups.items():
        row = {
            "pair_label": label,
            "orchestrator": group.get("group_key", {}).get("orchestrator"),
            "executor": group.get("group_key", {}).get("executor"),
            "entry_count": group["entry_count"],
            "evaluated_count": group["evaluated_count"],
            "failed_count": group["failed_count"],
            "mean_overall_score": group["mean_overall_score"],
            "min_overall_score": group["min_overall_score"],
            "max_overall_score": group["max_overall_score"],
            "label_counts": group["label_counts"],
            "status_counts": group["status_counts"],
            "suspicious_count": group["label_counts"].get("suspicious", 0),
            "abnormal_count": group["label_counts"].get("abnormal", 0),
            "note": "Offline normality comparison; prototype metric, not a production ranking.",
        }
        if "catalog_metadata" in group:
            row["catalog_metadata"] = group["catalog_metadata"]
        rows.append(row)
    return sorted(
        rows,
        key=lambda row: (
            row["mean_overall_score"] is not None,
            row["mean_overall_score"] or -1.0,
            row["evaluated_count"],
            -row["failed_count"],
            row["pair_label"],
        ),
        reverse=True,
    )


def _model_pair_key(entry: dict[str, Any]) -> dict[str, str | None]:
    pair = entry.get("model_pair") if isinstance(entry.get("model_pair"), dict) else {}
    orchestrator = pair.get("orchestrator") or "unknown_orchestrator"
    executor = pair.get("executor") or "unknown_executor"
    return {
        "orchestrator": orchestrator,
        "executor": executor,
        "pair_label": f"{orchestrator}->{executor}",
    }


def _load_optional_model_catalog(
    model_catalog: ModelCatalog | str | Path | None,
    *,
    project_root: Path,
) -> ModelCatalog | None:
    if model_catalog is None:
        return None
    if isinstance(model_catalog, ModelCatalog):
        return model_catalog
    return load_model_catalog(_resolve_path(model_catalog, project_root))


def _enrich_model_pair_groups_with_catalog(
    model_pair_groups: dict[str, Any],
    catalog: ModelCatalog,
) -> list[str]:
    warnings: list[str] = []
    for label, group in model_pair_groups.items():
        group_key = group.get("group_key") if isinstance(group.get("group_key"), dict) else {}
        pair_metadata, pair_warnings = _catalog_pair_metadata(
            catalog,
            orchestrator_id=_optional_text(group_key.get("orchestrator")) or "unknown_orchestrator",
            executor_id=_optional_text(group_key.get("executor")) or "unknown_executor",
        )
        group["catalog_metadata"] = pair_metadata
        warnings.extend(f"{warning}:{label}" for warning in pair_warnings)
    return warnings


def _catalog_pair_metadata(
    catalog: ModelCatalog,
    *,
    orchestrator_id: str,
    executor_id: str,
) -> tuple[dict[str, Any], list[str]]:
    orchestrator, orchestrator_warnings = _catalog_role_metadata(
        catalog,
        requested_model_id=orchestrator_id,
        role_name="orchestrator",
    )
    executor, executor_warnings = _catalog_role_metadata(
        catalog,
        requested_model_id=executor_id,
        role_name="executor",
    )
    warnings = sorted(set([*orchestrator_warnings, *executor_warnings]))
    orchestrator_pair_id = orchestrator["model_id"] if orchestrator is not None else orchestrator_id
    executor_pair_id = executor["model_id"] if executor is not None else executor_id
    notes = _catalog_pair_notes(orchestrator, executor)
    return (
        {
            "pair_id": f"{orchestrator_pair_id}__to__{executor_pair_id}",
            "known_catalog_pair": orchestrator is not None and executor is not None,
            "orchestrator": orchestrator,
            "executor": executor,
            "notes": notes,
            "warnings": warnings,
        },
        warnings,
    )


def _catalog_role_metadata(
    catalog: ModelCatalog,
    *,
    requested_model_id: str,
    role_name: Literal["orchestrator", "executor"],
) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        entry = get_model_entry(catalog, requested_model_id)
    except KeyError:
        return None, ["model_catalog_entry_missing"]

    warnings: list[str] = []
    if role_name == "orchestrator" and not entry.roles.orchestrator_candidate:
        warnings.append("orchestrator_role_not_catalog_candidate")
    if role_name == "executor" and not entry.roles.executor_candidate:
        warnings.append("executor_role_not_catalog_candidate")
    return _catalog_entry_metadata(entry, requested_model_id=requested_model_id), warnings


def _catalog_entry_metadata(entry: ModelCatalogEntry, *, requested_model_id: str) -> dict[str, Any]:
    metadata: dict[str, Any] = {
        "model_id": _safe_text(entry.model_id),
        "display_name": _safe_text(entry.display_name),
        "upstream_name": _safe_text(entry.upstream_name),
        "family": _safe_text(entry.family),
        "parameter_count_b": entry.parameter_count_b,
        "quantization": _safe_text(entry.quantization),
        "local_path": _safe_text(entry.local_path),
        "roles": entry.roles.model_dump(mode="json"),
        "tags": [_safe_text(tag) for tag in entry.tags],
        "requested_model_id": _safe_text(requested_model_id),
    }
    if requested_model_id != entry.model_id:
        metadata["resolved_from_alias"] = _safe_text(requested_model_id)
    if entry.historical_observations:
        metadata["notes"] = [_safe_text(note) for note in entry.historical_observations]
    return metadata


def _catalog_pair_notes(
    orchestrator: dict[str, Any] | None,
    executor: dict[str, Any] | None,
) -> list[str]:
    notes: list[str] = []
    if orchestrator is not None:
        notes.extend(f"orchestrator:{note}" for note in orchestrator.get("notes", []))
    if executor is not None:
        notes.extend(f"executor:{note}" for note in executor.get("notes", []))
    return notes


def _is_evaluated_entry(entry: dict[str, Any]) -> bool:
    return entry.get("status") == "ok" and isinstance(entry.get("overall_score"), float)


def _top_counts(counter: Counter[str], limit: int = 10) -> list[dict[str, Any]]:
    return [
        {"finding": name, "count": count}
        for name, count in counter.most_common(limit)
    ]


def _markdown_preview(result: NormalityComparisonResult) -> str:
    lines = [
        "# Offline Normality Comparison",
        "",
        "Prototype metric summary; not a production ranking.",
        "",
        f"- status: {result.status}",
        f"- input summaries: {result.input_summary_count}",
        f"- total entries: {result.total_entries}",
        f"- evaluated entries: {result.evaluated_entries}",
        f"- failed entries: {result.failed_entries}",
        "",
        "## Model Pair Leaderboard",
        "",
    ]
    if result.model_catalog_used:
        lines.extend(
            [
                "Catalog metadata is descriptive only and not a production recommendation.",
                "",
            ]
        )
    if not result.leaderboard:
        lines.append("- no evaluated model pairs")
    for row in result.leaderboard:
        catalog = row.get("catalog_metadata") if isinstance(row.get("catalog_metadata"), dict) else None
        catalog_label = _catalog_markdown_label(catalog) if catalog is not None else None
        catalog_suffix = f", catalog={catalog_label}" if catalog_label else ""
        warning_count = len(catalog.get("warnings", [])) if catalog is not None else 0
        warning_suffix = f", catalog_warnings={warning_count}" if catalog is not None else ""
        lines.append(
            f"- {row['pair_label']}: mean={row['mean_overall_score']}, "
            f"evaluated={row['evaluated_count']}, failed={row['failed_count']}"
            f"{catalog_suffix}{warning_suffix}"
        )
    return "\n".join(lines) + "\n"


def _catalog_markdown_label(catalog: dict[str, Any] | None) -> str | None:
    if catalog is None:
        return None
    orchestrator = catalog.get("orchestrator") if isinstance(catalog.get("orchestrator"), dict) else None
    executor = catalog.get("executor") if isinstance(catalog.get("executor"), dict) else None
    return f"{_catalog_role_markdown_label(orchestrator)} -> {_catalog_role_markdown_label(executor)}"


def _catalog_role_markdown_label(metadata: dict[str, Any] | None) -> str:
    if metadata is None:
        return "unknown"
    family = metadata.get("family") or "unknown_family"
    params = metadata.get("parameter_count_b")
    params_label = f"{params}B" if params is not None else "unknown_params"
    quantization = metadata.get("quantization") or "unknown_quant"
    return f"{family}/{params_label}/{quantization}"


def _resolve_path(path: str | Path, root: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def _path_display(path: Path, root: Path, *, redact_paths: bool) -> str | None:
    relative = _safe_relative(path, root)
    if relative is not None:
        return relative
    if redact_paths and _is_absolute_path(str(path)):
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


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _safe_text(str(value)).strip()
    return text or None


def _optional_score(value: Any) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        score = float(value)
        return score if 0.0 <= score <= 1.0 else None
    return None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_safe_text(value)]
    if isinstance(value, list):
        return [_safe_text(str(item)) for item in value if item is not None]
    return [_safe_text(str(value))]


def _safe_text(value: str, max_chars: int = 500) -> str:
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<absolute_path>", value)
    text = re.sub(r"(?<!\w)/(?:[^\s\"']+/)+[^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"\\\\[^\s\"']+", "<absolute_path>", text)
    if len(text) > max_chars:
        return text[:max_chars] + "...[truncated]"
    return text
