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
    validate_model_pair_execution_readiness,
    write_model_pair_execution_readiness_summary,
)
from .model_pair_first_run_packet import (
    LOCAL_MODEL_PAIR_ENTRYPOINT_REF,
    MODEL_PAIR_PLAN_FILENAME,
    SINGLE_TRIAL_RUNTIME_CONFIRMATION,
)


CONTROLLED_MINI_MATRIX_PACKET_SCHEMA_VERSION = "controlled_mini_matrix_packet_v1"
CONTROLLED_MINI_MATRIX_COMMANDS_SCHEMA_VERSION = "controlled_mini_matrix_commands_v1"
CONTROLLED_MINI_MATRIX_TAG = "controlled_mini_matrix"

COMMANDS_JSON_FILENAME = "commands.json"
README_FILENAME = "README.md"
_MAX_LIST_ITEMS = 200
_FORBIDDEN_OUTPUT_DIR_PARTS = {"reports", "experiments"}


class MiniMatrixPacketError(ValueError):
    """Controlled mini-matrix packet error safe to expose through CLI JSON."""


def build_controlled_mini_matrix_packet(
    *,
    output_dir: str | Path,
    base_local_pipeline_config_path: str | Path,
    model_catalog_path: str | Path,
    scenario_id: str,
    pair_id: str,
    run_id_prefix: str,
    repeat_count: int,
    tags: Sequence[str] = (),
    entrypoint: str = LOCAL_MODEL_PAIR_ENTRYPOINT_REF,
) -> dict[str, Any]:
    packet_dir_text = _safe_optional_text(output_dir)
    clean_run_id_prefix = _safe_optional_text(run_id_prefix)
    try:
        packet_dir = _validated_relative_path(output_dir, field_name="output_dir", for_output=True)
        base_config_path = _validated_relative_path(
            base_local_pipeline_config_path,
            field_name="base_local_pipeline_config_path",
        )
        catalog_path = _validated_relative_path(model_catalog_path, field_name="model_catalog_path")
        clean_scenario_id = _required_token(scenario_id, field_name="scenario_id")
        clean_pair_id = _required_token(pair_id, field_name="pair_id")
        clean_run_id_prefix = _required_token(run_id_prefix, field_name="run_id_prefix")
        clean_repeat_count = _validated_repeat_count(repeat_count)
        clean_tags = _clean_tags(tags)
        clean_entrypoint = _validated_entrypoint(entrypoint)

        base_config = _load_json_object(base_config_path, "base_local_pipeline_config")
        scenario_path_text = _required_text(base_config.get("scenario_path"), field_name="base_config_scenario_path")
        scenario_path = _validated_relative_path(scenario_path_text, field_name="scenario_path")
        catalog = load_model_catalog(catalog_path)
        packet_dir.mkdir(parents=True, exist_ok=True)

        plan = _build_mini_matrix_plan(
            catalog=catalog,
            catalog_path=catalog_path,
            scenario_id=clean_scenario_id,
            scenario_path=scenario_path,
            pair_id=clean_pair_id,
            run_id_prefix=clean_run_id_prefix,
            repeat_count=clean_repeat_count,
            tags=clean_tags,
        )
        plan_path = packet_dir / MODEL_PAIR_PLAN_FILENAME
        plan_path.write_text(
            json.dumps(plan.model_dump(mode="json"), ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        plan_payload = plan.model_dump(mode="json")

        readiness_summary = validate_model_pair_execution_readiness(
            plan_payload,
            role_config_resolver=_role_config_resolver(),
            scenario_config_resolver=_scenario_config_resolver(
                scenario_path_text=str(scenario_path).replace("\\", "/"),
                local_pipeline_config=base_config,
            ),
            model_binding_resolver=_model_binding_resolver(catalog),
        )
        readiness_summary_path = write_model_pair_execution_readiness_summary(readiness_summary, packet_dir)

        repeat_packets = []
        for trial in plan_payload["trials"]:
            repeat_index = int(trial["repeat_index"])
            run_id = f"{clean_run_id_prefix}_r{repeat_index}"
            run_output_dir = f"artifacts/single_trial_runs/{run_id}"
            local_config_path = packet_dir / f"local_pipeline_config.r{repeat_index:02d}.json"
            local_config = _local_config_for_repeat(base_config, run_id=run_id, run_output_dir=run_output_dir)
            local_config_path.write_text(
                json.dumps(local_config, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
            runtime_command = _runtime_command(
                plan_path=plan_path,
                readiness_summary_path=readiness_summary_path,
                local_pipeline_config_path=local_config_path,
                output_dir=run_output_dir,
                trial_id=str(trial["trial_id"]),
                run_id=run_id,
                entrypoint=clean_entrypoint,
                tags=clean_tags,
            )
            script_path = packet_dir / f"run_repeat_{repeat_index:02d}.ps1"
            script_path.write_text(_powershell_script(runtime_command), encoding="utf-8")
            repeat_packets.append(
                {
                    "repeat_index": repeat_index,
                    "run_id": run_id,
                    "trial_id": trial["trial_id"],
                    "output_dir": run_output_dir,
                    "local_pipeline_config_path": _relative_path(local_config_path),
                    "run_script_path": _relative_path(script_path),
                    "runtime_command": {
                        "argv": runtime_command,
                        "command": _command_text(runtime_command),
                        "no_runtime_execution": True,
                    },
                    "postprocess_commands": [
                        _office_artifact_summary_command(run_output_dir),
                    ],
                }
            )

        commands_payload = {
            "schema_version": CONTROLLED_MINI_MATRIX_COMMANDS_SCHEMA_VERSION,
            "packet_dir": _relative_path(packet_dir),
            "plan_path": _relative_path(plan_path),
            "readiness_summary_path": _relative_path(readiness_summary_path),
            "repeats": repeat_packets,
            "aggregate_command": _aggregate_command(
                run_output_dirs=[row["output_dir"] for row in repeat_packets],
                run_id_prefix=clean_run_id_prefix,
                repeat_count=clean_repeat_count,
            ),
            "notes": [
                "Prepared commands only; packet builder does not execute runtime.",
                "Run each repeat manually after starting endpoints.",
                "Run postprocess commands after each completed repeat.",
            ],
            "no_runtime_execution": True,
        }
        commands_path = packet_dir / COMMANDS_JSON_FILENAME
        commands_path.write_text(
            json.dumps(commands_payload, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        readme_path = packet_dir / README_FILENAME
        readme_path.write_text(_readme(commands_payload), encoding="utf-8")

        readiness_status = _safe_optional_text(readiness_summary.get("status")) or "not_ready"
        status = "ready" if readiness_status == "ready" else "not_ready"
        warnings = _string_list(readiness_summary.get("warnings"))
        if status != "ready":
            warnings.append("readiness_not_ready")
        return _safe_mapping(
            {
                "schema_version": CONTROLLED_MINI_MATRIX_PACKET_SCHEMA_VERSION,
                "status": status,
                "packet_dir": _relative_path(packet_dir),
                "plan_path": _relative_path(plan_path),
                "readiness_summary_path": _relative_path(readiness_summary_path),
                "commands_path": _relative_path(commands_path),
                "readme_path": _relative_path(readme_path),
                "run_id_prefix": clean_run_id_prefix,
                "repeat_count": clean_repeat_count,
                "run_ids": [row["run_id"] for row in repeat_packets],
                "output_dirs": [row["output_dir"] for row in repeat_packets],
                "trial_ids": [row["trial_id"] for row in repeat_packets],
                "readiness_status": readiness_status,
                "warnings": sorted(set(warnings)),
                "notes": ["controlled_mini_matrix_packet_prepared_offline", "runtime_commands_not_executed"],
                "tags": [CONTROLLED_MINI_MATRIX_TAG, *clean_tags],
                "no_runtime_execution": True,
            }
        )
    except MiniMatrixPacketError as exc:
        return _invalid_result(str(exc), packet_dir=packet_dir_text, run_id_prefix=clean_run_id_prefix)
    except (OSError, TypeError, ValueError, json.JSONDecodeError) as exc:
        return _invalid_result(_safe_error_code(exc), packet_dir=packet_dir_text, run_id_prefix=clean_run_id_prefix)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Prepare a no-runtime controlled mini-matrix packet.")
    parser.add_argument("--output-dir", required=True)
    parser.add_argument("--base-local-pipeline-config", dest="base_local_pipeline_config_path", required=True)
    parser.add_argument("--model-catalog", dest="model_catalog_path", required=True)
    parser.add_argument("--scenario-id", required=True)
    parser.add_argument("--pair-id", required=True)
    parser.add_argument("--run-id-prefix", required=True)
    parser.add_argument("--repeat-count", type=int, required=True)
    parser.add_argument("--tag", dest="tags", action="append", default=[])
    parser.add_argument("--entrypoint", default=LOCAL_MODEL_PAIR_ENTRYPOINT_REF)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    result = build_controlled_mini_matrix_packet(
        output_dir=args.output_dir,
        base_local_pipeline_config_path=args.base_local_pipeline_config_path,
        model_catalog_path=args.model_catalog_path,
        scenario_id=args.scenario_id,
        pair_id=args.pair_id,
        run_id_prefix=args.run_id_prefix,
        repeat_count=args.repeat_count,
        tags=tuple(args.tags or ()),
        entrypoint=args.entrypoint,
    )
    print(json.dumps(result, ensure_ascii=False, sort_keys=True))
    return 2 if result.get("status") == "invalid" else 0


def _build_mini_matrix_plan(
    *,
    catalog: ModelCatalog,
    catalog_path: Path,
    scenario_id: str,
    scenario_path: Path,
    pair_id: str,
    run_id_prefix: str,
    repeat_count: int,
    tags: tuple[str, ...],
) -> Any:
    scenario_ref = ModelComparisonScenarioRef(
        scenario_id=scenario_id,
        scenario_path=str(scenario_path).replace("\\", "/"),
        tags=[CONTROLLED_MINI_MATRIX_TAG, *tags],
    )
    config = ModelComparisonPlanConfig(
        plan_id=f"controlled_mini_matrix_{run_id_prefix}_r{repeat_count}",
        catalog_path=str(catalog_path).replace("\\", "/"),
        repetitions_per_pair=repeat_count,
        include_self_pairs=True,
        include_role_mismatch_pairs=True,
        tags=[CONTROLLED_MINI_MATRIX_TAG, *tags],
        notes=[
            MODEL_COMPARISON_PLAN_NOTE,
            "Controlled mini-matrix packet artifact only; runtime commands were not executed.",
        ],
    )
    plan = build_model_comparison_plan(catalog, [scenario_ref], config, project_root=Path("."))
    pairs = [pair for pair in plan.candidate_pairs if pair.get("pair_id") == pair_id]
    if not pairs:
        raise MiniMatrixPacketError("selected_pair_not_found")
    trials = [
        trial.model_copy(
            update={
                "tags": sorted({CONTROLLED_MINI_MATRIX_TAG, *tags, *trial.tags}),
                "notes": [*trial.notes, "Prepared for guarded mini-matrix repeat runtime opt-in."],
                "no_runtime_execution": True,
            }
        )
        for trial in plan.trials
        if trial.pair_id == pair_id and trial.scenario_id == scenario_id
    ]
    trials = sorted(trials, key=lambda trial: trial.repeat_index)
    if len(trials) != repeat_count:
        raise MiniMatrixPacketError("selected_repeat_count_mismatch")
    return plan.model_copy(
        update={
            "candidate_pairs": pairs,
            "trials": trials,
            "tags": sorted({CONTROLLED_MINI_MATRIX_TAG, *tags, *plan.tags}),
            "no_runtime_execution": True,
        }
    )


def _local_config_for_repeat(base_config: Mapping[str, Any], *, run_id: str, run_output_dir: str) -> dict[str, Any]:
    config = json.loads(json.dumps(dict(base_config)))
    pipeline_dir = f"{run_output_dir}/pipeline"
    workspace_dir = f"{pipeline_dir}/workspace"
    config["run_id"] = run_id
    config["out_dir"] = pipeline_dir
    action_repair = dict(config.get("action_parameter_repair") or {})
    action_repair["enabled"] = True
    action_repair["create_missing_docx_for_append"] = True
    action_repair["office_default_output_dir"] = f"{workspace_dir}/office_outputs"
    config["action_parameter_repair"] = action_repair
    config["office_real_document_enabled"] = True
    config["office_real_document_artifact_root"] = workspace_dir
    notes = _string_list(config.get("notes"))
    notes.append(f"Controlled mini-matrix repeat config for {run_id}.")
    config["notes"] = list(dict.fromkeys(notes))
    _validate_local_config_repeat_paths(config, run_output_dir=run_output_dir)
    return _safe_mapping(config)


def _validate_local_config_repeat_paths(config: Mapping[str, Any], *, run_output_dir: str) -> None:
    expected_pipeline_dir = f"{run_output_dir}/pipeline"
    if config.get("out_dir") != expected_pipeline_dir:
        raise MiniMatrixPacketError("local_config_out_dir_mismatch")
    repair = config.get("action_parameter_repair")
    if not isinstance(repair, Mapping):
        raise MiniMatrixPacketError("local_config_action_parameter_repair_missing")
    expected_office_dir = f"{expected_pipeline_dir}/workspace/office_outputs"
    if repair.get("office_default_output_dir") != expected_office_dir:
        raise MiniMatrixPacketError("local_config_office_default_output_dir_mismatch")
    expected_artifact_root = f"{expected_pipeline_dir}/workspace"
    if config.get("office_real_document_artifact_root") != expected_artifact_root:
        raise MiniMatrixPacketError("local_config_office_artifact_root_mismatch")


def _runtime_command(
    *,
    plan_path: Path,
    readiness_summary_path: Path,
    local_pipeline_config_path: Path,
    output_dir: str,
    trial_id: str,
    run_id: str,
    entrypoint: str,
    tags: tuple[str, ...],
) -> list[str]:
    command = [
        r".\.venv\Scripts\python.exe",
        "scripts/run_single_trial_controlled.py",
        "--plan",
        _relative_path(plan_path),
        "--readiness-summary",
        _relative_path(readiness_summary_path),
        "--entrypoint",
        entrypoint,
        "--local-pipeline-config",
        _relative_path(local_pipeline_config_path),
        "--output-dir",
        output_dir,
        "--trial-id",
        trial_id,
        "--allow-runtime-execution",
        "--confirm-runtime-execution",
        SINGLE_TRIAL_RUNTIME_CONFIRMATION,
        "--auto-matrix-adapter-outputs",
        "--run-id",
        run_id,
        "--tag",
        CONTROLLED_MINI_MATRIX_TAG,
    ]
    for tag in tags:
        command.extend(["--tag", tag])
    return command


def _office_artifact_summary_command(run_output_dir: str) -> dict[str, Any]:
    command = [
        r".\.venv\Scripts\python.exe",
        "scripts/summarize_office_execution_artifacts.py",
        "--trial-result",
        f"{run_output_dir}/model_pair_single_trial_result.json",
        "--output",
        f"{run_output_dir}/office_execution_artifact_summary.json",
    ]
    return {
        "name": "office_execution_artifact_summary",
        "argv": command,
        "command": _command_text(command),
        "no_runtime_execution": True,
    }


def _aggregate_command(*, run_output_dirs: list[str], run_id_prefix: str, repeat_count: int) -> dict[str, Any]:
    output_dir = f"artifacts/mini_matrix_summaries/{run_id_prefix}_r{repeat_count}"
    command = [
        r".\.venv\Scripts\python.exe",
        "scripts/aggregate_mini_matrix_results.py",
        "--output-dir",
        output_dir,
        "--summary-id",
        f"{run_id_prefix}_r{repeat_count}",
    ]
    for run_output_dir in run_output_dirs:
        command.extend(["--run-output-dir", run_output_dir])
    return {
        "name": "aggregate_mini_matrix_results",
        "argv": command,
        "command": _command_text(command),
        "output_dir": output_dir,
        "no_runtime_execution": True,
    }


def _role_config_resolver():
    def _resolve(context: Mapping[str, Any]) -> dict[str, Any]:
        return {
            "agents": [
                {"agent_id": "orchestrator", "role": "orchestrator", "model_id": context.get("orchestrator_model_id")},
                {"agent_id": "executor", "role": "executor", "model_id": context.get("executor_model_id")},
            ],
            "source": "controlled_mini_matrix_packet",
        }

    return _resolve


def _scenario_config_resolver(*, scenario_path_text: str, local_pipeline_config: Mapping[str, Any]):
    def _resolve(context: Mapping[str, Any]) -> dict[str, Any]:
        if not Path(scenario_path_text).exists():
            return {}
        payload: dict[str, Any] = {
            "scenario_id": context.get("scenario_id"),
            "scenario_path": context.get("scenario_path"),
            "source": "base_local_pipeline_config",
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


def _powershell_script(command: Sequence[str]) -> str:
    lines = [
        "# Generated offline by prepare_controlled_mini_matrix_packet.py.",
        "# This script does not start servers; start endpoints manually before running.",
        "# Runtime execution still requires the explicit confirmation token.",
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


def _readme(commands_payload: Mapping[str, Any]) -> str:
    lines = [
        "# Phase 8.26 Controlled Mini-Matrix Packet",
        "",
        "This packet contains prepared commands only. It does not execute models, servers, Office, or HTTP clients.",
        "",
        "Run repeats manually in order after starting both local endpoints:",
    ]
    for repeat in commands_payload.get("repeats", []):
        if not isinstance(repeat, Mapping):
            continue
        lines.append(f"- repeat {repeat.get('repeat_index')}: `{repeat.get('run_script_path')}`")
    lines.extend(
        [
            "",
            "After each repeat, run its postprocess command from `commands.json`.",
            "After all repeats, run the aggregate command from `commands.json`.",
            "",
        ]
    )
    return "\n".join(lines)


def _load_json_object(path: Path, label: str) -> dict[str, Any]:
    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MiniMatrixPacketError(f"{label}_file_missing") from exc
    except json.JSONDecodeError as exc:
        raise MiniMatrixPacketError(f"{label}_json_malformed") from exc
    if not isinstance(payload, dict):
        raise MiniMatrixPacketError(f"{label}_payload_not_object")
    return payload


def _validated_relative_path(value: str | Path, *, field_name: str, for_output: bool = False) -> Path:
    text = _required_text(value, field_name=field_name)
    if "://" in text or re.search(r"\s", text) or _is_absolute_path(text):
        raise MiniMatrixPacketError(f"{field_name}_forbidden")
    parts = [part for part in PurePosixPath(text.replace("\\", "/")).parts if part]
    lowered = [part.lower() for part in parts]
    if not parts or ".." in parts:
        raise MiniMatrixPacketError(f"{field_name}_forbidden")
    if for_output and set(lowered) & _FORBIDDEN_OUTPUT_DIR_PARTS:
        raise MiniMatrixPacketError(f"{field_name}_forbidden")
    return Path(text)


def _validated_repeat_count(value: int) -> int:
    if isinstance(value, bool):
        raise MiniMatrixPacketError("repeat_count_invalid")
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise MiniMatrixPacketError("repeat_count_invalid") from exc
    if parsed < 1 or parsed > 20:
        raise MiniMatrixPacketError("repeat_count_invalid")
    return parsed


def _validated_entrypoint(value: str) -> str:
    text = _required_text(value, field_name="entrypoint")
    if not re.fullmatch(r"[A-Za-z_][A-Za-z0-9_.]*:[A-Za-z_][A-Za-z0-9_]*", text):
        raise MiniMatrixPacketError("entrypoint_invalid")
    return text


def _required_token(value: Any, *, field_name: str) -> str:
    text = _required_text(value, field_name=field_name)
    if not re.fullmatch(r"[A-Za-z0-9_.:-]+", text):
        raise MiniMatrixPacketError(f"{field_name}_invalid")
    return text


def _required_text(value: Any, *, field_name: str) -> str:
    text = str(value).strip() if value is not None else ""
    if not text:
        raise MiniMatrixPacketError(f"{field_name}_required")
    return text


def _clean_tags(value: Sequence[str]) -> tuple[str, ...]:
    cleaned: list[str] = []
    for item in list(value)[:_MAX_LIST_ITEMS]:
        text = _required_token(item, field_name="tag")
        if text != CONTROLLED_MINI_MATRIX_TAG and text not in cleaned:
            cleaned.append(text)
    return tuple(cleaned)


def _command_text(command: Sequence[str]) -> str:
    return " ".join(str(item) for item in command)


def _relative_path(path: str | Path) -> str:
    text = str(path).replace("\\", "/")
    return "<absolute_path>" if _is_absolute_path(text) else text


def _safe_mapping(value: Mapping[str, Any]) -> dict[str, Any]:
    return {str(key): _safe_value(item) for key, item in value.items()}


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
        return value.replace("\\", "/") if not _is_absolute_path(value) else "<absolute_path>"
    return value


def _safe_optional_text(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, str):
        return [value]
    if isinstance(value, list | tuple | set):
        return [str(item) for item in value if item is not None]
    return [str(value)]


def _is_absolute_path(value: str) -> bool:
    return PureWindowsPath(value).is_absolute() or PurePosixPath(value).is_absolute() or bool(re.match(r"^[A-Za-z]:", value))


def _safe_error_code(exc: Exception) -> str:
    text = str(exc).strip()
    if not text or _is_absolute_path(text):
        return exc.__class__.__name__
    return text[:120]


def _invalid_result(error: str, *, packet_dir: str | None, run_id_prefix: str | None) -> dict[str, Any]:
    return {
        "schema_version": CONTROLLED_MINI_MATRIX_PACKET_SCHEMA_VERSION,
        "status": "invalid",
        "packet_dir": packet_dir,
        "run_id_prefix": run_id_prefix,
        "warnings": [error],
        "notes": ["controlled_mini_matrix_packet_invalid", "runtime_commands_not_executed"],
        "no_runtime_execution": True,
        "error": error,
    }


if __name__ == "__main__":
    raise SystemExit(main())
