from __future__ import annotations

import builtins
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
from src.agent.model_pair_matrix_adapters import (
    MATRIX_RUN_ADAPTER_SUMMARY_FILENAME,
    MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME,
    NORMALITY_JUDGE_INPUTS_JSONL_FILENAME,
)
from src.agent.model_pair_single_trial_execution import (
    MODEL_PAIR_SINGLE_TRIAL_MATRIX_SUMMARY_FILENAME,
    MODEL_PAIR_SINGLE_TRIAL_RESULT_FILENAME,
)
from src.agent.model_pair_single_trial_operator_runner import (
    SINGLE_TRIAL_RUNTIME_CONFIRMATION,
    ModelPairSingleTrialOperatorConfig,
    ModelPairSingleTrialOperatorError,
    build_parser,
    load_entrypoint_from_ref,
    main as operator_main,
    parse_entrypoint_ref,
    run_single_trial_operator,
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
            "task_summary": "Run one guarded controlled model-pair trial.",
            "expected_outputs": {"checks": [{"type": "status_equals", "expected": "succeeded"}]},
            "tags": ["single_trial_operator_test"],
            "no_runtime_execution": True,
        }
        for index in range(1, repetitions + 1)
    ]
    payload: dict[str, Any] = {
        "schema_version": "model_comparison_plan_v1",
        "plan_id": "model_pair_single_trial_operator_plan",
        "candidate_pairs": [
            {
                "pair_id": PAIR_ID,
                "orchestrator_model_id": "second_model",
                "executor_model_id": "first_model",
                "tags": ["single_trial_operator_test"],
            }
        ],
        "scenarios": [
            {
                "scenario_id": SCENARIO_ID,
                "scenario_path": SCENARIO_PATH,
                "task_summary": "Run one guarded controlled model-pair trial.",
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


def _plan_path(tmp_path: Path, plan: dict[str, Any] | None = None) -> Path:
    path = tmp_path / "plan.json"
    path.write_text(json.dumps(plan or _plan(), ensure_ascii=False, indent=2), encoding="utf-8")
    return path


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
        "summary": "Fake operator entrypoint selected a safe offline action.",
        "metadata": {"execution_attempted": False, "execution_success": None},
    }
    payload.update(overrides)
    return payload


def _fake_pipeline_result(**overrides: object) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "status": "completed",
        "success": True,
        "correctness_score": 0.97,
        "group_history": [_event()],
        "event_history": [_event(action="office_validate_docx")],
        "activity_trace": [_event(action="office_record_summary")],
        "artifacts": [{"path": "artifacts/single_trial_operator/report.docx"}],
        "resource_observation": {
            "runtime_mode": "fake_single_trial_operator",
            "backend": "explicit_operator_fake_entrypoint",
            "success": True,
            "wall_time_s": 1.7,
        },
        "warnings": ["fake_entrypoint_does_not_call_llama_server"],
        "notes": ["synthetic_single_trial_operator_pipeline_result"],
        "metadata": {"pipeline": "fake_single_trial_operator"},
        "no_runtime_execution": True,
    }
    payload.update(overrides)
    return payload


def _install_fake_entrypoint(
    monkeypatch: pytest.MonkeyPatch,
    *,
    module_name: str = "phase88_fake_operator_entrypoint",
    result: dict[str, Any] | None = None,
) -> tuple[str, list[dict[str, Any]]]:
    module = types.ModuleType(module_name)
    calls: list[dict[str, Any]] = []

    def run(entrypoint_input: dict[str, Any]) -> dict[str, Any]:
        calls.append(entrypoint_input)
        return result or _fake_pipeline_result()

    module.run = run  # type: ignore[attr-defined]
    monkeypatch.setitem(sys.modules, module_name, module)
    return f"{module_name}:run", calls


def _operator_config(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    *,
    plan: dict[str, Any] | None = None,
    readiness_summary_path: Path | None = None,
    output_dir: Path | None = None,
    result: dict[str, Any] | None = None,
    **overrides: object,
) -> ModelPairSingleTrialOperatorConfig:
    plan_payload = plan or _plan()
    entrypoint_ref, _ = _install_fake_entrypoint(monkeypatch, result=result)
    payload: dict[str, Any] = {
        "plan_path": _plan_path(tmp_path, plan_payload),
        "readiness_summary_path": readiness_summary_path or _ready_summary_path(tmp_path, plan_payload),
        "entrypoint_ref": entrypoint_ref,
        "output_dir": output_dir or tmp_path / "single",
        "trial_id": plan_payload["trials"][0]["trial_id"],
    }
    payload.update(overrides)
    return ModelPairSingleTrialOperatorConfig(**payload)


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def test_parse_entrypoint_ref_accepts_module_function() -> None:
    assert parse_entrypoint_ref("package.module:run_trial") == ("package.module", "run_trial")


@pytest.mark.parametrize(
    "ref",
    [
        "",
        "module",
        "module:",
        ":func",
        "module/sub:func",
        "module\\sub:func",
        "../module:func",
        "module..sub:func",
        "module:Class.method",
    ],
)
def test_parse_entrypoint_ref_rejects_invalid_refs(ref: str) -> None:
    with pytest.raises(ModelPairSingleTrialOperatorError):
        parse_entrypoint_ref(ref)


def test_load_entrypoint_from_ref_uses_explicit_temp_module(monkeypatch: pytest.MonkeyPatch) -> None:
    entrypoint_ref, _ = _install_fake_entrypoint(monkeypatch)

    assert callable(load_entrypoint_from_ref(entrypoint_ref))


def test_load_entrypoint_from_ref_does_not_call_entrypoint(monkeypatch: pytest.MonkeyPatch) -> None:
    entrypoint_ref, calls = _install_fake_entrypoint(monkeypatch)

    _ = load_entrypoint_from_ref(entrypoint_ref)

    assert calls == []


def test_operator_requires_plan(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _operator_config(tmp_path, monkeypatch, plan_path=None)

    result = run_single_trial_operator(config)

    assert result["status"] == "invalid"
    assert result["error"] == "plan_required"


def test_operator_requires_readiness_summary(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _operator_config(tmp_path, monkeypatch, readiness_summary_path=None)
    config = ModelPairSingleTrialOperatorConfig(
        plan_path=config.plan_path,
        entrypoint_ref=config.entrypoint_ref,
        output_dir=config.output_dir,
        trial_id=config.trial_id,
    )

    result = run_single_trial_operator(config)

    assert result["status"] == "invalid"
    assert result["error"] == "readiness_summary_required"


def test_operator_requires_entrypoint(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _operator_config(tmp_path, monkeypatch, entrypoint_ref=None)

    result = run_single_trial_operator(config)

    assert result["status"] == "invalid"
    assert result["error"] == "entrypoint_ref_required"


def test_operator_requires_trial_selector(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    config = _operator_config(tmp_path, monkeypatch, trial_id=None, pair_id=None, scenario_id=None)

    result = run_single_trial_operator(config)

    assert result["status"] == "invalid"
    assert result["error"] == "trial_selector_required"


def test_no_runtime_mode_calls_single_trial_api_with_allow_false(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agent.model_pair_single_trial_operator_runner as runner_module

    captured: dict[str, Any] = {}

    def fake_single_api(plan: dict[str, Any], *, pipeline_entrypoint: object, config: object) -> dict[str, Any]:
        captured["plan_id"] = plan["plan_id"]
        captured["callable"] = callable(pipeline_entrypoint)
        captured["allow_runtime_execution"] = config.allow_runtime_execution  # type: ignore[attr-defined]
        return {"status": "succeeded", "allow_runtime_execution": config.allow_runtime_execution}

    monkeypatch.setattr(runner_module, "run_single_model_pair_trial", fake_single_api)
    config = _operator_config(tmp_path, monkeypatch)

    result = runner_module.run_single_trial_operator(config)

    assert result["status"] == "succeeded"
    assert captured == {
        "plan_id": "model_pair_single_trial_operator_plan",
        "callable": True,
        "allow_runtime_execution": False,
    }


def test_runtime_opt_in_without_confirmation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = run_single_trial_operator(_operator_config(tmp_path, monkeypatch, allow_runtime_execution=True))

    assert result["status"] == "invalid"
    assert result["error"] == "runtime_confirmation_required"


def test_runtime_opt_in_with_wrong_confirmation_fails(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = run_single_trial_operator(
        _operator_config(
            tmp_path,
            monkeypatch,
            allow_runtime_execution=True,
            confirm_runtime_execution="YES",
        )
    )

    assert result["status"] == "invalid"
    assert result["error"] == "runtime_confirmation_invalid"


def test_exact_runtime_confirmation_sets_allow_true(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    import src.agent.model_pair_single_trial_operator_runner as runner_module

    captured: dict[str, Any] = {}

    def fake_single_api(_: dict[str, Any], *, pipeline_entrypoint: object, config: object) -> dict[str, Any]:
        captured["allow_runtime_execution"] = config.allow_runtime_execution  # type: ignore[attr-defined]
        return {
            "status": "succeeded",
            "allow_runtime_execution": config.allow_runtime_execution,  # type: ignore[attr-defined]
            "no_runtime_execution": False,
        }

    monkeypatch.setattr(runner_module, "run_single_model_pair_trial", fake_single_api)
    result = runner_module.run_single_trial_operator(
        _operator_config(
            tmp_path,
            monkeypatch,
            allow_runtime_execution=True,
            confirm_runtime_execution=SINGLE_TRIAL_RUNTIME_CONFIRMATION,
        )
    )

    assert result["status"] == "succeeded"
    assert captured["allow_runtime_execution"] is True
    assert result["runtime_confirmation"] == "accepted"


def test_selected_trial_executes_once_with_fake_entrypoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan(repetitions=2)
    entrypoint_ref, calls = _install_fake_entrypoint(monkeypatch)
    result = run_single_trial_operator(
        ModelPairSingleTrialOperatorConfig(
            plan_path=_plan_path(tmp_path, plan),
            readiness_summary_path=_ready_summary_path(tmp_path, plan),
            entrypoint_ref=entrypoint_ref,
            output_dir=tmp_path / "single",
            pair_id=PAIR_ID,
            scenario_id=SCENARIO_ID,
            repeat_index=2,
        )
    )

    assert result["status"] == "succeeded"
    assert len(calls) == 1
    assert calls[0]["trial_id"] == plan["trials"][1]["trial_id"]


def test_readiness_not_ready_blocks_entrypoint(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    entrypoint_ref, calls = _install_fake_entrypoint(monkeypatch)
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
    result = run_single_trial_operator(
        ModelPairSingleTrialOperatorConfig(
            plan_path=_plan_path(tmp_path),
            readiness_summary_path=readiness_path,
            entrypoint_ref=entrypoint_ref,
            output_dir=tmp_path / "single",
            trial_id=_plan()["trials"][0]["trial_id"],
        )
    )

    assert result["status"] == "invalid"
    assert result["error"] == "single_trial_readiness_gate_failed"
    assert calls == []


def test_operator_writes_single_trial_artifacts(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "single"
    result = run_single_trial_operator(_operator_config(tmp_path, monkeypatch, output_dir=output_dir))

    assert result["status"] == "succeeded"
    assert result["matrix_summary_path"] == MODEL_PAIR_SINGLE_TRIAL_MATRIX_SUMMARY_FILENAME
    assert result["trial_result_path"] == MODEL_PAIR_SINGLE_TRIAL_RESULT_FILENAME
    assert (output_dir / MODEL_PAIR_SINGLE_TRIAL_MATRIX_SUMMARY_FILENAME).is_file()
    assert (output_dir / MODEL_PAIR_SINGLE_TRIAL_RESULT_FILENAME).is_file()


def test_operator_auto_matrix_adapter_outputs_work(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    output_dir = tmp_path / "single"
    result = run_single_trial_operator(
        _operator_config(tmp_path, monkeypatch, output_dir=output_dir, auto_matrix_adapter_outputs=True)
    )
    adapter_dir = output_dir / "matrix_adapters"

    assert result["status"] == "succeeded"
    assert result["adapter_summary_path"] == f"matrix_adapters/{MATRIX_RUN_ADAPTER_SUMMARY_FILENAME}"
    assert (adapter_dir / MODEL_RESOURCE_OBSERVATIONS_JSONL_FILENAME).is_file()
    assert (adapter_dir / NORMALITY_JUDGE_INPUTS_JSONL_FILENAME).is_file()
    assert _json(adapter_dir / MATRIX_RUN_ADAPTER_SUMMARY_FILENAME)["trial_count"] == 1


def test_cli_stdout_result_is_concise_safe_json(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    plan = _plan()
    entrypoint_ref, _ = _install_fake_entrypoint(monkeypatch)
    code = operator_main(
        [
            "--plan",
            str(_plan_path(tmp_path, plan)),
            "--readiness-summary",
            str(_ready_summary_path(tmp_path, plan)),
            "--entrypoint",
            entrypoint_ref,
            "--output-dir",
            str(tmp_path / "single"),
            "--trial-id",
            plan["trials"][0]["trial_id"],
            "--tag",
            "phase_8_8",
        ]
    )
    stdout = capsys.readouterr().out
    payload = json.loads(stdout)
    text = json.dumps(payload, ensure_ascii=False)

    assert code == 0
    assert payload["status"] == "succeeded"
    assert payload["tags"] == ["phase_8_8"]
    assert "Traceback" not in stdout
    assert str(tmp_path) not in text
    assert len(stdout) < 12000


def test_absolute_paths_are_redacted_from_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "secret", "artifact.txt"])
    result = run_single_trial_operator(
        _operator_config(
            tmp_path,
            monkeypatch,
            result=_fake_pipeline_result(group_history=[_event(summary=f"opened {windows_path}")]),
        )
    )
    text = json.dumps(result, ensure_ascii=False)

    assert windows_path not in text
    assert "<absolute_path>" in text


def test_secret_like_text_is_redacted_from_result(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    result = run_single_trial_operator(
        _operator_config(
            tmp_path,
            monkeypatch,
            result=_fake_pipeline_result(warnings=["token=SECRET_TOKEN"], notes=["api_key=SECRET_KEY"]),
        )
    )
    text = json.dumps(result, ensure_ascii=False)

    assert "SECRET_TOKEN" not in text
    assert "SECRET_KEY" not in text
    assert "<redacted_secret>" in text


def test_raw_prompt_response_fields_are_not_copied(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    marker = "RAW_PROMPT_RESPONSE_MARKER_SHOULD_NOT_COPY"
    result = run_single_trial_operator(
        _operator_config(
            tmp_path,
            monkeypatch,
            result=_fake_pipeline_result(
                group_history=[_event(raw_prompt=marker, raw_response=marker, raw_model_output=marker)],
                metadata={"raw_prompt": marker, "raw_response": marker},
            ),
        )
    )
    text = json.dumps(result, ensure_ascii=False)

    assert marker not in text
    assert "raw_prompt" not in text
    assert "raw_response" not in text


@pytest.mark.parametrize("output_dir", [Path("reports") / "single", Path("experiments") / "single", Path("docs") / "ai" / "final_phase"])
def test_forbidden_output_dirs_are_rejected(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
    output_dir: Path,
) -> None:
    result = run_single_trial_operator(_operator_config(tmp_path, monkeypatch, output_dir=output_dir))

    assert result["status"] == "invalid"
    assert result["error"] == "output_dir_forbidden"


def test_no_general_public_cli_live_mode_added() -> None:
    from src.agent.model_pair_matrix_runner_cli import build_parser as matrix_build_parser

    matrix_help = matrix_build_parser().format_help()
    operator_help = build_parser().format_help()

    assert "--pipeline-entrypoint" not in matrix_help
    assert "--allow-runtime-execution" not in matrix_help
    assert "--orchestrator-base-url" not in operator_help
    assert "--executor-base-url" not in operator_help
    assert "--gguf" not in operator_help.lower()


def test_operator_does_not_import_or_read_forbidden_runtime_dependencies(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    plan = _plan()
    readiness_path = _ready_summary_path(tmp_path, plan)
    entrypoint_ref, _ = _install_fake_entrypoint(monkeypatch, module_name="phase88_guarded_import_entrypoint")
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
            raise AssertionError("operator runner must stay explicitly injected and offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(Path, "exists", forbid_gguf_exists)
    monkeypatch.setattr(Path, "read_text", forbid_gguf_read_text)
    monkeypatch.setattr(builtins, "__import__", forbid_runtime_import)

    import src.agent.model_pair_single_trial_operator_runner as runner_module

    importlib.reload(runner_module)
    result = runner_module.run_single_trial_operator(
        runner_module.ModelPairSingleTrialOperatorConfig(
            plan_path=_plan_path(tmp_path, plan),
            readiness_summary_path=readiness_path,
            entrypoint_ref=entrypoint_ref,
            output_dir=tmp_path / "single",
            trial_id=plan["trials"][0]["trial_id"],
        )
    )

    assert result["status"] == "succeeded"
    assert result["no_runtime_execution"] is True
