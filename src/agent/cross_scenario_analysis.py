from __future__ import annotations

import csv
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


Winner = Literal["first_model", "qwen2_5_3b_instruct_q4_k_m", "tie", "not_available"]


class ScenarioAnalysisInput(BaseModel):
    scenario_id: str
    analysis_path: str
    repeated_trials_path: str

    @field_validator("scenario_id", "analysis_path", "repeated_trials_path")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("ScenarioAnalysisInput fields must be non-empty.")
        return value


class ScenarioModelSummary(BaseModel):
    scenario_id: str
    model_id: str
    trial_count: int
    completed_trial_count: int
    failed_trial_count: int
    mean_initial_validation_accept_rate: float | None = None
    mean_final_validation_accept_rate: float | None = None
    mean_execution_success_rate: float | None = None
    mean_normal_activity_score: float | None = None
    mean_diversity_score: float | None = None
    mean_repetition_score: float | None = None
    mean_history_usage_score: float | None = None
    mean_sequence_coherence_score: float | None = None
    mean_avg_selection_latency_ms: float | None = None
    mean_avg_total_step_latency_ms: float | None = None
    common_failure_modes: dict[str, int] = Field(default_factory=dict)
    most_repeated_action_parameters: list[dict[str, Any]] = Field(default_factory=list)
    role_verdict: str | None = None
    coherence_verdict: str | None = None
    diversity_template_verdict: str | None = None


class CrossScenarioFailurePattern(BaseModel):
    model_id: str
    stable_failure_patterns: dict[str, int] = Field(default_factory=dict)
    scenario_specific_failure_patterns: dict[str, dict[str, int]] = Field(default_factory=dict)
    total_counts: dict[str, int] = Field(default_factory=dict)


class CrossScenarioModelAggregate(BaseModel):
    model_id: str
    scenario_count: int
    total_trials: int
    completed_trials: int
    failed_trials: int
    mean_initial_validation_accept_rate_across_scenarios: float | None = None
    mean_final_validation_accept_rate_across_scenarios: float | None = None
    mean_execution_success_rate_across_scenarios: float | None = None
    mean_normal_activity_score_across_scenarios: float | None = None
    mean_diversity_score_across_scenarios: float | None = None
    mean_repetition_score_across_scenarios: float | None = None
    mean_history_usage_score_across_scenarios: float | None = None
    mean_sequence_coherence_score_across_scenarios: float | None = None
    mean_avg_selection_latency_ms_across_scenarios: float | None = None
    metric_ranges: dict[str, dict[str, float | None]] = Field(default_factory=dict)
    stable_failure_patterns: dict[str, int] = Field(default_factory=dict)
    scenario_specific_failure_patterns: dict[str, dict[str, int]] = Field(default_factory=dict)
    dominant_action_patterns: list[dict[str, Any]] = Field(default_factory=list)
    template_behavior_consistency: dict[str, Any] = Field(default_factory=dict)
    scenario_sensitivity: str
    overall_behavioral_profile: list[str] = Field(default_factory=list)


class CrossScenarioMetricComparison(BaseModel):
    metric: str
    first_model_value: Any = None
    qwen2_5_3b_value: Any = None
    winner: Winner = "not_available"
    rationale: str | None = None


class CrossScenarioAnalysisResult(BaseModel):
    analysis_id: str
    generated_at: str
    inputs: list[ScenarioAnalysisInput]
    scenario_model_summaries: list[ScenarioModelSummary]
    model_aggregates: dict[str, CrossScenarioModelAggregate]
    metric_winners: list[CrossScenarioMetricComparison]
    failure_patterns: dict[str, CrossScenarioFailurePattern]
    scenario_sensitivity_report: dict[str, Any]
    recommendation_readiness: dict[str, Any]
    warnings: list[str] = Field(default_factory=list)


def load_scenario_behavioral_analysis(path: str | Path) -> dict[str, Any]:
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"Scenario analysis path not found: {root}")
    file_path = root / "consolidated_behavioral_analysis.json"
    if not file_path.exists():
        raise FileNotFoundError(f"Missing consolidated_behavioral_analysis.json in {root}")
    return json.loads(file_path.read_text(encoding="utf-8"))


def load_repeated_trials_summary(path: str | Path) -> dict[str, Any]:
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"Repeated trials path not found: {root}")
    payload: dict[str, Any] = {"warnings": []}
    for name in [
        "aggregate_metrics.json",
        "repeated_trials_comparison.json",
        "failure_modes.json",
        "trial_index.json",
    ]:
        file_path = root / name
        if file_path.exists():
            payload[name] = json.loads(file_path.read_text(encoding="utf-8"))
        else:
            payload["warnings"].append(f"missing_artifact: {file_path}")
            payload[name] = {} if name.endswith(".json") else []
    return payload


def build_cross_scenario_analysis(
    inputs: list[ScenarioAnalysisInput],
    *,
    analysis_id: str = "cross_scenario_behavioral_analysis_v1",
) -> CrossScenarioAnalysisResult:
    scenario_summaries: list[ScenarioModelSummary] = []
    warnings: list[str] = []
    loaded_analysis: dict[str, dict[str, Any]] = {}
    loaded_repeated: dict[str, dict[str, Any]] = {}

    for item in inputs:
        analysis = load_scenario_behavioral_analysis(item.analysis_path)
        repeated = load_repeated_trials_summary(item.repeated_trials_path)
        loaded_analysis[item.scenario_id] = analysis
        loaded_repeated[item.scenario_id] = repeated
        warnings.extend(repeated.get("warnings", []))
        scenario_summaries.extend(_scenario_model_summaries(item.scenario_id, analysis, repeated))

    aggregates = _model_aggregates(scenario_summaries, loaded_analysis)
    failure_patterns = _failure_patterns(scenario_summaries, loaded_analysis)
    sensitivity = _scenario_sensitivity(scenario_summaries)
    metric_winners = _metric_winners(aggregates)
    readiness = _recommendation_readiness(inputs, scenario_summaries, aggregates)
    return CrossScenarioAnalysisResult(
        analysis_id=analysis_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        inputs=inputs,
        scenario_model_summaries=scenario_summaries,
        model_aggregates=aggregates,
        metric_winners=metric_winners,
        failure_patterns=failure_patterns,
        scenario_sensitivity_report=sensitivity,
        recommendation_readiness=readiness,
        warnings=warnings,
    )


def write_cross_scenario_analysis(result: CrossScenarioAnalysisResult, out_dir: str | Path, *, force: bool = False) -> Path:
    out = Path(out_dir)
    if out.exists():
        if not force:
            raise FileExistsError(f"Cross-scenario output directory already exists: {out}")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "cross_scenario_analysis.json", result.model_dump(mode="json"))
    (out / "cross_scenario_analysis.md").write_text(_main_markdown(result), encoding="utf-8")
    _write_metrics_csv(out / "cross_scenario_metrics.csv", result)
    _write_json(out / "cross_scenario_failure_patterns.json", {k: v.model_dump(mode="json") for k, v in result.failure_patterns.items()})
    _write_failure_csv(out / "cross_scenario_failure_patterns.csv", result)
    _write_json(out / "cross_scenario_model_profiles.json", {k: v.model_dump(mode="json") for k, v in result.model_aggregates.items()})
    (out / "cross_scenario_model_profiles.md").write_text(_profiles_markdown(result), encoding="utf-8")
    _write_json(out / "scenario_sensitivity_report.json", result.scenario_sensitivity_report)
    (out / "scenario_sensitivity_report.md").write_text(_sensitivity_markdown(result), encoding="utf-8")
    _write_json(out / "recommendation_readiness.json", result.recommendation_readiness)
    (out / "recommendation_readiness.md").write_text(_readiness_markdown(result), encoding="utf-8")
    (out / "README.md").write_text(_readme(result), encoding="utf-8")
    (out / "replay_commands.ps1").write_text(_replay_command(result, out), encoding="utf-8")
    return out


def _scenario_model_summaries(
    scenario_id: str,
    analysis: dict[str, Any],
    repeated: dict[str, Any],
) -> list[ScenarioModelSummary]:
    aggregate_metrics = repeated.get("aggregate_metrics.json", {})
    failure_modes = repeated.get("failure_modes.json", {})
    rows: list[ScenarioModelSummary] = []
    for model_id, aggregate in aggregate_metrics.items():
        metrics = aggregate.get("metrics", {})
        role = (analysis.get("role_compliance") or {}).get(model_id, {})
        coherence = (analysis.get("coherence_history_usage") or {}).get(model_id, {})
        diversity = (analysis.get("diversity_template_behavior") or {}).get(model_id, {})
        failure = failure_modes.get(model_id, {})
        rows.append(
            ScenarioModelSummary(
                scenario_id=scenario_id,
                model_id=model_id,
                trial_count=int(aggregate.get("trial_count") or 0),
                completed_trial_count=int(aggregate.get("completed_trial_count") or 0),
                failed_trial_count=int(aggregate.get("failed_trial_count") or 0),
                mean_initial_validation_accept_rate=_mean_metric(metrics, "initial_validation_accept_rate"),
                mean_final_validation_accept_rate=_mean_metric(metrics, "final_validation_accept_rate"),
                mean_execution_success_rate=_mean_metric(metrics, "execution_success_rate"),
                mean_normal_activity_score=_mean_metric(metrics, "normal_activity_score"),
                mean_diversity_score=_mean_metric(metrics, "diversity_score"),
                mean_repetition_score=_mean_metric(metrics, "repetition_score"),
                mean_history_usage_score=_mean_metric(metrics, "history_usage_score"),
                mean_sequence_coherence_score=_mean_metric(metrics, "sequence_coherence_score"),
                mean_avg_selection_latency_ms=_mean_metric(metrics, "average_selection_latency_ms"),
                mean_avg_total_step_latency_ms=_mean_metric(metrics, "average_total_step_latency_ms"),
                common_failure_modes=dict(aggregate.get("common_failure_modes") or {}),
                most_repeated_action_parameters=list(aggregate.get("most_common_action_parameters") or failure.get("most_common_action_parameters") or []),
                role_verdict=role.get("verdict"),
                coherence_verdict=coherence.get("verdict"),
                diversity_template_verdict=diversity.get("verdict"),
            )
        )
    return rows


def _model_aggregates(
    summaries: list[ScenarioModelSummary],
    analyses: dict[str, dict[str, Any]],
) -> dict[str, CrossScenarioModelAggregate]:
    by_model: dict[str, list[ScenarioModelSummary]] = defaultdict(list)
    for summary in summaries:
        by_model[summary.model_id].append(summary)

    aggregates: dict[str, CrossScenarioModelAggregate] = {}
    for model_id, rows in by_model.items():
        values = {
            "final_validation": [r.mean_final_validation_accept_rate for r in rows],
            "execution_success": [r.mean_execution_success_rate for r in rows],
            "normal_activity": [r.mean_normal_activity_score for r in rows],
            "diversity": [r.mean_diversity_score for r in rows],
            "latency": [r.mean_avg_selection_latency_ms for r in rows],
        }
        stable, scenario_specific, total_failures = _split_failure_patterns(rows)
        action_patterns = _dominant_action_patterns(rows)
        template = _template_consistency(model_id, analyses)
        sensitivity = _sensitivity_verdict(rows)
        aggregates[model_id] = CrossScenarioModelAggregate(
            model_id=model_id,
            scenario_count=len(rows),
            total_trials=sum(r.trial_count for r in rows),
            completed_trials=sum(r.completed_trial_count for r in rows),
            failed_trials=sum(r.failed_trial_count for r in rows),
            mean_initial_validation_accept_rate_across_scenarios=_avg([r.mean_initial_validation_accept_rate for r in rows]),
            mean_final_validation_accept_rate_across_scenarios=_avg([r.mean_final_validation_accept_rate for r in rows]),
            mean_execution_success_rate_across_scenarios=_avg([r.mean_execution_success_rate for r in rows]),
            mean_normal_activity_score_across_scenarios=_avg([r.mean_normal_activity_score for r in rows]),
            mean_diversity_score_across_scenarios=_avg([r.mean_diversity_score for r in rows]),
            mean_repetition_score_across_scenarios=_avg([r.mean_repetition_score for r in rows]),
            mean_history_usage_score_across_scenarios=_avg([r.mean_history_usage_score for r in rows]),
            mean_sequence_coherence_score_across_scenarios=_avg([r.mean_sequence_coherence_score for r in rows]),
            mean_avg_selection_latency_ms_across_scenarios=_avg([r.mean_avg_selection_latency_ms for r in rows]),
            metric_ranges={name: _range(vals) for name, vals in values.items()},
            stable_failure_patterns=stable,
            scenario_specific_failure_patterns=scenario_specific,
            dominant_action_patterns=action_patterns,
            template_behavior_consistency=template,
            scenario_sensitivity=sensitivity,
            overall_behavioral_profile=_overall_profile(model_id, rows, stable, template, sensitivity),
        )
    return aggregates


def _failure_patterns(
    summaries: list[ScenarioModelSummary],
    analyses: dict[str, dict[str, Any]],
) -> dict[str, CrossScenarioFailurePattern]:
    by_model: dict[str, list[ScenarioModelSummary]] = defaultdict(list)
    for summary in summaries:
        by_model[summary.model_id].append(summary)
    result: dict[str, CrossScenarioFailurePattern] = {}
    for model_id, rows in by_model.items():
        stable, specific, total = _split_failure_patterns(rows)
        failure_counts = Counter(total)
        for analysis in analyses.values():
            failure = (analysis.get("failure_modes") or {}).get(model_id, {})
            for key in [
                "validation_failed_after_repair_count",
                "missing_required_parameter_count",
                "unsafe_path_count",
                "write_path_outside_workspace_count",
                "file_not_found_count",
                "max_consecutive_failures_count",
                "execution_error_count",
                "repair_attempt_count",
                "repair_success_count",
                "unrecovered_failure_count",
            ]:
                failure_counts[key] += int(failure.get(key) or 0)
        result[model_id] = CrossScenarioFailurePattern(
            model_id=model_id,
            stable_failure_patterns=stable,
            scenario_specific_failure_patterns=specific,
            total_counts=dict(failure_counts),
        )
    return result


def _scenario_sensitivity(summaries: list[ScenarioModelSummary]) -> dict[str, Any]:
    by_model: dict[str, list[ScenarioModelSummary]] = defaultdict(list)
    for summary in summaries:
        by_model[summary.model_id].append(summary)
    result: dict[str, Any] = {}
    for model_id, rows in by_model.items():
        if len(rows) < 2:
            result[model_id] = {"verdict": "not_available", "reason": "fewer than two scenarios"}
            continue
        a, b = rows[0], rows[1]
        deltas = {
            "initial_validity": _delta(a.mean_initial_validation_accept_rate, b.mean_initial_validation_accept_rate),
            "final_validity": _delta(a.mean_final_validation_accept_rate, b.mean_final_validation_accept_rate),
            "execution_success": _delta(a.mean_execution_success_rate, b.mean_execution_success_rate),
            "normal_activity": _delta(a.mean_normal_activity_score, b.mean_normal_activity_score),
            "diversity": _delta(a.mean_diversity_score, b.mean_diversity_score),
            "repetition": _delta(a.mean_repetition_score, b.mean_repetition_score),
            "history_usage": _delta(a.mean_history_usage_score, b.mean_history_usage_score),
            "latency_ms": _delta(a.mean_avg_selection_latency_ms, b.mean_avg_selection_latency_ms),
        }
        failure_changed = set(a.common_failure_modes) != set(b.common_failure_modes)
        verdict = _sensitivity_verdict(rows)
        result[model_id] = {
            "verdict": verdict,
            "scenario_order": [row.scenario_id for row in rows],
            "deltas": deltas,
            "failure_modes_changed": failure_changed,
            "dominant_action_patterns": [row.most_repeated_action_parameters for row in rows],
            "failure_modes": {row.scenario_id: row.common_failure_modes for row in rows},
        }
    return result


def _metric_winners(aggregates: dict[str, CrossScenarioModelAggregate]) -> list[CrossScenarioMetricComparison]:
    first = aggregates.get("first_model")
    second = aggregates.get("qwen2_5_3b_instruct_q4_k_m")
    if first is None or second is None:
        return []
    metrics = [
        ("contract_validity", first.mean_initial_validation_accept_rate_across_scenarios, second.mean_initial_validation_accept_rate_across_scenarios, True),
        ("final_validity", first.mean_final_validation_accept_rate_across_scenarios, second.mean_final_validation_accept_rate_across_scenarios, True),
        ("execution_success", first.mean_execution_success_rate_across_scenarios, second.mean_execution_success_rate_across_scenarios, True),
        ("normal_activity", first.mean_normal_activity_score_across_scenarios, second.mean_normal_activity_score_across_scenarios, True),
        ("diversity", first.mean_diversity_score_across_scenarios, second.mean_diversity_score_across_scenarios, True),
        ("lower_template_repetition", _template_penalty(first), _template_penalty(second), False),
        ("history_usage", first.mean_history_usage_score_across_scenarios, second.mean_history_usage_score_across_scenarios, True),
        ("latency", first.mean_avg_selection_latency_ms_across_scenarios, second.mean_avg_selection_latency_ms_across_scenarios, False),
        ("failure_stability", len(first.stable_failure_patterns), len(second.stable_failure_patterns), False),
    ]
    comparisons = [
        CrossScenarioMetricComparison(
            metric=name,
            first_model_value=a,
            qwen2_5_3b_value=b,
            winner=_winner(a, b, higher_is_better=higher),
        )
        for name, a, b, higher in metrics
    ]
    comparisons.append(
        CrossScenarioMetricComparison(
            metric="overall_evidence_leader",
            first_model_value="execution success only in office-worker; repair-dependent",
            qwen2_5_3b_value="stronger contract validity and latency; execution weak",
            winner="not_available",
            rationale="Evidence is mixed across two scenarios and not enough for a final model recommendation.",
        )
    )
    return comparisons


def _recommendation_readiness(
    inputs: list[ScenarioAnalysisInput],
    summaries: list[ScenarioModelSummary],
    aggregates: dict[str, CrossScenarioModelAggregate],
) -> dict[str, Any]:
    scenario_count = len(inputs)
    model_ids = sorted(aggregates)
    total_trials = sum(item.trial_count for item in summaries)
    return {
        "recommendation_readiness_status": "not_ready_for_final_recommendation",
        "criteria": {
            "at_least_2_scenarios_completed": scenario_count >= 2,
            "repeated_trials_per_model": all(agg.total_trials >= scenario_count * 3 for agg in aggregates.values()),
            "behavioral_analysis": True,
            "resource_latency_observations": True,
            "full_resource_benchmark": False,
            "multi_agent_capacity_estimate": False,
            "more_than_one_role": True,
            "real_browser_office_automation": False,
            "enough_for_provisional_model_preference": "limited",
            "enough_for_final_recommended_configuration": False,
        },
        "scenario_count": scenario_count,
        "model_ids": model_ids,
        "total_trajectories": total_trials,
        "provisional_findings": [
            "qwen2_5_3b_instruct_q4_k_m has stronger initial/final action-contract validity and lower latency.",
            "first_model achieved useful execution only in the office-worker scenario and remains repair-dependent.",
            "Both models are weak on coherence and template/repetition behavior.",
        ],
        "required_next_steps": [
            "Run resource/capacity evaluation.",
            "Resolve or explicitly document action workspace/safety mismatch for developer source-file reads.",
            "Add multi-agent capacity formula and measurement plan.",
            "Prepare final report only after resource/capacity data is available.",
        ],
    }


def _write_metrics_csv(path: Path, result: CrossScenarioAnalysisResult) -> None:
    rows = [item.model_dump(mode="json") for item in result.scenario_model_summaries]
    fields = list(rows[0]) if rows else []
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        writer.writerows(rows)


def _write_failure_csv(path: Path, result: CrossScenarioAnalysisResult) -> None:
    fields = ["model_id", "pattern", "stable", "count"]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for model_id, pattern in result.failure_patterns.items():
            for name, count in pattern.stable_failure_patterns.items():
                writer.writerow({"model_id": model_id, "pattern": name, "stable": True, "count": count})
            for scenario_id, values in pattern.scenario_specific_failure_patterns.items():
                for name, count in values.items():
                    writer.writerow({"model_id": model_id, "pattern": f"{scenario_id}:{name}", "stable": False, "count": count})


def _main_markdown(result: CrossScenarioAnalysisResult) -> str:
    lines = [
        "# Cross-Scenario Behavioral Analysis v1",
        "",
        "## 1. Executive Summary",
        "",
        "Across two scenarios, `qwen2_5_3b_instruct_q4_k_m` is consistently stronger on action-contract validity and latency. "
        "`first_model` is repair-dependent and only showed useful execution in the office-worker scenario. "
        "Both models remain weak on coherence and template-like behavior, so the project is not ready for a final model recommendation.",
        "",
        "## 2. Evidence Base",
        "",
        f"- scenarios: `{[item.scenario_id for item in result.inputs]}`",
        f"- models: `{list(result.model_aggregates)}`",
        f"- total trajectories: `{result.recommendation_readiness.get('total_trajectories')}`",
        "- protocol: local mode, execute-actions, max_steps=5, repair_attempts=1",
        "",
        "## 3. Cross-Scenario Metrics Table",
        "",
        "| scenario | model | trials | initial valid | final valid | execution success | normal score | diversity | history | latency ms | failures |",
        "|---|---|---:|---:|---:|---:|---:|---:|---:|---:|---|",
    ]
    for row in result.scenario_model_summaries:
        lines.append(
            f"| `{row.scenario_id}` | `{row.model_id}` | {row.trial_count} | "
            f"{row.mean_initial_validation_accept_rate} | {row.mean_final_validation_accept_rate} | "
            f"{row.mean_execution_success_rate} | {row.mean_normal_activity_score} | "
            f"{row.mean_diversity_score} | {row.mean_history_usage_score} | "
            f"{row.mean_avg_selection_latency_ms} | `{row.common_failure_modes}` |"
        )
    lines.extend(["", "## 4. Model Profiles", ""])
    lines.append(_profiles_markdown(result))
    lines.extend(["", "## 5. Scenario Sensitivity", ""])
    lines.append(_sensitivity_markdown(result))
    lines.extend(["", "## 6. Failure Pattern Analysis", ""])
    for model_id, pattern in result.failure_patterns.items():
        lines.append(f"- `{model_id}` stable: `{pattern.stable_failure_patterns}`; scenario-specific: `{pattern.scenario_specific_failure_patterns}`")
    lines.extend(["", "## 7. Resource/Latency Observations", ""])
    for metric in result.metric_winners:
        if metric.metric == "latency":
            lines.append(f"- Latency winner: `{metric.winner}` ({metric.first_model_value} ms vs {metric.qwen2_5_3b_value} ms).")
    lines.append("- These are per-step/per-run latency observations, not capacity measurements.")
    lines.extend(["", "## 8. Recommendation Readiness", ""])
    lines.append(_readiness_markdown(result))
    lines.extend(["", "## 9. What This Proves", ""])
    lines.extend([
        "- Repeated local-model experiment infrastructure works across two scenarios.",
        "- Artifacts support behavioral comparison across roles.",
        "- Failure modes are measurable and differ by model/scenario.",
    ])
    lines.extend(["", "## 10. What This Does Not Prove", ""])
    lines.extend([
        "- Production readiness.",
        "- Multi-agent capacity.",
        "- Final best model.",
        "- Real browser/office automation.",
    ])
    lines.extend(["", "## 11. Next Step", "", "Run resource/capacity evaluation and define the multi-agent capacity formula."])
    return "\n".join(lines) + "\n"


def _profiles_markdown(result: CrossScenarioAnalysisResult) -> str:
    lines: list[str] = []
    for model_id, aggregate in result.model_aggregates.items():
        lines.extend([
            f"### `{model_id}`",
            "",
            f"- profile: `{aggregate.overall_behavioral_profile}`",
            f"- stable failure patterns: `{aggregate.stable_failure_patterns}`",
            f"- scenario-specific failures: `{aggregate.scenario_specific_failure_patterns}`",
            f"- dominant action patterns: `{aggregate.dominant_action_patterns}`",
            f"- scenario sensitivity: `{aggregate.scenario_sensitivity}`",
            "",
        ])
    return "\n".join(lines)


def _sensitivity_markdown(result: CrossScenarioAnalysisResult) -> str:
    lines = ["| model | verdict | key deltas | failure modes changed |", "|---|---|---|---|"]
    for model_id, item in result.scenario_sensitivity_report.items():
        lines.append(f"| `{model_id}` | `{item.get('verdict')}` | `{item.get('deltas')}` | `{item.get('failure_modes_changed')}` |")
    return "\n".join(lines)


def _readiness_markdown(result: CrossScenarioAnalysisResult) -> str:
    readiness = result.recommendation_readiness
    lines = [
        f"Recommendation readiness status: `{readiness.get('recommendation_readiness_status')}`",
        "",
        "Criteria:",
    ]
    for key, value in readiness.get("criteria", {}).items():
        lines.append(f"- `{key}`: `{value}`")
    lines.append("")
    lines.append("Required next steps:")
    for item in readiness.get("required_next_steps", []):
        lines.append(f"- {item}")
    return "\n".join(lines)


def _readme(result: CrossScenarioAnalysisResult) -> str:
    return (
        "# Cross-Scenario Behavioral Analysis Artifact\n\n"
        f"- analysis_id: `{result.analysis_id}`\n"
        f"- generated_at: `{result.generated_at}`\n"
        f"- readiness: `{result.recommendation_readiness.get('recommendation_readiness_status')}`\n"
    )


def _replay_command(result: CrossScenarioAnalysisResult, out: Path) -> str:
    parts = ["python scripts\\compare_cross_scenario_behavior.py"]
    for item in result.inputs:
        parts.append(f"--scenario-analysis {item.scenario_id}={item.analysis_path}={item.repeated_trials_path}")
    parts.append(f"--out-dir {out}")
    parts.append(f"--label {result.analysis_id}")
    parts.append("--force")
    return " ".join(parts) + "\n"


def _split_failure_patterns(rows: list[ScenarioModelSummary]) -> tuple[dict[str, int], dict[str, dict[str, int]], dict[str, int]]:
    total = Counter()
    scenarios_by_pattern: dict[str, set[str]] = defaultdict(set)
    for row in rows:
        for name, count in row.common_failure_modes.items():
            total[name] += int(count)
            scenarios_by_pattern[name].add(row.scenario_id)
    stable = {name: total[name] for name, scenarios in scenarios_by_pattern.items() if len(scenarios) > 1}
    specific: dict[str, dict[str, int]] = {}
    for row in rows:
        values = {
            name: int(count)
            for name, count in row.common_failure_modes.items()
            if len(scenarios_by_pattern[name]) == 1
        }
        if values:
            specific[row.scenario_id] = values
    return stable, specific, dict(total)


def _dominant_action_patterns(rows: list[ScenarioModelSummary]) -> list[dict[str, Any]]:
    patterns: list[dict[str, Any]] = []
    for row in rows:
        for item in row.most_repeated_action_parameters:
            patterns.append({"scenario_id": row.scenario_id, **item})
    return patterns


def _template_consistency(model_id: str, analyses: dict[str, dict[str, Any]]) -> dict[str, Any]:
    verdicts = []
    flags: Counter[str] = Counter()
    for scenario_id, analysis in analyses.items():
        diversity = (analysis.get("diversity_template_behavior") or {}).get(model_id, {})
        verdicts.append({"scenario_id": scenario_id, "verdict": diversity.get("verdict")})
        for flag in diversity.get("template_behavior_flags") or []:
            flags[str(flag)] += 1
    return {"scenario_verdicts": verdicts, "flag_counts": dict(flags)}


def _overall_profile(
    model_id: str,
    rows: list[ScenarioModelSummary],
    stable: dict[str, int],
    template: dict[str, Any],
    sensitivity: str,
) -> list[str]:
    profile: list[str] = []
    if _avg([r.mean_initial_validation_accept_rate for r in rows]) == 1.0:
        profile.append("contract_valid_but_execution_weak")
    if any("validation_failed_after_repair" in r.common_failure_modes for r in rows):
        profile.append("repair_dependent")
    if template.get("flag_counts"):
        profile.append("template_like")
    if sensitivity in {"medium", "high"}:
        profile.append("scenario_sensitive")
    if not profile:
        profile.append("insufficient_signal")
    return profile


def _sensitivity_verdict(rows: list[ScenarioModelSummary]) -> str:
    if len(rows) < 2:
        return "not_available"
    execution_values = [r.mean_execution_success_rate for r in rows if r.mean_execution_success_rate is not None]
    normal_values = [r.mean_normal_activity_score for r in rows if r.mean_normal_activity_score is not None]
    final_values = [r.mean_final_validation_accept_rate for r in rows if r.mean_final_validation_accept_rate is not None]
    latency_values = [r.mean_avg_selection_latency_ms for r in rows if r.mean_avg_selection_latency_ms is not None]
    failure_sets = [set(r.common_failure_modes) for r in rows]
    if _span(execution_values) >= 0.5 or _span(normal_values) >= 0.3 or _span(final_values) >= 0.5:
        return "high"
    normalized_failure_sets = {tuple(sorted(f)) for f in failure_sets}
    if len(normalized_failure_sets) > 1 or _span(latency_values) > 100:
        return "medium"
    return "low"


def _template_penalty(aggregate: CrossScenarioModelAggregate) -> int:
    flags = aggregate.template_behavior_consistency.get("flag_counts") or {}
    return sum(int(value) for value in flags.values())


def _winner(a: Any, b: Any, *, higher_is_better: bool) -> Winner:
    if a is None or b is None:
        return "not_available"
    if a == b:
        return "tie"
    if higher_is_better:
        return "first_model" if a > b else "qwen2_5_3b_instruct_q4_k_m"
    return "first_model" if a < b else "qwen2_5_3b_instruct_q4_k_m"


def _mean_metric(metrics: dict[str, Any], name: str) -> float | None:
    value = (metrics.get(name) or {}).get("mean")
    return float(value) if isinstance(value, int | float) else None


def _avg(values: list[float | None]) -> float | None:
    numeric = [float(v) for v in values if isinstance(v, int | float)]
    if not numeric:
        return None
    return round(sum(numeric) / len(numeric), 6)


def _range(values: list[float | None]) -> dict[str, float | None]:
    numeric = [float(v) for v in values if isinstance(v, int | float)]
    if not numeric:
        return {"min": None, "max": None, "range": None}
    return {"min": min(numeric), "max": max(numeric), "range": round(max(numeric) - min(numeric), 6)}


def _span(values: list[float]) -> float:
    if not values:
        return 0.0
    return max(values) - min(values)


def _delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(b - a, 6)


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
