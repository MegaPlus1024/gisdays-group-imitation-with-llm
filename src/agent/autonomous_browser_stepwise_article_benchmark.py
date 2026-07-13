from __future__ import annotations

import json
import re
from collections import defaultdict
from collections.abc import Callable, Iterable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


STEPWISE_ARTICLE_RUN_SCHEMA_VERSION = "autonomous_browser_stepwise_article_run_result_v1"
STEPWISE_ARTICLE_BENCHMARK_SCHEMA_VERSION = "autonomous_browser_stepwise_article_benchmark_summary_v1"
DEFAULT_STEPWISE_ARTICLE_ACTIONS = (
    "browser_open_url",
    "browser_read_visible_text",
    "browser_scroll_down",
    "browser_find_text",
    "browser_extract_section",
    "final_answer",
)
DEFAULT_OUTPUT_JSON = "artifacts/autonomous_runtime_summaries/stepwise_article_benchmark_fake/benchmark_summary.json"


def _normalize_text(value: str) -> str:
    return " ".join(re.findall(r"[a-z0-9]+", value.casefold()))


def _coerce_string_list(value: Any) -> tuple[str, ...]:
    if value is None:
        return ()
    if isinstance(value, str):
        stripped = value.strip()
        return (stripped,) if stripped else ()
    if isinstance(value, Iterable):
        result: list[str] = []
        for item in value:
            if not isinstance(item, str):
                continue
            stripped = item.strip()
            if stripped:
                result.append(stripped)
        return tuple(result)
    return ()


@dataclass(frozen=True)
class ArticleSection:
    section_id: str
    title: str
    text: str

    def combined_text(self) -> str:
        return f"{self.title}\n{self.text}"

    def to_dict(self) -> dict[str, Any]:
        return {
            "section_id": self.section_id,
            "title": self.title,
            "text": self.text,
        }


@dataclass(frozen=True)
class ArticleDocument:
    logical_url: str
    title: str
    sections: tuple[ArticleSection, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "logical_url": self.logical_url,
            "title": self.title,
            "sections": [section.to_dict() for section in self.sections],
        }


@dataclass(frozen=True)
class StepwiseArticleScenario:
    scenario_id: str
    start_url: str
    task: str
    expected_answer_text: str
    allowed_urls: tuple[str, ...] = ()
    article_title_hint: str | None = None
    accepted_answer_texts: tuple[str, ...] = ()
    required_answer_fragments: tuple[str, ...] = ()
    forbidden_answer_fragments: tuple[str, ...] = ()
    required_citation_ids: tuple[str, ...] = ()
    required_section_ids: tuple[str, ...] = ()
    metadata: dict[str, Any] = field(default_factory=dict)

    def __post_init__(self) -> None:
        allowed_urls = _coerce_string_list(self.allowed_urls)
        if not self.start_url.strip():
            raise ValueError("start_url must be non-empty")
        if not allowed_urls:
            allowed_urls = (self.start_url,)
        elif self.start_url not in allowed_urls:
            allowed_urls = (self.start_url, *tuple(url for url in allowed_urls if url != self.start_url))
        object.__setattr__(self, "start_url", self.start_url.strip())
        object.__setattr__(self, "allowed_urls", allowed_urls)
        if isinstance(self.article_title_hint, str):
            stripped = self.article_title_hint.strip()
            object.__setattr__(self, "article_title_hint", stripped or None)

    @property
    def article_url(self) -> str:
        return self.start_url

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "start_url": self.start_url,
            "article_url": self.article_url,
            "task": self.task,
            "allowed_urls": list(self.allowed_urls),
            "article_title_hint": self.article_title_hint,
            "expected_answer_text": self.expected_answer_text,
            "accepted_answer_texts": list(self.accepted_answer_texts),
            "required_answer_fragments": list(self.required_answer_fragments),
            "forbidden_answer_fragments": list(self.forbidden_answer_fragments),
            "required_citation_ids": list(self.required_citation_ids),
            "required_section_ids": list(self.required_section_ids),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class StepwiseArticleObservation:
    scenario_id: str
    task: str
    page_opened: bool
    current_url: str | None
    allowed_urls: tuple[str, ...]
    recommended_start_url: str | None
    article_title_hint: str | None
    article_title: str | None
    visible_section_id: str | None
    visible_section_title: str | None
    visible_text: str
    available_actions: tuple[str, ...]
    sections_total: int
    sections_read_count: int
    sections_read_ids: tuple[str, ...]
    last_action_name: str | None = None
    last_find_result: dict[str, Any] | None = None
    last_error_code: str | None = None
    last_error_message: str | None = None

    def to_dict(self) -> dict[str, Any]:
        return {
            "scenario_id": self.scenario_id,
            "task": self.task,
            "page_opened": self.page_opened,
            "current_url": self.current_url,
            "allowed_urls": list(self.allowed_urls),
            "recommended_start_url": self.recommended_start_url,
            "article_title_hint": self.article_title_hint,
            "article_title": self.article_title,
            "visible_section_id": self.visible_section_id,
            "visible_section_title": self.visible_section_title,
            "visible_text": self.visible_text,
            "available_actions": list(self.available_actions),
            "sections_total": self.sections_total,
            "sections_read_count": self.sections_read_count,
            "sections_read_ids": list(self.sections_read_ids),
            "last_action_name": self.last_action_name,
            "last_find_result": dict(self.last_find_result) if isinstance(self.last_find_result, dict) else self.last_find_result,
            "last_error_code": self.last_error_code,
            "last_error_message": self.last_error_message,
        }


@dataclass(frozen=True)
class StepwiseArticleAction:
    action_name: str
    parameters: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "action_name": self.action_name,
            "parameters": dict(self.parameters),
        }


@dataclass(frozen=True)
class StepwiseArticleStepResult:
    step_index: int
    action: StepwiseArticleAction
    observation_before: StepwiseArticleObservation
    observation_after: StepwiseArticleObservation
    status: str
    error_code: str | None
    action_valid: bool
    details: dict[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "step_index": self.step_index,
            "action": self.action.to_dict(),
            "observation_before": self.observation_before.to_dict(),
            "observation_after": self.observation_after.to_dict(),
            "status": self.status,
            "error_code": self.error_code,
            "action_valid": self.action_valid,
            "details": dict(self.details),
        }


@dataclass(frozen=True)
class StepwiseArticleEvaluation:
    completed: bool
    passed: bool
    answer_correct: bool
    citation_correct: bool
    semantic_answer_correct: bool
    workflow_action_valid: bool
    steps_used: int
    sections_read: int
    unnecessary_action_count: int
    stopped_too_early: bool
    hallucinated_fact: bool
    missing_required_fact: bool
    invalid_action_count: int
    max_steps_exceeded: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "completed": self.completed,
            "passed": self.passed,
            "answer_correct": self.answer_correct,
            "citation_correct": self.citation_correct,
            "semantic_answer_correct": self.semantic_answer_correct,
            "workflow_action_valid": self.workflow_action_valid,
            "steps_used": self.steps_used,
            "sections_read": self.sections_read,
            "unnecessary_action_count": self.unnecessary_action_count,
            "stopped_too_early": self.stopped_too_early,
            "hallucinated_fact": self.hallucinated_fact,
            "missing_required_fact": self.missing_required_fact,
            "invalid_action_count": self.invalid_action_count,
            "max_steps_exceeded": self.max_steps_exceeded,
        }


@dataclass(frozen=True)
class StepwiseArticleRunResult:
    schema_version: str
    scenario_id: str
    model_name: str
    status: str
    stop_reason: str
    error_code: str | None
    max_steps: int
    final_answer_text: str | None
    final_citation_ids: tuple[str, ...]
    steps: tuple[StepwiseArticleStepResult, ...]
    evaluation: StepwiseArticleEvaluation
    diagnostics: dict[str, Any] = field(default_factory=dict)
    no_runtime_execution: bool = True
    model_execution: bool = False
    real_browser_execution: bool = False
    playwright_execution: bool = False
    browser_opened: bool = False
    fixture_only: bool = True

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "scenario_id": self.scenario_id,
            "model_name": self.model_name,
            "status": self.status,
            "stop_reason": self.stop_reason,
            "error_code": self.error_code,
            "max_steps": self.max_steps,
            "final_answer_text": self.final_answer_text,
            "final_citation_ids": list(self.final_citation_ids),
            "steps": [step.to_dict() for step in self.steps],
            "evaluation": self.evaluation.to_dict(),
            "diagnostics": dict(self.diagnostics),
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "fixture_only": self.fixture_only,
        }


class StepwiseArticleModel(Protocol):
    model_name: str

    def next_action(
        self,
        task: str,
        observation: StepwiseArticleObservation,
        memory: dict[str, Any],
    ) -> StepwiseArticleAction:
        ...


class FixtureArticleEnvironment:
    def __init__(self, catalog: Mapping[str, ArticleDocument] | None = None) -> None:
        self.catalog = dict(catalog or build_default_article_fixture_catalog())
        self.current_document: ArticleDocument | None = None
        self.visible_index = 0
        self.observed_section_ids: set[str] = set()
        self._last_find_result: dict[str, Any] | None = None

    def observe(
        self,
        scenario: StepwiseArticleScenario,
        *,
        last_action_name: str | None = None,
        last_find_result: Mapping[str, Any] | None = None,
        last_error_code: str | None = None,
        last_error_message: str | None = None,
    ) -> StepwiseArticleObservation:
        if self.current_document is None:
            return StepwiseArticleObservation(
                scenario_id=scenario.scenario_id,
                task=scenario.task,
                page_opened=False,
                current_url=None,
                allowed_urls=scenario.allowed_urls,
                recommended_start_url=scenario.start_url if len(scenario.allowed_urls) == 1 else None,
                article_title_hint=scenario.article_title_hint,
                article_title=None,
                visible_section_id=None,
                visible_section_title=None,
                visible_text="",
                available_actions=DEFAULT_STEPWISE_ARTICLE_ACTIONS,
                sections_total=0,
                sections_read_count=len(self.observed_section_ids),
                sections_read_ids=tuple(sorted(self.observed_section_ids)),
                last_action_name=last_action_name,
                last_find_result=dict(last_find_result) if isinstance(last_find_result, Mapping) else None,
                last_error_code=last_error_code,
                last_error_message=last_error_message,
            )
        section = self.current_document.sections[self.visible_index]
        return StepwiseArticleObservation(
            scenario_id=scenario.scenario_id,
            task=scenario.task,
            page_opened=True,
            current_url=self.current_document.logical_url,
            allowed_urls=scenario.allowed_urls,
            recommended_start_url=scenario.start_url if len(scenario.allowed_urls) == 1 else None,
            article_title_hint=scenario.article_title_hint,
            article_title=self.current_document.title,
            visible_section_id=section.section_id,
            visible_section_title=section.title,
            visible_text=section.combined_text(),
            available_actions=DEFAULT_STEPWISE_ARTICLE_ACTIONS,
            sections_total=len(self.current_document.sections),
            sections_read_count=len(self.observed_section_ids),
            sections_read_ids=tuple(sorted(self.observed_section_ids)),
            last_action_name=last_action_name,
            last_find_result=dict(last_find_result) if isinstance(last_find_result, Mapping) else dict(self._last_find_result) if isinstance(self._last_find_result, dict) else None,
            last_error_code=last_error_code,
            last_error_message=last_error_message,
        )

    def open_url(self, url: str, scenario: StepwiseArticleScenario) -> dict[str, Any]:
        normalized_url = url.strip()
        if normalized_url not in scenario.allowed_urls:
            return {
                "success": False,
                "error_code": "unknown_article_url",
                "error_message": "browser_open_url must use one of the allowed fixture article URLs.",
                "allowed_urls": list(scenario.allowed_urls),
                "recommended_start_url": scenario.start_url if len(scenario.allowed_urls) == 1 else None,
                "requested_url": normalized_url,
            }
        document = self.catalog.get(normalized_url)
        if document is None:
            return {
                "success": False,
                "error_code": "unknown_article_url",
                "error_message": "Requested fixture article URL is not present in the local article catalog.",
                "allowed_urls": list(scenario.allowed_urls),
                "recommended_start_url": scenario.start_url if len(scenario.allowed_urls) == 1 else None,
                "requested_url": normalized_url,
            }
        self.current_document = document
        self.visible_index = 0
        self._last_find_result = None
        visible_section = document.sections[0]
        return {
            "success": True,
            "logical_url": document.logical_url,
            "article_title": document.title,
            "visible_section_id": visible_section.section_id,
            "visible_section_title": visible_section.title,
        }

    def read_visible_text(self) -> dict[str, Any]:
        if self.current_document is None:
            return {
                "success": False,
                "error_code": "no_page_opened",
            }
        section = self.current_document.sections[self.visible_index]
        redundant = section.section_id in self.observed_section_ids
        self.observed_section_ids.add(section.section_id)
        return {
            "success": True,
            "section_id": section.section_id,
            "section_title": section.title,
            "visible_text": section.combined_text(),
            "newly_observed_section_ids": [] if redundant else [section.section_id],
            "redundant": redundant,
        }

    def scroll_down(self, pages: int = 1) -> dict[str, Any]:
        if self.current_document is None:
            return {
                "success": False,
                "error_code": "no_page_opened",
            }
        previous_index = self.visible_index
        self.visible_index = min(
            len(self.current_document.sections) - 1,
            self.visible_index + max(1, int(pages)),
        )
        section = self.current_document.sections[self.visible_index]
        return {
            "success": True,
            "section_id": section.section_id,
            "section_title": section.title,
            "visible_text": section.combined_text(),
            "changed_window": self.visible_index != previous_index,
            "redundant": self.visible_index == previous_index,
        }

    def find_text(self, query: str) -> dict[str, Any]:
        if self.current_document is None:
            return {
                "success": False,
                "error_code": "no_page_opened",
            }
        normalized_query = _normalize_text(query)
        scanned_section_ids: list[str] = []
        for index, section in enumerate(self.current_document.sections):
            scanned_section_ids.append(section.section_id)
            combined = _normalize_text(section.combined_text())
            if normalized_query and normalized_query in combined:
                self.visible_index = index
                self.observed_section_ids.update(scanned_section_ids)
                result = {
                    "success": True,
                    "found": True,
                    "query": query,
                    "section_id": section.section_id,
                    "section_title": section.title,
                    "visible_text": section.combined_text(),
                    "newly_observed_section_ids": scanned_section_ids,
                    "redundant": False,
                }
                self._last_find_result = result
                return result
        self.observed_section_ids.update(scanned_section_ids)
        result = {
            "success": True,
            "found": False,
            "query": query,
            "newly_observed_section_ids": scanned_section_ids,
            "redundant": False,
        }
        self._last_find_result = result
        return result

    def extract_section(
        self,
        *,
        section_id: str | None = None,
        section_title: str | None = None,
    ) -> dict[str, Any]:
        if self.current_document is None:
            return {
                "success": False,
                "error_code": "no_page_opened",
            }
        target_id = section_id.strip() if isinstance(section_id, str) else None
        target_title = section_title.strip() if isinstance(section_title, str) else None
        for index, section in enumerate(self.current_document.sections):
            matches_id = target_id is not None and section.section_id == target_id
            matches_title = target_title is not None and section.title == target_title
            if matches_id or matches_title:
                self.visible_index = index
                redundant = section.section_id in self.observed_section_ids
                self.observed_section_ids.add(section.section_id)
                return {
                    "success": True,
                    "section_id": section.section_id,
                    "section_title": section.title,
                    "section_text": section.combined_text(),
                    "newly_observed_section_ids": [] if redundant else [section.section_id],
                    "redundant": redundant,
                }
        return {
            "success": False,
            "error_code": "section_not_found",
        }

    def execute_action(
        self,
        action: StepwiseArticleAction,
        scenario: StepwiseArticleScenario,
    ) -> tuple[str, str | None, bool, dict[str, Any], StepwiseArticleObservation]:
        if action.action_name not in DEFAULT_STEPWISE_ARTICLE_ACTIONS:
            observation = self.observe(scenario, last_action_name=action.action_name)
            return (
                "rejected",
                "invalid_action",
                False,
                {"allowed_actions": list(DEFAULT_STEPWISE_ARTICLE_ACTIONS)},
                observation,
            )
        if action.action_name == "final_answer":
            observation = self.observe(scenario, last_action_name=action.action_name)
            return ("succeeded", None, True, {}, observation)

        if action.action_name == "browser_open_url":
            result = self.open_url(str(action.parameters.get("url", "")).strip(), scenario)
        elif action.action_name == "browser_read_visible_text":
            result = self.read_visible_text()
        elif action.action_name == "browser_scroll_down":
            result = self.scroll_down(int(action.parameters.get("pages", 1) or 1))
        elif action.action_name == "browser_find_text":
            result = self.find_text(str(action.parameters.get("query", "")).strip())
        else:
            result = self.extract_section(
                section_id=action.parameters.get("section_id"),
                section_title=action.parameters.get("section_title"),
            )

        status = "succeeded" if result.get("success") else "failed"
        error_code = None if result.get("success") else str(result.get("error_code") or "action_failed")
        action_valid = bool(result.get("success"))
        observation = self.observe(
            scenario,
            last_action_name=action.action_name,
            last_find_result=result if action.action_name == "browser_find_text" else self._last_find_result,
            last_error_code=error_code,
            last_error_message=None if result.get("success") else str(result.get("error_message") or error_code or "action_failed"),
        )
        return (status, error_code, action_valid, result, observation)


class _BaseFakeArticleModel:
    model_name = "base_fake_model"

    def _scenario(self, memory: Mapping[str, Any]) -> StepwiseArticleScenario:
        return memory["scenario"]

    def _final_action(self, scenario: StepwiseArticleScenario, key: str = "perfect") -> StepwiseArticleAction:
        suffix = "" if key == "perfect" else f"_{key}"
        answer_text = str(scenario.metadata.get(f"{key}_answer_text") or scenario.metadata.get("perfect_answer_text") or scenario.expected_answer_text)
        citation_ids = _coerce_string_list(
            scenario.metadata.get(f"{key}_citation_ids")
            or scenario.metadata.get("perfect_citation_ids")
            or scenario.required_citation_ids
        )
        return StepwiseArticleAction(
            action_name="final_answer",
            parameters={
                "answer_text": answer_text,
                "citation_ids": list(citation_ids),
            },
        )


class PerfectArticleFakeModel(_BaseFakeArticleModel):
    model_name = "perfect_article_fake_model"

    def next_action(
        self,
        task: str,
        observation: StepwiseArticleObservation,
        memory: dict[str, Any],
    ) -> StepwiseArticleAction:
        scenario = self._scenario(memory)
        read_ids = set(observation.sections_read_ids)
        if not observation.page_opened:
            return StepwiseArticleAction("browser_open_url", {"url": scenario.article_url})
        if scenario.scenario_id == "article_short_single_fact":
            if "harbor_hours" not in read_ids:
                return StepwiseArticleAction("browser_read_visible_text", {})
            return self._final_action(scenario)
        if scenario.scenario_id == "article_medium_two_fact_cross_section":
            if "policy_scope" not in read_ids:
                return StepwiseArticleAction("browser_read_visible_text", {})
            if observation.visible_section_id == "policy_scope":
                return StepwiseArticleAction("browser_scroll_down", {"pages": 1})
            if "escalation_owner" not in read_ids:
                return StepwiseArticleAction("browser_read_visible_text", {})
            return self._final_action(scenario)
        if scenario.scenario_id == "article_long_multi_section_summary":
            if "route_shift" not in read_ids:
                return StepwiseArticleAction("browser_read_visible_text", {})
            if observation.visible_section_id == "route_shift":
                return StepwiseArticleAction("browser_scroll_down", {"pages": 1})
            if "supplies_status" not in read_ids:
                return StepwiseArticleAction("browser_read_visible_text", {})
            if observation.visible_section_id == "supplies_status":
                return StepwiseArticleAction("browser_scroll_down", {"pages": 1})
            if "safety_checkpoint" not in read_ids:
                return StepwiseArticleAction("browser_extract_section", {"section_id": "safety_checkpoint"})
            return self._final_action(scenario)
        if scenario.scenario_id == "article_negative_absence_check":
            last_find = observation.last_find_result or {}
            if not last_find:
                return StepwiseArticleAction("browser_find_text", {"query": str(scenario.metadata.get("find_query", "Playwright"))})
            return self._final_action(scenario)
        if scenario.scenario_id == "article_similar_terms_disambiguation":
            last_find = observation.last_find_result or {}
            if not last_find:
                return StepwiseArticleAction("browser_find_text", {"query": str(scenario.metadata.get("find_query", "manual approval"))})
            return self._final_action(scenario)
        return self._final_action(scenario)


class EarlyStopFakeModel(_BaseFakeArticleModel):
    model_name = "early_stop_fake_model"

    def next_action(
        self,
        task: str,
        observation: StepwiseArticleObservation,
        memory: dict[str, Any],
    ) -> StepwiseArticleAction:
        scenario = self._scenario(memory)
        if not observation.page_opened:
            return StepwiseArticleAction("browser_open_url", {"url": scenario.article_url})
        return self._final_action(scenario, "partial")


class HallucinatingFakeModel(_BaseFakeArticleModel):
    model_name = "hallucinating_fake_model"

    def next_action(
        self,
        task: str,
        observation: StepwiseArticleObservation,
        memory: dict[str, Any],
    ) -> StepwiseArticleAction:
        scenario = self._scenario(memory)
        if not observation.page_opened:
            return StepwiseArticleAction("browser_open_url", {"url": scenario.article_url})
        return self._final_action(scenario, "hallucinated")


class FindThenAnswerFakeModel(_BaseFakeArticleModel):
    model_name = "find_then_answer_fake_model"

    def next_action(
        self,
        task: str,
        observation: StepwiseArticleObservation,
        memory: dict[str, Any],
    ) -> StepwiseArticleAction:
        scenario = self._scenario(memory)
        if not observation.page_opened:
            return StepwiseArticleAction("browser_open_url", {"url": scenario.article_url})
        if not observation.last_find_result:
            return StepwiseArticleAction(
                "browser_find_text",
                {"query": str(scenario.metadata.get("find_query", ""))},
            )
        return self._final_action(scenario)


class InvalidActionFakeModel(_BaseFakeArticleModel):
    model_name = "invalid_action_fake_model"

    def next_action(
        self,
        task: str,
        observation: StepwiseArticleObservation,
        memory: dict[str, Any],
    ) -> StepwiseArticleAction:
        scenario = self._scenario(memory)
        step_count = len(memory.get("step_results", []))
        read_ids = set(observation.sections_read_ids)
        if step_count == 0:
            return StepwiseArticleAction("browser_click", {"target_text": "Read more"})
        if not observation.page_opened:
            return StepwiseArticleAction("browser_open_url", {"url": scenario.article_url})
        if scenario.scenario_id == "article_short_single_fact" and "harbor_hours" not in read_ids:
            return StepwiseArticleAction("browser_read_visible_text", {})
        return self._final_action(scenario)


def build_default_article_fixture_catalog() -> dict[str, ArticleDocument]:
    return {
        "https://local.article/harbor-office-hours": ArticleDocument(
            logical_url="https://local.article/harbor-office-hours",
            title="Harbor Bulletin",
            sections=(
                ArticleSection(
                    section_id="harbor_hours",
                    title="Harbor Office Hours",
                    text="The harbor office opens at 06:30 each weekday for visitor processing.",
                ),
            ),
        ),
        "https://local.article/office-access-update": ArticleDocument(
            logical_url="https://local.article/office-access-update",
            title="Workspace Policy Memo",
            sections=(
                ArticleSection(
                    section_id="policy_scope",
                    title="Policy Scope",
                    text="Workspace policy version 2026 allows read-only fixture review for planning checks.",
                ),
                ArticleSection(
                    section_id="escalation_owner",
                    title="Escalation Owner",
                    text="Escalation owner Mira Chen approves exceptions for this memo.",
                ),
            ),
        ),
        "https://local.article/research-station-briefing": ArticleDocument(
            logical_url="https://local.article/research-station-briefing",
            title="Expedition Update",
            sections=(
                ArticleSection(
                    section_id="route_shift",
                    title="Route Shift",
                    text="The route shifted to the North Pass after fog blocked the South Ridge approach.",
                ),
                ArticleSection(
                    section_id="supplies_status",
                    title="Supplies Status",
                    text="Supplies remain stable with water reserves for four days.",
                ),
                ArticleSection(
                    section_id="safety_checkpoint",
                    title="Safety Checkpoint",
                    text="Each team must report a checkpoint every two hours.",
                ),
            ),
        ),
        "https://local.article/maintenance-window": ArticleDocument(
            logical_url="https://local.article/maintenance-window",
            title="Tooling Note",
            sections=(
                ArticleSection(
                    section_id="tooling_note",
                    title="Tooling Note",
                    text="The note documents curl.exe usage and fixture replay verification. No browser engines are named.",
                ),
            ),
        ),
        "https://local.article/project-codenames": ArticleDocument(
            logical_url="https://local.article/project-codenames",
            title="Approval Reference",
            sections=(
                ArticleSection(
                    section_id="match_review",
                    title="Policy Match Review",
                    text="Policy Match Review confirms manual approval for APR-42.",
                ),
                ArticleSection(
                    section_id="archive_review",
                    title="Policy Archive Review",
                    text="Policy Archive Review covers historical snapshots only and does not confirm manual approval.",
                ),
            ),
        ),
    }


def build_default_stepwise_article_scenarios() -> dict[str, StepwiseArticleScenario]:
    return {
        "article_short_single_fact": StepwiseArticleScenario(
            scenario_id="article_short_single_fact",
            start_url="https://local.article/harbor-office-hours",
            task="What time does the harbor office open?",
            article_title_hint="Harbor Bulletin",
            expected_answer_text="The harbor office opens at 06:30.",
            required_answer_fragments=("06:30", "harbor office opens"),
            required_citation_ids=("harbor_hours",),
            required_section_ids=("harbor_hours",),
            metadata={
                "perfect_answer_text": "The harbor office opens at 06:30.",
                "perfect_citation_ids": ["harbor_hours"],
                "partial_answer_text": "The harbor office opens in the morning.",
                "partial_citation_ids": ["harbor_hours"],
                "hallucinated_answer_text": "The harbor office opens at 08:00.",
                "hallucinated_citation_ids": ["harbor_hours"],
            },
        ),
        "article_medium_two_fact_cross_section": StepwiseArticleScenario(
            scenario_id="article_medium_two_fact_cross_section",
            start_url="https://local.article/office-access-update",
            task="State the workspace policy version and the escalation owner.",
            article_title_hint="Workspace Policy Memo",
            expected_answer_text="Workspace policy version 2026 and escalation owner Mira Chen.",
            required_answer_fragments=("workspace policy version 2026", "mira chen"),
            required_citation_ids=("policy_scope", "escalation_owner"),
            required_section_ids=("policy_scope", "escalation_owner"),
            metadata={
                "perfect_answer_text": "Workspace policy version 2026 and escalation owner Mira Chen.",
                "perfect_citation_ids": ["policy_scope", "escalation_owner"],
                "partial_answer_text": "Workspace policy version 2026.",
                "partial_citation_ids": ["policy_scope"],
                "hallucinated_answer_text": "Workspace policy version 2024 and escalation owner Mira Chen.",
                "hallucinated_citation_ids": ["policy_scope", "escalation_owner"],
            },
        ),
        "article_long_multi_section_summary": StepwiseArticleScenario(
            scenario_id="article_long_multi_section_summary",
            start_url="https://local.article/research-station-briefing",
            task="Summarize the route change, supply status, and checkpoint cadence.",
            article_title_hint="Expedition Update",
            expected_answer_text="The route moved to the North Pass, supplies cover four days of water, and checkpoints are due every two hours.",
            required_answer_fragments=("north pass", "four days", "every two hours"),
            required_citation_ids=("route_shift", "supplies_status", "safety_checkpoint"),
            required_section_ids=("route_shift", "supplies_status", "safety_checkpoint"),
            metadata={
                "perfect_answer_text": "The route moved to the North Pass, supplies cover four days of water, and checkpoints are due every two hours.",
                "perfect_citation_ids": ["route_shift", "supplies_status", "safety_checkpoint"],
                "partial_answer_text": "The route moved to the North Pass and supplies are stable.",
                "partial_citation_ids": ["route_shift", "supplies_status"],
                "hallucinated_answer_text": "The route stayed on the South Ridge and checkpoints are daily.",
                "hallucinated_citation_ids": ["route_shift", "safety_checkpoint"],
            },
        ),
        "article_negative_absence_check": StepwiseArticleScenario(
            scenario_id="article_negative_absence_check",
            start_url="https://local.article/maintenance-window",
            task="Does the tooling note mention Playwright?",
            article_title_hint="Tooling Note",
            expected_answer_text="No, the tooling note does not mention Playwright.",
            accepted_answer_texts=("Playwright is not mentioned in the tooling note.",),
            required_answer_fragments=("does not mention playwright",),
            forbidden_answer_fragments=("mentions playwright", "playwright is used"),
            required_citation_ids=("tooling_note",),
            required_section_ids=("tooling_note",),
            metadata={
                "find_query": "Playwright",
                "perfect_answer_text": "No, the tooling note does not mention Playwright.",
                "perfect_citation_ids": ["tooling_note"],
                "partial_answer_text": "The tooling note is about curl.exe.",
                "partial_citation_ids": ["tooling_note"],
                "hallucinated_answer_text": "Yes, the tooling note mentions Playwright.",
                "hallucinated_citation_ids": ["tooling_note"],
            },
        ),
        "article_similar_terms_disambiguation": StepwiseArticleScenario(
            scenario_id="article_similar_terms_disambiguation",
            start_url="https://local.article/project-codenames",
            task="Which review confirms manual approval for APR-42?",
            article_title_hint="Approval Reference",
            expected_answer_text="Policy Match Review confirms manual approval for APR-42.",
            accepted_answer_texts=("The confirming review is Policy Match Review.",),
            required_answer_fragments=("policy match review", "manual approval", "apr 42"),
            forbidden_answer_fragments=("policy archive review confirms",),
            required_citation_ids=("match_review",),
            required_section_ids=("match_review",),
            metadata={
                "find_query": "manual approval",
                "perfect_answer_text": "Policy Match Review confirms manual approval for APR-42.",
                "perfect_citation_ids": ["match_review"],
                "partial_answer_text": "A policy review confirms approval.",
                "partial_citation_ids": ["match_review"],
                "hallucinated_answer_text": "Policy Archive Review confirms manual approval for APR-42.",
                "hallucinated_citation_ids": ["archive_review"],
            },
        ),
    }


def build_default_fake_model_factories() -> dict[str, Callable[[], StepwiseArticleModel]]:
    return {
        "perfect": PerfectArticleFakeModel,
        "find_then_answer": FindThenAnswerFakeModel,
        "early_stop": EarlyStopFakeModel,
        "hallucinating": HallucinatingFakeModel,
        "invalid_action": InvalidActionFakeModel,
    }


def run_stepwise_article_scenario(
    scenario: StepwiseArticleScenario,
    model: StepwiseArticleModel,
    max_steps: int = 12,
    *,
    catalog: Mapping[str, ArticleDocument] | None = None,
    trial_index: int = 1,
) -> StepwiseArticleRunResult:
    environment = FixtureArticleEnvironment(catalog)
    observation = environment.observe(scenario)
    steps: list[StepwiseArticleStepResult] = []
    final_answer_text: str | None = None
    final_citation_ids: tuple[str, ...] = ()
    model_execution_attempted = False
    model_execution_completed = False
    memory: dict[str, Any] = {
        "scenario": scenario,
        "step_results": [],
        "trial_index": trial_index,
    }
    stop_reason = "max_steps_exceeded"
    error_code: str | None = None
    diagnostics: dict[str, Any] = {}

    for step_index in range(1, max_steps + 1):
        try:
            action = model.next_action(scenario.task, observation, memory)
        except Exception as exc:
            model_execution_attempted = model_execution_attempted or bool(
                getattr(model, "model_execution_attempted", False)
            )
            model_execution_completed = model_execution_completed or bool(
                getattr(model, "model_execution_completed", False)
            )
            stop_reason = "model_error"
            error_code = str(getattr(exc, "error_code", "model_step_failed"))
            diagnostics = dict(getattr(exc, "diagnostics", {}))
            break
        if not isinstance(action, StepwiseArticleAction):
            raise TypeError("stepwise fake models must return StepwiseArticleAction instances")

        observation_before = observation
        if action.action_name == "final_answer":
            final_answer_text = str(action.parameters.get("answer_text", "")).strip() or None
            final_citation_ids = _coerce_string_list(action.parameters.get("citation_ids"))
            observation_after = environment.observe(
                scenario,
                last_action_name=action.action_name,
                last_find_result=observation.last_find_result,
            )
            step_result = StepwiseArticleStepResult(
                step_index=step_index,
                action=action,
                observation_before=observation_before,
                observation_after=observation_after,
                status="succeeded",
                error_code=None,
                action_valid=final_answer_text is not None,
                details={
                    "citation_ids": list(final_citation_ids),
                },
            )
            steps.append(step_result)
            memory["step_results"].append(step_result.to_dict())
            observation = observation_after
            stop_reason = "final_answer"
            break

        status, error_code, action_valid, details, observation_after = environment.execute_action(action, scenario)
        model_execution_attempted = model_execution_attempted or bool(
            getattr(model, "model_execution_attempted", False)
        )
        model_execution_completed = model_execution_completed or bool(
            getattr(model, "model_execution_completed", False)
        )
        step_result = StepwiseArticleStepResult(
            step_index=step_index,
            action=action,
            observation_before=observation_before,
            observation_after=observation_after,
            status=status,
            error_code=error_code,
            action_valid=action_valid,
            details=details,
        )
        steps.append(step_result)
        memory["step_results"].append(step_result.to_dict())
        observation = observation_after
        if _is_repeated_invalid_action_loop(steps):
            stop_reason = "repeated_invalid_action_loop"
            error_code = "repeated_invalid_action_loop"
            diagnostics = {
                "repeated_action_name": action.action_name,
                "repeated_action_parameters": dict(action.parameters),
                "repeat_count": 3,
            }
            break
    evaluation = _evaluate_run(
        scenario=scenario,
        steps=steps,
        final_answer_text=final_answer_text,
        final_citation_ids=final_citation_ids,
        max_steps=max_steps,
        sections_read_ids=tuple(sorted(environment.observed_section_ids)),
        stop_reason=stop_reason,
    )
    model_execution_attempted = model_execution_attempted or bool(
        getattr(model, "model_execution_attempted", False)
    )
    model_execution_completed = model_execution_completed or bool(
        getattr(model, "model_execution_completed", False)
    )
    model_execution = model_execution_attempted
    status = "succeeded" if evaluation.passed else "failed"
    if error_code is None and not evaluation.passed and stop_reason == "max_steps_exceeded":
        error_code = "max_steps_exceeded"
    return StepwiseArticleRunResult(
        schema_version=STEPWISE_ARTICLE_RUN_SCHEMA_VERSION,
        scenario_id=scenario.scenario_id,
        model_name=getattr(model, "model_name", type(model).__name__),
        status=status,
        stop_reason=stop_reason,
        error_code=error_code,
        max_steps=max_steps,
        final_answer_text=final_answer_text,
        final_citation_ids=final_citation_ids,
        steps=tuple(steps),
        evaluation=evaluation,
        diagnostics=diagnostics,
        no_runtime_execution=not model_execution,
        model_execution=model_execution,
        browser_opened=False,
    )


def run_stepwise_article_benchmark(
    scenarios: Iterable[StepwiseArticleScenario] | Mapping[str, StepwiseArticleScenario],
    model_factories: Mapping[str, Callable[[], StepwiseArticleModel]],
    trials_per_scenario: int = 3,
    max_steps: int = 12,
    *,
    catalog: Mapping[str, ArticleDocument] | None = None,
) -> dict[str, Any]:
    if trials_per_scenario <= 0:
        raise ValueError("trials_per_scenario must be positive")
    if max_steps <= 0:
        raise ValueError("max_steps must be positive")
    scenario_list = (
        list(scenarios.values())
        if isinstance(scenarios, Mapping)
        else list(scenarios)
    )
    per_trial_results: list[dict[str, Any]] = []
    grouped_model_trials: dict[str, list[StepwiseArticleRunResult]] = defaultdict(list)
    grouped_scenario_trials: dict[str, list[tuple[str, StepwiseArticleRunResult]]] = defaultdict(list)

    for model_alias, factory in model_factories.items():
        for scenario in scenario_list:
            for trial_index in range(1, trials_per_scenario + 1):
                model = factory()
                run_result = run_stepwise_article_scenario(
                    scenario,
                    model,
                    max_steps=max_steps,
                    catalog=catalog,
                    trial_index=trial_index,
                )
                grouped_model_trials[model_alias].append(run_result)
                grouped_scenario_trials[scenario.scenario_id].append((model_alias, run_result))
                per_trial_results.append(
                    {
                        "model_alias": model_alias,
                        "trial_label": f"trial_{trial_index:02d}",
                        "scenario_id": scenario.scenario_id,
                        "result": run_result.to_dict(),
                    }
                )

    per_model_summary = [
        _summarize_model_trials(
            model_alias,
            grouped_model_trials.get(model_alias, []),
            trials_per_scenario,
            scenario_list,
        )
        for model_alias in model_factories
    ]
    per_scenario_summary = [
        _summarize_scenario_trials(scenario, grouped_scenario_trials[scenario.scenario_id], trials_per_scenario)
        for scenario in scenario_list
    ]
    any_model_execution = any(
        bool(trial["result"].get("model_execution"))
        for trial in per_trial_results
    )
    return {
        "schema_version": STEPWISE_ARTICLE_BENCHMARK_SCHEMA_VERSION,
        "status": "succeeded",
        "error_code": None,
        "trials_per_scenario": trials_per_scenario,
        "max_steps": max_steps,
        "models_total": len(model_factories),
        "scenarios_total": len(scenario_list),
        "per_trial_results": per_trial_results,
        "per_model_summary": per_model_summary,
        "per_scenario_summary": per_scenario_summary,
        "no_runtime_execution": not any_model_execution,
        "model_execution": any_model_execution,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
        "fixture_only": True,
    }


def _is_repeated_invalid_action_loop(steps: list[StepwiseArticleStepResult], *, threshold: int = 3) -> bool:
    if len(steps) < threshold:
        return False
    recent_steps = steps[-threshold:]
    first = recent_steps[0]
    if first.action_valid:
        return False
    reference_name = first.action.action_name
    reference_parameters = first.action.parameters
    return all(
        not step.action_valid
        and step.action.action_name == reference_name
        and step.action.parameters == reference_parameters
        for step in recent_steps
    )


def write_stepwise_article_benchmark_summary(
    summary: Mapping[str, Any],
    output_path: str | Path = DEFAULT_OUTPUT_JSON,
) -> str:
    destination = Path(output_path)
    destination.parent.mkdir(parents=True, exist_ok=True)
    destination.write_text(
        json.dumps(dict(summary), ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )
    return destination.as_posix()


def _evaluate_run(
    *,
    scenario: StepwiseArticleScenario,
    steps: list[StepwiseArticleStepResult],
    final_answer_text: str | None,
    final_citation_ids: tuple[str, ...],
    max_steps: int,
    sections_read_ids: tuple[str, ...],
    stop_reason: str,
) -> StepwiseArticleEvaluation:
    normalized_answer = _normalize_text(final_answer_text or "")
    accepted_exact = {
        _normalize_text(scenario.expected_answer_text),
        *(_normalize_text(item) for item in scenario.accepted_answer_texts),
    }
    answer_correct = bool(normalized_answer) and normalized_answer in accepted_exact
    semantic_answer_correct = bool(normalized_answer)
    for fragment in scenario.required_answer_fragments:
        if _normalize_text(fragment) not in normalized_answer:
            semantic_answer_correct = False
            break
    hallucinated_fact = False
    for fragment in scenario.forbidden_answer_fragments:
        if _normalize_text(fragment) in normalized_answer:
            hallucinated_fact = True
            semantic_answer_correct = False
            break
    citation_correct = set(scenario.required_citation_ids).issubset(set(final_citation_ids))
    invalid_action_count = sum(1 for step in steps if not step.action_valid)
    workflow_action_valid = invalid_action_count == 0 and all(
        step.status in {"succeeded"} for step in steps if step.action.action_name != "final_answer"
    )
    completed = final_answer_text is not None
    missing_required_fact = completed and not semantic_answer_correct
    max_steps_exceeded = stop_reason == "max_steps_exceeded"
    sections_read_count = len(set(sections_read_ids))
    required_sections_seen = set(scenario.required_section_ids).issubset(set(sections_read_ids))
    stopped_too_early = completed and (missing_required_fact or not required_sections_seen)
    unnecessary_action_count = sum(
        1
        for step in steps
        if bool(step.details.get("redundant"))
    )
    passed = (
        completed
        and answer_correct
        and citation_correct
        and semantic_answer_correct
        and workflow_action_valid
        and not hallucinated_fact
        and not max_steps_exceeded
    )
    return StepwiseArticleEvaluation(
        completed=completed,
        passed=passed,
        answer_correct=answer_correct,
        citation_correct=citation_correct,
        semantic_answer_correct=semantic_answer_correct,
        workflow_action_valid=workflow_action_valid,
        steps_used=len(steps),
        sections_read=sections_read_count,
        unnecessary_action_count=unnecessary_action_count,
        stopped_too_early=stopped_too_early,
        hallucinated_fact=hallucinated_fact,
        missing_required_fact=missing_required_fact,
        invalid_action_count=invalid_action_count,
        max_steps_exceeded=max_steps_exceeded,
    )


def _summarize_model_trials(
    model_alias: str,
    runs: list[StepwiseArticleRunResult],
    trials_per_scenario: int,
    scenarios: list[StepwiseArticleScenario],
) -> dict[str, Any]:
    total_trials = len(runs)
    passed_trials = sum(1 for run in runs if run.evaluation.passed)
    total_steps = sum(run.evaluation.steps_used for run in runs)
    total_invalid_actions = sum(run.evaluation.invalid_action_count for run in runs)
    average_steps = round(total_steps / total_trials, 6) if total_trials else 0.0
    answer_correct_rate = round(
        sum(1 for run in runs if run.evaluation.answer_correct) / total_trials,
        6,
    ) if total_trials else 0.0
    citation_correct_rate = round(
        sum(1 for run in runs if run.evaluation.citation_correct) / total_trials,
        6,
    ) if total_trials else 0.0
    invalid_action_rate = round(total_invalid_actions / total_steps, 6) if total_steps else 0.0
    scenario_passes = 0
    for scenario in scenarios:
        scenario_runs = [run for run in runs if run.scenario_id == scenario.scenario_id]
        if any(run.evaluation.passed for run in scenario_runs):
            scenario_passes += 1
    scenario_total = len(scenarios)
    pass_rate = round(passed_trials / total_trials, 6) if total_trials else 0.0
    pass_at_k = round(scenario_passes / scenario_total, 6) if scenario_total else 0.0
    return {
        "model_alias": model_alias,
        "trials_total": total_trials,
        "passed_trials": passed_trials,
        "pass_rate": pass_rate,
        "pass_at_k": pass_at_k,
        "average_steps_used": average_steps,
        "answer_correct_rate": answer_correct_rate,
        "citation_correct_rate": citation_correct_rate,
        "invalid_action_rate": invalid_action_rate,
    }


def _summarize_scenario_trials(
    scenario: StepwiseArticleScenario,
    runs: list[tuple[str, StepwiseArticleRunResult]],
    trials_per_scenario: int,
) -> dict[str, Any]:
    grouped: dict[str, list[StepwiseArticleRunResult]] = defaultdict(list)
    for model_alias, run in runs:
        grouped[model_alias].append(run)
    model_breakdown = []
    for model_alias, model_runs in sorted(grouped.items()):
        passed_trials = sum(1 for run in model_runs if run.evaluation.passed)
        model_breakdown.append(
            {
                "model_alias": model_alias,
                "trials_total": len(model_runs),
                "passed_trials": passed_trials,
                "pass_rate": round(passed_trials / len(model_runs), 6) if model_runs else 0.0,
            }
        )
    return {
        "scenario_id": scenario.scenario_id,
        "task": scenario.task,
        "trials_per_scenario": trials_per_scenario,
        "model_breakdown": model_breakdown,
    }
