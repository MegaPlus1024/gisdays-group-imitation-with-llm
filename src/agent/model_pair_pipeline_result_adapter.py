from __future__ import annotations

import dataclasses
import re
from collections.abc import Callable, Mapping
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from .model_pair_matrix_runner import ModelPairTrialExecutionRequest


PIPELINE_RESULT_ADAPTER_NAME = "orchestrator_executor_pipeline_result_adapter"

_ALLOWED_STATUSES = {"succeeded", "failed", "skipped", "dry_run"}
_SUCCESS_STATUSES = {"ok", "success", "succeeded", "completed", "complete", "passed"}
_FAILURE_STATUSES = {"failed", "failure", "error", "errored", "invalid_input", "completed_with_failures"}
_SKIPPED_STATUSES = {"skipped", "skip"}
_HISTORY_FALLBACK_KEYS = ("events", "steps", "conversation", "history")
_ARTIFACT_KEYS = ("artifact_refs", "artifacts", "output_files", "generated_files")
_MAX_TEXT_CHARS = 500
_MAX_LIST_ITEMS = 200


def adapt_orchestrator_executor_pipeline_result(
    pipeline_result: Any,
    *,
    request: ModelPairTrialExecutionRequest | None = None,
    default_status: str | None = None,
) -> dict[str, Any]:
    payload = _payload_dict(pipeline_result)
    raw_status = _optional_text(_first_value(payload, "status", "state", "result_status"))
    warnings = _string_list(payload.get("warnings"))
    notes = _notes(payload)

    status, status_warning = _normalized_status(
        raw_status,
        success_hint=_first_value(payload, "task_success", "success", "completed"),
        default_status=default_status,
    )
    if status_warning:
        warnings.append(status_warning)

    metadata = _metadata(
        pipeline_result,
        payload,
        raw_status=raw_status,
        request=request,
    )
    resource_observation = _resource_observation(payload)
    task_success = _task_success(payload, status=status)
    artifact_refs = _artifact_refs(payload)
    error_code = _error_code(payload)

    return {
        "status": status,
        "task_success": task_success,
        "correctness_score": _optional_score(payload.get("correctness_score")),
        "group_history": _history_rows(payload.get("group_history")),
        "event_history": _history_rows(payload.get("event_history")),
        "activity_trace": _activity_trace(payload),
        "artifact_refs": artifact_refs,
        "resource_observation": resource_observation,
        "error_code": error_code,
        "warnings": sorted(set(warnings)),
        "notes": notes,
        "metadata": metadata,
        "no_runtime_execution": _no_runtime_execution(payload.get("no_runtime_execution")),
    }


def make_pipeline_result_adapter_callable(
    pipeline_callable: Callable[[ModelPairTrialExecutionRequest], Any],
) -> Callable[[ModelPairTrialExecutionRequest], dict[str, Any]]:
    def _call(request: ModelPairTrialExecutionRequest) -> dict[str, Any]:
        return adapt_orchestrator_executor_pipeline_result(
            pipeline_callable(request),
            request=request,
        )

    return _call


def _payload_dict(value: Any) -> dict[str, Any]:
    if isinstance(value, Mapping):
        return dict(value)
    if dataclasses.is_dataclass(value) and not isinstance(value, type):
        return dataclasses.asdict(value)
    model_dump = getattr(value, "model_dump", None)
    if callable(model_dump):
        try:
            dumped = model_dump(mode="json")
        except TypeError:
            dumped = model_dump()
        if isinstance(dumped, Mapping):
            return dict(dumped)
    if hasattr(value, "__dict__"):
        return {
            key: item
            for key, item in vars(value).items()
            if not key.startswith("_")
        }
    return {}


def _normalized_status(
    raw_status: str | None,
    *,
    success_hint: Any,
    default_status: str | None,
) -> tuple[str, str | None]:
    default = _safe_status(default_status)
    success = _optional_bool(success_hint)
    if raw_status:
        lowered = raw_status.lower()
        if lowered in _SKIPPED_STATUSES:
            return "skipped", None
    if success is False:
        return "failed", None
    if raw_status:
        lowered = raw_status.lower()
        if lowered in _FAILURE_STATUSES:
            return "failed", None
        if lowered in _SUCCESS_STATUSES:
            return "succeeded", None
        if success is True:
            return "succeeded", None
    elif success is True:
        return "succeeded", None
    if default:
        return default, "pipeline_status_unknown"
    return "failed", "pipeline_status_unknown"


def _safe_status(value: str | None) -> str | None:
    text = _optional_text(value)
    if text in _ALLOWED_STATUSES:
        return text
    return None


def _task_success(payload: Mapping[str, Any], *, status: str) -> bool | None:
    explicit = _optional_bool(_first_value(payload, "task_success", "success", "completed"))
    if explicit is not None:
        return explicit
    if status == "succeeded":
        return True
    if status == "failed":
        return False
    return None


def _activity_trace(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    explicit = _history_rows(payload.get("activity_trace"))
    if explicit:
        return explicit
    for key in _HISTORY_FALLBACK_KEYS:
        rows = _history_rows(payload.get(key))
        if rows:
            return rows
    return _per_agent_attempt_rows(payload.get("per_agent_results"))


def _per_agent_attempt_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for trajectory in _list_value(value):
        trajectory_payload = _payload_dict(trajectory)
        agent_id = _optional_text(trajectory_payload.get("agent_id"))
        for attempt in _list_value(trajectory_payload.get("attempts")):
            attempt_payload = _payload_dict(attempt)
            if not attempt_payload:
                continue
            rows.append(
                _safe_value(
                    {
                        "agent_id": agent_id or attempt_payload.get("agent_id"),
                        "group_step_index": attempt_payload.get("group_step_index"),
                        "agent_step_index": attempt_payload.get("agent_step_index"),
                        "task_id": attempt_payload.get("task_id"),
                        "action": attempt_payload.get("action"),
                        "status": "failure" if attempt_payload.get("error_type") else "success",
                        "summary": attempt_payload.get("error_message") or "Executor attempt completed.",
                        "metadata": {
                            "parse_success": attempt_payload.get("parse_success"),
                            "validation_accepted": attempt_payload.get("validation_accepted"),
                            "execution_attempted": attempt_payload.get("execution_attempted"),
                            "execution_success": attempt_payload.get("execution_success"),
                        },
                    }
                )
            )
            if len(rows) >= _MAX_LIST_ITEMS:
                return rows
    return rows


def _history_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for item in _list_value(value):
        row = _payload_dict(item)
        if row:
            rows.append(_safe_value(row))
        if len(rows) >= _MAX_LIST_ITEMS:
            break
    return rows


def _artifact_refs(payload: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in _ARTIFACT_KEYS:
        refs.extend(_artifact_refs_from_value(payload.get(key)))
    artifact_dir = _optional_text(payload.get("artifact_dir"))
    if artifact_dir:
        refs.append(artifact_dir)
    return list(dict.fromkeys(refs))[:_MAX_LIST_ITEMS]


def _artifact_refs_from_value(value: Any) -> list[str]:
    refs: list[str] = []
    for item in _list_value(value):
        if isinstance(item, str):
            text = _optional_text(item)
            if text:
                refs.append(text)
            continue
        row = _payload_dict(item)
        for key in ("path", "artifact_path", "file_path", "output_path", "path_relative", "ref"):
            text = _optional_text(row.get(key))
            if text:
                refs.append(text)
    return refs


def _resource_observation(payload: Mapping[str, Any]) -> dict[str, Any]:
    value = payload.get("resource_observation")
    return _safe_value(dict(value)) if isinstance(value, Mapping) else {}


def _error_code(payload: Mapping[str, Any]) -> str | None:
    for key in ("error_code", "failure_reason", "error_type"):
        text = _optional_text(payload.get(key))
        if text:
            return text
    error = payload.get("error")
    if isinstance(error, Mapping):
        for key in ("error_code", "error_type", "type", "code"):
            text = _optional_text(error.get(key))
            if text:
                return text
    text = _optional_text(error)
    if text and _looks_like_safe_error_code(text):
        return text
    errors = payload.get("errors")
    for item in _list_value(errors):
        row = _payload_dict(item)
        for key in ("error_code", "error_type", "type", "code", "stage"):
            text = _optional_text(row.get(key))
            if text:
                return text
    return None


def _looks_like_safe_error_code(value: str) -> bool:
    if _secret_like_text(value) or _is_absolute_path(value):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", value))


def _notes(payload: Mapping[str, Any]) -> list[str]:
    notes = _string_list(payload.get("notes"))
    stopped_reason = _optional_text(payload.get("stopped_reason"))
    if stopped_reason:
        notes.append(stopped_reason)
    return list(dict.fromkeys(notes))[:_MAX_LIST_ITEMS]


def _metadata(
    pipeline_result: Any,
    payload: Mapping[str, Any],
    *,
    raw_status: str | None,
    request: ModelPairTrialExecutionRequest | None,
) -> dict[str, Any]:
    metadata = _safe_value(dict(payload.get("metadata"))) if isinstance(payload.get("metadata"), Mapping) else {}
    metadata["adapter_name"] = PIPELINE_RESULT_ADAPTER_NAME
    metadata["source_result_type"] = _source_result_type(pipeline_result)
    metadata["pipeline_status_raw"] = raw_status
    if request is not None:
        metadata["request"] = {
            "trial_id": request.trial_id,
            "scenario_id": request.scenario_id,
            "pair_id": request.pair_id,
            "orchestrator_model_id": request.orchestrator_model_id,
            "executor_model_id": request.executor_model_id,
        }
    return _safe_value(metadata)


def _source_result_type(value: Any) -> str:
    if isinstance(value, Mapping):
        return "mapping"
    return _safe_text(type(value).__name__)


def _optional_score(value: Any) -> float | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None
    return parsed if 0.0 <= parsed <= 1.0 else None


def _no_runtime_execution(value: Any) -> bool:
    return value if isinstance(value, bool) else True


def _first_value(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            _safe_text(str(key)): _safe_value(item)
            for key, item in value.items()
            if not _secret_like_key(str(key))
        }
    if isinstance(value, list):
        return [_safe_value(item) for item in value[:_MAX_LIST_ITEMS]]
    if isinstance(value, tuple):
        return [_safe_value(item) for item in value[:_MAX_LIST_ITEMS]]
    if isinstance(value, str):
        return _safe_text(value)
    return value


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
        return [_safe_text(str(item)) for item in list(value)[:_MAX_LIST_ITEMS] if item is not None]
    return [_safe_text(str(value))]


def _safe_text(value: str) -> str:
    text = _redact_secret_text(value)
    url_placeholders: dict[str, str] = {}

    def preserve_url(match: re.Match[str]) -> str:
        placeholder = f"__SAFE_URL_{len(url_placeholders)}__"
        url_placeholders[placeholder] = re.sub(
            r"://[^/\s:@]+:[^/\s@]+@",
            "://<redacted_secret>@",
            match.group(0),
        )
        return placeholder

    text = re.sub(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s\"']+", preserve_url, text)
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"(?<!\w)/(?:[^\s\"']+/)+[^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"\\\\[^\s\"']+", "<absolute_path>", text)
    if _is_absolute_path(text):
        text = "<absolute_path>"
    for placeholder, url in url_placeholders.items():
        text = text.replace(placeholder, url)
    if len(text) > _MAX_TEXT_CHARS:
        return text[:_MAX_TEXT_CHARS] + "...[truncated]"
    return text


def _redact_secret_text(value: str) -> str:
    return re.sub(
        r"(?i)['\"]?\b(api[_-]?key|token|secret|password|credential|auth)\b['\"]?\s*[:=]\s*['\"]?[^,\s'\"}]+",
        "<redacted_secret>",
        value,
    )


def _secret_like_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        token in lowered
        for token in (
            "raw_prompt",
            "raw_response",
            "raw_output",
            "raw_model_output",
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
    )


def _secret_like_text(value: str) -> bool:
    return bool(re.search(r"(?i)\b(api[_-]?key|token|secret|password|credential|auth)\b", value))


def _is_absolute_path(value: str) -> bool:
    return (
        PureWindowsPath(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or bool(re.match(r"^[A-Za-z]:", value))
    )
