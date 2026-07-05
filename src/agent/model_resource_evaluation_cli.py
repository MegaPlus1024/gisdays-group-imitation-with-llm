from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .model_catalog import load_model_catalog
from .model_resource_evaluation import (
    MODEL_RESOURCE_SUMMARY_FILENAME,
    run_model_resource_evaluation,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Aggregate explicit offline model resource observation files.",
    )
    parser.add_argument("--input", action="append", default=[], help="Explicit JSON/JSONL observation file.")
    parser.add_argument("--output-dir", required=True, help="Directory for model_resource_summary.json.")
    parser.add_argument("--model-catalog", default=None, help="Optional model catalog metadata JSON.")
    parser.add_argument("--tag", action="append", default=[], help="Optional run tag. Repeatable.")
    parser.add_argument("--summary-id", default=None, help="Optional summary id.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        if not args.input:
            _print_json(_invalid_payload("input_required"))
            return 2
        model_catalog = None
        if args.model_catalog:
            catalog_path = Path(args.model_catalog)
            model_catalog = load_model_catalog(catalog_path if catalog_path.is_absolute() else Path.cwd() / catalog_path)
        summary = run_model_resource_evaluation(
            args.input,
            args.output_dir,
            model_catalog=model_catalog,
            summary_id=args.summary_id,
            tags=args.tag,
            project_root=Path.cwd(),
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json(_invalid_payload(exc.__class__.__name__))
        return 2

    payload = {
        "status": summary.status,
        "input_count": summary.input_count,
        "observation_count": summary.observation_count,
        "invalid_count": summary.invalid_count,
        "group_counts": {key: len(value) for key, value in summary.groups.items()},
        "summary_path": summary.summary_path_relative or MODEL_RESOURCE_SUMMARY_FILENAME,
    }
    _print_json(payload)
    return 0 if summary.status == "ok" else 2


def _invalid_payload(error: str) -> dict[str, object]:
    return {
        "status": "invalid_input",
        "input_count": 0,
        "observation_count": 0,
        "invalid_count": 0,
        "group_counts": {},
        "summary_path": None,
        "error": error,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

