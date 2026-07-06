from __future__ import annotations

import argparse
import json
import sys
from typing import Sequence

from .model_evaluation_compatibility_gate import (
    run_model_evaluation_compatibility_gate,
    write_model_evaluation_compatibility_report,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run an offline compatibility gate for model evaluation artifacts.",
    )
    parser.add_argument("--golden-fixture-dir", required=True, help="Golden fixture pack directory.")
    parser.add_argument("--workflow-output-dir", default=None, help="Optional workflow output directory to compare.")
    parser.add_argument("--output-dir", required=True, help="Compatibility report output directory.")
    parser.add_argument("--compatibility-id", default="model_evaluation_compatibility")
    parser.add_argument("--strict", action="store_true", default=False, help="Return nonzero on warnings.")
    parser.add_argument("--write-markdown-preview", action="store_true", default=False)
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        report = run_model_evaluation_compatibility_gate(
            golden_fixture_dir=args.golden_fixture_dir,
            workflow_output_dir=args.workflow_output_dir,
            compatibility_id=args.compatibility_id,
        )
        report_path, _ = write_model_evaluation_compatibility_report(
            report,
            args.output_dir,
            write_markdown_preview=args.write_markdown_preview,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json(_invalid_payload("model_evaluation_compatibility", exc.__class__.__name__))
        return 2

    payload = {
        "status": report.status,
        "compatibility_id": report.compatibility_id,
        "checked_artifact_count": report.checked_artifact_count,
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "report_path": report_path.name,
        "no_runtime_execution": report.no_runtime_execution,
    }
    _print_json(payload)
    if report.status == "incompatible":
        return 2
    if args.strict and report.warning_count:
        return 2
    return 0


def _invalid_payload(compatibility_id: str, error: str) -> dict[str, object]:
    return {
        "status": "invalid_input",
        "compatibility_id": compatibility_id,
        "checked_artifact_count": 0,
        "error_count": 1,
        "warning_count": 0,
        "report_path": None,
        "no_runtime_execution": True,
        "error": error,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
