from __future__ import annotations

import builtins
import json
import subprocess
import sys
import shutil
from pathlib import Path
from typing import Any

import pytest

from src.agent.autonomous_browser_plan_playwright_replay_operator import (
    CONFIG_SCHEMA_VERSION,
    REQUIRED_ALLOW_FLAG,
    REQUIRED_CONFIRM_VALUE,
    SUMMARY_SCHEMA_VERSION,
    load_autonomous_browser_plan_playwright_replay_operator_config,
    run_autonomous_browser_plan_playwright_replay_operator,
)


PROJECT_ROOT = Path(__file__).resolve().parents[1]
EXAMPLE_CONFIG_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_plan_playwright_replay_operator.example.json"
PLAN_SOURCE_PATH = PROJECT_ROOT / "configs" / "autonomous_runtime" / "browser_plan.example.json"
DEFAULT_REPLAY_PLAN_PATH = "artifacts/autonomous_runtime_summaries/model_plan_playwright_replay_packet/playwright_replay_plan.json"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_plan_playwright_replay_operator_tests"
EXAMPLE_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/model_plan_playwright_replay_operator"
SCRIPT_PATH = PROJECT_ROOT / "scripts" / "run_autonomous_browser_plan_playwright_replay_operator.py"


def _base_plan() -> dict[str, Any]:
    return json.loads(PLAN_SOURCE_PATH.read_text(encoding="utf-8"))


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
    plan["actions"] = plan["actions"][:2]
    return plan


def _fake_playwright_executor(
    replay_result: dict[str, Any],
    calls: list[tuple[Mapping[str, Any], Any, Path]],
) -> Any:
    def executor(normalized_plan: Mapping[str, Any], config: Any, repo_root: Path) -> dict[str, Any]:
        calls.append((normalized_plan, config, repo_root))
        return dict(replay_result)

    return executor


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
    assert config.replay_plan_path == DEFAULT_REPLAY_PLAN_PATH
    assert config.output_dir == EXAMPLE_OUTPUT_DIR
    assert config.fixture_scope == "local_only"
    assert config.headless is True
    assert config.timeout_ms == 30_000
    assert config.allowed_hosts == ("local.intranet", "local-intranet.test", "docs.local", "portal.local")
    assert all(not Path(path).is_absolute() for path in (config.replay_plan_path, config.output_dir))


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
    assert payload["replay_plan_path"] == DEFAULT_REPLAY_PLAN_PATH
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
