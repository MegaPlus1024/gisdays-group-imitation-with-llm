from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .model_catalog import load_model_catalog
from .model_comparison_plan import (
    MODEL_COMPARISON_PLAN_FILENAME,
    ModelComparisonPlanConfig,
    build_model_comparison_plan,
    write_model_comparison_plan,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Build an offline model comparison planning artifact from a model catalog.",
    )
    parser.add_argument("--model-catalog", default=None, help="Path to model_catalog.example.json.")
    parser.add_argument(
        "--scenario",
        action="append",
        default=[],
        help="Explicit relative scenario config path. Repeat to include multiple scenarios.",
    )
    parser.add_argument("--output-dir", default=None, help="Directory for model_comparison_plan.json.")
    parser.add_argument("--repetitions", type=int, default=1, help="Trial repetitions per scenario/pair.")
    parser.add_argument("--include-self-pairs", dest="include_self_pairs", action="store_true", default=True)
    parser.add_argument("--exclude-self-pairs", dest="include_self_pairs", action="store_false")
    parser.add_argument("--include-role-mismatch-pairs", action="store_true", default=False)
    parser.add_argument("--tag", action="append", default=[], help="Plan tag. Repeatable.")
    parser.add_argument("--plan-id", default="model_comparison_plan", help="Optional plan id.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        if not args.model_catalog:
            _print_json(_invalid_payload("model_catalog_required"))
            return 2
        if not args.scenario:
            _print_json(_invalid_payload("scenario_required"))
            return 2
        if not args.output_dir:
            _print_json(_invalid_payload("output_dir_required"))
            return 2
        if args.repetitions < 1:
            _print_json(_invalid_payload("repetitions_must_be_positive"))
            return 2

        project_root = Path.cwd()
        catalog = load_model_catalog(project_root / args.model_catalog if not Path(args.model_catalog).is_absolute() else args.model_catalog)
        config = ModelComparisonPlanConfig(
            plan_id=args.plan_id,
            catalog_path=_display_path(args.model_catalog, project_root),
            repetitions_per_pair=args.repetitions,
            include_self_pairs=args.include_self_pairs,
            include_role_mismatch_pairs=args.include_role_mismatch_pairs,
            tags=args.tag,
        )
        plan = build_model_comparison_plan(
            catalog,
            args.scenario,
            config,
            project_root=project_root,
        )
        plan_path = write_model_comparison_plan(plan, args.output_dir)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json(_invalid_payload(exc.__class__.__name__))
        return 2

    _print_json(
        {
            "status": "ok",
            "plan_id": plan.plan_id,
            "model_count": plan.model_catalog_summary["model_count"],
            "candidate_pair_count": len(plan.candidate_pairs),
            "trial_count": len(plan.trials),
            "plan_path": plan_path.name if plan_path.name == MODEL_COMPARISON_PLAN_FILENAME else str(plan_path),
        }
    )
    return 0


def _display_path(path: str, project_root: Path) -> str:
    candidate = Path(path)
    if not candidate.is_absolute():
        return candidate.as_posix()
    try:
        return candidate.resolve(strict=False).relative_to(project_root.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return "<absolute_path>"


def _invalid_payload(error: str) -> dict[str, object]:
    return {
        "status": "invalid_input",
        "plan_id": None,
        "model_count": 0,
        "candidate_pair_count": 0,
        "trial_count": 0,
        "plan_path": None,
        "error": error,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))

