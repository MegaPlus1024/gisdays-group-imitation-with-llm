from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare orchestrator/executor pair matrices across scenarios.")
    parser.add_argument("--simple-matrix-root", required=True)
    parser.add_argument("--heavy-matrix-root", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--label", default="cross_scenario_pair_matrix_v1")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from src.agent.orchestrator_executor_cross_scenario_analysis import compare_pair_matrices

    result = compare_pair_matrices(
        simple_matrix_root=_project_path(args.simple_matrix_root),
        heavy_matrix_root=_project_path(args.heavy_matrix_root),
        out_dir=_project_path(args.out_dir),
        label=args.label,
        force=args.force,
    )
    if args.json_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
    else:
        print(f"comparison_id: {result['comparison_id']}")
        print(f"simple_scenario_best_pair: {result.get('simple_scenario_best_pair')}")
        print(f"heavy_scenario_best_pair: {result.get('heavy_scenario_best_pair')}")
        print(f"best_observed_pair_across_tested_scenarios: {result.get('best_observed_pair_across_tested_scenarios')}")
        print(f"out_dir: {_project_path(args.out_dir)}")
    return 0


def _project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


if __name__ == "__main__":
    raise SystemExit(main())
