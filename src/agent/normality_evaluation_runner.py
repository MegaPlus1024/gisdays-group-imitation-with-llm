from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from src.agent.normality_judge import (
    NormalityJudgeConfig,
    NormalityJudgeEvent,
    NormalityJudgeInput,
    NormalityJudgeProvider,
    NormalityJudgeResult,
    aggregate_normality_results,
    build_normality_judge_prompt,
    parse_llm_normality_judge_output,
    run_normality_judge,
    sanitize_judge_text,
)


NORMALITY_EVALUATION_RUNNER_SCHEMA_VERSION = "normality_evaluation_runner_v1"
NORMALITY_EVALUATION_SUMMARY_FILENAME = "normality_judge_summary.json"
NORMALITY_BATCH_SUMMARY_FILENAME = "normality_judge_batch_summary.json"
NORMALITY_JUDGE_PROMPT_PREVIEW_FILENAME = "normality_judge_prompt_preview.txt"

NormalityEvaluationRunStatus = Literal[
    "ok",
    "input_missing",
    "invalid_input",
    "judge_disabled",
    "write_failed",
]


class NormalityEvaluationRunConfig(BaseModel):
    enabled: bool = True
    judge_enabled: bool = True
    judge_mode: Literal["fake", "deterministic"] = "deterministic"
    judge_provider: Literal["fake", "deterministic", "disabled", "static", "llm"] = "deterministic"
    write_summary: bool = True
    scenario_id: str | None = None
    task_summary: str | None = None
    input_path: str | None = None
    output_dir: str | None = None
    project_root: Path = Field(default_factory=lambda: Path("."))
    max_events: int = 100
    max_text_chars: int = 500
    max_input_bytes: int = 1_000_000
    include_raw_outputs: bool = False
    redact_paths: bool = True

    @field_validator("max_events", "max_text_chars", "max_input_bytes")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_events, max_text_chars, and max_input_bytes must be >= 1.")
        return value

    def resolve_project_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.project_root / path


class NormalityEventsLoadResult(BaseModel):
    status: Literal["ok", "input_missing", "invalid_input"]
    records: list[dict[str, Any]] = Field(default_factory=list)
    payload_metadata: dict[str, Any] = Field(default_factory=dict)
    input_path_relative: str | None = None
    warnings: list[str] = Field(default_factory=list)


class NormalityEvaluationRunResult(BaseModel):
    status: NormalityEvaluationRunStatus
    scenario_id: str | None = None
    input_path_relative: str | None = None
    output_dir_relative: str | None = None
    summary_path_relative: str | None = None
    event_count: int = 0
    label: str | None = None
    overall_score: float | None = None
    dimension_scores: dict[str, Any] = Field(default_factory=dict)
    findings: list[str] = Field(default_factory=list)
    redactions_applied: list[str] = Field(default_factory=list)
    judge_mode: str | None = None
    judge_provider: str | None = None
    model_called: bool = False
    raw_response_path_relative: str | None = None
    prompt_preview_path_relative: str | None = None
    event_preview: list[dict[str, Any]] = Field(default_factory=list)
    judge_result: NormalityJudgeResult | None = None
    aggregation: dict[str, Any] | None = None
    warnings: list[str] = Field(default_factory=list)
    schema_version: str = NORMALITY_EVALUATION_RUNNER_SCHEMA_VERSION


class NormalityBatchEvaluationEntry(BaseModel):
    input_path_display: str | None = None
    input_path_relative: str | None = None
    status: str
    label: str | None = None
    overall_score: float | None = None
    event_count: int = 0
    summary_path_relative: str | None = None
    judge_mode: str | None = None
    judge_provider: str | None = None
    warnings: list[str] = Field(default_factory=list)
    findings: list[str] = Field(default_factory=list)
    redactions_applied: list[str] = Field(default_factory=list)
    event_preview: list[dict[str, Any]] = Field(default_factory=list)


class NormalityBatchEvaluationResult(BaseModel):
    status: str
    input_count: int
    evaluated_count: int
    failed_count: int
    judge_mode: str | None = None
    judge_provider: str | None = None
    output_dir_relative: str | None = None
    batch_summary_path_relative: str | None = None
    aggregation: dict[str, Any] = Field(default_factory=dict)
    entries: list[NormalityBatchEvaluationEntry] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    schema_version: str = NORMALITY_EVALUATION_RUNNER_SCHEMA_VERSION


def load_normality_events_from_file(
    input_path: str | Path | None,
    *,
    project_root: str | Path = Path("."),
    max_input_bytes: int = 1_000_000,
) -> NormalityEventsLoadResult:
    root = Path(project_root)
    if input_path is None:
        return NormalityEventsLoadResult(status="input_missing", warnings=["input_path_missing"])

    path = _resolve_path(input_path, root)
    input_path_relative = _safe_relative(path, root)
    if not path.exists() or not path.is_file():
        return NormalityEventsLoadResult(
            status="input_missing",
            input_path_relative=input_path_relative,
            warnings=["input_file_missing"],
        )

    try:
        if path.stat().st_size > max_input_bytes:
            return NormalityEventsLoadResult(
                status="invalid_input",
                input_path_relative=input_path_relative,
                warnings=["input_file_too_large"],
            )
        text = path.read_text(encoding="utf-8")
    except OSError:
        return NormalityEventsLoadResult(
            status="invalid_input",
            input_path_relative=input_path_relative,
            warnings=["input_file_unreadable"],
        )
    except UnicodeDecodeError:
        return NormalityEventsLoadResult(
            status="invalid_input",
            input_path_relative=input_path_relative,
            warnings=["input_file_not_utf8_text"],
        )

    if path.suffix.lower() == ".jsonl":
        return _load_jsonl_events(text, input_path_relative)
    return _load_json_events(text, input_path_relative)


def run_normality_evaluation_from_file(
    config: NormalityEvaluationRunConfig,
    *,
    provider: NormalityJudgeProvider | None = None,
) -> NormalityEvaluationRunResult:
    if not config.enabled or not config.judge_enabled:
        return _disabled_result(config)

    load_result, judge_input = build_normality_judge_input_from_file(config)
    if load_result.status != "ok" or judge_input is None:
        return NormalityEvaluationRunResult(
            status=load_result.status,
            input_path_relative=load_result.input_path_relative,
            output_dir_relative=_output_dir_relative(config),
            warnings=load_result.warnings,
        )

    judge_config = _judge_config(config)
    judge_result = run_normality_judge(judge_input, judge_config, provider=provider)
    status: NormalityEvaluationRunStatus = "ok"
    if judge_result.status == "disabled":
        status = "judge_disabled"
    elif judge_result.status == "invalid_input":
        status = "invalid_input"

    result = _result_from_judge(
        status=status,
        load_result=load_result,
        output_dir_relative=_output_dir_relative(config),
        judge_input=judge_input,
        judge_config=judge_config,
        judge_result=judge_result,
        warnings=load_result.warnings,
    )
    if config.output_dir and config.write_summary:
        result.summary_path_relative = _summary_path_relative(config)
        try:
            write_normality_evaluation_summary(result, config.resolve_project_path(config.output_dir))
        except OSError:
            result.status = "write_failed"
            result.warnings = sorted(set([*result.warnings, "summary_write_failed"]))
    return result


def run_batch_normality_evaluation(
    config: NormalityEvaluationRunConfig,
    input_paths: list[str | Path],
    *,
    provider: NormalityJudgeProvider | None = None,
) -> NormalityBatchEvaluationResult:
    entries: list[NormalityBatchEvaluationEntry] = []
    if not input_paths:
        result = NormalityBatchEvaluationResult(
            status="invalid_input",
            input_count=0,
            evaluated_count=0,
            failed_count=0,
            judge_mode=config.judge_mode,
            judge_provider=config.judge_provider,
            output_dir_relative=_output_dir_relative(config),
            aggregation=_batch_aggregation(entries),
            warnings=["input_paths_missing"],
        )
        return _write_batch_result_if_requested(result, config)

    for input_path in input_paths:
        item_config = config.model_copy(
            update={
                "input_path": str(input_path),
                "write_summary": False,
            }
        )
        item_result = run_normality_evaluation_from_file(item_config, provider=provider)
        entries.append(_batch_entry_from_result(input_path, item_result, config))

    evaluated_count = sum(1 for entry in entries if entry.status in {"ok", "judge_disabled"})
    failed_count = len(entries) - evaluated_count
    status = _batch_status(entries, evaluated_count)
    result = NormalityBatchEvaluationResult(
        status=status,
        input_count=len(entries),
        evaluated_count=evaluated_count,
        failed_count=failed_count,
        judge_mode=config.judge_mode,
        judge_provider=_batch_judge_provider(entries, config.judge_provider),
        output_dir_relative=_output_dir_relative(config),
        aggregation=_batch_aggregation(entries),
        entries=entries,
        warnings=_batch_warnings(entries),
    )
    return _write_batch_result_if_requested(result, config)


def write_batch_normality_evaluation_summary(
    result: NormalityBatchEvaluationResult,
    output_dir: str | Path,
) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / NORMALITY_BATCH_SUMMARY_FILENAME
    summary_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary_path


def build_normality_judge_input_from_file(
    config: NormalityEvaluationRunConfig,
) -> tuple[NormalityEventsLoadResult, NormalityJudgeInput | None]:
    load_result = load_normality_events_from_file(
        config.input_path,
        project_root=config.project_root,
        max_input_bytes=config.max_input_bytes,
    )
    if load_result.status != "ok":
        return load_result, None
    return (
        load_result,
        _judge_input_from_records(
            records=load_result.records,
            metadata=load_result.payload_metadata,
            config=config,
        ),
    )


def write_normality_judge_prompt_preview(
    judge_input: NormalityJudgeInput,
    output_dir: str | Path,
    *,
    config: NormalityJudgeConfig | NormalityEvaluationRunConfig | None = None,
) -> Path:
    judge_config = (
        _judge_config(config)
        if isinstance(config, NormalityEvaluationRunConfig)
        else config or NormalityJudgeConfig(enabled=True, mode="llm", judge_provider="llm")
    )
    prompt = build_normality_judge_prompt(judge_input, judge_config)
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / NORMALITY_JUDGE_PROMPT_PREVIEW_FILENAME
    path.write_text(
        "\n".join(
            [
                "OFFLINE_NORMALITY_JUDGE_PROMPT_PREVIEW",
                "No model was called.",
                "Expected response: strict JSON only.",
                "",
                prompt,
            ]
        )
        + "\n",
        encoding="utf-8",
    )
    return path


def write_normality_judge_prompt_preview_from_file(
    config: NormalityEvaluationRunConfig,
) -> tuple[Path | None, list[str]]:
    if not config.output_dir:
        return None, ["output_dir_missing"]
    load_result, judge_input = build_normality_judge_input_from_file(config)
    if load_result.status != "ok" or judge_input is None:
        return None, load_result.warnings
    try:
        path = write_normality_judge_prompt_preview(
            judge_input,
            config.resolve_project_path(config.output_dir),
            config=config,
        )
    except OSError:
        return None, ["prompt_preview_write_failed"]
    return path, []


def run_normality_evaluation_from_saved_llm_response(
    config: NormalityEvaluationRunConfig,
    raw_response_path: str | Path,
) -> NormalityEvaluationRunResult:
    load_result, judge_input = build_normality_judge_input_from_file(config)
    if load_result.status != "ok" or judge_input is None:
        return NormalityEvaluationRunResult(
            status=load_result.status,
            input_path_relative=load_result.input_path_relative,
            output_dir_relative=_output_dir_relative(config),
            warnings=load_result.warnings,
        )

    raw_path = config.resolve_project_path(raw_response_path)
    raw_relative = _safe_relative(raw_path, config.project_root)
    raw_text, raw_warnings = _read_raw_response_text(raw_path, config.max_input_bytes)
    if raw_text is None:
        return NormalityEvaluationRunResult(
            status="invalid_input",
            scenario_id=judge_input.scenario_id,
            input_path_relative=load_result.input_path_relative,
            output_dir_relative=_output_dir_relative(config),
            event_count=len(judge_input.events),
            judge_mode="llm_saved_response",
            judge_provider="llm",
            model_called=False,
            raw_response_path_relative=raw_relative,
            warnings=raw_warnings,
        )

    judge_config = NormalityJudgeConfig(
        enabled=True,
        mode="llm",
        judge_provider="llm",
        max_events=config.max_events,
        max_text_chars=config.max_text_chars,
        include_raw_outputs=config.include_raw_outputs,
        redact_paths=config.redact_paths,
    )
    judge_result = parse_llm_normality_judge_output(raw_text, judge_config)
    result = _result_from_judge(
        status="ok" if judge_result.status == "ok" else "invalid_input",
        load_result=load_result,
        output_dir_relative=_output_dir_relative(config),
        judge_input=judge_input,
        judge_config=judge_config,
        judge_result=judge_result,
        warnings=raw_warnings,
    )
    result.judge_mode = "llm_saved_response"
    result.judge_provider = "llm"
    result.model_called = False
    result.raw_response_path_relative = raw_relative
    if config.output_dir and config.write_summary:
        result.summary_path_relative = _summary_path_relative(config)
        try:
            write_normality_evaluation_summary(result, config.resolve_project_path(config.output_dir))
        except OSError:
            result.status = "write_failed"
            result.warnings = sorted(set([*result.warnings, "summary_write_failed"]))
    return result


def run_normality_evaluation_for_group_history(
    *,
    group_history: list[Any],
    scenario_id: str,
    task_summary: str,
    output_dir: str | Path | None = None,
    project_root: str | Path = Path("."),
    agent_roles: dict[str, str] | None = None,
    constraints: list[str] | None = None,
    expected_behavior: str | None = None,
    environment_summary: str | None = None,
    trial_id: str | None = None,
    config: NormalityEvaluationRunConfig | None = None,
    provider: NormalityJudgeProvider | None = None,
) -> NormalityEvaluationRunResult:
    runtime_config = _group_history_config(
        config=config,
        scenario_id=scenario_id,
        task_summary=task_summary,
        output_dir=output_dir,
        project_root=project_root,
    )
    if not runtime_config.enabled or not runtime_config.judge_enabled:
        return _disabled_result(runtime_config)

    records = [_record_dict(item) for item in group_history]
    metadata = {
        "scenario_id": scenario_id,
        "trial_id": trial_id,
        "task_summary": task_summary,
        "agent_roles": agent_roles or _agent_roles(records, {}),
        "constraints": constraints or [],
        "expected_behavior": expected_behavior,
        "environment_summary": environment_summary,
    }
    judge_input = _judge_input_from_records(
        records=records,
        metadata=metadata,
        config=runtime_config,
    )
    judge_config = _judge_config(runtime_config)
    judge_result = run_normality_judge(judge_input, judge_config, provider=provider)
    status: NormalityEvaluationRunStatus = "ok"
    if judge_result.status == "disabled":
        status = "judge_disabled"
    elif judge_result.status == "invalid_input":
        status = "invalid_input"

    load_result = NormalityEventsLoadResult(status="ok", records=records)
    result = _result_from_judge(
        status=status,
        load_result=load_result,
        output_dir_relative=_output_dir_relative(runtime_config),
        judge_input=judge_input,
        judge_config=judge_config,
        judge_result=judge_result,
        warnings=[],
    )
    if runtime_config.output_dir and runtime_config.write_summary:
        result.summary_path_relative = _summary_path_relative(runtime_config)
        try:
            write_normality_evaluation_summary(
                result,
                runtime_config.resolve_project_path(runtime_config.output_dir),
            )
        except OSError:
            result.status = "write_failed"
            result.warnings = sorted(set([*result.warnings, "summary_write_failed"]))
    return result


def write_normality_evaluation_for_pipeline_result(
    pipeline_result: Any,
    *,
    output_dir: str | Path | None = None,
    project_root: str | Path = Path("."),
    config: NormalityEvaluationRunConfig | None = None,
    task_summary: str | None = None,
    agent_roles: dict[str, str] | None = None,
    provider: NormalityJudgeProvider | None = None,
) -> NormalityEvaluationRunResult:
    payload = _record_dict(pipeline_result)
    scenario_id = _as_non_empty_str(payload.get("scenario_id")) or "offline_pipeline_result"
    plan = _dict_value(payload.get("plan"))
    history = payload.get("group_history") or []
    if not isinstance(history, list):
        history = []
    return run_normality_evaluation_for_group_history(
        group_history=history,
        scenario_id=scenario_id,
        task_summary=(
            task_summary
            or _as_non_empty_str(plan.get("expected_group_outcome"))
            or "Evaluate offline pipeline group history artifacts."
        ),
        output_dir=output_dir,
        project_root=project_root,
        agent_roles=agent_roles or _agent_roles_from_pipeline_payload(payload),
        expected_behavior=_as_non_empty_str(plan.get("expected_group_outcome")),
        environment_summary="Offline fake/local pipeline result artifacts.",
        trial_id=_as_non_empty_str(payload.get("run_id")),
        config=config,
        provider=provider,
    )


def write_normality_evaluation_summary(
    result: NormalityEvaluationRunResult,
    output_dir: str | Path,
) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    summary_path = out_dir / NORMALITY_EVALUATION_SUMMARY_FILENAME
    summary_path.write_text(
        json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return summary_path


def _disabled_result(config: NormalityEvaluationRunConfig) -> NormalityEvaluationRunResult:
    judge_config = _judge_config(config).model_copy(update={"enabled": False})
    judge_input = NormalityJudgeInput(
        scenario_id=config.scenario_id or "offline_normality_evaluation",
        task_summary=config.task_summary or "Offline normality evaluation was disabled.",
        events=[
            NormalityJudgeEvent(
                agent_id="offline_runner",
                role="normality_evaluation_runner",
                action="normality_evaluation_disabled",
                status="disabled",
            )
        ],
    )
    judge_result = run_normality_judge(judge_input, judge_config)
    result = NormalityEvaluationRunResult(
        status="judge_disabled",
        scenario_id=judge_input.scenario_id,
        input_path_relative=None,
        output_dir_relative=_output_dir_relative(config),
        event_count=0,
        label=judge_result.label,
        overall_score=judge_result.overall_score,
        dimension_scores={
            key: value.model_dump(mode="json")
            for key, value in judge_result.dimension_scores.items()
        },
        findings=judge_result.findings,
        redactions_applied=judge_result.redactions_applied,
        judge_mode=judge_result.judge_mode,
        judge_provider=judge_result.provider_name,
        judge_result=judge_result,
        aggregation=aggregate_normality_results([judge_result]),
        warnings=["normality_judge_disabled"],
    )
    if config.output_dir and config.write_summary:
        result.summary_path_relative = _summary_path_relative(config)
        try:
            write_normality_evaluation_summary(result, config.resolve_project_path(config.output_dir))
        except OSError:
            result.status = "write_failed"
            result.warnings = sorted(set([*result.warnings, "summary_write_failed"]))
    return result


def _load_jsonl_events(
    text: str,
    input_path_relative: str | None,
) -> NormalityEventsLoadResult:
    records: list[dict[str, Any]] = []
    warnings: list[str] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            return NormalityEventsLoadResult(
                status="invalid_input",
                input_path_relative=input_path_relative,
                warnings=[f"jsonl_decode_error_line_{line_number}"],
            )
        if not isinstance(row, dict):
            return NormalityEventsLoadResult(
                status="invalid_input",
                input_path_relative=input_path_relative,
                warnings=[f"jsonl_row_not_object_line_{line_number}"],
            )
        records.append(row)
    if not records:
        warnings.append("no_records_found")
    return NormalityEventsLoadResult(
        status="ok",
        records=records,
        input_path_relative=input_path_relative,
        warnings=warnings,
    )


def _load_json_events(
    text: str,
    input_path_relative: str | None,
) -> NormalityEventsLoadResult:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        return NormalityEventsLoadResult(
            status="invalid_input",
            input_path_relative=input_path_relative,
            warnings=["json_decode_error"],
        )

    if isinstance(payload, list):
        records, warnings = _coerce_record_list(payload)
        return NormalityEventsLoadResult(
            status="invalid_input" if records is None else "ok",
            records=records or [],
            input_path_relative=input_path_relative,
            warnings=warnings,
        )

    if isinstance(payload, dict):
        records_key = _first_record_key(payload)
        if records_key:
            records, warnings = _coerce_record_list(payload[records_key])
            metadata = _safe_payload_metadata(payload)
            return NormalityEventsLoadResult(
                status="invalid_input" if records is None else "ok",
                records=records or [],
                payload_metadata=metadata,
                input_path_relative=input_path_relative,
                warnings=warnings,
            )
        if _looks_like_event_record(payload):
            return NormalityEventsLoadResult(
                status="ok",
                records=[payload],
                payload_metadata=_safe_payload_metadata(payload),
                input_path_relative=input_path_relative,
            )
    return NormalityEventsLoadResult(
        status="invalid_input",
        input_path_relative=input_path_relative,
        warnings=["json_payload_has_no_event_records"],
    )


def _coerce_record_list(payload: Any) -> tuple[list[dict[str, Any]] | None, list[str]]:
    if not isinstance(payload, list):
        return None, ["event_records_not_list"]
    records: list[dict[str, Any]] = []
    for index, row in enumerate(payload):
        if not isinstance(row, dict):
            return None, [f"event_record_not_object_index_{index}"]
        records.append(row)
    warnings: list[str] = []
    if not records:
        warnings.append("no_records_found")
    return records, warnings


def _judge_input_from_records(
    *,
    records: list[dict[str, Any]],
    metadata: dict[str, Any],
    config: NormalityEvaluationRunConfig,
) -> NormalityJudgeInput:
    agent_roles = _agent_roles(records, metadata)
    return NormalityJudgeInput(
        scenario_id=config.scenario_id
        or _as_non_empty_str(metadata.get("scenario_id"))
        or "offline_normality_evaluation",
        trial_id=_as_non_empty_str(metadata.get("trial_id")),
        task_summary=config.task_summary
        or _as_non_empty_str(metadata.get("task_summary"))
        or _as_non_empty_str(metadata.get("expected_behavior"))
        or "Evaluate stored local agent activity artifacts.",
        agent_roles=agent_roles,
        events=[_event_from_record(record, agent_roles) for record in records],
        constraints=_string_list(metadata.get("constraints")),
        expected_behavior=_as_non_empty_str(metadata.get("expected_behavior")),
        environment_summary=_as_non_empty_str(metadata.get("environment_summary")),
    )


def _event_from_record(
    record: dict[str, Any],
    agent_roles: dict[str, str],
) -> NormalityJudgeEvent:
    metadata = _dict_value(record.get("metadata"))
    next_action = _dict_value(record.get("next_action"))
    parameters = _first_dict(record.get("parameters"), next_action.get("parameters"), next_action.get("params"))
    agent_id = _as_non_empty_str(record.get("agent_id")) or "unknown_agent"
    role = (
        _as_non_empty_str(record.get("role"))
        or _as_non_empty_str(record.get("agent_role"))
        or agent_roles.get(agent_id)
        or "unknown"
    )
    status = (
        _as_non_empty_str(record.get("status"))
        or _status_from_metadata(metadata)
        or "unknown"
    )
    return NormalityJudgeEvent(
        agent_id=agent_id,
        role=role,
        action=_action_from_record(record, next_action),
        status=status,
        timestamp=_as_non_empty_str(record.get("timestamp")),
        error_code=_error_code(record, metadata),
        params_summary=_params_summary(record, parameters),
        result_summary=_result_summary(record),
        artifact_paths=_artifact_paths(record, metadata, parameters),
        policy_decision=_policy_decision(record, metadata),
        notes=_notes(record, metadata),
    )


def _result_from_judge(
    *,
    status: NormalityEvaluationRunStatus,
    load_result: NormalityEventsLoadResult,
    output_dir_relative: str | None,
    judge_input: NormalityJudgeInput,
    judge_config: NormalityJudgeConfig,
    judge_result: NormalityJudgeResult,
    warnings: list[str],
) -> NormalityEvaluationRunResult:
    return NormalityEvaluationRunResult(
        status=status,
        scenario_id=judge_input.scenario_id,
        input_path_relative=load_result.input_path_relative,
        output_dir_relative=output_dir_relative,
        event_count=len(judge_input.events),
        label=judge_result.label,
        overall_score=judge_result.overall_score,
        dimension_scores={
            key: value.model_dump(mode="json")
            for key, value in judge_result.dimension_scores.items()
        },
        findings=judge_result.findings,
        redactions_applied=judge_result.redactions_applied,
        judge_mode=judge_result.judge_mode,
        judge_provider=judge_result.provider_name,
        event_preview=_event_preview(judge_input, judge_config),
        judge_result=judge_result,
        aggregation=aggregate_normality_results([judge_result]),
        warnings=sorted(set(warnings)),
    )


def _event_preview(
    judge_input: NormalityJudgeInput,
    config: NormalityJudgeConfig,
) -> list[dict[str, Any]]:
    preview: list[dict[str, Any]] = []
    for event in judge_input.events[: config.max_events]:
        params_summary, _ = sanitize_judge_text(event.params_summary, config)
        result_summary, _ = sanitize_judge_text(event.result_summary, config)
        notes = [sanitize_judge_text(note, config)[0] for note in event.notes]
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
                "notes": notes,
            }
        )
    return preview


def _judge_config(config: NormalityEvaluationRunConfig) -> NormalityJudgeConfig:
    return NormalityJudgeConfig(
        enabled=config.judge_enabled,
        mode=config.judge_mode,
        judge_provider=config.judge_provider,
        max_events=config.max_events,
        max_text_chars=config.max_text_chars,
        include_raw_outputs=config.include_raw_outputs,
        redact_paths=config.redact_paths,
    )


def _group_history_config(
    *,
    config: NormalityEvaluationRunConfig | None,
    scenario_id: str,
    task_summary: str,
    output_dir: str | Path | None,
    project_root: str | Path,
) -> NormalityEvaluationRunConfig:
    updates = {
        "scenario_id": scenario_id,
        "task_summary": task_summary,
    }
    if output_dir is not None:
        updates["output_dir"] = str(output_dir)
    if project_root != Path(".") or config is None:
        updates["project_root"] = Path(project_root)
    if config is None:
        return NormalityEvaluationRunConfig.model_validate(updates)
    payload = config.model_dump()
    payload.update(updates)
    return NormalityEvaluationRunConfig.model_validate(payload)


def _first_record_key(payload: dict[str, Any]) -> str | None:
    for key in ("group_history", "events", "records", "history"):
        if key in payload:
            return key
    return None


def _safe_payload_metadata(payload: dict[str, Any]) -> dict[str, Any]:
    allowed_keys = {
        "scenario_id",
        "trial_id",
        "task_summary",
        "agent_roles",
        "constraints",
        "expected_behavior",
        "environment_summary",
    }
    return {key: payload[key] for key in allowed_keys if key in payload}


def _looks_like_event_record(payload: dict[str, Any]) -> bool:
    return bool({"agent_id", "action", "next_action", "status"} & set(payload))


def _agent_roles(records: list[dict[str, Any]], metadata: dict[str, Any]) -> dict[str, str]:
    raw_roles = metadata.get("agent_roles")
    roles: dict[str, str] = {}
    if isinstance(raw_roles, dict):
        roles.update({str(key): str(value) for key, value in raw_roles.items()})
    for record in records:
        agent_id = _as_non_empty_str(record.get("agent_id")) or "unknown_agent"
        role = _as_non_empty_str(record.get("role")) or _as_non_empty_str(record.get("agent_role"))
        roles.setdefault(agent_id, role or "unknown")
    return roles


def _agent_roles_from_pipeline_payload(payload: dict[str, Any]) -> dict[str, str]:
    roles: dict[str, str] = {}
    per_agent_results = payload.get("per_agent_results")
    if isinstance(per_agent_results, list):
        for item in per_agent_results:
            row = _record_dict(item)
            agent_id = _as_non_empty_str(row.get("agent_id"))
            if not agent_id:
                continue
            role_hint = " ".join(
                str(part)
                for part in [
                    row.get("role_template_path"),
                    row.get("activity_profile_path"),
                    row.get("assigned_goal"),
                    agent_id,
                ]
                if part
            ).lower()
            if any(token in role_hint for token in ("office", "document", "spreadsheet", "presentation")):
                roles[agent_id] = "office document worker"
            elif "developer" in role_hint:
                roles[agent_id] = "developer"
            elif role_hint.strip():
                roles[agent_id] = role_hint
            else:
                roles[agent_id] = "unknown"
    return roles


def _action_from_record(record: dict[str, Any], next_action: dict[str, Any]) -> str:
    return (
        _as_non_empty_str(record.get("action"))
        or _as_non_empty_str(record.get("action_name"))
        or _as_non_empty_str(next_action.get("action"))
        or _as_non_empty_str(next_action.get("name"))
        or "unknown_action"
    )


def _status_from_metadata(metadata: dict[str, Any]) -> str | None:
    if metadata.get("execution_success") is True:
        return "success"
    if metadata.get("execution_success") is False:
        return "failure"
    if metadata.get("validation_accepted") is False:
        return "rejected"
    return None


def _error_code(record: dict[str, Any], metadata: dict[str, Any]) -> str | None:
    for source in (record, metadata):
        for key in ("error_code", "error_type", "error"):
            value = _as_non_empty_str(source.get(key))
            if value:
                return value
    if metadata.get("validation_accepted") is False:
        return "validation_failed"
    if metadata.get("execution_success") is False:
        return "execution_failed"
    return None


def _params_summary(record: dict[str, Any], parameters: dict[str, Any]) -> str | None:
    explicit = _as_non_empty_str(record.get("params_summary"))
    if explicit:
        return explicit
    if parameters:
        return json.dumps(parameters, ensure_ascii=False, sort_keys=True)
    return None


def _result_summary(record: dict[str, Any]) -> str | None:
    for key in ("result_summary", "summary", "message"):
        value = _as_non_empty_str(record.get(key))
        if value:
            return value
    result = record.get("result")
    if isinstance(result, str) and result.strip():
        return result
    if isinstance(result, dict):
        for key in ("summary", "message"):
            value = _as_non_empty_str(result.get(key))
            if value:
                return value
    return None


def _artifact_paths(
    record: dict[str, Any],
    metadata: dict[str, Any],
    parameters: dict[str, Any],
) -> list[str]:
    paths: list[str] = []
    for source in (record, metadata, parameters):
        paths.extend(_string_list(source.get("artifact_paths")))
        for key in ("artifact_path", "path", "file_path", "output_path", "path_relative"):
            value = _as_non_empty_str(source.get(key))
            if value:
                paths.append(value)
    return list(dict.fromkeys(paths))


def _policy_decision(record: dict[str, Any], metadata: dict[str, Any]) -> str | None:
    explicit = _as_non_empty_str(record.get("policy_decision"))
    if explicit:
        return explicit
    virtual_policy = _dict_value(metadata.get("virtual_network_policy"))
    for key in ("code", "decision", "allowed"):
        value = virtual_policy.get(key)
        if value is not None:
            return str(value)
    return None


def _notes(record: dict[str, Any], metadata: dict[str, Any]) -> list[str]:
    notes = _string_list(record.get("notes"))
    for key in ("execution_attempted", "execution_success", "validation_accepted"):
        if key in metadata:
            notes.append(f"{key}={metadata[key]}")
    return notes


def _output_dir_relative(config: NormalityEvaluationRunConfig) -> str | None:
    if not config.output_dir:
        return None
    return _safe_relative(config.resolve_project_path(config.output_dir), config.project_root)


def _summary_path_relative(config: NormalityEvaluationRunConfig) -> str | None:
    if not config.output_dir:
        return None
    return _safe_relative(
        config.resolve_project_path(config.output_dir) / NORMALITY_EVALUATION_SUMMARY_FILENAME,
        config.project_root,
    )


def _batch_summary_path_relative(config: NormalityEvaluationRunConfig) -> str | None:
    if not config.output_dir:
        return None
    return _safe_relative(
        config.resolve_project_path(config.output_dir) / NORMALITY_BATCH_SUMMARY_FILENAME,
        config.project_root,
    )


def _batch_entry_from_result(
    input_path: str | Path,
    result: NormalityEvaluationRunResult,
    config: NormalityEvaluationRunConfig,
) -> NormalityBatchEvaluationEntry:
    return NormalityBatchEvaluationEntry(
        input_path_display=_input_path_display(input_path, config),
        input_path_relative=result.input_path_relative,
        status=result.status,
        label=result.label,
        overall_score=result.overall_score,
        event_count=result.event_count,
        summary_path_relative=result.summary_path_relative,
        judge_mode=result.judge_mode,
        judge_provider=result.judge_provider,
        warnings=result.warnings,
        findings=result.findings,
        redactions_applied=result.redactions_applied,
        event_preview=result.event_preview,
    )


def _batch_status(entries: list[NormalityBatchEvaluationEntry], evaluated_count: int) -> str:
    if not entries or evaluated_count == 0:
        return "invalid_input"
    if all(entry.status == "judge_disabled" for entry in entries):
        return "judge_disabled"
    return "ok"


def _batch_judge_provider(entries: list[NormalityBatchEvaluationEntry], fallback: str | None) -> str | None:
    for entry in entries:
        if entry.judge_provider:
            return entry.judge_provider
    return fallback


def _batch_warnings(entries: list[NormalityBatchEvaluationEntry]) -> list[str]:
    warnings: set[str] = set()
    for entry in entries:
        warnings.update(entry.warnings)
    return sorted(warnings)


def _batch_aggregation(entries: list[NormalityBatchEvaluationEntry]) -> dict[str, Any]:
    successful = [
        NormalityJudgeResult(
            status="ok",
            label=entry.label,
            overall_score=entry.overall_score,
            judge_mode="deterministic",
            provider_name=None,
            findings=entry.findings,
        )
        for entry in entries
        if entry.status == "ok" and entry.label is not None and entry.overall_score is not None
    ]
    aggregation = aggregate_normality_results(successful)
    status_counts = Counter(entry.status for entry in entries)
    finding_counts: Counter[str] = Counter()
    for entry in entries:
        finding_counts.update(entry.findings)
    aggregation["status_counts"] = dict(status_counts)
    aggregation["finding_counts"] = dict(finding_counts)
    return aggregation


def _input_path_display(input_path: str | Path, config: NormalityEvaluationRunConfig) -> str | None:
    path = config.resolve_project_path(input_path)
    relative = _safe_relative(path, config.project_root)
    if relative is not None:
        return relative
    text = str(input_path)
    if config.redact_paths and _is_absolute_path(text):
        return "<absolute_path>"
    safe, _ = sanitize_judge_text(text, _judge_config(config))
    return safe or None


def _write_batch_result_if_requested(
    result: NormalityBatchEvaluationResult,
    config: NormalityEvaluationRunConfig,
) -> NormalityBatchEvaluationResult:
    if not config.output_dir or not config.write_summary:
        return result
    result.batch_summary_path_relative = _batch_summary_path_relative(config)
    try:
        write_batch_normality_evaluation_summary(
            result,
            config.resolve_project_path(config.output_dir),
        )
    except OSError:
        result.status = "write_failed"
        result.warnings = sorted(set([*result.warnings, "batch_summary_write_failed"]))
    return result


def _read_raw_response_text(path: Path, max_input_bytes: int) -> tuple[str | None, list[str]]:
    if not path.exists() or not path.is_file():
        return None, ["raw_response_file_missing"]
    try:
        if path.stat().st_size > max_input_bytes:
            return None, ["raw_response_file_too_large"]
        return path.read_text(encoding="utf-8"), []
    except OSError:
        return None, ["raw_response_file_unreadable"]
    except UnicodeDecodeError:
        return None, ["raw_response_file_not_utf8_text"]


def _safe_artifact_path(path: str) -> str:
    return "<absolute_path>" if _is_absolute_path(path) else path


def _is_absolute_path(path: str) -> bool:
    return bool(
        re.match(r"^[A-Za-z]:[\\/]", path)
        or path.startswith("/")
        or path.startswith("\\\\")
    )


def _safe_relative(path: Path, root: Path) -> str | None:
    try:
        return path.resolve(strict=False).relative_to(root.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return None


def _resolve_path(path: str | Path, root: Path) -> Path:
    candidate = Path(path)
    if candidate.is_absolute():
        return candidate
    return root / candidate


def _record_dict(value: Any) -> dict[str, Any]:
    if hasattr(value, "model_dump"):
        data = value.model_dump(mode="json")
        return data if isinstance(data, dict) else {}
    if isinstance(value, dict):
        return value
    try:
        return dict(value)
    except (TypeError, ValueError):
        return {}


def _dict_value(value: Any) -> dict[str, Any]:
    return value if isinstance(value, dict) else {}


def _first_dict(*values: Any) -> dict[str, Any]:
    for value in values:
        if isinstance(value, dict):
            return value
    return {}


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return []


def _as_non_empty_str(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None
