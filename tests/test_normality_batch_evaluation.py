from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.normality_evaluation_cli import main
from src.agent.normality_evaluation_runner import (
    NORMALITY_BATCH_SUMMARY_FILENAME,
    NormalityEvaluationRunConfig,
    run_batch_normality_evaluation,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _event(
    action: str = "office_create_docx",
    *,
    agent_id: str = "office_agent",
    role: str = "office document worker",
    status: str = "success",
    summary: str = "Created an offline local document artifact.",
    artifact_paths: list[str] | None = None,
    extra: dict[str, object] | None = None,
) -> dict[str, object]:
    payload: dict[str, object] = {
        "agent_id": agent_id,
        "role": role,
        "action": action,
        "status": status,
        "summary": summary,
        "artifact_paths": artifact_paths or ["artifacts/office/report.docx"],
    }
    payload.update(extra or {})
    return payload


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )
    return path


def _config(tmp_path: Path, **overrides: object) -> NormalityEvaluationRunConfig:
    payload = {
        "project_root": tmp_path,
        "output_dir": "out",
        "scenario_id": "office_document_file_workflow_basic_v1",
        "task_summary": "Evaluate offline normal office document activity.",
        "max_text_chars": 80,
    }
    payload.update(overrides)
    return NormalityEvaluationRunConfig.model_validate(payload)


def _batch_summary(out_dir: Path) -> dict[str, Any]:
    return json.loads((out_dir / NORMALITY_BATCH_SUMMARY_FILENAME).read_text(encoding="utf-8"))


def _run_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    inputs: list[Path],
    output_dir: Path | None = None,
    extra_args: list[str] | None = None,
) -> tuple[int, dict[str, Any], str]:
    args: list[str] = []
    for input_path in inputs:
        args.extend(["--input", str(input_path)])
    args.extend(
        [
            "--output-dir",
            str(output_dir or tmp_path / "out"),
            "--scenario-id",
            "office_document_file_workflow_basic_v1",
            "--task-summary",
            "Evaluate normality of offline office workflow.",
        ]
    )
    args.extend(extra_args or [])
    code = main(args)
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def test_batch_runner_evaluates_two_json_and_jsonl_inputs(tmp_path: Path) -> None:
    first = _write_json(tmp_path / "first.json", [_event()])
    second = _write_jsonl(tmp_path / "second.jsonl", [_event("office_append_docx_section")])

    result = run_batch_normality_evaluation(_config(tmp_path), [first, second])

    assert result.status == "ok"
    assert result.input_count == 2
    assert result.evaluated_count == 2
    assert result.failed_count == 0
    assert [entry.status for entry in result.entries] == ["ok", "ok"]


def test_batch_summary_json_is_written(tmp_path: Path) -> None:
    first = _write_json(tmp_path / "first.json", [_event()])
    second = _write_jsonl(tmp_path / "second.jsonl", [_event()])

    result = run_batch_normality_evaluation(_config(tmp_path), [first, second])
    summary = _batch_summary(tmp_path / "out")

    assert result.batch_summary_path_relative == "out/normality_judge_batch_summary.json"
    assert summary["status"] == "ok"
    assert summary["input_count"] == 2
    assert len(summary["entries"]) == 2


def test_batch_aggregation_counts_scores_labels_and_statuses(tmp_path: Path) -> None:
    first = _write_json(tmp_path / "first.json", [_event()])
    second = _write_json(tmp_path / "second.json", [_event("office_append_docx_section")])

    result = run_batch_normality_evaluation(_config(tmp_path), [first, second])
    scores = [entry.overall_score for entry in result.entries if entry.overall_score is not None]

    assert result.aggregation["count"] == 2
    assert result.aggregation["mean_overall_score"] == pytest.approx(sum(scores) / len(scores))
    assert result.aggregation["label_counts"] == {"normal": 2}
    assert result.aggregation["status_counts"] == {"ok": 2}


def test_one_malformed_input_does_not_abort_batch(tmp_path: Path) -> None:
    valid = _write_json(tmp_path / "valid.json", [_event()])
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not json", encoding="utf-8")

    result = run_batch_normality_evaluation(_config(tmp_path), [valid, malformed])

    assert result.status == "ok"
    assert result.evaluated_count == 1
    assert result.failed_count == 1
    assert result.aggregation["status_counts"] == {"ok": 1, "invalid_input": 1}
    assert result.entries[1].warnings == ["json_decode_error"]


def test_missing_input_is_recorded_as_failed_entry(tmp_path: Path) -> None:
    valid = _write_json(tmp_path / "valid.json", [_event()])
    missing = tmp_path / "missing.json"

    result = run_batch_normality_evaluation(_config(tmp_path), [valid, missing])

    assert result.status == "ok"
    assert result.failed_count == 1
    assert result.entries[1].status == "input_missing"
    assert result.aggregation["status_counts"] == {"ok": 1, "input_missing": 1}


def test_all_invalid_inputs_return_controlled_non_ok_status(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    malformed = tmp_path / "malformed.json"
    malformed.write_text("{not json", encoding="utf-8")
    missing = tmp_path / "missing.json"

    code, payload, stderr = _run_cli(tmp_path, capsys, inputs=[malformed, missing])
    summary = _batch_summary(tmp_path / "out")

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert summary["status"] == "invalid_input"
    assert summary["evaluated_count"] == 0
    assert "Traceback" not in stderr


def test_cli_repeated_input_triggers_batch_mode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = _write_json(tmp_path / "first.json", [_event()])
    second = _write_json(tmp_path / "second.json", [_event()])

    code, payload, _ = _run_cli(tmp_path, capsys, inputs=[first, second])

    assert code == 0
    assert payload["status"] == "ok"
    assert payload["input_count"] == 2
    assert payload["batch_summary_path"] == NORMALITY_BATCH_SUMMARY_FILENAME


def test_single_input_cli_behavior_remains_compatible(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = _write_json(tmp_path / "first.json", [_event()])

    code, payload, _ = _run_cli(tmp_path, capsys, inputs=[first])

    assert code == 0
    assert set(payload) == {
        "event_count",
        "judge_provider",
        "label",
        "overall_score",
        "model_called",
        "prompt_preview_path",
        "status",
        "summary_path",
    }


def test_batch_stdout_is_concise_json_with_aggregate_fields(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = _write_json(tmp_path / "first.json", [_event()])
    second = _write_json(tmp_path / "second.json", [_event()])

    code, payload, _ = _run_cli(tmp_path, capsys, inputs=[first, second])

    assert code == 0
    assert set(payload) == {
        "batch_id",
        "batch_summary_path",
        "evaluated_count",
        "failed_count",
        "input_count",
        "judge_provider",
        "label_counts",
        "mean_overall_score",
        "status",
    }
    assert payload["label_counts"] == {"normal": 2}


def test_absolute_windows_path_in_input_is_redacted_in_batch_summary(tmp_path: Path) -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "outside.docx"])
    input_path = _write_json(
        tmp_path / "events.json",
        [_event(summary=f"Attempted {windows_path}", artifact_paths=[windows_path])],
    )

    run_batch_normality_evaluation(_config(tmp_path, max_text_chars=120), [input_path])
    summary_text = (tmp_path / "out" / NORMALITY_BATCH_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )
    summary = _batch_summary(tmp_path / "out")

    assert windows_path not in summary_text
    assert summary["entries"][0]["event_preview"][0]["artifact_paths"] == ["<absolute_path>"]
    assert "absolute_path" in summary["entries"][0]["redactions_applied"]


def test_absolute_posix_path_in_input_is_redacted_in_batch_summary(tmp_path: Path) -> None:
    posix_path = "/home/example/outside_workspace/outside.docx"
    input_path = _write_json(
        tmp_path / "events.json",
        [_event(summary=f"Attempted {posix_path}", artifact_paths=[posix_path])],
    )

    run_batch_normality_evaluation(_config(tmp_path), [input_path])
    summary_text = (tmp_path / "out" / NORMALITY_BATCH_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )
    summary = _batch_summary(tmp_path / "out")

    assert posix_path not in summary_text
    assert summary["entries"][0]["event_preview"][0]["artifact_paths"] == ["<absolute_path>"]


def test_relative_artifact_paths_are_preserved_in_batch_summary(tmp_path: Path) -> None:
    relative_path = "artifacts/office/summary.docx"
    input_path = _write_json(tmp_path / "events.json", [_event(artifact_paths=[relative_path])])

    run_batch_normality_evaluation(_config(tmp_path), [input_path])
    summary = _batch_summary(tmp_path / "out")

    assert summary["entries"][0]["event_preview"][0]["artifact_paths"] == [relative_path]


def test_long_raw_text_is_truncated_in_batch_summary(tmp_path: Path) -> None:
    long_text = "A" * 300
    input_path = _write_json(tmp_path / "events.json", [_event(summary=long_text)])

    run_batch_normality_evaluation(_config(tmp_path, max_text_chars=40), [input_path])
    summary_text = (tmp_path / "out" / NORMALITY_BATCH_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )
    summary = _batch_summary(tmp_path / "out")

    assert long_text not in summary_text
    assert "...[truncated]" in summary_text
    assert "truncated_text" in summary["entries"][0]["redactions_applied"]


def test_batch_summary_does_not_write_raw_full_events_by_default(tmp_path: Path) -> None:
    raw_marker = "RAW_FULL_EVENT_MARKER_SHOULD_NOT_APPEAR"
    input_path = _write_json(
        tmp_path / "events.json",
        [_event(extra={"raw_payload": raw_marker})],
    )

    run_batch_normality_evaluation(_config(tmp_path), [input_path])
    summary_text = (tmp_path / "out" / NORMALITY_BATCH_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )

    assert raw_marker not in summary_text


def test_batch_does_not_write_reports_or_experiments(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    first = _write_json(tmp_path / "first.json", [_event()])
    second = _write_json(tmp_path / "second.json", [_event()])

    code, _, _ = _run_cli(tmp_path, capsys, inputs=[first, second])

    assert code == 0
    assert not (PROJECT_ROOT / "reports" / NORMALITY_BATCH_SUMMARY_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / NORMALITY_BATCH_SUMMARY_FILENAME).exists()


def test_batch_does_not_create_http_model_browser_or_office_clients(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = __import__

    def forbidden_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("batch evaluation must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", forbidden_import)
    first = _write_json(tmp_path / "first.json", [_event()])
    second = _write_json(tmp_path / "second.json", [_event()])

    code, payload, _ = _run_cli(tmp_path, capsys, inputs=[first, second])

    assert code == 0
    assert payload["status"] == "ok"


def test_batch_source_does_not_import_runtime_backends() -> None:
    runner_source = (PROJECT_ROOT / "src" / "agent" / "normality_evaluation_runner.py").read_text(
        encoding="utf-8"
    )
    cli_source = (PROJECT_ROOT / "src" / "agent" / "normality_evaluation_cli.py").read_text(
        encoding="utf-8"
    )
    forbidden_tokens = [
        "import httpx",
        "from httpx",
        "LocalLLMClient",
        "import playwright",
        "from playwright",
        "import subprocess",
        "import docx",
        "from docx",
        "import openpyxl",
        "from openpyxl",
        "import pptx",
        "from pptx",
        "llama-server",
    ]

    assert all(token not in runner_source for token in forbidden_tokens)
    assert all(token not in cli_source for token in forbidden_tokens)
