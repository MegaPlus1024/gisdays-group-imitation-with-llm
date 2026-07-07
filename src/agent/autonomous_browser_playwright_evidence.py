from __future__ import annotations

import json
import re
from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any
from urllib.parse import urlparse


EVIDENCE_SCHEMA_VERSION = "autonomous_browser_playwright_smoke_evidence_v1"
SMOKE_SUMMARY_SCHEMA_VERSION = "autonomous_browser_playwright_smoke_summary_v1"
SUITE_SUMMARY_SCHEMA_VERSION = "autonomous_browser_playwright_suite_summary_v1"
SUCCESS_EVIDENCE_LEVEL = "guarded_real_browser_smoke_succeeded"
FAILED_EVIDENCE_LEVEL = "guarded_real_browser_smoke_not_succeeded"
SUITE_SUCCESS_EVIDENCE_LEVEL = "guarded_real_browser_suite_succeeded"
SUITE_FAILED_EVIDENCE_LEVEL = "guarded_real_browser_suite_not_succeeded"
REQUIRED_LOGICAL_URLS = (
    "https://local.intranet/tickets/1",
    "https://docs.local/docs/policy",
)
LIMITATIONS = (
    "single guarded smoke scenario",
    "headless Chromium only",
    "local fixture server only",
    "not production browser automation",
    "no external network",
    "no mail/git actions",
    "no LLM judge",
)


class PlaywrightSmokeEvidenceError(ValueError):
    """Raised when Playwright smoke evidence is malformed or unsafe."""


@dataclass(frozen=True)
class PlaywrightSmokeEvidence:
    schema_version: str
    source_schema_version: str
    operator_id: str
    status: str
    passed: bool
    actions_attempted: int
    actions_succeeded: int
    actions_failed: int
    expected_results_total: int
    expected_results_passed: int
    expected_results_failed: int
    logical_urls_visited: tuple[str, ...]
    served_url_policy: dict[str, Any]
    browser_backend: dict[str, Any]
    scenario_scope: dict[str, Any]
    evidence_level: str
    limitations: tuple[str, ...]
    scenario_count: int | None = None
    scenarios_attempted: int | None = None
    scenarios_succeeded: int | None = None
    scenarios_failed: int | None = None
    required_actions: tuple[str, ...] = ()
    required_actions_covered: tuple[str, ...] = ()
    required_actions_missing: tuple[str, ...] = ()
    overall_action_coverage_ratio: float | None = None

    def to_report(self) -> dict[str, Any]:
        report = {
            "schema_version": self.schema_version,
            "source_schema_version": self.source_schema_version,
            "operator_id": self.operator_id,
            "status": self.status,
            "passed": self.passed,
            "actions_attempted": self.actions_attempted,
            "actions_succeeded": self.actions_succeeded,
            "actions_failed": self.actions_failed,
            "expected_results_total": self.expected_results_total,
            "expected_results_passed": self.expected_results_passed,
            "expected_results_failed": self.expected_results_failed,
            "logical_urls_visited": list(self.logical_urls_visited),
            "served_url_policy": self.served_url_policy,
            "browser_backend": self.browser_backend,
            "scenario_scope": self.scenario_scope,
            "evidence_level": self.evidence_level,
            "limitations": list(self.limitations),
        }
        if self.scenario_count is not None:
            report.update(
                {
                    "scenario_count": self.scenario_count,
                    "scenarios_attempted": self.scenarios_attempted,
                    "scenarios_succeeded": self.scenarios_succeeded,
                    "scenarios_failed": self.scenarios_failed,
                    "required_actions": list(self.required_actions),
                    "required_actions_covered": list(self.required_actions_covered),
                    "required_actions_missing": list(self.required_actions_missing),
                    "overall_action_coverage_ratio": self.overall_action_coverage_ratio,
                }
            )
        return report


def validate_playwright_smoke_summary(summary: Mapping[str, Any]) -> PlaywrightSmokeEvidence:
    if not isinstance(summary, Mapping):
        raise PlaywrightSmokeEvidenceError("summary must be a mapping.")
    _reject_unsafe_strings(summary)

    source_schema_version = _string(summary.get("schema_version"), "schema_version")
    if source_schema_version == SMOKE_SUMMARY_SCHEMA_VERSION:
        return _validate_smoke_summary(summary, source_schema_version)
    if source_schema_version == SUITE_SUMMARY_SCHEMA_VERSION:
        return _validate_suite_summary(summary, source_schema_version)
    raise PlaywrightSmokeEvidenceError("unexpected Playwright summary schema_version.")


def _validate_smoke_summary(summary: Mapping[str, Any], source_schema_version: str) -> PlaywrightSmokeEvidence:
    actions_attempted = _int(summary.get("actions_attempted"), "actions_attempted")
    actions_succeeded = _int(summary.get("actions_succeeded"), "actions_succeeded")
    actions_failed = _int(summary.get("actions_failed"), "actions_failed")
    expected_results = _list(summary.get("expected_results"), "expected_results")
    expected_results_passed = sum(1 for item in expected_results if isinstance(item, Mapping) and item.get("passed") is True)
    expected_results_failed = len(expected_results) - expected_results_passed
    logical_urls = tuple(_string_list(summary.get("logical_urls_visited"), "logical_urls_visited"))
    served_urls = tuple(_served_urls(summary))
    _validate_served_urls(served_urls)

    status = _string(summary.get("status"), "status")
    error_code = summary.get("error_code")
    no_runtime_execution = summary.get("no_runtime_execution")
    passed = (
        status == "succeeded"
        and error_code is None
        and no_runtime_execution is False
        and actions_attempted == 6
        and actions_succeeded == 6
        and actions_failed == 0
        and len(expected_results) == 6
        and expected_results_passed == len(expected_results)
        and set(REQUIRED_LOGICAL_URLS).issubset(set(logical_urls))
        and bool(served_urls)
    )

    return PlaywrightSmokeEvidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        source_schema_version=source_schema_version,
        operator_id=_string(summary.get("operator_id"), "operator_id"),
        status=status,
        passed=passed,
        actions_attempted=actions_attempted,
        actions_succeeded=actions_succeeded,
        actions_failed=actions_failed,
        expected_results_total=len(expected_results),
        expected_results_passed=expected_results_passed,
        expected_results_failed=expected_results_failed,
        logical_urls_visited=logical_urls,
        served_url_policy={
            "loopback_only": True,
            "served_urls_checked": len(served_urls),
            "served_url_prefix": "http://127.0.0.1:8765/",
        },
        browser_backend=dict(_mapping(summary.get("browser_backend"), "browser_backend")),
        scenario_scope=dict(_mapping(summary.get("scenario_scope"), "scenario_scope")),
        evidence_level=SUCCESS_EVIDENCE_LEVEL if passed else FAILED_EVIDENCE_LEVEL,
        limitations=LIMITATIONS,
    )


def _validate_suite_summary(summary: Mapping[str, Any], source_schema_version: str) -> PlaywrightSmokeEvidence:
    actions_attempted = _int(summary.get("actions_attempted"), "actions_attempted")
    actions_succeeded = _int(summary.get("actions_succeeded"), "actions_succeeded")
    actions_failed = _int(summary.get("actions_failed"), "actions_failed")
    expected_results_total = _int(summary.get("expected_results_total"), "expected_results_total")
    expected_results_passed = _int(summary.get("expected_results_passed"), "expected_results_passed")
    expected_results_failed = _int(summary.get("expected_results_failed"), "expected_results_failed")
    logical_urls = tuple(_string_list(summary.get("logical_urls_visited"), "logical_urls_visited"))
    served_urls = tuple(_served_urls(summary))
    _validate_served_urls(served_urls)
    required_actions = tuple(_string_list(summary.get("required_actions"), "required_actions"))
    required_actions_covered = tuple(_string_list(summary.get("required_actions_covered"), "required_actions_covered"))
    required_actions_missing = tuple(_string_list(summary.get("required_actions_missing"), "required_actions_missing"))
    scenario_count = _int(summary.get("scenario_count"), "scenario_count")
    scenarios_attempted = _int(summary.get("scenarios_attempted"), "scenarios_attempted")
    scenarios_succeeded = _int(summary.get("scenarios_succeeded"), "scenarios_succeeded")
    scenarios_failed = _int(summary.get("scenarios_failed"), "scenarios_failed")
    status = _string(summary.get("status"), "status")
    error_code = summary.get("error_code")
    no_runtime_execution = summary.get("no_runtime_execution")
    passed = (
        status == "succeeded"
        and error_code is None
        and no_runtime_execution is False
        and scenario_count >= 1
        and scenarios_attempted == scenario_count
        and scenarios_succeeded == scenario_count
        and scenarios_failed == 0
        and actions_attempted > 0
        and actions_succeeded == actions_attempted
        and actions_failed == 0
        and expected_results_total > 0
        and expected_results_passed == expected_results_total
        and expected_results_failed == 0
        and bool(required_actions)
        and set(required_actions).issubset(set(required_actions_covered))
        and not required_actions_missing
        and bool(served_urls)
    )

    return PlaywrightSmokeEvidence(
        schema_version=EVIDENCE_SCHEMA_VERSION,
        source_schema_version=source_schema_version,
        operator_id=_string(summary.get("operator_id"), "operator_id"),
        status=status,
        passed=passed,
        actions_attempted=actions_attempted,
        actions_succeeded=actions_succeeded,
        actions_failed=actions_failed,
        expected_results_total=expected_results_total,
        expected_results_passed=expected_results_passed,
        expected_results_failed=expected_results_failed,
        logical_urls_visited=logical_urls,
        served_url_policy={
            "loopback_only": True,
            "served_urls_checked": len(served_urls),
            "served_url_prefix": "http://127.0.0.1:8765/",
        },
        browser_backend=dict(_mapping(summary.get("browser_backend"), "browser_backend")),
        scenario_scope={"mode": "suite"},
        evidence_level=SUITE_SUCCESS_EVIDENCE_LEVEL if passed else SUITE_FAILED_EVIDENCE_LEVEL,
        limitations=LIMITATIONS,
        scenario_count=scenario_count,
        scenarios_attempted=scenarios_attempted,
        scenarios_succeeded=scenarios_succeeded,
        scenarios_failed=scenarios_failed,
        required_actions=required_actions,
        required_actions_covered=required_actions_covered,
        required_actions_missing=required_actions_missing,
        overall_action_coverage_ratio=_number(summary.get("overall_action_coverage_ratio"), "overall_action_coverage_ratio"),
    )


def build_playwright_smoke_evidence_report(summary: Mapping[str, Any]) -> dict[str, Any]:
    return validate_playwright_smoke_summary(summary).to_report()


def render_playwright_smoke_evidence_markdown(report: Mapping[str, Any]) -> str:
    logical_urls = _string_list(report.get("logical_urls_visited"), "logical_urls_visited")
    limitations = _string_list(report.get("limitations"), "limitations")
    browser_backend = _mapping(report.get("browser_backend"), "browser_backend")
    scenario_scope = _mapping(report.get("scenario_scope"), "scenario_scope")
    served_url_policy = _mapping(report.get("served_url_policy"), "served_url_policy")
    lines = [
        "# Evidence: guarded Playwright browser smoke run",
        "",
        "## Summary",
        "",
        f"- Status: {report.get('status')}",
        "- Guarded real browser path: executed by operator",
        (
            "- Browser backend: "
            f"{browser_backend.get('browser_name')} via {browser_backend.get('type')}, "
            f"headless={browser_backend.get('headless')}"
        ),
        (
            "- Actions attempted/succeeded/failed: "
            f"{report.get('actions_attempted')}/{report.get('actions_succeeded')}/{report.get('actions_failed')}"
        ),
        f"- Expected results: {report.get('expected_results_passed')}/{report.get('expected_results_total')} passed",
        f"- Scenario: {scenario_scope.get('scenario_id')}",
        "- Fixture server: loopback-only local fixture server",
        f"- Evidence level: {report.get('evidence_level')}",
        "",
        "## What was verified",
        "",
        "- Playwright/Chromium launched through the guarded operator path.",
        "- Local fixture server served browser pages through loopback URLs.",
        "- Logical URLs mapped to loopback fixture files.",
        "- Browser actions opened pages, extracted text, searched content and prepared snapshots.",
        "- Expected text markers were found.",
        "- No external network was required.",
    ]
    if report.get("scenario_count") is not None:
        lines.extend(
            [
                "- Suite mode attempted bounded fixture-backed scenarios.",
                (
                    "- Required browser actions covered: "
                    f"{len(report.get('required_actions_covered') or [])}/{len(report.get('required_actions') or [])}"
                ),
            ]
        )
        missing_actions = report.get("required_actions_missing") or []
        if missing_actions:
            lines.append("- Required browser actions missing: " + ", ".join(f"`{item}`" for item in missing_actions))
        lines.extend(
            [
                "",
                "## Suite coverage",
                "",
                (
                    "- Scenarios attempted/succeeded/failed: "
                    f"{report.get('scenarios_attempted')}/{report.get('scenarios_succeeded')}/{report.get('scenarios_failed')}"
                ),
                f"- Overall action coverage ratio: {report.get('overall_action_coverage_ratio')}",
            ]
        )
    lines.extend(
        [
            "",
            "## Evidence details",
            "",
            f"- Source schema: `{report.get('source_schema_version')}`",
            f"- Operator id: `{report.get('operator_id')}`",
            f"- Passed: `{str(report.get('passed')).lower()}`",
            f"- Served URL policy: loopback_only={served_url_policy.get('loopback_only')}, checked={served_url_policy.get('served_urls_checked')}",
            "- Logical URLs visited:",
        ]
    )
    lines.extend(f"  - `{url}`" for url in logical_urls)
    lines.extend(
        [
            "",
            "## Limitations",
            "",
        ]
    )
    lines.extend(f"- {item}" for item in limitations)
    lines.append("")
    return "\n".join(lines)


def _served_urls(summary: Mapping[str, Any]) -> list[str]:
    urls: list[str] = []
    _collect_served_urls(summary, urls)
    return urls


def _collect_served_urls(value: Any, urls: list[str]) -> None:
    if isinstance(value, Mapping):
        served_url = value.get("served_url")
        if isinstance(served_url, str):
            urls.append(served_url)
        for child in value.values():
            _collect_served_urls(child, urls)
        return
    if isinstance(value, list):
        for child in value:
            _collect_served_urls(child, urls)


def _validate_served_urls(urls: tuple[str, ...]) -> None:
    for url in urls:
        parsed = urlparse(url)
        if parsed.scheme != "http" or parsed.hostname not in {"127.0.0.1", "localhost"}:
            raise PlaywrightSmokeEvidenceError("served URLs must be loopback-only.")
        if parsed.hostname == "127.0.0.1" and parsed.port != 8765:
            raise PlaywrightSmokeEvidenceError("served URL port must match the smoke fixture server.")


def _reject_unsafe_strings(value: Any) -> None:
    if isinstance(value, Mapping):
        for child in value.values():
            _reject_unsafe_strings(child)
        return
    if isinstance(value, list):
        for child in value:
            _reject_unsafe_strings(child)
        return
    if not isinstance(value, str):
        return
    if _looks_like_secret(value):
        raise PlaywrightSmokeEvidenceError("summary contains a secret-like value.")
    if value.startswith(("http://", "https://")):
        return
    if re.search(r"(?<![A-Za-z0-9])[A-Za-z]:[\\/]", value):
        raise PlaywrightSmokeEvidenceError("summary contains a local absolute path.")
    if re.search(r"(?<!\w)/(?:Users|home|tmp|var|etc|mnt|private)/", value):
        raise PlaywrightSmokeEvidenceError("summary contains a local absolute path.")


def _looks_like_secret(value: str) -> bool:
    patterns = (
        r"sk-[A-Za-z0-9_-]+",
        r"OPENAI_API_KEY\s*=",
        r"DEEPSEEK_API_KEY\s*=",
        r"Authorization\s*:",
        r"api_key[^A-Za-z0-9_-]+[A-Za-z0-9_-]{20,}",
    )
    return any(re.search(pattern, value, flags=re.IGNORECASE) for pattern in patterns)


def _mapping(value: Any, label: str) -> Mapping[str, Any]:
    if not isinstance(value, Mapping):
        raise PlaywrightSmokeEvidenceError(f"{label} must be a mapping.")
    return value


def _list(value: Any, label: str) -> list[Any]:
    if not isinstance(value, list):
        raise PlaywrightSmokeEvidenceError(f"{label} must be a list.")
    return value


def _string_list(value: Any, label: str) -> list[str]:
    items = _list(value, label)
    out: list[str] = []
    for item in items:
        if not isinstance(item, str):
            raise PlaywrightSmokeEvidenceError(f"{label} must contain strings.")
        out.append(item)
    return out


def _string(value: Any, label: str) -> str:
    if not isinstance(value, str) or not value.strip():
        raise PlaywrightSmokeEvidenceError(f"{label} must be a non-empty string.")
    return value


def _int(value: Any, label: str) -> int:
    if not isinstance(value, int):
        raise PlaywrightSmokeEvidenceError(f"{label} must be an integer.")
    return value


def _number(value: Any, label: str) -> float:
    if not isinstance(value, int | float):
        raise PlaywrightSmokeEvidenceError(f"{label} must be a number.")
    return float(value)


def report_to_json(report: Mapping[str, Any]) -> str:
    return json.dumps(dict(report), ensure_ascii=True, indent=2, sort_keys=True)
