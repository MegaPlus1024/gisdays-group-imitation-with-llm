from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .model_evaluation_artifact_validator import (
    REQUIRED_WORKFLOW_OUTPUT_ARTIFACTS,
    validate_model_evaluation_artifacts,
    validate_model_evaluation_workflow_output_dir,
    write_model_evaluation_artifact_validation_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Validate already-created offline model evaluation workflow artifacts.",
    )
    parser.add_argument("--workflow-output-dir", default=None, help="Existing workflow output directory.")
    parser.add_argument("--plan", default=None, help="Existing model_comparison_plan.json.")
    parser.add_argument("--readiness-report", default=None, help="Existing model_comparison_readiness_report.json.")
    parser.add_argument("--normality-comparison-summary", default=None, help="Existing normality_comparison_summary.json.")
    parser.add_argument("--model-resource-summary", default=None, help="Existing model_resource_summary.json.")
    parser.add_argument("--scorecard", default=None, help="Existing model_evaluation_scorecard.json.")
    parser.add_argument("--workflow-bundle", default=None, help="Existing model_evaluation_workflow_bundle.json.")
    parser.add_argument("--workflow-run-manifest", default=None, help="Existing workflow_run_manifest.json.")
    parser.add_argument("--output-dir", required=True, help="Validation report output directory.")
    parser.add_argument("--validation-id", default="model_evaluation_artifact_validation")
    parser.add_argument("--strict", action="store_true", default=False, help="Return nonzero on warnings.")
    parser.add_argument("--write-markdown-preview", action="store_true", default=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        conflict = _mode_conflict(args)
        if conflict is not None:
            _print_json(_invalid_payload(args.validation_id, conflict))
            return 2

        if args.workflow_output_dir:
            report = validate_model_evaluation_workflow_output_dir(
                args.workflow_output_dir,
                validation_id=args.validation_id,
            )
        else:
            report = validate_model_evaluation_artifacts(
                plan_path=args.plan,
                readiness_report_path=args.readiness_report,
                normality_comparison_summary_path=args.normality_comparison_summary,
                model_resource_summary_path=args.model_resource_summary,
                scorecard_path=args.scorecard,
                workflow_bundle_path=args.workflow_bundle,
                workflow_run_manifest_path=args.workflow_run_manifest,
                validation_id=args.validation_id,
                required_artifacts=REQUIRED_WORKFLOW_OUTPUT_ARTIFACTS if _explicit_full_workflow(args) else (),
            )

        report_path, _ = write_model_evaluation_artifact_validation_report(
            report,
            args.output_dir,
            write_markdown_preview=args.write_markdown_preview,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json(_invalid_payload("model_evaluation_artifact_validation", exc.__class__.__name__))
        return 2

    payload = {
        "status": report.status,
        "validation_id": report.validation_id,
        "checked_artifact_count": report.artifact_count,
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "report_path": report_path.name,
        "no_runtime_execution": report.no_runtime_execution,
    }
    _print_json(payload)
    if report.status == "invalid":
        return 2
    if args.strict and report.warning_count:
        return 2
    return 0


def _mode_conflict(args: argparse.Namespace) -> str | None:
    explicit_paths = [
        args.plan,
        args.readiness_report,
        args.normality_comparison_summary,
        args.model_resource_summary,
        args.scorecard,
        args.workflow_bundle,
        args.workflow_run_manifest,
    ]
    if args.workflow_output_dir and any(explicit_paths):
        return "workflow_output_dir_conflicts_with_explicit_paths"
    if not args.workflow_output_dir and not any(explicit_paths):
        return "artifact_input_required"
    return None


def _explicit_full_workflow(args: argparse.Namespace) -> bool:
    return all(
        [
            args.plan,
            args.readiness_report,
            args.scorecard,
            args.workflow_bundle,
            args.workflow_run_manifest,
        ]
    )


def _invalid_payload(validation_id: str, error: str) -> dict[str, object]:
    return {
        "status": "invalid_input",
        "validation_id": validation_id,
        "checked_artifact_count": 0,
        "error_count": 1,
        "warning_count": 0,
        "report_path": None,
        "no_runtime_execution": True,
        "error": error,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
