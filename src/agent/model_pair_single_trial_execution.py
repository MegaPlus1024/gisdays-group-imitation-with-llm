from __future__ import annotations

import json
import re
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .model_pair_matrix_adapters import (
    MATRIX_RUN_ADAPTER_SUMMARY_FILENAME,
    MatrixRunAdapterInputLoadError,
    write_matrix_run_adapter_outputs,
)
from .model_pair_matrix_runner import (
    ModelPairMatrixPlanError,
    ModelPairMatrixRunSummary,
    ModelPairTrialExecutionRequest,
    ModelPairTrialExecutionResult,
    build_trial_execution_requests_from_plan,
)
from .model_pair_pipeline_entrypoint_wrapper import (
    PipelineEntrypointCallable,
    PipelineEntrypointResolver,
    make_model_pair_entrypoint_executor,
)


MODEL_PAIR_SINGLE_TRIAL_EXECUTION_SCHEMA_VERSION = "model_pair_single_trial_execution_v1"
MODEL_PAIR_SINGLE_TRIAL_MATRIX_SUMMARY_FILENAME = "model_pair_single_trial_matrix_summary.json"
MODEL_PAIR_SINGLE_TRIAL_RESULT_FILENAME = "model_pair_single_trial_result.json"
MODEL_PAIR_SINGLE_TRIAL_EXECUTION_MODE = "single_trial_execution"

_MATRIX_ADAPTERS_DIRNAME = "matrix_adapters"
_MAX_TEXT_CHARS = 500
_MAX_LIST_ITEMS = 200
_FORBIDDEN_OUTPUT_DIR_PARTS = {"reports", "experiments"}


@dataclass(frozen=True)
class ModelPairSingleTrialExecutionConfig:
    output_dir: Path | str
    trial_id: str | None = None
    pair_id: str | None = None
    scenario_id: str | None = None
    repeat_index: int | None = None
    allow_runtime_execution: bool = False
    require_ready_readiness_summary: bool = True
    readiness_summary_path: Path | str | None = None
    write_matrix_summary: bool = True
    write_trial_result: bool = True
    auto_matrix_adapter_outputs: bool = False
    adapter_id: str | None = None
    role_config_resolver: PipelineEntrypointResolver | None = None
    scenario_config_resolver: PipelineEntrypointResolver | None = None
    model_binding_resolver: PipelineEntrypointResolver | None = None
    extra_config: Mapping[str, Any] | None = None
    run_id: str | None = None
    tags: tuple[str, ...] = ()


def run_single_model_pair_trial(
    plan: Any,
    *,
    pipeline_entrypoint: PipelineEntrypointCallable,
    config: ModelPairSingleTrialExecutionConfig,
) -> dict[str, Any]:
    if not isinstance(config, ModelPairSingleTrialExecutionConfig):
        return _invalid_result("config_invalid", config=None)
    if not callable(pipeline_entrypoint):
        return _invalid_result("pipeline_entrypoint_required", config=config)

    try:
        output_dir = _validated_output_dir(config.output_dir)
        requests = build_trial_execution_requests_from_plan(
            plan,
            execution_mode=MODEL_PAIR_SINGLE_TRIAL_EXECUTION_MODE,
        )
        selected = _select_single_trial(requests, config)
        gate_findings: list[dict[str, Any]] = []
        if config.require_ready_readiness_summary:
            readiness_summary = _load_readiness_summary(config.readiness_summary_path)
            gate_findings = validate_single_trial_readiness_gate(
                readiness_summary,
                trial_id=selected.trial_id,
                pair_id=selected.pair_id,
                scenario_id=selected.scenario_id,
            )
            gate_errors = [finding for finding in gate_findings if finding.get("severity") == "error"]
            if gate_errors:
                return _invalid_result(
                    "single_trial_readiness_gate_failed",
                    config=config,
                    request=selected,
                    gate_findings=gate_findings,
                )

        executor = make_model_pair_entrypoint_executor(
            pipeline_entrypoint,
            allow_runtime_execution=bool(config.allow_runtime_execution),
            role_config_resolver=config.role_config_resolver,
            scenario_config_resolver=config.scenario_config_resolver,
            model_binding_resolver=config.model_binding_resolver,
            extra_config=config.extra_config,
        )
        trial_result = executor.execute_trial(selected)
        matrix_summary = _single_trial_matrix_summary(
            selected,
            trial_result,
            run_id=config.run_id or "model_pair_single_trial_execution",
            notes=_api_notes(config.tags),
        )

        matrix_summary_path: Path | None = None
        trial_result_path: Path | None = None
        adapter_summary: dict[str, Any] | None = None
        if config.write_matrix_summary:
            matrix_summary_path = _write_matrix_summary(matrix_summary, output_dir)
        if config.write_trial_result:
            trial_result_path = _write_trial_result(trial_result, output_dir)
        if config.auto_matrix_adapter_outputs:
            adapter_summary = write_matrix_run_adapter_outputs(
                matrix_summary,
                output_dir / _MATRIX_ADAPTERS_DIRNAME,
                adapter_id=config.adapter_id,
            )
    except ModelPairMatrixPlanError as exc:
        return _invalid_result(str(exc), config=config)
    except MatrixRunAdapterInputLoadError as exc:
        return _invalid_result(str(exc), config=config)
    except OSError:
        return _invalid_result("write_failed", config=config)
    except (TypeError, ValueError) as exc:
        return _invalid_result(_safe_error_code(exc), config=config)

    return _api_result(
        selected,
        trial_result,
        matrix_summary,
        output_dir=output_dir,
        matrix_summary_path=matrix_summary_path,
        trial_result_path=trial_result_path,
        adapter_summary=adapter_summary,
        config=config,
        gate_findings=gate_findings,
    )


def validate_single_trial_readiness_gate(
    readiness_summary: Any,
    *,
    trial_id: str,
    pair_id: str,
    scenario_id: str,
) -> list[dict[str, Any]]:
    payload, load_findings = _coerce_readiness_summary(readiness_summary)
    if load_findings:
        return load_findings
    findings: list[dict[str, Any]] = []
    status = _safe_optional_text(payload.get("status"))
    if status != "ready":
        findings.append(
            _finding(
                "error",
                "readiness_summary_not_ready",
                trial_id=trial_id,
                pair_id=pair_id,
                scenario_id=scenario_id,
                message="Readiness summary status is not ready.",
            )
        )
    rows = payload.get("findings")
    if not isinstance(rows, list):
        findings.append(
            _finding(
                "error",
                "readiness_summary_malformed",
                trial_id=trial_id,
                pair_id=pair_id,
                scenario_id=scenario_id,
                message="Readiness summary findings must be an array.",
            )
        )
        return findings
    for row in rows:
        if not isinstance(row, Mapping):
            findings.append(
                _finding(
                    "error",
                    "readiness_summary_malformed",
                    trial_id=trial_id,
                    pair_id=pair_id,
                    scenario_id=scenario_id,
                    message="Readiness summary finding must be an object.",
                )
            )
            continue
        if not _finding_matches_selected(row, trial_id=trial_id, pair_id=pair_id, scenario_id=scenario_id):
            continue
        severity = _safe_optional_text(row.get("severity")) or "warning"
        code = _safe_optional_text(row.get("code")) or "readiness_finding"
        if severity == "error":
            findings.append(
                _finding(
                    "error",
                    "selected_trial_not_ready",
                    trial_id=trial_id,
                    pair_id=pair_id,
                    scenario_id=scenario_id,
                    message=code,
                )
            )
        elif severity == "warning":
            findings.append(
                _finding(
                    "warning",
                    code,
                    trial_id=trial_id,
                    pair_id=pair_id,
                    scenario_id=scenario_id,
                    message=_safe_optional_text(row.get("message")) or code,
                )
            )
    return findings


def _select_single_trial(
    requests: list[ModelPairTrialExecutionRequest],
    config: ModelPairSingleTrialExecutionConfig,
) -> ModelPairTrialExecutionRequest:
    trial_id = _safe_optional_text(config.trial_id)
    pair_id = _safe_optional_text(config.pair_id)
    scenario_id = _safe_optional_text(config.scenario_id)
    repeat_index = config.repeat_index
    if trial_id:
        matches = [request for request in requests if request.trial_id == trial_id]
    else:
        if not pair_id or not scenario_id:
            raise ValueError("trial_selector_required")
        matches = [
            request
            for request in requests
            if request.pair_id == pair_id
            and request.scenario_id == scenario_id
            and (repeat_index is None or request.repeat_index == repeat_index)
        ]
    if not matches:
        raise ValueError("selected_trial_not_found")
    if len(matches) > 1:
        raise ValueError("selected_trial_ambiguous")
    return matches[0]


def _load_readiness_summary(path: str | Path | None) -> dict[str, Any] | None:
    if path is None:
        return None
    candidate = Path(path)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ValueError("readiness_summary_missing") from exc
    except OSError as exc:
        raise ValueError("readiness_summary_unreadable") from exc
    except json.JSONDecodeError as exc:
        raise ValueError("readiness_summary_malformed") from exc
    if not isinstance(payload, dict):
        raise ValueError("readiness_summary_malformed")
    return payload


def _coerce_readiness_summary(readiness_summary: Any) -> tuple[dict[str, Any], list[dict[str, Any]]]:
    if readiness_summary is None:
        return {}, [_finding("error", "readiness_summary_missing", message="Readiness summary is required.")]
    if isinstance(readiness_summary, Mapping):
        return dict(readiness_summary), []
    path = Path(readiness_summary)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}, [_finding("error", "readiness_summary_missing", message="Readiness summary file is missing.")]
    except (OSError, json.JSONDecodeError):
        return {}, [_finding("error", "readiness_summary_malformed", message="Readiness summary is malformed.")]
    if not isinstance(payload, dict):
        return {}, [_finding("error", "readiness_summary_malformed", message="Readiness summary must be an object.")]
    return payload, []


def _finding_matches_selected(
    finding: Mapping[str, Any],
    *,
    trial_id: str,
    pair_id: str,
    scenario_id: str,
) -> bool:
    finding_trial_id = _safe_optional_text(finding.get("trial_id"))
    if finding_trial_id:
        return finding_trial_id == trial_id
    finding_pair_id = _safe_optional_text(finding.get("pair_id"))
    finding_scenario_id = _safe_optional_text(finding.get("scenario_id"))
    return finding_pair_id == pair_id and finding_scenario_id == scenario_id


def _single_trial_matrix_summary(
    request: ModelPairTrialExecutionRequest,
    result: ModelPairTrialExecutionResult,
    *,
    run_id: str,
    notes: list[str],
) -> ModelPairMatrixRunSummary:
    status_counts = Counter([result.status])
    warnings = sorted(set(result.warnings))
    result_ids = [result.trial_id]
    pair_summary = {
        "pair_id": request.pair_id,
        "trial_count": 1,
        "succeeded_count": status_counts["succeeded"],
        "failed_count": status_counts["failed"],
        "skipped_count": status_counts["skipped"],
        "dry_run_count": status_counts["dry_run"],
        "task_success_count": 1 if result.task_success is True else 0,
        "task_failure_count": 1 if result.task_success is False else 0,
        "mean_correctness_score": result.correctness_score,
        "normality_input_ref_count": 1 if result.normality_input_ref else 0,
        "resource_observation_count": 1 if result.resource_observation is not None else 0,
        "trial_ids": result_ids,
        "warnings": warnings,
        "orchestrator_model_id": result.orchestrator_model_id,
        "executor_model_id": result.executor_model_id,
        "scenario_ids": [result.scenario_id],
    }
    scenario_summary = {
        "scenario_id": request.scenario_id,
        "trial_count": 1,
        "succeeded_count": status_counts["succeeded"],
        "failed_count": status_counts["failed"],
        "skipped_count": status_counts["skipped"],
        "dry_run_count": status_counts["dry_run"],
        "task_success_count": 1 if result.task_success is True else 0,
        "task_failure_count": 1 if result.task_success is False else 0,
        "mean_correctness_score": result.correctness_score,
        "normality_input_ref_count": 1 if result.normality_input_ref else 0,
        "resource_observation_count": 1 if result.resource_observation is not None else 0,
        "trial_ids": result_ids,
        "warnings": warnings,
        "scenario_path": request.scenario_path,
        "pair_ids": [request.pair_id],
    }
    return ModelPairMatrixRunSummary(
        run_id=run_id,
        plan_id=_safe_optional_text(request.metadata.get("plan_id")) or "model_pair_single_trial_execution",
        execution_mode=MODEL_PAIR_SINGLE_TRIAL_EXECUTION_MODE,
        trial_count=1,
        succeeded_count=status_counts["succeeded"],
        failed_count=status_counts["failed"],
        skipped_count=status_counts["skipped"],
        dry_run_count=status_counts["dry_run"],
        pair_summaries=[pair_summary],
        scenario_summaries=[scenario_summary],
        trial_results=[result],
        warnings=warnings,
        notes=["Single trial model pair execution only.", *notes],
        no_runtime_execution=bool(request.no_runtime_execution and result.no_runtime_execution),
    )


def _write_matrix_summary(summary: ModelPairMatrixRunSummary, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / MODEL_PAIR_SINGLE_TRIAL_MATRIX_SUMMARY_FILENAME
    path.write_text(
        json.dumps(summary.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _write_trial_result(result: ModelPairTrialExecutionResult, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / MODEL_PAIR_SINGLE_TRIAL_RESULT_FILENAME
    path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _api_result(
    request: ModelPairTrialExecutionRequest,
    result: ModelPairTrialExecutionResult,
    matrix_summary: ModelPairMatrixRunSummary,
    *,
    output_dir: Path,
    matrix_summary_path: Path | None,
    trial_result_path: Path | None,
    adapter_summary: Mapping[str, Any] | None,
    config: ModelPairSingleTrialExecutionConfig,
    gate_findings: list[dict[str, Any]],
) -> dict[str, Any]:
    adapter_summary_path = (
        output_dir / _MATRIX_ADAPTERS_DIRNAME / MATRIX_RUN_ADAPTER_SUMMARY_FILENAME
        if adapter_summary is not None
        else None
    )
    warning_codes = [finding["code"] for finding in gate_findings if finding.get("severity") == "warning"]
    payload = {
        "schema_version": MODEL_PAIR_SINGLE_TRIAL_EXECUTION_SCHEMA_VERSION,
        "status": result.status if result.status in {"succeeded", "failed", "skipped"} else "failed",
        "run_id": matrix_summary.run_id,
        "trial_id": result.trial_id,
        "pair_id": result.pair_id,
        "scenario_id": result.scenario_id,
        "repeat_index": request.repeat_index,
        "allow_runtime_execution": bool(config.allow_runtime_execution),
        "no_runtime_execution": bool(matrix_summary.no_runtime_execution),
        "trial_result": result.model_dump(mode="json"),
        "matrix_summary_path": _relative_path(matrix_summary_path, output_dir) if matrix_summary_path else None,
        "trial_result_path": _relative_path(trial_result_path, output_dir) if trial_result_path else None,
        "adapter_summary_path": _relative_path(adapter_summary_path, output_dir) if adapter_summary_path else None,
        "warnings": sorted(set([*warning_codes, *result.warnings, *matrix_summary.warnings])),
        "notes": _safe_text_list([*matrix_summary.notes, *result.notes]),
        "tags": _safe_text_list(config.tags),
    }
    return _safe_mapping(payload)


def _invalid_result(
    error: str,
    *,
    config: ModelPairSingleTrialExecutionConfig | None,
    request: ModelPairTrialExecutionRequest | None = None,
    gate_findings: list[dict[str, Any]] | None = None,
) -> dict[str, Any]:
    gate_findings = gate_findings or []
    warnings = [error, *(finding["code"] for finding in gate_findings if finding.get("severity") == "warning")]
    payload = {
        "schema_version": MODEL_PAIR_SINGLE_TRIAL_EXECUTION_SCHEMA_VERSION,
        "status": "invalid",
        "run_id": _safe_optional_text(config.run_id) if config is not None else None,
        "trial_id": request.trial_id if request else _safe_optional_text(config.trial_id) if config else None,
        "pair_id": request.pair_id if request else _safe_optional_text(config.pair_id) if config else None,
        "scenario_id": request.scenario_id if request else _safe_optional_text(config.scenario_id) if config else None,
        "repeat_index": request.repeat_index if request else config.repeat_index if config else None,
        "allow_runtime_execution": bool(config.allow_runtime_execution) if config else False,
        "no_runtime_execution": True,
        "trial_result": {},
        "matrix_summary_path": None,
        "trial_result_path": None,
        "adapter_summary_path": None,
        "warnings": sorted(set(_safe_text_list(warnings))),
        "notes": ["single_trial_execution_invalid"],
        "findings": gate_findings,
        "tags": _safe_text_list(config.tags) if config else [],
        "error": _safe_text(error),
    }
    return _safe_mapping(payload)


def _api_notes(tags: tuple[str, ...]) -> list[str]:
    notes = ["model_pair_single_trial_execution_programmatic_only"]
    safe_tags = _safe_text_list(tags)
    if safe_tags:
        notes.append("single_trial_tags:" + ",".join(safe_tags))
    return notes


def _validated_output_dir(value: str | Path) -> Path:
    try:
        out_dir = Path(value)
    except TypeError as exc:
        raise ValueError("output_dir_invalid") from exc
    parts = {part.lower() for part in out_dir.parts}
    if parts & _FORBIDDEN_OUTPUT_DIR_PARTS:
        raise ValueError("output_dir_forbidden")
    return out_dir


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
