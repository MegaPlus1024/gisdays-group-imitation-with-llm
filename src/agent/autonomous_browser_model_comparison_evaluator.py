from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_planner_output_ingestion import ingest_autonomous_browser_planner_output


CONFIG_SCHEMA_VERSION = "autonomous_browser_model_comparison_evaluator_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_model_comparison_evaluator_summary_v1"
DEFAULT_PACKET_ID = "browser_model_comparison_packet_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_comparison_packet/evaluation_runs"
INGESTION_SCHEMA_VERSION = "autonomous_browser_planner_output_ingestion_config_v1"


@dataclass(frozen=True)
class ModelComparisonEvaluatorSummary:
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
    scenario_results: tuple[dict[str, Any], ...] = ()
    model_summaries: tuple[dict[str, Any], ...] = ()
    evidence_ranked_models: tuple[dict[str, Any], ...] = ()
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
            "scenario_results": [_jsonable(item) for item in self.scenario_results],
            "model_summaries": [_jsonable(item) for item in self.model_summaries],
            "evidence_ranked_models": [_jsonable(item) for item in self.evidence_ranked_models],
            "limitations": list(self.limitations),
            "fixture_execution_requested": self.fixture_execution_requested,
        }


def run_autonomous_browser_model_comparison_evaluator(
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
    model_specs = tuple(config_result["models"])
    scenario_specs = tuple(config_result["scenarios"])
    limitations = tuple(config_result.get("limitations") or _limitations())

    scenario_results: list[dict[str, Any]] = []
    model_summaries: dict[str, dict[str, Any]] = {}
    outputs_present = 0
    outputs_missing = 0
    outputs_ingested = 0
    outputs_rejected = 0
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

    for model_spec in model_specs:
        alias = str(model_spec["alias"])
        model_summaries[alias] = _empty_model_summary(alias, str(model_spec["model_path"]))

    for scenario_spec in scenario_specs:
        scenario_id = str(scenario_spec["scenario_id"])
        scenario_label = str(scenario_spec["scenario_label"])
        scenario_request_paths = scenario_spec["request_paths"]
        scenario_output_paths = scenario_spec["output_paths"]
        for model_spec in model_specs:
            alias = str(model_spec["alias"])
            model_path = str(model_spec["model_path"])
            request_path = str(scenario_request_paths[alias])
            output_path = str(scenario_output_paths[alias])
            result = _evaluate_output(
                repo_root=repo,
                packet_id=packet_id,
                model_alias=alias,
                model_path=model_path,
                scenario_id=scenario_id,
                scenario_label=scenario_label,
                request_path=request_path,
                output_path=output_path,
                evaluation_output_dir=output_dir,
                execute_fixture=execute_fixture,
            )
            scenario_results.append(result)

            model_summary = model_summaries[alias]
            model_summary["outputs_total"] += 1
            if result["captured_output_present"]:
                outputs_present += 1
                model_summary["outputs_present"] += 1
            else:
                outputs_missing += 1
                any_missing = True
                model_summary["outputs_missing"] += 1

            if result["status"] == "succeeded":
                outputs_ingested += 1
                model_summary["outputs_ingested"] += 1
            elif result["status"] in {"rejected", "failed"} and result["captured_output_present"]:
                outputs_rejected += 1
                any_rejected = True
                model_summary["outputs_rejected"] += 1
                if first_issue_code is None:
                    first_issue_code = str(result.get("error_code") or "comparison_output_failed")

            if result["dry_run_status"] == "accepted":
                dry_runs_succeeded += 1
                model_summary["dry_runs_succeeded"] += 1
            elif result["captured_output_present"]:
                dry_runs_failed += 1
                model_summary["dry_runs_failed"] += 1

            if result["fixture_execution_status"] == "succeeded":
                fixture_runs_succeeded += 1
                model_summary["fixture_runs_succeeded"] += 1
            elif result["captured_output_present"] and execute_fixture:
                fixture_runs_failed += 1
                model_summary["fixture_runs_failed"] += 1

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
            model_summary["scenario_results"].append(result)

    if outputs_missing > 0:
        status = "completed_with_missing_outputs"
        error_code = "missing_captured_outputs"
    elif outputs_rejected > 0:
        status = "completed_with_failures"
        error_code = first_issue_code or "comparison_outputs_rejected"
    else:
        status = "succeeded"
        error_code = None

    ranked_models = tuple()
    if outputs_missing == 0:
        ranked_models = tuple(
            sorted(
                model_summaries.values(),
                key=lambda item: (
                    item["outputs_rejected"],
                    item["actions_failed_total"],
                    -item["expected_results_passed_total"],
                    item["alias"],
                ),
            )
        )

    summary = ModelComparisonEvaluatorSummary(
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
        outputs_total=len(model_specs) * len(scenario_specs),
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
        scenario_results=tuple(scenario_results),
        model_summaries=tuple(model_summaries.values()),
        evidence_ranked_models=ranked_models,
        limitations=limitations,
        fixture_execution_requested=execute_fixture,
    )
    return summary.to_dict()


def write_autonomous_browser_model_comparison_evaluator_summary(summary: Mapping[str, Any], output_dir: str | Path) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_model_comparison_evaluator_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _evaluate_output(
    *,
    repo_root: Path,
    packet_id: str,
    model_alias: str,
    model_path: str,
    scenario_id: str,
    scenario_label: str,
    request_path: str,
    output_path: str,
    evaluation_output_dir: str,
    execute_fixture: bool,
) -> dict[str, Any]:
    raw_path = repo_root / output_path
    request_path_relative = request_path
    if not raw_path.exists():
        return {
            "packet_id": packet_id,
            "model_alias": model_alias,
            "model_path": model_path,
            "scenario_id": scenario_id,
            "scenario_label": scenario_label,
            "request_path": request_path_relative,
            "output_path": output_path,
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
            "response_metadata_path": None,
        }

    ingestion_output_dir = f"{evaluation_output_dir}/ingestion/{model_alias}/{scenario_label}"
    summary = ingest_autonomous_browser_planner_output(
        {
            "schema_version": INGESTION_SCHEMA_VERSION,
            "source_output_path": output_path,
            "output_dir": ingestion_output_dir,
            "limitations": ["model comparison evaluator"],
        },
        repo_root=repo_root,
        execute_fixture=execute_fixture,
    )

    response_metadata = _load_response_metadata(raw_path.with_name("response.json"))
    scenario_result = {
        "packet_id": packet_id,
        "model_alias": model_alias,
        "model_path": model_path,
        "scenario_id": scenario_id,
        "scenario_label": scenario_label,
        "request_path": request_path_relative,
        "output_path": output_path,
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
        "response_metadata_path": response_metadata.get("response_metadata_path"),
    }
    return scenario_result


def _load_response_metadata(path: Path) -> dict[str, Any]:
    if not path.exists():
        return {
            "finish_reason": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "response_metadata_path": None,
        }
    try:
        payload = json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {
            "finish_reason": None,
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
            "response_metadata_path": path.as_posix(),
        }

    finish_reason = None
    if isinstance(payload, Mapping):
        choices = payload.get("choices")
        if isinstance(choices, list) and choices:
            first_choice = choices[0]
            if isinstance(first_choice, Mapping):
                finish_reason = _safe_text(first_choice.get("finish_reason"))
        usage = payload.get("usage")
        prompt_tokens = _safe_int(usage.get("prompt_tokens")) if isinstance(usage, Mapping) else None
        completion_tokens = _safe_int(usage.get("completion_tokens")) if isinstance(usage, Mapping) else None
        total_tokens = _safe_int(usage.get("total_tokens")) if isinstance(usage, Mapping) else None
    else:
        prompt_tokens = None
        completion_tokens = None
        total_tokens = None
    return {
        "finish_reason": finish_reason,
        "prompt_tokens": prompt_tokens,
        "completion_tokens": completion_tokens,
        "total_tokens": total_tokens,
        "response_metadata_path": path.as_posix(),
    }


def _load_config(config_artifact: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config_artifact, Mapping):
        payload = dict(config_artifact)
    else:
        try:
            payload = json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))
        except OSError:
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "packet_id": None,
                "output_dir": None,
                "packet_output_dir": None,
                "limitations": _limitations(),
            }
        except json.JSONDecodeError:
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
            "packet_id": _safe_identifier(payload.get("packet_id", DEFAULT_PACKET_ID)),
            "output_dir": _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR)),
            "packet_output_dir": _safe_relative_path(payload.get("packet_output_dir", DEFAULT_OUTPUT_DIR)),
            "limitations": _limitations(),
        }

    packet_id = _safe_identifier(payload.get("packet_id", DEFAULT_PACKET_ID))
    output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR))
    packet_output_dir = _safe_relative_path(payload.get("packet_output_dir", DEFAULT_OUTPUT_DIR))
    if packet_id is None or output_dir is None or packet_output_dir is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "packet_output_dir": packet_output_dir,
            "limitations": _limitations(),
        }

    models = _safe_model_specs(payload.get("models"))
    scenarios = _safe_scenario_specs(payload.get("scenarios"))
    if models is None or scenarios is None:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "output_dir": output_dir,
            "packet_output_dir": packet_output_dir,
            "limitations": _limitations(),
        }
    if not payload.get("no_runtime_execution") is True:
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
        "models": models,
        "scenarios": scenarios,
        "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
    }


def _safe_model_specs(value: Any) -> tuple[dict[str, str], ...] | None:
    if not isinstance(value, list) or not value:
        return None
    specs: list[dict[str, str]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            return None
        alias = _safe_identifier(entry.get("alias"))
        model_path = _safe_relative_path(entry.get("model_path"))
        if alias is None or model_path is None:
            return None
        specs.append({"alias": alias, "model_path": model_path})
    return tuple(specs)


def _safe_scenario_specs(value: Any) -> tuple[dict[str, Any], ...] | None:
    if not isinstance(value, list) or not value:
        return None
    specs: list[dict[str, Any]] = []
    for entry in value:
        if not isinstance(entry, Mapping):
            return None
        scenario_id = _safe_identifier(entry.get("scenario_id"))
        scenario_label = _safe_identifier(entry.get("scenario_label"))
        prompt_filename = _safe_identifier(entry.get("prompt_filename"))
        max_tokens = entry.get("max_tokens")
        request_paths = entry.get("request_paths")
        output_paths = entry.get("output_paths")
        if (
            scenario_id is None
            or scenario_label is None
            or prompt_filename is None
            or not isinstance(max_tokens, int)
            or isinstance(max_tokens, bool)
            or max_tokens < 1
            or not isinstance(request_paths, Mapping)
            or not isinstance(output_paths, Mapping)
        ):
            return None
        cleaned_request_paths: dict[str, str] = {}
        cleaned_output_paths: dict[str, str] = {}
        for key, path_value in request_paths.items():
            alias = _safe_identifier(key)
            path = _safe_relative_path(path_value)
            if alias is None or path is None:
                return None
            cleaned_request_paths[alias] = path
        for key, path_value in output_paths.items():
            alias = _safe_identifier(key)
            path = _safe_relative_path(path_value)
            if alias is None or path is None:
                return None
            cleaned_output_paths[alias] = path
        specs.append(
            {
                "scenario_id": scenario_id,
                "scenario_label": scenario_label,
                "prompt_filename": prompt_filename,
                "max_tokens": max_tokens,
                "request_paths": cleaned_request_paths,
                "output_paths": cleaned_output_paths,
            }
        )
    return tuple(specs)


def _empty_model_summary(alias: str, model_path: str) -> dict[str, Any]:
    return {
        "alias": alias,
        "model_path": model_path,
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
        "scenario_results": [],
    }


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _safe_identifier(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    if any(ch in stripped for ch in ("\\", "/", ":", "\0")):
        return None
    return stripped


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


def _safe_int(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int):
        return value
    return None


def _int(value: Any) -> int:
    return _safe_int(value) or 0


def _limitations() -> tuple[str, ...]:
    return (
        "offline comparison evaluator only",
        "captured planner outputs only",
        "no model calls",
        "no real browser execution",
        "no Playwright import in evaluator",
        "fixture replay remains offline only",
        "not production browser automation",
    )


def _failure_summary(
    *,
    packet_id: str | None,
    output_dir: str | None,
    packet_output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = ModelComparisonEvaluatorSummary(
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
        scenario_results=(),
        model_summaries=(),
        evidence_ranked_models=(),
        limitations=limitations,
        fixture_execution_requested=False,
    )
    return summary.to_dict()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, tuple | list):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    return value


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
