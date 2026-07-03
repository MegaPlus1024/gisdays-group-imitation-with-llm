from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import sys
import threading
import time
from concurrent.futures import Future, ThreadPoolExecutor, wait
from collections import Counter
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .orchestrator_executor_runtime_probe import (
    ManagedServer,
    PairSpec,
    RuntimeProbeConfig,
    _base_url,
    _endpoint_json,
    _llama_server_pids,
    _server_flags_used,
    _server_payload,
    _start_managed_servers,
    _stop_managed_servers,
    collect_gpu_telemetry,
    collect_system_snapshot,
    summarize_samples,
)
from .repeated_orchestrator_executor_trials import (
    RepeatedGroupRunConfig,
    run_repeated_group_trials,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
StressStatus = Literal["completed", "completed_with_failures", "failed", "blocked"]


@dataclass(frozen=True)
class RuntimeProfile:
    profile_id: str
    description: str
    server_params: dict[str, Any] = field(default_factory=dict)
    expected_gpu_usage: str = "unknown"
    confidence: str = "low"
    limitations: list[str] = field(default_factory=list)


@dataclass(frozen=True)
class StressProbeConfig:
    project_root: Path
    mode: Literal["local", "fake"]
    models_config_path: str
    runtime_profiles_config_path: str
    scenario_path: str
    out_root: str
    label: str
    pairs: list[PairSpec]
    profile_ids: list[str]
    concurrency_levels: list[int]
    runs_per_level: int
    base_port: int = 8081
    max_group_steps: int = 2
    max_steps_per_agent: int = 1
    orchestrator_max_tokens: int = 1024
    orchestrator_repair_attempts: int = 1
    repair_attempts: int = 1
    execute_actions: bool = True
    timeout_seconds: float = 180.0
    sample_interval_seconds: float = 0.5
    continue_on_failure: bool = True
    force: bool = False
    skipped_concurrency_levels: list[int] = field(default_factory=list)
    skip_reason: str | None = None


def load_runtime_profiles(project_root: Path, config_path: str | Path) -> dict[str, RuntimeProfile]:
    path = Path(config_path)
    if not path.is_absolute():
        path = project_root / path
    payload = json.loads(path.read_text(encoding="utf-8"))
    profiles: dict[str, RuntimeProfile] = {}
    for row in payload.get("profiles") or []:
        profile_id = str(row.get("profile_id") or "").strip()
        if not profile_id:
            raise ValueError("Runtime profile is missing profile_id.")
        if profile_id in profiles:
            raise ValueError(f"Runtime profile is duplicated: {profile_id}")
        server_params = row.get("server_params") or {}
        if not isinstance(server_params, dict):
            raise ValueError(f"Runtime profile server_params must be an object: {profile_id}")
        profiles[profile_id] = RuntimeProfile(
            profile_id=profile_id,
            description=str(row.get("description") or ""),
            server_params=server_params,
            expected_gpu_usage=str(row.get("expected_gpu_usage") or "unknown"),
            confidence=str(row.get("confidence") or "low"),
            limitations=[str(item) for item in row.get("limitations") or []],
        )
    if not profiles:
        raise ValueError("Runtime profiles config must contain at least one profile.")
    return profiles


def select_runtime_profiles(
    profiles: dict[str, RuntimeProfile], profile_ids: list[str]
) -> list[RuntimeProfile]:
    selected: list[RuntimeProfile] = []
    for profile_id in profile_ids:
        if profile_id not in profiles:
            raise ValueError(f"Unknown runtime profile: {profile_id}")
        selected.append(profiles[profile_id])
    if not selected:
        raise ValueError("At least one runtime profile is required.")
    return selected


def run_bounded_stress_probe(config: StressProbeConfig) -> dict[str, Any]:
    _validate_config(config)
    out_root = _prepare_output_root(config.project_root / config.out_root, force=config.force)
    profiles = load_runtime_profiles(config.project_root, config.runtime_profiles_config_path)
    selected_profiles = select_runtime_profiles(profiles, config.profile_ids)
    batches: list[dict[str, Any]] = []
    metrics_rows: list[dict[str, Any]] = []
    system_before = collect_system_snapshot()
    gpu_before = collect_gpu_telemetry()

    for pair in config.pairs:
        for profile in selected_profiles:
            for level in config.concurrency_levels:
                batch = _run_stress_batch(
                    config=config,
                    out_root=out_root,
                    pair=pair,
                    profile=profile,
                    concurrency_level=level,
                )
                batches.append(batch)
                metrics_rows.append(batch["metrics"])
                if batch["status"] in {"failed", "blocked"} and not config.continue_on_failure:
                    break

    system_after = collect_system_snapshot()
    gpu_after = collect_gpu_telemetry()
    summary = compute_summary_by_pair_profile(metrics_rows)
    tradeoff = build_quality_latency_tradeoff(metrics_rows)
    comparison = build_gpu_vs_cpu_comparison(metrics_rows, selected_profiles)
    capacity = build_capacity_estimates(summary, metrics_rows)
    profile_validation = build_runtime_profile_validation(selected_profiles, metrics_rows, gpu_before, gpu_after)
    endpoint_check = _ports_health(config.base_port, 8)
    result = {
        "probe_id": config.label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": config.mode,
        "models_config_path": config.models_config_path,
        "runtime_profiles_config_path": config.runtime_profiles_config_path,
        "scenario_path": config.scenario_path,
        "protocol": _protocol_payload(config),
        "system_before": system_before,
        "system_after": system_after,
        "gpu_before": gpu_before,
        "gpu_after": gpu_after,
        "batches": batches,
        "stress_batch_metrics": metrics_rows,
        "stress_summary_by_pair_profile": summary,
        "stress_quality_latency_tradeoff": tradeoff,
        "runtime_profile_validation": profile_validation,
        "gpu_vs_cpu_stress_comparison": comparison,
        "capacity_stress_estimates": capacity,
        "post_run_endpoint_check": endpoint_check,
        "skipped_concurrency_levels": config.skipped_concurrency_levels,
        "skip_reason": config.skip_reason,
        "limitations": [
            "Bounded smoke only; this is not a destructive or production stress test.",
            "No external network, real browser automation, or real office automation was used.",
            "Concurrency is limited to the requested local levels and short scenario bounds.",
            "GPU telemetry is device-level and can include unrelated local graphics workload.",
        ],
    }
    write_stress_probe_outputs(result, out_root, config)
    return result


class StressSampler:
    def __init__(
        self,
        *,
        pids: list[int],
        endpoints: dict[str, int],
        interval_seconds: float,
    ) -> None:
        self.pids = pids
        self.endpoints = endpoints
        self.interval_seconds = max(0.1, interval_seconds)
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="stress-probe-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        try:
            import psutil  # type: ignore
        except Exception as exc:
            self.samples.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "psutil_available": False,
                    "error": str(exc) or exc.__class__.__name__,
                    "processes": [],
                    "gpu": collect_gpu_telemetry(),
                    "endpoints": _endpoint_sample(self.endpoints),
                }
            )
            return

        processes = []
        for pid in self.pids:
            try:
                process = psutil.Process(pid)
                process.cpu_percent(interval=None)
                processes.append(process)
            except Exception:
                continue

        while not self._stop.is_set():
            vm = psutil.virtual_memory()
            process_rows = []
            for process in list(processes):
                try:
                    process_rows.append(
                        {
                            "pid": process.pid,
                            "name": process.name(),
                            "rss_mb": _mb(process.memory_info().rss),
                            "cpu_percent": round(float(process.cpu_percent(interval=None)), 6),
                            "status": process.status(),
                        }
                    )
                except Exception as exc:
                    process_rows.append({"pid": process.pid, "error": str(exc) or exc.__class__.__name__})
            self.samples.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "psutil_available": True,
                    "processes": process_rows,
                    "pair_rss_mb": round(sum(float(row.get("rss_mb") or 0.0) for row in process_rows), 6),
                    "pair_cpu_percent": round(sum(float(row.get("cpu_percent") or 0.0) for row in process_rows), 6),
                    "system_cpu_percent": round(float(psutil.cpu_percent(interval=None)), 6),
                    "system_ram_total_mb": _mb(vm.total),
                    "system_ram_available_mb": _mb(vm.available),
                    "active_llama_server_processes": len([row for row in process_rows if not row.get("error")]),
                    "gpu": collect_gpu_telemetry(),
                    "endpoints": _endpoint_sample(self.endpoints),
                }
            )
            self._stop.wait(self.interval_seconds)


def aggregate_batch_metrics(
    *,
    pair: PairSpec,
    profile: RuntimeProfile,
    concurrency_level: int,
    planned_runs: int,
    run_records: list[dict[str, Any]],
    samples: list[dict[str, Any]],
    server_error: str | None,
    batch_wall_time_ms: float,
    max_group_steps: int,
) -> dict[str, Any]:
    completed_records = [record for record in run_records if record.get("status") == "completed"]
    failed_records = [record for record in run_records if record.get("status") in {"failed", "timeout"}]
    aggregates = [record.get("aggregate") or {} for record in run_records]
    completed_aggregates = [record.get("aggregate") or {} for record in completed_records]
    failure_modes = Counter()
    for aggregate in aggregates:
        failure_modes.update(aggregate.get("common_failure_modes") or {})
    for record in failed_records:
        if record.get("error_type"):
            failure_modes[str(record["error_type"])] += 1

    telemetry = summarize_stress_samples(samples)
    mean_wall = _safe_mean([_number(item.get("mean_wall_time_ms")) for item in aggregates])
    p95_wall = _percentile([_number(item.get("mean_wall_time_ms")) for item in aggregates], 95)
    mean_quality = _safe_mean([_number(item.get("mean_pair_quality_score")) for item in completed_aggregates])
    mean_execution = _safe_mean([_number(item.get("mean_execution_success_rate")) for item in completed_aggregates])
    total_errors = sum(_int(item.get("total_errors")) for item in aggregates)
    total_errors += sum(1 for record in failed_records if not record.get("aggregate"))
    timeout_count = sum(1 for record in run_records if record.get("status") == "timeout")
    endpoint_error_count = _endpoint_error_count(failure_modes, server_error, samples)
    minutes = batch_wall_time_ms / 60000.0 if batch_wall_time_ms > 0 else 0.0
    throughput_runs = round(len(completed_records) / minutes, 6) if minutes > 0 else None
    throughput_steps = round((len(completed_records) * max_group_steps) / minutes, 6) if minutes > 0 else None
    verdict = _stability_verdict(
        runs_started=len(run_records),
        runs_completed=len(completed_records),
        runs_failed=len(failed_records),
        timeout_count=timeout_count,
        endpoint_error_count=endpoint_error_count,
        server_error=server_error,
    )
    return {
        "profile_id": profile.profile_id,
        "pair": pair.label,
        "pair_id": pair.pair_id,
        "concurrency_level": concurrency_level,
        "planned_runs": planned_runs,
        "runs_started": len(run_records),
        "runs_completed": len(completed_records),
        "runs_failed": len(failed_records),
        "timeout_count": timeout_count,
        "mean_wall_time_ms": mean_wall,
        "p95_wall_time_ms": p95_wall,
        "mean_pair_quality_score": mean_quality,
        "mean_execution_success_rate": mean_execution,
        "total_errors": total_errors,
        "errors_per_run": round(total_errors / len(run_records), 6) if run_records else None,
        "validation_failure_count": _count_failure_modes(failure_modes, "validation"),
        "repair_failure_count": _count_failure_modes(failure_modes, "repair"),
        "endpoint_error_count": endpoint_error_count,
        "peak_ram_mb_total": telemetry.get("peak_ram_mb_pair"),
        "peak_ram_mb_per_server": telemetry.get("peak_ram_mb_per_server"),
        "peak_cpu_percent_total": telemetry.get("peak_cpu_percent_pair"),
        "peak_vram_mb": telemetry.get("gpu_peak_vram_mb"),
        "mean_vram_mb": telemetry.get("gpu_mean_vram_mb"),
        "peak_gpu_utilization_percent": telemetry.get("gpu_peak_utilization_percent"),
        "mean_gpu_utilization_percent": telemetry.get("gpu_mean_utilization_percent"),
        "gpu_telemetry_available": telemetry.get("gpu_telemetry_available"),
        "gpu_name": telemetry.get("gpu_name"),
        "gpu_total_vram_mb": telemetry.get("gpu_total_vram_mb"),
        "throughput_runs_per_minute": throughput_runs,
        "throughput_group_steps_per_minute": throughput_steps,
        "batch_wall_time_ms": round(batch_wall_time_ms, 6),
        "sample_count": telemetry.get("sample_count"),
        "server_error": server_error,
        "common_failure_modes": dict(failure_modes.most_common(12)),
        "stability_verdict": verdict,
    }


def summarize_stress_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    summary = summarize_samples(samples)
    process_rss = []
    endpoint_unhealthy_samples = 0
    for sample in samples:
        for process in sample.get("processes") or []:
            value = _number(process.get("rss_mb"))
            if value is not None:
                process_rss.append(value)
        endpoints = sample.get("endpoints") or {}
        if any(not row.get("healthy") for row in endpoints.values()):
            endpoint_unhealthy_samples += 1
    summary["peak_ram_mb_per_server"] = _safe_max(process_rss)
    summary["endpoint_unhealthy_sample_count"] = endpoint_unhealthy_samples
    return summary


def compute_summary_by_pair_profile(metrics_rows: list[dict[str, Any]]) -> list[dict[str, Any]]:
    grouped: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in metrics_rows:
        grouped.setdefault((str(row.get("pair")), str(row.get("profile_id"))), []).append(row)

    summaries: list[dict[str, Any]] = []
    for (pair, profile_id), rows in sorted(grouped.items()):
        rows = sorted(rows, key=lambda row: int(row.get("concurrency_level") or 0))
        baseline = _row_for_level(rows, 1)
        max_stable = _max_level_with_verdict(rows, {"stable"})
        summaries.append(
            {
                "pair": pair,
                "profile_id": profile_id,
                "levels_observed": [row.get("concurrency_level") for row in rows],
                "max_stable_concurrency_observed": max_stable,
                "max_nonfailed_concurrency_observed": _max_level_with_verdict(rows, {"stable", "degraded"}),
                "quality_degradation_at_concurrency_2": _quality_degradation(baseline, _row_for_level(rows, 2)),
                "latency_degradation_at_concurrency_2": _latency_degradation(baseline, _row_for_level(rows, 2)),
                "quality_degradation_at_concurrency_4": _quality_degradation(baseline, _row_for_level(rows, 4)),
                "latency_degradation_at_concurrency_4": _latency_degradation(baseline, _row_for_level(rows, 4)),
                "bottleneck": _infer_bottleneck(rows),
                "mean_quality_across_levels": _safe_mean(
                    [_number(row.get("mean_pair_quality_score")) for row in rows]
                ),
                "max_peak_ram_mb_total": _safe_max([_number(row.get("peak_ram_mb_total")) for row in rows]),
                "max_peak_vram_mb": _safe_max([_number(row.get("peak_vram_mb")) for row in rows]),
                "max_peak_gpu_utilization_percent": _safe_max(
                    [_number(row.get("peak_gpu_utilization_percent")) for row in rows]
                ),
                "verdicts": {
                    str(row.get("concurrency_level")): row.get("stability_verdict")
                    for row in rows
                },
            }
        )
    return summaries


def build_quality_latency_tradeoff(metrics_rows: list[dict[str, Any]]) -> dict[str, Any]:
    rankings = []
    for row in metrics_rows:
        quality = _number(row.get("mean_pair_quality_score")) or 0.0
        wall = _number(row.get("mean_wall_time_ms")) or 0.0
        errors = _int(row.get("total_errors"))
        throughput = _number(row.get("throughput_runs_per_minute")) or 0.0
        score = quality
        score -= min(errors, 20) * 0.01
        if wall > 0:
            score += min(0.2, 5000.0 / wall * 0.05)
        score += min(0.15, throughput * 0.01)
        if row.get("stability_verdict") == "failed":
            score -= 0.5
        elif row.get("stability_verdict") == "unstable":
            score -= 0.25
        elif row.get("stability_verdict") == "degraded":
            score -= 0.1
        rankings.append(
            {
                "pair": row.get("pair"),
                "profile_id": row.get("profile_id"),
                "concurrency_level": row.get("concurrency_level"),
                "mean_pair_quality_score": row.get("mean_pair_quality_score"),
                "mean_wall_time_ms": row.get("mean_wall_time_ms"),
                "total_errors": row.get("total_errors"),
                "throughput_runs_per_minute": row.get("throughput_runs_per_minute"),
                "stability_verdict": row.get("stability_verdict"),
                "quality_latency_score": round(score, 6),
            }
        )
    rankings.sort(key=lambda row: row["quality_latency_score"], reverse=True)
    return {
        "rankings": rankings,
        "best_observed_batch": rankings[0] if rankings else None,
        "recommendation_status": "preliminary only",
    }


def build_gpu_vs_cpu_comparison(
    metrics_rows: list[dict[str, Any]], profiles: list[RuntimeProfile]
) -> dict[str, Any]:
    cpu_ids = {
        profile.profile_id
        for profile in profiles
        if profile.expected_gpu_usage == "none" or "cpu" in profile.profile_id.lower()
    }
    gpu_ids = {
        profile.profile_id
        for profile in profiles
        if profile.expected_gpu_usage == "high" or "gpu" in profile.profile_id.lower()
    }
    rows = []
    by_key = {
        (row.get("pair"), row.get("profile_id"), row.get("concurrency_level")): row
        for row in metrics_rows
    }
    pairs = sorted({row.get("pair") for row in metrics_rows})
    levels = sorted({_int(row.get("concurrency_level")) for row in metrics_rows})
    for pair in pairs:
        for level in levels:
            cpu_row = next(
                (by_key.get((pair, profile_id, level)) for profile_id in cpu_ids if by_key.get((pair, profile_id, level))),
                None,
            )
            gpu_row = next(
                (by_key.get((pair, profile_id, level)) for profile_id in gpu_ids if by_key.get((pair, profile_id, level))),
                None,
            )
            if not cpu_row or not gpu_row:
                continue
            cpu_wall = _number(cpu_row.get("mean_wall_time_ms"))
            gpu_wall = _number(gpu_row.get("mean_wall_time_ms"))
            rows.append(
                {
                    "pair": pair,
                    "concurrency_level": level,
                    "cpu_profile_id": cpu_row.get("profile_id"),
                    "gpu_profile_id": gpu_row.get("profile_id"),
                    "cpu_mean_wall_time_ms": cpu_wall,
                    "gpu_mean_wall_time_ms": gpu_wall,
                    "speedup_wall_time_ratio": round(cpu_wall / gpu_wall, 6)
                    if cpu_wall and gpu_wall and gpu_wall > 0
                    else None,
                    "cpu_mean_pair_quality_score": cpu_row.get("mean_pair_quality_score"),
                    "gpu_mean_pair_quality_score": gpu_row.get("mean_pair_quality_score"),
                    "cpu_total_errors": cpu_row.get("total_errors"),
                    "gpu_total_errors": gpu_row.get("total_errors"),
                    "cpu_throughput_runs_per_minute": cpu_row.get("throughput_runs_per_minute"),
                    "gpu_throughput_runs_per_minute": gpu_row.get("throughput_runs_per_minute"),
                    "cpu_stability_verdict": cpu_row.get("stability_verdict"),
                    "gpu_stability_verdict": gpu_row.get("stability_verdict"),
                    "interpretation": _cpu_gpu_interpretation(cpu_row, gpu_row),
                }
            )
    return {
        "rows": rows,
        "summary": "GPU and CPU profiles are compared only for matching pair/concurrency rows.",
    }


def build_capacity_estimates(
    summary_rows: list[dict[str, Any]], metrics_rows: list[dict[str, Any]]
) -> list[dict[str, Any]]:
    metrics_by_pair_profile: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for row in metrics_rows:
        metrics_by_pair_profile.setdefault((str(row.get("pair")), str(row.get("profile_id"))), []).append(row)

    estimates = []
    for row in summary_rows:
        key = (str(row.get("pair")), str(row.get("profile_id")))
        metrics = metrics_by_pair_profile.get(key) or []
        stable_metrics = [item for item in metrics if item.get("stability_verdict") == "stable"]
        estimates.append(
            {
                "pair": row.get("pair"),
                "profile_id": row.get("profile_id"),
                "max_stable_concurrency_observed": row.get("max_stable_concurrency_observed"),
                "max_nonfailed_concurrency_observed": row.get("max_nonfailed_concurrency_observed"),
                "best_stable_throughput_runs_per_minute": _safe_max(
                    [_number(item.get("throughput_runs_per_minute")) for item in stable_metrics]
                ),
                "best_stable_throughput_group_steps_per_minute": _safe_max(
                    [_number(item.get("throughput_group_steps_per_minute")) for item in stable_metrics]
                ),
                "bottleneck": row.get("bottleneck"),
                "confidence": "medium" if stable_metrics else "low",
                "notes": [
                    "Estimate is based on observed bounded stress levels only.",
                    "Do not extrapolate beyond the maximum tested concurrency.",
                ],
            }
        )
    return estimates


def build_runtime_profile_validation(
    profiles: list[RuntimeProfile],
    metrics_rows: list[dict[str, Any]],
    gpu_before: dict[str, Any],
    gpu_after: dict[str, Any],
) -> dict[str, Any]:
    rows = []
    for profile in profiles:
        profile_rows = [row for row in metrics_rows if row.get("profile_id") == profile.profile_id]
        peak_gpu_util = _safe_max([_number(row.get("peak_gpu_utilization_percent")) for row in profile_rows])
        peak_vram = _safe_max([_number(row.get("peak_vram_mb")) for row in profile_rows])
        uses_cpu_only = bool(profile.server_params.get("cpu_only"))
        uses_gpu_offload = bool(
            profile.server_params.get("gpu_layers")
            or profile.server_params.get("orchestrator_gpu_layers")
            or profile.server_params.get("executor_gpu_layers")
        )
        strict_cpu_truly_strict = None
        if uses_cpu_only:
            strict_cpu_truly_strict = bool(peak_gpu_util is None or peak_gpu_util <= 5.0)
        rows.append(
            {
                "profile_id": profile.profile_id,
                "description": profile.description,
                "server_params": profile.server_params,
                "expected_gpu_usage": profile.expected_gpu_usage,
                "confidence": profile.confidence,
                "uses_cpu_only_flag": uses_cpu_only,
                "uses_explicit_gpu_offload": uses_gpu_offload,
                "strict_cpu_truly_strict": strict_cpu_truly_strict,
                "peak_gpu_utilization_percent_observed": peak_gpu_util,
                "peak_vram_mb_observed": peak_vram,
                "limitations": profile.limitations,
            }
        )
    return {
        "gpu_before": gpu_before,
        "gpu_after": gpu_after,
        "profiles": rows,
        "note": (
            "strict_cpu_truly_strict is based on device-level telemetry and may be false "
            "if unrelated GPU work was active during sampling."
        ),
    }


def write_stress_probe_outputs(result: dict[str, Any], out_root: Path, config: StressProbeConfig) -> None:
    batches = result["batches"]
    metrics = result["stress_batch_metrics"]
    summary = result["stress_summary_by_pair_profile"]
    tradeoff = result["stress_quality_latency_tradeoff"]
    comparison = result["gpu_vs_cpu_stress_comparison"]
    capacity = result["capacity_stress_estimates"]
    validation = result["runtime_profile_validation"]

    _write_json(out_root / "stress_probe_index.json", batches)
    _write_csv(_index_rows(batches), out_root / "stress_probe_index.csv", _INDEX_FIELDS)
    _write_json(out_root / "stress_batch_metrics.json", metrics)
    _write_csv(metrics, out_root / "stress_batch_metrics.csv", _BATCH_METRIC_FIELDS)
    _write_json(out_root / "stress_summary_by_pair_profile.json", summary)
    _write_csv(summary, out_root / "stress_summary_by_pair_profile.csv", _SUMMARY_FIELDS)
    _write_json(out_root / "stress_quality_latency_tradeoff.json", tradeoff)
    (out_root / "stress_quality_latency_tradeoff.md").write_text(
        _quality_latency_markdown(tradeoff),
        encoding="utf-8",
    )
    _write_json(out_root / "runtime_profile_validation.json", validation)
    _write_json(out_root / "gpu_vs_cpu_stress_comparison.json", comparison)
    (out_root / "gpu_vs_cpu_stress_comparison.md").write_text(
        _gpu_vs_cpu_markdown(comparison),
        encoding="utf-8",
    )
    _write_json(out_root / "capacity_stress_estimates.json", capacity)
    _write_csv(capacity, out_root / "capacity_stress_estimates.csv", _CAPACITY_FIELDS)
    (out_root / "README.md").write_text(_root_readme(result), encoding="utf-8")
    (out_root / "replay_commands.ps1").write_text(_replay_command(config) + "\n", encoding="utf-8")
    batches_dir = out_root / "batches"
    batches_dir.mkdir(exist_ok=True)
    (batches_dir / "README.md").write_text(_batches_readme(batches), encoding="utf-8")


def _run_stress_batch(
    *,
    config: StressProbeConfig,
    out_root: Path,
    pair: PairSpec,
    profile: RuntimeProfile,
    concurrency_level: int,
) -> dict[str, Any]:
    batch_id = f"{pair.pair_id}__{profile.profile_id}__concurrency_{concurrency_level}"
    batch_dir = out_root / pair.pair_id / profile.profile_id / f"concurrency_{concurrency_level}"
    batch_dir.mkdir(parents=True, exist_ok=True)
    planned_runs = max(config.runs_per_level, concurrency_level)
    servers: list[ManagedServer] = []
    sampler: StressSampler | None = None
    samples: list[dict[str, Any]] = []
    server_error: str | None = None
    run_records: list[dict[str, Any]] = []
    started_at = time.perf_counter()

    try:
        if config.mode == "local":
            runtime_config = _runtime_config_for_profile(config, profile, pair)
            servers = _start_managed_servers(runtime_config, pair)
            sampler = StressSampler(
                pids=sorted({pid for server in servers for pid in server.llama_pids}),
                endpoints={server.role: server.port for server in servers},
                interval_seconds=config.sample_interval_seconds,
            )
            sampler.start()
        run_records = _run_group_runs(
            config=config,
            batch_dir=batch_dir,
            batch_id=batch_id,
            pair=pair,
            concurrency_level=concurrency_level,
            planned_runs=planned_runs,
        )
    except Exception as exc:
        server_error = str(exc) or exc.__class__.__name__
    finally:
        if sampler is not None:
            sampler.stop()
            samples = sampler.samples
        if servers:
            _stop_managed_servers(servers)

    batch_wall = _elapsed_ms(started_at)
    metrics = aggregate_batch_metrics(
        pair=pair,
        profile=profile,
        concurrency_level=concurrency_level,
        planned_runs=planned_runs,
        run_records=run_records,
        samples=samples,
        server_error=server_error,
        batch_wall_time_ms=batch_wall,
        max_group_steps=config.max_group_steps,
    )
    status: StressStatus
    if server_error:
        status = "blocked"
    elif metrics["runs_failed"]:
        status = "completed_with_failures"
    else:
        status = "completed"

    server_run = _server_run_payload(config, pair, profile, servers, server_error)
    summary = {
        "batch_id": batch_id,
        "status": status,
        "pair": pair.label,
        "pair_id": pair.pair_id,
        "profile_id": profile.profile_id,
        "concurrency_level": concurrency_level,
        "artifact_path": str(batch_dir),
        "planned_runs": planned_runs,
        "server_strategy": _server_strategy(pair, config.mode),
        "server_flags_used": _server_flags_used(servers),
        "server_run": server_run,
        "metrics": metrics,
    }

    _write_json(batch_dir / "server_run.json", server_run)
    _write_jsonl(batch_dir / "telemetry_samples.jsonl", samples)
    _write_json(batch_dir / "run_index.json", run_records)
    _write_json(batch_dir / "batch_summary.json", summary)
    (batch_dir / "README.md").write_text(_batch_readme(summary), encoding="utf-8")
    _write_json(out_root / "batches" / f"{batch_id}.json", summary)
    return summary


def _run_group_runs(
    *,
    config: StressProbeConfig,
    batch_dir: Path,
    batch_id: str,
    pair: PairSpec,
    concurrency_level: int,
    planned_runs: int,
) -> list[dict[str, Any]]:
    if config.mode == "local":
        return _run_group_runs_subprocess(
            config=config,
            batch_dir=batch_dir,
            batch_id=batch_id,
            pair=pair,
            concurrency_level=concurrency_level,
            planned_runs=planned_runs,
        )

    executor = ThreadPoolExecutor(max_workers=concurrency_level, thread_name_prefix="stress-group-run")
    futures: dict[Future[dict[str, Any]], int] = {}
    try:
        for run_number in range(1, planned_runs + 1):
            futures[
                executor.submit(
                    _run_single_group_run,
                    config=config,
                    batch_dir=batch_dir,
                    batch_id=batch_id,
                    pair=pair,
                    run_number=run_number,
                )
            ] = run_number
        timeout_batches = math.ceil(planned_runs / max(1, concurrency_level))
        batch_timeout_seconds = config.timeout_seconds * timeout_batches
        done, not_done = wait(futures, timeout=batch_timeout_seconds)
        records: list[dict[str, Any]] = []
        for future in done:
            run_number = futures[future]
            try:
                records.append(future.result())
            except Exception as exc:
                records.append(_failed_run_record(batch_dir, batch_id, run_number, exc))
        for future in not_done:
            run_number = futures[future]
            future.cancel()
            records.append(_timeout_run_record(batch_dir, batch_id, run_number, config.timeout_seconds))
        records.sort(key=lambda row: int(row.get("run_number") or 0))
        return records
    finally:
        executor.shutdown(wait=False, cancel_futures=True)


def _run_group_runs_subprocess(
    *,
    config: StressProbeConfig,
    batch_dir: Path,
    batch_id: str,
    pair: PairSpec,
    concurrency_level: int,
    planned_runs: int,
) -> list[dict[str, Any]]:
    pending = list(range(1, planned_runs + 1))
    running: dict[int, dict[str, Any]] = {}
    records: list[dict[str, Any]] = []

    while pending or running:
        while pending and len(running) < concurrency_level:
            run_number = pending.pop(0)
            running[run_number] = _start_group_run_subprocess(
                config=config,
                batch_dir=batch_dir,
                batch_id=batch_id,
                pair=pair,
                run_number=run_number,
            )

        for run_number, state in list(running.items()):
            proc: subprocess.Popen[str] = state["process"]
            elapsed = time.perf_counter() - float(state["started_at"])
            if proc.poll() is not None:
                records.append(_subprocess_run_record(state))
                del running[run_number]
                continue
            if elapsed > config.timeout_seconds:
                records.append(_timeout_subprocess_run_record(state, config.timeout_seconds))
                del running[run_number]

        if pending or running:
            time.sleep(0.2)

    records.sort(key=lambda row: int(row.get("run_number") or 0))
    return records


def _start_group_run_subprocess(
    *,
    config: StressProbeConfig,
    batch_dir: Path,
    batch_id: str,
    pair: PairSpec,
    run_number: int,
) -> dict[str, Any]:
    run_id = f"{batch_id}__run_{run_number:03d}"
    group_root = batch_dir / "group_runs" / f"run_{run_number:03d}"
    group_root.mkdir(parents=True, exist_ok=True)
    command = [
        sys.executable,
        "scripts\\run_repeated_orchestrator_executor_trials.py",
        "--mode",
        config.mode,
        "--models-config",
        config.models_config_path,
        "--scenario",
        config.scenario_path,
        "--out-root",
        str(group_root.relative_to(config.project_root)),
        "--label",
        run_id,
        "--trials",
        "1",
        "--orchestrator-model-id",
        pair.orchestrator_model_id,
        "--executor-model-id",
        pair.executor_model_id,
        "--orchestrator-base-url",
        _base_url(config.base_port),
        "--executor-base-url",
        _base_url(config.base_port + 1),
        "--no-manage-servers",
        "--max-group-steps",
        str(config.max_group_steps),
        "--max-steps-per-agent",
        str(config.max_steps_per_agent),
        "--orchestrator-max-tokens",
        str(config.orchestrator_max_tokens),
        "--orchestrator-repair-attempts",
        str(config.orchestrator_repair_attempts),
        "--repair-attempts",
        str(config.repair_attempts),
        "--continue-on-trial-failure",
        "--force",
    ]
    command.append("--execute-actions" if config.execute_actions else "--no-execute-actions")
    proc = subprocess.Popen(
        command,
        cwd=config.project_root,
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
    )
    return {
        "run_number": run_number,
        "run_id": run_id,
        "group_root": group_root,
        "started_at": time.perf_counter(),
        "process": proc,
        "command": command,
    }


def _subprocess_run_record(state: dict[str, Any]) -> dict[str, Any]:
    proc: subprocess.Popen[str] = state["process"]
    stdout, stderr = proc.communicate(timeout=5)
    group_root: Path = state["group_root"]
    (group_root / "subprocess_stdout.txt").write_text(stdout or "", encoding="utf-8")
    (group_root / "subprocess_stderr.txt").write_text(stderr or "", encoding="utf-8")
    result_path = group_root / "repeated_group_trials_result.json"
    if not result_path.exists():
        return _failed_subprocess_record(state, "MissingResult", "repeated_group_trials_result.json was not created")
    payload = json.loads(result_path.read_text(encoding="utf-8"))
    aggregate = payload.get("aggregate") or {}
    failed = _int(aggregate.get("failed_trial_count"))
    status = "failed" if failed or proc.returncode not in (0, None) else "completed"
    return {
        "run_number": state["run_number"],
        "run_id": state["run_id"],
        "status": status,
        "artifact_path": str(group_root),
        "wall_time_ms_probe": _elapsed_ms(float(state["started_at"])),
        "return_code": proc.returncode,
        "aggregate": aggregate,
        "trial_index": payload.get("trial_index") or [],
        "failure_modes": payload.get("failure_modes") or aggregate.get("common_failure_modes") or {},
    }


def _timeout_subprocess_run_record(state: dict[str, Any], timeout_seconds: float) -> dict[str, Any]:
    proc: subprocess.Popen[str] = state["process"]
    proc.kill()
    stdout, stderr = proc.communicate(timeout=10)
    group_root: Path = state["group_root"]
    (group_root / "subprocess_stdout.txt").write_text(stdout or "", encoding="utf-8")
    (group_root / "subprocess_stderr.txt").write_text(stderr or "", encoding="utf-8")
    payload = {
        "run_number": state["run_number"],
        "run_id": state["run_id"],
        "status": "timeout",
        "artifact_path": str(group_root),
        "timeout_seconds": timeout_seconds,
        "wall_time_ms_probe": _elapsed_ms(float(state["started_at"])),
        "error_type": "TimeoutError",
        "error_message": f"Group run did not finish within {timeout_seconds} seconds.",
        "command": state["command"],
    }
    _write_json(group_root / "timeout_error.json", payload)
    return payload


def _failed_subprocess_record(state: dict[str, Any], error_type: str, error_message: str) -> dict[str, Any]:
    group_root: Path = state["group_root"]
    payload = {
        "run_number": state["run_number"],
        "run_id": state["run_id"],
        "status": "failed",
        "artifact_path": str(group_root),
        "wall_time_ms_probe": _elapsed_ms(float(state["started_at"])),
        "return_code": state["process"].returncode,
        "error_type": error_type,
        "error_message": error_message,
        "command": state["command"],
    }
    _write_json(group_root / "run_error.json", payload)
    return payload


def _run_single_group_run(
    *,
    config: StressProbeConfig,
    batch_dir: Path,
    batch_id: str,
    pair: PairSpec,
    run_number: int,
) -> dict[str, Any]:
    started = time.perf_counter()
    run_id = f"{batch_id}__run_{run_number:03d}"
    group_root = batch_dir / "group_runs" / f"run_{run_number:03d}"
    try:
        result = run_repeated_group_trials(
            RepeatedGroupRunConfig(
                project_root=config.project_root,
                mode=config.mode,
                models_config_path=config.models_config_path,
                scenario_path=config.scenario_path,
                out_root=str(group_root.relative_to(config.project_root)),
                label=run_id,
                trials=1,
                orchestrator_model_id=pair.orchestrator_model_id,
                executor_model_id=pair.executor_model_id,
                orchestrator_base_url=_base_url(config.base_port) if config.mode == "local" else None,
                executor_base_url=_base_url(config.base_port + 1) if config.mode == "local" else None,
                orchestrator_max_tokens=config.orchestrator_max_tokens,
                orchestrator_repair_attempts=config.orchestrator_repair_attempts,
                max_group_steps=config.max_group_steps,
                max_steps_per_agent=config.max_steps_per_agent,
                repair_attempts=config.repair_attempts,
                execute_actions=config.execute_actions,
                continue_on_trial_failure=True,
                force=True,
            )
        )
        aggregate = result.aggregate.model_dump(mode="json")
        failed = aggregate.get("failed_trial_count") or 0
        return {
            "run_number": run_number,
            "run_id": run_id,
            "status": "failed" if failed else "completed",
            "artifact_path": str(group_root),
            "wall_time_ms_probe": _elapsed_ms(started),
            "aggregate": aggregate,
            "trial_index": result.trial_index,
            "failure_modes": result.failure_modes,
        }
    except Exception as exc:
        return _failed_run_record(group_root, batch_id, run_number, exc, started=started)


def _failed_run_record(
    artifact_root: Path,
    batch_id: str,
    run_number: int,
    exc: Exception,
    *,
    started: float | None = None,
) -> dict[str, Any]:
    artifact_root.mkdir(parents=True, exist_ok=True)
    run_id = f"{batch_id}__run_{run_number:03d}"
    payload = {
        "run_number": run_number,
        "run_id": run_id,
        "status": "failed",
        "artifact_path": str(artifact_root),
        "wall_time_ms_probe": _elapsed_ms(started) if started is not None else None,
        "error_type": exc.__class__.__name__,
        "error_message": str(exc) or exc.__class__.__name__,
    }
    _write_json(artifact_root / "run_error.json", payload)
    (artifact_root / "README.md").write_text(
        f"# Failed Stress Group Run\n\nRun id: `{run_id}`\n\nError: `{payload['error_message']}`\n",
        encoding="utf-8",
    )
    return payload


def _timeout_run_record(
    batch_dir: Path, batch_id: str, run_number: int, timeout_seconds: float
) -> dict[str, Any]:
    artifact_root = batch_dir / "group_runs" / f"run_{run_number:03d}"
    artifact_root.mkdir(parents=True, exist_ok=True)
    run_id = f"{batch_id}__run_{run_number:03d}"
    payload = {
        "run_number": run_number,
        "run_id": run_id,
        "status": "timeout",
        "artifact_path": str(artifact_root),
        "timeout_seconds": timeout_seconds,
        "error_type": "TimeoutError",
        "error_message": f"Group run did not finish within {timeout_seconds} seconds.",
    }
    _write_json(artifact_root / "timeout_error.json", payload)
    (artifact_root / "README.md").write_text(
        f"# Timed Out Stress Group Run\n\nRun id: `{run_id}`\n\nTimeout: `{timeout_seconds}` seconds\n",
        encoding="utf-8",
    )
    return payload


def _runtime_config_for_profile(
    config: StressProbeConfig,
    profile: RuntimeProfile,
    pair: PairSpec,
) -> RuntimeProbeConfig:
    params = profile.server_params
    gpu_layers = params.get("gpu_layers")
    main_gpu = params.get("main_gpu")
    return RuntimeProbeConfig(
        project_root=config.project_root,
        mode=config.mode,
        models_config_path=config.models_config_path,
        out_root=config.out_root,
        label=config.label,
        pairs=[pair],
        scenarios=[],
        trials=1,
        base_orchestrator_port=config.base_port,
        base_executor_port=config.base_port + 1,
        manage_servers=True,
        max_steps_per_agent=config.max_steps_per_agent,
        orchestrator_repair_attempts=config.orchestrator_repair_attempts,
        repair_attempts=config.repair_attempts,
        execute_actions=config.execute_actions,
        sample_interval_seconds=config.sample_interval_seconds,
        continue_on_pair_failure=True,
        force=False,
        orchestrator_gpu_layers=_param(params, "orchestrator_gpu_layers", gpu_layers),
        executor_gpu_layers=_param(params, "executor_gpu_layers", gpu_layers),
        orchestrator_main_gpu=_param(params, "orchestrator_main_gpu", main_gpu),
        executor_main_gpu=_param(params, "executor_main_gpu", main_gpu),
        split_mode=params.get("split_mode"),
        tensor_split=params.get("tensor_split"),
        threads=params.get("threads"),
        ctx_size=params.get("ctx_size"),
        batch_size=params.get("batch_size"),
        ubatch_size=params.get("ubatch_size"),
        flash_attention=params.get("flash_attention"),
        cpu_only=bool(params.get("cpu_only")),
    )


def _protocol_payload(config: StressProbeConfig) -> dict[str, Any]:
    return {
        "pairs": [pair.label for pair in config.pairs],
        "profiles": config.profile_ids,
        "concurrency_levels": config.concurrency_levels,
        "skipped_concurrency_levels": config.skipped_concurrency_levels,
        "skip_reason": config.skip_reason,
        "runs_per_level": config.runs_per_level,
        "actual_runs_per_level_rule": "max(runs_per_level, concurrency_level)",
        "base_port": config.base_port,
        "max_group_steps": config.max_group_steps,
        "max_steps_per_agent": config.max_steps_per_agent,
        "orchestrator_max_tokens": config.orchestrator_max_tokens,
        "orchestrator_repair_attempts": config.orchestrator_repair_attempts,
        "repair_attempts": config.repair_attempts,
        "execute_actions": config.execute_actions,
        "timeout_seconds": config.timeout_seconds,
        "sample_interval_seconds": config.sample_interval_seconds,
        "continue_on_failure": config.continue_on_failure,
        "server_strategy": "two separate llama-server endpoints per pair, including same-model pairs",
    }


def _server_run_payload(
    config: StressProbeConfig,
    pair: PairSpec,
    profile: RuntimeProfile,
    servers: list[ManagedServer],
    server_error: str | None,
) -> dict[str, Any]:
    return {
        "server_error": server_error,
        "server_strategy": _server_strategy(pair, config.mode),
        "profile_id": profile.profile_id,
        "profile_server_params": profile.server_params,
        "ports": {
            "orchestrator": config.base_port,
            "executor": config.base_port + 1,
        },
        "servers": [_server_payload(server) for server in servers],
    }


def _server_strategy(pair: PairSpec, mode: str) -> str:
    if mode == "fake":
        return "fake mode; no servers started"
    if pair.orchestrator_model_id == pair.executor_model_id:
        return "two separate llama-server endpoints for the same model on different ports"
    return "two separate llama-server endpoints on different ports"


def _endpoint_sample(endpoints: dict[str, int]) -> dict[str, dict[str, Any]]:
    return {
        role: {"port": port, "healthy": _endpoint_json(port) is not None}
        for role, port in endpoints.items()
    }


def _endpoint_error_count(
    failure_modes: Counter[str],
    server_error: str | None,
    samples: list[dict[str, Any]],
) -> int:
    count = 1 if server_error else 0
    for key, value in failure_modes.items():
        lowered = key.lower()
        if "http" in lowered or "endpoint" in lowered or "connection" in lowered or "urlerror" in lowered:
            count += int(value)
    count += sum(_int((sample.get("endpoints") or {}).get("endpoint_error_count")) for sample in samples)
    return count


def _stability_verdict(
    *,
    runs_started: int,
    runs_completed: int,
    runs_failed: int,
    timeout_count: int,
    endpoint_error_count: int,
    server_error: str | None,
) -> str:
    if server_error or runs_started == 0:
        return "failed"
    if runs_completed == 0:
        return "failed"
    if timeout_count or endpoint_error_count or runs_failed >= max(1, math.ceil(runs_started / 2)):
        return "unstable"
    if runs_failed:
        return "degraded"
    return "stable"


def _count_failure_modes(failure_modes: Counter[str], needle: str) -> int:
    return sum(count for key, count in failure_modes.items() if needle in key.lower())


def _row_for_level(rows: list[dict[str, Any]], level: int) -> dict[str, Any] | None:
    return next((row for row in rows if row.get("concurrency_level") == level), None)


def _max_level_with_verdict(rows: list[dict[str, Any]], accepted: set[str]) -> int | None:
    levels = [
        _int(row.get("concurrency_level"))
        for row in rows
        if str(row.get("stability_verdict")) in accepted
    ]
    return max(levels) if levels else None


def _quality_degradation(
    baseline: dict[str, Any] | None, current: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not baseline or not current:
        return None
    base = _number(baseline.get("mean_pair_quality_score"))
    value = _number(current.get("mean_pair_quality_score"))
    if base is None or value is None:
        return None
    return {"absolute": round(base - value, 6), "relative": round((base - value) / base, 6) if base else None}


def _latency_degradation(
    baseline: dict[str, Any] | None, current: dict[str, Any] | None
) -> dict[str, Any] | None:
    if not baseline or not current:
        return None
    base = _number(baseline.get("mean_wall_time_ms"))
    value = _number(current.get("mean_wall_time_ms"))
    if base is None or value is None:
        return None
    return {"ratio": round(value / base, 6) if base else None, "delta_ms": round(value - base, 6)}


def _infer_bottleneck(rows: list[dict[str, Any]]) -> str:
    if any(row.get("stability_verdict") in {"unstable", "failed"} and row.get("endpoint_error_count") for row in rows):
        return "endpoint/server"
    if _safe_max([_number(row.get("peak_cpu_percent_total")) for row in rows]) and (
        _safe_max([_number(row.get("peak_cpu_percent_total")) for row in rows]) or 0
    ) >= 80.0:
        return "CPU"
    gpu_peak = _safe_max([_number(row.get("peak_gpu_utilization_percent")) for row in rows]) or 0.0
    if gpu_peak >= 85.0:
        return "GPU"
    total_vram = _safe_max([_number(row.get("gpu_total_vram_mb")) for row in rows]) or 0.0
    peak_vram = _safe_max([_number(row.get("peak_vram_mb")) for row in rows]) or 0.0
    if total_vram > 0 and peak_vram / total_vram >= 0.90:
        return "VRAM"
    if any((_int(row.get("total_errors")) > 0 or row.get("stability_verdict") == "degraded") for row in rows):
        return "model-output quality"
    return "unknown"


def _cpu_gpu_interpretation(cpu_row: dict[str, Any], gpu_row: dict[str, Any]) -> str:
    cpu_wall = _number(cpu_row.get("mean_wall_time_ms"))
    gpu_wall = _number(gpu_row.get("mean_wall_time_ms"))
    if gpu_row.get("stability_verdict") in {"failed", "unstable"}:
        return "GPU profile was not stable for this row."
    if cpu_wall and gpu_wall and gpu_wall > 0:
        speedup = cpu_wall / gpu_wall
        if speedup > 1.05:
            return "GPU profile was faster in wall time for this bounded row."
        if speedup < 0.95:
            return "GPU profile was slower in wall time for this bounded row."
    return "CPU and GPU wall time were roughly comparable for this bounded row."


def _ports_health(base_port: int, count: int) -> dict[str, Any]:
    rows = []
    for port in range(base_port, base_port + count):
        rows.append({"port": port, "endpoint_active": _endpoint_json(port) is not None})
    return {
        "checked_ports": rows,
        "all_checked_ports_stopped": not any(row["endpoint_active"] for row in rows),
        "active_llama_server_pids": _llama_server_pids(PROJECT_ROOT),
    }


def _prepare_output_root(out_root: Path, *, force: bool) -> Path:
    if out_root.exists():
        if not force:
            raise FileExistsError(f"Stress probe output root already exists: {out_root}")
        resolved = out_root.resolve()
        try:
            resolved.relative_to(PROJECT_ROOT.resolve())
        except ValueError as exc:
            raise RuntimeError(f"Refusing to remove output outside project root: {resolved}") from exc
        if resolved == PROJECT_ROOT.resolve():
            raise RuntimeError("Refusing to remove project root.")
        shutil.rmtree(resolved)
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "batches").mkdir(exist_ok=True)
    return out_root


def _validate_config(config: StressProbeConfig) -> None:
    if config.runs_per_level < 1:
        raise ValueError("runs_per_level must be >= 1.")
    if not config.pairs:
        raise ValueError("At least one pair is required.")
    if not config.profile_ids:
        raise ValueError("At least one runtime profile is required.")
    if not config.concurrency_levels:
        raise ValueError("At least one concurrency level is required.")
    for level in config.concurrency_levels:
        if level < 1:
            raise ValueError("Concurrency levels must be >= 1.")
        if level > 4:
            raise ValueError("Refusing to run concurrency level > 4.")
    if config.timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be > 0.")


def _index_rows(batches: list[dict[str, Any]]) -> list[dict[str, Any]]:
    return [
        {
            "batch_id": batch.get("batch_id"),
            "status": batch.get("status"),
            "pair": batch.get("pair"),
            "profile_id": batch.get("profile_id"),
            "concurrency_level": batch.get("concurrency_level"),
            "artifact_path": batch.get("artifact_path"),
            "stability_verdict": (batch.get("metrics") or {}).get("stability_verdict"),
            "server_error": (batch.get("metrics") or {}).get("server_error"),
        }
        for batch in batches
    ]


def _quality_latency_markdown(tradeoff: dict[str, Any]) -> str:
    lines = [
        "# Stress Quality/Latency Tradeoff",
        "",
        "| pair | profile | concurrency | quality | wall_time_ms | errors | throughput_runs_per_minute | verdict | score |",
        "|---|---|---:|---:|---:|---:|---:|---|---:|",
    ]
    for row in tradeoff.get("rankings") or []:
        lines.append(
            f"| `{row.get('pair')}` | `{row.get('profile_id')}` | {row.get('concurrency_level')} | "
            f"{row.get('mean_pair_quality_score')} | {row.get('mean_wall_time_ms')} | "
            f"{row.get('total_errors')} | {row.get('throughput_runs_per_minute')} | "
            f"`{row.get('stability_verdict')}` | {row.get('quality_latency_score')} |"
        )
    lines.append("")
    lines.append(f"Recommendation status: `{tradeoff.get('recommendation_status')}`.")
    return "\n".join(lines) + "\n"


def _gpu_vs_cpu_markdown(comparison: dict[str, Any]) -> str:
    lines = [
        "# GPU vs CPU Stress Comparison",
        "",
        "| pair | concurrency | CPU profile | GPU profile | CPU wall ms | GPU wall ms | speedup | CPU verdict | GPU verdict | interpretation |",
        "|---|---:|---|---|---:|---:|---:|---|---|---|",
    ]
    for row in comparison.get("rows") or []:
        lines.append(
            f"| `{row.get('pair')}` | {row.get('concurrency_level')} | `{row.get('cpu_profile_id')}` | "
            f"`{row.get('gpu_profile_id')}` | {row.get('cpu_mean_wall_time_ms')} | "
            f"{row.get('gpu_mean_wall_time_ms')} | {row.get('speedup_wall_time_ratio')} | "
            f"`{row.get('cpu_stability_verdict')}` | `{row.get('gpu_stability_verdict')}` | "
            f"{row.get('interpretation')} |"
        )
    return "\n".join(lines) + "\n"


def _root_readme(result: dict[str, Any]) -> str:
    return "\n".join(
        [
            "# Bounded Stress Candidate Pairs v1",
            "",
            f"- probe_id: `{result.get('probe_id')}`",
            f"- mode: `{result.get('mode')}`",
            f"- scenario: `{result.get('scenario_path')}`",
            "- server strategy: two separate local endpoints per pair, including same-model pairs.",
            "- bounded smoke only; not a production recommendation.",
            f"- skipped_concurrency_levels: `{result.get('skipped_concurrency_levels')}`",
            f"- skip_reason: `{result.get('skip_reason')}`",
            "",
            "Primary files:",
            "",
            "- `stress_probe_index.json` / `.csv`",
            "- `stress_batch_metrics.json` / `.csv`",
            "- `stress_summary_by_pair_profile.json` / `.csv`",
            "- `runtime_profile_validation.json`",
            "- `gpu_vs_cpu_stress_comparison.md`",
            "- `capacity_stress_estimates.json` / `.csv`",
            "",
        ]
    )


def _batches_readme(batches: list[dict[str, Any]]) -> str:
    lines = ["# Stress Batches", ""]
    for batch in batches:
        lines.append(
            f"- `{batch.get('batch_id')}`: `{batch.get('status')}`, "
            f"verdict `{(batch.get('metrics') or {}).get('stability_verdict')}`"
        )
    return "\n".join(lines) + "\n"


def _batch_readme(summary: dict[str, Any]) -> str:
    metrics = summary.get("metrics") or {}
    return "\n".join(
        [
            f"# Stress Batch {summary.get('batch_id')}",
            "",
            f"- pair: `{summary.get('pair')}`",
            f"- profile: `{summary.get('profile_id')}`",
            f"- concurrency_level: `{summary.get('concurrency_level')}`",
            f"- status: `{summary.get('status')}`",
            f"- stability_verdict: `{metrics.get('stability_verdict')}`",
            f"- runs_completed: `{metrics.get('runs_completed')}`",
            f"- runs_failed: `{metrics.get('runs_failed')}`",
            "",
            "Files:",
            "",
            "- `server_run.json`",
            "- `telemetry_samples.jsonl`",
            "- `run_index.json`",
            "- `batch_summary.json`",
            "- `group_runs/`",
            "",
        ]
    )


def _replay_command(config: StressProbeConfig) -> str:
    pairs = ",".join(f"{pair.orchestrator_model_id}:{pair.executor_model_id}" for pair in config.pairs)
    profiles = ",".join(config.profile_ids)
    levels = ",".join(str(level) for level in config.concurrency_levels)
    action_flag = "--execute-actions" if config.execute_actions else "--no-execute-actions"
    continue_flag = " --continue-on-failure" if config.continue_on_failure else ""
    force_flag = " --force" if config.force else ""
    command = (
        ".\\.venv\\Scripts\\python.exe scripts\\run_orchestrator_executor_stress_probe.py "
        f"--models-config {config.models_config_path} "
        f"--runtime-profiles-config {config.runtime_profiles_config_path} "
        f"--scenario {config.scenario_path} "
        f"--out-root {config.out_root} "
        f"--label {config.label} "
        f"--pairs {pairs} "
        f"--profiles {profiles} "
        f"--concurrency-levels {levels} "
        f"--runs-per-level {config.runs_per_level} "
        f"--base-port {config.base_port} "
        f"--max-group-steps {config.max_group_steps} "
        f"--max-steps-per-agent {config.max_steps_per_agent} "
        f"--orchestrator-max-tokens {config.orchestrator_max_tokens} "
        f"--orchestrator-repair-attempts {config.orchestrator_repair_attempts} "
        f"--repair-attempts {config.repair_attempts} "
        f"{action_flag} "
        f"--timeout-seconds {config.timeout_seconds} "
        f"--sample-interval-seconds {config.sample_interval_seconds}"
        f"{continue_flag}{force_flag}"
    )
    if config.skipped_concurrency_levels:
        command += " --skipped-concurrency-levels " + ",".join(
            str(level) for level in config.skipped_concurrency_levels
        )
    if config.skip_reason:
        command += f" --skip-reason \"{config.skip_reason}\""
    return command


def _write_json(path: Path, payload: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows),
        encoding="utf-8",
    )


def _write_csv(rows: list[dict[str, Any]], path: Path, fieldnames: list[str]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        for row in rows:
            clean = {
                key: json.dumps(value, ensure_ascii=False, sort_keys=True)
                if isinstance(value, (dict, list))
                else value
                for key, value in row.items()
            }
            writer.writerow(clean)


def _param(params: dict[str, Any], key: str, fallback: Any) -> Any:
    return params[key] if key in params else fallback


def _elapsed_ms(start: float) -> float:
    return round((time.perf_counter() - start) * 1000.0, 6)


def _mb(value: float) -> float:
    return round(float(value) / 1024.0 / 1024.0, 6)


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return None


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return 0


def _safe_mean(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 6)


def _safe_max(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return round(max(clean), 6) if clean else None


def _percentile(values: list[float | None], percentile: int) -> float | None:
    clean = sorted(value for value in values if value is not None)
    if not clean:
        return None
    if len(clean) == 1:
        return round(clean[0], 6)
    rank = math.ceil((percentile / 100.0) * len(clean)) - 1
    rank = min(max(rank, 0), len(clean) - 1)
    return round(clean[rank], 6)


_INDEX_FIELDS = [
    "batch_id",
    "status",
    "pair",
    "profile_id",
    "concurrency_level",
    "artifact_path",
    "stability_verdict",
    "server_error",
]

_BATCH_METRIC_FIELDS = [
    "profile_id",
    "pair",
    "pair_id",
    "concurrency_level",
    "planned_runs",
    "runs_started",
    "runs_completed",
    "runs_failed",
    "timeout_count",
    "mean_wall_time_ms",
    "p95_wall_time_ms",
    "mean_pair_quality_score",
    "mean_execution_success_rate",
    "total_errors",
    "errors_per_run",
    "validation_failure_count",
    "repair_failure_count",
    "endpoint_error_count",
    "peak_ram_mb_total",
    "peak_ram_mb_per_server",
    "peak_cpu_percent_total",
    "peak_vram_mb",
    "mean_vram_mb",
    "peak_gpu_utilization_percent",
    "mean_gpu_utilization_percent",
    "gpu_telemetry_available",
    "gpu_name",
    "gpu_total_vram_mb",
    "throughput_runs_per_minute",
    "throughput_group_steps_per_minute",
    "batch_wall_time_ms",
    "sample_count",
    "server_error",
    "common_failure_modes",
    "stability_verdict",
]

_SUMMARY_FIELDS = [
    "pair",
    "profile_id",
    "levels_observed",
    "max_stable_concurrency_observed",
    "max_nonfailed_concurrency_observed",
    "quality_degradation_at_concurrency_2",
    "latency_degradation_at_concurrency_2",
    "quality_degradation_at_concurrency_4",
    "latency_degradation_at_concurrency_4",
    "bottleneck",
    "mean_quality_across_levels",
    "max_peak_ram_mb_total",
    "max_peak_vram_mb",
    "max_peak_gpu_utilization_percent",
    "verdicts",
]

_CAPACITY_FIELDS = [
    "pair",
    "profile_id",
    "max_stable_concurrency_observed",
    "max_nonfailed_concurrency_observed",
    "best_stable_throughput_runs_per_minute",
    "best_stable_throughput_group_steps_per_minute",
    "bottleneck",
    "confidence",
    "notes",
]
