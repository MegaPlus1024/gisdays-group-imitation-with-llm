from __future__ import annotations

import importlib
import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.model_pair_execution_readiness import (
    validate_model_pair_execution_readiness,
    write_model_pair_execution_readiness_summary,
)
from src.agent.model_pair_matrix_adapters import (
    MATRIX_RUN_ADAPTER_SUMMARY_FILENAME,
    MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME,
    NORMALITY_JUDGE_INPUTS_JSONL_FILENAME,
)
from src.agent.model_pair_matrix_runner import MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME
from src.agent.model_pair_single_trial_execution import (
    MODEL_PAIR_SINGLE_TRIAL_MATRIX_SUMMARY_FILENAME,
    MODEL_PAIR_SINGLE_TRIAL_RESULT_FILENAME,
    ModelPairSingleTrialExecutionConfig,
    run_single_model_pair_trial,
    validate_single_trial_readiness_gate,
)


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
            "task_summary": "Run one controlled model-pair trial.",
            "expected_outputs": {"checks": [{"type": "status_equals", "expected": "succeeded"}]},
            "tags": ["single_trial_test"],
            "no_runtime_execution": True,
        }
        for index in range(1, repetitions + 1)
    ]
    payload: dict[str, Any] = {
        "schema_version": "model_comparison_plan_v1",
        "plan_id": "model_pair_single_trial_plan",
        "candidate_pairs": [
            {
                "pair_id": PAIR_ID,
                "orchestrator_model_id": "second_model",
                "executor_model_id": "first_model",
                "tags": ["single_trial_test"],
            }
        ],
        "scenarios": [
            {
                "scenario_id": SCENARIO_ID,
                "scenario_path": SCENARIO_PATH,
                "task_summary": "Run one controlled model-pair trial.",
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
    return {"agents": [{"agent_id": "office_agent", "scenario_id": context["scenario_id"]}]}


def _model_bindings(context: dict[str, Any]) -> dict[str, Any]:
    return {
        "orchestrator": {"model_id": context["orchestrator_model_id"], "provider": "explicit_fixture"},
        "executor": {"model_id": context["executor_model_id"], "provider": "explicit_fixture"},
    }


def _ready_summary_path(tmp_path: Path, plan: dict[str, Any] | None = None) -> Path:
    summary = validate_model_pair_execution_readiness(
        plan or _plan(),
        role_config_resolver=_role_config,
        scenario_config_resolver=_scenario_config,
        model_binding_resolver=_model_bindings,
    )
    return write_model_pair_execution_readiness_summary(summary, tmp_path / "readiness")


def _readiness_path(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "readiness" / "model_pair_execution_readiness_summary.json"
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return path


def _event(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "group_step_index": 1,
        "agent_id": "office_agent",
        "task_id": "task_1",
        "action": "office_create_docx",
        "status": "success",
        "summary": "Fake single-trial entrypoint selected a safe offline action.",
        "metadata": {"execution_attempted": False, "execution_success": None},
    }
    payload.update(overrides)
    return payload


def _fake_pipeline_result(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "completed",
        "success": True,
        "correctness_score": 0.96,
        "group_history": [_event()],
        "event_history": [_event(action="office_validate_docx")],
        "activity_trace": [_event(action="office_record_summary")],
        "artifacts": [{"path": "artifacts/single_trial/report.docx"}],
        "resource_observation": {
            "runtime_mode": "fake_single_trial",
            "backend": "explicit_single_trial_fake",
            "success": True,
            "wall_time_s": 1.9,
        },
        "warnings": ["fake_entrypoint_does_not_call_llama_server"],
        "notes": ["synthetic_single_trial_pipeline_result"],
        "metadata": {"pipeline": "fake_single_trial"},
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _jsonl(path: Path) -> list[dict[str, Any]]:
    return [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line.strip()]


def test_selects_trial_by_trial_id(tmp_path: Path) -> None:
    plan = _plan(repetitions=2)
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][1]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )

    assert result["status"] == "succeeded"
    assert result["trial_id"] == plan["trials"][1]["trial_id"]
    assert result["repeat_index"] == 2


def test_selects_trial_by_pair_id_and_scenario_id(tmp_path: Path) -> None:
    plan = _plan()
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            pair_id=PAIR_ID,
            scenario_id=SCENARIO_ID,
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )

    assert result["status"] == "succeeded"
    assert result["pair_id"] == PAIR_ID
    assert result["scenario_id"] == SCENARIO_ID


def test_multiple_matches_require_repeat_index(tmp_path: Path) -> None:
    plan = _plan(repetitions=2)
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            pair_id=PAIR_ID,
            scenario_id=SCENARIO_ID,
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )

    assert result["status"] == "invalid"
    assert result["error"] == "selected_trial_ambiguous"


def test_no_match_returns_controlled_invalid_result(tmp_path: Path) -> None:
    result = run_single_model_pair_trial(
        _plan(),
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id="missing_trial",
            readiness_summary_path=_ready_summary_path(tmp_path),
        ),
    )

    assert result["status"] == "invalid"
    assert result["error"] == "selected_trial_not_found"
    assert "selected_trial_not_found" in result["warnings"]


def test_missing_readiness_summary_blocks_when_required(tmp_path: Path) -> None:
    plan = _plan()
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
        ),
    )

    assert result["status"] == "invalid"
    assert "readiness_summary_missing" in {finding["code"] for finding in result["findings"]}


def test_readiness_status_not_ready_blocks(tmp_path: Path) -> None:
    plan = _plan()
    readiness_path = _readiness_path(
        tmp_path,
        {
            "schema_version": "model_pair_execution_readiness_v1",
            "status": "not_ready",
            "findings": [],
            "warnings": [],
            "notes": [],
            "no_runtime_execution": True,
        },
    )
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=readiness_path,
        ),
    )

    assert result["status"] == "invalid"
    assert "readiness_summary_not_ready" in {finding["code"] for finding in result["findings"]}


def test_error_finding_for_selected_trial_blocks(tmp_path: Path) -> None:
    plan = _plan()
    readiness_path = _readiness_path(
        tmp_path,
        {
            "schema_version": "model_pair_execution_readiness_v1",
            "status": "ready",
            "findings": [
                {
                    "severity": "error",
                    "code": "scenario_config_missing",
                    "trial_id": plan["trials"][0]["trial_id"],
                    "pair_id": PAIR_ID,
                    "scenario_id": SCENARIO_ID,
                    "message": "blocked",
                }
            ],
            "warnings": [],
            "notes": [],
            "no_runtime_execution": True,
        },
    )

    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=readiness_path,
        ),
    )

    assert result["status"] == "invalid"
    assert "selected_trial_not_ready" in {finding["code"] for finding in result["findings"]}


def test_warning_finding_for_selected_trial_does_not_block_but_is_copied(tmp_path: Path) -> None:
    plan = _plan()
    readiness_path = _readiness_path(
        tmp_path,
        {
            "schema_version": "model_pair_execution_readiness_v1",
            "status": "ready",
            "findings": [
                {
                    "severity": "warning",
                    "code": "role_config_missing",
                    "trial_id": plan["trials"][0]["trial_id"],
                    "pair_id": PAIR_ID,
                    "scenario_id": SCENARIO_ID,
                    "message": "optional",
                }
            ],
            "warnings": ["role_config_missing"],
            "notes": [],
            "no_runtime_execution": True,
        },
    )
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=readiness_path,
        ),
    )

    assert result["status"] == "succeeded"
    assert "role_config_missing" in result["warnings"]


def test_ready_summary_permits_execution(tmp_path: Path) -> None:
    plan = _plan()
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )

    assert result["status"] == "succeeded"
    assert result["trial_result"]["task_success"] is True


def test_fake_entrypoint_is_called_exactly_once(tmp_path: Path) -> None:
    plan = _plan()
    calls: list[dict[str, Any]] = []

    def entrypoint(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(entrypoint_input)
        return _fake_pipeline_result()

    run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=entrypoint,
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )

    assert len(calls) == 1
    assert calls[0]["trial_id"] == plan["trials"][0]["trial_id"]


def test_only_one_trial_is_executed_even_when_plan_has_multiple_trials(tmp_path: Path) -> None:
    plan = _plan(repetitions=2)
    calls: list[str] = []

    def entrypoint(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(entrypoint_input["trial_id"])
        return _fake_pipeline_result()

    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=entrypoint,
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            pair_id=PAIR_ID,
            scenario_id=SCENARIO_ID,
            repeat_index=2,
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )

    assert result["status"] == "succeeded"
    assert calls == [plan["trials"][1]["trial_id"]]


def test_default_allow_runtime_execution_false_reaches_entrypoint_input(tmp_path: Path) -> None:
    plan = _plan()
    calls: list[dict[str, Any]] = []

    def entrypoint(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(entrypoint_input)
        return _fake_pipeline_result()

    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=entrypoint,
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )

    assert calls[0]["execution_options"]["allow_runtime_execution"] is False
    assert calls[0]["execution_options"]["no_runtime_execution"] is True
    assert result["allow_runtime_execution"] is False
    assert result["no_runtime_execution"] is True


def test_allow_runtime_execution_true_is_explicit_and_reaches_entrypoint_input(tmp_path: Path) -> None:
    plan = _plan()
    calls: list[dict[str, Any]] = []

    def entrypoint(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(entrypoint_input)
        return _fake_pipeline_result(no_runtime_execution=False)

    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=entrypoint,
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            allow_runtime_execution=True,
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )

    assert calls[0]["execution_options"]["allow_runtime_execution"] is True
    assert calls[0]["execution_options"]["no_runtime_execution"] is False
    assert calls[0]["metadata"]["explicit_runtime_opt_in"] is True
    assert result["allow_runtime_execution"] is True
    assert result["no_runtime_execution"] is False


def test_entrypoint_exception_becomes_controlled_failed_trial_result(tmp_path: Path) -> None:
    plan = _plan()

    def entrypoint(_: dict[str, Any]) -> dict[str, Any]:
        raise RuntimeError("RAW_SECRET_EXCEPTION_DETAIL")

    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=entrypoint,
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )
    text = json.dumps(result, ensure_ascii=False)

    assert result["status"] == "failed"
    assert result["trial_result"]["error_code"] == "pipeline_executor_failed"
    assert "RAW_SECRET_EXCEPTION_DETAIL" not in text
    assert "RuntimeError" not in text


def test_writes_single_trial_result_artifact(tmp_path: Path) -> None:
    plan = _plan()
    output_dir = tmp_path / "single"
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=output_dir,
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )
    payload = _json(output_dir / MODEL_PAIR_SINGLE_TRIAL_RESULT_FILENAME)

    assert result["trial_result_path"] == MODEL_PAIR_SINGLE_TRIAL_RESULT_FILENAME
    assert payload["trial_id"] == plan["trials"][0]["trial_id"]
    assert payload["status"] == "succeeded"


def test_writes_one_trial_matrix_summary_artifact(tmp_path: Path) -> None:
    plan = _plan()
    output_dir = tmp_path / "single"
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=output_dir,
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )
    payload = _json(output_dir / MODEL_PAIR_SINGLE_TRIAL_MATRIX_SUMMARY_FILENAME)

    assert result["matrix_summary_path"] == MODEL_PAIR_SINGLE_TRIAL_MATRIX_SUMMARY_FILENAME
    assert result["matrix_summary_path"] != MODEL_PAIR_MATRIX_RUN_SUMMARY_FILENAME
    assert payload["trial_count"] == 1
    assert payload["trial_results"][0]["trial_id"] == plan["trials"][0]["trial_id"]


def test_auto_adapter_outputs_write_resource_observations_and_normality_inputs(tmp_path: Path) -> None:
    plan = _plan()
    output_dir = tmp_path / "single"
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=output_dir,
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
            auto_matrix_adapter_outputs=True,
            adapter_id="single_trial_adapter_test",
        ),
    )
    adapter_dir = output_dir / "matrix_adapters"
    observations = _jsonl(adapter_dir / MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME)
    normality_inputs = _jsonl(adapter_dir / NORMALITY_JUDGE_INPUTS_JSONL_FILENAME)
    adapter_summary = _json(adapter_dir / MATRIX_RUN_ADAPTER_SUMMARY_FILENAME)

    assert result["adapter_summary_path"] == f"matrix_adapters/{MATRIX_RUN_ADAPTER_SUMMARY_FILENAME}"
    assert observations[0]["backend"] == "explicit_single_trial_fake"
    assert normality_inputs[0]["trial_id"] == plan["trials"][0]["trial_id"]
    assert adapter_summary["adapter_id"] == "single_trial_adapter_test"
    assert adapter_summary["trial_count"] == 1


def test_auto_adapter_outputs_do_not_run_normality_judge(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    def forbidden_judge(*_: object, **__: object) -> object:
        raise AssertionError("normality judge must not run from single-trial API")

    monkeypatch.setattr("src.agent.normality_judge.run_normality_judge", forbidden_judge)
    plan = _plan()

    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
            auto_matrix_adapter_outputs=True,
        ),
    )

    assert result["status"] == "succeeded"


def test_result_paths_are_relative_and_safe(tmp_path: Path) -> None:
    plan = _plan()
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
            auto_matrix_adapter_outputs=True,
        ),
    )

    assert result["matrix_summary_path"] == MODEL_PAIR_SINGLE_TRIAL_MATRIX_SUMMARY_FILENAME
    assert result["trial_result_path"] == MODEL_PAIR_SINGLE_TRIAL_RESULT_FILENAME
    assert result["adapter_summary_path"] == f"matrix_adapters/{MATRIX_RUN_ADAPTER_SUMMARY_FILENAME}"
    assert "<absolute_path>" not in json.dumps(result, ensure_ascii=False)


def test_single_trial_sanitizer_preserves_runtime_urls_and_secret_queries() -> None:
    import src.agent.model_pair_single_trial_execution as single_module

    assert single_module._safe_text("http://127.0.0.1:8080/v1") == "http://127.0.0.1:8080/v1"
    assert single_module._safe_text("http://127.0.0.1:8081/v1") == "http://127.0.0.1:8081/v1"
    assert single_module._safe_text("https://example.test/v1") == "https://example.test/v1"
    assert single_module._safe_text("ws://127.0.0.1:8080/ws") == "ws://127.0.0.1:8080/ws"
    assert (
        single_module._safe_text("http://host/v1?token=secret")
        == "http://host/v1?token=<redacted_secret>"
    )


def test_failed_pipeline_error_diagnostics_are_persisted_in_result_and_matrix(tmp_path: Path) -> None:
    plan = _plan()
    output_dir = tmp_path / "single_failed"
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(
            status="failed",
            success=False,
            group_history=[],
            errors=[
                {
                    "stage": "orchestrator",
                    "error_type": "local_model_http_error",
                    "error_message": "local_model_http_error: HTTP None for /v1/chat/completions",
                    "diagnostics": {
                        "error_code": "local_model_http_error",
                        "endpoint_path": "/v1/chat/completions",
                        "model_id": "second_model",
                        "api_model": "second_model",
                    },
                }
            ],
            stopped_reason="local_model_http_error: HTTP None for /v1/chat/completions",
            metadata={},
            no_runtime_execution=False,
        ),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=output_dir,
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
            allow_runtime_execution=True,
        ),
    )
    trial_payload = _json(output_dir / MODEL_PAIR_SINGLE_TRIAL_RESULT_FILENAME)
    matrix_payload = _json(output_dir / MODEL_PAIR_SINGLE_TRIAL_MATRIX_SUMMARY_FILENAME)

    assert result["status"] == "failed"
    assert trial_payload["error_code"] == "local_model_http_error"
    assert trial_payload["metadata"]["diagnostics"]["error_code"] == "local_model_http_error"
    assert trial_payload["metadata"]["diagnostics"]["errors"][0]["diagnostics"]["endpoint_path"] == "/v1/chat/completions"
    assert matrix_payload["trial_results"][0]["error_code"] == "local_model_http_error"
    assert (
        matrix_payload["trial_results"][0]["metadata"]["diagnostics"]["errors"][0]["diagnostics"]["endpoint_path"]
        == "/v1/chat/completions"
    )


def test_secrets_and_absolute_paths_are_redacted(tmp_path: Path) -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "secret", "artifact.txt"])
    plan = _plan()
    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(
            group_history=[_event(summary=f"opened {windows_path} token=SECRET_TOKEN")],
            warnings=["api_key=SECRET_KEY"],
        ),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )
    text = json.dumps(result, ensure_ascii=False)

    assert windows_path not in text
    assert "SECRET_TOKEN" not in text
    assert "SECRET_KEY" not in text
    assert "<absolute_path>" in text
    assert "<redacted_secret>" in text


def test_raw_prompt_response_fields_are_not_copied(tmp_path: Path) -> None:
    marker = "RAW_PROMPT_RESPONSE_MARKER_SHOULD_NOT_COPY"
    plan = _plan()

    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(
            group_history=[_event(raw_prompt=marker, raw_response=marker, raw_model_output=marker)],
            metadata={"raw_response": marker, "raw_prompt": marker},
        ),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )
    text = json.dumps(result, ensure_ascii=False)

    assert marker not in text
    assert "raw_prompt" not in text
    assert "raw_response" not in text


def test_validate_single_trial_readiness_gate_handles_malformed_summary() -> None:
    findings = validate_single_trial_readiness_gate(
        {"status": "ready", "findings": "not-array"},
        trial_id="trial",
        pair_id=PAIR_ID,
        scenario_id=SCENARIO_ID,
    )

    assert findings[0]["code"] == "readiness_summary_malformed"
    assert findings[0]["severity"] == "error"


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
    plan = _plan()

    result = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )
    forbidden = run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=ModelPairSingleTrialExecutionConfig(
            output_dir=Path("reports") / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
        ),
    )

    assert result["status"] == "succeeded"
    assert forbidden["status"] == "invalid"
    assert forbidden["error"] == "output_dir_forbidden"


def test_no_model_http_llama_browser_office_imports_or_gguf_reads(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    readiness_path = _ready_summary_path(tmp_path, plan)
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
            raise AssertionError("single-trial API must stay dependency-injected")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr("builtins.__import__", forbid_runtime_import)

    import src.agent.model_pair_single_trial_execution as single_module

    importlib.reload(single_module)
    result = single_module.run_single_model_pair_trial(
        plan,
        pipeline_entrypoint=lambda _: _fake_pipeline_result(),
        config=single_module.ModelPairSingleTrialExecutionConfig(
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
            readiness_summary_path=readiness_path,
        ),
    )

    assert result["status"] == "succeeded"
    assert result["no_runtime_execution"] is True
