from __future__ import annotations

import argparse
import csv
import hashlib
import json
import platform
import re
import shutil
import socket
import subprocess
import sys
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Iterable

PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.orchestrator_executor_runtime_probe import (
    collect_gpu_telemetry,
    summarize_samples,
)


CASE_SPECS: tuple[dict[str, Any], ...] = (
    {
        "case_id": "short",
        "payload_words": 448,
        "max_tokens": 64,
        "target_prompt_tokens": 512,
    },
    {
        "case_id": "medium",
        "payload_words": 1856,
        "max_tokens": 128,
        "target_prompt_tokens": 2048,
    },
    {
        "case_id": "long",
        "payload_words": 7424,
        "max_tokens": 128,
        "target_prompt_tokens": 8192,
    },
)


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def percentile(values: Iterable[float], quantile: float) -> float | None:
    ordered = sorted(float(value) for value in values)
    if not ordered:
        return None
    if quantile <= 0:
        return round(ordered[0], 6)
    if quantile >= 1:
        return round(ordered[-1], 6)
    position = (len(ordered) - 1) * quantile
    lower = int(position)
    upper = min(lower + 1, len(ordered) - 1)
    fraction = position - lower
    value = ordered[lower] + (ordered[upper] - ordered[lower]) * fraction
    return round(value, 6)


def safe_mean(values: Iterable[float | int | None]) -> float | None:
    valid = [float(value) for value in values if isinstance(value, (int, float))]
    return round(mean(valid), 6) if valid else None


def safe_min(values: Iterable[float | int | None]) -> float | None:
    valid = [float(value) for value in values if isinstance(value, (int, float))]
    return round(min(valid), 6) if valid else None


def safe_max(values: Iterable[float | int | None]) -> float | None:
    valid = [float(value) for value in values if isinstance(value, (int, float))]
    return round(max(valid), 6) if valid else None


def deterministic_payload(word_count: int) -> str:
    if word_count <= 0:
        raise ValueError("word_count must be positive")
    return " ".join(["x"] * word_count)


def build_corpus() -> list[dict[str, Any]]:
    corpus: list[dict[str, Any]] = []
    for spec in CASE_SPECS:
        case_id = str(spec["case_id"])
        payload = deterministic_payload(int(spec["payload_words"]))
        messages = [
            {
                "role": "system",
                "content": (
                    "You are running a deterministic local inference benchmark. "
                    "Do not analyze the payload. Produce a plain continuation."
                ),
            },
            {
                "role": "user",
                "content": (
                    "Repeat the lowercase word benchmark separated by single spaces. "
                    "Continue until the generation budget stops you. "
                    "Do not emit JSON or markdown.\n\n"
                    f"PAYLOAD_{case_id.upper()}:\n{payload}"
                ),
            },
        ]
        serialized = json.dumps(messages, ensure_ascii=False, separators=(",", ":"))
        corpus.append(
            {
                **spec,
                "messages": messages,
                "messages_sha256": hashlib.sha256(
                    serialized.encode("utf-8")
                ).hexdigest(),
                "payload_character_count": len(payload),
            }
        )
    return corpus


def prepare_output_dir(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(
            f"Output directory already exists: {path}. Use --force to overwrite."
        )
    if path.exists():
        shutil.rmtree(path)
    path.mkdir(parents=True, exist_ok=True)


def append_jsonl(path: Path, payload: dict[str, Any]) -> None:
    with path.open("a", encoding="utf-8") as handle:
        handle.write(json.dumps(payload, ensure_ascii=False, sort_keys=True) + "\n")


def write_json(path: Path, payload: Any) -> None:
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def sha256_file(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for chunk in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(chunk)
    return digest.hexdigest()


def validate_model_file(
    path: Path,
    *,
    expected_bytes: int | None = None,
    expected_sha256: str | None = None,
) -> dict[str, Any]:
    if not path.is_file():
        raise FileNotFoundError(path)
    actual_bytes = path.stat().st_size
    normalized_expected_sha256: str | None = None
    if expected_sha256 is not None:
        normalized_expected_sha256 = expected_sha256.strip().lower()
        if not re.fullmatch(r"[0-9a-f]{64}", normalized_expected_sha256):
            raise ValueError("Expected SHA-256 must be 64 lowercase/uppercase hex characters")
    actual_sha256 = sha256_file(path) if expected_sha256 else None
    if expected_bytes is not None and actual_bytes != expected_bytes:
        raise ValueError(
            f"Model byte size mismatch: expected {expected_bytes}, got {actual_bytes}"
        )
    if normalized_expected_sha256 is not None:
        if actual_sha256 != normalized_expected_sha256:
            raise ValueError(
                "Model SHA-256 mismatch: "
                f"expected {normalized_expected_sha256}, got {actual_sha256}"
            )
    return {
        "path": str(path),
        "bytes": actual_bytes,
        "sha256": actual_sha256,
        "expected_bytes": expected_bytes,
        "expected_sha256": normalized_expected_sha256,
    }


def port_is_free(host: str, port: int) -> bool:
    try:
        with socket.create_connection((host, port), timeout=0.5):
            return False
    except OSError:
        return True


def validate_local_host(host: str) -> str:
    normalized = host.strip().lower()
    if normalized not in {"127.0.0.1", "localhost"}:
        raise ValueError("This harness only supports localhost/127.0.0.1 hosts")
    return normalized


def find_llama_server_processes() -> list[dict[str, Any]]:
    try:
        import psutil
    except Exception:
        return []
    matches: list[dict[str, Any]] = []
    for process in psutil.process_iter(["pid", "name", "cmdline"]):
        try:
            name = str(process.info.get("name") or "")
            cmdline = [
                str(part) for part in (process.info.get("cmdline") or [])
            ]
        except Exception:
            continue
        executable = Path(cmdline[0]).name if cmdline else ""
        if "llama-server" in name.lower() or "llama-server" in executable.lower():
            matches.append(
                {
                    "pid": process.info.get("pid"),
                    "name": name,
                    "cmdline": cmdline,
                }
            )
    return matches


def build_server_args(
    *,
    server_path: Path,
    model_path: Path,
    model_id: str,
    host: str,
    port: int,
    ctx_size: int,
    gpu_layers: str,
    parallel: int,
    jinja: bool = False,
    reasoning: str | None = None,
    server_log_verbosity: int | None = None,
) -> list[str]:
    if server_log_verbosity is not None and server_log_verbosity < 0:
        raise ValueError("server_log_verbosity must be non-negative")
    server_args = [
        str(server_path),
        "--model",
        str(model_path),
        "--alias",
        model_id,
        "--host",
        host,
        "--port",
        str(port),
        "--ctx-size",
        str(ctx_size),
        "--n-gpu-layers",
        str(gpu_layers),
        "--parallel",
        str(parallel),
    ]
    if jinja:
        server_args.append("--jinja")
    if reasoning:
        server_args.extend(["--reasoning", reasoning])
    if server_log_verbosity is not None:
        server_args.extend(["-lv", str(server_log_verbosity)])
    return server_args


def build_server_command_payload(server_args: list[str]) -> dict[str, Any]:
    return {"argv": list(server_args)}


def parse_startup_log_evidence(text: str, *, expected_alias: str) -> dict[str, Any]:
    def search(pattern: str) -> re.Match[str] | None:
        return re.search(pattern, text, re.IGNORECASE)

    evidence: dict[str, Any] = {
        "expected_alias": expected_alias,
        "alias_present": expected_alias in text,
        "backend_vulkan1_present": bool(search(r"Vulkan1\s*:")),
        "gpu_name": None,
        "offloaded_layers": None,
        "vulkan1_model_buffer_mib": None,
        "vulkan1_kv_buffer_mib": None,
        "vulkan1_compute_buffer_mib": None,
        "oom_or_failed_allocation_present": bool(
            search(r"\bOOM\b|out of memory|failed allocation|allocation failed|alloc failed")
        ),
        "reasoning_disabled": bool(search(r"thinking\s*=\s*0")),
        "context_size": None,
    }
    gpu = search(r"Vulkan1\s*:\s*([^\r\n(]+)")
    if gpu:
        evidence["gpu_name"] = gpu.group(1).strip()
    for field, pattern, cast in [
        ("offloaded_layers", r"offloaded\s+(\d+/\d+)\s+layers\s+to GPU", str),
        ("vulkan1_model_buffer_mib", r"Vulkan1 model buffer size\s*=\s*([0-9.]+)\s*MiB", float),
        ("vulkan1_kv_buffer_mib", r"Vulkan1 KV buffer size\s*=\s*([0-9.]+)\s*MiB", float),
        ("vulkan1_compute_buffer_mib", r"Vulkan1 compute buffer size\s*=\s*([0-9.]+)\s*MiB", float),
        ("context_size", r"n_ctx\s*=\s*(\d+)", int),
    ]:
        match = search(pattern)
        if match:
            evidence[field] = cast(match.group(1))
    return evidence


def read_startup_log_evidence(
    stderr_path: Path,
    *,
    expected_alias: str,
) -> dict[str, Any]:
    text = (
        stderr_path.read_text(encoding="utf-8", errors="replace")
        if stderr_path.exists()
        else ""
    )
    return parse_startup_log_evidence(text, expected_alias=expected_alias)


def validate_startup_log_evidence(
    evidence: dict[str, Any],
    *,
    expected_offloaded_layers: str | None = None,
    require_alias: bool = False,
    expected_context_size: int | None = None,
    require_reasoning_off: bool = False,
) -> list[str]:
    failures: list[str] = []
    if not evidence.get("backend_vulkan1_present"):
        failures.append("startup_log_missing_vulkan1_backend")
    if require_alias and not evidence.get("alias_present"):
        failures.append("startup_log_missing_expected_alias")
    if expected_offloaded_layers and evidence.get("offloaded_layers") != expected_offloaded_layers:
        failures.append("startup_log_offloaded_layers_mismatch")
    if expected_context_size is not None and evidence.get("context_size") != expected_context_size:
        failures.append("startup_log_context_size_mismatch")
    if require_reasoning_off and evidence.get("reasoning_disabled") is not True:
        failures.append("startup_log_reasoning_not_disabled")
    if evidence.get("oom_or_failed_allocation_present"):
        failures.append("startup_log_contains_oom_or_failed_allocation")
    return failures


def build_optional_replay_flags(
    *,
    jinja: bool,
    reasoning: str | None,
    expected_model_bytes: int | None,
    expected_model_sha256: str | None,
    expected_offloaded_layers: str | None,
    require_startup_alias: bool,
    server_log_verbosity: int | None,
) -> str:
    optional_replay_flags = ""
    if jinja:
        optional_replay_flags += "  --jinja `\n"
    if reasoning:
        optional_replay_flags += f"  --reasoning {reasoning} `\n"
    if server_log_verbosity is not None:
        optional_replay_flags += (
            f"  --server-log-verbosity {server_log_verbosity} `\n"
        )
    if expected_model_bytes is not None:
        optional_replay_flags += (
            f"  --expected-model-bytes {expected_model_bytes} `\n"
        )
    if expected_model_sha256:
        optional_replay_flags += (
            f"  --expected-model-sha256 {expected_model_sha256} `\n"
        )
    if expected_offloaded_layers:
        optional_replay_flags += (
            f"  --expected-offloaded-layers {expected_offloaded_layers} `\n"
        )
    if require_startup_alias:
        optional_replay_flags += "  --require-startup-alias `\n"
    return optional_replay_flags


def private_memory_mb(process: Any) -> float | None:
    try:
        info = process.memory_full_info()
    except Exception:
        try:
            info = process.memory_info()
        except Exception:
            return None
    for field_name in ("private", "uss"):
        value = getattr(info, field_name, None)
        if isinstance(value, (int, float)):
            return round(float(value) / (1024.0 * 1024.0), 6)
    return None


class PhaseSampler:
    def __init__(self, *, interval_seconds: float) -> None:
        if interval_seconds <= 0:
            raise ValueError("interval_seconds must be positive")
        self.interval_seconds = interval_seconds
        self.samples: list[dict[str, Any]] = []
        self._phase = "baseline_without_server"
        self._server_pid: int | None = None
        self._lock = threading.Lock()
        self._stop = threading.Event()
        self._thread: threading.Thread | None = None
        self._started_perf: float | None = None

    def set_phase(self, phase: str) -> None:
        with self._lock:
            self._phase = phase

    def set_server_pid(self, pid: int | None) -> None:
        with self._lock:
            self._server_pid = pid

    def start(self) -> None:
        if self._thread is not None:
            raise RuntimeError("sampler already started")
        self._started_perf = time.perf_counter()
        self._thread = threading.Thread(
            target=self._run,
            name="deterministic-gpu-resource-sampler",
            daemon=True,
        )
        self._thread.start()

    def stop(self) -> None:
        self._stop.set()
        if self._thread is not None:
            self._thread.join(timeout=max(3.0, self.interval_seconds * 4))

    def _snapshot_state(self) -> tuple[str, int | None]:
        with self._lock:
            return self._phase, self._server_pid

    def _run(self) -> None:
        try:
            import psutil
        except Exception as exc:
            self.samples.append(
                {
                    "timestamp": now_utc_iso(),
                    "phase": self._phase,
                    "psutil_available": False,
                    "error": str(exc) or exc.__class__.__name__,
                    "gpu": collect_gpu_telemetry(),
                }
            )
            return

        logical_cpu_count = psutil.cpu_count(logical=True) or 1
        psutil.cpu_percent(interval=None)
        process_handles: dict[int, Any] = {}

        while not self._stop.is_set():
            phase, server_pid = self._snapshot_state()
            process_rows: list[dict[str, Any]] = []
            if server_pid is not None:
                pids = [server_pid]
                try:
                    parent = psutil.Process(server_pid)
                    pids.extend(child.pid for child in parent.children(recursive=True))
                except Exception:
                    pass
                for pid in sorted(set(pids)):
                    try:
                        process = process_handles.get(pid)
                        if process is None:
                            process = psutil.Process(pid)
                            process.cpu_percent(interval=None)
                            process_handles[pid] = process
                        cpu_raw = round(float(process.cpu_percent(interval=None)), 6)
                        memory = process.memory_info()
                        process_rows.append(
                            {
                                "pid": pid,
                                "name": process.name(),
                                "rss_mb": round(
                                    float(memory.rss) / (1024.0 * 1024.0),
                                    6,
                                ),
                                "private_mb": private_memory_mb(process),
                                "cpu_percent_raw": cpu_raw,
                                "cpu_percent_normalized": round(
                                    cpu_raw / logical_cpu_count,
                                    6,
                                ),
                                "status": process.status(),
                            }
                        )
                    except Exception as exc:
                        process_rows.append(
                            {
                                "pid": pid,
                                "error": str(exc) or exc.__class__.__name__,
                            }
                        )

            virtual_memory = psutil.virtual_memory()
            gpu = collect_gpu_telemetry()
            elapsed_seconds = (
                time.perf_counter() - self._started_perf
                if self._started_perf is not None
                else None
            )
            self.samples.append(
                {
                    "timestamp": now_utc_iso(),
                    "elapsed_seconds": (
                        round(elapsed_seconds, 6)
                        if elapsed_seconds is not None
                        else None
                    ),
                    "phase": phase,
                    "server_pid": server_pid,
                    "psutil_available": True,
                    "logical_cpu_count": logical_cpu_count,
                    "processes": process_rows,
                    "pair_rss_mb": round(
                        sum(float(row.get("rss_mb") or 0.0) for row in process_rows),
                        6,
                    ),
                    "pair_private_mb": round(
                        sum(
                            float(row.get("private_mb") or 0.0)
                            for row in process_rows
                        ),
                        6,
                    ),
                    "pair_cpu_percent": round(
                        sum(
                            float(row.get("cpu_percent_raw") or 0.0)
                            for row in process_rows
                        ),
                        6,
                    ),
                    "pair_cpu_percent_normalized": round(
                        sum(
                            float(row.get("cpu_percent_normalized") or 0.0)
                            for row in process_rows
                        ),
                        6,
                    ),
                    "system_cpu_percent": round(
                        float(psutil.cpu_percent(interval=None)),
                        6,
                    ),
                    "system_ram_total_mb": round(
                        float(virtual_memory.total) / (1024.0 * 1024.0),
                        6,
                    ),
                    "system_ram_available_mb": round(
                        float(virtual_memory.available) / (1024.0 * 1024.0),
                        6,
                    ),
                    "system_ram_used_mb": round(
                        float(virtual_memory.used) / (1024.0 * 1024.0),
                        6,
                    ),
                    "active_llama_server_processes": len(
                        [row for row in process_rows if not row.get("error")]
                    ),
                    "gpu": gpu,
                }
            )
            self._stop.wait(self.interval_seconds)


def phase_summary(samples: list[dict[str, Any]], phase: str) -> dict[str, Any]:
    selected = [sample for sample in samples if sample.get("phase") == phase]
    base = summarize_samples(selected)
    gpu_rows = [
        sample.get("gpu") or {}
        for sample in selected
        if (sample.get("gpu") or {}).get("gpu_telemetry_available") is True
    ]
    base.update(
        {
            "phase": phase,
            "mean_private_mb": safe_mean(
                sample.get("pair_private_mb") for sample in selected
            ),
            "peak_private_mb": safe_max(
                sample.get("pair_private_mb") for sample in selected
            ),
            "mean_cpu_percent_normalized": safe_mean(
                sample.get("pair_cpu_percent_normalized") for sample in selected
            ),
            "peak_cpu_percent_normalized": safe_max(
                sample.get("pair_cpu_percent_normalized") for sample in selected
            ),
            "mean_system_cpu_percent": safe_mean(
                sample.get("system_cpu_percent") for sample in selected
            ),
            "peak_system_cpu_percent": safe_max(
                sample.get("system_cpu_percent") for sample in selected
            ),
            "mean_system_ram_used_mb": safe_mean(
                sample.get("system_ram_used_mb") for sample in selected
            ),
            "peak_system_ram_used_mb": safe_max(
                sample.get("system_ram_used_mb") for sample in selected
            ),
            "gpu_mean_temperature_c": safe_mean(
                gpu.get("temperature_c") for gpu in gpu_rows
            ),
            "gpu_mean_power_draw_w": safe_mean(
                gpu.get("power_draw_w") for gpu in gpu_rows
            ),
        }
    )
    return base


def delta(after: float | int | None, before: float | int | None) -> float | None:
    if not isinstance(after, (int, float)) or not isinstance(
        before, (int, float)
    ):
        return None
    return round(float(after) - float(before), 6)


def build_resource_summary(samples: list[dict[str, Any]]) -> dict[str, Any]:
    phases = sorted(
        {
            str(sample.get("phase"))
            for sample in samples
            if isinstance(sample.get("phase"), str)
        }
    )
    by_phase = {phase: phase_summary(samples, phase) for phase in phases}
    baseline = by_phase.get("baseline_without_server") or {}
    loaded = by_phase.get("loaded_idle") or {}
    workload_phases = [
        phase
        for phase in phases
        if phase.startswith("workload_")
    ]
    workload_samples = [
        sample
        for sample in samples
        if sample.get("phase") in workload_phases
    ]
    workload = summarize_samples(workload_samples)
    total_vram = safe_max(
        (sample.get("gpu") or {}).get("total_vram_mb")
        for sample in samples
        if (sample.get("gpu") or {}).get("gpu_telemetry_available") is True
    )
    peak_vram = workload.get("gpu_peak_vram_mb")
    return {
        "sample_count": len(samples),
        "phases": by_phase,
        "workload_combined": workload,
        "derived": {
            "loaded_idle_vram_delta_mb": delta(
                loaded.get("gpu_mean_vram_mb"),
                baseline.get("gpu_mean_vram_mb"),
            ),
            "loaded_idle_rss_delta_mb": delta(
                loaded.get("mean_ram_mb_pair"),
                baseline.get("mean_ram_mb_pair"),
            ),
            "loaded_idle_private_delta_mb": delta(
                loaded.get("mean_private_mb"),
                baseline.get("mean_private_mb"),
            ),
            "workload_vram_growth_over_loaded_idle_mb": delta(
                peak_vram,
                loaded.get("gpu_mean_vram_mb"),
            ),
            "peak_vram_headroom_mb": delta(total_vram, peak_vram),
        },
    }


def evaluate_gpu_offload_evidence(
    resource_summary: dict[str, Any],
    gpu_layers_argument: str,
    *,
    minimum_loaded_vram_delta_mb: float = 512.0,
) -> dict[str, Any]:
    normalized_layers = str(gpu_layers_argument).strip().lower()
    gpu_layers_requested = normalized_layers not in {
        "",
        "0",
        "none",
        "off",
        "false",
    }
    derived = resource_summary.get("derived") or {}
    workload = resource_summary.get("workload_combined") or {}
    loaded_delta = derived.get("loaded_idle_vram_delta_mb")
    workload_peak_utilization = workload.get(
        "gpu_peak_utilization_percent"
    )
    telemetry_available = workload.get("gpu_telemetry_available") is True
    loaded_delta_sufficient = (
        isinstance(loaded_delta, (int, float))
        and float(loaded_delta) >= minimum_loaded_vram_delta_mb
    )
    workload_gpu_active = (
        isinstance(workload_peak_utilization, (int, float))
        and float(workload_peak_utilization) > 0.0
    )
    verified = bool(
        gpu_layers_requested
        and telemetry_available
        and loaded_delta_sufficient
        and workload_gpu_active
    )
    reasons: list[str] = []
    if not gpu_layers_requested:
        reasons.append("gpu_layers_not_requested")
    if not telemetry_available:
        reasons.append("gpu_telemetry_unavailable_during_workload")
    if not loaded_delta_sufficient:
        reasons.append("loaded_vram_delta_below_threshold")
    if not workload_gpu_active:
        reasons.append("no_positive_gpu_utilization_sample_during_workload")
    return {
        "verified": verified,
        "gpu_layers_argument": str(gpu_layers_argument),
        "minimum_loaded_vram_delta_mb": minimum_loaded_vram_delta_mb,
        "baseline_to_loaded_idle_vram_delta_mb": loaded_delta,
        "workload_peak_gpu_utilization_percent": workload_peak_utilization,
        "gpu_telemetry_available_during_workload": telemetry_available,
        "reasons": reasons,
    }


def evaluate_idle_stability(
    telemetry_samples: list[dict[str, Any]],
    *,
    required_consecutive_samples: int = 4,
    max_gpu_utilization_percent: float = 10.0,
    max_vram_change_mb: float = 32.0,
) -> dict[str, Any]:
    if required_consecutive_samples <= 0:
        raise ValueError("required_consecutive_samples must be positive")
    if max_gpu_utilization_percent < 0:
        raise ValueError("max_gpu_utilization_percent must be non-negative")
    if max_vram_change_mb < 0:
        raise ValueError("max_vram_change_mb must be non-negative")

    usable = [
        sample
        for sample in telemetry_samples
        if sample.get("gpu_telemetry_available") is True
        and isinstance(sample.get("used_vram_mb"), (int, float))
        and isinstance(sample.get("gpu_utilization_percent"), (int, float))
    ]
    tail = usable[-required_consecutive_samples:]
    utilization_values = [
        float(sample["gpu_utilization_percent"])
        for sample in tail
    ]
    vram_values = [float(sample["used_vram_mb"]) for sample in tail]
    enough_samples = len(tail) == required_consecutive_samples
    peak_utilization = safe_max(utilization_values)
    vram_span = (
        round(max(vram_values) - min(vram_values), 6)
        if vram_values
        else None
    )
    utilization_stable = bool(
        enough_samples
        and peak_utilization is not None
        and peak_utilization <= max_gpu_utilization_percent
    )
    vram_stable = bool(
        enough_samples
        and vram_span is not None
        and vram_span <= max_vram_change_mb
    )
    reasons: list[str] = []
    if not enough_samples:
        reasons.append("insufficient_gpu_telemetry_samples")
    if enough_samples and not utilization_stable:
        reasons.append("gpu_utilization_above_idle_threshold")
    if enough_samples and not vram_stable:
        reasons.append("vram_not_stable")
    return {
        "stable": bool(enough_samples and utilization_stable and vram_stable),
        "required_consecutive_samples": required_consecutive_samples,
        "usable_sample_count": len(usable),
        "evaluated_sample_count": len(tail),
        "max_gpu_utilization_percent": max_gpu_utilization_percent,
        "observed_peak_gpu_utilization_percent": peak_utilization,
        "max_vram_change_mb": max_vram_change_mb,
        "observed_vram_span_mb": vram_span,
        "reasons": reasons,
    }


def wait_for_idle_stability(
    *,
    timeout_seconds: float,
    sample_interval_seconds: float,
    required_consecutive_samples: int,
    max_gpu_utilization_percent: float,
    max_vram_change_mb: float,
) -> dict[str, Any]:
    if timeout_seconds <= 0:
        raise ValueError("timeout_seconds must be positive")
    if sample_interval_seconds <= 0:
        raise ValueError("sample_interval_seconds must be positive")

    started = time.monotonic()
    telemetry_samples: list[dict[str, Any]] = []
    last_evaluation: dict[str, Any] | None = None
    while time.monotonic() - started < timeout_seconds:
        telemetry = collect_gpu_telemetry()
        telemetry_samples.append(telemetry)
        last_evaluation = evaluate_idle_stability(
            telemetry_samples,
            required_consecutive_samples=required_consecutive_samples,
            max_gpu_utilization_percent=max_gpu_utilization_percent,
            max_vram_change_mb=max_vram_change_mb,
        )
        if last_evaluation["stable"]:
            return {
                **last_evaluation,
                "elapsed_seconds": round(time.monotonic() - started, 6),
                "telemetry_samples": telemetry_samples,
            }
        time.sleep(sample_interval_seconds)

    raise TimeoutError(
        "GPU idle stabilization timeout: "
        + json.dumps(last_evaluation or {}, ensure_ascii=False, sort_keys=True)
    )


def flatten_sample(sample: dict[str, Any]) -> dict[str, Any]:
    gpu = sample.get("gpu") if isinstance(sample.get("gpu"), dict) else {}
    return {
        "timestamp": sample.get("timestamp"),
        "elapsed_seconds": sample.get("elapsed_seconds"),
        "phase": sample.get("phase"),
        "server_pid": sample.get("server_pid"),
        "psutil_available": sample.get("psutil_available"),
        "pair_rss_mb": sample.get("pair_rss_mb"),
        "pair_private_mb": sample.get("pair_private_mb"),
        "pair_cpu_percent_raw": sample.get("pair_cpu_percent"),
        "pair_cpu_percent_normalized": sample.get(
            "pair_cpu_percent_normalized"
        ),
        "system_cpu_percent": sample.get("system_cpu_percent"),
        "system_ram_total_mb": sample.get("system_ram_total_mb"),
        "system_ram_available_mb": sample.get("system_ram_available_mb"),
        "system_ram_used_mb": sample.get("system_ram_used_mb"),
        "active_llama_server_processes": sample.get(
            "active_llama_server_processes"
        ),
        "gpu_telemetry_available": gpu.get("gpu_telemetry_available"),
        "gpu_name": gpu.get("gpu_name"),
        "gpu_driver_version": gpu.get("driver_version"),
        "gpu_total_vram_mb": gpu.get("total_vram_mb"),
        "gpu_used_vram_mb": gpu.get("used_vram_mb"),
        "gpu_utilization_percent": gpu.get("gpu_utilization_percent"),
        "gpu_memory_utilization_percent": gpu.get(
            "gpu_memory_utilization_percent"
        ),
        "gpu_temperature_c": gpu.get("temperature_c"),
        "gpu_power_draw_w": gpu.get("power_draw_w"),
        "error": sample.get("error") or gpu.get("error") or gpu.get("reason"),
    }


def write_resource_csv(samples: list[dict[str, Any]], path: Path) -> None:
    rows = [flatten_sample(sample) for sample in samples]
    fieldnames = list(flatten_sample({}).keys())
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(rows)


def output_file_hashes(out_dir: Path) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for path in sorted(item for item in out_dir.iterdir() if item.is_file()):
        if path.name == "evidence_manifest.json":
            continue
        rows.append(
            {
                "file": path.name,
                "bytes": path.stat().st_size,
                "sha256": sha256_file(path),
            }
        )
    return rows


def extract_assistant_content(payload: dict[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError(
            "Missing assistant content at choices[0].message.content"
        ) from exc
    if not isinstance(content, str):
        raise ValueError("Assistant content is not a string")
    return content


def request_record_summary(records: list[dict[str, Any]]) -> dict[str, Any]:
    measured = [
        record
        for record in records
        if record.get("request_kind") == "measured"
    ]
    per_case: dict[str, Any] = {}
    for case_id in [str(spec["case_id"]) for spec in CASE_SPECS]:
        selected = [
            record for record in measured if record.get("case_id") == case_id
        ]
        successful = [
            record for record in selected if record.get("success") is True
        ]
        wall_ms = [
            float(record["wall_time_ms"])
            for record in successful
            if isinstance(record.get("wall_time_ms"), (int, float))
        ]
        prompt_tokens = [
            record.get("usage", {}).get("prompt_tokens")
            for record in successful
        ]
        completion_tokens = [
            record.get("usage", {}).get("completion_tokens")
            for record in successful
        ]
        prompt_tps = [
            record.get("llama_timings", {}).get("prompt_per_second")
            for record in successful
        ]
        predicted_tps = [
            record.get("llama_timings", {}).get("predicted_per_second")
            for record in successful
        ]
        per_case[case_id] = {
            "requested": len(selected),
            "succeeded": len(successful),
            "failed": len(selected) - len(successful),
            "token_budget_met_count": sum(
                1
                for record in successful
                if record.get("token_budget_met") is True
            ),
            "wall_time_ms": {
                "mean": safe_mean(wall_ms),
                "p50": percentile(wall_ms, 0.50),
                "p95": percentile(wall_ms, 0.95),
                "min": safe_min(wall_ms),
                "max": safe_max(wall_ms),
            },
            "prompt_tokens": {
                "mean": safe_mean(prompt_tokens),
                "min": safe_min(prompt_tokens),
                "max": safe_max(prompt_tokens),
            },
            "completion_tokens": {
                "mean": safe_mean(completion_tokens),
                "min": safe_min(completion_tokens),
                "max": safe_max(completion_tokens),
            },
            "llama_tokens_per_second": {
                "prompt_mean": safe_mean(prompt_tps),
                "predicted_mean": safe_mean(predicted_tps),
            },
        }
    return {
        "measured_request_count": len(measured),
        "successful_request_count": sum(
            1 for record in measured if record.get("success") is True
        ),
        "failed_request_count": sum(
            1 for record in measured if record.get("success") is not True
        ),
        "token_budget_met_count": sum(
            1 for record in measured if record.get("token_budget_met") is True
        ),
        "per_case": per_case,
    }


def wait_for_models(
    *,
    client: Any,
    models_url: str,
    process: subprocess.Popen[Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"llama-server exited during startup with code {process.returncode}"
            )
        try:
            response = client.get(models_url)
            response.raise_for_status()
            payload = response.json()
            if isinstance(payload, dict):
                return payload
            last_error = "models response was not a JSON object"
        except Exception as exc:
            last_error = str(exc) or exc.__class__.__name__
        time.sleep(0.25)
    raise TimeoutError(
        f"llama-server readiness timeout after {timeout_seconds}s: {last_error}"
    )


def wait_for_health(
    *,
    client: Any,
    health_url: str,
    process: subprocess.Popen[Any],
    timeout_seconds: float,
) -> dict[str, Any]:
    deadline = time.monotonic() + timeout_seconds
    last_error: str | None = None
    while time.monotonic() < deadline:
        if process.poll() is not None:
            raise RuntimeError(
                f"llama-server exited during health polling with code {process.returncode}"
            )
        try:
            response = client.get(health_url)
            if 200 <= response.status_code < 300:
                return {
                    "status_code": response.status_code,
                    "body_preview": response.text[:200],
                }
            last_error = f"HTTP {response.status_code}: {response.text[:200]}"
        except Exception as exc:
            last_error = str(exc) or exc.__class__.__name__
        time.sleep(0.25)
    raise TimeoutError(
        f"llama-server health timeout after {timeout_seconds}s: {last_error}"
    )


def endpoint_is_live(client: Any, models_url: str) -> bool:
    try:
        response = client.get(models_url)
        return response.status_code < 500
    except Exception:
        return False


def model_ids_from_response(payload: dict[str, Any]) -> list[str]:
    data = payload.get("data")
    if not isinstance(data, list):
        return []
    return [
        str(item.get("id"))
        for item in data
        if isinstance(item, dict) and isinstance(item.get("id"), str)
    ]


def post_chat(
    *,
    client: Any,
    endpoint: str,
    payload: dict[str, Any],
    request_id: str,
    request_kind: str,
    case_id: str,
    run_index: int,
) -> dict[str, Any]:
    started_at = now_utc_iso()
    started_perf = time.perf_counter()
    response_payload: dict[str, Any] | None = None
    error_type: str | None = None
    error_message: str | None = None
    success = False
    status_code: int | None = None
    try:
        response = client.post(endpoint, json=payload)
        status_code = response.status_code
        response.raise_for_status()
        decoded = response.json()
        if not isinstance(decoded, dict):
            raise ValueError("chat response was not a JSON object")
        response_payload = decoded
        extract_assistant_content(decoded)
        success = True
    except Exception as exc:
        error_type = exc.__class__.__name__
        error_message = str(exc) or exc.__class__.__name__
    wall_time_ms = round((time.perf_counter() - started_perf) * 1000.0, 6)
    usage = (
        response_payload.get("usage")
        if isinstance(response_payload, dict)
        and isinstance(response_payload.get("usage"), dict)
        else {}
    )
    timings = (
        response_payload.get("timings")
        if isinstance(response_payload, dict)
        and isinstance(response_payload.get("timings"), dict)
        else {}
    )
    completion_tokens = usage.get("completion_tokens")
    max_tokens = payload.get("max_tokens")
    return {
        "request_id": request_id,
        "request_kind": request_kind,
        "case_id": case_id,
        "run_index": run_index,
        "started_at": started_at,
        "finished_at": now_utc_iso(),
        "success": success,
        "status_code": status_code,
        "error_type": error_type,
        "error_message": error_message,
        "wall_time_ms": wall_time_ms,
        "usage": {
            "prompt_tokens": (
                usage.get("prompt_tokens")
                if isinstance(usage.get("prompt_tokens"), int)
                else None
            ),
            "completion_tokens": (
                completion_tokens
                if isinstance(completion_tokens, int)
                else None
            ),
            "total_tokens": (
                usage.get("total_tokens")
                if isinstance(usage.get("total_tokens"), int)
                else None
            ),
        },
        "llama_timings": {
            key: timings.get(key)
            if isinstance(timings.get(key), (int, float))
            else None
            for key in (
                "prompt_n",
                "prompt_ms",
                "prompt_per_second",
                "predicted_n",
                "predicted_ms",
                "predicted_per_second",
            )
        },
        "token_budget_met": (
            success
            and isinstance(completion_tokens, int)
            and isinstance(max_tokens, int)
            and completion_tokens == max_tokens
        ),
        "finish_reason": (
            response_payload.get("choices", [{}])[0].get("finish_reason")
            if isinstance(response_payload, dict)
            and isinstance(response_payload.get("choices"), list)
            and response_payload.get("choices")
            and isinstance(response_payload["choices"][0], dict)
            else None
        ),
        "response": response_payload,
    }


def terminate_process(process: subprocess.Popen[Any]) -> dict[str, Any]:
    initial_return_code = process.poll()
    if initial_return_code is not None:
        return {
            "initiated_by_harness": False,
            "method": "already_exited",
            "forced_kill": False,
            "return_code": initial_return_code,
            "process_stopped": True,
        }

    process.terminate()
    method = "terminate"
    forced_kill = False
    try:
        process.wait(timeout=15)
    except subprocess.TimeoutExpired:
        process.kill()
        process.wait(timeout=10)
        method = "kill_after_terminate_timeout"
        forced_kill = True
    return {
        "initiated_by_harness": True,
        "method": method,
        "forced_kill": forced_kill,
        "return_code": process.returncode,
        "process_stopped": process.poll() is not None,
    }


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a deterministic single-model llama-server GPU resource "
            "harness with baseline, loading, idle, warmup and workload phases."
        )
    )
    parser.add_argument("--model-id", required=True)
    parser.add_argument("--model-path", required=True)
    parser.add_argument("--server-path", required=True)
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--host", default="127.0.0.1")
    parser.add_argument("--port", type=int, default=8080)
    parser.add_argument("--ctx-size", type=int, default=12288)
    parser.add_argument("--gpu-layers", default="999")
    parser.add_argument("--parallel", type=int, default=1)
    parser.add_argument("--jinja", action="store_true")
    parser.add_argument("--reasoning", choices=("off", "none", "on", "auto"))
    parser.add_argument("--server-log-verbosity", type=int)
    parser.add_argument("--expected-model-bytes", type=int)
    parser.add_argument("--expected-model-sha256")
    parser.add_argument("--expected-offloaded-layers")
    parser.add_argument("--require-startup-alias", action="store_true")
    parser.add_argument("--sample-interval-seconds", type=float, default=0.5)
    parser.add_argument("--baseline-seconds", type=float, default=3.0)
    parser.add_argument("--loaded-idle-seconds", type=float, default=5.0)
    parser.add_argument(
        "--idle-stabilization-timeout-seconds",
        type=float,
        default=30.0,
    )
    parser.add_argument("--idle-stable-samples", type=int, default=4)
    parser.add_argument(
        "--idle-max-gpu-utilization-percent",
        type=float,
        default=10.0,
    )
    parser.add_argument("--idle-max-vram-change-mb", type=float, default=32.0)
    parser.add_argument("--post-idle-seconds", type=float, default=2.0)
    parser.add_argument("--warmup-runs", type=int, default=3)
    parser.add_argument("--runs-per-case", type=int, default=10)
    parser.add_argument("--timeout-seconds", type=float, default=180.0)
    parser.add_argument("--force", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    args = build_parser().parse_args(argv)
    if args.port <= 0:
        raise ValueError("--port must be positive")
    args.host = validate_local_host(args.host)
    if args.parallel != 1:
        raise ValueError("This harness requires --parallel 1")
    if str(args.gpu_layers).strip().lower() in {
        "",
        "0",
        "none",
        "off",
        "false",
    }:
        raise ValueError(
            "This harness requires explicit GPU offload; --gpu-layers must be non-zero"
        )
    if args.warmup_runs < 0 or args.runs_per_case <= 0:
        raise ValueError("warmup runs must be >= 0 and runs per case must be > 0")
    if args.idle_stabilization_timeout_seconds <= 0:
        raise ValueError("idle stabilization timeout must be positive")
    if args.idle_stable_samples <= 0:
        raise ValueError("idle stable samples must be positive")
    if args.idle_max_gpu_utilization_percent < 0:
        raise ValueError("idle GPU utilization threshold must be non-negative")
    if args.idle_max_vram_change_mb < 0:
        raise ValueError("idle VRAM change threshold must be non-negative")

    model_path = Path(args.model_path).resolve()
    server_path = Path(args.server_path).resolve()
    out_dir = Path(args.out_dir).resolve()
    model_file_validation = validate_model_file(
        model_path,
        expected_bytes=args.expected_model_bytes,
        expected_sha256=args.expected_model_sha256,
    )
    if not server_path.is_file():
        raise FileNotFoundError(server_path)
    if not port_is_free(args.host, args.port):
        raise RuntimeError(
            f"Port is not free before harness startup: {args.host}:{args.port}"
        )
    running_servers = find_llama_server_processes()
    if running_servers:
        pids = [item.get("pid") for item in running_servers]
        raise RuntimeError(
            f"llama-server process already running before harness startup: {pids}"
        )
    prepare_output_dir(out_dir, args.force)

    corpus = build_corpus()
    write_json(out_dir / "corpus.json", corpus)
    requests_path = out_dir / "requests.jsonl"
    responses_path = out_dir / "responses.jsonl"
    samples_path = out_dir / "resource_samples.jsonl"
    stdout_path = out_dir / "server_stdout.log"
    stderr_path = out_dir / "server_stderr.log"

    base_url = f"http://{args.host}:{args.port}"
    health_url = f"{base_url}/health"
    models_url = f"{base_url}/v1/models"
    chat_endpoint = f"{base_url}/v1/chat/completions"
    server_args = build_server_args(
        server_path=server_path,
        model_path=model_path,
        model_id=args.model_id,
        host=args.host,
        port=args.port,
        ctx_size=args.ctx_size,
        gpu_layers=str(args.gpu_layers),
        parallel=args.parallel,
        jinja=args.jinja,
        reasoning=args.reasoning,
        server_log_verbosity=args.server_log_verbosity,
    )
    manifest = {
        "schema_version": "deterministic_gpu_resource_harness_v1",
        "created_at": now_utc_iso(),
        "project_commit": subprocess.run(
            ["git", "rev-parse", "--short", "HEAD"],
            cwd=PROJECT_ROOT,
            text=True,
            capture_output=True,
            check=False,
        ).stdout.strip()
        or None,
        "model_id": args.model_id,
        "model_path": str(model_path),
        "model_file_validation": model_file_validation,
        "server_path": str(server_path),
        "server_args": server_args[1:],
        "base_url": base_url,
        "health_url": health_url,
        "ctx_size": args.ctx_size,
        "gpu_layers": str(args.gpu_layers),
        "parallel": args.parallel,
        "jinja": args.jinja,
        "reasoning": args.reasoning,
        "server_log_verbosity": args.server_log_verbosity,
        "expected_offloaded_layers": args.expected_offloaded_layers,
        "sample_interval_seconds": args.sample_interval_seconds,
        "baseline_seconds": args.baseline_seconds,
        "loaded_idle_seconds": args.loaded_idle_seconds,
        "idle_stabilization": {
            "timeout_seconds": args.idle_stabilization_timeout_seconds,
            "required_consecutive_samples": args.idle_stable_samples,
            "max_gpu_utilization_percent": (
                args.idle_max_gpu_utilization_percent
            ),
            "max_vram_change_mb": args.idle_max_vram_change_mb,
        },
        "post_idle_seconds": args.post_idle_seconds,
        "warmup_runs": args.warmup_runs,
        "runs_per_case": args.runs_per_case,
        "platform": platform.platform(),
        "python_version": sys.version,
        "cases": [
            {
                key: case[key]
                for key in (
                    "case_id",
                    "payload_words",
                    "payload_character_count",
                    "max_tokens",
                    "target_prompt_tokens",
                    "messages_sha256",
                )
            }
            for case in corpus
        ],
        "limitations": [
            "Prompt token targets are approximate; actual server usage is recorded.",
            "GPU process memory is not required because Windows WDDM may omit it.",
            "The harness measures one server and one model at a time.",
            "Capacity and concurrency are not measured.",
        ],
    }
    write_json(out_dir / "manifest.json", manifest)
    write_json(out_dir / "server_command.json", build_server_command_payload(server_args))

    sampler = PhaseSampler(interval_seconds=args.sample_interval_seconds)
    process: subprocess.Popen[Any] | None = None
    stdout_handle = stdout_path.open("w", encoding="utf-8")
    stderr_handle = stderr_path.open("w", encoding="utf-8")
    request_records: list[dict[str, Any]] = []
    models_payload: dict[str, Any] | None = None
    health_payload: dict[str, Any] | None = None
    smoke_record: dict[str, Any] | None = None
    idle_stabilization: dict[str, Any] | None = None
    shutdown_result: dict[str, Any] | None = None
    fatal_error: dict[str, Any] | None = None

    import httpx

    client = httpx.Client(timeout=args.timeout_seconds, trust_env=False)
    sampler.set_phase("baseline_without_server")
    sampler.start()
    try:
        if endpoint_is_live(client, models_url):
            raise RuntimeError(
                f"Endpoint is already live before baseline: {models_url}"
            )

        time.sleep(args.baseline_seconds)

        sampler.set_phase("server_loading")
        process = subprocess.Popen(
            server_args,
            cwd=PROJECT_ROOT,
            stdout=stdout_handle,
            stderr=stderr_handle,
            text=True,
        )
        sampler.set_server_pid(process.pid)
        health_payload = wait_for_health(
            client=client,
            health_url=health_url,
            process=process,
            timeout_seconds=args.timeout_seconds,
        )
        write_json(out_dir / "health_response.json", health_payload)
        models_payload = wait_for_models(
            client=client,
            models_url=models_url,
            process=process,
            timeout_seconds=args.timeout_seconds,
        )
        write_json(out_dir / "models_response.json", models_payload)
        model_ids = model_ids_from_response(models_payload)
        if args.model_id not in model_ids:
            raise RuntimeError(
                f"Expected model id {args.model_id!r}; received {model_ids!r}"
            )

        idle_stabilization = wait_for_idle_stability(
            timeout_seconds=args.idle_stabilization_timeout_seconds,
            sample_interval_seconds=args.sample_interval_seconds,
            required_consecutive_samples=args.idle_stable_samples,
            max_gpu_utilization_percent=(
                args.idle_max_gpu_utilization_percent
            ),
            max_vram_change_mb=args.idle_max_vram_change_mb,
        )
        write_json(out_dir / "idle_stabilization.json", idle_stabilization)

        sampler.set_phase("loaded_idle")
        time.sleep(args.loaded_idle_seconds)

        sampler.set_phase("direct_smoke")
        smoke_payload = {
            "model": args.model_id,
            "messages": [
                {
                    "role": "system",
                    "content": (
                        "Return exactly one raw JSON object. "
                        "No markdown and no prose."
                    ),
                },
                {
                    "role": "user",
                    "content": (
                        'Return exactly: {"action_name":"finish",'
                        '"parameters":{}}'
                    ),
                },
            ],
            "temperature": 0,
            "max_tokens": 64,
            "seed": 0,
            "cache_prompt": False,
        }
        append_jsonl(
            requests_path,
            {
                "request_id": "direct_smoke",
                "request_kind": "smoke",
                "case_id": "smoke",
                "run_index": 1,
                "payload": smoke_payload,
            },
        )
        smoke_record = post_chat(
            client=client,
            endpoint=chat_endpoint,
            payload=smoke_payload,
            request_id="direct_smoke",
            request_kind="smoke",
            case_id="smoke",
            run_index=1,
        )
        append_jsonl(responses_path, smoke_record)
        write_json(out_dir / "direct_smoke.json", smoke_record)
        if not smoke_record["success"]:
            raise RuntimeError(
                f"Direct smoke request failed: {smoke_record['error_message']}"
            )
        smoke_content = extract_assistant_content(smoke_record["response"])
        try:
            smoke_json = json.loads(smoke_content)
        except Exception as exc:
            raise RuntimeError(f"Direct smoke output is not JSON: {exc}") from exc
        if smoke_json != {"action_name": "finish", "parameters": {}}:
            raise RuntimeError(
                f"Direct smoke output mismatch: {smoke_content!r}"
            )

        short_case = next(case for case in corpus if case["case_id"] == "short")
        sampler.set_phase("warmup")
        for run_index in range(1, args.warmup_runs + 1):
            payload = {
                "model": args.model_id,
                "messages": short_case["messages"],
                "temperature": 0,
                "max_tokens": 32,
                "seed": 0,
                "cache_prompt": False,
                "ignore_eos": True,
            }
            request_id = f"warmup_{run_index:03d}"
            append_jsonl(
                requests_path,
                {
                    "request_id": request_id,
                    "request_kind": "warmup",
                    "case_id": "short",
                    "run_index": run_index,
                    "payload": payload,
                },
            )
            record = post_chat(
                client=client,
                endpoint=chat_endpoint,
                payload=payload,
                request_id=request_id,
                request_kind="warmup",
                case_id="short",
                run_index=run_index,
            )
            request_records.append(record)
            append_jsonl(responses_path, record)
            if not record["success"]:
                raise RuntimeError(
                    f"Warmup request failed: {record['error_message']}"
                )

        for case in corpus:
            case_id = str(case["case_id"])
            sampler.set_phase(f"workload_{case_id}")
            for run_index in range(1, args.runs_per_case + 1):
                payload = {
                    "model": args.model_id,
                    "messages": case["messages"],
                    "temperature": 0,
                    "max_tokens": int(case["max_tokens"]),
                    "seed": 0,
                    "cache_prompt": False,
                    "ignore_eos": True,
                }
                request_id = f"{case_id}_{run_index:03d}"
                append_jsonl(
                    requests_path,
                    {
                        "request_id": request_id,
                        "request_kind": "measured",
                        "case_id": case_id,
                        "run_index": run_index,
                        "payload": payload,
                    },
                )
                record = post_chat(
                    client=client,
                    endpoint=chat_endpoint,
                    payload=payload,
                    request_id=request_id,
                    request_kind="measured",
                    case_id=case_id,
                    run_index=run_index,
                )
                request_records.append(record)
                append_jsonl(responses_path, record)
                if not record["success"]:
                    raise RuntimeError(
                        f"Measured request {request_id} failed: "
                        f"{record['error_message']}"
                    )

        sampler.set_phase("post_workload_idle")
        time.sleep(args.post_idle_seconds)
    except Exception as exc:
        fatal_error = {
            "timestamp": now_utc_iso(),
            "error_type": exc.__class__.__name__,
            "error_message": str(exc) or exc.__class__.__name__,
        }
        write_json(out_dir / "error.json", fatal_error)
    finally:
        sampler.stop()
        if process is not None:
            shutdown_result = terminate_process(process)
        client.close()
        stdout_handle.close()
        stderr_handle.close()

    for sample in sampler.samples:
        append_jsonl(samples_path, sample)
    write_resource_csv(sampler.samples, out_dir / "resource_samples.csv")
    resource_summary = build_resource_summary(sampler.samples)
    write_json(out_dir / "resource_summary.json", resource_summary)

    benchmark_requests = request_record_summary(request_records)
    measured_expected = args.runs_per_case * len(CASE_SPECS)
    gpu_offload_evidence = evaluate_gpu_offload_evidence(
        resource_summary,
        str(args.gpu_layers),
    )
    validation_failures: list[str] = []
    if not gpu_offload_evidence["verified"]:
        validation_failures.append("actual_gpu_offload_not_verified")
    if not isinstance(idle_stabilization, dict) or not idle_stabilization.get(
        "stable"
    ):
        validation_failures.append("loaded_idle_not_stabilized")
    if isinstance(shutdown_result, dict) and not shutdown_result.get(
        "process_stopped"
    ):
        validation_failures.append("server_process_not_stopped")
    if not port_is_free(args.host, args.port):
        validation_failures.append("server_port_not_released")
    remaining_servers = find_llama_server_processes()
    if remaining_servers:
        validation_failures.append("llama_server_process_still_running")
    startup_log_evidence = read_startup_log_evidence(
        stderr_path,
        expected_alias=args.model_id,
    )
    validation_failures.extend(
        validate_startup_log_evidence(
            startup_log_evidence,
            expected_offloaded_layers=args.expected_offloaded_layers,
            require_alias=args.require_startup_alias,
            expected_context_size=args.ctx_size,
            require_reasoning_off=args.reasoning == "off",
        )
    )
    status = (
        "succeeded"
        if fatal_error is None
        and not validation_failures
        and benchmark_requests["successful_request_count"] == measured_expected
        and benchmark_requests["token_budget_met_count"] == measured_expected
        else "failed"
    )
    benchmark_summary = {
        "schema_version": "deterministic_gpu_resource_harness_summary_v1",
        "status": status,
        "error": fatal_error,
        "validation_failures": validation_failures,
        "model_id": args.model_id,
        "project_commit": manifest["project_commit"],
        "server_pid": process.pid if process is not None else None,
        "server_return_code": (
            shutdown_result.get("return_code")
            if isinstance(shutdown_result, dict)
            else (process.returncode if process is not None else None)
        ),
        "shutdown": shutdown_result,
        "post_shutdown": {
            "port_released": port_is_free(args.host, args.port),
            "remaining_llama_server_processes": remaining_servers,
        },
        "startup_log_evidence": startup_log_evidence,
        "health_response": health_payload,
        "idle_stabilization": idle_stabilization,
        "models_response_model_ids": (
            model_ids_from_response(models_payload)
            if isinstance(models_payload, dict)
            else []
        ),
        "direct_smoke_success": (
            smoke_record.get("success")
            if isinstance(smoke_record, dict)
            else False
        ),
        "requests": benchmark_requests,
        "resources": resource_summary,
        "gpu_runtime_measured": gpu_offload_evidence["verified"],
        "actual_gpu_offload_evidence": {
            **gpu_offload_evidence,
            "server_stdout_log": str(stdout_path),
            "server_stderr_log": str(stderr_path),
        },
        "output_files": sorted(
            path.name for path in out_dir.iterdir() if path.is_file()
        ),
        "created_at": now_utc_iso(),
    }
    write_json(out_dir / "benchmark_summary.json", benchmark_summary)

    optional_replay_flags = build_optional_replay_flags(
        jinja=args.jinja,
        reasoning=args.reasoning,
        expected_model_bytes=args.expected_model_bytes,
        expected_model_sha256=args.expected_model_sha256,
        expected_offloaded_layers=args.expected_offloaded_layers,
        require_startup_alias=args.require_startup_alias,
        server_log_verbosity=args.server_log_verbosity,
    )
    replay = f"""# Replay

```powershell
.\\.venv\\Scripts\\python.exe scripts\\run_deterministic_gpu_resource_harness.py `
  --model-id {args.model_id} `
  --model-path "{model_path}" `
  --server-path "{server_path}" `
  --port {args.port} `
  --ctx-size {args.ctx_size} `
  --gpu-layers {args.gpu_layers} `
  --parallel 1 `
{optional_replay_flags}\
  --idle-stabilization-timeout-seconds {args.idle_stabilization_timeout_seconds} `
  --idle-stable-samples {args.idle_stable_samples} `
  --idle-max-gpu-utilization-percent {args.idle_max_gpu_utilization_percent} `
  --idle-max-vram-change-mb {args.idle_max_vram_change_mb} `
  --out-dir "{out_dir}"
```
"""
    (out_dir / "replay_commands.md").write_text(replay, encoding="utf-8")
    evidence_manifest = {
        "schema_version": "deterministic_gpu_resource_harness_evidence_manifest_v1",
        "created_at": now_utc_iso(),
        "model_id": args.model_id,
        "status": status,
        "benchmark_summary_file": "benchmark_summary.json",
        "resource_summary_file": "resource_summary.json",
        "raw_samples_file": "resource_samples.jsonl",
        "server_stdout_log": "server_stdout.log",
        "server_stderr_log": "server_stderr.log",
        "server_command_file": "server_command.json",
        "model_file_validation": model_file_validation,
        "server_startup_validation": startup_log_evidence,
        "post_shutdown": benchmark_summary["post_shutdown"],
        "files": output_file_hashes(out_dir),
    }
    write_json(out_dir / "evidence_manifest.json", evidence_manifest)
    print(json.dumps(benchmark_summary, ensure_ascii=False, sort_keys=True))
    return 0 if status == "succeeded" else 1


if __name__ == "__main__":
    raise SystemExit(main())
