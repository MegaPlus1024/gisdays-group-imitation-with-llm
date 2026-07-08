from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_scenario_suite import (
    AutonomousBrowserScenarioSuiteValidationError,
    load_autonomous_browser_scenario_suite,
)
from src.agent.autonomous_runtime_browser_suite_integration import (
    INTEGRATION_SCHEMA_VERSION,
    run_autonomous_browser_suite_task,
)


CONFIG_SCHEMA_VERSION = "autonomous_browser_suite_integration_config_v1"
SUMMARY_FILENAME = "autonomous_browser_suite_integration_summary.json"
MARKDOWN_FILENAME = "autonomous_browser_suite_integration_summary.md"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the autonomous runtime to browser suite integration offline.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--markdown-output")
    args = parser.parse_args(argv)

    try:
        config = _load_config(Path(args.config))
        output_dir = _resolve_output_dir(args.output_dir or str(config["output_dir"]))
        suite_path = _resolve_repo_path(str(config["suite_config_path"]))
        suite_payload = json.loads(suite_path.read_text(encoding="utf-8"))
        if not isinstance(suite_payload, dict):
            raise ValueError("suite_config_path must reference a JSON object.")
        suite_payload = _apply_suite_limit(suite_payload, config.get("max_scenarios"))
        summary = run_autonomous_browser_suite_task(
            suite_payload,
            repo_root=PROJECT_ROOT,
            suite_config_display_path=_display_path(suite_path),
        )
        output_dir.mkdir(parents=True, exist_ok=True)
        summary_path = output_dir / SUMMARY_FILENAME
        output_payload = dict(summary)
        output_payload["output_files"] = [_display_path(summary_path)]
        summary_path.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

        markdown_output = args.markdown_output or None
        if markdown_output:
            markdown_path = _resolve_output_path(markdown_output)
            markdown_path.parent.mkdir(parents=True, exist_ok=True)
            markdown_path.write_text(_render_markdown(output_payload), encoding="utf-8")
            output_payload["output_files"].append(_display_path(markdown_path))
            summary_path.write_text(json.dumps(output_payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    except (OSError, json.JSONDecodeError, ValueError, AutonomousBrowserScenarioSuiteValidationError) as exc:
        payload = {
            "schema_version": INTEGRATION_SCHEMA_VERSION,
            "status": "invalid_input",
            "error_code": "config_validation_failed",
            "error_message": str(exc),
            "no_runtime_execution": True,
        }
        _emit(payload)
        return 2

    _emit(_compact_output(output_payload))
    return 0 if output_payload.get("status") == "succeeded" else 1


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(payload, dict):
        raise ValueError("config root must be a JSON object.")
    if str(payload.get("schema_version", "")) != CONFIG_SCHEMA_VERSION:
        raise ValueError("config schema_version must match autonomous_browser_suite_integration_config_v1.")
    if not isinstance(payload.get("no_runtime_execution"), bool) or payload["no_runtime_execution"] is not True:
        raise ValueError("no_runtime_execution must be true.")
    integration_id = _safe_identifier(payload.get("integration_id"), "integration_id")
    suite_config_path = _safe_relative_path(str(payload.get("suite_config_path", "")), "suite_config_path")
    output_dir = _safe_relative_path(str(payload.get("output_dir", "")), "output_dir")
    expected_required_actions = _string_list(payload.get("expected_required_actions"), "expected_required_actions")
    max_scenarios = payload.get("max_scenarios")
    if max_scenarios is not None:
        if isinstance(max_scenarios, bool) or not isinstance(max_scenarios, int) or max_scenarios < 1:
            raise ValueError("max_scenarios must be a positive integer when provided.")
    notes = str(payload.get("notes", "")).strip()
    suite = load_autonomous_browser_scenario_suite(_resolve_repo_path(suite_config_path))
    if expected_required_actions != list(suite.expected_required_actions):
        raise ValueError("expected_required_actions must match the suite config.")
    if max_scenarios is not None and max_scenarios > len(suite.scenario_paths):
        raise ValueError("max_scenarios cannot exceed the suite scenario count.")
    return {
        "integration_id": integration_id,
        "suite_config_path": suite_config_path,
        "output_dir": output_dir,
        "max_scenarios": max_scenarios,
        "expected_required_actions": expected_required_actions,
        "notes": notes,
    }


def _apply_suite_limit(payload: dict[str, Any], max_scenarios: int | None) -> dict[str, Any]:
    if max_scenarios is None:
        return payload
    scenario_paths = payload.get("scenario_paths")
    if not isinstance(scenario_paths, list):
        raise ValueError("suite scenario_paths must be a list.")
    if max_scenarios > len(scenario_paths):
        raise ValueError("max_scenarios cannot exceed the suite scenario count.")
    limited = dict(payload)
    limited["scenario_paths"] = scenario_paths[:max_scenarios]
    expected_min = limited.get("expected_min_passed_scenarios", max_scenarios)
    if isinstance(expected_min, int) and not isinstance(expected_min, bool):
        limited["expected_min_passed_scenarios"] = min(expected_min, max_scenarios)
    else:
        limited["expected_min_passed_scenarios"] = max_scenarios
    return limited


def _render_markdown(payload: dict[str, Any]) -> str:
    lines = [
        "# Autonomous Browser Suite Integration",
        "",
        f"- status: {payload.get('status')}",
        f"- browser_suite_status: {payload.get('browser_suite_status')}",
        f"- stop_reason: {payload.get('stop_reason')}",
        f"- runtime_trace_event_count: {payload.get('runtime_trace_event_count')}",
        f"- scenarios: {payload.get('scenarios_succeeded')}/{payload.get('scenarios_attempted')}",
        f"- actions: {payload.get('actions_succeeded')}/{payload.get('actions_attempted')}",
        f"- expected_results: {payload.get('expected_results_passed')}/{payload.get('expected_results_total')}",
        f"- required_actions_covered: {len(payload.get('required_actions_covered', []))}",
        f"- required_actions_missing: {', '.join(payload.get('required_actions_missing', [])) or 'none'}",
        f"- no_runtime_execution: {payload.get('no_runtime_execution')}",
        "",
        "## Limitations",
        "",
    ]
    lines.extend(f"- {item}" for item in payload.get("limitations", []))
    return "\n".join(lines) + "\n"


def _compact_output(payload: dict[str, Any]) -> dict[str, Any]:
    compact = dict(payload)
    if "output_files" in compact and not compact["output_files"]:
        compact.pop("output_files")
    return compact


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _resolve_output_dir(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _resolve_output_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _display_path(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(PROJECT_ROOT.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return path.name


def _safe_identifier(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise ValueError(f"{label} must be a non-empty string.")
    stripped = value.strip()
    if any(ch in stripped for ch in ("\\", "/", ":", "\0")):
        raise ValueError(f"{label} must be a safe identifier.")
    return stripped


def _safe_relative_path(value: str, label: str) -> str:
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        raise ValueError(f"{label} must be non-empty.")
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        raise ValueError(f"{label} must be a safe relative path.")
    return path.as_posix()


def _string_list(value: Any, label: str) -> list[str]:
    if not isinstance(value, list):
        raise ValueError(f"{label} must be a list.")
    out: list[str] = []
    for item in value:
        if not isinstance(item, str) or not item.strip():
            raise ValueError(f"{label} must contain non-empty strings.")
        out.append(item.strip())
    return out


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
