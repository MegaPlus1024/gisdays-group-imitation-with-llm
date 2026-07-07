from __future__ import annotations

import argparse
import glob
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.model_pair_mini_matrix_aggregation import (
    MiniMatrixAggregationError,
    aggregate_mini_matrix_results,
    write_mini_matrix_aggregate_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Aggregate completed controlled mini-matrix repeat outputs offline.")
    parser.add_argument("--run-output-dir", action="append", default=[], help="Single repeat output directory.")
    parser.add_argument("--run-output-glob", action="append", default=[], help="Glob for repeat output directories.")
    parser.add_argument("--output-dir", required=True, help="Directory for mini_matrix_aggregate_summary.json.")
    parser.add_argument("--summary-id")
    args = parser.parse_args(argv)

    run_dirs = _run_dirs(args.run_output_dir, args.run_output_glob)
    try:
        summary = aggregate_mini_matrix_results(run_dirs, summary_id=args.summary_id)
        summary_path = write_mini_matrix_aggregate_summary(summary, args.output_dir)
    except MiniMatrixAggregationError as exc:
        _emit({"status": "invalid_input", "error": str(exc), "no_runtime_execution": True})
        return 2
    except OSError:
        _emit({"status": "write_failed", "error": "mini_matrix_aggregate_write_failed", "no_runtime_execution": True})
        return 1

    _emit(
        {
            "status": "ok",
            "summary_path": _display_path(summary_path),
            "repeat_count": summary.get("repeat_count", 0),
            "succeeded_count": summary.get("succeeded_count", 0),
            "failed_count": summary.get("failed_count", 0),
            "task_success_count": summary.get("task_success_count", 0),
            "execution_success_count": summary.get("execution_success_count", 0),
            "office_artifact_count": summary.get("office_artifact_count", 0),
            "correctness_score_count": summary.get("correctness_score_count", 0),
            "mean_correctness_score": summary.get("mean_correctness_score"),
            "execution_correctness_pass_count": summary.get("execution_correctness_pass_count", 0),
            "artifact_correctness_pass_count": summary.get("artifact_correctness_pass_count", 0),
            "warnings": summary.get("warnings", []),
            "no_runtime_execution": True,
        }
    )
    return 0


def _run_dirs(explicit: list[str], patterns: list[str]) -> list[str]:
    rows = [item for item in explicit if item]
    for pattern in patterns:
        rows.extend(sorted(glob.glob(pattern)))
    return list(dict.fromkeys(rows))


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _display_path(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(Path.cwd().resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return path.name


if __name__ == "__main__":
    raise SystemExit(main())
