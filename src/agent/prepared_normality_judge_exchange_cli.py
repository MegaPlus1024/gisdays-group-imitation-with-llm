from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .normality_evaluation_runner import NORMALITY_BATCH_SUMMARY_FILENAME
from .prepared_normality_judge_exchange import (
    NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME,
    NORMALITY_JUDGE_PROMPT_PACK_SUMMARY_FILENAME,
    PreparedNormalityJudgeExchangeError,
    build_normality_batch_summary_from_raw_responses,
    build_prepared_normality_judge_prompt_pack,
    load_exchange_prepared_normality_inputs,
    load_normality_judge_raw_responses,
    load_prepared_normality_judge_prompt_pack,
    write_prepared_normality_judge_prompt_pack,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Export and import prepared normality judge exchange artifacts without live LLM calls.",
        exit_on_error=False,
    )
    subparsers = parser.add_subparsers(dest="command")

    export_parser = subparsers.add_parser("export-prompts", exit_on_error=False)
    export_parser.add_argument("--input", action="append", default=[], help="Prepared normality input JSON/JSONL. Repeatable.")
    export_parser.add_argument("--output-dir", required=True)
    export_parser.add_argument("--pack-id", default=None)
    export_parser.add_argument("--tag", action="append", default=[])

    import_parser = subparsers.add_parser("import-responses", exit_on_error=False)
    import_parser.add_argument("--prompt-pack", required=True)
    import_parser.add_argument("--raw-responses", required=True)
    import_parser.add_argument("--output-dir", required=True)
    import_parser.add_argument("--summary-id", default=None)
    import_parser.add_argument("--tag", action="append", default=[])

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        if args.command == "export-prompts":
            return _export_prompts(args)
        if args.command == "import-responses":
            return _import_responses(args)
        _print_json(_invalid_payload("command_required"))
        return 2
    except argparse.ArgumentError:
        _print_json(_invalid_payload("argument_error"))
        return 2
    except PreparedNormalityJudgeExchangeError as exc:
        _print_json(_invalid_payload(str(exc)))
        return 2
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json(_invalid_payload(exc.__class__.__name__))
        return 2


def _export_prompts(args: argparse.Namespace) -> int:
    prepared_inputs = load_exchange_prepared_normality_inputs(args.input)
    prompt_pack = build_prepared_normality_judge_prompt_pack(
        prepared_inputs,
        pack_id=args.pack_id,
        tags=args.tag,
    )
    write_prepared_normality_judge_prompt_pack(prompt_pack, args.output_dir)
    _print_json(
        {
            "status": "ok",
            "pack_id": prompt_pack.get("pack_id"),
            "input_count": prompt_pack.get("input_count", 0),
            "prompt_count": prompt_pack.get("prompt_count", 0),
            "skipped_count": prompt_pack.get("skipped_count", 0),
            "prompt_pack_path": NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME,
            "summary_path": NORMALITY_JUDGE_PROMPT_PACK_SUMMARY_FILENAME,
            "no_runtime_execution": True,
        }
    )
    return 0


def _import_responses(args: argparse.Namespace) -> int:
    prompt_pack = load_prepared_normality_judge_prompt_pack(args.prompt_pack)
    raw_responses = load_normality_judge_raw_responses(args.raw_responses)
    result = build_normality_batch_summary_from_raw_responses(
        prompt_pack,
        raw_responses,
        summary_id=args.summary_id,
        tags=args.tag,
        output_dir=args.output_dir,
    )
    missing_response_count = sum(
        1
        for entry in result.entries
        if "judge_response_missing" in entry.warnings
    )
    invalid_count = result.failed_count
    _print_json(
        {
            "status": result.status,
            "summary_id": result.batch_id,
            "response_count": len(raw_responses),
            "evaluated_count": result.evaluated_count,
            "invalid_count": invalid_count,
            "missing_response_count": missing_response_count,
            "summary_path": result.batch_summary_path_relative or NORMALITY_BATCH_SUMMARY_FILENAME,
            "no_runtime_execution": True,
        }
    )
    return 0 if result.status == "ok" else 2


def _invalid_payload(error: str) -> dict[str, object]:
    return {
        "status": "invalid_input",
        "pack_id": None,
        "summary_id": None,
        "input_count": 0,
        "prompt_count": 0,
        "skipped_count": 0,
        "response_count": 0,
        "evaluated_count": 0,
        "invalid_count": 0,
        "missing_response_count": 0,
        "prompt_pack_path": None,
        "summary_path": None,
        "no_runtime_execution": True,
        "error": error,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
