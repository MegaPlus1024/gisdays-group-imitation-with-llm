from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.agent.orchestrator_executor_runtime_probe import (
    PairSpec,
    RuntimeProbeConfig,
    ScenarioSpec,
    build_quality_cost_tradeoff,
    estimate_capacity,
    run_runtime_probe,
    summarize_samples,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_telemetry_aggregation_from_fake_samples() -> None:
    samples = [
        {
            "psutil_available": True,
            "pair_rss_mb": 100.0,
            "pair_cpu_percent": 12.5,
            "system_ram_available_mb": 1000.0,
            "active_llama_server_processes": 2,
            "gpu": {
                "gpu_telemetry_available": True,
                "gpu_name": "Test GPU",
                "driver_version": "1.0",
                "total_vram_mb": 24000.0,
                "used_vram_mb": 1000.0,
                "gpu_utilization_percent": 10.0,
                "gpu_memory_utilization_percent": 5.0,
                "temperature_c": 40.0,
                "power_draw_w": 20.0,
            },
        },
        {
            "psutil_available": True,
            "pair_rss_mb": 150.0,
            "pair_cpu_percent": 25.0,
            "system_ram_available_mb": 900.0,
            "active_llama_server_processes": 2,
            "gpu": {
                "gpu_telemetry_available": True,
                "gpu_name": "Test GPU",
                "driver_version": "1.0",
                "total_vram_mb": 24000.0,
                "used_vram_mb": 1250.0,
                "gpu_utilization_percent": 33.0,
                "gpu_memory_utilization_percent": 8.0,
                "temperature_c": 42.0,
                "power_draw_w": 30.0,
            },
        },
    ]

    summary = summarize_samples(samples)

    assert summary["sample_count"] == 2
    assert summary["peak_ram_mb_pair"] == 150.0
    assert summary["peak_cpu_percent_pair"] == 25.0
    assert summary["min_system_ram_available_mb"] == 900.0
    assert summary["gpu_telemetry_available"] is True
    assert summary["gpu_name"] == "Test GPU"
    assert summary["gpu_peak_vram_mb"] == 1250.0
    assert summary["gpu_peak_utilization_percent"] == 33.0


def test_capacity_estimate_formula_uses_pair_peak_ram() -> None:
    rows = [
        {
            "pair": "second_model->first_model",
            "scenario_agent_count": 4,
            "peak_ram_mb_pair": 2000.0,
            "peak_cpu_percent_pair": 40.0,
            "mean_wall_time_ms": 5000.0,
            "mean_group_step_time_ms": 2500.0,
            "completed_trials": 3,
        }
    ]
    estimates = estimate_capacity(rows, {"total_ram_mb": 12000.0})

    first = estimates[0]
    reserve_4096 = first["estimates_by_reserve_mb"]["4096"]
    assert reserve_4096["estimated_concurrent_pairs_by_ram"] == 3
    assert reserve_4096["estimated_agents_by_ram"] == 12
    assert first["confidence"] == "medium"


def test_quality_cost_ranking_prefers_lower_error_high_quality_pair() -> None:
    rows = [
        {
            "pair": "second_model->first_model",
            "mean_pair_quality_score": 0.82,
            "total_errors": 18,
            "peak_ram_mb_pair": 2200.0,
            "mean_wall_time_ms": 7000.0,
        },
        {
            "pair": "second_model->first_model",
            "mean_pair_quality_score": 0.90,
            "total_errors": 0,
            "peak_ram_mb_pair": 2200.0,
            "mean_wall_time_ms": 2000.0,
        },
        {
            "pair": "second_model->second_model",
            "mean_pair_quality_score": 0.88,
            "total_errors": 6,
            "peak_ram_mb_pair": 3000.0,
            "mean_wall_time_ms": 8000.0,
        },
    ]
    capacity = [
        {"pair": "second_model->first_model", "peak_ram_mb_pair": 2200.0},
        {"pair": "second_model->second_model", "peak_ram_mb_pair": 3000.0},
    ]

    tradeoff = build_quality_cost_tradeoff(rows, capacity)

    assert tradeoff["preliminary_quality_winner"] == "second_model->second_model"
    assert tradeoff["rankings"][0]["pair"] == "second_model->second_model"


def test_failed_probe_is_preserved_without_real_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agent.orchestrator_executor_runtime_probe as probe

    def fail_run(*args: object, **kwargs: object) -> object:
        raise RuntimeError("synthetic repeated-run failure")

    monkeypatch.setattr(probe, "run_repeated_group_trials", fail_run)
    out_root = tmp_path / "runtime_probe"
    config = RuntimeProbeConfig(
        project_root=tmp_path,
        mode="fake",
        models_config_path="configs/evaluation_models.json",
        out_root="runtime_probe",
        label="test_probe",
        pairs=[PairSpec("second_model", "first_model")],
        scenarios=[ScenarioSpec("simple", "configs/multi_agent_scenarios/office_developer_group_basic.json", 1, 768)],
        trials=1,
        manage_servers=False,
        force=True,
    )

    result = run_runtime_probe(config)

    assert result["runs"][0]["status"] == "blocked"
    assert (out_root / "simple_second_to_first" / "runtime_probe_blocker.json").exists()
    assert (out_root / "runtime_capacity_report.md").exists()


def test_runtime_probe_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/probe_orchestrator_executor_runtime.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--sample-interval-seconds" in completed.stdout
    assert "--pairs" in completed.stdout
