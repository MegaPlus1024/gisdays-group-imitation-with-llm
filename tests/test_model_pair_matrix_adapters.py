from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_pair_matrix_adapters import (
    MATRIX_RUN_ADAPTER_SUMMARY_FILENAME,
    MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME,
    NORMALITY_JUDGE_INPUTS_JSONL_FILENAME,
    build_normality_inputs_from_matrix_run_summary,
    build_resource_observations_from_matrix_run_summary,
    write_matrix_run_adapter_outputs,
    write_normality_inputs_jsonl,
    write_resource_observations_jsonl,
)
from src.agent.model_pair_matrix_adapters_cli import main as adapters_cli_main
from src.agent.model_pair_matrix_runner import MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME
from src.agent.model_resource_evaluation import (
    load_model_resource_observations_from_file,
    summarize_model_resource_observations,
)
from src.agent.normality_evaluation_runner import load_normality_events_from_file


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _event(**overrides: object) -> dict[str, Any]:
    payload = {
        "agent_id": "office_agent",
        "role": "office document worker",
        "action": "office_create_docx",
        "status": "success",
        "summary": "Created an offline document artifact.",
        "artifact_paths": ["artifacts/office/report.docx"],
    }
    payload.update(overrides)
    return payload


def _trial(**overrides: object) -> dict[str, Any]:
    payload = {
        "trial_id": "trial_001",
        "scenario_id": "office_document_file_workflow_basic_v1",
        "pair_id": "second_model__to__first_model",
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
        "status": "succeeded",
        "task_success": True,
        "correctness_score": 0.93,
        "warnings": [],
        "notes": ["synthetic_matrix_trial"],
        "tags": ["adapter_test"],
        "no_runtime_execution": True,
        "execution_mode": "static_fixture",
    }
    payload.update(overrides)
    return payload


def _matrix_summary(*trials: dict[str, Any], **overrides: object) -> dict[str, Any]:
    payload = {
        "schema_version": "model_pair_matrix_run_summary_v1",
        "run_id": "adapter_matrix_run",
        "plan_id": "adapter_matrix_plan",
        "execution_mode": "static_fixture",
        "trial_count": len(trials) or 1,
        "succeeded_count": 1,
        "failed_count": 0,
        "skipped_count": 0,
        "dry_run_count": 0,
        "pair_summaries": [],
        "scenario_summaries": [],
        "trial_results": list(trials) or [_trial()],
        "warnings": [],
        "notes": ["Synthetic matrix run summary."],
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _write_json(path: Path, payload: object) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _jsonl_rows(path: Path) -> list[dict[str, Any]]:
    return [
        json.loads(line)
        for line in path.read_text(encoding="utf-8").splitlines()
        if line.strip()
    ]


def test_resource_adapter_uses_explicit_resource_observation_when_present() -> None:
    trial = _trial(
        resource_observation={
            "observation_id": "explicit_resource_1",
            "runtime_mode": "offline_static",
            "backend": "fixture_backend",
            "success": True,
            "wall_time_s": 1.25,
            "peak_ram_gb": 2.5,
            "raw_prompt": "do not copy",
            "api_key": "do not copy",
            "notes": ["Wrote C:\\Users\\Example\\secret\\report.docx"],
        }
    )

    observations = build_resource_observations_from_matrix_run_summary(_matrix_summary(trial))

    assert observations[0]["observation_id"] == "explicit_resource_1"
    assert observations[0]["trial_id"] == "trial_001"
    assert observations[0]["pair_id"] == "second_model__to__first_model"
    assert observations[0]["wall_time_s"] == 1.25
    assert observations[0]["peak_ram_gb"] == 2.5
    assert observations[0]["runtime_mode"] == "offline_static"
    assert "raw_prompt" not in observations[0]
    assert "api_key" not in observations[0]
    assert observations[0]["notes"] == ["Wrote <absolute_path>"]


def test_resource_adapter_creates_minimal_observation_without_metrics() -> None:
    observations = build_resource_observations_from_matrix_run_summary(_matrix_summary(_trial()))

    assert observations == [
        {
            "observation_id": "trial_001__resource",
            "trial_id": "trial_001",
            "scenario_id": "office_document_file_workflow_basic_v1",
            "pair_id": "second_model__to__first_model",
            "orchestrator_model_id": "second_model",
            "executor_model_id": "first_model",
            "success": True,
            "runtime_mode": "unknown",
            "backend": "unknown",
            "notes": ["synthetic_matrix_trial"],
            "tags": ["adapter_test"],
        }
    ]


def test_resource_adapter_does_not_invent_ram_vram_or_wall_time() -> None:
    observation = build_resource_observations_from_matrix_run_summary(_matrix_summary(_trial()))[0]

    assert "wall_time_s" not in observation
    assert "peak_ram_gb" not in observation
    assert "peak_vram_gb" not in observation


@pytest.mark.parametrize(
    ("trial_status", "task_success", "expected"),
    [
        ("succeeded", None, True),
        ("failed", None, False),
        ("dry_run", None, None),
        ("succeeded", False, False),
    ],
)
def test_resource_adapter_derives_success_from_task_success_or_status(
    trial_status: str,
    task_success: bool | None,
    expected: bool | None,
) -> None:
    observation = build_resource_observations_from_matrix_run_summary(
        _matrix_summary(_trial(status=trial_status, task_success=task_success))
    )[0]

    assert observation.get("success") is expected


def test_resource_observations_are_accepted_by_resource_evaluator(tmp_path: Path) -> None:
    observations = build_resource_observations_from_matrix_run_summary(_matrix_summary(_trial()))
    path = write_resource_observations_jsonl(observations, tmp_path)
    loaded = load_model_resource_observations_from_file(path, project_root=tmp_path)
    summary = summarize_model_resource_observations(loaded.observations)

    assert loaded.status == "ok"
    assert summary.status == "ok"
    assert summary.groups["by_pair"]["second_model__to__first_model"].observation_count == 1


@pytest.mark.parametrize("trace_key", ["group_history", "event_history", "activity_trace"])
def test_normality_adapter_uses_existing_trace_fields(trace_key: str, tmp_path: Path) -> None:
    trial = _trial(**{trace_key: [_event(action="office_append_docx_section")]})

    inputs = build_normality_inputs_from_matrix_run_summary(_matrix_summary(trial))
    input_path = _write_json(tmp_path / "normality_input.json", inputs[0])
    loaded = load_normality_events_from_file(input_path, project_root=tmp_path)

    assert inputs[0][trace_key][0]["action"] == "office_append_docx_section"
    assert inputs[0]["events"][0]["action"] == "office_append_docx_section"
    assert "normality_trace_missing" not in inputs[0]["warnings"]
    assert loaded.status == "ok"
    assert loaded.records[0]["action"] == "office_append_docx_section"


def test_normality_adapter_marks_missing_trace_without_fabricating_activity() -> None:
    inputs = build_normality_inputs_from_matrix_run_summary(_matrix_summary(_trial()))

    assert inputs[0]["events"] == []
    assert inputs[0]["adapter_status"] == "invalid_input"
    assert "normality_trace_missing" in inputs[0]["warnings"]


def test_normality_adapter_redacts_absolute_windows_paths() -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "report.docx"])
    trial = _trial(group_history=[_event(summary=f"Opened {windows_path}", artifact_paths=[windows_path])])

    payload_text = json.dumps(
        build_normality_inputs_from_matrix_run_summary(_matrix_summary(trial)),
        ensure_ascii=False,
    )

    assert windows_path not in payload_text
    assert "<absolute_path>" in payload_text


def test_normality_adapter_redacts_absolute_posix_paths() -> None:
    posix_path = "/home/example/outside_workspace/report.docx"
    trial = _trial(group_history=[_event(summary=f"Opened {posix_path}", artifact_paths=[posix_path])])

    payload_text = json.dumps(
        build_normality_inputs_from_matrix_run_summary(_matrix_summary(trial)),
        ensure_ascii=False,
    )

    assert posix_path not in payload_text
    assert "<absolute_path>" in payload_text


def test_normality_adapter_does_not_copy_raw_secret_like_fields() -> None:
    trial = _trial(
        group_history=[
            _event(
                raw_prompt="RAW_PROMPT_SHOULD_NOT_COPY",
                raw_response="RAW_RESPONSE_SHOULD_NOT_COPY",
                api_key="SECRET_SHOULD_NOT_COPY",
                summary="token=SECRET_TOKEN should be redacted",
            )
        ],
        auth_token="TRIAL_TOKEN_SHOULD_NOT_COPY",
    )

    payload_text = json.dumps(
        build_normality_inputs_from_matrix_run_summary(_matrix_summary(trial)),
        ensure_ascii=False,
    )

    assert "RAW_PROMPT_SHOULD_NOT_COPY" not in payload_text
    assert "RAW_RESPONSE_SHOULD_NOT_COPY" not in payload_text
    assert "SECRET_SHOULD_NOT_COPY" not in payload_text
    assert "SECRET_TOKEN" not in payload_text
    assert "<redacted_secret>" in payload_text


def test_writes_jsonl_resource_observations(tmp_path: Path) -> None:
    observations = build_resource_observations_from_matrix_run_summary(_matrix_summary(_trial()))

    path = write_resource_observations_jsonl(observations, tmp_path)

    assert path == tmp_path / MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME
    assert _jsonl_rows(path)[0]["observation_id"] == "trial_001__resource"


def test_writes_jsonl_normality_inputs(tmp_path: Path) -> None:
    inputs = build_normality_inputs_from_matrix_run_summary(_matrix_summary(_trial(group_history=[_event()])))

    path = write_normality_inputs_jsonl(inputs, tmp_path)

    assert path == tmp_path / NORMALITY_JUDGE_INPUTS_JSONL_FILENAME
    assert _jsonl_rows(path)[0]["trial_id"] == "trial_001"


def test_writes_adapter_summary(tmp_path: Path) -> None:
    summary = write_matrix_run_adapter_outputs(
        _matrix_summary(_trial(group_history=[_event()]), _trial(trial_id="trial_002")),
        tmp_path,
        adapter_id="adapter_test_run",
    )
    payload = json.loads((tmp_path / MATRIX_RUN_ADAPTER_SUMMARY_FILENAME).read_text(encoding="utf-8"))

    assert summary["schema_version"] == "matrix_run_adapter_summary_v1"
    assert payload["adapter_id"] == "adapter_test_run"
    assert payload["trial_count"] == 2
    assert payload["resource_observation_count"] == 2
    assert payload["normality_input_count"] == 2
    assert payload["normality_missing_trace_count"] == 1
    assert payload["output_paths"]["resource_observations"] == MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME
    assert payload["output_paths"]["normality_inputs"] == NORMALITY_JUDGE_INPUTS_JSONL_FILENAME


def test_cli_converts_matrix_summary(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    matrix_path = _write_json(tmp_path / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME, _matrix_summary(_trial(group_history=[_event()])))

    code = adapters_cli_main(
        [
            "--matrix-run-summary",
            str(matrix_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--adapter-id",
            "cli_adapter",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["status"] == "ok"
    assert payload["trial_count"] == 1
    assert payload["resource_observation_count"] == 1
    assert payload["normality_input_count"] == 1
    assert payload["resource_observations_path"] == MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME
    assert payload["normality_inputs_path"] == NORMALITY_JUDGE_INPUTS_JSONL_FILENAME
    assert (tmp_path / "out" / MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME).is_file()
    assert (tmp_path / "out" / NORMALITY_JUDGE_INPUTS_JSONL_FILENAME).is_file()


def test_cli_resource_only_writes_only_resource_observations(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    matrix_path = _write_json(tmp_path / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME, _matrix_summary(_trial(group_history=[_event()])))

    code = adapters_cli_main(
        [
            "--matrix-run-summary",
            str(matrix_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--resource-only",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["resource_observation_count"] == 1
    assert payload["normality_input_count"] == 0
    assert (tmp_path / "out" / MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME).is_file()
    assert not (tmp_path / "out" / NORMALITY_JUDGE_INPUTS_JSONL_FILENAME).exists()


def test_cli_normality_only_writes_only_normality_inputs(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    matrix_path = _write_json(tmp_path / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME, _matrix_summary(_trial(group_history=[_event()])))

    code = adapters_cli_main(
        [
            "--matrix-run-summary",
            str(matrix_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--normality-only",
        ]
    )
    payload = json.loads(capsys.readouterr().out)

    assert code == 0
    assert payload["resource_observation_count"] == 0
    assert payload["normality_input_count"] == 1
    assert not (tmp_path / "out" / MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME).exists()
    assert (tmp_path / "out" / NORMALITY_JUDGE_INPUTS_JSONL_FILENAME).is_file()


def test_cli_missing_summary_returns_nonzero_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = adapters_cli_main(
        [
            "--matrix-run-summary",
            str(tmp_path / "missing.json"),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "matrix_summary_file_missing"
    assert "Traceback" not in captured.err


def test_cli_malformed_summary_returns_nonzero_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    matrix_path = tmp_path / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME
    matrix_path.write_text("{bad-json", encoding="utf-8")

    code = adapters_cli_main(
        [
            "--matrix-run-summary",
            str(matrix_path),
            "--output-dir",
            str(tmp_path / "out"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "matrix_summary_json_malformed"
    assert "Traceback" not in captured.err


def test_optional_task_summary_map_is_used_by_cli(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    matrix_path = _write_json(tmp_path / MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME, _matrix_summary(_trial(group_history=[_event()])))
    task_summary_path = _write_json(
        tmp_path / "task_summary_map.json",
        {"office_document_file_workflow_basic_v1": "Mapped normality task summary."},
    )

    code = adapters_cli_main(
        [
            "--matrix-run-summary",
            str(matrix_path),
            "--output-dir",
            str(tmp_path / "out"),
            "--task-summary-map",
            str(task_summary_path),
            "--normality-only",
        ]
    )
    rows = _jsonl_rows(tmp_path / "out" / NORMALITY_JUDGE_INPUTS_JSONL_FILENAME)

    assert code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "ok"
    assert rows[0]["task_summary"] == "Mapped normality task summary."


def test_no_reports_or_experiments_files_are_written(tmp_path: Path) -> None:
    write_matrix_run_adapter_outputs(_matrix_summary(_trial(group_history=[_event()])), tmp_path / "out")

    assert not (PROJECT_ROOT / "reports" / MATRIX_RUN_ADAPTER_SUMMARY_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / MATRIX_RUN_ADAPTER_SUMMARY_FILENAME).exists()


def test_no_gguf_model_probe_browser_or_office_calls_are_made(
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
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("matrix adapters must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    summary = write_matrix_run_adapter_outputs(
        _matrix_summary(_trial(group_history=[_event()])),
        tmp_path / "out",
    )

    assert summary["no_runtime_execution"] is True
