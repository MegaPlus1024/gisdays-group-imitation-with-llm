from __future__ import annotations

import builtins
import copy
import importlib
import json
import sys
import types
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_pair_execution_readiness import (
    validate_model_pair_execution_readiness,
    write_model_pair_execution_readiness_summary,
)
from src.agent.model_pair_local_pipeline_entrypoint import (
    build_effective_local_pipeline_model_config_preview,
    build_orchestrator_executor_run_config_from_local_pipeline_config,
    is_runtime_execution_enabled,
    run_local_model_pair_trial,
    validate_local_entrypoint_runtime_config,
)
from src.agent.model_pair_pipeline_entrypoint_wrapper import build_pipeline_entrypoint_input
from src.agent.model_pair_pipeline_result_adapter import adapt_orchestrator_executor_pipeline_result
from src.agent.model_pair_single_trial_execution import (
    ModelPairSingleTrialExecutionConfig,
    run_single_model_pair_trial,
)
from src.agent.model_pair_single_trial_operator_runner import (
    ModelPairSingleTrialOperatorConfig,
    SINGLE_TRIAL_RUNTIME_CONFIRMATION,
    load_entrypoint_from_ref,
    run_single_trial_operator,
)


PAIR_ID = "second_model__to__first_model"
SCENARIO_ID = "office_document_file_workflow_basic_v1"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
LOCAL_ENTRYPOINT_REF = "src.agent.model_pair_local_pipeline_entrypoint:run_local_model_pair_trial"
EXAMPLE_CONFIG_PATH = Path("configs/local_pipeline/single_trial_local_pipeline.example.json")


def _local_pipeline_config(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "mode": "fake",
        "models_config_path": "configs/evaluation_models.json",
        "out_dir": "artifacts/local_pipeline_runs/phase_8_10_test",
        "force": True,
        "execute_actions": False,
        "max_group_steps": 1,
        "max_steps_per_agent": 1,
    }
    payload.update(overrides)
    return payload


def _entrypoint_input(*, allow_runtime: bool | None = False, **overrides: object) -> dict[str, Any]:
    execution_options: dict[str, Any] = {"no_runtime_execution": allow_runtime is not True}
    if allow_runtime is not None:
        execution_options["allow_runtime_execution"] = allow_runtime
    payload: dict[str, Any] = {
        "trial_id": f"{PAIR_ID}__{SCENARIO_ID}__r01",
        "pair_id": PAIR_ID,
        "scenario_id": SCENARIO_ID,
        "scenario_path": SCENARIO_PATH,
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
        "task_summary": "Run one local model-pair entrypoint trial.",
        "expected_outputs": {"checks": [{"type": "status_equals", "expected": "succeeded"}]},
        "tags": ["local_entrypoint_test"],
        "scenario_config": {"scenario_id": SCENARIO_ID, "scenario_path": SCENARIO_PATH, "max_group_steps": 1},
        "role_config": {"agents": [{"agent_id": "office_agent", "role": "fixture"}]},
        "model_bindings": {
            "orchestrator": {"model_id": "second_model", "provider": "explicit_fixture"},
            "executor": {"model_id": "first_model", "provider": "explicit_fixture"},
        },
        "execution_options": execution_options,
        "metadata": {"explicit_runtime_opt_in": allow_runtime is True},
        "local_pipeline_config": _local_pipeline_config(),
    }
    payload.update(overrides)
    return payload


def _event(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "group_step_index": 1,
        "agent_id": "office_agent",
        "task_id": "task_1",
        "action": "office_create_docx",
        "status": "success",
        "summary": "Fake local entrypoint runtime helper selected a safe offline action.",
        "metadata": {"execution_attempted": False, "execution_success": None},
    }
    payload.update(overrides)
    return payload


def _fake_pipeline_result(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "completed",
        "success": True,
        "correctness_score": 0.98,
        "group_history": [_event()],
        "event_history": [_event(action="office_validate_docx")],
        "activity_trace": [_event(action="office_record_summary")],
        "artifacts": [{"path": "artifacts/local_entrypoint/report.docx"}],
        "resource_observation": {
            "runtime_mode": "fake_local_entrypoint",
            "backend": "monkeypatched_local_entrypoint_helper",
            "success": True,
            "wall_time_s": 1.5,
        },
        "warnings": ["fake_helper_does_not_call_llama_server"],
        "notes": ["synthetic_local_entrypoint_pipeline_result"],
        "metadata": {"pipeline": "fake_local_entrypoint"},
        "no_runtime_execution": False,
    }
    payload.update(overrides)
    return payload


def _plan(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "schema_version": "model_comparison_plan_v1",
        "plan_id": "model_pair_local_entrypoint_plan",
        "candidate_pairs": [
            {
                "pair_id": PAIR_ID,
                "orchestrator_model_id": "second_model",
                "executor_model_id": "first_model",
                "tags": ["local_entrypoint_test"],
            }
        ],
        "scenarios": [
            {
                "scenario_id": SCENARIO_ID,
                "scenario_path": SCENARIO_PATH,
                "task_summary": "Run one local model-pair entrypoint trial.",
            }
        ],
        "trials": [
            {
                "trial_id": f"{PAIR_ID}__{SCENARIO_ID}__r01",
                "pair_id": PAIR_ID,
                "scenario_id": SCENARIO_ID,
                "repeat_index": 1,
                "task_summary": "Run one local model-pair entrypoint trial.",
                "expected_outputs": {"checks": [{"type": "status_equals", "expected": "succeeded"}]},
                "tags": ["local_entrypoint_test"],
                "no_runtime_execution": True,
                "local_pipeline_config": _local_pipeline_config(out_dir="artifacts/local_pipeline_runs/operator_test"),
            }
        ],
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
    return {"agents": [{"agent_id": "office_agent", "scenario_id": context["scenario_id"]}]}


def _model_bindings(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "orchestrator": {"model_id": context["orchestrator_model_id"], "provider": "explicit_fixture"},
        "executor": {"model_id": context["executor_model_id"], "provider": "explicit_fixture"},
    }


def _plan_path(tmp_path: Path, plan: dict[str, Any] | None = None) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan or _plan(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def _local_pipeline_config_path(tmp_path: Path, **overrides: object) -> Path:
    payload = _local_pipeline_config(**overrides)
    path = tmp_path / "local_pipeline_config.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _ready_summary_path(tmp_path: Path, plan: dict[str, Any] | None = None) -> Path:
    summary = validate_model_pair_execution_readiness(
        plan or _plan(),
        role_config_resolver=_role_config,
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=_model_bindings,
    )
    return write_model_pair_execution_readiness_summary(summary, tmp_path / "readiness")


def _codes(result: dict[str, Any]) -> set[str]:
    findings = result.get("findings", [])
    if not isinstance(findings, list):
        return set()
    return {finding["code"] for finding in findings if isinstance(finding, dict) and "code" in finding}


def _diagnostics(result: dict[str, Any]) -> dict[str, Any]:
    metadata = result.get("metadata")
    if isinstance(metadata, dict) and isinstance(metadata.get("diagnostics"), dict):
        return metadata["diagnostics"]
    return {}


def _install_fake_existing_pipeline_module(
    monkeypatch: pytest.MonkeyPatch,
    *,
    result: dict[str, Any] | None = None,
    config_raises: bool = False,
    runner_init_raises: bool = False,
    run_raises: bool = False,
) -> list[tuple[str, Any]]:
    calls: list[tuple[str, Any]] = []
    module = types.ModuleType("src.agent.orchestrator_executor_pipeline")

    class FakeRunConfig:
        def __init__(self, payload: dict[str, Any]) -> None:
            self.payload = payload

        @classmethod
        def model_validate(cls, payload: dict[str, Any]) -> "FakeRunConfig":
            calls.append(("config", payload))
            if config_raises:
                raise TypeError("bad config C:\\Users\\Example\\secret\\cfg.json token=SECRET_TOKEN")
            return cls(payload)

    class FakeRunner:
        def __init__(self, config: FakeRunConfig) -> None:
            calls.append(("runner_init", config.payload))
            if runner_init_raises:
                raise RuntimeError("runner init failed api_key=SECRET_KEY")
            self.config = config

        def run(self) -> dict[str, Any]:
            calls.append(("run", self.config.payload))
            if run_raises:
                raise RuntimeError(
                    "runner run failed at C:\\Users\\Example\\run.txt "
                    "token=SECRET_TOKEN raw_prompt=DO_NOT_COPY"
                )
            return result or _fake_pipeline_result()

    module.OrchestratorExecutorRunConfig = FakeRunConfig  # type: ignore[attr-defined]
    module.OrchestratorExecutorRunner = FakeRunner  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, "src.agent.orchestrator_executor_pipeline", module)
    return calls


def test_no_runtime_input_returns_skipped_result() -> None:
    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=False))

    assert result["status"] == "skipped"
    assert result["task_success"] is False
    assert result["error_code"] == "runtime_execution_not_enabled"
    assert result["warnings"] == ["runtime_execution_not_enabled"]
    assert result["metadata"]["entrypoint"] == "run_local_model_pair_trial"
    assert result["metadata"]["no_runtime_execution"] is True
    assert result["no_runtime_execution"] is True


def test_no_runtime_input_does_not_call_existing_pipeline_helper(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    def forbidden(_: dict[str, Any]) -> object:
        raise AssertionError("existing pipeline helper must not run in no-runtime mode")

    monkeypatch.setattr(local_entrypoint, "_run_existing_pipeline_entrypoint", forbidden)

    result = local_entrypoint.run_local_model_pair_trial(_entrypoint_input(allow_runtime=False))

    assert result["status"] == "skipped"


def test_runtime_false_or_missing_is_safe() -> None:
    false_result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=False))
    missing_result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=None))

    assert is_runtime_execution_enabled(_entrypoint_input(allow_runtime=False)) is False
    assert is_runtime_execution_enabled(_entrypoint_input(allow_runtime=None)) is False
    assert false_result["status"] == "skipped"
    assert missing_result["status"] == "skipped"


def test_runtime_true_validation_checks_required_fields() -> None:
    payload = _entrypoint_input(
        allow_runtime=True,
        trial_id="",
        pair_id=None,
        scenario_id="",
        orchestrator_model_id=None,
        executor_model_id="",
    )

    codes = {finding["code"] for finding in validate_local_entrypoint_runtime_config(payload)}

    assert "trial_id_missing" in codes
    assert "pair_id_missing" in codes
    assert "scenario_id_missing" in codes
    assert "orchestrator_model_id_missing" in codes
    assert "executor_model_id_missing" in codes


def test_runtime_true_missing_local_pipeline_config_returns_controlled_missing() -> None:
    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=True, local_pipeline_config=None))

    assert result["status"] == "failed"
    assert result["error_code"] == "local_pipeline_config_missing"
    assert "local_pipeline_config_missing" in _codes(result)
    assert _diagnostics(result)["failure_stage"] == "validation"
    assert "local_pipeline_config" in _diagnostics(result)["required_fields_missing"]


def test_runtime_true_invalid_local_pipeline_config_returns_controlled_invalid() -> None:
    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=True, local_pipeline_config="invalid"))

    assert result["status"] == "failed"
    assert result["error_code"] == "local_pipeline_config_invalid"
    assert "local_pipeline_config_invalid" in _codes(result)
    assert _diagnostics(result)["failure_stage"] == "validation"


def test_local_entrypoint_accepts_nested_extra_config_compatibility_path(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_existing_pipeline_module(monkeypatch)

    result = run_local_model_pair_trial(
        _entrypoint_input(
            allow_runtime=True,
            local_pipeline_config=None,
            extra_config={"local_pipeline_config": _local_pipeline_config()},
        )
    )

    assert result["status"] == "completed"
    assert result["resource_observation"]["backend"] == "monkeypatched_local_entrypoint_helper"


def test_wrapper_lifts_local_pipeline_config_to_entrypoint_input() -> None:
    payload = build_pipeline_entrypoint_input(
        _entrypoint_input(allow_runtime=False, local_pipeline_config=None),
        extra_config={"local_pipeline_config": _local_pipeline_config(run_id="lift_test")},
    )

    assert payload["local_pipeline_config"]["run_id"] == "lift_test"
    assert payload["extra_config"]["local_pipeline_config"]["run_id"] == "lift_test"


def test_wrapper_passes_raw_dual_endpoint_config_without_mutating_input() -> None:
    extra_config = {
        "local_pipeline_config": _local_pipeline_config(
            run_id="dual_endpoint_raw",
            orchestrator_base_url="http://127.0.0.1:8080/v1",
            executor_base_url="http://127.0.0.1:8081/v1",
        )
    }
    before = copy.deepcopy(extra_config)

    payload = build_pipeline_entrypoint_input(
        _entrypoint_input(allow_runtime=False, local_pipeline_config=None),
        extra_config=extra_config,
    )
    payload["local_pipeline_config"]["orchestrator_base_url"] = "changed"

    assert extra_config == before
    assert payload["extra_config"]["local_pipeline_config"]["orchestrator_base_url"] == "http://127.0.0.1:8080/v1"
    assert payload["extra_config"]["local_pipeline_config"]["executor_base_url"] == "http://127.0.0.1:8081/v1"
    assert "htt<absolute_path>" not in json.dumps(payload, ensure_ascii=False)


def test_local_entrypoint_sanitizer_preserves_runtime_urls_and_secret_queries() -> None:
    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    assert local_entrypoint._safe_text("http://127.0.0.1:8080/v1") == "http://127.0.0.1:8080/v1"
    assert local_entrypoint._safe_text("http://127.0.0.1:8081/v1") == "http://127.0.0.1:8081/v1"
    assert local_entrypoint._safe_text("https://example.test/v1") == "https://example.test/v1"
    assert local_entrypoint._safe_text("ws://127.0.0.1:8080/ws") == "ws://127.0.0.1:8080/ws"
    assert (
        local_entrypoint._safe_text("http://host/v1?token=secret")
        == "http://host/v1?token=<redacted_secret>"
    )


def test_example_local_pipeline_config_is_safe_relative_json() -> None:
    payload = json.loads(EXAMPLE_CONFIG_PATH.read_text(encoding="utf-8"))

    assert payload["schema_version"] == "single_trial_local_pipeline_config_v1"
    assert payload["out_dir"].startswith("artifacts/single_trial_runs/")
    assert payload["scenario_path"] == SCENARIO_PATH
    assert payload["execution_options"]["allow_runtime_execution"] is True
    assert payload["execute_actions"] is False
    for key in ("models_config_path", "scenario_path", "out_dir"):
        value = Path(payload[key])
        assert not value.is_absolute()
        assert ".." not in value.parts
    assert "reports" not in Path(payload["out_dir"]).parts
    assert "experiments" not in Path(payload["out_dir"]).parts


def test_runtime_true_does_not_lazy_import_existing_pipeline_before_validation(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_fake_existing_pipeline_module(monkeypatch)

    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=True, scenario_config={}))

    assert result["status"] == "failed"
    assert result["error_code"] == "local_pipeline_config_invalid"
    assert "scenario_config_missing" in _codes(result)
    assert calls == []


def test_runtime_true_lazy_imports_and_calls_existing_pipeline_runner_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_fake_existing_pipeline_module(monkeypatch)

    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))

    assert result["status"] == "completed"
    assert [name for name, _ in calls] == ["config", "runner_init", "run"]


def test_entrypoint_passes_expected_config_shape_to_existing_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_fake_existing_pipeline_module(monkeypatch)
    payload = _entrypoint_input(
        allow_runtime=True,
        local_pipeline_config=_local_pipeline_config(out_dir="artifacts/local_pipeline_runs/shape_test"),
    )

    run_result = run_local_model_pair_trial(payload)
    config_payload = calls[0][1]

    assert run_result["status"] == "completed"
    assert config_payload["mode"] == "fake"
    assert config_payload["scenario_path"] == SCENARIO_PATH
    assert config_payload["orchestrator_model_id"] == "second_model"
    assert config_payload["executor_model_id"] == "first_model"
    assert config_payload["run_id"] == payload["trial_id"]
    assert config_payload["out_dir"] == "artifacts/local_pipeline_runs/shape_test"
    assert config_payload["execute_actions"] is False


def test_config_build_helper_accepts_first_run_packet_local_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_fake_existing_pipeline_module(monkeypatch)
    local_config = json.loads(
        Path("artifacts/first_run_packets/phase_8_13_first/local_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )

    config = build_orchestrator_executor_run_config_from_local_pipeline_config(
        _entrypoint_input(allow_runtime=True, local_pipeline_config=local_config)
    )

    assert config.payload["mode"] == "local"
    assert config.payload["models_config_path"] == "configs/evaluation_models.json"
    assert config.payload["scenario_path"] == SCENARIO_PATH
    assert config.payload["out_dir"] == "artifacts/single_trial_runs/phase_8_11_first/pipeline"
    assert config.payload["orchestrator_model_id"] == "second_model"
    assert config.payload["executor_model_id"] == "first_model"
    assert [name for name, _ in calls] == ["config"]


def test_config_build_helper_accepts_dual_endpoint_controlled_trial_config(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_fake_existing_pipeline_module(monkeypatch)
    local_config = json.loads(
        Path("configs/local_pipeline/single_trial_local_pipeline.dual_endpoint.example.json").read_text(
            encoding="utf-8"
        )
    )
    local_config["prompt_budget"] = {
        "executor_max_prompt_chars": 12000,
        "orchestrator_max_prompt_chars": 16000,
        "max_history_items": 6,
        "compact_executor_context": True,
    }
    local_config["action_parameter_repair"] = {
        "enabled": True,
        "office_default_output_dir": (
            "artifacts/single_trial_runs/phase_8_21_action_repair_retry/"
            "pipeline/workspace/office_outputs"
        ),
    }

    config = build_orchestrator_executor_run_config_from_local_pipeline_config(
        _entrypoint_input(allow_runtime=True, local_pipeline_config=local_config)
    )

    assert config.payload["mode"] == "local"
    assert config.payload["run_id"] == "phase_8_17_dual_endpoint"
    assert config.payload["out_dir"] == "artifacts/single_trial_runs/phase_8_17_dual_endpoint/pipeline"
    assert config.payload["orchestrator_base_url"] == "http://127.0.0.1:8080/v1"
    assert config.payload["executor_base_url"] == "http://127.0.0.1:8081/v1"
    assert config.payload["prompt_budget"]["executor_max_prompt_chars"] == 12000
    assert config.payload["prompt_budget"]["compact_executor_context"] is True
    assert config.payload["action_parameter_repair"]["enabled"] is True
    assert config.payload["action_parameter_repair"]["office_default_output_dir"].endswith(
        "pipeline/workspace/office_outputs"
    )
    assert config.payload["orchestrator_model_id"] == "second_model"
    assert config.payload["executor_model_id"] == "first_model"
    assert [name for name, _ in calls] == ["config"]


def test_effective_config_preview_reports_dual_endpoint_packet_without_runtime() -> None:
    local_config = json.loads(
        Path("artifacts/first_run_packets/phase_8_17_dual_endpoint/local_pipeline_config.json").read_text(
            encoding="utf-8"
        )
    )

    preview = build_effective_local_pipeline_model_config_preview(
        _entrypoint_input(allow_runtime=True, local_pipeline_config=local_config)
    )
    text = json.dumps(preview, ensure_ascii=False)

    assert preview["status"] == "resolved"
    assert preview["orchestrator_model_id"] == "second_model"
    assert preview["executor_model_id"] == "first_model"
    assert preview["orchestrator_base_url"] == "http://127.0.0.1:8080/v1"
    assert preview["executor_base_url"] == "http://127.0.0.1:8081/v1"
    assert preview["orchestrator_api_model"] == "second_model"
    assert preview["executor_api_model"] == "first_model"
    assert preview["shared_endpoint"] is False
    assert preview["no_runtime_execution"] is True
    assert "htt<absolute_path>" not in text


def test_run_config_build_failure_returns_staged_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_existing_pipeline_module(monkeypatch, config_raises=True)

    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))
    text = json.dumps(result, ensure_ascii=False)

    assert result["status"] == "failed"
    assert result["error_code"] == "local_pipeline_run_config_build_failed"
    assert _diagnostics(result)["failure_stage"] == "run_config_build"
    assert _diagnostics(result)["exception_type"] == "TypeError"
    assert "C:\\Users" not in text
    assert "SECRET_TOKEN" not in text
    assert "Traceback" not in text


def test_runner_init_failure_returns_staged_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_existing_pipeline_module(monkeypatch, runner_init_raises=True)

    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))
    text = json.dumps(result, ensure_ascii=False)

    assert result["status"] == "failed"
    assert result["error_code"] == "local_pipeline_runner_init_failed"
    assert _diagnostics(result)["failure_stage"] == "runner_init"
    assert _diagnostics(result)["exception_type"] == "RuntimeError"
    assert "SECRET_KEY" not in text
    assert "Traceback" not in text


def test_runner_run_failure_returns_staged_diagnostics_without_raw_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_existing_pipeline_module(monkeypatch, run_raises=True)

    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))
    text = json.dumps(result, ensure_ascii=False)

    assert result["status"] == "failed"
    assert result["error_code"] == "local_pipeline_runner_run_failed"
    assert _diagnostics(result)["failure_stage"] == "runner_run"
    assert _diagnostics(result)["exception_type"] == "RuntimeError"
    assert "SECRET_TOKEN" not in text
    assert "DO_NOT_COPY" not in text
    assert "raw_prompt" not in text
    assert "C:\\Users" not in text
    assert "Traceback" not in text


def test_result_sanitize_failure_returns_staged_diagnostics_without_raw_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    monkeypatch.setattr(
        local_entrypoint,
        "_run_existing_pipeline_entrypoint",
        lambda _: _fake_pipeline_result(),
    )

    def fail_sanitize(*_: object, **__: object) -> dict[str, Any]:
        raise ValueError(
            "sanitize failed C:\\Users\\Example\\raw.txt "
            "api_key=SECRET_KEY raw_response=DO_NOT_COPY"
        )

    monkeypatch.setattr(local_entrypoint, "_safe_pipeline_result", fail_sanitize)

    result = local_entrypoint.run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))
    text = json.dumps(result, ensure_ascii=False)

    assert result["status"] == "failed"
    assert result["error_code"] == "local_pipeline_result_sanitize_failed"
    assert _diagnostics(result)["failure_stage"] == "sanitize"
    assert _diagnostics(result)["exception_type"] == "ValueError"
    assert "SECRET_KEY" not in text
    assert "DO_NOT_COPY" not in text
    assert "raw_response" not in text
    assert "C:\\Users" not in text
    assert "Traceback" not in text


def test_runtime_true_missing_model_bindings_returns_controlled_failed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_fake_existing_pipeline_module(monkeypatch)

    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=True, model_bindings={}))

    assert result["status"] == "failed"
    assert result["error_code"] == "local_pipeline_config_invalid"
    assert "model_bindings_missing" in _codes(result)
    assert calls == []


def test_runtime_true_missing_scenario_config_returns_controlled_failed_result(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_fake_existing_pipeline_module(monkeypatch)

    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=True, scenario_config={}))

    assert result["status"] == "failed"
    assert result["error_code"] == "local_pipeline_config_invalid"
    assert "scenario_config_missing" in _codes(result)
    assert calls == []


def test_runtime_true_valid_config_calls_monkeypatched_helper_once(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    calls: list[dict[str, Any]] = []

    def fake_helper(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(entrypoint_input)
        return _fake_pipeline_result()

    monkeypatch.setattr(local_entrypoint, "_run_existing_pipeline_entrypoint", fake_helper)
    result = local_entrypoint.run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))

    assert len(calls) == 1
    assert result["status"] == "completed"
    assert result["task_success"] is True
    assert result["resource_observation"]["backend"] == "monkeypatched_local_entrypoint_helper"


def test_monkeypatched_existing_pipeline_success_passes_through_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    monkeypatch.setattr(
        local_entrypoint,
        "_run_existing_pipeline_entrypoint",
        lambda _: _fake_pipeline_result(artifact_dir="artifacts/local_entrypoint"),
    )

    result = local_entrypoint.run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))

    assert result["status"] == "completed"
    assert result["task_success"] is True
    assert result["artifact_refs"] == ["artifacts/local_entrypoint/report.docx", "artifacts/local_entrypoint"]
    assert result["metadata"]["entrypoint"] == "run_local_model_pair_trial"
    assert result["no_runtime_execution"] is False


def test_existing_pipeline_success_result_passes_adapter_with_fake_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_existing_pipeline_module(monkeypatch, result=_fake_pipeline_result())

    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))
    adapted = adapt_orchestrator_executor_pipeline_result(result)

    assert adapted["status"] == "succeeded"
    assert adapted["resource_observation"]["backend"] == "monkeypatched_local_entrypoint_helper"


def test_monkeypatched_existing_pipeline_failure_passes_through_safely(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    monkeypatch.setattr(
        local_entrypoint,
        "_run_existing_pipeline_entrypoint",
        lambda _: _fake_pipeline_result(status="failed", success=False, failure_reason="fake_pipeline_failed"),
    )

    result = local_entrypoint.run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))

    assert result["status"] == "failed"
    assert result["task_success"] is False
    assert result["error_code"] == "fake_pipeline_failed"


def test_monkeypatched_existing_pipeline_failed_result_preserves_safe_error_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    windows_path = "\\".join(["C:", "Users", "Example", "secret", "run.txt"])
    monkeypatch.setattr(
        local_entrypoint,
        "_run_existing_pipeline_entrypoint",
        lambda _: _fake_pipeline_result(
            status="failed",
            success=False,
            group_history=[],
            errors=[
                {
                    "stage": "orchestrator",
                    "error_type": "local_model_http_error",
                    "error_message": (
                        "Request URL is missing protocol for "
                        "http://127.0.0.1:8080/v1/chat/completions "
                        f"{windows_path} token=SECRET_TOKEN raw_prompt=DO_NOT_COPY"
                    ),
                    "diagnostics": {
                        "endpoint_path": "/v1/chat/completions",
                        "api_model": "second_model",
                    },
                }
            ],
            artifact_dir="artifacts/single_trial_runs/phase_8_17_dual_endpoint/pipeline",
        ),
    )

    result = local_entrypoint.run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))
    text = json.dumps(result, ensure_ascii=False)

    assert result["status"] == "failed"
    assert result["error_code"] == "local_model_http_error"
    assert _diagnostics(result)["pipeline_status"] == "failed"
    assert _diagnostics(result)["error_code"] == "local_model_http_error"
    assert _diagnostics(result)["errors"][0]["stage"] == "orchestrator"
    assert _diagnostics(result)["errors"][0]["diagnostics"]["endpoint_path"] == "/v1/chat/completions"
    assert _diagnostics(result)["errors"][0]["diagnostics"]["api_model"] == "second_model"
    assert "http://127.0.0.1:8080/v1/chat/completions" in text
    assert "htt<absolute_path>" not in text
    assert "C:\\Users" not in text
    assert "SECRET_TOKEN" not in text
    assert "DO_NOT_COPY" not in text
    assert "raw_prompt" not in text


def test_existing_pipeline_failed_result_passes_adapter_with_fake_module(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_existing_pipeline_module(
        monkeypatch,
        result=_fake_pipeline_result(status="failed", success=False, failure_reason="fake_pipeline_failed"),
    )

    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))
    adapted = adapt_orchestrator_executor_pipeline_result(result)

    assert result["status"] == "failed"
    assert adapted["status"] == "failed"
    assert adapted["error_code"] == "fake_pipeline_failed"


def test_existing_pipeline_exception_becomes_controlled_failed_result_without_raw_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    marker = "RAW_SECRET_EXCEPTION_DETAIL token=SECRET_TOKEN"

    def fake_helper(_: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError(marker)

    monkeypatch.setattr(local_entrypoint, "_run_existing_pipeline_entrypoint", fake_helper)
    result = local_entrypoint.run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))
    text = json.dumps(result, ensure_ascii=False)

    assert result["status"] == "failed"
    assert result["error_code"] == "local_pipeline_entrypoint_failed"
    assert _diagnostics(result)["failure_stage"] == "entrypoint"
    assert _diagnostics(result)["exception_type"] == "RuntimeError"
    assert marker not in text
    assert "SECRET_TOKEN" not in text
    assert "Traceback" not in text


def test_existing_pipeline_runner_exception_becomes_controlled_failed_without_raw_leak(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    _install_fake_existing_pipeline_module(monkeypatch, run_raises=True)

    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))
    text = json.dumps(result, ensure_ascii=False)

    assert result["status"] == "failed"
    assert result["error_code"] == "local_pipeline_runner_run_failed"
    assert _diagnostics(result)["failure_stage"] == "runner_run"
    assert "DO_NOT_COPY" not in text
    assert "raw_prompt" not in text
    assert "SECRET_TOKEN" not in text
    assert "Traceback" not in text


def test_returned_shape_is_accepted_by_pipeline_result_adapter() -> None:
    no_runtime = adapt_orchestrator_executor_pipeline_result(
        run_local_model_pair_trial(_entrypoint_input(allow_runtime=False))
    )
    runtime = adapt_orchestrator_executor_pipeline_result(_fake_pipeline_result())

    assert no_runtime["status"] == "skipped"
    assert no_runtime["task_success"] is False
    assert runtime["status"] == "succeeded"


def test_entrypoint_loads_from_guarded_operator_ref() -> None:
    entrypoint = load_entrypoint_from_ref(LOCAL_ENTRYPOINT_REF)

    result = entrypoint(_entrypoint_input(allow_runtime=False))

    assert result["status"] == "skipped"
    assert result["error_code"] == "runtime_execution_not_enabled"


def test_entrypoint_works_through_guarded_operator_runner_no_runtime(tmp_path: Path) -> None:
    plan = _plan()
    result = run_single_trial_operator(
        ModelPairSingleTrialOperatorConfig(
            plan_path=_plan_path(tmp_path, plan),
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
            entrypoint_ref=LOCAL_ENTRYPOINT_REF,
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
        )
    )

    assert result["status"] == "skipped"
    assert result["no_runtime_execution"] is True
    assert result["trial_result"]["error_code"] == "runtime_execution_not_enabled"


def test_entrypoint_works_through_single_trial_stack_with_monkeypatched_runtime_helper(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    plan = _plan()
    calls: list[dict[str, Any]] = []

    def fake_helper(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(entrypoint_input)
        return _fake_pipeline_result()

    monkeypatch.setattr(local_entrypoint, "_run_existing_pipeline_entrypoint", fake_helper)
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=local_entrypoint.run_local_model_pair_trial,
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single_runtime_fake",
            trial_id=plan["trials"][0]["trial_id"],
            allow_runtime_execution=True,
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
            role_config_resolver=_role_config,
            scenario_config_resolver=_scenario_config,
            model_binding_resolver=_model_bindings,
            extra_config={
                "local_pipeline_config": _local_pipeline_config(
                    orchestrator_base_url="http://127.0.0.1:8080/v1",
                    executor_base_url="http://127.0.0.1:8081/v1",
                )
            },
        ),
    )

    assert result["status"] == "succeeded"
    assert result["no_runtime_execution"] is False
    assert len(calls) == 1
    assert calls[0]["execution_options"]["allow_runtime_execution"] is True
    assert calls[0]["local_pipeline_config"]["out_dir"] == "artifacts/local_pipeline_runs/phase_8_10_test"
    assert calls[0]["local_pipeline_config"]["orchestrator_base_url"] == "http://127.0.0.1:8080/v1"
    assert calls[0]["local_pipeline_config"]["executor_base_url"] == "http://127.0.0.1:8081/v1"


def test_guarded_operator_runner_runtime_path_uses_fake_existing_pipeline_only(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    calls = _install_fake_existing_pipeline_module(monkeypatch)
    plan = _plan()

    result = run_single_trial_operator(
        ModelPairSingleTrialOperatorConfig(
            plan_path=_plan_path(tmp_path, plan),
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
            entrypoint_ref=LOCAL_ENTRYPOINT_REF,
            local_pipeline_config_path=_local_pipeline_config_path(tmp_path),
            output_dir=tmp_path / "single_operator_runtime_fake",
            trial_id=plan["trials"][0]["trial_id"],
            allow_runtime_execution=True,
            confirm_runtime_execution=SINGLE_TRIAL_RUNTIME_CONFIRMATION,
        )
    )

    assert result["status"] == "succeeded"
    assert result["no_runtime_execution"] is False
    assert [name for name, _ in calls] == ["config", "runner_init", "run"]


def test_raw_prompt_response_fields_are_not_copied(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    marker = "RAW_PROMPT_RESPONSE_MARKER_SHOULD_NOT_COPY"
    monkeypatch.setattr(
        local_entrypoint,
        "_run_existing_pipeline_entrypoint",
        lambda _: _fake_pipeline_result(
            group_history=[_event(raw_prompt=marker, raw_response=marker, raw_model_output=marker)],
            metadata={"raw_prompt": marker, "raw_response": marker},
        ),
    )

    result = local_entrypoint.run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))
    text = json.dumps(result, ensure_ascii=False)

    assert marker not in text
    assert "raw_prompt" not in text
    assert "raw_response" not in text


def test_absolute_paths_are_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    windows_path = "\\".join(["C:", "Users", "Example", "secret", "artifact.txt"])
    monkeypatch.setattr(
        local_entrypoint,
        "_run_existing_pipeline_entrypoint",
        lambda _: _fake_pipeline_result(group_history=[_event(summary=f"opened {windows_path}")]),
    )

    result = local_entrypoint.run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))
    text = json.dumps(result, ensure_ascii=False)

    assert windows_path not in text
    assert "<absolute_path>" in text


def test_embedded_http_urls_are_not_mangled_by_path_redaction(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    windows_path = "\\".join(["C:", "Users", "Example", "secret", "artifact.txt"])
    monkeypatch.setattr(
        local_entrypoint,
        "_run_existing_pipeline_entrypoint",
        lambda _: _fake_pipeline_result(
            group_history=[
                _event(
                    summary=(
                        "Client error '400 Bad Request' for url "
                        "'http://127.0.0.1:8080/v1/chat/completions' "
                        f"while reading {windows_path} token=SECRET_TOKEN"
                    )
                )
            ]
        ),
    )

    result = local_entrypoint.run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))
    text = json.dumps(result, ensure_ascii=False)

    assert "http://127.0.0.1:8080/v1/chat/completions" in text
    assert "htt<absolute_path>" not in text
    assert windows_path not in text
    assert "SECRET_TOKEN" not in text


def test_secret_like_text_is_redacted(monkeypatch: pytest.MonkeyPatch) -> None:
    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    monkeypatch.setattr(
        local_entrypoint,
        "_run_existing_pipeline_entrypoint",
        lambda _: _fake_pipeline_result(warnings=["token=SECRET_TOKEN"], notes=["api_key=SECRET_KEY"]),
    )

    result = local_entrypoint.run_local_model_pair_trial(_entrypoint_input(allow_runtime=True))
    text = json.dumps(result, ensure_ascii=False)

    assert "SECRET_TOKEN" not in text
    assert "SECRET_KEY" not in text
    assert "<redacted_secret>" in text


def test_no_model_http_llama_browser_office_imports_or_gguf_reads(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_exists = Path.exists
    original_read_text = Path.read_text
    original_import = builtins.__import__

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
            "win32com",
        }:
            raise AssertionError("local entrypoint must not import runtime clients")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr(builtins, "__import__", forbid_runtime_import)

    import src.agent.model_pair_local_pipeline_entrypoint as local_entrypoint

    importlib.reload(local_entrypoint)
    result = local_entrypoint.run_local_model_pair_trial(_entrypoint_input(allow_runtime=False))

    assert result["status"] == "skipped"
    assert result["no_runtime_execution"] is True


def test_no_reports_or_experiments_are_written(monkeypatch: pytest.MonkeyPatch) -> None:
    original_write_text = Path.write_text

    def forbid_reports_or_experiments_write(self: Path, *args: object, **kwargs: object) -> int:
        if "reports" in self.parts or "experiments" in self.parts:
            raise AssertionError("unexpected reports/experiments write")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", forbid_reports_or_experiments_write)

    result = run_local_model_pair_trial(_entrypoint_input(allow_runtime=False))

    assert result["status"] == "skipped"
