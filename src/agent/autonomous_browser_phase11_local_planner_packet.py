from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any


PACKET_SCHEMA_VERSION = "autonomous_browser_phase11_local_planner_packet_v1"
PACKET_CONFIG_SCHEMA_VERSION = "autonomous_browser_phase11_local_planner_packet_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_phase11_local_planner_packet_summary_v1"
DEFAULT_PACKET_ID = "browser_phase11_local_planner_packet_v1"
DEFAULT_MODEL = "second_model"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/phase11_local_planner_packet"
DEFAULT_INGESTION_SUITE_CONFIG_PATH = "artifacts/autonomous_runtime_summaries/phase11_local_planner_packet/ingestion_suite_config.local.json"
DEFAULT_INGESTION_SUITE_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/phase11_local_planner_packet/ingestion_suite_runs"
DEFAULT_SCENARIO_IDS = (
    "browser_ticket_triage_review",
    "browser_approval_form_review",
)
ALLOWED_MODEL_IDS = (DEFAULT_MODEL,)


@dataclass(frozen=True)
class AutonomousBrowserPhase11LocalPlannerPacketSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    model_execution: bool
    real_browser_execution: bool
    packet_id: str | None
    model: str | None
    scenario_count: int
    scenario_ids: tuple[str, ...] = ()
    output_dir: str | None = None
    packet_files: tuple[str, ...] = ()
    expected_raw_output_paths: tuple[str, ...] = ()
    ingestion_suite_config_path: str | None = None
    execution_status: str = "skipped_by_design"
    post_run_commands_count: int = 0
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
            "model": self.model,
            "scenario_count": self.scenario_count,
            "scenario_ids": list(self.scenario_ids),
            "output_dir": self.output_dir,
            "packet_files": list(self.packet_files),
            "expected_raw_output_paths": list(self.expected_raw_output_paths),
            "ingestion_suite_config_path": self.ingestion_suite_config_path,
            "execution_status": self.execution_status,
            "post_run_commands_count": self.post_run_commands_count,
            "limitations": list(self.limitations),
        }


def build_autonomous_browser_phase11_local_planner_packet(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    config_result = _load_config(config_artifact)
    if config_result["status"] != "ok":
        return _failure_summary(
            packet_id=config_result.get("packet_id"),
            model=config_result.get("model"),
            scenario_ids=tuple(config_result.get("scenario_ids") or ()),
            output_dir=config_result.get("output_dir"),
            error_code=str(config_result.get("error_code") or "config_validation_failed"),
            limitations=tuple(config_result.get("limitations") or _limitations()),
        )

    packet_id = str(config_result["packet_id"])
    model = str(config_result["model"])
    scenario_ids = tuple(str(item) for item in config_result["scenario_ids"])
    output_dir = str(config_result["output_dir"])
    ingestion_suite_config_path = str(config_result["ingestion_suite_config_path"])
    limitations = tuple(config_result.get("limitations") or _limitations())

    packet_dir = repo / output_dir
    packet_dir.mkdir(parents=True, exist_ok=True)

    packet_files: list[str] = []
    request_paths: dict[str, str] = {}
    output_paths: dict[str, str] = {}
    prompt_paths: dict[str, str] = {}
    scenario_packets: list[dict[str, Any]] = []

    for scenario_id in scenario_ids:
        prompt_filename = _prompt_filename_for_scenario(scenario_id)
        scenario_dir_name = _scenario_dir_name(scenario_id)
        scenario_dir = packet_dir / scenario_dir_name
        scenario_dir.mkdir(parents=True, exist_ok=True)

        prompt_path = packet_dir / prompt_filename
        prompt_text = _build_prompt_text(scenario_id)
        _write_text(prompt_path, prompt_text + "\n")
        prompt_path_relative = f"{output_dir}/{prompt_filename}"
        prompt_paths[scenario_id] = prompt_path_relative
        packet_files.append(prompt_path_relative)

        request_path = scenario_dir / "request.json"
        request_payload = _build_request_payload(
            packet_id=packet_id,
            scenario_id=scenario_id,
            model=model,
            prompt_text=prompt_text,
            prompt_path=prompt_path_relative,
        )
        _write_json(request_path, request_payload)
        request_path_relative = f"{output_dir}/{scenario_dir_name}/request.json"
        request_paths[scenario_id] = request_path_relative
        packet_files.append(request_path_relative)

        raw_output_path_relative = f"{output_dir}/{scenario_dir_name}/raw_planner_output.txt"
        output_paths[scenario_id] = raw_output_path_relative

        scenario_packets.append(
            {
                "scenario_id": scenario_id,
                "prompt_path": prompt_path_relative,
                "request_path": request_path_relative,
                "raw_output_path": raw_output_path_relative,
            }
        )

    _write_json(packet_dir / "request_paths.json", request_paths)
    packet_files.append(f"{output_dir}/request_paths.json")

    _write_json(packet_dir / "output_paths.json", output_paths)
    packet_files.append(f"{output_dir}/output_paths.json")

    ingestion_suite_config = _build_ingestion_suite_config(
        packet_id=packet_id,
        expected_raw_output_paths=tuple(output_paths[scenario_id] for scenario_id in scenario_ids),
    )
    _write_json(packet_dir / "ingestion_suite_config.local.json", ingestion_suite_config)
    packet_files.append(f"{output_dir}/ingestion_suite_config.local.json")

    commands = _build_commands(
        output_dir=output_dir,
        request_paths=request_paths,
        output_paths=output_paths,
        prompt_paths=prompt_paths,
        ingestion_suite_config_path=ingestion_suite_config_path,
    )
    _write_json(packet_dir / "commands.json", {"commands": commands})
    packet_files.append(f"{output_dir}/commands.json")

    commands_md = _build_commands_markdown(commands, output_dir=output_dir)
    _write_text(packet_dir / "commands.md", commands_md)
    packet_files.append(f"{output_dir}/commands.md")

    readme_text = _build_readme(
        packet_id=packet_id,
        model=model,
        scenario_ids=scenario_ids,
        output_dir=output_dir,
        ingestion_suite_config_path=ingestion_suite_config_path,
        expected_raw_output_paths=tuple(output_paths[scenario_id] for scenario_id in scenario_ids),
    )
    _write_text(packet_dir / "README.md", readme_text)
    packet_files.append(f"{output_dir}/README.md")

    packet_json = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "packet_id": packet_id,
        "model": model,
        "scenario_count": len(scenario_ids),
        "scenario_ids": list(scenario_ids),
        "scenario_packets": scenario_packets,
        "ingestion_suite_config_path": ingestion_suite_config_path,
        "limitations": list(limitations),
    }
    _write_json(packet_dir / "autonomous_browser_phase11_local_planner_packet.json", packet_json)
    packet_files.append(f"{output_dir}/autonomous_browser_phase11_local_planner_packet.json")

    summary_relative_path = f"{output_dir}/autonomous_browser_phase11_local_planner_packet_summary.json"
    packet_files.append(summary_relative_path)
    summary = AutonomousBrowserPhase11LocalPlannerPacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="succeeded",
        error_code=None,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        packet_id=packet_id,
        model=model,
        scenario_count=len(scenario_ids),
        scenario_ids=scenario_ids,
        output_dir=output_dir,
        packet_files=tuple(packet_files),
        expected_raw_output_paths=tuple(output_paths[scenario_id] for scenario_id in scenario_ids),
        ingestion_suite_config_path=ingestion_suite_config_path,
        execution_status="skipped_by_design",
        post_run_commands_count=len(commands),
        limitations=limitations,
    )
    summary_payload = summary.to_dict()
    _write_json(packet_dir / "autonomous_browser_phase11_local_planner_packet_summary.json", summary_payload)
    return summary_payload


def write_autonomous_browser_phase11_local_planner_packet_summary(
    summary: Mapping[str, Any],
    output_dir: str | Path,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_phase11_local_planner_packet_summary.json"
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
                "model": None,
                "scenario_ids": (),
                "output_dir": None,
                "limitations": _limitations(),
            }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": None,
            "model": None,
            "scenario_ids": (),
            "output_dir": None,
            "limitations": _limitations(),
        }
    if str(payload.get("schema_version", "")) != PACKET_CONFIG_SCHEMA_VERSION:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": _safe_identifier(payload.get("packet_id", DEFAULT_PACKET_ID)),
            "model": _safe_identifier(payload.get("model", DEFAULT_MODEL)),
            "scenario_ids": _safe_scenario_ids(payload.get("scenario_ids")),
            "output_dir": _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR)),
            "limitations": _limitations(),
        }

    packet_id = _safe_identifier(payload.get("packet_id", DEFAULT_PACKET_ID))
    model = _safe_identifier(payload.get("model", DEFAULT_MODEL))
    output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR))
    ingestion_suite_config_path = _safe_relative_path(
        payload.get("ingestion_suite_config_path", DEFAULT_INGESTION_SUITE_CONFIG_PATH)
    )
    scenario_ids = _safe_scenario_ids(payload.get("scenario_ids"))

    if packet_id is None or model is None or output_dir is None or ingestion_suite_config_path is None or scenario_ids is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "model": model,
            "scenario_ids": scenario_ids or (),
            "output_dir": output_dir,
            "limitations": _limitations(),
        }
    if model not in ALLOWED_MODEL_IDS:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "model": model,
            "scenario_ids": scenario_ids,
            "output_dir": output_dir,
            "limitations": _limitations(),
        }
    if tuple(scenario_ids) != DEFAULT_SCENARIO_IDS:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "model": model,
            "scenario_ids": scenario_ids,
            "output_dir": output_dir,
            "limitations": _limitations(),
        }
    if payload.get("no_runtime_execution") is not True:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "model": model,
            "scenario_ids": scenario_ids,
            "output_dir": output_dir,
            "limitations": _limitations(),
        }

    return {
        "status": "ok",
        "packet_id": packet_id,
        "model": model,
        "scenario_ids": scenario_ids,
        "output_dir": output_dir,
        "ingestion_suite_config_path": ingestion_suite_config_path,
        "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
    }


def _build_request_payload(
    *,
    packet_id: str,
    scenario_id: str,
    model: str,
    prompt_text: str,
    prompt_path: str,
) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a local browser planner."},
            {"role": "user", "content": prompt_text},
        ],
        "temperature": 0,
        "max_tokens": 256,
        "stream": False,
        "metadata": {
            "packet_id": packet_id,
            "scenario_id": scenario_id,
            "prompt_path": prompt_path,
        },
    }


def _build_ingestion_suite_config(*, packet_id: str, expected_raw_output_paths: tuple[str, ...]) -> dict[str, Any]:
    return {
        "schema_version": "autonomous_browser_planner_output_ingestion_suite_config_v1",
        "suite_id": f"{packet_id}_ingestion_suite_v1",
        "captured_outputs": list(expected_raw_output_paths),
        "replay_mode": "dry_run",
        "output_dir": DEFAULT_INGESTION_SUITE_OUTPUT_DIR,
        "expected_min_ingested": 2,
        "expected_max_rejected": 0,
        "limitations": [
            "phase 11 local planner packet only",
            "manual second_model runs only",
            "no model calls by Codex",
            "no real browser execution",
            "fixture replay remains offline only",
            "not production browser automation",
        ],
    }


def _build_commands(
    *,
    output_dir: str,
    request_paths: dict[str, str],
    output_paths: dict[str, str],
    prompt_paths: dict[str, str],
    ingestion_suite_config_path: str,
) -> list[dict[str, Any]]:
    ticket_request_path = _windows_path(request_paths["browser_ticket_triage_review"])
    approval_request_path = _windows_path(request_paths["browser_approval_form_review"])
    ticket_output_path = _windows_path(output_paths["browser_ticket_triage_review"])
    approval_output_path = _windows_path(output_paths["browser_approval_form_review"])
    ticket_prompt_path = _windows_path(prompt_paths["browser_ticket_triage_review"])
    approval_prompt_path = _windows_path(prompt_paths["browser_approval_form_review"])
    ticket_response_path = ticket_output_path.replace("raw_planner_output.txt", "response.json")
    approval_response_path = approval_output_path.replace("raw_planner_output.txt", "response.json")

    return [
        {
            "id": "build_phase11_packet",
            "manual_only": False,
            "description": "Build the Phase 11 dual-scenario local planner packet.",
            "command": r".\.venv\Scripts\python.exe scripts/build_autonomous_browser_phase11_local_planner_packet.py --config configs/autonomous_runtime/browser_phase11_local_planner_packet.example.json",
        },
        {
            "id": "read_ticket_triage_prompt",
            "manual_only": True,
            "description": "Read the ticket triage compact prompt before the manual model run.",
            "command": f'Get-Content "{ticket_prompt_path}" -Raw',
        },
        {
            "id": "ticket_triage_curl_request",
            "manual_only": True,
            "description": "Run the ticket triage manual model call with curl.exe and save the response JSON.",
            "command": (
                "# Manual operator only. Codex must not launch models. Do not use Invoke-RestMethod for planner generation.\n"
                f'curl.exe --max-time 90 -sS -X POST http://127.0.0.1:8080/v1/chat/completions -H "Content-Type: application/json" --data-binary "@{ticket_request_path}" --output "{ticket_response_path}"'
            ),
        },
        {
            "id": "ticket_triage_extract_content",
            "manual_only": True,
            "description": "Extract response.choices[0].message.content into raw_planner_output.txt for ticket triage.",
            "command": (
                f'$response = Get-Content "{ticket_response_path}" -Raw | ConvertFrom-Json\n'
                f'$response.choices[0].message.content | Set-Content "{ticket_output_path}" -Encoding utf8'
            ),
        },
        {
            "id": "read_approval_review_prompt",
            "manual_only": True,
            "description": "Read the approval review compact prompt before the manual model run.",
            "command": f'Get-Content "{approval_prompt_path}" -Raw',
        },
        {
            "id": "approval_review_curl_request",
            "manual_only": True,
            "description": "Run the approval review manual model call with curl.exe and save the response JSON.",
            "command": (
                "# Manual operator only. Codex must not launch models. Do not use Invoke-RestMethod for planner generation.\n"
                f'curl.exe --max-time 90 -sS -X POST http://127.0.0.1:8080/v1/chat/completions -H "Content-Type: application/json" --data-binary "@{approval_request_path}" --output "{approval_response_path}"'
            ),
        },
        {
            "id": "approval_review_extract_content",
            "manual_only": True,
            "description": "Extract response.choices[0].message.content into raw_planner_output.txt for approval review.",
            "command": (
                f'$response = Get-Content "{approval_response_path}" -Raw | ConvertFrom-Json\n'
                f'$response.choices[0].message.content | Set-Content "{approval_output_path}" -Encoding utf8'
            ),
        },
        {
            "id": "run_ingestion_suite_dry_run",
            "manual_only": False,
            "description": "Run the captured-output ingestion suite in dry-run mode.",
            "command": r".\.venv\Scripts\python.exe scripts/run_autonomous_browser_planner_output_ingestion_suite.py --config artifacts/autonomous_runtime_summaries/phase11_local_planner_packet/ingestion_suite_config.local.json",
        },
        {
            "id": "run_ingestion_suite_fixture",
            "manual_only": False,
            "description": "Run the captured-output ingestion suite with fixture execution.",
            "command": r".\.venv\Scripts\python.exe scripts/run_autonomous_browser_planner_output_ingestion_suite.py --config artifacts/autonomous_runtime_summaries/phase11_local_planner_packet/ingestion_suite_config.local.json --execute-fixture",
        },
        {
            "id": "run_pytest",
            "manual_only": False,
            "description": "Run the offline test suite.",
            "command": r".\.venv\Scripts\python.exe -m pytest",
        },
    ]


def _build_commands_markdown(commands: list[dict[str, Any]], *, output_dir: str) -> str:
    lines = [
        "# Phase 11 Local Planner Packet Commands",
        "",
        "Codex must not launch models.",
        "Use `planner_prompt.ticket_triage.compact.txt` and `planner_prompt.approval_review.compact.txt` as the prompt sources for the two scenarios.",
        "Do not use Invoke-RestMethod for planner generation.",
        "A human operator may run the local planner separately and save each model output as text.",
        f"The packet output directory is `{output_dir}`.",
        "",
    ]
    for command in commands:
        lines.extend(
            [
                f"## {command['id']}",
                command["description"],
                "```powershell",
                command["command"],
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _build_readme(
    *,
    packet_id: str,
    model: str,
    scenario_ids: tuple[str, ...],
    output_dir: str,
    ingestion_suite_config_path: str,
    expected_raw_output_paths: tuple[str, ...],
) -> str:
    lines = [
        "# Phase 11 Local Planner Packet",
        "",
        f"Packet id: `{packet_id}`",
        f"Model: `{model}`",
        f"Scenario count: `{len(scenario_ids)}`",
        "",
        "## Scope",
        "",
        "- manual `second_model` runs for two local fixture scenarios",
        "- compact prompt files for ticket triage and approval review",
        "- captured-output ingestion suite validates and replays both outputs offline",
        "- purpose is diversity evidence across the new Phase 11 browser fixture scenarios",
        "",
        "## Safety",
        "",
        "- Codex must not launch models.",
        "- Do not use Invoke-RestMethod for planner generation.",
        "- No real browser execution.",
        "- Fixture replay remains offline only.",
        "- No production readiness claim.",
        "",
        "## Scenarios",
        "",
    ]
    for scenario_id, raw_output_path in zip(scenario_ids, expected_raw_output_paths, strict=True):
        lines.append(f"- `{scenario_id}` -> `{raw_output_path}`")
    lines.extend(
        [
            "",
            "## Ingestion Suite",
            "",
            f"- Config: `{ingestion_suite_config_path}`",
            f"- Offline ingestion output dir: `{DEFAULT_INGESTION_SUITE_OUTPUT_DIR}`",
            "",
            "## Operator Flow",
            "",
            f"1. Build the packet into `{output_dir}`.",
            "2. Read the scenario-specific compact prompt file.",
            "3. Run the local planner manually with `curl.exe --max-time`.",
            "4. Save each model `message.content` to `raw_planner_output.txt`.",
            "5. Run the ingestion suite in dry-run mode.",
            "6. Run the ingestion suite with fixture execution.",
            "7. Run pytest.",
            "",
        ]
    )
    return "\n".join(lines)


def _failure_summary(
    *,
    packet_id: str | None,
    model: str | None,
    scenario_ids: tuple[str, ...],
    output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = AutonomousBrowserPhase11LocalPlannerPacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        packet_id=packet_id,
        model=model,
        scenario_count=len(scenario_ids),
        scenario_ids=scenario_ids,
        output_dir=output_dir,
        packet_files=(),
        expected_raw_output_paths=(),
        ingestion_suite_config_path=None,
        execution_status="skipped_by_design",
        post_run_commands_count=0,
        limitations=limitations,
    )
    return summary.to_dict()


def _limitations() -> tuple[str, ...]:
    return (
        "phase 11 local planner packet only",
        "manual second_model runs only",
        "no model calls by Codex",
        "no real browser execution",
        "fixture replay remains offline only",
        "not production browser automation",
    )


def _build_prompt_text(scenario_id: str) -> str:
    if scenario_id == "browser_ticket_triage_review":
        skeleton = """{
"schema_version": "autonomous_browser_plan_v1",
"plan_id": "browser_ticket_triage_review_plan_v1",
"goal": "Review the ticket board and capture ticket detail evidence.",
"scenario_id": "browser_ticket_triage_review",
"max_actions": 4,
"actions": [
{
"step_id": "open_ticket_board",
"action_name": "browser_open_url",
"parameters": {
"url": "https://local.intranet/tickets"
},
"expected_text": "Ticket Board"
},
{
"step_id": "open_ticket_detail",
"action_name": "browser_click",
"parameters": {
"target_text": "Ticket 1"
},
"expected_text": "Quarterly Access Review",
"expected_url": "https://local.intranet/tickets/1"
},
{
"step_id": "extract_ticket_detail",
"action_name": "browser_extract_text",
"parameters": {},
"expected_text": "Priority: high. Local fixture only."
},
{
"step_id": "snapshot_ticket_detail",
"action_name": "browser_snapshot",
"parameters": {},
"expected_text": "Local fixture only."
}
]
}"""
        markers = "Ticket board, Ticket 1, Priority, Local fixture only"
        goal = "Review the local ticket board fixture and capture ticket detail evidence."
    elif scenario_id == "browser_approval_form_review":
        skeleton = """{
"schema_version": "autonomous_browser_plan_v1",
"plan_id": "browser_approval_form_review_plan_v1",
"goal": "Review the approvals queue and approval request evidence.",
"scenario_id": "browser_approval_form_review",
"max_actions": 7,
"actions": [
{
"step_id": "open_portal_home",
"action_name": "browser_open_url",
"parameters": {
"url": "https://portal.local/portal"
},
"expected_text": "Approvals queue"
},
{
"step_id": "click_approvals_queue",
"action_name": "browser_click",
"parameters": {
"target_text": "Approvals queue"
},
"expected_text": "Pending approval check",
"expected_url": "https://portal.local/portal/approvals"
},
{
"step_id": "open_request_form",
"action_name": "browser_open_url",
"parameters": {
"url": "https://local-intranet.test/portal/request"
},
"expected_text": "Approval request"
},
{
"step_id": "snapshot_request_form",
"action_name": "browser_snapshot",
"parameters": {},
"expected_text": "Approval request"
},
{
"step_id": "open_policy_docs",
"action_name": "browser_open_url",
"parameters": {
"url": "https://docs.local/docs/policy"
},
"expected_text": "Allowed activity"
},
{
"step_id": "extract_policy_docs",
"action_name": "browser_extract_text",
"parameters": {},
"expected_text": "fixture-backed"
},
{
"step_id": "snapshot_policy_docs",
"action_name": "browser_snapshot",
"parameters": {},
"expected_text": "fixture-backed"
}
]
}"""
        markers = "Approvals queue, Approval request, Allowed activity, fixture-backed"
        goal = "Review the local approvals and policy fixtures and capture approval-request evidence."
    else:
        raise ValueError(f"unsupported scenario_id: {scenario_id}")

    return "\n".join(
        [
            "Return exactly one valid JSON object.",
            "No markdown.",
            "No code fences.",
            "No explanations.",
            "Root object must include schema_version, plan_id, goal, scenario_id, max_actions, and actions.",
            "schema_version must be autonomous_browser_plan_v1.",
            f"scenario_id must be {scenario_id}.",
            "Use only local fixture-backed browser actions.",
            "Do not use localhost or 127.0.0.1 in the returned plan.",
            f"Markers to preserve in the plan: {markers}.",
            "Allowed actions: browser_open_url, browser_click, browser_extract_text, browser_fill, browser_submit, browser_wait, browser_search, browser_snapshot.",
            "Allowed fixture hosts: local.intranet, local-intranet.test, docs.local, portal.local.",
            f"Goal: {goal}",
            "Use this exact minimal target skeleton:",
            skeleton,
        ]
    )


def _prompt_filename_for_scenario(scenario_id: str) -> str:
    if scenario_id == "browser_ticket_triage_review":
        return "planner_prompt.ticket_triage.compact.txt"
    if scenario_id == "browser_approval_form_review":
        return "planner_prompt.approval_review.compact.txt"
    raise ValueError(f"unsupported scenario_id: {scenario_id}")


def _scenario_dir_name(scenario_id: str) -> str:
    if scenario_id == "browser_ticket_triage_review":
        return "ticket_triage"
    if scenario_id == "browser_approval_form_review":
        return "approval_review"
    raise ValueError(f"unsupported scenario_id: {scenario_id}")


def _safe_scenario_ids(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, list) or len(value) != len(DEFAULT_SCENARIO_IDS):
        return None
    cleaned: list[str] = []
    for item in value:
        identifier = _safe_identifier(item)
        if identifier is None:
            return None
        cleaned.append(identifier)
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
