from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent import model_evaluation_artifact_contracts as contracts
from src.agent import model_evaluation_artifact_registry as registry
from src.agent.model_pair_execution_readiness import (
    MODEL_PAIR_EXECUTION_READINESS_SUMMARY_FILENAME,
    MODEL_PAIR_EXECUTION_READINESS_SCHEMA_VERSION,
    ModelPairExecutionReadinessConfig,
    validate_model_pair_execution_readiness,
    write_model_pair_execution_readiness_summary,
)
from src.agent.model_pair_pipeline_entrypoint_wrapper import build_pipeline_entrypoint_input


PAIR_ID = "second_model__to__first_model"
SCENARIO_ID = "office_document_file_workflow_basic_v1"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"


def _plan(*, repetitions: int = 1, **overrides: object) -> dict[str, Any]:
    trials = [
        {
            "trial_id": f"{PAIR_ID}__{SCENARIO_ID}__r{index:02d}",
            "pair_id": PAIR_ID,
            "scenario_id": SCENARIO_ID,
            "repeat_index": index,
            "task_summary": "Validate controlled real-execution readiness.",
            "expected_outputs": {"checks": [{"type": "status_equals", "expected": "succeeded"}]},
            "tags": ["readiness_test"],
            "no_runtime_execution": True,
        }
        for index in range(1, repetitions + 1)
    ]
    payload: dict[str, Any] = {
        "schema_version": "model_comparison_plan_v1",
        "plan_id": "model_pair_execution_readiness_plan",
        "candidate_pairs": [
            {
                "pair_id": PAIR_ID,
                "orchestrator_model_id": "second_model",
                "executor_model_id": "first_model",
                "tags": ["readiness_test"],
            }
        ],
        "scenarios": [
            {
                "scenario_id": SCENARIO_ID,
                "scenario_path": SCENARIO_PATH,
                "task_summary": "Validate controlled real-execution readiness.",
            }
        ],
        "trials": trials,
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _scenario_config(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "scenario_id": context["scenario_id"],
        "scenario_path": context["scenario_path"],
        "max_group_steps": 1,
    }


def _role_config(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "agents": [
            {
                "agent_id": "office_agent",
                "role": "offline_fixture",
                "scenario_id": context["scenario_id"],
            }
        ]
    }


def _model_bindings(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "orchestrator": {
            "model_id": context["orchestrator_model_id"],
            "provider": "explicit_fixture",
        },
        "executor": {
            "model_id": context["executor_model_id"],
            "provider": "explicit_fixture",
        },
    }


def _codes(summary: dict[str, Any]) -> set[str]:
    return {finding["code"] for finding in summary["findings"]}


def _findings(summary: dict[str, Any], code: str) -> list[dict[str, Any]]:
    return [finding for finding in summary["findings"] if finding["code"] == code]


def test_ready_plan_with_fake_resolvers_returns_ready() -> None:
    summary = validate_model_pair_execution_readiness(
        _plan(),
        role_config_resolver=_role_config,
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=_model_bindings,
    )

    assert summary["schema_version"] == MODEL_PAIR_EXECUTION_READINESS_SCHEMA_VERSION
    assert summary["status"] == "ready"
    assert summary["trial_count"] == 1
    assert summary["ready_trial_count"] == 1
    assert summary["not_ready_trial_count"] == 0
    assert summary["model_pair_count"] == 1
    assert summary["scenario_count"] == 1
    assert summary["warnings"] == []
    assert summary["no_runtime_execution"] is True


def test_missing_model_binding_returns_not_ready() -> None:
    summary = validate_model_pair_execution_readiness(
        _plan(),
        scenario_config_resolver=_scenario_config,
    )

    assert summary["status"] == "not_ready"
    assert "model_binding_missing" in _codes(summary)


def test_missing_orchestrator_binding_is_detected() -> None:
    def bindings(context: dict[str, Any]) -> dict[str, Any]:
        return {"executor": {"model_id": context["executor_model_id"]}}

    summary = validate_model_pair_execution_readiness(
        _plan(),
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=bindings,
    )

    assert summary["status"] == "not_ready"
    assert "orchestrator_binding_missing" in _codes(summary)


def test_missing_executor_binding_is_detected() -> None:
    def bindings(context: dict[str, Any]) -> dict[str, Any]:
        return {"orchestrator": {"model_id": context["orchestrator_model_id"]}}

    summary = validate_model_pair_execution_readiness(
        _plan(),
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=bindings,
    )

    assert summary["status"] == "not_ready"
    assert "executor_binding_missing" in _codes(summary)


def test_missing_scenario_config_is_detected_when_required() -> None:
    summary = validate_model_pair_execution_readiness(
        _plan(),
        model_binding_resolver=_model_bindings,
    )

    assert summary["status"] == "not_ready"
    assert "scenario_config_missing" in _codes(summary)


def test_missing_role_config_is_warning_and_ready_by_default() -> None:
    summary = validate_model_pair_execution_readiness(
        _plan(),
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=_model_bindings,
    )

    assert summary["status"] == "ready"
    assert "role_config_missing" in _codes(summary)
    assert "role_config_missing" in summary["warnings"]
    assert _findings(summary, "role_config_missing")[0]["severity"] == "warning"


def test_role_config_required_mode_detects_missing_role_config() -> None:
    summary = validate_model_pair_execution_readiness(
        _plan(),
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=_model_bindings,
        config=ModelPairExecutionReadinessConfig(require_role_config=True),
    )

    assert summary["status"] == "not_ready"
    assert _findings(summary, "role_config_missing")[0]["severity"] == "error"


def test_resolvers_are_called_once_per_trial_where_needed() -> None:
    calls = {"scenario": 0, "role": 0, "bindings": 0}

    def scenario(context: dict[str, Any]) -> dict[str, Any]:
        calls["scenario"] += 1
        return _scenario_config(context)

    def role(context: dict[str, Any]) -> dict[str, Any]:
        calls["role"] += 1
        return _role_config(context)

    def bindings(context: dict[str, Any]) -> dict[str, Any]:
        calls["bindings"] += 1
        return _model_bindings(context)

    summary = validate_model_pair_execution_readiness(
        _plan(repetitions=2),
        role_config_resolver=role,
        scenario_config_resolver=scenario,
        model_binding_resolver=bindings,
    )

    assert summary["status"] == "ready"
    assert calls == {"scenario": 2, "role": 2, "bindings": 2}


def test_resolver_exception_becomes_controlled_finding_without_traceback() -> None:
    def scenario(_: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("RAW_SECRET_EXCEPTION_DETAIL token=SECRET_TOKEN")

    summary = validate_model_pair_execution_readiness(
        _plan(),
        role_config_resolver=_role_config,
        scenario_config_resolver=scenario,
        model_binding_resolver=_model_bindings,
    )
    text = json.dumps(summary, ensure_ascii=False)

    assert summary["status"] == "not_ready"
    assert "scenario_config_resolver_failed" in _codes(summary)
    assert "RAW_SECRET_EXCEPTION_DETAIL" not in text
    assert "SECRET_TOKEN" not in text
    assert "Traceback" not in text


def test_entrypoint_input_is_built_but_pipeline_entrypoint_is_not_called(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agent.model_pair_execution_readiness as readiness_module

    calls = {"build": 0, "pipeline": 0}

    def tracked_build(*args: object, **kwargs: object) -> dict[str, Any]:
        calls["build"] += 1
        return build_pipeline_entrypoint_input(*args, **kwargs)

    def pipeline_entrypoint(_: dict[str, Any]) -> dict[str, Any]:
        calls["pipeline"] += 1
        raise AssertionError("pipeline entrypoint must not be called")

    monkeypatch.setattr(readiness_module, "build_pipeline_entrypoint_input", tracked_build)
    _ = pipeline_entrypoint

    summary = readiness_module.validate_model_pair_execution_readiness(
        _plan(),
        role_config_resolver=_role_config,
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=_model_bindings,
    )

    assert summary["status"] == "ready"
    assert calls == {"build": 1, "pipeline": 0}


def test_allow_runtime_execution_false_keeps_no_runtime_execution() -> None:
    summary = validate_model_pair_execution_readiness(
        _plan(),
        role_config_resolver=_role_config,
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=_model_bindings,
        config=ModelPairExecutionReadinessConfig(allow_runtime_execution=False),
    )

    assert summary["allow_runtime_execution"] is False
    assert summary["no_runtime_execution"] is True


def test_allow_runtime_execution_true_is_explicit_but_still_no_runtime_execution() -> None:
    summary = validate_model_pair_execution_readiness(
        _plan(),
        role_config_resolver=_role_config,
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=_model_bindings,
        config=ModelPairExecutionReadinessConfig(allow_runtime_execution=True, tags=("real_opt_in_check",)),
    )

    assert summary["status"] == "ready"
    assert summary["allow_runtime_execution"] is True
    assert summary["no_runtime_execution"] is True
    assert "runtime_opt_in_explicit" in _codes(summary)
    assert summary["tags"] == ["real_opt_in_check"]


def test_summary_redacts_absolute_windows_paths() -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "secret", "trial.json"])
    plan = _plan()
    plan["trials"][0]["trial_id"] = windows_path

    summary = validate_model_pair_execution_readiness(
        plan,
        scenario_config_resolver=_scenario_config,
    )
    text = json.dumps(summary, ensure_ascii=False)

    assert windows_path not in text
    assert "<absolute_path>" in text


def test_summary_redacts_absolute_posix_paths() -> None:
    posix_path = "/home/example/secret/trial.json"
    plan = _plan()
    plan["trials"][0]["trial_id"] = posix_path

    summary = validate_model_pair_execution_readiness(
        plan,
        scenario_config_resolver=_scenario_config,
    )
    text = json.dumps(summary, ensure_ascii=False)

    assert posix_path not in text
    assert "<absolute_path>" in text


def test_summary_redacts_secret_like_values() -> None:
    plan = _plan()
    plan["trials"][0]["trial_id"] = "trial token=SECRET_TOKEN"

    summary = validate_model_pair_execution_readiness(
        plan,
        scenario_config_resolver=_scenario_config,
    )
    text = json.dumps(summary, ensure_ascii=False)

    assert "SECRET_TOKEN" not in text
    assert "<redacted_secret>" in text


def test_writer_creates_readiness_summary_json(tmp_path: Path) -> None:
    summary = validate_model_pair_execution_readiness(
        _plan(),
        role_config_resolver=_role_config,
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=_model_bindings,
    )

    path = write_model_pair_execution_readiness_summary(summary, tmp_path / "readiness")
    payload = json.loads(path.read_text(encoding="utf-8"))

    assert path == tmp_path / "readiness" / MODEL_PAIR_EXECUTION_READINESS_SUMMARY_FILENAME
    assert payload["schema_version"] == MODEL_PAIR_EXECUTION_READINESS_SCHEMA_VERSION
    assert payload["status"] == "ready"


def test_registry_and_contracts_include_readiness_artifact_type() -> None:
    info = registry.get_artifact_schema_info(registry.MODEL_PAIR_EXECUTION_READINESS_SUMMARY)
    summary = validate_model_pair_execution_readiness(
        _plan(),
        role_config_resolver=_role_config,
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=_model_bindings,
    )
    issues = contracts.validate_artifact_against_contract(
        summary,
        registry.MODEL_PAIR_EXECUTION_READINESS_SUMMARY,
    )

    assert info.schema_version == MODEL_PAIR_EXECUTION_READINESS_SCHEMA_VERSION
    assert info.default_filename == MODEL_PAIR_EXECUTION_READINESS_SUMMARY_FILENAME
    assert issues == []


def test_no_public_cli_live_mode_added() -> None:
    from src.agent.model_pair_matrix_runner_cli import build_parser

    help_text = build_parser().format_help()

    assert "--pipeline-entrypoint" not in help_text
    assert "--allow-runtime-execution" not in help_text
    assert "--orchestrator-base-url" not in help_text
    assert "--executor-base-url" not in help_text


def test_no_reports_or_experiments_files_are_written(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_write_text = Path.write_text

    def forbid_reports_or_experiments_write(self: Path, *args: object, **kwargs: object) -> int:
        if "reports" in self.parts or "experiments" in self.parts:
            raise AssertionError("unexpected reports/experiments write")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", forbid_reports_or_experiments_write)
    summary = validate_model_pair_execution_readiness(
        _plan(),
        role_config_resolver=_role_config,
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=_model_bindings,
    )

    path = write_model_pair_execution_readiness_summary(summary, tmp_path / "readiness")

    assert path.is_file()
    with pytest.raises(ValueError, match="output_dir_forbidden"):
        write_model_pair_execution_readiness_summary(summary, Path("reports") / "readiness")


def test_no_model_http_llama_browser_office_imports_or_gguf_reads(
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
        if name.split(".", maxsplit=1)[0] in {
            "httpx",
            "requests",
            "openai",
            "playwright",
            "selenium",
            "torch",
            "llama_cpp",
            "docx",
            "openpyxl",
            "pptx",
        }:
            raise AssertionError("readiness validation must stay data-only")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    import src.agent.model_pair_execution_readiness as readiness_module

    importlib.reload(readiness_module)
    summary = readiness_module.validate_model_pair_execution_readiness(
        _plan(),
        role_config_resolver=_role_config,
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=_model_bindings,
    )

    assert summary["status"] == "ready"
    assert summary["no_runtime_execution"] is True
