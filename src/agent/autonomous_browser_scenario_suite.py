from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path, PurePosixPath
from typing import Any

from .autonomous_runtime_scenarios import (
    AutonomousRuntimeScenarioValidationError,
    load_autonomous_runtime_scenario,
    run_autonomous_runtime_scenario,
)


SUITE_SCHEMA_VERSION = "autonomous_browser_scenario_suite_v1"
SUITE_SUMMARY_SCHEMA_VERSION = "autonomous_browser_scenario_suite_summary_v1"


class AutonomousBrowserScenarioSuiteValidationError(ValueError):
    """Raised for expected browser scenario suite validation failures."""


@dataclass(frozen=True)
class AutonomousBrowserScenarioSuite:
    schema_version: str
    suite_id: str
    description: str = ""
    scenario_paths: tuple[str, ...] = ()
    expected_min_passed_scenarios: int = 0
    expected_required_actions: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> AutonomousBrowserScenarioSuite:
        suite = cls(
            schema_version=str(payload.get("schema_version", "")),
            suite_id=_required_id(payload, "suite_id"),
            description=str(payload.get("description", "")),
            scenario_paths=tuple(
                _safe_relative_path(path, "scenario_path")
                for path in _string_list(payload.get("scenario_paths"), "scenario_paths")
            ),
            expected_min_passed_scenarios=_int(payload.get("expected_min_passed_scenarios", 0), "expected_min_passed_scenarios"),
            expected_required_actions=tuple(
                _required_browser_action(action)
                for action in _string_list(payload.get("expected_required_actions", []), "expected_required_actions")
            ),
        )
        return suite.validate()

    def validate(self) -> AutonomousBrowserScenarioSuite:
        if self.schema_version != SUITE_SCHEMA_VERSION:
            raise AutonomousBrowserScenarioSuiteValidationError("schema_version does not match autonomous_browser_scenario_suite_v1.")
        if not self.scenario_paths:
            raise AutonomousBrowserScenarioSuiteValidationError("scenario_paths must be non-empty.")
        if self.expected_min_passed_scenarios < 0:
            raise AutonomousBrowserScenarioSuiteValidationError("expected_min_passed_scenarios must be >= 0.")
        if self.expected_min_passed_scenarios > len(self.scenario_paths):
            raise AutonomousBrowserScenarioSuiteValidationError("expected_min_passed_scenarios cannot exceed scenario_count.")
        _reject_duplicates(self.scenario_paths, "scenario_path")
        _reject_duplicates(self.expected_required_actions, "expected_required_action")
        return self


@dataclass(frozen=True)
class AutonomousBrowserScenarioSuiteResult:
    suite: AutonomousBrowserScenarioSuite
    scenario_results: tuple[dict[str, Any], ...] = field(default_factory=tuple)
    no_runtime_execution: bool = True

    def to_summary(self) -> dict[str, Any]:
        return build_browser_scenario_suite_summary(self)


def load_autonomous_browser_scenario_suite(path: str | Path) -> AutonomousBrowserScenarioSuite:
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise AutonomousBrowserScenarioSuiteValidationError("Suite JSON is malformed.") from exc
    except OSError as exc:
        raise AutonomousBrowserScenarioSuiteValidationError("Suite file could not be read.") from exc
    if not isinstance(payload, dict):
        raise AutonomousBrowserScenarioSuiteValidationError("Suite root must be a JSON object.")
    try:
        return AutonomousBrowserScenarioSuite.from_dict(payload)
    except AutonomousBrowserScenarioSuiteValidationError:
        raise
    except Exception as exc:
        raise AutonomousBrowserScenarioSuiteValidationError(str(exc)) from exc


def run_autonomous_browser_scenario_suite(
    suite: AutonomousBrowserScenarioSuite,
    *,
    repo_root: str | Path | None = None,
) -> AutonomousBrowserScenarioSuiteResult:
    root = Path(repo_root) if repo_root is not None else Path(".")
    results: list[dict[str, Any]] = []
    for scenario_path in suite.scenario_paths:
        display_path = PurePosixPath(scenario_path).as_posix()
        try:
            scenario = load_autonomous_runtime_scenario(root / scenario_path)
            scenario_summary = run_autonomous_runtime_scenario(scenario, fixture_root=root)
            scenario_summary["no_runtime_execution"] = True
            passed = bool(scenario_summary.get("expected_results_passed"))
            results.append(
                {
                    "scenario_id": scenario_summary.get("scenario_id", scenario.scenario_id),
                    "scenario_path": display_path,
                    "status": "passed" if passed else "failed",
                    "expected_results_passed": passed,
                    "browser_coverage": scenario_summary.get("browser_coverage", {}),
                    "task_counts": scenario_summary.get("task_counts", {}),
                    "stop_reason": scenario_summary.get("stop_reason"),
                    "browser_sessions": _compact_browser_sessions(scenario_summary),
                    "no_runtime_execution": bool(scenario_summary.get("no_runtime_execution")),
                    "failure_reason": None if passed else "expected_results_failed",
                }
            )
        except AutonomousRuntimeScenarioValidationError as exc:
            results.append(_failed_scenario_result(display_path, "scenario_validation_failed", str(exc)))
        except OSError:
            results.append(_failed_scenario_result(display_path, "scenario_run_failed", "scenario_file_or_fixture_read_failed"))
    return AutonomousBrowserScenarioSuiteResult(suite=suite, scenario_results=tuple(results))


def build_browser_scenario_suite_summary(result: AutonomousBrowserScenarioSuiteResult) -> dict[str, Any]:
    scenario_results = list(result.scenario_results)
    passed = [item for item in scenario_results if item.get("status") == "passed"]
    failed = [item for item in scenario_results if item.get("status") != "passed"]
    required_actions = list(result.suite.expected_required_actions)
    covered_actions = _covered_actions(scenario_results)
    missing_actions = sorted(set(required_actions).difference(covered_actions))
    required_action_set = set(required_actions)
    return {
        "schema_version": SUITE_SUMMARY_SCHEMA_VERSION,
        "suite_id": result.suite.suite_id,
        "scenario_count": len(result.suite.scenario_paths),
        "scenarios_passed": len(passed),
        "scenarios_failed": len(failed),
        "expected_min_passed_scenarios": result.suite.expected_min_passed_scenarios,
        "expected_min_passed_scenarios_met": len(passed) >= result.suite.expected_min_passed_scenarios,
        "required_actions": required_actions,
        "required_actions_covered": sorted(required_action_set.intersection(covered_actions)),
        "required_actions_missing": missing_actions,
        "overall_action_coverage_ratio": (
            len(required_action_set.intersection(covered_actions)) / len(required_action_set)
            if required_action_set
            else 1.0
        ),
        "scenario_summaries": scenario_results,
        "failure_reasons": [
            {
                "scenario_path": str(item.get("scenario_path", "")),
                "scenario_id": item.get("scenario_id"),
                "failure_reason": item.get("failure_reason"),
                "error": item.get("error"),
            }
            for item in failed
        ],
        "no_runtime_execution": result.no_runtime_execution,
    }


def _failed_scenario_result(scenario_path: str, reason: str, error: str) -> dict[str, Any]:
    return {
        "scenario_id": None,
        "scenario_path": scenario_path,
        "status": "failed",
        "expected_results_passed": False,
        "browser_coverage": {},
        "task_counts": {},
        "stop_reason": None,
        "browser_sessions": {},
        "no_runtime_execution": True,
        "failure_reason": reason,
        "error": error,
    }


def _covered_actions(scenario_results: list[dict[str, Any]]) -> set[str]:
    covered: set[str] = set()
    for result in scenario_results:
        coverage = result.get("browser_coverage")
        actions = coverage.get("actions_executed") if isinstance(coverage, dict) else []
        if isinstance(actions, list):
            covered.update(str(action) for action in actions if isinstance(action, str))
    return covered


def _compact_browser_sessions(scenario_summary: Mapping[str, Any]) -> dict[str, dict[str, Any]]:
    sessions = scenario_summary.get("browser_session_summaries")
    if not isinstance(sessions, dict):
        return {}
    compact: dict[str, dict[str, Any]] = {}
    for session_id, session in sessions.items():
        if not isinstance(session, dict):
            continue
        compact[str(session_id)] = {
            "current_url": session.get("current_url"),
            "actions_attempted": session.get("actions_attempted"),
            "actions_succeeded": session.get("actions_succeeded"),
            "actions_failed": session.get("actions_failed"),
            "policy_denials": session.get("policy_denials"),
            "snapshot_count": session.get("snapshot_count"),
            "policy_flags": session.get("policy_flags", {}),
        }
    return compact


def _required_id(payload: Mapping[str, Any], key: str) -> str:
    value = payload.get(key)
    if not isinstance(value, str) or not value.strip():
        raise AutonomousBrowserScenarioSuiteValidationError(f"{key} must be a non-empty string.")
    stripped = value.strip()
    if any(ch in stripped for ch in ("\\", "/", ":", "\0")):
        raise AutonomousBrowserScenarioSuiteValidationError(f"{key} must be a safe identifier.")
    return stripped


def _required_browser_action(value: str) -> str:
    if not value.startswith("browser_"):
        raise AutonomousBrowserScenarioSuiteValidationError("expected_required_actions must be browser actions only.")
    return value


def _safe_relative_path(value: str, label: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        raise AutonomousBrowserScenarioSuiteValidationError(f"{label} must be non-empty.")
    if "://" in normalized or Path(value).is_absolute() or PurePosixPath(normalized).is_absolute():
        raise AutonomousBrowserScenarioSuiteValidationError(f"{label} must be a safe relative path.")
    if any(part == ".." for part in PurePosixPath(normalized).parts):
        raise AutonomousBrowserScenarioSuiteValidationError(f"{label} must not contain traversal.")
    return PurePosixPath(normalized).as_posix()


def _string_list(value: Any, label: str) -> list[str]:
    if value is None:
        return []
    if not isinstance(value, list):
        raise AutonomousBrowserScenarioSuiteValidationError(f"{label} must be a list.")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise AutonomousBrowserScenarioSuiteValidationError(f"{label} must contain non-empty strings.")
        out.append(item.strip())
    return out


def _int(value: Any, label: str) -> int:
    if isinstance(value, bool) or not isinstance(value, int):
        raise AutonomousBrowserScenarioSuiteValidationError(f"{label} must be an integer.")
    return value


def _reject_duplicates(values: tuple[str, ...], label: str) -> None:
    seen: set[str] = set()
    for value in values:
        if value in seen:
            raise AutonomousBrowserScenarioSuiteValidationError(f"Duplicate {label}: {value}")
        seen.add(value)
