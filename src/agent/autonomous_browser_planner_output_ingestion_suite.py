from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_planner_output_ingestion import (
    CONFIG_SCHEMA_VERSION as INGESTION_CONFIG_SCHEMA_VERSION,
    ingest_autonomous_browser_planner_output,
    write_autonomous_browser_planner_output_ingestion_summary,
)


SUITE_CONFIG_SCHEMA_VERSION = "autonomous_browser_planner_output_ingestion_suite_config_v1"
SUITE_SUMMARY_SCHEMA_VERSION = "autonomous_browser_planner_output_ingestion_suite_summary_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/browser_planner_output_ingestion_suite"
DEFAULT_EXPECTED_MIN_INGESTED = 1
DEFAULT_EXPECTED_MAX_REJECTED = 0
DEFAULT_REPLAY_MODE = "dry_run"
ALLOWED_REPLAY_MODES = ("dry_run", "fixture_execution")


@dataclass(frozen=True)
class AutonomousBrowserPlannerOutputIngestionSuiteSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    real_browser_execution: bool
    model_execution: bool
    suite_id: str | None
    replay_mode: str
    outputs_total: int
    outputs_ingested: int
    outputs_rejected: int
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
    output_summaries: tuple[dict[str, Any], ...] = ()
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
            "outputs_total": self.outputs_total,
            "outputs_ingested": self.outputs_ingested,
            "outputs_rejected": self.outputs_rejected,
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
            "output_summaries": [dict(item) for item in self.output_summaries],
            "thresholds": dict(self.thresholds),
            "limitations": list(self.limitations),
        }


def run_autonomous_browser_planner_output_ingestion_suite(
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
            limitations=tuple(config_result.get("limitations") or _limitations()),
        )

    suite_id = str(config_result["suite_id"])
    output_paths = tuple(str(path) for path in config_result["captured_outputs"])
    replay_mode = "fixture_execution" if execute_fixture else str(config_result["replay_mode"])
    expected_min_ingested = _int(config_result["expected_min_ingested"])
    expected_max_rejected = _int(config_result["expected_max_rejected"])
    output_dir = str(config_result["output_dir"])
    output_summaries: list[dict[str, Any]] = []
    outputs_ingested = 0
    outputs_rejected = 0
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
    any_issue = False
    first_issue_code: str | None = None

    for index, output_path_value in enumerate(output_paths):
        output_summary = _ingest_captured_output(
            output_path_value,
            repo_root=repo,
            output_dir=_child_output_dir(output_dir, index),
            replay_mode=replay_mode,
            output_index=index,
            execute_fixture=execute_fixture or replay_mode == "fixture_execution",
        )
        output_summaries.append(output_summary)

        status = str(output_summary.get("status") or "failed")
        if status == "succeeded":
            outputs_ingested += 1
        else:
            outputs_rejected += 1
            any_issue = True
            if first_issue_code is None:
                first_issue_code = str(output_summary.get("error_code") or "captured_output_failed")

        if str(output_summary.get("dry_run_status")) == "accepted":
            dry_runs_succeeded += 1
        else:
            dry_runs_failed += 1

        if replay_mode == "fixture_execution" or execute_fixture:
            if str(output_summary.get("fixture_execution_status")) == "succeeded":
                fixture_runs_succeeded += 1
            else:
                fixture_runs_failed += 1

        actions_attempted_total += _int(output_summary.get("actions_attempted"))
        actions_succeeded_total += _int(output_summary.get("actions_succeeded"))
        actions_failed_total += _int(output_summary.get("actions_failed"))
        expected_results_total += _int(output_summary.get("expected_results_total"))
        expected_results_passed += _int(output_summary.get("expected_results_passed"))
        expected_results_failed += _int(output_summary.get("expected_results_failed"))

    thresholds_met = outputs_ingested >= expected_min_ingested and outputs_rejected <= expected_max_rejected
    if not output_summaries:
        status = "failed"
        error_code = "no_captured_outputs_provided"
    elif not thresholds_met:
        status = "failed"
        error_code = first_issue_code or "suite_thresholds_not_met"
    elif any_issue:
        status = "completed_with_failures"
        error_code = first_issue_code or "suite_completed_with_failures"
    else:
        status = "succeeded"
        error_code = None

    summary = AutonomousBrowserPlannerOutputIngestionSuiteSummary(
        schema_version=SUITE_SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        no_runtime_execution=True,
        real_browser_execution=False,
        model_execution=False,
        suite_id=suite_id,
        replay_mode=replay_mode,
        outputs_total=len(output_summaries),
        outputs_ingested=outputs_ingested,
        outputs_rejected=outputs_rejected,
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
        output_summaries=tuple(output_summaries),
        thresholds={
            "expected_min_ingested": expected_min_ingested,
            "expected_max_rejected": expected_max_rejected,
        },
        limitations=_limitations(),
    )
    return summary.to_dict()


def write_autonomous_browser_planner_output_ingestion_suite_summary(
    summary: Mapping[str, Any],
    output_dir: str | Path,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_planner_output_ingestion_suite_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _load_suite_config(config_artifact: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config_artifact, Mapping):
        payload = dict(config_artifact)
    else:
        try:
            payload = json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))
        except OSError:
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "suite_id": None,
                "replay_mode": DEFAULT_REPLAY_MODE,
                "limitations": _limitations(),
            }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "suite_id": None,
            "replay_mode": DEFAULT_REPLAY_MODE,
            "limitations": _limitations(),
        }
    if str(payload.get("schema_version", "")) != SUITE_CONFIG_SCHEMA_VERSION:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "suite_id": _safe_text(payload.get("suite_id")),
            "replay_mode": str(payload.get("replay_mode", DEFAULT_REPLAY_MODE)).strip() or DEFAULT_REPLAY_MODE,
            "limitations": _limitations(),
        }
    suite_id = _safe_text(payload.get("suite_id"))
    captured_outputs = payload.get("captured_outputs")
    replay_mode = str(payload.get("replay_mode", DEFAULT_REPLAY_MODE)).strip()
    output_dir_value = payload.get("output_dir", DEFAULT_OUTPUT_DIR)
    expected_min_ingested = payload.get("expected_min_ingested", DEFAULT_EXPECTED_MIN_INGESTED)
    expected_max_rejected = payload.get("expected_max_rejected", DEFAULT_EXPECTED_MAX_REJECTED)
    if not suite_id:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "suite_id": None,
            "replay_mode": replay_mode or DEFAULT_REPLAY_MODE,
            "limitations": _limitations(),
        }
    if replay_mode not in ALLOWED_REPLAY_MODES:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "suite_id": suite_id,
            "replay_mode": replay_mode,
            "limitations": _limitations(),
        }
    if not isinstance(captured_outputs, list) or not captured_outputs:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "suite_id": suite_id,
            "replay_mode": replay_mode,
            "limitations": _limitations(),
        }

    cleaned_captured_outputs: list[str] = []
    for index, candidate in enumerate(captured_outputs):
        safe_output = _safe_relative_path(candidate)
        if safe_output is None:
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "suite_id": suite_id,
                "replay_mode": replay_mode,
                "limitations": _limitations(),
            }
        cleaned_captured_outputs.append(safe_output)

    safe_output_dir = _safe_relative_path(output_dir_value)
    if safe_output_dir is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "suite_id": suite_id,
            "replay_mode": replay_mode,
            "limitations": _limitations(),
        }
    if not isinstance(expected_min_ingested, int) or isinstance(expected_min_ingested, bool) or expected_min_ingested < 0:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "suite_id": suite_id,
            "replay_mode": replay_mode,
            "limitations": _limitations(),
        }
    if not isinstance(expected_max_rejected, int) or isinstance(expected_max_rejected, bool) or expected_max_rejected < 0:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "suite_id": suite_id,
            "replay_mode": replay_mode,
            "limitations": _limitations(),
        }
    return {
        "status": "ok",
        "suite_id": suite_id,
        "captured_outputs": cleaned_captured_outputs,
        "replay_mode": replay_mode,
        "output_dir": safe_output_dir,
        "expected_min_ingested": expected_min_ingested,
        "expected_max_rejected": expected_max_rejected,
        "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
    }


def _ingest_captured_output(
    captured_output_path: str,
    *,
    repo_root: Path,
    output_dir: str,
    replay_mode: str,
    output_index: int,
    execute_fixture: bool,
) -> dict[str, Any]:
    output_path = repo_root / captured_output_path
    if not output_path.exists():
        output_summary = {
            "output_index": output_index,
            "captured_output_path": captured_output_path,
            "status": "failed",
            "error_code": "missing_captured_output_file",
            "no_runtime_execution": True,
            "real_browser_execution": False,
            "model_execution": False,
            "validation_status": "skipped",
            "dry_run_status": "skipped",
            "fixture_execution_status": "skipped",
            "actions_total": 0,
            "actions_attempted": 0,
            "actions_succeeded": 0,
            "actions_failed": 0,
            "expected_results_total": 0,
            "expected_results_passed": 0,
            "expected_results_failed": 0,
            "limitations": list(_limitations()),
        }
        output_summary["ingestion_summary"] = dict(output_summary)
        return output_summary

    summary = ingest_autonomous_browser_planner_output(
        {
            "schema_version": INGESTION_CONFIG_SCHEMA_VERSION,
            "source_output_path": captured_output_path,
            "output_dir": output_dir,
            "limitations": ["suite ingestion"],
        },
        repo_root=repo_root,
        execute_fixture=execute_fixture,
    )
    output_summary = dict(summary)
    output_summary["output_index"] = output_index
    output_summary["captured_output_path"] = captured_output_path
    output_summary["replay_mode"] = replay_mode
    output_summary["ingestion_summary"] = dict(summary)
    return output_summary


def _child_output_dir(parent_output_dir: str, index: int) -> str:
    return f"{parent_output_dir}/output_{index:03d}"


def _suite_failure(
    *,
    suite_id: str | None,
    replay_mode: str,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = AutonomousBrowserPlannerOutputIngestionSuiteSummary(
        schema_version=SUITE_SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        no_runtime_execution=True,
        real_browser_execution=False,
        model_execution=False,
        suite_id=suite_id,
        replay_mode=replay_mode,
        outputs_total=0,
        outputs_ingested=0,
        outputs_rejected=0,
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
        output_summaries=(),
        thresholds={
            "expected_min_ingested": DEFAULT_EXPECTED_MIN_INGESTED,
            "expected_max_rejected": DEFAULT_EXPECTED_MAX_REJECTED,
        },
        limitations=limitations,
    )
    return summary.to_dict()


def _limitations() -> tuple[str, ...]:
    return (
        "offline ingestion suite only",
        "captured planner outputs only",
        "no model calls",
        "no real browser execution",
        "fixture execution remains offline only",
        "guarded Playwright suite evidence remains separate",
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
