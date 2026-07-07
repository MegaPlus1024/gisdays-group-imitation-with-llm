from __future__ import annotations

import importlib
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from scripts.summarize_office_execution_artifacts import main as summarize_cli_main
from src.agent.model_pair_office_execution_artifacts import (
    OFFICE_EXECUTION_ARTIFACT_SUMMARY_SCHEMA_VERSION,
    summarize_office_execution_artifacts,
)


def _trial(path: str, **overrides: object) -> dict[str, Any]:
    payload = {
        "trial_id": "trial_001",
        "scenario_id": "office_document_file_workflow_basic_v1",
        "pair_id": "second_model__to__first_model",
        "status": "succeeded",
        "task_success": True,
        "artifact_refs": ["artifacts/single_trial_runs/phase_test/pipeline"],
        "group_history": [
            {
                "task_id": "t1",
                "agent_id": "document_summary_agent",
                "action": "office_append_docx_section",
                "metadata": {
                    "validation_accepted": True,
                    "execution_attempted": True,
                    "execution_success": True,
                    "precreate_metadata": {
                        "path": path,
                        "precreate_success": True,
                    },
                },
            }
        ],
    }
    payload.update(overrides)
    return payload


def _write_docx(project_root: Path, relative_path: str, paragraphs: list[str]) -> Path:
    pytest.importorskip("docx")
    docx_module = importlib.import_module("docx")
    path = project_root / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    document = docx_module.Document()
    for paragraph in paragraphs:
        document.add_paragraph(paragraph)
    document.save(path)
    return path


def test_harvester_extracts_precreated_docx_artifact_with_bounded_excerpt(tmp_path: Path) -> None:
    relative_path = "artifacts/single_trial_runs/phase_test/pipeline/workspace/office_outputs/report.docx"
    _write_docx(tmp_path, relative_path, ["Alpha paragraph.", "Beta paragraph with extra detail."])

    summary = summarize_office_execution_artifacts(
        _trial(relative_path),
        project_root=tmp_path,
        max_text_chars=24,
    )
    payload_text = json.dumps(summary, ensure_ascii=False)

    assert summary["schema_version"] == OFFICE_EXECUTION_ARTIFACT_SUMMARY_SCHEMA_VERSION
    assert summary["run_id"] == "phase_test"
    assert summary["artifact_count"] == 1
    assert summary["readable_count"] == 1
    assert summary["artifacts"][0]["path"] == relative_path
    assert summary["artifacts"][0]["extension"] == ".docx"
    assert summary["artifacts"][0]["exists"] is True
    assert summary["artifacts"][0]["size_bytes"] > 0
    assert summary["artifacts"][0]["readable"] is True
    assert summary["artifacts"][0]["paragraph_count"] == 2
    assert summary["artifacts"][0]["safe_text_excerpt"].endswith("...[truncated]")
    assert str(tmp_path) not in payload_text


def test_harvester_marks_missing_docx_without_traceback(tmp_path: Path) -> None:
    relative_path = "artifacts/single_trial_runs/phase_test/pipeline/workspace/office_outputs/missing.docx"

    summary = summarize_office_execution_artifacts(_trial(relative_path), project_root=tmp_path)

    assert summary["artifact_count"] == 1
    assert summary["missing_count"] == 1
    assert summary["artifacts"][0]["exists"] is False
    assert summary["artifacts"][0]["readable"] is False
    assert "office_artifact_missing" in summary["warnings"]


def test_harvester_suppresses_absolute_paths(tmp_path: Path) -> None:
    absolute_path = str(tmp_path / "outside.docx")

    summary = summarize_office_execution_artifacts(_trial(absolute_path), project_root=tmp_path)
    payload_text = json.dumps(summary, ensure_ascii=False)

    assert absolute_path not in payload_text
    assert summary["artifacts"][0]["path"] == "<absolute_path>"
    assert "absolute_artifact_path_suppressed" in summary["warnings"]


def test_harvester_handles_missing_python_docx_dependency(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative_path = "artifacts/single_trial_runs/phase_test/pipeline/workspace/office_outputs/report.docx"
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"placeholder")

    def missing_docx(name: str, *args: object, **kwargs: object) -> object:
        if name == "docx":
            raise ImportError("missing")
        return importlib.import_module(name, *args, **kwargs)

    monkeypatch.setattr("importlib.import_module", missing_docx)

    summary = summarize_office_execution_artifacts(_trial(relative_path), project_root=tmp_path)

    assert summary["artifacts"][0]["exists"] is True
    assert summary["artifacts"][0]["readable"] is False
    assert summary["artifacts"][0]["dependency_missing"] == "python-docx"
    assert "office_artifact_docx_dependency_missing" in summary["warnings"]


def test_postprocess_script_writes_office_execution_summary(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    relative_path = "artifacts/single_trial_runs/phase_test/pipeline/workspace/office_outputs/report.docx"
    _write_docx(tmp_path, relative_path, ["Script paragraph."])
    trial_path = tmp_path / "model_pair_single_trial_result.json"
    trial_path.write_text(json.dumps(_trial(relative_path), ensure_ascii=False), encoding="utf-8")
    output_path = tmp_path / "office_execution_artifact_summary.json"

    code = summarize_cli_main(
        [
            "--trial-result",
            str(trial_path),
            "--output",
            str(output_path),
            "--project-root",
            str(tmp_path),
        ]
    )
    stdout = json.loads(capsys.readouterr().out)
    summary = json.loads(output_path.read_text(encoding="utf-8"))

    assert code == 0
    assert stdout["status"] == "ok"
    assert stdout["artifact_count"] == 1
    assert summary["artifacts"][0]["path"] == relative_path


def test_postprocess_script_runs_from_scripts_directory(tmp_path: Path) -> None:
    relative_path = "artifacts/single_trial_runs/phase_test/pipeline/workspace/office_outputs/report.docx"
    _write_docx(tmp_path, relative_path, ["Subprocess paragraph."])
    trial_path = tmp_path / "model_pair_single_trial_result.json"
    trial_path.write_text(json.dumps(_trial(relative_path), ensure_ascii=False), encoding="utf-8")
    output_path = tmp_path / "office_execution_artifact_summary.json"

    completed = subprocess.run(
        [
            sys.executable,
            "scripts/summarize_office_execution_artifacts.py",
            "--trial-result",
            str(trial_path),
            "--output",
            str(output_path),
            "--project-root",
            str(tmp_path),
        ],
        check=False,
        capture_output=True,
        text=True,
    )

    assert completed.returncode == 0
    assert "Traceback" not in completed.stderr
    assert json.loads(completed.stdout)["status"] == "ok"
    assert json.loads(output_path.read_text(encoding="utf-8"))["artifact_count"] == 1


def test_harvester_does_not_import_runtime_clients(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    relative_path = "artifacts/single_trial_runs/phase_test/pipeline/workspace/office_outputs/report.docx"
    path = tmp_path / relative_path
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(b"placeholder")
    original_import_module = importlib.import_module

    def forbid_runtime_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright", "win32com", "pythoncom", "uno"}:
            raise AssertionError("unexpected runtime client import")
        if name == "docx":
            raise ImportError("docx deliberately unavailable")
        return original_import_module(name, *args, **kwargs)

    monkeypatch.setattr("importlib.import_module", forbid_runtime_import)

    summary = summarize_office_execution_artifacts(_trial(relative_path), project_root=tmp_path)

    assert summary["no_runtime_execution"] is True
