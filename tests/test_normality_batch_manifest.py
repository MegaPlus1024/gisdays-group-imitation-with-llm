from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.normality_evaluation_cli import main
from src.agent.normality_evaluation_runner import (
    NORMALITY_BATCH_MANIFEST_SCHEMA_VERSION,
    NORMALITY_BATCH_SUMMARY_FILENAME,
    NormalityEvaluationRunConfig,
    load_normality_batch_manifest,
    run_batch_normality_evaluation_from_manifest,
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
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False), encoding="utf-8")
    return path


def _write_jsonl(path: Path, rows: list[dict[str, object]]) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        "\n".join(json.dumps(row, ensure_ascii=False) for row in rows),
        encoding="utf-8",
    )
    return path


def _manifest_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "schema_version": NORMALITY_BATCH_MANIFEST_SCHEMA_VERSION,
        "batch_id": "office_fake_smoke_batch_v1",
        "description": "Offline normality evaluation inputs for fake office scenario smoke.",
        "default_scenario_id": "office_document_file_workflow_basic_v1",
        "default_task_summary": "Evaluate normality of offline office workflow.",
        "inputs": [
            {
                "input_path": "runs/run_001/group_history.json",
                "trial_id": "run_001",
                "model_pair": {"orchestrator": "second_model", "executor": "first_model"},
                "tags": ["office", "fake", "smoke"],
            },
            {
                "input_path": "runs/run_002/group_history.jsonl",
                "trial_id": "run_002",
                "scenario_id": "office_document_override_v1",
                "task_summary": "Evaluate the overridden office task.",
                "tags": ["office", "jsonl"],
            },
        ],
    }
    payload.update(overrides)
    return payload


def _write_default_inputs(manifest_dir: Path) -> None:
    _write_json(manifest_dir / "runs" / "run_001" / "group_history.json", [_event()])
    _write_jsonl(
        manifest_dir / "runs" / "run_002" / "group_history.jsonl",
        [_event("office_append_docx_section")],
    )


def _write_manifest(manifest_dir: Path, payload: dict[str, object] | None = None) -> Path:
    return _write_json(manifest_dir / "manifest.json", payload or _manifest_payload())


def _config(tmp_path: Path, **overrides: object) -> NormalityEvaluationRunConfig:
    payload = {
        "project_root": tmp_path,
        "output_dir": "out",
        "scenario_id": None,
        "task_summary": None,
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
    manifest_path: Path,
    output_dir: Path | None = None,
    extra_args: list[str] | None = None,
) -> tuple[int, dict[str, Any], str]:
    args = [
        "--input-manifest",
        str(manifest_path),
        "--output-dir",
        str(output_dir or tmp_path / "out"),
    ]
    args.extend(extra_args or [])
    code = main(args)
    captured = capsys.readouterr()
    return code, json.loads(captured.out), captured.err


def test_loads_valid_manifest(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "batch"
    manifest_path = _write_manifest(manifest_dir)

    result = load_normality_batch_manifest(manifest_path, project_root=tmp_path)

    assert result.status == "ok"
    assert result.manifest is not None
    assert result.manifest.batch_id == "office_fake_smoke_batch_v1"
    assert len(result.manifest.inputs) == 2


def test_relative_input_paths_resolve_relative_to_manifest_parent(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "batch"
    _write_default_inputs(manifest_dir)
    manifest_path = _write_manifest(manifest_dir)

    result = run_batch_normality_evaluation_from_manifest(_config(tmp_path), manifest_path)

    assert result.status == "ok"
    assert result.entries[0].input_path_relative == "runs/run_001/group_history.json"
    assert result.entries[1].input_path_relative == "runs/run_002/group_history.jsonl"


def test_manifest_defaults_apply_to_entries(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "batch"
    _write_default_inputs(manifest_dir)
    manifest_path = _write_manifest(manifest_dir)

    result = run_batch_normality_evaluation_from_manifest(_config(tmp_path), manifest_path)

    assert result.entries[0].scenario_id == "office_document_file_workflow_basic_v1"
    assert result.entries[0].task_summary == "Evaluate normality of offline office workflow."


def test_manifest_entry_metadata_overrides_defaults(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "batch"
    _write_default_inputs(manifest_dir)
    manifest_path = _write_manifest(manifest_dir)

    result = run_batch_normality_evaluation_from_manifest(_config(tmp_path), manifest_path)

    assert result.entries[1].scenario_id == "office_document_override_v1"
    assert result.entries[1].task_summary == "Evaluate the overridden office task."


def test_batch_from_manifest_evaluates_two_inputs(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "batch"
    _write_default_inputs(manifest_dir)
    manifest_path = _write_manifest(manifest_dir)

    result = run_batch_normality_evaluation_from_manifest(_config(tmp_path), manifest_path)

    assert result.status == "ok"
    assert result.input_count == 2
    assert result.evaluated_count == 2
    assert result.failed_count == 0
    assert result.aggregation["label_counts"] == {"normal": 2}


def test_batch_summary_includes_manifest_metadata(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "batch"
    _write_default_inputs(manifest_dir)
    manifest_path = _write_manifest(manifest_dir)

    run_batch_normality_evaluation_from_manifest(_config(tmp_path), manifest_path)
    summary = _batch_summary(tmp_path / "out")

    assert summary["manifest_schema_version"] == NORMALITY_BATCH_MANIFEST_SCHEMA_VERSION
    assert summary["batch_id"] == "office_fake_smoke_batch_v1"
    assert summary["description"] == "Offline normality evaluation inputs for fake office scenario smoke."
    assert summary["entries"][0]["trial_id"] == "run_001"
    assert summary["entries"][0]["model_pair"] == {
        "orchestrator": "second_model",
        "executor": "first_model",
    }
    assert summary["entries"][0]["tags"] == ["office", "fake", "smoke"]


def test_malformed_manifest_returns_controlled_error_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_path = tmp_path / "batch" / "manifest.json"
    manifest_path.parent.mkdir(parents=True)
    manifest_path.write_text("{not json", encoding="utf-8")

    code, payload, stderr = _run_cli(tmp_path, capsys, manifest_path=manifest_path)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert "Traceback" not in stderr


def test_missing_manifest_returns_controlled_error_without_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_path = tmp_path / "missing" / "manifest.json"

    code, payload, stderr = _run_cli(tmp_path, capsys, manifest_path=manifest_path)

    assert code == 2
    assert payload["status"] == "input_missing"
    assert "Traceback" not in stderr


def test_empty_inputs_list_returns_controlled_error(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "batch"
    manifest_path = _write_manifest(manifest_dir, _manifest_payload(inputs=[]))

    result = run_batch_normality_evaluation_from_manifest(_config(tmp_path), manifest_path)

    assert result.status == "invalid_input"
    assert result.input_count == 0
    assert "manifest_inputs_empty" in result.warnings


def test_entry_missing_input_path_is_failed_entry(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "batch"
    _write_json(manifest_dir / "runs" / "run_001" / "group_history.json", [_event()])
    manifest_path = _write_manifest(
        manifest_dir,
        _manifest_payload(
            inputs=[
                {"input_path": "runs/run_001/group_history.json", "trial_id": "run_001"},
                {"trial_id": "missing_path_entry", "tags": ["bad-entry"]},
            ]
        ),
    )

    result = run_batch_normality_evaluation_from_manifest(_config(tmp_path), manifest_path)

    assert result.status == "ok"
    assert result.evaluated_count == 1
    assert result.failed_count == 1
    assert result.entries[1].status == "invalid_input"
    assert result.entries[1].warnings == ["manifest_entry_input_path_missing"]


def test_absolute_input_path_in_manifest_is_rejected(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "batch"
    absolute_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "history.json"])
    manifest_path = _write_manifest(
        manifest_dir,
        _manifest_payload(inputs=[{"input_path": absolute_path, "trial_id": "absolute"}]),
    )

    result = run_batch_normality_evaluation_from_manifest(_config(tmp_path), manifest_path)

    assert result.status == "invalid_input"
    assert result.entries[0].input_path_display == "<absolute_path>"
    assert result.entries[0].warnings == ["manifest_absolute_input_path_rejected"]


def test_cli_input_manifest_triggers_manifest_batch_mode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_dir = tmp_path / "batch"
    _write_default_inputs(manifest_dir)
    manifest_path = _write_manifest(manifest_dir)

    code, payload, _ = _run_cli(tmp_path, capsys, manifest_path=manifest_path)

    assert code == 0
    assert payload["status"] == "ok"
    assert payload["batch_id"] == "office_fake_smoke_batch_v1"
    assert payload["input_count"] == 2
    assert payload["batch_summary_path"] == NORMALITY_BATCH_SUMMARY_FILENAME


def test_cli_rejects_combining_input_and_input_manifest(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_path = _write_manifest(tmp_path / "batch")
    input_path = _write_json(tmp_path / "events.json", [_event()])

    code = main(
        [
            "--input-manifest",
            str(manifest_path),
            "--input",
            str(input_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "input_manifest_cannot_combine_with_input"


def test_batch_summary_does_not_leak_absolute_manifest_parent_path(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "batch" / "private_parent"
    _write_default_inputs(manifest_dir)
    manifest_path = _write_manifest(manifest_dir)

    run_batch_normality_evaluation_from_manifest(_config(tmp_path), manifest_path)
    summary_text = (tmp_path / "out" / NORMALITY_BATCH_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )

    assert str(manifest_dir) not in summary_text
    assert "runs/run_001/group_history.json" in summary_text


def test_absolute_path_inside_event_is_redacted(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "batch"
    posix_path = "/home/example/outside_workspace/outside.docx"
    _write_json(
        manifest_dir / "runs" / "run_001" / "group_history.json",
        [_event(summary=f"Attempted {posix_path}", artifact_paths=[posix_path])],
    )
    manifest_path = _write_manifest(
        manifest_dir,
        _manifest_payload(inputs=[{"input_path": "runs/run_001/group_history.json"}]),
    )

    run_batch_normality_evaluation_from_manifest(_config(tmp_path), manifest_path)
    summary_text = (tmp_path / "out" / NORMALITY_BATCH_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )
    summary = _batch_summary(tmp_path / "out")

    assert posix_path not in summary_text
    assert summary["entries"][0]["event_preview"][0]["artifact_paths"] == ["<absolute_path>"]


def test_relative_artifact_path_inside_event_is_preserved(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "batch"
    relative_path = "artifacts/office/summary.docx"
    _write_json(
        manifest_dir / "runs" / "run_001" / "group_history.json",
        [_event(artifact_paths=[relative_path])],
    )
    manifest_path = _write_manifest(
        manifest_dir,
        _manifest_payload(inputs=[{"input_path": "runs/run_001/group_history.json"}]),
    )

    run_batch_normality_evaluation_from_manifest(_config(tmp_path), manifest_path)
    summary = _batch_summary(tmp_path / "out")

    assert summary["entries"][0]["event_preview"][0]["artifact_paths"] == [relative_path]


def test_manifest_batch_summary_does_not_write_raw_full_events(tmp_path: Path) -> None:
    manifest_dir = tmp_path / "batch"
    raw_marker = "RAW_FULL_EVENT_MARKER_SHOULD_NOT_APPEAR"
    _write_json(
        manifest_dir / "runs" / "run_001" / "group_history.json",
        [_event(extra={"raw_payload": raw_marker})],
    )
    manifest_path = _write_manifest(
        manifest_dir,
        _manifest_payload(inputs=[{"input_path": "runs/run_001/group_history.json"}]),
    )

    run_batch_normality_evaluation_from_manifest(_config(tmp_path), manifest_path)
    summary_text = (tmp_path / "out" / NORMALITY_BATCH_SUMMARY_FILENAME).read_text(
        encoding="utf-8"
    )

    assert raw_marker not in summary_text


def test_manifest_batch_does_not_write_reports_or_experiments(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    manifest_dir = tmp_path / "batch"
    _write_default_inputs(manifest_dir)
    manifest_path = _write_manifest(manifest_dir)

    code, _, _ = _run_cli(tmp_path, capsys, manifest_path=manifest_path)

    assert code == 0
    assert not (PROJECT_ROOT / "reports" / NORMALITY_BATCH_SUMMARY_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / NORMALITY_BATCH_SUMMARY_FILENAME).exists()


def test_manifest_batch_does_not_create_http_model_browser_or_office_clients(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_import = __import__

    def forbidden_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("manifest batch evaluation must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", forbidden_import)
    manifest_dir = tmp_path / "batch"
    _write_default_inputs(manifest_dir)
    manifest_path = _write_manifest(manifest_dir)

    code, payload, _ = _run_cli(tmp_path, capsys, manifest_path=manifest_path)

    assert code == 0
    assert payload["status"] == "ok"
