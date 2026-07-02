from __future__ import annotations

import csv
import json
import math
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .model_behavior_comparison import (
    ModelComparisonMetric,
    ModelRunArtifact,
    load_model_run_artifact,
)


TrialStatus = Literal["completed", "failed"]


class RepeatedTrialSpec(BaseModel):
    model_id: str
    trial_id: str
    run_id: str
    artifact_path: str

    @field_validator("model_id", "trial_id", "run_id", "artifact_path")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("RepeatedTrialSpec fields must be non-empty.")
        return value


class RepeatedTrialResult(BaseModel):
    spec: RepeatedTrialSpec
    status: TrialStatus
    return_code: int | None = None
    error_message: str | None = None
    artifact: ModelRunArtifact | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class RepeatedTrialAggregate(BaseModel):
    model_id: str
    trial_count: int
    completed_trial_count: int
    failed_trial_count: int
    metrics: dict[str, Any]
    common_failure_modes: dict[str, int] = Field(default_factory=dict)
    most_common_actions: list[dict[str, Any]] = Field(default_factory=list)
    most_common_action_parameters: list[dict[str, Any]] = Field(default_factory=list)


class RepeatedTrialSeriesResult(BaseModel):
    model_id: str
    trials: list[RepeatedTrialResult] = Field(default_factory=list)
    aggregate: RepeatedTrialAggregate | None = None


class RepeatedTrialsComparison(BaseModel):
    comparison_id: str
    generated_at: str
    status: Literal["complete", "partial"]
    protocol_compatible: bool
    protocol_checks: list[dict[str, Any]]
    trial_index: list[dict[str, Any]]
    aggregates: dict[str, RepeatedTrialAggregate]
    metric_winners: list[ModelComparisonMetric]
    failure_modes: dict[str, Any]
    interpretation: dict[str, Any]
    limitations: list[str]


def load_trial_run_artifact(path: str | Path) -> ModelRunArtifact:
    return load_model_run_artifact(path)


def aggregate_trials_for_model(run_paths: list[str | Path], *, model_id: str | None = None) -> RepeatedTrialAggregate:
    trials: list[RepeatedTrialResult] = []
    for index, run_path in enumerate(run_paths, start=1):
        spec = RepeatedTrialSpec(
            model_id=model_id or f"model_{index}",
            trial_id=f"trial_{index:03d}",
            run_id=Path(run_path).name,
            artifact_path=str(run_path),
        )
        artifact = load_model_run_artifact(run_path)
        trial_model_id = str(artifact.metrics.get("model_id") or spec.model_id)
        spec.model_id = trial_model_id
        trials.append(
            RepeatedTrialResult(
                spec=spec,
                status="completed" if artifact.status == "complete" else "failed",
                artifact=artifact,
                metrics=artifact.metrics,
            )
        )
    return _aggregate_trial_results(model_id or (trials[0].spec.model_id if trials else "unknown"), trials)


def compare_repeated_trial_groups(
    model_a_runs: list[str | Path],
    model_b_runs: list[str | Path],
    *,
    comparison_id: str = "repeated_trials_comparison",
) -> RepeatedTrialsComparison:
    first_trials = _trial_results_from_paths(model_a_runs)
    second_trials = _trial_results_from_paths(model_b_runs)
    first_model_id = first_trials[0].spec.model_id if first_trials else "first"
    second_model_id = second_trials[0].spec.model_id if second_trials else "second"
    first_aggregate = _aggregate_trial_results(first_model_id, first_trials)
    second_aggregate = _aggregate_trial_results(second_model_id, second_trials)
    return build_repeated_trials_comparison(
        [RepeatedTrialSeriesResult(model_id=first_model_id, trials=first_trials, aggregate=first_aggregate),
         RepeatedTrialSeriesResult(model_id=second_model_id, trials=second_trials, aggregate=second_aggregate)],
        comparison_id=comparison_id,
    )


def build_repeated_trials_comparison(
    series_results: list[RepeatedTrialSeriesResult],
    *,
    comparison_id: str,
) -> RepeatedTrialsComparison:
    for series in series_results:
        if series.aggregate is None:
            series.aggregate = _aggregate_trial_results(series.model_id, series.trials)
    trial_index = [_trial_index_row(trial) for series in series_results for trial in series.trials]
    aggregates = {
        series.model_id: series.aggregate
        for series in series_results
        if series.aggregate is not None
    }
    protocol_checks = _protocol_checks(series_results)
    protocol_compatible = all(item["compatible"] for item in protocol_checks)
    status: Literal["complete", "partial"] = "complete"
    if any(trial.status == "failed" for series in series_results for trial in series.trials):
        status = "partial"
    metric_winners = _aggregate_metric_winners(aggregates)
    failure_modes = {
        model_id: {
            "common_failure_modes": aggregate.common_failure_modes,
            "most_common_actions": aggregate.most_common_actions,
            "most_common_action_parameters": aggregate.most_common_action_parameters,
        }
        for model_id, aggregate in aggregates.items()
    }
    interpretation = {
        "confidence": "low" if sum(a.trial_count for a in aggregates.values()) < 10 else "medium",
        "summary": (
            "Repeated trials provide a stronger signal than single-run comparison, "
            "but this is still one short scenario and should not be treated as a final model recommendation."
        ),
    }
    limitations = [
        "Only one scenario is repeated.",
        "Three trials per model is a small sample.",
        "No multi-agent run is included.",
        "Browser behavior remains simulated-only and office behavior remains stub/file-based.",
        "Resource metrics are lightweight scenario-run metadata, not a benchmark monitor.",
    ]
    return RepeatedTrialsComparison(
        comparison_id=comparison_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        protocol_compatible=protocol_compatible,
        protocol_checks=protocol_checks,
        trial_index=trial_index,
        aggregates=aggregates,
        metric_winners=metric_winners,
        failure_modes=failure_modes,
        interpretation=interpretation,
        limitations=limitations,
    )


def write_repeated_trials_report(comparison: RepeatedTrialsComparison, out_dir: str | Path) -> Path:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    (out_path / "trial_index.json").write_text(
        json.dumps(comparison.trial_index, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_trial_index_csv(comparison, out_path / "trial_index.csv")
    aggregate_payload = {
        model_id: aggregate.model_dump(mode="json")
        for model_id, aggregate in comparison.aggregates.items()
    }
    (out_path / "aggregate_metrics.json").write_text(
        json.dumps(aggregate_payload, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    _write_aggregate_csv(comparison, out_path / "aggregate_metrics.csv")
    (out_path / "failure_modes.json").write_text(
        json.dumps(comparison.failure_modes, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_path / "repeated_trials_comparison.json").write_text(
        json.dumps(comparison.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_path / "repeated_trials_comparison.md").write_text(
        _comparison_markdown(comparison),
        encoding="utf-8",
    )
    (out_path / "README.md").write_text(_readme_markdown(comparison), encoding="utf-8")
    return out_path


def write_replay_command(out_dir: str | Path, command: str) -> None:
    Path(out_dir, "replay_commands.ps1").write_text(command.rstrip() + "\n", encoding="utf-8")


def prepare_output_root(out_root: str | Path, *, force: bool) -> Path:
    out_path = Path(out_root)
    if out_path.exists():
        if not force:
            raise FileExistsError(f"Repeated trials output root already exists: {out_path}")
        shutil.rmtree(out_path)
    out_path.mkdir(parents=True, exist_ok=True)
    return out_path


def _trial_results_from_paths(paths: list[str | Path]) -> list[RepeatedTrialResult]:
    trials: list[RepeatedTrialResult] = []
    for index, path in enumerate(paths, start=1):
        artifact = load_model_run_artifact(path)
        model_id = str(artifact.metrics.get("model_id") or "unknown")
        spec = RepeatedTrialSpec(
            model_id=model_id,
            trial_id=f"trial_{index:03d}",
            run_id=str(artifact.metrics.get("run_id") or Path(path).name),
            artifact_path=str(path),
        )
        trials.append(
            RepeatedTrialResult(
                spec=spec,
                status="completed" if artifact.status == "complete" else "failed",
                artifact=artifact,
                metrics=artifact.metrics,
            )
        )
    return trials


def _aggregate_trial_results(model_id: str, trials: list[RepeatedTrialResult]) -> RepeatedTrialAggregate:
    completed = [trial for trial in trials if trial.metrics]
    failed_count = sum(1 for trial in trials if trial.status == "failed")
    metrics: dict[str, Any] = {}
    for key in [
        "step_count",
        "initial_validation_accept_rate",
        "final_validation_accept_rate",
        "execution_success_rate",
        "normal_activity_score",
        "diversity_score",
        "repetition_score",
        "sequence_coherence_score",
        "history_usage_score",
        "average_selection_latency_ms",
        "average_total_step_latency_ms",
    ]:
        values = [_number(trial.metrics.get(key)) for trial in completed]
        values = [value for value in values if value is not None]
        metrics[key] = _summary_stats(values)

    total_fields = {
        "total_file_not_found_count": "file_not_found_count",
        "total_unsafe_path_count": "unsafe_path_count",
        "total_validation_failure_count": "validation_failure_count",
        "total_repair_attempt_count": "repair_attempt_count",
        "total_successful_execution_count": "execution_success_count",
    }
    for output_key, metric_key in total_fields.items():
        metrics[output_key] = sum(int(trial.metrics.get(metric_key) or 0) for trial in completed)

    action_counter: Counter[str] = Counter()
    parameter_counter: Counter[str] = Counter()
    failure_counter: Counter[str] = Counter()
    for trial in completed:
        for action in trial.metrics.get("selected_action_sequence") or []:
            action_counter[str(action)] += 1
        artifact = trial.artifact
        if artifact is not None:
            for selected in artifact.selected_actions:
                next_action = selected.get("next_action") or selected
                key = json.dumps(
                    {
                        "action": next_action.get("action"),
                        "parameters": next_action.get("parameters") or {},
                    },
                    ensure_ascii=False,
                    sort_keys=True,
                )
                parameter_counter[key] += 1
        for error_type, count in (trial.metrics.get("execution_error_types") or {}).items():
            failure_counter[str(error_type)] += int(count)

    return RepeatedTrialAggregate(
        model_id=model_id,
        trial_count=len(trials),
        completed_trial_count=len(completed),
        failed_trial_count=failed_count,
        metrics=metrics,
        common_failure_modes=dict(failure_counter.most_common()),
        most_common_actions=[
            {"action": action, "count": count}
            for action, count in action_counter.most_common(10)
        ],
        most_common_action_parameters=[
            {"action_parameters": key, "count": count}
            for key, count in parameter_counter.most_common(10)
        ],
    )


def _protocol_checks(series_results: list[RepeatedTrialSeriesResult]) -> list[dict[str, Any]]:
    fields = [
        "scenario_path",
        "max_steps",
        "repair_enabled",
        "repair_attempts_per_step",
        "execute_actions",
    ]
    checks: list[dict[str, Any]] = []
    artifacts = [
        trial.artifact
        for series in series_results
        for trial in series.trials
        if trial.artifact is not None
    ]
    for field in fields:
        values = [artifact.metrics.get(field) for artifact in artifacts]
        comparable_values = [value for value in values if value is not None]
        checks.append(
            {
                "name": field,
                "values": comparable_values,
                "compatible": bool(comparable_values and len(set(map(str, comparable_values))) == 1),
                "checked": bool(comparable_values),
            }
        )
    return checks


def _aggregate_metric_winners(aggregates: dict[str, RepeatedTrialAggregate]) -> list[ModelComparisonMetric]:
    if len(aggregates) != 2:
        return []
    model_ids = list(aggregates)
    first_id, second_id = model_ids[0], model_ids[1]
    first = aggregates[first_id]
    second = aggregates[second_id]
    specs = [
        ("mean_first_attempt_validity", "initial_validation_accept_rate", True),
        ("mean_final_validity", "final_validation_accept_rate", True),
        ("mean_execution_success", "execution_success_rate", True),
        ("mean_normal_activity", "normal_activity_score", True),
        ("mean_diversity", "diversity_score", True),
        ("mean_repetition", "repetition_score", True),
        ("mean_history_usage", "history_usage_score", True),
        ("mean_selection_latency", "average_selection_latency_ms", False),
        ("mean_total_step_latency", "average_total_step_latency_ms", False),
        ("stability_execution_success_std", "execution_success_rate", False, "std"),
    ]
    winners: list[ModelComparisonMetric] = []
    for item in specs:
        name, metric_key, higher = item[:3]
        stat_name = item[3] if len(item) > 3 else "mean"
        first_value = (first.metrics.get(metric_key) or {}).get(stat_name)
        second_value = (second.metrics.get(metric_key) or {}).get(stat_name)
        winners.append(
            ModelComparisonMetric(
                name=name,
                first_value=first_value,
                second_value=second_value,
                winner=_winner(first_value, second_value, higher_is_better=higher),
                higher_is_better=higher,
            )
        )
    first_failures = sum(first.common_failure_modes.values())
    second_failures = sum(second.common_failure_modes.values())
    winners.append(
        ModelComparisonMetric(
            name="fewer_recurring_execution_failures",
            first_value=first_failures,
            second_value=second_failures,
            winner=_winner(first_failures, second_failures, higher_is_better=False),
            higher_is_better=False,
        )
    )
    return winners


def _trial_index_row(trial: RepeatedTrialResult) -> dict[str, Any]:
    metrics = trial.metrics
    return {
        "model_id": trial.spec.model_id,
        "trial_id": trial.spec.trial_id,
        "run_id": trial.spec.run_id,
        "artifact_path": trial.spec.artifact_path,
        "status": trial.status,
        "return_code": trial.return_code,
        "error_message": trial.error_message,
        "step_count": metrics.get("step_count"),
        "initial_validation_accept_rate": metrics.get("initial_validation_accept_rate"),
        "final_validation_accept_rate": metrics.get("final_validation_accept_rate"),
        "execution_success_rate": metrics.get("execution_success_rate"),
        "normal_activity_score": metrics.get("normal_activity_score"),
        "average_selection_latency_ms": metrics.get("average_selection_latency_ms"),
        "stop_reason": metrics.get("stop_reason"),
    }


def _write_trial_index_csv(comparison: RepeatedTrialsComparison, path: Path) -> None:
    fieldnames = [
        "model_id",
        "trial_id",
        "run_id",
        "artifact_path",
        "status",
        "return_code",
        "error_message",
        "step_count",
        "initial_validation_accept_rate",
        "final_validation_accept_rate",
        "execution_success_rate",
        "normal_activity_score",
        "average_selection_latency_ms",
        "stop_reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(comparison.trial_index)


def _write_aggregate_csv(comparison: RepeatedTrialsComparison, path: Path) -> None:
    fieldnames = ["model_id", "metric", "mean", "std", "min", "max", "count", "total"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for model_id, aggregate in comparison.aggregates.items():
            for metric, value in aggregate.metrics.items():
                if isinstance(value, dict):
                    writer.writerow({"model_id": model_id, "metric": metric, **value})
                else:
                    writer.writerow({"model_id": model_id, "metric": metric, "total": value})


def _comparison_markdown(comparison: RepeatedTrialsComparison) -> str:
    lines = [
        "# Repeated Trials Comparison",
        "",
        f"- comparison_id: `{comparison.comparison_id}`",
        f"- protocol_compatible: `{comparison.protocol_compatible}`",
        f"- status: `{comparison.status}`",
        f"- confidence: `{comparison.interpretation.get('confidence')}`",
        "",
        "## Aggregate Metrics",
        "",
        "| model_id | trials | failed | mean initial validity | mean final validity | mean execution success | mean normal score | mean selection latency ms |",
        "|---|---:|---:|---:|---:|---:|---:|---:|",
    ]
    for model_id, aggregate in comparison.aggregates.items():
        metrics = aggregate.metrics
        lines.append(
            f"| `{model_id}` | {aggregate.trial_count} | {aggregate.failed_trial_count} | "
            f"{_stat(metrics, 'initial_validation_accept_rate', 'mean')} | "
            f"{_stat(metrics, 'final_validation_accept_rate', 'mean')} | "
            f"{_stat(metrics, 'execution_success_rate', 'mean')} | "
            f"{_stat(metrics, 'normal_activity_score', 'mean')} | "
            f"{_stat(metrics, 'average_selection_latency_ms', 'mean')} |"
        )
    lines.extend(["", "## Metric Winners", "", "| metric | winner | first | second |", "|---|---|---:|---:|"])
    for winner in comparison.metric_winners:
        lines.append(f"| {winner.name} | `{winner.winner}` | {winner.first_value} | {winner.second_value} |")
    lines.extend(["", "## Failure Modes", ""])
    for model_id, failure in comparison.failure_modes.items():
        lines.append(f"### `{model_id}`")
        lines.append("")
        lines.append(f"- common_failure_modes: `{failure.get('common_failure_modes')}`")
        lines.append(f"- most_common_actions: `{failure.get('most_common_actions')}`")
        lines.append(f"- most_common_action_parameters: `{failure.get('most_common_action_parameters')}`")
        lines.append("")
    lines.extend(["## Limitations", ""])
    lines.extend(f"- {item}" for item in comparison.limitations)
    lines.append("")
    return "\n".join(lines)


def _readme_markdown(comparison: RepeatedTrialsComparison) -> str:
    return (
        "# Repeated Model Trials Artifact\n\n"
        f"- comparison_id: `{comparison.comparison_id}`\n"
        f"- generated_at: `{comparison.generated_at}`\n"
        f"- protocol_compatible: `{comparison.protocol_compatible}`\n"
        f"- status: `{comparison.status}`\n\n"
        "Root files include trial index, aggregate metrics, failure modes, and repeated-trials comparison reports.\n"
    )


def _summary_stats(values: list[float]) -> dict[str, float | int | None]:
    if not values:
        return {"mean": None, "std": None, "min": None, "max": None, "count": 0}
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {
        "mean": round(mean, 6),
        "std": round(math.sqrt(variance), 6),
        "min": min(values),
        "max": max(values),
        "count": len(values),
    }


def _number(value: Any) -> float | None:
    if isinstance(value, bool):
        return float(value)
    if isinstance(value, int | float):
        return float(value)
    return None


def _winner(first: Any, second: Any, *, higher_is_better: bool) -> Literal["first", "second", "tie", "not_available"]:
    if first is None or second is None:
        return "not_available"
    if first == second:
        return "tie"
    if higher_is_better:
        return "first" if first > second else "second"
    return "first" if first < second else "second"


def _stat(metrics: dict[str, Any], metric: str, stat: str) -> Any:
    return (metrics.get(metric) or {}).get(stat)
