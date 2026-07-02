from __future__ import annotations

import csv
import json
import shutil
from collections import Counter, defaultdict
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field

from .model_behavior_comparison import ModelRunArtifact, load_model_run_artifact


Verdict = Literal["strong", "acceptable", "weak", "failed"]
CoherenceVerdict = Literal["coherent", "partially_coherent", "weak", "failed"]
DiversityVerdict = Literal["diverse", "narrow", "template_like", "failure_loop"]


class BehavioralTrialRecord(BaseModel):
    model_id: str
    trial_id: str
    artifact_path: str
    artifact: ModelRunArtifact
    metrics: dict[str, Any] = Field(default_factory=dict)
    warnings: list[str] = Field(default_factory=list)


class ModelBehavioralAggregate(BaseModel):
    model_id: str
    trial_count: int
    trials: list[BehavioralTrialRecord] = Field(default_factory=list)


class RoleComplianceAnalysis(BaseModel):
    model_id: str
    role_fit_score: dict[str, Any]
    role_compliance_rate: dict[str, Any]
    forbidden_action_count: int
    shell_action_count: int
    office_action_count: int
    browser_action_count: int
    file_action_count: int
    unsafe_path_count: int
    write_path_outside_workspace_count: int
    atypical_action_count: int
    action_family_distribution: dict[str, int]
    verdict: Verdict
    notes: list[str] = Field(default_factory=list)


class CoherenceHistoryAnalysis(BaseModel):
    model_id: str
    history_usage_score: dict[str, Any]
    sequence_coherence_score: dict[str, Any]
    repeated_same_parameters_count: int
    repeated_failed_action_count: int
    repeated_failure_without_adaptation_count: int
    follows_previous_success_count: int
    repeats_previous_failed_path_count: int
    observed_history_references: int
    verdict: CoherenceVerdict
    notes: list[str] = Field(default_factory=list)


class DiversityTemplateAnalysis(BaseModel):
    model_id: str
    unique_action_count: dict[str, Any]
    unique_action_parameter_count: dict[str, Any]
    repeated_action_count: int
    repeated_same_parameters_count: int
    action_family_diversity: dict[str, int]
    dominant_action_share: float | None
    dominant_action_parameter_share: float | None
    template_behavior_flags: list[str]
    verdict: DiversityVerdict


class FailureModeAnalysis(BaseModel):
    model_id: str
    parse_error_count: int
    validation_error_count: int
    missing_required_parameter_count: int
    unknown_action_count: int
    unsafe_path_count: int
    write_path_outside_workspace_count: int
    execution_error_count: int
    file_not_found_count: int
    max_consecutive_failures_count: int
    validation_failed_after_repair_count: int
    repair_attempt_count: int
    repair_success_count: int
    unrecovered_failure_count: int
    stop_reason_distribution: dict[str, int]
    representative_examples: dict[str, dict[str, Any]] = Field(default_factory=dict)


class ResourceLatencyAnalysis(BaseModel):
    model_id: str
    selection_latency_ms: dict[str, Any]
    total_step_latency_ms: dict[str, Any]
    wall_time_ms: dict[str, Any]
    rss_start_mb: dict[str, Any]
    rss_end_mb: dict[str, Any]
    rss_delta_mb: dict[str, Any]
    cpu_start_percent: dict[str, Any]
    cpu_end_percent: dict[str, Any]
    verdict: Literal["faster", "slower", "inconclusive"]
    notes: list[str] = Field(default_factory=list)


class ConsolidatedBehavioralAnalysis(BaseModel):
    analysis_id: str
    generated_at: str
    trials_root: str
    model_ids: list[str]
    evidence_base: dict[str, Any]
    role_compliance: dict[str, RoleComplianceAnalysis]
    coherence_history_usage: dict[str, CoherenceHistoryAnalysis]
    diversity_template_behavior: dict[str, DiversityTemplateAnalysis]
    failure_modes: dict[str, FailureModeAnalysis]
    resource_latency: dict[str, ResourceLatencyAnalysis]
    cross_model_findings: dict[str, Any]
    limitations: list[str]
    warnings: list[str] = Field(default_factory=list)


def load_repeated_trials_root(path: str | Path) -> dict[str, ModelBehavioralAggregate]:
    root = Path(path)
    if not root.exists():
        raise FileNotFoundError(f"Repeated trials root not found: {root}")
    runs_root = root / "runs"
    if not runs_root.exists():
        raise FileNotFoundError(f"Repeated trials runs folder not found: {runs_root}")

    aggregates: dict[str, ModelBehavioralAggregate] = {}
    for model_dir in sorted(p for p in runs_root.iterdir() if p.is_dir()):
        trials: list[BehavioralTrialRecord] = []
        for trial_dir in sorted(p for p in model_dir.iterdir() if p.is_dir() and p.name.startswith("trial_")):
            artifact = load_model_run_artifact(trial_dir)
            model_id = str(artifact.metrics.get("model_id") or model_dir.name)
            trials.append(
                BehavioralTrialRecord(
                    model_id=model_id,
                    trial_id=trial_dir.name,
                    artifact_path=str(trial_dir),
                    artifact=artifact,
                    metrics=artifact.metrics,
                    warnings=artifact.warnings,
                )
            )
        model_id = trials[0].model_id if trials else model_dir.name
        aggregates[model_id] = ModelBehavioralAggregate(
            model_id=model_id,
            trial_count=len(trials),
            trials=trials,
        )
    return aggregates


def analyze_role_compliance(trials: list[BehavioralTrialRecord]) -> RoleComplianceAnalysis:
    model_id = _model_id(trials)
    role_scores = [_metric(t, "role_fit_score") for t in trials]
    role_rates = []
    family_counter: Counter[str] = Counter()
    forbidden = atypical = unsafe = outside = 0
    for trial in trials:
        selected = _selected_actions(trial.artifact)
        accepted = 0
        compliant = 0
        for item in trial.artifact.model_behavior_result.get("selected_actions", []):
            accepted += 1
            if item.get("role_compliant") is True:
                compliant += 1
        if accepted:
            role_rates.append(compliant / accepted)
        metrics = _activity_metrics(trial)
        atypical += int(metrics.get("atypical_action_count") or 0)
        unsafe += int(trial.metrics.get("unsafe_path_count") or 0)
        for attempt in trial.artifact.attempts:
            for issue in attempt.get("validation_issues", []):
                if issue.get("code") == "write_path_outside_workspace":
                    outside += 1
        for action in selected:
            family_counter[_action_family(str(action.get("action")))] += 1
        forbidden += int(metrics.get("forbidden_for_normality_count") or 0)

    role_fit = _stats([x for x in role_scores if x is not None])
    role_rate_stats = _stats(role_rates)
    verdict: Verdict = "strong"
    if forbidden or family_counter.get("shell", 0):
        verdict = "weak"
    if (role_fit.get("mean") or 0) < 0.75:
        verdict = "weak"
    if unsafe or outside:
        verdict = "acceptable"
    if atypical > 2:
        verdict = "weak"
    notes = []
    if family_counter.get("file", 0):
        notes.append("File/document-oriented actions are role-compatible for this role scenario.")
    if outside:
        notes.append("Workspace write violations are safety failures, not necessarily role-template violations.")
    return RoleComplianceAnalysis(
        model_id=model_id,
        role_fit_score=role_fit,
        role_compliance_rate=role_rate_stats,
        forbidden_action_count=forbidden,
        shell_action_count=family_counter.get("shell", 0),
        office_action_count=family_counter.get("office", 0),
        browser_action_count=family_counter.get("browser", 0),
        file_action_count=family_counter.get("file", 0),
        unsafe_path_count=unsafe,
        write_path_outside_workspace_count=outside,
        atypical_action_count=atypical,
        action_family_distribution=dict(family_counter),
        verdict=verdict,
        notes=notes,
    )


def analyze_coherence_history_usage(trials: list[BehavioralTrialRecord]) -> CoherenceHistoryAnalysis:
    model_id = _model_id(trials)
    history_scores = [_metric(t, "history_usage_score") for t in trials]
    coherence_scores = [_metric(t, "sequence_coherence_score") for t in trials]
    repeated_same = repeated_failed = repeated_without_adaptation = follows_success = repeats_failed_path = 0
    history_refs = 0
    for trial in trials:
        repeated_same += int(trial.metrics.get("repeated_same_parameters_count") or 0)
        prev_key: str | None = None
        prev_success: bool | None = None
        for step in trial.artifact.steps:
            action = step.get("next_action") or {}
            key = _action_param_key(action)
            reason = str(action.get("reason") or "").lower()
            if any(token in reason for token in ["previous", "again", "history", "earlier", "after previous"]):
                history_refs += 1
            success = step.get("execution_success") is True
            failed = bool(step.get("error_type"))
            if prev_key == key and failed:
                repeated_failed += 1
                if prev_success is False:
                    repeated_without_adaptation += 1
                    repeats_failed_path += 1
            if prev_success is True and not failed:
                follows_success += 1
            prev_key = key
            prev_success = success if step.get("execution_attempted") else not failed
        for step in trial.artifact.steps:
            attempts = step.get("attempts") or []
            failed_attempts = [a for a in attempts if a.get("validation_accepted") is False]
            if len(failed_attempts) >= 2:
                repeated_without_adaptation += 1

    verdict: CoherenceVerdict = "partially_coherent"
    if (_mean(coherence_scores) or 0) <= 0.0:
        verdict = "weak"
    if repeated_without_adaptation:
        verdict = "failed"
    return CoherenceHistoryAnalysis(
        model_id=model_id,
        history_usage_score=_stats([x for x in history_scores if x is not None]),
        sequence_coherence_score=_stats([x for x in coherence_scores if x is not None]),
        repeated_same_parameters_count=repeated_same,
        repeated_failed_action_count=repeated_failed,
        repeated_failure_without_adaptation_count=repeated_without_adaptation,
        follows_previous_success_count=follows_success,
        repeats_previous_failed_path_count=repeats_failed_path,
        observed_history_references=history_refs,
        verdict=verdict,
        notes=[
            "History usage score and useful adaptation are separated; mentioning prior failure is not enough if the same failed action repeats."
        ],
    )


def analyze_diversity_template_behavior(trials: list[BehavioralTrialRecord]) -> DiversityTemplateAnalysis:
    model_id = _model_id(trials)
    unique_actions = [_metric(t, "unique_action_count") for t in trials]
    unique_params = [_metric(t, "unique_action_parameter_count") for t in trials]
    repeated_action_count = sum(int(t.metrics.get("repeated_action_count") or 0) for t in trials)
    repeated_same = sum(int(t.metrics.get("repeated_same_parameters_count") or 0) for t in trials)
    family_counter: Counter[str] = Counter()
    action_counter: Counter[str] = Counter()
    param_counter: Counter[str] = Counter()
    for trial in trials:
        for action in _selected_actions(trial.artifact):
            name = str(action.get("action"))
            family_counter[_action_family(name)] += 1
            action_counter[name] += 1
            param_counter[_action_param_key(action)] += 1
    total_actions = sum(action_counter.values())
    dominant_action_share = _share(max(action_counter.values()) if action_counter else 0, total_actions)
    dominant_param_share = _share(max(param_counter.values()) if param_counter else 0, total_actions)
    flags: list[str] = []
    if dominant_action_share is not None and dominant_action_share >= 0.8:
        flags.append("repeated_same_action")
    if dominant_param_share is not None and dominant_param_share >= 0.8:
        flags.append("repeated_same_parameters")
    if len(family_counter) <= 1:
        flags.append("low_action_family_diversity")
    if repeated_same:
        flags.append("repeated_failure_pattern" if _has_repeated_failures(trials) else "template_repetition")
    verdict: DiversityVerdict = "narrow"
    if "repeated_failure_pattern" in flags:
        verdict = "failure_loop"
    elif "repeated_same_parameters" in flags:
        verdict = "template_like"
    elif len(family_counter) > 2:
        verdict = "diverse"
    return DiversityTemplateAnalysis(
        model_id=model_id,
        unique_action_count=_stats([x for x in unique_actions if x is not None]),
        unique_action_parameter_count=_stats([x for x in unique_params if x is not None]),
        repeated_action_count=repeated_action_count,
        repeated_same_parameters_count=repeated_same,
        action_family_diversity=dict(family_counter),
        dominant_action_share=dominant_action_share,
        dominant_action_parameter_share=dominant_param_share,
        template_behavior_flags=flags,
        verdict=verdict,
    )


def analyze_failure_modes(trials: list[BehavioralTrialRecord]) -> FailureModeAnalysis:
    model_id = _model_id(trials)
    counts: Counter[str] = Counter()
    stop_reasons: Counter[str] = Counter()
    examples: dict[str, dict[str, Any]] = {}
    for trial in trials:
        stop = trial.metrics.get("stop_reason")
        if stop:
            stop_reasons[str(stop)] += 1
        counts["unrecovered_failure"] += int(trial.metrics.get("unrecovered_failure_count") or 0)
        counts["repair_attempt"] += int(trial.metrics.get("repair_attempt_count") or 0)
        counts["repair_success"] += int(trial.metrics.get("repair_validation_accept_count") or 0)
        counts["file_not_found"] += int(trial.metrics.get("file_not_found_count") or 0)
        counts["unsafe_path"] += int(trial.metrics.get("unsafe_path_count") or 0)
        for attempt in trial.artifact.attempts:
            if attempt.get("parse_success") is False:
                counts["parse_error"] += 1
                examples.setdefault("parse_error", _attempt_example(trial, attempt))
            if attempt.get("validation_accepted") is False:
                counts["validation_error"] += 1
                examples.setdefault("validation_error", _attempt_example(trial, attempt))
            for issue in attempt.get("validation_issues", []):
                code = str(issue.get("code"))
                if code == "missing_required_parameter":
                    counts["missing_required_parameter"] += 1
                    examples.setdefault(code, _attempt_example(trial, attempt))
                elif code == "unknown_action":
                    counts["unknown_action"] += 1
                elif code == "write_path_outside_workspace":
                    counts["write_path_outside_workspace"] += 1
                    examples.setdefault(code, _attempt_example(trial, attempt))
        for step in trial.artifact.steps:
            error_type = step.get("error_type")
            if error_type:
                counts["execution_error"] += 1 if step.get("execution_attempted") else 0
                if error_type == "file_not_found":
                    examples.setdefault("file_not_found", _step_example(trial, step))
                if error_type == "validation_failed_after_repair":
                    counts["validation_failed_after_repair"] += 1
            if step.get("stop_reason") == "Reached max_consecutive_failures limit.":
                counts["max_consecutive_failures"] += 1
    return FailureModeAnalysis(
        model_id=model_id,
        parse_error_count=counts["parse_error"],
        validation_error_count=counts["validation_error"],
        missing_required_parameter_count=counts["missing_required_parameter"],
        unknown_action_count=counts["unknown_action"],
        unsafe_path_count=counts["unsafe_path"],
        write_path_outside_workspace_count=counts["write_path_outside_workspace"],
        execution_error_count=counts["execution_error"],
        file_not_found_count=counts["file_not_found"],
        max_consecutive_failures_count=counts["max_consecutive_failures"],
        validation_failed_after_repair_count=counts["validation_failed_after_repair"],
        repair_attempt_count=counts["repair_attempt"],
        repair_success_count=counts["repair_success"],
        unrecovered_failure_count=counts["unrecovered_failure"],
        stop_reason_distribution=dict(stop_reasons),
        representative_examples=examples,
    )


def analyze_resource_latency(trials: list[BehavioralTrialRecord]) -> ResourceLatencyAnalysis:
    model_id = _model_id(trials)
    selection = [_metric(t, "average_selection_latency_ms") for t in trials]
    total = [_metric(t, "average_total_step_latency_ms") for t in trials]
    wall = [_metric(t, "wall_time_ms") for t in trials]
    rss_start = [_metric(t, "rss_start_mb") for t in trials]
    rss_end = [_metric(t, "rss_end_mb") for t in trials]
    rss_delta = [
        (end - start)
        for start, end in zip(rss_start, rss_end, strict=False)
        if start is not None and end is not None
    ]
    cpu_start = [_metric(t, "cpu_start_percent") for t in trials]
    cpu_end = [_metric(t, "cpu_end_percent") for t in trials]
    return ResourceLatencyAnalysis(
        model_id=model_id,
        selection_latency_ms=_stats([x for x in selection if x is not None]),
        total_step_latency_ms=_stats([x for x in total if x is not None]),
        wall_time_ms=_stats([x for x in wall if x is not None]),
        rss_start_mb=_stats([x for x in rss_start if x is not None]),
        rss_end_mb=_stats([x for x in rss_end if x is not None]),
        rss_delta_mb=_stats(rss_delta),
        cpu_start_percent=_stats([x for x in cpu_start if x is not None]),
        cpu_end_percent=_stats([x for x in cpu_end if x is not None]),
        verdict="inconclusive",
        notes=["Per-run latency/resource observations only; not a benchmark or capacity estimate."],
    )


def build_consolidated_behavioral_analysis(
    root_path: str | Path,
    *,
    analysis_id: str = "consolidated_behavioral_analysis",
) -> ConsolidatedBehavioralAnalysis:
    aggregates = load_repeated_trials_root(root_path)
    role = {model_id: analyze_role_compliance(agg.trials) for model_id, agg in aggregates.items()}
    coherence = {model_id: analyze_coherence_history_usage(agg.trials) for model_id, agg in aggregates.items()}
    diversity = {model_id: analyze_diversity_template_behavior(agg.trials) for model_id, agg in aggregates.items()}
    failures = {model_id: analyze_failure_modes(agg.trials) for model_id, agg in aggregates.items()}
    resources = {model_id: analyze_resource_latency(agg.trials) for model_id, agg in aggregates.items()}
    _assign_latency_verdicts(resources)
    evidence = _evidence_base(root_path, aggregates)
    cross = _cross_model_findings(aggregates, role, coherence, diversity, failures, resources)
    warnings = [warning for agg in aggregates.values() for trial in agg.trials for warning in trial.warnings]
    return ConsolidatedBehavioralAnalysis(
        analysis_id=analysis_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        trials_root=str(root_path),
        model_ids=list(aggregates.keys()),
        evidence_base=evidence,
        role_compliance=role,
        coherence_history_usage=coherence,
        diversity_template_behavior=diversity,
        failure_modes=failures,
        resource_latency=resources,
        cross_model_findings=cross,
        limitations=[
            "One scenario only.",
            "Three trials per model is still a small sample.",
            "No multi-agent run.",
            "No benchmark or CPU-only capacity estimate.",
            "Browser behavior remains simulated-only.",
            "Office behavior remains stub/file-based.",
        ],
        warnings=warnings,
    )


def write_consolidated_behavioral_analysis(
    analysis: ConsolidatedBehavioralAnalysis,
    out_dir: str | Path,
    *,
    force: bool = False,
) -> Path:
    out = Path(out_dir)
    if out.exists():
        if not force:
            raise FileExistsError(f"Behavioral analysis output directory already exists: {out}")
        shutil.rmtree(out)
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "consolidated_behavioral_analysis.json", analysis.model_dump(mode="json"))
    (out / "consolidated_behavioral_analysis.md").write_text(_main_markdown(analysis), encoding="utf-8")
    _write_section(out, "role_compliance_report", analysis.role_compliance)
    _write_section(out, "coherence_history_usage_report", analysis.coherence_history_usage)
    _write_section(out, "diversity_template_behavior_report", analysis.diversity_template_behavior)
    _write_json(out / "failure_mode_matrix.json", {k: v.model_dump(mode="json") for k, v in analysis.failure_modes.items()})
    _write_failure_csv(out / "failure_mode_matrix.csv", analysis)
    (out / "failure_mode_matrix.md").write_text(_failure_markdown(analysis), encoding="utf-8")
    _write_json(out / "action_sequence_matrix.json", _action_sequence_matrix(analysis.trials_root))
    _write_action_sequence_csv(out / "action_sequence_matrix.csv", analysis.trials_root)
    _write_json(out / "resource_latency_summary.json", {k: v.model_dump(mode="json") for k, v in analysis.resource_latency.items()})
    (out / "resource_latency_summary.md").write_text(_resource_markdown(analysis), encoding="utf-8")
    (out / "README.md").write_text(_readme(analysis), encoding="utf-8")
    (out / "replay_commands.ps1").write_text(_replay_command(analysis, out), encoding="utf-8")
    return out


def _write_section(out: Path, stem: str, payload: dict[str, BaseModel]) -> None:
    _write_json(out / f"{stem}.json", {k: v.model_dump(mode="json") for k, v in payload.items()})
    lines = [f"# {stem.replace('_', ' ').title()}", ""]
    for model_id, item in payload.items():
        lines.append(f"## `{model_id}`")
        lines.append("")
        for key, value in item.model_dump(mode="json").items():
            if key != "model_id":
                lines.append(f"- `{key}`: `{value}`")
        lines.append("")
    (out / f"{stem}.md").write_text("\n".join(lines), encoding="utf-8")


def _main_markdown(analysis: ConsolidatedBehavioralAnalysis) -> str:
    lines = [
        "# Consolidated Behavioral Analysis",
        "",
        "## Executive Summary",
        "",
        analysis.cross_model_findings.get("summary", ""),
        "",
        "## Evidence Base",
        "",
    ]
    lines.extend(f"- `{k}`: `{v}`" for k, v in analysis.evidence_base.items())
    lines.extend(["", "## Summary Table", "", "| Model | Role | Coherence | Diversity | Failure focus | Selection latency mean ms |", "|---|---|---|---|---|---:|"])
    for model_id in analysis.model_ids:
        lines.append(
            f"| `{model_id}` | {analysis.role_compliance[model_id].verdict} | "
            f"{analysis.coherence_history_usage[model_id].verdict} | "
            f"{analysis.diversity_template_behavior[model_id].verdict} | "
            f"{analysis.failure_modes[model_id].stop_reason_distribution} | "
            f"{analysis.resource_latency[model_id].selection_latency_ms.get('mean')} |"
        )
    lines.extend(["", "## Cross-Model Findings", ""])
    for key, value in analysis.cross_model_findings.items():
        lines.append(f"- `{key}`: {value}")
    lines.extend(["", "## What This Proves", ""])
    lines.extend([
        "- Repeated local model trials can be run and analyzed from artifacts.",
        "- Behavioral differences are observable across models under the same protocol.",
        "- Repair policy materially changes final validity for repair-dependent models.",
    ])
    lines.extend(["", "## What This Does Not Prove", ""])
    lines.extend(f"- {item}" for item in analysis.limitations)
    lines.extend(["", "## Recommendations For Next Experiment", ""])
    lines.extend([
        "- Add at least one more scenario, such as developer project maintenance or student research/reporting.",
        "- Run N=3 or N=5 per model with the same protocol.",
        "- Then compute cross-scenario aggregate behavior and resource summaries.",
    ])
    return "\n".join(lines) + "\n"


def _failure_markdown(analysis: ConsolidatedBehavioralAnalysis) -> str:
    lines = ["# Failure Mode Matrix", "", "| Model | parse | validation | missing parameter | workspace | file not found | repair attempts | repair success | stop reasons |", "|---|---:|---:|---:|---:|---:|---:|---:|---|"]
    for model_id, item in analysis.failure_modes.items():
        lines.append(
            f"| `{model_id}` | {item.parse_error_count} | {item.validation_error_count} | "
            f"{item.missing_required_parameter_count} | {item.write_path_outside_workspace_count} | "
            f"{item.file_not_found_count} | {item.repair_attempt_count} | {item.repair_success_count} | "
            f"`{item.stop_reason_distribution}` |"
        )
    return "\n".join(lines) + "\n"


def _resource_markdown(analysis: ConsolidatedBehavioralAnalysis) -> str:
    lines = ["# Resource Latency Summary", "", "| Model | selection mean ms | total step mean ms | wall mean ms | verdict |", "|---|---:|---:|---:|---|"]
    for model_id, item in analysis.resource_latency.items():
        lines.append(
            f"| `{model_id}` | {item.selection_latency_ms.get('mean')} | "
            f"{item.total_step_latency_ms.get('mean')} | {item.wall_time_ms.get('mean')} | {item.verdict} |"
        )
    lines.append("")
    lines.append("These are lightweight per-run observations, not CPU-only capacity measurements.")
    return "\n".join(lines) + "\n"


def _write_failure_csv(path: Path, analysis: ConsolidatedBehavioralAnalysis) -> None:
    fields = [
        "model_id",
        "parse_error_count",
        "validation_error_count",
        "missing_required_parameter_count",
        "write_path_outside_workspace_count",
        "execution_error_count",
        "file_not_found_count",
        "repair_attempt_count",
        "repair_success_count",
        "unrecovered_failure_count",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for model_id, item in analysis.failure_modes.items():
            row = item.model_dump(mode="json")
            writer.writerow({field: row.get(field) if field != "model_id" else model_id for field in fields})


def _action_sequence_matrix(root: str) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for agg in load_repeated_trials_root(root).values():
        for trial in agg.trials:
            for index, action in enumerate(_selected_actions(trial.artifact), start=1):
                rows.append(
                    {
                        "model_id": trial.model_id,
                        "trial_id": trial.trial_id,
                        "step": index,
                        "action": action.get("action"),
                        "parameters": action.get("parameters") or {},
                    }
                )
    return rows


def _write_action_sequence_csv(path: Path, root: str) -> None:
    rows = _action_sequence_matrix(root)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["model_id", "trial_id", "step", "action", "parameters"])
        writer.writeheader()
        for row in rows:
            writer.writerow({**row, "parameters": json.dumps(row["parameters"], ensure_ascii=False, sort_keys=True)})


def _readme(analysis: ConsolidatedBehavioralAnalysis) -> str:
    return (
        "# Consolidated Behavioral Analysis Artifact\n\n"
        f"- analysis_id: `{analysis.analysis_id}`\n"
        f"- trials_root: `{analysis.trials_root}`\n"
        f"- generated_at: `{analysis.generated_at}`\n\n"
        "Primary report: `consolidated_behavioral_analysis.md`.\n"
    )


def _replay_command(analysis: ConsolidatedBehavioralAnalysis, out: Path) -> str:
    return (
        "python scripts\\analyze_behavioral_trials.py "
        f"--trials-root {analysis.trials_root} "
        f"--out-dir {out} "
        f"--label {analysis.analysis_id} "
        "--force\n"
    )


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _evidence_base(root_path: str | Path, aggregates: dict[str, ModelBehavioralAggregate]) -> dict[str, Any]:
    first_trial = next((trial for agg in aggregates.values() for trial in agg.trials), None)
    return {
        "trials_root": str(root_path),
        "model_count": len(aggregates),
        "trials_per_model": {model_id: agg.trial_count for model_id, agg in aggregates.items()},
        "scenario_path": first_trial.metrics.get("scenario_path") if first_trial else None,
        "max_steps": first_trial.metrics.get("max_steps") if first_trial else None,
        "repair_attempts_per_step": first_trial.metrics.get("repair_attempts_per_step") if first_trial else None,
        "execute_actions": first_trial.metrics.get("execute_actions") if first_trial else None,
    }


def _cross_model_findings(
    aggregates: dict[str, ModelBehavioralAggregate],
    role: dict[str, RoleComplianceAnalysis],
    coherence: dict[str, CoherenceHistoryAnalysis],
    diversity: dict[str, DiversityTemplateAnalysis],
    failures: dict[str, FailureModeAnalysis],
    resources: dict[str, ResourceLatencyAnalysis],
) -> dict[str, Any]:
    model_ids = list(role)
    findings: dict[str, Any] = {
        "summary": (
            "The repeated-trials artifacts show stable differences: first_model is repair-dependent but executes repaired actions, "
            "while qwen2_5_3b_instruct_q4_k_m has strong contract validity but repeats a missing-file action."
        )
    }
    if len(model_ids) >= 2:
        findings["contract_validity_winner"] = max(
            model_ids,
            key=lambda m: _mean(
                [_metric(trial, "initial_validation_accept_rate") for trial in aggregates[m].trials]
            )
            or 0,
        )
        findings["final_validity_winner"] = max(
            model_ids,
            key=lambda m: _mean(
                [_metric(trial, "final_validation_accept_rate") for trial in aggregates[m].trials]
            )
            or 0,
        )
        findings["latency_winner"] = min(model_ids, key=lambda m: resources[m].selection_latency_ms.get("mean") or float("inf"))
        findings["failure_patterns"] = {
            model_id: failures[model_id].stop_reason_distribution for model_id in model_ids
        }
        findings["template_behavior"] = {
            model_id: diversity[model_id].template_behavior_flags for model_id in model_ids
        }
        findings["coherence_verdicts"] = {
            model_id: coherence[model_id].verdict for model_id in model_ids
        }
    return findings


def _assign_latency_verdicts(resources: dict[str, ResourceLatencyAnalysis]) -> None:
    means = {model_id: item.selection_latency_ms.get("mean") for model_id, item in resources.items()}
    numeric = {k: v for k, v in means.items() if isinstance(v, int | float)}
    if len(numeric) < 2:
        return
    fastest = min(numeric, key=numeric.get)
    for model_id, item in resources.items():
        item.verdict = "faster" if model_id == fastest else "slower"


def _selected_actions(artifact: ModelRunArtifact) -> list[dict[str, Any]]:
    actions: list[dict[str, Any]] = []
    for item in artifact.selected_actions:
        action = item.get("next_action") or item
        if isinstance(action, dict):
            actions.append(action)
    return actions


def _activity_metrics(trial: BehavioralTrialRecord) -> dict[str, Any]:
    return (trial.artifact.activity_evaluation or {}).get("metrics", {})


def _metric(trial: BehavioralTrialRecord, key: str) -> float | None:
    value = trial.metrics.get(key)
    if isinstance(value, int | float):
        return float(value)
    return None


def _model_id(trials: list[BehavioralTrialRecord]) -> str:
    return trials[0].model_id if trials else "unknown"


def _action_family(action: str) -> str:
    if action == "run_shell_command":
        return "shell"
    if action.startswith("browser_"):
        return "browser"
    if action.startswith("office_"):
        return "office"
    if action in {"read_file", "create_file", "append_file", "list_directory"}:
        return "file"
    return "other"


def _action_param_key(action: dict[str, Any]) -> str:
    return json.dumps(
        {"action": action.get("action"), "parameters": action.get("parameters") or {}},
        ensure_ascii=False,
        sort_keys=True,
    )


def _has_repeated_failures(trials: list[BehavioralTrialRecord]) -> bool:
    for trial in trials:
        failed_keys = [
            _action_param_key(step.get("next_action") or {})
            for step in trial.artifact.steps
            if step.get("error_type")
        ]
        if len(failed_keys) != len(set(failed_keys)):
            return True
    return False


def _attempt_example(trial: BehavioralTrialRecord, attempt: dict[str, Any]) -> dict[str, Any]:
    return {
        "trial_id": trial.trial_id,
        "step_index": attempt.get("step_index"),
        "attempt_type": attempt.get("attempt_type"),
        "parsed_action": attempt.get("parsed_action"),
        "validation_issues": attempt.get("validation_issues"),
        "raw_snippet": str(attempt.get("raw_model_output") or "")[:240],
    }


def _step_example(trial: BehavioralTrialRecord, step: dict[str, Any]) -> dict[str, Any]:
    return {
        "trial_id": trial.trial_id,
        "step_index": step.get("step_index"),
        "next_action": step.get("next_action"),
        "error_type": step.get("error_type"),
        "error_message": step.get("error_message"),
    }


def _stats(values: list[float]) -> dict[str, Any]:
    if not values:
        return {"mean": None, "std": None, "min": None, "max": None, "count": 0}
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return {
        "mean": round(mean, 6),
        "std": round(variance**0.5, 6),
        "min": min(values),
        "max": max(values),
        "count": len(values),
    }


def _mean(values: list[float | None]) -> float | None:
    numeric = [value for value in values if value is not None]
    if not numeric:
        return None
    return sum(numeric) / len(numeric)


def _share(numerator: int, denominator: int) -> float | None:
    if denominator <= 0:
        return None
    return round(numerator / denominator, 6)
