from __future__ import annotations

import json
import re
from pathlib import Path
from typing import Any, Mapping

from .model_pair_matrix_runner import ModelPairMatrixRunSummary
from .normality_judge import NormalityJudgeConfig, sanitize_judge_text


MATRIX_RUN_ADAPTER_SUMMARY_SCHEMA_VERSION = "matrix_run_adapter_summary_v1"
MATRIX_RUN_ADAPTER_SUMMARY_FILENAME = "matrix_run_adapter_summary.json"
MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME = "model_resource_observations.jsonl"
NORMALITY_JUDGE_INPUTS_JSONL_FILENAME = "normality_judge_inputs.jsonl"

_RESOURCE_OBSERVATION_FIELDS = {
    "observation_id",
    "model_id",
    "orchestrator_model_id",
    "executor_model_id",
    "pair_id",
    "scenario_id",
    "trial_id",
    "runtime_mode",
    "backend",
    "success",
    "error_code",
    "wall_time_s",
    "peak_ram_gb",
    "peak_vram_gb",
    "prompt_tokens",
    "completion_tokens",
    "total_tokens",
    "concurrency",
    "notes",
    "tags",
}
_TRACE_KEYS = ("group_history", "event_history", "activity_trace", "events", "history")
_MAX_TEXT_CHARS = 500


class MatrixRunAdapterInputLoadError(ValueError):
    """Controlled adapter input-loading error safe to expose through CLI JSON."""


def build_resource_observations_from_matrix_run_summary(
    matrix_summary: ModelPairMatrixRunSummary | Mapping[str, Any] | str | Path,
) -> list[dict[str, Any]]:
    payload = _coerce_matrix_summary_payload(matrix_summary)
    observations: list[dict[str, Any]] = []
    for index, trial in enumerate(_trial_results(payload), start=1):
        explicit = trial.get("resource_observation")
        if isinstance(explicit, Mapping):
            observation = _resource_observation_from_explicit(dict(explicit), trial, index=index)
        else:
            observation = _minimal_resource_observation(trial, index=index)
        observations.append(_drop_none_values(observation))
    return observations


def write_resource_observations_jsonl(
    observations: list[Mapping[str, Any]],
    output_dir: str | Path,
    filename: str = MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME,
) -> Path:
    return _write_jsonl([dict(row) for row in observations], output_dir, filename)


def build_normality_inputs_from_matrix_run_summary(
    matrix_summary: ModelPairMatrixRunSummary | Mapping[str, Any] | str | Path,
    task_summary_by_scenario: Mapping[str, str] | None = None,
) -> list[dict[str, Any]]:
    payload = _coerce_matrix_summary_payload(matrix_summary)
    source_run_id = _optional_text(payload.get("run_id")) or "unknown_matrix_run"
    task_summaries = dict(task_summary_by_scenario or {})
    inputs: list[dict[str, Any]] = []
    for trial in _trial_results(payload):
        trace_key, trace_records = _trace_records(trial)
        warnings = _string_list(trial.get("warnings"))
        if trace_records is None:
            trace_records = []
            warnings.append("normality_trace_missing")
        safe_records = [_safe_value(record) for record in trace_records if isinstance(record, Mapping)]
        scenario_id = _optional_text(trial.get("scenario_id")) or "unknown_scenario"
        pair_id = _optional_text(trial.get("pair_id")) or _pair_id_from_trial(trial)
        model_pair = {
            "orchestrator": _optional_text(trial.get("orchestrator_model_id")) or "unknown_orchestrator",
            "executor": _optional_text(trial.get("executor_model_id")) or "unknown_executor",
        }
        row: dict[str, Any] = {
            "input_format": "normality_judge_input_record_v1",
            "trial_id": _optional_text(trial.get("trial_id")) or "unknown_trial",
            "scenario_id": scenario_id,
            "pair_id": pair_id,
            "model_pair": model_pair,
            "task_summary": _task_summary(trial, scenario_id, task_summaries),
            "events": safe_records,
            "tags": _string_list(trial.get("tags")),
            "metadata": _normality_metadata(trial, source_run_id=source_run_id),
            "warnings": sorted(set(warnings)),
            "no_runtime_execution": True,
        }
        if trace_key is not None:
            row[trace_key] = safe_records
        else:
            row["adapter_status"] = "invalid_input"
        inputs.append(_safe_value(row))
    return inputs


def write_normality_inputs_jsonl(
    inputs: list[Mapping[str, Any]],
    output_dir: str | Path,
    filename: str = NORMALITY_JUDGE_INPUTS_JSONL_FILENAME,
) -> Path:
    return _write_jsonl([dict(row) for row in inputs], output_dir, filename)


def write_matrix_run_adapter_outputs(
    matrix_summary: ModelPairMatrixRunSummary | Mapping[str, Any] | str | Path,
    output_dir: str | Path,
    *,
    write_resource: bool = True,
    write_normality: bool = True,
    task_summary_by_scenario: Mapping[str, str] | None = None,
    adapter_id: str | None = None,
) -> dict[str, Any]:
    payload = _coerce_matrix_summary_payload(matrix_summary)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    resource_observations: list[dict[str, Any]] = []
    normality_inputs: list[dict[str, Any]] = []
    output_paths: dict[str, str | None] = {
        "resource_observations": None,
        "normality_inputs": None,
        "adapter_summary": MATRIX_RUN_ADAPTER_SUMMARY_FILENAME,
    }

    if write_resource:
        resource_observations = build_resource_observations_from_matrix_run_summary(payload)
        resource_path = write_resource_observations_jsonl(resource_observations, out_dir)
        output_paths["resource_observations"] = _relative_output_path(resource_path, out_dir)
    if write_normality:
        normality_inputs = build_normality_inputs_from_matrix_run_summary(
            payload,
            task_summary_by_scenario=task_summary_by_scenario,
        )
        normality_path = write_normality_inputs_jsonl(normality_inputs, out_dir)
        output_paths["normality_inputs"] = _relative_output_path(normality_path, out_dir)

    summary = _adapter_summary(
        payload,
        resource_observations=resource_observations,
        normality_inputs=normality_inputs,
        output_paths=output_paths,
        adapter_id=adapter_id,
    )
    summary_path = out_dir / MATRIX_RUN_ADAPTER_SUMMARY_FILENAME
    summary_path.write_text(
        json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary


def _coerce_matrix_summary_payload(
    matrix_summary: ModelPairMatrixRunSummary | Mapping[str, Any] | str | Path,
) -> dict[str, Any]:
    if isinstance(matrix_summary, ModelPairMatrixRunSummary):
        return matrix_summary.model_dump(mode="json")
    if isinstance(matrix_summary, Mapping):
        return dict(matrix_summary)
    path = Path(matrix_summary)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MatrixRunAdapterInputLoadError("matrix_summary_file_missing") from exc
    except OSError as exc:
        raise MatrixRunAdapterInputLoadError("matrix_summary_file_unreadable") from exc
    except json.JSONDecodeError as exc:
        raise MatrixRunAdapterInputLoadError("matrix_summary_json_malformed") from exc
    if not isinstance(payload, dict):
        raise MatrixRunAdapterInputLoadError("matrix_summary_payload_not_object")
    return payload


def _trial_results(payload: dict[str, Any]) -> list[dict[str, Any]]:
    rows = payload.get("trial_results")
    if not isinstance(rows, list):
        raise MatrixRunAdapterInputLoadError("matrix_trial_results_missing")
    out: list[dict[str, Any]] = []
    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            raise MatrixRunAdapterInputLoadError(f"matrix_trial_result_not_object:{index}")
        out.append(row)
    return out


def _resource_observation_from_explicit(
    explicit: dict[str, Any],
    trial: dict[str, Any],
    *,
    index: int,
) -> dict[str, Any]:
    observation = {
        key: _safe_value(value)
        for key, value in explicit.items()
        if key in _RESOURCE_OBSERVATION_FIELDS and not _secret_like_key(key)
    }
    fallback = _minimal_resource_observation(trial, index=index)
    for key, value in fallback.items():
        observation.setdefault(key, value)
    if observation.get("success") is None:
        observation["success"] = _derive_success(trial)
    return observation


def _minimal_resource_observation(trial: dict[str, Any], *, index: int) -> dict[str, Any]:
    trial_id = _optional_text(trial.get("trial_id")) or f"trial_{index:03d}"
    return {
        "observation_id": _optional_text(trial.get("observation_id")) or f"{trial_id}__resource",
        "trial_id": trial_id,
        "scenario_id": _optional_text(trial.get("scenario_id")),
        "pair_id": _optional_text(trial.get("pair_id")) or _pair_id_from_trial(trial),
        "orchestrator_model_id": _optional_text(trial.get("orchestrator_model_id")),
        "executor_model_id": _optional_text(trial.get("executor_model_id")),
        "success": _derive_success(trial),
        "error_code": _optional_text(trial.get("error_code")),
        "runtime_mode": _optional_text(trial.get("runtime_mode")) or "unknown",
        "backend": _optional_text(trial.get("backend")) or "unknown",
        "notes": _string_list(trial.get("notes")),
        "tags": _string_list(trial.get("tags")),
    }


def _derive_success(trial: dict[str, Any]) -> bool | None:
    task_success = trial.get("task_success")
    if isinstance(task_success, bool):
        return task_success
    status = _optional_text(trial.get("status"))
    if status in {"succeeded", "success", "ok", "passed", "completed"}:
        return True
    if status in {"failed", "failure", "error", "invalid_input"}:
        return False
    return None


def _trace_records(trial: dict[str, Any]) -> tuple[str | None, list[Any] | None]:
    for key in _TRACE_KEYS:
        value = trial.get(key)
        if isinstance(value, list):
            return key, value
    return None, None


def _task_summary(
    trial: dict[str, Any],
    scenario_id: str,
    task_summary_by_scenario: dict[str, str],
) -> str:
    mapped = task_summary_by_scenario.get(scenario_id)
    if mapped:
        return _safe_text(mapped)
    for key in ("task_summary", "expected_behavior", "expected_group_behavior", "description"):
        value = _optional_text(trial.get(key))
        if value:
            return value
    return f"Offline matrix run trial for scenario {scenario_id}."


def _normality_metadata(trial: dict[str, Any], *, source_run_id: str) -> dict[str, Any]:
    metadata = {
        "source_run_id": source_run_id,
        "matrix_trial_status": _optional_text(trial.get("status")),
        "task_success": trial.get("task_success") if isinstance(trial.get("task_success"), bool) else None,
        "correctness_score": trial.get("correctness_score"),
        "error_code": _optional_text(trial.get("error_code")),
        "repeat_index": _int_or_none(trial.get("repeat_index")),
        "no_runtime_execution": True,
        "trial_warnings": _string_list(trial.get("warnings")),
        "trial_notes": _string_list(trial.get("notes")),
    }
    metadata.update(_action_execution_metadata(trial))
    metadata.update(_office_execution_artifact_metadata(trial))
    return _drop_none_values(metadata)


def _action_execution_metadata(trial: dict[str, Any]) -> dict[str, Any]:
    group_history = [row for row in _list_value(trial.get("group_history")) if isinstance(row, Mapping)]
    validation_rows = [row for row in group_history if "validation_accepted" in _metadata(row)]
    execution_rows = [
        row
        for row in group_history
        if "execution_attempted" in _metadata(row) or "execution_success" in _metadata(row)
    ]
    if not validation_rows and not execution_rows:
        return {}
    return {
        "validation_success_count": sum(1 for row in validation_rows if _metadata(row).get("validation_accepted") is True),
        "execution_attempted_count": sum(1 for row in execution_rows if _metadata(row).get("execution_attempted") is True),
        "execution_success_count": sum(1 for row in execution_rows if _metadata(row).get("execution_success") is True),
        "action_execution_enabled": any(_metadata(row).get("action_execution_enabled") is True for row in group_history),
    }


def _office_execution_artifact_metadata(trial: dict[str, Any]) -> dict[str, Any]:
    trial_metadata = trial.get("metadata") if isinstance(trial.get("metadata"), Mapping) else {}
    summary = _first_mapping(
        trial.get("office_execution_artifact_summary"),
        trial_metadata.get("office_execution_artifact_summary") if isinstance(trial_metadata, Mapping) else None,
    )
    output: dict[str, Any] = {}
    for source in (trial, trial_metadata):
        if not isinstance(source, Mapping):
            continue
        for key in ("office_execution_artifact_summary_ref", "office_execution_artifact_summary_path"):
            text = _optional_text(source.get(key))
            if text:
                output["office_execution_artifact_summary_ref"] = text
                break
        if output.get("office_execution_artifact_summary_ref"):
            break
    if summary is not None:
        output["office_execution_artifact_count"] = _int_or_none(summary.get("artifact_count"))
        output["office_execution_artifact_readable_count"] = _int_or_none(summary.get("readable_count"))
    return output


def _metadata(row: Mapping[str, Any]) -> Mapping[str, Any]:
    metadata = row.get("metadata")
    return metadata if isinstance(metadata, Mapping) else {}


def _first_mapping(*values: Any) -> Mapping[str, Any] | None:
    for value in values:
        if isinstance(value, Mapping):
            return value
    return None


def _adapter_summary(
    payload: dict[str, Any],
    *,
    resource_observations: list[dict[str, Any]],
    normality_inputs: list[dict[str, Any]],
    output_paths: dict[str, str | None],
    adapter_id: str | None,
) -> dict[str, Any]:
    normality_missing_trace_count = sum(
        1 for row in normality_inputs if "normality_trace_missing" in row.get("warnings", [])
    )
    warnings = sorted(
        {
            *_string_list(payload.get("warnings")),
            *(
                "normality_trace_missing"
                for row in normality_inputs
                if "normality_trace_missing" in row.get("warnings", [])
            ),
        }
    )
    return _drop_none_values(
        {
            "schema_version": MATRIX_RUN_ADAPTER_SUMMARY_SCHEMA_VERSION,
            "adapter_id": _optional_text(adapter_id),
            "source_run_id": _optional_text(payload.get("run_id")) or "unknown_matrix_run",
            "trial_count": _int_or_count(payload.get("trial_count"), len(_trial_results(payload))),
            "resource_observation_count": len(resource_observations),
            "normality_input_count": len(normality_inputs),
            "normality_missing_trace_count": normality_missing_trace_count,
            "output_paths": output_paths,
            "warnings": warnings,
            "no_runtime_execution": True,
        }
    )


def _write_jsonl(rows: list[dict[str, Any]], output_dir: str | Path, filename: str) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / filename
    path.write_text(
        "".join(
            json.dumps(_safe_value(row), ensure_ascii=False, separators=(",", ":"), sort_keys=True) + "\n"
            for row in rows
        ),
        encoding="utf-8",
    )
    return path


def _relative_output_path(path: Path, output_dir: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(output_dir.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return path.name


def _pair_id_from_trial(trial: dict[str, Any]) -> str:
    orchestrator = _optional_text(trial.get("orchestrator_model_id")) or "unknown_orchestrator"
    executor = _optional_text(trial.get("executor_model_id")) or "unknown_executor"
    return f"{orchestrator}__to__{executor}"


def _drop_none_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            _safe_text(str(key)): _safe_value(item)
            for key, item in value.items()
            if not _secret_like_key(str(key))
        }
    if isinstance(value, list):
        return [_safe_value(item) for item in value]
    if isinstance(value, tuple):
        return [_safe_value(item) for item in value]
    if isinstance(value, str):
        return _safe_text(value)
    return value


def _safe_text(value: str) -> str:
    safe, _ = sanitize_judge_text(
        _redact_secret_text(value),
        NormalityJudgeConfig(enabled=True, mode="deterministic", max_text_chars=_MAX_TEXT_CHARS),
    )
    return safe


def _redact_secret_text(value: str) -> str:
    return re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password|credential|auth)\s*[:=]\s*['\"]?[^,\s'\"]+",
        lambda match: f"{match.group(1)}=<redacted_secret>",
        value,
    )


def _secret_like_key(key: str) -> bool:
    lowered = key.lower()
    secret_tokens = (
        "raw_prompt",
        "raw_response",
        "full_prompt",
        "full_response",
        "prompt_text",
        "response_text",
        "api_key",
        "apikey",
        "token",
        "secret",
        "password",
        "credential",
        "auth",
    )
    return any(token in lowered for token in secret_tokens)


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
    if isinstance(value, list | tuple | set):
        return [_safe_text(str(item)) for item in value if item is not None]
    return [_safe_text(str(value))]


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _int_or_count(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _int_or_none(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None
