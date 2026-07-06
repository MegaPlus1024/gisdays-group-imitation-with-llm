from __future__ import annotations

import json
import re
from collections import Counter
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Mapping

from .normality_evaluation_runner import (
    NORMALITY_BATCH_SUMMARY_FILENAME,
    NormalityBatchEvaluationEntry,
    NormalityBatchEvaluationResult,
    write_batch_normality_evaluation_summary,
)
from .normality_judge import (
    NormalityJudgeConfig,
    NormalityJudgeResult,
    aggregate_normality_results,
    build_normality_judge_prompt,
    parse_llm_normality_judge_output,
    sanitize_judge_text,
)
from .prepared_normality_input_processor import (
    PreparedNormalityInputLoadError,
    convert_prepared_input_to_normality_judge_input,
    load_prepared_normality_inputs,
)


PREPARED_NORMALITY_JUDGE_PROMPT_PACK_SCHEMA_VERSION = "prepared_normality_judge_prompt_pack_v1"
NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME = "normality_judge_prompt_pack.jsonl"
NORMALITY_JUDGE_PROMPT_PACK_SUMMARY_FILENAME = "normality_judge_prompt_pack_summary.json"
NORMALITY_JUDGE_BATCH_RAW_RESPONSES_JSONL_FILENAME = "normality_judge_raw_responses.jsonl"
PREPARED_NORMALITY_JUDGE_PROMPT_PACK_NOTES = [
    "Offline prompt pack only; no model execution performed.",
    "Not a production recommendation.",
]

_TRACE_KEYS = ("events", "group_history", "event_history", "activity_trace", "history")
_MAX_INPUT_BYTES = 1_000_000
_MAX_TEXT_CHARS = 500


class PreparedNormalityJudgeExchangeError(ValueError):
    """Controlled exchange error safe to expose through CLI JSON."""


def load_exchange_prepared_normality_inputs(
    paths: list[str | Path],
    *,
    max_input_bytes: int = _MAX_INPUT_BYTES,
) -> list[dict[str, Any]]:
    if not paths:
        raise PreparedNormalityJudgeExchangeError("prepared_inputs_required")
    inputs: list[dict[str, Any]] = []
    try:
        for path in paths:
            inputs.extend(load_prepared_normality_inputs(path, max_input_bytes=max_input_bytes))
    except PreparedNormalityInputLoadError as exc:
        raise PreparedNormalityJudgeExchangeError(str(exc)) from exc
    return inputs


def build_prepared_normality_judge_prompt_pack(
    prepared_inputs: list[Mapping[str, Any]],
    *,
    pack_id: str | None = None,
    prompt_config: NormalityJudgeConfig | None = None,
    tags: list[str] | None = None,
) -> dict[str, Any]:
    cfg = prompt_config or NormalityJudgeConfig(
        enabled=True,
        mode="llm",
        judge_provider="llm",
        max_text_chars=_MAX_TEXT_CHARS,
    )
    prompts: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, prepared in enumerate(prepared_inputs, start=1):
        prompt_item = _prompt_item_from_prepared_input(
            dict(prepared),
            index=index,
            pack_id=pack_id,
            config=cfg,
        )
        prompts.append(prompt_item)
        warnings.extend(prompt_item.get("warnings", []))

    prompt_count = sum(1 for item in prompts if item.get("status") == "ok")
    return {
        "schema_version": PREPARED_NORMALITY_JUDGE_PROMPT_PACK_SCHEMA_VERSION,
        "pack_id": _safe_optional_text(pack_id) or "prepared_normality_judge_prompt_pack",
        "input_count": len(prepared_inputs),
        "prompt_count": prompt_count,
        "skipped_count": len(prepared_inputs) - prompt_count,
        "prompts": prompts,
        "tags": _safe_string_list(tags or []),
        "warnings": sorted(set(_safe_text(warning) for warning in warnings)),
        "notes": list(PREPARED_NORMALITY_JUDGE_PROMPT_PACK_NOTES),
        "no_runtime_execution": True,
    }


def write_prepared_normality_judge_prompt_pack(
    prompt_pack: Mapping[str, Any],
    output_dir: str | Path,
) -> tuple[Path, Path]:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    prompt_pack_path = out_dir / NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME
    summary_path = out_dir / NORMALITY_JUDGE_PROMPT_PACK_SUMMARY_FILENAME
    prompts = [item for item in prompt_pack.get("prompts", []) if isinstance(item, Mapping)]
    prompt_pack_path.write_text(
        "".join(json.dumps(_safe_value(dict(item)), ensure_ascii=False, sort_keys=True) + "\n" for item in prompts),
        encoding="utf-8",
    )
    summary_path.write_text(
        json.dumps(_prompt_pack_summary(prompt_pack), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return prompt_pack_path, summary_path


def load_prepared_normality_judge_prompt_pack(path: str | Path) -> dict[str, Any]:
    candidate = Path(path)
    try:
        if not candidate.exists() or not candidate.is_file():
            raise PreparedNormalityJudgeExchangeError("prompt_pack_file_missing")
        if candidate.stat().st_size > _MAX_INPUT_BYTES:
            raise PreparedNormalityJudgeExchangeError("prompt_pack_file_too_large")
        text = candidate.read_text(encoding="utf-8")
    except PreparedNormalityJudgeExchangeError:
        raise
    except OSError as exc:
        raise PreparedNormalityJudgeExchangeError("prompt_pack_file_unreadable") from exc
    except UnicodeDecodeError as exc:
        raise PreparedNormalityJudgeExchangeError("prompt_pack_file_not_utf8_text") from exc

    if candidate.suffix.lower() == ".jsonl":
        prompts = _load_jsonl_objects(text, error_prefix="prompt_pack")
        return {
            "schema_version": PREPARED_NORMALITY_JUDGE_PROMPT_PACK_SCHEMA_VERSION,
            "pack_id": "loaded_prompt_pack",
            "input_count": len(prompts),
            "prompt_count": sum(1 for item in prompts if item.get("status") == "ok"),
            "skipped_count": sum(1 for item in prompts if item.get("status") != "ok"),
            "prompts": prompts,
            "warnings": _warnings_from_rows(prompts),
            "notes": list(PREPARED_NORMALITY_JUDGE_PROMPT_PACK_NOTES),
            "no_runtime_execution": True,
        }

    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PreparedNormalityJudgeExchangeError("prompt_pack_json_malformed") from exc
    if isinstance(payload, dict) and isinstance(payload.get("prompts"), list):
        return payload
    raise PreparedNormalityJudgeExchangeError("prompt_pack_payload_invalid")


def load_normality_judge_raw_responses(path: str | Path) -> list[dict[str, Any]]:
    candidate = Path(path)
    try:
        if not candidate.exists() or not candidate.is_file():
            raise PreparedNormalityJudgeExchangeError("raw_responses_file_missing")
        if candidate.stat().st_size > _MAX_INPUT_BYTES:
            raise PreparedNormalityJudgeExchangeError("raw_responses_file_too_large")
        text = candidate.read_text(encoding="utf-8")
    except PreparedNormalityJudgeExchangeError:
        raise
    except OSError as exc:
        raise PreparedNormalityJudgeExchangeError("raw_responses_file_unreadable") from exc
    except UnicodeDecodeError as exc:
        raise PreparedNormalityJudgeExchangeError("raw_responses_file_not_utf8_text") from exc

    rows = _load_jsonl_objects(text, error_prefix="raw_responses") if candidate.suffix.lower() == ".jsonl" else _load_json_response_records(text)
    for index, row in enumerate(rows, start=1):
        if not _safe_optional_text(row.get("raw_response")):
            raise PreparedNormalityJudgeExchangeError(f"raw_response_missing:{index}")
    return rows


def write_normality_judge_raw_responses_jsonl(
    responses: list[Mapping[str, Any]],
    output_dir: str | Path,
) -> Path:
    out_dir = Path(output_dir)
    out_dir.mkdir(parents=True, exist_ok=True)
    path = out_dir / NORMALITY_JUDGE_BATCH_RAW_RESPONSES_JSONL_FILENAME
    path.write_text(
        "".join(json.dumps(_safe_response_record(dict(row)), ensure_ascii=False, sort_keys=True) + "\n" for row in responses),
        encoding="utf-8",
    )
    return path


def build_normality_batch_summary_from_raw_responses(
    prompt_pack: Mapping[str, Any] | list[Mapping[str, Any]],
    raw_responses: list[Mapping[str, Any]],
    *,
    summary_id: str | None = None,
    tags: list[str] | None = None,
    output_dir: str | Path | None = None,
    parser_config: NormalityJudgeConfig | None = None,
) -> NormalityBatchEvaluationResult:
    prompts = _prompt_rows(prompt_pack)
    response_by_prompt_id, response_by_trial_id, unknown_response_warnings = _response_indexes(prompts, raw_responses)
    entries: list[NormalityBatchEvaluationEntry] = []
    judge_results: list[NormalityJudgeResult] = []
    for index, prompt in enumerate(prompts, start=1):
        entry, judge_result = _entry_from_prompt_response(
            prompt,
            response_by_prompt_id=response_by_prompt_id,
            response_by_trial_id=response_by_trial_id,
            parser_config=parser_config,
            index=index,
        )
        entries.append(entry)
        if judge_result is not None:
            judge_results.append(judge_result)

    evaluated_count = sum(1 for entry in entries if entry.status == "ok")
    failed_count = len(entries) - evaluated_count
    warnings = sorted({*_batch_warnings(entries), *unknown_response_warnings})
    result = NormalityBatchEvaluationResult(
        status=_batch_status(entries, evaluated_count),
        manifest_schema_version=PREPARED_NORMALITY_JUDGE_PROMPT_PACK_SCHEMA_VERSION,
        batch_id=_safe_optional_text(summary_id),
        description="Prepared normality judge exchange import. Raw responses were parsed offline.",
        input_count=len(entries),
        evaluated_count=evaluated_count,
        failed_count=failed_count,
        judge_mode="llm_saved_response",
        judge_provider="llm_normality_judge_parser",
        output_dir_relative=Path(output_dir).name if output_dir is not None else None,
        batch_summary_path_relative=NORMALITY_BATCH_SUMMARY_FILENAME if output_dir is not None else None,
        aggregation=_batch_aggregation(entries, judge_results),
        entries=entries,
        warnings=warnings,
    )
    if tags:
        result.entries = [
            entry.model_copy(update={"tags": sorted(set([*entry.tags, *_safe_string_list(tags)]))})
            for entry in result.entries
        ]
    if output_dir is not None:
        try:
            write_batch_normality_evaluation_summary(result, output_dir)
        except OSError:
            result.status = "write_failed"
            result.warnings = sorted({*result.warnings, "batch_summary_write_failed"})
    return result


def _prompt_item_from_prepared_input(
    prepared: dict[str, Any],
    *,
    index: int,
    pack_id: str | None,
    config: NormalityJudgeConfig,
) -> dict[str, Any]:
    prompt_id = _prompt_id(prepared, index=index, pack_id=pack_id)
    warnings = _record_trace_warnings(prepared)
    base = {
        "prompt_id": prompt_id,
        "trial_id": _safe_optional_text(prepared.get("trial_id")),
        "scenario_id": _safe_optional_text(prepared.get("scenario_id")),
        "pair_id": _safe_optional_text(prepared.get("pair_id")),
        "model_pair": _safe_model_pair(prepared.get("model_pair")),
        "task_summary": _safe_optional_text(prepared.get("task_summary")),
        "metadata": _prompt_metadata(prepared),
        "warnings": warnings,
    }
    if warnings:
        return {
            **base,
            "status": "skipped",
            "prompt": None,
        }

    judge_input = convert_prepared_input_to_normality_judge_input(prepared, max_events=config.max_events)
    prompt = build_normality_judge_prompt(judge_input, config)
    return {
        **base,
        "status": "ok",
        "prompt": prompt,
        "metadata": {
            **base["metadata"],
            "redactions_applied": [],
            "no_runtime_execution": True,
        },
    }


def _prompt_pack_summary(prompt_pack: Mapping[str, Any]) -> dict[str, Any]:
    prompts = [item for item in prompt_pack.get("prompts", []) if isinstance(item, Mapping)]
    summary_prompts = [
        {
            "prompt_id": _safe_optional_text(item.get("prompt_id")),
            "trial_id": _safe_optional_text(item.get("trial_id")),
            "scenario_id": _safe_optional_text(item.get("scenario_id")),
            "pair_id": _safe_optional_text(item.get("pair_id")),
            "status": _safe_optional_text(item.get("status")) or "unknown",
            "warning_count": len(_list_value(item.get("warnings"))),
            "prompt_char_count": len(item.get("prompt")) if isinstance(item.get("prompt"), str) else 0,
        }
        for item in prompts
    ]
    return {
        "schema_version": prompt_pack.get("schema_version") or PREPARED_NORMALITY_JUDGE_PROMPT_PACK_SCHEMA_VERSION,
        "pack_id": _safe_optional_text(prompt_pack.get("pack_id")),
        "input_count": _int_or_count(prompt_pack.get("input_count"), len(prompts)),
        "prompt_count": _int_or_count(prompt_pack.get("prompt_count"), sum(1 for item in prompts if item.get("status") == "ok")),
        "skipped_count": _int_or_count(prompt_pack.get("skipped_count"), sum(1 for item in prompts if item.get("status") != "ok")),
        "prompts": summary_prompts,
        "warnings": _safe_string_list(prompt_pack.get("warnings")),
        "notes": _safe_string_list(prompt_pack.get("notes")) or list(PREPARED_NORMALITY_JUDGE_PROMPT_PACK_NOTES),
        "no_runtime_execution": True,
    }


def _entry_from_prompt_response(
    prompt: Mapping[str, Any],
    *,
    response_by_prompt_id: dict[str, dict[str, Any]],
    response_by_trial_id: dict[str, dict[str, Any]],
    parser_config: NormalityJudgeConfig | None,
    index: int,
) -> tuple[NormalityBatchEvaluationEntry, NormalityJudgeResult | None]:
    prompt_warnings = _safe_string_list(prompt.get("warnings"))
    if prompt.get("status") != "ok":
        warnings = sorted({*prompt_warnings, "prompt_skipped"})
        return _invalid_entry_for_prompt(prompt, warnings=warnings, index=index), None

    response = _response_for_prompt(prompt, response_by_prompt_id, response_by_trial_id)
    if response is None:
        warnings = sorted({*prompt_warnings, "judge_response_missing"})
        return _invalid_entry_for_prompt(prompt, warnings=warnings, index=index), None

    config = parser_config or NormalityJudgeConfig(enabled=True, mode="llm", judge_provider="llm")
    judge_result = parse_llm_normality_judge_output(str(response.get("raw_response") or ""), config)
    status = "ok" if judge_result.status == "ok" else "invalid_input"
    entry = NormalityBatchEvaluationEntry(
        input_path_display=None,
        input_path_relative=None,
        trial_id=_safe_optional_text(prompt.get("trial_id")),
        scenario_id=_safe_optional_text(prompt.get("scenario_id")),
        task_summary=_safe_optional_text(prompt.get("task_summary")),
        model_pair=_safe_model_pair(prompt.get("model_pair")),
        tags=[],
        status=status,
        label=judge_result.label,
        overall_score=judge_result.overall_score,
        event_count=_int_or_count(_dict_value(prompt.get("metadata")).get("event_count"), 0),
        summary_path_relative=None,
        judge_mode="llm_saved_response",
        judge_provider=judge_result.provider_name,
        warnings=prompt_warnings,
        findings=judge_result.findings,
        redactions_applied=judge_result.redactions_applied,
        event_preview=[],
    )
    return entry, judge_result


def _invalid_entry_for_prompt(
    prompt: Mapping[str, Any],
    *,
    warnings: list[str],
    index: int,
) -> NormalityBatchEvaluationEntry:
    findings = sorted({warning for warning in warnings if warning})
    return NormalityBatchEvaluationEntry(
        input_path_display=None,
        input_path_relative=None,
        trial_id=_safe_optional_text(prompt.get("trial_id")) or f"prompt_{index:03d}",
        scenario_id=_safe_optional_text(prompt.get("scenario_id")),
        task_summary=_safe_optional_text(prompt.get("task_summary")),
        model_pair=_safe_model_pair(prompt.get("model_pair")),
        tags=[],
        status="invalid_input",
        label="not_evaluated",
        overall_score=0.0,
        event_count=0,
        judge_mode="llm_saved_response",
        judge_provider=None,
        warnings=warnings,
        findings=findings or ["judge_response_invalid"],
        redactions_applied=[],
        event_preview=[],
    )


def _load_json_response_records(text: str) -> list[dict[str, Any]]:
    try:
        payload = json.loads(text)
    except json.JSONDecodeError as exc:
        raise PreparedNormalityJudgeExchangeError("raw_responses_json_malformed") from exc
    if isinstance(payload, list):
        return _coerce_object_rows(payload, "raw_responses")
    if isinstance(payload, dict):
        for key in ("responses", "raw_responses", "records"):
            if key in payload:
                return _coerce_object_rows(payload[key], key)
        if "raw_response" in payload:
            return [payload]
        raise PreparedNormalityJudgeExchangeError("raw_responses_records_missing")
    raise PreparedNormalityJudgeExchangeError("raw_responses_payload_not_supported")


def _load_jsonl_objects(text: str, *, error_prefix: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            row = json.loads(line)
        except json.JSONDecodeError as exc:
            raise PreparedNormalityJudgeExchangeError(f"{error_prefix}_jsonl_decode_error_line_{line_number}") from exc
        if not isinstance(row, dict):
            raise PreparedNormalityJudgeExchangeError(f"{error_prefix}_jsonl_record_not_object_line_{line_number}")
        rows.append(row)
    if not rows:
        raise PreparedNormalityJudgeExchangeError(f"{error_prefix}_records_empty")
    return rows


def _coerce_object_rows(payload: Any, source: str) -> list[dict[str, Any]]:
    if not isinstance(payload, list):
        raise PreparedNormalityJudgeExchangeError(f"{source}_records_not_list")
    rows: list[dict[str, Any]] = []
    for index, item in enumerate(payload, start=1):
        if not isinstance(item, dict):
            raise PreparedNormalityJudgeExchangeError(f"{source}_record_not_object:{index}")
        rows.append(item)
    return rows


def _prompt_rows(prompt_pack: Mapping[str, Any] | list[Mapping[str, Any]]) -> list[dict[str, Any]]:
    if isinstance(prompt_pack, list):
        return [dict(item) for item in prompt_pack if isinstance(item, Mapping)]
    prompts = prompt_pack.get("prompts")
    if isinstance(prompts, list):
        return [dict(item) for item in prompts if isinstance(item, Mapping)]
    raise PreparedNormalityJudgeExchangeError("prompt_pack_prompts_missing")


def _response_indexes(
    prompts: list[dict[str, Any]],
    raw_responses: list[Mapping[str, Any]],
) -> tuple[dict[str, dict[str, Any]], dict[str, dict[str, Any]], list[str]]:
    known_prompt_ids = {_safe_optional_text(prompt.get("prompt_id")) for prompt in prompts}
    known_trial_ids = {_safe_optional_text(prompt.get("trial_id")) for prompt in prompts}
    by_prompt_id: dict[str, dict[str, Any]] = {}
    by_trial_id: dict[str, dict[str, Any]] = {}
    warnings: list[str] = []
    for index, response in enumerate(raw_responses, start=1):
        row = dict(response)
        prompt_id = _safe_optional_text(row.get("prompt_id"))
        trial_id = _safe_optional_text(row.get("trial_id"))
        if prompt_id:
            by_prompt_id[prompt_id] = row
        if trial_id:
            by_trial_id[trial_id] = row
        if (prompt_id and prompt_id not in known_prompt_ids) and (not trial_id or trial_id not in known_trial_ids):
            warnings.append(f"unknown_prompt_response:{prompt_id}")
        elif not prompt_id and not trial_id:
            warnings.append(f"raw_response_identity_missing:{index}")
    return by_prompt_id, by_trial_id, sorted(set(warnings))


def _response_for_prompt(
    prompt: Mapping[str, Any],
    response_by_prompt_id: dict[str, dict[str, Any]],
    response_by_trial_id: dict[str, dict[str, Any]],
) -> dict[str, Any] | None:
    prompt_id = _safe_optional_text(prompt.get("prompt_id"))
    if prompt_id and prompt_id in response_by_prompt_id:
        return response_by_prompt_id[prompt_id]
    trial_id = _safe_optional_text(prompt.get("trial_id"))
    if trial_id and trial_id in response_by_trial_id:
        return response_by_trial_id[trial_id]
    return None


def _record_trace_warnings(record: Mapping[str, Any]) -> list[str]:
    warnings = set(_safe_string_list(record.get("warnings")))
    out: set[str] = set()
    if _safe_optional_text(record.get("adapter_status")) == "invalid_input":
        out.add("adapter_status_invalid_input")
    if "normality_trace_missing" in warnings:
        out.add("normality_trace_missing")
    if not _has_trace(record):
        out.add("normality_trace_missing")
    return sorted(out)


def _has_trace(record: Mapping[str, Any]) -> bool:
    for key in _TRACE_KEYS:
        value = record.get(key)
        if isinstance(value, list) and any(isinstance(item, Mapping) for item in value):
            return True
    return False


def _prompt_id(prepared: Mapping[str, Any], *, index: int, pack_id: str | None) -> str:
    trial_id = _safe_optional_text(prepared.get("trial_id"))
    prefix = _safe_optional_text(pack_id) or "prepared_normality_judge"
    return f"{prefix}__{trial_id}" if trial_id else f"{prefix}__prompt_{index:03d}"


def _prompt_metadata(prepared: Mapping[str, Any]) -> dict[str, Any]:
    metadata = _dict_value(prepared.get("metadata"))
    event_count = 0
    for key in _TRACE_KEYS:
        value = prepared.get(key)
        if isinstance(value, list):
            event_count = len([item for item in value if isinstance(item, Mapping)])
            break
    return _safe_value(
        {
            "source_run_id": metadata.get("source_run_id"),
            "event_count": event_count,
            "no_runtime_execution": True,
        }
    )


def _warnings_from_rows(rows: list[Mapping[str, Any]]) -> list[str]:
    warnings: set[str] = set()
    for row in rows:
        warnings.update(_safe_string_list(row.get("warnings")))
    return sorted(warnings)


def _batch_status(entries: list[NormalityBatchEvaluationEntry], evaluated_count: int) -> str:
    if not entries or evaluated_count == 0:
        return "invalid_input"
    return "ok"


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


def _safe_response_record(row: dict[str, Any]) -> dict[str, Any]:
    return {
        key: _safe_value(value)
        for key, value in row.items()
        if key in {"prompt_id", "trial_id", "raw_response", "metadata", "warnings"}
    }


def _safe_model_pair(value: Any) -> dict[str, str] | None:
    if not isinstance(value, Mapping):
        return None
    out = {
        _safe_text(str(key)): _safe_text(str(item))
        for key, item in value.items()
        if item is not None
    }
    return out or None


def _safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            _safe_text(str(key)): _safe_value(item)
            for key, item in value.items()
            if not _secret_like_key(str(key))
        }
    if isinstance(value, list | tuple):
        return [_safe_value(item) for item in value]
    if isinstance(value, str):
        return _safe_text(value)
    return value


def _safe_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [_safe_text(value)]
    if isinstance(value, list | tuple | set):
        return [_safe_text(str(item)) for item in value if item is not None]
    return [_safe_text(str(value))]


def _safe_optional_text(value: Any) -> str | None:
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


def _list_value(value: Any) -> list[Any]:
    return value if isinstance(value, list) else []


def _dict_value(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, Mapping) else {}


def _int_or_count(value: Any, fallback: int) -> int:
    if isinstance(value, bool):
        return fallback
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _secret_like_key(key: str) -> bool:
    lowered = key.lower()
    return any(token in lowered for token in ("api_key", "apikey", "token", "secret", "password", "credential", "auth"))


def _is_absolute_path(value: str) -> bool:
    return (
        PureWindowsPath(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or bool(re.match(r"^[A-Za-z]:", value))
    )
