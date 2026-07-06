from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.normality_comparison import compare_normality_batch_summaries
from src.agent.normality_evaluation_runner import NORMALITY_BATCH_SUMMARY_FILENAME
from src.agent.normality_judge import NORMALITY_DIMENSIONS
from src.agent.prepared_normality_judge_exchange import (
    NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME,
    NORMALITY_JUDGE_PROMPT_PACK_SUMMARY_FILENAME,
    PreparedNormalityJudgeExchangeError,
    build_normality_batch_summary_from_raw_responses,
    build_prepared_normality_judge_prompt_pack,
    load_exchange_prepared_normality_inputs,
    load_normality_judge_raw_responses,
    load_prepared_normality_judge_prompt_pack,
    write_prepared_normality_judge_prompt_pack,
)
from src.agent.prepared_normality_judge_exchange_cli import main as exchange_cli_main


PROJECT_ROOT = Path(__file__).resolve().parents[1]
RAW_RESPONSE_MARKER = "RAW_FULL_RESPONSE_MARKER_SHOULD_NOT_COPY"


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
        "model_pair": {"orchestrator": "second_model", "executor": "first_model"},
        "task_summary": "Evaluate prepared offline office activity.",
        "events": [_event()],
        "tags": ["exchange_test"],
        "metadata": {"source_run_id": "matrix_run_001", "no_runtime_execution": True},
        "warnings": [],
        "no_runtime_execution": True,
    }
    if trace_key != "events":
        payload[trace_key] = [_event(action=f"{trace_key}_action")]
        payload["events"] = payload[trace_key]
    payload.update(overrides)
    return payload


def _missing_trace_input(**overrides: object) -> dict[str, Any]:
    payload = _prepared_input(
        events=[],
        adapter_status="invalid_input",
        warnings=["normality_trace_missing"],
    )
    payload.update(overrides)
    return payload


def _dimension(score: float = 0.89) -> dict[str, Any]:
    return {"score": score, "rationale": "Plausible offline activity.", "findings": []}


def _judge_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "label": "normal",
        "overall_score": 0.89,
        "dimension_scores": {name: _dimension() for name in NORMALITY_DIMENSIONS},
        "findings": [],
        "redactions_applied": [],
        "ignored_raw_field": RAW_RESPONSE_MARKER,
    }
    payload.update(overrides)
    return payload


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


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def _response_for_prompt(prompt: dict[str, Any], **overrides: object) -> dict[str, Any]:
    payload = {
        "prompt_id": prompt["prompt_id"],
        "trial_id": prompt["trial_id"],
        "raw_response": json.dumps(_judge_payload(), ensure_ascii=False),
    }
    payload.update(overrides)
    return payload


def test_export_prompts_from_prepared_jsonl_valid_trace(tmp_path: Path) -> None:
    input_path = _write_jsonl(tmp_path / "normality_judge_inputs.jsonl", [_prepared_input()])
    prepared_inputs = _jsonl_rows(input_path)

    pack = build_prepared_normality_judge_prompt_pack(prepared_inputs, pack_id="exchange_pack")

    assert pack["schema_version"] == "prepared_normality_judge_prompt_pack_v1"
    assert pack["pack_id"] == "exchange_pack"
    assert pack["input_count"] == 1
    assert pack["prompt_count"] == 1
    assert pack["prompts"][0]["status"] == "ok"
    assert "NORMALITY_JUDGE_PROMPT_CONTRACT" in pack["prompts"][0]["prompt"]


@pytest.mark.parametrize("shape", ["list", "inputs", "normality_inputs", "records"])
def test_export_prompts_from_json_list_and_dict_inputs(tmp_path: Path, shape: str) -> None:
    payload: object = [_prepared_input()]
    if shape != "list":
        payload = {shape: [_prepared_input()]}
    path = _write_json(tmp_path / f"{shape}.json", payload)

    pack = build_prepared_normality_judge_prompt_pack(load_exchange_prepared_normality_inputs([path]))

    assert pack["prompt_count"] == 1
    assert pack["prompts"][0]["trial_id"] == "trial_001"


def test_missing_trace_is_marked_skipped_without_fake_events() -> None:
    pack = build_prepared_normality_judge_prompt_pack([_missing_trace_input()])
    item = pack["prompts"][0]

    assert pack["prompt_count"] == 0
    assert pack["skipped_count"] == 1
    assert item["status"] == "skipped"
    assert item["prompt"] is None
    assert "normality_trace_missing" in item["warnings"]


def test_prompt_pack_contains_identity_and_pair_metadata() -> None:
    item = build_prepared_normality_judge_prompt_pack([_prepared_input()])["prompts"][0]

    assert item["trial_id"] == "trial_001"
    assert item["scenario_id"] == "office_document_file_workflow_basic_v1"
    assert item["pair_id"] == "second_model__to__first_model"
    assert item["model_pair"] == {"executor": "first_model", "orchestrator": "second_model"}
    assert item["metadata"]["event_count"] == 1


def test_prompt_text_has_contract_dimensions_and_no_absolute_paths() -> None:
    posix_path = "/home/example/outside_workspace/report.docx"
    pack = build_prepared_normality_judge_prompt_pack(
        [_prepared_input(group_history=[_event(summary=f"Opened {posix_path}", artifact_paths=[posix_path])])]
    )
    prompt = pack["prompts"][0]["prompt"]

    assert "OUTPUT_JSON_CONTRACT" in prompt
    assert "FINAL_RESPONSE_RULE" in prompt
    assert all(name in prompt for name in NORMALITY_DIMENSIONS)
    assert posix_path not in prompt


def test_prompt_pack_writer_creates_jsonl_and_summary(tmp_path: Path) -> None:
    pack = build_prepared_normality_judge_prompt_pack([_prepared_input()], pack_id="writer_pack")

    prompt_path, summary_path = write_prepared_normality_judge_prompt_pack(pack, tmp_path / "out")
    prompt_rows = _jsonl_rows(prompt_path)
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert prompt_path.name == NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME
    assert summary_path.name == NORMALITY_JUDGE_PROMPT_PACK_SUMMARY_FILENAME
    assert prompt_rows[0]["prompt_id"] == "writer_pack__trial_001"
    assert "prompt" not in summary["prompts"][0]
    assert summary["prompt_count"] == 1


def test_raw_responses_jsonl_load_works(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "normality_judge_raw_responses.jsonl", [{"prompt_id": "p1", "raw_response": "{}"}])

    rows = load_normality_judge_raw_responses(path)

    assert rows == [{"prompt_id": "p1", "raw_response": "{}"}]


@pytest.mark.parametrize("shape", ["list", "responses", "raw_responses", "records"])
def test_raw_responses_json_list_and_dict_load_work(tmp_path: Path, shape: str) -> None:
    rows = [{"prompt_id": "p1", "raw_response": json.dumps(_judge_payload())}]
    payload: object = rows if shape == "list" else {shape: rows}
    path = _write_json(tmp_path / f"{shape}.json", payload)

    loaded = load_normality_judge_raw_responses(path)

    assert loaded[0]["prompt_id"] == "p1"


def test_import_valid_raw_response_creates_batch_summary(tmp_path: Path) -> None:
    pack = build_prepared_normality_judge_prompt_pack([_prepared_input()], pack_id="import_pack")
    response = _response_for_prompt(pack["prompts"][0])

    result = build_normality_batch_summary_from_raw_responses(
        pack,
        [response],
        summary_id="normality_import",
        output_dir=tmp_path / "out",
    )
    summary = json.loads((tmp_path / "out" / NORMALITY_BATCH_SUMMARY_FILENAME).read_text(encoding="utf-8"))

    assert result.status == "ok"
    assert result.evaluated_count == 1
    assert result.entries[0].label == "normal"
    assert summary["batch_id"] == "normality_import"
    assert summary["entries"][0]["judge_mode"] == "llm_saved_response"


def test_fenced_json_raw_response_parses() -> None:
    pack = build_prepared_normality_judge_prompt_pack([_prepared_input()])
    raw = "```json\n" + json.dumps(_judge_payload(label="suspicious")) + "\n```"

    result = build_normality_batch_summary_from_raw_responses(
        pack,
        [_response_for_prompt(pack["prompts"][0], raw_response=raw)],
    )

    assert result.status == "ok"
    assert result.entries[0].label == "suspicious"


def test_malformed_raw_response_becomes_controlled_invalid_result() -> None:
    pack = build_prepared_normality_judge_prompt_pack([_prepared_input()])

    result = build_normality_batch_summary_from_raw_responses(
        pack,
        [_response_for_prompt(pack["prompts"][0], raw_response="{bad-json")],
    )
    entry = result.entries[0]

    assert result.status == "invalid_input"
    assert entry.status == "invalid_input"
    assert entry.label == "not_evaluated"
    assert entry.findings == ["llm_judge_parse_failed"]


def test_missing_response_for_prompt_is_controlled_invalid() -> None:
    pack = build_prepared_normality_judge_prompt_pack([_prepared_input()])

    result = build_normality_batch_summary_from_raw_responses(pack, [])
    entry = result.entries[0]

    assert result.status == "invalid_input"
    assert entry.status == "invalid_input"
    assert "judge_response_missing" in entry.warnings
    assert "judge_response_missing" in entry.findings


def test_unknown_prompt_id_response_creates_warning_not_crash() -> None:
    pack = build_prepared_normality_judge_prompt_pack([_prepared_input()])

    result = build_normality_batch_summary_from_raw_responses(
        pack,
        [
            _response_for_prompt(pack["prompts"][0]),
            {"prompt_id": "unknown_prompt", "raw_response": json.dumps(_judge_payload())},
        ],
    )

    assert result.status == "ok"
    assert "unknown_prompt_response:unknown_prompt" in result.warnings


def test_batch_summary_is_compatible_with_normality_comparison(tmp_path: Path) -> None:
    pack = build_prepared_normality_judge_prompt_pack([_prepared_input(), _missing_trace_input()])
    result = build_normality_batch_summary_from_raw_responses(
        pack,
        [_response_for_prompt(pack["prompts"][0])],
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


def test_cli_export_prompts_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = _write_jsonl(tmp_path / "normality_judge_inputs.jsonl", [_prepared_input()])

    code = exchange_cli_main(
        [
            "export-prompts",
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--pack-id",
            "cli_pack",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "ok"
    assert payload["pack_id"] == "cli_pack"
    assert payload["prompt_count"] == 1
    assert payload["prompt_pack_path"] == NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME
    assert (tmp_path / "out" / NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME).is_file()
    assert (tmp_path / "out" / NORMALITY_JUDGE_PROMPT_PACK_SUMMARY_FILENAME).is_file()


def test_cli_import_responses_works(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    pack = build_prepared_normality_judge_prompt_pack([_prepared_input()], pack_id="cli_import_pack")
    prompt_pack_path, _ = write_prepared_normality_judge_prompt_pack(pack, tmp_path / "pack")
    responses_path = _write_jsonl(
        tmp_path / "responses.jsonl",
        [_response_for_prompt(pack["prompts"][0])],
    )

    code = exchange_cli_main(
        [
            "import-responses",
            "--prompt-pack",
            str(prompt_pack_path),
            "--raw-responses",
            str(responses_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--summary-id",
            "cli_summary",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "ok"
    assert payload["summary_id"] == "cli_summary"
    assert payload["response_count"] == 1
    assert payload["evaluated_count"] == 1
    assert payload["summary_path"] == NORMALITY_BATCH_SUMMARY_FILENAME


def test_cli_missing_input_returns_nonzero_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = exchange_cli_main(
        [
            "export-prompts",
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


def test_cli_has_no_live_llm_or_http_provider_flags() -> None:
    from src.agent.prepared_normality_judge_exchange_cli import build_parser

    help_text = build_parser().format_help()

    assert "--provider" not in help_text
    assert "http" not in help_text.lower()


def test_raw_full_response_is_not_copied_into_summary(tmp_path: Path) -> None:
    pack = build_prepared_normality_judge_prompt_pack([_prepared_input()])
    raw_response = json.dumps(_judge_payload(), ensure_ascii=False)

    build_normality_batch_summary_from_raw_responses(
        pack,
        [_response_for_prompt(pack["prompts"][0], raw_response=raw_response)],
        output_dir=tmp_path / "out",
    )
    summary_text = (tmp_path / "out" / NORMALITY_BATCH_SUMMARY_FILENAME).read_text(encoding="utf-8")

    assert RAW_RESPONSE_MARKER not in summary_text
    assert "raw_response" not in summary_text


def test_no_reports_or_experiments_files_are_written(tmp_path: Path) -> None:
    pack = build_prepared_normality_judge_prompt_pack([_prepared_input()])
    write_prepared_normality_judge_prompt_pack(pack, tmp_path / "out")
    build_normality_batch_summary_from_raw_responses(
        pack,
        [_response_for_prompt(pack["prompts"][0])],
        output_dir=tmp_path / "out",
    )

    assert not (PROJECT_ROOT / "reports" / NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / NORMALITY_JUDGE_PROMPT_PACK_JSONL_FILENAME).exists()
    assert not (PROJECT_ROOT / "reports" / NORMALITY_BATCH_SUMMARY_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / NORMALITY_BATCH_SUMMARY_FILENAME).exists()


def test_no_models_gguf_probes_browser_office_llm_or_http_clients_are_launched(
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
            raise AssertionError("exchange must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    code = exchange_cli_main(
        [
            "export-prompts",
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )

    assert code == 0


def test_prompt_pack_summary_contract_payload_shape() -> None:
    pack = build_prepared_normality_judge_prompt_pack([_prepared_input()], pack_id="contract_pack")
    summary = json.loads(
        json.dumps(
            {
                "schema_version": pack["schema_version"],
                "pack_id": pack["pack_id"],
                "input_count": pack["input_count"],
                "prompt_count": pack["prompt_count"],
                "skipped_count": pack["skipped_count"],
                "prompts": [
                    {
                        "prompt_id": pack["prompts"][0]["prompt_id"],
                        "trial_id": pack["prompts"][0]["trial_id"],
                        "status": pack["prompts"][0]["status"],
                        "warning_count": 0,
                        "prompt_char_count": len(pack["prompts"][0]["prompt"]),
                    }
                ],
                "warnings": [],
                "notes": pack["notes"],
                "no_runtime_execution": True,
            },
            ensure_ascii=False,
        )
    )

    assert summary["schema_version"] == "prepared_normality_judge_prompt_pack_v1"
    assert "prompt" not in summary["prompts"][0]
