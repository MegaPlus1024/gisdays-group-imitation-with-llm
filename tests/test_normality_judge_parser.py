from __future__ import annotations

import json
from pathlib import Path
from typing import Any

from src.agent.normality_judge import (
    LLMNormalityJudgeProvider,
    NORMALITY_DIMENSIONS,
    NORMALITY_JUDGE_SCHEMA_VERSION,
    NormalityJudgeConfig,
    NormalityJudgeEvent,
    NormalityJudgeInput,
    parse_llm_normality_judge_output,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _dimension(score: float | str = 0.87, rationale: str = "Dimension rationale.") -> dict[str, Any]:
    return {"score": score, "rationale": rationale, "findings": []}


def _payload(**overrides: Any) -> dict[str, Any]:
    payload: dict[str, Any] = {
        "label": "normal",
        "overall_score": 0.87,
        "dimension_scores": {
            name: _dimension(0.87, f"{name} looks plausible.")
            for name in NORMALITY_DIMENSIONS
        },
        "findings": [],
        "redactions_applied": True,
    }
    payload.update(overrides)
    return payload


def _input() -> NormalityJudgeInput:
    return NormalityJudgeInput(
        scenario_id="office_document_file_workflow_basic_v1",
        task_summary="Evaluate parsed LLM normality output.",
        events=[
            NormalityJudgeEvent(
                agent_id="office_agent",
                role="office document worker",
                action="office_create_docx",
                status="success",
            )
        ],
    )


def test_parse_valid_exact_json() -> None:
    result = parse_llm_normality_judge_output(json.dumps(_payload()))

    assert result.status == "ok"
    assert result.label == "normal"
    assert result.overall_score == 0.87
    assert set(result.dimension_scores) == set(NORMALITY_DIMENSIONS)
    assert result.provider_name == "llm_normality_judge_parser"


def test_parse_json_inside_markdown_code_fence() -> None:
    raw = "```json\n" + json.dumps(_payload(label="suspicious")) + "\n```"

    result = parse_llm_normality_judge_output(raw)

    assert result.status == "ok"
    assert result.label == "suspicious"


def test_parse_json_with_safe_pre_and_post_text() -> None:
    raw = "Analysis omitted.\n" + json.dumps(_payload(label="abnormal")) + "\nDone."

    result = parse_llm_normality_judge_output(raw)

    assert result.status == "ok"
    assert result.label == "abnormal"


def test_invalid_json_returns_controlled_invalid_result() -> None:
    result = parse_llm_normality_judge_output("{not json")

    assert result.status == "invalid_input"
    assert result.label == "not_evaluated"
    assert result.findings == ["llm_judge_parse_failed"]


def test_missing_required_label_returns_controlled_invalid_result() -> None:
    payload = _payload()
    payload.pop("label")

    result = parse_llm_normality_judge_output(json.dumps(payload))

    assert result.status == "invalid_input"
    assert result.findings == ["llm_judge_schema_invalid"]


def test_unknown_label_returns_controlled_invalid_result() -> None:
    result = parse_llm_normality_judge_output(json.dumps(_payload(label="excellent")))

    assert result.status == "invalid_input"
    assert result.findings == ["llm_judge_unknown_label"]


def test_score_strings_are_coerced() -> None:
    payload = _payload(overall_score="0.82")
    payload["dimension_scores"]["task_relevance"]["score"] = "0.81"

    result = parse_llm_normality_judge_output(json.dumps(payload))

    assert result.status == "ok"
    assert result.overall_score == 0.82
    assert result.dimension_scores["task_relevance"].score == 0.81


def test_out_of_range_scores_are_clamped_with_finding() -> None:
    payload = _payload(overall_score=1.7)
    payload["dimension_scores"]["action_safety"]["score"] = -0.5

    result = parse_llm_normality_judge_output(json.dumps(payload))

    assert result.status == "ok"
    assert result.overall_score == 1.0
    assert result.dimension_scores["action_safety"].score == 0.0
    assert "score_clamped" in result.findings


def test_missing_dimension_returns_controlled_invalid_result() -> None:
    payload = _payload()
    payload["dimension_scores"].pop("artifact_hygiene")

    result = parse_llm_normality_judge_output(json.dumps(payload))

    assert result.status == "invalid_input"
    assert result.findings == ["llm_judge_dimension_missing"]


def test_extra_unknown_fields_do_not_break_parser() -> None:
    result = parse_llm_normality_judge_output(
        json.dumps(_payload(extra_field={"ignored": True}))
    )

    assert result.status == "ok"
    assert result.label == "normal"


def test_long_rationale_is_truncated() -> None:
    payload = _payload()
    payload["dimension_scores"]["task_relevance"]["rationale"] = "A" * 240

    result = parse_llm_normality_judge_output(
        json.dumps(payload),
        NormalityJudgeConfig(enabled=True, mode="llm", max_text_chars=40),
    )

    assert "A" * 240 not in result.dimension_scores["task_relevance"].rationale
    assert "...[truncated]" in result.dimension_scores["task_relevance"].rationale
    assert "truncated_text" in result.redactions_applied


def test_absolute_windows_path_is_redacted_in_rationale_and_finding() -> None:
    windows_path = "\\".join(["C:", "Users", "Example", "outside_workspace", "outside.docx"])
    payload = _payload(findings=[f"Observed {windows_path}"])
    payload["dimension_scores"]["artifact_hygiene"]["rationale"] = f"Observed {windows_path}"

    result = parse_llm_normality_judge_output(json.dumps(payload))
    serialized = result.model_dump_json()

    assert windows_path not in serialized
    assert "absolute_path" in result.redactions_applied


def test_absolute_posix_path_is_redacted_in_rationale_and_finding() -> None:
    posix_path = "/home/example/outside_workspace/outside.docx"
    payload = _payload(findings=[f"Observed {posix_path}"])
    payload["dimension_scores"]["artifact_hygiene"]["rationale"] = f"Observed {posix_path}"

    result = parse_llm_normality_judge_output(json.dumps(payload))
    serialized = result.model_dump_json()

    assert posix_path not in serialized
    assert "absolute_path" in result.redactions_applied


def test_relative_artifact_path_is_preserved() -> None:
    relative_path = "artifacts/office/summary.docx"
    payload = _payload(findings=[f"Observed {relative_path}"])
    payload["dimension_scores"]["artifact_hygiene"]["rationale"] = f"Observed {relative_path}"

    result = parse_llm_normality_judge_output(json.dumps(payload))
    serialized = result.model_dump_json()

    assert result.status == "ok"
    assert relative_path in serialized


def test_parser_result_includes_schema_version_and_llm_marker() -> None:
    result = parse_llm_normality_judge_output(json.dumps(_payload()))

    assert result.schema_version == NORMALITY_JUDGE_SCHEMA_VERSION
    assert result.judge_mode == "llm"
    assert result.provider_name == "llm_normality_judge_parser"


def test_llm_placeholder_provider_with_raw_response_uses_parser() -> None:
    provider = LLMNormalityJudgeProvider(raw_response=json.dumps(_payload(label="suspicious")))

    result = provider.evaluate(
        _input(),
        NormalityJudgeConfig(enabled=True, mode="llm", judge_provider="llm"),
    )

    assert result.status == "ok"
    assert result.label == "suspicious"
    assert result.provider_name == "llm_normality_judge_parser"


def test_llm_placeholder_provider_without_raw_response_stays_not_configured() -> None:
    result = LLMNormalityJudgeProvider().evaluate(
        _input(),
        NormalityJudgeConfig(enabled=True, mode="llm", judge_provider="llm"),
    )

    assert result.status == "invalid_input"
    assert result.label == "not_evaluated"
    assert result.findings == ["llm_judge_provider_not_configured"]
    assert result.provider_name == "llm_normality_judge_placeholder"


def test_parser_source_does_not_import_runtime_backends() -> None:
    source = (PROJECT_ROOT / "src" / "agent" / "normality_judge.py").read_text(
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

    assert all(token not in source for token in forbidden_tokens)
