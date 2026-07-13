from __future__ import annotations

import csv
import json
from pathlib import Path
from typing import Any

from .autonomous_browser_stateful_readonly_workflow import (
    build_default_stateful_readonly_workflow_scenarios,
    build_final_presentation_stateful_readonly_workflow_scenarios,
    build_frozen_raw_stateful_readonly_workflow_scenarios,
)
from .evaluation_models import EvaluationModelRegistry, load_evaluation_models_config


SUMMARY_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_planner_final_presentation_summary_v1"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_planner_summaries/final_presentation_benchmark_tables"
MARKDOWN_FILENAME = "final_presentation_benchmark_summary.md"
CSV_FILENAME = "final_presentation_benchmark_models.csv"
JSON_FILENAME = "final_presentation_benchmark_summary.json"


def summarize_final_presentation_benchmark(
    *,
    evaluator_summary: dict[str, Any],
    runner_summary: dict[str, Any] | None = None,
    packet_manifest: dict[str, Any] | None = None,
    models_config_path: str | Path = "configs/evaluation_models.json",
) -> dict[str, Any]:
    registry = EvaluationModelRegistry(load_evaluation_models_config(models_config_path))
    model_aliases = [str(item) for item in evaluator_summary.get("model_aliases", [])]
    scenario_ids = [str(item) for item in evaluator_summary.get("scenario_ids", [])]
    scenario_catalog = str(
        evaluator_summary.get("scenario_catalog")
        or (packet_manifest.get("scenario_catalog") if packet_manifest else "")
    )
    scenario_defs = _scenario_definitions_for_catalog(scenario_catalog)
    runner_results = {
        str(item.get("model_alias")): item
        for item in runner_summary.get("model_results", [])
    } if isinstance(runner_summary, dict) else {}

    best_model = str(evaluator_summary.get("best_model_by_pass_rate") or "") or None
    model_summaries = {
        str(item["alias"]): dict(item)
        for item in evaluator_summary.get("model_summaries", [])
        if isinstance(item, dict) and "alias" in item
    }
    model_rows: list[dict[str, Any]] = []
    for alias in model_aliases:
        summary = model_summaries.get(alias, {})
        spec = registry.require(alias)
        runner_row = runner_results.get(alias, {})
        total_elapsed = _safe_float(runner_row.get("elapsed_seconds"))
        requests_total = int(runner_row.get("requests_total", 0) or 0)
        average_request = round(total_elapsed / requests_total, 6) if total_elapsed is not None and requests_total > 0 else None
        finish_counts = dict(summary.get("finish_reason_counts") or {})
        failure_counts = dict(summary.get("failure_class_counts") or {})
        notes: list[str] = []
        if alias == best_model:
            notes.append("best pass rate")
        role = spec.role or ""
        if "baseline" in role:
            notes.append("small baseline")
        if "Qwen" not in spec.display_name:
            notes.append("non-Qwen")
        model_rows.append(
            {
                "model_alias": alias,
                "model_label": spec.display_name,
                "role": role,
                "outputs_present": int(summary.get("outputs_present", 0) or 0),
                "validation_accepted": int(summary.get("validation_accepted", 0) or 0),
                "validation_rejected": int(summary.get("validation_rejected", 0) or 0),
                "workflows_succeeded": int(summary.get("workflows_succeeded", 0) or 0),
                "workflows_failed": int(summary.get("workflows_failed", 0) or 0),
                "pass_rate_overall": _safe_float(summary.get("pass_rate_overall")) or 0.0,
                "validation_acceptance_rate": _safe_float(summary.get("validation_acceptance_rate")) or 0.0,
                "finish_reason_stop": int(finish_counts.get("stop", 0) or 0),
                "finish_reason_length": int(finish_counts.get("length", 0) or 0),
                "failure_model_failed_task": int(failure_counts.get("model_failed_task", 0) or 0),
                "total_elapsed_seconds": total_elapsed,
                "average_request_seconds": average_request,
                "notes": "; ".join(notes),
            }
        )
    model_rows.sort(key=lambda item: (-float(item["pass_rate_overall"]), str(item["model_alias"])))

    grouped_outputs: dict[tuple[str, str], list[dict[str, Any]]] = {}
    for item in evaluator_summary.get("output_summaries", []):
        if not isinstance(item, dict):
            continue
        key = (str(item.get("scenario_id") or ""), str(item.get("model_alias") or ""))
        grouped_outputs.setdefault(key, []).append(item)

    scenario_matrix_rows: list[dict[str, Any]] = []
    for scenario_id in scenario_ids:
        scenario = scenario_defs.get(scenario_id)
        row = {
            "scenario_id": scenario_id,
            "difficulty": getattr(scenario, "difficulty", "unknown") if scenario is not None else "unknown",
            "benchmark_category": getattr(scenario, "benchmark_category", None) if scenario is not None else None,
            "objective": getattr(scenario, "objective", "") if scenario is not None else "",
            "results": {},
        }
        for alias in model_aliases:
            row["results"][alias] = _combine_trial_results(grouped_outputs.get((scenario_id, alias), []))
        scenario_matrix_rows.append(row)

    strongest_non_qwen = next(
        (row for row in model_rows if "Qwen" not in str(row["model_label"])),
        None,
    )
    small_baseline = next(
        (row for row in model_rows if row["model_alias"] == "first_model" or "baseline" in str(row["role"])),
        None,
    )
    interpretation_lines = [
        f"Winner by pass rate: `{best_model}`." if best_model is not None else "Winner by pass rate: unavailable.",
        (
            f"Strongest non-Qwen model in this table: `{strongest_non_qwen['model_alias']}` "
            f"at `{strongest_non_qwen['workflows_succeeded']}` successful workflows."
        )
        if strongest_non_qwen is not None
        else "Strongest non-Qwen model: unavailable.",
        (
            f"Small baseline result: `{small_baseline['model_alias']}` finished "
            f"`{small_baseline['workflows_succeeded']}` workflows with pass rate "
            f"`{small_baseline['pass_rate_overall']:.3f}`."
        )
        if small_baseline is not None
        else "Small baseline result: unavailable.",
        "Caveats: fixture-only, no production-readiness claim, no model-specific prompt tuning, and local runtime conditions may change the ranking.",
    ]
    interpretation_markdown = "\n".join(f"- {line}" for line in interpretation_lines)

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": "succeeded",
        "error_code": None,
        "scenario_catalog": scenario_catalog,
        "winner_by_pass_rate": best_model,
        "model_rows": model_rows,
        "scenario_matrix_rows": scenario_matrix_rows,
        "interpretation_markdown": interpretation_markdown,
        "runner_summary_present": runner_summary is not None,
    }


def write_final_presentation_benchmark_summary(
    *,
    evaluator_summary: dict[str, Any],
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    runner_summary: dict[str, Any] | None = None,
    packet_manifest: dict[str, Any] | None = None,
    models_config_path: str | Path = "configs/evaluation_models.json",
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    summary = summarize_final_presentation_benchmark(
        evaluator_summary=evaluator_summary,
        runner_summary=runner_summary,
        packet_manifest=packet_manifest,
        models_config_path=models_config_path,
    )
    repo = Path(repo_root) if repo_root is not None else Path(".")
    output_root = repo / Path(output_dir)
    output_root.mkdir(parents=True, exist_ok=True)

    markdown_path = output_root / MARKDOWN_FILENAME
    csv_path = output_root / CSV_FILENAME
    json_path = output_root / JSON_FILENAME

    markdown_path.write_text(_render_markdown(summary), encoding="utf-8")
    _write_csv(csv_path, summary["model_rows"])
    json_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    return {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": "succeeded",
        "error_code": None,
        "output_dir": Path(output_dir).as_posix(),
        "markdown_path": f"{Path(output_dir).as_posix()}/{MARKDOWN_FILENAME}",
        "csv_path": f"{Path(output_dir).as_posix()}/{CSV_FILENAME}",
        "json_path": f"{Path(output_dir).as_posix()}/{JSON_FILENAME}",
        "winner_by_pass_rate": summary.get("winner_by_pass_rate"),
    }


def load_json_artifact(path: str | Path) -> dict[str, Any]:
    payload = json.loads(Path(path).read_text(encoding="utf-8-sig"))
    if not isinstance(payload, dict):
        raise ValueError("artifact root must be a JSON object")
    return payload


def _scenario_definitions_for_catalog(catalog: str) -> dict[str, Any]:
    if catalog == "legacy_stateful_v1":
        return build_default_stateful_readonly_workflow_scenarios()
    if catalog == "frozen_raw_v1":
        return build_frozen_raw_stateful_readonly_workflow_scenarios()
    if catalog == "final_presentation_v1":
        return build_final_presentation_stateful_readonly_workflow_scenarios()
    return {}


def _safe_float(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return round(float(value), 6)
    return None


def _combine_trial_results(results: list[dict[str, Any]]) -> str:
    if not results:
        return "MISSING"
    statuses = [_cell_status(item) for item in results]
    if all(item == "PASS" for item in statuses):
        return "PASS"
    if "FAIL" in statuses:
        return "FAIL"
    if "REJECTED" in statuses:
        return "REJECTED"
    return "MISSING"


def _cell_status(result: dict[str, Any]) -> str:
    if not bool(result.get("captured_output_present")):
        return "MISSING"
    if str(result.get("validation_status") or "") != "accepted":
        return "REJECTED"
    if str(result.get("workflow_status") or "") == "succeeded":
        return "PASS"
    return "FAIL"


def _write_csv(path: Path, rows: list[dict[str, Any]]) -> None:
    fieldnames = [
        "model_alias",
        "model_label",
        "role",
        "outputs_present",
        "validation_accepted",
        "validation_rejected",
        "workflows_succeeded",
        "workflows_failed",
        "pass_rate_overall",
        "validation_acceptance_rate",
        "finish_reason_stop",
        "finish_reason_length",
        "failure_model_failed_task",
        "total_elapsed_seconds",
        "average_request_seconds",
        "notes",
    ]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fieldnames)
        writer.writeheader()
        for row in rows:
            writer.writerow(row)


def _render_markdown(summary: dict[str, Any]) -> str:
    model_rows = summary["model_rows"]
    scenario_rows = summary["scenario_matrix_rows"]
    model_header = (
        "| model_alias | model_label | role | outputs_present | validation_accepted | "
        "validation_rejected | workflows_succeeded | workflows_failed | pass_rate_overall | "
        "validation_acceptance_rate | finish_reason_stop | finish_reason_length | "
        "failure_model_failed_task | total_elapsed_seconds | average_request_seconds | notes |\n"
        "| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | --- |\n"
    )
    model_lines = "".join(
        (
            f"| {row['model_alias']} | {row['model_label']} | {row['role']} | {row['outputs_present']} | "
            f"{row['validation_accepted']} | {row['validation_rejected']} | {row['workflows_succeeded']} | "
            f"{row['workflows_failed']} | {row['pass_rate_overall']:.3f} | "
            f"{row['validation_acceptance_rate']:.3f} | {row['finish_reason_stop']} | "
            f"{row['finish_reason_length']} | {row['failure_model_failed_task']} | "
            f"{'' if row['total_elapsed_seconds'] is None else row['total_elapsed_seconds']} | "
            f"{'' if row['average_request_seconds'] is None else row['average_request_seconds']} | {row['notes']} |\n"
        )
        for row in model_rows
    )

    aliases = [str(row["model_alias"]) for row in model_rows]
    matrix_header = (
        "| scenario_id | difficulty | category | " + " | ".join(aliases) + " |\n"
        "| --- | --- | --- | " + " | ".join("---" for _ in aliases) + " |\n"
    )
    matrix_lines = "".join(
        (
            f"| {row['scenario_id']} | {row['difficulty']} | {row.get('benchmark_category') or ''} | "
            + " | ".join(str(row["results"].get(alias, "MISSING")) for alias in aliases)
            + " |\n"
        )
        for row in scenario_rows
    )

    return (
        "# Final Presentation Benchmark Summary\n\n"
        "## Model Table\n\n"
        f"{model_header}{model_lines}\n"
        "## Scenario Matrix\n\n"
        f"{matrix_header}{matrix_lines}\n"
        "## Interpretation\n\n"
        f"{summary['interpretation_markdown']}\n"
    )
