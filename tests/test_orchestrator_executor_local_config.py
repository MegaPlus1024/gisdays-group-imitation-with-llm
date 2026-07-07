from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import src.agent.orchestrator_executor_pipeline as pipeline
from src.agent.orchestrator_executor_pipeline import OrchestratorExecutorRunConfig, OrchestratorExecutorRunner


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCENARIO = "configs/multi_agent_scenarios/office_developer_group_basic.json"


def _json(path: Path) -> dict[str, Any]:
    return json.loads(path.read_text(encoding="utf-8"))


def _config(tmp_path: Path, **overrides: object) -> OrchestratorExecutorRunConfig:
    payload: dict[str, object] = {
        "project_root": PROJECT_ROOT,
        "mode": "local",
        "models_config_path": "configs/evaluation_models.json",
        "scenario_path": SCENARIO,
        "out_dir": str(tmp_path / "local_config_artifacts"),
        "run_id": "test_local_config",
        "orchestrator_model_id": "second_model",
        "executor_model_id": "first_model",
        "orchestrator_base_url": "http://127.0.0.1:8081/v1",
        "executor_base_url": "http://127.0.0.1:8082/v1",
        "orchestrator_model_name": "second_model.gguf",
        "executor_model_name": "first_model.gguf",
        "max_group_steps": 1,
        "max_steps_per_agent": 1,
        "repair_attempts": 1,
        "execute_actions": False,
        "force": True,
    }
    payload.update(overrides)
    return OrchestratorExecutorRunConfig.model_validate(payload)


def test_local_mode_providers_receive_separate_base_urls(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, dict[str, str]] = {}

    class CapturingOrchestratorProvider:
        def __init__(self, model: pipeline.OrchestratorModelConfig) -> None:
            captured["orchestrator"] = model.model_dump(mode="json")

        def create_plan(self, *, scenario, agents, agent_action_names):  # type: ignore[no-untyped-def]
            del agent_action_names
            return pipeline.OrchestratorProviderResult(
                raw_model_output=json.dumps(
                    {
                        "tasks": [
                            {
                                "task_id": f"task_{index}",
                                "agent_id": agent.agent_id,
                                "goal": agent.assigned_goal,
                                "allowed_action_focus": ["read_file"],
                                "success_criteria": "Local config test produced a valid assignment.",
                            }
                            for index, agent in enumerate(agents, start=1)
                        ],
                        "coordination_notes": "Use local files only.",
                        "expected_group_outcome": "Both agents perform one safe local action.",
                    }
                ),
                prompt_messages=[],
            )

    class CapturingExecutorProvider:
        def __init__(self, model: pipeline.ExecutorModelConfig) -> None:
            captured["executor"] = model.model_dump(mode="json")

        def next_action(self, *, agent, task, state, group_step_index, agent_step_index, out_dir, project_root):  # type: ignore[no-untyped-def]
            del agent, task, state, group_step_index, agent_step_index, out_dir, project_root
            return pipeline.ExecutorProviderResult(
                raw_model_output=json.dumps(
                    {
                        "action": "read_file",
                        "parameters": {"path": "docs/ai/model_research_metadata.md"},
                        "reason": "Read a local documentation file.",
                        "expected_result": "The local file is available.",
                    }
                )
            )

    monkeypatch.setattr(pipeline, "LocalOrchestratorPlanProvider", CapturingOrchestratorProvider)
    monkeypatch.setattr(pipeline, "LocalExecutorActionProvider", CapturingExecutorProvider)

    result = OrchestratorExecutorRunner(_config(tmp_path)).run()

    assert result.status == "completed"
    assert captured["orchestrator"]["base_url"] == "http://127.0.0.1:8081/v1"
    assert captured["executor"]["base_url"] == "http://127.0.0.1:8082/v1"
    assert captured["orchestrator"]["model_name"] == "second_model.gguf"
    assert captured["executor"]["model_name"] == "first_model.gguf"
    assert captured["orchestrator"]["api_model"] == "second_model.gguf"
    assert captured["executor"]["api_model"] == "first_model.gguf"


def test_manifest_records_runtime_overrides_with_mocked_local_providers(
    tmp_path: Path,
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class FakeLocalOrchestratorProvider(pipeline.FakeOrchestratorPlanProvider):
        def __init__(self, model: pipeline.OrchestratorModelConfig) -> None:
            self.model = model

    class FakeLocalExecutorProvider(pipeline.FakeExecutorActionProvider):
        def __init__(self, model: pipeline.ExecutorModelConfig) -> None:
            self.model = model

    monkeypatch.setattr(pipeline, "LocalOrchestratorPlanProvider", FakeLocalOrchestratorProvider)
    monkeypatch.setattr(pipeline, "LocalExecutorActionProvider", FakeLocalExecutorProvider)

    result = OrchestratorExecutorRunner(_config(tmp_path)).run()
    manifest = _json(Path(result.artifact_dir or "") / "manifest.json")

    assert manifest["orchestrator_model_id"] == "second_model"
    assert manifest["executor_model_id"] == "first_model"
    assert manifest["orchestrator_base_url"] == "http://127.0.0.1:8081/v1"
    assert manifest["executor_base_url"] == "http://127.0.0.1:8082/v1"
    assert manifest["orchestrator_api_model"] == "second_model.gguf"
    assert manifest["executor_api_model"] == "first_model.gguf"
    assert manifest["runtime_overrides"]["orchestrator_base_url"] == "http://127.0.0.1:8081/v1"
    assert manifest["runtime_overrides"]["executor_base_url"] == "http://127.0.0.1:8082/v1"


def test_effective_runtime_warnings_use_overridden_base_urls_and_preserve_api_model(
    tmp_path: Path,
) -> None:
    orchestrator = pipeline.OrchestratorModelConfig(
        model_id="second_model",
        base_url="http://127.0.0.1:8080/v1",
        model_name="second_model.gguf",
        api_model="second_model",
    )
    executor = pipeline.ExecutorModelConfig(
        model_id="first_model",
        base_url="http://127.0.0.1:8080/v1",
        model_name="first_model.gguf",
        api_model="first_model",
    )
    config = _config(
        tmp_path,
        orchestrator_base_url="http://127.0.0.1:8080/v1",
        executor_base_url="http://127.0.0.1:8081/v1",
        orchestrator_model_name=None,
        executor_model_name=None,
    )

    effective_orchestrator, effective_executor = pipeline._apply_runtime_overrides(
        orchestrator,
        executor,
        config,
    )

    assert effective_orchestrator.base_url == "http://127.0.0.1:8080/v1"
    assert effective_executor.base_url == "http://127.0.0.1:8081/v1"
    assert effective_orchestrator.api_model == "second_model"
    assert effective_executor.api_model == "first_model"
    assert (
        "local_mode_uses_same_base_url_for_orchestrator_and_executor; manual runtime coordination may be required"
        not in pipeline._runtime_warnings("local", effective_orchestrator, effective_executor)
    )
    assert (
        "local_mode_uses_same_base_url_for_orchestrator_and_executor; manual runtime coordination may be required"
        in pipeline._runtime_warnings("local", orchestrator, executor)
    )


def test_config_accepts_prompt_budget_block(tmp_path: Path) -> None:
    config = _config(
        tmp_path,
        prompt_budget={
            "executor_max_prompt_chars": 12000,
            "orchestrator_max_prompt_chars": 16000,
            "max_history_items": 6,
            "compact_executor_context": True,
        },
    )

    assert config.prompt_budget.executor_max_prompt_chars == 12000
    assert config.prompt_budget.orchestrator_max_prompt_chars == 16000
    assert config.prompt_budget.max_history_items == 6
    assert config.prompt_budget.compact_executor_context is True


def test_pipeline_sanitizer_preserves_runtime_urls_and_secret_queries() -> None:
    assert pipeline._safe_text("http://127.0.0.1:8080/v1") == "http://127.0.0.1:8080/v1"
    assert pipeline._safe_text("http://127.0.0.1:8081/v1") == "http://127.0.0.1:8081/v1"
    assert pipeline._safe_text("https://example.test/v1") == "https://example.test/v1"
    assert pipeline._safe_text("wss://127.0.0.1:8081/ws") == "wss://127.0.0.1:8081/ws"
    assert pipeline._safe_text("http://host/v1?token=secret") == "http://host/v1?token=<redacted_secret>"


def test_local_http_error_uses_path_only_endpoint_diagnostics() -> None:
    model = pipeline.OrchestratorModelConfig(
        model_id="second_model",
        base_url="http://127.0.0.1:8080/v1",
        model_name="second_model.gguf",
        api_model="second_model",
    )
    payload = {
        "model": "second_model",
        "messages": [{"role": "user", "content": "shape only"}],
        "temperature": 0.0,
        "max_tokens": 1,
    }
    error = pipeline._local_model_http_error(
        pipeline.httpx.ConnectError("Request URL is missing an 'http://' or 'https://' protocol."),
        model=model,
        payload=payload,
        url="http://127.0.0.1:8080/v1/chat/completions",
    )

    assert error.error_code == "local_model_http_error"
    assert error.diagnostics["endpoint_path"] == "/v1/chat/completions"
    assert "http://127.0.0.1:8080" not in error.diagnostics["endpoint_path"]
    assert pipeline._endpoint_path("htt<absolute_path>/chat/completions") == "/chat/completions"


def test_cli_accepts_base_url_overrides_and_fake_mode_remains_offline(tmp_path: Path) -> None:
    out_dir = tmp_path / "cli_override_artifacts"
    completed = subprocess.run(
        [
            sys.executable,
            "scripts/run_orchestrator_executor_group.py",
            "--mode",
            "fake",
            "--models-config",
            "configs/evaluation_models.json",
            "--scenario",
            SCENARIO,
            "--out-dir",
            str(out_dir),
            "--run-id",
            "cli_override_fake",
            "--orchestrator-model-id",
            "second_model",
            "--executor-model-id",
            "first_model",
            "--orchestrator-base-url",
            "http://127.0.0.1:8081/v1",
            "--executor-base-url",
            "http://127.0.0.1:8082/v1",
            "--orchestrator-model-name",
            "second_model.gguf",
            "--executor-model-name",
            "first_model.gguf",
            "--max-group-steps",
            "1",
            "--max-steps-per-agent",
            "1",
            "--no-execute-actions",
            "--force",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    assert "orchestrator_base_url_override: http://127.0.0.1:8081/v1" in completed.stdout
    manifest = _json(out_dir / "manifest.json")
    assert manifest["orchestrator_base_url"] == "http://127.0.0.1:8081/v1"
    assert manifest["executor_base_url"] == "http://127.0.0.1:8082/v1"


def test_start_llama_server_port_dry_run_is_documented() -> None:
    script = (PROJECT_ROOT / "scripts" / "start_llama_server.ps1").read_text(encoding="utf-8")

    assert "[int]$Port = 8080" in script
    assert "-Port <port>" in script
    assert "-ApiModel <alias>" in script
    assert "--port $Port" in script
    assert "--alias" in script
    assert "-DryRun" in script


def test_config_rejects_empty_runtime_override(tmp_path: Path) -> None:
    with pytest.raises(ValueError, match="Optional runtime override values"):
        _config(tmp_path, orchestrator_base_url=" ")
