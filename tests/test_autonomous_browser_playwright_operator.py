from __future__ import annotations

import builtins
import json
import subprocess
import sys
from pathlib import Path
from typing import Any

import pytest

import scripts.run_autonomous_browser_playwright_operator as runner_module
from src.agent.autonomous_browser_playwright_execution import PlaywrightExecutionConfig
from src.agent.autonomous_browser_playwright_operator import (
    REQUIRED_ALLOW_FLAG,
    REQUIRED_CONFIRM_FLAG,
    REQUIRED_CONFIRM_VALUE,
    PlaywrightOperatorConfig,
    PlaywrightOperatorConfigError,
    build_playwright_operator_packet,
    load_playwright_operator_config,
    validate_playwright_operator_config,
)
from src.agent.autonomous_browser_runtime import BROWSER_RUNTIME_ACTION_NAMES


PROJECT_ROOT = Path(__file__).resolve().parents[1]
CONFIG_PATH = PROJECT_ROOT / "configs/autonomous_runtime/playwright_operator.example.json"
RUNNER_PATH = PROJECT_ROOT / "scripts/run_autonomous_browser_playwright_operator.py"


def _payload() -> dict[str, Any]:
    return json.loads(CONFIG_PATH.read_text(encoding="utf-8"))


def _write_config(tmp_path: Path, payload: dict[str, Any]) -> Path:
    path = tmp_path / "playwright_operator.json"
    path.write_text(json.dumps(payload, ensure_ascii=True, indent=2), encoding="utf-8")
    return path


def _load_payload(payload: dict[str, Any], tmp_path: Path) -> PlaywrightOperatorConfig:
    return load_playwright_operator_config(_write_config(tmp_path, payload))


def test_config_example_loads() -> None:
    config = load_playwright_operator_config(CONFIG_PATH)

    assert config.schema_version == "playwright_operator_config_v1"
    assert config.operator_id == "browser_suite_playwright_operator_v1"
    assert config.scenario_suite_path == "configs/autonomous_runtime/browser_scenario_suite.example.json"
    assert config.execution_scope == {"mode": "first_scenario_only", "max_browser_actions": 8}


def test_readiness_validates_safe_config() -> None:
    readiness = validate_playwright_operator_config(
        load_playwright_operator_config(CONFIG_PATH),
        repo_root=PROJECT_ROOT,
    )

    assert readiness.ready is True
    assert readiness.to_dict()["schema_version"] == "playwright_operator_readiness_v1"
    assert readiness.to_dict()["no_runtime_execution"] is True
    assert f"{REQUIRED_CONFIRM_FLAG} {REQUIRED_CONFIRM_VALUE}" in readiness.to_dict()["required_operator_guards"]


def test_readiness_rejects_absolute_output_path(tmp_path: Path) -> None:
    payload = _payload()
    payload["output_dir"] = str(tmp_path / "out")

    with pytest.raises(PlaywrightOperatorConfigError, match="safe relative path"):
        _load_payload(payload, tmp_path)


def test_readiness_rejects_missing_suite_path(tmp_path: Path) -> None:
    payload = _payload()
    payload["scenario_suite_path"] = "configs/autonomous_runtime/missing_suite.json"
    config = _load_payload(payload, tmp_path)
    readiness = validate_playwright_operator_config(config, repo_root=PROJECT_ROOT)

    assert readiness.ready is False
    checks = {item["name"]: item for item in readiness.to_dict()["checks"]}
    assert checks["scenario_suite_path_exists"]["passed"] is False
    assert checks["scenario_suite_loads"]["passed"] is False


def test_readiness_rejects_config_without_guard_requirements(tmp_path: Path) -> None:
    payload = _payload()
    payload.pop("required_guards")

    with pytest.raises(PlaywrightOperatorConfigError, match="required_guards"):
        _load_payload(payload, tmp_path)


def test_readiness_rejects_unsupported_execution_scope_mode(tmp_path: Path) -> None:
    payload = _payload()
    payload["execution_scope"] = {"mode": "all_scenarios", "max_browser_actions": 8}
    config = _load_payload(payload, tmp_path)
    readiness = validate_playwright_operator_config(config, repo_root=PROJECT_ROOT)

    checks = {item["name"]: item for item in readiness.to_dict()["checks"]}
    assert readiness.ready is False
    assert checks["execution_scope_mode"]["passed"] is False


def test_readiness_rejects_invalid_execution_scope_action_limit(tmp_path: Path) -> None:
    payload = _payload()
    payload["execution_scope"] = {"mode": "first_scenario_only", "max_browser_actions": 0}
    config = _load_payload(payload, tmp_path)
    readiness = validate_playwright_operator_config(config, repo_root=PROJECT_ROOT)

    checks = {item["name"]: item for item in readiness.to_dict()["checks"]}
    assert readiness.ready is False
    assert checks["execution_scope_max_actions"]["passed"] is False


def test_dry_run_does_not_import_playwright(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith("playwright"):
            raise AssertionError("dry-run must not import Playwright")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    readiness = validate_playwright_operator_config(
        load_playwright_operator_config(CONFIG_PATH),
        repo_root=PROJECT_ROOT,
    )

    assert readiness.ready is True


def test_dry_run_does_not_start_fixture_server(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name in {"http.server", "socketserver"} or name.startswith("playwright"):
            raise AssertionError("dry-run must not start server or import Playwright")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    packet = build_playwright_operator_packet(
        load_playwright_operator_config(CONFIG_PATH),
        repo_root=PROJECT_ROOT,
    )

    assert packet.readiness.ready is True
    assert packet.no_runtime_execution is True


def test_runner_refuses_without_allow_real_browser() -> None:
    result = subprocess.run(
        [sys.executable, str(RUNNER_PATH), "--config", str(CONFIG_PATH)],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 2
    assert payload["status"] == "refused"
    assert payload["error"] == f"missing_required_guard:{REQUIRED_ALLOW_FLAG}"
    assert payload["no_runtime_execution"] is True


def test_runner_refuses_without_exact_confirm_guard() -> None:
    result = subprocess.run(
        [sys.executable, str(RUNNER_PATH), "--config", str(CONFIG_PATH), "--allow-real-browser"],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 2
    assert payload["status"] == "refused"
    assert payload["error"] == "missing_or_invalid_confirm_real_browser"


def test_runner_with_one_missing_guard_refuses() -> None:
    result = subprocess.run(
        [
            sys.executable,
            str(RUNNER_PATH),
            "--config",
            str(CONFIG_PATH),
            "--confirm-real-browser",
            REQUIRED_CONFIRM_VALUE,
        ],
        cwd=PROJECT_ROOT,
        check=False,
        capture_output=True,
        text=True,
    )
    payload = json.loads(result.stdout)

    assert result.returncode == 2
    assert payload["error"] == f"missing_required_guard:{REQUIRED_ALLOW_FLAG}"


def test_runner_with_both_guards_invokes_injected_execution_runner(
    monkeypatch: pytest.MonkeyPatch,
    capsys: pytest.CaptureFixture[str],
) -> None:
    calls: list[PlaywrightExecutionConfig] = []

    class FakeSummary:
        status = "succeeded"

        def to_dict(self) -> dict[str, Any]:
            return {
                "schema_version": "autonomous_browser_playwright_smoke_summary_v1",
                "status": self.status,
                "no_runtime_execution": False,
                "browser_backend": {"type": "playwright", "browser_name": "chromium", "headless": True},
                "actions_attempted": 1,
            }

    def fake_runner(config: PlaywrightExecutionConfig) -> FakeSummary:
        calls.append(config)
        return FakeSummary()

    monkeypatch.setattr(runner_module, "write_autonomous_runtime_scenario_summary", lambda *args, **kwargs: None)
    rc = runner_module.main(
        [
            "--config",
            str(CONFIG_PATH),
            "--allow-real-browser",
            "--confirm-real-browser",
            REQUIRED_CONFIRM_VALUE,
        ],
        execution_runner=fake_runner,
    )
    payload = json.loads(capsys.readouterr().out)

    assert rc == 0
    assert payload["status"] == "succeeded"
    assert payload["no_runtime_execution"] is False
    assert len(calls) == 1
    assert calls[0].operator_id == "browser_suite_playwright_operator_v1"


def test_packet_builder_emits_commands_and_readme(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    packet = build_playwright_operator_packet(
        load_playwright_operator_config(CONFIG_PATH),
        config_path="configs/autonomous_runtime/playwright_operator.example.json",
        packet_output_dir="packets/playwright_operator",
        repo_root=PROJECT_ROOT,
    )

    assert packet.packet_dir == "packets/playwright_operator"
    assert Path("packets/playwright_operator/commands.json").is_file()
    assert Path("packets/playwright_operator/readiness_summary.json").is_file()
    readme = Path("packets/playwright_operator/README.md").read_text(encoding="utf-8")
    assert "Codex must not run" in readme


def test_packet_commands_include_both_guards(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    build_playwright_operator_packet(
        load_playwright_operator_config(CONFIG_PATH),
        config_path="configs/autonomous_runtime/playwright_operator.example.json",
        packet_output_dir="packets/playwright_operator",
        repo_root=PROJECT_ROOT,
    )
    commands = json.loads(Path("packets/playwright_operator/commands.json").read_text(encoding="utf-8"))
    guarded = next(command for command in commands["commands"] if command["name"] == "operator_guarded_real_browser")

    assert REQUIRED_ALLOW_FLAG in guarded["argv"]
    assert f"{REQUIRED_CONFIRM_FLAG} {REQUIRED_CONFIRM_VALUE}" in guarded["argv"]
    assert guarded["requires_operator"] is True
    assert not any("playwright install" in command["argv"].lower() for command in commands["commands"])


def test_packet_does_not_include_secrets(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    build_playwright_operator_packet(
        load_playwright_operator_config(CONFIG_PATH),
        config_path="configs/autonomous_runtime/playwright_operator.example.json",
        packet_output_dir="packets/playwright_operator",
        repo_root=PROJECT_ROOT,
    )
    encoded = "\n".join(path.read_text(encoding="utf-8") for path in Path("packets/playwright_operator").iterdir() if path.is_file())

    assert "OPENAI_API_KEY" not in encoded
    assert "DEEPSEEK_API_KEY" not in encoded
    assert "Authorization:" not in encoded
    assert "sk-" not in encoded


def test_no_local_absolute_paths_in_generated_packet(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.chdir(tmp_path)
    packet = build_playwright_operator_packet(
        load_playwright_operator_config(CONFIG_PATH),
        config_path="configs/autonomous_runtime/playwright_operator.example.json",
        packet_output_dir="packets/playwright_operator",
        repo_root=PROJECT_ROOT,
    )
    encoded = json.dumps(packet.to_dict(), ensure_ascii=False) + "\n"
    encoded += "\n".join(path.read_text(encoding="utf-8") for path in Path("packets/playwright_operator").iterdir() if path.is_file())

    assert str(PROJECT_ROOT) not in encoded
    assert ":\\" not in encoded


def test_suite_path_is_validated_through_existing_suite_loader() -> None:
    readiness = validate_playwright_operator_config(
        load_playwright_operator_config(CONFIG_PATH),
        repo_root=PROJECT_ROOT,
    ).to_dict()

    assert any(item["name"] == "scenario_suite_loads" and item["passed"] for item in readiness["checks"])
    assert any(item["name"].startswith("browser_namespace:") and item["passed"] for item in readiness["checks"])


def test_no_mail_git_calendar_action_support_added() -> None:
    names = set(BROWSER_RUNTIME_ACTION_NAMES)

    assert not any(name.startswith(("mail_", "git_", "calendar_", "email_")) for name in names)
    assert "browser_open_url" in names


def test_no_llm_api_model_browser_playwright_calls_are_made(monkeypatch: pytest.MonkeyPatch) -> None:
    original_import = builtins.__import__
    forbidden = ("playwright", "llama_cpp", "openai", "http.server", "socketserver")

    def guarded_import(name: str, *args: Any, **kwargs: Any) -> Any:
        if name.startswith(forbidden):
            raise AssertionError(f"forbidden runtime import: {name}")
        return original_import(name, *args, **kwargs)

    monkeypatch.setattr(builtins, "__import__", guarded_import)

    readiness = validate_playwright_operator_config(
        load_playwright_operator_config(CONFIG_PATH),
        repo_root=PROJECT_ROOT,
    )

    assert readiness.ready is True
    assert readiness.no_runtime_execution is True
