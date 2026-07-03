from __future__ import annotations

import csv
import json
import math
from collections import Counter
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from .evaluation_models import EvaluationModelRegistry, load_evaluation_models_config


PairRunStatus = Literal["completed", "reused", "failed", "skipped"]


class PairSpec(BaseModel):
    orchestrator_model_id: str
    executor_model_id: str

    @field_validator("orchestrator_model_id", "executor_model_id")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("PairSpec model ids must be non-empty.")
        return value.strip()

    @property
    def pair_id(self) -> str:
        return pair_id_for(self.orchestrator_model_id, self.executor_model_id)

    @property
    def label(self) -> str:
        return f"{self.orchestrator_model_id}->{self.executor_model_id}"


class PairRunReference(BaseModel):
    pair_id: str
    orchestrator_model_id: str
    executor_model_id: str
    source: Literal["generated", "reused", "failed", "skipped"]
    artifact_path: str
    original_artifact_path: str | None = None
    protocol_match: bool | None = None
    protocol_notes: list[str] = Field(default_factory=list)
    server_strategy: str | None = None
    server_notes: list[str] = Field(default_factory=list)


class PairMatrixAggregate(BaseModel):
    orchestrator_model_id: str
    executor_model_id: str
    orchestrator_upstream_name: str | None = None
    executor_upstream_name: str | None = None
    trial_count: int = 0
    completed_trial_count: int = 0
    failed_trial_count: int = 0
    mean_pair_quality_score: float | None = None
    std_pair_quality_score: float | None = None
    mean_execution_success_rate: float | None = None
    mean_final_validation_success_rate: float | None = None
    mean_plan_valid_rate: float | None = None
    mean_executor_model_calls: float | None = None
    total_errors: int = 0
    common_failure_modes: dict[str, int] = Field(default_factory=dict)
    mean_wall_time_ms: float | None = None
    mean_orchestrator_latency_ms: float | None = None
    mean_executor_latency_ms: float | None = None
    safety_violation_count: int = 0
    pair_verdict_distribution: dict[str, int] = Field(default_factory=dict)
    resource_notes: list[str] = Field(default_factory=list)


class PairMatrixRunResult(BaseModel):
    spec: PairSpec
    pair_id: str
    status: PairRunStatus
    reference: PairRunReference
    aggregate: PairMatrixAggregate | None = None
    trial_index: list[dict[str, Any]] = Field(default_factory=list)
    prototype_pair_rank_score: float | None = None
    error_message: str | None = None
    skipped_reason: str | None = None


class PairMatrixComparisonResult(BaseModel):
    comparison_id: str
    generated_at: str
    scenario_path: str
    mode: Literal["fake", "local"]
    trials_per_pair: int
    pairs: list[PairMatrixRunResult]
    rankings: list[dict[str, Any]]
    best_observed_pair: str | None = None
    pair_failure_modes: dict[str, dict[str, int]] = Field(default_factory=dict)
    pair_resource_summary: dict[str, Any] = Field(default_factory=dict)
    limitations: list[str] = Field(default_factory=list)
    interpretation: dict[str, Any] = Field(default_factory=dict)


def pair_id_for(orchestrator_model_id: str, executor_model_id: str) -> str:
    return f"{orchestrator_model_id}__{executor_model_id}".replace(":", "_").replace("/", "_")


def parse_pair_spec(value: str) -> PairSpec:
    if ":" not in value:
        raise ValueError(f"Pair must use orchestrator:executor format: {value}")
    orchestrator_model_id, executor_model_id = value.split(":", 1)
    return PairSpec(orchestrator_model_id=orchestrator_model_id, executor_model_id=executor_model_id)


def parse_pair_specs(value: str) -> list[PairSpec]:
    pairs = [parse_pair_spec(item.strip()) for item in value.split(",") if item.strip()]
    if not pairs:
        raise ValueError("At least one pair must be provided.")
    seen: set[str] = set()
    duplicates: list[str] = []
    for pair in pairs:
        if pair.pair_id in seen:
            duplicates.append(pair.label)
        seen.add(pair.pair_id)
    if duplicates:
        raise ValueError(f"Duplicate pair specs: {', '.join(duplicates)}")
    return pairs


def load_repeated_group_trials(root: str | Path) -> dict[str, Any]:
    root_path = Path(root)
    reference_path = root_path / "reused_pair_run.json"
    if reference_path.exists():
        reference = _read_json(reference_path)
        original = reference.get("original_artifact_path")
        if not original:
            raise ValueError(f"reused_pair_run.json has no original_artifact_path: {reference_path}")
        return load_repeated_group_trials(original)
    result_path = root_path / "repeated_group_trials_result.json"
    if not result_path.exists():
        raise FileNotFoundError(f"Repeated group result not found: {result_path}")
    return _read_json(result_path)


def aggregate_pair_result(
    pair_root: str | Path,
    *,
    models_config_path: str | Path = "configs/evaluation_models.json",
    project_root: str | Path = ".",
    reference_source: Literal["generated", "reused"] = "generated",
    original_artifact_path: str | None = None,
    protocol_match: bool | None = None,
    protocol_notes: list[str] | None = None,
    server_strategy: str | None = None,
    server_notes: list[str] | None = None,
) -> PairMatrixRunResult:
    pair_root_path = Path(pair_root)
    repeated = load_repeated_group_trials(original_artifact_path or pair_root_path)
    spec = PairSpec(
        orchestrator_model_id=str(repeated["orchestrator_model_id"]),
        executor_model_id=str(repeated["executor_model_id"]),
    )
    aggregate_payload = repeated.get("aggregate") or {}
    trial_index = list(repeated.get("trial_index") or [])
    verdict_distribution = Counter(str(row.get("pair_verdict") or "unknown") for row in trial_index)
    upstream = _model_upstream_names(models_config_path, project_root)
    resource_notes_payload = _resource_notes(aggregate_payload, reference_source, server_strategy)
    if server_notes:
        resource_notes_payload.extend(server_notes)
    aggregate = PairMatrixAggregate(
        orchestrator_model_id=spec.orchestrator_model_id,
        executor_model_id=spec.executor_model_id,
        orchestrator_upstream_name=upstream.get(spec.orchestrator_model_id),
        executor_upstream_name=upstream.get(spec.executor_model_id),
        trial_count=_int(aggregate_payload.get("trial_count")),
        completed_trial_count=_int(aggregate_payload.get("completed_trial_count")),
        failed_trial_count=_int(aggregate_payload.get("failed_trial_count")),
        mean_pair_quality_score=_number(aggregate_payload.get("mean_pair_quality_score")),
        std_pair_quality_score=_number(aggregate_payload.get("std_pair_quality_score")),
        mean_execution_success_rate=_number(aggregate_payload.get("mean_execution_success_rate")),
        mean_final_validation_success_rate=_number(aggregate_payload.get("mean_final_validation_success_rate")),
        mean_plan_valid_rate=_number(aggregate_payload.get("mean_plan_valid_rate")),
        mean_executor_model_calls=_number(aggregate_payload.get("mean_executor_call_count")),
        total_errors=_int(aggregate_payload.get("total_errors")),
        common_failure_modes={str(k): _int(v) for k, v in (aggregate_payload.get("common_failure_modes") or {}).items()},
        mean_wall_time_ms=_number(aggregate_payload.get("mean_wall_time_ms")),
        mean_orchestrator_latency_ms=_number(aggregate_payload.get("mean_orchestrator_latency_ms")),
        mean_executor_latency_ms=_number(aggregate_payload.get("mean_executor_latency_ms")),
        safety_violation_count=_int(aggregate_payload.get("total_safety_violations")),
        pair_verdict_distribution=dict(verdict_distribution),
        resource_notes=resource_notes_payload,
    )
    reference = PairRunReference(
        pair_id=spec.pair_id,
        orchestrator_model_id=spec.orchestrator_model_id,
        executor_model_id=spec.executor_model_id,
        source=reference_source,
        artifact_path=str(pair_root_path),
        original_artifact_path=original_artifact_path,
        protocol_match=protocol_match,
        protocol_notes=protocol_notes or [],
        server_strategy=server_strategy,
        server_notes=server_notes or [],
    )
    status: PairRunStatus = "reused" if reference_source == "reused" else "completed"
    return PairMatrixRunResult(
        spec=spec,
        pair_id=spec.pair_id,
        status=status,
        reference=reference,
        aggregate=aggregate,
        trial_index=trial_index,
        prototype_pair_rank_score=prototype_pair_rank_score(aggregate),
    )


def failed_pair_result(
    spec: PairSpec,
    pair_root: str | Path,
    error_message: str,
    *,
    source: Literal["failed", "skipped"] = "failed",
    protocol_notes: list[str] | None = None,
    server_strategy: str | None = None,
    server_notes: list[str] | None = None,
) -> PairMatrixRunResult:
    status: PairRunStatus = "skipped" if source == "skipped" else "failed"
    aggregate = PairMatrixAggregate(
        orchestrator_model_id=spec.orchestrator_model_id,
        executor_model_id=spec.executor_model_id,
        total_errors=1,
        common_failure_modes={error_message.split(":", 1)[0] or "pair_error": 1},
        resource_notes=server_notes or [],
    )
    reference = PairRunReference(
        pair_id=spec.pair_id,
        orchestrator_model_id=spec.orchestrator_model_id,
        executor_model_id=spec.executor_model_id,
        source=source,
        artifact_path=str(Path(pair_root)),
        protocol_match=False,
        protocol_notes=protocol_notes or [],
        server_strategy=server_strategy,
        server_notes=server_notes or [],
    )
    return PairMatrixRunResult(
        spec=spec,
        pair_id=spec.pair_id,
        status=status,
        reference=reference,
        aggregate=aggregate,
        prototype_pair_rank_score=0.0,
        error_message=error_message,
        skipped_reason=error_message if source == "skipped" else None,
    )


def validate_repeated_run_protocol(
    root: str | Path,
    spec: PairSpec,
    *,
    scenario_path: str,
    mode: Literal["fake", "local"],
    trials: int,
    max_group_steps: int | None,
    max_steps_per_agent: int | None,
    orchestrator_repair_attempts: int,
    repair_attempts: int,
    execute_actions: bool,
    orchestrator_max_tokens: int | None = None,
) -> tuple[bool, list[str]]:
    notes: list[str] = []
    try:
        repeated = load_repeated_group_trials(root)
    except Exception as exc:
        return False, [f"could not load repeated group run: {exc}"]

    def check(name: str, observed: Any, expected: Any) -> None:
        if expected is not None and observed != expected:
            notes.append(f"{name} mismatch: observed={observed!r}, expected={expected!r}")

    check("orchestrator_model_id", repeated.get("orchestrator_model_id"), spec.orchestrator_model_id)
    check("executor_model_id", repeated.get("executor_model_id"), spec.executor_model_id)
    aggregate = repeated.get("aggregate") or {}
    check("trial_count", aggregate.get("trial_count"), trials)
    if _int(aggregate.get("completed_trial_count")) <= 0:
        notes.append("completed_trial_count is zero")

    trial_index = repeated.get("trial_index") or []
    first_artifact = Path(str(trial_index[0].get("artifact_path"))) if trial_index else None
    manifest_path = first_artifact / "manifest.json" if first_artifact else Path(root) / "runs" / "trial_001" / "manifest.json"
    if not manifest_path.exists():
        notes.append(f"trial manifest missing: {manifest_path}")
    else:
        manifest = _read_json(manifest_path)
        check("mode", manifest.get("mode"), mode)
        check("scenario_path", _norm_path(str(manifest.get("scenario_path") or "")), _norm_path(scenario_path))
        check("max_group_steps", manifest.get("max_group_steps"), max_group_steps)
        check("max_steps_per_agent", manifest.get("max_steps_per_agent"), max_steps_per_agent)
        check("orchestrator_repair_attempts", manifest.get("orchestrator_repair_attempts"), orchestrator_repair_attempts)
        check("executor_repair_attempts", manifest.get("executor_repair_attempts"), repair_attempts)
        check("execute_actions", manifest.get("execute_actions"), execute_actions)
        check("orchestrator_max_tokens", manifest.get("orchestrator_max_tokens"), orchestrator_max_tokens)
    if not notes:
        notes.append("protocol matched requested pair matrix settings")
    return all("mismatch" not in note and "missing" not in note and "could not" not in note for note in notes), notes


def compare_pair_results(
    pair_results: list[PairMatrixRunResult],
    *,
    comparison_id: str,
    scenario_path: str,
    mode: Literal["fake", "local"],
    trials_per_pair: int,
) -> PairMatrixComparisonResult:
    ranked = rank_pairs(pair_results)
    best = ranked[0]["pair"] if ranked else None
    failure_modes = {
        result.pair_id: (result.aggregate.common_failure_modes if result.aggregate else {})
        for result in pair_results
    }
    resource_summary = {
        result.pair_id: {
            "mean_wall_time_ms": result.aggregate.mean_wall_time_ms if result.aggregate else None,
            "mean_orchestrator_latency_ms": result.aggregate.mean_orchestrator_latency_ms if result.aggregate else None,
            "mean_executor_latency_ms": result.aggregate.mean_executor_latency_ms if result.aggregate else None,
            "resource_notes": result.aggregate.resource_notes if result.aggregate else [],
            "server_strategy": result.reference.server_strategy,
        }
        for result in pair_results
    }
    return PairMatrixComparisonResult(
        comparison_id=comparison_id,
        generated_at=datetime.now(timezone.utc).isoformat(),
        scenario_path=scenario_path,
        mode=mode,
        trials_per_pair=trials_per_pair,
        pairs=pair_results,
        rankings=ranked,
        best_observed_pair=best,
        pair_failure_modes=failure_modes,
        pair_resource_summary=resource_summary,
        limitations=[
            "Only one group scenario is included.",
            "N=3 per pair is directional prototype evidence, not a benchmark.",
            "No GPU runtime was configured or measured.",
            "No stress or concurrent capacity test was run.",
            "prototype_pair_rank_score is not a final production score.",
        ],
        interpretation=_interpretation(pair_results, best),
    )


def rank_pairs(pair_results: list[PairMatrixRunResult]) -> list[dict[str, Any]]:
    rows: list[dict[str, Any]] = []
    for result in pair_results:
        aggregate = result.aggregate
        score = result.prototype_pair_rank_score
        if aggregate is None:
            score = 0.0
        elif score is None:
            score = prototype_pair_rank_score(aggregate)
        rows.append(
            {
                "rank": 0,
                "pair": result.spec.label,
                "pair_id": result.pair_id,
                "status": result.status,
                "completed_trials": aggregate.completed_trial_count if aggregate else 0,
                "failed_trials": aggregate.failed_trial_count if aggregate else 0,
                "mean_pair_quality_score": aggregate.mean_pair_quality_score if aggregate else None,
                "std_pair_quality_score": aggregate.std_pair_quality_score if aggregate else None,
                "mean_execution_success_rate": aggregate.mean_execution_success_rate if aggregate else None,
                "mean_final_validation_success_rate": aggregate.mean_final_validation_success_rate if aggregate else None,
                "total_errors": aggregate.total_errors if aggregate else 0,
                "common_failure_modes": aggregate.common_failure_modes if aggregate else {},
                "prototype_pair_rank_score": score,
            }
        )
    rows.sort(
        key=lambda row: (
            float(row["prototype_pair_rank_score"] or 0.0),
            int(row["completed_trials"] or 0),
            -int(row["failed_trials"] or 0),
        ),
        reverse=True,
    )
    for index, row in enumerate(rows, start=1):
        row["rank"] = index
    return rows


def prototype_pair_rank_score(aggregate: PairMatrixAggregate) -> float:
    quality = _clamp01(aggregate.mean_pair_quality_score)
    execution = _clamp01(aggregate.mean_execution_success_rate)
    final_validation = _clamp01(aggregate.mean_final_validation_success_rate)
    plan_valid = _clamp01(aggregate.mean_plan_valid_rate)
    stability = _stability_component(aggregate.std_pair_quality_score)
    latency = _latency_component(aggregate.mean_wall_time_ms)
    score = (
        0.35 * quality
        + 0.25 * execution
        + 0.15 * final_validation
        + 0.10 * plan_valid
        + 0.10 * stability
        + 0.05 * latency
    )
    if aggregate.failed_trial_count:
        score -= min(0.25, aggregate.failed_trial_count * 0.05)
    if aggregate.total_errors:
        score -= min(0.25, aggregate.total_errors * 0.02)
    return round(max(0.0, min(1.0, score)), 6)


def write_pair_matrix_report(
    result: PairMatrixComparisonResult,
    out_dir: str | Path,
    *,
    replay_command: str | None = None,
) -> Path:
    out_path = Path(out_dir)
    out_path.mkdir(parents=True, exist_ok=True)
    _write_json(out_path / "pair_matrix_index.json", [_index_row(pair) for pair in result.pairs])
    _write_index_csv(result.pairs, out_path / "pair_matrix_index.csv")
    _write_json(out_path / "pair_matrix_comparison.json", result.model_dump(mode="json"))
    (out_path / "pair_matrix_comparison.md").write_text(_comparison_markdown(result), encoding="utf-8")
    _write_rankings_csv(result.rankings, out_path / "pair_rankings.csv")
    _write_json(out_path / "pair_failure_modes.json", result.pair_failure_modes)
    (out_path / "pair_failure_modes.md").write_text(_failure_modes_markdown(result), encoding="utf-8")
    _write_json(out_path / "pair_resource_summary.json", result.pair_resource_summary)
    (out_path / "pair_resource_summary.md").write_text(_resource_summary_markdown(result), encoding="utf-8")
    (out_path / "README.md").write_text(_readme_markdown(result), encoding="utf-8")
    (out_path / "replay_commands.ps1").write_text((replay_command or "").rstrip() + "\n", encoding="utf-8")
    return out_path


def write_reused_pair_reference(
    pair_root: str | Path,
    spec: PairSpec,
    original_artifact_path: str,
    *,
    protocol_match: bool,
    protocol_notes: list[str],
) -> None:
    pair_root_path = Path(pair_root)
    pair_root_path.mkdir(parents=True, exist_ok=True)
    payload = {
        "pair_id": spec.pair_id,
        "orchestrator_model_id": spec.orchestrator_model_id,
        "executor_model_id": spec.executor_model_id,
        "original_artifact_path": original_artifact_path,
        "protocol_match": protocol_match,
        "protocol_notes": protocol_notes,
        "created_at": datetime.now(timezone.utc).isoformat(),
    }
    _write_json(pair_root_path / "reused_pair_run.json", payload)
    (pair_root_path / "README.md").write_text(
        "# Reused Pair Run\n\n"
        f"- pair: `{spec.label}`\n"
        f"- original artifact: `{original_artifact_path}`\n"
        f"- protocol_match: `{protocol_match}`\n",
        encoding="utf-8",
    )


def write_failed_pair_artifact(pair_root: str | Path, result: PairMatrixRunResult) -> None:
    pair_root_path = Path(pair_root)
    pair_root_path.mkdir(parents=True, exist_ok=True)
    _write_json(pair_root_path / "pair_error.json", result.model_dump(mode="json"))
    (pair_root_path / "README.md").write_text(
        "# Failed Pair Run\n\n"
        f"- pair: `{result.spec.label}`\n"
        f"- status: `{result.status}`\n"
        f"- error: `{result.error_message or result.skipped_reason or ''}`\n",
        encoding="utf-8",
    )


def _index_row(result: PairMatrixRunResult) -> dict[str, Any]:
    aggregate = result.aggregate
    return {
        "pair": result.spec.label,
        "pair_id": result.pair_id,
        "status": result.status,
        "source": result.reference.source,
        "artifact_path": result.reference.artifact_path,
        "original_artifact_path": result.reference.original_artifact_path,
        "completed_trials": aggregate.completed_trial_count if aggregate else 0,
        "failed_trials": aggregate.failed_trial_count if aggregate else 0,
        "mean_pair_quality_score": aggregate.mean_pair_quality_score if aggregate else None,
        "std_pair_quality_score": aggregate.std_pair_quality_score if aggregate else None,
        "mean_execution_success_rate": aggregate.mean_execution_success_rate if aggregate else None,
        "total_errors": aggregate.total_errors if aggregate else 0,
        "common_failure_modes": aggregate.common_failure_modes if aggregate else {},
        "prototype_pair_rank_score": result.prototype_pair_rank_score,
        "error_message": result.error_message,
    }


def _write_index_csv(results: list[PairMatrixRunResult], path: Path) -> None:
    fieldnames = [
        "pair",
        "pair_id",
        "status",
        "source",
        "artifact_path",
        "original_artifact_path",
        "completed_trials",
        "failed_trials",
        "mean_pair_quality_score",
        "std_pair_quality_score",
        "mean_execution_success_rate",
        "total_errors",
        "common_failure_modes",
        "prototype_pair_rank_score",
        "error_message",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for result in results:
            row = _index_row(result)
            row["common_failure_modes"] = json.dumps(row["common_failure_modes"], ensure_ascii=False, sort_keys=True)
            writer.writerow(row)


def _write_rankings_csv(rankings: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "rank",
        "pair",
        "pair_id",
        "status",
        "completed_trials",
        "failed_trials",
        "mean_pair_quality_score",
        "std_pair_quality_score",
        "mean_execution_success_rate",
        "mean_final_validation_success_rate",
        "total_errors",
        "common_failure_modes",
        "prototype_pair_rank_score",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rankings:
            payload = dict(row)
            payload["common_failure_modes"] = json.dumps(payload["common_failure_modes"], ensure_ascii=False, sort_keys=True)
            writer.writerow(payload)


def _comparison_markdown(result: PairMatrixComparisonResult) -> str:
    lines = [
        "# Orchestrator/Executor Pair Matrix Comparison v1",
        "",
        "## 1. Purpose",
        "",
        "This matrix supports the TZ goal by comparing local orchestrator/executor pair behavior for one controlled group-agent scenario. It helps select the current best observed pair for this scenario without making a final production recommendation.",
        "",
        "## 2. Evidence base",
        "",
        f"- scenario: `{result.scenario_path}`",
        f"- mode: `{result.mode}`",
        f"- trials per pair: `{result.trials_per_pair}`",
        "- models: `first_model` Qwen2.5 1.5B Instruct Q4_K_M, `second_model` Qwen2.5 3B Instruct Q4_K_M",
        "- local endpoints are loopback llama-server endpoints when server management is enabled",
        "- same scenario, action execution mode, repair policy, and pair quality metrics are used across pairs",
        "",
        "## 3. Pair summary table",
        "",
        "| pair | completed_trials | mean_pair_quality_score | std_pair_quality_score | mean_execution_success_rate | mean_final_validation_success_rate | total_errors | common_failure_modes | prototype_pair_rank_score |",
        "|---|---:|---:|---:|---:|---:|---:|---|---:|",
    ]
    for row in result.rankings:
        lines.append(
            f"| `{row['pair']}` | {row['completed_trials']} | {row['mean_pair_quality_score']} | "
            f"{row['std_pair_quality_score']} | {row['mean_execution_success_rate']} | "
            f"{row['mean_final_validation_success_rate']} | {row['total_errors']} | "
            f"`{row['common_failure_modes']}` | {row['prototype_pair_rank_score']} |"
        )
    lines.extend(
        [
            "",
            "## 4. Pair ranking",
            "",
            "The ranking uses `prototype_pair_rank_score`, a local prototype-only score: pair quality, execution success, final validation, plan validity, stability, and a lightweight latency component. It is not a final production score.",
            "",
        ]
    )
    for row in result.rankings:
        lines.append(f"{row['rank']}. `{row['pair']}` - `{row['prototype_pair_rank_score']}`")
    lines.extend(
        [
            "",
            "## 5. Failure analysis",
            "",
            _failure_modes_markdown(result, include_title=False),
            "",
            "## 6. Resource/latency notes",
            "",
            _resource_summary_markdown(result, include_title=False),
            "",
            "## 7. Interpretation",
            "",
            result.interpretation.get("summary", ""),
            "",
        ]
    )
    for note in result.interpretation.get("pair_notes", []):
        lines.append(f"- {note}")
    lines.extend(
        [
            "",
            "## 8. Limitations",
            "",
        ]
    )
    for limitation in result.limitations:
        lines.append(f"- {limitation}")
    lines.extend(
        [
            "",
            "## 9. Next step",
            "",
            "Add a heavier multi-agent scenario, measure GPU/runtime separately, and only then update the final report with a broader recommendation.",
            "",
        ]
    )
    return "\n".join(lines)


def _failure_modes_markdown(result: PairMatrixComparisonResult, *, include_title: bool = True) -> str:
    lines: list[str] = []
    if include_title:
        lines.extend(["# Pair Failure Modes", ""])
    if not result.pair_failure_modes:
        lines.append("No pair failure modes were recorded.")
    for pair_id, modes in result.pair_failure_modes.items():
        lines.append(f"- `{pair_id}`: `{modes}`")
    return "\n".join(lines)


def _resource_summary_markdown(result: PairMatrixComparisonResult, *, include_title: bool = True) -> str:
    lines: list[str] = []
    if include_title:
        lines.extend(["# Pair Resource Summary", ""])
    for pair_id, payload in result.pair_resource_summary.items():
        lines.append(
            f"- `{pair_id}`: wall_ms=`{payload.get('mean_wall_time_ms')}`, "
            f"orchestrator_ms=`{payload.get('mean_orchestrator_latency_ms')}`, "
            f"executor_ms=`{payload.get('mean_executor_latency_ms')}`, "
            f"server_strategy=`{payload.get('server_strategy')}`"
        )
    if not result.pair_resource_summary:
        lines.append("No resource summary rows were recorded.")
    return "\n".join(lines)


def _readme_markdown(result: PairMatrixComparisonResult) -> str:
    return (
        "# Orchestrator/Executor Pair Matrix\n\n"
        f"- comparison_id: `{result.comparison_id}`\n"
        f"- scenario: `{result.scenario_path}`\n"
        f"- mode: `{result.mode}`\n"
        f"- trials_per_pair: `{result.trials_per_pair}`\n"
        f"- best_observed_pair: `{result.best_observed_pair}`\n\n"
        "See `pair_matrix_comparison.md`, `pair_matrix_comparison.json`, and `pair_rankings.csv`.\n"
    )


def _interpretation(pair_results: list[PairMatrixRunResult], best: str | None) -> dict[str, Any]:
    by_label = {result.spec.label: result for result in pair_results}
    notes: list[str] = []
    if best == "second_model->first_model":
        notes.append("second_model -> first_model remains the current best observed pair for this scenario.")
    if best == "second_model->second_model":
        notes.append("second_model -> second_model is strongest here, suggesting the stronger executor improved this scenario while likely increasing local resource cost.")
    first_first = by_label.get("first_model->first_model")
    second_first = by_label.get("second_model->first_model")
    if first_first and second_first and (first_first.prototype_pair_rank_score or 0) < (second_first.prototype_pair_rank_score or 0):
        notes.append("first_model -> first_model trails the larger-orchestrator baseline, supporting use of a larger orchestrator for this scenario.")
    first_second = by_label.get("first_model->second_model")
    if first_second and first_second.aggregate and first_second.aggregate.completed_trial_count:
        notes.append("first_model -> second_model provides evidence about whether executor strength can compensate for a smaller orchestrator.")
    return {
        "best_observed_pair": best,
        "final_recommendation_ready": False,
        "summary": (
            f"The current best observed pair for this one scenario is `{best}`. "
            "This is directional prototype evidence only; final recommendation requires more scenarios and resource measurements."
            if best
            else "No successful pair produced enough evidence to identify a current best observed pair."
        ),
        "pair_notes": notes,
    }


def _resource_notes(aggregate: dict[str, Any], source: str, server_strategy: str | None) -> list[str]:
    notes = [f"source={source}"]
    if server_strategy:
        notes.append(server_strategy)
    wall_time = _number(aggregate.get("mean_wall_time_ms"))
    if wall_time is not None:
        notes.append(f"mean_wall_time_ms={wall_time}")
    return notes


def _model_upstream_names(models_config_path: str | Path, project_root: str | Path) -> dict[str, str | None]:
    path = Path(models_config_path)
    if not path.is_absolute():
        path = Path(project_root) / path
    config = load_evaluation_models_config(path)
    registry = EvaluationModelRegistry(config)
    return {model_id: registry.require(model_id).upstream_model_name for model_id in registry.model_ids()}


def _stability_component(value: float | None) -> float:
    if value is None:
        return 0.0
    return round(max(0.0, min(1.0, 1.0 - min(abs(value), 1.0))), 6)


def _latency_component(value: float | None) -> float:
    if value is None:
        return 0.5
    return round(max(0.0, min(1.0, 1.0 - (value / 10000.0))), 6)


def _clamp01(value: float | None) -> float:
    if value is None or math.isnan(value):
        return 0.0
    return max(0.0, min(1.0, value))


def _norm_path(value: str) -> str:
    return value.replace("\\", "/").strip("/")


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


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
