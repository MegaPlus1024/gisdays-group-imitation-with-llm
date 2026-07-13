from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from src.agent.autonomous_browser_stepwise_article_benchmark import (
    DEFAULT_STEPWISE_ARTICLE_ACTIONS,
    EarlyStopFakeModel,
    FindThenAnswerFakeModel,
    FixtureArticleEnvironment,
    HallucinatingFakeModel,
    InvalidActionFakeModel,
    PerfectArticleFakeModel,
    StepwiseArticleAction,
    build_default_article_fixture_catalog,
    build_default_stepwise_article_scenarios,
    run_stepwise_article_benchmark,
    run_stepwise_article_scenario,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_stepwise_article_benchmark_fake.py"


def test_open_article_url_without_network() -> None:
    env = FixtureArticleEnvironment(build_default_article_fixture_catalog())
    scenarios = build_default_stepwise_article_scenarios()
    scenario = scenarios["article_short_single_fact"]
    result = env.open_url(scenario.start_url, scenario)

    assert result["success"] is True
    assert result["logical_url"] == "https://local.article/harbor-office-hours"
    assert result["article_title"] == "Harbor Bulletin"


def test_read_visible_text_returns_section_text() -> None:
    env = FixtureArticleEnvironment(build_default_article_fixture_catalog())
    scenarios = build_default_stepwise_article_scenarios()
    env.open_url(scenarios["article_medium_two_fact_cross_section"].start_url, scenarios["article_medium_two_fact_cross_section"])

    result = env.read_visible_text()

    assert result["success"] is True
    assert result["section_id"] == "policy_scope"
    assert "Workspace policy version 2026" in result["visible_text"]


def test_scroll_down_changes_visible_window() -> None:
    env = FixtureArticleEnvironment(build_default_article_fixture_catalog())
    scenarios = build_default_stepwise_article_scenarios()
    env.open_url(scenarios["article_medium_two_fact_cross_section"].start_url, scenarios["article_medium_two_fact_cross_section"])

    result = env.scroll_down()

    assert result["success"] is True
    assert result["changed_window"] is True
    assert result["section_id"] == "escalation_owner"
    assert "Mira Chen" in result["visible_text"]


def test_find_text_finds_matching_section() -> None:
    env = FixtureArticleEnvironment(build_default_article_fixture_catalog())
    scenarios = build_default_stepwise_article_scenarios()
    env.open_url(scenarios["article_similar_terms_disambiguation"].start_url, scenarios["article_similar_terms_disambiguation"])

    result = env.find_text("manual approval")

    assert result["success"] is True
    assert result["found"] is True
    assert result["section_id"] == "match_review"
    assert result["section_title"] == "Policy Match Review"


def test_extract_section_is_deterministic() -> None:
    env = FixtureArticleEnvironment(build_default_article_fixture_catalog())
    scenarios = build_default_stepwise_article_scenarios()
    env.open_url(scenarios["article_long_multi_section_summary"].start_url, scenarios["article_long_multi_section_summary"])

    result = env.extract_section(section_id="safety_checkpoint")

    assert result["success"] is True
    assert result["section_id"] == "safety_checkpoint"
    assert "every two hours" in result["section_text"]


def test_built_in_scenarios_define_start_urls_present_in_catalog() -> None:
    catalog = build_default_article_fixture_catalog()
    scenarios = build_default_stepwise_article_scenarios()

    for scenario in scenarios.values():
        assert scenario.start_url
        assert scenario.start_url in scenario.allowed_urls
        assert scenario.start_url in catalog


def test_initial_observation_exposes_allowed_urls_and_recommended_start_url() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    scenario = scenarios["article_short_single_fact"]
    env = FixtureArticleEnvironment(build_default_article_fixture_catalog())

    observation = env.observe(scenario)

    assert observation.page_opened is False
    assert observation.current_url is None
    assert observation.allowed_urls == (scenario.start_url,)
    assert observation.recommended_start_url == scenario.start_url
    assert observation.article_title_hint == "Harbor Bulletin"


def test_unknown_open_url_failure_includes_allowed_urls_in_observation() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    scenario = scenarios["article_short_single_fact"]
    env = FixtureArticleEnvironment(build_default_article_fixture_catalog())

    status, error_code, action_valid, details, observation = env.execute_action(
        action=StepwiseArticleAction(
            "browser_open_url",
            {"url": "https://example.com/harbor-office-hours"},
        ),
        scenario=scenario,
    )

    assert status == "failed"
    assert error_code == "unknown_article_url"
    assert action_valid is False
    assert details["allowed_urls"] == [scenario.start_url]
    assert observation.allowed_urls == (scenario.start_url,)
    assert observation.recommended_start_url == scenario.start_url
    assert observation.last_error_code == "unknown_article_url"
    assert observation.last_error_message


def test_redundant_extract_observation_includes_progress_feedback() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    scenario = scenarios["article_medium_two_fact_cross_section"]
    env = FixtureArticleEnvironment(build_default_article_fixture_catalog())

    env.execute_action(
        StepwiseArticleAction("browser_open_url", {"url": scenario.start_url}),
        scenario,
    )
    env.execute_action(
        StepwiseArticleAction("browser_extract_section", {"section_id": "policy_scope"}),
        scenario,
    )
    status, error_code, action_valid, details, observation = env.execute_action(
        StepwiseArticleAction("browser_extract_section", {"section_id": "policy_scope"}),
        scenario,
    )

    assert status == "succeeded"
    assert error_code is None
    assert action_valid is True
    assert details["redundant"] is True
    assert details["newly_observed_section_ids"] == []
    assert observation.last_action_status == "succeeded"
    assert observation.last_action_redundant is True
    assert observation.last_newly_observed_section_ids == ()
    assert observation.sections_read_progress == "1/2"
    assert observation.sections_unread_count == 1
    assert observation.unread_section_ids == ("escalation_owner",)
    assert observation.last_action_message
    assert "Last action succeeded but was redundant" in observation.last_action_message
    assert "Sections read: 1/2" in observation.last_action_message
    assert "Do not repeat the same action with the same parameters" in observation.last_action_message


def test_repeated_invalid_open_url_loop_stops_early() -> None:
    scenarios = build_default_stepwise_article_scenarios()

    class RepeatingInvalidUrlModel:
        model_name = "repeating_invalid_url_model"

        def next_action(self, task, observation, memory):  # type: ignore[no-untyped-def]
            return StepwiseArticleAction(
                "browser_open_url",
                {"url": "https://example.com/harbor-office-hours"},
            )

    result = run_stepwise_article_scenario(
        scenarios["article_short_single_fact"],
        RepeatingInvalidUrlModel(),
        max_steps=12,
    )

    assert result.status == "failed"
    assert result.stop_reason == "repeated_invalid_action_loop"
    assert result.error_code == "repeated_invalid_action_loop"
    assert result.evaluation.max_steps_exceeded is False
    assert result.evaluation.invalid_action_count == 3
    assert len(result.steps) == 3


class RepeatingRedundantExtractFakeModel:
    model_name = "repeating_redundant_extract_model"

    def next_action(self, task, observation, memory):  # type: ignore[no-untyped-def]
        scenario = memory["scenario"]
        if not observation.page_opened:
            return StepwiseArticleAction("browser_open_url", {"url": scenario.start_url})
        return StepwiseArticleAction("browser_extract_section", {"section_id": "policy_scope"})


def test_repeated_valid_redundant_extract_loop_stops_before_max_steps() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_medium_two_fact_cross_section"],
        RepeatingRedundantExtractFakeModel(),
        max_steps=12,
    )

    assert result.status == "failed"
    assert result.stop_reason == "repeated_redundant_action_loop"
    assert result.error_code == "repeated_redundant_action_loop"
    assert len(result.steps) == 5
    assert result.evaluation.max_steps_exceeded is False
    assert result.evaluation.invalid_action_count == 0
    assert result.evaluation.workflow_action_valid is True
    assert result.evaluation.unnecessary_action_count == 3
    assert result.evaluation.repeated_redundant_action_count == 3
    assert result.evaluation.repeated_redundant_action_loop_detected is True
    assert result.evaluation.sections_unread_count_at_stop == 1
    assert result.evaluation.sections_read_progress_at_stop == "1/2"

    last_observation = result.steps[-1].observation_after
    assert last_observation.last_action_redundant is True
    assert last_observation.repeated_redundant_action_count == 3
    assert last_observation.repeated_action_count == 4
    assert last_observation.sections_unread_count == 1


class FinalAnswerAfterReadModel:
    model_name = "final_answer_after_read_model"

    def __init__(self, *, answer_text: str, citation_ids: list[str]) -> None:
        self.answer_text = answer_text
        self.citation_ids = citation_ids

    def next_action(self, task, observation, memory):  # type: ignore[no-untyped-def]
        scenario = memory["scenario"]
        if not observation.page_opened:
            return StepwiseArticleAction("browser_open_url", {"url": scenario.start_url})
        if not observation.sections_read_ids:
            return StepwiseArticleAction("browser_read_visible_text", {})
        return StepwiseArticleAction(
            "final_answer",
            {
                "answer_text": self.answer_text,
                "citation_ids": self.citation_ids,
            },
        )


def test_full_sentence_required_fact_passes_without_exact_match() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_short_single_fact"],
        FinalAnswerAfterReadModel(
            answer_text="The harbor office opens at 06:30 each weekday for visitor processing.",
            citation_ids=["harbor_hours"],
        ),
        max_steps=5,
    )

    assert result.status == "succeeded"
    assert result.evaluation.answer_exact_match is False
    assert result.evaluation.answer_correct is False
    assert result.evaluation.answer_contains_required_fact is True
    assert result.evaluation.semantic_answer_correct is True
    assert result.evaluation.pass_used_semantic_answer is True
    assert result.evaluation.answer_match_note == "full sentence accepted because required fact was present"
    assert result.evaluation.passed is True


def test_exact_answer_match_remains_diagnostic_and_passes() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    scenario = scenarios["article_short_single_fact"]
    result = run_stepwise_article_scenario(
        scenario,
        FinalAnswerAfterReadModel(
            answer_text=scenario.expected_answer_text,
            citation_ids=["harbor_hours"],
        ),
        max_steps=5,
    )

    assert result.status == "succeeded"
    assert result.evaluation.answer_exact_match is True
    assert result.evaluation.answer_correct is True
    assert result.evaluation.semantic_answer_correct is True
    assert result.evaluation.pass_used_semantic_answer is False
    assert result.evaluation.passed is True


def test_wrong_fact_fails_semantic_answer_correctness() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_short_single_fact"],
        FinalAnswerAfterReadModel(
            answer_text="The harbor office opens at 08:00 each weekday.",
            citation_ids=["harbor_hours"],
        ),
        max_steps=5,
    )

    assert result.status == "failed"
    assert result.evaluation.answer_exact_match is False
    assert result.evaluation.answer_contains_required_fact is False
    assert result.evaluation.semantic_answer_correct is False
    assert result.evaluation.missing_required_fact is True
    assert result.evaluation.passed is False


def test_semantic_answer_with_wrong_citation_fails() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_short_single_fact"],
        FinalAnswerAfterReadModel(
            answer_text="The harbor office opens at 06:30 each weekday for visitor processing.",
            citation_ids=["wrong_section"],
        ),
        max_steps=5,
    )

    assert result.status == "failed"
    assert result.evaluation.semantic_answer_correct is True
    assert result.evaluation.citation_correct is False
    assert result.evaluation.passed is False


def test_correct_final_answer_and_citation_can_pass() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_medium_two_fact_cross_section"],
        PerfectArticleFakeModel(),
        max_steps=6,
    )

    assert result.status == "succeeded"
    assert result.evaluation.completed is True
    assert result.evaluation.answer_correct is True
    assert result.evaluation.citation_correct is True
    assert result.evaluation.passed is True
    assert result.no_runtime_execution is True
    assert result.real_browser_execution is False
    assert result.playwright_execution is False


def test_semantic_correctness_is_separate_from_workflow_action_validity() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_short_single_fact"],
        InvalidActionFakeModel(),
        max_steps=5,
    )

    assert result.evaluation.semantic_answer_correct is True
    assert result.evaluation.answer_correct is True
    assert result.evaluation.citation_correct is True
    assert result.evaluation.workflow_action_valid is False
    assert result.evaluation.passed is False


def test_invalid_action_is_recorded_separately() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_short_single_fact"],
        InvalidActionFakeModel(),
        max_steps=5,
    )

    assert result.evaluation.invalid_action_count == 1
    assert result.steps[0].action.action_name == "browser_click"
    assert result.steps[0].status == "rejected"
    assert result.steps[0].error_code == "invalid_action"


def test_early_stop_is_detected() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_medium_two_fact_cross_section"],
        EarlyStopFakeModel(),
        max_steps=3,
    )

    assert result.status == "failed"
    assert result.evaluation.completed is True
    assert result.evaluation.missing_required_fact is True
    assert result.evaluation.stopped_too_early is True
    assert result.evaluation.passed is False


def test_hallucinated_answer_is_detected() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_negative_absence_check"],
        HallucinatingFakeModel(),
        max_steps=3,
    )

    assert result.status == "failed"
    assert result.evaluation.hallucinated_fact is True
    assert result.evaluation.semantic_answer_correct is False
    assert result.evaluation.passed is False


def test_negative_absence_scenario_only_passes_for_correct_absence_answer() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    passed = run_stepwise_article_scenario(
        scenarios["article_negative_absence_check"],
        PerfectArticleFakeModel(),
        max_steps=3,
    )
    failed = run_stepwise_article_scenario(
        scenarios["article_negative_absence_check"],
        HallucinatingFakeModel(),
        max_steps=3,
    )

    assert passed.evaluation.passed is True
    assert passed.evaluation.answer_correct is True
    assert failed.evaluation.passed is False
    assert failed.evaluation.hallucinated_fact is True


def test_find_then_answer_model_uses_find_text_path() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_similar_terms_disambiguation"],
        FindThenAnswerFakeModel(),
        max_steps=4,
    )

    assert result.status == "succeeded"
    assert any(step.action.action_name == "browser_find_text" for step in result.steps)
    assert result.final_answer_text == "Policy Match Review confirms manual approval for APR-42."


def test_multi_trial_summary_computes_pass_rate_and_pass_at_k() -> None:
    scenarios = build_default_stepwise_article_scenarios()

    class AlternatingFactory:
        def __init__(self) -> None:
            self.calls = 0

        def __call__(self):
            self.calls += 1
            if self.calls % 2 == 1:
                return PerfectArticleFakeModel()
            return EarlyStopFakeModel()

    summary = run_stepwise_article_benchmark(
        scenarios=[
            scenarios["article_short_single_fact"],
            scenarios["article_negative_absence_check"],
        ],
        model_factories={"alternating": AlternatingFactory()},
        trials_per_scenario=2,
        max_steps=4,
    )

    model_summary = summary["per_model_summary"][0]
    assert model_summary["model_alias"] == "alternating"
    assert model_summary["pass_rate"] == 0.5
    assert model_summary["pass_at_k"] == 1.0


def test_default_article_action_set_excludes_browser_click() -> None:
    assert "browser_click" not in DEFAULT_STEPWISE_ARTICLE_ACTIONS
    assert DEFAULT_STEPWISE_ARTICLE_ACTIONS == (
        "browser_open_url",
        "browser_read_visible_text",
        "browser_scroll_down",
        "browser_find_text",
        "browser_extract_section",
        "final_answer",
    )


def test_fake_cli_smoke_outputs_summary_and_optional_json(tmp_path: Path) -> None:
    output_path = tmp_path / "summary.json"

    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--trials-per-scenario",
            "1",
            "--max-steps",
            "4",
            "--output-json",
            str(output_path),
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )

    assert completed.returncode == 0, completed.stderr
    payload = json.loads(completed.stdout)
    assert payload["status"] == "succeeded"
    assert payload["no_runtime_execution"] is True
    assert payload["model_execution"] is False
    assert payload["real_browser_execution"] is False
    assert payload["playwright_execution"] is False
    assert output_path.exists()
