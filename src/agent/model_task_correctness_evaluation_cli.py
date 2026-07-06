from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .model_task_correctness_evaluation import (
    TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME,
    DisabledTaskCorrectnessEvaluator,
    RuleBasedTaskCorrectnessEvaluator,
    StaticTaskCorrectnessEvaluator,
    TaskCorrectnessEvaluationInput,
    TaskCorrectnessInputLoadError,
    build_correctness_inputs_from_matrix_run_summary,
    evaluate_task_correctness_batch,
    load_task_correctness_inputs_from_file,
    write_task_correctness_batch_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Evaluate offline task correctness for model-pair trial outputs.",
    )
    parser.add_argument("--input", action="append", default=[], help="JSON/JSONL correctness input file. Repeatable.")
    parser.add_argument("--matrix-run-summary", default=None, help="Optional model_pair_matrix_run_summary.json.")
    parser.add_argument("--output-dir", default=None, help="Required output directory.")
    parser.add_argument("--summary-id", default=None, help="Optional summary id.")
    parser.add_argument("--evaluator", choices=("rule_based", "static", "disabled"), default="rule_based")
    parser.add_argument("--static-result", default=None, help="Optional JSON mapping for static evaluator.")
    parser.add_argument("--tag", action="append", default=[], help="Optional summary tag. Repeatable.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        if not args.output_dir:
            _print_json(_invalid_payload("output_dir_required"))
            return 2
        if not args.input and not args.matrix_run_summary:
            _print_json(_invalid_payload("input_required"))
            return 2

        inputs = _load_inputs(args.input, args.matrix_run_summary)
        evaluator = _build_evaluator(args.evaluator, args.static_result)
        summary = evaluate_task_correctness_batch(
            inputs,
            evaluator,
            summary_id=args.summary_id,
            tags=args.tag,
        )
        summary_path = write_task_correctness_batch_summary(summary, args.output_dir)
    except TaskCorrectnessInputLoadError as exc:
        _print_json(_invalid_payload(str(exc)))
        return 2
    except OSError:
        _print_json(_invalid_payload("write_failed", status="write_failed"))
        return 2
    except (ValueError, json.JSONDecodeError) as exc:
        _print_json(_invalid_payload(exc.__class__.__name__))
        return 2

    _print_json(
        {
            "status": "ok" if summary.invalid_count == 0 else "partial",
            "summary_id": summary.summary_id,
            "input_count": summary.input_count,
            "evaluated_count": summary.evaluated_count,
            "passed_count": summary.passed_count,
            "failed_count": summary.failed_count,
            "partial_count": summary.partial_count,
            "skipped_count": summary.skipped_count,
            "mean_correctness_score": summary.mean_correctness_score,
            "summary_path": _summary_path(summary_path, Path(args.output_dir)),
        }
    )
    return 0


def _load_inputs(input_paths: list[str], matrix_run_summary: str | None) -> list[TaskCorrectnessEvaluationInput]:
    inputs: list[TaskCorrectnessEvaluationInput] = []
    for path in input_paths:
        inputs.extend(load_task_correctness_inputs_from_file(path))
    if matrix_run_summary:
        inputs.extend(build_correctness_inputs_from_matrix_run_summary(matrix_run_summary))
    if not inputs:
        raise TaskCorrectnessInputLoadError("input_rows_missing")
    return inputs


def _build_evaluator(
    evaluator_name: str,
    static_result_path: str | None,
) -> RuleBasedTaskCorrectnessEvaluator | StaticTaskCorrectnessEvaluator | DisabledTaskCorrectnessEvaluator:
    if evaluator_name == "disabled":
        return DisabledTaskCorrectnessEvaluator()
    if evaluator_name == "static":
        mapping = _load_static_mapping(static_result_path) if static_result_path else {}
        return StaticTaskCorrectnessEvaluator(mapping)
    return RuleBasedTaskCorrectnessEvaluator()


def _load_static_mapping(path: str | None) -> dict[str, object]:
    if path is None:
        return {}
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise TaskCorrectnessInputLoadError("static_result_file_missing") from exc
    except OSError as exc:
        raise TaskCorrectnessInputLoadError("static_result_file_unreadable") from exc
    except json.JSONDecodeError as exc:
        raise TaskCorrectnessInputLoadError("static_result_json_malformed") from exc
    if not isinstance(payload, dict):
        raise TaskCorrectnessInputLoadError("static_result_payload_not_object")
    if isinstance(payload.get("results_by_trial_or_pair"), dict):
        return dict(payload["results_by_trial_or_pair"])
    return payload


def _summary_path(path: Path, output_dir: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(output_dir.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return path.name if path.name == TASK_CORRECTNESS_BATCH_SUMMARY_FILENAME else "<absolute_path>"


def _invalid_payload(error: str, *, status: str = "invalid_input") -> dict[str, object]:
    return {
        "status": status,
        "summary_id": None,
        "input_count": 0,
        "evaluated_count": 0,
        "passed_count": 0,
        "failed_count": 0,
        "partial_count": 0,
        "skipped_count": 0,
        "mean_correctness_score": None,
        "summary_path": None,
        "error": error,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
