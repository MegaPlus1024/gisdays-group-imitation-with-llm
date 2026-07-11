from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_stateful_readonly_planner_materializer import (  # noqa: E402 - repo-local import after path setup.
    SUMMARY_SCHEMA_VERSION,
    run_autonomous_browser_stateful_readonly_planner_materializer,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Materialize accepted stateful read-only planner outputs into workflow artifacts.")
    parser.add_argument("--packet-dir", required=True)
    parser.add_argument("--output-dir")
    args = parser.parse_args(argv)

    try:
        summary = run_autonomous_browser_stateful_readonly_planner_materializer(
            _resolve_repo_path(args.packet_dir),
            repo_root=PROJECT_ROOT,
            output_dir=args.output_dir,
        )
        if args.output_dir:
            output_dir = _resolve_repo_path(args.output_dir)
            output_dir.mkdir(parents=True, exist_ok=True)
            summary_path = output_dir / "autonomous_browser_stateful_readonly_planner_materializer_summary.json"
            summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    except (OSError, ValueError) as exc:
        summary = {
            "schema_version": SUMMARY_SCHEMA_VERSION,
            "status": "failed",
            "error_code": "config_validation_failed",
            "error_message": str(exc),
            "outputs_total": 0,
            "outputs_present": 0,
            "outputs_missing": 0,
            "outputs_accepted": 0,
            "outputs_rejected": 0,
            "workflows_materialized": 0,
            "workflows_failed": 0,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "real_network_traffic": False,
            "fixture_only": True,
            "no_runtime_execution": True,
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

