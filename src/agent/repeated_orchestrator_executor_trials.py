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

from .orchestrator_executor_pipeline import (
    OrchestratorExecutorRunConfig,
    OrchestratorExecutorRunner,
)


TrialStatus = Literal["completed", "failed"]
SeriesStatus = Literal["complete", "partial"]


class RepeatedGroupTrialSpec(BaseModel):
    trial_id: str
    run_id: str
    artifact_path: str
    orchestrator_model_id: str
    executor_model_id: str

    @field_validator("trial_id", "run_id", "artifact_path", "orchestrator_model_id", "executor_model_id")
    @classmethod
    def validate_non_empty(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("RepeatedGroupTrialSpec fields must be non-empty.")
        return value


class RepeatedGroupTrialResult(BaseModel):
    spec: RepeatedGroupTrialSpec
    status: TrialStatus
    return_code: int | None = None
    error_message: str | None = None
    metrics: dict[str, Any] = Field(default_factory=dict)


class RepeatedGroupTrialAggregate(BaseModel):
    trial_count: int
    completed_trial_count: int
    failed_trial_count: int
    mean_pair_quality_score: float | None = None
    std_pair_quality_score: float | None = None
    min_pair_quality_score: float | None = None
    max_pair_quality_score: float | None = None
    mean_plan_valid_rate: float | None = None
    mean_executor_call_count: float | None = None
    mean_final_validation_success_rate: float | None = None
    mean_execution_success_rate: float | None = None
    total_safety_violations: int = 0
    total_errors: int = 0
    common_failure_modes: dict[str, int] = Field(default_factory=dict)
    common_actions: dict[str, int] = Field(default_factory=dict)
    common_action_parameters: dict[str, int] = Field(default_factory=dict)
    mean_wall_time_ms: float | None = None
    mean_orchestrator_latency_ms: float | None = None
    mean_executor_latency_ms: float | None = None


class RepeatedGroupTrialSeriesResult(BaseModel):
    label: str
    orchestrator_model_id: str
    executor_model_id: str
    trials: list[RepeatedGroupTrialResult] = Field(default_factory=list)
    aggregate: RepeatedGroupTrialAggregate | None = None


class RepeatedGroupPairComparisonResult(BaseModel):
    comparison_id: str
    generated_at: str
    status: SeriesStatus
    orchestrator_model_id: str
    executor_model_id: str
    trial_index: list[dict[str, Any]]
    aggregate: RepeatedGroupTrialAggregate
    failure_modes: dict[str, int]
    action_patterns: dict[str, Any]
    limitations: list[str]
    interpretation: dict[str, Any]


class RepeatedGroupRunConfig(BaseModel):
    project_root: Path = Path(".")
    mode: Literal["fake", "local"] = "fake"
    models_config_path: str = "configs/evaluation_models.json"
    scenario_path: str = "configs/multi_agent_scenarios/office_developer_group_basic.json"
    out_root: str
    label: str
    trials: int = 3
    orchestrator_model_id: str = "second_model"
    executor_model_id: str = "first_model"
    orchestrator_base_url: str | None = None
    executor_base_url: str | None = None
    orchestrator_model_name: str | None = None
    executor_model_name: str | None = None
    orchestrator_max_tokens: int | None = None
    orchestrator_temperature: float | None = None
    orchestrator_repair_attempts: int = 0
    max_group_steps: int | None = None
    max_steps_per_agent: int | None = None
    repair_attempts: int = 0
    execute_actions: bool = True
    continue_on_trial_failure: bool = False
    force: bool = False

    @field_validator("project_root")
    @classmethod
    def resolve_project_root(cls, value: Path) -> Path:
        return value.resolve()

    @field_validator("out_root", "label", "orchestrator_model_id", "executor_model_id")
    @classmethod
    def validate_non_empty_text(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("RepeatedGroupRunConfig text fields must be non-empty.")
        return value

    @field_validator("trials")
    @classmethod
    def validate_trials(cls, value: int) -> int:
        if value < 1:
            raise ValueError("trials must be >= 1.")
        return value

    @field_validator("orchestrator_repair_attempts", "repair_attempts")
    @classmethod
    def validate_repair_attempts(cls, value: int) -> int:
        if value < 0:
            raise ValueError("repair attempts must be >= 0.")
        return value

    def project_path(self, value: str | Path) -> Path:
        path = Path(value)
        if path.is_absolute():
            return path
        return self.project_root / path


def load_group_run_artifact(path: str | Path) -> dict[str, Any]:
    artifact_dir = Path(path)
    return {
        "artifact_dir": str(artifact_dir),
        "manifest": _read_json(artifact_dir / "manifest.json"),
        "pair_quality_metrics": _read_json(artifact_dir / "pair_quality_metrics.json"),
        "pair_evaluation": _read_json(artifact_dir / "pair_evaluation.json"),
        "resource_summary": _read_json(artifact_dir / "resource_summary.json"),
        "orchestrator_attempts": _read_jsonl(artifact_dir / "orchestrator_attempts.jsonl"),
        "per_agent_attempts": _read_jsonl(artifact_dir / "per_agent_attempts.jsonl"),
        "per_agent_actions": _read_jsonl(artifact_dir / "per_agent_actions.jsonl"),
        "errors": _read_jsonl(artifact_dir / "errors.jsonl"),
    }


def collect_group_trial_metrics(trial_path: str | Path) -> dict[str, Any]:
    artifact = load_group_run_artifact(trial_path)
    manifest = artifact["manifest"]
    quality = artifact["pair_quality_metrics"]
    quality_metadata = quality.get("metadata") or {}
    pair_eval = artifact["pair_evaluation"]
    resource = artifact["resource_summary"]
    orchestrator_attempts = artifact["orchestrator_attempts"]
    per_agent_attempts = artifact["per_agent_attempts"]
    errors = artifact["errors"]

    initial_orchestrator = orchestrator_attempts[0] if orchestrator_attempts else {}
    orchestrator_repair_attempts = [a for a in orchestrator_attempts if a.get("attempt_type") == "repair"]
    executor_latencies = [
        _number(attempt.get("latency_ms") or attempt.get("selection_latency_ms"))
        for attempt in per_agent_attempts
    ]
    executor_latencies = [value for value in executor_latencies if value is not None]

    actions = [str((attempt.get("parsed_action") or {}).get("action")) for attempt in per_agent_attempts if attempt.get("parsed_action")]
    action_counter = Counter(actions)
    parameter_counter: Counter[str] = Counter()
    for attempt in per_agent_attempts:
        parsed = attempt.get("parsed_action") or {}
        if not parsed:
            continue
        parameter_counter[
            json.dumps(
                {
                    "action": parsed.get("action"),
                    "parameters": parsed.get("parameters") or {},
                },
                ensure_ascii=False,
                sort_keys=True,
            )
        ] += 1

    failure_counter = Counter(_failure_modes(errors, per_agent_attempts))
    main_errors = _main_errors(errors, per_agent_attempts)
    repeated_action_count = sum(count - 1 for count in action_counter.values() if count > 1)
    dominant_action_parameters = [
        {"action_parameters": key, "count": count}
        for key, count in parameter_counter.most_common(5)
    ]

    executor_calls = len(per_agent_attempts)
    final_validation_success = _int(quality_metadata.get("final_validation_success_count"))
    execution_attempted_count = sum(1 for attempt in per_agent_attempts if attempt.get("execution_attempted") is True)
    execution_success_count = _int(quality_metadata.get("execution_success_count"))

    return {
        "trial_id": Path(trial_path).name,
        "run_id": manifest.get("run_id"),
        "artifact_path": str(Path(trial_path)),
        "status": manifest.get("status"),
        "success": manifest.get("success"),
        "plan_valid": quality.get("orchestrator_plan_valid"),
        "orchestrator_initial_parse_success": initial_orchestrator.get("parse_success"),
        "orchestrator_repair_attempt_count": len(orchestrator_repair_attempts),
        "executor_model_calls_attempted": executor_calls,
        "initial_validation_success_count": _int(quality_metadata.get("initial_validation_success_count")),
        "final_validation_success_count": final_validation_success,
        "repair_attempt_count": _int(quality_metadata.get("repair_attempt_count")),
        "execution_attempted_count": execution_attempted_count,
        "execution_success_count": execution_success_count,
        "safety_violation_count": _int(quality.get("safety_violation_count")),
        "error_count": len(errors),
        "pair_quality_score": _number(quality.get("pair_quality_score")),
        "pair_verdict": pair_eval.get("verdict"),
        "wall_time_ms": _number(resource.get("wall_time_ms")),
        "orchestrator_latency_ms": _mean(
            [_number(attempt.get("latency_ms")) for attempt in orchestrator_attempts if _number(attempt.get("latency_ms")) is not None]
        ),
        "executor_latency_mean_ms": _mean(executor_latencies),
        "repeated_action_count": repeated_action_count,
        "dominant_action_parameters": dominant_action_parameters,
        "main_errors": main_errors,
        "common_failure_modes": dict(failure_counter),
        "common_actions": dict(action_counter),
        "stopped_reason": manifest.get("stopped_reason"),
    }


def aggregate_group_trials(trial_paths: list[str | Path]) -> RepeatedGroupTrialAggregate:
    metrics = [collect_group_trial_metrics(path) for path in trial_paths]
    trials = [
        RepeatedGroupTrialResult(
            spec=RepeatedGroupTrialSpec(
                trial_id=str(item["trial_id"]),
                run_id=str(item.get("run_id") or item["trial_id"]),
                artifact_path=str(item["artifact_path"]),
                orchestrator_model_id="unknown",
                executor_model_id="unknown",
            ),
            status="failed" if item.get("status") == "failed" else "completed",
            metrics=item,
        )
        for item in metrics
    ]
    return _aggregate_trial_results(trials)


def run_repeated_group_trials(config: RepeatedGroupRunConfig) -> RepeatedGroupPairComparisonResult:
    out_root = prepare_output_root(config.project_path(config.out_root), force=config.force)
    trial_results: list[RepeatedGroupTrialResult] = []
    for trial_number in range(1, config.trials + 1):
        trial_id = f"trial_{trial_number:03d}"
        run_id = f"{config.label}_{trial_id}"
        artifact_path = out_root / "runs" / trial_id
        spec = RepeatedGroupTrialSpec(
            trial_id=trial_id,
            run_id=run_id,
            artifact_path=str(artifact_path),
            orchestrator_model_id=config.orchestrator_model_id,
            executor_model_id=config.executor_model_id,
        )
        try:
            result = OrchestratorExecutorRunner(_group_run_config(config, artifact_path, run_id)).run()
            metrics = collect_group_trial_metrics(artifact_path)
            status: TrialStatus = "failed" if result.status == "failed" else "completed"
            trial_result = RepeatedGroupTrialResult(
                spec=spec,
                status=status,
                return_code=0 if status == "completed" else 1,
                error_message=result.stopped_reason if status == "failed" else None,
                metrics=metrics,
            )
        except Exception as exc:
            artifact_path.mkdir(parents=True, exist_ok=True)
            _write_json(
                artifact_path / "trial_error.json",
                {
                    "trial_id": trial_id,
                    "run_id": run_id,
                    "error_type": exc.__class__.__name__,
                    "error_message": str(exc) or exc.__class__.__name__,
                },
            )
            (artifact_path / "README.md").write_text(
                f"# Failed Group Trial\n\nRun id: `{run_id}`\n\nError: `{str(exc) or exc.__class__.__name__}`\n",
                encoding="utf-8",
            )
            trial_result = RepeatedGroupTrialResult(
                spec=spec,
                status="failed",
                return_code=1,
                error_message=str(exc) or exc.__class__.__name__,
                metrics=_failed_trial_metrics(spec, exc),
            )
        trial_results.append(trial_result)
        if trial_result.status == "failed" and not config.continue_on_trial_failure:
            break

    series = RepeatedGroupTrialSeriesResult(
        label=config.label,
        orchestrator_model_id=config.orchestrator_model_id,
        executor_model_id=config.executor_model_id,
        trials=trial_results,
    )
    series.aggregate = _aggregate_trial_results(trial_results)
    comparison = _comparison_from_series(series)
    write_repeated_group_trials_report(comparison, out_root)
    write_replay_command(out_root, _replay_command(config))
    return comparison


def write_repeated_group_trials_report(result: RepeatedGroupPairComparisonResult, out_root: str | Path) -> Path:
    out_path = Path(out_root)
    out_path.mkdir(parents=True, exist_ok=True)
    _write_json(out_path / "trial_index.json", result.trial_index)
    _write_trial_index_csv(result.trial_index, out_path / "trial_index.csv")
    _write_json(out_path / "aggregate_group_metrics.json", result.aggregate.model_dump(mode="json"))
    _write_aggregate_csv(result.aggregate, out_path / "aggregate_group_metrics.csv")
    _write_json(out_path / "failure_modes.json", result.failure_modes)
    _write_json(out_path / "action_patterns.json", result.action_patterns)
    _write_json(out_path / "repeated_group_trials_result.json", result.model_dump(mode="json"))
    (out_path / "repeated_group_trials_report.md").write_text(_report_markdown(result), encoding="utf-8")
    (out_path / "README.md").write_text(_readme_markdown(result), encoding="utf-8")
    return out_path


def write_replay_command(out_root: str | Path, command: str) -> None:
    Path(out_root, "replay_commands.ps1").write_text(command.rstrip() + "\n", encoding="utf-8")


def prepare_output_root(out_root: str | Path, *, force: bool) -> Path:
    out_path = Path(out_root)
    if out_path.exists():
        if not force:
            raise FileExistsError(f"Repeated group trials output root already exists: {out_path}")
        shutil.rmtree(out_path)
    out_path.mkdir(parents=True, exist_ok=True)
    return out_path


def _group_run_config(config: RepeatedGroupRunConfig, artifact_path: Path, run_id: str) -> OrchestratorExecutorRunConfig:
    return OrchestratorExecutorRunConfig(
        project_root=config.project_root,
        mode=config.mode,
        models_config_path=config.models_config_path,
        scenario_path=config.scenario_path,
        out_dir=str(artifact_path),
        run_id=run_id,
        orchestrator_model_id=config.orchestrator_model_id,
        executor_model_id=config.executor_model_id,
        orchestrator_base_url=config.orchestrator_base_url,
        executor_base_url=config.executor_base_url,
        orchestrator_model_name=config.orchestrator_model_name,
        executor_model_name=config.executor_model_name,
        orchestrator_max_tokens=config.orchestrator_max_tokens,
        orchestrator_temperature=config.orchestrator_temperature,
        orchestrator_repair_attempts=config.orchestrator_repair_attempts,
        max_group_steps=config.max_group_steps,
        max_steps_per_agent=config.max_steps_per_agent,
        repair_attempts=config.repair_attempts,
        execute_actions=config.execute_actions,
        force=True,
    )


def _aggregate_trial_results(trials: list[RepeatedGroupTrialResult]) -> RepeatedGroupTrialAggregate:
    metric_rows = [trial.metrics for trial in trials]
    completed = [trial for trial in trials if trial.status == "completed"]
    pair_scores = [_number(row.get("pair_quality_score")) for row in metric_rows]
    pair_scores = [value for value in pair_scores if value is not None]
    failure_counter: Counter[str] = Counter()
    action_counter: Counter[str] = Counter()
    parameter_counter: Counter[str] = Counter()
    for row in metric_rows:
        failure_counter.update(row.get("common_failure_modes") or {})
        action_counter.update(row.get("common_actions") or {})
        for item in row.get("dominant_action_parameters") or []:
            parameter_counter[str(item.get("action_parameters"))] += int(item.get("count") or 0)

    return RepeatedGroupTrialAggregate(
        trial_count=len(trials),
        completed_trial_count=len(completed),
        failed_trial_count=sum(1 for trial in trials if trial.status == "failed"),
        mean_pair_quality_score=_summary_mean(pair_scores),
        std_pair_quality_score=_summary_std(pair_scores),
        min_pair_quality_score=min(pair_scores) if pair_scores else None,
        max_pair_quality_score=max(pair_scores) if pair_scores else None,
        mean_plan_valid_rate=_summary_mean([_bool_rate(row.get("plan_valid")) for row in metric_rows]),
        mean_executor_call_count=_summary_mean([_number(row.get("executor_model_calls_attempted")) for row in metric_rows]),
        mean_final_validation_success_rate=_summary_mean(
            [
                _rate(
                    _int(row.get("final_validation_success_count")),
                    max(1, _int(row.get("executor_model_calls_attempted"))),
                )
                for row in metric_rows
            ]
        ),
        mean_execution_success_rate=_summary_mean(
            [
                _rate(
                    _int(row.get("execution_success_count")),
                    max(1, _int(row.get("execution_attempted_count"))),
                )
                for row in metric_rows
            ]
        ),
        total_safety_violations=sum(_int(row.get("safety_violation_count")) for row in metric_rows),
        total_errors=sum(_int(row.get("error_count")) for row in metric_rows),
        common_failure_modes=dict(failure_counter.most_common(10)),
        common_actions=dict(action_counter.most_common(10)),
        common_action_parameters=dict(parameter_counter.most_common(10)),
        mean_wall_time_ms=_summary_mean([_number(row.get("wall_time_ms")) for row in metric_rows]),
        mean_orchestrator_latency_ms=_summary_mean([_number(row.get("orchestrator_latency_ms")) for row in metric_rows]),
        mean_executor_latency_ms=_summary_mean([_number(row.get("executor_latency_mean_ms")) for row in metric_rows]),
    )


def _comparison_from_series(series: RepeatedGroupTrialSeriesResult) -> RepeatedGroupPairComparisonResult:
    aggregate = series.aggregate or _aggregate_trial_results(series.trials)
    status: SeriesStatus = "partial" if aggregate.failed_trial_count else "complete"
    trial_index = [_trial_index_row(trial) for trial in series.trials]
    return RepeatedGroupPairComparisonResult(
        comparison_id=series.label,
        generated_at=datetime.now(timezone.utc).isoformat(),
        status=status,
        orchestrator_model_id=series.orchestrator_model_id,
        executor_model_id=series.executor_model_id,
        trial_index=trial_index,
        aggregate=aggregate,
        failure_modes=aggregate.common_failure_modes,
        action_patterns={
            "common_actions": aggregate.common_actions,
            "common_action_parameters": aggregate.common_action_parameters,
        },
        limitations=[
            "Only one orchestrator/executor pair is included.",
            "Only one scenario is repeated.",
            "N=3 is a robustness smoke, not a benchmark or final recommendation.",
            "The runner is sequential and does not measure concurrent capacity.",
            "No GPU runtime is configured or measured.",
        ],
        interpretation={
            "closes_group_pair_single_run_gap": aggregate.completed_trial_count > 1 and aggregate.failed_trial_count == 0,
            "recommendation_ready": False,
            "summary": (
                "Repeated local group trials strengthen evidence for this one pair/scenario, "
                "but do not establish production readiness, GPU throughput, concurrent capacity, or a final best pair."
            ),
        },
    )


def _trial_index_row(trial: RepeatedGroupTrialResult) -> dict[str, Any]:
    row = {
        "trial_id": trial.spec.trial_id,
        "run_id": trial.spec.run_id,
        "artifact_path": trial.spec.artifact_path,
        "status": trial.metrics.get("status") or trial.status,
        "trial_status": trial.status,
        "success": trial.metrics.get("success"),
        "plan_valid": trial.metrics.get("plan_valid"),
        "executor_calls": trial.metrics.get("executor_model_calls_attempted"),
        "final_validation_success_count": trial.metrics.get("final_validation_success_count"),
        "execution_success_count": trial.metrics.get("execution_success_count"),
        "pair_quality_score": trial.metrics.get("pair_quality_score"),
        "main_errors": "; ".join(trial.metrics.get("main_errors") or []),
        "return_code": trial.return_code,
        "error_message": trial.error_message,
    }
    row.update({key: value for key, value in trial.metrics.items() if key not in row})
    return row


def _failed_trial_metrics(spec: RepeatedGroupTrialSpec, exc: Exception) -> dict[str, Any]:
    return {
        "trial_id": spec.trial_id,
        "run_id": spec.run_id,
        "artifact_path": spec.artifact_path,
        "status": "failed",
        "success": False,
        "plan_valid": False,
        "orchestrator_initial_parse_success": None,
        "orchestrator_repair_attempt_count": 0,
        "executor_model_calls_attempted": 0,
        "initial_validation_success_count": 0,
        "final_validation_success_count": 0,
        "repair_attempt_count": 0,
        "execution_attempted_count": 0,
        "execution_success_count": 0,
        "safety_violation_count": 0,
        "error_count": 1,
        "pair_quality_score": None,
        "pair_verdict": "failed",
        "wall_time_ms": None,
        "orchestrator_latency_ms": None,
        "executor_latency_mean_ms": None,
        "repeated_action_count": 0,
        "dominant_action_parameters": [],
        "main_errors": [f"{exc.__class__.__name__}: {str(exc) or exc.__class__.__name__}"],
        "common_failure_modes": {exc.__class__.__name__: 1},
        "common_actions": {},
        "stopped_reason": str(exc) or exc.__class__.__name__,
    }


def _failure_modes(errors: list[dict[str, Any]], attempts: list[dict[str, Any]]) -> list[str]:
    modes: list[str] = []
    for error in errors:
        if error.get("error_type"):
            modes.append(str(error["error_type"]))
        for issue in error.get("validation_issues") or []:
            if issue.get("code"):
                modes.append(str(issue["code"]))
    for attempt in attempts:
        if attempt.get("error_type"):
            modes.append(str(attempt["error_type"]))
        for issue in attempt.get("validation_issues") or []:
            if issue.get("code"):
                modes.append(str(issue["code"]))
    return modes


def _main_errors(errors: list[dict[str, Any]], attempts: list[dict[str, Any]]) -> list[str]:
    messages: list[str] = []
    for error in errors:
        error_type = str(error.get("error_type") or "error")
        message = str(error.get("error_message") or "")
        messages.append(f"{error_type}: {message}".strip(": "))
    for attempt in attempts:
        if not attempt.get("error_type"):
            continue
        error_type = str(attempt.get("error_type"))
        message = str(attempt.get("error_message") or "")
        messages.append(f"{attempt.get('agent_id')} {error_type}: {message}".strip(": "))
    return list(dict.fromkeys(messages))


def _write_trial_index_csv(rows: list[dict[str, Any]], path: Path) -> None:
    fieldnames = [
        "trial_id",
        "run_id",
        "artifact_path",
        "status",
        "trial_status",
        "success",
        "plan_valid",
        "executor_calls",
        "final_validation_success_count",
        "execution_success_count",
        "pair_quality_score",
        "main_errors",
        "return_code",
        "error_message",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def _write_aggregate_csv(aggregate: RepeatedGroupTrialAggregate, path: Path) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=["metric", "value"])
        writer.writeheader()
        for key, value in aggregate.model_dump(mode="json").items():
            if isinstance(value, dict):
                writer.writerow({"metric": key, "value": json.dumps(value, ensure_ascii=False, sort_keys=True)})
            else:
                writer.writerow({"metric": key, "value": value})


def _report_markdown(result: RepeatedGroupPairComparisonResult) -> str:
    rows = result.trial_index
    aggregate = result.aggregate
    lines = [
        "# Repeated Local Orchestrator/Executor Group Trials v1",
        "",
        "## 1. Purpose",
        "",
        "This repeated run targets the TZ group-agent gap by checking whether one local orchestrator/executor pair can repeat the same short group scenario more than once.",
        "",
        "## 2. Model pair",
        "",
        f"- orchestrator: `{result.orchestrator_model_id}` / Qwen2.5 3B Instruct Q4_K_M",
        f"- executor: `{result.executor_model_id}` / Qwen2.5 1.5B Instruct Q4_K_M",
        "",
        "## 3. Scenario",
        "",
        "`office_developer_group_basic_v1`",
        "",
        "## 4. Protocol",
        "",
        "- N=3 unless the run was interrupted or blocked.",
        "- `max_group_steps=1`.",
        "- `max_steps_per_agent=1`.",
        "- Orchestrator and executor repair attempts are enabled according to the replay command.",
        "- `execute-actions=true`.",
        "- Local mode uses two loopback endpoints when server management is enabled.",
        "",
        "## 5. Trial summary table",
        "",
        "| trial_id | status | success | plan_valid | executor_calls | final_validation_success_count | execution_success_count | pair_quality_score | main_errors |",
        "|---|---|---|---|---:|---:|---:|---:|---|",
    ]
    for row in rows:
        lines.append(
            f"| `{row.get('trial_id')}` | `{row.get('status')}` | `{row.get('success')}` | "
            f"`{row.get('plan_valid')}` | {row.get('executor_calls')} | "
            f"{row.get('final_validation_success_count')} | {row.get('execution_success_count')} | "
            f"{row.get('pair_quality_score')} | {row.get('main_errors') or ''} |"
        )
    lines.extend(
        [
            "",
            "## 6. Aggregate metrics",
            "",
            f"- mean_pair_quality_score: `{aggregate.mean_pair_quality_score}`",
            f"- std_pair_quality_score: `{aggregate.std_pair_quality_score}`",
            f"- mean_final_validation_success_rate: `{aggregate.mean_final_validation_success_rate}`",
            f"- mean_execution_success_rate: `{aggregate.mean_execution_success_rate}`",
            f"- total_errors: `{aggregate.total_errors}`",
            f"- total_safety_violations: `{aggregate.total_safety_violations}`",
            "",
            "## 7. Failure modes",
            "",
            f"`{result.failure_modes}`",
            "",
            "## 8. Interpretation",
            "",
            "What this proves if trials succeed: the local group pair pipeline is repeatable for this one pair and one scenario.",
            "",
            "What it does not prove:",
            "",
            "- production readiness;",
            "- GPU throughput;",
            "- concurrent capacity;",
            "- final best pair.",
            "",
            "## 9. Next step",
            "",
            "If stable, compare more pairs or run a measured GPU/capacity smoke. If unstable, analyze failures and repeat the same protocol.",
            "",
        ]
    )
    return "\n".join(lines)


def _readme_markdown(result: RepeatedGroupPairComparisonResult) -> str:
    return (
        "# Repeated Local Orchestrator/Executor Group Trials\n\n"
        f"- label: `{result.comparison_id}`\n"
        f"- status: `{result.status}`\n"
        f"- orchestrator: `{result.orchestrator_model_id}`\n"
        f"- executor: `{result.executor_model_id}`\n"
        f"- trial_count: `{result.aggregate.trial_count}`\n\n"
        "See `repeated_group_trials_report.md`, `trial_index.json`, and `aggregate_group_metrics.json`.\n"
    )


def _replay_command(config: RepeatedGroupRunConfig) -> str:
    action_flag = "--execute-actions" if config.execute_actions else "--no-execute-actions"
    continue_flag = " --continue-on-trial-failure" if config.continue_on_trial_failure else ""
    optional = ""
    if config.orchestrator_base_url:
        optional += f"--orchestrator-base-url {config.orchestrator_base_url} "
    if config.executor_base_url:
        optional += f"--executor-base-url {config.executor_base_url} "
    if config.orchestrator_model_name:
        optional += f"--orchestrator-model-name {config.orchestrator_model_name} "
    if config.executor_model_name:
        optional += f"--executor-model-name {config.executor_model_name} "
    if config.orchestrator_max_tokens is not None:
        optional += f"--orchestrator-max-tokens {config.orchestrator_max_tokens} "
    return (
        "python scripts\\run_repeated_orchestrator_executor_trials.py "
        f"--mode {config.mode} "
        f"--models-config {config.models_config_path} "
        f"--scenario {config.scenario_path} "
        f"--out-root {config.out_root} "
        f"--label {config.label} "
        f"--trials {config.trials} "
        f"--orchestrator-model-id {config.orchestrator_model_id} "
        f"--executor-model-id {config.executor_model_id} "
        f"{optional}"
        f"--max-group-steps {config.max_group_steps or 1} "
        f"--max-steps-per-agent {config.max_steps_per_agent or 1} "
        f"--orchestrator-repair-attempts {config.orchestrator_repair_attempts} "
        f"--repair-attempts {config.repair_attempts} "
        f"{action_flag} "
        "--force"
        f"{continue_flag}"
    )


def _read_json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _read_jsonl(path: Path) -> list[dict[str, Any]]:
    if not path.exists():
        return []
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


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


def _bool_rate(value: Any) -> float | None:
    if value is None:
        return None
    return 1.0 if bool(value) else 0.0


def _rate(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 6)


def _mean(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return round(sum(clean) / len(clean), 6)


def _summary_mean(values: list[float | None]) -> float | None:
    return _mean(values)


def _summary_std(values: list[float]) -> float | None:
    if not values:
        return None
    mean = sum(values) / len(values)
    variance = sum((value - mean) ** 2 for value in values) / len(values)
    return round(math.sqrt(variance), 6)
