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
    FlagshipJudgeExchangeError,
    build_flagship_judge_summary_from_responses,
    load_flagship_judge_inputs_jsonl,
    load_flagship_judge_raw_responses_jsonl,
    write_flagship_judge_summary,
)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="Parse saved flagship judge responses offline.")
    parser.add_argument("--inputs", required=True, help="Path to flagship_judge_inputs.jsonl.")
    parser.add_argument("--raw-responses", required=True, help="Path to saved raw_responses.jsonl.")
    parser.add_argument("--output", required=True, help="Path to write flagship judge summary JSON.")
    parser.add_argument("--summary-id")
    parser.add_argument("--judge-model-id")
    parser.add_argument("--judge-provider", default="manual_or_external_api")
    args = parser.parse_args(argv)

    try:
        inputs = load_flagship_judge_inputs_jsonl(args.inputs)
        raw_responses = load_flagship_judge_raw_responses_jsonl(args.raw_responses)
        summary = build_flagship_judge_summary_from_responses(
            inputs,
            raw_responses,
            summary_id=args.summary_id,
            judge_model_id=args.judge_model_id,
            judge_provider=args.judge_provider,
        )
        output_path = write_flagship_judge_summary(summary, args.output)
    except FlagshipJudgeExchangeError as exc:
        _emit({"status": "invalid_input", "error": str(exc), "no_runtime_execution": True})
        return 2
    except OSError:
        _emit({"status": "write_failed", "error": "flagship_judge_summary_write_failed", "no_runtime_execution": True})
        return 1

    _emit(
        {
            "status": "ok" if summary.get("invalid_response_count") == 0 else "completed_with_invalid",
            "summary_id": summary.get("summary_id"),
            "response_count": summary.get("response_count", 0),
            "valid_response_count": summary.get("valid_response_count", 0),
            "invalid_response_count": summary.get("invalid_response_count", 0),
            "summary_path": _display_path(output_path),
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
