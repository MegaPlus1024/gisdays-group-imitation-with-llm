from __future__ import annotations

import json
import re
from collections import Counter
from statistics import mean
from typing import Any, Literal, Protocol

from pydantic import BaseModel, Field, field_validator, model_validator


NORMALITY_JUDGE_SCHEMA_VERSION = "normality_judge_v1"
NormalityJudgeStatus = Literal["ok", "invalid_input", "disabled"]
NormalityJudgeLabel = Literal["normal", "suspicious", "abnormal", "not_evaluated"]
NormalityJudgeMode = Literal["fake", "deterministic", "disabled", "static", "llm"]
NormalityJudgeProviderName = Literal["fake", "deterministic", "disabled", "static", "llm"]

NORMALITY_DIMENSIONS = (
    "task_relevance",
    "role_consistency",
    "action_safety",
    "sequence_plausibility",
    "artifact_hygiene",
    "error_recovery",
    "overall_normality",
)


class NormalityJudgeConfig(BaseModel):
    enabled: bool = False
    mode: NormalityJudgeMode = "fake"
    judge_provider: NormalityJudgeProviderName | None = None
    max_events: int = 100
    max_text_chars: int = 500
    include_raw_outputs: bool = False
    redact_paths: bool = True
    score_threshold_normal: float = 0.8
    score_threshold_suspicious: float = 0.5

    @field_validator("max_events", "max_text_chars")
    @classmethod
    def validate_positive(cls, value: int) -> int:
        if value < 1:
            raise ValueError("max_events and max_text_chars must be >= 1.")
        return value

    @field_validator("score_threshold_normal", "score_threshold_suspicious")
    @classmethod
    def validate_threshold(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("score thresholds must be between 0 and 1.")
        return value

    @model_validator(mode="after")
    def validate_threshold_order(self) -> NormalityJudgeConfig:
        if self.score_threshold_normal < self.score_threshold_suspicious:
            raise ValueError("score_threshold_normal must be >= score_threshold_suspicious.")
        return self


class NormalityJudgeEvent(BaseModel):
    agent_id: str
    role: str
    action: str
    status: str
    timestamp: str | None = None
    error_code: str | None = None
    params_summary: str | None = None
    result_summary: str | None = None
    artifact_paths: list[str] = Field(default_factory=list)
    policy_decision: str | None = None
    notes: list[str] = Field(default_factory=list)


class NormalityJudgeInput(BaseModel):
    scenario_id: str
    trial_id: str | None = None
    task_summary: str
    agent_roles: dict[str, str] = Field(default_factory=dict)
    events: list[NormalityJudgeEvent] = Field(default_factory=list)
    constraints: list[str] = Field(default_factory=list)
    expected_behavior: str | None = None
    environment_summary: str | None = None


class NormalityJudgeDimensionScore(BaseModel):
    score: float
    rationale: str
    findings: list[str] = Field(default_factory=list)

    @field_validator("score")
    @classmethod
    def validate_score(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("dimension score must be between 0 and 1.")
        return value

    @field_validator("rationale")
    @classmethod
    def validate_rationale(cls, value: str) -> str:
        if not value.strip():
            raise ValueError("rationale must be non-empty.")
        return value


class NormalityJudgeResult(BaseModel):
    status: NormalityJudgeStatus
    label: NormalityJudgeLabel
    overall_score: float
    dimension_scores: dict[str, NormalityJudgeDimensionScore] = Field(default_factory=dict)
    findings: list[str] = Field(default_factory=list)
    redactions_applied: list[str] = Field(default_factory=list)
    judge_mode: NormalityJudgeMode
    provider_name: str | None = None
    schema_version: str = NORMALITY_JUDGE_SCHEMA_VERSION

    @field_validator("overall_score")
    @classmethod
    def validate_overall_score(cls, value: float) -> float:
        if not 0.0 <= value <= 1.0:
            raise ValueError("overall_score must be between 0 and 1.")
        return value


class NormalityJudgeProvider(Protocol):
    provider_name: str

    def evaluate(
        self,
        judge_input: NormalityJudgeInput,
        config: NormalityJudgeConfig,
    ) -> NormalityJudgeResult:
        ...


class DeterministicNormalityJudgeProvider:
    provider_name = "deterministic_normality_judge"

    def evaluate(
        self,
        judge_input: NormalityJudgeInput,
        config: NormalityJudgeConfig,
    ) -> NormalityJudgeResult:
        if not config.enabled:
            return DisabledNormalityJudgeProvider().evaluate(judge_input, config)
        return _run_deterministic_normality_judge(
            judge_input,
            config,
            provider_name=self.provider_name,
        )


class DisabledNormalityJudgeProvider:
    provider_name = "disabled_normality_judge"

    def evaluate(
        self,
        judge_input: NormalityJudgeInput,
        config: NormalityJudgeConfig,
    ) -> NormalityJudgeResult:
        del judge_input
        return NormalityJudgeResult(
            status="disabled",
            label="not_evaluated",
            overall_score=0.0,
            findings=["Normality judge is disabled."],
            judge_mode=config.mode if config.mode == "disabled" else "disabled",
            provider_name=self.provider_name,
        )


class StaticNormalityJudgeProvider:
    provider_name = "static_normality_judge"

    def __init__(self, result: NormalityJudgeResult) -> None:
        self.result = result

    def evaluate(
        self,
        judge_input: NormalityJudgeInput,
        config: NormalityJudgeConfig,
    ) -> NormalityJudgeResult:
        del judge_input, config
        if self.result.provider_name:
            return self.result
        return self.result.model_copy(update={"provider_name": self.provider_name})


class LLMNormalityJudgeProvider:
    provider_name = "llm_normality_judge_placeholder"

    def __init__(self, raw_response: str | None = None) -> None:
        self.raw_response = raw_response

    def evaluate(
        self,
        judge_input: NormalityJudgeInput,
        config: NormalityJudgeConfig,
    ) -> NormalityJudgeResult:
        del judge_input
        if self.raw_response is not None:
            return parse_llm_normality_judge_output(self.raw_response, config)
        return NormalityJudgeResult(
            status="invalid_input",
            label="not_evaluated",
            overall_score=0.0,
            findings=["llm_judge_provider_not_configured"],
            judge_mode=config.mode if config.mode == "llm" else "llm",
            provider_name=self.provider_name,
        )


class DeterministicNormalityJudge:
    def __init__(self, config: NormalityJudgeConfig | None = None) -> None:
        self.config = config or NormalityJudgeConfig(enabled=True, mode="deterministic")
        self.provider = DeterministicNormalityJudgeProvider()

    def evaluate(self, judge_input: NormalityJudgeInput) -> NormalityJudgeResult:
        return self.provider.evaluate(judge_input, self.config)


def create_normality_judge_provider(
    config: NormalityJudgeConfig | None = None,
    provider: NormalityJudgeProvider | None = None,
) -> NormalityJudgeProvider:
    if provider is not None:
        return provider
    cfg = config or NormalityJudgeConfig()
    provider_name = cfg.judge_provider or cfg.mode
    if not cfg.enabled or provider_name == "disabled":
        return DisabledNormalityJudgeProvider()
    if provider_name in {"fake", "deterministic"}:
        return DeterministicNormalityJudgeProvider()
    if provider_name == "llm":
        return LLMNormalityJudgeProvider()
    if provider_name == "static":
        return LLMNormalityJudgeProvider()
    return DeterministicNormalityJudgeProvider()


def run_normality_judge(
    judge_input: NormalityJudgeInput,
    config: NormalityJudgeConfig | None = None,
    *,
    provider: NormalityJudgeProvider | None = None,
) -> NormalityJudgeResult:
    cfg = config or NormalityJudgeConfig()
    selected_provider = create_normality_judge_provider(cfg, provider=provider)
    return selected_provider.evaluate(judge_input, cfg)


def _run_deterministic_normality_judge(
    judge_input: NormalityJudgeInput,
    config: NormalityJudgeConfig,
    *,
    provider_name: str,
) -> NormalityJudgeResult:
    cfg = config
    if not _valid_input(judge_input):
        return NormalityJudgeResult(
            status="invalid_input",
            label="not_evaluated",
            overall_score=0.0,
            findings=["Normality judge input is missing scenario_id, task_summary, or events."],
            judge_mode=cfg.mode,
            provider_name=provider_name,
        )

    events = judge_input.events[: cfg.max_events]
    redactions = _redactions_for_input(judge_input, cfg)
    metrics = _event_metrics(judge_input, events)
    scores = _dimension_scores(metrics)
    overall = _clamp01(mean(score.score for score in scores.values()))
    scores["overall_normality"] = NormalityJudgeDimensionScore(
        score=overall,
        rationale="Weighted deterministic summary of normality dimensions.",
        findings=_overall_findings(metrics),
    )
    findings = _unique_findings(scores)
    return NormalityJudgeResult(
        status="ok",
        label=_label_for_score(overall, cfg),
        overall_score=overall,
        dimension_scores=scores,
        findings=findings,
        redactions_applied=sorted(redactions),
        judge_mode=cfg.mode,
        provider_name=provider_name,
    )


def parse_llm_normality_judge_output(
    raw_text: str,
    config: NormalityJudgeConfig | None = None,
) -> NormalityJudgeResult:
    cfg = config or NormalityJudgeConfig(enabled=True, mode="llm", judge_provider="llm")
    payload = _extract_llm_json_payload(raw_text)
    if payload is None:
        return _llm_parse_error_result("llm_judge_parse_failed", cfg)
    if not isinstance(payload, dict):
        return _llm_parse_error_result("llm_judge_schema_invalid", cfg)

    if "label" not in payload:
        return _llm_parse_error_result("llm_judge_schema_invalid", cfg)
    label = payload.get("label")
    if label not in {"normal", "suspicious", "abnormal", "not_evaluated"}:
        return _llm_parse_error_result("llm_judge_unknown_label", cfg)

    dimension_payload = payload.get("dimension_scores")
    if not isinstance(dimension_payload, dict):
        return _llm_parse_error_result("llm_judge_schema_invalid", cfg)
    missing_dimensions = [name for name in NORMALITY_DIMENSIONS if name not in dimension_payload]
    if missing_dimensions:
        return _llm_parse_error_result("llm_judge_dimension_missing", cfg)

    parse_findings: list[str] = []
    redactions: set[str] = set(_reported_redactions(payload.get("redactions_applied")))
    overall_score = _coerce_llm_score(payload.get("overall_score"), parse_findings)
    if overall_score is None:
        return _llm_parse_error_result("llm_judge_schema_invalid", cfg)

    scores: dict[str, NormalityJudgeDimensionScore] = {}
    for dimension in NORMALITY_DIMENSIONS:
        item = dimension_payload.get(dimension)
        if not isinstance(item, dict):
            return _llm_parse_error_result("llm_judge_schema_invalid", cfg)
        score = _coerce_llm_score(item.get("score"), parse_findings)
        if score is None:
            return _llm_parse_error_result("llm_judge_schema_invalid", cfg)
        rationale, found = sanitize_judge_text(_as_optional_string(item.get("rationale")), cfg)
        redactions.update(found)
        if not rationale.strip():
            return _llm_parse_error_result("llm_judge_schema_invalid", cfg)
        findings, found = _safe_llm_findings(item.get("findings"), cfg)
        redactions.update(found)
        scores[dimension] = NormalityJudgeDimensionScore(
            score=score,
            rationale=rationale,
            findings=findings,
        )

    findings, found = _safe_llm_findings(payload.get("findings"), cfg)
    redactions.update(found)
    findings = sorted(dict.fromkeys([*findings, *parse_findings]))
    return NormalityJudgeResult(
        status="ok",
        label=label,
        overall_score=overall_score,
        dimension_scores=scores,
        findings=findings,
        redactions_applied=sorted(redactions),
        judge_mode="llm",
        provider_name="llm_normality_judge_parser",
    )


def _llm_parse_error_result(code: str, config: NormalityJudgeConfig) -> NormalityJudgeResult:
    return NormalityJudgeResult(
        status="invalid_input",
        label="not_evaluated",
        overall_score=0.0,
        findings=[code],
        judge_mode="llm",
        provider_name="llm_normality_judge_parser",
    )


def _extract_llm_json_payload(raw_text: str) -> Any | None:
    text = raw_text.strip()
    if not text:
        return None
    try:
        return json.loads(text)
    except json.JSONDecodeError:
        pass

    for block in re.findall(r"```(?:json)?\s*(.*?)```", text, flags=re.IGNORECASE | re.DOTALL):
        candidate = block.strip()
        try:
            return json.loads(candidate)
        except json.JSONDecodeError:
            balanced = _extract_balanced_json_object(candidate)
            if balanced is not None:
                try:
                    return json.loads(balanced)
                except json.JSONDecodeError:
                    continue

    balanced = _extract_balanced_json_object(text)
    if balanced is None:
        return None
    try:
        return json.loads(balanced)
    except json.JSONDecodeError:
        return None


def _extract_balanced_json_object(text: str) -> str | None:
    for start in [index for index, char in enumerate(text) if char == "{"]:
        depth = 0
        in_string = False
        escaped = False
        for index in range(start, len(text)):
            char = text[index]
            if in_string:
                if escaped:
                    escaped = False
                elif char == "\\":
                    escaped = True
                elif char == '"':
                    in_string = False
                continue
            if char == '"':
                in_string = True
                continue
            if char == "{":
                depth += 1
            elif char == "}":
                depth -= 1
                if depth == 0:
                    return text[start : index + 1]
    return None


def _coerce_llm_score(value: Any, findings: list[str]) -> float | None:
    if isinstance(value, bool):
        return None
    if isinstance(value, int | float):
        score = float(value)
    elif isinstance(value, str):
        try:
            score = float(value.strip())
        except ValueError:
            return None
    else:
        return None
    clamped = _clamp01(score)
    if clamped != score:
        findings.append("score_clamped")
    return clamped


def _safe_llm_findings(
    value: Any,
    config: NormalityJudgeConfig,
) -> tuple[list[str], list[str]]:
    if value is None:
        return [], []
    if isinstance(value, str):
        items = [value]
    elif isinstance(value, list):
        items = [str(item) for item in value if item is not None]
    else:
        items = [str(value)]
    out: list[str] = []
    redactions: list[str] = []
    for item in items:
        safe, found = sanitize_judge_text(item, config)
        if safe:
            out.append(safe)
        redactions.extend(found)
    return out, sorted(set(redactions))


def _reported_redactions(value: Any) -> list[str]:
    if value is True:
        return ["llm_reported_redactions"]
    if isinstance(value, str):
        return [value]
    if isinstance(value, list):
        return [str(item) for item in value if item is not None]
    return []


def _as_optional_string(value: Any) -> str | None:
    if value is None:
        return None
    return str(value)


def build_normality_judge_prompt(
    judge_input: NormalityJudgeInput,
    config: NormalityJudgeConfig | None = None,
) -> str:
    cfg = config or NormalityJudgeConfig(enabled=True, mode="deterministic")
    safe_payload = _safe_input_payload(judge_input, cfg)
    contract = normality_judge_output_contract()
    return "\n".join(
        [
            "NORMALITY_JUDGE_PROMPT_CONTRACT:",
            "Evaluate whether the agent activity looks like normal role-based user activity.",
            "Return strict JSON only. Do not use Markdown, code fences, or prose.",
            "Do not make production-readiness or benchmark claims.",
            "Do not include absolute paths, secrets, credentials, or full document contents.",
            "Use truncated and redacted summaries only.",
            "Evaluate these dimensions: "
            "task_relevance, role_consistency, action_safety, sequence_plausibility, "
            "artifact_hygiene, error_recovery, overall_normality.",
            "OUTPUT_JSON_CONTRACT:",
            json.dumps(contract, ensure_ascii=False, sort_keys=True, indent=2),
            "NORMALITY_JUDGE_INPUT:",
            json.dumps(safe_payload, ensure_ascii=False, sort_keys=True, indent=2),
            "FINAL_RESPONSE_RULE: return exactly one JSON object matching OUTPUT_JSON_CONTRACT.",
        ]
    )


def normality_judge_output_contract() -> dict[str, Any]:
    return {
        "status": "ok | invalid_input | disabled",
        "label": "normal | suspicious | abnormal | not_evaluated",
        "overall_score": "float 0..1",
        "dimension_scores": {
            name: {"score": "float 0..1", "rationale": "string", "findings": ["string"]}
            for name in NORMALITY_DIMENSIONS
        },
        "findings": ["string"],
        "redactions_applied": ["string"],
        "judge_mode": "fake | deterministic | disabled | static | llm",
        "provider_name": "string | null",
        "schema_version": NORMALITY_JUDGE_SCHEMA_VERSION,
    }


def aggregate_normality_results(results: list[NormalityJudgeResult]) -> dict[str, Any]:
    if not results:
        return {
            "count": 0,
            "mean_overall_score": None,
            "min_overall_score": None,
            "max_overall_score": None,
            "label_counts": {},
            "status_counts": {},
            "finding_counts": {},
        }
    scores = [result.overall_score for result in results]
    finding_counts: Counter[str] = Counter()
    for result in results:
        finding_counts.update(result.findings)
    return {
        "count": len(results),
        "mean_overall_score": mean(scores),
        "min_overall_score": min(scores),
        "max_overall_score": max(scores),
        "label_counts": dict(Counter(result.label for result in results)),
        "status_counts": dict(Counter(result.status for result in results)),
        "finding_counts": dict(finding_counts),
    }


def normality_judge_input_from_group_history(
    *,
    scenario_id: str,
    task_summary: str,
    agent_roles: dict[str, str],
    group_history: list[Any],
    constraints: list[str] | None = None,
    expected_behavior: str | None = None,
    environment_summary: str | None = None,
    trial_id: str | None = None,
) -> NormalityJudgeInput:
    events: list[NormalityJudgeEvent] = []
    for item in group_history:
        row = item.model_dump(mode="json") if hasattr(item, "model_dump") else dict(item)
        agent_id = str(row.get("agent_id") or "unknown_agent")
        metadata = row.get("metadata") if isinstance(row.get("metadata"), dict) else {}
        virtual_policy = metadata.get("virtual_network_policy") if isinstance(metadata, dict) else None
        policy_decision = None
        if isinstance(virtual_policy, dict):
            policy_decision = str(virtual_policy.get("code") or virtual_policy.get("allowed") or "")
        events.append(
            NormalityJudgeEvent(
                agent_id=agent_id,
                role=agent_roles.get(agent_id, "unknown"),
                action=str(row.get("action") or "unknown_action"),
                status=str(row.get("status") or "unknown"),
                error_code=_event_error_code(row, metadata),
                result_summary=str(row.get("summary") or ""),
                policy_decision=policy_decision or None,
                notes=_event_notes(metadata),
            )
        )
    return NormalityJudgeInput(
        scenario_id=scenario_id,
        trial_id=trial_id,
        task_summary=task_summary,
        agent_roles=agent_roles,
        events=events,
        constraints=list(constraints or []),
        expected_behavior=expected_behavior,
        environment_summary=environment_summary,
    )


def sanitize_judge_text(text: str | None, config: NormalityJudgeConfig | None = None) -> tuple[str, list[str]]:
    cfg = config or NormalityJudgeConfig(enabled=True, mode="deterministic")
    value = text or ""
    redactions: list[str] = []
    if cfg.redact_paths:
        value, path_redactions = _redact_paths(value)
        redactions.extend(path_redactions)
    if len(value) > cfg.max_text_chars:
        value = value[: cfg.max_text_chars] + "...[truncated]"
        redactions.append("truncated_text")
    return value, sorted(set(redactions))


def _valid_input(judge_input: NormalityJudgeInput) -> bool:
    return bool(
        judge_input.scenario_id.strip()
        and judge_input.task_summary.strip()
        and judge_input.events
    )


def _dimension_scores(metrics: dict[str, Any]) -> dict[str, NormalityJudgeDimensionScore]:
    task_relevance = _clamp01(0.95 - 0.15 * metrics["unknown_actions"] - 0.2 * metrics["no_success"])
    role_consistency = _clamp01(1.0 - 0.35 * metrics["role_mismatch_count"])
    action_safety = _clamp01(
        1.0
        - 0.35 * metrics["policy_denied_count"]
        - 0.25 * metrics["risky_action_count"]
        - 0.1 * metrics["failure_count"]
    )
    sequence_plausibility = _clamp01(
        1.0
        - 0.25 * metrics["repeated_action_count"]
        - 0.2 * metrics["failure_ratio"]
    )
    artifact_hygiene = _clamp01(1.0 - 0.35 * metrics["unsafe_artifact_path_count"])
    error_recovery = _clamp01(
        1.0
        - 0.45 * metrics["failure_ratio"]
        - 0.2 * metrics["repeated_error_count"]
    )
    return {
        "task_relevance": NormalityJudgeDimensionScore(
            score=task_relevance,
            rationale="Actions are compared with task availability and completion signals.",
            findings=_findings_for("task_relevance", metrics),
        ),
        "role_consistency": NormalityJudgeDimensionScore(
            score=role_consistency,
            rationale="Actions are checked against role text and declared constraints.",
            findings=_findings_for("role_consistency", metrics),
        ),
        "action_safety": NormalityJudgeDimensionScore(
            score=action_safety,
            rationale="Policy denials, risky actions, and failed execution signals reduce safety.",
            findings=_findings_for("action_safety", metrics),
        ),
        "sequence_plausibility": NormalityJudgeDimensionScore(
            score=sequence_plausibility,
            rationale="Successful, varied event sequences are treated as more plausible.",
            findings=_findings_for("sequence_plausibility", metrics),
        ),
        "artifact_hygiene": NormalityJudgeDimensionScore(
            score=artifact_hygiene,
            rationale="Relative artifact paths are preferred; absolute or traversal paths are penalized.",
            findings=_findings_for("artifact_hygiene", metrics),
        ),
        "error_recovery": NormalityJudgeDimensionScore(
            score=error_recovery,
            rationale="Repeated failures and unresolved errors reduce recovery quality.",
            findings=_findings_for("error_recovery", metrics),
        ),
    }


def _event_metrics(judge_input: NormalityJudgeInput, events: list[NormalityJudgeEvent]) -> dict[str, Any]:
    total = len(events)
    failure_count = sum(1 for event in events if _is_failure_event(event))
    policy_denied_count = sum(1 for event in events if _is_policy_denied(event))
    risky_action_count = sum(1 for event in events if _is_risky_action(event.action))
    repeated_action_count = max(0, total - len({event.action for event in events}))
    repeated_error_count = _repeated_error_count(events)
    unsafe_artifact_path_count = sum(
        1
        for event in events
        for path in event.artifact_paths
        if _is_unsafe_artifact_path(path)
    )
    role_mismatch_count = sum(
        1 for event in events if _role_mismatch(event, judge_input)
    )
    unknown_actions = sum(1 for event in events if event.action == "unknown_action")
    return {
        "total": total,
        "failure_count": failure_count,
        "failure_ratio": failure_count / max(total, 1),
        "policy_denied_count": policy_denied_count,
        "risky_action_count": risky_action_count,
        "repeated_action_count": repeated_action_count,
        "repeated_error_count": repeated_error_count,
        "unsafe_artifact_path_count": unsafe_artifact_path_count,
        "role_mismatch_count": role_mismatch_count,
        "unknown_actions": unknown_actions,
        "no_success": int(all(_is_failure_event(event) for event in events)),
    }


def _role_mismatch(event: NormalityJudgeEvent, judge_input: NormalityJudgeInput) -> bool:
    allowed_actions = _constraint_actions(judge_input.constraints, "allowed")
    forbidden_actions = _constraint_actions(judge_input.constraints, "forbidden")
    if event.action in forbidden_actions:
        return True
    if allowed_actions and event.action not in allowed_actions:
        return True
    role_text = f"{event.role} {judge_input.agent_roles.get(event.agent_id, '')}".lower()
    family = _action_family(event.action)
    if family in {"browser", "shell", "office"} and family not in role_text:
        return True
    return False


def _constraint_actions(constraints: list[str], kind: Literal["allowed", "forbidden"]) -> set[str]:
    actions: set[str] = set()
    for constraint in constraints:
        lower = constraint.lower()
        if kind == "allowed" and "allowed" not in lower:
            continue
        if kind == "forbidden" and "forbidden" not in lower:
            continue
        actions.update(re.findall(r"\b[a-z][a-z0-9_]+(?:_[a-z0-9]+)*\b", lower))
    stop_words = {
        "allowed",
        "allowed_actions",
        "allowed_action_names",
        "forbidden",
        "forbidden_actions",
        "forbidden_action_names",
        "actions",
        "action",
        "names",
        "only",
        "none",
    }
    return actions - stop_words


def _safe_input_payload(judge_input: NormalityJudgeInput, config: NormalityJudgeConfig) -> dict[str, Any]:
    redactions: set[str] = set()
    payload = judge_input.model_dump(mode="json")
    for key in ["task_summary", "expected_behavior", "environment_summary"]:
        safe, found = sanitize_judge_text(payload.get(key), config)
        payload[key] = safe
        redactions.update(found)
    payload["events"] = [_safe_event_payload(event, config, redactions) for event in judge_input.events[: config.max_events]]
    payload["redaction_notes"] = sorted(redactions)
    if not config.include_raw_outputs:
        payload["raw_outputs_included"] = False
    return payload


def _safe_event_payload(
    event: NormalityJudgeEvent,
    config: NormalityJudgeConfig,
    redactions: set[str],
) -> dict[str, Any]:
    payload = event.model_dump(mode="json")
    for key in ["params_summary", "result_summary", "policy_decision"]:
        safe, found = sanitize_judge_text(payload.get(key), config)
        payload[key] = safe
        redactions.update(found)
    safe_notes: list[str] = []
    for note in event.notes:
        safe, found = sanitize_judge_text(note, config)
        safe_notes.append(safe)
        redactions.update(found)
    payload["notes"] = safe_notes
    safe_paths: list[str] = []
    for path in event.artifact_paths:
        if _is_absolute_path(path):
            safe_paths.append("<absolute_path>")
            redactions.add("absolute_path")
        else:
            safe_paths.append(path)
    payload["artifact_paths"] = safe_paths
    return payload


def _redactions_for_input(judge_input: NormalityJudgeInput, config: NormalityJudgeConfig) -> set[str]:
    payload = _safe_input_payload(judge_input, config)
    return set(payload.get("redaction_notes", []))


def _redact_paths(value: str) -> tuple[str, list[str]]:
    redactions: list[str] = []
    patterns = [
        re.compile(r"\b[A-Za-z]:[\\/][^\s\"'<>|]+"),
        re.compile(r"\\\\[A-Za-z0-9_.-]+\\[^\s\"'<>|]+"),
        re.compile(r"(?<![A-Za-z0-9_.-])/(?:Users|home|root|tmp|var|etc|opt|mnt|private)/[^\s\"']+"),
    ]
    out = value
    for pattern in patterns:
        if pattern.search(out):
            redactions.append("absolute_path")
            out = pattern.sub("<absolute_path>", out)
    return out, sorted(set(redactions))


def _label_for_score(score: float, config: NormalityJudgeConfig) -> NormalityJudgeLabel:
    if score >= config.score_threshold_normal:
        return "normal"
    if score >= config.score_threshold_suspicious:
        return "suspicious"
    return "abnormal"


def _unique_findings(scores: dict[str, NormalityJudgeDimensionScore]) -> list[str]:
    out: list[str] = []
    for score in scores.values():
        out.extend(score.findings)
    return sorted(dict.fromkeys(out))


def _overall_findings(metrics: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if metrics["failure_count"] == 0 and metrics["policy_denied_count"] == 0:
        findings.append("coherent_successful_sequence")
    if metrics["policy_denied_count"]:
        findings.append("policy_denied_events_present")
    if metrics["role_mismatch_count"]:
        findings.append("role_inconsistent_actions_present")
    return findings


def _findings_for(dimension: str, metrics: dict[str, Any]) -> list[str]:
    findings: list[str] = []
    if dimension == "task_relevance" and metrics["unknown_actions"]:
        findings.append("unknown_actions_present")
    if dimension == "role_consistency" and metrics["role_mismatch_count"]:
        findings.append("role_inconsistent_actions_present")
    if dimension == "action_safety":
        if metrics["policy_denied_count"]:
            findings.append("policy_denied_events_present")
        if metrics["risky_action_count"]:
            findings.append("risky_actions_present")
    if dimension == "sequence_plausibility" and metrics["repeated_action_count"]:
        findings.append("repeated_actions_present")
    if dimension == "artifact_hygiene" and metrics["unsafe_artifact_path_count"]:
        findings.append("unsafe_artifact_paths_present")
    if dimension == "error_recovery" and metrics["repeated_error_count"]:
        findings.append("repeated_errors_present")
    if dimension == "error_recovery" and metrics["failure_count"]:
        findings.append("execution_errors_present")
    return findings


def _is_failure_event(event: NormalityJudgeEvent) -> bool:
    status = event.status.lower()
    if status in {"failure", "failed", "error", "rejected"}:
        return True
    return bool(event.error_code)


def _is_policy_denied(event: NormalityJudgeEvent) -> bool:
    text = " ".join(
        part
        for part in [event.policy_decision, event.error_code, event.status]
        if part
    ).lower()
    return "denied" in text or "policy_denied" in text


def _is_risky_action(action: str) -> bool:
    lower = action.lower()
    risky_tokens = ("shell", "command", "credential", "token", "secret", "password", "external")
    return any(token in lower for token in risky_tokens)


def _action_family(action: str) -> str:
    lower = action.lower()
    if lower.startswith("browser_") or "browser" in lower:
        return "browser"
    if lower.startswith("office_") or "docx" in lower or "xlsx" in lower or "pptx" in lower:
        return "office"
    if "shell" in lower or "command" in lower:
        return "shell"
    if lower.endswith("_file") or lower in {"read_file", "create_file", "append_file", "list_directory"}:
        return "file"
    return "unknown"


def _repeated_error_count(events: list[NormalityJudgeEvent]) -> int:
    codes = [event.error_code for event in events if event.error_code]
    return sum(count - 1 for count in Counter(codes).values() if count > 1)


def _is_unsafe_artifact_path(path: str) -> bool:
    return _is_absolute_path(path) or ".." in path.replace("\\", "/").split("/")


def _is_absolute_path(path: str) -> bool:
    return bool(
        re.match(r"^[A-Za-z]:[\\/]", path)
        or path.startswith("/")
        or path.startswith("\\\\")
    )


def _event_error_code(row: dict[str, Any], metadata: dict[str, Any]) -> str | None:
    for key in ("error_code", "error_type"):
        value = row.get(key)
        if isinstance(value, str) and value:
            return value
    if isinstance(metadata, dict):
        for key in ("error_code", "error_type"):
            value = metadata.get(key)
            if isinstance(value, str) and value:
                return value
        if metadata.get("validation_accepted") is False:
            return "validation_failed"
    return None


def _event_notes(metadata: dict[str, Any]) -> list[str]:
    notes: list[str] = []
    if not isinstance(metadata, dict):
        return notes
    for key in ("execution_attempted", "execution_success", "validation_accepted"):
        if key in metadata:
            notes.append(f"{key}={metadata[key]}")
    return notes


def _clamp01(value: float) -> float:
    return max(0.0, min(1.0, value))
