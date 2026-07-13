from __future__ import annotations

import json
from typing import Any

import httpx
import pytest

import src.agent.orchestrator_executor_pipeline as pipeline
from src.agent.evaluation_models import EvaluationModelRegistry, load_evaluation_models_config


def _orchestrator_model(**overrides: object) -> pipeline.OrchestratorModelConfig:
    payload: dict[str, object] = {
        "model_id": "second_model",
        "base_url": "http://127.0.0.1:8080/v1",
        "model_name": "second_model.gguf",
        "api_model": "second_model",
        "temperature": 0.0,
        "max_tokens": 512,
        "timeout_seconds": 1.0,
    }
    payload.update(overrides)
    return pipeline.OrchestratorModelConfig.model_validate(payload)


def _executor_model(**overrides: object) -> pipeline.ExecutorModelConfig:
    payload: dict[str, object] = {
        "model_id": "first_model",
        "base_url": "http://127.0.0.1:8080/v1",
        "model_name": "first_model.gguf",
        "api_model": "first_model",
        "temperature": 0.0,
        "max_tokens": 512,
        "timeout_seconds": 1.0,
    }
    payload.update(overrides)
    return pipeline.ExecutorModelConfig.model_validate(payload)


def test_request_preview_uses_api_model_without_prompt_content() -> None:
    preview = pipeline.build_local_chat_completion_request_preview(
        _orchestrator_model(),
        [{"role": "user", "content": "PROMPT_DO_NOT_COPY"}],
    )

    assert preview["model_id"] == "second_model"
    assert preview["api_model"] == "second_model"
    assert preview["endpoint_path"] == "/v1/chat/completions"
    assert preview["request_shape"] == {
        "has_messages": True,
        "message_count": 1,
        "has_tools": False,
        "has_response_format": False,
        "has_stream": False,
        "temperature_present": True,
        "max_tokens_present": True,
        "estimated_prompt_chars": len("user") + len("PROMPT_DO_NOT_COPY"),
    }
    assert "PROMPT_DO_NOT_COPY" not in json.dumps(preview, ensure_ascii=False)


def test_request_preview_falls_back_to_model_name_when_api_model_missing() -> None:
    preview = pipeline.build_local_chat_completion_request_preview(
        _executor_model(api_model=None),
        [{"role": "user", "content": "test"}],
    )

    assert preview["model_id"] == "first_model"
    assert preview["api_model"] == "first_model.gguf"


def test_local_chat_payload_is_conservative_and_uses_api_model(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    captured: dict[str, Any] = {}

    class FakeClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            captured["client_kwargs"] = kwargs

        def __enter__(self) -> FakeClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, json: dict[str, Any]) -> httpx.Response:
            captured["url"] = url
            captured["payload"] = json
            return httpx.Response(
                200,
                json={"choices": [{"message": {"content": '{"ok": true}'}}]},
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(pipeline.httpx, "Client", FakeClient)

    raw = pipeline.LocalOrchestratorPlanProvider(_orchestrator_model())._chat(
        [{"role": "user", "content": "PROMPT_DO_NOT_COPY"}]
    )

    assert raw == '{"ok": true}'
    assert captured["url"] == "http://127.0.0.1:8080/v1/chat/completions"
    assert captured["payload"]["model"] == "second_model"
    assert set(captured["payload"]) == {"model", "messages", "temperature", "max_tokens"}
    assert captured["payload"]["temperature"] == 0.0
    assert captured["payload"]["max_tokens"] == 512
    assert captured["client_kwargs"]["trust_env"] is False


def test_http_400_becomes_safe_bad_request_diagnostics(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    class BadRequestClient:
        def __init__(self, *args: object, **kwargs: object) -> None:
            del args, kwargs

        def __enter__(self) -> BadRequestClient:
            return self

        def __exit__(self, *args: object) -> None:
            return None

        def post(self, url: str, json: dict[str, Any]) -> httpx.Response:
            del json
            return httpx.Response(
                400,
                text='{"error":"bad model","raw_prompt":"DO_NOT_COPY","token":"SECRET_TOKEN","path":"C:\\\\Users\\\\m\\\\secret.txt"}',
                request=httpx.Request("POST", url),
            )

    monkeypatch.setattr(pipeline.httpx, "Client", BadRequestClient)

    with pytest.raises(pipeline.LocalModelHTTPError) as exc_info:
        pipeline.LocalExecutorActionProvider(_executor_model())._chat(
            [{"role": "user", "content": "PROMPT_DO_NOT_COPY"}]
        )

    exc = exc_info.value
    diagnostics = exc.diagnostics
    diagnostics_text = json.dumps(diagnostics, ensure_ascii=False)

    assert exc.error_code == "local_model_http_bad_request"
    assert diagnostics["error_code"] == "local_model_http_bad_request"
    assert diagnostics["http_status"] == 400
    assert diagnostics["endpoint_path"] == "/v1/chat/completions"
    assert diagnostics["model_id"] == "first_model"
    assert diagnostics["api_model"] == "first_model"
    assert diagnostics["request_shape"]["message_count"] == 1
    assert diagnostics["request_shape"]["has_tools"] is False
    assert "bad model" in diagnostics["safe_response_excerpt"]
    assert "PROMPT_DO_NOT_COPY" not in diagnostics_text
    assert "DO_NOT_COPY" not in diagnostics_text
    assert "SECRET_TOKEN" not in diagnostics_text
    assert "C:\\Users" not in diagnostics_text
    assert "Traceback" not in diagnostics_text


def test_executor_history_carries_safe_http_diagnostics() -> None:
    attempt = pipeline.ExecutorActionAttempt(
        group_step_index=1,
        agent_step_index=1,
        agent_id="document_summary_agent",
        task_id="t1",
        raw_model_output="",
        error_type="local_model_http_bad_request",
        error_message="local_model_http_bad_request: HTTP 400 for /v1/chat/completions",
        error_diagnostics={
            "http_status": 400,
            "endpoint_path": "/v1/chat/completions",
            "model_id": "first_model",
            "api_model": "first_model",
            "request_shape": {"message_count": 1},
        },
    )

    record = pipeline._history_from_attempt(attempt)

    assert record.status == "skipped"
    assert record.metadata["diagnostics"]["http_status"] == 400
    assert record.metadata["diagnostics"]["endpoint_path"] == "/v1/chat/completions"


def test_registry_api_model_maps_phase_8_slots_to_payload_aliases() -> None:
    config = load_evaluation_models_config("configs/evaluation_models.json")
    registry = EvaluationModelRegistry(config)

    orchestrator = pipeline._orchestrator_model_config(registry.require("second_model"))
    executor = pipeline._executor_model_config(registry.require("first_model"))

    assert orchestrator.model_name == "second_model.gguf"
    assert orchestrator.api_model == "second_model"
    assert executor.model_name == "first_model.gguf"
    assert executor.api_model == "first_model"
    assert pipeline.build_local_chat_completion_request_preview(orchestrator)["api_model"] == "second_model"
    assert pipeline.build_local_chat_completion_request_preview(executor)["api_model"] == "first_model"
    assert orchestrator.base_url == "http://127.0.0.1:8080/v1"
    assert executor.base_url == "http://127.0.0.1:8081/v1"
    assert (
        "local_mode_uses_same_base_url_for_orchestrator_and_executor; manual runtime coordination may be required"
        not in pipeline._runtime_warnings("local", orchestrator, executor)
    )
