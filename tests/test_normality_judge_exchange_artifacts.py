from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.normality_evaluation_cli import main
from src.agent.normality_evaluation_runner import (
    NORMALITY_EVALUATION_SUMMARY_FILENAME,
    NORMALITY_JUDGE_PROMPT_PREVIEW_FILENAME,
    NormalityEvaluationRunConfig,
    run_normality_evaluation_from_saved_llm_response,
    write_normality_judge_prompt_preview_from_file,
)
from src.agent.normality_judge import NORMALITY_DIMENSIONS


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _event(
    *,
    summary: str = "Created an offline local document artifact.",
    artifact_paths: list[str] | None = None,
) -> dict[str, object]:
    return {
        "agent_id": "office_agent",
        "role": "office document worker",
        "action": "office_create_docx",
        "status": "success",
        "summary": summary,
        "artifact_paths": artifact_paths or ["artifacts/office/summary.docx"],
    }


def _dimension(score: float | str = 0.88, rationale: str = "Plausible dimension.") -> dict[str, Any]:
    return {"score": score, "rationale": rationale, "findings": []}


def _llm_payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "label": "normal",
        "overall_score": 0.88,
        "dimension_scores": {
            name: _dimension(0.88, f"{name} is plausible.")
            for name in NORMALITY_DIMENSIONS
        },
        "findings": [],
        "redactions_applied": [],
    }
    payload.update(overrides)
    return payload


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _summary(out_dir: Path) -> dict[str, Any]:
    return json.loads((out_dir / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(encoding="utf-8"))


def _config(tmp_path: Path, **overrides: object) -> NormalityEvaluationRunConfig:
    payload = {
        "project_root": tmp_path,
        "input_path": "events.json",
        "output_dir": "out",
        "scenario_id": "office_document_file_workflow_basic_v1",
        "task_summary": "Evaluate normality of offline office workflow.",
        "max_text_chars": 80,
    }
    payload.update(overrides)
    return NormalityEvaluationRunConfig.model_validate(payload)


def _run_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    extra_args: list[str] | None = None,
) -> tuple[int, dict[str, Any], str]:
    args = [
        "--input",
        str(tmp_path / "events.json"),
        "--output-dir",
        str(tmp_path / "out"),
        "--scenario-id",
        "office_document_file_workflow_basic_v1",
        "--task-summary",
        "Evaluate normality of offline office workflow.",
    ]
    args.extend(extra_args or [])
    code = main(args)
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def test_prompt_preview_file_is_written_from_json_input(tmp_path: Path) -> None:
    _write_json(tmp_path / "events.json", [_event()])

    path, warnings = write_normality_judge_prompt_preview_from_file(_config(tmp_path))

    assert warnings == []
    assert path == tmp_path / "out" / NORMALITY_JUDGE_PROMPT_PREVIEW_FILENAME
    assert path.is_file()


def test_prompt_preview_is_redacted_and_truncated(tmp_path: Path) -> None:
    posix_path = "/home/example/outside_workspace/outside.docx"
    long_text = f"{posix_path} " + ("A" * 240)
    _write_json(tmp_path / "events.json", [_event(summary=long_text, artifact_paths=[posix_path])])

    path, _ = write_normality_judge_prompt_preview_from_file(
        _config(tmp_path, max_text_chars=40)
    )
    text = path.read_text(encoding="utf-8") if path else ""

    assert posix_path not in text
    assert "A" * 240 not in text
    assert "...[truncated]" in text


def test_prompt_preview_contains_strict_json_contract(tmp_path: Path) -> None:
    _write_json(tmp_path / "events.json", [_event()])

    path, _ = write_normality_judge_prompt_preview_from_file(_config(tmp_path))
    text = path.read_text(encoding="utf-8") if path else ""

    assert "OFFLINE_NORMALITY_JUDGE_PROMPT_PREVIEW" in text
    assert "No model was called." in text
    assert "Return strict JSON only" in text
    assert "FINAL_RESPONSE_RULE" in text


def test_prompt_preview_redacts_absolute_windows_path(tmp_path: Path) -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "outside.docx"])
    _write_json(tmp_path / "events.json", [_event(summary=windows_path, artifact_paths=[windows_path])])

    path, _ = write_normality_judge_prompt_preview_from_file(_config(tmp_path))
    text = path.read_text(encoding="utf-8") if path else ""

    assert windows_path not in text
    assert "<absolute_path>" in text


def test_prompt_preview_preserves_relative_artifact_path(tmp_path: Path) -> None:
    relative_path = "artifacts/office/summary.docx"
    _write_json(tmp_path / "events.json", [_event(artifact_paths=[relative_path])])

    path, _ = write_normality_judge_prompt_preview_from_file(_config(tmp_path))
    text = path.read_text(encoding="utf-8") if path else ""

    assert relative_path in text


def test_cli_write_prompt_preview_writes_prompt_file_and_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_json(tmp_path / "events.json", [_event()])

    code, payload, _ = _run_cli(tmp_path, capsys, extra_args=["--write-prompt-preview"])
    summary = _summary(tmp_path / "out")

    assert code == 0
    assert payload["prompt_preview_path"] == NORMALITY_JUDGE_PROMPT_PREVIEW_FILENAME
    assert summary["prompt_preview_path_relative"] == NORMALITY_JUDGE_PROMPT_PREVIEW_FILENAME
    assert (tmp_path / "out" / NORMALITY_JUDGE_PROMPT_PREVIEW_FILENAME).is_file()


def test_saved_valid_raw_llm_response_file_is_parsed_into_summary(tmp_path: Path) -> None:
    _write_json(tmp_path / "events.json", [_event()])
    response_path = _write_json(tmp_path / "raw_response.txt", _llm_payload(label="suspicious", overall_score=0.66))

    result = run_normality_evaluation_from_saved_llm_response(
        _config(tmp_path, judge_provider="llm"),
        response_path,
    )
    summary = _summary(tmp_path / "out")

    assert result.status == "ok"
    assert summary["label"] == "suspicious"
    assert summary["overall_score"] == 0.66
    assert summary["dimension_scores"]["overall_normality"]["score"] == 0.88


def test_saved_response_summary_metadata_model_not_called(tmp_path: Path) -> None:
    _write_json(tmp_path / "events.json", [_event()])
    response_path = _write_json(tmp_path / "raw_response.txt", _llm_payload())

    run_normality_evaluation_from_saved_llm_response(_config(tmp_path, judge_provider="llm"), response_path)
    summary = _summary(tmp_path / "out")

    assert summary["judge_provider"] == "llm"
    assert summary["judge_mode"] == "llm_saved_response"
    assert summary["model_called"] is False
    assert summary["raw_response_path_relative"] == "raw_response.txt"


def test_cli_llm_without_raw_response_is_not_configured(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_json(tmp_path / "events.json", [_event()])

    code, payload, _ = _run_cli(tmp_path, capsys, extra_args=["--judge-provider", "llm"])

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["judge_provider"] == "llm_normality_judge_placeholder"
    assert payload["model_called"] is False


def test_missing_raw_response_file_returns_nonzero_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_json(tmp_path / "events.json", [_event()])

    code, payload, stderr = _run_cli(
        tmp_path,
        capsys,
        extra_args=["--judge-provider", "llm", "--raw-judge-response", str(tmp_path / "missing.txt")],
    )

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert "Traceback" not in stderr


def test_invalid_raw_response_json_returns_nonzero_controlled_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_json(tmp_path / "events.json", [_event()])
    raw_path = tmp_path / "raw_response.txt"
    raw_path.write_text("{not json", encoding="utf-8")

    code, payload, stderr = _run_cli(
        tmp_path,
        capsys,
        extra_args=["--judge-provider", "llm", "--raw-judge-response", str(raw_path)],
    )
    summary = _summary(tmp_path / "out")

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert summary["findings"] == ["llm_judge_parse_failed"]
    assert "Traceback" not in stderr


def test_raw_response_overlong_rationale_is_truncated_and_redacted(tmp_path: Path) -> None:
    _write_json(tmp_path / "events.json", [_event()])
    posix_path = "/home/example/outside_workspace/outside.docx"
    payload = _llm_payload()
    payload["dimension_scores"]["task_relevance"]["rationale"] = f"{posix_path} " + ("B" * 240)
    response_path = _write_json(tmp_path / "raw_response.txt", payload)

    run_normality_evaluation_from_saved_llm_response(
        _config(tmp_path, judge_provider="llm", max_text_chars=50),
        response_path,
    )
    summary_text = (tmp_path / "out" / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )

    assert posix_path not in summary_text
    assert "B" * 240 not in summary_text
    assert "...[truncated]" in summary_text


def test_no_http_client_or_model_call_is_created(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = __import__

    def forbidden_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright"}:
            raise AssertionError("exchange artifact path must not import runtime clients")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", forbidden_import)
    _write_json(tmp_path / "events.json", [_event()])
    response_path = _write_json(tmp_path / "raw_response.txt", _llm_payload())

    code, payload, _ = _run_cli(
        tmp_path,
        capsys,
        extra_args=["--judge-provider", "llm", "--raw-judge-response", str(response_path)],
    )

    assert code == 0
    assert payload["model_called"] is False


def test_no_reports_or_experiments_files_are_written(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_json(tmp_path / "events.json", [_event()])

    code, _, _ = _run_cli(tmp_path, capsys, extra_args=["--write-prompt-preview"])

    assert code == 0
    assert not (PROJECT_ROOT / "reports" / NORMALITY_EVALUATION_SUMMARY_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / NORMALITY_EVALUATION_SUMMARY_FILENAME).exists()
    assert not (PROJECT_ROOT / "reports" / NORMALITY_JUDGE_PROMPT_PREVIEW_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / NORMALITY_JUDGE_PROMPT_PREVIEW_FILENAME).exists()
