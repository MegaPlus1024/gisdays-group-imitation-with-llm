from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_model_comparison_evaluator import (
    CONFIG_SCHEMA_VERSION,
    SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_model_comparison_evaluator,
    write_autonomous_browser_model_comparison_evaluator_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Run the offline model comparison evaluator.")
    parser.add_argument("--config", required=True)
    parser.add_argument("--execute-fixture", action="store_true")
    args = parser.parse_args(argv)

    try:
        config = _load_config(Path(args.config))
        summary = run_autonomous_browser_model_comparison_evaluator(
            config,
            repo_root=PROJECT_ROOT,
            execute_fixture=args.execute_fixture,
        )
        output_dir = config.get("output_dir")
        if output_dir:
            write_autonomous_browser_model_comparison_evaluator_summary(summary, _resolve_repo_path(output_dir))
    except (OSError, json.JSONDecodeError, ValueError) as exc:
        summary = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "status": "failed",
            "error_code": "config_validation_failed",
            "error_message": str(exc),
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
        }
        _emit(summary)
        return 2

    _emit(summary)
    return 0 if summary.get("status") != "failed" else 1


def _load_config(path: Path) -> dict[str, Any]:
    payload = json.loads(path.read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("config root must be a JSON object.")
    if str(payload.get("schema_version", "")) != CONFIG_SCHEMA_VERSION:
        raise ValueError("config schema_version must match autonomous_browser_model_comparison_evaluator_config_v1.")
    if payload.get("no_runtime_execution") is not True:
        raise ValueError("no_runtime_execution must be true.")
    return dict(payload)


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
