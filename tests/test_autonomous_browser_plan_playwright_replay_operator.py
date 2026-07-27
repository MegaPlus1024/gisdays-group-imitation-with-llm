from __future__ import annotations

import builtins
import json
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_plan_validation import validate_autonomous_browser_plan
from src.agent.autonomous_browser_plan_playwright_replay_operator import (
    CONFIG_SCHEMA_VERSION,
    REQUIRED_ALLOW_FLAG,
    REQUIRED_CONFIRM_VALUE,
    SUMMARY_SCHEMA_VERSION,
    load_autonomous_browser_plan_playwright_replay_operator_config,
    run_autonomous_browser_plan_playwright_replay_operator,
)
from src.agent.autonomous_browser_playwright_execution import PlaywrightExecutionResult, RealPlaywrightBackend, _click_locator_from_page


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_plan_playwright_replay_operator.example.json"
PLAN_SOURCE_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_plan.example.json"
DEFAULT_REPLAY_PLAN_PATH = "artifacts/autonomous_runtime_summaries/model_plan_playwright_replay_packet/playwright_replay_plan.json"
EXAMPLE_REPLAY_PLAN_PATH = "tests/fixtures/autonomous_browser_plan_playwright_replay/operator/replay_plan.json"
REPLAY_FIXTURE_ROOT = PROJECT_ROOT / "tests" / "fixtures" / "autonomous_browser_plan_playwright_replay"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_plan_playwright_replay_operator_tests"
EXAMPLE_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_plan_playwright_replay_operator"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_plan_playwright_replay_operator.py"


def _base_plan() -> dict[str, Any]:
    return json.loads(PLAN_SOURCE_PATH.read_text(encoding="utf-8"))


def _resolve_repo_fixture(relative_path: str) -> Path:
    path = Path(relative_path)
    assert not path.is_absolute()
    assert "artifacts" not in path.parts
    resolved = (PROJECT_ROOT / path).resolve()
    assert resolved.is_relative_to(PROJECT_ROOT.resolve())
    assert resolved.is_relative_to(REPLAY_FIXTURE_ROOT.resolve())
    assert resolved.is_file()
    return resolved


def _write_replay_plan(repo_root: Path, plan: dict[str, Any], *, relative_path: str = DEFAULT_REPLAY_PLAN_PATH) -> Path:
    replay_plan = {
        "schema_version": "autonomous_browser_plan_playwright_replay_packet_v1",
        "packet_id": "browser_plan_playwright_replay_packet_v1",
        "source_output_path": "artifacts/autonomous_runtime_summaries/local_planner_repeated_trials_packet/trial_01/raw_planner_output.txt",
        "extracted_plan_id": plan["plan_id"],
        "actions_total": len(plan["actions"]),
        "future_operator_guard_required": True,
        "model_execution": False,
        "real_browser_execution": False,
        "no_runtime_execution": True,
        "local_fixture_only_scope": True,
        "allowed_browser_hosts": [
            "local.intranet",
            "local-intranet.test",
            "docs.local",
            "portal.local",
        ],
        "no_external_urls": True,
        "no_credentials_or_secrets": True,
        "no_general_browsing": True,
        "normalized_plan_path": relative_path.replace("playwright_replay_plan.json", "normalized_plan.json"),
        "normalized_plan": plan,
        "limitations": ["test fixture"],
    }
    output_path = repo_root / relative_path
    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(replay_plan, ensure_ascii=False, indent=2), encoding="utf-8")
    return output_path


def _copy_fixture_site(repo_root: Path) -> Path:
    source = PROJECT_ROOT / "tests" / "fixtures" / "local_intranet" / "office_site_v1"
    target = repo_root / "tests" / "fixtures" / "local_intranet" / "office_site_v1"
    shutil.copytree(source, target, dirs_exist_ok=True)
    return target


def _playwright_supported_plan() -> dict[str, Any]:
    plan = _base_plan()
    plan["max_actions"] = 4
    plan["actions"] = [
        {
            "step_id": "open_home",
            "action_name": "browser_open_url",
            "parameters": {"url": "https://local.intranet/"},
            "expected_text": "Office Intranet",
        },
        {
            "step_id": "click_policy",
            "action_name": "browser_click",
            "parameters": {
                "url": "https://local.intranet/docs/policy",
                "target_text": "Workspace policy",
            },
            "expected_text": "Allowed activity",
        },
        {
            "step_id": "extract_policy",
            "action_name": "browser_extract_text",
            "parameters": {"url": "https://docs.local/docs/policy"},
            "expected_text": "Allowed activity",
        },
        {
            "step_id": "snapshot_policy",
            "action_name": "browser_snapshot",
            "parameters": {"url": "https://docs.local/docs/policy"},
            "expected_text": "Allowed activity",
        },
    ]
    return plan


def _fake_playwright_executor(
    replay_result: dict[str, Any],
    calls: list[tuple[Mapping[str, Any], Any, Path]],
) -> Any:
    def executor(normalized_plan: Mapping[str, Any], config: Any, repo_root: Path) -> dict[str, Any]:
        calls.append((normalized_plan, config, repo_root))
        return dict(replay_result)

    return executor


class _FakeClickLocator:
    def __init__(self, page: "_FakeClickPage", kind: str, *, count: int, click_handler: Any | None = None) -> None:
        self._page = page
        self._kind = kind
        self._count = count
        self._click_handler = click_handler

    def count(self) -> int:
        return self._count

    @property
    def first(self) -> "_FakeClickLocator":
        return self

    def filter(self, *, has_text: str) -> "_FakeClickLocator":
        if self._count <= 0 or has_text != self._page.target_text:
            return _FakeClickLocator(self._page, f"{self._kind}.filtered", count=0)
        return self

    def click(self, timeout: int) -> None:
        del timeout
        self._page.click_log.append(self._kind)
        if self._click_handler is not None:
            self._click_handler()


class _FakeClickPage:
    def __init__(
        self,
        *,
        url: str,
        title: str,
        body_text: str,
        target_text: str,
        role_link_count: int = 0,
        role_button_count: int = 0,
        anchor_count: int = 0,
        button_count: int = 0,
        text_count: int = 0,
        post_click_url: str | None = None,
        post_click_title: str | None = None,
        post_click_body_text: str | None = None,
    ) -> None:
        self.url = url
        self._title = title
        self._body_text = body_text
        self.target_text = target_text
        self.role_link_count = role_link_count
        self.role_button_count = role_button_count
        self.anchor_count = anchor_count
        self.button_count = button_count
        self.text_count = text_count
        self.post_click_url = post_click_url or url
        self.post_click_title = post_click_title or title
        self.post_click_body_text = post_click_body_text or body_text
        self.calls: list[tuple[Any, ...]] = []
        self.click_log: list[str] = []

    def get_by_role(self, role: str, *, name: str, exact: bool = True) -> _FakeClickLocator:
        self.calls.append(("get_by_role", role, name, exact))
        if name != self.target_text:
            return _FakeClickLocator(self, f"role:{role}:{name}", count=0)
        count = self.role_link_count if role == "link" else self.role_button_count if role == "button" else 0
        handler = self._apply_click if count > 0 and role in {"link", "button"} else None
        return _FakeClickLocator(self, f"role:{role}:{name}", count=count, click_handler=handler)

    def locator(self, selector: str) -> _FakeClickLocator:
        self.calls.append(("locator", selector))
        if selector == "a":
            return _FakeClickLocator(self, selector, count=self.anchor_count, click_handler=self._apply_click if self.anchor_count > 0 else None)
        if selector == "button":
            return _FakeClickLocator(self, selector, count=self.button_count, click_handler=self._apply_click if self.button_count > 0 else None)
        return _FakeClickLocator(self, selector, count=1, click_handler=self._apply_click)

    def get_by_text(self, text: str, exact: bool = True) -> _FakeClickLocator:
        self.calls.append(("get_by_text", text, exact))
        count = self.text_count if text == self.target_text else 0
        handler = self._apply_click if count > 0 else None
        return _FakeClickLocator(self, f"text:{text}", count=count, click_handler=handler)

    def wait_for_load_state(self, state: str, timeout: int) -> None:
        del timeout
        self.calls.append(("wait_for_load_state", state))

    def inner_text(self, selector: str, timeout: int) -> str:
        del selector, timeout
        self.calls.append(("inner_text", "body"))
        return self._body_text

    def title(self) -> str:
        self.calls.append(("title",))
        return self._title

    def _apply_click(self) -> None:
        self.url = self.post_click_url
        self._title = self.post_click_title
        self._body_text = self.post_click_body_text


def _write_config(
    repo_root: Path,
    *,
    replay_backend: str = "fixture",
    replay_plan_path: str = DEFAULT_REPLAY_PLAN_PATH,
    output_dir: str = DEFAULT_OUTPUT_DIR,
    allowed_hosts: list[str] | None = None,
    fixture_scope: str = "local_only",
    headless: bool = True,
    timeout_ms: int = 30_000,
) -> Path:
    payload = {
        "schema_version": CONFIG_SCHEMA_VERSION,
        "replay_backend": replay_backend,
        "replay_plan_path": replay_plan_path,
        "output_dir": output_dir,
        "allowed_hosts": allowed_hosts
        or ["local.intranet", "local-intranet.test", "docs.local", "portal.local"],
        "fixture_scope": fixture_scope,
        "headless": headless,
        "timeout_ms": timeout_ms,
        "limitations": ["test fixture"],
    }
    path = repo_root / "replay_operator_config.json"
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    return path


def test_example_config_loads_with_relative_paths() -> None:
    config = load_autonomous_browser_plan_playwright_replay_operator_config(EXAMPLE_CONFIG_PATH)

    assert config.schema_version == CONFIG_SCHEMA_VERSION
    assert config.replay_backend == "fixture"
    assert config.replay_plan_path == EXAMPLE_REPLAY_PLAN_PATH
    assert config.output_dir == EXAMPLE_OUTPUT_DIR
    assert config.fixture_scope == "local_only"
    assert config.headless is True
    assert config.timeout_ms == 30_000
    assert config.allowed_hosts == ("local.intranet", "local-intranet.test", "docs.local", "portal.local")
    assert all(not Path(path).is_absolute() for path in (config.replay_plan_path, config.output_dir))
    replay_plan_path = _resolve_repo_fixture(config.replay_plan_path)
    replay_plan = json.loads(replay_plan_path.read_text(encoding="utf-8"))
    assert isinstance(replay_plan, dict)
    assert validate_autonomous_browser_plan(replay_plan)["status"] == "accepted"


def test_default_run_refuses_without_guards(tmp_path: Path) -> None:
    config_path = _write_config(tmp_path)

    summary = run_autonomous_browser_plan_playwright_replay_operator(config_path, repo_root=tmp_path)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "refused"
    assert summary["error_code"] == "allow_real_browser_required"
    assert summary["guard_status"] == "refused"
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["replay_backend"] == "fixture"
    assert summary["replay_plan_path"] == DEFAULT_REPLAY_PLAN_PATH
    assert summary["plan_id"] is None
    assert summary["actions_total"] == 0
    assert summary["actions_attempted"] == 0
    assert summary["actions_succeeded"] == 0
    assert summary["actions_failed"] == 0
    assert summary["expected_results_total"] == 0
    assert summary["output_files"] == [f"{DEFAULT_OUTPUT_DIR}/autonomous_browser_plan_playwright_replay_operator_summary.json"]
    assert (tmp_path / DEFAULT_OUTPUT_DIR / "autonomous_browser_plan_playwright_replay_operator_summary.json").exists()


@pytest.mark.parametrize(
    ("allow_real_browser", "confirm_real_browser"),
    [
        (True, None),
        (False, REQUIRED_CONFIRM_VALUE),
    ],
)
def test_one_guard_only_refuses(tmp_path: Path, allow_real_browser: bool, confirm_real_browser: str | None) -> None:
    config_path = _write_config(tmp_path)

    summary = run_autonomous_browser_plan_playwright_replay_operator(
        config_path,
        repo_root=tmp_path,
        allow_real_browser=allow_real_browser,
        confirm_real_browser=confirm_real_browser,
    )

    assert summary["status"] == "refused"
    assert summary["error_code"] == "allow_real_browser_required"
    assert summary["guard_status"] == "refused"
    assert summary["no_runtime_execution"] is True
    assert summary["real_browser_execution"] is False
    assert summary["replay_backend"] == "fixture"


def test_dry_run_succeeds_without_browser(tmp_path: Path) -> None:
    plan = _base_plan()
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path)

    summary = run_autonomous_browser_plan_playwright_replay_operator(config_path, repo_root=tmp_path, dry_run=True)
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["status"] == "succeeded"
    assert summary["error_code"] is None
    assert summary["guard_status"] == "dry_run"
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["replay_backend"] == "fixture"
    assert summary["fixture_replay_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["real_network_traffic"] is False
    assert summary["plan_id"] == "browser_policy_research_plan_v1"
    assert summary["actions_total"] == 3
    assert summary["actions_attempted"] == 0
    assert summary["actions_succeeded"] == 0
    assert summary["actions_failed"] == 0
    assert summary["expected_results_total"] == 3
    assert summary["expected_results_passed"] == 0
    assert summary["expected_results_failed"] == 0
    assert summary["output_files"] == [f"{DEFAULT_OUTPUT_DIR}/autonomous_browser_plan_playwright_replay_operator_summary.json"]
    assert str(tmp_path) not in encoded
    assert "C:\\" not in encoded
    assert "supersecret" not in encoded
    assert (tmp_path / DEFAULT_OUTPUT_DIR / "autonomous_browser_plan_playwright_replay_operator_summary.json").exists()


def test_backend_playwright_phase11_plan_accepts_click_and_snapshot_without_playwright_import(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _playwright_supported_plan()
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path, replay_backend="playwright")
    calls: list[tuple[str, str, dict[str, Any]]] = []

    class FakeServer:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        def __enter__(self) -> "FakeServer":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            del exc_type, exc, tb

        def to_summary(self) -> dict[str, Any]:
            return {"base_url": "http://127.0.0.1:8765"}

    class FakeMapper:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        def map_logical_url(self, logical_url: str) -> str:
            return f"http://127.0.0.1:8765/{logical_url.split('://', 1)[-1].split('/', 1)[-1]}"

    class FakeBackend:
        def __init__(self, *args: Any, **kwargs: Any) -> None:
            del args, kwargs

        def __enter__(self) -> "FakeBackend":
            return self

        def __exit__(self, exc_type: Any, exc: Any, tb: Any) -> None:
            del exc_type, exc, tb

        def run_action(
            self,
            action_name: str,
            served_url: str,
            *,
            logical_url: str = "",
            expected_text: str | None = None,
            parameters: Mapping[str, Any] | None = None,
        ) -> PlaywrightExecutionResult:
            calls.append((action_name, served_url, dict(parameters or {})))
            return PlaywrightExecutionResult(
                action_name=action_name,
                logical_url=logical_url,
                served_url=served_url,
                success=True,
                text_preview=expected_text or f"fake {action_name} text",
                artifact_ref="playwright_snapshot_placeholder" if action_name == "browser_snapshot" else None,
                diagnostics={"fake_backend": True},
            )

    monkeypatch.setattr("src.agent.autonomous_browser_plan_playwright_replay_operator.LocalFixtureHttpServer", FakeServer)
    monkeypatch.setattr("src.agent.autonomous_browser_plan_playwright_replay_operator.FixtureUrlMapper", FakeMapper)
    monkeypatch.setattr("src.agent.autonomous_browser_plan_playwright_replay_operator.RealPlaywrightBackend", FakeBackend)

    summary = run_autonomous_browser_plan_playwright_replay_operator(
        config_path,
        repo_root=tmp_path,
        allow_real_browser=True,
        confirm_real_browser=REQUIRED_CONFIRM_VALUE,
        replay_backend="playwright",
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["status"] == "succeeded"
    assert summary["error_code"] is None
    assert summary["guard_status"] == "guarded_replay"
    assert summary["no_runtime_execution"] is False
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is True
    assert summary["replay_backend"] == "playwright"
    assert summary["fixture_replay_execution"] is False
    assert summary["playwright_execution"] is True
    assert summary["browser_opened"] is True
    assert summary["real_network_traffic"] is False
    assert summary["actions_total"] == 4
    assert summary["actions_attempted"] == 4
    assert summary["actions_succeeded"] == 4
    assert summary["actions_failed"] == 0
    assert summary["expected_results_total"] == 4
    assert summary["expected_results_passed"] == 4
    assert summary["expected_results_failed"] == 0
    assert [call[0] for call in calls] == [
        "browser_open_url",
        "browser_click",
        "browser_extract_text",
        "browser_snapshot",
    ]
    assert "supersecret" not in encoded
    assert str(tmp_path) not in encoded


def test_invalid_external_host_is_rejected(tmp_path: Path) -> None:
    plan = _base_plan()
    plan["actions"][0]["parameters"]["url"] = "https://example.com/"
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path)

    summary = run_autonomous_browser_plan_playwright_replay_operator(config_path, repo_root=tmp_path, dry_run=True)

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "external_url_not_allowed"
    assert summary["guard_status"] == "dry_run"
    assert summary["no_runtime_execution"] is True
    assert summary["real_browser_execution"] is False


def test_unsupported_action_is_rejected(tmp_path: Path) -> None:
    plan = _base_plan()
    plan["actions"][0]["action_name"] = "browser_not_real"
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path)

    summary = run_autonomous_browser_plan_playwright_replay_operator(config_path, repo_root=tmp_path, dry_run=True)

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "unknown_browser_action"
    assert summary["guard_status"] == "dry_run"
    assert summary["no_runtime_execution"] is True


def test_secret_like_values_are_not_leaked(tmp_path: Path) -> None:
    plan = _base_plan()
    plan["actions"][0]["parameters"]["url"] = "https://user:supersecret@local.intranet/"
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path)

    summary = run_autonomous_browser_plan_playwright_replay_operator(config_path, repo_root=tmp_path, dry_run=True)
    payload = json.dumps(summary, ensure_ascii=False)

    assert summary["status"] == "rejected"
    assert "supersecret" not in payload
    assert "user" not in payload
    assert str(tmp_path) not in payload


def test_backend_playwright_dry_run_succeeds_without_playwright_import(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plan = _playwright_supported_plan()
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path, replay_backend="playwright")
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = run_autonomous_browser_plan_playwright_replay_operator(config_path, repo_root=tmp_path, dry_run=True)
    payload = json.dumps(summary, ensure_ascii=False)

    assert summary["status"] == "succeeded"
    assert summary["guard_status"] == "dry_run"
    assert summary["replay_backend"] == "playwright"
    assert summary["no_runtime_execution"] is True
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["fixture_replay_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["real_network_traffic"] is False
    assert "supersecret" not in payload
    assert str(tmp_path) not in payload


def test_backend_playwright_refuses_without_guards(tmp_path: Path) -> None:
    plan = _playwright_supported_plan()
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path, replay_backend="playwright")

    summary = run_autonomous_browser_plan_playwright_replay_operator(config_path, repo_root=tmp_path)

    assert summary["status"] == "refused"
    assert summary["error_code"] == "allow_real_browser_required"
    assert summary["guard_status"] == "refused"
    assert summary["no_runtime_execution"] is True
    assert summary["replay_backend"] == "playwright"
    assert summary["fixture_replay_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["real_browser_execution"] is False


@pytest.mark.parametrize(
    ("allow_real_browser", "confirm_real_browser"),
    [
        (True, None),
        (False, REQUIRED_CONFIRM_VALUE),
    ],
)
def test_backend_playwright_one_guard_only_refuses(
    tmp_path: Path,
    allow_real_browser: bool,
    confirm_real_browser: str | None,
) -> None:
    plan = _playwright_supported_plan()
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path, replay_backend="playwright")

    summary = run_autonomous_browser_plan_playwright_replay_operator(
        config_path,
        repo_root=tmp_path,
        allow_real_browser=allow_real_browser,
        confirm_real_browser=confirm_real_browser,
    )

    assert summary["status"] == "refused"
    assert summary["error_code"] == "allow_real_browser_required"
    assert summary["guard_status"] == "refused"
    assert summary["no_runtime_execution"] is True
    assert summary["replay_backend"] == "playwright"
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["real_browser_execution"] is False


def test_unknown_backend_is_rejected_safely(tmp_path: Path) -> None:
    plan = _base_plan()
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path, replay_backend="unknown")

    summary = run_autonomous_browser_plan_playwright_replay_operator(config_path, repo_root=tmp_path, dry_run=True)
    payload = json.dumps(summary, ensure_ascii=False)

    assert summary["status"] == "failed"
    assert summary["error_code"] == "unknown_replay_backend"
    assert summary["guard_status"] == "config_validation_failed"
    assert summary["no_runtime_execution"] is True
    assert "unknown" in payload
    assert str(tmp_path) not in payload


def test_external_url_is_rejected_before_backend_execution(tmp_path: Path) -> None:
    plan = _playwright_supported_plan()
    plan["actions"][0]["parameters"]["url"] = "https://example.com/"
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path, replay_backend="playwright")
    calls: list[tuple[Mapping[str, Any], Any, Path]] = []

    summary = run_autonomous_browser_plan_playwright_replay_operator(
        config_path,
        repo_root=tmp_path,
        allow_real_browser=True,
        confirm_real_browser=REQUIRED_CONFIRM_VALUE,
        playwright_replay_executor=_fake_playwright_executor(
            {
                "status": "succeeded",
                "replay_backend": "playwright",
                "fixture_replay_execution": False,
                "playwright_execution": True,
                "browser_opened": True,
                "real_network_traffic": False,
                "real_browser_execution": True,
                "no_runtime_execution": False,
                "actions_attempted": 1,
                "actions_succeeded": 1,
                "actions_failed": 0,
                "expected_results_passed": 1,
                "expected_results_failed": 0,
                "expected_results_total": 1,
                "diagnostics": {"called": True},
            },
            calls,
        ),
    )

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "external_url_not_allowed"
    assert summary["guard_status"] == "guarded_replay"
    assert summary["no_runtime_execution"] is True
    assert summary["replay_backend"] == "playwright"
    assert calls == []


def test_unsupported_action_is_rejected_before_execution(tmp_path: Path) -> None:
    plan = _base_plan()
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path, replay_backend="playwright")
    calls: list[tuple[Mapping[str, Any], Any, Path]] = []

    summary = run_autonomous_browser_plan_playwright_replay_operator(
        config_path,
        repo_root=tmp_path,
        allow_real_browser=True,
        confirm_real_browser=REQUIRED_CONFIRM_VALUE,
        playwright_replay_executor=_fake_playwright_executor(
            {
                "status": "succeeded",
                "replay_backend": "playwright",
                "fixture_replay_execution": False,
                "playwright_execution": True,
                "browser_opened": True,
                "real_network_traffic": False,
                "real_browser_execution": True,
                "no_runtime_execution": False,
                "actions_attempted": 1,
                "actions_succeeded": 1,
                "actions_failed": 0,
                "expected_results_passed": 1,
                "expected_results_failed": 0,
                "expected_results_total": 1,
                "diagnostics": {"called": True},
            },
            calls,
        ),
    )

    assert summary["status"] == "rejected"
    assert summary["error_code"] == "unsupported_playwright_replay_action"
    assert summary["guard_status"] == "guarded_replay"
    assert summary["no_runtime_execution"] is True
    assert summary["replay_backend"] == "playwright"
    assert summary["fixture_replay_execution"] is False
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["real_browser_execution"] is False
    assert calls == []


def test_fake_playwright_adapter_path_can_be_unit_tested_without_playwright_import(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
) -> None:
    plan = _playwright_supported_plan()
    _copy_fixture_site(tmp_path)
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path, replay_backend="playwright")
    calls: list[tuple[Mapping[str, Any], Any, Path]] = []
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = run_autonomous_browser_plan_playwright_replay_operator(
        config_path,
        repo_root=tmp_path,
        allow_real_browser=True,
        confirm_real_browser=REQUIRED_CONFIRM_VALUE,
        playwright_replay_executor=_fake_playwright_executor(
            {
                "status": "succeeded",
                "replay_backend": "playwright",
                "fixture_replay_execution": False,
                "playwright_execution": True,
                "browser_opened": True,
                "real_network_traffic": False,
                "real_browser_execution": True,
                "no_runtime_execution": False,
                "actions_attempted": 2,
                "actions_succeeded": 2,
                "actions_failed": 0,
                "expected_results_passed": 2,
                "expected_results_failed": 0,
                "expected_results_total": 2,
                "diagnostics": {"fake": True},
            },
            calls,
        ),
    )

    assert summary["status"] == "succeeded"
    assert summary["replay_backend"] == "playwright"
    assert summary["no_runtime_execution"] is False
    assert summary["real_browser_execution"] is True
    assert summary["playwright_execution"] is True
    assert summary["browser_opened"] is True
    assert summary["fixture_replay_execution"] is False
    assert calls


def test_guarded_fixture_replay_uses_fixture_backend(tmp_path: Path) -> None:
    plan = _base_plan()
    _copy_fixture_site(tmp_path)
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path)

    summary = run_autonomous_browser_plan_playwright_replay_operator(
        config_path,
        repo_root=tmp_path,
        allow_real_browser=True,
        confirm_real_browser=REQUIRED_CONFIRM_VALUE,
    )
    encoded = json.dumps(summary, ensure_ascii=False)

    assert summary["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert summary["status"] == "succeeded"
    assert summary["error_code"] is None
    assert summary["guard_status"] == "guarded_replay"
    assert summary["no_runtime_execution"] is False
    assert summary["model_execution"] is False
    assert summary["real_browser_execution"] is False
    assert summary["replay_backend"] == "fixture"
    assert summary["fixture_replay_execution"] is True
    assert summary["playwright_execution"] is False
    assert summary["browser_opened"] is False
    assert summary["real_network_traffic"] is False
    assert summary["plan_id"] == "browser_policy_research_plan_v1"
    assert summary["actions_total"] == 3
    assert summary["actions_attempted"] == 3
    assert summary["actions_succeeded"] == 3
    assert summary["actions_failed"] == 0
    assert summary["expected_results_passed"] == 3
    assert summary["expected_results_failed"] == 0
    assert summary["expected_results_total"] == 3
    assert "fixture_source" in encoded
    assert "real_network_traffic" in encoded
    assert "browser_opened" in encoded
    assert "supersecret" not in encoded


def test_click_target_selection_prefers_clickable_link_over_generic_text() -> None:
    page = _FakeClickPage(
        url="https://local.intranet/",
        title="Office Intranet",
        body_text="Office Intranet Home Workspace policy Ticket board",
        target_text="Workspace policy",
        role_link_count=1,
        text_count=1,
    )

    locator, diagnostics = _click_locator_from_page(page, selector=None, target_text="Workspace policy")

    assert locator is not None
    assert diagnostics["selector_kind"] == "role_link"
    assert diagnostics["clickable"] is True
    assert page.calls[0] == ("get_by_role", "link", "Workspace policy", True)


def test_click_without_navigation_requires_visible_expected_text() -> None:
    backend = RealPlaywrightBackend(headless=True, timeout_ms=1_000)
    backend._page = _FakeClickPage(
        url="https://local.intranet/",
        title="Office Intranet",
        body_text="Office Intranet Home Workspace policy Ticket board",
        target_text="Workspace policy",
        role_link_count=1,
    )

    result = backend.run_action(
        "browser_click",
        "https://local.intranet/",
        logical_url="https://local.intranet/",
        expected_text="Allowed activity",
        parameters={"target_text": "Workspace policy"},
    )

    assert result.success is False
    assert result.error_code == "browser_click_navigation_not_detected"
    assert result.diagnostics["expected_text"] == "Allowed activity"
    assert result.diagnostics["expected_text_found"] is False


def test_click_navigation_updates_url_and_expected_text_preview() -> None:
    backend = RealPlaywrightBackend(headless=True, timeout_ms=1_000)
    backend._page = _FakeClickPage(
        url="https://local.intranet/",
        title="Office Intranet",
        body_text="Office Intranet Home Ticket board Workspace policy",
        target_text="Ticket board",
        role_link_count=1,
        post_click_url="https://local.intranet/tickets",
        post_click_title="Ticket Board",
        post_click_body_text="Ticket Board Home Ticket 1 Team status Open tickets",
    )

    result = backend.run_action(
        "browser_click",
        "https://local.intranet/",
        logical_url="https://local.intranet/",
        expected_text="Ticket Board",
        parameters={"target_text": "Ticket board"},
    )

    assert result.success is True
    assert result.served_url == "https://local.intranet/tickets"
    assert result.diagnostics["expected_text"] == "Ticket Board"
    assert result.diagnostics["expected_text_found"] is True
    assert result.diagnostics["navigation_changed"] is True
    assert "Ticket Board Home Ticket 1 Team status Open tickets" in result.text_preview


def test_no_playwright_import_or_browser_server_model_use(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    plan = _playwright_supported_plan()
    _write_replay_plan(tmp_path, plan)
    config_path = _write_config(tmp_path, replay_backend="playwright")
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    summary = run_autonomous_browser_plan_playwright_replay_operator(config_path, repo_root=tmp_path, dry_run=True)

    assert summary["status"] == "succeeded"
    assert summary["guard_status"] == "dry_run"
    assert summary["replay_backend"] == "playwright"


def test_cli_refusal_smoke_uses_repo_local_paths() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--config", str(EXAMPLE_CONFIG_PATH)],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 2
    assert payload["status"] == "refused"
    assert payload["error_code"] == "allow_real_browser_required"
    assert payload["guard_status"] == "refused"
    assert payload["no_runtime_execution"] is True
    assert payload["real_browser_execution"] is False
    assert payload["replay_backend"] == "fixture"
    assert payload["replay_plan_path"] == EXAMPLE_REPLAY_PLAN_PATH
    assert payload["output_files"][0].startswith(EXAMPLE_OUTPUT_DIR)


def test_cli_dry_run_smoke_uses_repo_local_paths() -> None:
    completed = subprocess.run(
        [sys.executable, str(SCRIPT_PATH), "--config", str(EXAMPLE_CONFIG_PATH), "--dry-run"],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert payload["status"] == "succeeded"
    assert payload["guard_status"] == "dry_run"
    assert payload["no_runtime_execution"] is True
    assert payload["real_browser_execution"] is False
    assert payload["replay_backend"] == "fixture"
    assert payload["fixture_replay_execution"] is False
    assert payload["playwright_execution"] is False
    assert payload["browser_opened"] is False
    assert payload["real_network_traffic"] is False
    assert payload["model_execution"] is False
    assert completed.stdout.strip() == completed.stdout.strip().replace("\n", "")


def test_cli_dry_run_playwright_smoke_uses_repo_local_paths() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--config",
            str(EXAMPLE_CONFIG_PATH),
            "--dry-run",
            "--replay-backend",
            "playwright",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 0
    assert payload["schema_version"] == SUMMARY_SCHEMA_VERSION
    assert payload["status"] == "succeeded"
    assert payload["guard_status"] == "dry_run"
    assert payload["no_runtime_execution"] is True
    assert payload["replay_backend"] == "playwright"
    assert payload["real_browser_execution"] is False
    assert payload["fixture_replay_execution"] is False
    assert payload["playwright_execution"] is False
    assert payload["browser_opened"] is False
    assert payload["real_network_traffic"] is False
    assert payload["model_execution"] is False


def test_cli_refusal_playwright_smoke_uses_repo_local_paths() -> None:
    completed = subprocess.run(
        [
            sys.executable,
            str(SCRIPT_PATH),
            "--config",
            str(EXAMPLE_CONFIG_PATH),
            "--replay-backend",
            "playwright",
        ],
        cwd=PROJECT_ROOT,
        capture_output=True,
        text=True,
        check=False,
    )
    payload = json.loads(completed.stdout)

    assert completed.returncode == 2
    assert payload["status"] == "refused"
    assert payload["error_code"] == "allow_real_browser_required"
    assert payload["guard_status"] == "refused"
    assert payload["replay_backend"] == "playwright"
    assert payload["no_runtime_execution"] is True
    assert payload["real_browser_execution"] is False
