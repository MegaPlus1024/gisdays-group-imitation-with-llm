from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .autonomous_browser_model_comparison_packet import (
    _build_hard_approval_policy_match_prompt_text,
    _build_hard_policy_disambiguation_prompt_text,
    _build_hard_ticket_priority_crosscheck_prompt_text,
)


PACKET_SCHEMA_VERSION = "autonomous_browser_model_variance_packet_v1"
PACKET_CONFIG_SCHEMA_VERSION = "autonomous_browser_model_variance_packet_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_model_variance_packet_summary_v1"
EVALUATOR_CONFIG_SCHEMA_VERSION = "autonomous_browser_model_variance_evaluator_config_v1"
DEFAULT_PACKET_ID = "browser_model_variance_packet_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_variance_packet"
DEFAULT_EVALUATION_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_variance_packet/evaluation_runs"
DEFAULT_VARIANCE_CONFIG_PATH = "artifacts/autonomous_runtime_summaries/model_variance_packet/variance_config.local.json"
DEFAULT_MODEL_SPECS = (
    {"alias": "second_model", "model_path": "models/gguf/second_model.gguf"},
    {
        "alias": "third_model",
        "model_path": "models/gguf/third_model.gguf",
        "prompt_prefix": "/no_think",
    },
)
DEFAULT_SCENARIO_SPECS = (
    {
        "scenario_id": "hard_policy_disambiguation",
        "scenario_label": "hard_policy_disambiguation",
        "prompt_filename": "planner_prompt.compact.txt",
        "max_tokens": 1200,
    },
    {
        "scenario_id": "hard_ticket_priority_crosscheck",
        "scenario_label": "hard_ticket_priority_crosscheck",
        "prompt_filename": "planner_prompt.compact.txt",
        "max_tokens": 1200,
    },
    {
        "scenario_id": "hard_approval_policy_match",
        "scenario_label": "hard_approval_policy_match",
        "prompt_filename": "planner_prompt.compact.txt",
        "max_tokens": 1200,
    },
)
DEFAULT_TRIAL_COUNT = 3
DEFAULT_TRIAL_IDS = tuple(f"trial_{index:02d}" for index in range(1, DEFAULT_TRIAL_COUNT + 1))


@dataclass(frozen=True)
class AutonomousBrowserModelVariancePacketSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    model_execution: bool
    real_browser_execution: bool
    packet_id: str | None
    output_dir: str | None
    evaluation_output_dir: str | None
    models_total: int
    scenarios_total: int
    trial_count: int
    trials_total: int
    model_aliases: tuple[str, ...] = ()
    scenario_ids: tuple[str, ...] = ()
    trial_ids: tuple[str, ...] = ()
    packet_files: tuple[str, ...] = ()
    request_paths_path: str | None = None
    output_paths_path: str | None = None
    trial_records_path: str | None = None
    variance_config_path: str | None = None
    expected_raw_output_paths: tuple[str, ...] = ()
    commands_count: int = 0
    execution_status: str = "skipped_by_design"
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "packet_id": self.packet_id,
            "output_dir": self.output_dir,
            "evaluation_output_dir": self.evaluation_output_dir,
            "models_total": self.models_total,
            "scenarios_total": self.scenarios_total,
            "trial_count": self.trial_count,
            "trials_total": self.trials_total,
            "model_aliases": list(self.model_aliases),
            "scenario_ids": list(self.scenario_ids),
            "trial_ids": list(self.trial_ids),
            "packet_files": list(self.packet_files),
            "request_paths_path": self.request_paths_path,
            "output_paths_path": self.output_paths_path,
            "trial_records_path": self.trial_records_path,
            "variance_config_path": self.variance_config_path,
            "expected_raw_output_paths": list(self.expected_raw_output_paths),
            "commands_count": self.commands_count,
            "execution_status": self.execution_status,
            "limitations": list(self.limitations),
        }


def build_autonomous_browser_model_variance_packet(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    config_result = _load_config(config_artifact)
    if config_result["status"] != "ok":
        return _failure_summary(
            packet_id=config_result.get("packet_id"),
            output_dir=config_result.get("output_dir"),
            evaluation_output_dir=config_result.get("evaluation_output_dir"),
            error_code=str(config_result.get("error_code") or "config_validation_failed"),
            limitations=tuple(config_result.get("limitations") or _limitations()),
        )

    packet_id = str(config_result["packet_id"])
    output_dir = str(config_result["output_dir"])
    evaluation_output_dir = str(config_result["evaluation_output_dir"])
    model_specs = tuple(config_result["model_specs"])
    scenario_specs = tuple(config_result["scenario_specs"])
    trial_ids = tuple(config_result["trial_ids"])
    limitations = tuple(config_result.get("limitations") or _limitations())

    packet_dir = repo / output_dir
    packet_dir.mkdir(parents=True, exist_ok=True)

    packet_files: list[str] = []
    prompt_paths: dict[str, str] = {}
    request_paths: dict[str, dict[str, dict[str, str]]] = {}
    output_paths: dict[str, dict[str, dict[str, str]]] = {}
    trial_records: list[dict[str, Any]] = []
    model_aliases: list[str] = []
    scenario_ids: list[str] = []
    expected_raw_output_paths: list[str] = []

    for scenario_spec in scenario_specs:
        scenario_id = str(scenario_spec["scenario_id"])
        scenario_label = str(scenario_spec["scenario_label"])
        prompt_filename = str(scenario_spec["prompt_filename"])
        prompt_text = _build_prompt_text(scenario_id)
        prompt_path = packet_dir / "prompts" / scenario_label / prompt_filename
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        _write_text(prompt_path, prompt_text + "\n")
        prompt_relative_path = f"{output_dir}/prompts/{scenario_label}/{prompt_filename}"
        prompt_paths[scenario_label] = prompt_relative_path
        packet_files.append(prompt_relative_path)
        scenario_ids.append(scenario_id)

    for model_spec in model_specs:
        model_alias = str(model_spec["alias"])
        model_path = str(model_spec["model_path"])
        model_aliases.append(model_alias)
        request_paths[model_alias] = {}
        output_paths[model_alias] = {}
        for scenario_spec in scenario_specs:
            scenario_id = str(scenario_spec["scenario_id"])
            scenario_label = str(scenario_spec["scenario_label"])
            prompt_filename = str(scenario_spec["prompt_filename"])
            prompt_relative_path = prompt_paths[scenario_label]
            request_paths[model_alias][scenario_label] = {}
            output_paths[model_alias][scenario_label] = {}
            for trial_index, trial_id in enumerate(trial_ids, start=1):
                trial_dir = packet_dir / model_alias / scenario_label / trial_id
                trial_dir.mkdir(parents=True, exist_ok=True)
                request_path = trial_dir / "request.json"
                raw_output_path = trial_dir / "raw_planner_output.txt"
                response_path = trial_dir / "response.json"
                request_payload = _build_request_payload(
                    packet_id=packet_id,
                    model_alias=model_alias,
                    model_path=model_path,
                    prompt_prefix=str(model_spec.get("prompt_prefix")) if model_spec.get("prompt_prefix") else None,
                    scenario_id=scenario_id,
                    scenario_label=scenario_label,
                    trial_id=trial_id,
                    trial_index=trial_index,
                    prompt_filename=prompt_filename,
                    prompt_path=prompt_relative_path,
                    request_path=f"{output_dir}/{model_alias}/{scenario_label}/{trial_id}/request.json",
                    raw_output_path=f"{output_dir}/{model_alias}/{scenario_label}/{trial_id}/raw_planner_output.txt",
                    response_path=f"{output_dir}/{model_alias}/{scenario_label}/{trial_id}/response.json",
                    max_tokens=int(scenario_spec["max_tokens"]),
                    prompt_text=_build_prompt_text(scenario_id),
                )
                _write_json(request_path, request_payload)
                request_relative_path = f"{output_dir}/{model_alias}/{scenario_label}/{trial_id}/request.json"
                raw_output_relative_path = f"{output_dir}/{model_alias}/{scenario_label}/{trial_id}/raw_planner_output.txt"
                response_relative_path = f"{output_dir}/{model_alias}/{scenario_label}/{trial_id}/response.json"
                request_paths[model_alias][scenario_label][trial_id] = request_relative_path
                output_paths[model_alias][scenario_label][trial_id] = raw_output_relative_path
                trial_records.append(
                    {
                        "model_alias": model_alias,
                        "model_path": model_path,
                        "scenario_id": scenario_id,
                        "scenario_label": scenario_label,
                        "trial_id": trial_id,
                        "trial_index": trial_index,
                        "request_path": request_relative_path,
                        "output_path": raw_output_relative_path,
                        "response_metadata_path": response_relative_path,
                    }
                )
                expected_raw_output_paths.append(raw_output_relative_path)
                packet_files.extend([request_relative_path, raw_output_relative_path, response_relative_path])

    request_paths_path = packet_dir / "request_paths.json"
    _write_json(request_paths_path, request_paths)
    packet_files.append(f"{output_dir}/request_paths.json")

    output_paths_path = packet_dir / "output_paths.json"
    _write_json(output_paths_path, output_paths)
    packet_files.append(f"{output_dir}/output_paths.json")

    trial_records_path = packet_dir / "trial_records.json"
    _write_json(trial_records_path, trial_records)
    packet_files.append(f"{output_dir}/trial_records.json")

    variance_config = _build_variance_config(
        packet_id=packet_id,
        output_dir=output_dir,
        evaluation_output_dir=evaluation_output_dir,
        model_specs=model_specs,
        scenario_specs=scenario_specs,
        trial_ids=trial_ids,
        trial_records=trial_records,
        limitations=limitations,
    )
    variance_config_path = packet_dir / "variance_config.local.json"
    _write_json(variance_config_path, variance_config)
    packet_files.append(f"{output_dir}/variance_config.local.json")

    commands = _build_commands(
        output_dir=output_dir,
        model_specs=model_specs,
        scenario_specs=scenario_specs,
        trial_ids=trial_ids,
        evaluation_output_dir=evaluation_output_dir,
        variance_config_path=f"{output_dir}/variance_config.local.json",
    )
    _write_json(packet_dir / "commands.json", {"commands": commands})
    packet_files.append(f"{output_dir}/commands.json")

    commands_md = _build_commands_markdown(
        output_dir=output_dir,
        model_specs=model_specs,
        scenario_specs=scenario_specs,
        trial_ids=trial_ids,
        evaluation_output_dir=evaluation_output_dir,
    )
    _write_text(packet_dir / "commands.md", commands_md)
    packet_files.append(f"{output_dir}/commands.md")

    readme_text = _build_readme(
        packet_id=packet_id,
        output_dir=output_dir,
        evaluation_output_dir=evaluation_output_dir,
        model_specs=model_specs,
        scenario_specs=scenario_specs,
        trial_ids=trial_ids,
        request_paths=request_paths,
        output_paths=output_paths,
    )
    _write_text(packet_dir / "README.md", readme_text)
    packet_files.append(f"{output_dir}/README.md")

    packet_json = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "packet_id": packet_id,
        "output_dir": output_dir,
        "evaluation_output_dir": evaluation_output_dir,
        "model_specs": _jsonable(list(model_specs)),
        "scenario_specs": _jsonable(list(scenario_specs)),
        "trial_ids": list(trial_ids),
        "trial_records": _jsonable(trial_records),
        "request_paths_path": f"{output_dir}/request_paths.json",
        "output_paths_path": f"{output_dir}/output_paths.json",
        "trial_records_path": f"{output_dir}/trial_records.json",
        "variance_config_path": f"{output_dir}/variance_config.local.json",
        "limitations": list(limitations),
    }
    _write_json(packet_dir / "autonomous_browser_model_variance_packet.json", packet_json)
    packet_files.append(f"{output_dir}/autonomous_browser_model_variance_packet.json")

    summary_relative_path = f"{output_dir}/autonomous_browser_model_variance_packet_summary.json"
    packet_files.append(summary_relative_path)
    summary = AutonomousBrowserModelVariancePacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="succeeded",
        error_code=None,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        packet_id=packet_id,
        output_dir=output_dir,
        evaluation_output_dir=evaluation_output_dir,
        models_total=len(model_specs),
        scenarios_total=len(scenario_specs),
        trial_count=len(trial_ids),
        trials_total=len(trial_records),
        model_aliases=tuple(model_aliases),
        scenario_ids=tuple(scenario_ids),
        trial_ids=tuple(trial_ids),
        packet_files=tuple(packet_files),
        request_paths_path=f"{output_dir}/request_paths.json",
        output_paths_path=f"{output_dir}/output_paths.json",
        trial_records_path=f"{output_dir}/trial_records.json",
        variance_config_path=f"{output_dir}/variance_config.local.json",
        expected_raw_output_paths=tuple(expected_raw_output_paths),
        commands_count=len(commands),
        execution_status="skipped_by_design",
        limitations=limitations,
    )
    summary_payload = summary.to_dict()
    _write_json(packet_dir / "autonomous_browser_model_variance_packet_summary.json", summary_payload)
    return summary_payload


def write_autonomous_browser_model_variance_packet_summary(summary: Mapping[str, Any], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_model_variance_packet_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _load_config(config_artifact: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config_artifact, Mapping):
        payload = dict(config_artifact)
    else:
        try:
            payload = json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "packet_id": None,
                "output_dir": None,
                "evaluation_output_dir": None,
                "limitations": _limitations(),
            }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": None,
            "output_dir": None,
            "evaluation_output_dir": None,
            "limitations": _limitations(),
        }
    if str(payload.get("schema_version", "")) != PACKET_CONFIG_SCHEMA_VERSION:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": _safe_text(payload.get("packet_id", DEFAULT_PACKET_ID)),
            "output_dir": _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR)),
            "evaluation_output_dir": _safe_relative_path(
                payload.get("evaluation_output_dir", DEFAULT_EVALUATION_OUTPUT_DIR)
            ),
            "limitations": _limitations(),
        }

    packet_id = _safe_identifier(payload.get("packet_id", DEFAULT_PACKET_ID), "packet_id")
    output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR))
    evaluation_output_dir = _safe_relative_path(
        payload.get("evaluation_output_dir", DEFAULT_EVALUATION_OUTPUT_DIR)
    )
    variance_config_path = _safe_relative_path(
        payload.get("variance_config_path", DEFAULT_VARIANCE_CONFIG_PATH)
    )
    model_specs = _safe_model_specs(payload.get("model_specs", DEFAULT_MODEL_SPECS))
    scenario_specs = _safe_scenario_specs(payload.get("scenario_specs", DEFAULT_SCENARIO_SPECS))
    trial_ids = _safe_trial_ids(payload.get("trial_ids", DEFAULT_TRIAL_IDS))
    no_runtime_execution = payload.get("no_runtime_execution") is True

    if (
        packet_id is None
        or output_dir is None
        or evaluation_output_dir is None
        or variance_config_path is None
        or model_specs is None
        or scenario_specs is None
        or trial_ids is None
        or not no_runtime_execution
    ):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "evaluation_output_dir": evaluation_output_dir,
            "limitations": _limitations(),
        }
    if len(model_specs) != len(DEFAULT_MODEL_SPECS):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "evaluation_output_dir": evaluation_output_dir,
            "limitations": _limitations(),
        }
    if tuple(item["alias"] for item in model_specs) != tuple(item["alias"] for item in DEFAULT_MODEL_SPECS):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "evaluation_output_dir": evaluation_output_dir,
            "limitations": _limitations(),
        }
    if tuple(item["scenario_id"] for item in scenario_specs) != tuple(item["scenario_id"] for item in DEFAULT_SCENARIO_SPECS):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "evaluation_output_dir": evaluation_output_dir,
            "limitations": _limitations(),
        }
    if tuple(trial_ids) != DEFAULT_TRIAL_IDS:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "evaluation_output_dir": evaluation_output_dir,
            "limitations": _limitations(),
        }

    return {
        "status": "ok",
        "packet_id": packet_id,
        "output_dir": output_dir,
        "evaluation_output_dir": evaluation_output_dir,
        "variance_config_path": variance_config_path,
        "model_specs": tuple(model_specs),
        "scenario_specs": tuple(scenario_specs),
        "trial_ids": tuple(trial_ids),
        "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
    }


def _build_request_payload(
    *,
    packet_id: str,
    model_alias: str,
    model_path: str,
    prompt_prefix: str | None,
    scenario_id: str,
    scenario_label: str,
    trial_id: str,
    trial_index: int,
    prompt_filename: str,
    prompt_path: str,
    request_path: str,
    raw_output_path: str,
    response_path: str,
    max_tokens: int,
    prompt_text: str,
) -> dict[str, Any]:
    return {
        "model": model_alias,
        "messages": [
            {"role": "system", "content": "Return only valid JSON. No markdown. No explanation. No code fences."},
            {"role": "user", "content": _build_user_prompt(prompt_text, prompt_prefix)},
        ],
        "temperature": 0,
        "max_tokens": max_tokens,
        "stream": False,
        "metadata": {
            "packet_id": packet_id,
            "model_alias": model_alias,
            "model_path_expected": model_path,
            "scenario_id": scenario_id,
            "scenario_label": scenario_label,
            "trial_id": trial_id,
            "trial_index": trial_index,
            "prompt_filename": prompt_filename,
            "prompt_path": prompt_path,
            "request_path": request_path,
            "expected_raw_output_path": raw_output_path,
            "response_metadata_path": response_path,
        },
    }


def _build_variance_config(
    *,
    packet_id: str,
    output_dir: str,
    evaluation_output_dir: str,
    model_specs: tuple[dict[str, str], ...],
    scenario_specs: tuple[dict[str, Any], ...],
    trial_ids: tuple[str, ...],
    trial_records: list[dict[str, Any]],
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": EVALUATOR_CONFIG_SCHEMA_VERSION,
        "packet_id": packet_id,
        "output_dir": evaluation_output_dir,
        "packet_output_dir": output_dir,
        "replay_mode": "dry_run",
        "no_runtime_execution": True,
        "models": [
            {
                "alias": spec["alias"],
                "model_path": spec["model_path"],
                **({"prompt_prefix": spec["prompt_prefix"]} if "prompt_prefix" in spec else {}),
            }
            for spec in model_specs
        ],
        "scenarios": [
            {
                "scenario_id": spec["scenario_id"],
                "scenario_label": spec["scenario_label"],
                "prompt_filename": spec["prompt_filename"],
                "max_tokens": spec["max_tokens"],
            }
            for spec in scenario_specs
        ],
        "trial_ids": list(trial_ids),
        "trial_records": trial_records,
        "captured_outputs": [item["output_path"] for item in trial_records],
        "request_paths": _paths_by_model_scenario_trial(trial_records, "request_path"),
        "output_paths": _paths_by_model_scenario_trial(trial_records, "output_path"),
        "response_metadata_paths": _paths_by_model_scenario_trial(trial_records, "response_metadata_path"),
        "limitations": list(limitations),
    }


def _paths_by_model_scenario_trial(records: list[dict[str, Any]], key: str) -> dict[str, dict[str, dict[str, str]]]:
    nested: dict[str, dict[str, dict[str, str]]] = {}
    for record in records:
        model_alias = str(record["model_alias"])
        scenario_id = str(record["scenario_id"])
        trial_id = str(record["trial_id"])
        nested.setdefault(model_alias, {}).setdefault(scenario_id, {})[trial_id] = str(record[key])
    return nested


def _build_commands(
    *,
    output_dir: str,
    model_specs: tuple[dict[str, str], ...],
    scenario_specs: tuple[dict[str, Any], ...],
    trial_ids: tuple[str, ...],
    evaluation_output_dir: str,
    variance_config_path: str,
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = [
        {
            "id": "build_model_variance_packet",
            "manual_only": False,
            "description": "Build the repeated hard-trials variance packet.",
            "command": r".\.venv\Scripts\python.exe scripts/build_autonomous_browser_model_variance_packet.py --config configs/autonomous_runtime/browser_model_variance_packet.example.json",
        },
    ]
    for scenario_spec in scenario_specs:
        scenario_label = str(scenario_spec["scenario_label"])
        prompt_path = _windows_path(f"{output_dir}/prompts/{scenario_label}/{scenario_spec['prompt_filename']}")
        commands.append(
            {
                "id": f"read_{scenario_label}_prompt",
                "manual_only": True,
                "description": f"Read the {scenario_label} compact prompt before the manual model trials.",
                "command": f"Get-Content \"{prompt_path}\" -Raw",
            }
        )
    for model_spec in model_specs:
        model_alias = str(model_spec["alias"])
        for scenario_spec in scenario_specs:
            scenario_label = str(scenario_spec["scenario_label"])
            for trial_id in trial_ids:
                request_path = _windows_path(f"{output_dir}/{model_alias}/{scenario_label}/{trial_id}/request.json")
                response_path = _windows_path(f"{output_dir}/{model_alias}/{scenario_label}/{trial_id}/response.json")
                output_path = _windows_path(f"{output_dir}/{model_alias}/{scenario_label}/{trial_id}/raw_planner_output.txt")
                commands.extend(
                    [
                        {
                            "id": f"{model_alias}_{scenario_label}_{trial_id}_curl_request",
                            "manual_only": True,
                            "description": f"Run the {model_alias} manual model call for {scenario_label} / {trial_id} and save the response JSON.",
                            "command": (
                                "# Manual operator only. Codex must not launch models.\n"
                                "Do not use Invoke-RestMethod for planner generation.\n"
                                f"curl.exe --max-time 90 -sS -X POST http://127.0.0.1:8080/v1/chat/completions -H \"Content-Type: application/json\" --data-binary \"@{request_path}\" --output \"{response_path}\""
                            ),
                        },
                        {
                            "id": f"{model_alias}_{scenario_label}_{trial_id}_extract_content",
                            "manual_only": True,
                            "description": f"Extract response.choices[0].message.content into raw_planner_output.txt for {model_alias} / {scenario_label} / {trial_id}.",
                            "command": (
                                f"$response = Get-Content \"{response_path}\" -Raw | ConvertFrom-Json\n"
                                f"$response.choices[0].message.content | Set-Content \"{output_path}\" -Encoding utf8"
                            ),
                        },
                    ]
                )
    commands.extend(
        [
            {
                "id": "run_variance_evaluator_dry_run",
                "manual_only": False,
                "description": "Run the repeated-trials variance evaluator in dry-run mode.",
                "command": rf".\.venv\Scripts\python.exe scripts/run_autonomous_browser_model_variance_evaluator.py --config {variance_config_path}",
            },
            {
                "id": "run_variance_evaluator_fixture",
                "manual_only": False,
                "description": "Run the repeated-trials variance evaluator with fixture replay.",
                "command": rf".\.venv\Scripts\python.exe scripts/run_autonomous_browser_model_variance_evaluator.py --config {variance_config_path} --execute-fixture",
            },
            {
                "id": "run_pytest",
                "manual_only": False,
                "description": "Run the offline test suite.",
                "command": r".\.venv\Scripts\python.exe -m pytest",
            },
        ]
    )
    return commands


def _build_commands_markdown(
    *,
    output_dir: str,
    model_specs: tuple[dict[str, str], ...],
    scenario_specs: tuple[dict[str, Any], ...],
    trial_ids: tuple[str, ...],
    evaluation_output_dir: str,
) -> str:
    model_aliases = ", ".join(f"`{spec['alias']}`" for spec in model_specs)
    lines = [
        "# Repeated Hard Trials Commands",
        "",
        "Codex must not launch models.",
        f"The packet prepares repeated hard trials for {model_aliases}.",
        "Use `planner_prompt.compact.txt` as the prompt source for each trial.",
        "The `third_model` path is documented as `models/gguf/third_model.gguf` and is not accessed by Codex.",
        f"Packet output directory: `{output_dir}`.",
        f"Evaluator output directory: `{evaluation_output_dir}`.",
        "",
    ]
    for scenario_spec in scenario_specs:
        prompt_path = _windows_path(f"{output_dir}/prompts/{scenario_spec['scenario_label']}/{scenario_spec['prompt_filename']}")
        lines.extend(
            [
                f"## Read {scenario_spec['scenario_label']} Prompt",
                f"Prompt source for `{scenario_spec['scenario_id']}`.",
                "```powershell",
                f"Get-Content \"{prompt_path}\" -Raw",
                "```",
                "",
            ]
        )
    for model_spec in model_specs:
        for scenario_spec in scenario_specs:
            for trial_id in trial_ids:
                request_file_path = _windows_path(
                    f"{output_dir}/{model_spec['alias']}/{scenario_spec['scenario_label']}/{trial_id}/request.json"
                )
                response_file_path = _windows_path(
                    f"{output_dir}/{model_spec['alias']}/{scenario_spec['scenario_label']}/{trial_id}/response.json"
                )
                lines.extend(
                    [
                        f"## {model_spec['alias']} {scenario_spec['scenario_label']} {trial_id}",
                        f"Manual operator run for `{model_spec['alias']}` / `{scenario_spec['scenario_id']}` / `{trial_id}`.",
                        "```powershell",
                        (
                            f"curl.exe --max-time 90 -sS -X POST http://127.0.0.1:8080/v1/chat/completions -H \"Content-Type: application/json\" "
                            f"--data-binary \"@{request_file_path}\" "
                            f"--output \"{response_file_path}\""
                        ),
                        "```",
                        "",
                    ]
                )
    lines.extend(
        [
            "## Evaluation",
            "Run the offline variance evaluator after captured outputs exist.",
            "```powershell",
            rf".\.venv\Scripts\python.exe scripts/run_autonomous_browser_model_variance_evaluator.py --config {output_dir}/variance_config.local.json",
            "```",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _build_readme(
    *,
    packet_id: str,
    output_dir: str,
    evaluation_output_dir: str,
    model_specs: tuple[dict[str, str], ...],
    scenario_specs: tuple[dict[str, Any], ...],
    trial_ids: tuple[str, ...],
    request_paths: Mapping[str, Mapping[str, Mapping[str, str]]],
    output_paths: Mapping[str, Mapping[str, Mapping[str, str]]],
) -> str:
    model_aliases = ", ".join(f"`{spec['alias']}`" for spec in model_specs)
    lines = [
        "# Repeated Hard Trials Packet",
        "",
        f"Packet id: `{packet_id}`",
        "",
        "## Scope",
        "",
        "- Offline repeated-trials packet only.",
        f"- Prepares repeated hard-plan requests for {model_aliases}.",
        "- Reuses the calibrated compact hard prompts from the model-discrimination packet.",
        "- No model execution by Codex.",
        "- No browser execution by Codex.",
        "- The `third_model` path is a documentation/config expectation only.",
        "",
        "## Models",
        "",
    ]
    for spec in model_specs:
        model_note = f"- `{spec['alias']}` -> `{spec['model_path']}`"
        if spec.get("prompt_prefix"):
            model_note += f" with prompt prefix `{spec['prompt_prefix']}`"
        lines.append(model_note)
    lines.extend(
        [
            "",
            "## Scenarios",
            "",
        ]
    )
    for spec in scenario_specs:
        trial_preview = output_paths[model_specs[0]["alias"]][spec["scenario_label"]][trial_ids[0]]
        lines.append(f"- `{spec['scenario_label']}` / `{spec['scenario_id']}` -> `{trial_preview}`")
    lines.extend(
        [
            "",
            "## Operator Flow",
            "",
            f"1. Build the packet into `{output_dir}`.",
            "2. Read the scenario prompt files.",
            "3. Manually run each model request and save `response.json` and `raw_planner_output.txt` for each trial.",
            f"4. Run the variance evaluator into `{evaluation_output_dir}`.",
            "5. Run pytest.",
            "",
            "## Trial Layout",
            "",
            f"- Trial ids: {', '.join(f'`{trial_id}`' for trial_id in trial_ids)}.",
            "- Every trial is offline until the operator fills the captured output files.",
            "",
        ]
    )
    return "\n".join(lines)


def _build_prompt_text(scenario_id: str) -> str:
    if scenario_id == "hard_policy_disambiguation":
        return _build_hard_policy_disambiguation_prompt_text()
    if scenario_id == "hard_ticket_priority_crosscheck":
        return _build_hard_ticket_priority_crosscheck_prompt_text()
    if scenario_id == "hard_approval_policy_match":
        return _build_hard_approval_policy_match_prompt_text()
    raise ValueError(f"unsupported scenario_id: {scenario_id}")


def _build_user_prompt(prompt_text: str, prompt_prefix: str | None) -> str:
    if prompt_prefix:
        return f"{prompt_prefix}\n{prompt_text}"
    return prompt_text


def _safe_identifier(value: Any, label: str) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if any(ch.isspace() for ch in text):
        return None
    if any(sep in text for sep in ("/", "\\", ":", "..")):
        return None
    return text


def _safe_model_specs(value: Any) -> tuple[dict[str, str], ...] | None:
    if not isinstance(value, list) or not value:
        return None
    cleaned: list[dict[str, str]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        alias = _safe_identifier(item.get("alias"), "alias")
        model_path = _safe_relative_path(item.get("model_path"))
        if alias is None or model_path is None:
            return None
        spec: dict[str, str] = {"alias": alias, "model_path": model_path}
        prompt_prefix = item.get("prompt_prefix")
        if prompt_prefix is not None:
            if not isinstance(prompt_prefix, str) or not prompt_prefix.strip():
                return None
            spec["prompt_prefix"] = prompt_prefix.strip()
        cleaned.append(spec)
    return tuple(cleaned)


def _safe_scenario_specs(value: Any) -> tuple[dict[str, Any], ...] | None:
    if not isinstance(value, list) or not value:
        return None
    cleaned: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        scenario_id = _safe_identifier(item.get("scenario_id"), "scenario_id")
        scenario_label = _safe_identifier(item.get("scenario_label"), "scenario_label")
        prompt_filename = _safe_identifier(item.get("prompt_filename"), "prompt_filename")
        max_tokens = item.get("max_tokens")
        if scenario_id is None or scenario_label is None or prompt_filename is None:
            return None
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1:
            return None
        cleaned.append(
            {
                "scenario_id": scenario_id,
                "scenario_label": scenario_label,
                "prompt_filename": prompt_filename,
                "max_tokens": max_tokens,
            }
        )
    return tuple(cleaned)


def _safe_trial_ids(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    cleaned: list[str] = []
    for item in value:
        trial_id = _safe_identifier(item, "trial_id")
        if trial_id is None:
            return None
        cleaned.append(trial_id)
    return tuple(cleaned)


def _safe_relative_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return None
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        return None
    return path.as_posix()


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _failure_summary(
    *,
    packet_id: str | None,
    output_dir: str | None,
    evaluation_output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = AutonomousBrowserModelVariancePacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        packet_id=packet_id,
        output_dir=output_dir,
        evaluation_output_dir=evaluation_output_dir,
        models_total=0,
        scenarios_total=0,
        trial_count=0,
        trials_total=0,
        limitations=limitations,
    )
    return summary.to_dict()


def _limitations() -> tuple[str, ...]:
    return (
        "offline repeated hard trials packet only",
        "manual second_model and third_model runs only",
        "no model calls by Codex",
        "no real browser execution",
        "fixture replay remains offline only",
        "not production browser automation",
    )


def _write_text(path: Path, text: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Mapping[str, Any] | list[Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set):
        return [_jsonable(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _windows_path(value: str) -> str:
    return value.replace("/", "\\")
