from __future__ import annotations

import csv
import json
import shutil
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


@dataclass(frozen=True)
class PairScenarioMetrics:
    pair: str
    pair_id: str
    scenario_label: str
    status: str
    rank: int | None
    completed_trials: int
    failed_trials: int
    mean_pair_quality_score: float | None
    mean_execution_success_rate: float | None
    prototype_pair_rank_score: float | None
    common_failure_modes: dict[str, int]


def load_pair_matrix(root: str | Path) -> dict[str, Any]:
    path = Path(root) / "pair_matrix_comparison.json"
    if not path.exists():
        raise FileNotFoundError(f"pair_matrix_comparison.json not found: {path}")
    return json.loads(path.read_text(encoding="utf-8"))


def compare_pair_matrices(
    *,
    simple_matrix_root: str | Path,
    heavy_matrix_root: str | Path,
    out_dir: str | Path,
    label: str = "cross_scenario_pair_matrix_v1",
    force: bool = False,
) -> dict[str, Any]:
    simple = load_pair_matrix(simple_matrix_root)
    heavy = load_pair_matrix(heavy_matrix_root)
    simple_rows = _metrics_by_pair(simple, "simple")
    heavy_rows = _metrics_by_pair(heavy, "heavy")
    pair_ids = sorted(set(simple_rows) | set(heavy_rows))

    rows = [
        _compare_pair(pair_id, simple_rows.get(pair_id), heavy_rows.get(pair_id))
        for pair_id in pair_ids
    ]
    rows.sort(
        key=lambda row: (
            row["scenarios_completed"],
            row["mean_rank_score_across_scenarios"] or 0.0,
            row["mean_quality_across_scenarios"] or 0.0,
        ),
        reverse=True,
    )
    best = rows[0]["pair"] if rows else None
    result = {
        "comparison_id": label,
        "generated_at": datetime.now(timezone.utc).isoformat(),
        "simple_matrix_root": str(simple_matrix_root),
        "heavy_matrix_root": str(heavy_matrix_root),
        "simple_scenario_best_pair": simple.get("best_observed_pair"),
        "heavy_scenario_best_pair": heavy.get("best_observed_pair"),
        "best_observed_pair_across_tested_scenarios": best,
        "pairs": rows,
        "limitations": [
            "Only two group scenarios are compared.",
            "This is not a production recommendation.",
            "No GPU runtime or stress benchmark is included.",
            "Rank score is prototype-only.",
        ],
    }
    write_cross_scenario_report(result, out_dir, force=force)
    return result


def write_cross_scenario_report(result: dict[str, Any], out_dir: str | Path, *, force: bool = False) -> Path:
    out_path = Path(out_dir)
    if out_path.exists():
        if not force:
            raise FileExistsError(f"Output directory already exists: {out_path}")
        shutil.rmtree(out_path)
    out_path.mkdir(parents=True, exist_ok=True)
    _write_json(out_path / "cross_scenario_pair_comparison.json", result)
    (out_path / "cross_scenario_pair_comparison.md").write_text(_markdown(result), encoding="utf-8")
    _write_pair_stability_csv(result["pairs"], out_path / "pair_stability.csv")
    (out_path / "README.md").write_text(
        "# Cross-Scenario Pair Matrix Comparison\n\n"
        f"- comparison_id: `{result['comparison_id']}`\n"
        f"- simple_scenario_best_pair: `{result.get('simple_scenario_best_pair')}`\n"
        f"- heavy_scenario_best_pair: `{result.get('heavy_scenario_best_pair')}`\n"
        f"- best_observed_pair_across_tested_scenarios: `{result.get('best_observed_pair_across_tested_scenarios')}`\n",
        encoding="utf-8",
    )
    return out_path


def _metrics_by_pair(matrix: dict[str, Any], scenario_label: str) -> dict[str, PairScenarioMetrics]:
    rows: dict[str, PairScenarioMetrics] = {}
    for item in matrix.get("rankings") or []:
        pair_id = str(item.get("pair_id") or item.get("pair") or "")
        if not pair_id:
            continue
        rows[pair_id] = PairScenarioMetrics(
            pair=str(item.get("pair") or pair_id),
            pair_id=pair_id,
            scenario_label=scenario_label,
            status=str(item.get("status") or "unknown"),
            rank=_int_or_none(item.get("rank")),
            completed_trials=_int(item.get("completed_trials")),
            failed_trials=_int(item.get("failed_trials")),
            mean_pair_quality_score=_number(item.get("mean_pair_quality_score")),
            mean_execution_success_rate=_number(item.get("mean_execution_success_rate")),
            prototype_pair_rank_score=_number(item.get("prototype_pair_rank_score")),
            common_failure_modes={str(k): _int(v) for k, v in (item.get("common_failure_modes") or {}).items()},
        )
    return rows


def _compare_pair(
    pair_id: str,
    simple: PairScenarioMetrics | None,
    heavy: PairScenarioMetrics | None,
) -> dict[str, Any]:
    present = [row for row in [simple, heavy] if row is not None]
    completed = [row for row in present if row.completed_trials > 0 and row.status not in {"failed", "skipped"}]
    simple_quality = simple.mean_pair_quality_score if simple else None
    heavy_quality = heavy.mean_pair_quality_score if heavy else None
    simple_exec = simple.mean_execution_success_rate if simple else None
    heavy_exec = heavy.mean_execution_success_rate if heavy else None
    quality_drop = _drop(simple_quality, heavy_quality)
    execution_drop = _drop(simple_exec, heavy_exec)
    failure_change = {
        "simple": simple.common_failure_modes if simple else {},
        "heavy": heavy.common_failure_modes if heavy else {},
    }
    return {
        "pair": present[0].pair if present else pair_id,
        "pair_id": pair_id,
        "scenarios_present": len(present),
        "scenarios_completed": len(completed),
        "mean_rank_score_across_scenarios": _mean([row.prototype_pair_rank_score for row in completed]),
        "mean_quality_across_scenarios": _mean([row.mean_pair_quality_score for row in completed]),
        "quality_drop_simple_to_heavy": quality_drop,
        "execution_success_drop_simple_to_heavy": execution_drop,
        "failure_mode_change": failure_change,
        "simple_status": simple.status if simple else None,
        "heavy_status": heavy.status if heavy else None,
        "stability_verdict": _stability_verdict(simple, heavy, quality_drop, execution_drop),
    }


def _stability_verdict(
    simple: PairScenarioMetrics | None,
    heavy: PairScenarioMetrics | None,
    quality_drop: float | None,
    execution_drop: float | None,
) -> str:
    if simple is None or heavy is None:
        return "insufficient_data"
    if heavy.completed_trials == 0 or heavy.status in {"failed", "skipped"}:
        return "degraded_on_heavy"
    if simple.completed_trials == 0:
        return "heavy_only_success"
    if (quality_drop is not None and quality_drop > 0.1) or (execution_drop is not None and execution_drop > 0.1):
        return "degraded_on_heavy"
    if (heavy.prototype_pair_rank_score or 0.0) >= 0.8:
        return "stable_strong"
    return "stable_but_low_confidence"


def _markdown(result: dict[str, Any]) -> str:
    lines = [
        "# Cross-Scenario Orchestrator/Executor Pair Comparison v1",
        "",
        "This report compares prototype pair-matrix results across the simple and heavy group scenarios. It names the best observed pair across tested scenarios, not a production recommendation.",
        "",
        f"- simple scenario best pair: `{result.get('simple_scenario_best_pair')}`",
        f"- heavy scenario best pair: `{result.get('heavy_scenario_best_pair')}`",
        f"- best observed pair across tested scenarios: `{result.get('best_observed_pair_across_tested_scenarios')}`",
        "",
        "| pair | scenarios_completed | mean_rank_score | mean_quality | quality_drop_simple_to_heavy | execution_drop_simple_to_heavy | stability_verdict |",
        "|---|---:|---:|---:|---:|---:|---|",
    ]
    for row in result.get("pairs") or []:
        lines.append(
            f"| `{row['pair']}` | {row['scenarios_completed']} | "
            f"{row['mean_rank_score_across_scenarios']} | {row['mean_quality_across_scenarios']} | "
            f"{row['quality_drop_simple_to_heavy']} | {row['execution_success_drop_simple_to_heavy']} | "
            f"`{row['stability_verdict']}` |"
        )
    lines.extend(
        [
            "",
            "## Limitations",
            "",
        ]
    )
    for limitation in result.get("limitations") or []:
        lines.append(f"- {limitation}")
    return "\n".join(lines) + "\n"


def _write_pair_stability_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "pair",
        "pair_id",
        "scenarios_completed",
        "mean_rank_score_across_scenarios",
        "mean_quality_across_scenarios",
        "quality_drop_simple_to_heavy",
        "execution_success_drop_simple_to_heavy",
        "stability_verdict",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _drop(simple: float | None, heavy: float | None) -> float | None:
    if simple is None or heavy is None:
        return None
    return round(simple - heavy, 6)


def _mean(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 6)


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


def _int_or_none(value: Any) -> int | None:
    if value is None:
        return None
    return _int(value)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
