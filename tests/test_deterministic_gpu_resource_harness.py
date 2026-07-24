from __future__ import annotations

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts"))

from run_deterministic_gpu_resource_harness import (
    build_corpus,
    PhaseSampler,
    build_resource_summary,
    evaluate_gpu_offload_evidence,
    evaluate_idle_stability,
    flatten_sample,
    percentile,
    request_record_summary,
)


def test_build_corpus_is_deterministic_and_ordered() -> None:
    first = build_corpus()
    second = build_corpus()

    assert first == second
    assert [item["case_id"] for item in first] == [
        "short",
        "medium",
        "long",
    ]
    assert [item["payload_words"] for item in first] == [448, 1856, 7424]
    assert [item["max_tokens"] for item in first] == [64, 128, 128]
    assert len({item["messages_sha256"] for item in first}) == 3


def test_percentile_interpolates() -> None:
    values = [1.0, 2.0, 3.0, 4.0]

    assert percentile(values, 0.0) == 1.0
    assert percentile(values, 0.5) == 2.5
    assert percentile(values, 0.95) == 3.85
    assert percentile(values, 1.0) == 4.0
    assert percentile([], 0.5) is None


def test_request_record_summary_groups_measured_cases() -> None:
    records = [
        {
            "request_kind": "warmup",
            "case_id": "short",
            "success": True,
            "wall_time_ms": 1.0,
            "token_budget_met": True,
            "usage": {"prompt_tokens": 10, "completion_tokens": 5},
            "llama_timings": {},
        },
        {
            "request_kind": "measured",
            "case_id": "short",
            "success": True,
            "wall_time_ms": 100.0,
            "token_budget_met": True,
            "usage": {"prompt_tokens": 500, "completion_tokens": 64},
            "llama_timings": {
                "prompt_per_second": 1000.0,
                "predicted_per_second": 50.0,
            },
        },
        {
            "request_kind": "measured",
            "case_id": "short",
            "success": False,
            "wall_time_ms": 200.0,
            "token_budget_met": False,
            "usage": {},
            "llama_timings": {},
        },
    ]

    summary = request_record_summary(records)

    assert summary["measured_request_count"] == 2
    assert summary["successful_request_count"] == 1
    assert summary["failed_request_count"] == 1
    assert summary["token_budget_met_count"] == 1
    assert summary["per_case"]["short"]["wall_time_ms"]["p50"] == 100.0
    assert summary["per_case"]["short"]["prompt_tokens"]["mean"] == 500.0


def test_resource_summary_uses_pre_server_baseline() -> None:
    samples = [
        {
            "phase": "baseline_without_server",
            "psutil_available": True,
            "pair_rss_mb": 0.0,
            "pair_private_mb": 0.0,
            "pair_cpu_percent": 0.0,
            "pair_cpu_percent_normalized": 0.0,
            "system_cpu_percent": 2.0,
            "system_ram_used_mb": 1000.0,
            "system_ram_available_mb": 9000.0,
            "active_llama_server_processes": 0,
            "gpu": {
                "gpu_telemetry_available": True,
                "gpu_name": "GPU",
                "driver_version": "1",
                "total_vram_mb": 24000.0,
                "used_vram_mb": 1000.0,
                "gpu_utilization_percent": 0.0,
                "gpu_memory_utilization_percent": 4.0,
                "temperature_c": 35.0,
                "power_draw_w": 20.0,
            },
        },
        {
            "phase": "loaded_idle",
            "psutil_available": True,
            "pair_rss_mb": 8000.0,
            "pair_private_mb": 8200.0,
            "pair_cpu_percent": 5.0,
            "pair_cpu_percent_normalized": 0.2,
            "system_cpu_percent": 3.0,
            "system_ram_used_mb": 9000.0,
            "system_ram_available_mb": 1000.0,
            "active_llama_server_processes": 1,
            "gpu": {
                "gpu_telemetry_available": True,
                "gpu_name": "GPU",
                "driver_version": "1",
                "total_vram_mb": 24000.0,
                "used_vram_mb": 19000.0,
                "gpu_utilization_percent": 1.0,
                "gpu_memory_utilization_percent": 80.0,
                "temperature_c": 40.0,
                "power_draw_w": 30.0,
            },
        },
        {
            "phase": "workload_short",
            "psutil_available": True,
            "pair_rss_mb": 8100.0,
            "pair_private_mb": 8300.0,
            "pair_cpu_percent": 30.0,
            "pair_cpu_percent_normalized": 1.2,
            "system_cpu_percent": 10.0,
            "system_ram_used_mb": 9100.0,
            "system_ram_available_mb": 900.0,
            "active_llama_server_processes": 1,
            "gpu": {
                "gpu_telemetry_available": True,
                "gpu_name": "GPU",
                "driver_version": "1",
                "total_vram_mb": 24000.0,
                "used_vram_mb": 19500.0,
                "gpu_utilization_percent": 100.0,
                "gpu_memory_utilization_percent": 82.0,
                "temperature_c": 70.0,
                "power_draw_w": 150.0,
            },
        },
    ]

    summary = build_resource_summary(samples)

    assert summary["derived"]["loaded_idle_vram_delta_mb"] == 18000.0
    assert (
        summary["derived"]["workload_vram_growth_over_loaded_idle_mb"]
        == 500.0
    )
    assert summary["derived"]["peak_vram_headroom_mb"] == 4500.0
    assert (
        summary["phases"]["workload_short"][
            "peak_cpu_percent_normalized"
        ]
        == 1.2
    )


def test_flatten_sample_extracts_gpu_fields() -> None:
    row = flatten_sample(
        {
            "timestamp": "now",
            "phase": "loaded_idle",
            "pair_rss_mb": 1.0,
            "gpu": {
                "gpu_telemetry_available": True,
                "gpu_name": "GPU",
                "used_vram_mb": 2.0,
                "power_draw_w": 3.0,
            },
        }
    )

    assert row["phase"] == "loaded_idle"
    assert row["gpu_name"] == "GPU"
    assert row["gpu_used_vram_mb"] == 2.0
    assert row["gpu_power_draw_w"] == 3.0

def test_gpu_offload_evidence_requires_vram_delta_and_activity() -> None:
    resource_summary = {
        "derived": {"loaded_idle_vram_delta_mb": 18000.0},
        "workload_combined": {
            "gpu_telemetry_available": True,
            "gpu_peak_utilization_percent": 100.0,
        },
    }

    verified = evaluate_gpu_offload_evidence(resource_summary, "999")
    no_layers = evaluate_gpu_offload_evidence(resource_summary, "0")
    no_delta = evaluate_gpu_offload_evidence(
        {
            "derived": {"loaded_idle_vram_delta_mb": 128.0},
            "workload_combined": {
                "gpu_telemetry_available": True,
                "gpu_peak_utilization_percent": 100.0,
            },
        },
        "999",
    )
    no_activity = evaluate_gpu_offload_evidence(
        {
            "derived": {"loaded_idle_vram_delta_mb": 18000.0},
            "workload_combined": {
                "gpu_telemetry_available": True,
                "gpu_peak_utilization_percent": 0.0,
            },
        },
        "999",
    )

    assert verified["verified"] is True
    assert verified["reasons"] == []
    assert no_layers["verified"] is False
    assert "gpu_layers_not_requested" in no_layers["reasons"]
    assert no_delta["verified"] is False
    assert "loaded_vram_delta_below_threshold" in no_delta["reasons"]
    assert no_activity["verified"] is False
    assert (
        "no_positive_gpu_utilization_sample_during_workload"
        in no_activity["reasons"]
    )


def test_phase_sampler_starts_in_baseline_phase() -> None:
    sampler = PhaseSampler(interval_seconds=0.5)

    assert sampler._snapshot_state() == ("baseline_without_server", None)


def test_idle_stability_requires_quiet_gpu_and_stable_vram() -> None:
    stable_samples = [
        {
            "gpu_telemetry_available": True,
            "used_vram_mb": value,
            "gpu_utilization_percent": utilization,
        }
        for value, utilization in [
            (19103.0, 1.0),
            (19104.0, 0.0),
            (19103.0, 2.0),
            (19104.0, 0.0),
        ]
    ]
    busy_samples = stable_samples[:-1] + [
        {
            "gpu_telemetry_available": True,
            "used_vram_mb": 19104.0,
            "gpu_utilization_percent": 98.0,
        }
    ]
    moving_vram_samples = stable_samples[:-1] + [
        {
            "gpu_telemetry_available": True,
            "used_vram_mb": 19200.0,
            "gpu_utilization_percent": 0.0,
        }
    ]

    stable = evaluate_idle_stability(stable_samples)
    busy = evaluate_idle_stability(busy_samples)
    moving = evaluate_idle_stability(moving_vram_samples)

    assert stable["stable"] is True
    assert stable["reasons"] == []
    assert busy["stable"] is False
    assert "gpu_utilization_above_idle_threshold" in busy["reasons"]
    assert moving["stable"] is False
    assert "vram_not_stable" in moving["reasons"]
