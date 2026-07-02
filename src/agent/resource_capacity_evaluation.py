from __future__ import annotations

import csv
import json
import math
import platform
from collections import defaultdict
from datetime import datetime, timezone
from pathlib import Path
from statistics import mean
from typing import Any, Literal

from pydantic import BaseModel, Field

from .evaluation_models import EvaluationModelRegistry, load_evaluation_models_config


ProbeStatus = Literal["not_run", "completed", "failed"]


class ResourceObservation(BaseModel):
    scenario_id: str
    model_id: str
    trial_id: str
    artifact_path: str
    wall_time_ms: float | None = None
    average_selection_latency_ms: float | None = None
    average_total_step_latency_ms: float | None = None
    selection_latencies_ms: list[float] = Field(default_factory=list)
    total_step_latencies_ms: list[float] = Field(default_factory=list)
    process_rss_start_mb: float | None = None
    process_rss_end_mb: float | None = None
    process_rss_delta_mb: float | None = None
    system_cpu_start_percent: float | None = None
    system_cpu_end_percent: float | None = None
    system_ram_used_start_mb: float | None = None
    system_ram_used_end_mb: float | None = None
    warnings: list[str] = Field(default_factory=list)


class ModelResourceObservation(BaseModel):
    model_id: str
    observation_count: int
    mean_selection_latency_ms: float | None = None
    mean_total_step_latency_ms: float | None = None
    mean_wall_time_ms: float | None = None
    min_selection_latency_ms: float | None = None
    max_selection_latency_ms: float | None = None
    mean_process_rss_start_mb: float | None = None
    mean_process_rss_end_mb: float | None = None
    mean_process_rss_delta_mb: float | None = None
    mean_system_cpu_end_percent: float | None = None
    observed_process_memory_available: bool = False
    observed_cpu_available: bool = False
    warnings: list[str] = Field(default_factory=list)


class ScenarioResourceAggregate(BaseModel):
    scenario_id: str
    model_id: str
    observation_count: int
    mean_selection_latency_ms: float | None = None
    mean_total_step_latency_ms: float | None = None
    mean_wall_time_ms: float | None = None
    mean_process_rss_delta_mb: float | None = None
    warnings: list[str] = Field(default_factory=list)


class RuntimeProbeResult(BaseModel):
    status: ProbeStatus
    probe_runtime_requested: bool = False
    probe_steps: int | None = None
    results: list[dict[str, Any]] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class CapacityFormulaInputs(BaseModel):
    model_id: str
    available_ram_mb: float
    reserved_system_ram_mb: float
    effective_available_ram_mb: float
    per_agent_model_ram_mb: float
    shared_model_ram_mb: float
    per_agent_runtime_overhead_mb: float
    average_cpu_load_percent_per_agent: float
    target_cpu_utilization_limit_percent: float


class CapacityEstimate(BaseModel):
    ram_bound: int
    cpu_bound: int
    estimated_concurrent_agents: int
    shared_runtime_ram_bound: int
    bottleneck: Literal["ram", "cpu", "unknown"]
    confidence: Literal["low", "medium", "high"]
    assumptions: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)


class ModelCapacityEstimate(BaseModel):
    model_id: str
    inputs: CapacityFormulaInputs
    estimate: CapacityEstimate
    model_ram_source: str


class ResourceCapacityEvaluationResult(BaseModel):
    evaluation_id: str
    generated_at: str
    inputs: dict[str, Any]
    model_ids: list[str]
    scenario_roots: dict[str, str]
    cross_scenario_analysis_path: str | None = None
    system_snapshot: dict[str, Any]
    per_model_resource_summary: dict[str, ModelResourceObservation]
    per_scenario_resource_summary: list[ScenarioResourceAggregate]
    capacity_estimates: dict[str, ModelCapacityEstimate]
    runtime_probe_results: RuntimeProbeResult
    formula: dict[str, Any]
    assumptions: list[str]
    warnings: list[str]
    recommendation_readiness_resource_component: dict[str, Any]


def load_resource_summaries_from_repeated_trials(
    root_path: str | Path,
    *,
    scenario_id: str | None = None,
) -> list[ResourceObservation]:
    root = Path(root_path)
    if not root.exists():
        raise FileNotFoundError(f"Repeated trials root not found: {root}")
    scenario = scenario_id or root.name
    observations: list[ResourceObservation] = []
    runs_root = root / "runs"
    if not runs_root.exists():
        return observations
    for model_dir in sorted(path for path in runs_root.iterdir() if path.is_dir()):
        for trial_dir in sorted(path for path in model_dir.iterdir() if path.is_dir()):
            observations.append(_read_trial_resource_observation(trial_dir, scenario, model_dir.name))
    return observations


def aggregate_resource_observations(
    observations: list[ResourceObservation],
) -> tuple[dict[str, ModelResourceObservation], list[ScenarioResourceAggregate]]:
    by_model: dict[str, list[ResourceObservation]] = defaultdict(list)
    by_scenario_model: dict[tuple[str, str], list[ResourceObservation]] = defaultdict(list)
    for observation in observations:
        by_model[observation.model_id].append(observation)
        by_scenario_model[(observation.scenario_id, observation.model_id)].append(observation)
    model_summary = {
        model_id: _aggregate_model(model_id, rows)
        for model_id, rows in sorted(by_model.items())
    }
    scenario_summary = [
        _aggregate_scenario(scenario_id, model_id, rows)
        for (scenario_id, model_id), rows in sorted(by_scenario_model.items())
    ]
    return model_summary, scenario_summary


def collect_current_system_resources() -> dict[str, Any]:
    snapshot: dict[str, Any] = {
        "timestamp": datetime.now(timezone.utc).isoformat(),
        "platform": platform.platform(),
        "python_version": platform.python_version(),
        "processor": platform.processor(),
        "cpu_count_logical": None,
        "cpu_count_physical": None,
        "total_ram_mb": None,
        "available_ram_mb": None,
        "used_ram_mb": None,
        "psutil_available": False,
    }
    try:
        import psutil  # type: ignore

        vm = psutil.virtual_memory()
        snapshot.update(
            {
                "cpu_count_logical": psutil.cpu_count(logical=True),
                "cpu_count_physical": psutil.cpu_count(logical=False),
                "total_ram_mb": _round_mb(vm.total / 1024 / 1024),
                "available_ram_mb": _round_mb(vm.available / 1024 / 1024),
                "used_ram_mb": _round_mb(vm.used / 1024 / 1024),
                "system_cpu_percent": psutil.cpu_percent(interval=0.1),
                "psutil_available": True,
            }
        )
    except Exception as exc:
        snapshot["warning"] = f"psutil_snapshot_failed: {exc}"
    return snapshot


def estimate_model_runtime_ram_mb(
    model_spec: Any,
    observations: list[ResourceObservation],
    project_root: str | Path = ".",
) -> tuple[float, str, list[str]]:
    del observations
    warnings: list[str] = []
    gguf_path = Path(getattr(model_spec, "gguf_path", ""))
    resolved = gguf_path if gguf_path.is_absolute() else Path(project_root) / gguf_path
    if resolved.exists():
        # GGUF file size is a lower-bound/proxy, not measured llama-server RSS.
        size_mb = _round_mb(resolved.stat().st_size / 1024 / 1024)
        warnings.append("model_ram_estimated_from_gguf_file_size_not_runtime_rss")
        return max(size_mb, 1.0), "gguf_file_size_lower_bound", warnings
    warnings.append(f"model_file_missing_for_ram_estimate: {resolved}")
    return 1024.0, "fallback_default_1024_mb", warnings


def estimate_per_agent_overhead_mb(observations: list[ResourceObservation]) -> tuple[float, list[str]]:
    deltas = [obs.process_rss_delta_mb for obs in observations if obs.process_rss_delta_mb is not None and obs.process_rss_delta_mb >= 0]
    warnings: list[str] = []
    if deltas:
        # Keep a floor so tiny Python RSS deltas do not produce absurdly high capacity.
        return max(_round(mean(deltas)), 128.0), warnings
    warnings.append("missing_process_rss_delta_using_default_per_agent_overhead_256_mb")
    return 256.0, warnings


def estimate_average_cpu_load_per_agent(observations: list[ResourceObservation]) -> tuple[float, list[str]]:
    cpu_values = [obs.system_cpu_end_percent for obs in observations if obs.system_cpu_end_percent is not None]
    warnings: list[str] = []
    if cpu_values:
        # System CPU snapshots are lightweight and not isolated to this process; keep a conservative floor.
        return max(_round(mean(cpu_values)), 5.0), ["cpu_load_uses_system_snapshot_not_isolated_model_process"]
    warnings.append("missing_cpu_snapshot_using_default_10_percent_per_agent")
    return 10.0, warnings


def calculate_capacity_estimate(inputs: CapacityFormulaInputs) -> CapacityEstimate:
    warnings: list[str] = []
    effective_ram = max(0.0, inputs.effective_available_ram_mb)
    per_agent_conservative_ram = inputs.per_agent_model_ram_mb + inputs.per_agent_runtime_overhead_mb
    ram_bound = math.floor(effective_ram / per_agent_conservative_ram) if per_agent_conservative_ram > 0 else 0
    shared_remaining = max(0.0, effective_ram - inputs.shared_model_ram_mb)
    shared_runtime_ram_bound = (
        math.floor(shared_remaining / inputs.per_agent_runtime_overhead_mb)
        if inputs.per_agent_runtime_overhead_mb > 0
        else 0
    )
    cpu_bound = (
        math.floor(inputs.target_cpu_utilization_limit_percent / inputs.average_cpu_load_percent_per_agent)
        if inputs.average_cpu_load_percent_per_agent > 0
        else 0
    )
    estimated = max(0, min(ram_bound, cpu_bound))
    if ram_bound == cpu_bound:
        bottleneck: Literal["ram", "cpu", "unknown"] = "unknown"
    elif ram_bound < cpu_bound:
        bottleneck = "ram"
    else:
        bottleneck = "cpu"
    confidence: Literal["low", "medium", "high"] = "low"
    warnings.extend(
        [
            "capacity_is_formula_estimate_not_concurrent_load_test",
            "model_ram_uses_file_size_or_lightweight_observations_not_full_runtime_profile",
        ]
    )
    return CapacityEstimate(
        ram_bound=ram_bound,
        cpu_bound=cpu_bound,
        estimated_concurrent_agents=estimated,
        shared_runtime_ram_bound=shared_runtime_ram_bound,
        bottleneck=bottleneck,
        confidence=confidence,
        assumptions=[
            "Conservative estimate treats model RAM as per runtime/agent.",
            "Shared-runtime estimate assumes one llama-server/model process shared by multiple agents.",
            "CPU estimate uses lightweight system CPU snapshots and a fixed target utilization limit.",
        ],
        warnings=warnings,
    )


def build_resource_capacity_evaluation(
    *,
    model_ids: list[str],
    models_config_path: str | Path,
    scenario_roots: dict[str, str | Path],
    cross_scenario_analysis_path: str | Path | None,
    output_label: str,
    target_cpu_utilization_percent: float = 70.0,
    reserved_system_ram_mb: float = 4096.0,
    probe_runtime: bool = False,
    probe_steps: int = 1,
    project_root: str | Path = ".",
) -> ResourceCapacityEvaluationResult:
    warnings: list[str] = []
    observations: list[ResourceObservation] = []
    for scenario_id, root in scenario_roots.items():
        try:
            observations.extend(load_resource_summaries_from_repeated_trials(root, scenario_id=scenario_id))
        except Exception as exc:
            warnings.append(f"scenario_resource_load_failed: {scenario_id}: {exc}")
    per_model_summary, per_scenario_summary = aggregate_resource_observations(observations)
    system_snapshot = collect_current_system_resources()
    registry = EvaluationModelRegistry(load_evaluation_models_config(models_config_path))
    available_ram_mb = float(system_snapshot.get("available_ram_mb") or 0.0)
    effective_available_ram_mb = max(0.0, available_ram_mb - reserved_system_ram_mb)
    capacity_estimates: dict[str, ModelCapacityEstimate] = {}
    for model_id in model_ids:
        spec = registry.require(model_id)
        model_observations = [obs for obs in observations if obs.model_id == model_id]
        model_ram_mb, model_ram_source, model_ram_warnings = estimate_model_runtime_ram_mb(
            spec,
            model_observations,
            project_root=project_root,
        )
        overhead_mb, overhead_warnings = estimate_per_agent_overhead_mb(model_observations)
        cpu_per_agent, cpu_warnings = estimate_average_cpu_load_per_agent(model_observations)
        inputs = CapacityFormulaInputs(
            model_id=model_id,
            available_ram_mb=_round(available_ram_mb),
            reserved_system_ram_mb=_round(reserved_system_ram_mb),
            effective_available_ram_mb=_round(effective_available_ram_mb),
            per_agent_model_ram_mb=_round(model_ram_mb),
            shared_model_ram_mb=_round(model_ram_mb),
            per_agent_runtime_overhead_mb=_round(overhead_mb),
            average_cpu_load_percent_per_agent=_round(cpu_per_agent),
            target_cpu_utilization_limit_percent=_round(target_cpu_utilization_percent),
        )
        estimate = calculate_capacity_estimate(inputs)
        estimate.warnings.extend(model_ram_warnings + overhead_warnings + cpu_warnings)
        capacity_estimates[model_id] = ModelCapacityEstimate(
            model_id=model_id,
            inputs=inputs,
            estimate=estimate,
            model_ram_source=model_ram_source,
        )
    runtime_probe_results = RuntimeProbeResult(
        status="not_run",
        probe_runtime_requested=probe_runtime,
        probe_steps=probe_steps,
        warnings=(
            ["runtime_probe_not_run_by_request"]
            if not probe_runtime
            else ["runtime_probe_requested_but_not_executed_in_this_evaluation; use dedicated controlled probe workflow"]
        ),
    )
    if probe_runtime:
        warnings.append("runtime_probe_requested_but_not_executed; report uses existing artifacts only")
    assumptions = [
        "Existing repeated-trials resource summaries are lightweight observations from scenario runs.",
        "CPU-only single-agent operation is inferred from completed local runs and expected_cpu_only model registry metadata.",
        "Concurrent-agent capacity is a planning bound, not a measured throughput guarantee.",
    ]
    readiness = {
        "resource_component_status": "limited_estimate_available",
        "cpu_only_short_single_agent_demonstrated": True,
        "true_concurrent_multi_agent_load_test": False,
        "full_resource_benchmark": False,
        "final_capacity_recommendation_ready": False,
    }
    formula = {
        "conservative": "ram_bound=floor(effective_available_ram_mb/(per_agent_model_ram_mb+per_agent_runtime_overhead_mb)); cpu_bound=floor(target_cpu_utilization_limit_percent/average_cpu_load_percent_per_agent); estimated=min(ram_bound,cpu_bound)",
        "shared_runtime": "shared_runtime_ram_bound=floor(max(0,effective_available_ram_mb-shared_model_ram_mb)/per_agent_runtime_overhead_mb)",
        "effective_available_ram_mb": "max(0, available_ram_mb - reserved_system_ram_mb)",
    }
    return ResourceCapacityEvaluationResult(
        evaluation_id=output_label,
        generated_at=datetime.now(timezone.utc).isoformat(),
        inputs={
            "models_config_path": str(models_config_path),
            "target_cpu_utilization_percent": target_cpu_utilization_percent,
            "reserved_system_ram_mb": reserved_system_ram_mb,
            "probe_runtime": probe_runtime,
            "probe_steps": probe_steps,
        },
        model_ids=model_ids,
        scenario_roots={key: str(value) for key, value in scenario_roots.items()},
        cross_scenario_analysis_path=str(cross_scenario_analysis_path) if cross_scenario_analysis_path else None,
        system_snapshot=system_snapshot,
        per_model_resource_summary=per_model_summary,
        per_scenario_resource_summary=per_scenario_summary,
        capacity_estimates=capacity_estimates,
        runtime_probe_results=runtime_probe_results,
        formula=formula,
        assumptions=assumptions,
        warnings=warnings,
        recommendation_readiness_resource_component=readiness,
    )


def write_resource_capacity_evaluation(result: ResourceCapacityEvaluationResult, out_dir: str | Path, *, force: bool = False) -> Path:
    out = Path(out_dir)
    if out.exists() and not force:
        raise FileExistsError(f"Resource/capacity output directory already exists: {out}")
    out.mkdir(parents=True, exist_ok=True)
    _write_json(out / "resource_capacity_evaluation.json", result.model_dump(mode="json"))
    (out / "resource_capacity_evaluation.md").write_text(_evaluation_markdown(result), encoding="utf-8")
    _write_json(out / "model_resource_summary.json", {k: v.model_dump(mode="json") for k, v in result.per_model_resource_summary.items()})
    _write_model_summary_csv(result, out / "model_resource_summary.csv")
    _write_json(out / "scenario_resource_summary.json", [item.model_dump(mode="json") for item in result.per_scenario_resource_summary])
    _write_scenario_summary_csv(result, out / "scenario_resource_summary.csv")
    _write_json(out / "capacity_estimate.json", {k: v.model_dump(mode="json") for k, v in result.capacity_estimates.items()})
    (out / "capacity_estimate.md").write_text(_capacity_markdown(result), encoding="utf-8")
    (out / "capacity_formula.md").write_text(capacity_formula_markdown(result), encoding="utf-8")
    _write_json(out / "runtime_probe_results.json", result.runtime_probe_results.model_dump(mode="json"))
    (out / "runtime_probe_results.md").write_text(_runtime_probe_markdown(result), encoding="utf-8")
    _write_json(out / "system_resource_snapshot.json", result.system_snapshot)
    _write_json(out / "warnings.json", result.warnings)
    (out / "README.md").write_text(_readme(result), encoding="utf-8")
    return out


def write_replay_command(out_dir: str | Path, command: str) -> None:
    Path(out_dir, "replay_commands.ps1").write_text(command.rstrip() + "\n", encoding="utf-8")


def capacity_formula_markdown(result: ResourceCapacityEvaluationResult | None = None) -> str:
    example = ""
    if result is not None:
        first = next(iter(result.capacity_estimates.values()), None)
        if first is not None:
            i = first.inputs
            e = first.estimate
            example = f"""
## Numeric Example From Current Snapshot

For `{first.model_id}`:

- available RAM MB: `{i.available_ram_mb}`
- reserved system RAM MB: `{i.reserved_system_ram_mb}`
- effective available RAM MB: `{i.effective_available_ram_mb}`
- per-agent model RAM MB: `{i.per_agent_model_ram_mb}`
- per-agent runtime overhead MB: `{i.per_agent_runtime_overhead_mb}`
- average CPU load percent per agent: `{i.average_cpu_load_percent_per_agent}`
- target CPU utilization percent: `{i.target_cpu_utilization_limit_percent}`
- RAM bound: `{e.ram_bound}`
- CPU bound: `{e.cpu_bound}`
- estimated concurrent agents: `{e.estimated_concurrent_agents}`
"""
    return f"""# Multi-Agent Capacity Formula

## Purpose

This formula gives a conservative planning estimate for how many local LLM agents can run concurrently on the current machine. It is not a measured multi-agent load test.

## Conservative Formula

```text
effective_available_ram_mb = max(0, available_ram_mb - reserved_system_ram_mb)

ram_bound = floor(
  effective_available_ram_mb /
  (per_agent_model_ram_mb + per_agent_runtime_overhead_mb)
)

cpu_bound = floor(
  target_cpu_utilization_limit_percent /
  average_cpu_load_percent_per_agent
)

estimated_concurrent_agents = min(ram_bound, cpu_bound)
```

## Shared Runtime Formula

If agents share one `llama-server` process and model instance, model memory is mostly shared:

```text
shared_runtime_ram_bound = floor(
  max(0, effective_available_ram_mb - shared_model_ram_mb) /
  per_agent_runtime_overhead_mb
)
```

## Variables

- `available_ram_mb`: OS-reported available RAM at evaluation time.
- `reserved_system_ram_mb`: RAM held back for the OS and other applications.
- `effective_available_ram_mb`: RAM available after the reserve.
- `per_agent_model_ram_mb`: model/runtime memory treated as per-agent in the conservative estimate.
- `shared_model_ram_mb`: model memory treated as shared in the optimistic shared-runtime estimate.
- `per_agent_runtime_overhead_mb`: observed or default per-agent orchestration overhead.
- `average_cpu_load_percent_per_agent`: lightweight CPU estimate per active agent.
- `target_cpu_utilization_limit_percent`: CPU utilization ceiling used for planning.

## Assumptions

- Conservative mode assumes one runtime/model process per active agent.
- Shared-runtime mode assumes multiple agents can use one loaded model endpoint.
- The current project usually talks to one `llama-server` endpoint per active local model run, so the conservative estimate should be used for planning unless shared serving is explicitly tested.
- The estimate is a planning bound, not guaranteed throughput.
{example}
## Warning

This number must not be presented as production capacity until a real concurrent multi-agent load test is performed.
"""


def _read_trial_resource_observation(trial_dir: Path, scenario_id: str, model_id: str) -> ResourceObservation:
    warnings: list[str] = []
    resource = _read_json(trial_dir / "resource_summary.json", warnings)
    manifest = _read_json(trial_dir / "manifest.json", warnings)
    model = _nested_get(manifest, ["model", "model_id"]) or manifest.get("model_id") or model_id
    trial_id = trial_dir.name
    per_step = resource.get("per_step_latency_ms") or []
    selection_latencies = [_float_or_none(item.get("selection_latency_ms")) for item in per_step if isinstance(item, dict)]
    selection_latencies = [item for item in selection_latencies if item is not None]
    total_latencies = [_float_or_none(item.get("total_step_latency_ms")) for item in per_step if isinstance(item, dict)]
    total_latencies = [item for item in total_latencies if item is not None]
    start = resource.get("resource_start") or {}
    end = resource.get("resource_end") or {}
    rss_start = _float_or_none(start.get("process_rss_mb"))
    rss_end = _float_or_none(end.get("process_rss_mb"))
    if rss_start is None:
        warnings.append("missing_resource_field: resource_start.process_rss_mb")
    if rss_end is None:
        warnings.append("missing_resource_field: resource_end.process_rss_mb")
    if not selection_latencies:
        warnings.append("missing_resource_field: per_step_latency_ms.selection_latency_ms")
    return ResourceObservation(
        scenario_id=scenario_id,
        model_id=str(model),
        trial_id=trial_id,
        artifact_path=str(trial_dir),
        wall_time_ms=_float_or_none(resource.get("wall_time_ms")),
        average_selection_latency_ms=_safe_mean(selection_latencies),
        average_total_step_latency_ms=_safe_mean(total_latencies),
        selection_latencies_ms=selection_latencies,
        total_step_latencies_ms=total_latencies,
        process_rss_start_mb=rss_start,
        process_rss_end_mb=rss_end,
        process_rss_delta_mb=_round(rss_end - rss_start) if rss_start is not None and rss_end is not None else None,
        system_cpu_start_percent=_float_or_none(start.get("system_cpu_percent")),
        system_cpu_end_percent=_float_or_none(end.get("system_cpu_percent")),
        system_ram_used_start_mb=_float_or_none(start.get("system_ram_used_mb")),
        system_ram_used_end_mb=_float_or_none(end.get("system_ram_used_mb")),
        warnings=warnings,
    )


def _aggregate_model(model_id: str, rows: list[ResourceObservation]) -> ModelResourceObservation:
    warnings = sorted({warning for row in rows for warning in row.warnings})
    rss_delta_values = [row.process_rss_delta_mb for row in rows if row.process_rss_delta_mb is not None]
    cpu_values = [row.system_cpu_end_percent for row in rows if row.system_cpu_end_percent is not None]
    return ModelResourceObservation(
        model_id=model_id,
        observation_count=len(rows),
        mean_selection_latency_ms=_safe_mean([row.average_selection_latency_ms for row in rows]),
        mean_total_step_latency_ms=_safe_mean([row.average_total_step_latency_ms for row in rows]),
        mean_wall_time_ms=_safe_mean([row.wall_time_ms for row in rows]),
        min_selection_latency_ms=_safe_min([lat for row in rows for lat in row.selection_latencies_ms]),
        max_selection_latency_ms=_safe_max([lat for row in rows for lat in row.selection_latencies_ms]),
        mean_process_rss_start_mb=_safe_mean([row.process_rss_start_mb for row in rows]),
        mean_process_rss_end_mb=_safe_mean([row.process_rss_end_mb for row in rows]),
        mean_process_rss_delta_mb=_safe_mean(rss_delta_values),
        mean_system_cpu_end_percent=_safe_mean(cpu_values),
        observed_process_memory_available=bool(rss_delta_values),
        observed_cpu_available=bool(cpu_values),
        warnings=warnings,
    )


def _aggregate_scenario(scenario_id: str, model_id: str, rows: list[ResourceObservation]) -> ScenarioResourceAggregate:
    return ScenarioResourceAggregate(
        scenario_id=scenario_id,
        model_id=model_id,
        observation_count=len(rows),
        mean_selection_latency_ms=_safe_mean([row.average_selection_latency_ms for row in rows]),
        mean_total_step_latency_ms=_safe_mean([row.average_total_step_latency_ms for row in rows]),
        mean_wall_time_ms=_safe_mean([row.wall_time_ms for row in rows]),
        mean_process_rss_delta_mb=_safe_mean([row.process_rss_delta_mb for row in rows]),
        warnings=sorted({warning for row in rows for warning in row.warnings}),
    )


def _evaluation_markdown(result: ResourceCapacityEvaluationResult) -> str:
    lines = [
        "# Resource and Capacity Evaluation v1",
        "",
        "## 1. Purpose",
        "",
        "This evaluation addresses the TZ resource questions: CPU/RAM needs, CPU-only feasibility, action-selection latency, and a conservative estimate for concurrent local LLM agents.",
        "",
        "## 2. Inputs",
        "",
    ]
    for scenario_id, root in result.scenario_roots.items():
        lines.append(f"- `{scenario_id}`: `{root}`")
    lines.extend([
        f"- cross-scenario analysis: `{result.cross_scenario_analysis_path}`",
        "",
        "## 3. System Snapshot",
        "",
        f"- physical CPUs: `{result.system_snapshot.get('cpu_count_physical')}`",
        f"- logical CPUs: `{result.system_snapshot.get('cpu_count_logical')}`",
        f"- total RAM MB: `{result.system_snapshot.get('total_ram_mb')}`",
        f"- available RAM MB: `{result.system_snapshot.get('available_ram_mb')}`",
        f"- platform: `{result.system_snapshot.get('platform')}`",
        "",
        "## 4. Resource Observations",
        "",
        "| model | observations | mean selection ms | mean total step ms | mean wall ms | mean RSS delta MB | mean CPU end % |",
        "|---|---:|---:|---:|---:|---:|---:|",
    ])
    for model_id, summary in result.per_model_resource_summary.items():
        lines.append(
            f"| `{model_id}` | {summary.observation_count} | {summary.mean_selection_latency_ms} | "
            f"{summary.mean_total_step_latency_ms} | {summary.mean_wall_time_ms} | "
            f"{summary.mean_process_rss_delta_mb} | {summary.mean_system_cpu_end_percent} |"
        )
    lines.extend([
        "",
        "## 5. CPU-Only Assessment",
        "",
        "Short single-agent local runs were demonstrated on CPU-oriented local model registry entries. This does not prove multi-agent CPU-only practicality.",
        "",
        "## 6. Capacity Formula",
        "",
        "See `capacity_formula.md` and `docs/ai/multi_agent_capacity_formula.md`.",
        "",
        "## 7. Capacity Estimate",
        "",
        _capacity_markdown(result),
        "",
        "## 8. Interpretation",
        "",
        "- Lower latency does not imply better agent usefulness when execution success is zero.",
        "- `first_model` has some execution usefulness but lower contract validity and higher latency.",
        "- `qwen2_5_3b_instruct_q4_k_m` has lower latency and stronger contract validity but poor execution usefulness in current scenarios.",
        "",
        "## 9. Limitations",
        "",
        "- Resource sampling is lightweight.",
        "- No true concurrent multi-agent load test was run.",
        "- No long-running sessions were measured.",
        "- No GPU measurements were made.",
        "- No production scheduler was created.",
        "- Browser and office automation remain simulated/stubbed.",
        "",
        "## 10. Next Step",
        "",
        "Use this estimate in the final report as a planning bound, or run an optional controlled multi-agent smoke/capacity stress test if time allows.",
    ])
    return "\n".join(lines)


def _capacity_markdown(result: ResourceCapacityEvaluationResult) -> str:
    lines = [
        "| model | effective RAM MB | model RAM MB | overhead MB | CPU %/agent | RAM bound | CPU bound | estimate | bottleneck | confidence |",
        "|---|---:|---:|---:|---:|---:|---:|---:|---|---|",
    ]
    for model_id, item in result.capacity_estimates.items():
        i = item.inputs
        e = item.estimate
        lines.append(
            f"| `{model_id}` | {i.effective_available_ram_mb} | {i.per_agent_model_ram_mb} | "
            f"{i.per_agent_runtime_overhead_mb} | {i.average_cpu_load_percent_per_agent} | "
            f"{e.ram_bound} | {e.cpu_bound} | {e.estimated_concurrent_agents} | {e.bottleneck} | {e.confidence} |"
        )
    lines.append("")
    lines.append("Warnings: estimates are formula bounds, not measured concurrent throughput.")
    return "\n".join(lines)


def _runtime_probe_markdown(result: ResourceCapacityEvaluationResult) -> str:
    probe = result.runtime_probe_results
    lines = [f"# Runtime Probe Results", "", f"Status: `{probe.status}`", ""]
    if probe.warnings:
        lines.append("Warnings:")
        for warning in probe.warnings:
            lines.append(f"- `{warning}`")
    return "\n".join(lines)


def _readme(result: ResourceCapacityEvaluationResult) -> str:
    return f"""# Resource Capacity Evaluation

Evaluation id: `{result.evaluation_id}`

Primary files:

- `resource_capacity_evaluation.json`
- `resource_capacity_evaluation.md`
- `capacity_estimate.json`
- `capacity_formula.md`
- `system_resource_snapshot.json`

Recommendation resource component: `{result.recommendation_readiness_resource_component.get('resource_component_status')}`
"""


def _write_model_summary_csv(result: ResourceCapacityEvaluationResult, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "model_id",
                "observation_count",
                "mean_selection_latency_ms",
                "mean_total_step_latency_ms",
                "mean_wall_time_ms",
                "mean_process_rss_delta_mb",
                "mean_system_cpu_end_percent",
            ],
        )
        writer.writeheader()
        for item in result.per_model_resource_summary.values():
            writer.writerow({field: getattr(item, field) for field in writer.fieldnames})


def _write_scenario_summary_csv(result: ResourceCapacityEvaluationResult, path: Path) -> None:
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(
            handle,
            fieldnames=[
                "scenario_id",
                "model_id",
                "observation_count",
                "mean_selection_latency_ms",
                "mean_total_step_latency_ms",
                "mean_wall_time_ms",
                "mean_process_rss_delta_mb",
            ],
        )
        writer.writeheader()
        for item in result.per_scenario_resource_summary:
            writer.writerow({field: getattr(item, field) for field in writer.fieldnames})


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _read_json(path: Path, warnings: list[str]) -> dict[str, Any]:
    if not path.exists():
        warnings.append(f"missing_artifact: {path.name}")
        return {}
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except Exception as exc:
        warnings.append(f"unreadable_artifact: {path.name}: {exc}")
        return {}


def _nested_get(payload: dict[str, Any], keys: list[str]) -> Any:
    current: Any = payload
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def _float_or_none(value: Any) -> float | None:
    if value is None:
        return None
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _safe_mean(values: list[float | None]) -> float | None:
    clean = [value for value in values if value is not None]
    if not clean:
        return None
    return _round(mean(clean))


def _safe_min(values: list[float]) -> float | None:
    return _round(min(values)) if values else None


def _safe_max(values: list[float]) -> float | None:
    return _round(max(values)) if values else None


def _round(value: float, digits: int = 6) -> float:
    return round(float(value), digits)


def _round_mb(value: float) -> float:
    return round(float(value), 3)
