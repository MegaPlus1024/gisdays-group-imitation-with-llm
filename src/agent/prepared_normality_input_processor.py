from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Literal, Mapping

from pydantic import BaseModel, Field, field_validator

from .normality_evaluation_runner import (
    NORMALITY_BATCH_SUMMARY_FILENAME,
    NormalityBatchEvaluationEntry,
    NormalityBatchEvaluationResult,
    write_batch_normality_evaluation_summary,
)
from .normality_judge import (
    NormalityJudgeConfig,
    NormalityJudgeEvent,
    NormalityJudgeInput,
    NormalityJudgeProvider,
    NormalityJudgeResult,
    StaticNormalityJudgeProvider,
    aggregate_normality_results,
    run_normality_judge,
    sanitize_judge_text,
)


PREPARED_NORMALITY_INPUT_PROCESSOR_SCHEMA_VERSION = "prepared_normality_input_processor_v1"
PreparedNormalityProviderMode = Literal["deterministic", "disabled", "static"]

_TRACE_KEYS = ("events", "group_history", "event_history", "activity_trace", "history")
_MAX_INPUT_BYTES = 1_000_000
_MAX_TEXT_CHARS = 500


class PreparedNormalityInputLoadError(ValueError):
    """Controlled prepared-input error safe to expose through CLI JSON."""


class PreparedNormalityInputProcessorConfig(BaseModel):
    provider_mode: PreparedNormalityProviderMode = "deterministic"
    summary_id: str | None = None
    tags: list[str] = Field(default_factory=list)
    output_dir: str | Path | None = None
    max_events: int = 100
    max_text_chars: int = _MAX_TEXT_CHARS
    max_input_bytes: int = _MAX_INPUT_BYTES

    @field_validator("max_events", "max_text_chars", "max_input_bytes")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_events, max_text_chars, and max_input_bytes must be >= 1.")
        return value

    @field_validator("summary_id")
    @classmethod
    def validate_optional_text(cls, value: str | None) -> str | None:
        if value is None:
            return None
        cleaned = value.strip()
        if not cleaned:
            raise ValueError("summary_id must be non-empty when provided.")
        return _safe_text(cleaned)

    @field_validator("tags")
    @classmethod
    def validate_tags(cls, values: list[str]) -> list[str]:
        out: list[str] = []
        seen: set[str] = set()
        for value in values:
            cleaned = _safe_text(str(value)).strip()
            if cleaned and cleaned not in seen:
                out.append(cleaned)
                seen.add(cleaned)
        return out


def load_prepared_normality_inputs(
    path: str | Path,
    *,
    max_input_bytes: int = _MAX_INPUT_BYTES,
) -> list[dict[str, Any]]:
    candidate = Path(path)
    try:
        if not candidate.exists() or not candidate.is_file():
            raise PreparedNormalityInputLoadError("prepared_normality_input_file_missing")
        if candidate.stat().st_size > max_input_bytes:
            raise PreparedNormalityInputLoadError("prepared_normality_input_file_too_large")
        text = candidate.read_text(encoding="utf-8")
    except PreparedNormalityInputLoadError:
        raise
    except OSError as exc:
        raise PreparedNormalityInputLoadError("prepared_normality_input_file_unreadable") from exc
    except UnicodeDecodeError as exc:
        raise PreparedNormalityInputLoadError("prepared_normality_input_file_not_utf8_text") from exc

    rows = _load_jsonl_records(text) if candidate.suffix.lower() == ".jsonl" else _load_json_records(text)
    if not rows:
        raise PreparedNormalityInputLoadError("prepared_normality_input_records_empty")
    for index, row in enumerate(rows, start=1):
        _validate_prepared_record_identity(row, index=index)
    return rows


def convert_prepared_input_to_normality_judge_input(
    record: Mapping[str, Any],
    *,
    max_events: int = 100,
) -> NormalityJudgeInput:
    row = dict(record)
    _validate_prepared_record_identity(row, index=1)
    records = _trace_records(row)
    agent_roles = _agent_roles(records)
    return NormalityJudgeInput(
        scenario_id=_required_text(row.get("scenario_id"), "scenario_id"),
        trial_id=_optional_text(row.get("trial_id")),
        task_summary=_task_summary(row),
        agent_roles=agent_roles,
        events=[
            _event_from_record(trace_record, agent_roles)
            for trace_record in records[:max_events]
            if isinstance(trace_record, Mapping)
        ],
        constraints=_string_list(row.get("constraints")),
        expected_behavior=_optional_text(row.get("expected_behavior")),
        environment_summary=_environment_summary(row),
    )


def process_prepared_normality_inputs(
    inputs: list[Mapping[str, Any]],
    *,
    provider_mode: PreparedNormalityProviderMode = "deterministic",
    output_dir: str | Path | None = None,
    summary_id: str | None = None,
    tags: list[str] | None = None,
    static_result: NormalityJudgeResult | Mapping[str, Any] | None = None,
    max_events: int = 100,
    max_text_chars: int = _MAX_TEXT_CHARS,
) -> NormalityBatchEvaluationResult:
    config = PreparedNormalityInputProcessorConfig(
        provider_mode=provider_mode,
        summary_id=summary_id,
        tags=list(tags or []),
        output_dir=output_dir,
        max_events=max_events,
        max_text_chars=max_text_chars,
    )
    static_judge_result = _coerce_static_result(static_result) if provider_mode == "static" else None
    provider = StaticNormalityJudgeProvider(static_judge_result) if static_judge_result is not None else None

    entries: list[NormalityBatchEvaluationEntry] = []
    judge_results: list[NormalityJudgeResult] = []
    for index, record in enumerate(inputs, start=1):
        row = dict(record)
        entry, judge_result = _process_one_prepared_record(
            row,
            config=config,
            provider=provider,
            index=index,
        )
        entries.append(entry)
        if judge_result is not None:
            judge_results.append(judge_result)

    evaluated_count = sum(1 for entry in entries if entry.status in {"ok", "judge_disabled"})
    failed_count = len(entries) - evaluated_count
    result = NormalityBatchEvaluationResult(
        status=_batch_status(entries, evaluated_count),
        manifest_schema_version=PREPARED_NORMALITY_INPUT_PROCESSOR_SCHEMA_VERSION,
        batch_id=config.summary_id,
        description="Prepared normality judge input processor output. No live model client is created.",
        input_count=len(entries),
        evaluated_count=evaluated_count,
        failed_count=failed_count,
        judge_mode=provider_mode,
        judge_provider=_batch_judge_provider(entries, provider_mode),
        output_dir_relative=_output_dir_relative(output_dir),
        batch_summary_path_relative=_batch_summary_path_relative(output_dir),
        aggregation=_batch_aggregation(entries, judge_results),
        entries=entries,
        warnings=_batch_warnings(entries),
    )
    if output_dir is not None:
        try:
            write_batch_normality_evaluation_summary(result, output_dir)
        except OSError:
            result.status = "write_failed"
            result.warnings = sorted({*result.warnings, "batch_summary_write_failed"})
    return result


def load_static_normality_result(path: str | Path) -> NormalityJudgeResult:
    candidate = Path(path)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise PreparedNormalityInputLoadError("static_result_file_missing") from exc
    except OSError as exc:
        raise PreparedNormalityInputLoadError("static_result_file_unreadable") from exc
    except json.JSONDecodeError as exc:
        raise PreparedNormalityInputLoadError("static_result_json_malformed") from exc
    if not isinstance(payload, dict):
        raise PreparedNormalityInputLoadError("static_result_payload_not_object")
    try:
        return NormalityJudgeResult.model_validate(payload)
    except ValueError as exc:
        raise PreparedNormalityInputLoadError("static_result_validation_failed") from exc


def _process_one_prepared_record(
    record: dict[str, Any],
    *,
    config: PreparedNormalityInputProcessorConfig,
    provider: NormalityJudgeProvider | None,
    index: int,
) -> tuple[NormalityBatchEvaluationEntry, NormalityJudgeResult | None]:
    identity_warnings = _record_identity_warnings(record)
    trace_warnings = _record_trace_warnings(record)
    warnings = sorted({*_string_list(record.get("warnings")), *identity_warnings, *trace_warnings})
    if identity_warnings or trace_warnings:
        return _invalid_entry(record, warnings=warnings, index=index), None

    judge_input = convert_prepared_input_to_normality_judge_input(record, max_events=config.max_events)
    judge_config = _judge_config(config)
    judge_result = run_normality_judge(judge_input, judge_config, provider=provider)
    status = "ok"
    if judge_result.status == "disabled":
        status = "judge_disabled"
        warnings = sorted({*warnings, "normality_judge_disabled"})
    elif judge_result.status == "invalid_input":
        status = "invalid_input"
    entry = _entry_from_judge_result(
        record,
        judge_input=judge_input,
        judge_config=judge_config,
        judge_result=judge_result,
        status=status,
        warnings=warnings,
    )
    return entry, judge_result


def _entry_from_judge_result(
    record: dict[str, Any],
    *,
    judge_input: NormalityJudgeInput,
    judge_config: NormalityJudgeConfig,
    judge_result: NormalityJudgeResult,
    status: str,
    warnings: list[str],
) -> NormalityBatchEvaluationEntry:
    return NormalityBatchEvaluationEntry(
        input_path_display=None,
        input_path_relative=None,
        trial_id=judge_input.trial_id,
        scenario_id=judge_input.scenario_id,
        task_summary=judge_input.task_summary,
        model_pair=_model_pair(record),
        tags=_entry_tags(record),
        status=status,
        label=judge_result.label,
        overall_score=judge_result.overall_score,
        event_count=len(judge_input.events),
        summary_path_relative=None,
        judge_mode=judge_result.judge_mode,
        judge_provider=judge_result.provider_name,
        warnings=warnings,
        findings=judge_result.findings,
        redactions_applied=judge_result.redactions_applied,
        event_preview=_event_preview(judge_input, judge_config),
    )


def _invalid_entry(
    record: dict[str, Any],
    *,
    warnings: list[str],
    index: int,
) -> NormalityBatchEvaluationEntry:
    findings = sorted({warning for warning in warnings if warning})
    if not findings:
        findings = ["prepared_input_invalid"]
    return NormalityBatchEvaluationEntry(
        input_path_display=None,
        input_path_relative=None,
        trial_id=_optional_text(record.get("trial_id")) or f"prepared_input_{index:03d}",
        scenario_id=_optional_text(record.get("scenario_id")),
        task_summary=_optional_text(record.get("task_summary")),
        model_pair=_model_pair(record),
        tags=_entry_tags(record),
        status="invalid_input",
        label="not_evaluated",
        overall_score=0.0,
        event_count=0,
        judge_mode=None,
        judge_provider=None,
        warnings=warnings,
        findings=findings,
        redactions_applied=[],
        event_preview=[],
    )


def _load_jsonl_records(text: str) -> list[dict[str, Any]]:
    records: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PreparedNormalityInputLoadError(f"jsonl_decode_error_line_{line_number}") from exc
        if not isinstance(row, dict):
            raise PreparedNormalityInputLoadError(f"jsonl_record_not_object_line_{line_number}")
        records.append(row)
    return records


def _load_json_records(text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PreparedNormalityInputLoadError("prepared_normality_input_json_malformed") from exc
    if isinstance(payload, list):
        return _coerce_records(payload, source="json")
    if isinstance(payload, dict):
        for key in ("inputs", "normality_inputs", "records"):
            if key in payload:
                return _coerce_records(payload[key], source=key)
        if _looks_like_prepared_record(payload):
            return [payload]
        raise PreparedNormalityInputLoadError("prepared_normality_input_records_missing")
    raise PreparedNormalityInputLoadError("prepared_normality_input_payload_not_supported")


def _coerce_records(payload: Any, *, source: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise PreparedNormalityInputLoadError(f"{source}_records_not_list")
    records: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise PreparedNormalityInputLoadError(f"{source}_record_not_object:{index}")
        records.append(item)
    return records


def _validate_prepared_record_identity(record: dict[str, Any], *, index: int) -> None:
    warnings = _record_identity_warnings(record)
    if warnings:
        raise PreparedNormalityInputLoadError(f"prepared_input_identity_missing:{index}")


def _record_identity_warnings(record: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    if not _optional_text(record.get("trial_id")):
        warnings.append("trial_id_missing")
    if not _optional_text(record.get("scenario_id")):
        warnings.append("scenario_id_missing")
    if not _optional_text(record.get("pair_id")) and not isinstance(record.get("model_pair"), Mapping):
        warnings.append("model_pair_identity_missing")
    return warnings


def _record_trace_warnings(record: dict[str, Any]) -> list[str]:
    warnings: list[str] = []
    existing = set(_string_list(record.get("warnings")))
    if _optional_text(record.get("adapter_status")) == "invalid_input":
        warnings.append("adapter_status_invalid_input")
    if "normality_trace_missing" in existing:
        warnings.append("normality_trace_missing")
    if not _trace_records(record):
        warnings.append("normality_trace_missing")
    return sorted(set(warnings))


def _trace_records(record: Mapping[str, Any]) -> list[dict[str, Any]]:
    for key in _TRACE_KEYS:
        value = record.get(key)
        if isinstance(value, list):
            return [dict(item) for item in value if isinstance(item, Mapping)]
    return []


def _event_from_record(
    record: Mapping[str, Any],
    agent_roles: dict[str, str],
) -> NormalityJudgeEvent:
    metadata = _dict_value(record.get("metadata"))
    next_action = _dict_value(record.get("next_action"))
    parameters = _first_dict(record.get("parameters"), record.get("params"), next_action.get("parameters"))
    agent_id = _optional_text(record.get("agent_id")) or "unknown_agent"
    role = (
        _optional_text(record.get("role"))
        or _optional_text(record.get("agent_role"))
        or agent_roles.get(agent_id)
        or "unknown"
    )
    return NormalityJudgeEvent(
        agent_id=agent_id,
        role=role,
        action=_action_from_record(record, next_action),
        status=_event_status(record, metadata),
        timestamp=_optional_text(record.get("timestamp")),
        error_code=_error_code(record, metadata),
        params_summary=_params_summary(record, parameters),
        result_summary=_result_summary(record),
        artifact_paths=_artifact_paths(record, metadata, parameters),
        policy_decision=_policy_decision(record, metadata),
        notes=_notes(record, metadata),
    )


def _event_preview(judge_input: NormalityJudgeInput, config: NormalityJudgeConfig) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for event in judge_input.events[: config.max_events]:
        params_summary, _ = sanitize_judge_text(event.params_summary, config)
        result_summary, _ = sanitize_judge_text(event.result_summary, config)
        preview.append(
            {
                "agent_id": event.agent_id,
                "role": event.role,
                "action": event.action,
                "status": event.status,
                "error_code": event.error_code,
                "params_summary": params_summary or None,
                "result_summary": result_summary or None,
                "artifact_paths": [_safe_artifact_path(path) for path in event.artifact_paths],
                "policy_decision": event.policy_decision,
                "notes": [sanitize_judge_text(note, config)[0] for note in event.notes],
            }
        )
    return preview


def _judge_config(config: PreparedNormalityInputProcessorConfig) -> NormalityJudgeConfig:
    if config.provider_mode == "disabled":
        return NormalityJudgeConfig(
            enabled=False,
            mode="disabled",
            judge_provider="disabled",
            max_events=config.max_events,
            max_text_chars=config.max_text_chars,
        )
    return NormalityJudgeConfig(
        enabled=True,
        mode=config.provider_mode,
        judge_provider=config.provider_mode,
        max_events=config.max_events,
        max_text_chars=config.max_text_chars,
    )


def _coerce_static_result(value: NormalityJudgeResult | Mapping[str, Any] | None) -> NormalityJudgeResult:
    if value is None:
        raise PreparedNormalityInputLoadError("static_result_required")
    if isinstance(value, NormalityJudgeResult):
        return value
    try:
        return NormalityJudgeResult.model_validate(dict(value))
    except ValueError as exc:
        raise PreparedNormalityInputLoadError("static_result_validation_failed") from exc


def _batch_status(entries: list[NormalityBatchEvaluationEntry], evaluated_count: int) -> str:
    if not entries or evaluated_count == 0:
        return "invalid_input"
    if all(entry.status == "judge_disabled" for entry in entries):
        return "judge_disabled"
    return "ok"


def _batch_judge_provider(entries: list[NormalityBatchEvaluationEntry], fallback: str) -> str | None:
    for entry in entries:
        if entry.judge_provider:
            return entry.judge_provider
    return fallback


def _batch_warnings(entries: list[NormalityBatchEvaluationEntry]) -> list[str]:
    warnings: set[str] = set()
    for entry in entries:
        warnings.update(entry.warnings)
    return sorted(warnings)


def _batch_aggregation(
    entries: list[NormalityBatchEvaluationEntry],
    judge_results: list[NormalityJudgeResult],
) -> dict[str, Any]:
    successful = [result for result in judge_results if result.status == "ok"]
    aggregation = aggregate_normality_results(successful)
    aggregation["status_counts"] = dict(Counter(entry.status for entry in entries))
    finding_counts: Counter[str] = Counter()
    for entry in entries:
        finding_counts.update(entry.findings)
    aggregation["finding_counts"] = dict(finding_counts)
    return aggregation


def _model_pair(record: Mapping[str, Any]) -> dict[str, str] | None:
    raw_pair = record.get("model_pair")
    if isinstance(raw_pair, Mapping):
        pair = {
            _safe_text(str(key)): _safe_text(str(value))
            for key, value in raw_pair.items()
            if value is not None
        }
        return pair or None
    pair_id = _optional_text(record.get("pair_id"))
    if pair_id:
        return {"pair_id": pair_id}
    return None


def _entry_tags(record: Mapping[str, Any]) -> list[str]:
    return sorted(set(_string_list(record.get("tags"))))


def _agent_roles(records: list[dict[str, Any]]) -> dict[str, str]:
    roles: dict[str, str] = {}
    for record in records:
        agent_id = _optional_text(record.get("agent_id")) or "unknown_agent"
        role = _optional_text(record.get("role")) or _optional_text(record.get("agent_role")) or "unknown"
        roles.setdefault(agent_id, role)
    return roles


def _task_summary(record: Mapping[str, Any]) -> str:
    return (
        _optional_text(record.get("task_summary"))
        or _optional_text(record.get("expected_behavior"))
        or "Evaluate prepared offline normality judge input."
    )


def _environment_summary(record: Mapping[str, Any]) -> str | None:
    metadata = _dict_value(record.get("metadata"))
    source_run_id = _optional_text(metadata.get("source_run_id"))
    pair_id = _optional_text(record.get("pair_id"))
    parts = [part for part in [source_run_id, pair_id] if part]
    return "Prepared matrix adapter normality input: " + ", ".join(parts) if parts else None


def _looks_like_prepared_record(payload: dict[str, Any]) -> bool:
    return bool({"trial_id", "scenario_id", "pair_id", "model_pair"} & set(payload))


def _action_from_record(record: Mapping[str, Any], next_action: Mapping[str, Any]) -> str:
    return (
        _optional_text(record.get("action"))
        or _optional_text(record.get("action_name"))
        or _optional_text(next_action.get("action"))
        or _optional_text(next_action.get("name"))
        or "unknown_action"
    )


def _event_status(record: Mapping[str, Any], metadata: Mapping[str, Any]) -> str:
    explicit = _optional_text(record.get("status"))
    if explicit:
        return explicit
    if metadata.get("execution_success") is True:
        return "success"
    if metadata.get("execution_success") is False:
        return "failure"
    return "unknown"


def _error_code(record: Mapping[str, Any], metadata: Mapping[str, Any]) -> str | None:
    for source in (record, metadata):
        for key in ("error_code", "error_type", "error"):
            value = _optional_text(source.get(key))
            if value:
                return value
    return None


def _params_summary(record: Mapping[str, Any], parameters: Mapping[str, Any]) -> str | None:
    explicit = _optional_text(record.get("params_summary"))
    if explicit:
        return explicit
    if parameters:
        return json.dumps(dict(parameters), ensure_ascii=False, sort_keys=True)
    return None


def _result_summary(record: Mapping[str, Any]) -> str | None:
    for key in ("result_summary", "summary", "message"):
        value = _optional_text(record.get(key))
        if value:
            return value
    result = record.get("result")
    if isinstance(result, str) and result.strip():
        return result
    if isinstance(result, Mapping):
        for key in ("summary", "message"):
            value = _optional_text(result.get(key))
            if value:
                return value
    return None


def _artifact_paths(
    record: Mapping[str, Any],
    metadata: Mapping[str, Any],
    parameters: Mapping[str, Any],
) -> list[str]:
    paths: list[str] = []
    for source in (record, metadata, parameters):
        paths.extend(_string_list(source.get("artifact_paths")))
        for key in ("artifact_path", "path", "file_path", "output_path", "path_relative"):
            value = _optional_text(source.get(key))
            if value:
                paths.append(value)
    return list(dict.fromkeys(paths))


def _policy_decision(record: Mapping[str, Any], metadata: Mapping[str, Any]) -> str | None:
    explicit = _optional_text(record.get("policy_decision"))
    if explicit:
        return explicit
    virtual_policy = _dict_value(metadata.get("virtual_network_policy"))
    for key in ("code", "decision", "allowed"):
        value = virtual_policy.get(key)
        if value is not None:
            return str(value)
    return None


def _notes(record: Mapping[str, Any], metadata: Mapping[str, Any]) -> list[str]:
    notes = _string_list(record.get("notes"))
    for key in ("execution_attempted", "execution_success", "validation_accepted"):
        if key in metadata:
            notes.append(f"{key}={metadata[key]}")
    return notes


def _output_dir_relative(output_dir: str | Path | None) -> str | None:
    if output_dir is None:
        return None
    return Path(output_dir).name


def _batch_summary_path_relative(output_dir: str | Path | None) -> str | None:
    if output_dir is None:
        return None
    return NORMALITY_BATCH_SUMMARY_FILENAME


def _safe_artifact_path(path: str) -> str:
    if _is_absolute_path(path):
        return "<absolute_path>"
    return _safe_text(str(path))


def _is_absolute_path(value: str) -> bool:
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute() or bool(re.match(r"^[A-Za-z]:", value))


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, Mapping):
            return dict(value)
    return {}


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_safe_text(value)]
    if isinstance(value, list | tuple | set):
        return [_safe_text(str(item)) for item in value if item is not None]
    return [_safe_text(str(value))]


def _required_text(value: Any, field_name: str) -> str:
    text = _optional_text(value)
    if text is None:
        raise PreparedNormalityInputLoadError(f"{field_name}_missing")
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = _safe_text(str(value)).strip()
    return text or None


def _safe_text(value: str) -> str:
    safe, _ = sanitize_judge_text(
        value,
        NormalityJudgeConfig(enabled=True, mode="deterministic", max_text_chars=_MAX_TEXT_CHARS),
    )
    return safe
