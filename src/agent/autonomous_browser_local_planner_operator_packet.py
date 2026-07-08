from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_planner_packet import build_autonomous_browser_planner_packet


PACKET_SCHEMA_VERSION = "autonomous_browser_local_planner_operator_packet_v1"
PACKET_CONFIG_SCHEMA_VERSION = "autonomous_browser_local_planner_operator_packet_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_local_planner_operator_packet_summary_v1"
DEFAULT_OPERATOR_PACKET_ID = "browser_local_planner_operator_packet_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/local_planner_operator_packet"
DEFAULT_RECOMMENDED_PLANNER_MODEL = "second_model"
ALLOWED_MODEL_IDS = ("first_model", "second_model")
DEFAULT_PLANNER_PACKET_CONFIG_PATH = "configs/autonomous_runtime/browser_planner_packet.example.json"
DEFAULT_INGESTION_SUITE_CONFIG_PATH = "configs/autonomous_runtime/browser_planner_output_ingestion_suite.example.json"
DEFAULT_EXPECTED_RAW_OUTPUT_PATH = "artifacts/autonomous_runtime_summaries/local_planner_operator_packet/raw_planner_output.txt"


@dataclass(frozen=True)
class AutonomousBrowserLocalPlannerOperatorPacketSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    execution_status: str
    model_execution: bool
    real_browser_execution: bool
    operator_packet_id: str | None
    output_dir: str | None
    packet_files: tuple[str, ...] = ()
    expected_raw_output_path: str | None = None
    post_run_commands_count: int = 0
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "execution_status": self.execution_status,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "operator_packet_id": self.operator_packet_id,
            "output_dir": self.output_dir,
            "packet_files": list(self.packet_files),
            "expected_raw_output_path": self.expected_raw_output_path,
            "post_run_commands_count": self.post_run_commands_count,
            "limitations": list(self.limitations),
        }


def build_autonomous_browser_local_planner_operator_packet(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    config_result = _load_config(config_artifact)
    if config_result["status"] != "ok":
        return _failure_summary(
            operator_packet_id=config_result.get("operator_packet_id"),
            output_dir=config_result.get("output_dir"),
            error_code=str(config_result.get("error_code") or "config_validation_failed"),
            limitations=tuple(config_result.get("limitations") or _limitations()),
        )

    operator_packet_id = str(config_result["operator_packet_id"])
    output_dir = str(config_result["output_dir"])
    planner_packet_config_path = str(config_result["planner_packet_config_path"])
    expected_raw_output_path = str(config_result["expected_raw_output_path"])
    expected_ingestion_suite_config_path = str(config_result["expected_ingestion_suite_config_path"])
    model_ids_allowed = tuple(config_result["model_ids_allowed"])
    recommended_model = str(config_result["default_recommended_planner_model"])

    if not (repo / planner_packet_config_path).is_file() or not (repo / expected_ingestion_suite_config_path).is_file():
        return _failure_summary(
            operator_packet_id=operator_packet_id,
            output_dir=output_dir,
            error_code="config_validation_failed",
            limitations=tuple(config_result.get("limitations") or _limitations()),
        )

    planner_packet = build_autonomous_browser_planner_packet()
    packet_dir = repo / output_dir
    packet_dir.mkdir(parents=True, exist_ok=True)

    packet_files: list[str] = []

    operator_packet_payload = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "operator_packet_id": operator_packet_id,
        "planner_packet_config_path": planner_packet_config_path,
        "expected_raw_output_path": expected_raw_output_path,
        "expected_ingestion_suite_config_path": expected_ingestion_suite_config_path,
        "model_ids_allowed": list(model_ids_allowed),
        "default_recommended_planner_model": recommended_model,
        "limitations": list(_limitations()),
    }
    _write_json(packet_dir / "operator_packet.json", operator_packet_payload)
    packet_files.append(f"{output_dir}/operator_packet.json")

    readme_text = _build_readme(
        operator_packet_id=operator_packet_id,
        planner_packet_config_path=planner_packet_config_path,
        expected_raw_output_path=expected_raw_output_path,
        expected_ingestion_suite_config_path=expected_ingestion_suite_config_path,
        model_ids_allowed=model_ids_allowed,
        recommended_model=recommended_model,
    )
    _write_text(packet_dir / "README.md", readme_text)
    packet_files.append(f"{output_dir}/README.md")

    prompt_text = str(planner_packet.get("prompt_text", "")).strip()
    _write_text(packet_dir / "planner_prompt.txt", prompt_text + "\n")
    packet_files.append(f"{output_dir}/planner_prompt.txt")

    expected_paths_payload = {
        "expected_raw_output_path": expected_raw_output_path,
        "expected_ingestion_suite_config_path": expected_ingestion_suite_config_path,
        "planner_packet_config_path": planner_packet_config_path,
    }
    _write_json(packet_dir / "expected_output_paths.json", expected_paths_payload)
    packet_files.append(f"{output_dir}/expected_output_paths.json")

    commands = _build_commands(
        planner_packet_config_path=planner_packet_config_path,
        expected_raw_output_path=expected_raw_output_path,
        expected_ingestion_suite_config_path=expected_ingestion_suite_config_path,
    )
    _write_json(packet_dir / "commands.json", {"commands": commands})
    packet_files.append(f"{output_dir}/commands.json")

    commands_md = _build_commands_markdown(commands)
    _write_text(packet_dir / "commands.md", commands_md)
    packet_files.append(f"{output_dir}/commands.md")

    summary_path_relative = f"{output_dir}/autonomous_browser_local_planner_operator_packet_summary.json"
    packet_files.append(summary_path_relative)
    summary = AutonomousBrowserLocalPlannerOperatorPacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="succeeded",
        error_code=None,
        no_runtime_execution=True,
        execution_status="skipped_by_design",
        model_execution=False,
        real_browser_execution=False,
        operator_packet_id=operator_packet_id,
        output_dir=output_dir,
        packet_files=tuple(packet_files),
        expected_raw_output_path=expected_raw_output_path,
        post_run_commands_count=len(commands),
        limitations=_limitations(),
    )
    summary_payload = summary.to_dict()
    _write_json(packet_dir / "autonomous_browser_local_planner_operator_packet_summary.json", summary_payload)
    return summary_payload


def write_autonomous_browser_local_planner_operator_packet_summary(
    summary: Mapping[str, Any],
    output_dir: str | Path,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_local_planner_operator_packet_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _load_config(config_artifact: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config_artifact, Mapping):
        payload = dict(config_artifact)
    else:
        try:
            payload = json.loads(Path(config_artifact).read_text(encoding="utf-8"))
        except OSError:
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "limitations": _limitations(),
            }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "limitations": _limitations(),
        }
    if str(payload.get("schema_version", "")) != PACKET_CONFIG_SCHEMA_VERSION:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "limitations": _limitations(),
        }
    if payload.get("no_runtime_execution") is not True:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "limitations": _limitations(),
        }
    operator_packet_id = _safe_identifier(payload.get("operator_packet_id", DEFAULT_OPERATOR_PACKET_ID), "operator_packet_id")
    if not operator_packet_id:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "limitations": _limitations(),
        }

    planner_packet_config_path = _safe_relative_path(payload.get("planner_packet_config_path", DEFAULT_PLANNER_PACKET_CONFIG_PATH), "planner_packet_config_path")
    expected_raw_output_path = _safe_relative_path(payload.get("expected_raw_output_path", DEFAULT_EXPECTED_RAW_OUTPUT_PATH), "expected_raw_output_path")
    output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir")
    expected_ingestion_suite_config_path = _safe_relative_path(
        payload.get("expected_ingestion_suite_config_path", DEFAULT_INGESTION_SUITE_CONFIG_PATH),
        "expected_ingestion_suite_config_path",
    )
    model_ids_allowed = payload.get("model_ids_allowed")
    recommended_model = _safe_identifier(payload.get("default_recommended_planner_model", DEFAULT_RECOMMENDED_PLANNER_MODEL), "default_recommended_planner_model")

    if output_dir is None or planner_packet_config_path is None or expected_raw_output_path is None or expected_ingestion_suite_config_path is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "operator_packet_id": operator_packet_id,
            "output_dir": output_dir,
            "limitations": _limitations(),
        }
    if recommended_model != DEFAULT_RECOMMENDED_PLANNER_MODEL:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "operator_packet_id": operator_packet_id,
            "output_dir": output_dir,
            "limitations": _limitations(),
        }
    if not isinstance(model_ids_allowed, list) or sorted(str(item) for item in model_ids_allowed) != sorted(ALLOWED_MODEL_IDS):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "operator_packet_id": operator_packet_id,
            "output_dir": output_dir,
            "limitations": _limitations(),
        }

    return {
        "status": "ok",
        "operator_packet_id": operator_packet_id,
        "planner_packet_config_path": planner_packet_config_path,
        "expected_raw_output_path": expected_raw_output_path,
        "expected_ingestion_suite_config_path": expected_ingestion_suite_config_path,
        "model_ids_allowed": tuple(str(item) for item in model_ids_allowed),
        "default_recommended_planner_model": recommended_model,
        "output_dir": output_dir,
        "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
    }


def _existing_relative_file(path: Path) -> bool:
    return path.is_file() and not path.is_absolute() and ".." not in path.parts


def _build_commands(
    *,
    planner_packet_config_path: str,
    expected_raw_output_path: str,
    expected_ingestion_suite_config_path: str,
) -> list[dict[str, Any]]:
    return [
        {
            "id": "build_planner_packet",
            "manual_only": False,
            "description": "Build the offline planner packet.",
            "command": r".\.venv\Scripts\python.exe scripts/build_autonomous_browser_planner_packet.py --config " + planner_packet_config_path,
        },
        {
            "id": "manual_model_run",
            "manual_only": True,
            "description": "Human operator runs the local planner separately and saves raw stdout as text.",
            "command": (
                "# Manual operator step only: run the local planner model separately, choose second_model by default, "
                f"and save JSON-only stdout to {expected_raw_output_path}."
            ),
        },
        {
            "id": "ingest_dry_run",
            "manual_only": False,
            "description": "Validate and ingest the captured planner output in dry-run mode.",
            "command": r".\.venv\Scripts\python.exe scripts/ingest_autonomous_browser_planner_output.py --config configs/autonomous_runtime/browser_planner_output_ingestion.example.json",
        },
        {
            "id": "ingest_fixture",
            "manual_only": False,
            "description": "Validate and ingest the captured planner output with fixture replay.",
            "command": r".\.venv\Scripts\python.exe scripts/ingest_autonomous_browser_planner_output.py --config configs/autonomous_runtime/browser_planner_output_ingestion.example.json --execute-fixture",
        },
        {
            "id": "run_ingestion_suite",
            "manual_only": False,
            "description": "Run the captured-output ingestion suite.",
            "command": r".\.venv\Scripts\python.exe scripts/run_autonomous_browser_planner_output_ingestion_suite.py --config " + expected_ingestion_suite_config_path,
        },
        {
            "id": "run_pytest",
            "manual_only": False,
            "description": "Run the offline test suite.",
            "command": r".\.venv\Scripts\python.exe -m pytest",
        },
    ]


def _build_commands_markdown(commands: list[dict[str, Any]]) -> str:
    lines = [
        "# Local Planner Operator Commands",
        "",
        "Codex must not launch models.",
        "A human operator may run the local planner separately and save raw output as text.",
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
    operator_packet_id: str,
    planner_packet_config_path: str,
    expected_raw_output_path: str,
    expected_ingestion_suite_config_path: str,
    model_ids_allowed: tuple[str, ...],
    recommended_model: str,
) -> str:
    lines = [
        "# Local Planner Operator Packet",
        "",
        f"Operator packet id: `{operator_packet_id}`",
        "",
        "## Safety",
        "",
        "- Codex must not launch models.",
        "- A human operator may run the local planner separately.",
        f"- Save raw model output as text at `{expected_raw_output_path}`.",
        "- No secrets in prompt or output.",
        "- Expected model output is JSON only matching `autonomous_browser_plan_v1`.",
        "- No external URLs, no localhost/127.0.0.1, no file URLs, no credentials, no local paths.",
        "- No real browser execution.",
        "",
        "## Allowed Models",
        "",
        f"- `{', '.join(model_ids_allowed)}`",
        f"- Recommended planner model: `{recommended_model}`",
        "",
        "## Packet Inputs",
        "",
        f"- Planner packet config: `{planner_packet_config_path}`",
        f"- Ingestion suite config: `{expected_ingestion_suite_config_path}`",
        "",
        "## Verifier",
        "",
        "The existing captured-output ingestion suite is the verifier for the saved raw text output.",
        "",
        "## Operator Flow",
        "",
        "1. Build the planner packet.",
        "2. Run the local planner manually and save stdout as text.",
        "3. Ingest the captured output in dry-run mode.",
        "4. Ingest the captured output with fixture replay if needed.",
        "5. Run the captured-output ingestion suite.",
        "6. Run pytest.",
        "",
    ]
    return "\n".join(lines)


def _failure_summary(
    *,
    operator_packet_id: str | None,
    output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = AutonomousBrowserLocalPlannerOperatorPacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        no_runtime_execution=True,
        execution_status="skipped_by_design",
        model_execution=False,
        real_browser_execution=False,
        operator_packet_id=operator_packet_id,
        output_dir=output_dir,
        packet_files=(),
        expected_raw_output_path=None,
        post_run_commands_count=0,
        limitations=limitations,
    )
    return summary.to_dict()


def _limitations() -> tuple[str, ...]:
    return (
        "guarded operator packet only",
        "future manual local planner runs only",
        "no model calls",
        "no real browser execution",
        "captured output verifier remains separate",
        "not production browser automation",
    )


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


def _safe_identifier(value: Any, label: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    if any(ch in stripped for ch in ("\\", "/", ":", "\0")):
        return None
    return stripped


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
