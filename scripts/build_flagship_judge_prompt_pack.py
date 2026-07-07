from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.model_pair_flagship_judge_inputs import (
    FLAGSHIP_JUDGE_INPUTS_JSONL_FILENAME,
    FLAGSHIP_JUDGE_PROMPT_PACK_JSONL_FILENAME,
    FLAGSHIP_JUDGE_README_FILENAME,
    FLAGSHIP_JUDGE_SCHEMA_JSON_FILENAME,
    FlagshipJudgeExchangeError,
    build_flagship_judge_input_records,
    build_flagship_judge_prompt_rows,
    write_flagship_judge_prompt_pack,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Build an offline flagship judge prompt pack.")
    parser.add_argument("--run-output-dir", action="append", default=[], help="Mini-matrix repeat output directory.")
    parser.add_argument("--aggregate-summary", help="Path to mini_matrix_aggregate_summary.json.")
    parser.add_argument("--summary-id")
    parser.add_argument("--output-dir", required=True)
    args = parser.parse_args(argv)

    try:
        inputs = build_flagship_judge_input_records(
            args.run_output_dir,
            aggregate_summary_path=args.aggregate_summary,
            summary_id=args.summary_id,
        )
        prompts = build_flagship_judge_prompt_rows(inputs, summary_id=args.summary_id)
        paths = write_flagship_judge_prompt_pack(inputs, prompts, args.output_dir)
    except FlagshipJudgeExchangeError as exc:
        _emit({"status": "invalid_input", "error": str(exc), "no_runtime_execution": True})
        return 2
    except OSError:
        _emit({"status": "write_failed", "error": "flagship_judge_prompt_pack_write_failed", "no_runtime_execution": True})
        return 1

    _emit(
        {
            "status": "ok",
            "summary_id": args.summary_id or (inputs[0].get("summary_id") if inputs else None),
            "input_count": len(inputs),
            "prompt_count": len(prompts),
            "inputs_path": _display_path(paths["inputs"]),
            "prompt_pack_path": _display_path(paths["prompts"]),
            "schema_path": _display_path(paths["schema"]),
            "readme_path": _display_path(paths["readme"]),
            "filenames": [
                FLAGSHIP_JUDGE_INPUTS_JSONL_FILENAME,
                FLAGSHIP_JUDGE_PROMPT_PACK_JSONL_FILENAME,
                FLAGSHIP_JUDGE_SCHEMA_JSON_FILENAME,
                FLAGSHIP_JUDGE_README_FILENAME,
            ],
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
