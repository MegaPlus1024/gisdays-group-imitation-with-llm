from __future__ import annotations

import argparse
import json
import shutil
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run CPU-vs-GPU orchestrator/executor smoke comparison.")
    parser.add_argument("--models-config", default="configs/evaluation_models.json")
    parser.add_argument("--scenario", required=True)
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--pair", required=True, help="orchestrator:executor")
    parser.add_argument("--trials", type=int, default=1)
    parser.add_argument("--cpu-label", default="cpu_baseline")
    parser.add_argument("--gpu-label", default="gpu_smoke")
    parser.add_argument("--orchestrator-port", type=int, default=8081)
    parser.add_argument("--executor-port", type=int, default=8082)
    parser.add_argument("--gpu-layers", default="all")
    parser.add_argument("--main-gpu", type=int, default=0)
    parser.add_argument("--split-mode", choices=["none", "layer", "row", "tensor"], default="none")
    parser.add_argument("--threads", type=int, default=None)
    parser.add_argument("--ctx-size", type=int, default=4096)
    parser.add_argument("--batch-size", type=int, default=None)
    parser.add_argument("--ubatch-size", type=int, default=None)
    parser.add_argument("--flash-attention", choices=["on", "off", "auto"], default=None)
    parser.add_argument("--max-group-steps", type=int, default=2)
    parser.add_argument("--max-steps-per-agent", type=int, default=1)
    parser.add_argument("--orchestrator-max-tokens", type=int, default=1024)
    parser.add_argument("--orchestrator-repair-attempts", type=int, default=1)
    parser.add_argument("--repair-attempts", type=int, default=1)
    parser.add_argument("--execute-actions", action="store_true", default=True)
    parser.add_argument("--no-execute-actions", dest="execute_actions", action="store_false")
    parser.add_argument("--sample-interval-seconds", type=float, default=0.5)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.trials < 1:
        raise SystemExit("--trials must be >= 1")

    from src.agent.orchestrator_executor_runtime_probe import (
        PairSpec,
        RuntimeProbeConfig,
        ScenarioSpec,
        run_runtime_probe,
    )

    pair = _parse_pair(args.pair, PairSpec)
    out_root = _prepare_root(PROJECT_ROOT / args.out_root, force=args.force)
    scenario = ScenarioSpec(
        label="heavy",
        path=args.scenario,
        max_group_steps=args.max_group_steps,
        orchestrator_max_tokens=args.orchestrator_max_tokens,
    )

    cpu_result = run_runtime_probe(
        RuntimeProbeConfig(
            project_root=PROJECT_ROOT,
            mode="local",
            models_config_path=args.models_config,
            out_root=str((out_root / args.cpu_label).relative_to(PROJECT_ROOT)),
            label=args.cpu_label,
            pairs=[pair],
            scenarios=[scenario],
            trials=args.trials,
            base_orchestrator_port=args.orchestrator_port,
            base_executor_port=args.executor_port,
            manage_servers=True,
            max_steps_per_agent=args.max_steps_per_agent,
            orchestrator_repair_attempts=args.orchestrator_repair_attempts,
            repair_attempts=args.repair_attempts,
            execute_actions=args.execute_actions,
            sample_interval_seconds=args.sample_interval_seconds,
            continue_on_pair_failure=True,
            force=False,
            ctx_size=args.ctx_size,
            threads=args.threads,
            batch_size=args.batch_size,
            ubatch_size=args.ubatch_size,
            flash_attention=args.flash_attention,
        )
    )

    gpu_result = run_runtime_probe(
        RuntimeProbeConfig(
            project_root=PROJECT_ROOT,
            mode="local",
            models_config_path=args.models_config,
            out_root=str((out_root / args.gpu_label).relative_to(PROJECT_ROOT)),
            label=args.gpu_label,
            pairs=[pair],
            scenarios=[scenario],
            trials=args.trials,
            base_orchestrator_port=args.orchestrator_port,
            base_executor_port=args.executor_port,
            manage_servers=True,
            max_steps_per_agent=args.max_steps_per_agent,
            orchestrator_repair_attempts=args.orchestrator_repair_attempts,
            repair_attempts=args.repair_attempts,
            execute_actions=args.execute_actions,
            sample_interval_seconds=args.sample_interval_seconds,
            continue_on_pair_failure=True,
            force=False,
            orchestrator_gpu_layers=args.gpu_layers,
            executor_gpu_layers=args.gpu_layers,
            orchestrator_main_gpu=args.main_gpu,
            executor_main_gpu=args.main_gpu,
            split_mode=args.split_mode,
            ctx_size=args.ctx_size,
            threads=args.threads,
            batch_size=args.batch_size,
            ubatch_size=args.ubatch_size,
            flash_attention=args.flash_attention,
        )
    )

    comparison = build_comparison(args, pair, cpu_result, gpu_result, out_root)
    _write_json(out_root / "gpu_smoke_comparison.json", comparison)
    (out_root / "gpu_smoke_comparison.md").write_text(_comparison_markdown(comparison), encoding="utf-8")
    (out_root / "README.md").write_text(_readme(comparison), encoding="utf-8")
    (out_root / "replay_commands.ps1").write_text(_replay(args) + "\n", encoding="utf-8")

    if comparison["gpu_status"] in {"blocked", "failed"}:
        blocker = PROJECT_ROOT / "docs" / "ai" / "gpu_smoke_blocker_v1.md"
        blocker.write_text(_blocker_markdown(comparison), encoding="utf-8")

    print(f"artifact_root: {out_root}")
    print(f"cpu_status: {comparison['cpu_status']}")
    print(f"gpu_status: {comparison['gpu_status']}")
    print(f"speedup_wall_time_ratio: {comparison['speedup_wall_time_ratio']}")
    return 0


def build_comparison(args: argparse.Namespace, pair: Any, cpu_result: dict[str, Any], gpu_result: dict[str, Any], out_root: Path) -> dict[str, Any]:
    cpu_row = _first_row(cpu_result)
    gpu_row = _first_row(gpu_result)
    cpu_wall = _number(cpu_row.get("mean_wall_time_ms"))
    gpu_wall = _number(gpu_row.get("mean_wall_time_ms"))
    speedup = round(cpu_wall / gpu_wall, 6) if cpu_wall and gpu_wall and gpu_wall > 0 else None
    return {
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "artifact_root": str(out_root),
        "pair": pair.label,
        "scenario": args.scenario,
        "cpu_label": args.cpu_label,
        "gpu_label": args.gpu_label,
        "cpu_status": cpu_row.get("status"),
        "gpu_status": gpu_row.get("status"),
        "cpu_pair_quality_score": cpu_row.get("mean_pair_quality_score"),
        "gpu_pair_quality_score": gpu_row.get("mean_pair_quality_score"),
        "cpu_execution_success_rate": cpu_row.get("mean_execution_success_rate"),
        "gpu_execution_success_rate": gpu_row.get("mean_execution_success_rate"),
        "cpu_total_errors": cpu_row.get("total_errors"),
        "gpu_total_errors": gpu_row.get("total_errors"),
        "cpu_wall_time_ms": cpu_wall,
        "gpu_wall_time_ms": gpu_wall,
        "speedup_wall_time_ratio": speedup,
        "cpu_peak_ram_mb": cpu_row.get("peak_ram_mb_pair"),
        "gpu_peak_ram_mb": gpu_row.get("peak_ram_mb_pair"),
        "cpu_peak_cpu_percent": cpu_row.get("peak_cpu_percent_pair"),
        "gpu_peak_cpu_percent": gpu_row.get("peak_cpu_percent_pair"),
        "cpu_peak_vram_mb": cpu_row.get("gpu_peak_vram_mb"),
        "gpu_peak_vram_mb": gpu_row.get("gpu_peak_vram_mb"),
        "cpu_peak_gpu_utilization_percent": cpu_row.get("gpu_peak_utilization_percent"),
        "gpu_peak_gpu_utilization_percent": gpu_row.get("gpu_peak_utilization_percent"),
        "cpu_server_flags_used": cpu_row.get("server_flags_used"),
        "gpu_server_flags_used": gpu_row.get("server_flags_used"),
        "cpu_baseline_note": (
            "CPU baseline means no explicit wrapper GPU placement flags. "
            "This is not the same as strict --device none; local llama-server help reports default GPU layers as auto."
        ),
        "gpu_layers": args.gpu_layers,
        "main_gpu": args.main_gpu,
        "split_mode": args.split_mode,
        "interpretation": _interpretation(cpu_row, gpu_row, speedup),
    }


def _first_row(result: dict[str, Any]) -> dict[str, Any]:
    rows = result.get("runtime_metrics_by_pair_scenario") or []
    return rows[0] if rows else {}


def _interpretation(cpu_row: dict[str, Any], gpu_row: dict[str, Any], speedup: float | None) -> str:
    if gpu_row.get("status") in {"blocked", "failed"}:
        return "GPU smoke did not complete; preserve blocker artifacts and do not use GPU for stress testing yet."
    if speedup is None:
        return "GPU smoke completed but speedup could not be computed."
    if speedup > 1.05:
        return "GPU smoke was faster in wall time for this short run."
    if speedup < 0.95:
        return "GPU smoke was slower in wall time for this short run."
    return "GPU smoke wall time was roughly comparable to the CPU baseline."


def _comparison_markdown(comparison: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# GPU Smoke Comparison",
            "",
            f"- pair: `{comparison['pair']}`",
            f"- scenario: `{comparison['scenario']}`",
            f"- interpretation: {comparison['interpretation']}",
            f"- CPU baseline note: {comparison['cpu_baseline_note']}",
            "",
            "| metric | CPU baseline | GPU smoke |",
            "|---|---:|---:|",
            f"| status | `{comparison['cpu_status']}` | `{comparison['gpu_status']}` |",
            f"| pair_quality_score | {comparison['cpu_pair_quality_score']} | {comparison['gpu_pair_quality_score']} |",
            f"| execution_success_rate | {comparison['cpu_execution_success_rate']} | {comparison['gpu_execution_success_rate']} |",
            f"| total_errors | {comparison['cpu_total_errors']} | {comparison['gpu_total_errors']} |",
            f"| wall_time_ms | {comparison['cpu_wall_time_ms']} | {comparison['gpu_wall_time_ms']} |",
            f"| peak_ram_mb | {comparison['cpu_peak_ram_mb']} | {comparison['gpu_peak_ram_mb']} |",
            f"| peak_cpu_percent | {comparison['cpu_peak_cpu_percent']} | {comparison['gpu_peak_cpu_percent']} |",
            f"| peak_vram_mb | {comparison['cpu_peak_vram_mb']} | {comparison['gpu_peak_vram_mb']} |",
            f"| peak_gpu_utilization_percent | {comparison['cpu_peak_gpu_utilization_percent']} | {comparison['gpu_peak_gpu_utilization_percent']} |",
            "",
            f"speedup_wall_time_ratio: `{comparison['speedup_wall_time_ratio']}`",
            "",
        ]
    )


def _readme(comparison: dict[str, Any]) -> str:
    return (
        "# GPU Smoke Second-to-Second Heavy v1\n\n"
        f"- pair: `{comparison['pair']}`\n"
        f"- scenario: `{comparison['scenario']}`\n"
        "- CPU baseline and GPU smoke are both short N=1 local probes.\n"
        "- This is not a stress test and not a production recommendation.\n\n"
        "Primary files:\n\n"
        "- `gpu_smoke_comparison.json`\n"
        "- `gpu_smoke_comparison.md`\n"
        "- `cpu_baseline/`\n"
        "- `gpu_smoke/`\n"
    )


def _blocker_markdown(comparison: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# GPU Smoke Blocker v1",
            "",
            "The GPU smoke run did not complete successfully.",
            "",
            f"- artifact root: `{comparison['artifact_root']}`",
            f"- pair: `{comparison['pair']}`",
            f"- scenario: `{comparison['scenario']}`",
            f"- cpu_status: `{comparison['cpu_status']}`",
            f"- gpu_status: `{comparison['gpu_status']}`",
            "",
            "Do not claim GPU runtime support is ready until this blocker is resolved.",
            "",
        ]
    )


def _replay(args: argparse.Namespace) -> str:
    parts = [
        ".\\.venv\\Scripts\\python.exe",
        "scripts\\run_gpu_smoke_orchestrator_executor.py",
        "--models-config",
        args.models_config,
        "--scenario",
        args.scenario,
        "--out-root",
        args.out_root,
        "--pair",
        args.pair,
        "--trials",
        str(args.trials),
        "--cpu-label",
        args.cpu_label,
        "--gpu-label",
        args.gpu_label,
        "--orchestrator-port",
        str(args.orchestrator_port),
        "--executor-port",
        str(args.executor_port),
        "--gpu-layers",
        str(args.gpu_layers),
        "--main-gpu",
        str(args.main_gpu),
        "--split-mode",
        args.split_mode,
        "--ctx-size",
        str(args.ctx_size),
        "--max-group-steps",
        str(args.max_group_steps),
        "--max-steps-per-agent",
        str(args.max_steps_per_agent),
        "--orchestrator-max-tokens",
        str(args.orchestrator_max_tokens),
        "--orchestrator-repair-attempts",
        str(args.orchestrator_repair_attempts),
        "--repair-attempts",
        str(args.repair_attempts),
        "--execute-actions",
        "--sample-interval-seconds",
        str(args.sample_interval_seconds),
        "--force",
    ]
    if args.threads is not None:
        parts.extend(["--threads", str(args.threads)])
    if args.batch_size is not None:
        parts.extend(["--batch-size", str(args.batch_size)])
    if args.ubatch_size is not None:
        parts.extend(["--ubatch-size", str(args.ubatch_size)])
    if args.flash_attention:
        parts.extend(["--flash-attention", args.flash_attention])
    return " ".join(parts)


def _prepare_root(path: Path, *, force: bool) -> Path:
    if path.exists():
        if not force:
            raise FileExistsError(f"Output root already exists: {path}")
        resolved = path.resolve()
        try:
            resolved.relative_to(PROJECT_ROOT.resolve())
        except ValueError as exc:
            raise RuntimeError(f"Refusing to remove output outside project root: {resolved}") from exc
        if resolved == PROJECT_ROOT.resolve():
            raise RuntimeError("Refusing to remove project root.")
        shutil.rmtree(resolved)
    path.mkdir(parents=True, exist_ok=True)
    return path


def _parse_pair(value: str, pair_cls: type) -> Any:
    if ":" not in value:
        raise ValueError("--pair must use orchestrator:executor format")
    orchestrator, executor = [part.strip() for part in value.split(":", 1)]
    if not orchestrator or not executor:
        raise ValueError("--pair must use orchestrator:executor format")
    return pair_cls(orchestrator, executor)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _number(value: Any) -> float | None:
    return float(value) if isinstance(value, int | float) and not isinstance(value, bool) else None


if __name__ == "__main__":
    raise SystemExit(main())
