from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.model_pair_office_execution_artifacts import (
    OfficeExecutionArtifactSummaryError,
    load_trial_result,
    summarize_office_execution_artifacts,
    write_office_execution_artifact_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Summarize executed office document artifacts offline.")
    parser.add_argument("--trial-result", required=True, help="Path to model_pair_single_trial_result.json.")
    parser.add_argument("--output", required=True, help="Path to write office_execution_artifact_summary.json.")
    parser.add_argument("--project-root", default=".", help="Project root for resolving safe relative artifacts.")
    parser.add_argument("--max-text-chars", type=int, default=240, help="Maximum safe excerpt length per document.")
    args = parser.parse_args(argv)

    try:
        trial_result = load_trial_result(args.trial_result)
        summary = summarize_office_execution_artifacts(
            trial_result,
            project_root=args.project_root,
            max_text_chars=args.max_text_chars,
        )
        output_path = write_office_execution_artifact_summary(summary, args.output)
    except OfficeExecutionArtifactSummaryError as exc:
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
                "error": "office_execution_artifact_summary_write_failed",
                "no_runtime_execution": True,
            }
        )
        return 1

    _emit(
        {
            "status": "ok",
            "summary_path": _display_path(output_path),
            "artifact_count": summary.get("artifact_count", 0),
            "readable_count": summary.get("readable_count", 0),
            "missing_count": summary.get("missing_count", 0),
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
