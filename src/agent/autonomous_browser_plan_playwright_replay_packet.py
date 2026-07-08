from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_planner_output_ingestion import extract_autonomous_browser_plan_candidate
from .autonomous_browser_plan_validation import ALLOWED_BROWSER_HOSTS, validate_autonomous_browser_plan


PACKET_SCHEMA_VERSION = "autonomous_browser_plan_playwright_replay_packet_v1"
PACKET_CONFIG_SCHEMA_VERSION = "autonomous_browser_plan_playwright_replay_packet_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_plan_playwright_replay_packet_summary_v1"
DEFAULT_PACKET_ID = "browser_plan_playwright_replay_packet_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_plan_playwright_replay_packet"
DEFAULT_SOURCE_OUTPUT_PATH = (
    "artifacts/autonomous_runtime_summaries/local_planner_repeated_trials_packet/trial_01/raw_planner_output.txt"
)


@dataclass(frozen=True)
class AutonomousBrowserPlanPlaywrightReplayPacketSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    model_execution: bool
    real_browser_execution: bool
    source_output_path: str | None
    extracted_plan_id: str | None
    validation_status: str
    actions_total: int
    output_dir: str | None
    packet_files: tuple[str, ...] = ()
    future_operator_guard_required: bool = True
    diagnostics: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "source_output_path": self.source_output_path,
            "extracted_plan_id": self.extracted_plan_id,
            "validation_status": self.validation_status,
            "actions_total": self.actions_total,
            "output_dir": self.output_dir,
            "packet_files": list(self.packet_files),
            "future_operator_guard_required": self.future_operator_guard_required,
            "diagnostics": _jsonable(self.diagnostics),
            "limitations": list(self.limitations),
        }


def build_autonomous_browser_plan_playwright_replay_packet(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    config_result = _load_config(config_artifact)
    output_dir = config_result.get("output_dir")
    if config_result["status"] != "ok":
        return _failure_summary(
            source_output_path=config_result.get("source_output_path"),
            extracted_plan_id=config_result.get("extracted_plan_id"),
            validation_status=str(config_result.get("validation_status") or "skipped"),
            actions_total=_int(config_result.get("actions_total")),
            output_dir=output_dir if isinstance(output_dir, str) else None,
            error_code=str(config_result.get("error_code") or "config_validation_failed"),
            diagnostics=_failure_diagnostics(config_result),
            limitations=tuple(config_result.get("limitations") or _limitations()),
            repo_root=repo,
        )

    packet_id = str(config_result["packet_id"])
    source_output_path = str(config_result["source_output_path"])
    output_dir = str(config_result["output_dir"])
    packet_dir = repo / output_dir

    try:
        raw_text = (repo / source_output_path).read_text(encoding="utf-8-sig")
    except OSError:
        return _failure_summary(
            source_output_path=source_output_path,
            extracted_plan_id=None,
            validation_status="skipped",
            actions_total=0,
            output_dir=output_dir,
            error_code="source_output_read_failed",
            diagnostics={
                "source_output": {
                    "finding_type": "source_output_read_failed",
                    "path": "source_output_path",
                }
            },
            limitations=_limitations(),
            repo_root=repo,
        )

    extraction = extract_autonomous_browser_plan_candidate(raw_text)
    extraction_status = str(extraction.get("status") or "rejected")
    extracted_plan = extraction.get("candidate_plan")
    extracted_plan_id = extraction.get("extracted_plan_id")
    if extraction_status != "accepted" or not isinstance(extracted_plan, Mapping):
        return _failure_summary(
            source_output_path=source_output_path,
            extracted_plan_id=extracted_plan_id if isinstance(extracted_plan_id, str) else None,
            validation_status="skipped",
            actions_total=0,
            output_dir=output_dir,
            error_code=str(extraction.get("error_code") or "extraction_failed"),
            diagnostics={
                "source_output": {"path": source_output_path},
                "extraction": _extraction_diagnostics(extraction),
            },
            limitations=_limitations(),
            repo_root=repo,
        )

    validation_result = validate_autonomous_browser_plan(extracted_plan)
    validation_status = str(validation_result.get("status") or "rejected")
    actions_total = _int(validation_result.get("actions_total"))
    if validation_status != "accepted":
        return _failure_summary(
            source_output_path=source_output_path,
            extracted_plan_id=str(validation_result.get("plan_id") or extracted_plan_id or ""),
            validation_status=validation_status,
            actions_total=actions_total,
            output_dir=output_dir,
            error_code=str(validation_result.get("error_code") or "plan_validation_failed"),
            diagnostics={
                "source_output": {"path": source_output_path},
                "extraction": _extraction_diagnostics(extraction),
                "validation": _validation_diagnostics(validation_result),
            },
            limitations=_limitations(),
            repo_root=repo,
        )

    normalized_plan = validation_result.get("normalized_plan")
    if not isinstance(normalized_plan, Mapping):
        return _failure_summary(
            source_output_path=source_output_path,
            extracted_plan_id=str(validation_result.get("plan_id") or extracted_plan_id or ""),
            validation_status=validation_status,
            actions_total=actions_total,
            output_dir=output_dir,
            error_code="normalized_plan_missing",
            diagnostics={
                "source_output": {"path": source_output_path},
                "extraction": _extraction_diagnostics(extraction),
                "validation": _validation_diagnostics(validation_result),
            },
            limitations=_limitations(),
            repo_root=repo,
        )

    packet_dir.mkdir(parents=True, exist_ok=True)
    packet_files: list[str] = []

    normalized_plan_path = packet_dir / "normalized_plan.json"
    _write_json(normalized_plan_path, normalized_plan)
    packet_files.append(f"{output_dir}/normalized_plan.json")

    replay_packet_payload = _build_replay_packet_payload(
        packet_id=packet_id,
        source_output_path=source_output_path,
        extracted_plan_id=str(validation_result.get("plan_id") or extracted_plan_id or ""),
        validation_result=validation_result,
        normalized_plan=normalized_plan,
        output_dir=output_dir,
    )
    replay_packet_path = packet_dir / "playwright_replay_plan.json"
    _write_json(replay_packet_path, replay_packet_payload)
    packet_files.append(f"{output_dir}/playwright_replay_plan.json")

    commands = _build_commands(
        output_dir=output_dir,
        source_output_path=source_output_path,
    )
    _write_json(packet_dir / "commands.json", {"schema_version": f"{PACKET_SCHEMA_VERSION}_commands_v1", "packet_id": packet_id, "commands": commands, "future_operator_guard_required": True, "no_runtime_execution": True})
    packet_files.append(f"{output_dir}/commands.json")

    commands_md = _build_commands_markdown(output_dir=output_dir, source_output_path=source_output_path)
    _write_text(packet_dir / "commands.md", commands_md)
    packet_files.append(f"{output_dir}/commands.md")

    readme_text = _build_readme(
        packet_id=packet_id,
        source_output_path=source_output_path,
        output_dir=output_dir,
        validation_result=validation_result,
    )
    _write_text(packet_dir / "README.md", readme_text)
    packet_files.append(f"{output_dir}/README.md")

    summary_path = packet_dir / "autonomous_browser_plan_playwright_replay_packet_summary.json"
    packet_files.append(f"{output_dir}/autonomous_browser_plan_playwright_replay_packet_summary.json")
    summary = AutonomousBrowserPlanPlaywrightReplayPacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="succeeded",
        error_code=None,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        source_output_path=source_output_path,
        extracted_plan_id=str(validation_result.get("plan_id") or extracted_plan_id or ""),
        validation_status=validation_status,
        actions_total=actions_total,
        output_dir=output_dir,
        packet_files=tuple(packet_files),
        future_operator_guard_required=True,
        diagnostics={
            "source_output": {"path": source_output_path},
            "extraction": _extraction_diagnostics(extraction),
            "validation": _validation_diagnostics(validation_result),
            "packet": {
                "normalized_plan_path": f"{output_dir}/normalized_plan.json",
                "playwright_replay_plan_path": f"{output_dir}/playwright_replay_plan.json",
                "commands_path": f"{output_dir}/commands.md",
                "future_operator_guard_required": True,
                "allowed_browser_hosts": list(ALLOWED_BROWSER_HOSTS),
            },
        },
        limitations=_limitations(),
    )
    summary_payload = summary.to_dict()
    _write_json(summary_path, summary_payload)
    return summary_payload


def _build_replay_packet_payload(
    *,
    packet_id: str,
    source_output_path: str,
    extracted_plan_id: str,
    validation_result: Mapping[str, Any],
    normalized_plan: Mapping[str, Any],
    output_dir: str,
) -> dict[str, Any]:
    return {
        "schema_version": PACKET_SCHEMA_VERSION,
        "packet_id": packet_id,
        "source_output_path": source_output_path,
        "extracted_plan_id": extracted_plan_id,
        "actions_total": _int(validation_result.get("actions_total")),
        "future_operator_guard_required": True,
        "model_execution": False,
        "real_browser_execution": False,
        "no_runtime_execution": True,
        "local_fixture_only_scope": True,
        "allowed_browser_hosts": list(ALLOWED_BROWSER_HOSTS),
        "no_external_urls": True,
        "no_credentials_or_secrets": True,
        "no_general_browsing": True,
        "normalized_plan_path": f"{output_dir}/normalized_plan.json",
        "normalized_plan": _jsonable(normalized_plan),
        "limitations": list(_limitations()),
    }


def write_autonomous_browser_plan_playwright_replay_packet_summary(summary: Mapping[str, Any], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_plan_playwright_replay_packet_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


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
                "source_output_path": None,
                "output_dir": None,
                "packet_id": None,
                "validation_status": "skipped",
                "actions_total": 0,
                "limitations": _limitations(),
            }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "source_output_path": None,
            "output_dir": None,
            "packet_id": None,
            "validation_status": "skipped",
            "actions_total": 0,
            "limitations": _limitations(),
        }
    if str(payload.get("schema_version", "")) != PACKET_CONFIG_SCHEMA_VERSION:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "source_output_path": _safe_relative_path(payload.get("source_output_path"), "source_output_path"),
            "output_dir": _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir"),
            "packet_id": _safe_identifier(payload.get("packet_id", DEFAULT_PACKET_ID), "packet_id"),
            "validation_status": "skipped",
            "actions_total": 0,
            "limitations": _limitations(),
        }
    if payload.get("no_runtime_execution") is not True:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "source_output_path": _safe_relative_path(payload.get("source_output_path"), "source_output_path"),
            "output_dir": _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir"),
            "packet_id": _safe_identifier(payload.get("packet_id", DEFAULT_PACKET_ID), "packet_id"),
            "validation_status": "skipped",
            "actions_total": 0,
            "limitations": _limitations(),
        }

    packet_id = _safe_identifier(payload.get("packet_id", DEFAULT_PACKET_ID), "packet_id")
    source_output_path = _safe_relative_path(payload.get("source_output_path"), "source_output_path")
    output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir")
    if packet_id is None or source_output_path is None or output_dir is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "source_output_path": source_output_path,
            "output_dir": output_dir,
            "packet_id": packet_id,
            "validation_status": "skipped",
            "actions_total": 0,
            "limitations": _limitations(),
        }
    return {
        "status": "ok",
        "packet_id": packet_id,
        "source_output_path": source_output_path,
        "output_dir": output_dir,
        "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
    }


def _build_commands(*, output_dir: str, source_output_path: str) -> list[dict[str, Any]]:
    windows_output_dir = output_dir.replace("/", "\\")
    return [
        {
            "id": "build_playwright_replay_packet",
            "manual_only": False,
            "description": "Build the offline replay packet from a captured planner output.",
            "command": r".\.venv\Scripts\python.exe scripts/build_autonomous_browser_plan_playwright_replay_packet.py --config configs/autonomous_runtime/browser_plan_playwright_replay_packet.example.json",
        },
        {
            "id": "inspect_normalized_plan",
            "manual_only": True,
            "description": "Inspect the normalized plan before any future guarded operator action.",
            "command": f"Get-Content .\\{windows_output_dir}\\normalized_plan.json -Raw",
        },
        {
            "id": "future_guarded_operator_replay",
            "manual_only": True,
            "description": "Future guarded operator replay placeholder only.",
            "command": (
                "# Future operator-only step. Codex must not launch browser/server/model.\n"
                "# This phase only prepares the packet and does not execute Playwright.\n"
                "# When the guarded replay runner exists, use explicit operator approval:\n"
                r"# .\.venv\Scripts\python.exe scripts/run_autonomous_browser_playwright_operator.py --config configs/autonomous_runtime/playwright_operator.example.json --allow-real-browser --confirm-real-browser BROWSER_RUNTIME_OPT_IN"
            ),
        },
        {
            "id": "run_pytest",
            "manual_only": False,
            "description": "Run the offline test suite.",
            "command": r".\.venv\Scripts\python.exe -m pytest",
        },
    ]


def _build_commands_markdown(*, output_dir: str, source_output_path: str) -> str:
    lines = [
        "# Playwright Replay Packet Commands",
        "",
        "Codex must not launch browser/server/model.",
        "This phase does not run Playwright.",
        r"Use repo-local Python only: `.\.venv\Scripts\python.exe ...`.",
        "Do not use global python / pytest.",
        "Do not use Invoke-RestMethod.",
        "Do not commit raw artifacts.",
        "Future guarded operator execution requires explicit flags: `--allow-real-browser` and `--confirm-real-browser BROWSER_RUNTIME_OPT_IN`.",
        f"Captured planner output source: `{source_output_path}`.",
        f"Packet output directory: `{output_dir}`.",
        "",
    ]
    for command in _build_commands(output_dir=output_dir, source_output_path=source_output_path):
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
    source_output_path: str,
    output_dir: str,
    validation_result: Mapping[str, Any],
) -> str:
    lines = [
        "# Playwright Replay Packet",
        "",
        f"Packet id: `{packet_id}`",
        f"Source output: `{source_output_path}`",
        "",
        "## Scope",
        "",
        "- Captured planner output text only.",
        "- Existing extraction and validation logic only.",
        "- Normalized `autonomous_browser_plan_v1` packet files for future guarded operator replay.",
        "- No Playwright execution in this phase.",
        "",
        "## Safety",
        "",
        "- Codex must not launch browser/server/model.",
        "- Future guarded operator execution requires explicit flags.",
        "- No external URLs.",
        "- No credentials or secrets.",
        "- No general browsing.",
        "- Local fixture-only scope.",
        "- Repo-local Python only.",
        "- Do not use global python / pytest.",
        "- Do not use Invoke-RestMethod.",
        "",
        "## Allowed Hosts",
        "",
    ]
    for host in ALLOWED_BROWSER_HOSTS:
        lines.append(f"- `{host}`")
    lines.extend(
        [
            "",
            "## Validated Plan",
            "",
            f"- plan_id: `{validation_result.get('plan_id')}`",
            f"- actions_total: `{validation_result.get('actions_total')}`",
            f"- normalized_plan.json: `{output_dir}/normalized_plan.json`",
            f"- playwright_replay_plan.json: `{output_dir}/playwright_replay_plan.json`",
            "",
            "## Operator Flow",
            "",
            "1. Build the replay packet from the captured planner output.",
            "2. Inspect `normalized_plan.json`.",
            "3. Review `playwright_replay_plan.json` and the guarded operator notes.",
            "4. Use an explicitly guarded operator replay path only when it exists and only with local fixtures.",
            "5. Run pytest.",
            "",
        ]
    )
    return "\n".join(lines)


def _failure_summary(
    *,
    source_output_path: str | None,
    extracted_plan_id: str | None,
    validation_status: str,
    actions_total: int,
    output_dir: str | None,
    error_code: str,
    diagnostics: Mapping[str, Any],
    limitations: tuple[str, ...],
    repo_root: Path,
) -> dict[str, Any]:
    packet_files: tuple[str, ...] = ()
    if output_dir:
        packet_files = (f"{output_dir}/autonomous_browser_plan_playwright_replay_packet_summary.json",)
    summary = AutonomousBrowserPlanPlaywrightReplayPacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        source_output_path=source_output_path,
        extracted_plan_id=extracted_plan_id,
        validation_status=validation_status,
        actions_total=actions_total,
        output_dir=output_dir,
        packet_files=packet_files,
        future_operator_guard_required=True,
        diagnostics=dict(diagnostics),
        limitations=limitations,
    )
    payload = summary.to_dict()
    if output_dir:
        packet_dir = repo_root / output_dir
        packet_dir.mkdir(parents=True, exist_ok=True)
        _write_json(packet_dir / "autonomous_browser_plan_playwright_replay_packet_summary.json", payload)
    return payload


def _failure_diagnostics(config_result: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics: dict[str, Any] = {}
    if "source_output_path" in config_result and config_result["source_output_path"] is not None:
        diagnostics["source_output"] = {"path": config_result["source_output_path"]}
    if "output_dir" in config_result and config_result["output_dir"] is not None:
        diagnostics["output_dir"] = {"path": config_result["output_dir"]}
    diagnostics["config"] = {
        key: _jsonable(value)
        for key, value in config_result.items()
        if key in {"status", "error_code", "validation_status", "actions_total", "packet_id"}
    }
    return diagnostics


def _validation_diagnostics(validation_result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": validation_result.get("status"),
        "error_code": validation_result.get("error_code"),
        "plan_id": validation_result.get("plan_id"),
        "actions_total": validation_result.get("actions_total"),
        "diagnostics": [
            _safe_validation_diagnostic(item)
            for item in validation_result.get("diagnostics", [])
            if isinstance(item, Mapping)
        ],
    }


def _extraction_diagnostics(extraction: Mapping[str, Any]) -> dict[str, Any]:
    diagnostics = {
        "status": extraction.get("status"),
        "error_code": extraction.get("error_code"),
        "extracted_plan_id": extraction.get("extracted_plan_id"),
        "diagnostics": _jsonable(extraction.get("diagnostics", {})),
    }
    return diagnostics


def _safe_validation_diagnostic(item: Mapping[str, Any]) -> dict[str, Any]:
    safe_keys = (
        "finding_type",
        "path",
        "json_path",
        "key",
        "parameter_key",
        "error_code",
        "limit",
        "object_count",
        "actions_total",
        "type",
        "action_name",
        "expected_schema_version",
        "status",
    )
    return {key: _jsonable(item[key]) for key in safe_keys if key in item and item[key] is not None}


def _limitations() -> tuple[str, ...]:
    return (
        "offline packet only",
        "captured planner output only",
        "existing extraction and validation only",
        "no model calls",
        "no Playwright execution",
        "future operator guarded replay only",
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


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set):
        return [_jsonable(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0
