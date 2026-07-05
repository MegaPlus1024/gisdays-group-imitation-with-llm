from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent.normality_evaluation_cli import main
from src.agent.normality_evaluation_runner import NORMALITY_EVALUATION_SUMMARY_FILENAME


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


def _write_json(path: Path, payload: object) -> Path:
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> Path:
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )
    return path


def _run_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    *,
    input_path: Path | None = None,
    output_dir: Path | None = None,
    extra_args: list[str] | None = None,
) -> tuple[int, dict[str, object], str]:
    args = [
        "--input",
        str(input_path or tmp_path / "events.json"),
        "--output-dir",
        str(output_dir or tmp_path / "out"),
        "--scenario-id",
        "office_document_file_workflow_basic_v1",
        "--task-summary",
        "Evaluate normality of offline office workflow.",
    ]
    args.extend(extra_args or [])
    code = main(args)
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def _summary(out_dir: Path) -> dict[str, object]:
    return json.loads((out_dir / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(encoding="utf-8"))


def test_cli_evaluates_json_input_and_writes_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_json(tmp_path / "events.json", [_event()])

    code, payload, stderr = _run_cli(tmp_path, capsys)

    assert code == 0
    assert stderr == ""
    assert payload["status"] == "ok"
    assert payload["label"] == "normal"
    assert payload["event_count"] == 1
    assert (tmp_path / "out" / NORMALITY_EVALUATION_SUMMARY_FILENAME).is_file()


def test_cli_evaluates_jsonl_input(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    input_path = _write_jsonl(tmp_path / "events.jsonl", [_event(), _event()])

    code, payload, _ = _run_cli(tmp_path, capsys, input_path=input_path)
    summary = _summary(tmp_path / "out")

    assert code == 0
    assert payload["status"] == "ok"
    assert summary["event_count"] == 2


def test_cli_stdout_is_concise_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_json(tmp_path / "events.json", [_event(summary="short summary")])

    code, payload, _ = _run_cli(tmp_path, capsys)

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


def test_cli_default_provider_is_deterministic(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_json(tmp_path / "events.json", [_event()])

    code, payload, _ = _run_cli(tmp_path, capsys)
    summary = _summary(tmp_path / "out")

    assert code == 0
    assert payload["judge_provider"] == "deterministic_normality_judge"
    assert summary["judge_mode"] == "deterministic"


def test_cli_disabled_provider_returns_controlled_result(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    _write_json(tmp_path / "events.json", [_event()])

    code, payload, _ = _run_cli(tmp_path, capsys, extra_args=["--judge-provider", "disabled"])
    summary = _summary(tmp_path / "out")

    assert code == 0
    assert payload["status"] == "judge_disabled"
    assert payload["label"] == "not_evaluated"
    assert summary["judge_provider"] == "disabled_normality_judge"


def test_cli_llm_provider_uses_placeholder_without_model_call(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agent.normality_evaluation_cli as cli

    def forbidden_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright"}:
            raise AssertionError("CLI must not import runtime clients")
        return original_import(name, *args, **kwargs)

    original_import = __import__
    monkeypatch.setattr("builtins.__import__", forbidden_import)
    _write_json(tmp_path / "events.json", [_event()])

    code, payload, _ = _run_cli(tmp_path, capsys, extra_args=["--judge-provider", "llm"])
    summary = _summary(tmp_path / "out")

    assert cli is not None
    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["judge_provider"] == "llm_normality_judge_placeholder"
    assert summary["findings"] == ["llm_judge_provider_not_configured"]


def test_missing_input_returns_nonzero_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code, payload, stderr = _run_cli(tmp_path, capsys, input_path=tmp_path / "missing.json")

    assert code == 2
    assert payload["status"] == "input_missing"
    assert "Traceback" not in stderr


def test_malformed_json_returns_nonzero_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    input_path = tmp_path / "events.json"
    input_path.write_text("{not json", encoding="utf-8")

    code, payload, stderr = _run_cli(tmp_path, capsys, input_path=input_path)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert "Traceback" not in stderr


def test_cli_creates_output_dir(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_json(tmp_path / "events.json", [_event()])
    out_dir = tmp_path / "missing" / "out"

    code, _, _ = _run_cli(tmp_path, capsys, output_dir=out_dir)

    assert code == 0
    assert (out_dir / NORMALITY_EVALUATION_SUMMARY_FILENAME).is_file()


def test_cli_redacts_absolute_windows_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "outside.docx"])
    _write_json(
        tmp_path / "events.json",
        [_event(summary=f"Attempted {windows_path}", artifact_paths=[windows_path])],
    )

    code, payload, _ = _run_cli(tmp_path, capsys, extra_args=["--max-text-chars", "120"])
    summary_text = (tmp_path / "out" / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )
    stdout_text = json.dumps(payload, ensure_ascii=False)

    assert code == 0
    assert windows_path not in summary_text
    assert windows_path not in stdout_text
    assert "absolute_path" in _summary(tmp_path / "out")["redactions_applied"]


def test_cli_redacts_absolute_posix_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    posix_path = "/home/example/outside_workspace/outside.docx"
    _write_json(
        tmp_path / "events.json",
        [_event(summary=f"Attempted {posix_path}", artifact_paths=[posix_path])],
    )

    code, payload, _ = _run_cli(tmp_path, capsys)
    summary_text = (tmp_path / "out" / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )
    stdout_text = json.dumps(payload, ensure_ascii=False)

    assert code == 0
    assert posix_path not in summary_text
    assert posix_path not in stdout_text


def test_cli_preserves_relative_artifact_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    relative_path = "artifacts/office/summary.docx"
    _write_json(tmp_path / "events.json", [_event(artifact_paths=[relative_path])])

    code, _, _ = _run_cli(tmp_path, capsys)
    summary = _summary(tmp_path / "out")

    assert code == 0
    assert summary["event_preview"][0]["artifact_paths"] == [relative_path]


def test_cli_truncates_long_raw_text(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    long_text = "A" * 300
    _write_json(tmp_path / "events.json", [_event(summary=long_text)])

    code, _, _ = _run_cli(tmp_path, capsys, extra_args=["--max-text-chars", "40"])
    summary_text = (tmp_path / "out" / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )

    assert code == 0
    assert long_text not in summary_text
    assert "...[truncated]" in summary_text


def test_cli_include_raw_outputs_is_explicit_bounded_and_redacted(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    posix_path = "/home/example/outside_workspace/outside.docx"
    long_text = f"{posix_path} " + ("B" * 300)
    _write_json(tmp_path / "events.json", [_event(summary=long_text)])

    code, _, _ = _run_cli(
        tmp_path,
        capsys,
        extra_args=["--include-raw-outputs", "--max-text-chars", "50"],
    )
    summary_text = (tmp_path / "out" / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )

    assert code == 0
    assert posix_path not in summary_text
    assert "B" * 300 not in summary_text
    assert "...[truncated]" in summary_text


def test_cli_does_not_write_reports_or_experiments(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    _write_json(tmp_path / "events.json", [_event()])

    code, _, _ = _run_cli(tmp_path, capsys)

    assert code == 0
    assert not (PROJECT_ROOT / "reports" / NORMALITY_EVALUATION_SUMMARY_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / NORMALITY_EVALUATION_SUMMARY_FILENAME).exists()


def test_cli_source_does_not_import_runtime_backends() -> None:
    source = (PROJECT_ROOT / "src" / "agent" / "normality_evaluation_cli.py").read_text(
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

    assert all(token not in source for token in forbidden_tokens)
