from __future__ import annotations

import json
from pathlib import Path
from typing import Any

import pytest

from src.agent.normality_judge import (
    LLMNormalityJudgeProvider,
    LocalLLMNormalityJudgeClientAdapter,
    NORMALITY_DIMENSIONS,
    NormalityJudgeConfig,
    NormalityJudgeEvent,
    NormalityJudgeInput,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _dimension(score: float = 0.89, rationale: str = "Dimension is plausible.") -> dict[str, Any]:
    return {"score": score, "rationale": rationale, "findings": []}


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "label": "normal",
        "overall_score": 0.89,
        "dimension_scores": {
            name: _dimension(0.89, f"{name} is plausible.")
            for name in NORMALITY_DIMENSIONS
        },
        "findings": [],
        "redactions_applied": [],
    }
    payload.update(overrides)
    return payload


def _input(
    *,
    result_summary: str = "Created a local summary artifact.",
    artifact_paths: list[str] | None = None,
) -> NormalityJudgeInput:
    return NormalityJudgeInput(
        scenario_id="office_document_file_workflow_basic_v1",
        task_summary="Evaluate normal offline office document activity.",
        agent_roles={"office_agent": "office document worker"},
        events=[
            NormalityJudgeEvent(
                agent_id="office_agent",
                role="office document worker",
                action="office_create_docx",
                status="success",
                result_summary=result_summary,
                artifact_paths=artifact_paths or ["artifacts/office/summary.docx"],
            )
        ],
    )


def _config(**overrides: object) -> NormalityJudgeConfig:
    payload = {"enabled": True, "mode": "llm", "judge_provider": "llm"}
    payload.update(overrides)
    return NormalityJudgeConfig.model_validate(payload)


class CompleteClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[str, float | None]] = []

    def complete(self, prompt: str, *, timeout_s: float | None = None) -> object:
        self.calls.append((prompt, timeout_s))
        return self.response


class ChatClient:
    def __init__(self, response: object) -> None:
        self.response = response
        self.calls: list[tuple[str, float | None]] = []

    def chat(self, prompt: str, *, timeout_s: float | None = None) -> object:
        self.calls.append((prompt, timeout_s))
        return self.response


class RaisingClient:
    def complete(self, prompt: str, *, timeout_s: float | None = None) -> str:
        del prompt, timeout_s
        raise RuntimeError("token-like details must not leak")


def test_adapter_with_fake_complete_client_returns_text() -> None:
    client = CompleteClient("plain response")
    adapter = LocalLLMNormalityJudgeClientAdapter(client)

    assert adapter.complete("prompt", timeout_s=1.5) == "plain response"
    assert client.calls == [("prompt", 1.5)]


def test_adapter_with_callable_client_returns_text() -> None:
    calls: list[str] = []

    def fake_client(prompt: str) -> str:
        calls.append(prompt)
        return "callable response"

    adapter = LocalLLMNormalityJudgeClientAdapter(fake_client)

    assert adapter.complete("prompt") == "callable response"
    assert calls == ["prompt"]


def test_adapter_with_chat_response_extracts_text() -> None:
    raw = json.dumps(_payload(label="suspicious"))
    client = ChatClient({"choices": [{"message": {"content": raw}}]})
    adapter = LocalLLMNormalityJudgeClientAdapter(client)

    assert adapter.complete("prompt") == raw
    assert client.calls == [("prompt", None)]


def test_adapter_with_object_response_extracts_text() -> None:
    class Response:
        output_text = "object text"

    adapter = LocalLLMNormalityJudgeClientAdapter(CompleteClient(Response()))

    assert adapter.complete("prompt") == "object text"


def test_adapter_never_creates_local_llm_client_by_itself(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = __import__

    def forbidden_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"agent.llm_client", "src.agent.llm_client", "httpx"}:
            raise AssertionError("adapter must not import or create local runtime clients")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", forbidden_import)
    adapter = LocalLLMNormalityJudgeClientAdapter(CompleteClient("safe response"))

    assert adapter.complete("prompt") == "safe response"


def test_provider_using_adapter_calls_fake_client_once_and_parses_json() -> None:
    client = CompleteClient(json.dumps(_payload(overall_score=0.81)))
    adapter = LocalLLMNormalityJudgeClientAdapter(client)

    result = LLMNormalityJudgeProvider(llm_client=adapter).evaluate(_input(), _config())

    assert result.status == "ok"
    assert result.overall_score == 0.81
    assert result.judge_mode == "llm_injected_client"
    assert result.provider_name == "llm_normality_judge_injected_client"
    assert len(client.calls) == 1


def test_provider_using_adapter_handles_fenced_json() -> None:
    raw = "```json\n" + json.dumps(_payload(label="suspicious")) + "\n```"
    adapter = LocalLLMNormalityJudgeClientAdapter(CompleteClient(raw))

    result = LLMNormalityJudgeProvider(llm_client=adapter).evaluate(_input(), _config())

    assert result.status == "ok"
    assert result.label == "suspicious"


def test_provider_using_adapter_handles_client_exception() -> None:
    adapter = LocalLLMNormalityJudgeClientAdapter(RaisingClient())

    result = LLMNormalityJudgeProvider(llm_client=adapter).evaluate(_input(), _config())

    assert result.status == "invalid_input"
    assert "llm_judge_client_failed" in result.findings
    assert "llm_judge_client_error:RuntimeError" in result.findings
    assert all("token-like" not in finding for finding in result.findings)


def test_provider_using_adapter_handles_non_string_response_safely() -> None:
    adapter = LocalLLMNormalityJudgeClientAdapter(CompleteClient({"unexpected": ["shape"]}))

    result = LLMNormalityJudgeProvider(llm_client=adapter).evaluate(_input(), _config())

    assert result.status == "invalid_input"
    assert "llm_judge_client_failed" in result.findings
    assert "llm_judge_client_error:TypeError" in result.findings


def test_prompt_passed_to_fake_client_is_redacted_and_truncated() -> None:
    posix_path = "/home/example/outside_workspace/outside.docx"
    long_text = f"Created {posix_path} " + ("A" * 240)
    client = CompleteClient(json.dumps(_payload()))
    adapter = LocalLLMNormalityJudgeClientAdapter(client)

    LLMNormalityJudgeProvider(llm_client=adapter).evaluate(
        _input(result_summary=long_text, artifact_paths=[posix_path]),
        _config(max_text_chars=45),
    )
    prompt = client.calls[0][0]

    assert posix_path not in prompt
    assert "A" * 240 not in prompt
    assert "<absolute_path>" in prompt
    assert "...[truncated]" in prompt


def test_adapter_path_does_not_import_http_model_browser_or_office(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = __import__

    def forbidden_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("adapter path must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", forbidden_import)
    adapter = LocalLLMNormalityJudgeClientAdapter(CompleteClient(json.dumps(_payload())))

    result = LLMNormalityJudgeProvider(llm_client=adapter).evaluate(_input(), _config())

    assert result.status == "ok"


def test_normality_judge_source_does_not_import_runtime_backends_for_adapter() -> None:
    source = (PROJECT_ROOT / "src" / "agent" / "normality_judge.py").read_text(encoding="utf-8")
    forbidden_tokens = [
        "import httpx",
        "from httpx",
        "import playwright",
        "from playwright",
        "import subprocess",
        "import docx",
        "from docx",
        "import openpyxl",
        "from openpyxl",
        "import pptx",
        "from pptx",
        "llama-server",
    ]

    assert all(token not in source for token in forbidden_tokens)
