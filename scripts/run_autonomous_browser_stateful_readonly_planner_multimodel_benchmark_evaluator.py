from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_stateful_readonly_planner_multimodel_benchmark import (  # noqa: E402
    EVALUATOR_SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Run the optional stateful read-only multi-model benchmark evaluator."
    )
    parser.add_argument("--packet-dir", required=True)
    args = parser.parse_args(argv)

    try:
        summary = run_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator(
            packet_dir=_resolve_repo_path(args.packet_dir),
            repo_root=PROJECT_ROOT,
        )
    except (OSError, ValueError) as exc:
        summary = {
            "schema_version": EVALUATOR_SUMMARY_SCHEMA_VERSION,
            "status": "failed",
            "error_code": "config_validation_failed",
            "error_message": str(exc),
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "real_network_traffic": False,
            "fixture_only": True,
        }
        _emit(summary)
        return 2

    _emit(summary)
    return 0 if summary.get("status") == "succeeded" else 1


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
