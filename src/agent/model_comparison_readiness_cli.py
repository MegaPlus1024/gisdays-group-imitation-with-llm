from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .model_catalog import load_model_catalog
from .model_comparison_readiness import (
    MODEL_COMPARISON_READINESS_REPORT_FILENAME,
    load_model_comparison_plan_for_readiness,
    validate_model_comparison_readiness,
    write_model_comparison_readiness_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate offline model-comparison plan readiness without runtime execution.",
    )
    parser.add_argument("--plan", required=True, help="Path to model_comparison_plan.json.")
    parser.add_argument("--model-catalog", default=None, help="Optional model catalog JSON.")
    parser.add_argument(
        "--registry",
        default="configs/script_registry.example.json",
        help="Optional script registry JSON.",
    )
    parser.add_argument("--output-dir", required=True, help="Directory for readiness report output.")
    parser.add_argument(
        "--scenario-root",
        default=None,
        help="Root used for relative scenario and role paths. Defaults to the current directory.",
    )
    parser.add_argument("--strict", action="store_true", default=False, help="Return non-zero on warnings.")
    parser.add_argument("--write-markdown-preview", action="store_true", default=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        scenario_root = Path(args.scenario_root) if args.scenario_root else Path.cwd()
        plan = load_model_comparison_plan_for_readiness(args.plan)
        catalog = load_model_catalog(args.model_catalog) if args.model_catalog else None
        report = validate_model_comparison_readiness(
            plan,
            model_catalog=catalog,
            registry_path=args.registry,
            scenario_root=scenario_root,
        )
        report_path, _ = write_model_comparison_readiness_report(
            report,
            args.output_dir,
            write_markdown_preview=args.write_markdown_preview,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json(_invalid_payload(exc.__class__.__name__))
        return 2

    payload = {
        "status": report.status,
        "plan_id": report.plan_id,
        "trial_count": report.trial_count,
        "issue_count": report.summary.get("issue_count", len(report.issues)),
        "error_count": report.summary.get("error_count", 0),
        "warning_count": report.summary.get("warning_count", 0),
        "report_path": report_path.name if report_path.name else MODEL_COMPARISON_READINESS_REPORT_FILENAME,
        "no_runtime_execution": report.no_runtime_execution,
    }
    _print_json(payload)
    if report.status == "not_ready":
        return 2
    if args.strict and payload["warning_count"]:
        return 2
    return 0


def _invalid_payload(error: str) -> dict[str, object]:
    return {
        "status": "invalid_input",
        "plan_id": None,
        "trial_count": 0,
        "issue_count": 0,
        "error_count": 0,
        "warning_count": 0,
        "report_path": None,
        "no_runtime_execution": True,
        "error": error,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
