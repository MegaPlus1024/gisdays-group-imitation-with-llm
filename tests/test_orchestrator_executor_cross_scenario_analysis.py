from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.agent.orchestrator_executor_cross_scenario_analysis import compare_pair_matrices


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_matrix(root: Path, label: str, best_pair: str, score: float, quality: float, status: str = "completed") -> None:
    root.mkdir(parents=True, exist_ok=True)
    pair_id = best_pair.replace("->", "__")
    payload = {
        "comparison_id": label,
        "best_observed_pair": best_pair,
        "rankings": [
            {
                "rank": 1,
                "pair": best_pair,
                "pair_id": pair_id,
                "status": status,
                "completed_trials": 3 if status != "failed" else 0,
                "failed_trials": 0 if status != "failed" else 3,
                "mean_pair_quality_score": quality if status != "failed" else 0.0,
                "mean_execution_success_rate": 1.0 if status != "failed" else 0.0,
                "common_failure_modes": {} if status != "failed" else {"orchestrator_plan_parse_failed": 3},
                "prototype_pair_rank_score": score if status != "failed" else 0.0,
            }
        ],
    }
    (root / "pair_matrix_comparison.json").write_text(json.dumps(payload), encoding="utf-8")


def test_compare_pair_matrices_writes_outputs_and_stability(tmp_path: Path) -> None:
    simple = tmp_path / "simple"
    heavy = tmp_path / "heavy"
    _write_matrix(simple, "simple", "second_model->first_model", 0.95, 0.89)
    _write_matrix(heavy, "heavy", "second_model->first_model", 0.91, 0.84)

    result = compare_pair_matrices(
        simple_matrix_root=simple,
        heavy_matrix_root=heavy,
        out_dir=tmp_path / "cross",
        force=True,
    )

    assert result["simple_scenario_best_pair"] == "second_model->first_model"
    assert result["heavy_scenario_best_pair"] == "second_model->first_model"
    assert result["pairs"][0]["stability_verdict"] == "stable_strong"
    assert (tmp_path / "cross" / "cross_scenario_pair_comparison.json").exists()
    assert (tmp_path / "cross" / "pair_stability.csv").exists()


def test_cross_scenario_cli_help_works() -> None:
    completed = subprocess.run(
        [sys.executable, "scripts/compare_orchestrator_executor_pair_matrices.py", "--help"],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0
    assert "--simple-matrix-root" in completed.stdout
    assert "--heavy-matrix-root" in completed.stdout
