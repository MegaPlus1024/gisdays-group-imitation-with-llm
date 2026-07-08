from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_plan_runtime_bridge import run_autonomous_browser_plan_dry_run
from .autonomous_browser_plan_validation import validate_autonomous_browser_plan


PACKET_SCHEMA_VERSION = "autonomous_browser_planner_packet_v1"
PACKET_CONFIG_SCHEMA_VERSION = "autonomous_browser_planner_packet_config_v1"
REPLAY_SUMMARY_SCHEMA_VERSION = "autonomous_browser_planner_replay_summary_v1"
DEFAULT_PACKET_ID = "browser_planner_packet_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/browser_planner_packet"
DEFAULT_CANDIDATE_PLAN_PATH = "configs/autonomous_runtime/browser_planner_candidate.example.json"

ALLOWED_BROWSER_ACTIONS = (
    "browser_open_url",
    "browser_click",
    "browser_extract_text",
    "browser_fill",
    "browser_submit",
    "browser_wait",
    "browser_search",
    "browser_snapshot",
)

ALLOWED_LOGICAL_FIXTURE_HOSTS = (
    "local.intranet",
    "local-intranet.test",
    "docs.local",
    "portal.local",
)

PROHIBITED_OUTPUTS = (
    "external URLs",
    "localhost/127.0.0.1",
    "file URLs",
    "local absolute paths",
    "credentials/secrets",
    "browser execution requests",
    "API/model/runtime commands",
)


@dataclass(frozen=True)
class AutonomousBrowserPlannerPacket:
    schema_version: str
    packet_id: str
    prompt_text: str
    prompt_sections: dict[str, Any] = field(default_factory=dict)
    allowed_actions: tuple[str, ...] = ()
    allowed_logical_fixture_hosts: tuple[str, ...] = ()
    prohibited_outputs: tuple[str, ...] = ()
    candidate_plan_example_path: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "prompt_text": self.prompt_text,
            "prompt_sections": dict(self.prompt_sections),
            "allowed_actions": list(self.allowed_actions),
            "allowed_logical_fixture_hosts": list(self.allowed_logical_fixture_hosts),
            "prohibited_outputs": list(self.prohibited_outputs),
            "candidate_plan_example_path": self.candidate_plan_example_path,
        }


@dataclass(frozen=True)
class AutonomousBrowserPlannerReplaySummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    real_browser_execution: bool
    model_execution: bool
    candidate_plan_path: str | None
    validation_status: str
    dry_run_status: str
    fixture_execution_status: str
    actions_total: int
    actions_attempted: int
    actions_succeeded: int
    actions_failed: int
    expected_results_total: int
    expected_results_passed: int
    expected_results_failed: int
    stop_reason: str | None
    limitations: tuple[str, ...] = ()
    output_files: tuple[str, ...] = ()
    validation_result: dict[str, Any] = field(default_factory=dict)
    dry_run_summary: dict[str, Any] = field(default_factory=dict)
    fixture_execution_summary: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "real_browser_execution": self.real_browser_execution,
            "model_execution": self.model_execution,
            "candidate_plan_path": self.candidate_plan_path,
            "validation_status": self.validation_status,
            "dry_run_status": self.dry_run_status,
            "fixture_execution_status": self.fixture_execution_status,
            "actions_total": self.actions_total,
            "actions_attempted": self.actions_attempted,
            "actions_succeeded": self.actions_succeeded,
            "actions_failed": self.actions_failed,
            "expected_results_total": self.expected_results_total,
            "expected_results_passed": self.expected_results_passed,
            "expected_results_failed": self.expected_results_failed,
            "stop_reason": self.stop_reason,
            "limitations": list(self.limitations),
            "output_files": list(self.output_files),
            "validation_result": dict(self.validation_result),
            "dry_run_summary": dict(self.dry_run_summary),
            "fixture_execution_summary": dict(self.fixture_execution_summary),
        }


def build_autonomous_browser_planner_packet(
    *,
    packet_id: str = DEFAULT_PACKET_ID,
    candidate_plan_example_path: str | None = DEFAULT_CANDIDATE_PLAN_PATH,
) -> dict[str, Any]:
    prompt_text = _build_prompt_text()
    packet = AutonomousBrowserPlannerPacket(
        schema_version=PACKET_SCHEMA_VERSION,
        packet_id=packet_id,
        prompt_text=prompt_text,
        prompt_sections={
            "schema_reminder": "autonomous_browser_plan_v1",
            "allowed_actions": list(ALLOWED_BROWSER_ACTIONS),
            "allowed_logical_fixture_hosts": list(ALLOWED_LOGICAL_FIXTURE_HOSTS),
            "prohibited_outputs": list(PROHIBITED_OUTPUTS),
            "output_format": "JSON only",
            "candidate_plan_example_path": candidate_plan_example_path,
        },
        allowed_actions=ALLOWED_BROWSER_ACTIONS,
        allowed_logical_fixture_hosts=ALLOWED_LOGICAL_FIXTURE_HOSTS,
        prohibited_outputs=PROHIBITED_OUTPUTS,
        candidate_plan_example_path=candidate_plan_example_path,
    )
    return packet.to_dict()


def write_autonomous_browser_planner_packet(packet: Mapping[str, Any], output_dir: str | Path) -> dict[str, Path]:
    output_path = Path(output_dir)
    output_path.mkdir(parents=True, exist_ok=True)
    packet_path = output_path / "autonomous_browser_planner_packet.json"
    prompt_path = output_path / "autonomous_browser_planner_prompt.txt"
    packet_path.write_text(_dump(packet), encoding="utf-8")
    prompt_text = str(packet.get("prompt_text", "")).strip()
    prompt_path.write_text(prompt_text + "\n", encoding="utf-8")
    return {"packet": packet_path, "prompt": prompt_path}


def replay_autonomous_browser_planner_output(
    candidate_plan: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    execute_fixture: bool = False,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    candidate_path = _display_candidate_path(candidate_plan)
    validation_result = validate_autonomous_browser_plan(candidate_plan)
    validation_status = str(validation_result.get("status", "rejected"))
    actions_total = _int(validation_result.get("actions_total", 0))
    if validation_status != "accepted":
        summary = AutonomousBrowserPlannerReplaySummary(
            schema_version=REPLAY_SUMMARY_SCHEMA_VERSION,
            status="rejected",
            error_code=str(validation_result.get("error_code") or "browser_plan_validation_failed"),
            no_runtime_execution=True,
            real_browser_execution=False,
            model_execution=False,
            candidate_plan_path=candidate_path,
            validation_status=validation_status,
            dry_run_status="rejected",
            fixture_execution_status="skipped",
            actions_total=actions_total,
            actions_attempted=0,
            actions_succeeded=0,
            actions_failed=0,
            expected_results_total=0,
            expected_results_passed=0,
            expected_results_failed=0,
            stop_reason="validation_rejected",
            limitations=_limitations(),
            validation_result=validation_result,
        )
        return summary.to_dict()

    dry_run_summary = run_autonomous_browser_plan_dry_run(candidate_plan, repo_root=repo)
    if not execute_fixture:
        summary = AutonomousBrowserPlannerReplaySummary(
            schema_version=REPLAY_SUMMARY_SCHEMA_VERSION,
            status="succeeded",
            error_code=None,
            no_runtime_execution=True,
            real_browser_execution=False,
            model_execution=False,
            candidate_plan_path=candidate_path,
            validation_status=validation_status,
            dry_run_status=str(dry_run_summary.get("status", "accepted")),
            fixture_execution_status="skipped",
            actions_total=actions_total,
            actions_attempted=0,
            actions_succeeded=0,
            actions_failed=0,
            expected_results_total=0,
            expected_results_passed=0,
            expected_results_failed=0,
            stop_reason=str(dry_run_summary.get("stop_reason") or "all_tasks_terminal"),
            limitations=_limitations(),
            dry_run_summary=dry_run_summary,
            validation_result=validation_result,
        )
        return summary.to_dict()

    fixture_summary = run_autonomous_browser_plan_fixture_execution(candidate_plan, repo_root=repo)
    status = str(fixture_summary.get("status", "failed"))
    error_code = fixture_summary.get("error_code")
    summary = AutonomousBrowserPlannerReplaySummary(
        schema_version=REPLAY_SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        no_runtime_execution=True,
        real_browser_execution=False,
        model_execution=False,
        candidate_plan_path=candidate_path,
        validation_status=validation_status,
        dry_run_status=str(dry_run_summary.get("status", "accepted")),
        fixture_execution_status=status if status in {"succeeded", "failed", "rejected"} else "failed",
        actions_total=_int(fixture_summary.get("actions_planned", actions_total)),
        actions_attempted=_int(fixture_summary.get("actions_attempted", 0)),
        actions_succeeded=_int(fixture_summary.get("actions_succeeded", 0)),
        actions_failed=_int(fixture_summary.get("actions_failed", 0)),
        expected_results_total=_int(fixture_summary.get("expected_results_total", 0)),
        expected_results_passed=_int(fixture_summary.get("expected_results_passed", 0)),
        expected_results_failed=_int(fixture_summary.get("expected_results_failed", 0)),
        stop_reason=str(fixture_summary.get("stop_reason") or "all_tasks_terminal"),
        limitations=_limitations(),
        dry_run_summary=dry_run_summary,
        fixture_execution_summary=fixture_summary,
        validation_result=validation_result,
    )
    return summary.to_dict()


def _build_prompt_text() -> str:
    lines = [
        "You are a browser planner for offline fixture-backed execution.",
        "Return JSON only.",
        "",
        "SCHEMA REMINDER",
        "autonomous_browser_plan_v1",
        "",
        "ALLOWED ACTIONS",
        *[f"- {action}" for action in ALLOWED_BROWSER_ACTIONS],
        "",
        "ALLOWED LOGICAL FIXTURE HOSTS",
        *[f"- {host}" for host in ALLOWED_LOGICAL_FIXTURE_HOSTS],
        "",
        "PROHIBITED OUTPUTS",
        *[f"- {item}" for item in PROHIBITED_OUTPUTS],
        "",
        "OUTPUT FORMAT",
        "JSON only. Do not include markdown, prose, or code fences.",
        "Plan only for local fixture-backed browser actions.",
    ]
    return "\n".join(lines)


def _limitations() -> tuple[str, ...]:
    return (
        "offline planner prompt/output packet only",
        "future local LLM planning support only",
        "no model calls",
        "no real browser execution",
        "fixture replay remains offline only",
        "guarded Playwright suite evidence remains separate",
        "not production browser automation",
    )


def _display_candidate_path(candidate_plan: str | Path | Mapping[str, Any]) -> str | None:
    if isinstance(candidate_plan, Mapping):
        return None
    path = Path(candidate_plan)
    if path.is_absolute():
        try:
            return path.resolve(strict=False).relative_to(Path.cwd().resolve(strict=False)).as_posix()
        except (OSError, ValueError):
            return path.name
    return path.as_posix()


def _dump(payload: Mapping[str, Any]) -> str:
    import json

    return json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True)


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def run_autonomous_browser_plan_fixture_execution(
    candidate_plan: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    from .autonomous_browser_plan_fixture_execution import (
        run_autonomous_browser_plan_fixture_execution as _run_autonomous_browser_plan_fixture_execution,
    )

    return _run_autonomous_browser_plan_fixture_execution(candidate_plan, repo_root=repo_root)
