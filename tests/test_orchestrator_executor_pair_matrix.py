from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.agent.orchestrator_executor_pair_matrix import (
    PairMatrixAggregate,
    PairSpec,
    aggregate_pair_result,
    compare_pair_results,
    failed_pair_result,
    parse_pair_specs,
    prototype_pair_rank_score,
    rank_pairs,
    validate_repeated_run_protocol,
    write_failed_pair_artifact,
    write_pair_matrix_report,
    write_reused_pair_reference,
)
from src.agent.repeated_orchestrator_executor_trials import (
    RepeatedGroupRunConfig,
    run_repeated_group_trials,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "configs/multi_agent_scenarios/office_developer_group_basic.json"


def _json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _fake_repeated(tmp_path: Path, orchestrator: str, executor: str, label: str) -> Path:
    root = tmp_path / label
    run_repeated_group_trials(
        RepeatedGroupRunConfig(
            project_root=PROJECT_ROOT,
            mode="fake",
            models_config_path="configs/evaluation_models.json",
            scenario_path=SCENARIO,
            out_root=str(root),
            label=label,
            trials=2,
            orchestrator_model_id=orchestrator,
            executor_model_id=executor,
            max_group_steps=1,
            max_steps_per_agent=1,
            orchestrator_repair_attempts=1,
            repair_attempts=1,
            execute_actions=False,
            force=True,
        )
    )
    return root


def test_parse_pair_specs() -> None:
    pairs = parse_pair_specs("second_model:first_model,first_model:second_model")

    assert [pair.pair_id for pair in pairs] == [
        "second_model__first_model",
        "first_model__second_model",
    ]
    assert pairs[0].label == "second_model->first_model"


def test_aggregate_two_fake_pair_results_and_write_report(tmp_path: Path) -> None:
    first_root = _fake_repeated(tmp_path, "second_model", "first_model", "pair_a")
    second_root = _fake_repeated(tmp_path, "first_model", "first_model", "pair_b")
    first = aggregate_pair_result(first_root, project_root=PROJECT_ROOT)
    second = aggregate_pair_result(second_root, project_root=PROJECT_ROOT)

    result = compare_pair_results(
        [first, second],
        comparison_id="test_matrix",
        scenario_path=SCENARIO,
        mode="fake",
        trials_per_pair=2,
    )
    write_pair_matrix_report(result, tmp_path / "matrix")

    assert result.rankings[0]["prototype_pair_rank_score"] >= result.rankings[1]["prototype_pair_rank_score"]
    assert (tmp_path / "matrix" / "pair_matrix_comparison.json").exists()
    assert (tmp_path / "matrix" / "pair_matrix_comparison.md").exists()
    assert (tmp_path / "matrix" / "pair_rankings.csv").exists()


def test_rank_pairs_prefers_better_quality() -> None:
    weak = PairMatrixAggregate(
        orchestrator_model_id="first_model",
        executor_model_id="first_model",
        completed_trial_count=3,
        mean_pair_quality_score=0.6,
        mean_execution_success_rate=1.0,
        mean_final_validation_success_rate=1.0,
        mean_plan_valid_rate=1.0,
        std_pair_quality_score=0.1,
        mean_wall_time_ms=5000,
    )
    strong = PairMatrixAggregate(
        orchestrator_model_id="second_model",
        executor_model_id="first_model",
        completed_trial_count=3,
        mean_pair_quality_score=0.9,
        mean_execution_success_rate=1.0,
        mean_final_validation_success_rate=1.0,
        mean_plan_valid_rate=1.0,
        std_pair_quality_score=0.01,
        mean_wall_time_ms=2000,
    )

    weak_result = failed_pair_result(PairSpec(orchestrator_model_id="first_model", executor_model_id="first_model"), "weak", "")
    weak_result.status = "completed"
    weak_result.aggregate = weak
    weak_result.prototype_pair_rank_score = prototype_pair_rank_score(weak)
    strong_result = failed_pair_result(PairSpec(orchestrator_model_id="second_model", executor_model_id="first_model"), "strong", "")
    strong_result.status = "completed"
    strong_result.aggregate = strong
    strong_result.prototype_pair_rank_score = prototype_pair_rank_score(strong)

    rankings = rank_pairs([weak_result, strong_result])

    assert rankings[0]["pair"] == "second_model->first_model"


def test_reused_existing_pair_run_reference(tmp_path: Path) -> None:
    source_root = _fake_repeated(tmp_path, "second_model", "first_model", "source")
    spec = PairSpec(orchestrator_model_id="second_model", executor_model_id="first_model")
    protocol_match, notes = validate_repeated_run_protocol(
        source_root,
        spec,
        scenario_path=SCENARIO,
        mode="fake",
        trials=2,
        max_group_steps=1,
        max_steps_per_agent=1,
        orchestrator_repair_attempts=1,
        repair_attempts=1,
        execute_actions=False,
    )
    ref_root = tmp_path / "matrix" / "pairs" / spec.pair_id
    write_reused_pair_reference(ref_root, spec, str(source_root), protocol_match=protocol_match, protocol_notes=notes)
    result = aggregate_pair_result(
        ref_root,
        project_root=PROJECT_ROOT,
        reference_source="reused",
        original_artifact_path=str(source_root),
        protocol_match=protocol_match,
        protocol_notes=notes,
    )

    assert protocol_match is True
    assert result.status == "reused"
    assert _json(ref_root / "reused_pair_run.json")["protocol_match"] is True


def test_failed_pair_is_preserved(tmp_path: Path) -> None:
    spec = PairSpec(orchestrator_model_id="first_model", executor_model_id="missing_model")
    result = failed_pair_result(spec, tmp_path / "failed_pair", "RuntimeError: model missing")

    write_failed_pair_artifact(tmp_path / "failed_pair", result)

    assert result.status == "failed"
    assert (tmp_path / "failed_pair" / "pair_error.json").exists()
    assert _json(tmp_path / "failed_pair" / "pair_error.json")["error_message"] == "RuntimeError: model missing"


def test_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/run_orchestrator_executor_pair_matrix.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--pairs" in completed.stdout
    assert "--existing-pair-run" in completed.stdout


def test_cli_fake_pair_matrix_writes_outputs_without_servers(tmp_path: Path) -> None:
    out_root = tmp_path / "fake_pair_matrix"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_orchestrator_executor_pair_matrix.py",
            "--mode",
            "fake",
            "--models-config",
            "configs/evaluation_models.json",
            "--scenario",
            SCENARIO,
            "--out-root",
            str(out_root),
            "--label",
            "fake_pair_matrix",
            "--pairs",
            "second_model:first_model,first_model:first_model",
            "--trials",
            "2",
            "--max-group-steps",
            "1",
            "--max-steps-per-agent",
            "1",
            "--orchestrator-repair-attempts",
            "1",
            "--repair-attempts",
            "1",
            "--execute-actions",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert (out_root / "pair_matrix_comparison.json").exists()
    assert (out_root / "pair_matrix_comparison.md").exists()
    assert (out_root / "pair_rankings.csv").exists()
    assert _json(out_root / "pairs" / "second_model__first_model" / "server_run.json")["servers"] == []
    assert _json(out_root / "pairs" / "first_model__first_model" / "server_run.json")["servers"] == []
