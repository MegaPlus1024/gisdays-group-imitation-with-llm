from __future__ import annotations

import argparse
import json
import re
from collections.abc import Mapping, Sequence
from pathlib import Path, PurePosixPath, PureWindowsPath
from typing import Any

from .model_catalog import ModelCatalog, ModelCatalogEntry, load_model_catalog
from .model_comparison_plan import (
    MODEL_COMPARISON_PLAN_NOTE,
    ModelComparisonPlanConfig,
    ModelComparisonScenarioRef,
    build_model_comparison_plan,
)
from .model_pair_execution_readiness import (
    MODEL_PAIR_EXECUTION_READINESS_SUMMARY_FILENAME,
    validate_model_pair_execution_readiness,
    write_model_pair_execution_readiness_summary,
)


FIRST_SINGLE_TRIAL_RUN_PACKET_SCHEMA_VERSION = "first_single_trial_run_packet_v1"
FIRST_SINGLE_TRIAL_COMMAND_SCHEMA_VERSION = "first_single_trial_command_v1"
LOCAL_MODEL_PAIR_ENTRYPOINT_REF = (
    "src.agent.model_pair_local_pipeline_entrypoint:run_local_model_pair_trial"
)
SINGLE_TRIAL_RUNTIME_CONFIRMATION = "SINGLE_TRIAL_RUNTIME_OPT_IN"
CONTROLLED_SINGLE_TRIAL_TAG = "controlled_single_trial"
MODEL_PAIR_PLAN_FILENAME = "model_pair_plan.json"
LOCAL_PIPELINE_CONFIG_FILENAME = "local_pipeline_config.json"
RUN_SINGLE_TRIAL_SCRIPT_FILENAME = "run_single_trial_controlled.ps1"
COMMAND_JSON_FILENAME = "command.json"

_MAX_TEXT_CHARS = 500
_MAX_LIST_ITEMS = 200
_FORBIDDEN_OUTPUT_DIR_PARTS = {"reports", "experiments"}
_FORBIDDEN_READ_PATH_PARTS = {
    ".codex",
    ".env",
    ".git",
    ".venv",
    "auth.json",
    "credential",
    "credentials",
    "downloads",
    "key",
    "keys",
    "secret",
    "secrets",
    "telegram desktop",
    "token",
    "tokens",
}
_PATH_LIKE_KEY_RE = re.compile(
    r"(^|_)(path|dir|file|filename)$|(path|dir|file|filename)",
    re.IGNORECASE,
)
_ENTRYPOINT_RE = re.compile(r"^[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*$")


class FirstRunPacketError(ValueError):
    """Controlled packet-build error safe to expose through CLI JSON."""


def build_first_single_trial_run_packet(
    *,
    output_dir: str | Path,
    model_catalog_path: str | Path,
    scenario_id: str,
    pair_id: str,
    local_pipeline_config_path: str | Path,
    run_id: str,
    trial_id: str | None = None,
    repeat_index: int = 1,
    entrypoint: str = LOCAL_MODEL_PAIR_ENTRYPOINT_REF,
    auto_matrix_adapter_outputs: bool = True,
    tags: Sequence[str] = (),
) -> dict[str, Any]:
    """Build an offline packet for one explicitly controlled model-pair trial."""

    clean_run_id = _safe_optional_text(run_id)
    clean_trial_id = _safe_optional_text(trial_id)
    clean_pair_id = _safe_optional_text(pair_id)
    clean_scenario_id = _safe_optional_text(scenario_id)
    packet_dir_text = _safe_optional_text(output_dir)

    try:
        packet_dir = _validated_relative_path(output_dir, field_name="output_dir", for_output=True)
        catalog_path = _validated_relative_path(model_catalog_path, field_name="model_catalog_path")
        local_config_source_path = _validated_relative_path(
            local_pipeline_config_path,
            field_name="local_pipeline_config_path",
        )
        clean_run_id = _required_token(run_id, field_name="run_id")
        clean_pair_id = _required_token(pair_id, field_name="pair_id")
        clean_scenario_id = _required_token(scenario_id, field_name="scenario_id")
        repeat = _validated_repeat_index(repeat_index)
        clean_entrypoint = _validated_entrypoint(entrypoint)
        clean_tags = _clean_tags(tags)

        local_pipeline_config = _load_json_object(
            local_config_source_path,
            missing_code="local_pipeline_config_file_missing",
            malformed_code="local_pipeline_config_json_malformed",
            object_code="local_pipeline_config_payload_not_object",
        )
        _validate_local_pipeline_config_payload(local_pipeline_config)
        scenario_path_text = _required_text(
            local_pipeline_config.get("scenario_path"),
            field_name="local_pipeline_config_scenario_path",
        )
        scenario_path = _validated_relative_path(scenario_path_text, field_name="scenario_path")

        catalog = load_model_catalog(catalog_path)
        packet_dir.mkdir(parents=True, exist_ok=True)

        plan = _build_single_trial_plan(
            catalog=catalog,
            catalog_path=catalog_path,
            scenario_id=clean_scenario_id,
            scenario_path=scenario_path,
            pair_id=clean_pair_id,
            run_id=clean_run_id,
            trial_id=clean_trial_id,
            repeat_index=repeat,
            tags=clean_tags,
        )
        plan_path = _write_model_pair_plan(plan, packet_dir)
        plan_payload = plan.model_dump(mode="json")
        selected_trial = plan_payload["trials"][0]

        readiness_summary = validate_model_pair_execution_readiness(
            plan_payload,
            role_config_resolver=_role_config_resolver(),
            scenario_config_resolver=_scenario_config_resolver(
                scenario_path_text=str(scenario_path).replace("\\", "/"),
                local_pipeline_config=local_pipeline_config,
            ),
            model_binding_resolver=_model_binding_resolver(catalog),
        )
        readiness_summary_path = write_model_pair_execution_readiness_summary(
            readiness_summary,
            packet_dir,
        )

        copied_config_path = packet_dir / LOCAL_PIPELINE_CONFIG_FILENAME
        copied_config_path.write_text(
            json.dumps(
                _safe_config_for_packet(local_pipeline_config),
                ensure_ascii=False,
                indent=2,
                sort_keys=True,
            ),
            encoding="utf-8",
        )

        command = _build_controlled_command(
            packet_dir=packet_dir,
            plan_path=plan_path,
            readiness_summary_path=readiness_summary_path,
            local_pipeline_config_path=copied_config_path,
            run_id=clean_run_id,
            trial_id=str(selected_trial["trial_id"]),
            entrypoint=clean_entrypoint,
            auto_matrix_adapter_outputs=bool(auto_matrix_adapter_outputs),
            tags=clean_tags,
        )
        script_path = packet_dir / RUN_SINGLE_TRIAL_SCRIPT_FILENAME
        script_path.write_text(_powershell_script(command), encoding="utf-8")
        command_path = packet_dir / COMMAND_JSON_FILENAME
        command_payload = {
            "schema_version": FIRST_SINGLE_TRIAL_COMMAND_SCHEMA_VERSION,
            "argv": command,
            "command": _command_text(command),
            "script_path": _relative_path_text(script_path),
            "no_runtime_execution": True,
            "notes": [
                "Prepared command only; this packet builder does not execute runtime.",
                "The generated script requires explicit runtime confirmation before use.",
            ],
        }
        command_path.write_text(
            json.dumps(command_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )

        readiness_status = _safe_optional_text(readiness_summary.get("status")) or "not_ready"
        status = "ready" if readiness_status == "ready" else "not_ready"
        warnings = _safe_text_list(readiness_summary.get("warnings"))
        if status != "ready":
            warnings.append("readiness_not_ready")

        return _safe_mapping(
            {
                "schema_version": FIRST_SINGLE_TRIAL_RUN_PACKET_SCHEMA_VERSION,
                "status": status,
                "run_id": clean_run_id,
                "trial_id": selected_trial["trial_id"],
                "pair_id": clean_pair_id,
                "scenario_id": clean_scenario_id,
                "packet_dir": _relative_path_text(packet_dir),
                "plan_path": _relative_path_text(plan_path),
                "readiness_summary_path": _relative_path_text(readiness_summary_path),
                "local_pipeline_config_path": _relative_path_text(copied_config_path),
                "run_script_path": _relative_path_text(script_path),
                "command_path": _relative_path_text(command_path),
                "readiness_status": readiness_status,
                "warnings": sorted(set(warnings)),
                "notes": [
                    "first_single_trial_run_packet_prepared_offline",
                    "runtime_command_not_executed",
                    "llm_judge_not_executed",
                ],
                "no_runtime_execution": True,
                "auto_matrix_adapter_outputs": bool(auto_matrix_adapter_outputs),
                "tags": [CONTROLLED_SINGLE_TRIAL_TAG, *clean_tags],
            }
        )
    except FirstRunPacketError as exc:
        return _invalid_result(
            str(exc),
            run_id=clean_run_id,
            trial_id=clean_trial_id,
            pair_id=clean_pair_id,
            scenario_id=clean_scenario_id,
            packet_dir=packet_dir_text,
        )
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _invalid_result(
            _safe_error_code(exc),
            run_id=clean_run_id,
            trial_id=clean_trial_id,
            pair_id=clean_pair_id,
            scenario_id=clean_scenario_id,
            packet_dir=packet_dir_text,
        )


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Prepare an offline first single-trial run packet without executing runtime.",
    )
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--model-catalog", dest="model_catalog_path", required=True)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--local-pipeline-config", dest="local_pipeline_config_path", required=True)
    parser.add_argument("--run-id", required=True)
    parser.add_argument("--trial-id")
    parser.add_argument("--repeat-index", type=int, default=1)
    parser.add_argument("--tag", dest="tags", action="append", default=[])
    parser.add_argument("--entrypoint", default=LOCAL_MODEL_PAIR_ENTRYPOINT_REF)
    parser.add_argument(
        "--no-auto-matrix-adapter-outputs",
        dest="auto_matrix_adapter_outputs",
        action="store_false",
        default=True,
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = build_first_single_trial_run_packet(
        output_dir=args.output_dir,
        model_catalog_path=args.model_catalog_path,
        scenario_id=args.scenario_id,
        pair_id=args.pair_id,
        local_pipeline_config_path=args.local_pipeline_config_path,
        run_id=args.run_id,
        trial_id=args.trial_id,
        repeat_index=args.repeat_index,
        entrypoint=args.entrypoint,
        auto_matrix_adapter_outputs=args.auto_matrix_adapter_outputs,
        tags=tuple(args.tags or ()),
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result.get("status") == "invalid" else 0


def _build_single_trial_plan(
    *,
    catalog: ModelCatalog,
    catalog_path: Path,
    scenario_id: str,
    scenario_path: Path,
    pair_id: str,
    run_id: str,
    trial_id: str | None,
    repeat_index: int,
    tags: tuple[str, ...],
) -> Any:
    scenario_ref = ModelComparisonScenarioRef(
        scenario_id=scenario_id,
        scenario_path=str(scenario_path).replace("\\", "/"),
        tags=[CONTROLLED_SINGLE_TRIAL_TAG, *tags],
    )
    config = ModelComparisonPlanConfig(
        plan_id=f"first_single_trial_{run_id}",
        catalog_path=str(catalog_path).replace("\\", "/"),
        repetitions_per_pair=repeat_index,
        include_self_pairs=True,
        include_role_mismatch_pairs=True,
        tags=[CONTROLLED_SINGLE_TRIAL_TAG, *tags],
        notes=[
            MODEL_COMPARISON_PLAN_NOTE,
            "First single-trial packet artifact only; runtime command was not executed.",
        ],
    )
    plan = build_model_comparison_plan(
        catalog,
        [scenario_ref],
        config,
        project_root=Path("."),
    )
    pairs = [pair for pair in plan.candidate_pairs if pair.get("pair_id") == pair_id]
    if not pairs:
        raise FirstRunPacketError("selected_pair_not_found")
    trials = [
        trial
        for trial in plan.trials
        if trial.pair_id == pair_id
        and trial.scenario_id == scenario_id
        and trial.repeat_index == repeat_index
    ]
    if not trials:
        raise FirstRunPacketError("selected_trial_not_found")

    selected_trial = trials[0]
    selected_trial = selected_trial.model_copy(
        update={
            "trial_id": trial_id or selected_trial.trial_id,
            "tags": sorted({CONTROLLED_SINGLE_TRIAL_TAG, *tags, *selected_trial.tags}),
            "notes": [
                *selected_trial.notes,
                "Prepared for guarded single-trial runtime opt-in.",
            ],
            "warnings": list(selected_trial.warnings),
            "no_runtime_execution": True,
        }
    )
    return plan.model_copy(
        update={
            "candidate_pairs": pairs,
            "trials": [selected_trial],
            "tags": sorted({CONTROLLED_SINGLE_TRIAL_TAG, *tags, *plan.tags}),
            "no_runtime_execution": True,
        }
    )


def _write_model_pair_plan(plan: Any, output_dir: Path) -> Path:
    output_dir.mkdir(parents=True, exist_ok=True)
    path = output_dir / MODEL_PAIR_PLAN_FILENAME
    path.write_text(
        json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return path


def _role_config_resolver():
    def _resolve(context: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "agents": [
                {
                    "agent_id": "orchestrator",
                    "role": "orchestrator",
                    "model_id": context.get("orchestrator_model_id"),
                },
                {
                    "agent_id": "executor",
                    "role": "executor",
                    "model_id": context.get("executor_model_id"),
                },
            ],
            "source": "first_single_trial_run_packet",
        }

    return _resolve


def _scenario_config_resolver(
    *,
    scenario_path_text: str,
    local_pipeline_config: Mapping[str, Any],
):
    def _resolve(context: Mapping[str, Any]) -> dict[str, Any]:
        if not Path(scenario_path_text).exists():
            return {}
        payload: dict[str, Any] = {
            "scenario_id": context.get("scenario_id"),
            "scenario_path": context.get("scenario_path"),
            "source": "local_pipeline_config",
        }
        for key in ("max_group_steps", "max_steps_per_agent", "execute_actions"):
            if key in local_pipeline_config:
                payload[key] = local_pipeline_config[key]
        return payload

    return _resolve


def _model_binding_resolver(catalog: ModelCatalog):
    entries_by_id = {entry.model_id: entry for entry in catalog.models}

    def _resolve(context: Mapping[str, Any]) -> dict[str, Any]:
        orchestrator_id = _safe_optional_text(context.get("orchestrator_model_id"))
        executor_id = _safe_optional_text(context.get("executor_model_id"))
        return {
            "orchestrator": _binding_for_entry(entries_by_id.get(orchestrator_id or "")),
            "executor": _binding_for_entry(entries_by_id.get(executor_id or "")),
        }

    return _resolve


def _binding_for_entry(entry: ModelCatalogEntry | None) -> dict[str, Any]:
    if entry is None:
        return {}
    return {
        "model_id": entry.model_id,
        "provider": "model_catalog",
        "family": entry.family,
        "quantization": entry.quantization,
        "parameter_count_b": entry.parameter_count_b,
    }


def _build_controlled_command(
    *,
    packet_dir: Path,
    plan_path: Path,
    readiness_summary_path: Path,
    local_pipeline_config_path: Path,
    run_id: str,
    trial_id: str,
    entrypoint: str,
    auto_matrix_adapter_outputs: bool,
    tags: tuple[str, ...],
) -> list[str]:
    command = [
        r".\.venv\Scripts\python.exe",
        "scripts/run_single_trial_controlled.py",
        "--plan",
        _relative_path_text(plan_path),
        "--readiness-summary",
        _relative_path_text(readiness_summary_path),
        "--entrypoint",
        entrypoint,
        "--local-pipeline-config",
        _relative_path_text(local_pipeline_config_path),
        "--output-dir",
        f"artifacts/single_trial_runs/{run_id}",
        "--trial-id",
        trial_id,
        "--allow-runtime-execution",
        "--confirm-runtime-execution",
        SINGLE_TRIAL_RUNTIME_CONFIRMATION,
    ]
    if auto_matrix_adapter_outputs:
        command.append("--auto-matrix-adapter-outputs")
    command.extend(["--run-id", run_id, "--tag", CONTROLLED_SINGLE_TRIAL_TAG])
    for tag in tags:
        command.extend(["--tag", tag])
    _ = packet_dir
    return command


def _powershell_script(command: Sequence[str]) -> str:
    lines = [
        "# Generated offline by prepare_first_single_trial_run_packet.py.",
        "# This script starts local runtime only when you run it manually.",
        "# Runtime execution still requires --allow-runtime-execution and the explicit confirmation token.",
    ]
    command_lines = [f"{command[0]} {command[1]}"]
    index = 2
    while index < len(command):
        token = str(command[index])
        next_token = str(command[index + 1]) if index + 1 < len(command) else None
        if token.startswith("--") and next_token is not None and not next_token.startswith("--"):
            command_lines.append(f"  {token} {next_token}")
            index += 2
            continue
        command_lines.append(f"  {token}")
        index += 1
    for index, line in enumerate(command_lines):
        suffix = " `" if index < len(command_lines) - 1 else ""
        lines.append(f"{line}{suffix}")
    return "\n".join(lines) + "\n"


def _command_text(command: Sequence[str]) -> str:
    return " ".join(str(item) for item in command)


def _safe_config_for_packet(config: Mapping[str, Any]) -> dict[str, Any]:
    return _safe_mapping(dict(config))


def _load_json_object(
    path: Path,
    *,
    missing_code: str,
    malformed_code: str,
    object_code: str,
) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise FirstRunPacketError(missing_code) from exc
    except json.JSONDecodeError as exc:
        raise FirstRunPacketError(malformed_code) from exc
    if not isinstance(payload, dict):
        raise FirstRunPacketError(object_code)
    return payload


def _validate_local_pipeline_config_payload(payload: Mapping[str, Any]) -> None:
    if _contains_secret_like_config(payload):
        raise FirstRunPacketError("local_pipeline_config_secret_like")
    for key, value in _path_like_config_values(payload):
        field_name = f"local_pipeline_config_{key}"
        _validated_relative_path(value, field_name=field_name, for_output=key.endswith("dir"))
    if not _safe_optional_text(payload.get("out_dir")):
        raise FirstRunPacketError("local_pipeline_config_out_dir_missing")


def _path_like_config_values(payload: Mapping[str, Any], *, prefix: str = "") -> list[tuple[str, str]]:
    rows: list[tuple[str, str]] = []
    for key, value in payload.items():
        key_text = str(key)
        dotted_key = f"{prefix}.{key_text}" if prefix else key_text
        if isinstance(value, Mapping):
            rows.extend(_path_like_config_values(value, prefix=dotted_key))
            continue
        if isinstance(value, str) and _PATH_LIKE_KEY_RE.search(key_text):
            rows.append((dotted_key.lower(), value))
    return rows


def _validated_relative_path(
    value: str | Path,
    *,
    field_name: str,
    for_output: bool = False,
) -> Path:
    text = _required_text(value, field_name=field_name)
    if "://" in text:
        raise FirstRunPacketError(f"{field_name}_forbidden")
    if re.search(r"\s", text):
        raise FirstRunPacketError(f"{field_name}_contains_whitespace")
    if _is_absolute_path(text):
        raise FirstRunPacketError(f"{field_name}_must_be_relative")
    windows_path = PureWindowsPath(text)
    posix_path = PurePosixPath(text)
    parts = [part.strip() for part in (windows_path.parts if "\\" in text else posix_path.parts) if part.strip()]
    lowered = [part.lower() for part in parts]
    if not parts:
        raise FirstRunPacketError(f"{field_name}_required")
    if ".." in parts:
        raise FirstRunPacketError(f"{field_name}_must_not_traverse")
    if _is_docs_ai_final_path(lowered):
        raise FirstRunPacketError(f"{field_name}_forbidden")
    if for_output and set(lowered) & _FORBIDDEN_OUTPUT_DIR_PARTS:
        raise FirstRunPacketError(f"{field_name}_forbidden")
    if set(lowered) & _FORBIDDEN_READ_PATH_PARTS:
        raise FirstRunPacketError(f"{field_name}_forbidden")
    return Path(text)


def _required_token(value: Any, *, field_name: str) -> str:
    text = _required_text(value, field_name=field_name)
    if not re.match(r"^[A-Za-z0-9_.:-]+$", text):
        raise FirstRunPacketError(f"{field_name}_invalid")
    if _secret_like_text(text) or _is_absolute_path(text):
        raise FirstRunPacketError(f"{field_name}_forbidden")
    return text


def _required_text(value: Any, *, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise FirstRunPacketError(f"{field_name}_required")
    return text


def _validated_repeat_index(value: int) -> int:
    if isinstance(value, bool):
        raise FirstRunPacketError("repeat_index_invalid")
    try:
        repeat = int(value)
    except (TypeError, ValueError) as exc:
        raise FirstRunPacketError("repeat_index_invalid") from exc
    if repeat < 1:
        raise FirstRunPacketError("repeat_index_invalid")
    return repeat


def _validated_entrypoint(value: str) -> str:
    text = _required_text(value, field_name="entrypoint")
    if not _ENTRYPOINT_RE.match(text):
        raise FirstRunPacketError("entrypoint_invalid")
    if ".." in text or _secret_like_text(text):
        raise FirstRunPacketError("entrypoint_forbidden")
    return text


def _clean_tags(value: Sequence[str]) -> tuple[str, ...]:
    cleaned: list[str] = []
    for item in list(value)[:_MAX_LIST_ITEMS]:
        text = _required_token(item, field_name="tag")
        if text != CONTROLLED_SINGLE_TRIAL_TAG and text not in cleaned:
            cleaned.append(text)
    return tuple(cleaned)


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


def _invalid_result(
    error: str,
    *,
    run_id: str | None,
    trial_id: str | None,
    pair_id: str | None,
    scenario_id: str | None,
    packet_dir: str | None,
) -> dict[str, Any]:
    return _safe_mapping(
        {
            "schema_version": FIRST_SINGLE_TRIAL_RUN_PACKET_SCHEMA_VERSION,
            "status": "invalid",
            "run_id": run_id,
            "trial_id": trial_id,
            "pair_id": pair_id,
            "scenario_id": scenario_id,
            "packet_dir": packet_dir,
            "plan_path": None,
            "readiness_summary_path": None,
            "local_pipeline_config_path": None,
            "run_script_path": None,
            "command_path": None,
            "readiness_status": None,
            "warnings": [_safe_text(error)],
            "notes": ["first_single_trial_run_packet_invalid", "runtime_command_not_executed"],
            "no_runtime_execution": True,
            "error": _safe_text(error),
        }
    )


def _relative_path_text(path: str | Path) -> str:
    text = str(path).replace("\\", "/")
    if _is_absolute_path(text):
        return "<absolute_path>"
    return text


def _is_docs_ai_final_path(parts: Sequence[str]) -> bool:
    for index in range(0, max(0, len(parts) - 2)):
        if parts[index] == "docs" and parts[index + 1] == "ai" and parts[index + 2].startswith("final"):
            return True
    return False


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
    url_placeholders: dict[str, str] = {}

    def preserve_url(match: re.Match[str]) -> str:
        placeholder = f"__SAFE_URL_{len(url_placeholders)}__"
        url_placeholders[placeholder] = re.sub(
            r"://[^/\s:@]+:[^/\s@]+@",
            "://<redacted_secret>@",
            match.group(0),
        )
        return placeholder

    text = re.sub(r"[A-Za-z][A-Za-z0-9+.-]*://[^\s\"']+", preserve_url, text)
    text = re.sub(r"[A-Za-z]:[\\/][^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"(?<!\w)/(?:[^\s\"']+/)+[^\s\"']+", "<absolute_path>", text)
    text = re.sub(r"\\\\[^\s\"']+", "<absolute_path>", text)
    if _is_absolute_path(text):
        text = "<absolute_path>"
    for placeholder, url in url_placeholders.items():
        text = text.replace(placeholder, url)
    if len(text) > _MAX_TEXT_CHARS:
        return text[:_MAX_TEXT_CHARS] + "...[truncated]"
    return text


def _redact_secret_text(value: str) -> str:
    return re.sub(
        r"(?i)['\"]?\b(api[_-]?key|token|secret|password|credential|auth)\b['\"]?\s*[:=]\s*['\"]?[^,\s'\"}]+",
        "<redacted_secret>",
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
