from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from textwrap import dedent
from typing import Any

from .autonomous_browser_stateful_readonly_workflow import (
    build_default_stateful_readonly_workflow_scenarios,
)


CONFIG_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_packet_config_v1"
PACKET_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_packet_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_packet_summary_v1"
OUTPUT_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_output_v1"
DEFAULT_PACKET_ID = "phase_13e2_stateful_readonly_local_planner"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_packets/stateful_readonly_planner"
DEFAULT_CAPTURED_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_outputs/stateful_readonly_planner"
DEFAULT_MODEL_ALIASES = ("third_model",)
DEFAULT_SCENARIO_IDS = (
    "stateful_policy_ticket_crosscheck",
    "stateful_approval_policy_crosscheck",
    "stateful_intranet_overview_digest",
    "stateful_ticket_priority_digest",
    "stateful_policy_search_marker_review",
)
DEFAULT_MAX_TOKENS = 1800
DEFAULT_TEMPERATURE = 0.0
DEFAULT_PROMPT_PREFIXES = {"third_model": "/no_think"}
DEFAULT_PROMPT_FILENAME = "planner_prompt.compact.txt"
DEFAULT_REQUEST_FILENAME = "request.json"
DEFAULT_RESPONSE_FILENAME = "response.json"
DEFAULT_RAW_OUTPUT_FILENAME = "raw_planner_output.txt"
DEFAULT_ALLOWED_ACTIONS = (
    "browser_open_url",
    "browser_click",
    "browser_extract_text",
    "browser_snapshot",
)
DEFAULT_DISALLOWED_ACTIONS = (
    "browser_type_text",
    "browser_submit_form",
    "browser_upload_file",
    "browser_download_file",
    "external_url",
    "file_write",
)
DEFAULT_LIMITATIONS = (
    "read-only fixture-backed planner packet only",
    "manual local-model runs only",
    "no model calls by Codex",
    "no real browser execution",
    "no write/submit/type/upload/download actions",
    "fixture-backed evaluator remains offline only",
    "not production browser automation",
)
DEFAULT_REQUEST_MODEL_PATH = "models/gguf/third_model.gguf"
DEFAULT_REQUEST_MODEL_NAME = "third_model"
STRICT_JSON_SKELETON = dedent(
    """
    {
      "schema_version": "autonomous_browser_stateful_readonly_planner_output_v1",
      "scenario_id": "<scenario_id>",
      "workflow_id": "<workflow_id>",
      "goal": "<goal>",
      "actions": [
        {
          "step_id": "step_1",
          "action_name": "browser_open_url",
          "parameters": {
            "url": "https://local.intranet/"
          },
          "expected_text": "Office Intranet",
          "collect_fact_keys": []
        }
      ],
      "facts": [
        {
          "fact_id": "fact_1",
          "key": "example_key",
          "value": "example_value",
          "source_step_id": "step_1",
          "source_url": "https://local.intranet/",
          "evidence_item_id": "evidence_1"
        }
      ],
      "evidence_items": [
        {
          "evidence_item_id": "evidence_1",
          "source_step_id": "step_1",
          "source_url": "https://local.intranet/",
          "text_preview": "short evidence text",
          "fact_ids": ["fact_1"]
        }
      ],
      "final_answer": {
        "answer_text": "short final answer",
        "cited_fact_ids": ["fact_1"],
        "cited_evidence_item_ids": ["evidence_1"],
        "confidence": "medium"
      },
      "done_reason": "task_completed"
    }
    """
).strip()


@dataclass(frozen=True)
class StatefulReadonlyPlannerPacketModelSpec:
    alias: str
    prompt_prefix: str | None = None
    model_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        payload = {"alias": self.alias}
        if self.model_path is not None:
            payload["model_path"] = self.model_path
        if self.prompt_prefix is not None:
            payload["prompt_prefix"] = self.prompt_prefix
        return payload


@dataclass(frozen=True)
class StatefulReadonlyPlannerPacketScenarioSpec:
    scenario_id: str
    workflow_id: str
    goal: str
    start_url: str
    prompt_path: str
    request_path: str
    response_path: str
    raw_output_path: str
    expected_fact_keys: tuple[str, ...]
    expected_evidence_anchors: tuple[str, ...]
    route_hints: tuple[str, ...]
    final_answer_requirements: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "workflow_id": self.workflow_id,
            "goal": self.goal,
            "start_url": self.start_url,
            "prompt_path": self.prompt_path,
            "request_path": self.request_path,
            "response_path": self.response_path,
            "raw_output_path": self.raw_output_path,
            "expected_fact_keys": list(self.expected_fact_keys),
            "expected_evidence_anchors": list(self.expected_evidence_anchors),
            "route_hints": list(self.route_hints),
            "final_answer_requirements": list(self.final_answer_requirements),
        }


@dataclass(frozen=True)
class StatefulReadonlyPlannerPacketConfig:
    schema_version: str
    packet_id: str
    planner_backend: str
    model_aliases: tuple[str, ...]
    prompt_prefixes: dict[str, str]
    scenarios: tuple[str, ...]
    output_dir: str
    captured_output_dir: str
    fixture_only: bool
    external_network_allowed: bool
    writes_allowed: bool
    max_tokens: int
    temperature: float
    prompt_filename: str = DEFAULT_PROMPT_FILENAME
    limitations: tuple[str, ...] = DEFAULT_LIMITATIONS

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> StatefulReadonlyPlannerPacketConfig:
        schema_version = str(payload.get("schema_version", "")).strip()
        packet_id = _required_identifier(payload.get("packet_id"), "packet_id")
        planner_backend = str(payload.get("planner_backend", "")).strip().lower()
        model_aliases = tuple(_required_identifier_list(payload.get("model_aliases"), "model_aliases"))
        scenarios = tuple(_required_identifier_list(payload.get("scenarios"), "scenarios"))
        output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir")
        captured_output_dir = _safe_relative_path(payload.get("captured_output_dir", DEFAULT_CAPTURED_OUTPUT_DIR), "captured_output_dir")
        fixture_only = _required_bool(payload.get("fixture_only", True), "fixture_only")
        external_network_allowed = _required_bool(payload.get("external_network_allowed", False), "external_network_allowed")
        writes_allowed = _required_bool(payload.get("writes_allowed", False), "writes_allowed")
        max_tokens = _required_int(payload.get("max_tokens", DEFAULT_MAX_TOKENS), "max_tokens")
        temperature = _required_float(payload.get("temperature", DEFAULT_TEMPERATURE), "temperature")
        prompt_filename = str(payload.get("prompt_filename", DEFAULT_PROMPT_FILENAME)).strip() or DEFAULT_PROMPT_FILENAME
        prompt_prefixes_payload = payload.get("prompt_prefixes", {})
        prompt_prefixes: dict[str, str] = {}
        if not isinstance(prompt_prefixes_payload, Mapping):
            raise ValueError("prompt_prefixes must be an object.")
        for alias, prefix in prompt_prefixes_payload.items():
            clean_alias = _required_identifier(alias, "prompt_prefixes key")
            clean_prefix = _safe_text(prefix, "prompt_prefixes value")
            if clean_alias is None or clean_prefix is None:
                raise ValueError("prompt_prefixes must map safe identifiers to non-empty strings.")
            prompt_prefixes[clean_alias] = clean_prefix

        if schema_version != CONFIG_SCHEMA_VERSION:
            raise ValueError("schema_version must match autonomous_browser_stateful_readonly_planner_packet_config_v1.")
        if packet_id is None:
            raise ValueError("packet_id must be a safe identifier.")
        if planner_backend != "local_model_manual":
            raise ValueError("planner_backend must be local_model_manual.")
        if list(model_aliases) != list(DEFAULT_MODEL_ALIASES):
            raise ValueError("model_aliases must match the default stateful local planner alias set.")
        if list(scenarios) != list(DEFAULT_SCENARIO_IDS):
            raise ValueError("scenarios must match the five stateful read-only workflow scenarios.")
        if output_dir is None or captured_output_dir is None:
            raise ValueError("output_dir and captured_output_dir must be safe relative paths.")
        if not fixture_only:
            raise ValueError("fixture_only must be true.")
        if external_network_allowed:
            raise ValueError("external_network_allowed must be false.")
        if writes_allowed:
            raise ValueError("writes_allowed must be false.")
        if max_tokens <= 0:
            raise ValueError("max_tokens must be a positive integer.")
        if temperature < 0:
            raise ValueError("temperature must be non-negative.")

        for alias in model_aliases:
            if alias not in prompt_prefixes and alias == "third_model":
                prompt_prefixes[alias] = DEFAULT_PROMPT_PREFIXES[alias]
        if model_aliases and model_aliases[0] == "third_model" and prompt_prefixes.get("third_model") != "/no_think":
            raise ValueError("third_model prompt_prefix must be /no_think.")

        return cls(
            schema_version=schema_version,
            packet_id=packet_id,
            planner_backend=planner_backend,
            model_aliases=model_aliases,
            prompt_prefixes=prompt_prefixes,
            scenarios=scenarios,
            output_dir=output_dir,
            captured_output_dir=captured_output_dir,
            fixture_only=fixture_only,
            external_network_allowed=external_network_allowed,
            writes_allowed=writes_allowed,
            max_tokens=max_tokens,
            temperature=temperature,
            prompt_filename=prompt_filename,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "planner_backend": self.planner_backend,
            "model_aliases": list(self.model_aliases),
            "prompt_prefixes": dict(self.prompt_prefixes),
            "scenarios": list(self.scenarios),
            "output_dir": self.output_dir,
            "captured_output_dir": self.captured_output_dir,
            "fixture_only": self.fixture_only,
            "external_network_allowed": self.external_network_allowed,
            "writes_allowed": self.writes_allowed,
            "max_tokens": self.max_tokens,
            "temperature": self.temperature,
            "prompt_filename": self.prompt_filename,
        }


@dataclass(frozen=True)
class StatefulReadonlyPlannerPacketSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    model_execution: bool
    real_browser_execution: bool
    packet_id: str | None
    planner_backend: str | None
    output_dir: str | None
    captured_output_dir: str | None
    model_aliases: tuple[str, ...] = ()
    scenarios_total: int = 0
    requests_total: int = 0
    commands_count: int = 0
    request_records: tuple[dict[str, Any], ...] = ()
    packet_files: tuple[str, ...] = ()
    expected_output_schema_path: str | None = None
    limitations: tuple[str, ...] = DEFAULT_LIMITATIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "packet_id": self.packet_id,
            "planner_backend": self.planner_backend,
            "output_dir": self.output_dir,
            "captured_output_dir": self.captured_output_dir,
            "model_aliases": list(self.model_aliases),
            "scenarios_total": self.scenarios_total,
            "requests_total": self.requests_total,
            "commands_count": self.commands_count,
            "request_records": [dict(item) for item in self.request_records],
            "packet_files": list(self.packet_files),
            "expected_output_schema_path": self.expected_output_schema_path,
            "limitations": list(self.limitations),
        }


def build_autonomous_browser_stateful_readonly_planner_packet(
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
            captured_output_dir=config_result.get("captured_output_dir"),
            error_code=str(config_result.get("error_code") or "config_validation_failed"),
            limitations=tuple(config_result.get("limitations") or DEFAULT_LIMITATIONS),
        )

    config = StatefulReadonlyPlannerPacketConfig.from_dict(config_result["config"])
    packet_dir = repo / config.output_dir
    packet_dir.mkdir(parents=True, exist_ok=True)
    captured_output_dir = repo / config.captured_output_dir
    captured_output_dir.mkdir(parents=True, exist_ok=True)

    scenarios = build_default_stateful_readonly_workflow_scenarios()
    packet_files: list[str] = []
    request_records: list[dict[str, Any]] = []
    prompt_paths: dict[str, str] = {}

    expected_output_schema_rel = f"{config.output_dir}/expected_output_schema.md"
    expected_output_schema_path = packet_dir / "expected_output_schema.md"
    _write_text(expected_output_schema_path, _build_expected_output_schema_doc())
    packet_files.append(expected_output_schema_rel)

    for scenario_id in config.scenarios:
        scenario = scenarios[scenario_id]
        prompt_dir = packet_dir / "prompts" / scenario_id
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_text = _build_scenario_prompt_text(scenario_id=scenario_id, scenario=scenario)
        prompt_path = prompt_dir / config.prompt_filename
        _write_text(prompt_path, prompt_text)
        prompt_path_rel = f"{config.output_dir}/prompts/{scenario_id}/{config.prompt_filename}"
        prompt_paths[scenario_id] = prompt_path_rel
        packet_files.append(prompt_path_rel)

    for model_alias in config.model_aliases:
        prompt_prefix = config.prompt_prefixes.get(model_alias)
        model_dir = packet_dir / model_alias
        captured_model_dir = captured_output_dir / model_alias
        model_dir.mkdir(parents=True, exist_ok=True)
        captured_model_dir.mkdir(parents=True, exist_ok=True)

        for scenario_id in config.scenarios:
            scenario = scenarios[scenario_id]
            scenario_dir = model_dir / scenario_id
            captured_scenario_dir = captured_model_dir / scenario_id
            scenario_dir.mkdir(parents=True, exist_ok=True)
            captured_scenario_dir.mkdir(parents=True, exist_ok=True)

            request_path = scenario_dir / DEFAULT_REQUEST_FILENAME
            response_path = captured_scenario_dir / DEFAULT_RESPONSE_FILENAME
            raw_output_path = captured_scenario_dir / DEFAULT_RAW_OUTPUT_FILENAME

            prompt_path_rel = prompt_paths[scenario_id]
            request_rel = f"{config.output_dir}/{model_alias}/{scenario_id}/{DEFAULT_REQUEST_FILENAME}"
            response_rel = f"{config.captured_output_dir}/{model_alias}/{scenario_id}/{DEFAULT_RESPONSE_FILENAME}"
            raw_output_rel = f"{config.captured_output_dir}/{model_alias}/{scenario_id}/{DEFAULT_RAW_OUTPUT_FILENAME}"

            request_payload = _build_request_payload(
                packet_id=config.packet_id,
                model_alias=model_alias,
                prompt_prefix=prompt_prefix,
                scenario=scenario,
                trial_id=scenario_id,
                prompt_path=prompt_path_rel,
                request_path=request_rel,
                response_path=response_rel,
                raw_output_path=raw_output_rel,
                max_tokens=config.max_tokens,
                temperature=config.temperature,
                prompt_filename=config.prompt_filename,
            )
            _write_json(request_path, request_payload)
            packet_files.append(request_rel)

            request_records.append(
                {
                    "model_alias": model_alias,
                    "model_path": DEFAULT_REQUEST_MODEL_PATH,
                    "scenario_id": scenario_id,
                    "trial_id": scenario_id,
                    "workflow_id": scenario.workflow_id,
                    "request_path": request_rel,
                    "prompt_path": prompt_path_rel,
                    "response_path": response_rel,
                    "output_path": raw_output_rel,
                    "raw_output_path": raw_output_rel,
                    "prompt_prefix": prompt_prefix,
                    "max_tokens": config.max_tokens,
                }
            )

    commands = _build_commands(
        packet_id=config.packet_id,
        output_dir=config.output_dir,
        captured_output_dir=config.captured_output_dir,
        model_aliases=config.model_aliases,
        scenarios=config.scenarios,
        prompt_filename=config.prompt_filename,
    )
    commands_path = packet_dir / "commands.json"
    _write_json(commands_path, {"commands": commands})
    packet_files.append(f"{config.output_dir}/commands.json")

    commands_md = _build_commands_markdown(
        packet_id=config.packet_id,
        output_dir=config.output_dir,
        captured_output_dir=config.captured_output_dir,
        model_aliases=config.model_aliases,
        scenarios=config.scenarios,
        prompt_filename=config.prompt_filename,
    )
    _write_text(packet_dir / "commands.md", commands_md)
    packet_files.append(f"{config.output_dir}/commands.md")

    manifest = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "packet_id": config.packet_id,
        "planner_backend": config.planner_backend,
        "model_aliases": list(config.model_aliases),
        "prompt_prefixes": dict(config.prompt_prefixes),
        "scenarios": list(config.scenarios),
        "request_records": request_records,
        "request_count": len(request_records),
        "output_dir": config.output_dir,
        "captured_output_dir": config.captured_output_dir,
        "expected_output_schema_path": expected_output_schema_rel,
        "commands_path": f"{config.output_dir}/commands.json",
        "commands_md_path": f"{config.output_dir}/commands.md",
        "no_runtime_execution": True,
        "fixture_only": config.fixture_only,
        "external_network_allowed": config.external_network_allowed,
        "writes_allowed": config.writes_allowed,
        "limitations": list(DEFAULT_LIMITATIONS),
    }
    _write_json(packet_dir / "autonomous_browser_stateful_readonly_planner_packet.json", manifest)
    packet_files.append(f"{config.output_dir}/autonomous_browser_stateful_readonly_planner_packet.json")

    summary_relative_path = f"{config.output_dir}/autonomous_browser_stateful_readonly_planner_packet_summary.json"
    packet_files.append(summary_relative_path)
    summary = StatefulReadonlyPlannerPacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="succeeded",
        error_code=None,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        packet_id=config.packet_id,
        planner_backend=config.planner_backend,
        output_dir=config.output_dir,
        captured_output_dir=config.captured_output_dir,
        model_aliases=config.model_aliases,
        scenarios_total=len(config.scenarios),
        requests_total=len(request_records),
        commands_count=len(commands),
        request_records=tuple(request_records),
        packet_files=tuple(packet_files),
        expected_output_schema_path=expected_output_schema_rel,
        limitations=config.limitations,
    )
    summary_payload = summary.to_dict()
    _write_json(packet_dir / "autonomous_browser_stateful_readonly_planner_packet_summary.json", summary_payload)
    return summary_payload


def write_autonomous_browser_stateful_readonly_planner_packet_summary(
    summary: Mapping[str, Any],
    output_dir: str | Path,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_stateful_readonly_planner_packet_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _build_request_payload(
    *,
    packet_id: str,
    model_alias: str,
    prompt_prefix: str | None,
    scenario,
    trial_id: str,
    prompt_path: str,
    request_path: str,
    response_path: str,
    raw_output_path: str,
    max_tokens: int,
    temperature: float,
    prompt_filename: str,
    model_neutral_prompt: bool = False,
) -> dict[str, Any]:
    prompt_text = _build_scenario_prompt_text_with_mode(
        scenario_id=scenario.scenario_id,
        scenario=scenario,
        model_neutral_prompt=model_neutral_prompt,
    )
    user_content = f"{prompt_prefix}\n{prompt_text}" if prompt_prefix else prompt_text
    return {
        "model": model_alias,
        "messages": [
            {
                "role": "system",
                "content": (
                    "Return exactly one JSON object. No markdown. No prose. No code fences. "
                    "Use only the allowed read-only browser actions and keep every URL local to the fixture site."
                ),
            },
            {
                "role": "user",
                "content": user_content,
            },
        ],
        "temperature": temperature,
        "max_tokens": max_tokens,
        "stream": False,
        "metadata": {
            "packet_id": packet_id,
            "model_alias": model_alias,
            "model_path_expected": DEFAULT_REQUEST_MODEL_PATH,
            "scenario_id": scenario.scenario_id,
            "trial_id": trial_id,
            "workflow_id": scenario.workflow_id,
            "goal": scenario.objective,
            "prompt_filename": prompt_filename,
            "prompt_path": prompt_path,
            "request_path": request_path,
            "expected_raw_output_path": raw_output_path,
            "response_metadata_path": response_path,
            "prompt_prefix": prompt_prefix,
        },
    }


def _build_commands(
    *,
    packet_id: str,
    output_dir: str,
    captured_output_dir: str,
    model_aliases: tuple[str, ...],
    scenarios: tuple[str, ...],
    prompt_filename: str,
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = [
        {
            "id": "build_stateful_readonly_planner_packet",
            "manual_only": False,
            "description": "Build the read-only stateful planner packet.",
            "command": r".\.venv\Scripts\python.exe scripts/build_autonomous_browser_stateful_readonly_planner_packet.py --config configs\autonomous_runtime\browser_stateful_readonly_planner_packet.example.json",
        }
    ]
    for scenario_id in scenarios:
        prompt_path = _windows_path(f"{output_dir}/prompts/{scenario_id}/{prompt_filename}")
        commands.append(
            {
                "id": f"read_{scenario_id}_prompt",
                "manual_only": True,
                "description": f"Read the compact prompt for {scenario_id}.",
                "command": f'Get-Content "{prompt_path}" -Raw',
            }
        )
    for model_alias in model_aliases:
        for scenario_id in scenarios:
            request_path = _windows_path(f"{output_dir}/{model_alias}/{scenario_id}/{DEFAULT_REQUEST_FILENAME}")
            response_path = _windows_path(f"{captured_output_dir}/{model_alias}/{scenario_id}/{DEFAULT_RESPONSE_FILENAME}")
            raw_output_path = _windows_path(f"{captured_output_dir}/{model_alias}/{scenario_id}/{DEFAULT_RAW_OUTPUT_FILENAME}")
            commands.extend(
                [
                    {
                        "id": f"{model_alias}_{scenario_id}_curl_request",
                        "manual_only": True,
                        "description": f"Run the manual local-model request for {scenario_id} and save the raw response JSON.",
                        "command": (
                            "# Manual operator only. Codex must not launch models.\n"
                            "Do not use Invoke-RestMethod for planner generation.\n"
                            f"curl.exe --max-time 90 -sS -X POST http://127.0.0.1:8082/v1/chat/completions -H \"Content-Type: application/json\" --data-binary \"@{request_path}\" --output \"{response_path}\""
                        ),
                    },
                    {
                        "id": f"{model_alias}_{scenario_id}_extract_output",
                        "manual_only": True,
                        "description": f"Extract response.choices[0].message.content into raw_planner_output.txt for {scenario_id}.",
                        "command": (
                            f"$response = Get-Content \"{response_path}\" -Raw | ConvertFrom-Json\n"
                            f"$response.choices[0].message.content | Set-Content \"{raw_output_path}\" -Encoding utf8"
                        ),
                    },
                ]
            )
    commands.extend(
        [
            {
                "id": "run_stateful_readonly_planner_evaluator",
                "manual_only": False,
                "description": "Run the offline stateful planner evaluator with fixture execution.",
                "command": rf".\.venv\Scripts\python.exe scripts\run_autonomous_browser_stateful_readonly_planner_evaluator.py --packet-dir {output_dir} --execute-fixture",
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
    packet_id: str,
    output_dir: str,
    captured_output_dir: str,
    model_aliases: tuple[str, ...],
    scenarios: tuple[str, ...],
    prompt_filename: str,
) -> str:
    model_alias_list = ", ".join(f"`{alias}`" for alias in model_aliases)
    lines = [
        "# Stateful Read-Only Planner Packet Commands",
        "",
        "Codex must not launch models.",
        f"Packet id: `{packet_id}`.",
        f"The packet prepares manual local-model requests for {model_alias_list}.",
        "Use `planner_prompt.compact.txt` as the prompt source for each trial.",
        "The `third_model` path is documented as `models/gguf/third_model.gguf` and is not accessed by Codex.",
        "",
    ]
    for scenario_id in scenarios:
        prompt_path = _windows_path(f"{output_dir}/prompts/{scenario_id}/{prompt_filename}")
        lines.extend(
            [
                f"## Read {scenario_id} Prompt",
                "```powershell",
                f"Get-Content \"{prompt_path}\" -Raw",
                "```",
                "",
            ]
        )
    for model_alias in model_aliases:
        for scenario_id in scenarios:
            request_path = _windows_path(f"{output_dir}/{model_alias}/{scenario_id}/{DEFAULT_REQUEST_FILENAME}")
            response_path = _windows_path(f"{captured_output_dir}/{model_alias}/{scenario_id}/{DEFAULT_RESPONSE_FILENAME}")
            raw_output_path = _windows_path(f"{captured_output_dir}/{model_alias}/{scenario_id}/{DEFAULT_RAW_OUTPUT_FILENAME}")
            lines.extend(
                [
                    f"## {model_alias} {scenario_id}",
                    "```powershell",
                    (
                        f"curl.exe --max-time 90 -sS -X POST http://127.0.0.1:8082/v1/chat/completions -H \"Content-Type: application/json\" "
                        f"--data-binary \"@{request_path}\" --output \"{response_path}\""
                    ),
                    "```",
                    "```powershell",
                    f"$response.choices[0].message.content | Set-Content \"{raw_output_path}\" -Encoding utf8",
                    "```",
                    "",
                ]
            )
    lines.extend(
        [
            "## Evaluation",
            "```powershell",
            rf".\.venv\Scripts\python.exe scripts\run_autonomous_browser_stateful_readonly_planner_evaluator.py --packet-dir {output_dir} --execute-fixture",
            "```",
            "",
            "## Offline checks",
            "```powershell",
            r".\.venv\Scripts\python.exe -m pytest",
            "```",
            "",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _build_expected_output_schema_doc() -> str:
    return dedent(
        f"""
        # Stateful Read-Only Planner Output Schema

        Schema version: `{OUTPUT_SCHEMA_VERSION}`

        ## Top-level fields

        - `schema_version`
        - `scenario_id`
        - `workflow_id`
        - `goal`
        - `actions`
        - `facts`
        - `evidence_items`
        - `final_answer`
        - `done_reason`

        ## Actions

        Each action item must include:

        - `step_id`
        - `action_name`
        - `parameters`
        - `expected_text` (optional)
        - `expected_url` (optional)
        - `collect_fact_keys` (optional)

        Allowed action names:

        - `browser_open_url`
        - `browser_click`
        - `browser_extract_text`
        - `browser_snapshot`

        ### Forbidden aliases

        - `action`
        - `tool`
        - top-level `url`, `selector`, `name`, `label`, or `target_text` on action items
        - CSS selectors for `browser_click`
        - `browser_click` selectors instead of visible text

        ## Copyable strict JSON skeleton

        ```json
        {STRICT_JSON_SKELETON}
        ```

        ## Facts

        `facts` must be an array.

        Each fact item must include:

        - `fact_id`
        - `key`
        - `value`
        - `source_step_id`
        - `source_url` (optional)
        - `evidence_item_id` (optional)

        ## Evidence items

        `evidence_items` must be an array.

        Each evidence item must include:

        - `evidence_item_id`
        - `source_step_id`
        - `source_url` (optional)
        - `text_quote` or `text_preview`
        - `fact_ids` (optional)

        Forbidden aliases:

        - `id`
        - `text`
        - `content`
        - `source_step`

        ## Final answer

        The final answer object must include:

        - `answer_text`
        - `cited_fact_ids`
        - `cited_evidence_item_ids`
        - `confidence` (optional)
        - If included, `confidence` must be exactly one of `low`, `medium`, or `high`.

        Missing citations are invalid.

        ## Done reasons

        - `task_completed`
        - `insufficient_evidence`
        - `model_failed_task`
        - `policy_rejected`

        ## Safety boundary

        - Read-only only.
        - No write, submit, type, upload, or download actions.
        - No external URLs.
        - No markdown or prose outside the single JSON object in captured model output.
        """
    ).strip() + "\n"


def _build_scenario_prompt_text(*, scenario_id: str, scenario) -> str:
    return _build_scenario_prompt_text_with_mode(
        scenario_id=scenario_id,
        scenario=scenario,
        model_neutral_prompt=False,
    )


def _build_scenario_prompt_text_with_mode(
    *,
    scenario_id: str,
    scenario,
    model_neutral_prompt: bool,
) -> str:
    hints = _scenario_prompt_hints()[scenario_id]
    route_hints = "\n".join(f"- {item}" for item in hints["route_hints"])
    click_hints = "\n".join(
        f"- `browser_click` with `parameters.target_text`: `{item}`" for item in hints["click_targets"]
    )
    required_fact_keys = "\n".join(f"- `{item}`" for item in hints["required_fact_keys"])
    expected_evidence_anchors = "\n".join(f"- {item}" for item in hints["expected_evidence_anchors"])
    final_answer_requirements = "\n".join(f"- {item}" for item in hints["final_answer_requirements"])
    approval_fact_skeleton = ""
    if scenario_id == "stateful_approval_policy_crosscheck":
        approval_fact_skeleton = dedent(
            """
            ## Approval required facts

            Your facts array MUST include exactly these required keys at minimum:

            ```json
            [
              {
                "fact_id": "fact_1",
                "key": "approval_request",
                "value": "Request id: APR-51.",
                "source_step_id": "inspect_approval_match",
                "source_url": "https://local.intranet/portal/approval-match",
                "evidence_item_id": "evidence_1"
              },
              {
                "fact_id": "fact_2",
                "key": "approval_policy_anchor",
                "value": "Approval Policy Match",
                "source_step_id": "inspect_approval_match",
                "source_url": "https://local.intranet/portal/approval-match",
                "evidence_item_id": "evidence_2"
              },
              {
                "fact_id": "fact_3",
                "key": "approval_policy_marker",
                "value": "Policy match: confirmed.",
                "source_step_id": "inspect_approval_match",
                "source_url": "https://local.intranet/portal/approval-match",
                "evidence_item_id": "evidence_3"
              },
              {
                "fact_id": "fact_4",
                "key": "approval_decision_note",
                "value": "local fixtures only",
                "source_step_id": "inspect_approval_match",
                "source_url": "https://local.intranet/portal/approval-match",
                "evidence_item_id": "evidence_4"
              }
            ]
            ```

            - Do not omit approval_decision_note.
            - The final_answer must cite all four fact ids.
            """
        ).strip()

    model_specific_prompt_note = (
        "- If you are `third_model`, keep `/no_think` at the start of the request content."
        if not model_neutral_prompt
        else "- Use the same frozen task prompt for every enabled model alias. Do not add model-family-specific tuning."
    )

    return dedent(
        f"""
        # Stateful Read-Only Planner Prompt

        Return exactly one JSON object. No markdown. No prose. No code fences.
        Return valid strict JSON with no trailing commas.
        Use the schema version `{OUTPUT_SCHEMA_VERSION}`.

        ## Strict JSON skeleton

        ```json
        {STRICT_JSON_SKELETON}
        ```

        ## Scenario

        - `scenario_id`: `{scenario_id}`
        - `workflow_id`: `{scenario.workflow_id}`
        - `goal`: {scenario.objective}
        - `start_url`: `{scenario.start_url}`

        ## Read-only policy

        - Allowed actions: {", ".join(f"`{item}`" for item in DEFAULT_ALLOWED_ACTIONS)}.
        - Disallowed actions: {", ".join(f"`{item}`" for item in DEFAULT_DISALLOWED_ACTIONS)}.
        - Use only local fixture URLs.
        - No external URLs, writes, submits, typing, upload, or download actions.
        - Cite facts and evidence from visited fixture pages.
        {model_specific_prompt_note}
        - Do NOT use the field name `action`.
        - Do NOT use the field name `name` for actions.
        - Do NOT use the field name `tool`.
        - Do NOT place `url`, `selector`, `target_text`, or `label` at the top level of an action item.
        - Put all action parameters inside `parameters`.
        - For `browser_click` use `parameters.target_text`, not `selector`.
        - Do NOT use CSS selectors for `browser_click`.
        - `facts` MUST be an array, not an object.
        - `evidence_items` MUST be an array.
        - `final_answer` MUST include `cited_fact_ids` and `cited_evidence_item_ids`.
        - Return exactly one valid strict JSON object.
        - No comments.

        ## Route hints

        {route_hints}

        ## Suggested click targets

        {click_hints}

        ## Required fact keys

        {required_fact_keys}

        {approval_fact_skeleton if approval_fact_skeleton else ""}

        ## Expected evidence anchors

        {expected_evidence_anchors}

        ## Final answer requirements

        {final_answer_requirements}

        ## Confidence

        - `confidence` is optional.
        - If you include `confidence`, use exactly one of `low`, `medium`, or `high`.
        - Do not use numbers, percentages, booleans, or words like `certain` or `confident`.

        ## Output shape reminder

        - Include `schema_version`, `scenario_id`, `workflow_id`, `goal`, `actions`, `facts`, `evidence_items`, `final_answer`, and `done_reason`.
        - `done_reason` must be one of `task_completed`, `insufficient_evidence`, `model_failed_task`, or `policy_rejected`.
        - `actions` may only use the read-only browser action surface.
        - `final_answer.answer_text` should be concise and cite the collected facts/evidence ids.
        - Do not add trailing commas.
        """
    ).strip() + "\n"


def _scenario_prompt_hints() -> dict[str, dict[str, tuple[str, ...]]]:
    return {
        "stateful_policy_ticket_crosscheck": {
            "route_hints": (
                "Home -> Ticket board.",
                "Ticket board -> Ticket 1.",
                "Ticket 1 -> Workspace policy.",
                "The required ticket_id value is exactly Ticket 1.",
                "Do not invent internal ticket ids such as TICKET-12345.",
                "Copy ticket_id from the visible Ticket 1 page/title: Ticket 1 - Quarterly Access Review.",
                "The required ticket_topic value is exactly Quarterly Access Review.",
                "Copy ticket_priority from the visible text Priority: high.",
                "Copy ticket_role from the visible text Assigned role: office worker.",
                "The required policy_anchor value is exactly Workspace Policy.",
                "Do not use https://local.intranet/docs/policy as policy_anchor.",
                "The URL belongs in source_url only, not in the fact value.",
                "Copy policy_anchor from the visible page title/header text: Workspace Policy.",
                "The policy_marker must be copied exactly from the visible Workspace Policy search marker text: fixture-backed result for workspace policy review.",
                "Do not invent policy sections, approval rules, or admin approval language unless the fixture page visibly shows them.",
                "Workspace Policy facts and evidence should come from https://local.intranet/docs/policy.",
                "evidence text_preview must be a visible text span from the replayed page.",
            ),
            "click_targets": (
                "Ticket board",
                "Ticket 1",
                "Workspace Policy",
            ),
            "required_fact_keys": (
                "ticket_id",
                "ticket_topic",
                "ticket_priority",
                "ticket_role",
                "policy_anchor",
                "policy_marker",
            ),
            "expected_evidence_anchors": (
                "Office Intranet",
                "Ticket Board",
                "Ticket 1 - Quarterly Access Review",
                "Workspace Policy",
                "Search marker: fixture-backed result for workspace policy review.",
            ),
            "final_answer_requirements": (
                "Mention the ticket evidence and the policy evidence together.",
                "Explain the risk conclusion in one short sentence.",
                "Use ticket_id exactly as Ticket 1 and ticket_topic exactly as Quarterly Access Review.",
                "Use policy_anchor exactly as Workspace Policy, never the policy URL.",
                "Copy policy_marker exactly from the visible Workspace Policy marker.",
                "Cite the collected fact ids and evidence item ids.",
            ),
        },
        "stateful_approval_policy_crosscheck": {
            "route_hints": (
                "Home -> Approvals queue.",
                "Approvals queue -> Policy match review.",
                "Once Approval Policy Match is reached, prefer extract/snapshot and stop.",
            ),
            "click_targets": (
                "Approvals queue",
                "Policy match review",
            ),
            "required_fact_keys": (
                "approval_request",
                "approval_policy_anchor",
                "approval_policy_marker",
                "approval_decision_note",
            ),
            "expected_evidence_anchors": (
                "Portal Home",
                "Approvals Queue",
                "Approval Policy Match",
                "Request id: APR-51.",
                "Policy match: confirmed.",
                "Search marker: approval-policy match is the fixture-backed answer.",
            ),
            "final_answer_requirements": (
                "Mention the approval request and the policy match evidence.",
                "Do not omit approval_decision_note.",
                "Cite all four fact ids: approval_request, approval_policy_anchor, approval_policy_marker, and approval_decision_note.",
                "State the local decision in one short sentence.",
                "Cite the collected fact ids and evidence item ids.",
            ),
        },
        "stateful_intranet_overview_digest": {
            "route_hints": (
                "Home -> Ticket board.",
                "From Ticket board, use browser_open_url to open https://local.intranet/docs/policy.",
                "From Ticket board, use browser_open_url to open https://local.intranet/team/status.",
            ),
            "click_targets": (
                "Ticket board",
                "Workspace Policy",
                "Team status",
            ),
            "required_fact_keys": (
                "home_anchor",
                "ticket_board_anchor",
                "policy_anchor",
                "team_status_anchor",
            ),
            "expected_evidence_anchors": (
                "Office Intranet",
                "Ticket Board",
                "Priority cross-check board",
                "Workspace Policy",
                "Team Status",
            ),
            "final_answer_requirements": (
                "Summarize the home, ticket board, policy, and team status pages.",
                "Keep the digest compact and local-fixture specific.",
                "Cite the collected fact ids and evidence item ids.",
            ),
        },
        "stateful_ticket_priority_digest": {
            "route_hints": (
                "Home -> Ticket board.",
                "Use browser_open_url to open https://local.intranet/tickets/hardboard.",
                "Priority cross-check board -> Ticket 7.",
                "After Ticket 7, use browser_open_url to return to https://local.intranet/tickets/hardboard before inspecting Ticket 8.",
                "Priority cross-check board -> Ticket 8.",
                "Ticket 7 facts and evidence should come from https://local.intranet/tickets/7.",
                "Ticket 8 facts and evidence should come from https://local.intranet/tickets/8.",
                "The required ticket_8_requester_tier value is exactly office worker.",
                "Do not use general unless the Ticket 8 page visibly shows general.",
                "The required ticket_8_marker value is exactly decoy for the priority cross-check.",
                "Do not use none for ticket_8_marker because Ticket 8 visibly shows a search marker.",
                "Copy the phrase after Search marker: this page is the ... from the visible Ticket 8 page.",
                "Ticket 8 is the decoy; still copy its actual visible facts exactly.",
                "evidence text_preview must quote visible text from the Ticket 8 page.",
            ),
            "click_targets": (
                "Ticket 7",
                "Ticket 8",
            ),
            "required_fact_keys": (
                "ticket_7_id",
                "ticket_7_topic",
                "ticket_7_priority",
                "ticket_7_requester_tier",
                "ticket_7_marker",
                "ticket_8_id",
                "ticket_8_topic",
                "ticket_8_priority",
                "ticket_8_requester_tier",
                "ticket_8_marker",
            ),
            "expected_evidence_anchors": (
                "Priority cross-check board",
                "Ticket 7 - Escalation Review",
                "Priority: urgent.",
                "Requester tier: facilities.",
                "Ticket 8 - Follow-up Note",
                "Priority: low.",
                "Search marker: the escalation ticket is the urgent one.",
                "Search marker: this page is the decoy for the priority cross-check.",
            ),
            "final_answer_requirements": (
                "Identify the most important ticket and explain why it outranks the decoy.",
                "Mention the requester tier and priority evidence.",
                "After Ticket 7, reopen the hardboard with browser_open_url before continuing to Ticket 8.",
                "Copy ticket_8_requester_tier exactly from the visible Ticket 8 page.",
                "Copy ticket_8_marker exactly from the visible Ticket 8 page.",
                "Cite the collected fact ids and evidence item ids.",
            ),
        },
        "stateful_policy_search_marker_review": {
            "route_hints": (
                "Home -> Workspace policy.",
            ),
            "click_targets": (
                "Workspace Policy",
            ),
            "required_fact_keys": (
                "policy_anchor",
                "policy_marker",
            ),
            "expected_evidence_anchors": (
                "Workspace Policy",
                "fixture-backed result for workspace policy review",
            ),
            "final_answer_requirements": (
                "Return the workspace policy search marker and keep the answer short.",
                "Cite the policy anchor and policy marker fact ids.",
            ),
        },
        "stateful_policy_source_disambiguation": {
            "route_hints": (
                "Policy Disambiguation -> Archived policy.",
                "Archived policy -> Current policy.",
                "Use the archive page only to confirm it is not the live source.",
                "Finish on Workspace Policy, not on Archived Policy.",
            ),
            "click_targets": (
                "Archived policy",
                "Current policy",
            ),
            "required_fact_keys": (
                "live_policy_source",
                "archive_warning",
                "current_policy_anchor",
                "current_policy_marker",
            ),
            "expected_evidence_anchors": (
                "Policy Disambiguation",
                "Archived Policy",
                "Do not use this page as the current policy source.",
                "Workspace Policy",
                "fixture-backed result for workspace policy review",
            ),
            "final_answer_requirements": (
                "State that the current policy is the live source and the archive is not.",
                "Use current_policy_anchor exactly as Workspace Policy.",
                "Copy archive_warning from the visible archive page text.",
                "Cite the collected fact ids and evidence item ids.",
            ),
        },
        "stateful_approval_queue_absence_review": {
            "route_hints": (
                "Home -> Approvals queue.",
                "Inspect the queue page and stop there.",
                "Do not open Policy match review for this scenario because the task is an absence check on the queue itself.",
            ),
            "click_targets": (
                "Approvals queue",
            ),
            "required_fact_keys": (
                "queue_request_id",
                "queue_owner",
                "target_request_presence",
            ),
            "expected_evidence_anchors": (
                "Office Intranet",
                "Approvals Queue",
                "Approval item APR-42 is waiting for local policy verification.",
                "Owner: office worker.",
            ),
            "final_answer_requirements": (
                "Report that APR-51 is not found in the approvals queue.",
                "Also mention the visible queue item APR-42 and the owner office worker.",
                "Keep the answer short and queue-specific.",
                "Cite the collected fact ids and evidence item ids.",
            ),
        },
        "stateful_priority_exception_rule_review": {
            "route_hints": (
                "Open the priority cross-check board directly.",
                "Priority cross-check board -> Ticket 7.",
                "Use the board rule together with the Ticket 7 detail page.",
                "Do not visit Ticket 8 in this scenario.",
            ),
            "click_targets": (
                "Ticket 7",
            ),
            "required_fact_keys": (
                "priority_rule",
                "ticket_7_id",
                "ticket_7_requester_tier",
                "ticket_7_priority",
                "ticket_7_marker",
            ),
            "expected_evidence_anchors": (
                "Priority cross-check board",
                "Priority is determined by requester tier, not by queue age.",
                "Ticket 7 - Escalation Review",
                "Requester tier: facilities.",
                "Priority: urgent.",
            ),
            "final_answer_requirements": (
                "Explain that Ticket 7 is the urgent escalation ticket because requester tier overrides queue age.",
                "Copy the priority_rule exactly from the visible board text.",
                "Mention Ticket 7, facilities, and urgent.",
                "Cite the collected fact ids and evidence item ids.",
            ),
        },
    }


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
                "captured_output_dir": None,
                "limitations": DEFAULT_LIMITATIONS,
            }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": None,
            "output_dir": None,
            "captured_output_dir": None,
            "limitations": DEFAULT_LIMITATIONS,
        }
    try:
        config = StatefulReadonlyPlannerPacketConfig.from_dict(payload)
    except ValueError:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": _safe_text(payload.get("packet_id"), "packet_id"),
            "output_dir": _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir"),
            "captured_output_dir": _safe_relative_path(payload.get("captured_output_dir", DEFAULT_CAPTURED_OUTPUT_DIR), "captured_output_dir"),
            "limitations": DEFAULT_LIMITATIONS,
        }
    return {"status": "ok", "config": config.to_dict(), "limitations": config.limitations}


def _failure_summary(
    *,
    packet_id: str | None,
    output_dir: str | None,
    captured_output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = StatefulReadonlyPlannerPacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        packet_id=packet_id,
        planner_backend="local_model_manual",
        output_dir=output_dir,
        captured_output_dir=captured_output_dir,
        limitations=limitations,
    )
    return summary.to_dict()


def _required_identifier(value: Any, label: str) -> str | None:
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


def _required_identifier_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list) or not value:
        raise ValueError(f"{label} must be a non-empty list.")
    items: list[str] = []
    for candidate in value:
        identifier = _required_identifier(candidate, label)
        if identifier is None:
            raise ValueError(f"{label} contains an unsafe identifier.")
        items.append(identifier)
    return items


def _required_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean.")
    return value


def _required_int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise ValueError(f"{label} must be a positive integer.")
    return value


def _required_float(value: Any, label: str) -> float:
    if isinstance(value, bool) or not isinstance(value, (int, float)):
        raise ValueError(f"{label} must be a number.")
    return float(value)


def _safe_relative_path(value: Any, label: str) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return None
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        return None
    return path.as_posix()


def _safe_text(value: Any, label: str) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _windows_path(value: str) -> str:
    return value.replace("/", "\\")
