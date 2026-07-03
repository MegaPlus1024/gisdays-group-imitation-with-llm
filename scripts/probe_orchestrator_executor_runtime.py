from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Probe runtime/resource telemetry for orchestrator/executor pairs.")
    parser.add_argument("--models-config", default="configs/evaluation_models.json")
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--label", default="runtime_probe_candidate_pairs_v1")
    parser.add_argument("--pairs", required=True, help="Comma-separated orchestrator:executor pairs.")
    parser.add_argument("--scenarios", required=True, help="Comma-separated label=path scenario entries.")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--mode", choices=["local", "fake"], default="local")
    parser.add_argument("--base-orchestrator-port", type=int, default=8081)
    parser.add_argument("--base-executor-port", type=int, default=8082)
    parser.add_argument("--manage-servers", dest="manage_servers", action="store_true", default=True)
    parser.add_argument("--no-manage-servers", dest="manage_servers", action="store_false")
    parser.add_argument("--max-steps-per-agent", type=int, default=1)
    parser.add_argument("--max-group-steps", type=int, default=None)
    parser.add_argument("--simple-max-group-steps", type=int, default=1)
    parser.add_argument("--heavy-max-group-steps", type=int, default=2)
    parser.add_argument("--orchestrator-max-tokens", type=int, default=None)
    parser.add_argument("--simple-orchestrator-max-tokens", type=int, default=768)
    parser.add_argument("--heavy-orchestrator-max-tokens", type=int, default=1024)
    parser.add_argument("--orchestrator-repair-attempts", type=int, default=1)
    parser.add_argument("--repair-attempts", type=int, default=1)
    parser.add_argument("--execute-actions", dest="execute_actions", action="store_true", default=True)
    parser.add_argument("--no-execute-actions", dest="execute_actions", action="store_false")
    parser.add_argument("--sample-interval-seconds", type=float, default=0.5)
    parser.add_argument("--orchestrator-gpu-layers", default=None)
    parser.add_argument("--executor-gpu-layers", default=None)
    parser.add_argument("--orchestrator-main-gpu", type=int, default=None)
    parser.add_argument("--executor-main-gpu", type=int, default=None)
    parser.add_argument("--split-mode", choices=["none", "layer", "row", "tensor"], default=None)
    parser.add_argument("--tensor-split", default=None)
    parser.add_argument("--threads", type=int, default=None)
    parser.add_argument("--ctx-size", type=int, default=None)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--ubatch-size", type=int, default=None)
    parser.add_argument("--flash-attention", choices=["on", "off", "auto"], default=None)
    parser.add_argument("--cpu-only", action="store_true")
    parser.add_argument("--continue-on-pair-failure", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.trials < 1:
        parser.error("--trials must be >= 1")

    from src.agent.orchestrator_executor_runtime_probe import (
        PairSpec,
        RuntimeProbeConfig,
        ScenarioSpec,
        run_runtime_probe,
    )

    try:
        pairs = _parse_pairs(args.pairs, PairSpec)
        scenarios = _parse_scenarios(args, ScenarioSpec)
        result = run_runtime_probe(
            RuntimeProbeConfig(
                project_root=PROJECT_ROOT,
                mode=args.mode,
                models_config_path=args.models_config,
                out_root=args.out_root,
                label=args.label,
                pairs=pairs,
                scenarios=scenarios,
                trials=args.trials,
                base_orchestrator_port=args.base_orchestrator_port,
                base_executor_port=args.base_executor_port,
                manage_servers=args.manage_servers,
                max_steps_per_agent=args.max_steps_per_agent,
                orchestrator_repair_attempts=args.orchestrator_repair_attempts,
                repair_attempts=args.repair_attempts,
                execute_actions=args.execute_actions,
                sample_interval_seconds=args.sample_interval_seconds,
                continue_on_pair_failure=args.continue_on_pair_failure,
                force=args.force,
                orchestrator_gpu_layers=args.orchestrator_gpu_layers,
                executor_gpu_layers=args.executor_gpu_layers,
                orchestrator_main_gpu=args.orchestrator_main_gpu,
                executor_main_gpu=args.executor_main_gpu,
                split_mode=args.split_mode,
                tensor_split=args.tensor_split,
                threads=args.threads,
                ctx_size=args.ctx_size,
                batch_size=args.batch_size,
                ubatch_size=args.ubatch_size,
                flash_attention=args.flash_attention,
                cpu_only=args.cpu_only,
            )
        )
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: runtime probe failed: {exc}", file=sys.stderr)
        return 1

    if args.json_only:
        print(json.dumps(result, ensure_ascii=False, indent=2))
        return 0

    print(f"probe_id: {result['probe_id']}")
    print(f"mode: {result['mode']}")
    print(f"runs: {len(result['runs'])}")
    for row in result["runtime_metrics_by_pair_scenario"]:
        print(
            f"{row['scenario']} {row['pair']} completed={row['completed_trials']} "
            f"errors={row['total_errors']} peak_ram_mb={row['peak_ram_mb_pair']} "
            f"peak_cpu_percent={row['peak_cpu_percent_pair']} "
            f"peak_vram_mb={row.get('gpu_peak_vram_mb')}"
        )
    print(f"out_root: {PROJECT_ROOT / args.out_root}")
    return 0


def _parse_pairs(value: str, pair_cls: type) -> list:
    out = []
    for item in value.split(","):
        item = item.strip()
        if not item:
            continue
        if ":" not in item:
            raise ValueError(f"Pair must use orchestrator:executor format: {item}")
        orchestrator, executor = [part.strip() for part in item.split(":", 1)]
        if not orchestrator or not executor:
            raise ValueError(f"Pair must use orchestrator:executor format: {item}")
        out.append(pair_cls(orchestrator, executor))
    if not out:
        raise ValueError("At least one pair is required.")
    return out


def _parse_scenarios(args: argparse.Namespace, scenario_cls: type) -> list:
    out = []
    for item in args.scenarios.split(","):
        item = item.strip()
        if not item:
            continue
        if "=" not in item:
            raise ValueError(f"Scenario must use label=path format: {item}")
        label, path = [part.strip() for part in item.split("=", 1)]
        if not label or not path:
            raise ValueError(f"Scenario must use label=path format: {item}")
        max_group_steps = args.max_group_steps
        if max_group_steps is None:
            max_group_steps = args.heavy_max_group_steps if label.lower() == "heavy" else args.simple_max_group_steps
        max_tokens = args.orchestrator_max_tokens
        if max_tokens is None:
            max_tokens = args.heavy_orchestrator_max_tokens if label.lower() == "heavy" else args.simple_orchestrator_max_tokens
        out.append(scenario_cls(label=label, path=path, max_group_steps=max_group_steps, orchestrator_max_tokens=max_tokens))
    if not out:
        raise ValueError("At least one scenario is required.")
    return out


if __name__ == "__main__":
    raise SystemExit(main())
