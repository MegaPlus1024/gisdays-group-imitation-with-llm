from __future__ import annotations

import re
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any, Callable, Mapping

from .model_pair_matrix_runner import (
    ModelPairTrialExecutionRequest,
    ModelPairTrialExecutionResult,
    ModelPairTrialStatus,
)


PipelineExecutionCallable = Callable[[ModelPairTrialExecutionRequest], Mapping[str, Any]]

_ALLOWED_STATUSES: set[str] = {"succeeded", "failed", "skipped", "dry_run"}
_TRACE_KEYS = ("group_history", "event_history", "activity_trace")
_MAX_TEXT_CHARS = 500


class InjectedPipelineModelPairTrialExecutor:
    """Adapter from an explicitly injected pipeline callable to matrix trial results."""

    def __init__(self, pipeline_callable: PipelineExecutionCallable) -> None:
        if not callable(pipeline_callable):
            raise TypeError("pipeline_callable must be callable.")
        self.pipeline_callable = pipeline_callable

    def execute_trial(self, request: ModelPairTrialExecutionRequest) -> ModelPairTrialExecutionResult:
        try:
            payload = self.pipeline_callable(request)
        except Exception:
            return _failed_result(
                request,
                error_code="pipeline_executor_failed",
                warnings=["pipeline_executor_failed"],
                notes=["pipeline_executor_exception_suppressed"],
            )
        if not isinstance(payload, Mapping):
            return _failed_result(
                request,
                error_code="pipeline_result_invalid",
                warnings=["pipeline_result_invalid"],
                notes=["pipeline_callable_returned_non_mapping"],
            )
        return _result_from_pipeline_payload(request, payload)


def _result_from_pipeline_payload(
    request: ModelPairTrialExecutionRequest,
    payload: Mapping[str, Any],
) -> ModelPairTrialExecutionResult:
    raw_status = _optional_text(payload.get("status")) or "failed"
    warnings = _string_list(payload.get("warnings"))
    notes = _string_list(payload.get("notes"))
    error_code = _optional_text(payload.get("error_code"))
    status: ModelPairTrialStatus
    if raw_status not in _ALLOWED_STATUSES:
        status = "failed"
        error_code = "pipeline_result_status_invalid"
        warnings = sorted({*warnings, "pipeline_result_status_invalid"})
    else:
        status = raw_status  # type: ignore[assignment]

    correctness_score, score_warnings = _correctness_score(payload.get("correctness_score"))
    warnings = sorted({*warnings, *score_warnings})

    return ModelPairTrialExecutionResult(
        trial_id=request.trial_id,
        scenario_id=request.scenario_id,
        pair_id=request.pair_id,
        orchestrator_model_id=request.orchestrator_model_id,
        executor_model_id=request.executor_model_id,
        status=status,
        task_success=_optional_bool(payload.get("task_success")),
        correctness_score=correctness_score,
        normality_input_ref=_optional_text(payload.get("normality_input_ref")),
        resource_observation=_optional_mapping(payload.get("resource_observation")),
        group_history=_trace_records(payload.get("group_history")),
        event_history=_trace_records(payload.get("event_history")),
        activity_trace=_trace_records(payload.get("activity_trace")),
        artifact_refs=_string_list(payload.get("artifact_refs")),
        task_summary=_optional_text(payload.get("task_summary")) or request.task_summary,
        expected_outputs=_expected_outputs(payload.get("expected_outputs"), request.expected_outputs),
        tags=sorted({*request.tags, *_string_list(payload.get("tags"))}),
        metadata=_metadata(payload.get("metadata"), request),
        error_code=error_code,
        warnings=warnings,
        notes=notes,
        no_runtime_execution=_no_runtime_execution(payload.get("no_runtime_execution")),
        execution_mode=request.execution_mode,
    )


def _failed_result(
    request: ModelPairTrialExecutionRequest,
    *,
    error_code: str,
    warnings: list[str],
    notes: list[str],
) -> ModelPairTrialExecutionResult:
    return ModelPairTrialExecutionResult(
        trial_id=request.trial_id,
        scenario_id=request.scenario_id,
        pair_id=request.pair_id,
        orchestrator_model_id=request.orchestrator_model_id,
        executor_model_id=request.executor_model_id,
        status="failed",
        task_success=False,
        correctness_score=None,
        task_summary=request.task_summary,
        expected_outputs=request.expected_outputs,
        tags=request.tags,
        metadata=dict(request.metadata),
        error_code=error_code,
        warnings=warnings,
        notes=notes,
        no_runtime_execution=True,
        execution_mode=request.execution_mode,
    )


def _correctness_score(value: Any) -> tuple[float | None, list[str]]:
    if isinstance(value, bool) or value is None:
        return None, []
    try:
        parsed = float(value)
    except (TypeError, ValueError):
        return None, ["pipeline_correctness_score_invalid"]
    if not 0.0 <= parsed <= 1.0:
        return None, ["pipeline_correctness_score_invalid"]
    return parsed, []


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None


def _optional_mapping(value: Any) -> dict[str, Any] | None:
    if not isinstance(value, Mapping):
        return None
    return _safe_value(dict(value))


def _trace_records(value: Any) -> list[dict[str, Any]]:
    if not isinstance(value, list):
        return []
    return [_safe_value(dict(item)) for item in value if isinstance(item, Mapping)]


def _expected_outputs(value: Any, fallback: list[Any] | dict[str, Any]) -> list[Any] | dict[str, Any]:
    if isinstance(value, Mapping):
        return _safe_value(dict(value))
    if isinstance(value, list):
        return _safe_value(value)
    return fallback


def _metadata(value: Any, request: ModelPairTrialExecutionRequest) -> dict[str, Any]:
    metadata = _safe_value(dict(value)) if isinstance(value, Mapping) else {}
    metadata.setdefault("request_context", _safe_value(request.metadata))
    metadata.setdefault("no_runtime_execution", True)
    return metadata


def _no_runtime_execution(value: Any) -> bool:
    return value if isinstance(value, bool) else True


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


def _safe_text(value: str) -> str:
    text = _redact_secret_text(value)
    if re.fullmatch(r"/(?:v\d+/)?chat/completions", text.strip()):
        return text.strip()
    url_placeholders: dict[str, str] = {}

    def preserve_url(match: re.Match[str]) -> str:
        placeholder = f"__SAFE_URL_{len(url_placeholders)}__"
        url_placeholders[placeholder] = _safe_url_text(match.group(0))
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


def _safe_url_text(value: str) -> str:
    return re.sub(r"://[^/\s:@]+:[^/\s@]+@", "://<redacted_secret>@", value)


def _redact_secret_text(value: str) -> str:
    return re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password|credential|auth)\s*[:=]\s*['\"]?[^,\s'\"]+",
        lambda match: f"{match.group(1)}=<redacted_secret>",
        value,
    )


def _secret_like_key(key: str) -> bool:
    lowered = key.lower()
    return any(
        token in lowered
        for token in (
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
    )


def _is_absolute_path(value: str) -> bool:
    return (
        PureWindowsPath(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or bool(re.match(r"^[A-Za-z]:", value))
    )
