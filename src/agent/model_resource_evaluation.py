from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from pydantic import BaseModel, Field

from .model_catalog import ModelCatalog, ModelCatalogEntry, get_model_entry, load_model_catalog


MODEL_RESOURCE_SUMMARY_SCHEMA_VERSION = "model_resource_summary_v1"
MODEL_RESOURCE_SUMMARY_FILENAME = "model_resource_summary.json"


class ModelResourceObservation(BaseModel):
    observation_id: str
    model_id: str | None = None
    orchestrator_model_id: str | None = None
    executor_model_id: str | None = None
    pair_id: str | None = None
    scenario_id: str | None = None
    trial_id: str | None = None
    runtime_mode: str | None = "unknown"
    backend: str | None = "unknown"
    success: bool | None = None
    error_code: str | None = None
    wall_time_s: float | None = None
    peak_ram_gb: float | None = None
    peak_vram_gb: float | None = None
    prompt_tokens: int | None = None
    completion_tokens: int | None = None
    total_tokens: int | None = None
    concurrency: int | None = None
    notes: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)


class ModelResourceObservationLoadResult(BaseModel):
    status: Literal["ok", "input_missing", "invalid_input"]
    input_path_display: str | None = None
    observations: list[ModelResourceObservation] = Field(default_factory=list)
    invalid_count: int = 0
    warnings: list[str] = Field(default_factory=list)


class ModelResourceGroupSummary(BaseModel):
    group_key: str
    group_type: Literal["model", "pair", "runtime_mode", "scenario"]
    observation_count: int
    success_count: int
    failure_count: int
    success_rate: float | None
    mean_wall_time_s: float | None = None
    min_wall_time_s: float | None = None
    max_wall_time_s: float | None = None
    mean_peak_ram_gb: float | None = None
    max_peak_ram_gb: float | None = None
    mean_peak_vram_gb: float | None = None
    max_peak_vram_gb: float | None = None
    runtime_modes: list[str] = Field(default_factory=list)
    scenario_ids: list[str] = Field(default_factory=list)
    tags: list[str] = Field(default_factory=list)
    error_counts: dict[str, int] = Field(default_factory=dict)
    catalog_metadata: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)


class ModelResourceSummary(BaseModel):
    status: str
    input_count: int
    observation_count: int
    invalid_count: int
    groups: dict[str, dict[str, ModelResourceGroupSummary]]
    catalog_metadata: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    summary_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    summary_path_relative: str | None = None
    schema_version: str = MODEL_RESOURCE_SUMMARY_SCHEMA_VERSION


def load_model_resource_observations_from_file(
    path: str | Path,
    *,
    project_root: str | Path = Path("."),
    max_input_bytes: int = 1_000_000,
) -> ModelResourceObservationLoadResult:
    root = Path(project_root)
    candidate = _resolve_path(path, root)
    display = _path_display(candidate, root)
    if not candidate.exists() or not candidate.is_file():
        return ModelResourceObservationLoadResult(
            status="input_missing",
            input_path_display=display,
            warnings=["resource_observation_file_missing"],
        )
    try:
        if candidate.stat().st_size > max_input_bytes:
            return ModelResourceObservationLoadResult(
                status="invalid_input",
                input_path_display=display,
                invalid_count=1,
                warnings=["resource_observation_file_too_large"],
            )
        text = candidate.read_text(encoding="utf-8")
    except OSError:
        return ModelResourceObservationLoadResult(
            status="invalid_input",
            input_path_display=display,
            invalid_count=1,
            warnings=["resource_observation_file_unreadable"],
        )
    except UnicodeDecodeError:
        return ModelResourceObservationLoadResult(
            status="invalid_input",
            input_path_display=display,
            invalid_count=1,
            warnings=["resource_observation_file_not_utf8_text"],
        )

    if candidate.suffix.lower() == ".jsonl":
        return _load_jsonl_observations(text, display)
    return _load_json_observations(text, display)


def summarize_model_resource_observations(
    observations: list[ModelResourceObservation | dict[str, Any]],
    *,
    model_catalog: ModelCatalog | str | Path | None = None,
    summary_id: str | None = None,
    input_count: int = 1,
    invalid_count: int = 0,
    tags: list[str] | None = None,
    warnings: list[str] | None = None,
) -> ModelResourceSummary:
    catalog = _load_optional_catalog(model_catalog)
    normalized: list[ModelResourceObservation] = []
    summary_warnings = list(warnings or [])
    skipped_invalid = 0
    for index, item in enumerate(observations, start=1):
        obs, obs_warnings = _coerce_observation(item, index=index)
        summary_warnings.extend(obs_warnings)
        if obs is None:
            skipped_invalid += 1
            continue
        normalized.append(obs)

    groups = {
        "by_model": _group_by_model(normalized, catalog, summary_warnings),
        "by_pair": _group_by_pair(normalized, catalog, summary_warnings),
        "by_runtime_mode": _group_by_runtime_mode(normalized),
        "by_scenario": _group_by_scenario(normalized),
    }
    return ModelResourceSummary(
        status="ok" if normalized else "invalid_input",
        input_count=input_count,
        observation_count=len(normalized),
        invalid_count=invalid_count + skipped_invalid,
        groups=groups,
        catalog_metadata=_catalog_summary(catalog) if catalog is not None else None,
        warnings=sorted(set(summary_warnings)),
        summary_id=summary_id,
        tags=sorted(set(tags or [])),
    )


def write_model_resource_summary(
    summary: ModelResourceSummary,
    output_dir: str | Path,
) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / MODEL_RESOURCE_SUMMARY_FILENAME
    summary.summary_path_relative = MODEL_RESOURCE_SUMMARY_FILENAME
    path.write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def run_model_resource_evaluation(
    input_paths: list[str | Path],
    output_dir: str | Path,
    *,
    model_catalog: ModelCatalog | str | Path | None = None,
    summary_id: str | None = None,
    tags: list[str] | None = None,
    project_root: str | Path = Path("."),
) -> ModelResourceSummary:
    observations: list[ModelResourceObservation] = []
    warnings: list[str] = []
    invalid_count = 0
    for path in input_paths:
        loaded = load_model_resource_observations_from_file(path, project_root=project_root)
        observations.extend(loaded.observations)
        invalid_count += loaded.invalid_count
        warnings.extend(f"{loaded.input_path_display or '<input>'}:{warning}" for warning in loaded.warnings)
    summary = summarize_model_resource_observations(
        observations,
        model_catalog=model_catalog,
        summary_id=summary_id,
        input_count=len(input_paths),
        invalid_count=invalid_count,
        tags=tags,
        warnings=warnings,
    )
    write_model_resource_summary(summary, output_dir)
    return summary


def _load_json_observations(text: str, display: str | None) -> ModelResourceObservationLoadResult:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return ModelResourceObservationLoadResult(
            status="invalid_input",
            input_path_display=display,
            invalid_count=1,
            warnings=["resource_observation_json_decode_error"],
        )
    rows, warnings = _observation_rows(payload)
    return _normalize_rows(rows, display=display, warnings=warnings)


def _load_jsonl_observations(text: str, display: str | None) -> ModelResourceObservationLoadResult:
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    invalid_count = 0
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError:
            invalid_count += 1
            warnings.append(f"jsonl_decode_error_line_{line_number}")
            continue
        if isinstance(payload, dict):
            rows.append(payload)
        else:
            invalid_count += 1
            warnings.append(f"jsonl_observation_not_object_line_{line_number}")
    result = _normalize_rows(rows, display=display, warnings=warnings)
    result.invalid_count += invalid_count
    if result.status != "ok" and invalid_count:
        result.status = "invalid_input"
    return result


def _observation_rows(payload: Any) -> tuple[list[dict[str, Any]], list[str]]:
    if isinstance(payload, list):
        return [row for row in payload if isinstance(row, dict)], [
            f"observation_not_object_index_{index}"
            for index, row in enumerate(payload)
            if not isinstance(row, dict)
        ]
    if isinstance(payload, dict):
        for key in ("observations", "resource_observations", "records"):
            rows = payload.get(key)
            if isinstance(rows, list):
                return [row for row in rows if isinstance(row, dict)], [
                    f"observation_not_object_index_{index}"
                    for index, row in enumerate(rows)
                    if not isinstance(row, dict)
                ]
    return [], ["resource_observation_payload_has_no_records"]


def _normalize_rows(
    rows: list[dict[str, Any]],
    *,
    display: str | None,
    warnings: list[str],
) -> ModelResourceObservationLoadResult:
    observations: list[ModelResourceObservation] = []
    invalid_count = 0
    out_warnings = list(warnings)
    for index, row in enumerate(rows, start=1):
        obs, obs_warnings = _observation_from_payload(row, index=index)
        out_warnings.extend(obs_warnings)
        if obs is None:
            invalid_count += 1
            continue
        observations.append(obs)
    status: Literal["ok", "input_missing", "invalid_input"] = "ok" if observations else "invalid_input"
    return ModelResourceObservationLoadResult(
        status=status,
        input_path_display=display,
        observations=observations,
        invalid_count=invalid_count + len(warnings),
        warnings=sorted(set(out_warnings)),
    )


def _coerce_observation(
    item: ModelResourceObservation | dict[str, Any],
    *,
    index: int,
) -> tuple[ModelResourceObservation | None, list[str]]:
    if isinstance(item, ModelResourceObservation):
        payload = item.model_dump(mode="json")
    else:
        payload = item
    return _observation_from_payload(payload, index=index)


def _observation_from_payload(
    payload: dict[str, Any],
    *,
    index: int,
) -> tuple[ModelResourceObservation | None, list[str]]:
    warnings: list[str] = []
    model_id = _optional_text(_first_value(payload, "model_id", "model"))
    orchestrator = _optional_text(_first_value(payload, "orchestrator_model_id", "orchestrator"))
    executor = _optional_text(_first_value(payload, "executor_model_id", "executor"))
    pair_id = _optional_text(payload.get("pair_id"))
    if pair_id is None and orchestrator and executor:
        pair_id = f"{orchestrator}__to__{executor}"
    if pair_id and (not orchestrator or not executor):
        parsed_orchestrator, parsed_executor = _pair_parts(pair_id)
        orchestrator = orchestrator or parsed_orchestrator
        executor = executor or parsed_executor
    if not any([model_id, pair_id, orchestrator, executor]):
        return None, ["observation_missing_model_or_pair"]

    metrics, metric_warnings = _normalized_metrics(payload)
    warnings.extend(metric_warnings)
    if metric_warnings:
        return None, warnings

    observation_id = _optional_text(payload.get("observation_id")) or f"observation_{index:03d}"
    success = _optional_success(payload.get("success"), payload.get("status"))
    try:
        return (
            ModelResourceObservation(
                observation_id=observation_id,
                model_id=model_id,
                orchestrator_model_id=orchestrator,
                executor_model_id=executor,
                pair_id=pair_id,
                scenario_id=_optional_text(payload.get("scenario_id")),
                trial_id=_optional_text(payload.get("trial_id")),
                runtime_mode=_optional_text(payload.get("runtime_mode")) or "unknown",
                backend=_optional_text(payload.get("backend")) or "unknown",
                success=success,
                error_code=_optional_text(_first_value(payload, "error_code", "error_type", "error")),
                notes=_string_list(payload.get("notes")),
                tags=_string_list(payload.get("tags")),
                **metrics,
            ),
            warnings,
        )
    except ValueError:
        return None, [*warnings, "observation_validation_failed"]


def _normalized_metrics(payload: dict[str, Any]) -> tuple[dict[str, Any], list[str]]:
    warnings: list[str] = []
    metrics = {
        "wall_time_s": _optional_float(_first_value(payload, "wall_time_s", "duration_s", "wall_time_seconds")),
        "peak_ram_gb": _optional_float(_first_value(payload, "peak_ram_gb", "ram_peak_gb")),
        "peak_vram_gb": _optional_float(_first_value(payload, "peak_vram_gb", "vram_peak_gb")),
        "prompt_tokens": _optional_int(payload.get("prompt_tokens")),
        "completion_tokens": _optional_int(payload.get("completion_tokens")),
        "total_tokens": _optional_int(payload.get("total_tokens")),
        "concurrency": _optional_int(payload.get("concurrency")),
    }
    wall_time_ms = _optional_float(payload.get("wall_time_ms"))
    peak_ram_mb = _optional_float(payload.get("peak_ram_mb"))
    peak_vram_mb = _optional_float(payload.get("peak_vram_mb"))
    if metrics["wall_time_s"] is None and wall_time_ms is not None:
        metrics["wall_time_s"] = wall_time_ms / 1000.0
    if metrics["peak_ram_gb"] is None and peak_ram_mb is not None:
        metrics["peak_ram_gb"] = peak_ram_mb / 1024.0
    if metrics["peak_vram_gb"] is None and peak_vram_mb is not None:
        metrics["peak_vram_gb"] = peak_vram_mb / 1024.0

    for key, value in metrics.items():
        if value is not None and value < 0:
            warnings.append(f"negative_metric_rejected:{key}")
    if metrics.get("concurrency") is not None and metrics["concurrency"] == 0:
        warnings.append("negative_metric_rejected:concurrency")
    return metrics, warnings


def _group_by_model(
    observations: list[ModelResourceObservation],
    catalog: ModelCatalog | None,
    warnings: list[str],
) -> dict[str, ModelResourceGroupSummary]:
    buckets: dict[str, list[ModelResourceObservation]] = {}
    for obs in observations:
        for model_id in _model_ids_for_observation(obs):
            buckets.setdefault(model_id, []).append(obs)
    groups = {
        key: _group_summary(key, "model", rows)
        for key, rows in sorted(buckets.items())
    }
    if catalog is not None:
        for key, group in groups.items():
            group.catalog_metadata, group_warnings = _catalog_model_metadata(catalog, key)
            group.warnings = sorted(set([*group.warnings, *group_warnings]))
            warnings.extend(f"{warning}:{key}" for warning in group_warnings)
    return groups


def _group_by_pair(
    observations: list[ModelResourceObservation],
    catalog: ModelCatalog | None,
    warnings: list[str],
) -> dict[str, ModelResourceGroupSummary]:
    buckets: dict[str, list[ModelResourceObservation]] = {}
    for obs in observations:
        if obs.pair_id:
            buckets.setdefault(obs.pair_id, []).append(obs)
    groups = {
        key: _group_summary(key, "pair", rows)
        for key, rows in sorted(buckets.items())
    }
    if catalog is not None:
        for key, group in groups.items():
            group.catalog_metadata, group_warnings = _catalog_pair_metadata(catalog, key)
            group.warnings = sorted(set([*group.warnings, *group_warnings]))
            warnings.extend(f"{warning}:{key}" for warning in group_warnings)
    return groups


def _group_by_runtime_mode(observations: list[ModelResourceObservation]) -> dict[str, ModelResourceGroupSummary]:
    buckets: dict[str, list[ModelResourceObservation]] = {}
    for obs in observations:
        buckets.setdefault(obs.runtime_mode or "unknown", []).append(obs)
    return {
        key: _group_summary(key, "runtime_mode", rows)
        for key, rows in sorted(buckets.items())
    }


def _group_by_scenario(observations: list[ModelResourceObservation]) -> dict[str, ModelResourceGroupSummary]:
    buckets: dict[str, list[ModelResourceObservation]] = {}
    for obs in observations:
        buckets.setdefault(obs.scenario_id or "unknown_scenario", []).append(obs)
    return {
        key: _group_summary(key, "scenario", rows)
        for key, rows in sorted(buckets.items())
    }


def _group_summary(
    key: str,
    group_type: Literal["model", "pair", "runtime_mode", "scenario"],
    rows: list[ModelResourceObservation],
) -> ModelResourceGroupSummary:
    successes = [row for row in rows if row.success is True]
    failures = [row for row in rows if row.success is False]
    denominator = len(successes) + len(failures)
    wall_times = [row.wall_time_s for row in rows if row.wall_time_s is not None]
    peak_ram = [row.peak_ram_gb for row in rows if row.peak_ram_gb is not None]
    peak_vram = [row.peak_vram_gb for row in rows if row.peak_vram_gb is not None]
    error_counts = Counter(row.error_code for row in rows if row.error_code)
    return ModelResourceGroupSummary(
        group_key=key,
        group_type=group_type,
        observation_count=len(rows),
        success_count=len(successes),
        failure_count=len(failures),
        success_rate=(len(successes) / denominator) if denominator else None,
        mean_wall_time_s=mean(wall_times) if wall_times else None,
        min_wall_time_s=min(wall_times) if wall_times else None,
        max_wall_time_s=max(wall_times) if wall_times else None,
        mean_peak_ram_gb=mean(peak_ram) if peak_ram else None,
        max_peak_ram_gb=max(peak_ram) if peak_ram else None,
        mean_peak_vram_gb=mean(peak_vram) if peak_vram else None,
        max_peak_vram_gb=max(peak_vram) if peak_vram else None,
        runtime_modes=sorted({row.runtime_mode or "unknown" for row in rows}),
        scenario_ids=sorted({row.scenario_id for row in rows if row.scenario_id}),
        tags=sorted({tag for row in rows for tag in row.tags}),
        error_counts=dict(error_counts),
    )


def _model_ids_for_observation(obs: ModelResourceObservation) -> list[str]:
    ids: list[str] = []
    if obs.model_id:
        ids.append(obs.model_id)
    if obs.orchestrator_model_id:
        ids.append(obs.orchestrator_model_id)
    if obs.executor_model_id:
        ids.append(obs.executor_model_id)
    if obs.pair_id:
        orchestrator, executor = _pair_parts(obs.pair_id)
        ids.extend([item for item in (orchestrator, executor) if item])
    return sorted(set(ids))


def _catalog_model_metadata(catalog: ModelCatalog, model_id: str) -> tuple[dict[str, Any] | None, list[str]]:
    try:
        entry = get_model_entry(catalog, model_id)
    except KeyError:
        return None, ["model_catalog_entry_missing"]
    return _safe_catalog_entry(entry), []


def _catalog_pair_metadata(catalog: ModelCatalog, pair_id: str) -> tuple[dict[str, Any], list[str]]:
    orchestrator_id, executor_id = _pair_parts(pair_id)
    warnings: list[str] = []
    orchestrator, orchestrator_warnings = _catalog_model_metadata(catalog, orchestrator_id or "unknown_orchestrator")
    executor, executor_warnings = _catalog_model_metadata(catalog, executor_id or "unknown_executor")
    warnings.extend(orchestrator_warnings)
    warnings.extend(executor_warnings)
    return (
        {
            "pair_id": pair_id,
            "orchestrator": orchestrator,
            "executor": executor,
            "known_catalog_pair": orchestrator is not None and executor is not None,
        },
        sorted(set(warnings)),
    )


def _safe_catalog_entry(entry: ModelCatalogEntry) -> dict[str, Any]:
    return {
        "model_id": _safe_text(entry.model_id),
        "family": _safe_text(entry.family),
        "parameter_count_b": entry.parameter_count_b,
        "quantization": _safe_text(entry.quantization),
        "roles": entry.roles.model_dump(mode="json"),
        "tags": [_safe_text(tag) for tag in entry.tags],
        "local_path": _safe_text(entry.local_path),
    }


def _catalog_summary(catalog: ModelCatalog) -> dict[str, Any]:
    return {
        "schema_version": catalog.schema_version,
        "model_count": len(catalog.models),
        "models": [_safe_catalog_entry(entry) for entry in catalog.models],
    }


def _load_optional_catalog(model_catalog: ModelCatalog | str | Path | None) -> ModelCatalog | None:
    if model_catalog is None:
        return None
    if isinstance(model_catalog, ModelCatalog):
        return model_catalog
    return load_model_catalog(model_catalog)


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


def _optional_success(success: Any, status: Any) -> bool | None:
    if isinstance(success, bool):
        return success
    if isinstance(status, str):
        normalized = status.strip().lower()
        if normalized in {"ok", "success", "succeeded", "completed", "pass", "passed", "stable"}:
            return True
        if normalized in {"failed", "failure", "error", "invalid_input", "unstable"}:
            return False
    return None


def _first_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _safe_text(str(value)).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_safe_text(value)]
    if isinstance(value, list):
        return [_safe_text(str(item)) for item in value if item is not None]
    return [_safe_text(str(value))]


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


def _safe_text(value: str, max_chars: int = 500) -> str:
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<absolute_path>", value)
    text = re.sub(r"(?<!\w)/(?:[^\s\"']+/)+[^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"\\\\[^\s\"']+", "<absolute_path>", text)
    if len(text) > max_chars:
        return text[:max_chars] + "...[truncated]"
    return text

