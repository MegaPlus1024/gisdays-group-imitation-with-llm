from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

import pytest

from src.agent.orchestrator_executor_runtime_probe import PairSpec
from src.agent.orchestrator_executor_stress_probe import (
    RuntimeProfile,
    StressProbeConfig,
    aggregate_batch_metrics,
    compute_summary_by_pair_profile,
    load_runtime_profiles,
    run_bounded_stress_probe,
    select_runtime_profiles,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_parse_runtime_profiles(tmp_path: Path) -> None:
    profiles_path = tmp_path / "runtime_profiles.json"
    profiles_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "profile_id": "strict_cpu",
                        "description": "CPU only",
                        "server_params": {"cpu_only": True},
                        "expected_gpu_usage": "none",
                        "confidence": "medium",
                    }
                ]
            }
        ),
        encoding="utf-8",
    )

    profiles = load_runtime_profiles(tmp_path, profiles_path)

    assert profiles["strict_cpu"].server_params["cpu_only"] is True
    assert profiles["strict_cpu"].expected_gpu_usage == "none"


def test_reject_unknown_profile(tmp_path: Path) -> None:
    profiles = {"known": RuntimeProfile("known", "known profile")}

    with pytest.raises(ValueError, match="Unknown runtime profile"):
        select_runtime_profiles(profiles, ["missing"])


def test_aggregate_batch_metrics_computes_throughput_and_failures() -> None:
    pair = PairSpec("second_model", "first_model")
    profile = RuntimeProfile("strict_cpu", "CPU", expected_gpu_usage="none")
    run_records = [
        {
            "status": "completed",
            "aggregate": {
                "mean_wall_time_ms": 1000.0,
                "mean_pair_quality_score": 0.8,
                "mean_execution_success_rate": 1.0,
                "total_errors": 0,
                "common_failure_modes": {},
            },
        },
        {
            "status": "failed",
            "error_type": "SyntheticError",
            "aggregate": {
                "mean_wall_time_ms": 2000.0,
                "mean_pair_quality_score": 0.7,
                "mean_execution_success_rate": 0.5,
                "total_errors": 2,
                "common_failure_modes": {"validation_failed": 2},
            },
        },
    ]
    samples = [
        {
            "psutil_available": True,
            "pair_rss_mb": 300.0,
            "pair_cpu_percent": 40.0,
            "system_ram_available_mb": 1000.0,
            "active_llama_server_processes": 2,
            "processes": [{"rss_mb": 150.0}, {"rss_mb": 180.0}],
            "gpu": {
                "gpu_telemetry_available": True,
                "gpu_name": "Test GPU",
                "total_vram_mb": 24000.0,
                "used_vram_mb": 1000.0,
                "gpu_utilization_percent": 10.0,
                "gpu_memory_utilization_percent": 5.0,
                "temperature_c": 40.0,
                "power_draw_w": 20.0,
            },
        }
    ]

    metrics = aggregate_batch_metrics(
        pair=pair,
        profile=profile,
        concurrency_level=2,
        planned_runs=2,
        run_records=run_records,
        samples=samples,
        server_error=None,
        batch_wall_time_ms=60000.0,
        max_group_steps=2,
    )

    assert metrics["runs_completed"] == 1
    assert metrics["runs_failed"] == 1
    assert metrics["throughput_runs_per_minute"] == 1.0
    assert metrics["throughput_group_steps_per_minute"] == 2.0
    assert metrics["validation_failure_count"] == 2
    assert metrics["peak_ram_mb_per_server"] == 180.0
    assert metrics["stability_verdict"] == "unstable"


def test_compute_max_stable_concurrency() -> None:
    rows = [
        {
            "pair": "second_model->second_model",
            "profile_id": "gpu_full_offload",
            "concurrency_level": 1,
            "stability_verdict": "stable",
            "mean_pair_quality_score": 0.9,
            "mean_wall_time_ms": 1000.0,
            "total_errors": 0,
            "peak_cpu_percent_total": 40.0,
            "peak_gpu_utilization_percent": 50.0,
        },
        {
            "pair": "second_model->second_model",
            "profile_id": "gpu_full_offload",
            "concurrency_level": 2,
            "stability_verdict": "stable",
            "mean_pair_quality_score": 0.85,
            "mean_wall_time_ms": 1500.0,
            "total_errors": 1,
            "peak_cpu_percent_total": 45.0,
            "peak_gpu_utilization_percent": 60.0,
        },
    ]

    summary = compute_summary_by_pair_profile(rows)

    assert summary[0]["max_stable_concurrency_observed"] == 2
    assert summary[0]["quality_degradation_at_concurrency_2"]["absolute"] == 0.05
    assert summary[0]["latency_degradation_at_concurrency_2"]["ratio"] == 1.5


def test_failed_run_is_preserved_without_real_server(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agent.orchestrator_executor_stress_probe as stress

    profiles_path = tmp_path / "runtime_profiles.json"
    profiles_path.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "profile_id": "cpu_requested_device_none",
                        "description": "CPU requested",
                        "server_params": {"cpu_only": True},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    (tmp_path / "scenario.json").write_text(
        json.dumps({"metadata": {"fixture_paths": []}}),
        encoding="utf-8",
    )

    def fail_run(*args: object, **kwargs: object) -> object:
        raise RuntimeError("synthetic stress failure")

    def fail_if_server_starts(*args: object, **kwargs: object) -> object:
        raise AssertionError("server start should not be called in fake mode")

    monkeypatch.setattr(stress, "run_repeated_group_trials", fail_run)
    monkeypatch.setattr(stress, "_start_managed_servers", fail_if_server_starts)
    result = run_bounded_stress_probe(
        StressProbeConfig(
            project_root=tmp_path,
            mode="fake",
            models_config_path="configs/evaluation_models.json",
            runtime_profiles_config_path=str(profiles_path),
            scenario_path="scenario.json",
                out_root="stress",
                label="stress",
                pairs=[PairSpec("second_model", "first_model")],
                profile_ids=["cpu_requested_device_none"],
                concurrency_levels=[1],
                runs_per_level=1,
                force=True,
            )
        )

    batch = result["batches"][0]
    run_error = Path(batch["artifact_path"]) / "g001" / "run_error.json"
    assert batch["metrics"]["runs_failed"] == 1
    assert batch["batch_slug"].startswith("b1_")
    assert run_error.exists()
    assert "synthetic stress failure" in run_error.read_text(encoding="utf-8")


def test_stress_probe_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/run_orchestrator_executor_stress_probe.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--runtime-profiles-config" in completed.stdout
    assert "--concurrency-levels" in completed.stdout
