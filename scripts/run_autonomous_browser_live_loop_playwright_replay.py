from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_live_loop_playwright_replay import (  # noqa: E402 - repo-local import after sys.path setup.
    SUMMARY_SCHEMA_VERSION,
    load_autonomous_browser_live_loop_playwright_replay_config,
    run_autonomous_browser_live_loop_playwright_replay,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Prepare guarded Playwright replay for successful live-loop traces.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--dry-run", action="store_true")
    parser.add_argument("--allow-real-browser", action="store_true")
    parser.add_argument("--allow-playwright", action="store_true")
    parser.add_argument("--replay-backend")
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)

    try:
        config = _load_config(_resolve_repo_path(args.config))
        if args.output_dir:
            config["output_dir"] = args.output_dir
        if args.replay_backend:
            config["replay_backend"] = args.replay_backend
        summary = run_autonomous_browser_live_loop_playwright_replay(
            config,
            repo_root=PROJECT_ROOT,
            dry_run=args.dry_run,
            allow_real_browser=args.allow_real_browser,
            allow_playwright=args.allow_playwright,
            replay_backend=args.replay_backend,
        )
        _emit(summary)
        if summary.get("status") == "succeeded":
            return 0
        if summary.get("status") == "refused":
            return 2
        return 1
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "status": "failed",
            "error_code": "config_validation_failed",
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "error": str(exc),
        }
        _emit(payload)
        return 2


def _load_config(path: Path) -> dict[str, Any]:
    return load_autonomous_browser_live_loop_playwright_replay_config(path).to_dict()


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
