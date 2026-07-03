from __future__ import annotations

import csv
import json
import math
import shutil
import subprocess
import threading
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from .repeated_orchestrator_executor_trials import (
    RepeatedGroupRunConfig,
    run_repeated_group_trials,
)


PROJECT_ROOT = Path(__file__).resolve().parents[2]
ProbeStatus = Literal["completed", "completed_with_failures", "failed", "blocked"]


@dataclass(frozen=True)
class PairSpec:
    orchestrator_model_id: str
    executor_model_id: str

    @property
    def label(self) -> str:
        return f"{self.orchestrator_model_id}->{self.executor_model_id}"

    @property
    def pair_id(self) -> str:
        return f"{self.orchestrator_model_id}__{self.executor_model_id}"


@dataclass(frozen=True)
class ScenarioSpec:
    label: str
    path: str
    max_group_steps: int
    orchestrator_max_tokens: int | None = None


@dataclass
class ManagedServer:
    role: str
    model_id: str
    port: int
    wrapper_pid: int | None = None
    llama_pids: list[int] = field(default_factory=list)
    endpoint_ready: bool = False
    endpoint_stopped: bool = False
    startup_time_ms: float | None = None
    endpoint_before: bool = False
    endpoint_after: bool | None = None
    error: str | None = None


@dataclass(frozen=True)
class RuntimeProbeConfig:
    project_root: Path
    mode: Literal["local", "fake"]
    models_config_path: str
    out_root: str
    label: str
    pairs: list[PairSpec]
    scenarios: list[ScenarioSpec]
    trials: int
    base_orchestrator_port: int = 8081
    base_executor_port: int = 8082
    manage_servers: bool = True
    max_steps_per_agent: int = 1
    orchestrator_repair_attempts: int = 1
    repair_attempts: int = 1
    execute_actions: bool = True
    sample_interval_seconds: float = 0.5
    continue_on_pair_failure: bool = True
    force: bool = False


def run_runtime_probe(config: RuntimeProbeConfig) -> dict[str, Any]:
    out_root = _prepare_output_root(config.project_root / config.out_root, force=config.force)
    system_before = collect_system_snapshot()
    rows: list[dict[str, Any]] = []
    pair_runs: list[dict[str, Any]] = []

    for scenario in config.scenarios:
        for pair in config.pairs:
            run_label = f"{scenario.label}_{_pair_slug(pair)}"
            run_root = out_root / run_label
            run_root.mkdir(parents=True, exist_ok=True)
            pair_runs.append(
                _run_pair_scenario_probe(
                    config=config,
                    scenario=scenario,
                    pair=pair,
                    run_label=run_label,
                    run_root=run_root,
                )
            )
            rows.append(_metrics_row(pair_runs[-1]))
            if pair_runs[-1]["status"] in {"failed", "blocked"} and not config.continue_on_pair_failure:
                break

    system_after = collect_system_snapshot()
    capacity = estimate_capacity(rows, system_after)
    tradeoff = build_quality_cost_tradeoff(rows, capacity)
    result = {
        "probe_id": config.label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "mode": config.mode,
        "models_config_path": config.models_config_path,
        "system_before": system_before,
        "system_after": system_after,
        "runs": pair_runs,
        "runtime_metrics_by_pair_scenario": rows,
        "capacity_estimates": capacity,
        "quality_cost_tradeoff": tradeoff,
        "limitations": [
            "Short local runtime probe, not a production stress test.",
            "No external network, real browser automation, or real office automation was used.",
            "Capacity is estimated from measured short-run telemetry, not measured concurrency.",
            "GPU was audited separately but not used for these local measurements.",
        ],
    }
    write_runtime_probe_outputs(result, out_root, config)
    return result


def _run_pair_scenario_probe(
    *,
    config: RuntimeProbeConfig,
    scenario: ScenarioSpec,
    pair: PairSpec,
    run_label: str,
    run_root: Path,
) -> dict[str, Any]:
    servers: list[ManagedServer] = []
    sampler: ProcessSampler | None = None
    server_error: str | None = None
    status: ProbeStatus = "completed"
    started_at = time.perf_counter()
    try:
        if config.mode == "local" and config.manage_servers:
            servers = _start_managed_servers(config, pair)
            sampler = ProcessSampler(
                pids=sorted({pid for server in servers for pid in server.llama_pids}),
                interval_seconds=config.sample_interval_seconds,
            )
            sampler.start()
        result = run_repeated_group_trials(
            RepeatedGroupRunConfig(
                project_root=config.project_root,
                mode=config.mode,
                models_config_path=config.models_config_path,
                scenario_path=scenario.path,
                out_root=str(run_root.relative_to(config.project_root)),
                label=run_label,
                trials=config.trials,
                orchestrator_model_id=pair.orchestrator_model_id,
                executor_model_id=pair.executor_model_id,
                orchestrator_base_url=_base_url(config.base_orchestrator_port) if config.mode == "local" else None,
                executor_base_url=_base_url(config.base_executor_port) if config.mode == "local" else None,
                orchestrator_max_tokens=scenario.orchestrator_max_tokens,
                orchestrator_repair_attempts=config.orchestrator_repair_attempts,
                max_group_steps=scenario.max_group_steps,
                max_steps_per_agent=config.max_steps_per_agent,
                repair_attempts=config.repair_attempts,
                execute_actions=config.execute_actions,
                continue_on_trial_failure=True,
                force=True,
            )
        )
        if result.aggregate.failed_trial_count:
            status = "completed_with_failures"
    except Exception as exc:
        server_error = str(exc) or exc.__class__.__name__
        status = "blocked"
        _write_json(
            run_root / "runtime_probe_blocker.json",
            {
                "status": status,
                "error_type": exc.__class__.__name__,
                "error_message": server_error,
            },
        )
    finally:
        if sampler is not None:
            sampler.stop()
        samples = sampler.samples if sampler is not None else []
        if servers:
            _stop_managed_servers(servers)
        _write_server_run(run_root, servers, server_error)
        _write_json(run_root / "telemetry_samples.json", samples)
        _write_samples_csv(samples, run_root / "telemetry_samples.csv")

    metrics = _load_aggregate(run_root)
    telemetry = summarize_samples(samples)
    summary = {
        "run_label": run_label,
        "status": status,
        "scenario_label": scenario.label,
        "scenario_path": scenario.path,
        "pair": pair.label,
        "pair_id": pair.pair_id,
        "artifact_path": str(run_root),
        "wall_time_ms_probe": _elapsed_ms(started_at),
        "server_error": server_error,
        "servers": [_server_payload(server) for server in servers],
        "server_strategy": _server_strategy(config, pair),
        "aggregate": metrics,
        "telemetry": telemetry,
        "mean_group_step_time_ms": _mean_group_step_time_ms(metrics, scenario.max_group_steps),
        "mean_repair_latency_ms": _mean_repair_latency(run_root),
    }
    _write_json(run_root / "runtime_probe_summary.json", summary)
    return summary


class ProcessSampler:
    def __init__(self, *, pids: list[int], interval_seconds: float) -> None:
        self.pids = pids
        self.interval_seconds = max(0.1, interval_seconds)
        self.samples: list[dict[str, Any]] = []
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self.psutil_available = False

    def start(self) -> None:
        self._thread = threading.Thread(target=self._run, name="runtime-probe-sampler", daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=5)

    def _run(self) -> None:
        try:
            import psutil  # type: ignore

            self.psutil_available = True
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
                    }
                )
                self._stop.wait(self.interval_seconds)
        except Exception as exc:
            self.samples.append(
                {
                    "timestamp": datetime.now(timezone.utc).isoformat(),
                    "psutil_available": False,
                    "error": str(exc) or exc.__class__.__name__,
                    "processes": [],
                }
            )


def summarize_samples(samples: list[dict[str, Any]]) -> dict[str, Any]:
    pair_rss = [_number(sample.get("pair_rss_mb")) for sample in samples]
    pair_cpu = [_number(sample.get("pair_cpu_percent")) for sample in samples]
    system_available = [_number(sample.get("system_ram_available_mb")) for sample in samples]
    active_processes = [_number(sample.get("active_llama_server_processes")) for sample in samples]
    return {
        "sample_count": len(samples),
        "psutil_available": any(sample.get("psutil_available") is True for sample in samples),
        "peak_ram_mb_pair": _safe_max(pair_rss),
        "mean_ram_mb_pair": _safe_mean(pair_rss),
        "peak_cpu_percent_pair": _safe_max(pair_cpu),
        "mean_cpu_percent_pair": _safe_mean(pair_cpu),
        "min_system_ram_available_mb": _safe_min(system_available),
        "max_active_llama_server_processes": int(_safe_max(active_processes) or 0),
    }


def estimate_capacity(rows: list[dict[str, Any]], system_snapshot: dict[str, Any]) -> list[dict[str, Any]]:
    total_ram = float(system_snapshot.get("total_ram_mb") or 0.0)
    out: list[dict[str, Any]] = []
    by_pair: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        by_pair.setdefault(str(row["pair"]), []).append(row)
    for pair, pair_rows in sorted(by_pair.items()):
        peak_ram = _safe_max([_number(row.get("peak_ram_mb_pair")) for row in pair_rows]) or 0.0
        peak_cpu = _safe_max([_number(row.get("peak_cpu_percent_pair")) for row in pair_rows])
        mean_wall = _safe_mean([_number(row.get("mean_wall_time_ms")) for row in pair_rows])
        max_agents = max(int(row.get("scenario_agent_count") or 0) for row in pair_rows) or 1
        estimates_by_reserve: dict[str, Any] = {}
        for reserve in [4096.0, 8192.0]:
            available = max(0.0, total_ram - reserve)
            pairs_by_ram = math.floor(available / peak_ram) if peak_ram > 0 else 0
            estimates_by_reserve[str(int(reserve))] = {
                "reserve_ram_mb": reserve,
                "available_for_models_mb": round(available, 6),
                "estimated_concurrent_pairs_by_ram": pairs_by_ram,
                "estimated_agents_by_ram": pairs_by_ram * max_agents,
            }
        out.append(
            {
                "pair": pair,
                "peak_ram_mb_pair": peak_ram,
                "peak_cpu_percent_pair": peak_cpu,
                "mean_wall_time_per_trial_ms": mean_wall,
                "mean_group_step_time_ms": _safe_mean([_number(row.get("mean_group_step_time_ms")) for row in pair_rows]),
                "estimated_throughput_group_steps_per_hour": _throughput_group_steps_per_hour(pair_rows),
                "max_agents_per_pair": max_agents,
                "estimates_by_reserve_mb": estimates_by_reserve,
                "bottleneck": _bottleneck(peak_ram, peak_cpu, mean_wall),
                "confidence": "medium" if peak_ram > 0 and any(row.get("completed_trials") for row in pair_rows) else "low",
                "notes": [
                    "Capacity is estimated from short sequential local probes.",
                    "No concurrent stress test was run.",
                ],
            }
        )
    return out


def build_quality_cost_tradeoff(rows: list[dict[str, Any]], capacity: list[dict[str, Any]]) -> dict[str, Any]:
    capacity_by_pair = {item["pair"]: item for item in capacity}
    pair_rows: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        pair_rows.setdefault(str(row["pair"]), []).append(row)
    scores: list[dict[str, Any]] = []
    for pair, items in sorted(pair_rows.items()):
        quality = _safe_mean([_number(item.get("mean_pair_quality_score")) for item in items]) or 0.0
        errors = sum(int(item.get("total_errors") or 0) for item in items)
        peak_ram = float(capacity_by_pair.get(pair, {}).get("peak_ram_mb_pair") or 0.0)
        mean_wall = _safe_mean([_number(item.get("mean_wall_time_ms")) for item in items]) or 0.0
        cost_penalty = min(0.4, (peak_ram / 65536.0) + (mean_wall / 120000.0))
        stability_penalty = min(0.3, errors / 100.0)
        scores.append(
            {
                "pair": pair,
                "mean_quality": round(quality, 6),
                "total_errors": errors,
                "peak_ram_mb_pair": peak_ram,
                "mean_wall_time_ms": mean_wall,
                "quality_cost_score": round(max(0.0, quality - cost_penalty - stability_penalty), 6),
            }
        )
    scores.sort(key=lambda row: row["quality_cost_score"], reverse=True)
    quality_winner = max(scores, key=lambda row: row["mean_quality"])["pair"] if scores else None
    return {
        "rankings": scores,
        "preliminary_quality_winner": quality_winner,
        "preliminary_resource_balanced_winner": scores[0]["pair"] if scores else None,
        "recommendation_status": "preliminary only",
    }


def write_runtime_probe_outputs(result: dict[str, Any], out_root: Path, config: RuntimeProbeConfig) -> None:
    rows = result["runtime_metrics_by_pair_scenario"]
    capacity = result["capacity_estimates"]
    tradeoff = result["quality_cost_tradeoff"]
    _write_json(out_root / "runtime_probe_index.json", result["runs"])
    _write_index_csv(result["runs"], out_root / "runtime_probe_index.csv")
    _write_json(out_root / "runtime_metrics_by_pair_scenario.json", rows)
    _write_metrics_csv(rows, out_root / "runtime_metrics_by_pair_scenario.csv")
    _write_json(out_root / "capacity_estimates.json", capacity)
    _write_capacity_csv(capacity, out_root / "capacity_estimates.csv")
    _write_json(out_root / "quality_cost_tradeoff.json", tradeoff)
    _write_json(out_root / "gpu_runtime_status.json", _gpu_runtime_status_placeholder())
    (out_root / "quality_cost_tradeoff.md").write_text(_tradeoff_markdown(tradeoff), encoding="utf-8")
    (out_root / "runtime_capacity_report.md").write_text(_runtime_report(result), encoding="utf-8")
    (out_root / "README.md").write_text(_readme(result), encoding="utf-8")
    (out_root / "replay_commands.ps1").write_text(_replay_command(config) + "\n", encoding="utf-8")
    _write_json(out_root / "runtime_probe_result.json", result)


def collect_system_snapshot() -> dict[str, Any]:
    snapshot = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "psutil_available": False,
        "total_ram_mb": None,
        "available_ram_mb": None,
        "cpu_count_logical": None,
        "cpu_count_physical": None,
    }
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        snapshot.update(
            {
                "psutil_available": True,
                "total_ram_mb": _mb(vm.total),
                "available_ram_mb": _mb(vm.available),
                "cpu_count_logical": psutil.cpu_count(logical=True),
                "cpu_count_physical": psutil.cpu_count(logical=False),
                "system_cpu_percent": psutil.cpu_percent(interval=0.1),
            }
        )
    except Exception as exc:
        snapshot["warning"] = str(exc) or exc.__class__.__name__
    return snapshot


def _start_managed_servers(config: RuntimeProbeConfig, pair: PairSpec) -> list[ManagedServer]:
    if _endpoint_json(config.base_orchestrator_port) is not None or _endpoint_json(config.base_executor_port) is not None:
        raise RuntimeError("One or both requested runtime probe ports are already serving a local endpoint.")
    servers = [
        ManagedServer("orchestrator", pair.orchestrator_model_id, config.base_orchestrator_port),
        ManagedServer("executor", pair.executor_model_id, config.base_executor_port),
    ]
    before = set(_llama_server_pids(config.project_root))
    for server in servers:
        server.endpoint_before = _endpoint_json(server.port) is not None
        started = time.perf_counter()
        proc = subprocess.Popen(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ".\\scripts\\start_llama_server.ps1",
                "-ModelId",
                server.model_id,
                "-ModelsConfig",
                config.models_config_path,
                "-Port",
                str(server.port),
            ],
            cwd=config.project_root,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        server.wrapper_pid = proc.pid
        if not _wait_endpoint(server.port, 75):
            server.error = f"endpoint on port {server.port} did not become ready"
            raise RuntimeError(server.error)
        server.startup_time_ms = _elapsed_ms(started)
        server.endpoint_ready = True
        after = set(_llama_server_pids(config.project_root))
        server.llama_pids = sorted(after - before)
        before = after
    return servers


def _stop_managed_servers(servers: list[ManagedServer]) -> None:
    for server in servers:
        ids = [*server.llama_pids]
        if server.wrapper_pid:
            ids.append(server.wrapper_pid)
        ids = list(dict.fromkeys(pid for pid in ids if pid))
        if ids:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "$ids=@(" + ",".join(str(pid) for pid in ids) + "); foreach($id in $ids){Stop-Process -Id $id -Force -ErrorAction SilentlyContinue}",
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
    time.sleep(2)
    for server in servers:
        server.endpoint_after = _endpoint_json(server.port) is not None
        server.endpoint_stopped = server.endpoint_after is False


def _wait_endpoint(port: int, seconds: int) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _endpoint_json(port) is not None:
            return True
        time.sleep(0.5)
    return False


def _endpoint_json(port: int) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def _llama_server_pids(project_root: Path) -> list[int]:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_Process -Filter \"name = 'llama-server.exe'\" | Select-Object -ExpandProperty ProcessId) -join ','",
        ],
        cwd=project_root,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    return [int(item) for item in completed.stdout.strip().split(",") if item.strip().isdigit()]


def _load_aggregate(run_root: Path) -> dict[str, Any]:
    path = run_root / "aggregate_group_metrics.json"
    if not path.exists():
        return {}
    return json.loads(path.read_text(encoding="utf-8"))


def _metrics_row(summary: dict[str, Any]) -> dict[str, Any]:
    aggregate = summary.get("aggregate") or {}
    telemetry = summary.get("telemetry") or {}
    scenario_path = Path(str(summary.get("scenario_path") or ""))
    return {
        "pair": summary.get("pair"),
        "pair_id": summary.get("pair_id"),
        "scenario": summary.get("scenario_label"),
        "scenario_path": str(summary.get("scenario_path")),
        "scenario_agent_count": _scenario_agent_count(scenario_path),
        "status": summary.get("status"),
        "completed_trials": aggregate.get("completed_trial_count"),
        "failed_trials": aggregate.get("failed_trial_count"),
        "mean_pair_quality_score": aggregate.get("mean_pair_quality_score"),
        "mean_execution_success_rate": aggregate.get("mean_execution_success_rate"),
        "total_errors": aggregate.get("total_errors"),
        "common_failure_modes": aggregate.get("common_failure_modes") or {},
        "mean_wall_time_ms": aggregate.get("mean_wall_time_ms"),
        "mean_group_step_time_ms": summary.get("mean_group_step_time_ms"),
        "mean_orchestrator_latency_ms": aggregate.get("mean_orchestrator_latency_ms"),
        "mean_executor_latency_ms": aggregate.get("mean_executor_latency_ms"),
        "mean_repair_latency_ms": summary.get("mean_repair_latency_ms"),
        "peak_ram_mb_pair": telemetry.get("peak_ram_mb_pair"),
        "peak_cpu_percent_pair": telemetry.get("peak_cpu_percent_pair"),
        "sample_count": telemetry.get("sample_count"),
        "server_strategy": summary.get("server_strategy"),
        "artifact_path": summary.get("artifact_path"),
    }


def _scenario_agent_count(path: Path) -> int:
    resolved = path if path.is_absolute() else PROJECT_ROOT / path
    try:
        payload = json.loads(resolved.read_text(encoding="utf-8"))
        return len(payload.get("agents") or [])
    except Exception:
        return 0


def _mean_group_step_time_ms(metrics: dict[str, Any], max_group_steps: int) -> float | None:
    wall = _number(metrics.get("mean_wall_time_ms"))
    if wall is None or max_group_steps <= 0:
        return None
    return round(wall / max_group_steps, 6)


def _mean_repair_latency(run_root: Path) -> float | None:
    values: list[float] = []
    runs_root = run_root / "runs"
    if not runs_root.exists():
        return None
    for trial_dir in runs_root.iterdir():
        attempts_path = trial_dir / "per_agent_attempts.jsonl"
        if not attempts_path.exists():
            continue
        for line in attempts_path.read_text(encoding="utf-8").splitlines():
            if not line.strip():
                continue
            row = json.loads(line)
            if row.get("attempt_type") == "repair":
                value = _number(row.get("selection_latency_ms") or row.get("latency_ms"))
                if value is not None:
                    values.append(value)
    return _safe_mean(values)


def _throughput_group_steps_per_hour(rows: list[dict[str, Any]]) -> float | None:
    values = []
    for row in rows:
        step_ms = _number(row.get("mean_group_step_time_ms"))
        if step_ms and step_ms > 0:
            values.append(3600000.0 / step_ms)
    return _safe_mean(values)


def _bottleneck(peak_ram: float, peak_cpu: float | None, mean_wall: float | None) -> str:
    if peak_cpu is not None and peak_cpu >= 70.0:
        return "CPU-bound"
    if mean_wall is not None and mean_wall >= 10000.0:
        return "latency-bound"
    if peak_ram <= 0:
        return "unknown"
    return "unknown"


def _best_by(rows: list[dict[str, Any]], field: str) -> str | None:
    clean = [row for row in rows if _number(row.get(field)) is not None]
    if not clean:
        return None
    return str(max(clean, key=lambda row: float(row.get(field) or 0.0)).get("pair"))


def _server_strategy(config: RuntimeProbeConfig, pair: PairSpec) -> str:
    if config.mode == "fake":
        return "fake mode; no servers started"
    if not config.manage_servers:
        return "local mode using caller-provided endpoints"
    if pair.orchestrator_model_id == pair.executor_model_id:
        return "two separate llama-server endpoints for the same model on different ports"
    return "two separate llama-server endpoints on different ports"


def _server_payload(server: ManagedServer) -> dict[str, Any]:
    return {
        "role": server.role,
        "model_id": server.model_id,
        "port": server.port,
        "wrapper_pid": server.wrapper_pid,
        "llama_pids": server.llama_pids,
        "endpoint_ready": server.endpoint_ready,
        "endpoint_stopped": server.endpoint_stopped,
        "startup_time_ms": server.startup_time_ms,
        "endpoint_before": server.endpoint_before,
        "endpoint_after": server.endpoint_after,
        "error": server.error,
    }


def _write_server_run(run_root: Path, servers: list[ManagedServer], server_error: str | None) -> None:
    _write_json(
        run_root / "server_run.json",
        {
            "server_error": server_error,
            "servers": [_server_payload(server) for server in servers],
        },
    )


def _write_index_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames = ["run_label", "status", "scenario_label", "pair", "artifact_path", "wall_time_ms_probe", "server_error"]
    _write_csv(rows, path, fieldnames)


def _write_metrics_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "pair",
        "scenario",
        "completed_trials",
        "failed_trials",
        "mean_pair_quality_score",
        "mean_execution_success_rate",
        "total_errors",
        "mean_wall_time_ms",
        "mean_group_step_time_ms",
        "mean_orchestrator_latency_ms",
        "mean_executor_latency_ms",
        "peak_ram_mb_pair",
        "peak_cpu_percent_pair",
    ]
    _write_csv(rows, path, fieldnames)


def _write_capacity_csv(rows: list[dict[str, Any]], path: Path) -> None:
    flat = []
    for row in rows:
        estimate = row.get("estimates_by_reserve_mb", {}).get("4096", {})
        flat.append(
            {
                "pair": row.get("pair"),
                "peak_ram_mb_pair": row.get("peak_ram_mb_pair"),
                "peak_cpu_percent_pair": row.get("peak_cpu_percent_pair"),
                "estimated_concurrent_pairs_by_ram": estimate.get("estimated_concurrent_pairs_by_ram"),
                "estimated_agents_by_ram": estimate.get("estimated_agents_by_ram"),
                "bottleneck": row.get("bottleneck"),
                "confidence": row.get("confidence"),
            }
        )
    _write_csv(
        flat,
        path,
        [
            "pair",
            "peak_ram_mb_pair",
            "peak_cpu_percent_pair",
            "estimated_concurrent_pairs_by_ram",
            "estimated_agents_by_ram",
            "bottleneck",
            "confidence",
        ],
    )


def _write_samples_csv(samples: list[dict[str, Any]], path: Path) -> None:
    _write_csv(
        samples,
        path,
        [
            "timestamp",
            "psutil_available",
            "pair_rss_mb",
            "pair_cpu_percent",
            "system_cpu_percent",
            "system_ram_total_mb",
            "system_ram_available_mb",
            "active_llama_server_processes",
            "error",
        ],
    )


def _write_csv(rows: list[dict[str, Any]], path: Path, fieldnames: list[str]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _runtime_report(result: dict[str, Any]) -> str:
    lines = [
        "# Orchestrator/Executor Runtime and Capacity Probe v1",
        "",
        "## 1. Purpose",
        "",
        "Compare candidate orchestrator/executor pairs after simple and heavy scenario evidence.",
        "",
        "## 2. Candidate pairs",
        "",
    ]
    for pair in sorted({row["pair"] for row in result["runtime_metrics_by_pair_scenario"]}):
        lines.append(f"- `{pair}`")
    lines.extend(
        [
            "",
            "## 3. Runtime protocol",
            "",
            f"- probe_id: `{result.get('probe_id')}`",
            f"- mode: `{result.get('mode')}`",
            f"- models_config_path: `{result.get('models_config_path')}`",
            "- server management: managed two local llama-server endpoints per measured pair when run in local mode.",
            "- telemetry: per-process RSS/CPU sampled with psutil when available.",
            "- capacity estimate: derived from measured peak pair RSS and system RAM snapshot; it is not a concurrent stress test.",
            "",
            "Scenarios:",
            "",
        ]
    )
    seen_scenarios: set[tuple[str, str]] = set()
    for row in result["runtime_metrics_by_pair_scenario"]:
        scenario_key = (str(row["scenario"]), str(row.get("scenario_path")))
        if scenario_key in seen_scenarios:
            continue
        seen_scenarios.add(scenario_key)
        lines.append(f"- `{row['scenario']}`: `{row.get('scenario_path')}`")
    lines.extend(
        [
            "",
            "## 4. Runtime results table",
            "",
            "| pair | scenario | completed_trials | mean_pair_quality_score | mean_execution_success_rate | total_errors | mean_wall_time_ms | peak_ram_mb_pair | peak_cpu_percent_pair |",
            "|---|---|---:|---:|---:|---:|---:|---:|---:|",
        ]
    )
    for row in result["runtime_metrics_by_pair_scenario"]:
        lines.append(
            f"| `{row['pair']}` | `{row['scenario']}` | {row.get('completed_trials')} | "
            f"{row.get('mean_pair_quality_score')} | {row.get('mean_execution_success_rate')} | "
            f"{row.get('total_errors')} | {row.get('mean_wall_time_ms')} | "
            f"{row.get('peak_ram_mb_pair')} | {row.get('peak_cpu_percent_pair')} |"
        )
    lines.extend(["", "## 5. Capacity estimate", ""])
    lines.append("| pair | estimated pairs by RAM | estimated agents by RAM | bottleneck | confidence |")
    lines.append("|---|---:|---:|---|---|")
    for row in result["capacity_estimates"]:
        estimate = row.get("estimates_by_reserve_mb", {}).get("4096", {})
        lines.append(
            f"| `{row['pair']}` | {estimate.get('estimated_concurrent_pairs_by_ram')} | "
            f"{estimate.get('estimated_agents_by_ram')} | `{row.get('bottleneck')}` | `{row.get('confidence')}` |"
        )
    lines.extend(
        [
            "",
            "## 6. Quality vs cost tradeoff",
            "",
            _tradeoff_markdown(result["quality_cost_tradeoff"]),
            "",
            "## 7. GPU readiness",
            "",
            "- GPU runtime measured in this probe: no.",
            "- GPU audit is recorded separately in `gpu_runtime_status.json` and `docs/ai/gpu_runtime_readiness_audit.md`.",
            "- GPU is likely useful for throughput/capacity, but current CPU local group evidence is already functional.",
            "",
            "## 8. Recommendation status",
            "",
            f"`{result['quality_cost_tradeoff'].get('recommendation_status')}`. Runtime evidence is sufficient for a preliminary local prototype recommendation only, not for production sizing.",
            "",
            "## 9. Limitations",
            "",
        ]
    )
    for limitation in result["limitations"]:
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


def _tradeoff_markdown(tradeoff: dict[str, Any]) -> str:
    lines = [
        "| pair | mean_quality | total_errors | peak_ram_mb_pair | mean_wall_time_ms | quality_cost_score |",
        "|---|---:|---:|---:|---:|---:|",
    ]
    for row in tradeoff.get("rankings") or []:
        lines.append(
            f"| `{row['pair']}` | {row['mean_quality']} | {row['total_errors']} | "
            f"{row['peak_ram_mb_pair']} | {row['mean_wall_time_ms']} | {row['quality_cost_score']} |"
        )
    lines.append("")
    lines.append(f"Recommendation status: `{tradeoff.get('recommendation_status')}`.")
    return "\n".join(lines)


def _readme(result: dict[str, Any]) -> str:
    return (
        "# Runtime Probe Candidate Pairs\n\n"
        f"- probe_id: `{result['probe_id']}`\n"
        "- capacity is estimated from short local probes, not a stress test.\n\n"
        "Primary files:\n\n"
        "- `runtime_capacity_report.md`\n"
        "- `runtime_metrics_by_pair_scenario.json`\n"
        "- `capacity_estimates.json`\n"
        "- `quality_cost_tradeoff.md`\n"
        "- `gpu_runtime_status.json`\n"
    )


def _gpu_runtime_status_placeholder() -> dict[str, Any]:
    return {
        "gpu_detected": "not_collected_by_probe",
        "gpu_runtime_measured": False,
        "llama_server_gpu_flags_available": "not_collected_by_probe",
        "note": "Runtime probe measurements are CPU/runtime endpoint measurements. Hardware GPU audit is maintained separately.",
    }


def _replay_command(config: RuntimeProbeConfig) -> str:
    pairs = ",".join(f"{pair.orchestrator_model_id}:{pair.executor_model_id}" for pair in config.pairs)
    scenarios = ",".join(f"{scenario.label}={scenario.path}" for scenario in config.scenarios)
    action_flag = "--execute-actions" if config.execute_actions else "--no-execute-actions"
    server_flag = "--manage-servers" if config.manage_servers else "--no-manage-servers"
    return (
        "python scripts\\probe_orchestrator_executor_runtime.py "
        f"--mode {config.mode} "
        f"--models-config {config.models_config_path} "
        f"--out-root {config.out_root} "
        f"--label {config.label} "
        f"--pairs {pairs} "
        f"--scenarios {scenarios} "
        f"--trials {config.trials} "
        f"--base-orchestrator-port {config.base_orchestrator_port} "
        f"--base-executor-port {config.base_executor_port} "
        f"{server_flag} "
        f"--max-steps-per-agent {config.max_steps_per_agent} "
        f"--orchestrator-repair-attempts {config.orchestrator_repair_attempts} "
        f"--repair-attempts {config.repair_attempts} "
        f"{action_flag} "
        f"--sample-interval-seconds {config.sample_interval_seconds} "
        "--continue-on-pair-failure"
    )


def _prepare_output_root(out_root: Path, *, force: bool) -> Path:
    if out_root.exists():
        if not force:
            raise FileExistsError(f"Runtime probe output root already exists: {out_root}")
        resolved = out_root.resolve()
        try:
            resolved.relative_to(PROJECT_ROOT.resolve())
        except ValueError as exc:
            raise RuntimeError(f"Refusing to remove output outside project root: {resolved}") from exc
        if resolved == PROJECT_ROOT.resolve():
            raise RuntimeError("Refusing to remove project root.")
        shutil.rmtree(resolved)
    out_root.mkdir(parents=True, exist_ok=True)
    return out_root


def _base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/v1"


def _pair_slug(pair: PairSpec) -> str:
    if pair.orchestrator_model_id == "second_model" and pair.executor_model_id == "first_model":
        return "second_to_first"
    if pair.orchestrator_model_id == "second_model" and pair.executor_model_id == "second_model":
        return "second_to_second"
    return pair.pair_id


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _safe_mean(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 6)


def _safe_min(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return round(min(clean), 6) if clean else None


def _safe_max(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    return round(max(clean), 6) if clean else None
