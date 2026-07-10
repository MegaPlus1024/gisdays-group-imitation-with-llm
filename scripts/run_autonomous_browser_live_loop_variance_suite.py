from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_live_loop_variance_suite import (  # noqa: E402 - repo-local import after sys.path setup.
    CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_live_loop_variance_suite,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline guarded local-model live-loop variance suite.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--planner-backend", choices=["local_model"])
    parser.add_argument("--model-alias")
    parser.add_argument("--model-endpoint")
    parser.add_argument("--output-dir")
    parser.add_argument("--trial-label-prefix")
    parser.add_argument("--allow-model-calls", action="store_true")
    args = parser.parse_args(argv)

    try:
        config = _load_config(_resolve_repo_path(args.config))
        if args.planner_backend:
            config["planner_backend"] = args.planner_backend
        if args.model_alias:
            config["model_alias"] = args.model_alias
        if args.model_endpoint:
            config["model_endpoint"] = args.model_endpoint
        if args.output_dir:
            config["output_dir"] = args.output_dir
        if args.trial_label_prefix:
            config["trial_label_prefix"] = args.trial_label_prefix
        if args.allow_model_calls:
            config["allow_model_calls"] = True
        summary = run_autonomous_browser_live_loop_variance_suite(config, repo_root=PROJECT_ROOT)
        _emit(summary)
        if summary.get("status") == "succeeded":
            return 0
        if summary.get("error_code") == "config_validation_failed":
            return 2
        return 1
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        payload = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "status": "failed",
            "error_code": "config_validation_failed",
            "error_message": str(exc),
            "no_runtime_execution": True,
            "model_execution_attempted": False,
            "model_execution_completed": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
        }
        _emit(payload)
        return 2


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("variance suite config root must be a JSON object.")
    if str(payload.get("schema_version", "")) != CONFIG_SCHEMA_VERSION:
        raise ValueError("variance suite config schema_version must match autonomous_browser_live_loop_variance_suite_config_v1.")
    return dict(payload)


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
