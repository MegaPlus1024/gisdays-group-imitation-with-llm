from __future__ import annotations

import dataclasses
import importlib
import re
from collections.abc import Mapping
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


LOCAL_MODEL_PAIR_PIPELINE_ENTRYPOINT = "run_local_model_pair_trial"

_MAX_TEXT_CHARS = 500
_MAX_LIST_ITEMS = 200
_ARTIFACT_KEYS = ("artifact_refs", "artifacts", "output_files", "generated_files")
_FORBIDDEN_OUTPUT_DIR_PARTS = {"reports", "experiments"}


class LocalPipelineEntrypointConfigurationError(RuntimeError):
    """Controlled local entrypoint setup error safe to expose as an error code."""

    def __init__(self, code: str = "local_pipeline_entrypoint_not_configured") -> None:
        super().__init__(code)
        self.code = code


def run_local_model_pair_trial(entrypoint_input: Mapping[str, Any]) -> dict[str, Any]:
    if not is_runtime_execution_enabled(entrypoint_input):
        return _no_runtime_result()

    findings = validate_local_entrypoint_runtime_config(entrypoint_input)
    errors = [finding for finding in findings if finding.get("severity") == "error"]
    if errors:
        return _failed_result(
            "local_pipeline_entrypoint_config_invalid",
            entrypoint_input=entrypoint_input,
            findings=findings,
            notes=["Local pipeline entrypoint runtime config is invalid."],
        )

    try:
        pipeline_result = _run_existing_pipeline_entrypoint(entrypoint_input)
    except LocalPipelineEntrypointConfigurationError as exc:
        return _failed_result(
            _safe_local_error_code(exc.code),
            entrypoint_input=entrypoint_input,
            findings=[
                _finding(
                    "error",
                    _safe_local_error_code(exc.code),
                    message="Local pipeline entrypoint is not configured for runtime execution.",
                )
            ],
            notes=["Local pipeline entrypoint runtime path is not configured."],
        )
    except Exception:
        return _failed_result(
            "local_pipeline_entrypoint_failed",
            entrypoint_input=entrypoint_input,
            findings=[
                _finding(
                    "error",
                    "local_pipeline_entrypoint_failed",
                    message="Local pipeline entrypoint failed before producing a result.",
                )
            ],
            notes=["Local pipeline entrypoint failed before producing a result."],
        )

    return _safe_pipeline_result(pipeline_result, entrypoint_input=entrypoint_input)


def is_runtime_execution_enabled(entrypoint_input: Mapping[str, Any]) -> bool:
    if not isinstance(entrypoint_input, Mapping):
        return False
    execution_options = entrypoint_input.get("execution_options")
    if not isinstance(execution_options, Mapping):
        return False
    return execution_options.get("allow_runtime_execution") is True


def validate_local_entrypoint_runtime_config(entrypoint_input: Mapping[str, Any]) -> list[dict[str, Any]]:
    if not isinstance(entrypoint_input, Mapping):
        return [_finding("error", "entrypoint_input_invalid", message="Entrypoint input must be an object.")]

    findings: list[dict[str, Any]] = []
    if not is_runtime_execution_enabled(entrypoint_input):
        findings.append(
            _finding(
                "error",
                "runtime_execution_not_enabled",
                trial_id=entrypoint_input.get("trial_id"),
                pair_id=entrypoint_input.get("pair_id"),
                scenario_id=entrypoint_input.get("scenario_id"),
                message="Runtime execution must be explicitly enabled.",
            )
        )

    for field in ("trial_id", "pair_id", "scenario_id", "orchestrator_model_id", "executor_model_id"):
        if not _safe_optional_text(entrypoint_input.get(field)):
            findings.append(
                _finding(
                    "error",
                    f"{field}_missing",
                    trial_id=entrypoint_input.get("trial_id"),
                    pair_id=entrypoint_input.get("pair_id"),
                    scenario_id=entrypoint_input.get("scenario_id"),
                    message=f"Required entrypoint input field is missing: {field}",
                )
            )

    scenario_config = entrypoint_input.get("scenario_config")
    if not isinstance(scenario_config, Mapping) or not scenario_config:
        findings.append(
            _finding(
                "error",
                "scenario_config_missing",
                trial_id=entrypoint_input.get("trial_id"),
                pair_id=entrypoint_input.get("pair_id"),
                scenario_id=entrypoint_input.get("scenario_id"),
                message="Scenario config is required for runtime mode.",
            )
        )

    if _local_pipeline_config(entrypoint_input) is None:
        findings.append(
            _finding(
                "error",
                "local_pipeline_entrypoint_runtime_dependency_missing",
                trial_id=entrypoint_input.get("trial_id"),
                pair_id=entrypoint_input.get("pair_id"),
                scenario_id=entrypoint_input.get("scenario_id"),
                message="local_pipeline_config is required for runtime mode.",
            )
        )

    model_bindings = entrypoint_input.get("model_bindings")
    if not isinstance(model_bindings, Mapping) or not model_bindings:
        findings.append(
            _finding(
                "error",
                "model_bindings_missing",
                trial_id=entrypoint_input.get("trial_id"),
                pair_id=entrypoint_input.get("pair_id"),
                scenario_id=entrypoint_input.get("scenario_id"),
                message="Model bindings are required for runtime mode.",
            )
        )
        return findings

    for role in ("orchestrator", "executor"):
        binding = model_bindings.get(role)
        if not isinstance(binding, Mapping) or not binding:
            findings.append(
                _finding(
                    "error",
                    f"{role}_binding_missing",
                    trial_id=entrypoint_input.get("trial_id"),
                    pair_id=entrypoint_input.get("pair_id"),
                    scenario_id=entrypoint_input.get("scenario_id"),
                    message=f"{role} model binding is required for runtime mode.",
                )
            )
            continue
        if not _safe_optional_text(binding.get("model_id")):
            findings.append(
                _finding(
                    "error",
                    f"{role}_binding_model_id_missing",
                    trial_id=entrypoint_input.get("trial_id"),
                    pair_id=entrypoint_input.get("pair_id"),
                    scenario_id=entrypoint_input.get("scenario_id"),
                    message=f"{role} model binding must include model_id.",
                )
            )
    return findings


def _run_existing_pipeline_entrypoint(entrypoint_input: Mapping[str, Any]) -> Any:
    pipeline_module = importlib.import_module("src.agent.orchestrator_executor_pipeline")
    config_cls = getattr(pipeline_module, "OrchestratorExecutorRunConfig", None)
    runner_cls = getattr(pipeline_module, "OrchestratorExecutorRunner", None)
    if config_cls is None or runner_cls is None:
        raise LocalPipelineEntrypointConfigurationError("local_pipeline_entrypoint_runtime_dependency_missing")

    config_payload = _existing_pipeline_config_payload(entrypoint_input)
    try:
        if callable(getattr(config_cls, "model_validate", None)):
            config = config_cls.model_validate(config_payload)
        else:
            config = config_cls(**config_payload)
        runner = runner_cls(config)
    except LocalPipelineEntrypointConfigurationError:
        raise
    except Exception as exc:
        raise LocalPipelineEntrypointConfigurationError("local_pipeline_entrypoint_config_invalid") from exc
    run = getattr(runner, "run", None)
    if not callable(run):
        raise LocalPipelineEntrypointConfigurationError("local_pipeline_entrypoint_runtime_dependency_missing")
    return run()


def _existing_pipeline_config_payload(entrypoint_input: Mapping[str, Any]) -> dict[str, Any]:
    local_config = _local_pipeline_config(entrypoint_input)
    if local_config is None:
        raise LocalPipelineEntrypointConfigurationError("local_pipeline_entrypoint_runtime_dependency_missing")
    payload = dict(local_config)
    payload.setdefault("scenario_path", _safe_optional_text(entrypoint_input.get("scenario_path")))
    payload.setdefault("run_id", _safe_optional_text(entrypoint_input.get("trial_id")) or "local_model_pair_trial")
    payload.setdefault("orchestrator_model_id", _safe_optional_text(entrypoint_input.get("orchestrator_model_id")))
    payload.setdefault("executor_model_id", _safe_optional_text(entrypoint_input.get("executor_model_id")))
    _validate_existing_pipeline_out_dir(payload.get("out_dir"))
    return {key: value for key, value in payload.items() if value is not None}


def _local_pipeline_config(entrypoint_input: Mapping[str, Any]) -> dict[str, Any] | None:
    for candidate in _local_pipeline_config_candidates(entrypoint_input):
        if isinstance(candidate, Mapping):
            return dict(candidate)
    return None


def _local_pipeline_config_candidates(entrypoint_input: Mapping[str, Any]) -> list[Any]:
    candidates: list[Any] = [entrypoint_input.get("local_pipeline_config")]
    extra_config = entrypoint_input.get("extra_config")
    if isinstance(extra_config, Mapping):
        candidates.extend(
            [
                extra_config.get("local_pipeline_config"),
                extra_config.get("local_pipeline"),
            ]
        )
    metadata = entrypoint_input.get("metadata")
    if isinstance(metadata, Mapping):
        candidates.append(metadata.get("local_pipeline_config"))
        context_metadata = metadata.get("context_metadata")
        if isinstance(context_metadata, Mapping):
            candidates.append(context_metadata.get("local_pipeline_config"))
    return candidates


def _validate_existing_pipeline_out_dir(value: Any) -> None:
    text = _safe_optional_text(value)
    if not text:
        raise LocalPipelineEntrypointConfigurationError("local_pipeline_entrypoint_runtime_dependency_missing")
    try:
        parts = [part.lower() for part in Path(text).parts]
    except TypeError as exc:
        raise LocalPipelineEntrypointConfigurationError("local_pipeline_entrypoint_config_invalid") from exc
    if set(parts) & _FORBIDDEN_OUTPUT_DIR_PARTS or _is_docs_ai_final_path(parts):
        raise LocalPipelineEntrypointConfigurationError("local_pipeline_entrypoint_output_dir_forbidden")


def _is_docs_ai_final_path(parts: list[str]) -> bool:
    for index in range(0, max(0, len(parts) - 2)):
        if parts[index] == "docs" and parts[index + 1] == "ai" and parts[index + 2].startswith("final"):
            return True
    return False


def _no_runtime_result() -> dict[str, Any]:
    return _safe_mapping(
        {
            "status": "skipped",
            "task_success": False,
            "error_code": "runtime_execution_not_enabled",
            "group_history": [],
            "event_history": [],
            "activity_trace": [],
            "artifact_refs": [],
            "resource_observation": {},
            "warnings": ["runtime_execution_not_enabled"],
            "notes": ["Local pipeline entrypoint loaded but runtime execution was not enabled."],
            "metadata": {
                "entrypoint": LOCAL_MODEL_PAIR_PIPELINE_ENTRYPOINT,
                "no_runtime_execution": True,
            },
            "no_runtime_execution": True,
        }
    )


def _failed_result(
    error_code: str,
    *,
    entrypoint_input: Mapping[str, Any],
    findings: list[dict[str, Any]],
    notes: list[str],
) -> dict[str, Any]:
    warning_codes = [error_code, *(finding["code"] for finding in findings if finding.get("code"))]
    return _safe_mapping(
        {
            "status": "failed",
            "task_success": False,
            "error_code": error_code,
            "group_history": [],
            "event_history": [],
            "activity_trace": [],
            "artifact_refs": [],
            "resource_observation": {},
            "warnings": sorted(set(_safe_text_list(warning_codes))),
            "notes": notes,
            "metadata": {
                "entrypoint": LOCAL_MODEL_PAIR_PIPELINE_ENTRYPOINT,
                "no_runtime_execution": False,
                "findings": findings,
                "trial_id": entrypoint_input.get("trial_id"),
                "pair_id": entrypoint_input.get("pair_id"),
                "scenario_id": entrypoint_input.get("scenario_id"),
            },
            "findings": findings,
            "no_runtime_execution": False,
        }
    )


def _safe_pipeline_result(
    pipeline_result: Any,
    *,
    entrypoint_input: Mapping[str, Any],
) -> dict[str, Any]:
    payload = _payload_dict(pipeline_result)
    metadata = _safe_mapping(payload.get("metadata")) if isinstance(payload.get("metadata"), Mapping) else {}
    metadata.update(
        {
            "entrypoint": LOCAL_MODEL_PAIR_PIPELINE_ENTRYPOINT,
            "no_runtime_execution": False,
            "trial_id": entrypoint_input.get("trial_id"),
            "pair_id": entrypoint_input.get("pair_id"),
            "scenario_id": entrypoint_input.get("scenario_id"),
        }
    )
    return _safe_mapping(
        {
            "status": _safe_optional_text(_first_value(payload, "status", "state", "result_status")) or "failed",
            "task_success": _task_success(payload),
            "success": _optional_bool(_first_value(payload, "success", "completed")),
            "correctness_score": payload.get("correctness_score"),
            "group_history": _history_rows(payload.get("group_history")),
            "event_history": _history_rows(payload.get("event_history")),
            "activity_trace": _activity_trace(payload),
            "artifact_refs": _artifact_refs(payload),
            "resource_observation": (
                _safe_mapping(payload.get("resource_observation"))
                if isinstance(payload.get("resource_observation"), Mapping)
                else {}
            ),
            "error_code": _error_code(payload),
            "warnings": _safe_text_list(payload.get("warnings")),
            "notes": _safe_text_list(payload.get("notes")),
            "metadata": metadata,
            "no_runtime_execution": _optional_bool(payload.get("no_runtime_execution")) or False,
        }
    )


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
        return {key: item for key, item in vars(value).items() if not key.startswith("_")}
    return {}


def _task_success(payload: Mapping[str, Any]) -> bool | None:
    explicit = _optional_bool(_first_value(payload, "task_success", "success", "completed"))
    if explicit is not None:
        return explicit
    status = (_safe_optional_text(_first_value(payload, "status", "state", "result_status")) or "").lower()
    if status in {"completed", "complete", "success", "succeeded", "ok", "passed"}:
        return True
    if status in {"failed", "failure", "error", "errored", "invalid_input", "completed_with_failures"}:
        return False
    return None


def _activity_trace(payload: Mapping[str, Any]) -> list[dict[str, Any]]:
    explicit = _history_rows(payload.get("activity_trace"))
    if explicit:
        return explicit
    for key in ("events", "steps", "conversation", "history"):
        rows = _history_rows(payload.get(key))
        if rows:
            return rows
    return []


def _history_rows(value: Any) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    if not isinstance(value, list):
        return rows
    for item in value[:_MAX_LIST_ITEMS]:
        row = _payload_dict(item)
        if row:
            rows.append(_safe_mapping(row))
    return rows


def _artifact_refs(payload: Mapping[str, Any]) -> list[str]:
    refs: list[str] = []
    for key in _ARTIFACT_KEYS:
        refs.extend(_artifact_refs_from_value(payload.get(key)))
    artifact_dir = _safe_optional_text(payload.get("artifact_dir"))
    if artifact_dir:
        refs.append(artifact_dir)
    return list(dict.fromkeys(refs))[:_MAX_LIST_ITEMS]


def _artifact_refs_from_value(value: Any) -> list[str]:
    refs: list[str] = []
    if not isinstance(value, list):
        return refs
    for item in value[:_MAX_LIST_ITEMS]:
        if isinstance(item, str):
            text = _safe_optional_text(item)
            if text:
                refs.append(text)
            continue
        row = _payload_dict(item)
        for key in ("path", "artifact_path", "file_path", "output_path", "path_relative", "ref"):
            text = _safe_optional_text(row.get(key))
            if text:
                refs.append(text)
    return refs


def _error_code(payload: Mapping[str, Any]) -> str | None:
    for key in ("error_code", "failure_reason", "error_type"):
        text = _safe_optional_text(payload.get(key))
        if text and _looks_like_safe_error_code(text):
            return text
    error = payload.get("error")
    if isinstance(error, Mapping):
        for key in ("error_code", "error_type", "type", "code"):
            text = _safe_optional_text(error.get(key))
            if text and _looks_like_safe_error_code(text):
                return text
    text = _safe_optional_text(error)
    if text and _looks_like_safe_error_code(text):
        return text
    return None


def _first_value(payload: Mapping[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _finding(
    severity: str,
    code: str,
    *,
    message: str,
    trial_id: Any = None,
    pair_id: Any = None,
    scenario_id: Any = None,
) -> dict[str, Any]:
    return _safe_mapping(
        {
            "severity": severity,
            "code": code,
            "trial_id": trial_id,
            "pair_id": pair_id,
            "scenario_id": scenario_id,
            "message": message,
        }
    )


def _safe_local_error_code(value: Any) -> str:
    text = _safe_optional_text(value)
    if text and _looks_like_safe_error_code(text):
        return text
    return "local_pipeline_entrypoint_failed"


def _looks_like_safe_error_code(value: str) -> bool:
    if _secret_like_text(value) or _is_absolute_path(value):
        return False
    return bool(re.fullmatch(r"[A-Za-z0-9_.:-]{1,120}", value))


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


def _optional_bool(value: Any) -> bool | None:
    return value if isinstance(value, bool) else None
