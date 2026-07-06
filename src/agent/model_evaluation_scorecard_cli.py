from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .model_evaluation_scorecard import (
    MODEL_EVALUATION_SCORECARD_FILENAME,
    load_json_summary,
    run_model_evaluation_scorecard,
)
from .model_task_correctness_evaluation import TaskCorrectnessBatchSummary


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an offline combined model evaluation scorecard.",
    )
    parser.add_argument("--model-catalog", default=None, help="Required model catalog JSON.")
    parser.add_argument("--output-dir", default=None, help="Directory for model_evaluation_scorecard.json.")
    parser.add_argument("--model-comparison-plan", default=None, help="Optional model_comparison_plan.json.")
    parser.add_argument(
        "--normality-comparison-summary",
        default=None,
        help="Optional normality_comparison_summary.json.",
    )
    parser.add_argument("--model-resource-summary", default=None, help="Optional model_resource_summary.json.")
    parser.add_argument("--task-correctness-summary", default=None, help="Optional task_correctness_batch_summary.json.")
    parser.add_argument("--scorecard-id", default="model_evaluation_scorecard", help="Optional scorecard id.")
    parser.add_argument("--write-markdown-preview", action="store_true", default=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        if not args.model_catalog:
            _print_json(_invalid_payload("model_catalog_required"))
            return 2
        if not args.output_dir:
            _print_json(_invalid_payload("output_dir_required"))
            return 2

        task_correctness_summary = None
        if args.task_correctness_summary:
            loaded_correctness = load_json_summary(args.task_correctness_summary, project_root=Path.cwd())
            if loaded_correctness.status != "ok" or loaded_correctness.payload is None:
                error = (
                    "task_correctness_summary_missing"
                    if loaded_correctness.status == "input_missing"
                    else "task_correctness_summary_invalid_input"
                )
                _print_json(_invalid_payload(error))
                return 2
            try:
                task_correctness_summary = TaskCorrectnessBatchSummary.model_validate(
                    loaded_correctness.payload
                ).model_dump(mode="json")
            except ValueError:
                _print_json(_invalid_payload("task_correctness_summary_invalid_input"))
                return 2

        scorecard = run_model_evaluation_scorecard(
            args.model_catalog,
            args.output_dir,
            model_comparison_plan_path=args.model_comparison_plan,
            normality_comparison_summary_path=args.normality_comparison_summary,
            model_resource_summary_path=args.model_resource_summary,
            task_correctness_summary=task_correctness_summary,
            scorecard_id=args.scorecard_id,
            project_root=Path.cwd(),
            write_markdown_preview=args.write_markdown_preview,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json(_invalid_payload(exc.__class__.__name__))
        return 2

    _print_json(
        {
            "status": scorecard.status,
            "scorecard_id": scorecard.scorecard_id,
            "model_count": scorecard.model_count,
            "model_pair_count": scorecard.model_pair_count,
            "warnings_count": len(scorecard.warnings),
            "scorecard_path": scorecard.scorecard_path_relative or MODEL_EVALUATION_SCORECARD_FILENAME,
            "markdown_preview_path": scorecard.markdown_preview_path_relative,
            "task_correctness_summary_used": scorecard.task_correctness_summary_used,
            "no_runtime_execution": scorecard.no_runtime_execution,
        }
    )
    return 0 if scorecard.status == "ok" else 2


def _invalid_payload(error: str) -> dict[str, object]:
    return {
        "status": "invalid_input",
        "scorecard_id": None,
        "model_count": 0,
        "model_pair_count": 0,
        "warnings_count": 0,
        "scorecard_path": None,
        "markdown_preview_path": None,
        "task_correctness_summary_used": False,
        "no_runtime_execution": True,
        "error": error,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
