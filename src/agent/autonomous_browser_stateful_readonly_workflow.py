from __future__ import annotations

import json
import re
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any

from .autonomous_browser_live_loop import DEFAULT_FIXTURE_MANIFEST_PATH, _safe_relative_path
from .autonomous_browser_runtime import (
    BrowserRuntimeAction,
    BrowserRuntimeObservation,
    BrowserRuntimePolicy,
    BrowserRuntimeSession,
    BrowserRuntimeVerifier,
    FixtureBackedBrowserRuntimeExecutor,
)


SUMMARY_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_workflow_summary_v1"
STATE_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_workflow_state_v1"
TRACE_SCHEMA_VERSION = "autonomous_browser_stateful_readonly_workflow_trace_v1"
DEFAULT_ALLOWED_ACTIONS = (
    "browser_open_url",
    "browser_click",
    "browser_extract_text",
    "browser_snapshot",
)
DEFAULT_DISALLOWED_ACTIONS = (
    "browser_type_text",
    "browser_submit_form",
    "browser_upload_file",
    "browser_download_file",
    "external_url",
    "file_write",
)
DEFAULT_LIMITATIONS = (
    "read-only fixture-backed workflow",
    "no model calls",
    "no real browser execution",
    "no Playwright import",
    "not production browser automation",
)
DEFAULT_WORKFLOW_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/stateful_readonly_workflows"


@dataclass(frozen=True)
class StatefulReadonlyWorkflowPolicy:
    allowed_actions: tuple[str, ...] = DEFAULT_ALLOWED_ACTIONS
    disallowed_actions: tuple[str, ...] = DEFAULT_DISALLOWED_ACTIONS
    external_network_allowed: bool = False
    writes_allowed: bool = False

    def to_dict(self) -> dict[str, Any]:
        return {
            "allowed_actions": list(self.allowed_actions),
            "disallowed_actions": list(self.disallowed_actions),
            "external_network_allowed": self.external_network_allowed,
            "writes_allowed": self.writes_allowed,
        }

    def allows(self, action_name: str) -> bool:
        return action_name in self.allowed_actions and action_name not in self.disallowed_actions

    def rejects(self, action_name: str) -> bool:
        return not self.allows(action_name) or action_name in self.disallowed_actions


@dataclass(frozen=True)
class StatefulReadonlyWorkflowStep:
    step_id: str
    action_name: str
    parameters: dict[str, Any] = field(default_factory=dict)
    expected_text: str = ""
    expected_url: str | None = None
    collect_fact_keys: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        payload = {
            "step_id": self.step_id,
            "action_name": self.action_name,
            "parameters": dict(self.parameters),
            "expected_text": self.expected_text,
            "collect_fact_keys": list(self.collect_fact_keys),
        }
        if self.expected_url is not None:
            payload["expected_url"] = self.expected_url
        return payload


@dataclass
class StatefulReadonlyWorkflowState:
    workflow_id: str
    scenario_id: str
    step_index: int = 0
    current_observation: dict[str, Any] | None = None
    visited_urls: list[str] = field(default_factory=list)
    facts: dict[str, Any] = field(default_factory=dict)
    evidence_items: list[dict[str, Any]] = field(default_factory=list)
    pending_objectives: list[str] = field(default_factory=list)
    final_answer: str | None = None
    final_status: str = "running"
    trace_entries: list[dict[str, Any]] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": STATE_SCHEMA_VERSION,
            "workflow_id": self.workflow_id,
            "scenario_id": self.scenario_id,
            "step_index": self.step_index,
            "current_observation": dict(self.current_observation) if isinstance(self.current_observation, dict) else self.current_observation,
            "visited_urls": list(self.visited_urls),
            "facts": dict(self.facts),
            "evidence_items": [dict(item) for item in self.evidence_items],
            "pending_objectives": list(self.pending_objectives),
            "final_answer": self.final_answer,
            "final_status": self.final_status,
            "trace_entries": [dict(item) for item in self.trace_entries],
        }


@dataclass(frozen=True)
class StatefulReadonlyWorkflowScenarioDefinition:
    scenario_id: str
    workflow_id: str
    start_url: str
    objective: str
    steps: tuple[StatefulReadonlyWorkflowStep, ...]
    final_answer_builder: Callable[[StatefulReadonlyWorkflowState], str]
    fact_extractor: Callable[[BrowserRuntimeObservation, StatefulReadonlyWorkflowStep, StatefulReadonlyWorkflowState], dict[str, Any]]
    read_only_policy: StatefulReadonlyWorkflowPolicy = field(default_factory=StatefulReadonlyWorkflowPolicy)
    limitations: tuple[str, ...] = DEFAULT_LIMITATIONS


@dataclass(frozen=True)
class StatefulReadonlyWorkflowSummary:
    schema_version: str
    workflow_id: str
    scenario_id: str
    status: str
    error_code: str | None
    stop_reason: str | None
    steps_attempted: int
    steps_succeeded: int
    steps_failed: int
    actions_attempted: int
    actions_succeeded: int
    actions_failed: int
    facts_collected_total: int
    evidence_items_total: int
    visited_urls: tuple[str, ...]
    final_answer: str | None
    failure_class: str
    model_execution: bool
    real_browser_execution: bool
    playwright_execution: bool
    browser_opened: bool
    real_network_traffic: bool
    fixture_only: bool
    no_runtime_execution: bool
    limitations: tuple[str, ...]
    trace_path: str
    state_path: str
    summary_path: str
    policy: dict[str, Any]
    trace_entries: tuple[dict[str, Any], ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "workflow_id": self.workflow_id,
            "scenario_id": self.scenario_id,
            "status": self.status,
            "error_code": self.error_code,
            "stop_reason": self.stop_reason,
            "steps_attempted": self.steps_attempted,
            "steps_succeeded": self.steps_succeeded,
            "steps_failed": self.steps_failed,
            "actions_attempted": self.actions_attempted,
            "actions_succeeded": self.actions_succeeded,
            "actions_failed": self.actions_failed,
            "facts_collected_total": self.facts_collected_total,
            "evidence_items_total": self.evidence_items_total,
            "visited_urls": list(self.visited_urls),
            "final_answer": self.final_answer,
            "failure_class": self.failure_class,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "playwright_execution": self.playwright_execution,
            "browser_opened": self.browser_opened,
            "real_network_traffic": self.real_network_traffic,
            "fixture_only": self.fixture_only,
            "no_runtime_execution": self.no_runtime_execution,
            "limitations": list(self.limitations),
            "trace_path": self.trace_path,
            "state_path": self.state_path,
            "summary_path": self.summary_path,
            "policy": dict(self.policy),
            "trace_entries": [dict(item) for item in self.trace_entries],
        }


def build_default_stateful_readonly_workflow_scenarios(
    policy: StatefulReadonlyWorkflowPolicy | None = None,
) -> dict[str, StatefulReadonlyWorkflowScenarioDefinition]:
    policy = policy or StatefulReadonlyWorkflowPolicy()
    return {
        "stateful_policy_ticket_crosscheck": StatefulReadonlyWorkflowScenarioDefinition(
            scenario_id="stateful_policy_ticket_crosscheck",
            workflow_id="stateful_policy_ticket_crosscheck",
            start_url="https://local.intranet/",
            objective="Cross-check ticket priority against workspace policy.",
            steps=(
                StatefulReadonlyWorkflowStep(
                    step_id="open_home",
                    action_name="browser_open_url",
                    parameters={"url": "https://local.intranet/"},
                    expected_text="Office Intranet",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="click_ticket_board",
                    action_name="browser_click",
                    parameters={"target_text": "Ticket board"},
                    expected_text="Ticket Board",
                    expected_url="https://local.intranet/tickets",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="click_ticket_1",
                    action_name="browser_click",
                    parameters={"target_text": "Ticket 1"},
                    expected_text="Ticket 1 - Quarterly Access Review",
                    expected_url="https://local.intranet/tickets/1",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="inspect_ticket",
                    action_name="browser_extract_text",
                    parameters={},
                    expected_text="Priority: high.",
                    collect_fact_keys=("ticket_topic", "ticket_priority", "ticket_role", "ticket_status"),
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="click_policy",
                    action_name="browser_click",
                    parameters={"target_text": "Workspace policy"},
                    expected_text="Workspace Policy",
                    expected_url="https://local.intranet/docs/policy",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="inspect_policy",
                    action_name="browser_snapshot",
                    parameters={},
                    expected_text="fixture-backed result for workspace policy review",
                    collect_fact_keys=("policy_anchor", "policy_marker"),
                ),
            ),
            final_answer_builder=_build_policy_ticket_final_answer,
            fact_extractor=_extract_policy_ticket_facts,
            read_only_policy=policy,
        ),
        "stateful_approval_policy_crosscheck": StatefulReadonlyWorkflowScenarioDefinition(
            scenario_id="stateful_approval_policy_crosscheck",
            workflow_id="stateful_approval_policy_crosscheck",
            start_url="https://local.intranet/",
            objective="Cross-check approval policy evidence.",
            steps=(
                StatefulReadonlyWorkflowStep(
                    step_id="open_home",
                    action_name="browser_open_url",
                    parameters={"url": "https://local.intranet/"},
                    expected_text="Office Intranet",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="click_approvals_queue",
                    action_name="browser_click",
                    parameters={"target_text": "Approvals queue"},
                    expected_text="Approvals Queue",
                    expected_url="https://local.intranet/portal/approvals",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="click_policy_match_review",
                    action_name="browser_click",
                    parameters={"target_text": "Policy match review"},
                    expected_text="Approval Policy Match",
                    expected_url="https://local.intranet/portal/approval-match",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="inspect_approval_match",
                    action_name="browser_extract_text",
                    parameters={},
                    expected_text="Policy match: confirmed.",
                    collect_fact_keys=(
                        "approval_request",
                        "approval_policy_anchor",
                        "approval_policy_marker",
                        "approval_decision_note",
                    ),
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="click_policy",
                    action_name="browser_click",
                    parameters={"target_text": "Workspace policy"},
                    expected_text="Workspace Policy",
                    expected_url="https://local.intranet/docs/policy",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="inspect_policy",
                    action_name="browser_snapshot",
                    parameters={},
                    expected_text="fixture-backed result for workspace policy review",
                    collect_fact_keys=("policy_anchor", "policy_marker"),
                ),
            ),
            final_answer_builder=_build_approval_final_answer,
            fact_extractor=_extract_approval_facts,
            read_only_policy=policy,
        ),
        "stateful_intranet_overview_digest": StatefulReadonlyWorkflowScenarioDefinition(
            scenario_id="stateful_intranet_overview_digest",
            workflow_id="stateful_intranet_overview_digest",
            start_url="https://local.intranet/",
            objective="Summarize the intranet home, ticket board, policy, and team status pages.",
            steps=(
                StatefulReadonlyWorkflowStep(
                    step_id="open_home",
                    action_name="browser_open_url",
                    parameters={"url": "https://local.intranet/"},
                    expected_text="Office Intranet",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="click_ticket_board",
                    action_name="browser_click",
                    parameters={"target_text": "Ticket board"},
                    expected_text="Ticket Board",
                    expected_url="https://local.intranet/tickets",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="open_policy",
                    action_name="browser_open_url",
                    parameters={"url": "https://local.intranet/docs/policy"},
                    expected_text="Workspace Policy",
                    expected_url="https://local.intranet/docs/policy",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="open_team_status",
                    action_name="browser_open_url",
                    parameters={"url": "https://local.intranet/team/status"},
                    expected_text="Team Status",
                ),
            ),
            final_answer_builder=_build_overview_digest_final_answer,
            fact_extractor=_extract_overview_digest_facts,
            read_only_policy=policy,
        ),
        "stateful_ticket_priority_digest": StatefulReadonlyWorkflowScenarioDefinition(
            scenario_id="stateful_ticket_priority_digest",
            workflow_id="stateful_ticket_priority_digest",
            start_url="https://local.intranet/",
            objective="Identify the most important ticket from the priority cross-check board.",
            steps=(
                StatefulReadonlyWorkflowStep(
                    step_id="open_home",
                    action_name="browser_open_url",
                    parameters={"url": "https://local.intranet/"},
                    expected_text="Office Intranet",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="open_hardboard",
                    action_name="browser_open_url",
                    parameters={"url": "https://local.intranet/tickets/hardboard"},
                    expected_text="Ticket Board",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="click_ticket_7",
                    action_name="browser_click",
                    parameters={"target_text": "Ticket 7"},
                    expected_text="Ticket 7 - Escalation Review",
                    expected_url="https://local.intranet/tickets/7",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="inspect_ticket_7",
                    action_name="browser_extract_text",
                    parameters={},
                    expected_text="Priority: urgent.",
                    collect_fact_keys=("ticket_7_priority", "ticket_7_requester_tier", "ticket_7_marker"),
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="click_ticket_board",
                    action_name="browser_click",
                    parameters={"target_text": "Ticket board"},
                    expected_text="Ticket Board",
                    expected_url="https://local.intranet/tickets/hardboard",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="click_ticket_8",
                    action_name="browser_click",
                    parameters={"target_text": "Ticket 8"},
                    expected_text="Ticket 8 - Follow-up Note",
                    expected_url="https://local.intranet/tickets/8",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="inspect_ticket_8",
                    action_name="browser_snapshot",
                    parameters={},
                    expected_text="Search marker: this page is the decoy for the priority cross-check.",
                    collect_fact_keys=("ticket_8_priority", "ticket_8_requester_tier", "ticket_8_marker"),
                ),
            ),
            final_answer_builder=_build_ticket_priority_digest_final_answer,
            fact_extractor=_extract_ticket_priority_digest_facts,
            read_only_policy=policy,
        ),
        "stateful_policy_search_marker_review": StatefulReadonlyWorkflowScenarioDefinition(
            scenario_id="stateful_policy_search_marker_review",
            workflow_id="stateful_policy_search_marker_review",
            start_url="https://local.intranet/",
            objective="Find the workspace policy search marker.",
            steps=(
                StatefulReadonlyWorkflowStep(
                    step_id="open_home",
                    action_name="browser_open_url",
                    parameters={"url": "https://local.intranet/"},
                    expected_text="Office Intranet",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="click_policy",
                    action_name="browser_click",
                    parameters={"target_text": "Workspace policy"},
                    expected_text="Workspace Policy",
                    expected_url="https://local.intranet/docs/policy",
                ),
                StatefulReadonlyWorkflowStep(
                    step_id="inspect_policy",
                    action_name="browser_extract_text",
                    parameters={},
                    expected_text="fixture-backed result for workspace policy review",
                    collect_fact_keys=("policy_anchor", "policy_marker"),
                ),
            ),
            final_answer_builder=_build_policy_marker_final_answer,
            fact_extractor=_extract_policy_marker_facts,
            read_only_policy=policy,
        ),
    }


def run_autonomous_browser_stateful_readonly_workflow(
    scenario: StatefulReadonlyWorkflowScenarioDefinition,
    *,
    repo_root: str | Path | None = None,
    output_dir: str | Path | None = None,
    fixture_manifest_path: str | Path = DEFAULT_FIXTURE_MANIFEST_PATH,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    workflow_output_dir = _safe_relative_path(output_dir or DEFAULT_WORKFLOW_OUTPUT_DIR, "output_dir")
    if workflow_output_dir is None:
        return _workflow_failure(
            scenario_id=scenario.scenario_id,
            workflow_id=scenario.workflow_id,
            output_dir=DEFAULT_WORKFLOW_OUTPUT_DIR,
            error_code="config_validation_failed",
            failure_class="config_error",
            stop_reason="config_validation_failed",
            limitations=scenario.limitations,
            diagnostics={"config_error": "output_dir must be a safe relative path."},
        )

    workflow_dir = repo / workflow_output_dir / scenario.scenario_id
    workflow_dir.mkdir(parents=True, exist_ok=True)
    trace_rel_path = f"{workflow_output_dir}/{scenario.scenario_id}/workflow_trace.json"
    state_rel_path = f"{workflow_output_dir}/{scenario.scenario_id}/workflow_state.json"
    summary_rel_path = f"{workflow_output_dir}/{scenario.scenario_id}/workflow_summary.json"
    trace_path = repo / trace_rel_path
    state_path = repo / state_rel_path
    summary_path = repo / summary_rel_path

    state = StatefulReadonlyWorkflowState(
        workflow_id=scenario.workflow_id,
        scenario_id=scenario.scenario_id,
        pending_objectives=[scenario.objective],
    )
    session = BrowserRuntimeSession(
        session_id=f"{scenario.workflow_id}_session",
        agent_id="stateful_readonly_workflow",
        workspace_id="stateful_readonly_workspace",
        environment_id="stateful_readonly_environment",
        allowed_domains=("local.intranet", "docs.local", "portal.local", "local-intranet.test", "localhost", "127.0.0.1"),
        start_url=scenario.start_url,
        policy_flags=BrowserRuntimePolicy().to_flags(),
    )
    executor = FixtureBackedBrowserRuntimeExecutor(
        fixture_manifest_path=fixture_manifest_path,
        project_root=repo,
        policy=BrowserRuntimePolicy(),
    )
    verifier = BrowserRuntimeVerifier()

    steps_attempted = 0
    steps_succeeded = 0
    steps_failed = 0
    actions_attempted = 0
    actions_succeeded = 0
    actions_failed = 0
    status = "running"
    error_code: str | None = None
    stop_reason: str | None = None
    failure_class = "none"
    model_execution = False
    real_browser_execution = False
    playwright_execution = False
    browser_opened = False
    real_network_traffic = False

    for index, step in enumerate(scenario.steps, start=1):
        state.step_index = index
        steps_attempted += 1
        if not step.step_id.strip() or not step.action_name.strip():
            status = "failed"
            error_code = "script_error"
            stop_reason = "script_error"
            failure_class = "script_error"
            state.final_status = status
            state.trace_entries.append(
                _trace_entry(
                    step_index=index,
                    step=step,
                    status="failed",
                    error_code=error_code,
                    failure_class=failure_class,
                    observed_url=session.current_url,
                )
            )
            steps_failed += 1
            break
        if scenario.read_only_policy.rejects(step.action_name):
            status = "rejected"
            error_code = "action_not_allowed_by_scenario_policy"
            stop_reason = "scenario_policy_rejected"
            failure_class = "scenario_policy_rejected"
            state.final_status = status
            state.trace_entries.append(
                _trace_entry(
                    step_index=index,
                    step=step,
                    status="rejected",
                    error_code=error_code,
                    failure_class=failure_class,
                    observed_url=session.current_url,
                )
            )
            steps_failed += 1
            break

        action = BrowserRuntimeAction(
            agent_id=session.agent_id,
            action_type="browser",
            action_name=step.action_name,
            parameters=dict(step.parameters),
            session_id=session.session_id,
            task_id=scenario.scenario_id,
        )
        result = executor.execute(action, session)
        actions_attempted += 1
        if result.success:
            actions_succeeded += 1
        else:
            actions_failed += 1

        verification = verifier.verify(
            result,
            expected_text=step.expected_text or None,
            expected_url=step.expected_url,
        )
        if not result.success:
            status = "failed"
            error_code = result.error_type or "fixture_error"
            stop_reason = "fixture_error"
            failure_class = _failure_class_from_error_code(error_code, step=step, result=result)
            state.final_status = status
            state.trace_entries.append(
                _trace_entry(
                    step_index=index,
                    step=step,
                    status="failed",
                    error_code=error_code,
                    failure_class=failure_class,
                    observed_url=session.current_url,
                    result=result,
                    verification=verification,
                )
            )
            steps_failed += 1
            break
        if not verification.passed:
            status = "failed"
            error_code = verification.reason or "validation_error"
            stop_reason = "validation_error"
            failure_class = "validation_error"
            state.final_status = status
            state.trace_entries.append(
                _trace_entry(
                    step_index=index,
                    step=step,
                    status="failed",
                    error_code=error_code,
                    failure_class=failure_class,
                    observed_url=session.current_url,
                    result=result,
                    verification=verification,
                )
            )
            steps_failed += 1
            break

        steps_succeeded += 1
        observation = result.observation or session.last_observation
        extracted_fact_keys: tuple[str, ...] = ()
        evidence_item_id: str | None = None
        if observation is not None:
            extracted_fact_keys, evidence_item_id = _update_state_from_observation(state, step, observation, scenario.fact_extractor)
            if observation.current_url and observation.current_url not in state.visited_urls:
                state.visited_urls.append(observation.current_url)
            if step.action_name == "browser_open_url":
                browser_opened = True
        state.trace_entries.append(
            _trace_entry(
                step_index=index,
                step=step,
                status="succeeded",
                error_code=None,
                failure_class="none",
                observed_url=observation.current_url if observation else session.current_url,
                result=result,
                verification=verification,
                fact_keys=extracted_fact_keys,
                evidence_item_ids=(evidence_item_id,) if evidence_item_id is not None else (),
            )
        )

    if status == "running":
        try:
            state.final_answer = scenario.final_answer_builder(state)
        except Exception as exc:  # noqa: BLE001 - workflow builder failures are runtime data.
            status = "failed"
            error_code = "workflow_objective_unmet"
            stop_reason = "model_failed_task"
            failure_class = "model_failed_task"
            state.final_status = status
            state.trace_entries.append(
                {
                    "step_index": state.step_index,
                    "action_name": "final_answer_builder",
                    "action_parameters": {},
                    "status": "failed",
                    "error_code": error_code,
                    "failure_class": failure_class,
                    "observed_url": session.current_url,
                    "expected_text": None,
                    "extracted_fact_keys": [],
                    "evidence_item_ids": [],
                    "error_message": exc.__class__.__name__,
                }
            )
        else:
            status = "succeeded"
            stop_reason = "goal_satisfied"
            failure_class = "none"
            state.final_status = status

    state_path.write_text(json.dumps(state.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    summary = StatefulReadonlyWorkflowSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        workflow_id=scenario.workflow_id,
        scenario_id=scenario.scenario_id,
        status=status,
        error_code=error_code,
        stop_reason=stop_reason,
        steps_attempted=steps_attempted,
        steps_succeeded=steps_succeeded,
        steps_failed=steps_failed,
        actions_attempted=actions_attempted,
        actions_succeeded=actions_succeeded,
        actions_failed=actions_failed,
        facts_collected_total=len(state.facts),
        evidence_items_total=len(state.evidence_items),
        visited_urls=tuple(state.visited_urls),
        final_answer=state.final_answer,
        failure_class=failure_class,
        model_execution=model_execution,
        real_browser_execution=real_browser_execution,
        playwright_execution=playwright_execution,
        browser_opened=browser_opened,
        real_network_traffic=real_network_traffic,
        fixture_only=True,
        no_runtime_execution=True,
        limitations=scenario.limitations,
        trace_path=trace_rel_path,
        state_path=state_rel_path,
        summary_path=summary_rel_path,
        policy=scenario.read_only_policy.to_dict(),
        trace_entries=tuple(state.trace_entries),
    )
    payload = summary.to_dict()
    _write_json(trace_path, {
        "schema_version": TRACE_SCHEMA_VERSION,
        "workflow_id": scenario.workflow_id,
        "scenario_id": scenario.scenario_id,
        "trace_entries": state.trace_entries,
    })
    _write_json(summary_path, payload)
    return payload


def _update_state_from_observation(
    state: StatefulReadonlyWorkflowState,
    step: StatefulReadonlyWorkflowStep,
    observation: BrowserRuntimeObservation,
    fact_extractor: Callable[[BrowserRuntimeObservation, StatefulReadonlyWorkflowStep, StatefulReadonlyWorkflowState], dict[str, Any]],
) -> tuple[tuple[str, ...], str | None]:
    facts = fact_extractor(observation, step, state)
    if not facts:
        return (), None
    evidence_item_id = f"{state.workflow_id}-evidence-{len(state.evidence_items) + 1}"
    new_fact_keys: list[str] = []
    for key, value in facts.items():
        if key not in state.facts or state.facts[key] != value:
            state.facts[key] = value
            new_fact_keys.append(key)
    state.evidence_items.append(
        {
            "evidence_item_id": evidence_item_id,
            "source_step_id": step.step_id,
            "source_url": observation.current_url,
            "title": observation.title,
            "text_preview": observation.text_preview[:300],
            "fact_keys": new_fact_keys,
        }
    )
    return tuple(new_fact_keys), evidence_item_id


def _trace_entry(
    *,
    step_index: int,
    step: StatefulReadonlyWorkflowStep,
    status: str,
    error_code: str | None,
    failure_class: str,
    observed_url: str | None,
    result: Any | None = None,
    verification: Any | None = None,
    fact_keys: tuple[str, ...] = (),
    evidence_item_ids: tuple[str, ...] = (),
) -> dict[str, Any]:
    entry: dict[str, Any] = {
        "step_index": step_index,
        "action_name": step.action_name,
        "action_parameters": _sanitize_action_parameters(step.parameters),
        "status": status,
        "error_code": error_code,
        "observed_url": observed_url,
        "expected_text": step.expected_text or None,
        "failure_class": failure_class,
        "extracted_fact_keys": list(fact_keys),
        "evidence_item_ids": list(evidence_item_ids),
    }
    if step.expected_url is not None:
        entry["expected_url"] = step.expected_url
    if verification is not None:
        entry["expected_result"] = verification.to_dict() if hasattr(verification, "to_dict") else None
    if result is not None and hasattr(result, "to_dict"):
        entry["action_result"] = result.to_dict()
    return entry


def _sanitize_action_parameters(parameters: Mapping[str, Any]) -> dict[str, Any]:
    payload: dict[str, Any] = {}
    for key, value in parameters.items():
        if isinstance(value, str):
            payload[key] = value
        elif isinstance(value, (int, float, bool)) or value is None:
            payload[key] = value
        elif isinstance(value, list):
            payload[key] = [item for item in value if isinstance(item, (str, int, float, bool)) or item is None]
        elif isinstance(value, dict):
            payload[key] = _sanitize_action_parameters(value)
    return payload


def _failure_class_from_error_code(
    error_code: str,
    *,
    step: StatefulReadonlyWorkflowStep,
    result: Any,
) -> str:
    del step, result
    if error_code == "action_not_allowed_by_scenario_policy":
        return "scenario_policy_rejected"
    if error_code in {"config_validation_failed", "workflow_config_invalid"}:
        return "config_error"
    if error_code in {"fixture_resolution_failed", "browser_click_target_not_found"}:
        return "fixture_error"
    if error_code in {"expected_text_missing", "expected_url_mismatch", "required_artifact_missing", "browser_action_failed"}:
        return "validation_error"
    if error_code in {"script_error", "workflow_objective_unmet"}:
        return "model_failed_task"
    return "script_error"


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _workflow_failure(
    *,
    scenario_id: str,
    workflow_id: str,
    output_dir: str,
    error_code: str,
    failure_class: str,
    stop_reason: str,
    limitations: tuple[str, ...],
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    summary = StatefulReadonlyWorkflowSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        workflow_id=workflow_id,
        scenario_id=scenario_id,
        status="failed",
        error_code=error_code,
        stop_reason=stop_reason,
        steps_attempted=0,
        steps_succeeded=0,
        steps_failed=0,
        actions_attempted=0,
        actions_succeeded=0,
        actions_failed=0,
        facts_collected_total=0,
        evidence_items_total=0,
        visited_urls=(),
        final_answer=None,
        failure_class=failure_class,
        model_execution=False,
        real_browser_execution=False,
        playwright_execution=False,
        browser_opened=False,
        real_network_traffic=False,
        fixture_only=True,
        no_runtime_execution=True,
        limitations=limitations,
        trace_path=f"{output_dir}/{scenario_id}/workflow_trace.json",
        state_path=f"{output_dir}/{scenario_id}/workflow_state.json",
        summary_path=f"{output_dir}/{scenario_id}/workflow_summary.json",
        policy=StatefulReadonlyWorkflowPolicy().to_dict(),
    )
    payload = summary.to_dict()
    if diagnostics:
        payload["diagnostics"] = dict(diagnostics)
    return payload


def _safe_relative_path_for_workflow(value: Any, label: str) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return None
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        return None
    return path.as_posix()


def _compact_text(text: str) -> str:
    return re.sub(r"\s+", " ", text).strip()


def _build_policy_ticket_final_answer(state: StatefulReadonlyWorkflowState) -> str:
    ticket = state.facts.get("ticket_topic", "Quarterly Access Review")
    priority = state.facts.get("ticket_priority", "high")
    role = state.facts.get("ticket_role", "office worker")
    policy_marker = state.facts.get("policy_marker", "fixture-backed result for workspace policy review")
    return (
        f"Ticket 1 cross-check complete: {ticket} is {priority} priority for {role}; "
        f"policy match confirmed by {policy_marker}. Risk conclusion: review required."
    )


def _build_approval_final_answer(state: StatefulReadonlyWorkflowState) -> str:
    approval_item = state.facts.get("approval_request", "APR-51")
    policy_marker = state.facts.get("approval_policy_marker", "approval-policy match is the fixture-backed answer")
    return (
        f"Approval cross-check complete: {approval_item} matches local policy evidence; "
        f"{policy_marker} Recommended outcome: local review approved."
    )


def _build_overview_digest_final_answer(state: StatefulReadonlyWorkflowState) -> str:
    return (
        "Intranet overview reviewed home, ticket board, workspace policy, and team status; "
        "the local fixture shows routine ticket updates, policy guidance, and team note-taking."
    )


def _build_ticket_priority_digest_final_answer(state: StatefulReadonlyWorkflowState) -> str:
    priority = state.facts.get("ticket_7_priority", "urgent")
    requester = state.facts.get("ticket_7_requester_tier", "facilities")
    return (
        f"Most important ticket: Ticket 7 - Escalation Review because requester tier is {requester} and priority is {priority}. "
        "Ticket 8 is the lower-priority decoy."
    )


def _build_policy_marker_final_answer(state: StatefulReadonlyWorkflowState) -> str:
    marker = state.facts.get("policy_marker", "fixture-backed result for workspace policy review")
    return f"Workspace policy evidence marker: {marker}."


def _extract_policy_ticket_facts(
    observation: BrowserRuntimeObservation,
    step: StatefulReadonlyWorkflowStep,
    state: StatefulReadonlyWorkflowState,
) -> dict[str, Any]:
    del step, state
    text = _compact_text(f"{observation.title or ''} {observation.text_preview or ''}")
    facts: dict[str, Any] = {}
    if "Ticket 1" in text:
        facts["ticket_id"] = "Ticket 1"
    if "Quarterly Access Review" in text:
        facts["ticket_topic"] = "Quarterly Access Review"
    if "Priority: high" in text:
        facts["ticket_priority"] = "high"
    if "Assigned role: office worker" in text:
        facts["ticket_role"] = "office worker"
    if "Status: open" in text:
        facts["ticket_status"] = "open"
    if "Workspace Policy" in text:
        facts["policy_anchor"] = "Workspace Policy"
    if "fixture-backed result for workspace policy review" in text:
        facts["policy_marker"] = "fixture-backed result for workspace policy review"
    return facts


def _extract_approval_facts(
    observation: BrowserRuntimeObservation,
    step: StatefulReadonlyWorkflowStep,
    state: StatefulReadonlyWorkflowState,
) -> dict[str, Any]:
    del step, state
    text = _compact_text(f"{observation.title or ''} {observation.text_preview or ''}")
    facts: dict[str, Any] = {}
    if "APR-51" in text:
        facts["approval_request"] = "APR-51"
    if "Approval Policy Match" in text:
        facts["approval_policy_anchor"] = "Approval Policy Match"
    if "Policy match: confirmed" in text:
        facts["approval_policy_marker"] = "Policy match: confirmed."
    if "local fixtures only" in text:
        facts["approval_decision_note"] = "local fixtures only"
    return facts


def _extract_overview_digest_facts(
    observation: BrowserRuntimeObservation,
    step: StatefulReadonlyWorkflowStep,
    state: StatefulReadonlyWorkflowState,
) -> dict[str, Any]:
    del step, state
    text = _compact_text(f"{observation.title or ''} {observation.text_preview or ''}")
    facts: dict[str, Any] = {}
    if "Office Intranet" in text:
        facts["home_anchor"] = "Office Intranet"
    if "Ticket Board" in text:
        facts["ticket_board_anchor"] = "Ticket Board"
    if "Workspace Policy" in text:
        facts["policy_anchor"] = "Workspace Policy"
    if "Team Status" in text:
        facts["team_status_anchor"] = "Team Status"
    return facts


def _extract_ticket_priority_digest_facts(
    observation: BrowserRuntimeObservation,
    step: StatefulReadonlyWorkflowStep,
    state: StatefulReadonlyWorkflowState,
) -> dict[str, Any]:
    del step, state
    text = _compact_text(f"{observation.title or ''} {observation.text_preview or ''}")
    facts: dict[str, Any] = {}
    if "Ticket 7" in text:
        facts["ticket_7_id"] = "Ticket 7"
    if "Escalation Review" in text:
        facts["ticket_7_topic"] = "Escalation Review"
    if "Priority: urgent" in text:
        facts["ticket_7_priority"] = "urgent"
    if "Requester tier: facilities" in text:
        facts["ticket_7_requester_tier"] = "facilities"
    if "Ticket 8" in text:
        facts["ticket_8_id"] = "Ticket 8"
    if "Follow-up Note" in text:
        facts["ticket_8_topic"] = "Follow-up Note"
    if "Priority: low" in text:
        facts["ticket_8_priority"] = "low"
    if "office worker" in text:
        facts["ticket_8_requester_tier"] = "office worker"
    if "decoy for the priority cross-check" in text:
        facts["ticket_8_marker"] = "decoy for the priority cross-check"
    if "the escalation ticket is the urgent one" in text:
        facts["ticket_7_marker"] = "the escalation ticket is the urgent one"
    return facts


def _extract_policy_marker_facts(
    observation: BrowserRuntimeObservation,
    step: StatefulReadonlyWorkflowStep,
    state: StatefulReadonlyWorkflowState,
) -> dict[str, Any]:
    del step, state
    text = _compact_text(f"{observation.title or ''} {observation.text_preview or ''}")
    facts: dict[str, Any] = {}
    if "Workspace Policy" in text:
        facts["policy_anchor"] = "Workspace Policy"
    if "fixture-backed result for workspace policy review" in text:
        facts["policy_marker"] = "fixture-backed result for workspace policy review"
    return facts
