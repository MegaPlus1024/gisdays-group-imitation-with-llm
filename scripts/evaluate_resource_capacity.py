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
        description="Evaluate resource observations and conservative multi-agent capacity from existing artifacts."
    )
    parser.add_argument("--models-config", default="configs/evaluation_models.json")
    parser.add_argument("--model-ids", required=True, help="Comma-separated model ids.")
    parser.add_argument(
        "--repeated-trials-root",
        action="append",
        required=True,
        help="Scenario root formatted as scenario_id=path.",
    )
    parser.add_argument("--cross-scenario-analysis")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--label", default="resource_capacity_v1")
    parser.add_argument("--target-cpu-utilization-percent", type=float, default=70.0)
    parser.add_argument("--reserved-system-ram-mb", type=float, default=4096.0)
    parser.add_argument("--probe-runtime", dest="probe_runtime", action="store_true")
    parser.add_argument("--no-probe-runtime", dest="probe_runtime", action="store_false")
    parser.set_defaults(probe_runtime=False)
    parser.add_argument("--probe-steps", type=int, default=1)
    parser.add_argument("--manage-server", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    return parser


def _project_path(value: str | None) -> Path | None:
    if value is None:
        return None
    path = Path(value)
    return path if path.is_absolute() else PROJECT_ROOT / path


def _parse_scenario_root(value: str) -> tuple[str, Path]:
    parts = value.split("=", 1)
    if len(parts) != 2:
        raise ValueError("--repeated-trials-root must be formatted as scenario_id=path")
    scenario_id, path = parts
    if not scenario_id.strip():
        raise ValueError("scenario_id must be non-empty")
    resolved = _project_path(path)
    assert resolved is not None
    return scenario_id, resolved


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from src.agent.resource_capacity_evaluation import (
        build_resource_capacity_evaluation,
        capacity_formula_markdown,
        write_replay_command,
        write_resource_capacity_evaluation,
    )

    try:
        model_ids = [item.strip() for item in args.model_ids.split(",") if item.strip()]
        scenario_roots = dict(_parse_scenario_root(item) for item in args.repeated_trials_root)
        result = build_resource_capacity_evaluation(
            model_ids=model_ids,
            models_config_path=_project_path(args.models_config) or Path(args.models_config),
            scenario_roots=scenario_roots,
            cross_scenario_analysis_path=_project_path(args.cross_scenario_analysis),
            output_label=args.label,
            target_cpu_utilization_percent=args.target_cpu_utilization_percent,
            reserved_system_ram_mb=args.reserved_system_ram_mb,
            probe_runtime=args.probe_runtime,
            probe_steps=args.probe_steps,
            project_root=PROJECT_ROOT,
        )
        out = write_resource_capacity_evaluation(result, _project_path(args.out_dir) or Path(args.out_dir), force=args.force)
        (out / "capacity_formula.md").write_text(capacity_formula_markdown(result), encoding="utf-8")
        write_replay_command(out, " ".join(sys.argv))
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: resource/capacity evaluation failed: {exc}", file=sys.stderr)
        return 1

    if args.json_only:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
        return 0

    print(f"evaluation_id: {result.evaluation_id}")
    print(f"out_dir: {out}")
    print(f"runtime_probe_status: {result.runtime_probe_results.status}")
    print("model_id,mean_selection_latency_ms,estimated_concurrent_agents,bottleneck,confidence")
    for model_id, estimate in result.capacity_estimates.items():
        summary = result.per_model_resource_summary.get(model_id)
        print(
            f"{model_id},{summary.mean_selection_latency_ms if summary else None},"
            f"{estimate.estimate.estimated_concurrent_agents},{estimate.estimate.bottleneck},"
            f"{estimate.estimate.confidence}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
