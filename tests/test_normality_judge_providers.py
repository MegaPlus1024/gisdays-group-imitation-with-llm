from __future__ import annotations

import json
from pathlib import Path

from src.agent.normality_evaluation_runner import (
    NORMALITY_EVALUATION_SUMMARY_FILENAME,
    NormalityEvaluationRunConfig,
    run_normality_evaluation_from_file,
)
from src.agent.normality_judge import (
    DeterministicNormalityJudgeProvider,
    DisabledNormalityJudgeProvider,
    LLMNormalityJudgeProvider,
    NORMALITY_DIMENSIONS,
    NormalityJudgeConfig,
    NormalityJudgeEvent,
    NormalityJudgeInput,
    NormalityJudgeResult,
    StaticNormalityJudgeProvider,
    create_normality_judge_provider,
    run_normality_judge,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _enabled_config(**overrides: object) -> NormalityJudgeConfig:
    payload = {"enabled": True, "mode": "deterministic"}
    payload.update(overrides)
    return NormalityJudgeConfig.model_validate(payload)


def _judge_input() -> NormalityJudgeInput:
    return NormalityJudgeInput(
        scenario_id="office_document_file_workflow_basic_v1",
        task_summary="Evaluate normal offline office document activity.",
        agent_roles={"office_agent": "office document worker"},
        constraints=["allowed_actions: office_create_docx"],
        events=[
            NormalityJudgeEvent(
                agent_id="office_agent",
                role="office document worker",
                action="office_create_docx",
                status="success",
                artifact_paths=["artifacts/office/summary.docx"],
                result_summary="Created a local summary artifact.",
            )
        ],
    )


def _llm_dimension(score: float = 0.91, rationale: str = "Dimension is plausible.") -> dict[str, object]:
    return {"score": score, "rationale": rationale, "findings": []}


def _llm_payload(**overrides: object) -> dict[str, object]:
    payload: dict[str, object] = {
        "label": "normal",
        "overall_score": 0.91,
        "dimension_scores": {
            name: _llm_dimension(0.91, f"{name} is plausible.")
            for name in NORMALITY_DIMENSIONS
        },
        "findings": [],
        "redactions_applied": [],
    }
    payload.update(overrides)
    return payload


class FakeLLMClient:
    def __init__(self, response: str) -> None:
        self.response = response
        self.calls: list[tuple[str, float | None]] = []

    def complete(self, prompt: str, *, timeout_s: float | None = None) -> str:
        self.calls.append((prompt, timeout_s))
        return self.response


class RaisingLLMClient:
    def complete(self, prompt: str, *, timeout_s: float | None = None) -> str:
        del prompt, timeout_s
        raise RuntimeError("sensitive details should not be included")


def _write_events(path: Path) -> None:
    path.write_text(
        json.dumps(
            [
                {
                    "agent_id": "office_agent",
                    "role": "office document worker",
                    "action": "office_create_docx",
                    "status": "success",
                    "summary": "Created a local summary artifact.",
                    "artifact_paths": ["artifacts/office/summary.docx"],
                }
            ],
            ensure_ascii=False,
        ),
        encoding="utf-8",
    )


def test_deterministic_provider_matches_run_normality_judge_shape() -> None:
    judge_input = _judge_input()
    config = _enabled_config()

    provider_result = DeterministicNormalityJudgeProvider().evaluate(judge_input, config)
    function_result = run_normality_judge(judge_input, config)

    assert provider_result.status == function_result.status == "ok"
    assert provider_result.label == function_result.label
    assert provider_result.overall_score == function_result.overall_score
    assert provider_result.provider_name == "deterministic_normality_judge"
    assert function_result.provider_name == "deterministic_normality_judge"


def test_run_normality_judge_backward_compatibility_still_works() -> None:
    result = run_normality_judge(_judge_input(), _enabled_config())

    assert result.status == "ok"
    assert result.label == "normal"
    assert result.judge_mode == "deterministic"
    assert "overall_normality" in result.dimension_scores


def test_disabled_provider_returns_not_evaluated() -> None:
    result = DisabledNormalityJudgeProvider().evaluate(
        _judge_input(),
        NormalityJudgeConfig(enabled=False, mode="disabled"),
    )

    assert result.status == "disabled"
    assert result.label == "not_evaluated"
    assert result.overall_score == 0.0
    assert result.provider_name == "disabled_normality_judge"


def test_provider_factory_maps_fake_and_deterministic() -> None:
    fake = create_normality_judge_provider(_enabled_config(mode="fake"))
    deterministic = create_normality_judge_provider(_enabled_config(mode="deterministic"))

    assert isinstance(fake, DeterministicNormalityJudgeProvider)
    assert isinstance(deterministic, DeterministicNormalityJudgeProvider)


def test_provider_factory_maps_disabled() -> None:
    provider = create_normality_judge_provider(
        _enabled_config(judge_provider="disabled"),
    )

    assert isinstance(provider, DisabledNormalityJudgeProvider)


def test_provider_factory_uses_injected_static_provider() -> None:
    result = NormalityJudgeResult(
        status="ok",
        label="suspicious",
        overall_score=0.42,
        findings=["static_provider_used"],
        judge_mode="static",
    )
    provider = StaticNormalityJudgeProvider(result)

    assert create_normality_judge_provider(_enabled_config(judge_provider="static"), provider=provider) is provider
    evaluated = provider.evaluate(_judge_input(), _enabled_config(judge_provider="static"))
    assert evaluated.provider_name == "static_normality_judge"


def test_llm_placeholder_returns_controlled_not_configured_result() -> None:
    result = LLMNormalityJudgeProvider().evaluate(
        _judge_input(),
        _enabled_config(judge_provider="llm"),
    )

    assert result.status == "invalid_input"
    assert result.label == "not_evaluated"
    assert result.provider_name == "llm_normality_judge_placeholder"
    assert result.findings == ["llm_judge_provider_not_configured"]


def test_llm_provider_with_raw_response_still_uses_parser() -> None:
    provider = LLMNormalityJudgeProvider(raw_response=json.dumps(_llm_payload(label="suspicious")))

    result = provider.evaluate(_judge_input(), _enabled_config(mode="llm", judge_provider="llm"))

    assert result.status == "ok"
    assert result.label == "suspicious"
    assert result.provider_name == "llm_normality_judge_parser"
    assert result.judge_mode == "llm"


def test_llm_provider_with_fake_injected_client_calls_client_once() -> None:
    client = FakeLLMClient(json.dumps(_llm_payload()))
    provider = LLMNormalityJudgeProvider(llm_client=client, timeout_s=2.5)

    result = provider.evaluate(_judge_input(), _enabled_config(mode="llm", judge_provider="llm"))

    assert result.status == "ok"
    assert result.label == "normal"
    assert result.provider_name == "llm_normality_judge_injected_client"
    assert result.judge_mode == "llm_injected_client"
    assert "llm_judge_injected_client_used" in result.findings
    assert "external_model_runtime_false" in result.findings
    assert len(client.calls) == 1
    assert client.calls[0][1] == 2.5


def test_fake_injected_client_receives_prompt_contract_and_dimensions() -> None:
    client = FakeLLMClient(json.dumps(_llm_payload()))

    LLMNormalityJudgeProvider(llm_client=client).evaluate(
        _judge_input(),
        _enabled_config(mode="llm", judge_provider="llm"),
    )
    prompt = client.calls[0][0]

    assert "NORMALITY_JUDGE_PROMPT_CONTRACT" in prompt
    assert "OUTPUT_JSON_CONTRACT" in prompt
    assert "FINAL_RESPONSE_RULE" in prompt
    assert all(name in prompt for name in NORMALITY_DIMENSIONS)


def test_injected_callable_response_parses_to_result() -> None:
    calls: list[str] = []

    def fake_callable(prompt: str) -> str:
        calls.append(prompt)
        return json.dumps(_llm_payload(overall_score=0.77))

    result = LLMNormalityJudgeProvider(llm_client=fake_callable).evaluate(
        _judge_input(),
        _enabled_config(mode="llm", judge_provider="llm"),
    )

    assert result.status == "ok"
    assert result.overall_score == 0.77
    assert len(calls) == 1


def test_injected_client_markdown_fenced_json_parses() -> None:
    raw = "```json\n" + json.dumps(_llm_payload(label="suspicious")) + "\n```"
    client = FakeLLMClient(raw)

    result = LLMNormalityJudgeProvider(llm_client=client).evaluate(
        _judge_input(),
        _enabled_config(mode="llm", judge_provider="llm"),
    )

    assert result.status == "ok"
    assert result.label == "suspicious"
    assert result.judge_mode == "llm_injected_client"


def test_injected_client_malformed_json_returns_controlled_invalid_result() -> None:
    client = FakeLLMClient("{not json")

    result = LLMNormalityJudgeProvider(llm_client=client).evaluate(
        _judge_input(),
        _enabled_config(mode="llm", judge_provider="llm"),
    )

    assert result.status == "invalid_input"
    assert "llm_judge_parse_failed" in result.findings
    assert result.provider_name == "llm_normality_judge_injected_client"


def test_injected_client_exception_returns_controlled_invalid_result() -> None:
    result = LLMNormalityJudgeProvider(llm_client=RaisingLLMClient()).evaluate(
        _judge_input(),
        _enabled_config(mode="llm", judge_provider="llm"),
    )

    assert result.status == "invalid_input"
    assert "llm_judge_client_failed" in result.findings
    assert "llm_judge_client_error:RuntimeError" in result.findings
    assert all("sensitive" not in finding for finding in result.findings)


def test_injected_client_empty_string_returns_controlled_invalid_result() -> None:
    result = LLMNormalityJudgeProvider(llm_client=FakeLLMClient("  ")).evaluate(
        _judge_input(),
        _enabled_config(mode="llm", judge_provider="llm"),
    )

    assert result.status == "invalid_input"
    assert result.findings == ["external_model_runtime_false", "llm_judge_empty_response"]


def test_prompt_sent_to_injected_client_is_redacted_and_truncated() -> None:
    posix_path = "/home/example/outside_workspace/outside.docx"
    long_text = f"Created {posix_path} " + ("A" * 240)
    judge_input = NormalityJudgeInput(
        scenario_id="office_document_file_workflow_basic_v1",
        task_summary="Evaluate local offline activity.",
        events=[
            NormalityJudgeEvent(
                agent_id="office_agent",
                role="office document worker",
                action="office_create_docx",
                status="success",
                result_summary=long_text,
                artifact_paths=[posix_path],
            )
        ],
    )
    client = FakeLLMClient(json.dumps(_llm_payload()))

    LLMNormalityJudgeProvider(llm_client=client).evaluate(
        judge_input,
        _enabled_config(mode="llm", judge_provider="llm", max_text_chars=45),
    )
    prompt = client.calls[0][0]

    assert posix_path not in prompt
    assert "A" * 240 not in prompt
    assert "<absolute_path>" in prompt
    assert "...[truncated]" in prompt


def test_injected_client_path_does_not_create_runtime_imports(monkeypatch) -> None:
    original_import = __import__

    def forbidden_import(name: str, *args: object, **kwargs: object) -> object:
        if name in {"httpx", "openai", "playwright", "docx", "openpyxl", "pptx"}:
            raise AssertionError("injected LLM judge path must stay offline")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr("builtins.__import__", forbidden_import)
    result = LLMNormalityJudgeProvider(llm_client=FakeLLMClient(json.dumps(_llm_payload()))).evaluate(
        _judge_input(),
        _enabled_config(mode="llm", judge_provider="llm"),
    )

    assert result.status == "ok"


def test_provider_factory_can_construct_llm_provider_with_injected_client() -> None:
    client = FakeLLMClient(json.dumps(_llm_payload(label="suspicious")))
    provider = create_normality_judge_provider(
        _enabled_config(mode="llm", judge_provider="llm"),
        llm_client=client,
    )

    result = provider.evaluate(_judge_input(), _enabled_config(mode="llm", judge_provider="llm"))

    assert isinstance(provider, LLMNormalityJudgeProvider)
    assert result.status == "ok"
    assert result.label == "suspicious"
    assert len(client.calls) == 1


def test_injected_static_provider_is_used_by_runner(tmp_path: Path) -> None:
    events_path = tmp_path / "events.json"
    output_dir = tmp_path / "normality"
    _write_events(events_path)
    static_result = NormalityJudgeResult(
        status="ok",
        label="suspicious",
        overall_score=0.42,
        findings=["static_provider_used"],
        judge_mode="static",
    )

    result = run_normality_evaluation_from_file(
        NormalityEvaluationRunConfig(
            project_root=tmp_path,
            input_path="events.json",
            output_dir="normality",
            scenario_id="office_document_file_workflow_basic_v1",
            task_summary="Evaluate with injected static provider.",
            judge_provider="static",
        ),
        provider=StaticNormalityJudgeProvider(static_result),
    )
    summary = json.loads((output_dir / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(encoding="utf-8"))

    assert result.label == "suspicious"
    assert result.overall_score == 0.42
    assert result.judge_provider == "static_normality_judge"
    assert summary["judge_provider"] == "static_normality_judge"
    assert summary["findings"] == ["static_provider_used"]


def test_runner_summary_includes_deterministic_provider_and_mode(tmp_path: Path) -> None:
    _write_events(tmp_path / "events.json")

    run_normality_evaluation_from_file(
        NormalityEvaluationRunConfig(
            project_root=tmp_path,
            input_path="events.json",
            output_dir="normality",
            scenario_id="office_document_file_workflow_basic_v1",
            task_summary="Evaluate deterministic provider metadata.",
        )
    )
    summary = json.loads(
        (tmp_path / "normality" / NORMALITY_EVALUATION_SUMMARY_FILENAME).read_text(
            encoding="utf-8"
        )
    )

    assert summary["judge_mode"] == "deterministic"
    assert summary["judge_provider"] == "deterministic_normality_judge"
    assert summary["judge_result"]["provider_name"] == "deterministic_normality_judge"


def test_provider_modules_do_not_import_runtime_backends() -> None:
    normality_source = (PROJECT_ROOT / "src" / "agent" / "normality_judge.py").read_text(
        encoding="utf-8"
    )
    runner_source = (PROJECT_ROOT / "src" / "agent" / "normality_evaluation_runner.py").read_text(
        encoding="utf-8"
    )
    forbidden_tokens = [
        "import httpx",
        "from httpx",
        "LocalLLMClient",
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

    assert all(token not in normality_source for token in forbidden_tokens)
    assert all(token not in runner_source for token in forbidden_tokens)
