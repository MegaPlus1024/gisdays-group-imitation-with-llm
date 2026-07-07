from __future__ import annotations

import copy
import re
from collections.abc import Callable, Mapping
from pathlib import PurePosixPath, PureWindowsPath
from typing import Any

from .model_pair_pipeline_bridge import make_model_pair_pipeline_callable
from .model_pair_pipeline_executor import InjectedPipelineModelPairTrialExecutor


PipelineEntrypointCallable = Callable[[dict[str, Any]], Any]
PipelineEntrypointResolver = Callable[[Mapping[str, Any]], Mapping[str, Any] | None]

_MAX_TEXT_CHARS = 500
_MAX_LIST_ITEMS = 200


def build_pipeline_entrypoint_input(
    context: Mapping[str, Any],
    *,
    role_config_resolver: PipelineEntrypointResolver | None = None,
    scenario_config_resolver: PipelineEntrypointResolver | None = None,
    model_binding_resolver: PipelineEntrypointResolver | None = None,
    extra_config: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    safe_context = _safe_mapping(context)
    scenario_config = _resolve_optional_mapping(
        scenario_config_resolver,
        safe_context,
        "scenario_config_resolver_return_invalid",
    )
    role_config = _resolve_optional_mapping(
        role_config_resolver,
        safe_context,
        "role_config_resolver_return_invalid",
    )
    model_bindings = _resolve_optional_mapping(
        model_binding_resolver,
        safe_context,
        "model_binding_resolver_return_invalid",
    )

    scenario_config.setdefault("scenario_id", _safe_optional_text(safe_context.get("scenario_id")))
    scenario_config.setdefault("scenario_path", _safe_optional_text(safe_context.get("scenario_path")))
    model_bindings.setdefault(
        "orchestrator",
        {"model_id": _safe_optional_text(safe_context.get("orchestrator_model_id"))},
    )
    model_bindings.setdefault(
        "executor",
        {"model_id": _safe_optional_text(safe_context.get("executor_model_id"))},
    )

    metadata = _safe_mapping(safe_context.get("metadata")) if isinstance(safe_context.get("metadata"), Mapping) else {}
    entrypoint_input: dict[str, Any] = {
        "trial_id": _safe_optional_text(safe_context.get("trial_id")),
        "scenario_id": _safe_optional_text(safe_context.get("scenario_id")),
        "scenario_path": _safe_optional_text(safe_context.get("scenario_path")),
        "pair_id": _safe_optional_text(safe_context.get("pair_id")),
        "orchestrator_model_id": _safe_optional_text(safe_context.get("orchestrator_model_id")),
        "executor_model_id": _safe_optional_text(safe_context.get("executor_model_id")),
        "repeat_index": _safe_int(safe_context.get("repeat_index")),
        "task_summary": _safe_optional_text(safe_context.get("task_summary")),
        "expected_outputs": _safe_expected_outputs(safe_context.get("expected_outputs")),
        "tags": _safe_text_list(safe_context.get("tags")),
        "model_pair": {
            "pair_id": _safe_optional_text(safe_context.get("pair_id")),
            "orchestrator_model_id": _safe_optional_text(safe_context.get("orchestrator_model_id")),
            "executor_model_id": _safe_optional_text(safe_context.get("executor_model_id")),
        },
        "scenario_config": _drop_none_values(scenario_config),
        "role_config": _drop_none_values(role_config),
        "model_bindings": _drop_none_values(model_bindings),
        "execution_options": {
            "allow_runtime_execution": False,
            "no_runtime_execution": True,
            "context_no_runtime_execution": _safe_bool(safe_context.get("no_runtime_execution"), default=True),
        },
        "metadata": _drop_none_values(
            {
                "wrapper": "model_pair_pipeline_entrypoint_wrapper",
                "source_execution_mode": _safe_optional_text(safe_context.get("execution_mode")),
                "context_metadata": metadata,
                "explicit_runtime_opt_in": False,
            }
        ),
    }

    if extra_config:
        raw_extra_config = _copy_raw_mapping(extra_config)
        entrypoint_input["extra_config"] = raw_extra_config
        local_pipeline_config = raw_extra_config.get("local_pipeline_config")
        if isinstance(local_pipeline_config, Mapping):
            entrypoint_input["local_pipeline_config"] = _copy_raw_mapping(local_pipeline_config)
    return entrypoint_input


def make_explicit_pipeline_entrypoint_callable(
    pipeline_entrypoint: PipelineEntrypointCallable,
    *,
    allow_runtime_execution: bool = False,
    role_config_resolver: PipelineEntrypointResolver | None = None,
    scenario_config_resolver: PipelineEntrypointResolver | None = None,
    model_binding_resolver: PipelineEntrypointResolver | None = None,
    extra_config: Mapping[str, Any] | None = None,
) -> Callable[[dict[str, Any]], Any]:
    if not callable(pipeline_entrypoint):
        raise TypeError("pipeline_entrypoint must be callable.")

    runtime_allowed = bool(allow_runtime_execution)

    def _call(context: dict[str, Any]) -> Any:
        entrypoint_input = build_pipeline_entrypoint_input(
            context,
            role_config_resolver=role_config_resolver,
            scenario_config_resolver=scenario_config_resolver,
            model_binding_resolver=model_binding_resolver,
            extra_config=extra_config,
        )
        entrypoint_input["execution_options"]["allow_runtime_execution"] = runtime_allowed
        entrypoint_input["execution_options"]["no_runtime_execution"] = not runtime_allowed
        entrypoint_input["metadata"]["explicit_runtime_opt_in"] = runtime_allowed
        if runtime_allowed:
            entrypoint_input["metadata"]["runtime_opt_in_source"] = "programmatic_wrapper_construction"
        return pipeline_entrypoint(entrypoint_input)

    return _call


def make_model_pair_entrypoint_executor(
    pipeline_entrypoint: PipelineEntrypointCallable,
    *,
    allow_runtime_execution: bool = False,
    role_config_resolver: PipelineEntrypointResolver | None = None,
    scenario_config_resolver: PipelineEntrypointResolver | None = None,
    model_binding_resolver: PipelineEntrypointResolver | None = None,
    extra_config: Mapping[str, Any] | None = None,
) -> InjectedPipelineModelPairTrialExecutor:
    entrypoint_callable = make_explicit_pipeline_entrypoint_callable(
        pipeline_entrypoint,
        allow_runtime_execution=allow_runtime_execution,
        role_config_resolver=role_config_resolver,
        scenario_config_resolver=scenario_config_resolver,
        model_binding_resolver=model_binding_resolver,
        extra_config=extra_config,
    )
    return InjectedPipelineModelPairTrialExecutor(make_model_pair_pipeline_callable(entrypoint_callable))


def _resolve_optional_mapping(
    resolver: PipelineEntrypointResolver | None,
    context: Mapping[str, Any],
    error_code: str,
) -> dict[str, Any]:
    if resolver is None:
        return {}
    resolved = resolver(copy.deepcopy(dict(context)))
    if resolved is None:
        return {}
    if not isinstance(resolved, Mapping):
        raise ValueError(error_code)
    return _safe_mapping(resolved)


def _safe_expected_outputs(value: Any) -> list[Any] | dict[str, Any]:
    if isinstance(value, Mapping):
        return _safe_mapping(value)
    if isinstance(value, list | tuple):
        return [_safe_value(item) for item in list(value)[:_MAX_LIST_ITEMS]]
    return []


def _safe_mapping(value: Mapping[str, Any] | Any) -> dict[str, Any]:
    if not isinstance(value, Mapping):
        return {}
    return {
        _safe_text(str(key)): _safe_value(item)
        for key, item in value.items()
        if not _secret_like_key(str(key))
    }


def _safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return _safe_mapping(value)
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


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool) or value is None:
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_bool(value: Any, *, default: bool) -> bool:
    return value if isinstance(value, bool) else default


def _safe_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_safe_text(value)]
    if isinstance(value, list | tuple | set):
        return [_safe_text(str(item)) for item in list(value)[:_MAX_LIST_ITEMS] if item is not None]
    return [_safe_text(str(value))]


def _drop_none_values(payload: dict[str, Any]) -> dict[str, Any]:
    return {key: value for key, value in payload.items() if value is not None}


def _copy_raw_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    try:
        return copy.deepcopy(dict(value))
    except Exception:
        return dict(value)
