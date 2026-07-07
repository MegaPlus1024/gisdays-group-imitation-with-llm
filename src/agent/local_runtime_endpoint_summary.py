from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any


LOCAL_RUNTIME_ENDPOINT_SUMMARY_SCHEMA_VERSION = "local_runtime_endpoint_summary_v1"
LOCAL_RUNTIME_ENDPOINT_SUMMARY_FILENAME = "local_runtime_endpoint_summary.json"

_MAX_TEXT_CHARS = 500
_MAX_LIST_ITEMS = 200
_ENDPOINT_FIELDS = (
    "base_url",
    "api_base",
    "endpoint",
    "server_url",
    "openai_base_url",
    "llama_cpp_server_url",
)
_FORBIDDEN_PATH_PARTS = {
    ".codex",
    ".env",
    ".git",
    ".venv",
    "auth.json",
    "credential",
    "credentials",
    "key",
    "keys",
    "secret",
    "secrets",
    "token",
    "tokens",
}
_FORBIDDEN_OUTPUT_DIR_PARTS = {"reports", "experiments"}


class LocalRuntimeEndpointSummaryError(ValueError):
    """Controlled summary error safe to expose through CLI JSON."""


def summarize_local_runtime_endpoints(local_pipeline_config: Mapping[str, Any]) -> dict[str, Any]:
    """Summarize configured local runtime endpoints without connecting to them."""

    if not isinstance(local_pipeline_config, Mapping):
        return _summary(
            status="missing",
            models_config_path=None,
            orchestrator_model_id=None,
            executor_model_id=None,
            orchestrator_endpoint=None,
            executor_endpoint=None,
            missing_fields=["local_pipeline_config"],
            warnings=["local_pipeline_config_not_object"],
        )

    warnings: list[str] = []
    missing_fields: list[str] = []
    notes = ["Endpoint summary only; no network connection attempted."]
    models_config_path = _safe_optional_text(local_pipeline_config.get("models_config_path"))
    scenario_path = _safe_optional_text(local_pipeline_config.get("scenario_path"))
    orchestrator_model_id = _safe_optional_text(local_pipeline_config.get("orchestrator_model_id"))
    executor_model_id = _safe_optional_text(local_pipeline_config.get("executor_model_id"))

    scenario_payload = _load_optional_json_mapping(
        scenario_path,
        field_name="scenario_path",
        warnings=warnings,
    )
    if scenario_payload:
        orchestrator_model_id = orchestrator_model_id or _safe_optional_text(
            scenario_payload.get("orchestrator_model_id")
        )
        executor_model_id = executor_model_id or _safe_optional_text(scenario_payload.get("executor_model_id"))

    if not orchestrator_model_id:
        missing_fields.append("orchestrator_model_id")
    if not executor_model_id:
        missing_fields.append("executor_model_id")

    models_payload = _load_optional_json_mapping(
        models_config_path,
        field_name="models_config_path",
        warnings=warnings,
    )
    models_by_id = _models_by_id(models_payload)

    orchestrator_endpoint = _endpoint_for_model(
        model_id=orchestrator_model_id,
        role="orchestrator",
        local_pipeline_config=local_pipeline_config,
        models_by_id=models_by_id,
        missing_fields=missing_fields,
    )
    executor_endpoint = _endpoint_for_model(
        model_id=executor_model_id,
        role="executor",
        local_pipeline_config=local_pipeline_config,
        models_by_id=models_by_id,
        missing_fields=missing_fields,
    )

    if not models_config_path:
        missing_fields.append("models_config_path")
    if models_config_path and not models_payload:
        missing_fields.append("models_config")

    status = _summary_status(orchestrator_endpoint, executor_endpoint, missing_fields)
    return _summary(
        status=status,
        models_config_path=models_config_path,
        orchestrator_model_id=orchestrator_model_id,
        executor_model_id=executor_model_id,
        orchestrator_endpoint=orchestrator_endpoint,
        executor_endpoint=executor_endpoint,
        missing_fields=missing_fields,
        warnings=warnings,
        notes=notes,
    )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Summarize local model runtime endpoints from offline config only.",
    )
    parser.add_argument("--local-pipeline-config", required=True)
    parser.add_argument("--output")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        local_config_path = _validated_relative_path(
            args.local_pipeline_config,
            field_name="local_pipeline_config",
        )
        local_config = _load_required_json_mapping(local_config_path)
        summary = summarize_local_runtime_endpoints(local_config)
        if args.output:
            output_path = _validated_relative_path(args.output, field_name="output", for_output=True)
            output_path.parent.mkdir(parents=True, exist_ok=True)
            output_path.write_text(
                json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
    except LocalRuntimeEndpointSummaryError as exc:
        summary = _summary(
            status="missing",
            models_config_path=None,
            orchestrator_model_id=None,
            executor_model_id=None,
            orchestrator_endpoint=None,
            executor_endpoint=None,
            missing_fields=[],
            warnings=[str(exc)],
        )
        print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
        return 2

    print(json.dumps(summary, ensure_ascii=False, sort_keys=True))
    return 0 if summary.get("status") in {"resolved", "partial", "missing"} else 2


def _endpoint_for_model(
    *,
    model_id: str | None,
    role: str,
    local_pipeline_config: Mapping[str, Any],
    models_by_id: Mapping[str, Mapping[str, Any]],
    missing_fields: list[str],
) -> str | None:
    override = _safe_optional_text(local_pipeline_config.get(f"{role}_base_url"))
    if override:
        return override.rstrip("/")
    if not model_id:
        missing_fields.append(f"{role}_model_id")
        return None
    model = models_by_id.get(model_id)
    if model is None:
        missing_fields.append(f"{role}_model_config")
        return None
    endpoint = _endpoint_from_model_config(model)
    if endpoint is None:
        missing_fields.append(f"{role}_endpoint")
    return endpoint


def _endpoint_from_model_config(model: Mapping[str, Any]) -> str | None:
    for field in _ENDPOINT_FIELDS:
        text = _safe_optional_text(model.get(field))
        if text:
            return text.rstrip("/")
    host = _safe_optional_text(model.get("host"))
    port = _safe_optional_text(model.get("port"))
    if host and port:
        return f"{host}:{port}"
    if host:
        return host
    return None


def _models_by_id(payload: Mapping[str, Any] | None) -> dict[str, Mapping[str, Any]]:
    if not isinstance(payload, Mapping):
        return {}
    rows = payload.get("models")
    if not isinstance(rows, list):
        return {}
    models: dict[str, Mapping[str, Any]] = {}
    for row in rows[:_MAX_LIST_ITEMS]:
        if not isinstance(row, Mapping):
            continue
        model_id = _safe_optional_text(row.get("model_id"))
        if model_id:
            models[model_id] = row
    return models


def _summary_status(
    orchestrator_endpoint: str | None,
    executor_endpoint: str | None,
    missing_fields: Sequence[str],
) -> str:
    if orchestrator_endpoint and executor_endpoint and not missing_fields:
        return "resolved"
    if orchestrator_endpoint or executor_endpoint:
        return "partial"
    return "missing"


def _summary(
    *,
    status: str,
    models_config_path: str | None,
    orchestrator_model_id: str | None,
    executor_model_id: str | None,
    orchestrator_endpoint: str | None,
    executor_endpoint: str | None,
    missing_fields: Sequence[str],
    warnings: Sequence[str],
    notes: Sequence[str] | None = None,
) -> dict[str, Any]:
    return _safe_mapping(
        {
            "schema_version": LOCAL_RUNTIME_ENDPOINT_SUMMARY_SCHEMA_VERSION,
            "status": status,
            "models_config_path": models_config_path,
            "orchestrator_model_id": orchestrator_model_id,
            "executor_model_id": executor_model_id,
            "orchestrator_endpoint": orchestrator_endpoint,
            "executor_endpoint": executor_endpoint,
            "shared_endpoint": (
                bool(orchestrator_endpoint)
                and bool(executor_endpoint)
                and orchestrator_endpoint == executor_endpoint
            ),
            "missing_fields": sorted(set(_safe_text_list(missing_fields))),
            "warnings": sorted(set(_safe_text_list(warnings))),
            "notes": _safe_text_list(notes or ["Endpoint summary only; no network connection attempted."]),
            "no_runtime_execution": True,
        }
    )


def _load_required_json_mapping(path: Path) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise LocalRuntimeEndpointSummaryError("local_pipeline_config_missing") from exc
    except json.JSONDecodeError as exc:
        raise LocalRuntimeEndpointSummaryError("local_pipeline_config_malformed") from exc
    if not isinstance(payload, dict):
        raise LocalRuntimeEndpointSummaryError("local_pipeline_config_not_object")
    return payload


def _load_optional_json_mapping(
    value: str | None,
    *,
    field_name: str,
    warnings: list[str],
) -> dict[str, Any] | None:
    if not value:
        return None
    try:
        path = _validated_relative_path(value, field_name=field_name)
        payload = json.loads(path.read_text(encoding="utf-8"))
    except (LocalRuntimeEndpointSummaryError, FileNotFoundError, OSError, json.JSONDecodeError):
        warnings.append(f"{field_name}_unreadable")
        return None
    if not isinstance(payload, dict):
        warnings.append(f"{field_name}_not_object")
        return None
    return payload


def _validated_relative_path(
    value: str | Path,
    *,
    field_name: str,
    for_output: bool = False,
) -> Path:
    text = str(value).strip()
    if not text:
        raise LocalRuntimeEndpointSummaryError(f"{field_name}_required")
    if "://" in text or _is_absolute_path(text):
        raise LocalRuntimeEndpointSummaryError(f"{field_name}_forbidden")
    path = PureWindowsPath(text) if "\\" in text else PurePosixPath(text)
    parts = [part.strip() for part in path.parts if part.strip()]
    lowered = [part.lower() for part in parts]
    if not parts:
        raise LocalRuntimeEndpointSummaryError(f"{field_name}_required")
    if ".." in parts:
        raise LocalRuntimeEndpointSummaryError(f"{field_name}_forbidden")
    if set(lowered) & _FORBIDDEN_PATH_PARTS:
        raise LocalRuntimeEndpointSummaryError(f"{field_name}_forbidden")
    if for_output and (set(lowered) & _FORBIDDEN_OUTPUT_DIR_PARTS or _is_docs_ai_final_path(lowered)):
        raise LocalRuntimeEndpointSummaryError(f"{field_name}_forbidden")
    return Path(text)


def _is_docs_ai_final_path(parts: Sequence[str]) -> bool:
    for index in range(0, max(0, len(parts) - 2)):
        if parts[index] == "docs" and parts[index + 1] == "ai" and parts[index + 2].startswith("final"):
            return True
    return False


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
    if re.match(r"^[A-Za-z][A-Za-z0-9+.-]*://", text):
        text = re.sub(r"://[^/\s:@]+:[^/\s@]+@", "://<redacted_secret>@", text)
        if len(text) > _MAX_TEXT_CHARS:
            return text[:_MAX_TEXT_CHARS] + "...[truncated]"
        return text
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
            "api_key",
            "apikey",
            "auth",
            "credential",
            "password",
            "raw_model_output",
            "raw_output",
            "raw_prompt",
            "raw_response",
            "secret",
            "token",
        )
    )


def _is_absolute_path(value: str) -> bool:
    return (
        PureWindowsPath(value).is_absolute()
        or PurePosixPath(value).is_absolute()
        or bool(re.match(r"^[A-Za-z]:", value))
    )


if __name__ == "__main__":
    raise SystemExit(main())
