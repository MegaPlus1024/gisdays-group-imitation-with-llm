from __future__ import annotations

import hashlib
import json
from collections import Counter
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_planner_output_ingestion import ingest_autonomous_browser_planner_output
from .autonomous_browser_plan_validation import validate_autonomous_browser_plan


CONFIG_SCHEMA_VERSION = "autonomous_browser_model_variance_evaluator_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_model_variance_evaluator_summary_v1"
DEFAULT_PACKET_ID = "browser_model_variance_packet_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_variance_packet/evaluation_runs"
INGESTION_SCHEMA_VERSION = "autonomous_browser_planner_output_ingestion_config_v1"
DEFAULT_MODEL_SPECS = (
    {"alias": "second_model", "model_path": "models/gguf/second_model.gguf"},
    {
        "alias": "third_model",
        "model_path": "models/gguf/third_model.gguf",
        "prompt_prefix": "/no_think",
    },
)
DEFAULT_SCENARIO_SPECS = (
    {
        "scenario_id": "hard_policy_disambiguation",
        "scenario_label": "hard_policy_disambiguation",
        "prompt_filename": "planner_prompt.compact.txt",
        "max_tokens": 1200,
    },
    {
        "scenario_id": "hard_ticket_priority_crosscheck",
        "scenario_label": "hard_ticket_priority_crosscheck",
        "prompt_filename": "planner_prompt.compact.txt",
        "max_tokens": 1200,
    },
    {
        "scenario_id": "hard_approval_policy_match",
        "scenario_label": "hard_approval_policy_match",
        "prompt_filename": "planner_prompt.compact.txt",
        "max_tokens": 1200,
    },
)
DEFAULT_TRIAL_IDS = tuple(f"trial_{index:02d}" for index in range(1, 4))


@dataclass(frozen=True)
class ModelVarianceEvaluatorSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    model_execution: bool
    real_browser_execution: bool
    playwright_execution: bool
    browser_opened: bool
    packet_id: str | None
    output_dir: str | None
    packet_output_dir: str | None
    models_total: int
    scenarios_total: int
    trial_count: int
    trials_total: int
    outputs_total: int
    outputs_present: int
    outputs_missing: int
    outputs_ingested: int
    outputs_rejected: int
    dry_runs_succeeded: int
    dry_runs_failed: int
    fixture_runs_succeeded: int
    fixture_runs_failed: int
    actions_attempted_total: int
    actions_succeeded_total: int
    actions_failed_total: int
    expected_results_total: int
    expected_results_passed_total: int
    expected_results_failed_total: int
    trial_results: tuple[dict[str, Any], ...] = ()
    model_summaries: tuple[dict[str, Any], ...] = ()
    scenario_model_summaries: tuple[dict[str, Any], ...] = ()
    scenario_summaries: tuple[dict[str, Any], ...] = ()
    limitations: tuple[str, ...] = ()
    fixture_execution_requested: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "packet_id": self.packet_id,
            "output_dir": self.output_dir,
            "packet_output_dir": self.packet_output_dir,
            "models_total": self.models_total,
            "scenarios_total": self.scenarios_total,
            "trial_count": self.trial_count,
            "trials_total": self.trials_total,
            "outputs_total": self.outputs_total,
            "outputs_present": self.outputs_present,
            "outputs_missing": self.outputs_missing,
            "outputs_ingested": self.outputs_ingested,
            "outputs_rejected": self.outputs_rejected,
            "dry_runs_succeeded": self.dry_runs_succeeded,
            "dry_runs_failed": self.dry_runs_failed,
            "fixture_runs_succeeded": self.fixture_runs_succeeded,
            "fixture_runs_failed": self.fixture_runs_failed,
            "actions_attempted_total": self.actions_attempted_total,
            "actions_succeeded_total": self.actions_succeeded_total,
            "actions_failed_total": self.actions_failed_total,
            "expected_results_total": self.expected_results_total,
            "expected_results_passed_total": self.expected_results_passed_total,
            "expected_results_failed_total": self.expected_results_failed_total,
            "trial_results": [_jsonable(item) for item in self.trial_results],
            "model_summaries": [_jsonable(item) for item in self.model_summaries],
            "scenario_model_summaries": [_jsonable(item) for item in self.scenario_model_summaries],
            "scenario_summaries": [_jsonable(item) for item in self.scenario_summaries],
            "limitations": list(self.limitations),
            "fixture_execution_requested": self.fixture_execution_requested,
        }


def run_autonomous_browser_model_variance_evaluator(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
    execute_fixture: bool = False,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    config_result = _load_config(config_artifact)
    if config_result["status"] != "ok":
        return _failure_summary(
            packet_id=config_result.get("packet_id"),
            output_dir=config_result.get("output_dir"),
            packet_output_dir=config_result.get("packet_output_dir"),
            error_code=str(config_result.get("error_code") or "config_validation_failed"),
            limitations=tuple(config_result.get("limitations") or _limitations()),
        )

    packet_id = str(config_result["packet_id"])
    output_dir = str(config_result["output_dir"])
    packet_output_dir = str(config_result["packet_output_dir"])
    model_specs = tuple(config_result["model_specs"])
    scenario_specs = tuple(config_result["scenario_specs"])
    trial_ids = tuple(config_result["trial_ids"])
    trial_records = tuple(config_result["trial_records"])
    limitations = tuple(config_result.get("limitations") or _limitations())

    trial_results: list[dict[str, Any]] = []
    model_summaries = {
        str(model_spec["alias"]): _empty_model_summary(
            str(model_spec["alias"]),
            str(model_spec["model_path"]),
            trial_ids,
        )
        for model_spec in model_specs
    }
    scenario_model_summaries = {
        (str(model_spec["alias"]), str(scenario_spec["scenario_id"])): _empty_scenario_summary(
            str(model_spec["alias"]),
            str(model_spec["model_path"]),
            str(scenario_spec["scenario_id"]),
            str(scenario_spec["scenario_label"]),
            trial_ids,
        )
        for model_spec in model_specs
        for scenario_spec in scenario_specs
    }

    outputs_present = 0
    outputs_missing = 0
    outputs_ingested = 0
    outputs_rejected = 0
    validation_accepted_total = 0
    validation_rejected_total = 0
    dry_runs_succeeded = 0
    dry_runs_failed = 0
    fixture_runs_succeeded = 0
    fixture_runs_failed = 0
    actions_attempted_total = 0
    actions_succeeded_total = 0
    actions_failed_total = 0
    expected_results_total = 0
    expected_results_passed_total = 0
    expected_results_failed_total = 0
    any_missing = False
    any_rejected = False
    first_issue_code: str | None = None

    for record in trial_records:
        result = _evaluate_trial(
            repo_root=repo,
            packet_id=packet_id,
            model_alias=str(record["model_alias"]),
            model_path=str(record["model_path"]),
            scenario_id=str(record["scenario_id"]),
            scenario_label=str(record["scenario_label"]),
            trial_id=str(record["trial_id"]),
            trial_index=_int(record.get("trial_index")),
            request_path=str(record["request_path"]),
            output_path=str(record["output_path"]),
            response_metadata_path=str(record["response_metadata_path"]),
            evaluation_output_dir=output_dir,
            execute_fixture=execute_fixture,
        )
        trial_results.append(result)

        alias = str(result["model_alias"])
        scenario_id = str(result["scenario_id"])
        model_summary = model_summaries[alias]
        scenario_summary = scenario_model_summaries[(alias, scenario_id)]
        model_summary["outputs_total"] += 1
        scenario_summary["outputs_total"] += 1

        if result["captured_output_present"]:
            outputs_present += 1
            model_summary["outputs_present"] += 1
            scenario_summary["outputs_present"] += 1
            if result["validation_status"] == "accepted":
                validation_accepted_total += 1
                model_summary["validation_accepted_total"] += 1
                scenario_summary["validation_accepted_total"] += 1
            else:
                validation_rejected_total += 1
                model_summary["validation_rejected_total"] += 1
                scenario_summary["validation_rejected_total"] += 1
        else:
            outputs_missing += 1
            any_missing = True
            model_summary["outputs_missing"] += 1
            scenario_summary["outputs_missing"] += 1

        if result["status"] == "succeeded":
            outputs_ingested += 1
            model_summary["outputs_ingested"] += 1
            scenario_summary["outputs_ingested"] += 1
        elif result["captured_output_present"] and result["status"] in {"rejected", "failed"}:
            outputs_rejected += 1
            any_rejected = True
            model_summary["outputs_rejected"] += 1
            scenario_summary["outputs_rejected"] += 1
            if first_issue_code is None:
                first_issue_code = str(result.get("error_code") or "variance_output_failed")

        if result["dry_run_status"] == "accepted":
            dry_runs_succeeded += 1
            model_summary["dry_runs_succeeded"] += 1
            scenario_summary["dry_runs_succeeded"] += 1
        else:
            dry_runs_failed += 1
            model_summary["dry_runs_failed"] += 1
            scenario_summary["dry_runs_failed"] += 1

        if result["fixture_execution_status"] == "succeeded":
            fixture_runs_succeeded += 1
            model_summary["fixture_runs_succeeded"] += 1
            scenario_summary["fixture_runs_succeeded"] += 1
        elif result["captured_output_present"] and execute_fixture:
            fixture_runs_failed += 1
            model_summary["fixture_runs_failed"] += 1
            scenario_summary["fixture_runs_failed"] += 1

        actions_attempted_total += _int(result.get("actions_attempted"))
        actions_succeeded_total += _int(result.get("actions_succeeded"))
        actions_failed_total += _int(result.get("actions_failed"))
        expected_results_total += _int(result.get("expected_results_total"))
        expected_results_passed_total += _int(result.get("expected_results_passed"))
        expected_results_failed_total += _int(result.get("expected_results_failed"))

        model_summary["actions_attempted_total"] += _int(result.get("actions_attempted"))
        model_summary["actions_succeeded_total"] += _int(result.get("actions_succeeded"))
        model_summary["actions_failed_total"] += _int(result.get("actions_failed"))
        model_summary["expected_results_total"] += _int(result.get("expected_results_total"))
        model_summary["expected_results_passed_total"] += _int(result.get("expected_results_passed"))
        model_summary["expected_results_failed_total"] += _int(result.get("expected_results_failed"))
        model_summary["completion_tokens"].append(result.get("completion_tokens"))
        model_summary["total_tokens"].append(result.get("total_tokens"))
        _increment_counter(model_summary["finish_reason_counts"], result.get("finish_reason"))
        _increment_counter(model_summary["error_code_counts"], result.get("error_code"))
        if result.get("plan_fingerprint"):
            model_summary["_plan_fingerprints"].add(str(result["plan_fingerprint"]))
            scenario_summary["_plan_fingerprints"].add(str(result["plan_fingerprint"]))

        scenario_summary["actions_attempted_total"] += _int(result.get("actions_attempted"))
        scenario_summary["actions_succeeded_total"] += _int(result.get("actions_succeeded"))
        scenario_summary["actions_failed_total"] += _int(result.get("actions_failed"))
        scenario_summary["expected_results_total"] += _int(result.get("expected_results_total"))
        scenario_summary["expected_results_passed_total"] += _int(result.get("expected_results_passed"))
        scenario_summary["expected_results_failed_total"] += _int(result.get("expected_results_failed"))
        _increment_counter(scenario_summary["finish_reason_counts"], result.get("finish_reason"))
        _increment_counter(scenario_summary["error_code_counts"], result.get("error_code"))

        model_summary["trial_results"].append(result)
        scenario_summary["trial_results"].append(result)

    if outputs_missing > 0:
        status = "completed_with_missing_outputs"
        error_code = "missing_captured_outputs"
    elif outputs_rejected > 0:
        status = "completed_with_failures"
        error_code = first_issue_code or "variance_outputs_rejected"
    else:
        status = "succeeded"
        error_code = None

    finalized_model_summaries = tuple(
        _finalize_model_summary(summary)
        for summary in model_summaries.values()
    )
    finalized_scenario_summaries = tuple(
        _finalize_scenario_summary(summary)
        for summary in scenario_model_summaries.values()
    )

    summary = ModelVarianceEvaluatorSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status=status,
        error_code=error_code,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        packet_id=packet_id,
        output_dir=output_dir,
        packet_output_dir=packet_output_dir,
        models_total=len(model_specs),
        scenarios_total=len(scenario_specs),
        trial_count=len(trial_ids),
        trials_total=len(trial_records),
        outputs_total=len(trial_records),
        outputs_present=outputs_present,
        outputs_missing=outputs_missing,
        outputs_ingested=outputs_ingested,
        outputs_rejected=outputs_rejected,
        dry_runs_succeeded=dry_runs_succeeded,
        dry_runs_failed=dry_runs_failed,
        fixture_runs_succeeded=fixture_runs_succeeded,
        fixture_runs_failed=fixture_runs_failed,
        actions_attempted_total=actions_attempted_total,
        actions_succeeded_total=actions_succeeded_total,
        actions_failed_total=actions_failed_total,
        expected_results_total=expected_results_total,
        expected_results_passed_total=expected_results_passed_total,
        expected_results_failed_total=expected_results_failed_total,
        trial_results=tuple(trial_results),
        model_summaries=finalized_model_summaries,
        scenario_model_summaries=finalized_scenario_summaries,
        scenario_summaries=finalized_scenario_summaries,
        limitations=limitations,
        fixture_execution_requested=execute_fixture,
    )
    return summary.to_dict()


def write_autonomous_browser_model_variance_evaluator_summary(summary: Mapping[str, Any], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_model_variance_evaluator_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _evaluate_trial(
    *,
    repo_root: Path,
    packet_id: str,
    model_alias: str,
    model_path: str,
    scenario_id: str,
    scenario_label: str,
    trial_id: str,
    trial_index: int,
    request_path: str,
    output_path: str,
    response_metadata_path: str,
    evaluation_output_dir: str,
    execute_fixture: bool,
) -> dict[str, Any]:
    raw_path = repo_root / output_path
    response_path = repo_root / response_metadata_path
    if not raw_path.exists():
        return {
            "packet_id": packet_id,
            "model_alias": model_alias,
            "model_path": model_path,
            "scenario_id": scenario_id,
            "scenario_label": scenario_label,
            "trial_id": trial_id,
            "trial_index": trial_index,
            "request_path": request_path,
            "output_path": output_path,
            "response_metadata_path": response_metadata_path,
            "captured_output_present": False,
            "status": "missing",
            "error_code": "missing_captured_output_file",
            "no_runtime_execution": True,
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "extraction_status": "skipped",
            "validation_status": "skipped",
            "dry_run_status": "skipped",
            "fixture_execution_status": "skipped",
            "actions_attempted": 0,
            "actions_succeeded": 0,
            "actions_failed": 0,
            "expected_results_total": 0,
            "expected_results_passed": 0,
            "expected_results_failed": 0,
            "finish_reason": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "plan_fingerprint": None,
        }

    ingestion_output_dir = f"{evaluation_output_dir}/ingestion/{model_alias}/{scenario_label}/{trial_id}"
    summary = ingest_autonomous_browser_planner_output(
        {
            "schema_version": INGESTION_SCHEMA_VERSION,
            "source_output_path": output_path,
            "output_dir": ingestion_output_dir,
            "limitations": ["model variance evaluator"],
        },
        repo_root=repo_root,
        execute_fixture=execute_fixture,
    )
    response_metadata = _load_response_metadata(response_path, repo_root=repo_root)
    plan_fingerprint = _trial_plan_fingerprint(summary)
    return {
        "packet_id": packet_id,
        "model_alias": model_alias,
        "model_path": model_path,
        "scenario_id": scenario_id,
        "scenario_label": scenario_label,
        "trial_id": trial_id,
        "trial_index": trial_index,
        "request_path": request_path,
        "output_path": output_path,
        "response_metadata_path": response_metadata_path,
        "captured_output_present": True,
        "status": str(summary.get("status") or "failed"),
        "error_code": summary.get("error_code"),
        "no_runtime_execution": bool(summary.get("no_runtime_execution", True)),
        "model_execution": False,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
        "extraction_status": summary.get("extraction_status"),
        "validation_status": summary.get("validation_status"),
        "dry_run_status": summary.get("dry_run_status"),
        "fixture_execution_status": summary.get("fixture_execution_status"),
        "actions_attempted": _int(summary.get("actions_attempted")),
        "actions_succeeded": _int(summary.get("actions_succeeded")),
        "actions_failed": _int(summary.get("actions_failed")),
        "expected_results_total": _int(summary.get("expected_results_total")),
        "expected_results_passed": _int(summary.get("expected_results_passed")),
        "expected_results_failed": _int(summary.get("expected_results_failed")),
        "finish_reason": response_metadata.get("finish_reason"),
        "prompt_tokens": response_metadata.get("prompt_tokens"),
        "completion_tokens": response_metadata.get("completion_tokens"),
        "total_tokens": response_metadata.get("total_tokens"),
        "plan_fingerprint": plan_fingerprint,
    }


def _load_response_metadata(path: Path, *, repo_root: Path) -> dict[str, Any]:
    response_metadata_path = _relative_path(repo_root, path)
    if not path.exists():
        return {
            "finish_reason": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "response_metadata_path": response_metadata_path,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {
            "finish_reason": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "response_metadata_path": response_metadata_path,
        }

    finish_reason = None
    prompt_tokens = None
    completion_tokens = None
    total_tokens = None
    if isinstance(payload, Mapping):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, Mapping):
                finish_reason = _safe_text(first_choice.get("finish_reason"))
        usage = payload.get("usage")
        if isinstance(usage, Mapping):
            prompt_tokens = _safe_int(usage.get("prompt_tokens"))
            completion_tokens = _safe_int(usage.get("completion_tokens"))
            total_tokens = _safe_int(usage.get("total_tokens"))
    return {
        "finish_reason": finish_reason,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "response_metadata_path": response_metadata_path,
    }


def _trial_plan_fingerprint(summary: Mapping[str, Any]) -> str | None:
    dry_run_summary = summary.get("diagnostics", {}).get("replay", {}).get("dry_run_summary", {})
    if not isinstance(dry_run_summary, Mapping):
        return None
    validation_result = dry_run_summary.get("validation_result", {})
    if not isinstance(validation_result, Mapping):
        return None
    normalized_plan = validation_result.get("normalized_plan")
    if not isinstance(normalized_plan, Mapping):
        return None
    payload = json.dumps(normalized_plan, ensure_ascii=False, sort_keys=True, separators=(",", ":"))
    return hashlib.sha256(payload.encode("utf-8")).hexdigest()


def _finalize_model_summary(summary: dict[str, Any]) -> dict[str, Any]:
    completion_tokens = [value for value in summary.pop("completion_tokens") if isinstance(value, int)]
    total_tokens = [value for value in summary.pop("total_tokens") if isinstance(value, int)]
    fingerprints = sorted(summary.pop("_plan_fingerprints"))
    summary["pass_rate_validation"] = _safe_ratio(summary["validation_accepted_total"], summary["outputs_present"])
    summary["pass_rate_fixture"] = _safe_ratio(summary["fixture_runs_succeeded"], summary["scenario_trials_total"])
    summary["finish_reason_counts"] = dict(sorted(summary["finish_reason_counts"].items()))
    summary["error_code_counts"] = dict(sorted(summary["error_code_counts"].items()))
    summary["unique_plan_fingerprints"] = fingerprints
    summary["unique_plan_fingerprints_total"] = len(fingerprints)
    summary["completion_tokens_min"], summary["completion_tokens_max"], summary["completion_tokens_avg"] = _stats(completion_tokens)
    summary["total_tokens_min"], summary["total_tokens_max"], summary["total_tokens_avg"] = _stats(total_tokens)
    summary.pop("trial_results")
    return summary


def _finalize_scenario_summary(summary: dict[str, Any]) -> dict[str, Any]:
    fingerprints = sorted(summary.pop("_plan_fingerprints"))
    summary["finish_reason_counts"] = dict(sorted(summary["finish_reason_counts"].items()))
    summary["error_code_counts"] = dict(sorted(summary["error_code_counts"].items()))
    summary["unique_plan_fingerprints"] = fingerprints
    summary["stable_plan"] = summary["outputs_present"] == summary["trials_total"] and summary["outputs_rejected"] == 0 and len(fingerprints) == 1
    summary.pop("trial_results")
    return summary


def _empty_model_summary(alias: str, model_path: str, trial_ids: tuple[str, ...]) -> dict[str, Any]:
    return {
        "alias": alias,
        "model_path": model_path,
        "trials_total": len(trial_ids),
        "trial_count_per_scenario": len(trial_ids),
        "scenario_trials_total": len(trial_ids) * len(DEFAULT_SCENARIO_SPECS),
        "outputs_total": 0,
        "outputs_present": 0,
        "outputs_missing": 0,
        "outputs_ingested": 0,
        "outputs_rejected": 0,
        "validation_accepted_total": 0,
        "validation_rejected_total": 0,
        "dry_runs_succeeded": 0,
        "dry_runs_failed": 0,
        "fixture_runs_succeeded": 0,
        "fixture_runs_failed": 0,
        "actions_attempted_total": 0,
        "actions_succeeded_total": 0,
        "actions_failed_total": 0,
        "expected_results_total": 0,
        "expected_results_passed_total": 0,
        "expected_results_failed_total": 0,
        "finish_reason_counts": Counter(),
        "error_code_counts": Counter(),
        "completion_tokens": [],
        "total_tokens": [],
        "_plan_fingerprints": set(),
        "trial_results": [],
    }


def _empty_scenario_summary(
    alias: str,
    model_path: str,
    scenario_id: str,
    scenario_label: str,
    trial_ids: tuple[str, ...],
) -> dict[str, Any]:
    return {
        "model_alias": alias,
        "model_path": model_path,
        "scenario_id": scenario_id,
        "scenario_label": scenario_label,
        "trials_total": len(trial_ids),
        "validation_accepted_total": 0,
        "validation_rejected_total": 0,
        "outputs_total": 0,
        "outputs_present": 0,
        "outputs_missing": 0,
        "outputs_ingested": 0,
        "outputs_rejected": 0,
        "dry_runs_succeeded": 0,
        "dry_runs_failed": 0,
        "fixture_runs_succeeded": 0,
        "fixture_runs_failed": 0,
        "actions_attempted_total": 0,
        "actions_succeeded_total": 0,
        "actions_failed_total": 0,
        "expected_results_total": 0,
        "expected_results_passed_total": 0,
        "expected_results_failed_total": 0,
        "finish_reason_counts": Counter(),
        "error_code_counts": Counter(),
        "_plan_fingerprints": set(),
        "trial_results": [],
    }


def _increment_counter(counter: Counter, value: Any) -> None:
    text = _safe_text(value)
    if text is not None:
        counter[text] += 1


def _safe_ratio(numerator: int, denominator: int) -> float:
    if denominator <= 0:
        return 0.0
    return round(numerator / denominator, 3)


def _stats(values: list[int]) -> tuple[int | None, int | None, float | None]:
    if not values:
        return None, None, None
    return min(values), max(values), round(sum(values) / len(values), 3)


def _load_config(config_artifact: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config_artifact, Mapping):
        payload = dict(config_artifact)
    else:
        try:
            payload = json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))
        except (OSError, json.JSONDecodeError):
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "packet_id": None,
                "output_dir": None,
                "packet_output_dir": None,
                "limitations": _limitations(),
            }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": None,
            "output_dir": None,
            "packet_output_dir": None,
            "limitations": _limitations(),
        }
    if str(payload.get("schema_version", "")) != CONFIG_SCHEMA_VERSION:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": _safe_text(payload.get("packet_id", DEFAULT_PACKET_ID)),
            "output_dir": _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR)),
            "packet_output_dir": _safe_relative_path(payload.get("packet_output_dir", DEFAULT_OUTPUT_DIR)),
            "limitations": _limitations(),
        }

    packet_id = _safe_identifier(payload.get("packet_id", DEFAULT_PACKET_ID))
    output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR))
    packet_output_dir = _safe_relative_path(payload.get("packet_output_dir", DEFAULT_OUTPUT_DIR))
    no_runtime_execution = payload.get("no_runtime_execution") is True
    replay_mode = str(payload.get("replay_mode", "dry_run")).strip() or "dry_run"
    model_specs = _safe_model_specs(payload.get("models"))
    scenario_specs = _safe_scenario_specs(payload.get("scenarios"))
    trial_ids = _safe_trial_ids(payload.get("trial_ids"))
    trial_records = _safe_trial_records(payload.get("trial_records"))
    captured_outputs = payload.get("captured_outputs")

    if (
        packet_id is None
        or output_dir is None
        or packet_output_dir is None
        or not no_runtime_execution
        or replay_mode not in {"dry_run", "fixture_execution"}
        or model_specs is None
        or scenario_specs is None
        or trial_ids is None
        or trial_records is None
    ):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "packet_output_dir": packet_output_dir,
            "limitations": _limitations(),
        }
    expected_trials = len(model_specs) * len(scenario_specs) * len(trial_ids)
    if len(trial_records) != expected_trials:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "packet_output_dir": packet_output_dir,
            "limitations": _limitations(),
        }
    if isinstance(captured_outputs, list) and len(captured_outputs) != expected_trials:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "packet_output_dir": packet_output_dir,
            "limitations": _limitations(),
        }
    if tuple(item["alias"] for item in model_specs) != tuple(spec["alias"] for spec in DEFAULT_MODEL_SPECS):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "packet_output_dir": packet_output_dir,
            "limitations": _limitations(),
        }
    if tuple(item["scenario_id"] for item in scenario_specs) != tuple(spec["scenario_id"] for spec in DEFAULT_SCENARIO_SPECS):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "packet_output_dir": packet_output_dir,
            "limitations": _limitations(),
        }
    if tuple(trial_ids) != DEFAULT_TRIAL_IDS:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "packet_output_dir": packet_output_dir,
            "limitations": _limitations(),
        }

    return {
        "status": "ok",
        "packet_id": packet_id,
        "output_dir": output_dir,
        "packet_output_dir": packet_output_dir,
        "model_specs": tuple(model_specs),
        "scenario_specs": tuple(scenario_specs),
        "trial_ids": tuple(trial_ids),
        "trial_records": tuple(trial_records),
        "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
    }


def _safe_model_specs(value: Any) -> tuple[dict[str, Any], ...] | None:
    if not isinstance(value, list) or not value:
        return None
    cleaned: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        alias = _safe_identifier(item.get("alias"))
        model_path = _safe_relative_path(item.get("model_path"))
        if alias is None or model_path is None:
            return None
        spec: dict[str, Any] = {"alias": alias, "model_path": model_path}
        prompt_prefix = item.get("prompt_prefix")
        if prompt_prefix is not None:
            if not isinstance(prompt_prefix, str) or not prompt_prefix.strip():
                return None
            spec["prompt_prefix"] = prompt_prefix.strip()
        cleaned.append(spec)
    return tuple(cleaned)


def _safe_scenario_specs(value: Any) -> tuple[dict[str, Any], ...] | None:
    if not isinstance(value, list) or not value:
        return None
    cleaned: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        scenario_id = _safe_identifier(item.get("scenario_id"))
        scenario_label = _safe_identifier(item.get("scenario_label"))
        prompt_filename = _safe_identifier(item.get("prompt_filename"))
        max_tokens = item.get("max_tokens")
        if scenario_id is None or scenario_label is None or prompt_filename is None:
            return None
        if not isinstance(max_tokens, int) or isinstance(max_tokens, bool) or max_tokens < 1:
            return None
        cleaned.append(
            {
                "scenario_id": scenario_id,
                "scenario_label": scenario_label,
                "prompt_filename": prompt_filename,
                "max_tokens": max_tokens,
            }
        )
    return tuple(cleaned)


def _safe_trial_ids(value: Any) -> tuple[str, ...] | None:
    if not isinstance(value, list) or not value:
        return None
    cleaned: list[str] = []
    for item in value:
        trial_id = _safe_identifier(item)
        if trial_id is None:
            return None
        cleaned.append(trial_id)
    return tuple(cleaned)


def _safe_trial_records(value: Any) -> tuple[dict[str, Any], ...] | None:
    if not isinstance(value, list) or not value:
        return None
    cleaned: list[dict[str, Any]] = []
    for item in value:
        if not isinstance(item, Mapping):
            return None
        model_alias = _safe_identifier(item.get("model_alias"))
        model_path = _safe_relative_path(item.get("model_path"))
        scenario_id = _safe_identifier(item.get("scenario_id"))
        scenario_label = _safe_identifier(item.get("scenario_label"))
        trial_id = _safe_identifier(item.get("trial_id"))
        request_path = _safe_relative_path(item.get("request_path"))
        output_path = _safe_relative_path(item.get("output_path"))
        response_metadata_path = _safe_relative_path(item.get("response_metadata_path"))
        trial_index = item.get("trial_index")
        if (
            model_alias is None
            or model_path is None
            or scenario_id is None
            or scenario_label is None
            or trial_id is None
            or request_path is None
            or output_path is None
            or response_metadata_path is None
            or not isinstance(trial_index, int)
            or isinstance(trial_index, bool)
            or trial_index < 1
        ):
            return None
        cleaned.append(
            {
                "model_alias": model_alias,
                "model_path": model_path,
                "scenario_id": scenario_id,
                "scenario_label": scenario_label,
                "trial_id": trial_id,
                "trial_index": trial_index,
                "request_path": request_path,
                "output_path": output_path,
                "response_metadata_path": response_metadata_path,
            }
        )
    return tuple(cleaned)


def _safe_identifier(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    if any(ch.isspace() for ch in text):
        return None
    if any(sep in text for sep in ("/", "\\", ":", "..")):
        return None
    return text


def _safe_relative_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return None
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        return None
    return path.as_posix()


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return None


def _int(value: Any) -> int:
    if isinstance(value, bool):
        return int(value)
    if isinstance(value, int):
        return value
    return 0


def _failure_summary(
    *,
    packet_id: str | None,
    output_dir: str | None,
    packet_output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = ModelVarianceEvaluatorSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        packet_id=packet_id,
        output_dir=output_dir,
        packet_output_dir=packet_output_dir,
        models_total=0,
        scenarios_total=0,
        trial_count=0,
        trials_total=0,
        outputs_total=0,
        outputs_present=0,
        outputs_missing=0,
        outputs_ingested=0,
        outputs_rejected=0,
        dry_runs_succeeded=0,
        dry_runs_failed=0,
        fixture_runs_succeeded=0,
        fixture_runs_failed=0,
        actions_attempted_total=0,
        actions_succeeded_total=0,
        actions_failed_total=0,
        expected_results_total=0,
        expected_results_passed_total=0,
        expected_results_failed_total=0,
        limitations=limitations,
    )
    return summary.to_dict()


def _limitations() -> tuple[str, ...]:
    return (
        "offline repeated hard-trials evaluator only",
        "manual second_model and third_model outputs only",
        "no model calls",
        "no real browser execution",
        "fixture replay remains offline only",
        "not production browser automation",
    )


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list | set):
        return [_jsonable(item) for item in value]
    if isinstance(value, str | int | float | bool) or value is None:
        return value
    return str(value)


def _relative_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve(strict=False).relative_to(repo_root.resolve(strict=False)).as_posix()
    except (OSError, ValueError):
        return path.as_posix()
