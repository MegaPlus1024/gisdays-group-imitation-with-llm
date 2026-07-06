from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .normality_evaluation_runner import NORMALITY_BATCH_SUMMARY_FILENAME
from .prepared_normality_input_processor import (
    PreparedNormalityInputLoadError,
    load_prepared_normality_inputs,
    load_static_normality_result,
    process_prepared_normality_inputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Process prepared normality_judge_inputs.jsonl artifacts without live LLM calls.",
        exit_on_error=False,
    )
    parser.add_argument("--input", action="append", default=[], help="Prepared normality input JSON/JSONL. Repeatable.")
    parser.add_argument("--output-dir", required=True, help="Directory for normality_judge_batch_summary.json.")
    parser.add_argument(
        "--provider",
        choices=("deterministic", "disabled", "static"),
        default="deterministic",
        help="Safe offline provider mode. Live LLM providers are intentionally unavailable.",
    )
    parser.add_argument("--static-result", default=None, help="Optional NormalityJudgeResult JSON for static mode.")
    parser.add_argument("--summary-id", default=None, help="Optional batch summary id.")
    parser.add_argument("--tag", action="append", default=[], help="Optional batch tag. Repeatable.")
    parser.add_argument("--max-events", type=int, default=100)
    parser.add_argument("--max-text-chars", type=int, default=500)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        if not args.input:
            _print_json(_invalid_payload("input_required"))
            return 2
        inputs = []
        for input_path in args.input:
            inputs.extend(load_prepared_normality_inputs(input_path))
        static_result = load_static_normality_result(args.static_result) if args.static_result else None
        result = process_prepared_normality_inputs(
            inputs,
            provider_mode=args.provider,
            output_dir=args.output_dir,
            summary_id=args.summary_id,
            tags=args.tag,
            static_result=static_result,
            max_events=args.max_events,
            max_text_chars=args.max_text_chars,
        )
    except argparse.ArgumentError as exc:
        _print_json(_invalid_payload(_argument_error_code(exc)))
        return 2
    except PreparedNormalityInputLoadError as exc:
        _print_json(_invalid_payload(str(exc)))
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json(_invalid_payload(exc.__class__.__name__))
        return 2

    _print_json(_stdout_payload(result))
    return 0 if result.status in {"ok", "judge_disabled"} else 2


def _stdout_payload(result: object) -> dict[str, object]:
    failed_count = int(getattr(result, "failed_count", 0) or 0)
    return {
        "status": getattr(result, "status", "invalid_input"),
        "summary_id": getattr(result, "batch_id", None),
        "input_count": getattr(result, "input_count", 0),
        "evaluated_count": getattr(result, "evaluated_count", 0),
        "invalid_count": failed_count,
        "skipped_count": failed_count,
        "summary_path": getattr(result, "batch_summary_path_relative", None) or NORMALITY_BATCH_SUMMARY_FILENAME,
        "no_runtime_execution": True,
    }


def _invalid_payload(error: str) -> dict[str, object]:
    return {
        "status": "invalid_input",
        "summary_id": None,
        "input_count": 0,
        "evaluated_count": 0,
        "invalid_count": 0,
        "skipped_count": 0,
        "summary_path": None,
        "no_runtime_execution": True,
        "error": error,
    }


def _argument_error_code(exc: argparse.ArgumentError) -> str:
    argument_name = getattr(exc, "argument_name", "")
    if argument_name == "--provider":
        return "unsupported_provider"
    return "argument_error"


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
