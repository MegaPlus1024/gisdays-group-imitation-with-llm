from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_live_loop import (  # noqa: E402 - repo-local import after sys.path setup.
    AutonomousBrowserLiveLoopConfigError,
    run_autonomous_browser_live_loop,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run an offline live autonomous browser loop over local fixtures.")
    parser.add_argument("--config", required=True)
    args = parser.parse_args(argv)

    try:
        summary = run_autonomous_browser_live_loop(Path(args.config), repo_root=PROJECT_ROOT)
        _emit(summary)
        return 0 if summary.get("status") == "succeeded" else 1
    except AutonomousBrowserLiveLoopConfigError as exc:
        payload = {
            "schema_version": "autonomous_browser_live_loop_summary_v1",
            "status": "failed",
            "error_code": "config_validation_failed",
            "error_message": str(exc),
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
        }
        _emit(payload)
        return 2


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
