from __future__ import annotations

from pathlib import Path

from src.agent.normality_judge import (
    DeterministicNormalityJudge,
    NormalityJudgeConfig,
    NormalityJudgeEvent,
    NormalityJudgeInput,
    aggregate_normality_results,
    build_normality_judge_prompt,
    normality_judge_input_from_group_history,
    run_normality_judge,
    sanitize_judge_text,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]


def _enabled_config(**overrides: object) -> NormalityJudgeConfig:
    payload = {"enabled": True, "mode": "deterministic"}
    payload.update(overrides)
    return NormalityJudgeConfig.model_validate(payload)


def _event(
    action: str,
    *,
    agent_id: str = "office_agent",
    role: str = "office worker",
    status: str = "success",
    error_code: str | None = None,
    policy_decision: str | None = None,
    result_summary: str | None = "Completed local activity.",
    params_summary: str | None = None,
    artifact_paths: list[str] | None = None,
) -> NormalityJudgeEvent:
    return NormalityJudgeEvent(
        agent_id=agent_id,
        role=role,
        action=action,
        status=status,
        error_code=error_code,
        params_summary=params_summary,
        result_summary=result_summary,
        artifact_paths=artifact_paths or [],
        policy_decision=policy_decision,
    )


def _judge_input(events: list[NormalityJudgeEvent], **overrides: object) -> NormalityJudgeInput:
    payload = {
        "scenario_id": "office_document_file_workflow_basic_v1",
        "task_summary": "Evaluate normal office and browser-like local user activity.",
        "agent_roles": {
            "office_agent": "office worker",
            "browser_agent": "browser worker",
            "developer_agent": "developer",
        },
        "events": events,
        "constraints": [
            "allowed_actions: office_create_docx, office_append_docx_section, browser_open_url, read_file",
            "forbidden_actions: run_shell_command",
        ],
        "expected_behavior": "Use allowed local actions and keep artifacts relative.",
        "environment_summary": "Controlled offline local activity environment.",
    }
    payload.update(overrides)
    return NormalityJudgeInput.model_validate(payload)


def test_disabled_config_returns_not_evaluated() -> None:
    result = run_normality_judge(
        _judge_input([_event("office_create_docx")]),
        NormalityJudgeConfig(enabled=False),
    )

    assert result.status == "disabled"
    assert result.label == "not_evaluated"
    assert result.overall_score == 0.0


def test_empty_input_returns_invalid_result() -> None:
    result = run_normality_judge(_judge_input([]), _enabled_config())

    assert result.status == "invalid_input"
    assert result.label == "not_evaluated"
    assert result.overall_score == 0.0


def test_successful_coherent_sequence_scores_high() -> None:
    result = run_normality_judge(
        _judge_input(
            [
                _event("office_create_docx", artifact_paths=["artifacts/office/report.docx"]),
                _event("office_append_docx_section", artifact_paths=["artifacts/office/report.docx"]),
                _event(
                    "browser_open_url",
                    agent_id="browser_agent",
                    role="browser worker",
                    result_summary="Opened allowlisted local page.",
                ),
            ]
        ),
        _enabled_config(),
    )

    assert result.status == "ok"
    assert result.label == "normal"
    assert result.overall_score >= 0.8
    assert result.dimension_scores["action_safety"].score >= 0.8


def test_policy_denied_or_forbidden_action_scores_lower() -> None:
    clean = run_normality_judge(
        _judge_input([_event("office_create_docx")]),
        _enabled_config(),
    )
    denied = run_normality_judge(
        _judge_input(
            [
                _event(
                    "run_shell_command",
                    role="office worker",
                    status="failure",
                    error_code="virtual_network_policy_denied",
                    policy_decision="policy_denied",
                )
            ]
        ),
        _enabled_config(),
    )

    assert denied.overall_score < clean.overall_score
    assert denied.dimension_scores["action_safety"].score < clean.dimension_scores["action_safety"].score
    assert "policy_denied_events_present" in denied.findings


def test_repeated_execution_errors_reduce_error_recovery() -> None:
    result = run_normality_judge(
        _judge_input(
            [
                _event("office_create_docx", status="failure", error_code="execution_failed"),
                _event("office_create_docx", status="failure", error_code="execution_failed"),
                _event("office_create_docx", status="failure", error_code="execution_failed"),
            ]
        ),
        _enabled_config(),
    )

    assert result.dimension_scores["error_recovery"].score < 0.3
    assert "repeated_errors_present" in result.findings


def test_role_inconsistent_action_reduces_role_consistency() -> None:
    result = run_normality_judge(
        _judge_input(
            [
                _event(
                    "browser_open_url",
                    role="office worker",
                    result_summary="Tried browser action from office-only role.",
                )
            ],
            constraints=["allowed_actions: office_create_docx"],
        ),
        _enabled_config(),
    )

    assert result.dimension_scores["role_consistency"].score < 1.0
    assert "role_inconsistent_actions_present" in result.findings


def test_scores_are_clamped_between_zero_and_one() -> None:
    result = run_normality_judge(
        _judge_input(
            [
                _event(
                    "run_shell_command",
                    status="failure",
                    error_code="policy_denied",
                    policy_decision="policy_denied",
                    artifact_paths=["/home/example/outside.txt"],
                )
                for _ in range(12)
            ],
            constraints=["forbidden_actions: run_shell_command"],
        ),
        _enabled_config(),
    )

    assert 0.0 <= result.overall_score <= 1.0
    assert all(0.0 <= score.score <= 1.0 for score in result.dimension_scores.values())


def test_labels_follow_thresholds() -> None:
    normal = run_normality_judge(
        _judge_input([_event("office_create_docx")]),
        _enabled_config(score_threshold_normal=0.8, score_threshold_suspicious=0.5),
    )
    suspicious = run_normality_judge(
        _judge_input(
            [
                _event(
                    "run_shell_command",
                    status="failure",
                    error_code="policy_denied",
                    policy_decision="policy_denied",
                )
            ],
            constraints=["forbidden_actions: run_shell_command"],
        ),
        _enabled_config(score_threshold_normal=0.8, score_threshold_suspicious=0.5),
    )
    abnormal = run_normality_judge(
        _judge_input(
            [
                _event(
                    "run_shell_command",
                    status="failure",
                    error_code="policy_denied",
                    policy_decision="policy_denied",
                    artifact_paths=["/home/example/outside.txt"],
                )
                for _ in range(4)
            ],
            constraints=["forbidden_actions: run_shell_command"],
        ),
        _enabled_config(score_threshold_normal=0.95, score_threshold_suspicious=0.75),
    )

    assert normal.label == "normal"
    assert suspicious.label == "suspicious"
    assert abnormal.label == "abnormal"


def test_prompt_builder_includes_json_contract() -> None:
    prompt = build_normality_judge_prompt(
        _judge_input([_event("office_create_docx")]),
        _enabled_config(),
    )

    assert "OUTPUT_JSON_CONTRACT" in prompt
    assert "overall_normality" in prompt
    assert "Return strict JSON only" in prompt
    assert "Do not make production-readiness" in prompt


def test_prompt_builder_truncates_long_text() -> None:
    long_text = "A" * 300
    prompt = build_normality_judge_prompt(
        _judge_input([_event("office_create_docx", result_summary=long_text)]),
        _enabled_config(max_text_chars=40),
    )

    assert long_text not in prompt
    assert "...[truncated]" in prompt


def test_windows_absolute_path_is_redacted() -> None:
    path = "C:" + "\\" + "Users" + "\\" + "Example" + "\\" + "secret.txt"
    sanitized, redactions = sanitize_judge_text(
        f"Read from {path}",
        _enabled_config(),
    )

    assert "<absolute_path>" in sanitized
    assert path not in sanitized
    assert "absolute_path" in redactions


def test_posix_absolute_path_is_redacted() -> None:
    path = "/home/example/secret.txt"
    sanitized, redactions = sanitize_judge_text(
        f"Read from {path}",
        _enabled_config(),
    )

    assert "<absolute_path>" in sanitized
    assert path not in sanitized
    assert "absolute_path" in redactions


def test_relative_artifact_path_is_preserved() -> None:
    path = "artifacts/office/report.docx"
    prompt = build_normality_judge_prompt(
        _judge_input([_event("office_create_docx", artifact_paths=[path])]),
        _enabled_config(),
    )

    assert path in prompt
    assert "<absolute_path>" not in prompt


def test_aggregation_returns_counts_and_means() -> None:
    result_a = run_normality_judge(
        _judge_input([_event("office_create_docx")]),
        _enabled_config(),
    )
    result_b = run_normality_judge(
        _judge_input(
            [
                _event(
                    "run_shell_command",
                    status="failure",
                    error_code="policy_denied",
                    policy_decision="policy_denied",
                )
            ],
            constraints=["forbidden_actions: run_shell_command"],
        ),
        _enabled_config(),
    )

    aggregate = aggregate_normality_results([result_a, result_b])

    assert aggregate["count"] == 2
    assert aggregate["mean_overall_score"] == (result_a.overall_score + result_b.overall_score) / 2
    assert aggregate["label_counts"][result_a.label] >= 1
    assert aggregate["status_counts"]["ok"] == 2


def test_group_history_adapter_builds_judge_input() -> None:
    judge_input = normality_judge_input_from_group_history(
        scenario_id="scenario_v1",
        task_summary="Review group activity.",
        agent_roles={"office_agent": "office worker"},
        constraints=["allowed_actions: read_file"],
        group_history=[
            {
                "agent_id": "office_agent",
                "action": "read_file",
                "status": "success",
                "summary": "Read local metadata.",
                "metadata": {
                    "validation_accepted": True,
                    "execution_attempted": False,
                    "execution_success": None,
                },
            }
        ],
    )

    assert judge_input.scenario_id == "scenario_v1"
    assert judge_input.events[0].agent_id == "office_agent"
    assert judge_input.events[0].action == "read_file"
    assert "execution_attempted=False" in judge_input.events[0].notes


def test_scaffold_has_no_llm_network_or_optional_runtime_imports() -> None:
    source = (PROJECT_ROOT / "src" / "agent" / "normality_judge.py").read_text(encoding="utf-8")

    assert "httpx" not in source
    assert "LocalLLMClient" not in source
    assert "playwright" not in source.lower()
    assert "import docx" not in source.lower()
    assert "from docx" not in source.lower()
    assert "import openpyxl" not in source.lower()
    assert "from openpyxl" not in source.lower()
    assert "import pptx" not in source.lower()
    assert "from pptx" not in source.lower()


def test_deterministic_judge_class_uses_pure_offline_evaluator() -> None:
    judge = DeterministicNormalityJudge()
    result = judge.evaluate(_judge_input([_event("office_create_docx")]))

    assert result.status == "ok"
    assert result.judge_mode == "deterministic"
