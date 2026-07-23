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


def test_open_url_records_only_initially_visible_section_as_evidence() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    scenario = scenarios["article_similar_terms_disambiguation"]
    env = FixtureArticleEnvironment(build_default_article_fixture_catalog())

    status, _, _, details, observation = env.execute_action(
        StepwiseArticleAction("browser_open_url", {"url": scenario.start_url}),
        scenario,
    )

    assert status == "succeeded"
    assert details["newly_observed_section_ids"] == ["match_review"]
    assert details["evidence_source"] == "visible_text"
    assert observation.observed_evidence_count == 1
    assert observation.observed_section_ids == ("match_review",)
    assert observation.sections_read_progress == "1/2"
    assert observation.sections_unread_count == 1
    assert observation.last_newly_observed_section_ids == ("match_review",)
    assert "Policy Match Review confirms manual approval for APR-42" in observation.observed_evidence_text
    assert "Policy Archive Review covers historical snapshots" not in observation.observed_evidence_text


def test_scroll_down_records_new_visible_section_without_duplicate_evidence() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    scenario = scenarios["article_similar_terms_disambiguation"]
    env = FixtureArticleEnvironment(build_default_article_fixture_catalog())

    env.execute_action(
        StepwiseArticleAction("browser_open_url", {"url": scenario.start_url}),
        scenario,
    )
    status, _, _, details, observation = env.execute_action(
        StepwiseArticleAction("browser_scroll_down", {}),
        scenario,
    )

    assert status == "succeeded"
    assert details["newly_observed_section_ids"] == ["archive_review"]
    assert details["redundant"] is False
    assert observation.observed_section_ids == ("match_review", "archive_review")
    assert observation.observed_evidence_count == 2
    assert observation.sections_read_progress == "2/2"
    assert "Policy Archive Review covers historical snapshots" in observation.observed_evidence_text

    _, _, _, details, observation = env.execute_action(
        StepwiseArticleAction("browser_scroll_down", {}),
        scenario,
    )

    assert details["redundant"] is True
    assert details["newly_observed_section_ids"] == []
    assert observation.observed_section_ids == ("match_review", "archive_review")
    assert observation.observed_evidence_count == 2


def test_open_url_exposes_only_current_visible_long_article_evidence() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    scenario = scenarios["article_long_multi_section_summary"]
    env = FixtureArticleEnvironment(build_default_article_fixture_catalog())

    _, _, _, details, observation = env.execute_action(
        StepwiseArticleAction("browser_open_url", {"url": scenario.start_url}),
        scenario,
    )

    assert details["visible_section_id"] == "route_shift"
    assert "North Pass" in details["visible_text"]
    assert "water reserves for four days" not in details["visible_text"]
    assert "every two hours" not in details["visible_text"]
    assert observation.observed_section_ids == ("route_shift",)
    assert observation.observed_evidence_count == 1
    assert observation.sections_unread_count == 2


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
    assert observation.observed_sections == ()
    assert observation.observed_section_ids == ()
    assert observation.observed_evidence_count == 0
    assert observation.observed_evidence_text == "Observed evidence so far: none."


def test_observed_evidence_memory_tracks_extracted_sections_without_duplicates() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    scenario = scenarios["article_medium_two_fact_cross_section"]
    env = FixtureArticleEnvironment(build_default_article_fixture_catalog())

    env.execute_action(
        StepwiseArticleAction("browser_open_url", {"url": scenario.start_url}),
        scenario,
    )
    status, _, _, _, observation = env.execute_action(
        StepwiseArticleAction("browser_extract_section", {"section_id": "escalation_owner"}),
        scenario,
    )

    assert status == "succeeded"
    assert observation.observed_evidence_count == 2
    assert observation.observed_section_ids == ("policy_scope", "escalation_owner")
    assert observation.observed_sections[0].section_id == "policy_scope"
    assert "Workspace policy version 2026" in observation.observed_sections[0].section_text
    assert "Escalation owner Mira Chen approves exceptions" in observation.observed_sections[1].section_text
    assert "[escalation_owner] Escalation Owner:" in observation.observed_evidence_text

    _, _, _, _, observation = env.execute_action(
        StepwiseArticleAction("browser_extract_section", {"section_id": "policy_scope"}),
        scenario,
    )

    assert observation.observed_evidence_count == 2
    assert observation.observed_section_ids == ("policy_scope", "escalation_owner")
    assert "Workspace policy version 2026" in observation.observed_evidence_text
    assert "Escalation owner Mira Chen" in observation.observed_evidence_text

    _, _, _, _, observation = env.execute_action(
        StepwiseArticleAction("browser_extract_section", {"section_id": "policy_scope"}),
        scenario,
    )

    assert observation.observed_evidence_count == 2
    assert observation.observed_section_ids == ("policy_scope", "escalation_owner")
    assert [section.section_id for section in observation.observed_sections] == [
        "policy_scope",
        "escalation_owner",
    ]


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
    assert len(result.steps) == 4
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
    assert last_observation.repeated_action_count == 3
    assert last_observation.sections_unread_count == 1


class EvidenceMemoryFakeModel:
    model_name = "evidence_memory_fake_model"

    def __init__(
        self,
        *,
        answer_text: str = "Workspace policy version 2026 and escalation owner Mira Chen.",
        citation_ids: list[str] | None = None,
    ) -> None:
        self.answer_text = answer_text
        self.citation_ids = citation_ids or ["policy_scope", "escalation_owner"]

    def next_action(self, task, observation, memory):  # type: ignore[no-untyped-def]
        scenario = memory["scenario"]
        observed_ids = set(observation.observed_section_ids)
        if not observation.page_opened:
            return StepwiseArticleAction("browser_open_url", {"url": scenario.start_url})
        if "escalation_owner" not in observed_ids:
            return StepwiseArticleAction("browser_extract_section", {"section_id": "escalation_owner"})
        if "policy_scope" not in observed_ids:
            return StepwiseArticleAction("browser_extract_section", {"section_id": "policy_scope"})
        evidence_text = "\n".join(section.section_text for section in observation.observed_sections)
        assert "Escalation owner Mira Chen approves exceptions" in evidence_text
        assert "Workspace policy version 2026" in evidence_text
        return StepwiseArticleAction(
            "final_answer",
            {
                "answer_text": self.answer_text,
                "citation_ids": self.citation_ids,
            },
        )


class MissingOwnerAfterReadingFakeModel:
    model_name = "missing_owner_after_reading_fake_model"

    def next_action(self, task, observation, memory):  # type: ignore[no-untyped-def]
        scenario = memory["scenario"]
        observed_ids = set(observation.observed_section_ids)
        if not observation.page_opened:
            return StepwiseArticleAction("browser_open_url", {"url": scenario.start_url})
        if "escalation_owner" not in observed_ids:
            return StepwiseArticleAction("browser_extract_section", {"section_id": "escalation_owner"})
        if "policy_scope" not in observed_ids:
            return StepwiseArticleAction("browser_extract_section", {"section_id": "policy_scope"})
        return StepwiseArticleAction(
            "final_answer",
            {
                "answer_text": "The workspace policy version is 2026, and the escalation owner is not mentioned in the provided text.",
                "citation_ids": ["policy_scope"],
            },
        )


def test_evidence_memory_fake_model_passes_medium_multi_section_answer() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_medium_two_fact_cross_section"],
        EvidenceMemoryFakeModel(),
        max_steps=6,
    )

    assert result.status == "succeeded"
    assert result.evaluation.passed is True
    assert result.evaluation.sections_read == 2
    assert result.evaluation.observed_evidence_count_at_stop == 2
    assert result.evaluation.observed_section_ids_at_stop == ("policy_scope", "escalation_owner")
    assert result.evaluation.final_answer_supported_citation_ids == ("policy_scope", "escalation_owner")
    assert result.evaluation.missing_citation_ids == ()
    assert result.evaluation.required_facts_total == 2
    assert result.evaluation.required_facts_matched == 2
    assert result.evaluation.matched_required_fact_ids == ("policy_version", "escalation_owner")
    assert result.evaluation.missing_required_fact_ids == ()


def test_medium_semantic_answer_with_version_and_owner_passes_without_exact_match() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_medium_two_fact_cross_section"],
        EvidenceMemoryFakeModel(
            answer_text="The workspace policy version is 2026, and the escalation owner is Mira Chen.",
            citation_ids=["policy_scope", "escalation_owner"],
        ),
        max_steps=6,
    )

    assert result.status == "succeeded"
    assert result.evaluation.answer_exact_match is False
    assert result.evaluation.answer_correct is False
    assert result.evaluation.answer_contains_required_fact is True
    assert result.evaluation.semantic_answer_correct is True
    assert result.evaluation.missing_required_fact is False
    assert result.evaluation.stopped_too_early is False
    assert result.evaluation.passed is True
    assert result.evaluation.required_facts_total == 2
    assert result.evaluation.required_facts_matched == 2
    assert result.evaluation.matched_required_fact_ids == ("policy_version", "escalation_owner")
    assert result.evaluation.missing_required_fact_ids == ()


def test_answer_claiming_owner_missing_fails_after_owner_evidence_was_read() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_medium_two_fact_cross_section"],
        MissingOwnerAfterReadingFakeModel(),
        max_steps=6,
    )

    assert result.status == "failed"
    assert result.evaluation.sections_read == 2
    assert result.evaluation.observed_evidence_count_at_stop == 2
    assert result.evaluation.semantic_answer_correct is False
    assert result.evaluation.missing_required_fact is True
    assert result.evaluation.missing_required_fact_ids == ("escalation_owner",)
    assert result.evaluation.stopped_too_early is False
    assert result.evaluation.citation_correct is False
    assert result.evaluation.missing_citation_ids == ("escalation_owner",)


def test_medium_answer_only_policy_version_fails_missing_owner_fact() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_medium_two_fact_cross_section"],
        EvidenceMemoryFakeModel(
            answer_text="The workspace policy version is 2026.",
            citation_ids=["policy_scope", "escalation_owner"],
        ),
        max_steps=6,
    )

    assert result.status == "failed"
    assert result.evaluation.required_facts_matched == 1
    assert result.evaluation.matched_required_fact_ids == ("policy_version",)
    assert result.evaluation.missing_required_fact_ids == ("escalation_owner",)
    assert result.evaluation.semantic_answer_correct is False
    assert result.evaluation.missing_required_fact is True


def test_medium_answer_only_owner_fails_missing_policy_version_fact() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_medium_two_fact_cross_section"],
        EvidenceMemoryFakeModel(
            answer_text="The escalation owner is Mira Chen.",
            citation_ids=["policy_scope", "escalation_owner"],
        ),
        max_steps=6,
    )

    assert result.status == "failed"
    assert result.evaluation.required_facts_matched == 1
    assert result.evaluation.matched_required_fact_ids == ("escalation_owner",)
    assert result.evaluation.missing_required_fact_ids == ("policy_version",)
    assert result.evaluation.semantic_answer_correct is False
    assert result.evaluation.missing_required_fact is True


def test_medium_answer_with_both_facts_requires_policy_scope_citation() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_medium_two_fact_cross_section"],
        EvidenceMemoryFakeModel(
            answer_text="The workspace policy version is 2026, and the escalation owner is Mira Chen.",
            citation_ids=["escalation_owner"],
        ),
        max_steps=6,
    )

    assert result.status == "failed"
    assert result.evaluation.semantic_answer_correct is True
    assert result.evaluation.citation_correct is False
    assert result.evaluation.missing_citation_ids == ("policy_scope",)
    assert result.evaluation.passed is False


def test_medium_answer_with_both_facts_requires_escalation_owner_citation() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_medium_two_fact_cross_section"],
        EvidenceMemoryFakeModel(
            answer_text="The workspace policy version is 2026, and the escalation owner is Mira Chen.",
            citation_ids=["policy_scope"],
        ),
        max_steps=6,
    )

    assert result.status == "failed"
    assert result.evaluation.semantic_answer_correct is True
    assert result.evaluation.citation_correct is False
    assert result.evaluation.missing_citation_ids == ("escalation_owner",)
    assert result.evaluation.passed is False


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


class OpenThenAnswerSimilarTermsModel:
    model_name = "open_then_answer_similar_terms_model"

    def __init__(self, *, citation_ids: list[str] | None = None) -> None:
        self.citation_ids = citation_ids or ["match_review"]

    def next_action(self, task, observation, memory):  # type: ignore[no-untyped-def]
        scenario = memory["scenario"]
        if not observation.page_opened:
            return StepwiseArticleAction("browser_open_url", {"url": scenario.start_url})
        return StepwiseArticleAction(
            "final_answer",
            {
                "answer_text": "Policy Match Review confirms manual approval for APR-42.",
                "citation_ids": self.citation_ids,
            },
        )


def test_similar_terms_can_pass_from_initial_visible_evidence() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_similar_terms_disambiguation"],
        OpenThenAnswerSimilarTermsModel(),
        max_steps=3,
    )

    assert result.status == "succeeded"
    assert result.stop_reason == "final_answer"
    assert result.evaluation.passed is True
    assert result.evaluation.observed_evidence_count_at_stop == 1
    assert result.evaluation.observed_section_ids_at_stop == ("match_review",)
    assert result.evaluation.sections_read_progress_at_stop == "1/2"
    assert result.evaluation.sections_unread_count_at_stop == 1
    assert result.evaluation.stopped_too_early is False


def test_similar_terms_wrong_citation_still_fails() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_similar_terms_disambiguation"],
        OpenThenAnswerSimilarTermsModel(citation_ids=["archive_review"]),
        max_steps=3,
    )

    assert result.status == "failed"
    assert result.evaluation.semantic_answer_correct is True
    assert result.evaluation.citation_correct is False
    assert result.evaluation.missing_citation_ids == ("match_review",)
    assert result.evaluation.stopped_too_early is False
    assert result.evaluation.passed is False


class SimilarTermsAnswerBeforeOpenModel:
    model_name = "similar_terms_answer_before_open_model"

    def next_action(self, task, observation, memory):  # type: ignore[no-untyped-def]
        return StepwiseArticleAction(
            "final_answer",
            {
                "answer_text": "Policy Match Review confirms manual approval for APR-42.",
                "citation_ids": ["match_review"],
            },
        )


def test_similar_terms_answer_before_open_is_stopped_too_early() -> None:
    scenarios = build_default_stepwise_article_scenarios()
    result = run_stepwise_article_scenario(
        scenarios["article_similar_terms_disambiguation"],
        SimilarTermsAnswerBeforeOpenModel(),
        max_steps=3,
    )

    assert result.status == "failed"
    assert result.evaluation.observed_evidence_count_at_stop == 0
    assert result.evaluation.citation_correct is True
    assert result.evaluation.stopped_too_early is True
    assert result.evaluation.passed is False


def test_long_summary_missing_facts_remains_strict_after_visible_observation() -> None:
    scenarios = build_default_stepwise_article_scenarios()

    class OpenThenPartialLongAnswerModel:
        model_name = "open_then_partial_long_answer_model"

        def next_action(self, task, observation, memory):  # type: ignore[no-untyped-def]
            scenario = memory["scenario"]
            if not observation.page_opened:
                return StepwiseArticleAction("browser_open_url", {"url": scenario.start_url})
            return StepwiseArticleAction(
                "final_answer",
                {
                    "answer_text": "The route moved to the North Pass.",
                    "citation_ids": ["route_shift"],
                },
            )

    result = run_stepwise_article_scenario(
        scenarios["article_long_multi_section_summary"],
        OpenThenPartialLongAnswerModel(),
        max_steps=3,
    )

    assert result.status == "failed"
    assert result.evaluation.observed_section_ids_at_stop == ("route_shift",)
    assert result.evaluation.missing_required_fact is True
    assert result.evaluation.missing_required_fact_ids == ("required_fragment_2", "required_fragment_3")
    assert result.evaluation.stopped_too_early is True
    assert result.evaluation.passed is False


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
