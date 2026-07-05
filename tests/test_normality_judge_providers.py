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
