from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_plan_playwright_replay_operator import (
    AutonomousBrowserPlanPlaywrightReplayOperatorConfigError,
    run_autonomous_browser_plan_playwright_replay_operator,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run guarded replay for a validated model-generated browser plan.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-real-browser", action="store_true")
    parser.add_argument("--confirm-real-browser")
    parser.add_argument("--replay-backend")
    args = parser.parse_args(argv)

    try:
        summary = run_autonomous_browser_plan_playwright_replay_operator(
            args.config,
            repo_root=PROJECT_ROOT,
            allow_real_browser=args.allow_real_browser,
            confirm_real_browser=args.confirm_real_browser,
            dry_run=args.dry_run,
            replay_backend=args.replay_backend,
        )
    except AutonomousBrowserPlanPlaywrightReplayOperatorConfigError as exc:
        print(
            json.dumps(
                {
                    "status": "failed",
                    "error_code": "config_validation_failed",
                    "guard_status": "config_validation_failed",
                    "no_runtime_execution": True,
                    "model_execution": False,
                    "real_browser_execution": False,
                    "error": str(exc),
                },
                ensure_ascii=False,
                separators=(",", ":"),
            )
        )
        return 2

    print(json.dumps(summary, ensure_ascii=False, separators=(",", ":")))
    if summary["status"] == "succeeded":
        return 0
    if summary["status"] == "refused":
        return 2
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
