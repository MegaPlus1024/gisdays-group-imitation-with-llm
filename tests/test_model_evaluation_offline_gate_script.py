from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from scripts import check_model_evaluation_offline as offline_gate_script
from src.agent.model_evaluation_compatibility_gate import (
    MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME,
)
from src.agent.model_evaluation_workflow_runner import (
    ModelEvaluationWorkflowRunConfig,
    run_offline_model_evaluation_workflow,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
GOLDEN_DIR = PROJECT_ROOT / "tests" / "fixtures" / "model_evaluation_workflow_golden"
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"


def _payload(capsys: pytest.CaptureFixture[str]) -> dict[str, Any]:
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    return json.loads(captured.out)


def _assert_no_tmp_path_leak(payload_text: str, tmp_path: Path) -> None:
    variants = {
        str(tmp_path),
        str(tmp_path).replace("\\", "/"),
        str(tmp_path).replace("\\", "\\\\"),
        tmp_path.as_posix(),
    }
    assert all(variant not in payload_text for variant in variants)


def _workflow_config(tmp_path: Path) -> ModelEvaluationWorkflowRunConfig:
    return ModelEvaluationWorkflowRunConfig.model_validate(
        {
            "workflow_id": "offline_gate_script_workflow",
            "model_catalog_path": str(CATALOG_PATH),
            "scenario_paths": [SCENARIO_PATH],
            "output_dir": str(tmp_path / "workflow"),
            "repetitions_per_pair": 1,
            "include_self_pairs": True,
            "tags": ["offline_gate_script_test"],
        }
    )


def _workflow_output(tmp_path: Path) -> Path:
    result = run_offline_model_evaluation_workflow(_workflow_config(tmp_path))
    assert result.status == "partial"
    return tmp_path / "workflow"


def test_script_runs_with_output_dir_and_returns_zero(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = offline_gate_script.main(["--output-dir", str(tmp_path / "gate")])
    payload = _payload(capsys)

    assert code == 0
    assert payload["status"] == "compatible"
    assert payload["check_mode"] == "golden_only"


def test_script_writes_compatibility_report(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = offline_gate_script.main(["--output-dir", str(tmp_path / "gate")])
    payload = _payload(capsys)

    assert code == 0
    assert payload["report_path"] == MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME
    assert (tmp_path / "gate" / MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME).is_file()


def test_script_stdout_is_valid_concise_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = offline_gate_script.main(["--output-dir", str(tmp_path / "gate"), "--quiet"])
    payload = _payload(capsys)

    assert code == 0
    assert set(payload) == {
        "status",
        "compatibility_id",
        "checked_artifact_count",
        "error_count",
        "warning_count",
        "report_path",
        "check_mode",
        "no_runtime_execution",
    }


def test_script_supports_explicit_golden_fixture_dir(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = offline_gate_script.main(
        [
            "--golden-fixture-dir",
            str(GOLDEN_DIR),
            "--output-dir",
            str(tmp_path / "gate"),
        ]
    )
    payload = _payload(capsys)

    assert code == 0
    assert payload["status"] == "compatible"


def test_script_supports_workflow_output_dir(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    workflow_dir = _workflow_output(tmp_path)
    capsys.readouterr()

    code = offline_gate_script.main(
        [
            "--workflow-output-dir",
            str(workflow_dir),
            "--output-dir",
            str(tmp_path / "gate"),
        ]
    )
    payload = _payload(capsys)

    assert code == 0
    assert payload["status"] == "compatible_with_warnings"
    assert payload["check_mode"] == "golden_plus_workflow_output"
    assert payload["warning_count"] > 0


def test_script_strict_returns_zero_for_clean_golden_only_check(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = offline_gate_script.main(["--output-dir", str(tmp_path / "gate"), "--strict"])
    payload = _payload(capsys)

    assert code == 0
    assert payload["status"] == "compatible"
    assert payload["warning_count"] == 0


def test_script_missing_golden_fixture_dir_returns_nonzero_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = offline_gate_script.main(
        [
            "--golden-fixture-dir",
            str(tmp_path / "missing_golden"),
            "--output-dir",
            str(tmp_path / "gate"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "golden_fixture_dir_missing"
    assert "Traceback" not in captured.err


def test_script_does_not_leak_absolute_tmp_path_in_stdout(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = offline_gate_script.main(["--output-dir", str(tmp_path / "gate")])
    captured = capsys.readouterr()

    assert code == 0
    _assert_no_tmp_path_leak(captured.out, tmp_path)


def test_script_help_contains_no_runtime_wording(capsys: pytest.CaptureFixture[str]) -> None:
    with pytest.raises(SystemExit) as exc:
        offline_gate_script.main(["--help"])
    captured = capsys.readouterr()
    help_text = " ".join(captured.out.lower().split())

    assert exc.value.code == 0
    assert "offline compatibility gate only" in help_text
    assert "no model execution is performed" in help_text
    assert "not a production recommendation" in help_text


def test_script_does_not_write_reports_or_experiments(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = offline_gate_script.main(["--output-dir", str(tmp_path / "gate")])
    payload = _payload(capsys)

    assert code == 0
    assert payload["status"] == "compatible"
    assert not (PROJECT_ROOT / "reports" / MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME).exists()


def test_script_makes_no_gguf_model_probe_browser_or_office_calls(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_read_text = Path.read_text
    original_import = __import__

    def forbid_gguf_read_text(self: Path, *args: object, **kwargs: object) -> str:
        if self.suffix.lower() == ".gguf":
            raise AssertionError("unexpected GGUF read")
        return original_read_text(self, *args, **kwargs)

    def forbid_runtime_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("offline gate script must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    code = offline_gate_script.main(["--output-dir", str(tmp_path / "gate")])
    payload = _payload(capsys)

    assert code == 0
    assert payload["status"] == "compatible"
