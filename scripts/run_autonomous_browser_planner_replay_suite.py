from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_planner_replay_suite import (
    REPLAY_SUITE_SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_planner_replay_suite,
    write_autonomous_browser_planner_replay_suite_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an offline replay suite for browser planner candidates.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--output-dir")
    parser.add_argument("--execute-fixture", action="store_true")
    args = parser.parse_args(argv)

    try:
        summary = run_autonomous_browser_planner_replay_suite(
            _resolve_repo_path(args.config),
            repo_root=PROJECT_ROOT,
            execute_fixture=args.execute_fixture,
        )
        output_dir = args.output_dir or _maybe_output_dir(summary)
        if output_dir:
            write_autonomous_browser_planner_replay_suite_summary(summary, _resolve_repo_path(output_dir))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        summary = {
            "schema_version": REPLAY_SUITE_SUMMARY_SCHEMA_VERSION,
            "status": "failed",
            "error_code": "suite_run_failed",
            "error_message": str(exc),
            "no_runtime_execution": True,
            "real_browser_execution": False,
            "model_execution": False,
        }
        _emit(summary)
        return 2

    _emit(summary)
    return 0 if summary.get("status") == "succeeded" else 1


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _maybe_output_dir(summary: dict[str, Any]) -> str | None:
    del summary
    return "artifacts/autonomous_runtime_summaries/browser_planner_replay_suite"


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
