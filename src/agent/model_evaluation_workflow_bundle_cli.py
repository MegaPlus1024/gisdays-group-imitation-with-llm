from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .model_evaluation_workflow_bundle import (
    MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME,
    build_model_evaluation_workflow_bundle,
    write_model_evaluation_workflow_bundle,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an offline model evaluation workflow bundle from existing JSON artifacts.",
    )
    parser.add_argument("--model-catalog", required=True, help="Required model catalog JSON.")
    parser.add_argument("--model-comparison-plan", required=True, help="Required model comparison plan JSON.")
    parser.add_argument("--readiness-report", required=True, help="Required readiness report JSON.")
    parser.add_argument("--normality-comparison-summary", default=None, help="Optional normality comparison summary JSON.")
    parser.add_argument("--model-resource-summary", default=None, help="Optional model resource summary JSON.")
    parser.add_argument("--model-evaluation-scorecard", default=None, help="Optional model evaluation scorecard JSON.")
    parser.add_argument("--output-dir", required=True, help="Directory for model_evaluation_workflow_bundle.json.")
    parser.add_argument("--bundle-id", default="model_evaluation_workflow_bundle", help="Optional bundle id.")
    parser.add_argument("--write-markdown-preview", action="store_true", default=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        output_dir = Path(args.output_dir)
        bundle = build_model_evaluation_workflow_bundle(
            model_catalog_path=args.model_catalog,
            model_comparison_plan_path=args.model_comparison_plan,
            readiness_report_path=args.readiness_report,
            normality_comparison_summary_path=args.normality_comparison_summary,
            model_resource_summary_path=args.model_resource_summary,
            model_evaluation_scorecard_path=args.model_evaluation_scorecard,
            bundle_id=args.bundle_id,
            base_dir=output_dir.parent,
        )
        bundle_path, _ = write_model_evaluation_workflow_bundle(
            bundle,
            output_dir,
            write_markdown_preview=args.write_markdown_preview,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json(_invalid_payload(exc.__class__.__name__))
        return 2

    optional_present = bundle.summary.get("optional_artifacts_present", [])
    payload = {
        "status": bundle.status,
        "bundle_id": bundle.bundle_id,
        "required_artifacts_ok": bool(bundle.summary.get("required_artifacts_ok")),
        "optional_artifacts_present": optional_present if isinstance(optional_present, list) else [],
        "warning_count": len(bundle.warnings),
        "bundle_path": bundle_path.name if bundle_path.name else MODEL_EVALUATION_WORKFLOW_BUNDLE_FILENAME,
        "no_runtime_execution": bundle.no_runtime_execution,
    }
    _print_json(payload)
    return 0 if bundle.status != "invalid" else 2


def _invalid_payload(error: str) -> dict[str, object]:
    return {
        "status": "invalid_input",
        "bundle_id": None,
        "required_artifacts_ok": False,
        "optional_artifacts_present": [],
        "warning_count": 0,
        "bundle_path": None,
        "no_runtime_execution": True,
        "error": error,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
