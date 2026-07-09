from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_local_planner_operator_packet import _build_compact_prompt_text as _build_phase10_policy_prompt_text
from .autonomous_browser_phase11_local_planner_packet import _build_prompt_text as _build_phase11_prompt_text


PACKET_SCHEMA_VERSION = "autonomous_browser_model_comparison_packet_v1"
PACKET_CONFIG_SCHEMA_VERSION = "autonomous_browser_model_comparison_packet_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_model_comparison_packet_summary_v1"
DEFAULT_PACKET_ID = "browser_model_comparison_packet_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_comparison_packet"
DEFAULT_EVALUATION_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_comparison_packet/evaluation_runs"
DEFAULT_COMPARISON_CONFIG_PATH = "artifacts/autonomous_runtime_summaries/model_comparison_packet/comparison_config.local.json"
DEFAULT_MODEL_SPECS = (
    {"alias": "first_model", "model_path": "models/gguf/first_model.gguf"},
    {"alias": "second_model", "model_path": "models/gguf/second_model.gguf"},
    {
        "alias": "third_model",
        "model_path": "models/gguf/third_model.gguf",
        "prompt_prefix": "/no_think",
    },
)
DEFAULT_SCENARIO_SPECS = (
    {
        "scenario_id": "browser_intranet_policy_research",
        "scenario_label": "policy_family",
        "prompt_filename": "planner_prompt.policy_family.compact.txt",
        "max_tokens": 1200,
    },
    {
        "scenario_id": "browser_ticket_triage_review",
        "scenario_label": "ticket_triage",
        "prompt_filename": "planner_prompt.ticket_triage.compact.txt",
        "max_tokens": 1200,
    },
    {
        "scenario_id": "browser_approval_form_review",
        "scenario_label": "approval_review",
        "prompt_filename": "planner_prompt.approval_review.compact.txt",
        "max_tokens": 1200,
    },
)


@dataclass(frozen=True)
class ModelComparisonPacketSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    model_execution: bool
    real_browser_execution: bool
    packet_id: str | None
    output_dir: str | None
    evaluation_output_dir: str | None
    model_count: int
    scenario_count: int
    model_aliases: tuple[str, ...] = ()
    scenario_ids: tuple[str, ...] = ()
    packet_files: tuple[str, ...] = ()
    request_paths_path: str | None = None
    output_paths_path: str | None = None
    comparison_config_path: str | None = None
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
            "model_count": self.model_count,
            "scenario_count": self.scenario_count,
            "model_aliases": list(self.model_aliases),
            "scenario_ids": list(self.scenario_ids),
            "packet_files": list(self.packet_files),
            "request_paths_path": self.request_paths_path,
            "output_paths_path": self.output_paths_path,
            "comparison_config_path": self.comparison_config_path,
            "expected_raw_output_paths": list(self.expected_raw_output_paths),
            "commands_count": self.commands_count,
            "execution_status": self.execution_status,
            "limitations": list(self.limitations),
        }


def build_autonomous_browser_model_comparison_packet(
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
    limitations = tuple(config_result.get("limitations") or _limitations())

    packet_dir = repo / output_dir
    packet_dir.mkdir(parents=True, exist_ok=True)

    packet_files: list[str] = []
    request_paths: dict[str, dict[str, str]] = {}
    output_paths: dict[str, dict[str, str]] = {}
    prompt_paths: dict[str, str] = {}
    comparison_scenarios: list[dict[str, Any]] = []
    model_aliases: list[str] = []
    scenario_ids: list[str] = []

    for scenario_spec in scenario_specs:
        scenario_id = str(scenario_spec["scenario_id"])
        scenario_label = str(scenario_spec["scenario_label"])
        prompt_filename = str(scenario_spec["prompt_filename"])
        prompt_text = _build_prompt_text(scenario_id)
        prompt_path = packet_dir / "prompts" / scenario_label / prompt_filename
        prompt_path.parent.mkdir(parents=True, exist_ok=True)
        _write_text(prompt_path, prompt_text + "\n")
        prompt_path_relative = f"{output_dir}/prompts/{scenario_label}/{prompt_filename}"
        prompt_paths[scenario_label] = prompt_path_relative
        packet_files.append(prompt_path_relative)
        comparison_scenarios.append(
            {
                "scenario_id": scenario_id,
                "scenario_label": scenario_label,
                "prompt_path": prompt_path_relative,
                "max_tokens": int(scenario_spec["max_tokens"]),
            }
        )
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
            prompt_path_relative = prompt_paths[scenario_label]
            request_dir = packet_dir / model_alias / scenario_label
            request_dir.mkdir(parents=True, exist_ok=True)
            request_path = request_dir / "request.json"
            raw_output_path = request_dir / "raw_planner_output.txt"
            request_payload = _build_request_payload(
                packet_id=packet_id,
                model_alias=model_alias,
                model_path=model_path,
                prompt_prefix=str(model_spec.get("prompt_prefix")) if model_spec.get("prompt_prefix") else None,
                scenario_id=scenario_id,
                scenario_label=scenario_label,
                prompt_filename=prompt_filename,
                prompt_path=prompt_path_relative,
                request_path=f"{output_dir}/{model_alias}/{scenario_label}/request.json",
                raw_output_path=f"{output_dir}/{model_alias}/{scenario_label}/raw_planner_output.txt",
                max_tokens=int(scenario_spec["max_tokens"]),
                prompt_text=_build_prompt_text(scenario_id),
            )
            _write_json(request_path, request_payload)
            request_path_relative = f"{output_dir}/{model_alias}/{scenario_label}/request.json"
            raw_output_path_relative = f"{output_dir}/{model_alias}/{scenario_label}/raw_planner_output.txt"
            request_paths[model_alias][scenario_label] = request_path_relative
            output_paths[model_alias][scenario_label] = raw_output_path_relative
            packet_files.extend([request_path_relative, raw_output_path_relative])

    request_paths_path = packet_dir / "request_paths.json"
    _write_json(request_paths_path, request_paths)
    packet_files.append(f"{output_dir}/request_paths.json")

    output_paths_path = packet_dir / "output_paths.json"
    _write_json(output_paths_path, output_paths)
    packet_files.append(f"{output_dir}/output_paths.json")

    comparison_config = _build_comparison_config(
        packet_id=packet_id,
        output_dir=output_dir,
        evaluation_output_dir=evaluation_output_dir,
        model_specs=model_specs,
        scenario_specs=scenario_specs,
        request_paths=request_paths,
        output_paths=output_paths,
        prompt_paths=prompt_paths,
        limitations=limitations,
    )
    comparison_config_path = packet_dir / "comparison_config.local.json"
    _write_json(comparison_config_path, comparison_config)
    packet_files.append(f"{output_dir}/comparison_config.local.json")

    commands = _build_commands(
        output_dir=output_dir,
        request_paths=request_paths,
        output_paths=output_paths,
        prompt_paths=prompt_paths,
        model_specs=model_specs,
        scenario_specs=scenario_specs,
        evaluation_output_dir=evaluation_output_dir,
        comparison_config_path=f"{output_dir}/comparison_config.local.json",
    )
    _write_json(packet_dir / "commands.json", {"commands": commands})
    packet_files.append(f"{output_dir}/commands.json")

    commands_md = _build_commands_markdown(
        output_dir=output_dir,
        model_specs=model_specs,
        scenario_specs=scenario_specs,
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
        "request_paths_path": f"{output_dir}/request_paths.json",
        "output_paths_path": f"{output_dir}/output_paths.json",
        "comparison_config_path": f"{output_dir}/comparison_config.local.json",
        "limitations": list(limitations),
    }
    _write_json(packet_dir / "model_comparison_packet.json", packet_json)
    packet_files.append(f"{output_dir}/model_comparison_packet.json")

    summary_relative_path = f"{output_dir}/autonomous_browser_model_comparison_packet_summary.json"
    packet_files.append(summary_relative_path)
    summary = ModelComparisonPacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="succeeded",
        error_code=None,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        packet_id=packet_id,
        output_dir=output_dir,
        evaluation_output_dir=evaluation_output_dir,
        model_count=len(model_specs),
        scenario_count=len(scenario_specs),
        model_aliases=tuple(model_aliases),
        scenario_ids=tuple(scenario_ids),
        packet_files=tuple(packet_files),
        request_paths_path=f"{output_dir}/request_paths.json",
        output_paths_path=f"{output_dir}/output_paths.json",
        comparison_config_path=f"{output_dir}/comparison_config.local.json",
        expected_raw_output_paths=tuple(
            output_paths[model_spec["alias"]][scenario_spec["scenario_label"]]
            for model_spec in model_specs
            for scenario_spec in scenario_specs
        ),
        commands_count=len(commands),
        execution_status="skipped_by_design",
        limitations=limitations,
    )
    summary_payload = summary.to_dict()
    _write_json(packet_dir / "autonomous_browser_model_comparison_packet_summary.json", summary_payload)
    return summary_payload


def write_autonomous_browser_model_comparison_packet_summary(summary: Mapping[str, Any], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_model_comparison_packet_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _build_request_payload(
    *,
    packet_id: str,
    model_alias: str,
    model_path: str,
    prompt_prefix: str | None,
    scenario_id: str,
    scenario_label: str,
    prompt_filename: str,
    prompt_path: str,
    request_path: str,
    raw_output_path: str,
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
            "prompt_filename": prompt_filename,
            "prompt_path": prompt_path,
            "request_path": request_path,
            "expected_raw_output_path": raw_output_path,
        },
    }


def _build_comparison_config(
    *,
    packet_id: str,
    output_dir: str,
    evaluation_output_dir: str,
    model_specs: tuple[dict[str, str], ...],
    scenario_specs: tuple[dict[str, Any], ...],
    request_paths: Mapping[str, Mapping[str, str]],
    output_paths: Mapping[str, Mapping[str, str]],
    prompt_paths: Mapping[str, str],
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "schema_version": "autonomous_browser_model_comparison_evaluator_config_v1",
        "packet_id": packet_id,
        "output_dir": evaluation_output_dir,
        "packet_output_dir": output_dir,
        "models": [
            {
                "alias": item["alias"],
                "model_path": item["model_path"],
                **({"prompt_prefix": item["prompt_prefix"]} if "prompt_prefix" in item else {}),
            }
            for item in model_specs
        ],
        "scenarios": [
            {
                "scenario_id": item["scenario_id"],
                "scenario_label": item["scenario_label"],
                "prompt_filename": item["prompt_filename"],
                "prompt_path": prompt_paths[item["scenario_label"]],
                "max_tokens": item["max_tokens"],
                "request_paths": {model["alias"]: request_paths[model["alias"]][item["scenario_label"]] for model in model_specs},
                "output_paths": {model["alias"]: output_paths[model["alias"]][item["scenario_label"]] for model in model_specs},
            }
            for item in scenario_specs
        ],
        "request_paths_path": f"{output_dir}/request_paths.json",
        "output_paths_path": f"{output_dir}/output_paths.json",
        "limitations": list(limitations),
        "no_runtime_execution": True,
    }


def _build_commands(
    *,
    output_dir: str,
    request_paths: Mapping[str, Mapping[str, str]],
    output_paths: Mapping[str, Mapping[str, str]],
    prompt_paths: Mapping[str, str],
    model_specs: tuple[dict[str, str], ...],
    scenario_specs: tuple[dict[str, Any], ...],
    evaluation_output_dir: str,
    comparison_config_path: str,
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = [
        {
            "id": "build_model_comparison_packet",
            "manual_only": False,
            "description": "Build the offline model comparison packet.",
            "command": r".\.venv\Scripts\python.exe scripts/build_autonomous_browser_model_comparison_packet.py --config configs/autonomous_runtime/browser_model_comparison_packet.example.json",
        },
        {
            "id": "run_model_comparison_evaluator",
            "manual_only": False,
            "description": "Run the offline model comparison evaluator.",
            "command": rf".\.venv\Scripts\python.exe scripts/run_autonomous_browser_model_comparison_evaluator.py --config {comparison_config_path}",
        },
    ]
    for scenario_spec in scenario_specs:
        scenario_label = str(scenario_spec["scenario_label"])
        prompt_path = _windows_path(prompt_paths[scenario_label])
        commands.append(
            {
                "id": f"read_{scenario_label}_prompt",
                "manual_only": True,
                "description": f"Read the {scenario_label} compact prompt before manual model runs.",
                "command": f"Get-Content {prompt_path} -Raw",
            }
        )
    for model_spec in model_specs:
        model_alias = str(model_spec["alias"])
        for scenario_spec in scenario_specs:
            scenario_label = str(scenario_spec["scenario_label"])
            request_path = _windows_path(request_paths[model_alias][scenario_label])
            response_path = request_path.replace("request.json", "response.json")
            output_path = _windows_path(output_paths[model_alias][scenario_label])
            commands.extend(
                [
                    {
                        "id": f"{model_alias}_{scenario_label}_curl_request",
                        "manual_only": True,
                        "description": f"Run the {model_alias} manual model call for {scenario_label} and save the response JSON.",
                        "command": (
                            "# Manual operator only. Codex must not launch models.\n"
                            f"curl.exe --max-time 90 -sS -X POST http://127.0.0.1:8080/v1/chat/completions -H \"Content-Type: application/json\" --data-binary \"@{request_path}\" --output \"{response_path}\""
                        ),
                    },
                    {
                        "id": f"{model_alias}_{scenario_label}_extract_content",
                        "manual_only": True,
                        "description": f"Extract response.choices[0].message.content into raw_planner_output.txt for {model_alias} / {scenario_label}.",
                        "command": (
                            f"$response = Get-Content \"{response_path}\" -Raw | ConvertFrom-Json\n"
                            f"$response.choices[0].message.content | Set-Content \"{output_path}\" -Encoding utf8"
                        ),
                    },
                ]
            )
    commands.append(
        {
            "id": "run_pytest",
            "manual_only": False,
            "description": "Run the offline test suite.",
            "command": r".\.venv\Scripts\python.exe -m pytest",
        }
    )
    return commands


def _build_commands_markdown(
    *,
    output_dir: str,
    model_specs: tuple[dict[str, str], ...],
    scenario_specs: tuple[dict[str, Any], ...],
    evaluation_output_dir: str,
) -> str:
    model_aliases = ", ".join(f"`{spec['alias']}`" for spec in model_specs)
    lines = [
        "# Model Comparison Packet Commands",
        "",
        "Codex must not launch models.",
        f"The packet prepares comparison requests for {model_aliases}.",
        "Use `planner_prompt.compact.txt` as the prompt source for each trial.",
        "The `third_model` path is documented as `models/gguf/third_model.gguf` and is not accessed by Codex.",
        f"Packet output directory: `{output_dir}`.",
        f"Evaluator output directory: `{evaluation_output_dir}`.",
        "",
    ]
    for scenario_spec in scenario_specs:
        prompt_file_path = _windows_path(f"{output_dir}/prompts/{scenario_spec['scenario_label']}/{scenario_spec['prompt_filename']}")
        lines.extend(
            [
                f"## Read {scenario_spec['scenario_label']} Prompt",
                f"Prompt source for `{scenario_spec['scenario_id']}`.",
                "```powershell",
                f"Get-Content \"{prompt_file_path}\" -Raw",
                "```",
                "",
            ]
        )
    for model_spec in model_specs:
        for scenario_spec in scenario_specs:
            request_file_path = _windows_path(
                f"{output_dir}/{model_spec['alias']}/{scenario_spec['scenario_label']}/request.json"
            )
            response_file_path = _windows_path(
                f"{output_dir}/{model_spec['alias']}/{scenario_spec['scenario_label']}/response.json"
            )
            lines.extend(
                [
                    f"## {model_spec['alias']} {scenario_spec['scenario_label']}",
                    f"Manual operator run for `{model_spec['alias']}` / `{scenario_spec['scenario_id']}`.",
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
            "Run the offline comparison evaluator after captured outputs exist.",
            "```powershell",
            rf".\.venv\Scripts\python.exe scripts/run_autonomous_browser_model_comparison_evaluator.py --config {output_dir}/comparison_config.local.json",
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
    request_paths: Mapping[str, Mapping[str, str]],
    output_paths: Mapping[str, Mapping[str, str]],
) -> str:
    model_aliases = ", ".join(f"`{spec['alias']}`" for spec in model_specs)
    lines = [
        "# Model Comparison Packet",
        "",
        f"Packet id: `{packet_id}`",
        "",
        "## Scope",
        "",
        "- Offline packet only.",
        f"- Prepares comparison requests for {model_aliases}.",
        "- Reuses the existing compact browser-planner prompts from Phase 10 and Phase 11.",
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
        lines.append(
            f"- `{spec['scenario_label']}` / `{spec['scenario_id']}` -> `{output_paths[model_specs[0]['alias']][spec['scenario_label']]}`"
        )
    lines.extend(
        [
            "",
            "## Operator Flow",
            "",
            f"1. Build the packet into `{output_dir}`.",
            "2. Read the scenario prompt files.",
            "3. Manually run each model request and save `response.json` and `raw_planner_output.txt`.",
            f"4. Run the comparison evaluator into `{evaluation_output_dir}`.",
            "5. Run pytest.",
            "",
        ]
    )
    return "\n".join(lines)


def _build_prompt_text(scenario_id: str) -> str:
    if scenario_id == "browser_intranet_policy_research":
        return _build_phase10_policy_prompt_text()
    if scenario_id == "browser_ticket_triage_review":
        return _build_phase11_prompt_text(scenario_id)
    if scenario_id == "browser_approval_form_review":
        return _build_phase11_prompt_text(scenario_id)
    if scenario_id == "hard_policy_disambiguation":
        return _build_hard_policy_disambiguation_prompt_text()
    if scenario_id == "hard_ticket_priority_crosscheck":
        return _build_hard_ticket_priority_crosscheck_prompt_text()
    if scenario_id == "hard_approval_policy_match":
        return _build_hard_approval_policy_match_prompt_text()
    raise ValueError(f"unsupported scenario_id: {scenario_id}")


def _build_hard_policy_disambiguation_prompt_text() -> str:
    return "\n".join(
        [
            "You are generating one offline browser plan for local fixtures only.",
            "Scenario id: hard_policy_disambiguation.",
            "Goal: choose the live policy source and ignore the archived copy.",
            "Use the local fixture pages only: https://local.intranet/docs/policy-disambiguation and https://local.intranet/docs/policy; the archive decoy is https://local.intranet/docs/policy-archive.",
            "Required output schema_version: autonomous_browser_plan_v1.",
            "Required top-level fields: schema_version, plan_id, goal, scenario_id, max_actions, actions.",
            "Allowed action names: browser_open_url, browser_click, browser_extract_text, browser_snapshot.",
            "Plan skeleton: start with browser_open_url for the disambiguation page, click the current policy link, extract the current policy marker, and stop after the live source is confirmed.",
            "Do not use the archive page as the answer source.",
            "The archive copy is intentionally not the correct answer.",
            "Do not output markdown, prose, code fences, or multiple JSON objects.",
            "Return exactly one JSON object with only the plan fields.",
        ]
    )


def _build_hard_ticket_priority_crosscheck_prompt_text() -> str:
    return "\n".join(
        [
            "You are generating one offline browser plan for local fixtures only.",
            "Scenario id: hard_ticket_priority_crosscheck.",
            "Goal: identify the urgent escalation ticket by cross-checking requester tier against priority.",
            "Use the local fixture pages only: https://local.intranet/tickets/hardboard, https://local.intranet/tickets/7, and https://local.intranet/tickets/8.",
            "Required output schema_version: autonomous_browser_plan_v1.",
            "Required top-level fields: schema_version, plan_id, goal, scenario_id, max_actions, actions.",
            "Allowed action names: browser_open_url, browser_click, browser_extract_text, browser_snapshot.",
            "Plan skeleton: open the ticket board, inspect the escalation ticket, compare requester tier versus priority, and extract the urgent marker from the correct ticket.",
            "Ticket 7 is the escalation review with requester tier facilities and priority urgent; Ticket 8 is the decoy with requester tier office worker and priority low.",
            "Do not follow the decoy ticket to the final answer.",
            "Do not output markdown, prose, code fences, or multiple JSON objects.",
            "Return exactly one JSON object with only the plan fields.",
        ]
    )


def _build_hard_approval_policy_match_prompt_text() -> str:
    return "\n".join(
        [
            "You are generating one offline browser plan for local fixtures only.",
            "Scenario id: hard_approval_policy_match.",
            "Goal: confirm the local-only approval marker from the policy-matched portal page.",
            "Use the local fixture pages only: https://portal.local/portal, https://portal.local/portal/approvals, and https://portal.local/portal/approval-match.",
            "Required output schema_version: autonomous_browser_plan_v1.",
            "Required top-level fields: schema_version, plan_id, goal, scenario_id, max_actions, actions.",
            "Allowed action names: browser_open_url, browser_click, browser_extract_text, browser_snapshot.",
            "Plan skeleton: open the portal, follow the approvals queue, inspect the policy-match page, and extract the local-only approval marker.",
            "The approval-match page states request id APR-51, requester office worker, policy match confirmed, and decision note local fixtures only.",
            "Do not use any external site, mail, calendar, or non-fixture source.",
            "Do not output markdown, prose, code fences, or multiple JSON objects.",
            "Return exactly one JSON object with only the plan fields.",
        ]
    )


def _load_config(config_artifact: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config_artifact, Mapping):
        payload = dict(config_artifact)
    else:
        try:
            payload = json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))
        except OSError:
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "packet_id": None,
                "output_dir": None,
                "evaluation_output_dir": None,
                "limitations": _limitations(),
            }
        except json.JSONDecodeError:
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
            "packet_id": _safe_identifier(payload.get("packet_id", DEFAULT_PACKET_ID)),
            "output_dir": _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR)),
            "evaluation_output_dir": _safe_relative_path(payload.get("evaluation_output_dir", DEFAULT_EVALUATION_OUTPUT_DIR)),
            "limitations": _limitations(),
        }

    packet_id = _safe_identifier(payload.get("packet_id", DEFAULT_PACKET_ID))
    output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR))
    evaluation_output_dir = _safe_relative_path(payload.get("evaluation_output_dir", DEFAULT_EVALUATION_OUTPUT_DIR))
    if packet_id is None or output_dir is None or evaluation_output_dir is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "evaluation_output_dir": evaluation_output_dir,
            "limitations": _limitations(),
        }

    model_specs_value = payload.get("model_specs")
    scenario_specs_value = payload.get("scenario_specs")
    if not isinstance(model_specs_value, list) or not isinstance(scenario_specs_value, list):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "evaluation_output_dir": evaluation_output_dir,
            "limitations": _limitations(),
        }

    model_specs = _safe_model_specs(model_specs_value)
    scenario_specs = _safe_scenario_specs(scenario_specs_value)
    if model_specs is None or scenario_specs is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "evaluation_output_dir": evaluation_output_dir,
            "limitations": _limitations(),
        }
    if not model_specs or not scenario_specs:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "evaluation_output_dir": evaluation_output_dir,
            "limitations": _limitations(),
        }
    if not payload.get("no_runtime_execution") is True:
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
        "model_specs": model_specs,
        "scenario_specs": scenario_specs,
        "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
    }


def _safe_model_specs(value: list[Any]) -> tuple[dict[str, str], ...] | None:
    items: list[dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            return None
        alias = _safe_identifier(entry.get("alias"))
        model_path = _safe_relative_path(entry.get("model_path"))
        if alias is None or model_path is None:
            return None
        prompt_prefix = _safe_prompt_prefix(entry.get("prompt_prefix"))
        if prompt_prefix is None and alias == "third_model":
            prompt_prefix = "/no_think"
        model_spec = {"alias": alias, "model_path": model_path}
        if prompt_prefix is not None:
            model_spec["prompt_prefix"] = prompt_prefix
        items.append(model_spec)
    return tuple(items)


def _safe_scenario_specs(value: list[Any]) -> tuple[dict[str, Any], ...] | None:
    items: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            return None
        scenario_id = _safe_identifier(entry.get("scenario_id"))
        scenario_label = _safe_identifier(entry.get("scenario_label"))
        prompt_filename = _safe_identifier(entry.get("prompt_filename"))
        max_tokens = entry.get("max_tokens")
        if (
            scenario_id is None
            or scenario_label is None
            or prompt_filename is None
            or not isinstance(max_tokens, int)
            or isinstance(max_tokens, bool)
            or max_tokens < 1
        ):
            return None
        items.append(
            {
                "scenario_id": scenario_id,
                "scenario_label": scenario_label,
                "prompt_filename": prompt_filename,
                "max_tokens": max_tokens,
            }
        )
    return tuple(items)


def _build_commands_markdown(
    *,
    output_dir: str,
    model_specs: tuple[dict[str, str], ...],
    scenario_specs: tuple[dict[str, Any], ...],
    evaluation_output_dir: str,
) -> str:
    model_aliases = ", ".join(f"`{spec['alias']}`" for spec in model_specs)
    lines = [
        "# Model Comparison Packet Commands",
        "",
        "Codex must not launch models.",
        f"The packet prepares comparison requests for {model_aliases}.",
        "Use `planner_prompt.compact.txt` as the prompt source for each trial.",
        "The `third_model` path is documented as `models/gguf/third_model.gguf` and is not accessed by Codex.",
        "",
    ]
    for scenario_spec in scenario_specs:
        lines.extend(
            [
                f"## Read {scenario_spec['scenario_label']} Prompt",
                "```powershell",
                f"Get-Content .\\{output_dir}\\prompts\\{scenario_spec['scenario_label']}\\{scenario_spec['prompt_filename']} -Raw",
                "```",
                "",
            ]
        )
    for model_spec in model_specs:
        for scenario_spec in scenario_specs:
            lines.extend(
                [
                    f"## {model_spec['alias']} {scenario_spec['scenario_label']}",
                    "```powershell",
                    (
                        f'curl.exe --max-time 90 -sS -X POST http://127.0.0.1:8080/v1/chat/completions -H "Content-Type: application/json" '
                        f'--data-binary "@.\\{output_dir}\\{model_spec["alias"]}\\{scenario_spec["scenario_label"]}\\request.json" '
                        f'--output "@.\\{output_dir}\\{model_spec["alias"]}\\{scenario_spec["scenario_label"]}\\response.json"'
                    ),
                    "```",
                    "",
                ]
            )
    lines.extend(
        [
            "## Evaluation",
            "```powershell",
            rf".\.venv\Scripts\python.exe scripts/run_autonomous_browser_model_comparison_evaluator.py --config {output_dir}/comparison_config.local.json",
            "```",
            "",
            f"Evaluator output directory: `{evaluation_output_dir}`.",
        ]
    )
    return "\n".join(lines).rstrip() + "\n"


def _limitations() -> tuple[str, ...]:
    return (
        "offline comparison packet only",
        "manual operator model runs only",
        "no model calls by Codex",
        "no real browser execution",
        "no Playwright import in offline packet or evaluator",
        "fixture replay remains offline only",
        "not production browser automation",
    )


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


def _safe_prompt_prefix(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _build_user_prompt(prompt_text: str, prompt_prefix: str | None) -> str:
    if not prompt_prefix:
        return prompt_text
    return f"{prompt_prefix}\n{prompt_text}"


def _safe_identifier(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    if any(ch in stripped for ch in ("\\", "/", ":", "\0")):
        return None
    return stripped


def _windows_path(value: str) -> str:
    return value.replace("/", "\\")


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    return value


def _failure_summary(
    *,
    packet_id: str | None,
    output_dir: str | None,
    evaluation_output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = ModelComparisonPacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        packet_id=packet_id,
        output_dir=output_dir,
        evaluation_output_dir=evaluation_output_dir,
        model_count=0,
        scenario_count=0,
        packet_files=(),
        request_paths_path=None,
        output_paths_path=None,
        comparison_config_path=None,
        expected_raw_output_paths=(),
        commands_count=0,
        execution_status="skipped_by_design",
        limitations=limitations,
    )
    return summary.to_dict()
