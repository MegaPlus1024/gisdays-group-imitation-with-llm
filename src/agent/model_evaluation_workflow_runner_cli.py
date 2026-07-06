from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .model_evaluation_workflow_runner import (
    ModelEvaluationWorkflowRunConfig,
    run_offline_model_evaluation_workflow,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run a one-shot offline model evaluation workflow from explicit inputs.",
    )
    parser.add_argument("--model-catalog", default=None, help="Required model catalog JSON.")
    parser.add_argument("--scenario", action="append", default=[], help="Required scenario JSON path. Repeatable.")
    parser.add_argument("--output-dir", default=None, help="Required workflow output directory.")
    parser.add_argument("--repetitions", type=int, default=1, help="Trial repetitions per scenario/pair.")
    parser.add_argument("--include-self-pairs", dest="include_self_pairs", action="store_true", default=True)
    parser.add_argument("--exclude-self-pairs", dest="include_self_pairs", action="store_false")
    parser.add_argument("--include-role-mismatch-pairs", action="store_true", default=False)
    parser.add_argument("--normality-batch-summary", action="append", default=[], help="Optional normality batch summary.")
    parser.add_argument("--resource-observation", action="append", default=[], help="Optional resource observation JSON/JSONL.")
    parser.add_argument("--resource-summary", default=None, help="Optional existing model_resource_summary.json.")
    parser.add_argument("--tag", action="append", default=[], help="Optional workflow tag. Repeatable.")
    parser.add_argument("--workflow-id", default=None, help="Optional workflow id.")
    parser.add_argument("--write-markdown-previews", action="store_true", default=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        if not args.model_catalog:
            _print_json(_invalid_payload("model_catalog_required"))
            return 2
        if not args.scenario:
            _print_json(_invalid_payload("scenario_required"))
            return 2
        if not args.output_dir:
            _print_json(_invalid_payload("output_dir_required"))
            return 2

        config = ModelEvaluationWorkflowRunConfig(
            workflow_id=args.workflow_id,
            model_catalog_path=args.model_catalog,
            scenario_paths=args.scenario,
            output_dir=args.output_dir,
            repetitions_per_pair=args.repetitions,
            include_self_pairs=args.include_self_pairs,
            include_role_mismatch_pairs=args.include_role_mismatch_pairs,
            normality_batch_summary_paths=args.normality_batch_summary,
            resource_observation_paths=args.resource_observation,
            resource_summary_path=args.resource_summary,
            tags=args.tag,
            write_markdown_previews=args.write_markdown_previews,
        )
        result = run_offline_model_evaluation_workflow(config)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json(_invalid_payload(exc.__class__.__name__))
        return 2

    payload = {
        "status": result.status,
        "workflow_id": result.workflow_id,
        "candidate_pair_count": result.candidate_pair_count,
        "trial_count": result.trial_count,
        "readiness_status": result.readiness_status,
        "scorecard_path": result.artifact_paths.get("model_evaluation_scorecard"),
        "bundle_path": result.artifact_paths.get("workflow_bundle"),
        "warning_count": len(result.warnings),
        "no_runtime_execution": result.no_runtime_execution,
    }
    _print_json(payload)
    return 0 if result.status in {"ok", "partial"} else 2


def _invalid_payload(error: str) -> dict[str, object]:
    return {
        "status": "invalid_input",
        "workflow_id": None,
        "candidate_pair_count": 0,
        "trial_count": 0,
        "readiness_status": None,
        "scorecard_path": None,
        "bundle_path": None,
        "warning_count": 0,
        "no_runtime_execution": True,
        "error": error,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
