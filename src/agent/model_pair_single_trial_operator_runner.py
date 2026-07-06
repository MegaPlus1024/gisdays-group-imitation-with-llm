from __future__ import annotations

import argparse
import importlib
import json
import re
from collections.abc import Callable, Mapping, Sequence
from dataclasses import dataclass
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from . import model_pair_single_trial_execution as _single_trial_execution


MODEL_PAIR_SINGLE_TRIAL_OPERATOR_RUNNER_SCHEMA_VERSION = "model_pair_single_trial_operator_runner_v1"
SINGLE_TRIAL_RUNTIME_CONFIRMATION = "SINGLE_TRIAL_RUNTIME_OPT_IN"
LOCAL_MODEL_PAIR_ENTRYPOINT_REF = "src.agent.model_pair_local_pipeline_entrypoint:run_local_model_pair_trial"

_MAX_TEXT_CHARS = 500
_MAX_LIST_ITEMS = 200
_FORBIDDEN_OUTPUT_DIR_PARTS = {"reports", "experiments"}
_ENTRYPOINT_MODULE_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*(?:\.[A-Za-z_][A-Za-z0-9_]*)*$")
_ENTRYPOINT_FUNCTION_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_]*$")
_PATH_LIKE_KEY_RE = re.compile(r"(^|_)(path|dir|file|root)$")

_DEFAULT_RUN_SINGLE_MODEL_PAIR_TRIAL = _single_trial_execution.run_single_model_pair_trial
run_single_model_pair_trial = _DEFAULT_RUN_SINGLE_MODEL_PAIR_TRIAL


class ModelPairSingleTrialOperatorError(ValueError):
    """Controlled operator-runner error safe to expose through JSON output."""


@dataclass(frozen=True)
class ModelPairSingleTrialOperatorConfig:
    plan_path: Path | str | None = None
    readiness_summary_path: Path | str | None = None
    entrypoint_ref: str | None = None
    local_pipeline_config_path: Path | str | None = None
    output_dir: Path | str | None = None
    trial_id: str | None = None
    pair_id: str | None = None
    scenario_id: str | None = None
    repeat_index: int | None = None
    allow_runtime_execution: bool = False
    confirm_runtime_execution: str | None = None
    auto_matrix_adapter_outputs: bool = False
    run_id: str | None = None
    tags: tuple[str, ...] = ()
    write_trial_result: bool = True
    write_matrix_summary: bool = True


def parse_entrypoint_ref(ref: str) -> tuple[str, str]:
    if not isinstance(ref, str) or not ref.strip():
        raise ModelPairSingleTrialOperatorError("entrypoint_ref_required")
    text = ref.strip()
    if any(token in text for token in ("/", "\\", "..")):
        raise ModelPairSingleTrialOperatorError("entrypoint_ref_invalid")
    if text.count(":") != 1:
        raise ModelPairSingleTrialOperatorError("entrypoint_ref_invalid")
    module_name, function_name = (part.strip() for part in text.split(":", maxsplit=1))
    if not module_name or not function_name:
        raise ModelPairSingleTrialOperatorError("entrypoint_ref_invalid")
    if not _ENTRYPOINT_MODULE_RE.fullmatch(module_name):
        raise ModelPairSingleTrialOperatorError("entrypoint_ref_invalid")
    if not _ENTRYPOINT_FUNCTION_RE.fullmatch(function_name):
        raise ModelPairSingleTrialOperatorError("entrypoint_ref_invalid")
    return module_name, function_name


def load_entrypoint_from_ref(ref: str) -> Callable[[dict[str, Any]], Any]:
    module_name, function_name = parse_entrypoint_ref(ref)
    try:
        module = importlib.import_module(module_name)
    except ImportError as exc:
        raise ModelPairSingleTrialOperatorError("entrypoint_import_failed") from exc
    try:
        entrypoint = getattr(module, function_name)
    except AttributeError as exc:
        raise ModelPairSingleTrialOperatorError("entrypoint_attribute_missing") from exc
    if not callable(entrypoint):
        raise ModelPairSingleTrialOperatorError("entrypoint_not_callable")
    return entrypoint


def run_single_trial_operator(args_or_config: Any) -> dict[str, Any]:
    config: ModelPairSingleTrialOperatorConfig | None = None
    try:
        config = _coerce_config(args_or_config)
        _validate_required_config(config)
        output_dir = _validated_output_dir(config.output_dir)
        _validate_runtime_confirmation(config)
        plan_payload = _load_json_object(
            config.plan_path,
            missing_value_code="plan_required",
            missing_file_code="plan_file_missing",
            unreadable_code="plan_file_unreadable",
            malformed_code="plan_json_malformed",
            object_code="plan_payload_not_object",
        )
        _load_json_object(
            config.readiness_summary_path,
            missing_value_code="readiness_summary_required",
            missing_file_code="readiness_summary_file_missing",
            unreadable_code="readiness_summary_file_unreadable",
            malformed_code="readiness_summary_json_malformed",
            object_code="readiness_summary_payload_not_object",
        )
        local_pipeline_config = _load_local_pipeline_config(config)
        entrypoint = load_entrypoint_from_ref(config.entrypoint_ref or "")
        single_result = _current_single_trial_api()(
            plan_payload,
            pipeline_entrypoint=entrypoint,
            config=_single_trial_execution.ModelPairSingleTrialExecutionConfig(
                output_dir=output_dir,
                trial_id=config.trial_id,
                pair_id=config.pair_id,
                scenario_id=config.scenario_id,
                repeat_index=config.repeat_index,
                allow_runtime_execution=bool(config.allow_runtime_execution),
                readiness_summary_path=config.readiness_summary_path,
                write_matrix_summary=bool(config.write_matrix_summary),
                write_trial_result=bool(config.write_trial_result),
                auto_matrix_adapter_outputs=bool(config.auto_matrix_adapter_outputs),
                extra_config=(
                    {"local_pipeline_config": local_pipeline_config}
                    if local_pipeline_config is not None
                    else None
                ),
                run_id=config.run_id,
                tags=config.tags,
            ),
        )
    except ModelPairSingleTrialOperatorError as exc:
        return _invalid_result(str(exc), config=config)
    except (OSError, TypeError, ValueError) as exc:
        return _invalid_result(_safe_error_code(exc), config=config)

    return _operator_result(single_result, config=config)


def _current_single_trial_api() -> Callable[..., dict[str, Any]]:
    if run_single_model_pair_trial is _DEFAULT_RUN_SINGLE_MODEL_PAIR_TRIAL:
        return _single_trial_execution.run_single_model_pair_trial
    return run_single_model_pair_trial


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one guarded model-pair trial from explicit offline artifacts and an explicit entrypoint.",
        epilog=(
            "Project-owned local entrypoint target: "
            "src.agent.model_pair_local_pipeline_entrypoint:run_local_model_pair_trial"
        ),
    )
    parser.add_argument("--plan", dest="plan_path")
    parser.add_argument("--readiness-summary", dest="readiness_summary_path")
    parser.add_argument("--entrypoint", dest="entrypoint_ref")
    parser.add_argument("--local-pipeline-config", dest="local_pipeline_config_path")
    parser.add_argument("--output-dir", dest="output_dir")
    parser.add_argument("--trial-id", dest="trial_id")
    parser.add_argument("--pair-id", dest="pair_id")
    parser.add_argument("--scenario-id", dest="scenario_id")
    parser.add_argument("--repeat-index", dest="repeat_index", type=int)
    parser.add_argument("--allow-runtime-execution", dest="allow_runtime_execution", action="store_true")
    parser.add_argument("--confirm-runtime-execution", dest="confirm_runtime_execution")
    parser.add_argument("--auto-matrix-adapter-outputs", dest="auto_matrix_adapter_outputs", action="store_true")
    parser.add_argument("--run-id", dest="run_id")
    parser.add_argument("--tag", dest="tags", action="append", default=[])
    parser.add_argument("--no-trial-result-file", dest="write_trial_result", action="store_false", default=True)
    parser.add_argument("--no-matrix-summary-file", dest="write_matrix_summary", action="store_false", default=True)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = run_single_trial_operator(args)
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 0 if result.get("status") == "succeeded" else 2


def _coerce_config(value: Any) -> ModelPairSingleTrialOperatorConfig:
    if isinstance(value, ModelPairSingleTrialOperatorConfig):
        return value
    if isinstance(value, Mapping):
        source = dict(value)
        return ModelPairSingleTrialOperatorConfig(
            plan_path=_field(source, "plan_path", "plan"),
            readiness_summary_path=_field(source, "readiness_summary_path", "readiness_summary"),
            entrypoint_ref=_field(source, "entrypoint_ref", "entrypoint"),
            local_pipeline_config_path=_field(source, "local_pipeline_config_path", "local_pipeline_config"),
            output_dir=_field(source, "output_dir"),
            trial_id=_field(source, "trial_id"),
            pair_id=_field(source, "pair_id"),
            scenario_id=_field(source, "scenario_id"),
            repeat_index=_coerce_repeat_index(_field(source, "repeat_index")),
            allow_runtime_execution=_coerce_bool(_field(source, "allow_runtime_execution"), default=False),
            confirm_runtime_execution=_field(source, "confirm_runtime_execution"),
            auto_matrix_adapter_outputs=_coerce_bool(_field(source, "auto_matrix_adapter_outputs"), default=False),
            run_id=_field(source, "run_id"),
            tags=_coerce_tags(_field(source, "tags", "tag")),
            write_trial_result=_coerce_bool(_field(source, "write_trial_result"), default=True),
            write_matrix_summary=_coerce_bool(_field(source, "write_matrix_summary"), default=True),
        )
    if hasattr(value, "__dict__"):
        return _coerce_config(vars(value))
    raise ModelPairSingleTrialOperatorError("config_invalid")


def _field(source: Mapping[str, Any], *names: str) -> Any:
    for name in names:
        if name in source:
            return source[name]
    return None


def _coerce_repeat_index(value: Any) -> int | None:
    if value is None or value == "":
        return None
    if isinstance(value, bool):
        raise ModelPairSingleTrialOperatorError("repeat_index_invalid")
    try:
        return int(value)
    except (TypeError, ValueError) as exc:
        raise ModelPairSingleTrialOperatorError("repeat_index_invalid") from exc


def _coerce_bool(value: Any, *, default: bool) -> bool:
    if value is None:
        return default
    if isinstance(value, bool):
        return value
    if isinstance(value, str):
        normalized = value.strip().lower()
        if normalized in {"1", "true", "yes", "on"}:
            return True
        if normalized in {"0", "false", "no", "off"}:
            return False
    raise ModelPairSingleTrialOperatorError("bool_field_invalid")


def _coerce_tags(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        return (_safe_text(value),)
    if isinstance(value, list | tuple | set):
        return tuple(_safe_text(str(item)) for item in list(value)[:_MAX_LIST_ITEMS] if item is not None)
    raise ModelPairSingleTrialOperatorError("tags_invalid")


def _validate_required_config(config: ModelPairSingleTrialOperatorConfig) -> None:
    if not _safe_optional_text(config.plan_path):
        raise ModelPairSingleTrialOperatorError("plan_required")
    if not _safe_optional_text(config.readiness_summary_path):
        raise ModelPairSingleTrialOperatorError("readiness_summary_required")
    if not _safe_optional_text(config.entrypoint_ref):
        raise ModelPairSingleTrialOperatorError("entrypoint_ref_required")
    if not _safe_optional_text(config.output_dir):
        raise ModelPairSingleTrialOperatorError("output_dir_required")
    if not _safe_optional_text(config.trial_id):
        if not _safe_optional_text(config.pair_id) or not _safe_optional_text(config.scenario_id):
            raise ModelPairSingleTrialOperatorError("trial_selector_required")


def _validate_runtime_confirmation(config: ModelPairSingleTrialOperatorConfig) -> None:
    if not config.allow_runtime_execution:
        return
    if config.confirm_runtime_execution is None:
        raise ModelPairSingleTrialOperatorError("runtime_confirmation_required")
    if config.confirm_runtime_execution != SINGLE_TRIAL_RUNTIME_CONFIRMATION:
        raise ModelPairSingleTrialOperatorError("runtime_confirmation_invalid")


def _load_json_object(
    value: str | Path | None,
    *,
    missing_value_code: str,
    missing_file_code: str,
    unreadable_code: str,
    malformed_code: str,
    object_code: str,
) -> dict[str, Any]:
    if not _safe_optional_text(value):
        raise ModelPairSingleTrialOperatorError(missing_value_code)
    path = Path(value)
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise ModelPairSingleTrialOperatorError(missing_file_code) from exc
    except OSError as exc:
        raise ModelPairSingleTrialOperatorError(unreadable_code) from exc
    except json.JSONDecodeError as exc:
        raise ModelPairSingleTrialOperatorError(malformed_code) from exc
    if not isinstance(payload, dict):
        raise ModelPairSingleTrialOperatorError(object_code)
    return payload


def _load_local_pipeline_config(config: ModelPairSingleTrialOperatorConfig) -> dict[str, Any] | None:
    has_path = _safe_optional_text(config.local_pipeline_config_path) is not None
    if not has_path:
        if config.allow_runtime_execution and _is_local_model_pair_entrypoint(config.entrypoint_ref):
            raise ModelPairSingleTrialOperatorError("local_pipeline_config_required")
        return None
    path = _validated_relative_config_path(config.local_pipeline_config_path)
    payload = _load_json_object(
        path,
        missing_value_code="local_pipeline_config_required",
        missing_file_code="local_pipeline_config_file_missing",
        unreadable_code="local_pipeline_config_file_unreadable",
        malformed_code="local_pipeline_config_json_malformed",
        object_code="local_pipeline_config_payload_not_object",
    )
    _validate_local_pipeline_config_payload(payload)
    return payload


def _is_local_model_pair_entrypoint(ref: Any) -> bool:
    return _safe_optional_text(ref) == LOCAL_MODEL_PAIR_ENTRYPOINT_REF


def _validated_relative_config_path(value: str | Path | None) -> Path:
    if value is None:
        raise ModelPairSingleTrialOperatorError("local_pipeline_config_required")
    text = str(value).strip()
    if not text:
        raise ModelPairSingleTrialOperatorError("local_pipeline_config_required")
    if _is_forbidden_config_file_path_text(text):
        raise ModelPairSingleTrialOperatorError("local_pipeline_config_path_forbidden")
    return Path(text)


def _validate_local_pipeline_config_payload(payload: Mapping[str, Any]) -> None:
    if _contains_secret_like_config(payload):
        raise ModelPairSingleTrialOperatorError("local_pipeline_config_secret_like")
    for path_key, path_value in _path_like_config_values(payload):
        if _is_forbidden_path_text(path_value):
            raise ModelPairSingleTrialOperatorError("local_pipeline_config_path_forbidden")
        if path_key.endswith("out_dir") or path_key == "out_dir" or path_key.endswith("_dir"):
            _validate_local_pipeline_output_dir(path_value)
    out_dir = payload.get("out_dir")
    if not _safe_optional_text(out_dir):
        raise ModelPairSingleTrialOperatorError("local_pipeline_config_out_dir_missing")
    if isinstance(out_dir, str):
        _validate_local_pipeline_output_dir(out_dir)


def _path_like_config_values(payload: Mapping[str, Any], *, prefix: str = "") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for key, value in payload.items():
        key_text = str(key)
        dotted_key = f"{prefix}.{key_text}" if prefix else key_text
        if isinstance(value, Mapping):
            rows.extend(_path_like_config_values(value, prefix=dotted_key))
            continue
        if isinstance(value, str) and _is_path_like_key(key_text):
            rows.append((key_text.lower(), value))
    return rows


def _is_path_like_key(key: str) -> bool:
    return bool(_PATH_LIKE_KEY_RE.search(key.lower()))


def _validate_local_pipeline_output_dir(value: str) -> None:
    parts = [part.lower() for part in Path(value).parts]
    if set(parts) & _FORBIDDEN_OUTPUT_DIR_PARTS or _is_docs_ai_final_path(parts):
        raise ModelPairSingleTrialOperatorError("local_pipeline_config_output_dir_forbidden")


def _is_forbidden_path_text(value: str) -> bool:
    text = value.strip()
    if not text:
        return True
    if "://" in text:
        return True
    windows_path = PureWindowsPath(text)
    posix_path = PurePosixPath(text)
    if windows_path.is_absolute() or posix_path.is_absolute() or bool(re.match(r"^[A-Za-z]:", text)):
        return True
    return any(part == ".." for part in windows_path.parts) or any(part == ".." for part in posix_path.parts)


def _is_forbidden_config_file_path_text(value: str) -> bool:
    text = value.strip()
    if not text or "://" in text:
        return True
    windows_path = PureWindowsPath(text)
    posix_path = PurePosixPath(text)
    return any(part == ".." for part in windows_path.parts) or any(part == ".." for part in posix_path.parts)


def _contains_secret_like_config(value: Any) -> bool:
    if isinstance(value, Mapping):
        for key, item in value.items():
            if _secret_like_key(str(key)) or _contains_secret_like_config(item):
                return True
        return False
    if isinstance(value, list | tuple | set):
        return any(_contains_secret_like_config(item) for item in value)
    if isinstance(value, str):
        return _secret_assignment_like_text(value)
    return False


def _secret_assignment_like_text(value: str) -> bool:
    return bool(
        re.search(
            r"(?i)\b(api[_-]?key|token|secret|password|credential|auth)\s*[:=]\s*['\"]?[^,\s'\"]+",
            value,
        )
    )


def _validated_output_dir(value: str | Path | None) -> Path:
    if not _safe_optional_text(value):
        raise ModelPairSingleTrialOperatorError("output_dir_required")
    try:
        output_dir = Path(value)
    except TypeError as exc:
        raise ModelPairSingleTrialOperatorError("output_dir_invalid") from exc
    parts = [part.lower() for part in output_dir.parts]
    if set(parts) & _FORBIDDEN_OUTPUT_DIR_PARTS:
        raise ModelPairSingleTrialOperatorError("output_dir_forbidden")
    if _is_docs_ai_final_path(parts):
        raise ModelPairSingleTrialOperatorError("output_dir_forbidden")
    return output_dir


def _is_docs_ai_final_path(parts: list[str]) -> bool:
    for index in range(0, max(0, len(parts) - 2)):
        if parts[index] == "docs" and parts[index + 1] == "ai" and parts[index + 2].startswith("final"):
            return True
    return False


def _operator_result(
    single_result: Mapping[str, Any],
    *,
    config: ModelPairSingleTrialOperatorConfig,
) -> dict[str, Any]:
    payload = dict(single_result)
    payload["operator_schema_version"] = MODEL_PAIR_SINGLE_TRIAL_OPERATOR_RUNNER_SCHEMA_VERSION
    payload["operator_runner"] = "model_pair_single_trial_operator_runner"
    payload["entrypoint_ref"] = _safe_optional_text(config.entrypoint_ref)
    payload["runtime_confirmation"] = "accepted" if config.allow_runtime_execution else "not_required"
    payload["auto_matrix_adapter_outputs"] = bool(config.auto_matrix_adapter_outputs)
    return _safe_mapping(payload)


def _invalid_result(
    error: str,
    *,
    config: ModelPairSingleTrialOperatorConfig | None,
) -> dict[str, Any]:
    allow_runtime = bool(config.allow_runtime_execution) if config is not None else False
    payload = {
        "operator_schema_version": MODEL_PAIR_SINGLE_TRIAL_OPERATOR_RUNNER_SCHEMA_VERSION,
        "status": "invalid",
        "run_id": _safe_optional_text(config.run_id) if config is not None else None,
        "trial_id": _safe_optional_text(config.trial_id) if config is not None else None,
        "pair_id": _safe_optional_text(config.pair_id) if config is not None else None,
        "scenario_id": _safe_optional_text(config.scenario_id) if config is not None else None,
        "repeat_index": config.repeat_index if config is not None else None,
        "allow_runtime_execution": allow_runtime,
        "no_runtime_execution": True,
        "matrix_summary_path": None,
        "trial_result_path": None,
        "adapter_summary_path": None,
        "warnings": [_safe_text(error)],
        "notes": ["single_trial_operator_runner_invalid"],
        "tags": _safe_text_list(config.tags) if config is not None else [],
        "error": _safe_text(error),
    }
    return _safe_mapping(payload)


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


if __name__ == "__main__":
    raise SystemExit(main())
