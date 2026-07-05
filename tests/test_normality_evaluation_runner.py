from __future__ import annotations

import json
from pathlib import Path

from src.agent.normality_evaluation_runner import (
    NORMALITY_EVALUATION_SUMMARY_FILENAME,
    NormalityEvaluationRunConfig,
    load_normality_events_from_file,
    run_normality_evaluation_from_file,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )
    return path


def _event(
    action: str = "office_create_docx",
    *,
    agent_id: str = "office_agent",
    role: str = "office document worker",
    status: str = "success",
    summary: str = "Created an offline local document artifact.",
    artifact_paths: list[str] | None = None,
) -> dict[str, object]:
    return {
        "agent_id": agent_id,
        "role": role,
        "action": action,
        "status": status,
        "summary": summary,
        "artifact_paths": artifact_paths or ["artifacts/office/report.docx"],
    }


def _config(tmp_path: Path, **overrides: object) -> NormalityEvaluationRunConfig:
    payload = {
        "project_root": tmp_path,
        "input_path": "events.json",
        "output_dir": "out",
        "scenario_id": "office_document_file_workflow_basic_v1",
        "task_summary": "Evaluate offline normal office document activity.",
        "max_text_chars": 80,
    }
    payload.update(overrides)
    return NormalityEvaluationRunConfig.model_validate(payload)


def test_load_json_list_events(tmp_path: Path) -> None:
    path = _write_json(tmp_path / "events.json", [_event()])

    result = load_normality_events_from_file(path, project_root=tmp_path)

    assert result.status == "ok"
    assert result.input_path_relative == "events.json"
    assert result.records[0]["action"] == "office_create_docx"


def test_load_json_dict_group_history(tmp_path: Path) -> None:
    path = _write_json(
        tmp_path / "history.json",
        {
            "scenario_id": "offline_group_scenario",
            "agent_roles": {"office_agent": "office document worker"},
            "group_history": [_event()],
        },
    )

    result = load_normality_events_from_file(path, project_root=tmp_path)

    assert result.status == "ok"
    assert result.payload_metadata["scenario_id"] == "offline_group_scenario"
    assert result.records[0]["agent_id"] == "office_agent"


def test_load_jsonl_events(tmp_path: Path) -> None:
    path = _write_jsonl(tmp_path / "events.jsonl", [_event(), _event("office_append_docx_section")])

    result = load_normality_events_from_file(path, project_root=tmp_path)

    assert result.status == "ok"
    assert result.input_path_relative == "events.jsonl"
    assert [row["action"] for row in result.records] == [
        "office_create_docx",
        "office_append_docx_section",
    ]


def test_missing_input_returns_controlled_status(tmp_path: Path) -> None:
    result = run_normality_evaluation_from_file(
        _config(tmp_path, input_path="missing.json", output_dir="out")
    )

    assert result.status == "input_missing"
    assert result.warnings == ["input_file_missing"]


def test_malformed_json_returns_invalid_input(tmp_path: Path) -> None:
    (tmp_path / "events.json").write_text("{not json", encoding="utf-8")

    result = run_normality_evaluation_from_file(_config(tmp_path))

    assert result.status == "invalid_input"
    assert "json_decode_error" in result.warnings


def test_runner_evaluates_valid_events_and_writes_summary(tmp_path: Path) -> None:
    _write_json(tmp_path / "events.json", [_event(), _event("office_append_docx_section")])

    result = run_normality_evaluation_from_file(_config(tmp_path))
    summary_path = tmp_path / "out" / NORMALITY_EVALUATION_SUMMARY_FILENAME
    summary = json.loads(summary_path.read_text(encoding="utf-8"))

    assert result.status == "ok"
    assert result.event_count == 2
    assert result.label == "normal"
    assert result.overall_score is not None
    assert "overall_normality" in result.dimension_scores
    assert summary["status"] == "ok"
    assert summary["label"] == "normal"
    assert summary["summary_path_relative"] == "out/normality_judge_summary.json"


def test_summary_redacts_absolute_windows_path(tmp_path: Path) -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "outside.docx"])
    _write_json(
        tmp_path / "events.json",
        [
            _event(
                summary=f"Attempted to touch {windows_path}",
                artifact_paths=[windows_path],
            )
        ],
    )

    result = run_normality_evaluation_from_file(_config(tmp_path, max_text_chars=120))
    summary_text = (tmp_path / "out" / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )

    assert windows_path not in summary_text
    assert "absolute_path" in result.redactions_applied
    assert result.event_preview[0]["artifact_paths"] == ["<absolute_path>"]


def test_summary_redacts_absolute_posix_path(tmp_path: Path) -> None:
    posix_path = "/home/example/outside_workspace/outside.docx"
    _write_json(
        tmp_path / "events.json",
        [_event(summary=f"Attempted to touch {posix_path}", artifact_paths=[posix_path])],
    )

    result = run_normality_evaluation_from_file(_config(tmp_path))
    summary_text = (tmp_path / "out" / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )

    assert posix_path not in summary_text
    assert "absolute_path" in result.redactions_applied
    assert result.event_preview[0]["artifact_paths"] == ["<absolute_path>"]


def test_relative_artifact_path_is_preserved_in_preview(tmp_path: Path) -> None:
    relative_path = "artifacts/office/report.docx"
    _write_json(tmp_path / "events.json", [_event(artifact_paths=[relative_path])])

    result = run_normality_evaluation_from_file(_config(tmp_path))

    assert result.event_preview[0]["artifact_paths"] == [relative_path]


def test_long_text_is_truncated_and_raw_full_output_is_not_written(tmp_path: Path) -> None:
    long_text = "A" * 240
    _write_json(tmp_path / "events.json", [_event(summary=long_text)])

    run_normality_evaluation_from_file(_config(tmp_path, max_text_chars=40))
    summary_text = (tmp_path / "out" / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )

    assert long_text not in summary_text
    assert "...[truncated]" in summary_text


def test_disabled_judge_returns_controlled_status(tmp_path: Path) -> None:
    _write_json(tmp_path / "events.json", [_event()])

    result = run_normality_evaluation_from_file(
        _config(tmp_path, judge_enabled=False, output_dir="out")
    )

    assert result.status == "judge_disabled"
    assert result.label == "not_evaluated"
    assert result.event_count == 0
    assert "normality_judge_disabled" in result.warnings


def test_repeated_errors_score_lower_than_successful_activity(tmp_path: Path) -> None:
    clean_path = tmp_path / "clean.json"
    error_path = tmp_path / "errors.json"
    _write_json(clean_path, [_event(), _event("office_append_docx_section")])
    _write_json(
        error_path,
        [
            {
                **_event(status="failure"),
                "error_code": "execution_failed",
                "summary": "Execution failed.",
            }
            for _ in range(3)
        ],
    )

    clean = run_normality_evaluation_from_file(_config(tmp_path, input_path="clean.json", output_dir="clean_out"))
    errors = run_normality_evaluation_from_file(_config(tmp_path, input_path="errors.json", output_dir="error_out"))

    assert clean.overall_score is not None
    assert errors.overall_score is not None
    assert errors.overall_score < clean.overall_score
    assert "execution_errors_present" in errors.findings


def test_runner_source_does_not_import_runtime_backends() -> None:
    source = (PROJECT_ROOT / "src" / "agent" / "normality_evaluation_runner.py").read_text(
        encoding="utf-8"
    )

    forbidden_imports = [
        "httpx",
        "LocalLLMClient",
        "playwright",
        "subprocess",
        "docx",
        "openpyxl",
        "pptx",
        "llama",
    ]
    assert all(name not in source for name in forbidden_imports)
