from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_planner_packet import replay_autonomous_browser_planner_output
from .autonomous_browser_plan_validation import PLAN_SCHEMA_VERSION, validate_autonomous_browser_plan


CONFIG_SCHEMA_VERSION = "autonomous_browser_planner_output_ingestion_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_planner_output_ingestion_summary_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/browser_planner_output_ingestion"


@dataclass(frozen=True)
class AutonomousBrowserPlannerOutputIngestionSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    real_browser_execution: bool
    model_execution: bool
    source_output_path: str | None
    extraction_status: str
    extracted_plan_id: str | None
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
    diagnostics: dict[str, Any] = field(default_factory=dict)
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "real_browser_execution": self.real_browser_execution,
            "model_execution": self.model_execution,
            "source_output_path": self.source_output_path,
            "extraction_status": self.extraction_status,
            "extracted_plan_id": self.extracted_plan_id,
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
            "diagnostics": _jsonable(self.diagnostics),
            "limitations": list(self.limitations),
        }


def ingest_autonomous_browser_planner_output(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    execute_fixture: bool = False,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    config_result = _load_config(config_artifact)
    if config_result["status"] != "ok":
        return _failure_summary(
            source_output_path=config_result.get("source_output_path"),
            error_code=str(config_result.get("error_code") or "config_validation_failed"),
            extraction_status="skipped",
            validation_status="skipped",
            dry_run_status="skipped",
            fixture_execution_status="skipped",
            diagnostics={"config": config_result.get("diagnostics", {})},
            limitations=tuple(config_result.get("limitations") or _limitations()),
        )

    source_output_path = str(config_result["source_output_path"])
    try:
        raw_text = (repo / source_output_path).read_text(encoding="utf-8")
    except OSError:
        return _failure_summary(
            source_output_path=source_output_path,
            error_code="source_output_read_failed",
            extraction_status="skipped",
            validation_status="skipped",
            dry_run_status="skipped",
            fixture_execution_status="skipped",
            diagnostics={
                "source_output": {
                    "finding_type": "source_output_read_failed",
                    "path": "source_output_path",
                }
            },
            limitations=_limitations(),
        )

    extraction = extract_autonomous_browser_plan_candidate(raw_text)
    extraction_status = str(extraction["status"])
    extracted_plan = extraction.get("candidate_plan")
    extracted_plan_id = extraction.get("extracted_plan_id")
    if extraction_status != "accepted" or not isinstance(extracted_plan, Mapping):
        return _failure_summary(
            source_output_path=source_output_path,
            error_code=str(extraction.get("error_code") or "extraction_failed"),
            extracted_plan_id=extracted_plan_id if isinstance(extracted_plan_id, str) else None,
            extraction_status=extraction_status,
            validation_status="skipped",
            dry_run_status="skipped",
            fixture_execution_status="skipped",
            diagnostics={
                "source_output": {"path": source_output_path},
                "extraction": extraction.get("diagnostics", {}),
            },
            limitations=_limitations(),
        )

    validation_result = validate_autonomous_browser_plan(extracted_plan)
    validation_status = str(validation_result.get("status", "rejected"))
    if validation_status != "accepted":
        return _failure_summary(
            source_output_path=source_output_path,
            error_code=str(validation_result.get("error_code") or "plan_validation_failed"),
            extracted_plan_id=str(validation_result.get("plan_id") or extracted_plan_id or ""),
            extraction_status=extraction_status,
            validation_status=validation_status,
            dry_run_status="skipped",
            fixture_execution_status="skipped",
            diagnostics={
                "source_output": {"path": source_output_path},
                "extraction": extraction.get("diagnostics", {}),
                "validation": _validation_diagnostics(validation_result),
            },
            limitations=_limitations(),
        )

    replay_summary = replay_autonomous_browser_planner_output(
        extracted_plan,
        repo_root=repo,
        execute_fixture=execute_fixture,
    )

    status = str(replay_summary.get("status") or "failed")
    summary = AutonomousBrowserPlannerOutputIngestionSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=replay_summary.get("error_code"),
        no_runtime_execution=True,
        real_browser_execution=False,
        model_execution=False,
        source_output_path=source_output_path,
        extraction_status=extraction_status,
        extracted_plan_id=str(replay_summary.get("validation_result", {}).get("plan_id") or extracted_plan_id or ""),
        validation_status=validation_status,
        dry_run_status=str(replay_summary.get("dry_run_status") or "skipped"),
        fixture_execution_status=str(replay_summary.get("fixture_execution_status") or "skipped"),
        actions_total=_int(replay_summary.get("actions_total")),
        actions_attempted=_int(replay_summary.get("actions_attempted")),
        actions_succeeded=_int(replay_summary.get("actions_succeeded")),
        actions_failed=_int(replay_summary.get("actions_failed")),
        expected_results_total=_int(replay_summary.get("expected_results_total")),
        expected_results_passed=_int(replay_summary.get("expected_results_passed")),
        expected_results_failed=_int(replay_summary.get("expected_results_failed")),
        diagnostics={
            "source_output": {"path": source_output_path},
            "extraction": extraction.get("diagnostics", {}),
            "validation": _validation_diagnostics(validation_result),
            "replay": {
                "status": status,
                "error_code": replay_summary.get("error_code"),
                "dry_run_status": replay_summary.get("dry_run_status"),
                "fixture_execution_status": replay_summary.get("fixture_execution_status"),
                "stop_reason": replay_summary.get("stop_reason"),
                "dry_run_summary": replay_summary.get("dry_run_summary", {}),
                "fixture_execution_summary": replay_summary.get("fixture_execution_summary", {}),
            },
        },
        limitations=_limitations(),
    )
    return summary.to_dict()


def write_autonomous_browser_planner_output_ingestion_summary(
    summary: Mapping[str, Any],
    output_dir: str | Path,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_planner_output_ingestion_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def extract_autonomous_browser_plan_candidate(raw_text: str) -> dict[str, Any]:
    spans = _find_top_level_object_spans(raw_text)
    diagnostics = {
        "object_count": len(spans),
        "findings": [],
    }
    if not spans:
        diagnostics["findings"].append({"finding_type": "no_json_object_found"})
        return {
            "status": "rejected",
            "error_code": "no_json_object_found",
            "extracted_plan_id": None,
            "candidate_plan": None,
            "diagnostics": diagnostics,
        }
    if len(spans) > 1:
        diagnostics["findings"].append({"finding_type": "multiple_json_objects_found", "object_count": len(spans)})
        return {
            "status": "rejected",
            "error_code": "multiple_json_objects_found",
            "extracted_plan_id": None,
            "candidate_plan": None,
            "diagnostics": diagnostics,
        }

    candidate_text = spans[0]
    try:
        candidate_plan = json.loads(candidate_text)
    except json.JSONDecodeError:
        diagnostics["findings"].append({"finding_type": "json_parse_failed", "path": "extracted_json"})
        return {
            "status": "rejected",
            "error_code": "json_parse_failed",
            "extracted_plan_id": None,
            "candidate_plan": None,
            "diagnostics": diagnostics,
        }

    if not isinstance(candidate_plan, dict):
        diagnostics["findings"].append({"finding_type": "invalid_json_root", "path": "extracted_json"})
        return {
            "status": "rejected",
            "error_code": "invalid_json_root",
            "extracted_plan_id": None,
            "candidate_plan": None,
            "diagnostics": diagnostics,
        }

    schema_version = str(candidate_plan.get("schema_version", "")).strip()
    plan_id = _safe_text(candidate_plan.get("plan_id"))
    if schema_version != PLAN_SCHEMA_VERSION:
        diagnostics["findings"].append({"finding_type": "wrong_schema_version", "path": "schema_version"})
        return {
            "status": "rejected",
            "error_code": "wrong_schema_version",
            "extracted_plan_id": plan_id,
            "candidate_plan": None,
            "diagnostics": diagnostics,
        }

    return {
        "status": "accepted",
        "error_code": None,
        "extracted_plan_id": plan_id,
        "candidate_plan": candidate_plan,
        "diagnostics": diagnostics,
    }


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
                "diagnostics": {"finding_type": "config_read_failed", "path": "config_artifact"},
            }
        except json.JSONDecodeError:
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "diagnostics": {"finding_type": "config_parse_failed", "path": "config_artifact"},
            }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "diagnostics": {"finding_type": "config_root_must_be_object"},
        }
    if str(payload.get("schema_version", "")) != CONFIG_SCHEMA_VERSION:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "diagnostics": {"finding_type": "config_schema_version_mismatch", "path": "schema_version"},
        }
    source_output_path = _safe_relative_path(payload.get("source_output_path"), "source_output_path")
    if source_output_path is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "diagnostics": {"finding_type": "invalid_relative_path", "path": "source_output_path"},
        }
    output_dir_value = payload.get("output_dir", DEFAULT_OUTPUT_DIR)
    output_dir = _safe_relative_path(output_dir_value, "output_dir")
    if output_dir is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "diagnostics": {"finding_type": "invalid_relative_path", "path": "output_dir"},
        }
    return {
        "status": "ok",
        "source_output_path": source_output_path,
        "output_dir": output_dir,
        "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
    }


def _find_top_level_object_spans(text: str) -> list[str]:
    spans: list[str] = []
    start: int | None = None
    depth = 0
    in_string = False
    escape = False

    for index, char in enumerate(text):
        if start is None:
            if char == "{":
                start = index
                depth = 1
                in_string = False
                escape = False
            continue

        if in_string:
            if escape:
                escape = False
                continue
            if char == "\\":
                escape = True
                continue
            if char == '"':
                in_string = False
            continue

        if char == '"':
            in_string = True
        elif char == "{":
            depth += 1
        elif char == "}":
            depth -= 1
            if depth == 0:
                spans.append(text[start : index + 1])
                start = None

    return spans


def _failure_summary(
    *,
    source_output_path: str | None,
    error_code: str,
    diagnostics: Mapping[str, Any],
    limitations: tuple[str, ...],
    extracted_plan_id: str | None = None,
    extraction_status: str = "rejected",
    validation_status: str = "skipped",
    dry_run_status: str = "skipped",
    fixture_execution_status: str = "skipped",
) -> dict[str, Any]:
    status = "failed" if error_code in {"source_output_read_failed", "config_validation_failed"} else "rejected"
    summary = AutonomousBrowserPlannerOutputIngestionSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        no_runtime_execution=True,
        real_browser_execution=False,
        model_execution=False,
        source_output_path=source_output_path,
        extraction_status=extraction_status,
        extracted_plan_id=extracted_plan_id,
        validation_status=validation_status,
        dry_run_status=dry_run_status,
        fixture_execution_status=fixture_execution_status,
        actions_total=0,
        actions_attempted=0,
        actions_succeeded=0,
        actions_failed=0,
        expected_results_total=0,
        expected_results_passed=0,
        expected_results_failed=0,
        diagnostics=dict(diagnostics),
        limitations=limitations,
    )
    return summary.to_dict()


def _validation_diagnostics(validation_result: Mapping[str, Any]) -> dict[str, Any]:
    return {
        "status": validation_result.get("status"),
        "error_code": validation_result.get("error_code"),
        "plan_id": validation_result.get("plan_id"),
        "actions_total": validation_result.get("actions_total"),
        "diagnostics": [dict(item) for item in validation_result.get("diagnostics", []) if isinstance(item, Mapping)],
    }


def _limitations() -> tuple[str, ...]:
    return (
        "offline ingestion only",
        "captured planner output only",
        "no model calls",
        "no real browser execution",
        "fixture execution remains offline only",
        "guarded Playwright suite evidence remains separate",
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


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set):
        return [_jsonable(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)
