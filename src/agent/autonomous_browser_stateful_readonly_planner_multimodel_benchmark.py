from __future__ import annotations

import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_stateful_readonly_planner_packet import (
    DEFAULT_MAX_TOKENS,
    DEFAULT_PROMPT_FILENAME,
    DEFAULT_PROMPT_PREFIXES,
    DEFAULT_RAW_OUTPUT_FILENAME,
    DEFAULT_REQUEST_FILENAME,
    DEFAULT_RESPONSE_FILENAME,
    DEFAULT_TEMPERATURE,
    _build_expected_output_schema_doc,
    _build_request_payload,
    _load_config as _load_base_packet_config,
)
from .autonomous_browser_stateful_readonly_planner_variance import (
    _evaluate_trial_record,
    _required_bool,
    _required_identifier_list,
    _required_int,
    _safe_identifier,
    _safe_ratio,
    _safe_relative_path,
    _write_json,
    _write_text,
)
from .autonomous_browser_stateful_readonly_workflow import (
    DEFAULT_STATEFUL_READONLY_SCENARIO_IDS,
    FROZEN_RAW_STATEFUL_READONLY_SCENARIO_IDS,
    build_default_stateful_readonly_workflow_scenarios,
    build_frozen_raw_stateful_readonly_workflow_scenarios,
)
from .evaluation_models import EvaluationModelRegistry, load_evaluation_models_config


BUILD_CONFIG_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_multimodel_benchmark_config_v1"
PACKET_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_multimodel_benchmark_packet_v1"
PACKET_SUMMARY_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_multimodel_benchmark_packet_summary_v1"
EVALUATOR_SUMMARY_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator_summary_v1"

DEFAULT_PACKET_ID = "phase_14_stateful_readonly_planner_multimodel_benchmark"
DEFAULT_BASE_PACKET_CONFIG = "configs/autonomous_runtime/browser_stateful_readonly_planner_packet.example.json"
DEFAULT_EVALUATION_MODELS_CONFIG = "configs/evaluation_models.json"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_packets/stateful_readonly_planner_multimodel_benchmark"
DEFAULT_CAPTURED_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_outputs/stateful_readonly_planner_multimodel_benchmark"
DEFAULT_EVALUATOR_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_summaries/stateful_readonly_planner_multimodel_benchmark"
DEFAULT_PACKET_MANIFEST_FILENAME = "benchmark_packet.json"
DEFAULT_PACKET_SUMMARY_FILENAME = "benchmark_packet_summary.json"
DEFAULT_EVALUATOR_SUMMARY_FILENAME = "benchmark_evaluator_summary.json"
DEFAULT_REQUEST_RECORDS_FILENAME = "request_records.json"
DEFAULT_REQUEST_PATHS_FILENAME = "request_paths.json"
DEFAULT_OUTPUT_PATHS_FILENAME = "output_paths.json"
DEFAULT_COMMANDS_FILENAME = "commands.json"
DEFAULT_COMMANDS_MD_FILENAME = "commands.md"
DEFAULT_EXPECTED_OUTPUT_SCHEMA_FILENAME = "expected_output_schema.md"
DEFAULT_README_FILENAME = "README.md"
DEFAULT_TRIAL_COUNT = 3
DEFAULT_MODEL_ALIASES = ("second_model", "third_model")
DEFAULT_SCENARIO_CATALOG = "legacy_stateful_v1"
DEFAULT_PROMPT_CONTRACT_MODE = "historical_default"
ALLOWED_SCENARIO_CATALOGS = {
    "legacy_stateful_v1": DEFAULT_STATEFUL_READONLY_SCENARIO_IDS,
    "frozen_raw_v1": FROZEN_RAW_STATEFUL_READONLY_SCENARIO_IDS,
}
ALLOWED_PROMPT_CONTRACT_MODES = {"historical_default", "frozen_raw"}
DEFAULT_LIMITATIONS = (
    "optional post-completion multi-model benchmark only",
    "manual operator model runs only",
    "no model calls by Codex",
    "offline fixture-backed evaluation only",
    "no real browser execution",
    "no Playwright execution",
    "not production browser automation",
)


@dataclass(frozen=True)
class StatefulReadonlyPlannerMultimodelBenchmarkBuildConfig:
    schema_version: str
    packet_id: str
    base_packet_config: str
    evaluation_models_config: str
    scenario_catalog: str
    prompt_contract_mode: str
    model_aliases: tuple[str, ...]
    scenarios: tuple[str, ...]
    trials_per_scenario: int
    output_dir: str
    captured_output_dir: str
    evaluator_output_dir: str
    fixture_only: bool
    external_network_allowed: bool
    writes_allowed: bool
    model_execution: bool
    real_browser_execution: bool
    playwright_execution: bool
    browser_opened: bool
    limitations: tuple[str, ...] = DEFAULT_LIMITATIONS

    @classmethod
    def from_dict(
        cls,
        payload: Mapping[str, Any],
    ) -> "StatefulReadonlyPlannerMultimodelBenchmarkBuildConfig":
        schema_version = str(payload.get("schema_version", "")).strip()
        packet_id = _safe_identifier(payload.get("packet_id"), "packet_id")
        base_packet_config = _safe_relative_path(
            payload.get("base_packet_config", DEFAULT_BASE_PACKET_CONFIG),
            "base_packet_config",
        )
        evaluation_models_config = _safe_relative_path(
            payload.get("evaluation_models_config", DEFAULT_EVALUATION_MODELS_CONFIG),
            "evaluation_models_config",
        )
        scenario_catalog = str(payload.get("scenario_catalog", DEFAULT_SCENARIO_CATALOG)).strip()
        prompt_contract_mode = str(
            payload.get("prompt_contract_mode", DEFAULT_PROMPT_CONTRACT_MODE)
        ).strip()
        model_aliases = tuple(_required_identifier_list(payload.get("model_aliases"), "model_aliases"))
        scenarios = tuple(_required_identifier_list(payload.get("scenarios"), "scenarios"))
        trials_per_scenario = _required_int(
            payload.get("trials_per_scenario", DEFAULT_TRIAL_COUNT),
            "trials_per_scenario",
        )
        output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir")
        captured_output_dir = _safe_relative_path(
            payload.get("captured_output_dir", DEFAULT_CAPTURED_OUTPUT_DIR),
            "captured_output_dir",
        )
        evaluator_output_dir = _safe_relative_path(
            payload.get("evaluator_output_dir", DEFAULT_EVALUATOR_OUTPUT_DIR),
            "evaluator_output_dir",
        )
        fixture_only = _required_bool(payload.get("fixture_only", True), "fixture_only")
        external_network_allowed = _required_bool(
            payload.get("external_network_allowed", False),
            "external_network_allowed",
        )
        writes_allowed = _required_bool(payload.get("writes_allowed", False), "writes_allowed")
        model_execution = _required_bool(payload.get("model_execution", False), "model_execution")
        real_browser_execution = _required_bool(
            payload.get("real_browser_execution", False),
            "real_browser_execution",
        )
        playwright_execution = _required_bool(
            payload.get("playwright_execution", False),
            "playwright_execution",
        )
        browser_opened = _required_bool(payload.get("browser_opened", False), "browser_opened")
        limitations = tuple(
            str(item).strip()
            for item in payload.get("limitations", [])
            if isinstance(item, str) and item.strip()
        )

        if schema_version != BUILD_CONFIG_SCHEMA_VERSION:
            raise ValueError(
                "schema_version must match autonomous_browser_stateful_readonly_planner_multimodel_benchmark_config_v1."
            )
        if packet_id is None:
            raise ValueError("packet_id must be a safe identifier.")
        if base_packet_config is None or evaluation_models_config is None:
            raise ValueError(
                "base_packet_config and evaluation_models_config must be safe relative paths."
            )
        if scenario_catalog not in ALLOWED_SCENARIO_CATALOGS:
            raise ValueError("scenario_catalog must be a supported stateful read-only scenario catalog.")
        if prompt_contract_mode not in ALLOWED_PROMPT_CONTRACT_MODES:
            raise ValueError("prompt_contract_mode must be a supported frozen/historical prompt mode.")
        if not model_aliases:
            raise ValueError("model_aliases must not be empty.")
        if len(set(model_aliases)) != len(model_aliases):
            raise ValueError("model_aliases must be unique.")
        allowed_scenarios = ALLOWED_SCENARIO_CATALOGS[scenario_catalog]
        if not scenarios:
            raise ValueError("scenarios must not be empty.")
        if len(set(scenarios)) != len(scenarios):
            raise ValueError("scenarios must be unique.")
        if any(item not in allowed_scenarios for item in scenarios):
            raise ValueError("scenarios must belong to the configured stateful read-only scenario catalog.")
        if trials_per_scenario <= 0:
            raise ValueError("trials_per_scenario must be a positive integer.")
        if output_dir is None or captured_output_dir is None or evaluator_output_dir is None:
            raise ValueError(
                "output_dir, captured_output_dir, and evaluator_output_dir must be safe relative paths."
            )
        if not fixture_only:
            raise ValueError("fixture_only must be true.")
        if external_network_allowed:
            raise ValueError("external_network_allowed must be false.")
        if writes_allowed:
            raise ValueError("writes_allowed must be false.")
        if model_execution:
            raise ValueError("model_execution must be false.")
        if real_browser_execution:
            raise ValueError("real_browser_execution must be false.")
        if playwright_execution:
            raise ValueError("playwright_execution must be false.")
        if browser_opened:
            raise ValueError("browser_opened must be false.")

        return cls(
            schema_version=schema_version,
            packet_id=packet_id,
            base_packet_config=base_packet_config,
            evaluation_models_config=evaluation_models_config,
            scenario_catalog=scenario_catalog,
            prompt_contract_mode=prompt_contract_mode,
            model_aliases=model_aliases,
            scenarios=scenarios,
            trials_per_scenario=trials_per_scenario,
            output_dir=output_dir,
            captured_output_dir=captured_output_dir,
            evaluator_output_dir=evaluator_output_dir,
            fixture_only=fixture_only,
            external_network_allowed=external_network_allowed,
            writes_allowed=writes_allowed,
            model_execution=model_execution,
            real_browser_execution=real_browser_execution,
            playwright_execution=playwright_execution,
            browser_opened=browser_opened,
            limitations=limitations or DEFAULT_LIMITATIONS,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "packet_id": self.packet_id,
            "base_packet_config": self.base_packet_config,
            "evaluation_models_config": self.evaluation_models_config,
            "scenario_catalog": self.scenario_catalog,
            "prompt_contract_mode": self.prompt_contract_mode,
            "model_aliases": list(self.model_aliases),
            "scenarios": list(self.scenarios),
            "trials_per_scenario": self.trials_per_scenario,
            "output_dir": self.output_dir,
            "captured_output_dir": self.captured_output_dir,
            "evaluator_output_dir": self.evaluator_output_dir,
            "fixture_only": self.fixture_only,
            "external_network_allowed": self.external_network_allowed,
            "writes_allowed": self.writes_allowed,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class StatefulReadonlyPlannerMultimodelBenchmarkPacketSummary:
    schema_version: str
    status: str
    error_code: str | None
    packet_id: str | None
    scenario_catalog: str | None
    prompt_contract_mode: str | None
    models_total: int
    model_aliases: tuple[str, ...]
    scenarios_total: int
    trials_per_scenario: int
    requests_total: int
    fixture_only: bool
    no_runtime_execution: bool = True
    model_execution: bool = False
    real_browser_execution: bool = False
    playwright_execution: bool = False
    browser_opened: bool = False
    output_dir: str | None = None
    captured_output_dir: str | None = None
    evaluator_output_dir: str | None = None
    scenario_ids: tuple[str, ...] = ()
    trial_ids: tuple[str, ...] = ()
    request_records: tuple[dict[str, Any], ...] = ()
    packet_files: tuple[str, ...] = ()
    request_records_path: str | None = None
    request_paths_path: str | None = None
    output_paths_path: str | None = None
    expected_output_schema_path: str | None = None
    commands_count: int = 0
    limitations: tuple[str, ...] = DEFAULT_LIMITATIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "packet_id": self.packet_id,
            "scenario_catalog": self.scenario_catalog,
            "prompt_contract_mode": self.prompt_contract_mode,
            "models_total": self.models_total,
            "model_aliases": list(self.model_aliases),
            "scenarios_total": self.scenarios_total,
            "trials_per_scenario": self.trials_per_scenario,
            "requests_total": self.requests_total,
            "fixture_only": self.fixture_only,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "output_dir": self.output_dir,
            "captured_output_dir": self.captured_output_dir,
            "evaluator_output_dir": self.evaluator_output_dir,
            "scenario_ids": list(self.scenario_ids),
            "trial_ids": list(self.trial_ids),
            "request_records": [_jsonable(item) for item in self.request_records],
            "packet_files": list(self.packet_files),
            "request_records_path": self.request_records_path,
            "request_paths_path": self.request_paths_path,
            "output_paths_path": self.output_paths_path,
            "expected_output_schema_path": self.expected_output_schema_path,
            "commands_count": self.commands_count,
            "limitations": list(self.limitations),
        }


@dataclass(frozen=True)
class StatefulReadonlyPlannerMultimodelBenchmarkEvaluatorSummary:
    schema_version: str
    status: str
    error_code: str | None
    packet_id: str | None
    packet_output_dir: str | None
    output_dir: str | None
    scenario_catalog: str | None
    prompt_contract_mode: str | None
    models_total: int
    model_aliases: tuple[str, ...]
    scenarios_total: int
    scenario_ids: tuple[str, ...]
    trials_per_scenario: int
    outputs_total: int
    outputs_present: int
    outputs_missing: int
    outputs_ingested: int
    outputs_rejected: int
    validation_accepted: int
    validation_rejected: int
    workflows_succeeded: int
    workflows_failed: int
    pass_rate_overall: float
    validation_acceptance_rate: float
    best_model_by_pass_rate: str | None
    fully_successful_models: tuple[str, ...]
    missing_output_models: tuple[str, ...]
    model_summaries: tuple[dict[str, Any], ...] = ()
    output_summaries: tuple[dict[str, Any], ...] = ()
    finish_reason_counts: dict[str, int] = field(default_factory=dict)
    failure_class_counts: dict[str, int] = field(default_factory=dict)
    no_runtime_execution: bool = True
    model_execution: bool = False
    real_browser_execution: bool = False
    playwright_execution: bool = False
    browser_opened: bool = False
    real_network_traffic: bool = False
    fixture_only: bool = True
    limitations: tuple[str, ...] = DEFAULT_LIMITATIONS

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "packet_id": self.packet_id,
            "packet_output_dir": self.packet_output_dir,
            "output_dir": self.output_dir,
            "scenario_catalog": self.scenario_catalog,
            "prompt_contract_mode": self.prompt_contract_mode,
            "models_total": self.models_total,
            "model_aliases": list(self.model_aliases),
            "scenarios_total": self.scenarios_total,
            "scenario_ids": list(self.scenario_ids),
            "trials_per_scenario": self.trials_per_scenario,
            "outputs_total": self.outputs_total,
            "outputs_present": self.outputs_present,
            "outputs_missing": self.outputs_missing,
            "outputs_ingested": self.outputs_ingested,
            "outputs_rejected": self.outputs_rejected,
            "validation_accepted": self.validation_accepted,
            "validation_rejected": self.validation_rejected,
            "workflows_succeeded": self.workflows_succeeded,
            "workflows_failed": self.workflows_failed,
            "pass_rate_overall": self.pass_rate_overall,
            "validation_acceptance_rate": self.validation_acceptance_rate,
            "best_model_by_pass_rate": self.best_model_by_pass_rate,
            "fully_successful_models": list(self.fully_successful_models),
            "missing_output_models": list(self.missing_output_models),
            "model_summaries": [_jsonable(item) for item in self.model_summaries],
            "output_summaries": [_jsonable(item) for item in self.output_summaries],
            "finish_reason_counts": dict(self.finish_reason_counts),
            "failure_class_counts": dict(self.failure_class_counts),
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "real_network_traffic": self.real_network_traffic,
            "fixture_only": self.fixture_only,
            "limitations": list(self.limitations),
        }


def _scenario_definitions_for_catalog(
    scenario_catalog: str,
) -> dict[str, Any]:
    if scenario_catalog == "legacy_stateful_v1":
        return build_default_stateful_readonly_workflow_scenarios()
    if scenario_catalog == "frozen_raw_v1":
        return build_frozen_raw_stateful_readonly_workflow_scenarios()
    raise ValueError("unsupported scenario catalog")


def _trial_labels_for_count(count: int) -> tuple[str, ...]:
    return tuple(f"trial_{index:02d}" for index in range(1, count + 1))


def build_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_packet(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    config_result = _load_build_config(config_artifact)
    if config_result["status"] != "ok":
        return _packet_failure_summary(
            packet_id=config_result.get("packet_id"),
            output_dir=config_result.get("output_dir"),
            captured_output_dir=config_result.get("captured_output_dir"),
            evaluator_output_dir=config_result.get("evaluator_output_dir"),
            error_code=str(config_result.get("error_code") or "config_validation_failed"),
            limitations=tuple(config_result.get("limitations") or DEFAULT_LIMITATIONS),
        )

    build_config = StatefulReadonlyPlannerMultimodelBenchmarkBuildConfig.from_dict(config_result["config"])
    base_config_path = repo / build_config.base_packet_config
    base_packet = _load_base_packet_config(base_config_path)
    if base_packet["status"] != "ok":
        return _packet_failure_summary(
            packet_id=build_config.packet_id,
            output_dir=build_config.output_dir,
            captured_output_dir=build_config.captured_output_dir,
            evaluator_output_dir=build_config.evaluator_output_dir,
            error_code=str(base_packet.get("error_code") or "config_validation_failed"),
            limitations=build_config.limitations,
        )

    base_config = base_packet["config"]
    prompt_filename = str(base_config.get("prompt_filename", DEFAULT_PROMPT_FILENAME))
    max_tokens = int(base_config.get("max_tokens", DEFAULT_MAX_TOKENS))
    temperature = float(base_config.get("temperature", DEFAULT_TEMPERATURE))

    try:
        registry = EvaluationModelRegistry(
            load_evaluation_models_config(repo / build_config.evaluation_models_config)
        )
    except (OSError, ValueError) as exc:
        return _packet_failure_summary(
            packet_id=build_config.packet_id,
            output_dir=build_config.output_dir,
            captured_output_dir=build_config.captured_output_dir,
            evaluator_output_dir=build_config.evaluator_output_dir,
            error_code="config_validation_failed",
            limitations=build_config.limitations,
            diagnostics={"error_message": str(exc)},
        )

    scenarios = _scenario_definitions_for_catalog(build_config.scenario_catalog)
    packet_dir = repo / build_config.output_dir
    captured_output_root = repo / build_config.captured_output_dir
    evaluator_output_root = repo / build_config.evaluator_output_dir
    packet_dir.mkdir(parents=True, exist_ok=True)
    captured_output_root.mkdir(parents=True, exist_ok=True)
    evaluator_output_root.mkdir(parents=True, exist_ok=True)

    request_paths: dict[str, dict[str, dict[str, str]]] = {}
    output_paths: dict[str, dict[str, dict[str, str]]] = {}
    request_records: list[dict[str, Any]] = []
    packet_files: list[str] = []
    scenario_ids = list(build_config.scenarios)
    trial_ids = list(_trial_labels_for_count(build_config.trials_per_scenario))

    expected_output_schema_rel = f"{build_config.output_dir}/{DEFAULT_EXPECTED_OUTPUT_SCHEMA_FILENAME}"
    _write_text(packet_dir / DEFAULT_EXPECTED_OUTPUT_SCHEMA_FILENAME, _build_expected_output_schema_doc())
    packet_files.append(expected_output_schema_rel)

    prompt_paths: dict[str, str] = {}
    for scenario_id in scenario_ids:
        scenario = scenarios[scenario_id]
        prompt_dir = packet_dir / "prompts" / scenario_id
        prompt_dir.mkdir(parents=True, exist_ok=True)
        prompt_path = prompt_dir / prompt_filename
        prompt_text = _build_prompt_text_for_scenario(
            scenario_id,
            scenario=scenario,
            model_neutral_prompt=(build_config.prompt_contract_mode == "frozen_raw"),
        )
        _write_text(prompt_path, prompt_text)
        prompt_rel = f"{build_config.output_dir}/prompts/{scenario_id}/{prompt_filename}"
        prompt_paths[scenario_id] = prompt_rel
        packet_files.append(prompt_rel)

    model_specs: list[dict[str, Any]] = []
    for requested_alias in build_config.model_aliases:
        try:
            model_spec = registry.require(requested_alias)
        except KeyError:
            return _packet_failure_summary(
                packet_id=build_config.packet_id,
                output_dir=build_config.output_dir,
                captured_output_dir=build_config.captured_output_dir,
                evaluator_output_dir=build_config.evaluator_output_dir,
                error_code="unknown_model_alias",
                limitations=build_config.limitations,
                diagnostics={"model_alias": requested_alias},
            )

        prompt_prefix = None
        if build_config.prompt_contract_mode == "historical_default":
            prompt_prefix = DEFAULT_PROMPT_PREFIXES.get(model_spec.model_id)
        model_specs.append(
            {
                "alias": requested_alias,
                "resolved_model_id": model_spec.model_id,
                "api_model": model_spec.api_model or model_spec.model_id,
                "model_path": model_spec.gguf_path,
                "base_url": model_spec.base_url.rstrip("/"),
                "prompt_prefix": prompt_prefix,
            }
        )

    for model_spec in model_specs:
        alias = str(model_spec["alias"])
        request_paths[alias] = {}
        output_paths[alias] = {}
        for scenario_id in scenario_ids:
            scenario = scenarios[scenario_id]
            request_paths[alias][scenario_id] = {}
            output_paths[alias][scenario_id] = {}
            for trial_index, trial_label in enumerate(trial_ids, start=1):
                trial_id = f"{scenario_id}__{trial_label}"
                trial_dir = packet_dir / alias / scenario_id / trial_label
                captured_trial_dir = captured_output_root / alias / scenario_id / trial_label
                trial_dir.mkdir(parents=True, exist_ok=True)
                captured_trial_dir.mkdir(parents=True, exist_ok=True)

                request_rel = f"{build_config.output_dir}/{alias}/{scenario_id}/{trial_label}/{DEFAULT_REQUEST_FILENAME}"
                response_rel = f"{build_config.captured_output_dir}/{alias}/{scenario_id}/{trial_label}/{DEFAULT_RESPONSE_FILENAME}"
                raw_output_rel = f"{build_config.captured_output_dir}/{alias}/{scenario_id}/{trial_label}/{DEFAULT_RAW_OUTPUT_FILENAME}"
                prompt_rel = prompt_paths[scenario_id]
                request_payload = _build_request_payload(
                    packet_id=build_config.packet_id,
                    model_alias=alias,
                    prompt_prefix=str(model_spec.get("prompt_prefix") or "") or None,
                    scenario=scenario,
                    trial_id=trial_id,
                    prompt_path=prompt_rel,
                    request_path=request_rel,
                    response_path=response_rel,
                    raw_output_path=raw_output_rel,
                    max_tokens=max_tokens,
                    temperature=temperature,
                    prompt_filename=prompt_filename,
                    model_neutral_prompt=(build_config.prompt_contract_mode == "frozen_raw"),
                )
                request_payload["model"] = str(model_spec["api_model"])
                request_payload["metadata"]["model_path_expected"] = str(model_spec["model_path"])
                request_payload["metadata"]["resolved_model_id"] = str(model_spec["resolved_model_id"])
                request_payload["metadata"]["requested_model_alias"] = alias
                request_payload["metadata"]["trial_label"] = trial_label
                request_payload["metadata"]["trial_index"] = trial_index
                request_payload["metadata"]["trials_per_scenario"] = build_config.trials_per_scenario
                _write_json(trial_dir / DEFAULT_REQUEST_FILENAME, request_payload)

                request_paths[alias][scenario_id][trial_label] = request_rel
                output_paths[alias][scenario_id][trial_label] = raw_output_rel
                request_records.append(
                    {
                        "model_alias": alias,
                        "resolved_model_id": model_spec["resolved_model_id"],
                        "api_model": model_spec["api_model"],
                        "model_path": model_spec["model_path"],
                        "prompt_prefix": model_spec.get("prompt_prefix"),
                        "scenario_id": scenario_id,
                        "trial_id": trial_id,
                        "trial_label": trial_label,
                        "trial_index": trial_index,
                        "workflow_id": scenario.workflow_id,
                        "request_path": request_rel,
                        "prompt_path": prompt_rel,
                        "response_path": response_rel,
                        "output_path": raw_output_rel,
                        "raw_output_path": raw_output_rel,
                        "max_tokens": max_tokens,
                    }
                )
                packet_files.extend([request_rel, response_rel, raw_output_rel])

    request_paths_path = packet_dir / DEFAULT_REQUEST_PATHS_FILENAME
    _write_json(request_paths_path, request_paths)
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_REQUEST_PATHS_FILENAME}")

    output_paths_path = packet_dir / DEFAULT_OUTPUT_PATHS_FILENAME
    _write_json(output_paths_path, output_paths)
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_OUTPUT_PATHS_FILENAME}")

    request_records_path = packet_dir / DEFAULT_REQUEST_RECORDS_FILENAME
    _write_json(request_records_path, request_records)
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_REQUEST_RECORDS_FILENAME}")

    commands = _build_commands(
        output_dir=build_config.output_dir,
        captured_output_dir=build_config.captured_output_dir,
        evaluator_output_dir=build_config.evaluator_output_dir,
        model_specs=model_specs,
        scenario_ids=scenario_ids,
        trial_ids=trial_ids,
        prompt_filename=prompt_filename,
        routine_config_path=(
            "configs/autonomous_runtime/browser_stateful_readonly_planner_frozen_raw_benchmark.example.json"
            if build_config.scenario_catalog == "frozen_raw_v1"
            else "configs/autonomous_runtime/browser_stateful_readonly_planner_multimodel_benchmark.example.json"
        ),
    )
    _write_json(packet_dir / DEFAULT_COMMANDS_FILENAME, {"commands": commands})
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_COMMANDS_FILENAME}")

    commands_md = _build_commands_markdown(
        output_dir=build_config.output_dir,
        captured_output_dir=build_config.captured_output_dir,
        evaluator_output_dir=build_config.evaluator_output_dir,
        model_specs=model_specs,
        scenario_ids=scenario_ids,
        trial_ids=trial_ids,
        prompt_filename=prompt_filename,
    )
    _write_text(packet_dir / DEFAULT_COMMANDS_MD_FILENAME, commands_md)
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_COMMANDS_MD_FILENAME}")

    readme_text = _build_readme(
        packet_id=build_config.packet_id,
        output_dir=build_config.output_dir,
        captured_output_dir=build_config.captured_output_dir,
        evaluator_output_dir=build_config.evaluator_output_dir,
        scenario_catalog=build_config.scenario_catalog,
        prompt_contract_mode=build_config.prompt_contract_mode,
        model_specs=model_specs,
        scenario_ids=scenario_ids,
        trial_ids=trial_ids,
    )
    _write_text(packet_dir / DEFAULT_README_FILENAME, readme_text)
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_README_FILENAME}")

    manifest = {
        "schema_version": PACKET_SCHEMA_VERSION,
        "packet_id": build_config.packet_id,
        "scenario_catalog": build_config.scenario_catalog,
        "prompt_contract_mode": build_config.prompt_contract_mode,
        "base_packet_config": build_config.base_packet_config,
        "evaluation_models_config": build_config.evaluation_models_config,
        "model_aliases": list(build_config.model_aliases),
        "model_specs": model_specs,
        "scenario_ids": scenario_ids,
        "trial_ids": trial_ids,
        "trials_per_scenario": build_config.trials_per_scenario,
        "request_records": request_records,
        "requests_total": len(request_records),
        "output_dir": build_config.output_dir,
        "captured_output_dir": build_config.captured_output_dir,
        "evaluator_output_dir": build_config.evaluator_output_dir,
        "request_records_path": f"{build_config.output_dir}/{DEFAULT_REQUEST_RECORDS_FILENAME}",
        "request_paths_path": f"{build_config.output_dir}/{DEFAULT_REQUEST_PATHS_FILENAME}",
        "output_paths_path": f"{build_config.output_dir}/{DEFAULT_OUTPUT_PATHS_FILENAME}",
        "expected_output_schema_path": expected_output_schema_rel,
        "no_runtime_execution": True,
        "model_execution": False,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
        "fixture_only": True,
        "limitations": list(build_config.limitations),
    }
    _write_json(packet_dir / DEFAULT_PACKET_MANIFEST_FILENAME, manifest)
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_PACKET_MANIFEST_FILENAME}")

    summary = StatefulReadonlyPlannerMultimodelBenchmarkPacketSummary(
        schema_version=PACKET_SUMMARY_SCHEMA_VERSION,
        status="succeeded",
        error_code=None,
        packet_id=build_config.packet_id,
        scenario_catalog=build_config.scenario_catalog,
        prompt_contract_mode=build_config.prompt_contract_mode,
        models_total=len(build_config.model_aliases),
        model_aliases=build_config.model_aliases,
        scenarios_total=len(scenario_ids),
        trials_per_scenario=build_config.trials_per_scenario,
        requests_total=len(request_records),
        fixture_only=True,
        output_dir=build_config.output_dir,
        captured_output_dir=build_config.captured_output_dir,
        evaluator_output_dir=build_config.evaluator_output_dir,
        scenario_ids=tuple(scenario_ids),
        trial_ids=tuple(trial_ids),
        request_records=tuple(request_records),
        packet_files=tuple(packet_files),
        request_records_path=f"{build_config.output_dir}/{DEFAULT_REQUEST_RECORDS_FILENAME}",
        request_paths_path=f"{build_config.output_dir}/{DEFAULT_REQUEST_PATHS_FILENAME}",
        output_paths_path=f"{build_config.output_dir}/{DEFAULT_OUTPUT_PATHS_FILENAME}",
        expected_output_schema_path=expected_output_schema_rel,
        commands_count=len(commands),
        limitations=build_config.limitations,
    ).to_dict()
    _write_json(packet_dir / DEFAULT_PACKET_SUMMARY_FILENAME, summary)
    packet_files.append(f"{build_config.output_dir}/{DEFAULT_PACKET_SUMMARY_FILENAME}")
    return summary


def run_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator(
    packet_dir: str | Path,
    *,
    repo_root: str | Path | None = None,
    output_dir: str | Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    packet_root = _resolve_repo_path(packet_dir, repo)
    manifest_result = _load_packet_manifest(packet_root, repo)
    if manifest_result["status"] != "ok":
        return _evaluator_failure_summary(
            packet_id=manifest_result.get("packet_id"),
            packet_output_dir=manifest_result.get("packet_output_dir"),
            output_dir=_safe_relative_path(output_dir or DEFAULT_EVALUATOR_OUTPUT_DIR, "output_dir"),
            error_code=str(manifest_result.get("error_code") or "config_validation_failed"),
            limitations=tuple(manifest_result.get("limitations") or DEFAULT_LIMITATIONS),
        )

    manifest = manifest_result["packet"]
    packet_id = str(manifest["packet_id"])
    packet_output_dir = str(manifest["output_dir"])
    captured_output_dir = str(manifest["captured_output_dir"])
    scenario_catalog = str(manifest.get("scenario_catalog") or DEFAULT_SCENARIO_CATALOG)
    prompt_contract_mode = str(
        manifest.get("prompt_contract_mode") or DEFAULT_PROMPT_CONTRACT_MODE
    )
    model_aliases = tuple(str(item) for item in manifest["model_aliases"])
    scenario_ids = tuple(str(item) for item in manifest["scenario_ids"])
    trial_ids = tuple(str(item) for item in manifest["trial_ids"])
    request_records = tuple(manifest["request_records"])
    model_specs = tuple(manifest.get("model_specs", []))
    limitations = tuple(manifest.get("limitations") or DEFAULT_LIMITATIONS)

    output_dir_value = _safe_relative_path(
        output_dir or manifest.get("evaluator_output_dir") or DEFAULT_EVALUATOR_OUTPUT_DIR,
        "output_dir",
    )
    if output_dir_value is None:
        return _evaluator_failure_summary(
            packet_id=packet_id,
            packet_output_dir=packet_output_dir,
            output_dir=None,
            error_code="config_validation_failed",
            limitations=limitations,
        )

    output_root = repo / output_dir_value
    output_root.mkdir(parents=True, exist_ok=True)

    scenario_defs = _scenario_definitions_for_catalog(scenario_catalog)
    model_path_map = {
        str(item["alias"]): str(item["model_path"])
        for item in model_specs
        if isinstance(item, Mapping) and "alias" in item and "model_path" in item
    }
    model_summary_map: dict[str, dict[str, Any]] = {
        alias: {
            "alias": alias,
            "model_path": model_path_map.get(alias),
            "outputs_total": 0,
            "outputs_present": 0,
            "outputs_missing": 0,
            "outputs_ingested": 0,
            "outputs_rejected": 0,
            "validation_accepted": 0,
            "validation_rejected": 0,
            "workflows_succeeded": 0,
            "workflows_failed": 0,
            "pass_rate_overall": 0.0,
            "validation_acceptance_rate": 0.0,
            "failure_class_counts": Counter(),
            "finish_reason_counts": Counter(),
        }
        for alias in model_aliases
    }

    output_summaries: list[dict[str, Any]] = []
    finish_reason_counts: Counter[str] = Counter()
    failure_class_counts: Counter[str] = Counter()
    outputs_present = 0
    outputs_missing = 0
    outputs_ingested = 0
    outputs_rejected = 0
    validation_accepted = 0
    validation_rejected = 0
    workflows_succeeded = 0
    workflows_failed = 0
    first_issue_code: str | None = None

    for record in request_records:
        scenario_id = str(record["scenario_id"])
        scenario = scenario_defs[scenario_id]
        trial_result = _evaluate_trial_record(
            repo_root=repo,
            packet_id=packet_id,
            packet_output_dir=packet_output_dir,
            record=record,
            scenario=scenario,
            execute_fixture=True,
        )
        output_summaries.append(trial_result)

        alias = str(trial_result["model_alias"])
        model_summary = model_summary_map[alias]
        model_summary["outputs_total"] += 1
        failure_class = str(trial_result.get("failure_class") or "unknown")
        failure_class_counts.update([failure_class])
        model_summary["failure_class_counts"].update([failure_class])
        finish_reason = trial_result.get("finish_reason")
        if finish_reason is not None:
            finish_reason_value = str(finish_reason)
            finish_reason_counts.update([finish_reason_value])
            model_summary["finish_reason_counts"].update([finish_reason_value])

        if trial_result["captured_output_present"]:
            outputs_present += 1
            model_summary["outputs_present"] += 1
            if trial_result["validation_status"] == "accepted":
                outputs_ingested += 1
                validation_accepted += 1
                model_summary["outputs_ingested"] += 1
                model_summary["validation_accepted"] += 1
                if trial_result["workflow_status"] == "succeeded":
                    workflows_succeeded += 1
                    model_summary["workflows_succeeded"] += 1
                else:
                    workflows_failed += 1
                    model_summary["workflows_failed"] += 1
                    if first_issue_code is None:
                        first_issue_code = str(trial_result.get("error_code") or "workflow_failed")
            else:
                outputs_rejected += 1
                validation_rejected += 1
                workflows_failed += 1
                model_summary["outputs_rejected"] += 1
                model_summary["validation_rejected"] += 1
                model_summary["workflows_failed"] += 1
                if first_issue_code is None:
                    first_issue_code = str(trial_result.get("error_code") or "validation_rejected")
        else:
            outputs_missing += 1
            workflows_failed += 1
            model_summary["outputs_missing"] += 1
            model_summary["workflows_failed"] += 1
            if first_issue_code is None:
                first_issue_code = str(trial_result.get("error_code") or "missing_captured_output_file")

    model_summaries: list[dict[str, Any]] = []
    fully_successful_models: list[str] = []
    missing_output_models: list[str] = []
    for alias in model_aliases:
        summary = model_summary_map[alias]
        summary["pass_rate_overall"] = _safe_ratio(summary["workflows_succeeded"], summary["outputs_total"])
        summary["validation_acceptance_rate"] = _safe_ratio(summary["validation_accepted"], summary["outputs_present"])
        summary["failure_class_counts"] = dict(sorted(summary["failure_class_counts"].items()))
        summary["finish_reason_counts"] = dict(sorted(summary["finish_reason_counts"].items()))
        if summary["outputs_missing"] > 0:
            missing_output_models.append(alias)
        if (
            summary["outputs_total"] > 0
            and summary["outputs_missing"] == 0
            and summary["validation_rejected"] == 0
            and summary["workflows_failed"] == 0
        ):
            fully_successful_models.append(alias)
        model_summaries.append(summary)

    best_model_alias = None
    if model_summaries:
        best_model_alias = sorted(
            model_summaries,
            key=lambda item: (
                -float(item["pass_rate_overall"]),
                -float(item["validation_acceptance_rate"]),
                str(item["alias"]),
            ),
        )[0]["alias"]

    if outputs_missing > 0:
        status = "completed_with_missing_outputs"
        error_code = "missing_captured_outputs"
    elif workflows_failed > 0 or validation_rejected > 0:
        status = "completed_with_failures"
        error_code = first_issue_code or "benchmark_output_failed"
    else:
        status = "succeeded"
        error_code = None

    payload = StatefulReadonlyPlannerMultimodelBenchmarkEvaluatorSummary(
        schema_version=EVALUATOR_SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        packet_id=packet_id,
        packet_output_dir=packet_output_dir,
        output_dir=output_dir_value,
        scenario_catalog=scenario_catalog,
        prompt_contract_mode=prompt_contract_mode,
        models_total=len(model_aliases),
        model_aliases=model_aliases,
        scenarios_total=len(scenario_ids),
        scenario_ids=scenario_ids,
        trials_per_scenario=len(trial_ids),
        outputs_total=len(request_records),
        outputs_present=outputs_present,
        outputs_missing=outputs_missing,
        outputs_ingested=outputs_ingested,
        outputs_rejected=outputs_rejected,
        validation_accepted=validation_accepted,
        validation_rejected=validation_rejected,
        workflows_succeeded=workflows_succeeded,
        workflows_failed=workflows_failed,
        pass_rate_overall=_safe_ratio(workflows_succeeded, len(request_records)),
        validation_acceptance_rate=_safe_ratio(validation_accepted, outputs_present),
        best_model_by_pass_rate=str(best_model_alias) if best_model_alias is not None else None,
        fully_successful_models=tuple(fully_successful_models),
        missing_output_models=tuple(missing_output_models),
        model_summaries=tuple(model_summaries),
        output_summaries=tuple(output_summaries),
        finish_reason_counts=dict(sorted(finish_reason_counts.items())),
        failure_class_counts=dict(sorted(failure_class_counts.items())),
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        real_network_traffic=False,
        fixture_only=True,
        limitations=limitations,
    ).to_dict()
    _write_json(output_root / DEFAULT_EVALUATOR_SUMMARY_FILENAME, payload)
    return payload


def _build_commands(
    *,
    output_dir: str,
    captured_output_dir: str,
    evaluator_output_dir: str,
    model_specs: list[dict[str, Any]],
    scenario_ids: list[str],
    trial_ids: list[str],
    prompt_filename: str,
    routine_config_path: str,
) -> list[dict[str, Any]]:
    commands: list[dict[str, Any]] = [
        {
            "id": "build_stateful_readonly_multimodel_benchmark_packet",
            "manual_only": False,
            "description": "Build the optional stateful read-only multi-model benchmark packet.",
            "command": (
                ".\\.venv\\Scripts\\python.exe scripts/build_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_packet.py "
                f"--config {_windows_path(routine_config_path)}"
            ),
        }
    ]
    for scenario_id in scenario_ids:
        prompt_path = _windows_path(f"{output_dir}/prompts/{scenario_id}/{prompt_filename}")
        commands.append(
            {
                "id": f"read_{scenario_id}_prompt",
                "manual_only": True,
                "description": f"Read the compact prompt for {scenario_id}.",
                "command": f'Get-Content "{prompt_path}" -Raw',
            }
        )
    for model_spec in model_specs:
        alias = str(model_spec["alias"])
        for scenario_id in scenario_ids:
            for trial_label in trial_ids:
                request_path = _windows_path(
                    f"{output_dir}/{alias}/{scenario_id}/{trial_label}/{DEFAULT_REQUEST_FILENAME}"
                )
                response_path = _windows_path(
                    f"{captured_output_dir}/{alias}/{scenario_id}/{trial_label}/{DEFAULT_RESPONSE_FILENAME}"
                )
                raw_output_path = _windows_path(
                    f"{captured_output_dir}/{alias}/{scenario_id}/{trial_label}/{DEFAULT_RAW_OUTPUT_FILENAME}"
                )
                commands.extend(
                    [
                        {
                            "id": f"{alias}_{scenario_id}_{trial_label}_curl_request",
                            "manual_only": True,
                            "description": (
                                f"Manual operator request for {alias} / {scenario_id} / {trial_label}."
                            ),
                            "command": (
                                "# Manual operator only. Codex must not launch models.\n"
                                "Do not use Invoke-RestMethod for planner generation.\n"
                                f"curl.exe --max-time 90 -sS -X POST {model_spec['base_url']}/chat/completions -H \"Content-Type: application/json\" --data-binary \"@{request_path}\" --output \"{response_path}\""
                            ),
                        },
                        {
                            "id": f"{alias}_{scenario_id}_{trial_label}_extract_output",
                            "manual_only": True,
                            "description": (
                                f"Extract response.choices[0].message.content for {alias} / {scenario_id} / {trial_label}."
                            ),
                            "command": (
                                f"$response = Get-Content \"{response_path}\" -Raw | ConvertFrom-Json\n"
                                f"$response.choices[0].message.content | Set-Content \"{raw_output_path}\" -Encoding utf8"
                            ),
                        },
                    ]
                )
    commands.append(
        {
            "id": "run_stateful_readonly_multimodel_benchmark_evaluator",
            "manual_only": False,
            "description": "Run the offline multi-model benchmark evaluator over captured outputs.",
            "command": rf".\.venv\Scripts\python.exe scripts\run_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator.py --packet-dir {output_dir}",
        }
    )
    commands.append(
        {
            "id": "run_pytest",
            "manual_only": False,
            "description": "Run the benchmark-related pytest coverage.",
            "command": r".\.venv\Scripts\python.exe -m pytest tests/test_autonomous_browser_stateful_readonly_planner_multimodel_benchmark.py tests/test_autonomous_browser_stateful_readonly_planner_variance.py",
        }
    )
    commands.append(
        {
            "id": "note_evaluator_output_dir",
            "manual_only": True,
            "description": "Evaluator summary target directory.",
            "command": _windows_path(evaluator_output_dir),
        }
    )
    return commands


def _build_commands_markdown(
    *,
    output_dir: str,
    captured_output_dir: str,
    evaluator_output_dir: str,
    model_specs: list[dict[str, Any]],
    scenario_ids: list[str],
    trial_ids: list[str],
    prompt_filename: str,
) -> str:
    lines = [
        "# Stateful Read-only Multi-model Benchmark Commands",
        "",
        "Codex must not launch models.",
        "Use `planner_prompt.compact.txt` as the prompt source for each trial.",
        "Generated packet/output artifacts are operator evidence only and must not be committed.",
        "",
        "## Models",
        "",
    ]
    for model_spec in model_specs:
        lines.append(
            f"- `{model_spec['alias']}` -> `{model_spec['model_path']}`"
        )
    lines.extend(
        [
            "",
            "## Prompt Read",
            "",
        ]
    )
    for scenario_id in scenario_ids:
        lines.append(
            f'- `Get-Content "{_windows_path(f"{output_dir}/prompts/{scenario_id}/{prompt_filename}")}" -Raw`'
        )
    lines.extend(
        [
            "",
            "## Manual Runs",
            "",
        ]
    )
    for model_spec in model_specs:
        alias = str(model_spec["alias"])
        for scenario_id in scenario_ids:
            for trial_label in trial_ids:
                request_path = _windows_path(
                    f"{output_dir}/{alias}/{scenario_id}/{trial_label}/{DEFAULT_REQUEST_FILENAME}"
                )
                response_path = _windows_path(
                    f"{captured_output_dir}/{alias}/{scenario_id}/{trial_label}/{DEFAULT_RESPONSE_FILENAME}"
                )
                raw_output_path = _windows_path(
                    f"{captured_output_dir}/{alias}/{scenario_id}/{trial_label}/{DEFAULT_RAW_OUTPUT_FILENAME}"
                )
                lines.extend(
                    [
                        f"- `{alias}` / `{scenario_id}` / `{trial_label}` request:",
                        (
                            f'  `curl.exe --max-time 90 -sS -X POST {model_spec["base_url"]}/chat/completions '
                            f'-H "Content-Type: application/json" --data-binary "@{request_path}" --output "{response_path}"`'
                        ),
                        f'  `$response = Get-Content "{response_path}" -Raw | ConvertFrom-Json`',
                        f'  `$response.choices[0].message.content | Set-Content "{raw_output_path}" -Encoding utf8`',
                    ]
                )
    lines.extend(
        [
            "",
            "## Evaluation",
            "",
            f"- evaluator summary target: `{_windows_path(evaluator_output_dir)}`",
            (
                "- `."
                "\\.venv\\Scripts\\python.exe scripts\\run_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator.py "
                f"--packet-dir {output_dir}`"
            ),
        ]
    )
    return "\n".join(lines).strip() + "\n"


def _build_readme(
    *,
    packet_id: str,
    output_dir: str,
    captured_output_dir: str,
    evaluator_output_dir: str,
    model_specs: list[dict[str, Any]],
    scenario_ids: list[str],
    trial_ids: list[str],
    scenario_catalog: str,
    prompt_contract_mode: str,
) -> str:
    model_lines = "\n".join(
        f"- `{item['alias']}` -> `{item['model_path']}`" for item in model_specs
    )
    scenario_lines = "\n".join(f"- `{scenario_id}`" for scenario_id in scenario_ids)
    return (
        f"# {packet_id}\n\n"
        "Optional post-completion multi-model benchmark packet for the controlled stateful "
        "read-only fixture scenarios.\n\n"
        "## Models\n\n"
        f"{model_lines}\n\n"
        "## Scenarios\n\n"
        f"{scenario_lines}\n\n"
        "## Trial Layout\n\n"
        f"- packet dir: `{output_dir}`\n"
        f"- captured outputs dir: `{captured_output_dir}`\n"
        f"- evaluator output dir: `{evaluator_output_dir}`\n"
        f"- scenario catalog: `{scenario_catalog}`\n"
        f"- prompt contract mode: `{prompt_contract_mode}`\n"
        f"- trials per scenario: `{len(trial_ids)}`\n\n"
        "This packet does not execute models, browser actions, Playwright, or external network traffic.\n"
    )


def _build_prompt_text_for_scenario(
    scenario_id: str,
    *,
    scenario: Any,
    model_neutral_prompt: bool,
) -> str:
    prompt_text = _build_request_payload(
        packet_id="preview_only",
        model_alias="preview_only",
        prompt_prefix=None,
        scenario=scenario,
        trial_id=f"{scenario_id}__preview",
        prompt_path="preview",
        request_path="preview",
        response_path="preview",
        raw_output_path="preview",
        max_tokens=DEFAULT_MAX_TOKENS,
        temperature=DEFAULT_TEMPERATURE,
        prompt_filename=DEFAULT_PROMPT_FILENAME,
        model_neutral_prompt=model_neutral_prompt,
    )["messages"][1]["content"]
    return prompt_text.rstrip() + "\n"


def _load_build_config(config_artifact: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    try:
        if isinstance(config_artifact, Mapping):
            payload = dict(config_artifact)
        else:
            payload = json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))
        if not isinstance(payload, Mapping):
            raise ValueError("config root must be a JSON object.")
        config = StatefulReadonlyPlannerMultimodelBenchmarkBuildConfig.from_dict(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": _safe_identifier(
                payload.get("packet_id"), "packet_id"  # type: ignore[name-defined]
            )
            if "payload" in locals() and isinstance(payload, Mapping)
            else None,
            "output_dir": _safe_relative_path(
                payload.get("output_dir"), "output_dir"  # type: ignore[name-defined]
            )
            if "payload" in locals() and isinstance(payload, Mapping)
            else None,
            "captured_output_dir": _safe_relative_path(
                payload.get("captured_output_dir"), "captured_output_dir"  # type: ignore[name-defined]
            )
            if "payload" in locals() and isinstance(payload, Mapping)
            else None,
            "evaluator_output_dir": _safe_relative_path(
                payload.get("evaluator_output_dir"), "evaluator_output_dir"  # type: ignore[name-defined]
            )
            if "payload" in locals() and isinstance(payload, Mapping)
            else None,
            "limitations": list(DEFAULT_LIMITATIONS),
            "error_message": str(exc),
        }
    return {"status": "ok", "config": config.to_dict() if hasattr(config, "to_dict") else payload}


def _load_packet_manifest(packet_root: Path, repo_root: Path) -> dict[str, Any]:
    manifest_path = packet_root / DEFAULT_PACKET_MANIFEST_FILENAME
    if not manifest_path.exists():
        return {
            "status": "failed",
            "error_code": "packet_manifest_missing",
            "packet_output_dir": _repo_relative_path(repo_root, packet_root),
            "limitations": list(DEFAULT_LIMITATIONS),
        }
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_output_dir": _repo_relative_path(repo_root, packet_root),
            "limitations": list(DEFAULT_LIMITATIONS),
            "error_message": str(exc),
        }
    if not isinstance(payload, Mapping):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_output_dir": _repo_relative_path(repo_root, packet_root),
            "limitations": list(DEFAULT_LIMITATIONS),
        }
    schema_version = str(payload.get("schema_version", "")).strip()
    if schema_version != PACKET_SCHEMA_VERSION:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_output_dir": _repo_relative_path(repo_root, packet_root),
            "limitations": list(DEFAULT_LIMITATIONS),
        }
    output_dir = _safe_relative_path(payload.get("output_dir"), "output_dir")
    captured_output_dir = _safe_relative_path(payload.get("captured_output_dir"), "captured_output_dir")
    evaluator_output_dir = _safe_relative_path(payload.get("evaluator_output_dir"), "evaluator_output_dir")
    if output_dir is None or captured_output_dir is None or evaluator_output_dir is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_output_dir": _repo_relative_path(repo_root, packet_root),
            "limitations": list(DEFAULT_LIMITATIONS),
        }
    packet = dict(payload)
    packet["output_dir"] = output_dir
    packet["captured_output_dir"] = captured_output_dir
    packet["evaluator_output_dir"] = evaluator_output_dir
    return {
        "status": "ok",
        "packet": packet,
        "packet_id": payload.get("packet_id"),
        "packet_output_dir": output_dir,
        "limitations": tuple(payload.get("limitations") or DEFAULT_LIMITATIONS),
    }


def _packet_failure_summary(
    *,
    packet_id: str | None,
    output_dir: str | None,
    captured_output_dir: str | None,
    evaluator_output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
    diagnostics: dict[str, Any] | None = None,
) -> dict[str, Any]:
    payload = StatefulReadonlyPlannerMultimodelBenchmarkPacketSummary(
        schema_version=PACKET_SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        packet_id=packet_id,
        scenario_catalog=None,
        prompt_contract_mode=None,
        models_total=0,
        model_aliases=(),
        scenarios_total=0,
        trials_per_scenario=0,
        requests_total=0,
        fixture_only=True,
        output_dir=output_dir,
        captured_output_dir=captured_output_dir,
        evaluator_output_dir=evaluator_output_dir,
        limitations=limitations,
    ).to_dict()
    if diagnostics:
        payload["diagnostics"] = _jsonable(diagnostics)
    return payload


def _evaluator_failure_summary(
    *,
    packet_id: str | None,
    packet_output_dir: str | None,
    output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    return StatefulReadonlyPlannerMultimodelBenchmarkEvaluatorSummary(
        schema_version=EVALUATOR_SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        packet_id=packet_id,
        packet_output_dir=packet_output_dir,
        output_dir=output_dir,
        scenario_catalog=None,
        prompt_contract_mode=None,
        models_total=0,
        model_aliases=(),
        scenarios_total=0,
        scenario_ids=(),
        trials_per_scenario=0,
        outputs_total=0,
        outputs_present=0,
        outputs_missing=0,
        outputs_ingested=0,
        outputs_rejected=0,
        validation_accepted=0,
        validation_rejected=0,
        workflows_succeeded=0,
        workflows_failed=0,
        pass_rate_overall=0.0,
        validation_acceptance_rate=0.0,
        best_model_by_pass_rate=None,
        fully_successful_models=(),
        missing_output_models=(),
        limitations=limitations,
    ).to_dict()


def _resolve_repo_path(value: str | Path, repo_root: Path) -> Path:
    path = Path(value)
    return path if path.is_absolute() else repo_root / path


def _repo_relative_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.name


def _windows_path(path_value: str) -> str:
    return path_value.replace("/", "\\")


def _jsonable(value: Any) -> Any:
    if isinstance(value, dict):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    return value
