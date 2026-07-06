from __future__ import annotations

import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .model_pair_matrix_adapters import (
    MATRIX_RUN_ADAPTER_SUMMARY_FILENAME,
    MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME,
    NORMALITY_JUDGE_INPUTS_JSONL_FILENAME,
    MatrixRunAdapterInputLoadError,
    write_matrix_run_adapter_outputs,
)
from .model_pair_matrix_runner import (
    MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME,
    MODEL_PAIR_TRIAL_RESULTS_JSONL_FILENAME,
    ModelPairMatrixPlanError,
    run_model_pair_matrix,
)
from .model_pair_pipeline_entrypoint_wrapper import (
    PipelineEntrypointCallable,
    PipelineEntrypointResolver,
    make_model_pair_entrypoint_executor,
)


MODEL_PAIR_EXECUTION_API_EXECUTION_MODE = "injected_pipeline"
_MATRIX_ADAPTERS_DIRNAME = "matrix_adapters"
_MAX_TEXT_CHARS = 500
_MAX_LIST_ITEMS = 200
_FORBIDDEN_OUTPUT_DIR_PARTS = {"reports", "experiments"}


@dataclass(frozen=True)
class ModelPairExecutionApiConfig:
    output_dir: Path | str
    allow_runtime_execution: bool = False
    write_trial_results_jsonl: bool = True
    auto_matrix_adapter_outputs: bool = False
    adapter_id: str | None = None
    role_config_resolver: PipelineEntrypointResolver | None = None
    scenario_config_resolver: PipelineEntrypointResolver | None = None
    model_binding_resolver: PipelineEntrypointResolver | None = None
    extra_config: Mapping[str, Any] | None = None
    run_id: str | None = None
    tags: tuple[str, ...] = ()


def run_model_pair_execution_matrix(
    plan: Any,
    *,
    pipeline_entrypoint: PipelineEntrypointCallable,
    config: ModelPairExecutionApiConfig,
) -> dict[str, Any]:
    if not isinstance(config, ModelPairExecutionApiConfig):
        return _invalid_result("config_invalid", config=None)
    if not callable(pipeline_entrypoint):
        return _invalid_result("pipeline_entrypoint_required", config=config)
    try:
        output_dir = _validated_output_dir(config.output_dir)
        executor = make_model_pair_entrypoint_executor(
            pipeline_entrypoint,
            allow_runtime_execution=bool(config.allow_runtime_execution),
            role_config_resolver=config.role_config_resolver,
            scenario_config_resolver=config.scenario_config_resolver,
            model_binding_resolver=config.model_binding_resolver,
            extra_config=config.extra_config,
        )
        summary = run_model_pair_matrix(
            plan,
            executor,
            run_id=config.run_id,
            output_dir=output_dir,
            execution_mode=MODEL_PAIR_EXECUTION_API_EXECUTION_MODE,
            write_trial_results_jsonl=bool(config.write_trial_results_jsonl),
            notes=_api_notes(config.tags),
        )
        adapter_summary: dict[str, Any] | None = None
        if config.auto_matrix_adapter_outputs:
            adapter_summary = write_matrix_run_adapter_outputs(
                summary,
                output_dir / _MATRIX_ADAPTERS_DIRNAME,
                adapter_id=config.adapter_id,
            )
    except ModelPairMatrixPlanError as exc:
        return _invalid_result(str(exc), config=config)
    except MatrixRunAdapterInputLoadError as exc:
        return _invalid_result(str(exc), config=config)
    except OSError:
        return _invalid_result("write_failed", config=config, status="write_failed")
    except (TypeError, ValueError) as exc:
        return _invalid_result(_safe_error_code(exc), config=config)

    return _api_result(
        summary,
        output_dir=output_dir,
        config=config,
        adapter_summary=adapter_summary,
    )


def run_model_pair_execution_matrix_from_plan_path(
    plan_path: str | Path,
    *,
    pipeline_entrypoint: PipelineEntrypointCallable,
    config: ModelPairExecutionApiConfig,
) -> dict[str, Any]:
    return run_model_pair_execution_matrix(
        plan_path,
        pipeline_entrypoint=pipeline_entrypoint,
        config=config,
    )


def _api_result(
    summary: Any,
    *,
    output_dir: Path,
    config: ModelPairExecutionApiConfig,
    adapter_summary: Mapping[str, Any] | None,
) -> dict[str, Any]:
    matrix_summary_path = output_dir / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME
    trial_results_path = (
        output_dir / MODEL_PAIR_TRIAL_RESULTS_JSONL_FILENAME
        if config.write_trial_results_jsonl
        else None
    )
    adapter_summary_path = (
        output_dir / _MATRIX_ADAPTERS_DIRNAME / MATRIX_RUN_ADAPTER_SUMMARY_FILENAME
        if adapter_summary is not None
        else None
    )
    result = {
        "status": "succeeded" if summary.failed_count == 0 else "failed",
        "run_id": summary.run_id,
        "execution_mode": summary.execution_mode,
        "allow_runtime_execution": bool(config.allow_runtime_execution),
        "no_runtime_execution": bool(summary.no_runtime_execution),
        "matrix_summary_path": _relative_path(matrix_summary_path, output_dir),
        "trial_results_path": _relative_path(trial_results_path, output_dir) if trial_results_path else None,
        "adapter_summary_path": _relative_path(adapter_summary_path, output_dir) if adapter_summary_path else None,
        "adapter_resource_observations_path": (
            f"{_MATRIX_ADAPTERS_DIRNAME}/{MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME}"
            if adapter_summary is not None
            else None
        ),
        "adapter_normality_inputs_path": (
            f"{_MATRIX_ADAPTERS_DIRNAME}/{NORMALITY_JUDGE_INPUTS_JSONL_FILENAME}"
            if adapter_summary is not None
            else None
        ),
        "trial_count": summary.trial_count,
        "succeeded_count": summary.succeeded_count,
        "failed_count": summary.failed_count,
        "skipped_count": summary.skipped_count,
        "dry_run_count": summary.dry_run_count,
        "resource_observation_count": _adapter_count(adapter_summary, "resource_observation_count"),
        "normality_input_count": _adapter_count(adapter_summary, "normality_input_count"),
        "normality_missing_trace_count": _adapter_count(adapter_summary, "normality_missing_trace_count"),
        "warnings": _safe_text_list(summary.warnings),
        "notes": _safe_text_list(summary.notes),
        "tags": _safe_text_list(config.tags),
    }
    return _safe_mapping(result)


def _invalid_result(
    error: str,
    *,
    config: ModelPairExecutionApiConfig | None,
    status: str = "invalid_input",
) -> dict[str, Any]:
    allow_runtime = bool(config.allow_runtime_execution) if config is not None else False
    return _safe_mapping(
        {
            "status": status,
            "run_id": _safe_optional_text(config.run_id) if config is not None else None,
            "execution_mode": MODEL_PAIR_EXECUTION_API_EXECUTION_MODE,
            "allow_runtime_execution": allow_runtime,
            "no_runtime_execution": not allow_runtime,
            "matrix_summary_path": None,
            "trial_results_path": None,
            "adapter_summary_path": None,
            "adapter_resource_observations_path": None,
            "adapter_normality_inputs_path": None,
            "trial_count": 0,
            "succeeded_count": 0,
            "failed_count": 0,
            "skipped_count": 0,
            "dry_run_count": 0,
            "resource_observation_count": None,
            "normality_input_count": None,
            "normality_missing_trace_count": None,
            "warnings": [_safe_text(error)],
            "notes": ["model_pair_execution_api_setup_invalid"],
            "tags": _safe_text_list(config.tags) if config is not None else [],
            "error": _safe_text(error),
        }
    )


def _validated_output_dir(value: Path | str) -> Path:
    try:
        output_dir = Path(value)
    except TypeError as exc:
        raise ValueError("output_dir_invalid") from exc
    parts = {part.lower() for part in output_dir.parts}
    if parts & _FORBIDDEN_OUTPUT_DIR_PARTS:
        raise ValueError("output_dir_forbidden")
    return output_dir


def _api_notes(tags: tuple[str, ...]) -> list[str]:
    notes = ["model_pair_execution_api_programmatic_only"]
    safe_tags = _safe_text_list(tags)
    if safe_tags:
        notes.append("api_tags:" + ",".join(safe_tags))
    return notes


def _adapter_count(adapter_summary: Mapping[str, Any] | None, key: str) -> int | None:
    if adapter_summary is None:
        return None
    value = adapter_summary.get(key)
    if isinstance(value, bool):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed >= 0 else None


def _relative_path(path: Path, output_dir: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(output_dir.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return path.name if path.name else "<absolute_path>"


def _safe_error_code(exc: Exception) -> str:
    text = str(exc).strip()
    if not text:
        return exc.__class__.__name__
    if _is_absolute_path(text) or _secret_like_text(text):
        return exc.__class__.__name__
    return _safe_text(text)


def _safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
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


def _safe_text_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_safe_text(value)]
    if isinstance(value, list | tuple | set):
        return [_safe_text(str(item)) for item in list(value)[:_MAX_LIST_ITEMS] if item is not None]
    return [_safe_text(str(value))]


def _safe_text(value: str) -> str:
    text = _redact_secret_text(value)
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"(?<!\w)/(?:[^\s\"']+/)+[^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"\\\\[^\s\"']+", "<absolute_path>", text)
    if _is_absolute_path(text):
        text = "<absolute_path>"
    if len(text) > _MAX_TEXT_CHARS:
        return text[:_MAX_TEXT_CHARS] + "...[truncated]"
    return text


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


def _secret_like_text(value: str) -> bool:
    return bool(re.search(r"(?i)\b(api[_-]?key|token|secret|password|credential|auth)\b", value))


def _is_absolute_path(value: str) -> bool:
    return (
        PureWindowsPath(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or bool(re.match(r"^[A-Za-z]:", value))
    )
