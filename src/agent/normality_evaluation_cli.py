from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from src.agent.normality_comparison import (
    compare_normality_batch_summaries,
    write_normality_comparison_summary,
)
from src.agent.normality_evaluation_runner import (
    NORMALITY_BATCH_SUMMARY_FILENAME,
    NORMALITY_EVALUATION_SUMMARY_FILENAME,
    NormalityEvaluationRunConfig,
    run_batch_normality_evaluation,
    run_batch_normality_evaluation_from_manifest,
    run_normality_evaluation_from_saved_llm_response,
    run_normality_evaluation_from_file,
    write_normality_evaluation_summary,
    write_normality_judge_prompt_preview_from_file,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run offline normality evaluation for a local JSON/JSONL artifact.",
    )
    parser.add_argument(
        "--input",
        action="append",
        help="Path to a JSON or JSONL event file. Repeat for offline batch evaluation.",
    )
    parser.add_argument(
        "--input-manifest",
        default=None,
        help="Path to an explicit normality batch manifest JSON file.",
    )
    parser.add_argument(
        "--compare-batch-summary",
        action="append",
        default=[],
        help="Path to a normality_judge_batch_summary.json file. Repeat for comparison.",
    )
    parser.add_argument(
        "--comparison-output-dir",
        default=None,
        help="Directory for normality comparison outputs. Defaults to --output-dir.",
    )
    parser.add_argument(
        "--write-comparison-markdown",
        action="store_true",
        help="Also write normality_comparison_preview.md for quick offline inspection.",
    )
    parser.add_argument(
        "--output-dir",
        required=True,
        help="Directory where normality_judge_summary.json will be written.",
    )
    parser.add_argument("--scenario-id", default=None, help="Optional scenario id override.")
    parser.add_argument("--task-summary", default=None, help="Optional task summary override.")
    parser.add_argument(
        "--judge-provider",
        default="deterministic",
        choices=["deterministic", "fake", "disabled", "llm"],
        help="Offline judge provider. The llm provider is a no-call placeholder.",
    )
    parser.add_argument("--max-events", type=int, default=100)
    parser.add_argument("--max-text-chars", type=int, default=500)
    parser.add_argument(
        "--include-raw-outputs",
        action="store_true",
        help="Request raw-output inclusion where supported; summaries remain bounded and redacted.",
    )
    parser.add_argument(
        "--no-redact-paths",
        action="store_true",
        help="Disable path redaction in summaries.",
    )
    parser.add_argument(
        "--prompt-preview",
        action="store_true",
        help="Deprecated alias for --write-prompt-preview.",
    )
    parser.add_argument(
        "--write-prompt-preview",
        action="store_true",
        help="Write normality_judge_prompt_preview.txt to the output directory.",
    )
    parser.add_argument(
        "--raw-judge-response",
        default=None,
        help="Path to a saved raw LLM judge response to parse offline.",
    )
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        input_paths = list(args.input or [])
        compare_paths = list(args.compare_batch_summary or [])
        if compare_paths:
            if input_paths or args.input_manifest or args.raw_judge_response:
                _print_json(_invalid_payload("comparison_mode_incompatible_args"))
                return 2
            if args.write_prompt_preview or args.prompt_preview:
                _print_json(_invalid_payload("comparison_mode_prompt_preview_unsupported"))
                return 2
            comparison = compare_normality_batch_summaries(
                compare_paths,
                project_root=Path.cwd(),
            )
            write_normality_comparison_summary(
                comparison,
                args.comparison_output_dir or args.output_dir,
                write_markdown=args.write_comparison_markdown,
            )
            _print_json(_comparison_stdout_payload(comparison))
            return _comparison_exit_code(comparison.status)
        if args.input_manifest and input_paths:
            _print_json(_invalid_payload("input_manifest_cannot_combine_with_input"))
            return 2
        if not args.input_manifest and not input_paths:
            _print_json(_invalid_payload("input_or_manifest_required"))
            return 2
        if args.input_manifest and args.raw_judge_response:
            _print_json(_invalid_payload("raw_judge_response_manifest_unsupported"))
            return 2
        if args.input_manifest and (args.write_prompt_preview or args.prompt_preview):
            _print_json(_invalid_payload("prompt_preview_manifest_unsupported"))
            return 2
        if len(input_paths) > 1 and args.raw_judge_response:
            _print_json(_invalid_payload("raw_judge_response_batch_unsupported"))
            return 2
        if len(input_paths) > 1 and (args.write_prompt_preview or args.prompt_preview):
            _print_json(_invalid_payload("prompt_preview_batch_unsupported"))
            return 2
        judge_mode = args.judge_provider if args.judge_provider in {"deterministic", "fake"} else "deterministic"
        config = NormalityEvaluationRunConfig(
            project_root=Path.cwd(),
            input_path=input_paths[0] if input_paths else None,
            output_dir=args.output_dir,
            scenario_id=args.scenario_id,
            task_summary=args.task_summary,
            judge_mode=judge_mode,
            judge_provider=args.judge_provider,
            max_events=args.max_events,
            max_text_chars=args.max_text_chars,
            include_raw_outputs=args.include_raw_outputs,
            redact_paths=not args.no_redact_paths,
        )
        if args.input_manifest:
            batch_result = run_batch_normality_evaluation_from_manifest(
                config,
                args.input_manifest,
            )
            _print_json(_batch_stdout_payload(batch_result))
            return _batch_exit_code(batch_result.status)
        if len(input_paths) > 1:
            batch_result = run_batch_normality_evaluation(config, input_paths)
            _print_json(_batch_stdout_payload(batch_result))
            return _batch_exit_code(batch_result.status)
        if args.raw_judge_response and args.judge_provider == "llm":
            result = run_normality_evaluation_from_saved_llm_response(
                config,
                args.raw_judge_response,
            )
        else:
            result = run_normality_evaluation_from_file(config)
        if args.write_prompt_preview or args.prompt_preview:
            prompt_path, warnings = write_normality_judge_prompt_preview_from_file(config)
            if prompt_path is not None:
                result.prompt_preview_path_relative = _display_path(prompt_path, config.output_dir)
                if config.output_dir and config.write_summary and result.event_count:
                    write_normality_evaluation_summary(result, config.resolve_project_path(config.output_dir))
            elif warnings:
                result.warnings = sorted(set([*getattr(result, "warnings", []), *warnings]))
    except (OSError, ValueError) as exc:
        _print_json(
            {
                "status": "invalid_input",
                "summary_path": None,
                "label": None,
                "overall_score": None,
                "event_count": 0,
                "judge_provider": None,
                "model_called": False,
                "prompt_preview_path": None,
                "error": exc.__class__.__name__,
            }
        )
        return 2

    _print_json(_stdout_payload(result))
    return _exit_code(result.status)


def _invalid_payload(error: str) -> dict[str, object]:
    return {
        "status": "invalid_input",
        "summary_path": None,
        "label": None,
        "overall_score": None,
        "event_count": 0,
        "judge_provider": None,
        "model_called": False,
        "prompt_preview_path": None,
        "error": error,
    }


def _stdout_payload(result: object) -> dict[str, object]:
    status = getattr(result, "status", "invalid_input")
    summary_path = getattr(result, "summary_path_relative", None)
    if summary_path is None and status in {"ok", "judge_disabled"}:
        summary_path = NORMALITY_EVALUATION_SUMMARY_FILENAME
    return {
        "status": status,
        "summary_path": summary_path,
        "label": getattr(result, "label", None),
        "overall_score": getattr(result, "overall_score", None),
        "event_count": getattr(result, "event_count", 0),
        "judge_provider": getattr(result, "judge_provider", None),
        "model_called": getattr(result, "model_called", False),
        "prompt_preview_path": getattr(result, "prompt_preview_path_relative", None),
    }


def _batch_stdout_payload(result: object) -> dict[str, object]:
    aggregation = getattr(result, "aggregation", {}) or {}
    status = getattr(result, "status", "invalid_input")
    batch_path = getattr(result, "batch_summary_path_relative", None)
    if batch_path is None and status != "write_failed":
        batch_path = NORMALITY_BATCH_SUMMARY_FILENAME
    return {
        "status": status,
        "batch_id": getattr(result, "batch_id", None),
        "input_count": getattr(result, "input_count", 0),
        "evaluated_count": getattr(result, "evaluated_count", 0),
        "failed_count": getattr(result, "failed_count", 0),
        "mean_overall_score": aggregation.get("mean_overall_score"),
        "label_counts": aggregation.get("label_counts", {}),
        "batch_summary_path": batch_path,
        "judge_provider": getattr(result, "judge_provider", None),
    }


def _comparison_stdout_payload(result: object) -> dict[str, object]:
    leaderboard = getattr(result, "leaderboard", []) or []
    top_model_pair = leaderboard[0].get("pair_label") if leaderboard else None
    return {
        "status": getattr(result, "status", "invalid_input"),
        "input_summary_count": getattr(result, "input_summary_count", 0),
        "total_entries": getattr(result, "total_entries", 0),
        "evaluated_entries": getattr(result, "evaluated_entries", 0),
        "failed_entries": getattr(result, "failed_entries", 0),
        "top_model_pair": top_model_pair,
        "comparison_summary_path": getattr(result, "comparison_summary_path_relative", None),
    }


def _exit_code(status: str) -> int:
    if status in {"ok", "judge_disabled"}:
        return 0
    return 2


def _batch_exit_code(status: str) -> int:
    if status in {"ok", "judge_disabled"}:
        return 0
    return 2


def _comparison_exit_code(status: str) -> int:
    if status == "ok":
        return 0
    return 2


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


def _display_path(path: Path, output_dir: str | None) -> str:
    if output_dir:
        try:
            return path.resolve(strict=False).relative_to(Path(output_dir).resolve(strict=False)).as_posix()
        except (OSError, ValueError):
            return path.name
    return path.name


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
