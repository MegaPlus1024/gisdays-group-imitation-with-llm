from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal

from .model_pair_matrix_runner import (
    ModelPairMatrixPlanError,
    build_trial_execution_requests_from_plan,
)
from .model_pair_pipeline_bridge import build_pipeline_trial_context
from .model_pair_pipeline_entrypoint_wrapper import (
    PipelineEntrypointResolver,
    build_pipeline_entrypoint_input,
)


MODEL_PAIR_EXECUTION_READINESS_SCHEMA_VERSION = "model_pair_execution_readiness_v1"
MODEL_PAIR_EXECUTION_READINESS_SUMMARY_FILENAME = "model_pair_execution_readiness_summary.json"
MODEL_PAIR_EXECUTION_READINESS_EXECUTION_MODE = "readiness_validation"

ReadinessStatus = Literal["ready", "not_ready"]
FindingSeverity = Literal["error", "warning", "info"]

_MAX_TEXT_CHARS = 500
_MAX_LIST_ITEMS = 200
_FORBIDDEN_OUTPUT_DIR_PARTS = {"reports", "experiments"}


@dataclass(frozen=True)
class ModelPairExecutionReadinessConfig:
    allow_runtime_execution: bool = False
    require_model_bindings: bool = True
    require_scenario_config: bool = True
    require_role_config: bool = False
    require_runtime_opt_in_for_real: bool = True
    tags: tuple[str, ...] = ()


def validate_model_pair_execution_readiness(
    plan: Any,
    *,
    role_config_resolver: PipelineEntrypointResolver | None = None,
    scenario_config_resolver: PipelineEntrypointResolver | None = None,
    model_binding_resolver: PipelineEntrypointResolver | None = None,
    config: ModelPairExecutionReadinessConfig | None = None,
) -> dict[str, Any]:
    cfg = config or ModelPairExecutionReadinessConfig()
    findings: list[dict[str, Any]] = []
    warnings: list[str] = []
    notes = ["Readiness validation only; no runtime execution performed."]
    if cfg.allow_runtime_execution:
        notes.append("Runtime opt-in was validated only; no runtime execution performed.")
    if cfg.tags:
        notes.append("readiness_tags:" + ",".join(_safe_text_list(cfg.tags)))

    try:
        requests = build_trial_execution_requests_from_plan(
            plan,
            execution_mode=MODEL_PAIR_EXECUTION_READINESS_EXECUTION_MODE,
        )
    except ModelPairMatrixPlanError as exc:
        finding = _finding(
            "error",
            "plan_invalid",
            message=str(exc),
        )
        return _summary(
            allow_runtime_execution=cfg.allow_runtime_execution,
            requests=[],
            ready_trial_ids=set(),
            findings=[finding],
            warnings=[],
            notes=notes,
            tags=cfg.tags,
        )

    ready_trial_ids: set[str] = set()
    for request in requests:
        context = build_pipeline_trial_context(request)
        tracker = _ResolverTracker()
        entrypoint_input = build_pipeline_entrypoint_input(
            context,
            role_config_resolver=_tracked_resolver(
                "role_config",
                role_config_resolver,
                tracker,
                request_context=context,
            ),
            scenario_config_resolver=_tracked_resolver(
                "scenario_config",
                scenario_config_resolver,
                tracker,
                request_context=context,
            ),
            model_binding_resolver=_tracked_resolver(
                "model_bindings",
                model_binding_resolver,
                tracker,
                request_context=context,
            ),
        )
        entrypoint_input["execution_options"]["allow_runtime_execution"] = bool(cfg.allow_runtime_execution)
        entrypoint_input["execution_options"]["no_runtime_execution"] = not bool(cfg.allow_runtime_execution)
        entrypoint_input["metadata"]["explicit_runtime_opt_in"] = bool(cfg.allow_runtime_execution)

        trial_findings = _validate_trial_entrypoint_input(
            entrypoint_input,
            context,
            tracker,
            config=cfg,
            has_role_resolver=role_config_resolver is not None,
            has_scenario_resolver=scenario_config_resolver is not None,
            has_model_binding_resolver=model_binding_resolver is not None,
        )
        findings.extend(trial_findings)
        if not any(finding["severity"] == "error" for finding in trial_findings):
            ready_trial_ids.add(request.trial_id)

    warnings = sorted({finding["code"] for finding in findings if finding["severity"] == "warning"})
    return _summary(
        allow_runtime_execution=cfg.allow_runtime_execution,
        requests=requests,
        ready_trial_ids=ready_trial_ids,
        findings=findings,
        warnings=warnings,
        notes=notes,
        tags=cfg.tags,
    )


def write_model_pair_execution_readiness_summary(
    summary: Mapping[str, Any],
    output_dir: str | Path,
) -> Path:
    out_dir = _validated_output_dir(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / MODEL_PAIR_EXECUTION_READINESS_SUMMARY_FILENAME
    path.write_text(
        json.dumps(_safe_mapping(summary), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


@dataclass
class _ResolverTracker:
    values: dict[str, dict[str, Any]]
    called: dict[str, int]
    failed: dict[str, str]

    def __init__(self) -> None:
        self.values = {}
        self.called = {}
        self.failed = {}


def _tracked_resolver(
    name: str,
    resolver: PipelineEntrypointResolver | None,
    tracker: _ResolverTracker,
    *,
    request_context: Mapping[str, Any],
) -> Callable[[Mapping[str, Any]], Mapping[str, Any] | None] | None:
    if resolver is None:
        return None

    def _call(context: Mapping[str, Any]) -> Mapping[str, Any] | None:
        tracker.called[name] = tracker.called.get(name, 0) + 1
        try:
            resolved = resolver(context)
        except Exception as exc:
            tracker.failed[name] = _safe_error_code(exc)
            return {}
        if resolved is None:
            tracker.values[name] = {}
            return {}
        if not isinstance(resolved, Mapping):
            tracker.failed[name] = f"{name}_resolver_return_invalid"
            tracker.values[name] = {}
            return {}
        safe = _safe_mapping(resolved)
        tracker.values[name] = safe
        return safe

    _ = request_context
    return _call


def _validate_trial_entrypoint_input(
    entrypoint_input: Mapping[str, Any],
    context: Mapping[str, Any],
    tracker: _ResolverTracker,
    *,
    config: ModelPairExecutionReadinessConfig,
    has_role_resolver: bool,
    has_scenario_resolver: bool,
    has_model_binding_resolver: bool,
) -> list[dict[str, Any]]:
    findings: list[dict[str, Any]] = []
    identity = {
        "trial_id": context.get("trial_id"),
        "pair_id": context.get("pair_id"),
        "scenario_id": context.get("scenario_id"),
    }

    for name, code in (
        ("scenario_config", "scenario_config_resolver_failed"),
        ("role_config", "role_config_resolver_failed"),
        ("model_bindings", "model_binding_resolver_failed"),
    ):
        if name in tracker.failed:
            findings.append(
                _finding(
                    "error",
                    code,
                    message=tracker.failed[name],
                    **identity,
                )
            )

    if config.require_model_bindings:
        if not has_model_binding_resolver:
            findings.append(
                _finding(
                    "error",
                    "model_binding_missing",
                    message="Explicit model binding resolver was not provided.",
                    **identity,
                )
            )
        else:
            bindings = tracker.values.get("model_bindings", {})
            if not bindings:
                findings.append(
                    _finding(
                        "error",
                        "model_binding_missing",
                        message="Explicit model binding resolver returned no bindings.",
                        **identity,
                    )
                )
            else:
                if not _binding_present(bindings.get("orchestrator")):
                    findings.append(
                        _finding(
                            "error",
                            "orchestrator_binding_missing",
                            message="Explicit orchestrator model binding is missing.",
                            **identity,
                        )
                    )
                if not _binding_present(bindings.get("executor")):
                    findings.append(
                        _finding(
                            "error",
                            "executor_binding_missing",
                            message="Explicit executor model binding is missing.",
                            **identity,
                        )
                    )

    if config.require_scenario_config:
        scenario_config = tracker.values.get("scenario_config", {})
        if not has_scenario_resolver or not scenario_config:
            findings.append(
                _finding(
                    "error",
                    "scenario_config_missing",
                    message="Explicit scenario config resolver did not provide scenario config.",
                    **identity,
                )
            )

    role_config = tracker.values.get("role_config", {})
    if config.require_role_config:
        if not has_role_resolver or not role_config:
            findings.append(
                _finding(
                    "error",
                    "role_config_missing",
                    message="Explicit role config resolver did not provide role config.",
                    **identity,
                )
            )
    elif not has_role_resolver or not role_config:
        findings.append(
            _finding(
                "warning",
                "role_config_missing",
                message="Role config was not provided; it is optional for this readiness profile.",
                **identity,
            )
        )

    for field in (
        "trial_id",
        "scenario_id",
        "pair_id",
        "orchestrator_model_id",
        "executor_model_id",
        "execution_options",
        "model_bindings",
        "scenario_config",
    ):
        value = entrypoint_input.get(field)
        if value in (None, "", {}, []):
            findings.append(
                _finding(
                    "error",
                    "entrypoint_required_field_missing",
                    message=f"Required entrypoint input field is missing: {field}",
                    **identity,
                )
            )

    if config.allow_runtime_execution:
        findings.append(
            _finding(
                "info",
                "runtime_opt_in_explicit",
                message="Runtime opt-in was explicit in readiness config; validation still performed no runtime execution.",
                **identity,
            )
        )

    return findings


def _summary(
    *,
    allow_runtime_execution: bool,
    requests: list[Any],
    ready_trial_ids: set[str],
    findings: list[dict[str, Any]],
    warnings: list[str],
    notes: list[str],
    tags: tuple[str, ...],
) -> dict[str, Any]:
    errors = [finding for finding in findings if finding.get("severity") == "error"]
    trial_ids = {request.trial_id for request in requests}
    not_ready_trial_count = len(trial_ids - ready_trial_ids)
    payload = {
        "schema_version": MODEL_PAIR_EXECUTION_READINESS_SCHEMA_VERSION,
        "status": "not_ready" if errors else "ready",
        "allow_runtime_execution": bool(allow_runtime_execution),
        "trial_count": len(requests),
        "ready_trial_count": len(ready_trial_ids),
        "not_ready_trial_count": not_ready_trial_count,
        "model_pair_count": len({request.pair_id for request in requests}),
        "scenario_count": len({request.scenario_id for request in requests}),
        "findings": findings,
        "warnings": sorted(_safe_text_list(warnings)),
        "notes": _safe_text_list(notes),
        "tags": _safe_text_list(tags),
        "no_runtime_execution": True,
    }
    return _safe_mapping(payload)


def _binding_present(value: Any) -> bool:
    if isinstance(value, Mapping):
        return bool(
            _safe_optional_text(value.get("model_id"))
            or _safe_optional_text(value.get("model_name"))
            or _safe_optional_text(value.get("binding_id"))
            or _safe_optional_text(value.get("provider"))
        )
    return _safe_optional_text(value) is not None


def _finding(
    severity: FindingSeverity,
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


def _validated_output_dir(value: str | Path) -> Path:
    try:
        out_dir = Path(value)
    except TypeError as exc:
        raise ValueError("output_dir_invalid") from exc
    parts = {part.lower() for part in out_dir.parts}
    if parts & _FORBIDDEN_OUTPUT_DIR_PARTS:
        raise ValueError("output_dir_forbidden")
    return out_dir


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
        if item is not None and not _secret_like_key(str(key))
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
