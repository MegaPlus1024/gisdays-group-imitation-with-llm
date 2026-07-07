from __future__ import annotations

import json
import os
import re
import urllib.error
import urllib.request
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any, Callable, Mapping, Sequence

from .model_pair_flagship_judge_inputs import (
    FLAGSHIP_JUDGE_VERDICT_SCHEMA_VERSION,
    build_flagship_judge_summary_from_responses,
    load_flagship_judge_raw_responses_jsonl,
    write_flagship_judge_summary,
)


FLAGSHIP_API_JUDGE_CONFIG_SCHEMA_VERSION = "flagship_api_judge_config_v1"
FLAGSHIP_API_JUDGE_RAW_RESPONSE_SCHEMA_VERSION = "flagship_api_judge_raw_response_v1"
FLAGSHIP_API_JUDGE_OPT_IN_CONFIRMATION = "LLM_JUDGE_API_OPT_IN"
DEFAULT_OPENAI_RESPONSES_PATH = "/responses"
EVALUATED_MODEL_IDS = {"first_model", "second_model"}

FlagshipAPITransport = Callable[[str, Mapping[str, str], bytes, float], Mapping[str, Any] | str]


class FlagshipAPIJudgeError(ValueError):
    """Guarded flagship API judge error safe to expose through CLI JSON."""


def load_flagship_api_judge_config(path: str | Path) -> dict[str, Any]:
    payload = _load_json_object(path, label="judge_config")
    config = _normalize_config(payload)
    _validate_config(config)
    return config


def load_flagship_judge_prompt_pack(path: str | Path) -> list[dict[str, Any]]:
    rows = _load_jsonl_objects(path, error_prefix="prompt_pack")
    return [row for row in rows if isinstance(row, dict)]


def load_flagship_judge_schema(path: str | Path) -> dict[str, Any]:
    schema = _load_json_object(path, label="judge_schema")
    if schema.get("properties", {}).get("schema_version", {}).get("const") != FLAGSHIP_JUDGE_VERDICT_SCHEMA_VERSION:
        raise FlagshipAPIJudgeError("judge_schema_version_invalid")
    return schema


def build_openai_responses_payload(
    prompt_record: Mapping[str, Any],
    schema: Mapping[str, Any],
    config: Mapping[str, Any],
) -> dict[str, Any]:
    model = _required_text(config.get("model"), "judge_model_missing")
    prompt = _required_text(prompt_record.get("prompt"), "prompt_record_prompt_missing")
    schema_name = _schema_name(schema)
    payload: dict[str, Any] = {
        "model": model,
        "input": [
            {
                "role": "system",
                "content": [
                    {
                        "type": "input_text",
                        "text": (
                            "You are an external flagship LLM judge and independent measurement instrument. "
                            "You are not one of the evaluated local models. Return only strict JSON."
                        ),
                    }
                ],
            },
            {
                "role": "user",
                "content": [{"type": "input_text", "text": prompt}],
            },
        ],
        "max_output_tokens": _safe_int(config.get("max_output_tokens"), fallback=2000),
        "text": {
            "format": {
                "type": "json_schema",
                "name": schema_name,
                "schema": dict(schema),
                "strict": True,
            }
        },
    }
    if _optional_text(config.get("reasoning_effort")):
        payload["reasoning"] = {"effort": _optional_text(config.get("reasoning_effort"))}
    if config.get("temperature") is not None:
        payload["temperature"] = config.get("temperature")
    return _safe_value(payload)


def extract_openai_response_text(response: Mapping[str, Any]) -> str:
    output_text = response.get("output_text")
    if isinstance(output_text, str) and output_text.strip():
        return output_text
    output = response.get("output")
    if isinstance(output, list):
        for item in output:
            if not isinstance(item, Mapping):
                continue
            content = item.get("content")
            if not isinstance(content, list):
                continue
            for content_item in content:
                if not isinstance(content_item, Mapping):
                    continue
                text = content_item.get("text")
                if isinstance(text, str) and text.strip():
                    return text
                if content_item.get("type") == "output_text":
                    output_text = content_item.get("output_text")
                    if isinstance(output_text, str) and output_text.strip():
                        return output_text
    raise FlagshipAPIJudgeError("judge_response_text_missing")


def run_guarded_flagship_api_judge(
    *,
    judge_config_path: str | Path,
    prompt_pack_path: str | Path,
    schema_path: str | Path,
    output_path: str | Path,
    allow_api_judge: bool = False,
    confirm_api_judge: str | None = None,
    dry_run: bool = False,
    max_records: int | None = None,
    parse_after_run: bool = False,
    parsed_output_path: str | Path | None = None,
    transport: FlagshipAPITransport | None = None,
    environ: Mapping[str, str] | None = None,
) -> dict[str, Any]:
    config = load_flagship_api_judge_config(judge_config_path)
    prompts = _limited_records(load_flagship_judge_prompt_pack(prompt_pack_path), max_records)
    schema = load_flagship_judge_schema(schema_path)
    if not prompts:
        raise FlagshipAPIJudgeError("prompt_pack_records_empty")
    output = Path(output_path)

    if dry_run:
        rows = [_dry_run_row(prompt, schema, config, index=index) for index, prompt in enumerate(prompts)]
        _write_jsonl(output, rows)
        return _runner_result(
            status="dry_run",
            prompt_count=len(prompts),
            response_count=0,
            output_path=output,
            api_call_count=0,
            warnings=[],
        )

    if not allow_api_judge:
        return _runner_result(
            status="refused",
            prompt_count=len(prompts),
            response_count=0,
            output_path=None,
            api_call_count=0,
            warnings=["api_judge_not_allowed"],
        )
    if confirm_api_judge != FLAGSHIP_API_JUDGE_OPT_IN_CONFIRMATION:
        return _runner_result(
            status="refused",
            prompt_count=len(prompts),
            response_count=0,
            output_path=None,
            api_call_count=0,
            warnings=["api_judge_confirmation_required"],
        )

    env = environ if environ is not None else os.environ
    key_name = _required_text(config.get("api_key_env"), "api_key_env_missing")
    api_key = env.get(key_name)
    if not api_key:
        return _runner_result(
            status="invalid_input",
            prompt_count=len(prompts),
            response_count=0,
            output_path=None,
            api_call_count=0,
            warnings=["judge_api_key_missing"],
        )
    if _optional_text(config.get("model")) in EVALUATED_MODEL_IDS:
        return _runner_result(
            status="invalid_input",
            prompt_count=len(prompts),
            response_count=0,
            output_path=None,
            api_call_count=0,
            warnings=["judge_model_matches_evaluated_pair"],
        )

    call = transport or _urllib_transport
    rows: list[dict[str, Any]] = []
    warnings: list[str] = []
    for index, prompt in enumerate(prompts):
        payload = build_openai_responses_payload(prompt, schema, config)
        url = _responses_url(config)
        headers = {
            "Content-Type": "application/json",
            "Authorization": f"Bearer {api_key}",
        }
        try:
            response = call(
                url,
                headers,
                json.dumps(payload, ensure_ascii=False).encode("utf-8"),
                float(config.get("timeout_seconds") or 120),
            )
            response_payload = _coerce_response_payload(response)
            raw_text = extract_openai_response_text(response_payload)
            parsed = _json_object_or_none(raw_text)
            rows.append(_raw_response_row(prompt, config, raw_text, parsed, index=index))
        except Exception as exc:
            code = _safe_error_code(exc)
            warnings.append(code)
            rows.append(_error_response_row(prompt, config, code, index=index))
    _write_jsonl(output, rows)

    parsed_path = Path(parsed_output_path) if parsed_output_path is not None else None
    if parse_after_run:
        if parsed_path is None:
            raise FlagshipAPIJudgeError("parsed_output_required")
        summary = build_flagship_judge_summary_from_responses(
            prompts,
            load_flagship_judge_raw_responses_jsonl(output),
            summary_id=_summary_id_from_prompt_rows(prompts),
            judge_model_id=_optional_text(config.get("model")),
            judge_provider=_optional_text(config.get("provider")) or "openai_responses_api",
        )
        write_flagship_judge_summary(summary, parsed_path)

    return _runner_result(
        status="ok" if not warnings else "completed_with_errors",
        prompt_count=len(prompts),
        response_count=len(rows),
        output_path=output,
        api_call_count=len(prompts),
        warnings=sorted(set(warnings)),
        parsed_output_path=parsed_path,
    )


def _normalize_config(payload: Mapping[str, Any]) -> dict[str, Any]:
    config = dict(payload)
    if config.get("provider") == "external_api":
        config["provider"] = "openai_responses_api"
    config.setdefault("base_url", "https://api.openai.com/v1")
    config.setdefault("timeout_seconds", 120)
    config.setdefault("response_format", "json_schema")
    return config


def _validate_config(config: Mapping[str, Any]) -> None:
    if config.get("schema_version") != FLAGSHIP_API_JUDGE_CONFIG_SCHEMA_VERSION:
        raise FlagshipAPIJudgeError("judge_config_schema_version_invalid")
    if config.get("provider") != "openai_responses_api":
        raise FlagshipAPIJudgeError("judge_provider_unsupported")
    _required_text(config.get("model"), "judge_model_missing")
    _required_text(config.get("api_key_env"), "api_key_env_missing")
    if config.get("judge_is_evaluated_model") is not False:
        raise FlagshipAPIJudgeError("judge_must_not_be_evaluated_model")
    if config.get("judge_is_independent_from_tested_pair") is not True:
        raise FlagshipAPIJudgeError("judge_must_be_independent_from_tested_pair")
    if _optional_text(config.get("model")) in EVALUATED_MODEL_IDS:
        raise FlagshipAPIJudgeError("judge_model_matches_evaluated_pair")
    base_url = _required_text(config.get("base_url"), "base_url_missing")
    if not (base_url.startswith("https://") or base_url.startswith("http://")):
        raise FlagshipAPIJudgeError("base_url_invalid")


def _dry_run_row(prompt: Mapping[str, Any], schema: Mapping[str, Any], config: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    payload = build_openai_responses_payload(prompt, schema, config)
    return _safe_value(
        {
            "schema_version": "flagship_api_judge_request_preview_v1",
            "summary_id": prompt.get("summary_id"),
            "run_id": prompt.get("run_id"),
            "trial_id": prompt.get("trial_id"),
            "judge_provider": config.get("provider"),
            "judge_model_id": config.get("model"),
            "request_preview": payload,
            "request_metadata": _request_metadata(prompt, schema, index=index),
            "no_api_call": True,
        }
    )


def _raw_response_row(
    prompt: Mapping[str, Any],
    config: Mapping[str, Any],
    raw_text: str,
    response: Mapping[str, Any] | None,
    *,
    index: int,
) -> dict[str, Any]:
    return _safe_value(
        {
            "schema_version": FLAGSHIP_API_JUDGE_RAW_RESPONSE_SCHEMA_VERSION,
            "summary_id": prompt.get("summary_id"),
            "run_id": prompt.get("run_id"),
            "trial_id": prompt.get("trial_id"),
            "judge_provider": config.get("provider"),
            "judge_model_id": config.get("model"),
            "response": dict(response) if response is not None else None,
            "raw_response": raw_text,
            "request_metadata": {
                "schema_name": FLAGSHIP_JUDGE_VERDICT_SCHEMA_VERSION,
                "prompt_record_index": index,
            },
            "no_runtime_execution": False,
        }
    )


def _error_response_row(
    prompt: Mapping[str, Any],
    config: Mapping[str, Any],
    error_code: str,
    *,
    index: int,
) -> dict[str, Any]:
    return _safe_value(
        {
            "schema_version": FLAGSHIP_API_JUDGE_RAW_RESPONSE_SCHEMA_VERSION,
            "summary_id": prompt.get("summary_id"),
            "run_id": prompt.get("run_id"),
            "trial_id": prompt.get("trial_id"),
            "judge_provider": config.get("provider"),
            "judge_model_id": config.get("model"),
            "response": None,
            "raw_response": None,
            "error_code": error_code,
            "request_metadata": {
                "schema_name": FLAGSHIP_JUDGE_VERDICT_SCHEMA_VERSION,
                "prompt_record_index": index,
            },
            "no_runtime_execution": False,
        }
    )


def _urllib_transport(url: str, headers: Mapping[str, str], body: bytes, timeout: float) -> Mapping[str, Any]:
    request = urllib.request.Request(url, data=body, headers=dict(headers), method="POST")
    try:
        with urllib.request.urlopen(request, timeout=timeout) as response:
            text = response.read().decode("utf-8")
    except urllib.error.HTTPError as exc:
        raise FlagshipAPIJudgeError(f"judge_api_http_error:{exc.code}") from exc
    except urllib.error.URLError as exc:
        raise FlagshipAPIJudgeError(f"judge_api_connection_error:{exc.__class__.__name__}") from exc
    payload = json.loads(text)
    if not isinstance(payload, Mapping):
        raise FlagshipAPIJudgeError("judge_api_response_not_object")
    return payload


def _coerce_response_payload(response: Mapping[str, Any] | str) -> dict[str, Any]:
    if isinstance(response, str):
        payload = json.loads(response)
    else:
        payload = dict(response)
    if not isinstance(payload, Mapping):
        raise FlagshipAPIJudgeError("judge_api_response_not_object")
    return dict(payload)


def _json_object_or_none(value: str) -> dict[str, Any] | None:
    try:
        payload = json.loads(value)
    except json.JSONDecodeError:
        return None
    return dict(payload) if isinstance(payload, Mapping) else None


def _responses_url(config: Mapping[str, Any]) -> str:
    base = str(config.get("base_url") or "").rstrip("/")
    return f"{base}{DEFAULT_OPENAI_RESPONSES_PATH}"


def _schema_name(schema: Mapping[str, Any]) -> str:
    title = str(schema.get("title") or FLAGSHIP_JUDGE_VERDICT_SCHEMA_VERSION)
    return re.sub(r"[^A-Za-z0-9_-]+", "_", title).strip("_") or FLAGSHIP_JUDGE_VERDICT_SCHEMA_VERSION


def _request_metadata(prompt: Mapping[str, Any], schema: Mapping[str, Any], *, index: int) -> dict[str, Any]:
    del prompt
    return {
        "schema_name": _schema_name(schema),
        "prompt_record_index": index,
    }


def _limited_records(rows: list[dict[str, Any]], max_records: int | None) -> list[dict[str, Any]]:
    if max_records is None:
        return rows
    if max_records < 1:
        raise FlagshipAPIJudgeError("max_records_invalid")
    return rows[:max_records]


def _summary_id_from_prompt_rows(rows: Sequence[Mapping[str, Any]]) -> str | None:
    for row in rows:
        text = _optional_text(row.get("summary_id"))
        if text:
            return text
    return None


def _runner_result(
    *,
    status: str,
    prompt_count: int,
    response_count: int,
    output_path: Path | None,
    api_call_count: int,
    warnings: list[str],
    parsed_output_path: Path | None = None,
) -> dict[str, Any]:
    return _safe_value(
        {
            "status": status,
            "prompt_count": prompt_count,
            "response_count": response_count,
            "api_call_count": api_call_count,
            "output_path": _display_path(output_path) if output_path else None,
            "parsed_output_path": _display_path(parsed_output_path) if parsed_output_path else None,
            "warnings": warnings,
            "no_runtime_execution": api_call_count == 0,
        }
    )


def _load_json_object(path: str | Path, *, label: str) -> dict[str, Any]:
    candidate = Path(path)
    try:
        payload = json.loads(candidate.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FlagshipAPIJudgeError(f"{label}_file_missing") from exc
    except OSError as exc:
        raise FlagshipAPIJudgeError(f"{label}_file_unreadable") from exc
    except json.JSONDecodeError as exc:
        raise FlagshipAPIJudgeError(f"{label}_json_malformed") from exc
    if not isinstance(payload, Mapping):
        raise FlagshipAPIJudgeError(f"{label}_payload_not_object")
    return dict(payload)


def _load_jsonl_objects(path: str | Path, *, error_prefix: str) -> list[dict[str, Any]]:
    candidate = Path(path)
    try:
        text = candidate.read_text(encoding="utf-8")
    except FileNotFoundError as exc:
        raise FlagshipAPIJudgeError(f"{error_prefix}_file_missing") from exc
    except OSError as exc:
        raise FlagshipAPIJudgeError(f"{error_prefix}_file_unreadable") from exc
    rows: list[dict[str, Any]] = []
    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            continue
        try:
            payload = json.loads(line)
        except json.JSONDecodeError as exc:
            raise FlagshipAPIJudgeError(f"{error_prefix}_jsonl_decode_error_line_{line_number}") from exc
        if not isinstance(payload, Mapping):
            raise FlagshipAPIJudgeError(f"{error_prefix}_record_not_object_line_{line_number}")
        rows.append(dict(payload))
    if not rows:
        raise FlagshipAPIJudgeError(f"{error_prefix}_records_empty")
    return rows


def _write_jsonl(path: Path, rows: Sequence[Mapping[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(_safe_value(dict(row)), ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )


def _required_text(value: Any, error: str) -> str:
    text = _optional_text(value)
    if not text:
        raise FlagshipAPIJudgeError(error)
    return text


def _optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    if not text:
        return None
    if _is_absolute_path(text):
        return "<absolute_path>"
    return _bounded_text(_redact_secret_text(text), 500)


def _safe_int(value: Any, *, fallback: int) -> int:
    if isinstance(value, bool):
        return int(value)
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return fallback
    return parsed if parsed >= 0 else fallback


def _safe_value(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {
            str(key): _safe_value(item)
            for key, item in value.items()
            if item is not None and str(key).lower() not in {"authorization", "api_key", "apikey"}
        }
    if isinstance(value, list | tuple):
        return [_safe_value(item) for item in value]
    if isinstance(value, str):
        return _bounded_text(_redact_secret_text(value), 24000)
    return value


def _safe_error_code(exc: Exception) -> str:
    if isinstance(exc, FlagshipAPIJudgeError):
        return str(exc)
    return f"judge_api_error:{exc.__class__.__name__}"


def _display_path(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(Path.cwd().resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return path.name


def _redact_secret_text(value: str) -> str:
    return re.sub(
        r"(?i)\b(api[_-]?key|token|secret|password|credential|auth|authorization)\s*[:=]\s*['\"]?[^,\s'\"]+",
        lambda match: f"{match.group(1)}=<redacted_secret>",
        value,
    )


def _bounded_text(value: str, max_chars: int) -> str:
    if len(value) > max_chars:
        return value[:max_chars] + "...[truncated]"
    return value


def _is_absolute_path(value: str) -> bool:
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute() or bool(re.match(r"^[A-Za-z]:", value))
