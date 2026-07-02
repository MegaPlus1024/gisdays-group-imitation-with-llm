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
        description="Build cross-scenario behavioral comparison from existing analysis artifacts."
    )
    parser.add_argument(
        "--scenario-analysis",
        action="append",
        required=True,
        help="Scenario input formatted as scenario_id=analysis_path=repeated_trials_path.",
    )
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--label", default="cross_scenario_behavioral_analysis_v1")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    return parser


def _project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _parse_scenario_input(value: str):
    from src.agent.cross_scenario_analysis import ScenarioAnalysisInput

    parts = value.split("=", 2)
    if len(parts) != 3:
        raise ValueError(
            "--scenario-analysis must be formatted as scenario_id=analysis_path=repeated_trials_path"
        )
    scenario_id, analysis_path, repeated_path = parts
    return ScenarioAnalysisInput(
        scenario_id=scenario_id,
        analysis_path=str(_project_path(analysis_path)),
        repeated_trials_path=str(_project_path(repeated_path)),
    )


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from src.agent.cross_scenario_analysis import (
        build_cross_scenario_analysis,
        write_cross_scenario_analysis,
    )

    try:
        inputs = [_parse_scenario_input(item) for item in args.scenario_analysis]
        result = build_cross_scenario_analysis(inputs, analysis_id=args.label)
        out = write_cross_scenario_analysis(result, _project_path(args.out_dir), force=args.force)
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: cross-scenario analysis failed: {exc}", file=sys.stderr)
        return 1

    if args.json_only:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0

    print(f"analysis_id: {result.analysis_id}")
    print(f"out_dir: {out}")
    print(f"recommendation_readiness_status: {result.recommendation_readiness.get('recommendation_readiness_status')}")
    print("")
    print("model_id,scenario_count,total_trials,mean_initial_validity,mean_final_validity,mean_execution_success,mean_normal_activity,mean_latency_ms,scenario_sensitivity")
    for model_id, aggregate in result.model_aggregates.items():
        print(
            f"{model_id},{aggregate.scenario_count},{aggregate.total_trials},"
            f"{aggregate.mean_initial_validation_accept_rate_across_scenarios},"
            f"{aggregate.mean_final_validation_accept_rate_across_scenarios},"
            f"{aggregate.mean_execution_success_rate_across_scenarios},"
            f"{aggregate.mean_normal_activity_score_across_scenarios},"
            f"{aggregate.mean_avg_selection_latency_ms_across_scenarios},"
            f"{aggregate.scenario_sensitivity}"
        )
    print("")
    print("metric_winners:")
    for metric in result.metric_winners:
        print(f"- {metric.metric}: {metric.winner}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
