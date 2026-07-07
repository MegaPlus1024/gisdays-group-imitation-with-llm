from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from .model_pair_matrix_runner import ModelPairTrialExecutionRequest
from .model_pair_pipeline_result_adapter import adapt_orchestrator_executor_pipeline_result


PipelineContextCallable = Callable[[dict[str, Any]], Any]
_MAX_TEXT_CHARS = 500
_MAX_LIST_ITEMS = 200


def build_pipeline_trial_context(request: ModelPairTrialExecutionRequest) -> dict[str, Any]:
    return {
        "trial_id": _safe_text(request.trial_id),
        "scenario_id": _safe_text(request.scenario_id),
        "scenario_path": _safe_text(request.scenario_path),
        "pair_id": _safe_text(request.pair_id),
        "orchestrator_model_id": _safe_text(request.orchestrator_model_id),
        "executor_model_id": _safe_text(request.executor_model_id),
        "repeat_index": request.repeat_index,
        "task_summary": _safe_optional_text(request.task_summary),
        "expected_outputs": _safe_value(request.expected_outputs),
        "tags": [_safe_text(tag) for tag in request.tags],
        "execution_mode": _safe_text(request.execution_mode),
        "no_runtime_execution": request.no_runtime_execution,
        "metadata": _safe_value(request.metadata),
    }


def make_model_pair_pipeline_callable(
    pipeline_callable: PipelineContextCallable,
    *,
    adapter_config: Mapping[str, Any] | None = None,
) -> Callable[[ModelPairTrialExecutionRequest], dict[str, Any]]:
    if not callable(pipeline_callable):
        raise TypeError("pipeline_callable must be callable.")
    config = dict(adapter_config or {})

    def _call(request: ModelPairTrialExecutionRequest) -> dict[str, Any]:
        context = build_pipeline_trial_context(request)
        pipeline_result = pipeline_callable(context)
        return adapt_orchestrator_executor_pipeline_result(
            pipeline_result,
            request=request,
            default_status=_safe_status(config.get("default_status")),
        )

    return _call


def _safe_status(value: Any) -> str | None:
    text = _safe_optional_text(value)
    return text if text in {"succeeded", "failed", "skipped", "dry_run"} else None


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
    if isinstance(value, set):
        return sorted(_safe_value(item) for item in list(value)[:_MAX_LIST_ITEMS])
    if isinstance(value, str):
        return _safe_text(value)
    if isinstance(value, int | float | bool) or value is None:
        return value
    return _safe_text(str(value))


def _safe_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _safe_text(str(value)).strip()
    return text or None


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


def _is_absolute_path(value: str) -> bool:
    return (
        PureWindowsPath(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or bool(re.match(r"^[A-Za-z]:", value))
    )
