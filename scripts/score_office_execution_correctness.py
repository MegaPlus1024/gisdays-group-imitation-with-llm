from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.model_pair_office_execution_correctness import (
    OfficeExecutionCorrectnessSummaryError,
    load_json_object,
    score_office_execution_correctness,
    write_office_execution_correctness_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Score office execution correctness from offline summaries.")
    parser.add_argument("--trial-result", required=True, help="Path to model_pair_single_trial_result.json.")
    parser.add_argument(
        "--office-artifact-summary",
        required=True,
        help="Path to office_execution_artifact_summary.json.",
    )
    parser.add_argument("--output", required=True, help="Path to write office_execution_correctness_summary.json.")
    args = parser.parse_args(argv)

    try:
        trial_result = load_json_object(args.trial_result, label="trial_result")
        office_summary = load_json_object(args.office_artifact_summary, label="office_artifact_summary")
        summary = score_office_execution_correctness(trial_result, office_summary)
        output_path = write_office_execution_correctness_summary(summary, args.output)
    except OfficeExecutionCorrectnessSummaryError as exc:
        _emit(
            {
                "status": "invalid_input",
                "error": str(exc),
                "no_runtime_execution": True,
            }
        )
        return 2
    except OSError:
        _emit(
            {
                "status": "write_failed",
                "error": "office_execution_correctness_summary_write_failed",
                "no_runtime_execution": True,
            }
        )
        return 1

    _emit(
        {
            "status": "ok",
            "summary_path": _display_path(output_path),
            "correctness_score": summary.get("correctness_score"),
            "execution_correctness_pass": summary.get("execution_correctness_pass"),
            "artifact_correctness_pass": summary.get("artifact_correctness_pass"),
            "warnings": summary.get("warnings", []),
            "no_runtime_execution": True,
        }
    )
    return 0


def _emit(payload: dict[str, Any]) -> None:
    print(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True))


def _display_path(path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(Path.cwd().resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return path.name


if __name__ == "__main__":
    raise SystemExit(main())
