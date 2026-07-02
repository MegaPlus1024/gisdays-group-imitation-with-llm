from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Compare two existing model behavior run artifacts without running models."
    )
    parser.add_argument("--first-run", required=True, help="First model artifact folder.")
    parser.add_argument("--second-run", required=True, help="Second model artifact folder.")
    parser.add_argument("--out-dir", required=True, help="Comparison output directory.")
    parser.add_argument("--label", default="model_behavior_comparison", help="Comparison id/label.")
    parser.add_argument("--force", action="store_true", help="Overwrite existing comparison output directory.")
    parser.add_argument(
        "--json-only",
        action="store_true",
        help="Print comparison JSON to stdout. Artifacts are still written to --out-dir.",
    )
    return parser


def _project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from src.agent.model_behavior_comparison import (
        compare_model_runs,
        write_model_comparison,
    )

    comparison = compare_model_runs(
        _project_path(args.first_run),
        _project_path(args.second_run),
        comparison_id=args.label,
    )
    try:
        out_dir = write_model_comparison(comparison, _project_path(args.out_dir), force=args.force)
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    if args.json_only:
        print(json.dumps(comparison.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0

    first = comparison.per_model["first"]
    second = comparison.per_model["second"]
    print(f"comparison_id: {comparison.comparison_id}")
    print(f"status: {comparison.status}")
    print(f"protocol_compatible: {comparison.protocol_compatible}")
    print(f"out_dir: {out_dir}")
    print("")
    print("metric,first,second")
    for key in [
        "model_id",
        "step_count",
        "initial_validation_accept_rate",
        "final_validation_accept_rate",
        "execution_success_rate",
        "normal_activity_score",
        "diversity_score",
        "repetition_score",
        "history_usage_score",
        "average_selection_latency_ms",
        "stop_reason",
    ]:
        print(f"{key},{first.get(key)},{second.get(key)}")
    print("")
    print("metric_winners:")
    for metric in comparison.metric_winners:
        print(f"- {metric.name}: {metric.winner}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
