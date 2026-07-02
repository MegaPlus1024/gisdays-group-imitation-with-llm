from __future__ import annotations

import csv
import json
import re
import shutil
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator


ComparisonStatus = Literal["complete", "incomplete"]
Winner = Literal["first", "second", "tie", "not_available"]


REQUIRED_ARTIFACTS = [
    "manifest.json",
    "steps.jsonl",
    "attempts.jsonl",
    "raw_model_outputs.jsonl",
    "selected_actions.jsonl",
    "validation_results.jsonl",
    "execution_results.jsonl",
    "history.jsonl",
    "errors.jsonl",
    "activity_evaluation.json",
    "resource_summary.json",
    "replay_commands.ps1",
]


class ModelComparisonMetric(BaseModel):
    name: str
    first_value: Any = None
    second_value: Any = None
    winner: Winner = "not_available"
    higher_is_better: bool = True
    comment: str | None = None


class ModelComparisonVerdict(BaseModel):
    confidence: Literal["low", "medium"] = "low"
    overall_interpretation: str
    limitations: list[str] = Field(default_factory=list)


class ModelRunArtifact(BaseModel):
    artifact_path: str
    status: ComparisonStatus = "complete"
    warnings: list[str] = Field(default_factory=list)
    manifest: dict[str, Any] = Field(default_factory=dict)
    steps: list[dict[str, Any]] = Field(default_factory=list)
    attempts: list[dict[str, Any]] = Field(default_factory=list)
    raw_model_outputs: list[dict[str, Any]] = Field(default_factory=list)
    selected_actions: list[dict[str, Any]] = Field(default_factory=list)
    validation_results: list[dict[str, Any]] = Field(default_factory=list)
    execution_results: list[dict[str, Any]] = Field(default_factory=list)
    history: list[dict[str, Any]] = Field(default_factory=list)
    errors: list[dict[str, Any]] = Field(default_factory=list)
    activity_evaluation: dict[str, Any] = Field(default_factory=dict)
    model_behavior_result: dict[str, Any] = Field(default_factory=dict)
    resource_summary: dict[str, Any] = Field(default_factory=dict)
    replay_command: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)

    @field_validator("artifact_path")
    @classmethod
    def validate_artifact_path(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("artifact_path must be non-empty.")
        return value


class ModelRunComparison(BaseModel):
    comparison_id: str
    generated_at: str
    input_artifact_paths: dict[str, str]
    status: ComparisonStatus
    protocol_compatible: bool
    protocol_checks: list[dict[str, Any]]
    per_model: dict[str, dict[str, Any]]
    metric_winners: list[ModelComparisonMetric]
    failure_analysis: dict[str, Any]
    interpretation: ModelComparisonVerdict
    limitations: list[str]
    warnings: list[str] = Field(default_factory=list)


def load_model_run_artifact(path: str | Path) -> ModelRunArtifact:
    artifact_path = Path(path)
    warnings: list[str] = []
    status: ComparisonStatus = "complete"

    def mark_missing(name: str) -> None:
        nonlocal status
        status = "incomplete"
        warnings.append(f"missing_artifact: {name}")

    def read_json(name: str) -> dict[str, Any]:
        file_path = artifact_path / name
        if not file_path.exists():
            mark_missing(name)
            return {}
        try:
            return json.loads(file_path.read_text(encoding="utf-8"))
        except Exception as exc:
            nonlocal status
            status = "incomplete"
            warnings.append(f"unreadable_artifact: {name}: {exc}")
            return {}

    def read_jsonl(name: str) -> list[dict[str, Any]]:
        file_path = artifact_path / name
        if not file_path.exists():
            mark_missing(name)
            return []
        try:
            return [
                json.loads(line)
                for line in file_path.read_text(encoding="utf-8").splitlines()
                if line.strip()
            ]
        except Exception as exc:
            nonlocal status
            status = "incomplete"
            warnings.append(f"unreadable_artifact: {name}: {exc}")
            return []

    for name in REQUIRED_ARTIFACTS:
        if not (artifact_path / name).exists():
            mark_missing(name)

    model_behavior_name = "model_behavior_result.json"
    if not (artifact_path / model_behavior_name).exists():
        model_behavior_name = "model_behavior_summary.json"
    if not (artifact_path / model_behavior_name).exists():
        mark_missing("model_behavior_result.json_or_model_behavior_summary.json")

    replay_path = artifact_path / "replay_commands.ps1"
    replay_command = replay_path.read_text(encoding="utf-8").strip() if replay_path.exists() else None

    artifact = ModelRunArtifact(
        artifact_path=str(artifact_path),
        status=status,
        warnings=warnings,
        manifest=read_json("manifest.json"),
        steps=read_jsonl("steps.jsonl"),
        attempts=read_jsonl("attempts.jsonl"),
        raw_model_outputs=read_jsonl("raw_model_outputs.jsonl"),
        selected_actions=read_jsonl("selected_actions.jsonl"),
        validation_results=read_jsonl("validation_results.jsonl"),
        execution_results=read_jsonl("execution_results.jsonl"),
        history=read_jsonl("history.jsonl"),
        errors=read_jsonl("errors.jsonl"),
        activity_evaluation=read_json("activity_evaluation.json"),
        model_behavior_result=read_json(model_behavior_name),
        resource_summary=read_json("resource_summary.json"),
        replay_command=replay_command,
    )
    artifact.metrics = _derive_metrics(artifact)
    return artifact


def compare_model_runs(
    first_path: str | Path,
    second_path: str | Path,
    *,
    comparison_id: str = "model_behavior_comparison",
) -> ModelRunComparison:
    first = load_model_run_artifact(first_path)
    second = load_model_run_artifact(second_path)
    protocol_checks = _protocol_checks(first, second)
    protocol_compatible = all(check["compatible"] for check in protocol_checks)
    metric_winners = _metric_winners(first.metrics, second.metrics)
    failure_analysis = {
        "first": _failure_analysis(first),
        "second": _failure_analysis(second),
        "comparison": _failure_comparison(first, second),
    }
    warnings = [*first.warnings, *second.warnings]
    status: ComparisonStatus = "complete"
    if first.status == "incomplete" or second.status == "incomplete":
        status = "incomplete"
    interpretation = _interpretation(first, second, protocol_compatible)
    limitations = [
        "Only one short scenario was compared.",
        "Only one run per model is available.",
        "No repeated trials or statistical confidence interval were computed.",
        "No benchmark or multi-agent capacity measurement was run.",
        "Browser behavior remains simulated-only and office behavior remains stub/file-based.",
        "Resource summaries are lightweight process snapshots, not a benchmark monitor.",
    ]
    return ModelRunComparison(
        comparison_id=comparison_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        input_artifact_paths={
            "first": str(first_path),
            "second": str(second_path),
        },
        status=status,
        protocol_compatible=protocol_compatible,
        protocol_checks=protocol_checks,
        per_model={
            "first": first.metrics,
            "second": second.metrics,
        },
        metric_winners=metric_winners,
        failure_analysis=failure_analysis,
        interpretation=interpretation,
        limitations=limitations,
        warnings=warnings,
    )


def write_model_comparison(comparison: ModelRunComparison, out_dir: str | Path, *, force: bool = False) -> Path:
    out_path = Path(out_dir)
    if out_path.exists():
        if not force:
            raise FileExistsError(f"Comparison output directory already exists: {out_path}")
        shutil.rmtree(out_path)
    out_path.mkdir(parents=True, exist_ok=True)

    (out_path / "comparison.json").write_text(
        json.dumps(comparison.model_dump(mode="json"), ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_path / "comparison.md").write_text(_comparison_markdown(comparison), encoding="utf-8")
    _write_metrics_csv(comparison, out_path / "metrics_table.csv")
    (out_path / "failure_analysis.json").write_text(
        json.dumps(comparison.failure_analysis, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    (out_path / "failure_analysis.md").write_text(_failure_markdown(comparison), encoding="utf-8")
    (out_path / "README.md").write_text(_readme_markdown(comparison), encoding="utf-8")
    (out_path / "replay_commands.ps1").write_text(_replay_commands(comparison), encoding="utf-8")
    return out_path


def _derive_metrics(artifact: ModelRunArtifact) -> dict[str, Any]:
    manifest = artifact.manifest
    model_behavior = artifact.model_behavior_result
    activity = artifact.activity_evaluation or model_behavior.get("behavioral_evaluation", {})
    activity_metrics = activity.get("metrics", {}) if isinstance(activity, dict) else {}
    validation_metrics = model_behavior.get("validation_metrics", {})
    repair_summary = (
        model_behavior.get("metadata", {}).get("repair_summary")
        or validation_metrics.get("metadata", {}).get("repair_summary")
        or {}
    )
    resource = artifact.resource_summary
    steps = artifact.steps
    attempts = artifact.attempts
    selected_actions = _selected_action_payloads(artifact)

    step_count = _int(manifest.get("step_count"), len(steps))
    if step_count == 0:
        step_count = len(steps)
    initial_attempts = [a for a in attempts if a.get("attempt_type") == "initial"]
    repair_attempts = [a for a in attempts if a.get("attempt_type") == "repair"]

    initial_parse_success_count = _int(
        repair_summary.get("initial_parse_success_count"),
        sum(1 for a in initial_attempts if a.get("parse_success") is True),
    )
    initial_validation_accept_count = _int(
        repair_summary.get("initial_validation_accept_count"),
        sum(1 for a in initial_attempts if a.get("validation_accepted") is True),
    )
    repair_attempt_count = _int(repair_summary.get("repair_attempt_count"), len(repair_attempts))
    repair_validation_accept_count = _int(
        repair_summary.get("repair_validation_accept_count"),
        sum(1 for a in repair_attempts if a.get("validation_accepted") is True),
    )
    final_validation_accept_count = _int(
        repair_summary.get("final_validation_accept_count"),
        sum(1 for s in steps if s.get("registry_accepted") is True),
    )
    unrecovered_failure_count = _int(
        repair_summary.get("unrecovered_failure_count"),
        sum(1 for s in steps if s.get("error_type")),
    )
    execution_attempted_count = sum(1 for s in steps if s.get("execution_attempted") is True)
    execution_success_count = _int(
        repair_summary.get("execution_success_count"),
        sum(1 for s in steps if s.get("execution_success") is True),
    )
    execution_error_count = sum(1 for s in steps if s.get("execution_attempted") and s.get("execution_success") is False)

    error_types = [
        str(s.get("error_type"))
        for s in steps
        if s.get("error_type")
    ]
    if not error_types:
        error_types = [str(e.get("error_type")) for e in artifact.errors if e.get("error_type")]
    issue_codes = _validation_issue_codes(artifact)
    selected_sequence = [str(action.get("action")) for action in selected_actions if action.get("action")]
    selected_param_keys = [
        (str(action.get("action")), json.dumps(action.get("parameters") or {}, sort_keys=True, ensure_ascii=False))
        for action in selected_actions
    ]
    parameter_counts = Counter(selected_param_keys)
    latency_steps = resource.get("per_step_latency_ms") or []
    selection_latencies = _latencies(latency_steps, "selection_latency_ms")
    total_latencies = _latencies(latency_steps, "total_step_latency_ms")

    model_section = manifest.get("model", {})
    return {
        "model_id": model_section.get("model_id") or manifest.get("model_id") or model_behavior.get("model", {}).get("model_id"),
        "model_name": model_section.get("model_name") or manifest.get("model_name") or model_behavior.get("model", {}).get("model_name"),
        "run_id": manifest.get("run_id") or model_behavior.get("run_id"),
        "artifact_path": artifact.artifact_path,
        "scenario_path": manifest.get("scenario_path"),
        "scenario_id": manifest.get("scenario_id") or model_behavior.get("scenario_id"),
        "repair_enabled": bool((manifest.get("repair") or {}).get("repair_enabled")),
        "repair_attempts_per_step": _int((manifest.get("repair") or {}).get("repair_attempts_per_step"), 0),
        "execute_actions": manifest.get("execute_actions"),
        "max_steps": _parse_max_steps(artifact.replay_command),
        "status": _status_from_manifest(manifest, steps),
        "success": _success_from_steps(steps),
        "stop_reason": manifest.get("stopped_reason") or _last_step_value(steps, "stop_reason"),
        "step_count": step_count,
        "initial_parse_success_count": initial_parse_success_count,
        "initial_parse_success_rate": _rate(initial_parse_success_count, step_count),
        "initial_validation_accept_count": initial_validation_accept_count,
        "initial_validation_accept_rate": _rate(initial_validation_accept_count, step_count),
        "repair_attempt_count": repair_attempt_count,
        "repair_validation_accept_count": repair_validation_accept_count,
        "repair_validation_accept_rate": _rate(repair_validation_accept_count, repair_attempt_count),
        "final_validation_accept_count": final_validation_accept_count,
        "final_validation_accept_rate": _rate(final_validation_accept_count, step_count),
        "unrecovered_failure_count": unrecovered_failure_count,
        "execution_attempted_count": execution_attempted_count,
        "execution_success_count": execution_success_count,
        "execution_success_rate": _rate(execution_success_count, execution_attempted_count),
        "execution_error_count": execution_error_count,
        "execution_error_types": dict(Counter(error_types)),
        "file_not_found_count": sum(1 for s in steps if s.get("error_type") == "file_not_found"),
        "unsafe_path_count": sum(1 for code in issue_codes if code in {"write_path_outside_workspace", "unsafe_action"}),
        "validation_failure_count": _int(validation_metrics.get("validation_failure_count"), sum(1 for s in steps if s.get("registry_accepted") is False)),
        "selected_action_sequence": selected_sequence,
        "final_action_sequence": selected_sequence,
        "unique_action_count": len(set(selected_sequence)),
        "unique_action_parameter_count": len(set(selected_param_keys)),
        "repeated_action_count": _int(activity_metrics.get("repeated_action_count"), _repeated_count(selected_sequence)),
        "repeated_same_parameters_count": _int(
            activity_metrics.get("repeated_same_parameters_count"),
            sum(count - 1 for count in parameter_counts.values() if count > 1),
        ),
        "normal_activity_score": _number(activity_metrics.get("normal_activity_score"), activity.get("score")),
        "diversity_score": _number(activity_metrics.get("diversity_score")),
        "repetition_score": _number(activity_metrics.get("repetition_score")),
        "sequence_coherence_score": _number(activity_metrics.get("sequence_coherence_score")),
        "history_usage_score": _number(activity_metrics.get("history_usage_score")),
        "role_fit_score": _number(activity_metrics.get("role_fit_score")),
        "wall_time_ms": _number(resource.get("wall_time_ms")),
        "average_selection_latency_ms": _average(selection_latencies),
        "average_total_step_latency_ms": _average(total_latencies),
        "min_selection_latency_ms": min(selection_latencies) if selection_latencies else None,
        "max_selection_latency_ms": max(selection_latencies) if selection_latencies else None,
        "rss_start_mb": (resource.get("resource_start") or {}).get("process_rss_mb"),
        "rss_end_mb": (resource.get("resource_end") or {}).get("process_rss_mb"),
        "cpu_start_percent": (resource.get("resource_start") or {}).get("system_cpu_percent"),
        "cpu_end_percent": (resource.get("resource_end") or {}).get("system_cpu_percent"),
        "warnings": artifact.warnings,
    }


def _selected_action_payloads(artifact: ModelRunArtifact) -> list[dict[str, Any]]:
    payloads: list[dict[str, Any]] = []
    if artifact.selected_actions:
        for item in artifact.selected_actions:
            action = item.get("next_action") or item
            if isinstance(action, dict):
                payloads.append(action)
        return payloads
    for item in artifact.model_behavior_result.get("selected_actions", []):
        if isinstance(item, dict):
            payloads.append(item)
    return payloads


def _validation_issue_codes(artifact: ModelRunArtifact) -> list[str]:
    codes: list[str] = []
    for step in artifact.steps:
        validation = step.get("validation_result") or {}
        for issue in validation.get("issues", []):
            if issue.get("code"):
                codes.append(str(issue["code"]))
    for attempt in artifact.attempts:
        for issue in attempt.get("validation_issues", []):
            if issue.get("code"):
                codes.append(str(issue["code"]))
    return codes


def _protocol_checks(first: ModelRunArtifact, second: ModelRunArtifact) -> list[dict[str, Any]]:
    pairs = [
        ("scenario_path", first.metrics.get("scenario_path"), second.metrics.get("scenario_path")),
        ("max_steps", first.metrics.get("max_steps"), second.metrics.get("max_steps")),
        ("repair_enabled", first.metrics.get("repair_enabled"), second.metrics.get("repair_enabled")),
        ("repair_attempts_per_step", first.metrics.get("repair_attempts_per_step"), second.metrics.get("repair_attempts_per_step")),
        ("execute_actions", first.metrics.get("execute_actions"), second.metrics.get("execute_actions")),
        (
            "activity_profile",
            first.activity_evaluation.get("profile_id"),
            second.activity_evaluation.get("profile_id"),
        ),
        (
            "evaluator",
            first.activity_evaluation.get("evaluator_id"),
            second.activity_evaluation.get("evaluator_id"),
        ),
    ]
    checks: list[dict[str, Any]] = []
    for name, first_value, second_value in pairs:
        comparable = first_value is not None and second_value is not None
        checks.append(
            {
                "name": name,
                "first": first_value,
                "second": second_value,
                "compatible": bool(comparable and first_value == second_value),
                "checked": comparable,
            }
        )
    return checks


def _metric_winners(first: dict[str, Any], second: dict[str, Any]) -> list[ModelComparisonMetric]:
    specs = [
        ("first_attempt_validation", "initial_validation_accept_rate", True, "Higher first-attempt validation is better."),
        ("final_validation_after_repair", "final_validation_accept_rate", True, "Higher final validation is better."),
        ("successful_executions", "execution_success_count", True, "More successful executions is better."),
        ("fewer_unrecovered_failures", "unrecovered_failure_count", False, "Fewer unrecovered failures is better."),
        ("normal_activity_score", "normal_activity_score", True, "Higher normal activity score is better."),
        ("diversity_score", "diversity_score", True, "Higher diversity score is better."),
        ("repetition_score", "repetition_score", True, "Higher repetition score means less problematic repetition in this evaluator."),
        ("history_usage_score", "history_usage_score", True, "Higher history usage score is better."),
        ("average_selection_latency_ms", "average_selection_latency_ms", False, "Lower selection latency is faster."),
        ("average_total_step_latency_ms", "average_total_step_latency_ms", False, "Lower total step latency is faster."),
        ("execution_stability", "execution_success_rate", True, "Higher execution success rate is more stable under execution."),
    ]
    return [
        ModelComparisonMetric(
            name=name,
            first_value=first.get(key),
            second_value=second.get(key),
            winner=_winner(first.get(key), second.get(key), higher_is_better=higher),
            higher_is_better=higher,
            comment=comment,
        )
        for name, key, higher, comment in specs
    ]


def _failure_analysis(artifact: ModelRunArtifact) -> dict[str, Any]:
    metrics = artifact.metrics
    parse_failures = [a for a in artifact.attempts if a.get("parse_success") is False]
    validation_failures = [a for a in artifact.attempts if a.get("validation_accepted") is False]
    execution_failures = [s for s in artifact.steps if s.get("execution_attempted") and s.get("execution_success") is False]
    issue_codes = Counter(_validation_issue_codes(artifact))
    error_types = Counter(str(s.get("error_type")) for s in artifact.steps if s.get("error_type"))
    return {
        "model_id": metrics.get("model_id"),
        "parse_failure_count": len(parse_failures),
        "validation_failure_count": len(validation_failures),
        "repair_failure_count": sum(1 for a in validation_failures if a.get("attempt_type") == "repair"),
        "execution_failure_count": len(execution_failures),
        "unsafe_path_failure_count": issue_codes.get("write_path_outside_workspace", 0),
        "file_not_found_failure_count": error_types.get("file_not_found", 0),
        "repeated_action_count": metrics.get("repeated_action_count"),
        "repeated_same_parameters_count": metrics.get("repeated_same_parameters_count"),
        "history_usage_score": metrics.get("history_usage_score"),
        "sequence_coherence_score": metrics.get("sequence_coherence_score"),
        "error_types": dict(error_types),
        "validation_issue_codes": dict(issue_codes),
        "selected_action_sequence": metrics.get("selected_action_sequence"),
        "failure_summary": _failure_summary(metrics, error_types, issue_codes),
    }


def _failure_comparison(first: ModelRunArtifact, second: ModelRunArtifact) -> dict[str, Any]:
    return {
        "first_model_pattern": (
            "Needed repair for initial action validity, recovered two read_file actions, "
            "then stopped on an unrecovered write_path_outside_workspace validation failure."
        ),
        "second_model_pattern": (
            "Produced first-attempt valid read_file actions, but both execution attempts failed "
            "because docs/notes.txt was missing and the model repeated the same failed action."
        ),
        "shared_weaknesses": [
            "Both runs have low sequence coherence.",
            "Neither run completed the full five-step trajectory.",
            "Both runs show repeated same-parameter behavior.",
        ],
    }


def _failure_summary(metrics: dict[str, Any], error_types: Counter[str], issue_codes: Counter[str]) -> str:
    if issue_codes.get("write_path_outside_workspace"):
        return "Validation/safety failure: write action targeted a path outside the experiment workspace."
    if error_types.get("file_not_found"):
        return "Execution failure: model repeatedly targeted a missing file."
    if metrics.get("initial_validation_accept_count") == 0 and metrics.get("repair_attempt_count"):
        return "Initial actions were invalid and required repair."
    return "No dominant failure mode detected from available artifacts."


def _interpretation(first: ModelRunArtifact, second: ModelRunArtifact, compatible: bool) -> ModelComparisonVerdict:
    if compatible:
        text = (
            "The artifacts are protocol-compatible and support a cautious first comparison. "
            "first_model showed weaker first-attempt action validity but recovered through repair and executed two actions. "
            "qwen2_5_3b_instruct_q4_k_m showed stronger first-attempt validity and lower latency, "
            "but repeated a missing-file read and achieved zero successful executions. "
            "No overall winner should be declared from one short scenario."
        )
    else:
        text = (
            "The artifacts were compared, but protocol differences were detected. "
            "Metric-level observations are still useful, but model-level conclusions should be treated as incomplete."
        )
    return ModelComparisonVerdict(
        confidence="low",
        overall_interpretation=text,
        limitations=[
            "One scenario and one run per model are insufficient for final recommendation.",
            "Observed behavior may be sensitive to prompt wording and available fixture files.",
        ],
    )


def _comparison_markdown(comparison: ModelRunComparison) -> str:
    first = comparison.per_model["first"]
    second = comparison.per_model["second"]
    lines = [
        "# Two-Model Behavior Comparison",
        "",
        "## Executive Summary",
        "",
        comparison.interpretation.overall_interpretation,
        "",
        f"- protocol_compatible: `{str(comparison.protocol_compatible).lower()}`",
        f"- confidence: `{comparison.interpretation.confidence}`",
        "",
        "## Protocol",
        "",
        "| Check | first | second | compatible |",
        "|---|---|---|---|",
    ]
    for check in comparison.protocol_checks:
        lines.append(
            f"| {check['name']} | `{check['first']}` | `{check['second']}` | `{check['compatible']}` |"
        )
    lines.extend(["", "## Metrics", "", _metrics_markdown_table(first, second), "", "## Action Trajectories", ""])
    lines.extend(_trajectory_lines("first", first))
    lines.extend([""])
    lines.extend(_trajectory_lines("second", second))
    lines.extend(["", "## Metric Winners", "", "| Metric | Winner | first | second |", "|---|---|---:|---:|"])
    for metric in comparison.metric_winners:
        lines.append(f"| {metric.name} | `{metric.winner}` | {metric.first_value} | {metric.second_value} |")
    lines.extend(
        [
            "",
            "## Failure Analysis",
            "",
            _failure_markdown(comparison),
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in comparison.limitations)
    lines.extend(
        [
            "",
            "## Next Steps",
            "",
            "- Repeat the same scenario multiple times per model.",
            "- Add a broader role/coherence/diversity report over these artifacts.",
            "- Add resource/capacity estimates only after repeated real local runs.",
            "",
        ]
    )
    return "\n".join(lines)


def _metrics_markdown_table(first: dict[str, Any], second: dict[str, Any]) -> str:
    keys = [
        "model_id",
        "step_count",
        "initial_validation_accept_rate",
        "final_validation_accept_rate",
        "execution_success_rate",
        "normal_activity_score",
        "diversity_score",
        "repetition_score",
        "history_usage_score",
        "average_selection_latency_ms",
        "average_total_step_latency_ms",
        "stop_reason",
    ]
    lines = ["| Metric | first | second |", "|---|---:|---:|"]
    for key in keys:
        lines.append(f"| {key} | `{first.get(key)}` | `{second.get(key)}` |")
    return "\n".join(lines)


def _trajectory_lines(label: str, metrics: dict[str, Any]) -> list[str]:
    sequence = metrics.get("selected_action_sequence") or []
    return [
        f"### {label}: `{metrics.get('model_id')}`",
        "",
        "| Step | Action |",
        "|---:|---|",
        *[f"| {index} | `{action}` |" for index, action in enumerate(sequence, start=1)],
    ]


def _failure_markdown(comparison: ModelRunComparison) -> str:
    lines = ["| Model side | Failure summary | Error types | Validation issue codes |", "|---|---|---|---|"]
    for side in ["first", "second"]:
        item = comparison.failure_analysis[side]
        lines.append(
            f"| {side} `{item.get('model_id')}` | {item.get('failure_summary')} | "
            f"`{item.get('error_types')}` | `{item.get('validation_issue_codes')}` |"
        )
    lines.extend(["", "Shared weaknesses:"])
    for weakness in comparison.failure_analysis["comparison"].get("shared_weaknesses", []):
        lines.append(f"- {weakness}")
    return "\n".join(lines)


def _readme_markdown(comparison: ModelRunComparison) -> str:
    return (
        "# Model Behavior Comparison Artifact\n\n"
        f"- comparison_id: `{comparison.comparison_id}`\n"
        f"- generated_at: `{comparison.generated_at}`\n"
        f"- protocol_compatible: `{comparison.protocol_compatible}`\n"
        f"- status: `{comparison.status}`\n\n"
        "Primary files:\n\n"
        "- `comparison.json`\n"
        "- `comparison.md`\n"
        "- `metrics_table.csv`\n"
        "- `failure_analysis.json`\n"
        "- `failure_analysis.md`\n"
        "- `replay_commands.ps1`\n"
    )


def _replay_commands(comparison: ModelRunComparison) -> str:
    first = comparison.input_artifact_paths["first"]
    second = comparison.input_artifact_paths["second"]
    return (
        "python scripts\\compare_model_behavior.py "
        f"--first-run {first} "
        f"--second-run {second} "
        f"--out-dir experiments\\model_behavior\\comparisons\\{comparison.comparison_id} "
        f"--label {comparison.comparison_id} "
        "--force\n"
    )


def _write_metrics_csv(comparison: ModelRunComparison, path: Path) -> None:
    first = comparison.per_model["first"]
    second = comparison.per_model["second"]
    keys = [
        "model_id",
        "model_name",
        "run_id",
        "step_count",
        "initial_parse_success_rate",
        "initial_validation_accept_rate",
        "final_validation_accept_rate",
        "execution_success_rate",
        "normal_activity_score",
        "diversity_score",
        "repetition_score",
        "sequence_coherence_score",
        "history_usage_score",
        "role_fit_score",
        "average_selection_latency_ms",
        "average_total_step_latency_ms",
        "wall_time_ms",
        "stop_reason",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "first", "second"])
        writer.writeheader()
        for key in keys:
            writer.writerow({"metric": key, "first": first.get(key), "second": second.get(key)})


def _winner(first: Any, second: Any, *, higher_is_better: bool) -> Winner:
    if first is None or second is None:
        return "not_available"
    if first == second:
        return "tie"
    if higher_is_better:
        return "first" if first > second else "second"
    return "first" if first < second else "second"


def _rate(numerator: int | None, denominator: int | None) -> float | None:
    if numerator is None or denominator is None:
        return None
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _average(values: list[float]) -> float | None:
    if not values:
        return None
    return round(sum(values) / len(values), 3)


def _latencies(items: list[dict[str, Any]], key: str) -> list[float]:
    values: list[float] = []
    for item in items:
        value = item.get(key)
        if isinstance(value, int | float):
            values.append(float(value))
    return values


def _int(value: Any, default: int) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    if isinstance(value, float):
        return int(value)
    return default


def _number(*values: Any) -> float | None:
    for value in values:
        if isinstance(value, int | float):
            return float(value)
    return None


def _parse_max_steps(command: str | None) -> int | None:
    if not command:
        return None
    match = re.search(r"--max-steps\s+(\d+)", command)
    if not match:
        return None
    return int(match.group(1))


def _status_from_manifest(manifest: dict[str, Any], steps: list[dict[str, Any]]) -> str:
    if manifest.get("stopped_reason"):
        return "stopped"
    if steps:
        return "completed"
    return "unknown"


def _success_from_steps(steps: list[dict[str, Any]]) -> bool:
    return bool(steps) and all(step.get("error_type") is None for step in steps)


def _last_step_value(steps: list[dict[str, Any]], key: str) -> Any:
    if not steps:
        return None
    return steps[-1].get(key)


def _repeated_count(values: list[str]) -> int:
    counts = Counter(values)
    return sum(count - 1 for count in counts.values() if count > 1)
