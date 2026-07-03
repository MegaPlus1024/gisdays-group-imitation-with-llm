from __future__ import annotations

import json
from pathlib import Path

from src.agent.orchestrator_executor_runtime_probe import PairSpec
from src.agent.orchestrator_executor_stress_probe import (
    RuntimeProfile,
    StressProbeConfig,
    _batch_artifact_dir,
    _enrich_run_record_diagnostics,
    _group_artifact_root,
    _short_batch_slug,
    _trial_workspace_path,
    inspect_scenario_fixtures,
    load_runtime_profiles,
    run_bounded_stress_probe,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def test_short_stress_layout_keeps_workspace_path_below_windows_limit() -> None:
    pair = PairSpec("second_model", "first_model")
    profile = RuntimeProfile("gpu_full_offload", "GPU")
    out_root = PROJECT_ROOT / "experiments" / "multi_agent" / "orchestrator_executor" / "bounded_stress_candidate_pairs_v2"

    old_workspace_file = (
        PROJECT_ROOT
        / "experiments"
        / "multi_agent"
        / "orchestrator_executor"
        / "bounded_stress_candidate_pairs_v1"
        / pair.pair_id
        / profile.profile_id
        / "concurrency_1"
        / "group_runs"
        / "run_001"
        / "runs"
        / "trial_001"
        / "workspace"
        / "office_agent_1_executor_note.md"
    )
    batch_dir = _batch_artifact_dir(out_root, _short_batch_slug(pair, profile, 1))
    workspace_file = _trial_workspace_path(_group_artifact_root(batch_dir, 1)) / "office_agent_1_executor_note.md"

    assert len(str(old_workspace_file)) >= 260
    assert len(str(workspace_file)) < 240


def test_inspect_scenario_fixtures_reports_missing_paths(tmp_path: Path) -> None:
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps({"metadata": {"fixture_paths": ["configs/missing_fixture.md"]}}),
        encoding="utf-8",
    )

    status = inspect_scenario_fixtures(tmp_path, scenario)

    assert status["all_present"] is False
    assert status["missing_fixture_paths"] == ["configs/missing_fixture.md"]
    assert status["fixture_strategy"] == "shared_read_only_project_root"


def test_missing_fixture_blocks_batch_with_clear_stage(tmp_path: Path) -> None:
    profiles = tmp_path / "runtime_profiles.json"
    profiles.write_text(
        json.dumps(
            {
                "profiles": [
                    {
                        "profile_id": "gpu_full_offload",
                        "description": "GPU",
                        "server_params": {"gpu_layers": "999"},
                    }
                ]
            }
        ),
        encoding="utf-8",
    )
    scenario = tmp_path / "scenario.json"
    scenario.write_text(
        json.dumps({"metadata": {"fixture_paths": ["configs/missing_fixture.md"]}}),
        encoding="utf-8",
    )

    result = run_bounded_stress_probe(
        StressProbeConfig(
            project_root=tmp_path,
            mode="fake",
            models_config_path="configs/evaluation_models.json",
            runtime_profiles_config_path=str(profiles),
            scenario_path=str(scenario),
            out_root="stress",
            label="stress",
            pairs=[PairSpec("second_model", "first_model")],
            profile_ids=["gpu_full_offload"],
            concurrency_levels=[1],
            runs_per_level=1,
            force=True,
        )
    )

    batch = result["batches"][0]
    assert batch["status"] == "blocked"
    assert batch["failed_stage"] == "scenario_fixture_preflight"
    assert batch["failure_reason"] == "missing_scenario_fixture"
    assert batch["missing_path"] == "configs/missing_fixture.md"
    assert batch["metrics"]["runs_started"] == 0


def test_long_path_file_not_found_is_classified_as_workspace_harness_bug() -> None:
    missing_path = str(
        PROJECT_ROOT
        / "experiments"
        / "multi_agent"
        / "orchestrator_executor"
        / "bounded_stress_candidate_pairs_v1"
        / "second_model__first_model"
        / "gpu_full_offload"
        / "concurrency_1"
        / "group_runs"
        / "run_001"
        / "runs"
        / "trial_001"
        / "workspace"
        / "office_agent_1_executor_note.md"
    )
    record = _enrich_run_record_diagnostics(
        {
            "status": "failed",
            "failure_modes": {"FileNotFoundError": 1},
            "trial_index": [
                {
                    "error_message": f"[Errno 2] No such file or directory: '{missing_path}'",
                }
            ],
        }
    )

    assert record["failed_stage"] == "artifact_workspace_write"
    assert record["failure_reason"] == "windows_max_path_limit"
    assert record["missing_path"] == missing_path
    assert record["missing_path_length"] >= 260


def test_active_runtime_profiles_do_not_expose_strict_cpu() -> None:
    profiles = load_runtime_profiles(PROJECT_ROOT, "configs/runtime_profiles.json")

    assert "strict_cpu" not in profiles
    assert profiles["cpu_requested_device_none"].server_params["cpu_only"] is True
    assert profiles["cpu_requested_device_none"].confidence == "low"
