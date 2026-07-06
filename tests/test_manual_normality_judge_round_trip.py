from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_evaluation_scorecard import (
    MODEL_EVALUATION_SCORECARD_FILENAME,
    build_model_evaluation_scorecard,
    write_model_evaluation_scorecard,
)
from src.agent.model_pair_matrix_adapters import (
    MATRIX_RUN_ADAPTER_SUMMARY_FILENAME,
    NORMALITY_JUDGE_INPUTS_JSONL_FILENAME,
    write_matrix_run_adapter_outputs,
)
from src.agent.normality_comparison import (
    NORMALITY_COMPARISON_SUMMARY_FILENAME,
    compare_normality_batch_summaries,
    write_normality_comparison_summary,
)
from src.agent.normality_evaluation_runner import NORMALITY_BATCH_SUMMARY_FILENAME
from src.agent.normality_judge import NORMALITY_DIMENSIONS
from src.agent.prepared_normality_judge_exchange import (
    NORMALITY_JUDGE_BATCH_RAW_RESPONSES_JSONL_FILENAME,
    NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME,
    NORMALITY_JUDGE_PROMPT_PACK_SUMMARY_FILENAME,
    build_normality_batch_summary_from_raw_responses,
    build_prepared_normality_judge_prompt_pack,
    load_exchange_prepared_normality_inputs,
    load_normality_judge_raw_responses,
    load_prepared_normality_judge_prompt_pack,
    write_prepared_normality_judge_prompt_pack,
)
from src.agent.prepared_normality_judge_exchange_cli import main as exchange_cli_main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
PAIR_ID = "second_model__to__first_model"
PAIR_LABEL = "second_model->first_model"
SCENARIO_ID = "office_document_file_workflow_basic_v1"
RAW_RESPONSE_MARKER = "RAW_MANUAL_JUDGE_RESPONSE_SHOULD_NOT_COPY"


def _event(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent_id": "office_agent",
        "role": "office document worker",
        "action": "office_create_docx",
        "status": "success",
        "summary": "Created an offline document artifact from a fixture request.",
        "artifact_paths": ["artifacts/office/manual_round_trip_report.docx"],
        "metadata": {
            "execution_attempted": False,
            "validation_accepted": True,
        },
    }
    payload.update(overrides)
    return payload


def _trial(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "trial_id": "manual_round_trip_trial_001",
        "scenario_id": SCENARIO_ID,
        "pair_id": PAIR_ID,
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
        "status": "succeeded",
        "task_success": True,
        "correctness_score": 0.94,
        "resource_observation": {
            "runtime_mode": "offline_fixture",
            "backend": "manual_round_trip_fixture",
            "success": True,
            "wall_time_s": 1.5,
            "notes": ["Synthetic offline observation only."],
        },
        "group_history": [
            _event(action="office_create_docx"),
            _event(action="office_validate_docx", summary="Validated the synthetic artifact metadata."),
        ],
        "task_summary": "Create and validate an offline office document artifact.",
        "warnings": [],
        "notes": ["manual_normality_round_trip"],
        "tags": ["manual_round_trip", "offline"],
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _matrix_summary(*trials: dict[str, Any]) -> dict[str, Any]:
    return {
        "schema_version": "model_pair_matrix_run_summary_v1",
        "run_id": "manual_round_trip_matrix_run",
        "plan_id": "manual_round_trip_plan",
        "execution_mode": "static_fixture",
        "trial_count": len(trials) or 1,
        "succeeded_count": len(trials) or 1,
        "failed_count": 0,
        "skipped_count": 0,
        "dry_run_count": 0,
        "pair_summaries": [],
        "scenario_summaries": [],
        "trial_results": list(trials) or [_trial()],
        "warnings": [],
        "notes": ["Synthetic matrix run summary for manual judge exchange."],
        "no_runtime_execution": True,
    }


def _dimension(score: float = 0.92) -> dict[str, Any]:
    return {
        "score": score,
        "rationale": "The saved response describes plausible offline agent activity.",
        "findings": [],
    }


def _judge_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "ok",
        "label": "normal",
        "overall_score": 0.92,
        "dimension_scores": {name: _dimension() for name in NORMALITY_DIMENSIONS},
        "findings": ["manual_saved_response_parsed"],
        "redactions_applied": [],
        "judge_mode": "llm",
        "provider_name": "manual_saved_fixture",
        "schema_version": "normality_judge_result_v1",
        "ignored_raw_field": RAW_RESPONSE_MARKER,
    }
    payload.update(overrides)
    return payload


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _response_for_prompt(prompt: dict[str, Any]) -> dict[str, Any]:
    return {
        "prompt_id": prompt["prompt_id"],
        "trial_id": prompt["trial_id"],
        "raw_response": json.dumps(_judge_payload(), ensure_ascii=False),
        "metadata": {"source": "manual_fixture", "no_runtime_execution": True},
    }


def _pair(scorecard: Any, pair_id: str) -> dict[str, Any]:
    return next(pair for pair in scorecard.model_pairs if pair["pair_id"] == pair_id)


def _assert_forbidden_repo_outputs_not_written() -> None:
    generated_names = {
        MATRIX_RUN_ADAPTER_SUMMARY_FILENAME,
        NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME,
        NORMALITY_JUDGE_PROMPT_PACK_SUMMARY_FILENAME,
        NORMALITY_JUDGE_BATCH_RAW_RESPONSES_JSONL_FILENAME,
        NORMALITY_BATCH_SUMMARY_FILENAME,
        NORMALITY_COMPARISON_SUMMARY_FILENAME,
        MODEL_EVALUATION_SCORECARD_FILENAME,
    }
    for folder in ("reports", "experiments"):
        for filename in generated_names:
            assert not (PROJECT_ROOT / folder / filename).exists()


def _run_manual_round_trip(tmp_path: Path) -> dict[str, Any]:
    adapter_dir = tmp_path / "matrix_adapters"
    adapter_summary = write_matrix_run_adapter_outputs(
        _matrix_summary(_trial()),
        adapter_dir,
        adapter_id="manual_round_trip_adapter",
    )
    normality_input_path = adapter_dir / NORMALITY_JUDGE_INPUTS_JSONL_FILENAME
    normality_inputs = load_exchange_prepared_normality_inputs([normality_input_path])

    prompt_pack = build_prepared_normality_judge_prompt_pack(
        normality_inputs,
        pack_id="manual_round_trip_pack",
        tags=["manual_round_trip"],
    )
    prompt_pack_path, prompt_summary_path = write_prepared_normality_judge_prompt_pack(
        prompt_pack,
        tmp_path / "prompt_pack",
    )
    loaded_prompt_pack = load_prepared_normality_judge_prompt_pack(prompt_pack_path)
    prompt = loaded_prompt_pack["prompts"][0]

    raw_response_path = _write_jsonl(
        tmp_path / NORMALITY_JUDGE_BATCH_RAW_RESPONSES_JSONL_FILENAME,
        [_response_for_prompt(prompt)],
    )
    raw_responses = load_normality_judge_raw_responses(raw_response_path)
    batch_result = build_normality_batch_summary_from_raw_responses(
        loaded_prompt_pack,
        raw_responses,
        summary_id="manual_round_trip_batch",
        tags=["manual_round_trip"],
        output_dir=tmp_path / "batch",
    )
    batch_summary_path = tmp_path / "batch" / NORMALITY_BATCH_SUMMARY_FILENAME

    comparison = compare_normality_batch_summaries([batch_summary_path], project_root=tmp_path)
    comparison_summary_path, _ = write_normality_comparison_summary(comparison, tmp_path / "comparison")

    scorecard = build_model_evaluation_scorecard(
        CATALOG_PATH,
        normality_comparison_summary_path=comparison_summary_path,
        scorecard_id="manual_round_trip_scorecard",
        project_root=PROJECT_ROOT,
    )
    scorecard_path, _ = write_model_evaluation_scorecard(scorecard, tmp_path / "scorecard")

    return {
        "adapter_summary": adapter_summary,
        "normality_input_path": normality_input_path,
        "normality_inputs": normality_inputs,
        "prompt_pack": prompt_pack,
        "prompt_pack_path": prompt_pack_path,
        "prompt_summary_path": prompt_summary_path,
        "loaded_prompt_pack": loaded_prompt_pack,
        "raw_response_path": raw_response_path,
        "batch_result": batch_result,
        "batch_summary_path": batch_summary_path,
        "comparison": comparison,
        "comparison_summary_path": comparison_summary_path,
        "scorecard": scorecard,
        "scorecard_path": scorecard_path,
    }


def test_manual_normality_judge_round_trip_feeds_comparison_and_scorecard(tmp_path: Path) -> None:
    result = _run_manual_round_trip(tmp_path)

    adapter_summary = result["adapter_summary"]
    normality_input_rows = _jsonl_rows(result["normality_input_path"])
    assert adapter_summary["normality_input_count"] == 1
    assert adapter_summary["normality_missing_trace_count"] == 0
    assert normality_input_rows[0]["trial_id"] == "manual_round_trip_trial_001"
    assert "normality_trace_missing" not in normality_input_rows[0]["warnings"]

    prompt_pack = result["prompt_pack"]
    prompt_summary = json.loads(result["prompt_summary_path"].read_text(encoding="utf-8"))
    prompt = result["loaded_prompt_pack"]["prompts"][0]
    full_prompt = prompt_pack["prompts"][0]["prompt"]
    assert prompt_pack["prompt_count"] == 1
    assert prompt_summary["prompt_count"] == 1
    assert prompt["metadata"]["no_runtime_execution"] is True
    assert "NORMALITY_JUDGE_PROMPT_CONTRACT" in full_prompt
    assert "OUTPUT_JSON_CONTRACT" in full_prompt
    assert all(dimension in full_prompt for dimension in NORMALITY_DIMENSIONS)
    assert str(tmp_path) not in full_prompt
    assert "C:\\" not in full_prompt

    raw_response_rows = _jsonl_rows(result["raw_response_path"])
    assert raw_response_rows[0]["prompt_id"] == prompt["prompt_id"]
    assert RAW_RESPONSE_MARKER in raw_response_rows[0]["raw_response"]

    batch_result = result["batch_result"]
    batch_summary_text = result["batch_summary_path"].read_text(encoding="utf-8")
    assert batch_result.status == "ok"
    assert batch_result.evaluated_count == prompt_pack["prompt_count"]
    assert batch_result.failed_count == 0
    assert batch_result.entries[0].label == "normal"
    assert RAW_RESPONSE_MARKER not in batch_summary_text
    assert "raw_response" not in batch_summary_text

    comparison = result["comparison"]
    comparison_summary = json.loads(result["comparison_summary_path"].read_text(encoding="utf-8"))
    assert comparison.status == "ok"
    assert PAIR_LABEL in comparison.groups["by_model_pair"]
    assert comparison.groups["by_model_pair"][PAIR_LABEL]["evaluated_count"] == 1
    assert comparison_summary["groups"]["by_model_pair"][PAIR_LABEL]["mean_overall_score"] == pytest.approx(0.92)

    scorecard = result["scorecard"]
    scorecard_text = result["scorecard_path"].read_text(encoding="utf-8")
    scorecard_pair = _pair(scorecard, PAIR_ID)
    assert scorecard.normality_summary_used is True
    assert scorecard.no_runtime_execution is True
    assert scorecard.overall["production_recommendation"] is False
    assert scorecard_pair["normality_metrics"]["evaluated_count"] == 1
    assert scorecard_pair["normality_metrics"]["mean_overall_score"] == pytest.approx(0.92)
    assert "normality_comparison_summary" in scorecard_pair["sources"]
    assert "production-ready" not in scorecard_text.lower()
    assert "no model execution performed" in scorecard_text.lower()
    assert RAW_RESPONSE_MARKER not in scorecard_text
    assert "raw_response" not in scorecard_text

    _assert_forbidden_repo_outputs_not_written()


def test_exchange_cli_export_import_round_trip_from_adapter_input(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    adapter_dir = tmp_path / "matrix_adapters"
    write_matrix_run_adapter_outputs(_matrix_summary(_trial()), adapter_dir)
    normality_input_path = adapter_dir / NORMALITY_JUDGE_INPUTS_JSONL_FILENAME

    export_code = exchange_cli_main(
        [
            "export-prompts",
            "--input",
            str(normality_input_path),
            "--output-dir",
            str(tmp_path / "prompt_pack"),
            "--pack-id",
            "cli_manual_pack",
        ]
    )
    export_payload = json.loads(capsys.readouterr().out)
    prompt_pack_path = tmp_path / "prompt_pack" / NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME
    prompt = _jsonl_rows(prompt_pack_path)[0]
    raw_response_path = _write_jsonl(
        tmp_path / NORMALITY_JUDGE_BATCH_RAW_RESPONSES_JSONL_FILENAME,
        [_response_for_prompt(prompt)],
    )

    import_code = exchange_cli_main(
        [
            "import-responses",
            "--prompt-pack",
            str(prompt_pack_path),
            "--raw-responses",
            str(raw_response_path),
            "--output-dir",
            str(tmp_path / "batch"),
            "--summary-id",
            "cli_manual_batch",
        ]
    )
    import_payload = json.loads(capsys.readouterr().out)

    assert export_code == 0
    assert export_payload["status"] == "ok"
    assert export_payload["prompt_count"] == 1
    assert export_payload["prompt_pack_path"] == NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME
    assert (tmp_path / "prompt_pack" / NORMALITY_JUDGE_PROMPT_PACK_SUMMARY_FILENAME).is_file()
    assert import_code == 0
    assert import_payload["status"] == "ok"
    assert import_payload["evaluated_count"] == 1
    assert import_payload["invalid_count"] == 0
    assert import_payload["summary_path"] == NORMALITY_BATCH_SUMMARY_FILENAME
    assert (tmp_path / "batch" / NORMALITY_BATCH_SUMMARY_FILENAME).is_file()


def test_manual_round_trip_does_not_touch_forbidden_runtime_clients_or_gguf(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_exists = Path.exists
    original_read_text = Path.read_text
    original_import = __import__

    def forbid_gguf_exists(self: Path) -> bool:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("unexpected GGUF exists check")
        return original_exists(self)

    def forbid_gguf_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("unexpected GGUF read")
        return original_read_text(self, *args, **kwargs)

    def forbid_runtime_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {
            "httpx",
            "openai",
            "playwright",
            "requests",
            "selenium",
            "torch",
            "llama_cpp",
            "docx",
            "openpyxl",
            "pptx",
        }:
            raise AssertionError("manual round trip must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    result = _run_manual_round_trip(tmp_path)

    assert result["batch_result"].status == "ok"
    assert result["scorecard"].no_runtime_execution is True
