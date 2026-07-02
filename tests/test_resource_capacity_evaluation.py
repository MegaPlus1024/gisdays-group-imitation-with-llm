from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.agent.resource_capacity_evaluation import (
    CapacityFormulaInputs,
    build_resource_capacity_evaluation,
    calculate_capacity_estimate,
    load_resource_summaries_from_repeated_trials,
    write_resource_capacity_evaluation,
)


def test_formula_calculation_ram_bound() -> None:
    estimate = calculate_capacity_estimate(
        CapacityFormulaInputs(
            model_id="m",
            available_ram_mb=8000,
            reserved_system_ram_mb=1000,
            effective_available_ram_mb=7000,
            per_agent_model_ram_mb=3000,
            shared_model_ram_mb=3000,
            per_agent_runtime_overhead_mb=500,
            average_cpu_load_percent_per_agent=5,
            target_cpu_utilization_limit_percent=70,
        )
    )

    assert estimate.ram_bound == 2
    assert estimate.cpu_bound == 14
    assert estimate.estimated_concurrent_agents == 2
    assert estimate.bottleneck == "ram"


def test_formula_calculation_cpu_bound() -> None:
    estimate = calculate_capacity_estimate(
        CapacityFormulaInputs(
            model_id="m",
            available_ram_mb=64000,
            reserved_system_ram_mb=4096,
            effective_available_ram_mb=59904,
            per_agent_model_ram_mb=1000,
            shared_model_ram_mb=1000,
            per_agent_runtime_overhead_mb=100,
            average_cpu_load_percent_per_agent=20,
            target_cpu_utilization_limit_percent=70,
        )
    )

    assert estimate.ram_bound > estimate.cpu_bound
    assert estimate.cpu_bound == 3
    assert estimate.estimated_concurrent_agents == 3
    assert estimate.bottleneck == "cpu"


def test_capacity_estimate_handles_missing_cpu_rss_with_warnings(tmp_path: Path) -> None:
    config = _write_models_config(tmp_path)
    root = _write_repeated_root(tmp_path, include_cpu_rss=False)
    result = build_resource_capacity_evaluation(
        model_ids=["first_model"],
        models_config_path=config,
        scenario_roots={"scenario": root},
        cross_scenario_analysis_path=None,
        output_label="test",
        project_root=tmp_path,
    )

    estimate = result.capacity_estimates["first_model"]
    assert estimate.inputs.per_agent_runtime_overhead_mb == 256.0
    assert "missing_process_rss_delta_using_default_per_agent_overhead_256_mb" in estimate.estimate.warnings


def test_repeated_trials_resource_summaries_load_from_temp_fixture(tmp_path: Path) -> None:
    root = _write_repeated_root(tmp_path)
    observations = load_resource_summaries_from_repeated_trials(root, scenario_id="scenario")

    assert len(observations) == 2
    assert observations[0].average_selection_latency_ms == 150.0


def test_aggregation_computes_mean_latency_correctly(tmp_path: Path) -> None:
    config = _write_models_config(tmp_path)
    root = _write_repeated_root(tmp_path)
    result = build_resource_capacity_evaluation(
        model_ids=["first_model"],
        models_config_path=config,
        scenario_roots={"scenario": root},
        cross_scenario_analysis_path=None,
        output_label="test",
        project_root=tmp_path,
    )

    assert result.per_model_resource_summary["first_model"].mean_selection_latency_ms == 150.0


def test_runtime_probe_results_not_run_when_no_probe(tmp_path: Path) -> None:
    config = _write_models_config(tmp_path)
    root = _write_repeated_root(tmp_path)
    result = build_resource_capacity_evaluation(
        model_ids=["first_model"],
        models_config_path=config,
        scenario_roots={"scenario": root},
        cross_scenario_analysis_path=None,
        output_label="test",
        probe_runtime=False,
        project_root=tmp_path,
    )

    assert result.runtime_probe_results.status == "not_run"
    assert result.runtime_probe_results.probe_runtime_requested is False


def test_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/evaluate_resource_capacity.py", "--help"],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--repeated-trials-root" in completed.stdout


def test_cli_writes_resource_capacity_outputs_from_fake_fixture(tmp_path: Path) -> None:
    config = _write_models_config(tmp_path)
    root = _write_repeated_root(tmp_path)
    out = tmp_path / "out"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/evaluate_resource_capacity.py",
            "--models-config",
            str(config),
            "--model-ids",
            "first_model",
            "--repeated-trials-root",
            f"scenario={root}",
            "--out-dir",
            str(out),
            "--label",
            "test_resource_capacity",
            "--no-probe-runtime",
            "--force",
        ],
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (out / "resource_capacity_evaluation.json").exists()
    assert (out / "capacity_estimate.md").exists()


def test_recommendation_readiness_limited_without_multi_agent_load_test(tmp_path: Path) -> None:
    config = _write_models_config(tmp_path)
    root = _write_repeated_root(tmp_path)
    result = build_resource_capacity_evaluation(
        model_ids=["first_model"],
        models_config_path=config,
        scenario_roots={"scenario": root},
        cross_scenario_analysis_path=None,
        output_label="test",
        project_root=tmp_path,
    )
    out = tmp_path / "out"
    write_resource_capacity_evaluation(result, out, force=True)

    payload = json.loads((out / "resource_capacity_evaluation.json").read_text(encoding="utf-8"))
    readiness = payload["recommendation_readiness_resource_component"]
    assert readiness["resource_component_status"] == "limited_estimate_available"
    assert readiness["true_concurrent_multi_agent_load_test"] is False


def _write_models_config(tmp_path: Path) -> Path:
    model_file = tmp_path / "models" / "gguf" / "first_model.gguf"
    model_file.parent.mkdir(parents=True)
    model_file.write_bytes(b"0" * 1024 * 1024)
    config = tmp_path / "models.json"
    config.write_text(
        json.dumps(
            {
                "schema_version": "evaluation_models_v1",
                "models": [
                    {
                        "model_id": "first_model",
                        "display_name": "First",
                        "model_name": "first.gguf",
                        "gguf_path": "models/gguf/first_model.gguf",
                        "quantization": "Q4_K_M",
                        "parameter_size": "1B",
                        "runtime": "llama.cpp / llama-server",
                        "base_url": "http://127.0.0.1:8080/v1",
                        "api_style": "openai_compatible",
                        "expected_cpu_only": True,
                        "ctx_size": 4096,
                        "timeout_seconds": 120.0,
                        "temperature": 0.0,
                        "max_tokens": 512,
                        "enabled": True,
                        "notes": [],
                    }
                ],
            }
        ),
        encoding="utf-8",
    )
    return config


def _write_repeated_root(tmp_path: Path, *, include_cpu_rss: bool = True) -> Path:
    root = tmp_path / "repeated"
    for trial in ["trial_001", "trial_002"]:
        trial_dir = root / "runs" / "first_model" / trial
        trial_dir.mkdir(parents=True)
        (trial_dir / "manifest.json").write_text(
            json.dumps({"model": {"model_id": "first_model"}}),
            encoding="utf-8",
        )
        start = {"system_cpu_percent": 1.0, "system_ram_used_mb": 1000.0}
        end = {"system_cpu_percent": 6.0, "system_ram_used_mb": 1010.0}
        if include_cpu_rss:
            start["process_rss_mb"] = 40.0
            end["process_rss_mb"] = 50.0
        (trial_dir / "resource_summary.json").write_text(
            json.dumps(
                {
                    "wall_time_ms": 500.0,
                    "resource_start": start,
                    "resource_end": end,
                    "per_step_latency_ms": [
                        {"selection_latency_ms": 100.0, "total_step_latency_ms": 110.0},
                        {"selection_latency_ms": 200.0, "total_step_latency_ms": 210.0},
                    ],
                }
            ),
            encoding="utf-8",
        )
    return root
