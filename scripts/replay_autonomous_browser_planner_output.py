from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_planner_packet import (
    PACKET_SCHEMA_VERSION,
    REPLAY_SUMMARY_SCHEMA_VERSION,
    replay_autonomous_browser_planner_output,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Replay a candidate browser planner output offline.")
    parser.add_argument("--candidate-plan", required=True)
    parser.add_argument("--execute-fixture", action="store_true")
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)

    try:
        summary = replay_autonomous_browser_planner_output(
            _resolve_repo_path(args.candidate_plan),
            repo_root=PROJECT_ROOT,
            execute_fixture=args.execute_fixture,
        )
        if args.output_dir:
            output_dir = _resolve_repo_path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            output_path = output_dir / "autonomous_browser_planner_replay_summary.json"
            output_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        summary = {
            "schema_version": REPLAY_SUMMARY_SCHEMA_VERSION,
            "status": "failed",
            "error_code": "candidate_replay_failed",
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


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
