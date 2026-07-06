from __future__ import annotations

import copy
import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_catalog import load_model_catalog
from src.agent.model_comparison_plan import ModelComparisonPlanConfig, build_model_comparison_plan
from src.agent.model_pair_matrix_adapters import (
    build_normality_inputs_from_matrix_run_summary,
    build_resource_observations_from_matrix_run_summary,
)
from src.agent.model_pair_matrix_runner import (
    ModelPairTrialExecutionRequest,
    build_trial_execution_requests_from_plan,
    run_model_pair_matrix,
)
from src.agent.model_pair_pipeline_bridge import (
    build_pipeline_trial_context,
    make_model_pair_pipeline_callable,
)
from src.agent.model_pair_pipeline_entrypoint_wrapper import (
    build_pipeline_entrypoint_input,
    make_explicit_pipeline_entrypoint_callable,
    make_model_pair_entrypoint_executor,
)
from src.agent.model_pair_pipeline_executor import InjectedPipelineModelPairTrialExecutor
from src.agent.model_resource_evaluation import summarize_model_resource_observations
from src.agent.model_task_correctness_evaluation import (
    build_correctness_inputs_from_matrix_run_summary,
    evaluate_task_correctness_batch,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CATALOG_PATH = PROJECT_ROOT / "configs" / "model_catalog.example.json"
SCENARIO_PATH = "configs/multi_agent_scenarios/office_document_file_workflow_basic_v1.json"
PAIR_ID = "second_model__to__first_model"
SCENARIO_ID = "office_document_file_workflow_basic_v1"


def _plan_payload(**overrides: object) -> dict[str, Any]:
    config = ModelComparisonPlanConfig.model_validate(
        {
            "plan_id": "pipeline_entrypoint_wrapper_plan",
            "include_self_pairs": False,
            "repetitions_per_pair": 1,
            "tags": ["pipeline_entrypoint_wrapper_test"],
            **overrides,
        }
    )
    plan = build_model_comparison_plan(
        load_model_catalog(CATALOG_PATH),
        [SCENARIO_PATH],
        config,
        project_root=PROJECT_ROOT,
    ).model_dump(mode="json")
    plan["trials"][0]["task_summary"] = "Run an explicit fake entrypoint wrapper trial."
    plan["trials"][0]["expected_outputs"] = {
        "checks": [{"type": "status_equals", "expected": "succeeded"}],
    }
    plan["trials"][0]["tags"] = ["entrypoint_wrapper", "offline"]
    return plan


def _request() -> ModelPairTrialExecutionRequest:
    return build_trial_execution_requests_from_plan(
        _plan_payload(),
        execution_mode="injected_pipeline",
    )[0]


def _context() -> dict[str, Any]:
    return build_pipeline_trial_context(_request())


def _event(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "group_step_index": 1,
        "agent_id": "office_agent",
        "task_id": "task_1",
        "action": "office_create_docx",
        "status": "success",
        "summary": "Fake entrypoint selected a safe offline action.",
        "metadata": {"execution_attempted": False, "execution_success": None},
    }
    payload.update(overrides)
    return payload


def _fake_pipeline_result(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "completed",
        "success": True,
        "correctness_score": 0.93,
        "group_history": [_event()],
        "event_history": [_event(action="office_validate_docx")],
        "activity_trace": [_event(action="office_record_summary")],
        "artifacts": [{"path": "artifacts/entrypoint_wrapper/report.docx"}],
        "resource_observation": {
            "runtime_mode": "fake_pipeline_entrypoint_wrapper",
            "backend": "explicit_entrypoint_fake",
            "success": True,
            "wall_time_s": 1.7,
        },
        "warnings": ["fake_entrypoint_does_not_call_llama_server"],
        "notes": ["synthetic_entrypoint_wrapper_pipeline_result"],
        "metadata": {"pipeline": "fake_entrypoint"},
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def test_build_input_maps_ids_model_pair_scenario_and_task_fields() -> None:
    payload = build_pipeline_entrypoint_input(_context())

    assert payload["trial_id"].endswith("__r01")
    assert payload["scenario_id"] == SCENARIO_ID
    assert payload["scenario_path"] == SCENARIO_PATH
    assert payload["pair_id"] == PAIR_ID
    assert payload["orchestrator_model_id"] == "second_model"
    assert payload["executor_model_id"] == "first_model"
    assert payload["model_pair"]["pair_id"] == PAIR_ID
    assert payload["model_pair"]["orchestrator_model_id"] == "second_model"
    assert payload["model_pair"]["executor_model_id"] == "first_model"
    assert payload["scenario_config"]["scenario_id"] == SCENARIO_ID
    assert payload["task_summary"] == "Run an explicit fake entrypoint wrapper trial."
    assert payload["expected_outputs"]["checks"][0]["type"] == "status_equals"
    assert payload["tags"] == ["entrypoint_wrapper", "offline"]


def test_default_runtime_flags_are_offline_only() -> None:
    payload = build_pipeline_entrypoint_input(_context())

    assert payload["execution_options"]["allow_runtime_execution"] is False
    assert payload["execution_options"]["no_runtime_execution"] is True
    assert payload["execution_options"]["context_no_runtime_execution"] is True
    assert payload["metadata"]["explicit_runtime_opt_in"] is False


def test_build_input_does_not_mutate_context() -> None:
    context = _context()
    before = copy.deepcopy(context)

    build_pipeline_entrypoint_input(context)

    assert context == before


def test_build_input_redacts_absolute_paths_secret_text_and_raw_fields() -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "secret", "scenario.json"])
    posix_path = "/home/example/secret/scenario.json"
    marker = "RAW_PROMPT_RESPONSE_MARKER_SHOULD_NOT_COPY"
    context = {
        **_context(),
        "scenario_path": windows_path,
        "task_summary": f"Read {posix_path} with token=SECRET_TOKEN",
        "tags": [f"opened {windows_path}"],
        "expected_outputs": {
            "raw_prompt": marker,
            "checks": [{"type": "status_equals", "expected": "succeeded"}],
        },
        "metadata": {
            "raw_response": marker,
            "api_key": marker,
            "note": "safe api_key=SECRET_TOKEN",
        },
    }

    text = json.dumps(build_pipeline_entrypoint_input(context), ensure_ascii=False)

    assert windows_path not in text
    assert posix_path not in text
    assert marker not in text
    assert "SECRET_TOKEN" not in text
    assert "raw_prompt" not in text
    assert "raw_response" not in text
    assert "<absolute_path>" in text
    assert "<redacted_secret>" in text


def test_resolvers_are_called_only_when_provided() -> None:
    calls: list[str] = []
    context = _context()

    without_resolvers = build_pipeline_entrypoint_input(context)

    assert calls == []
    assert without_resolvers["role_config"] == {}
    assert without_resolvers["scenario_config"]["scenario_id"] == SCENARIO_ID
    assert without_resolvers["model_bindings"]["orchestrator"]["model_id"] == "second_model"

    def role_resolver(seen: dict[str, Any]) -> dict[str, Any]:
        calls.append(f"role:{seen['trial_id']}")
        return {"agents": [{"agent_id": "office_agent", "role": "fixture"}]}

    def scenario_resolver(seen: dict[str, Any]) -> dict[str, Any]:
        calls.append(f"scenario:{seen['scenario_id']}")
        return {"scenario_id": seen["scenario_id"], "max_group_steps": 1}

    def binding_resolver(seen: dict[str, Any]) -> dict[str, Any]:
        calls.append(f"binding:{seen['pair_id']}")
        return {
            "orchestrator": {"model_id": seen["orchestrator_model_id"]},
            "executor": {"model_id": seen["executor_model_id"]},
        }

    with_resolvers = build_pipeline_entrypoint_input(
        context,
        role_config_resolver=role_resolver,
        scenario_config_resolver=scenario_resolver,
        model_binding_resolver=binding_resolver,
    )

    assert calls == [
        f"scenario:{SCENARIO_ID}",
        f"role:{context['trial_id']}",
        f"binding:{PAIR_ID}",
    ]
    assert with_resolvers["role_config"]["agents"][0]["agent_id"] == "office_agent"
    assert with_resolvers["scenario_config"]["max_group_steps"] == 1
    assert with_resolvers["model_bindings"]["executor"]["model_id"] == "first_model"


def test_wrapper_calls_fake_entrypoint_once_with_entrypoint_input_and_returns_result_unchanged() -> None:
    calls: list[dict[str, Any]] = []
    fake_result = _fake_pipeline_result()

    def entrypoint(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        assert isinstance(entrypoint_input, dict)
        assert not isinstance(entrypoint_input, ModelPairTrialExecutionRequest)
        assert "execution_options" in entrypoint_input
        assert "task_summary" in entrypoint_input
        calls.append(entrypoint_input)
        return fake_result

    returned = make_explicit_pipeline_entrypoint_callable(entrypoint)(_context())

    assert returned is fake_result
    assert len(calls) == 1
    assert calls[0]["pair_id"] == PAIR_ID
    assert calls[0]["metadata"]["wrapper"] == "model_pair_pipeline_entrypoint_wrapper"


def test_runtime_opt_in_must_be_explicit_at_wrapper_construction() -> None:
    calls: list[dict[str, Any]] = []

    def entrypoint(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(entrypoint_input)
        return _fake_pipeline_result(no_runtime_execution=False)

    wrapped = make_explicit_pipeline_entrypoint_callable(entrypoint, allow_runtime_execution=True)

    wrapped(_context())

    assert calls[0]["execution_options"]["allow_runtime_execution"] is True
    assert calls[0]["execution_options"]["no_runtime_execution"] is False
    assert calls[0]["metadata"]["explicit_runtime_opt_in"] is True
    assert calls[0]["metadata"]["runtime_opt_in_source"] == "programmatic_wrapper_construction"


def test_programmatic_composition_with_model_pair_pipeline_callable() -> None:
    seen: list[dict[str, Any]] = []

    def entrypoint(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        seen.append(entrypoint_input)
        return _fake_pipeline_result()

    normalized = make_model_pair_pipeline_callable(
        make_explicit_pipeline_entrypoint_callable(entrypoint)
    )(_request())

    assert len(seen) == 1
    assert seen[0]["execution_options"]["allow_runtime_execution"] is False
    assert normalized["status"] == "succeeded"
    assert normalized["task_success"] is True
    assert normalized["resource_observation"]["backend"] == "explicit_entrypoint_fake"


def test_programmatic_composition_with_injected_executor() -> None:
    executor = InjectedPipelineModelPairTrialExecutor(
        make_model_pair_pipeline_callable(
            make_explicit_pipeline_entrypoint_callable(lambda _: _fake_pipeline_result())
        )
    )

    result = executor.execute_trial(_request())

    assert result.status == "succeeded"
    assert result.task_success is True
    assert result.correctness_score == pytest.approx(0.93)
    assert result.group_history[0]["action"] == "office_create_docx"


def test_helper_builds_entrypoint_executor() -> None:
    executor = make_model_pair_entrypoint_executor(lambda _: _fake_pipeline_result())

    result = executor.execute_trial(_request())

    assert result.status == "succeeded"
    assert result.resource_observation is not None
    assert result.resource_observation["runtime_mode"] == "fake_pipeline_entrypoint_wrapper"


def test_entrypoint_executor_works_in_run_model_pair_matrix() -> None:
    summary = run_model_pair_matrix(
        _plan_payload(repetitions_per_pair=2),
        make_model_pair_entrypoint_executor(lambda _: _fake_pipeline_result()),
        execution_mode="injected_pipeline",
    )

    assert summary.trial_count == 2
    assert summary.succeeded_count == 2
    assert summary.no_runtime_execution is True
    assert summary.pair_summaries[0]["resource_observation_count"] == 2


def test_downstream_adapters_accept_entrypoint_wrapper_result() -> None:
    summary = run_model_pair_matrix(
        _plan_payload(),
        make_model_pair_entrypoint_executor(lambda _: _fake_pipeline_result()),
        execution_mode="injected_pipeline",
    )

    resource_observations = build_resource_observations_from_matrix_run_summary(summary)
    resource_summary = summarize_model_resource_observations(resource_observations)
    normality_inputs = build_normality_inputs_from_matrix_run_summary(summary)
    correctness_inputs = build_correctness_inputs_from_matrix_run_summary(summary)
    correctness_summary = evaluate_task_correctness_batch(correctness_inputs)

    assert resource_observations[0]["backend"] == "explicit_entrypoint_fake"
    assert resource_summary.groups["by_pair"][PAIR_ID].success_count == 1
    assert normality_inputs[0]["group_history"][0]["action"] == "office_create_docx"
    assert "normality_trace_missing" not in normality_inputs[0]["warnings"]
    assert correctness_inputs[0].trial_result["task_success"] is True
    assert correctness_summary.passed_count == 1


def test_no_public_cli_live_mode_added() -> None:
    from src.agent.model_pair_matrix_runner_cli import build_parser

    help_text = build_parser().format_help()

    assert "--plan" in help_text
    assert "--pipeline-entrypoint" not in help_text
    assert "--allow-runtime-execution" not in help_text
    assert "--orchestrator-base-url" not in help_text
    assert "--executor-base-url" not in help_text


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
            raise AssertionError("pipeline entrypoint wrapper must stay data-only")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    import src.agent.model_pair_pipeline_entrypoint_wrapper as wrapper_module

    importlib.reload(wrapper_module)
    payload = wrapper_module.build_pipeline_entrypoint_input(
        {
            "trial_id": "no_runtime_trial",
            "scenario_id": SCENARIO_ID,
            "scenario_path": SCENARIO_PATH,
            "pair_id": PAIR_ID,
            "orchestrator_model_id": "second_model",
            "executor_model_id": "first_model",
        }
    )

    assert payload["execution_options"]["no_runtime_execution"] is True


def test_wrapper_does_not_write_reports_or_experiments(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    original_write_text = Path.write_text

    def forbid_reports_or_experiments_write(self: Path, *args: object, **kwargs: object) -> int:
        if "reports" in self.parts or "experiments" in self.parts:
            raise AssertionError("unexpected reports/experiments write")
        return original_write_text(self, *args, **kwargs)

    monkeypatch.setattr(Path, "write_text", forbid_reports_or_experiments_write)

    wrapped = make_explicit_pipeline_entrypoint_callable(lambda _: _fake_pipeline_result())
    result = wrapped(_context())

    assert result["status"] == "completed"
