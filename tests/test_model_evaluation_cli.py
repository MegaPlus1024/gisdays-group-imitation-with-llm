from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.agent import model_evaluation_artifact_registry as registry
from src.agent import model_evaluation_cli as cli
from src.agent.model_evaluation_artifact_contracts import validate_artifact_against_contract
from src.agent.model_evaluation_artifact_validator import (
    MODEL_EVALUATION_ARTIFACT_VALIDATION_REPORT_FILENAME,
)
from src.agent.model_evaluation_compatibility_gate import (
    MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME,
)
from src.agent.model_evaluation_artifact_registry import build_version_payload
from src.agent.model_evaluation_cli import main as model_evaluation_cli_main
from src.agent.model_evaluation_workflow_runner import WORKFLOW_RUN_MANIFEST_FILENAME


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "configs" / "model_evaluation_workflow.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
GOLDEN_DIR = PROJECT_ROOT / "tests" / "fixtures" / "model_evaluation_workflow_golden"


def _load_json(path: Path) -> dict[str, object]:
    return json.loads(path.read_text(encoding="utf-8"))


def _assert_no_tmp_path_leak(payload_text: str, tmp_path: Path) -> None:
    variants = {
        str(tmp_path),
        str(tmp_path).replace("\\", "/"),
        str(tmp_path).replace("\\", "\\\\"),
        tmp_path.as_posix(),
    }
    assert all(variant not in payload_text for variant in variants)


def _run_partial_workflow(tmp_path: Path) -> Path:
    output_dir = tmp_path / "workflow"
    code = model_evaluation_cli_main(
        [
            "run",
            "--model-catalog",
            str(CATALOG_PATH),
            "--scenario",
            SCENARIO_PATH,
            "--output-dir",
            str(output_dir),
            "--workflow-id",
            "unified_cli_validation_source",
        ]
    )
    assert code == 0
    return output_dir


def _explicit_validation_paths(workflow_dir: Path) -> list[str]:
    return [
        "--plan",
        str(workflow_dir / "plan" / "model_comparison_plan.json"),
        "--readiness-report",
        str(workflow_dir / "readiness" / "model_comparison_readiness_report.json"),
        "--scorecard",
        str(workflow_dir / "scorecard" / "model_evaluation_scorecard.json"),
        "--workflow-bundle",
        str(workflow_dir / "bundle" / "model_evaluation_workflow_bundle.json"),
        "--workflow-run-manifest",
        str(workflow_dir / WORKFLOW_RUN_MANIFEST_FILENAME),
    ]


def _captured_json(capsys: pytest.CaptureFixture[str]) -> dict[str, object]:
    captured = capsys.readouterr()
    assert "Traceback" not in captured.err
    return json.loads(captured.out)


def test_version_returns_json_ok(capsys: pytest.CaptureFixture[str]) -> None:
    code = model_evaluation_cli_main(["version"])
    payload = _captured_json(capsys)

    assert code == 0
    assert payload["status"] == "ok"
    assert payload["tool"] == "offline_model_evaluation_cli"
    assert payload["supported_subcommands"] == ["run", "validate", "compatibility", "check", "schema", "version"]
    assert "model_evaluation_workflow_config_v1" in payload["supported_schema_versions"]
    assert "model_evaluation_artifact_validation_v1" in payload["supported_schema_versions"]
    assert "model_evaluation_compatibility_report_v1" in payload["supported_schema_versions"]
    assert payload["no_runtime_execution"] is True
    assert payload == build_version_payload()


def test_check_uses_default_golden_fixture_pack(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = model_evaluation_cli_main(["check", "--output-dir", str(tmp_path / "check")])
    payload = _captured_json(capsys)

    assert code == 0
    assert payload["status"] == "compatible"
    assert payload["check_mode"] == "golden_only"
    assert payload["report_path"] == MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME
    assert (tmp_path / "check" / MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME).is_file()


def test_check_explicit_golden_fixture_dir_works(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = model_evaluation_cli_main(
        [
            "check",
            "--golden-fixture-dir",
            str(GOLDEN_DIR),
            "--output-dir",
            str(tmp_path / "check"),
            "--compatibility-id",
            "explicit_golden_check",
        ]
    )
    payload = _captured_json(capsys)

    assert code == 0
    assert payload["status"] == "compatible"
    assert payload["compatibility_id"] == "explicit_golden_check"


def test_check_compares_generated_workflow_output(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsys.readouterr()
    workflow_dir = _run_partial_workflow(tmp_path)
    capsys.readouterr()

    code = model_evaluation_cli_main(
        [
            "check",
            "--workflow-output-dir",
            str(workflow_dir),
            "--output-dir",
            str(tmp_path / "check"),
        ]
    )
    payload = _captured_json(capsys)

    assert code == 0
    assert payload["status"] == "compatible_with_warnings"
    assert payload["check_mode"] == "golden_plus_workflow_output"
    assert payload["warning_count"] > 0


def test_check_strict_returns_zero_when_no_warnings(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = model_evaluation_cli_main(["check", "--output-dir", str(tmp_path / "check"), "--strict"])
    payload = _captured_json(capsys)

    assert code == 0
    assert payload["status"] == "compatible"
    assert payload["warning_count"] == 0


def test_check_strict_returns_nonzero_on_warnings(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsys.readouterr()
    workflow_dir = _run_partial_workflow(tmp_path)
    capsys.readouterr()

    code = model_evaluation_cli_main(
        [
            "check",
            "--workflow-output-dir",
            str(workflow_dir),
            "--output-dir",
            str(tmp_path / "check"),
            "--strict",
        ]
    )
    payload = _captured_json(capsys)

    assert code == 2
    assert payload["status"] == "compatible_with_warnings"
    assert payload["warning_count"] > 0


def test_check_missing_explicit_golden_fixture_dir_returns_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_golden = tmp_path / "missing_golden"

    code = model_evaluation_cli_main(
        [
            "check",
            "--golden-fixture-dir",
            str(missing_golden),
            "--output-dir",
            str(tmp_path / "check"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "golden_fixture_dir_missing"
    assert payload["check_mode"] == "golden_only"
    assert "Traceback" not in captured.err
    assert str(tmp_path) not in captured.out


def test_check_missing_default_golden_fixture_dir_returns_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(cli, "DEFAULT_GOLDEN_FIXTURE_RELATIVE_PATH", Path("missing_default_golden"))

    code = model_evaluation_cli_main(["check", "--output-dir", str(tmp_path / "check")])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "golden_fixture_dir_missing"
    assert "Traceback" not in captured.err


def test_check_stdout_is_concise_json(tmp_path: Path, capsys: pytest.CaptureFixture[str]) -> None:
    code = model_evaluation_cli_main(["check", "--output-dir", str(tmp_path / "check")])
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

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
    assert "Traceback" not in captured.err


def test_check_report_validates_against_contract(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = model_evaluation_cli_main(["check", "--output-dir", str(tmp_path / "check")])
    payload = _captured_json(capsys)
    report = _load_json(tmp_path / "check" / str(payload["report_path"]))

    assert code == 0
    assert validate_artifact_against_contract(
        report,
        registry.MODEL_EVALUATION_COMPATIBILITY_REPORT,
    ) == []


def test_check_stdout_and_report_do_not_leak_tmp_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = model_evaluation_cli_main(["check", "--output-dir", str(tmp_path / "check")])
    captured = capsys.readouterr()
    report_text = (tmp_path / "check" / MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME).read_text(encoding="utf-8")

    assert code == 0
    _assert_no_tmp_path_leak(captured.out, tmp_path)
    _assert_no_tmp_path_leak(report_text, tmp_path)


def test_check_no_reports_or_experiments_files_are_written(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = model_evaluation_cli_main(["check", "--output-dir", str(tmp_path / "check")])

    assert code == 0
    assert json.loads(capsys.readouterr().out)["status"] == "compatible"
    assert not (PROJECT_ROOT / "reports" / MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / MODEL_EVALUATION_COMPATIBILITY_REPORT_FILENAME).exists()


def test_check_no_gguf_model_probe_browser_or_office_calls_are_made(
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
            raise AssertionError("unified check must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    code = model_evaluation_cli_main(["check", "--output-dir", str(tmp_path / "check")])
    payload = _captured_json(capsys)

    assert code == 0
    assert payload["status"] == "compatible"


def test_run_config_mode_creates_workflow_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "workflow"

    code = model_evaluation_cli_main(
        [
            "run",
            "--config",
            str(EXAMPLE_CONFIG_PATH),
            "--output-dir",
            str(output_dir),
        ]
    )
    payload = _captured_json(capsys)

    assert code == 0
    assert payload["status"] == "partial"
    assert payload["workflow_id"] == "offline_model_eval_example_v1"
    assert payload["candidate_pair_count"] == 2
    assert (output_dir / WORKFLOW_RUN_MANIFEST_FILENAME).is_file()


def test_run_explicit_mode_creates_workflow_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    output_dir = tmp_path / "workflow"

    code = model_evaluation_cli_main(
        [
            "run",
            "--model-catalog",
            str(CATALOG_PATH),
            "--scenario",
            SCENARIO_PATH,
            "--output-dir",
            str(output_dir),
            "--workflow-id",
            "unified_cli_explicit",
        ]
    )
    payload = _captured_json(capsys)

    assert code == 0
    assert payload["status"] == "partial"
    assert payload["workflow_id"] == "unified_cli_explicit"
    assert payload["bundle_path"] == "bundle/model_evaluation_workflow_bundle.json"
    assert (output_dir / "plan" / "model_comparison_plan.json").is_file()


def test_run_rejects_config_mixed_with_explicit_model_catalog(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = model_evaluation_cli_main(
        [
            "run",
            "--config",
            str(EXAMPLE_CONFIG_PATH),
            "--model-catalog",
            str(CATALOG_PATH),
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )
    payload = _captured_json(capsys)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "config_conflicts_with_model_catalog"


def test_run_rejects_missing_scenario_in_explicit_mode(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = model_evaluation_cli_main(
        [
            "run",
            "--model-catalog",
            str(CATALOG_PATH),
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )
    payload = _captured_json(capsys)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "scenario_required"


def test_run_missing_config_returns_no_traceback_or_tmp_path(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_config = tmp_path / "missing_config.json"

    code = model_evaluation_cli_main(
        [
            "run",
            "--config",
            str(missing_config),
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid_input"
    assert payload["error"] == "ModelEvaluationWorkflowConfigError"
    assert "Traceback" not in captured.err
    assert str(tmp_path) not in captured.out
    assert str(tmp_path) not in captured.err


def test_validate_workflow_output_dir_validates_runner_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsys.readouterr()
    workflow_dir = _run_partial_workflow(tmp_path)
    capsys.readouterr()

    code = model_evaluation_cli_main(
        [
            "validate",
            "--workflow-output-dir",
            str(workflow_dir),
            "--output-dir",
            str(tmp_path / "validation"),
            "--validation-id",
            "unified_cli_validation",
        ]
    )
    payload = _captured_json(capsys)

    assert code == 0
    assert payload["status"] == "valid_with_warnings"
    assert payload["validation_id"] == "unified_cli_validation"
    assert payload["report_path"] == MODEL_EVALUATION_ARTIFACT_VALIDATION_REPORT_FILENAME


def test_validate_explicit_paths_validates_runner_artifacts(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsys.readouterr()
    workflow_dir = _run_partial_workflow(tmp_path)
    capsys.readouterr()

    code = model_evaluation_cli_main(
        [
            "validate",
            *_explicit_validation_paths(workflow_dir),
            "--output-dir",
            str(tmp_path / "validation"),
        ]
    )
    payload = _captured_json(capsys)

    assert code == 0
    assert payload["status"] == "valid"
    assert payload["checked_artifact_count"] == 5


def test_validate_strict_returns_nonzero_on_warnings(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    capsys.readouterr()
    workflow_dir = _run_partial_workflow(tmp_path)
    capsys.readouterr()

    code = model_evaluation_cli_main(
        [
            "validate",
            "--workflow-output-dir",
            str(workflow_dir),
            "--output-dir",
            str(tmp_path / "validation"),
            "--strict",
        ]
    )
    payload = _captured_json(capsys)

    assert code == 2
    assert payload["status"] == "valid_with_warnings"
    assert payload["warning_count"] > 0


def test_validate_missing_required_artifact_returns_no_traceback(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    missing_workflow = tmp_path / "missing_workflow"

    code = model_evaluation_cli_main(
        [
            "validate",
            "--workflow-output-dir",
            str(missing_workflow),
            "--output-dir",
            str(tmp_path / "validation"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 2
    assert payload["status"] == "invalid"
    assert "Traceback" not in captured.err
    assert str(tmp_path) not in captured.out


def test_success_stdout_is_concise_json(
    tmp_path: Path,
    capsys: pytest.CaptureFixture[str],
) -> None:
    code = model_evaluation_cli_main(
        [
            "run",
            "--model-catalog",
            str(CATALOG_PATH),
            "--scenario",
            SCENARIO_PATH,
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )
    captured = capsys.readouterr()
    payload = json.loads(captured.out)

    assert code == 0
    assert isinstance(payload, dict)
    assert "artifact_paths" not in payload
    assert "Traceback" not in captured.err


def test_no_reports_or_experiments_files_are_written(tmp_path: Path) -> None:
    model_evaluation_cli_main(
        [
            "run",
            "--model-catalog",
            str(CATALOG_PATH),
            "--scenario",
            SCENARIO_PATH,
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )

    assert not (PROJECT_ROOT / "reports" / WORKFLOW_RUN_MANIFEST_FILENAME).exists()
    assert not (PROJECT_ROOT / "experiments" / WORKFLOW_RUN_MANIFEST_FILENAME).exists()


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
            raise AssertionError("unified offline CLI must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    code = model_evaluation_cli_main(
        [
            "run",
            "--model-catalog",
            str(CATALOG_PATH),
            "--scenario",
            SCENARIO_PATH,
            "--output-dir",
            str(tmp_path / "workflow"),
        ]
    )

    assert code == 0
