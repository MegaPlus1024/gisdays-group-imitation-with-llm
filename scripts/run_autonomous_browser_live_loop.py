from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


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
    parser.add_argument("--planner-backend", choices=["offline_fixture", "scripted", "captured_plan", "local_model"])
    parser.add_argument("--scenario-id")
    parser.add_argument("--output-dir")
    parser.add_argument("--allow-model-calls", action="store_true")
    parser.add_argument("--model-endpoint")
    parser.add_argument("--model-alias")
    args = parser.parse_args(argv)

    try:
        config = _load_config(Path(args.config))
        if args.planner_backend:
            config.setdefault("planner_backend", {})
            config["planner_backend"]["kind"] = args.planner_backend
        if args.scenario_id:
            config["scenario_id"] = args.scenario_id
        if args.output_dir:
            config["output_dir"] = args.output_dir
        if args.allow_model_calls:
            config.setdefault("planner_backend", {})
            config["planner_backend"]["allow_model_calls"] = True
        if args.model_endpoint:
            config.setdefault("planner_backend", {})
            config["planner_backend"]["model_endpoint"] = args.model_endpoint
        if args.model_alias:
            config.setdefault("planner_backend", {})
            config["planner_backend"]["model_alias"] = args.model_alias
        summary = run_autonomous_browser_live_loop(config, repo_root=PROJECT_ROOT)
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
    except (OSError, json.JSONDecodeError, ValueError) as exc:
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


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("live loop config root must be a JSON object.")
    return payload


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
