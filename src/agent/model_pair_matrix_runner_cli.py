from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .model_pair_matrix_runner import (
    DEFAULT_MODEL_PAIR_MATRIX_EXECUTION_MODE,
    MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME,
    DryRunModelPairTrialExecutor,
    ModelPairMatrixPlanError,
    run_model_pair_matrix,
    write_model_pair_matrix_run_summary,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an offline model-pair matrix scaffold over a model comparison plan.",
    )
    parser.add_argument("--plan", default=None, help="Required model_comparison_plan.json.")
    parser.add_argument("--output-dir", default=None, help="Required output directory.")
    parser.add_argument("--run-id", default=None, help="Optional run id.")
    parser.add_argument("--execution-mode", default=DEFAULT_MODEL_PAIR_MATRIX_EXECUTION_MODE)
    parser.add_argument("--write-trial-results-jsonl", action="store_true", default=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        if not args.plan:
            _print_json(_invalid_payload("plan_required"))
            return 2
        if not args.output_dir:
            _print_json(_invalid_payload("output_dir_required"))
            return 2
        if args.execution_mode != DEFAULT_MODEL_PAIR_MATRIX_EXECUTION_MODE:
            _print_json(_invalid_payload("unsupported_execution_mode"))
            return 2

        summary = run_model_pair_matrix(
            args.plan,
            DryRunModelPairTrialExecutor(),
            run_id=args.run_id,
            execution_mode=args.execution_mode,
        )
        summary_path = write_model_pair_matrix_run_summary(
            summary,
            args.output_dir,
            write_trial_results_jsonl=args.write_trial_results_jsonl,
        )
    except ModelPairMatrixPlanError as exc:
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
            "status": "ok" if summary.failed_count == 0 else "failed",
            "run_id": summary.run_id,
            "execution_mode": summary.execution_mode,
            "trial_count": summary.trial_count,
            "dry_run_count": summary.dry_run_count,
            "failed_count": summary.failed_count,
            "summary_path": _summary_path(summary_path, Path(args.output_dir)),
        }
    )
    return 0 if summary.failed_count == 0 else 2


def _summary_path(path: Path, output_dir: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(output_dir.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return path.name if path.name == MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME else "<absolute_path>"


def _invalid_payload(error: str, *, status: str = "invalid_input") -> dict[str, object]:
    return {
        "status": status,
        "run_id": None,
        "execution_mode": DEFAULT_MODEL_PAIR_MATRIX_EXECUTION_MODE,
        "trial_count": 0,
        "dry_run_count": 0,
        "failed_count": 0,
        "summary_path": None,
        "error": error,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
