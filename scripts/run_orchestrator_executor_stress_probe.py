from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run bounded stress smoke for orchestrator/executor candidate pairs.")
    parser.add_argument("--models-config", default="configs/evaluation_models.json")
    parser.add_argument("--runtime-profiles-config", default="configs/runtime_profiles.json")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--label", default="bounded_stress_candidate_pairs_v1")
    parser.add_argument("--pairs", required=True, help="Comma-separated orchestrator:executor pairs.")
    parser.add_argument("--profiles", required=True, help="Comma-separated runtime profile ids.")
    parser.add_argument("--concurrency-levels", required=True, help="Comma-separated levels, max 4.")
    parser.add_argument("--runs-per-level", type=int, default=2)
    parser.add_argument("--base-port", type=int, default=8081)
    parser.add_argument("--max-group-steps", type=int, default=2)
    parser.add_argument("--max-steps-per-agent", type=int, default=1)
    parser.add_argument("--orchestrator-max-tokens", type=int, default=1024)
    parser.add_argument("--orchestrator-repair-attempts", type=int, default=1)
    parser.add_argument("--repair-attempts", type=int, default=1)
    parser.add_argument("--execute-actions", dest="execute_actions", action="store_true", default=True)
    parser.add_argument("--no-execute-actions", dest="execute_actions", action="store_false")
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--sample-interval-seconds", type=float, default=0.5)
    parser.add_argument("--continue-on-failure", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    parser.add_argument("--mode", choices=["local", "fake"], default="local")
    parser.add_argument("--skipped-concurrency-levels", default="")
    parser.add_argument("--skip-reason", default=None)
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        from src.agent.orchestrator_executor_runtime_probe import PairSpec
        from src.agent.orchestrator_executor_stress_probe import StressProbeConfig, run_bounded_stress_probe

        result = run_bounded_stress_probe(
            StressProbeConfig(
                project_root=PROJECT_ROOT,
                mode=args.mode,
                models_config_path=args.models_config,
                runtime_profiles_config_path=args.runtime_profiles_config,
                scenario_path=args.scenario,
                out_root=args.out_root,
                label=args.label,
                pairs=_parse_pairs(args.pairs, PairSpec),
                profile_ids=_parse_csv(args.profiles),
                concurrency_levels=_parse_int_csv(args.concurrency_levels),
                runs_per_level=args.runs_per_level,
                base_port=args.base_port,
                max_group_steps=args.max_group_steps,
                max_steps_per_agent=args.max_steps_per_agent,
                orchestrator_max_tokens=args.orchestrator_max_tokens,
                orchestrator_repair_attempts=args.orchestrator_repair_attempts,
                repair_attempts=args.repair_attempts,
                execute_actions=args.execute_actions,
                timeout_seconds=args.timeout_seconds,
                sample_interval_seconds=args.sample_interval_seconds,
                continue_on_failure=args.continue_on_failure,
                force=args.force,
                skipped_concurrency_levels=_parse_int_csv(args.skipped_concurrency_levels)
                if args.skipped_concurrency_levels
                else [],
                skip_reason=args.skip_reason,
            )
        )
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: stress probe failed: {exc}", file=sys.stderr)
        return 1

    if args.json_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"probe_id: {result['probe_id']}")
    print(f"mode: {result['mode']}")
    print(f"batches: {len(result['batches'])}")
    for row in result["stress_batch_metrics"]:
        print(
            f"{row['pair']} {row['profile_id']} concurrency={row['concurrency_level']} "
            f"completed={row['runs_completed']} failed={row['runs_failed']} "
            f"quality={row['mean_pair_quality_score']} wall_ms={row['mean_wall_time_ms']} "
            f"throughput={row['throughput_runs_per_minute']} verdict={row['stability_verdict']}"
        )
    print(f"out_root: {PROJECT_ROOT / args.out_root}")
    return 0


def _parse_pairs(value: str, pair_cls: type) -> list:
    pairs = []
    for item in _parse_csv(value):
        if ":" not in item:
            raise ValueError(f"Pair must use orchestrator:executor format: {item}")
        orchestrator, executor = [part.strip() for part in item.split(":", 1)]
        if not orchestrator or not executor:
            raise ValueError(f"Pair must use orchestrator:executor format: {item}")
        pairs.append(pair_cls(orchestrator, executor))
    if not pairs:
        raise ValueError("At least one pair is required.")
    return pairs


def _parse_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def _parse_int_csv(value: str) -> list[int]:
    levels = []
    for item in _parse_csv(value):
        try:
            levels.append(int(item))
        except ValueError as exc:
            raise ValueError(f"Concurrency level must be an integer: {item}") from exc
    return levels


if __name__ == "__main__":
    raise SystemExit(main())
