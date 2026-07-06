from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_pair_matrix_adapters import build_normality_inputs_from_matrix_run_summary
from src.agent.normality_comparison import compare_normality_batch_summaries
from src.agent.normality_evaluation_runner import NORMALITY_BATCH_SUMMARY_FILENAME
from src.agent.normality_judge import NORMALITY_DIMENSIONS, NormalityJudgeResult
from src.agent.prepared_normality_input_processor import (
    PreparedNormalityInputLoadError,
    convert_prepared_input_to_normality_judge_input,
    load_prepared_normality_inputs,
    process_prepared_normality_inputs,
)
from src.agent.prepared_normality_input_processor_cli import main as processor_cli_main


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _event(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "agent_id": "office_agent",
        "role": "office document worker",
        "action": "office_create_docx",
        "status": "success",
        "summary": "Created an offline document artifact.",
        "artifact_paths": ["artifacts/office/report.docx"],
    }
    payload.update(overrides)
    return payload


def _prepared_input(trace_key: str = "group_history", **overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "input_format": "normality_judge_input_record_v1",
        "trial_id": "trial_001",
        "scenario_id": "office_document_file_workflow_basic_v1",
        "pair_id": "second_model__to__first_model",
        "model_pair": {
            "orchestrator": "second_model",
            "executor": "first_model",
        },
        "task_summary": "Evaluate prepared offline office workflow activity.",
        "events": [_event()],
        "tags": ["prepared_test"],
        "metadata": {
            "source_run_id": "matrix_run_001",
            "no_runtime_execution": True,
        },
        "warnings": [],
        "no_runtime_execution": True,
    }
    if trace_key != "events":
        payload[trace_key] = [_event(action=f"{trace_key}_action")]
        payload["events"] = payload[trace_key]
    payload.update(overrides)
    return payload


def _missing_trace_input() -> dict[str, Any]:
    return _prepared_input(
        events=[],
        adapter_status="invalid_input",
        warnings=["normality_trace_missing"],
    )


def _matrix_prepared_input() -> dict[str, Any]:
    matrix_summary = {
        "schema_version": "model_pair_matrix_run_summary_v1",
        "run_id": "matrix_from_adapter",
        "trial_count": 1,
        "trial_results": [
            {
                "trial_id": "trial_from_adapter",
                "scenario_id": "office_document_file_workflow_basic_v1",
                "pair_id": "second_model__to__first_model",
                "orchestrator_model_id": "second_model",
                "executor_model_id": "first_model",
                "status": "succeeded",
                "task_success": True,
                "group_history": [_event()],
            }
        ],
    }
    return build_normality_inputs_from_matrix_run_summary(matrix_summary)[0]


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, Any]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "".join(json.dumps(row, ensure_ascii=False, sort_keys=True) + "\n" for row in rows),
        encoding="utf-8",
    )
    return path


def _static_result_payload(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "ok",
        "label": "suspicious",
        "overall_score": 0.42,
        "dimension_scores": {
            name: {
                "score": 0.42,
                "rationale": f"{name} static rationale.",
                "findings": [],
            }
            for name in NORMALITY_DIMENSIONS
        },
        "findings": ["static_provider_used"],
        "redactions_applied": [],
        "judge_mode": "static",
    }
    payload.update(overrides)
    return payload


def test_loads_jsonl_prepared_inputs(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "normality_judge_inputs.jsonl", [_prepared_input()])

    records = load_prepared_normality_inputs(path)

    assert records[0]["trial_id"] == "trial_001"


def test_loads_json_list_prepared_inputs(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "normality_inputs.json", [_prepared_input()])

    records = load_prepared_normality_inputs(path)

    assert len(records) == 1
    assert records[0]["scenario_id"] == "office_document_file_workflow_basic_v1"


@pytest.mark.parametrize("records_key", ["inputs", "normality_inputs", "records"])
def test_loads_json_dict_prepared_inputs(tmp_path: Path, records_key: str) -> None:
    path = _write_json(tmp_path / f"{records_key}.json", {records_key: [_prepared_input()]})

    records = load_prepared_normality_inputs(path)

    assert records[0]["pair_id"] == "second_model__to__first_model"


def test_missing_file_returns_controlled_error(tmp_path: Path) -> None:
    with pytest.raises(PreparedNormalityInputLoadError) as exc:
        load_prepared_normality_inputs(tmp_path / "missing.jsonl")

    assert str(exc.value) == "prepared_normality_input_file_missing"


def test_malformed_file_returns_controlled_error(tmp_path: Path) -> None:
    path = tmp_path / "normality_judge_inputs.json"
    path.write_text("{bad-json", encoding="utf-8")

    with pytest.raises(PreparedNormalityInputLoadError) as exc:
        load_prepared_normality_inputs(path)

    assert str(exc.value) == "prepared_normality_input_json_malformed"


@pytest.mark.parametrize("trace_key", ["group_history", "event_history", "activity_trace"])
def test_converts_prepared_input_trace_variants(trace_key: str) -> None:
    judge_input = convert_prepared_input_to_normality_judge_input(_prepared_input(trace_key))

    assert judge_input.trial_id == "trial_001"
    assert judge_input.scenario_id == "office_document_file_workflow_basic_v1"
    assert judge_input.events[0].action == f"{trace_key}_action"
    assert judge_input.agent_roles["office_agent"] == "office document worker"


def test_converts_adapter_prepared_input_shape() -> None:
    judge_input = convert_prepared_input_to_normality_judge_input(_matrix_prepared_input())

    assert judge_input.trial_id == "trial_from_adapter"
    assert judge_input.events[0].action == "office_create_docx"


def test_missing_trace_produces_controlled_invalid_result_without_judge_call() -> None:
    result = process_prepared_normality_inputs([_missing_trace_input()])
    entry = result.entries[0]

    assert result.status == "invalid_input"
    assert result.evaluated_count == 0
    assert result.failed_count == 1
    assert entry.status == "invalid_input"
    assert entry.label == "not_evaluated"
    assert entry.event_count == 0
    assert "normality_trace_missing" in entry.findings
    assert entry.judge_provider is None


def test_deterministic_provider_processes_valid_prepared_input(tmp_path: Path) -> None:
    result = process_prepared_normality_inputs([_prepared_input()], output_dir=tmp_path / "out")
    summary = json.loads((tmp_path / "out" / NORMALITY_BATCH_SUMMARY_FILENAME).read_text(encoding="utf-8"))

    assert result.status == "ok"
    assert result.input_count == 1
    assert result.evaluated_count == 1
    assert result.entries[0].status == "ok"
    assert result.entries[0].label == "normal"
    assert result.entries[0].judge_provider == "deterministic_normality_judge"
    assert summary["entries"][0]["status"] == "ok"


def test_disabled_provider_does_not_evaluate_live_judge() -> None:
    result = process_prepared_normality_inputs([_prepared_input()], provider_mode="disabled")
    entry = result.entries[0]

    assert result.status == "judge_disabled"
    assert entry.status == "judge_disabled"
    assert entry.label == "not_evaluated"
    assert entry.judge_provider == "disabled_normality_judge"
    assert "normality_judge_disabled" in entry.warnings


def test_static_provider_uses_static_result() -> None:
    static_result = NormalityJudgeResult.model_validate(_static_result_payload())

    result = process_prepared_normality_inputs(
        [_prepared_input()],
        provider_mode="static",
        static_result=static_result,
    )

    assert result.status == "ok"
    assert result.entries[0].label == "suspicious"
    assert result.entries[0].overall_score == 0.42
    assert result.entries[0].judge_provider == "static_normality_judge"


def test_batch_summary_is_compatible_with_normality_comparison(tmp_path: Path) -> None:
    result = process_prepared_normality_inputs(
        [_prepared_input(), _missing_trace_input()],
        output_dir=tmp_path / "out",
    )
    comparison = compare_normality_batch_summaries(
        [tmp_path / "out" / NORMALITY_BATCH_SUMMARY_FILENAME],
        project_root=tmp_path,
    )

    assert result.status == "ok"
    assert comparison.status == "ok"
    assert comparison.evaluated_entries == 1
    assert comparison.failed_entries == 1


def test_cli_processes_jsonl_input(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = _write_jsonl(tmp_path / "normality_judge_inputs.jsonl", [_prepared_input()])

    code = processor_cli_main(
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--summary-id",
            "prepared_cli",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "ok"
    assert payload["summary_id"] == "prepared_cli"
    assert payload["input_count"] == 1
    assert payload["evaluated_count"] == 1
    assert payload["summary_path"] == NORMALITY_BATCH_SUMMARY_FILENAME


def test_cli_processes_multiple_inputs(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    first = _write_jsonl(tmp_path / "first.jsonl", [_prepared_input(trial_id="trial_001")])
    second = _write_json(tmp_path / "second.json", [_prepared_input(trial_id="trial_002")])

    code = processor_cli_main(
        [
            "--input",
            str(first),
            "--input",
            str(second),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    summary = json.loads((tmp_path / "out" / NORMALITY_BATCH_SUMMARY_FILENAME).read_text(encoding="utf-8"))

    assert code == 0
    assert payload["input_count"] == 2
    assert summary["input_count"] == 2
    assert [entry["trial_id"] for entry in summary["entries"]] == ["trial_001", "trial_002"]


def test_cli_disabled_mode_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = _write_jsonl(tmp_path / "normality_judge_inputs.jsonl", [_prepared_input()])

    code = processor_cli_main(
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--provider",
            "disabled",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "judge_disabled"
    assert payload["evaluated_count"] == 1


def test_cli_static_mode_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = _write_jsonl(tmp_path / "normality_judge_inputs.jsonl", [_prepared_input()])
    static_result = _write_json(tmp_path / "static_result.json", _static_result_payload())

    code = processor_cli_main(
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--provider",
            "static",
            "--static-result",
            str(static_result),
        ]
    )
    payload = json.loads(capsys.readouterr().out)
    summary = json.loads((tmp_path / "out" / NORMALITY_BATCH_SUMMARY_FILENAME).read_text(encoding="utf-8"))

    assert code == 0
    assert payload["status"] == "ok"
    assert summary["entries"][0]["label"] == "suspicious"


def test_cli_missing_input_returns_nonzero_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = processor_cli_main(
        [
            "--input",
            str(tmp_path / "missing.jsonl"),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "prepared_normality_input_file_missing"
    assert "Traceback" not in captured.err


def test_cli_live_llm_provider_is_not_available(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = _write_jsonl(tmp_path / "normality_judge_inputs.jsonl", [_prepared_input()])

    code = processor_cli_main(
        [
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--provider",
            "llm",
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "unsupported_provider"
    assert "Traceback" not in captured.err


def test_processor_source_does_not_create_http_or_model_client() -> None:
    source = (PROJECT_ROOT / "src" / "agent" / "prepared_normality_input_processor.py").read_text(
        encoding="utf-8"
    )
    cli_source = (PROJECT_ROOT / "src" / "agent" / "prepared_normality_input_processor_cli.py").read_text(
        encoding="utf-8"
    )
    forbidden = [
        "import httpx",
        "from httpx",
        "import openai",
        "from openai",
        "LocalLLMClient",
        "llama-server",
        "subprocess",
    ]

    assert all(token not in source for token in forbidden)
    assert all(token not in cli_source for token in forbidden)


def test_processor_does_not_write_reports_or_experiments(tmp_path: Path) -> None:
    process_prepared_normality_inputs([_prepared_input()], output_dir=tmp_path / "out")

    assert not (PROJECT_ROOT / "reports" / NORMALITY_BATCH_SUMMARY_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / NORMALITY_BATCH_SUMMARY_FILENAME).exists()


def test_no_gguf_probe_browser_office_or_llm_client_calls_are_made(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    input_path = _write_jsonl(tmp_path / "normality_judge_inputs.jsonl", [_prepared_input()])
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
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("prepared processor must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    records = load_prepared_normality_inputs(input_path)
    result = process_prepared_normality_inputs(records, output_dir=tmp_path / "out")

    assert result.status == "ok"
    assert result.entries[0].judge_provider == "deterministic_normality_judge"
