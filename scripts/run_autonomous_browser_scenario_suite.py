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
    run_autonomous_browser_scenario_suite,
)
from src.agent.autonomous_runtime_scenarios import (
    AutonomousRuntimeScenarioValidationError,
    write_autonomous_runtime_scenario_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an offline fixture-backed autonomous browser scenario suite.")
    parser.add_argument("--suite", required=True)
    parser.add_argument("--output")
    parser.add_argument("--dry-run", action="store_true", help="Explicitly document that this run is fixture-only.")
    args = parser.parse_args(argv)

    try:
        suite = load_autonomous_browser_scenario_suite(args.suite)
        result = run_autonomous_browser_scenario_suite(suite, repo_root=PROJECT_ROOT)
        summary = result.to_summary()
        summary["dry_run"] = bool(args.dry_run)
        summary["no_runtime_execution"] = True
        if args.output:
            output_path = write_autonomous_runtime_scenario_summary(summary, args.output)
            summary["summary_path"] = _display_path(output_path)
    except (AutonomousBrowserScenarioSuiteValidationError, AutonomousRuntimeScenarioValidationError) as exc:
        _emit({"status": "invalid_input", "error": str(exc), "no_runtime_execution": True})
        return 2
    except OSError:
        _emit({"status": "write_failed", "error": "autonomous_browser_scenario_suite_output_write_failed", "no_runtime_execution": True})
        return 1

    _emit(summary)
    ok = bool(summary.get("expected_min_passed_scenarios_met")) and not summary.get("required_actions_missing")
    return 0 if ok else 1


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _display_path(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(Path.cwd().resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return path.name


if __name__ == "__main__":
    raise SystemExit(main())
