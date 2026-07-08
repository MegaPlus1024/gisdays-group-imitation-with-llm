from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_planner_packet import replay_autonomous_browser_planner_output


REPLAY_SUITE_CONFIG_SCHEMA_VERSION = "autonomous_browser_planner_replay_suite_config_v1"
REPLAY_SUITE_SUMMARY_SCHEMA_VERSION = "autonomous_browser_planner_replay_suite_summary_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/browser_planner_replay_suite"
DEFAULT_EXPECTED_MIN_ACCEPTED = 1
DEFAULT_EXPECTED_MIN_FIXTURE_SUCCESS = 0
DEFAULT_REPLAY_MODE = "dry_run"
ALLOWED_REPLAY_MODES = ("dry_run", "fixture_execution")


@dataclass(frozen=True)
class AutonomousBrowserPlannerReplaySuiteSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    real_browser_execution: bool
    model_execution: bool
    suite_id: str | None
    replay_mode: str
    candidates_total: int
    candidates_accepted: int
    candidates_rejected: int
    dry_runs_succeeded: int
    dry_runs_failed: int
    fixture_runs_succeeded: int
    fixture_runs_failed: int
    actions_attempted_total: int
    actions_succeeded_total: int
    actions_failed_total: int
    expected_results_total: int
    expected_results_passed: int
    expected_results_failed: int
    candidate_summaries: tuple[dict[str, Any], ...] = ()
    thresholds: dict[str, int] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "real_browser_execution": self.real_browser_execution,
            "model_execution": self.model_execution,
            "suite_id": self.suite_id,
            "replay_mode": self.replay_mode,
            "candidates_total": self.candidates_total,
            "candidates_accepted": self.candidates_accepted,
            "candidates_rejected": self.candidates_rejected,
            "dry_runs_succeeded": self.dry_runs_succeeded,
            "dry_runs_failed": self.dry_runs_failed,
            "fixture_runs_succeeded": self.fixture_runs_succeeded,
            "fixture_runs_failed": self.fixture_runs_failed,
            "actions_attempted_total": self.actions_attempted_total,
            "actions_succeeded_total": self.actions_succeeded_total,
            "actions_failed_total": self.actions_failed_total,
            "expected_results_total": self.expected_results_total,
            "expected_results_passed": self.expected_results_passed,
            "expected_results_failed": self.expected_results_failed,
            "candidate_summaries": [dict(item) for item in self.candidate_summaries],
            "thresholds": dict(self.thresholds),
            "limitations": list(self.limitations),
        }


def run_autonomous_browser_planner_replay_suite(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    execute_fixture: bool = False,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    config_result = _load_suite_config(config_artifact)
    if config_result["status"] != "ok":
        return _suite_failure(
            suite_id=config_result.get("suite_id"),
            replay_mode=config_result.get("replay_mode") or DEFAULT_REPLAY_MODE,
            error_code=str(config_result.get("error_code") or "config_validation_failed"),
            error_message=str(config_result.get("error_message") or "suite config could not be validated."),
            limitations=tuple(config_result.get("limitations") or _limitations()),
        )

    suite_id = str(config_result["suite_id"])
    replay_mode = "fixture_execution" if execute_fixture else str(config_result["replay_mode"])
    candidate_paths = tuple(str(path) for path in config_result["candidate_plans"])
    expected_min_accepted = _int(config_result["expected_min_accepted"])
    expected_min_fixture_success = _int(config_result["expected_min_fixture_success"])
    candidate_summaries: list[dict[str, Any]] = []
    candidates_accepted = 0
    candidates_rejected = 0
    dry_runs_succeeded = 0
    dry_runs_failed = 0
    fixture_runs_succeeded = 0
    fixture_runs_failed = 0
    actions_attempted_total = 0
    actions_succeeded_total = 0
    actions_failed_total = 0
    expected_results_total = 0
    expected_results_passed = 0
    expected_results_failed = 0
    any_candidate_issue = False
    first_issue_code: str | None = None

    for index, candidate_path_value in enumerate(candidate_paths):
        candidate_summary = _replay_candidate(
            candidate_path_value,
            repo_root=repo,
            replay_mode=replay_mode,
            candidate_index=index,
            execute_fixture=execute_fixture or replay_mode == "fixture_execution",
        )
        candidate_summaries.append(candidate_summary)

        if str(candidate_summary.get("validation_status")) == "accepted":
            candidates_accepted += 1
        else:
            candidates_rejected += 1

        if str(candidate_summary.get("dry_run_status")) == "accepted":
            dry_runs_succeeded += 1
        else:
            dry_runs_failed += 1

        if replay_mode == "fixture_execution":
            if str(candidate_summary.get("fixture_execution_status")) == "succeeded":
                fixture_runs_succeeded += 1
            else:
                fixture_runs_failed += 1

        actions_attempted_total += _int(candidate_summary.get("actions_attempted"))
        actions_succeeded_total += _int(candidate_summary.get("actions_succeeded"))
        actions_failed_total += _int(candidate_summary.get("actions_failed"))
        expected_results_total += _int(candidate_summary.get("expected_results_total"))
        expected_results_passed += _int(candidate_summary.get("expected_results_passed"))
        expected_results_failed += _int(candidate_summary.get("expected_results_failed"))

        if str(candidate_summary.get("status")) != "succeeded":
            any_candidate_issue = True
            if first_issue_code is None:
                first_issue_code = str(candidate_summary.get("error_code") or "candidate_replay_failed")

    thresholds_met = candidates_accepted >= expected_min_accepted
    if replay_mode == "fixture_execution":
        thresholds_met = thresholds_met and fixture_runs_succeeded >= expected_min_fixture_success

    if not candidate_summaries:
        status = "failed"
        error_code = "no_candidates_provided"
    elif not thresholds_met:
        status = "failed"
        error_code = first_issue_code or "suite_thresholds_not_met"
    elif any_candidate_issue:
        status = "completed_with_failures"
        error_code = first_issue_code or "suite_completed_with_failures"
    else:
        status = "succeeded"
        error_code = None

    summary = AutonomousBrowserPlannerReplaySuiteSummary(
        schema_version=REPLAY_SUITE_SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        no_runtime_execution=True,
        real_browser_execution=False,
        model_execution=False,
        suite_id=suite_id,
        replay_mode=replay_mode,
        candidates_total=len(candidate_summaries),
        candidates_accepted=candidates_accepted,
        candidates_rejected=candidates_rejected,
        dry_runs_succeeded=dry_runs_succeeded,
        dry_runs_failed=dry_runs_failed,
        fixture_runs_succeeded=fixture_runs_succeeded,
        fixture_runs_failed=fixture_runs_failed,
        actions_attempted_total=actions_attempted_total,
        actions_succeeded_total=actions_succeeded_total,
        actions_failed_total=actions_failed_total,
        expected_results_total=expected_results_total,
        expected_results_passed=expected_results_passed,
        expected_results_failed=expected_results_failed,
        candidate_summaries=tuple(candidate_summaries),
        thresholds={
            "expected_min_accepted": expected_min_accepted,
            "expected_min_fixture_success": expected_min_fixture_success,
        },
        limitations=_limitations(),
    )
    return summary.to_dict()


def write_autonomous_browser_planner_replay_suite_summary(
    summary: Mapping[str, Any],
    output_dir: str | Path,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_planner_replay_suite_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _load_suite_config(config_artifact: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config_artifact, Mapping):
        payload = dict(config_artifact)
    else:
        path = Path(config_artifact)
        payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "error_message": "suite config root must be a JSON object.",
        }
    if str(payload.get("schema_version", "")) != REPLAY_SUITE_CONFIG_SCHEMA_VERSION:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "error_message": "suite config schema_version must match autonomous_browser_planner_replay_suite_config_v1.",
        }
    suite_id = _safe_text(payload.get("suite_id"))
    candidate_plans = payload.get("candidate_plans")
    replay_mode = str(payload.get("replay_mode", DEFAULT_REPLAY_MODE)).strip()
    output_dir = payload.get("output_dir", DEFAULT_OUTPUT_DIR)
    expected_min_accepted = payload.get("expected_min_accepted", DEFAULT_EXPECTED_MIN_ACCEPTED)
    expected_min_fixture_success = payload.get("expected_min_fixture_success", DEFAULT_EXPECTED_MIN_FIXTURE_SUCCESS)
    if not suite_id:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "error_message": "suite_id must be a non-empty string.",
        }
    if replay_mode not in ALLOWED_REPLAY_MODES:
        return {
            "status": "failed",
            "suite_id": suite_id,
            "replay_mode": replay_mode,
            "error_code": "config_validation_failed",
            "error_message": "replay_mode must be dry_run or fixture_execution.",
        }
    if not isinstance(candidate_plans, list) or not candidate_plans:
        return {
            "status": "failed",
            "suite_id": suite_id,
            "replay_mode": replay_mode,
            "error_code": "config_validation_failed",
            "error_message": "candidate_plans must be a non-empty list.",
        }
    cleaned_candidate_plans: list[str] = []
    for index, candidate in enumerate(candidate_plans):
        if not isinstance(candidate, str) or not candidate.strip():
            return {
                "status": "failed",
                "suite_id": suite_id,
                "replay_mode": replay_mode,
                "error_code": "config_validation_failed",
                "error_message": f"candidate_plans[{index}] must be a non-empty string.",
            }
        cleaned_candidate_plans.append(candidate.strip())
    try:
        safe_output_dir = _safe_relative_path(str(output_dir), "output_dir")
    except ValueError as exc:
        return {
            "status": "failed",
            "suite_id": suite_id,
            "replay_mode": replay_mode,
            "error_code": "config_validation_failed",
            "error_message": str(exc),
        }
    if not isinstance(expected_min_accepted, int) or isinstance(expected_min_accepted, bool) or expected_min_accepted < 0:
        return {
            "status": "failed",
            "suite_id": suite_id,
            "replay_mode": replay_mode,
            "error_code": "config_validation_failed",
            "error_message": "expected_min_accepted must be a non-negative integer.",
        }
    if not isinstance(expected_min_fixture_success, int) or isinstance(expected_min_fixture_success, bool) or expected_min_fixture_success < 0:
        return {
            "status": "failed",
            "suite_id": suite_id,
            "replay_mode": replay_mode,
            "error_code": "config_validation_failed",
            "error_message": "expected_min_fixture_success must be a non-negative integer.",
        }
    return {
        "status": "ok",
        "suite_id": suite_id,
        "candidate_plans": cleaned_candidate_plans,
        "replay_mode": replay_mode,
        "output_dir": safe_output_dir,
        "expected_min_accepted": expected_min_accepted,
        "expected_min_fixture_success": expected_min_fixture_success,
        "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
    }


def _replay_candidate(
    candidate_path_value: str,
    *,
    repo_root: Path,
    replay_mode: str,
    candidate_index: int,
    execute_fixture: bool,
) -> dict[str, Any]:
    candidate_path, display_path, path_error = _resolve_candidate_path(candidate_path_value, repo_root)
    if path_error is not None:
        return {
            "candidate_index": candidate_index,
            "candidate_plan_path": display_path,
            "status": "failed",
            "error_code": path_error,
            "no_runtime_execution": True,
            "real_browser_execution": False,
            "model_execution": False,
            "validation_status": "rejected",
            "dry_run_status": "rejected",
            "fixture_execution_status": "skipped",
            "actions_total": 0,
            "actions_attempted": 0,
            "actions_succeeded": 0,
            "actions_failed": 0,
            "expected_results_total": 0,
            "expected_results_passed": 0,
            "expected_results_failed": 0,
            "stop_reason": "candidate_path_rejected",
            "limitations": list(_limitations()),
        }
    if not candidate_path.exists():
        return {
            "candidate_index": candidate_index,
            "candidate_plan_path": display_path,
            "status": "failed",
            "error_code": "missing_candidate_file",
            "no_runtime_execution": True,
            "real_browser_execution": False,
            "model_execution": False,
            "validation_status": "rejected",
            "dry_run_status": "rejected",
            "fixture_execution_status": "skipped",
            "actions_total": 0,
            "actions_attempted": 0,
            "actions_succeeded": 0,
            "actions_failed": 0,
            "expected_results_total": 0,
            "expected_results_passed": 0,
            "expected_results_failed": 0,
            "stop_reason": "candidate_file_missing",
            "limitations": list(_limitations()),
        }

    replay_summary = replay_autonomous_browser_planner_output(
        candidate_path,
        repo_root=repo_root,
        execute_fixture=execute_fixture,
    )
    candidate_summary = dict(replay_summary)
    candidate_summary["candidate_index"] = candidate_index
    candidate_summary["candidate_plan_path"] = display_path
    candidate_summary["replay_mode"] = replay_mode
    candidate_summary["status"] = str(candidate_summary.get("status", "failed"))
    return candidate_summary


def _resolve_candidate_path(candidate_path_value: str, repo_root: Path) -> tuple[Path, str, str | None]:
    normalized = candidate_path_value.replace("\\", "/").strip()
    path = Path(normalized)
    if not normalized:
        return path, "", "unsafe_candidate_path"
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        return path, _display_candidate_path(path, repo_root), "unsafe_candidate_path"
    return (repo_root / path).resolve(), path.as_posix(), None


def _display_candidate_path(candidate_path: Path, repo_root: Path) -> str:
    try:
        resolved = candidate_path.resolve(strict=False)
        return resolved.relative_to(repo_root.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return candidate_path.name or "candidate_plan.json"


def _safe_relative_path(value: str, label: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        raise ValueError(f"{label} must be non-empty.")
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        raise ValueError(f"{label} must be a safe relative path.")
    return path.as_posix()


def _suite_failure(
    *,
    suite_id: str | None,
    replay_mode: str,
    error_code: str,
    error_message: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = AutonomousBrowserPlannerReplaySuiteSummary(
        schema_version=REPLAY_SUITE_SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        no_runtime_execution=True,
        real_browser_execution=False,
        model_execution=False,
        suite_id=suite_id,
        replay_mode=replay_mode,
        candidates_total=0,
        candidates_accepted=0,
        candidates_rejected=0,
        dry_runs_succeeded=0,
        dry_runs_failed=0,
        fixture_runs_succeeded=0,
        fixture_runs_failed=0,
        actions_attempted_total=0,
        actions_succeeded_total=0,
        actions_failed_total=0,
        expected_results_total=0,
        expected_results_passed=0,
        expected_results_failed=0,
        candidate_summaries=(
            {
                "status": "failed",
                "error_code": error_code,
                "error_message": error_message,
                "no_runtime_execution": True,
                "real_browser_execution": False,
                "model_execution": False,
            },
        ),
        thresholds={
            "expected_min_accepted": DEFAULT_EXPECTED_MIN_ACCEPTED,
            "expected_min_fixture_success": DEFAULT_EXPECTED_MIN_FIXTURE_SUCCESS,
        },
        limitations=limitations,
    )
    return summary.to_dict()


def _limitations() -> tuple[str, ...]:
    return (
        "offline replay suite only",
        "candidate plans only",
        "no LLM calls",
        "no real browser execution",
        "fixture execution remains offline only",
        "guarded Playwright evidence remains separate",
        "not production browser automation",
    )


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0
