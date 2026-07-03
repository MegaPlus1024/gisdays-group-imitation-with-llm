from __future__ import annotations

import argparse
import json
import subprocess
import sys
import time
import urllib.error
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


@dataclass
class ManagedServer:
    role: str
    model_id: str
    port: int
    wrapper_pid: int | None = None
    llama_pids: list[int] = field(default_factory=list)
    endpoint_ready: bool = False
    endpoint_stopped: bool = False
    error: str | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run repeated orchestrator/executor group trials.")
    parser.add_argument("--models-config", default="configs/evaluation_models.json")
    parser.add_argument("--scenario", default="configs/multi_agent_scenarios/office_developer_group_basic.json")
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--label", default="repeated_group_trials")
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--mode", choices=["fake", "local"], default="fake")
    parser.add_argument("--orchestrator-model-id", default="second_model")
    parser.add_argument("--executor-model-id", default="first_model")
    parser.add_argument("--orchestrator-base-url", default=None)
    parser.add_argument("--executor-base-url", default=None)
    parser.add_argument("--orchestrator-model-name", default=None)
    parser.add_argument("--executor-model-name", default=None)
    parser.add_argument("--orchestrator-port", type=int, default=8081)
    parser.add_argument("--executor-port", type=int, default=8082)
    parser.add_argument("--manage-servers", dest="manage_servers", action="store_true", default=False)
    parser.add_argument("--no-manage-servers", dest="manage_servers", action="store_false")
    parser.add_argument("--max-group-steps", type=int, default=None)
    parser.add_argument("--max-steps-per-agent", type=int, default=None)
    parser.add_argument("--orchestrator-max-tokens", type=int, default=None)
    parser.add_argument("--orchestrator-temperature", type=float, default=None)
    parser.add_argument("--orchestrator-repair-attempts", type=int, default=0)
    parser.add_argument("--repair-attempts", type=int, default=0)
    parser.add_argument("--execute-actions", dest="execute_actions", action="store_true", default=True)
    parser.add_argument("--no-execute-actions", dest="execute_actions", action="store_false")
    parser.add_argument("--continue-on-trial-failure", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.trials < 1:
        parser.error("--trials must be >= 1")

    from src.agent.evaluation_models import preflight_evaluation_model, resolve_evaluation_model
    from src.agent.repeated_orchestrator_executor_trials import (
        RepeatedGroupRunConfig,
        run_repeated_group_trials,
    )

    out_root = _project_path(args.out_root)
    servers: list[ManagedServer] = []
    server_error: str | None = None

    orchestrator_base_url = args.orchestrator_base_url
    executor_base_url = args.executor_base_url
    if args.mode == "local":
        orchestrator_base_url = orchestrator_base_url or f"http://127.0.0.1:{args.orchestrator_port}/v1"
        executor_base_url = executor_base_url or f"http://127.0.0.1:{args.executor_port}/v1"

    try:
        if args.mode == "local":
            for model_id in [args.orchestrator_model_id, args.executor_model_id]:
                model = resolve_evaluation_model(model_id, _project_path(args.models_config))
                preflight = preflight_evaluation_model(model, PROJECT_ROOT, require_model_file=True)
                if preflight.status == "fail":
                    raise RuntimeError(f"preflight failed for {model_id}: {preflight.model_dump(mode='json')}")
        if args.mode == "local" and args.manage_servers:
            servers = _start_managed_servers(args)
        config = RepeatedGroupRunConfig(
            project_root=PROJECT_ROOT,
            mode=args.mode,
            models_config_path=args.models_config,
            scenario_path=args.scenario,
            out_root=args.out_root,
            label=args.label,
            trials=args.trials,
            orchestrator_model_id=args.orchestrator_model_id,
            executor_model_id=args.executor_model_id,
            orchestrator_base_url=orchestrator_base_url,
            executor_base_url=executor_base_url,
            orchestrator_model_name=args.orchestrator_model_name,
            executor_model_name=args.executor_model_name,
            orchestrator_max_tokens=args.orchestrator_max_tokens,
            orchestrator_temperature=args.orchestrator_temperature,
            orchestrator_repair_attempts=args.orchestrator_repair_attempts,
            max_group_steps=args.max_group_steps,
            max_steps_per_agent=args.max_steps_per_agent,
            repair_attempts=args.repair_attempts,
            execute_actions=args.execute_actions,
            continue_on_trial_failure=args.continue_on_trial_failure,
            force=args.force,
        )
        result = run_repeated_group_trials(config)
        exit_code = 0 if result.status == "complete" or args.continue_on_trial_failure else 1
    except Exception as exc:
        server_error = str(exc) or exc.__class__.__name__
        out_root.mkdir(parents=True, exist_ok=True)
        _write_blocker(out_root, args, server_error)
        result = None
        exit_code = 1
    finally:
        if servers:
            _stop_managed_servers(servers)
        if args.mode == "local" and args.manage_servers:
            out_root.mkdir(parents=True, exist_ok=True)
            _write_server_run(out_root, servers, server_error)

    if result is not None:
        _write_server_run(out_root, servers, server_error)
        (out_root / "replay_commands.ps1").write_text(_replay_command(args) + "\n", encoding="utf-8")
        if args.json_only:
            print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
        else:
            _print_summary(result, out_root)
    elif args.json_only:
        print(json.dumps({"status": "blocked", "error": server_error}, ensure_ascii=False, indent=2))
    else:
        print(f"ERROR: repeated group trials blocked: {server_error}", file=sys.stderr)
    return exit_code


def _start_managed_servers(args: argparse.Namespace) -> list[ManagedServer]:
    if _endpoint_json(args.orchestrator_port) is not None or _endpoint_json(args.executor_port) is not None:
        raise RuntimeError("One or both requested ports are already serving a local endpoint.")
    servers = [
        ManagedServer("orchestrator", args.orchestrator_model_id, args.orchestrator_port),
        ManagedServer("executor", args.executor_model_id, args.executor_port),
    ]
    before = set(_llama_server_pids())
    for server in servers:
        proc = subprocess.Popen(
            [
                "powershell",
                "-ExecutionPolicy",
                "Bypass",
                "-File",
                ".\\scripts\\start_llama_server.ps1",
                "-ModelId",
                server.model_id,
                "-ModelsConfig",
                args.models_config,
                "-Port",
                str(server.port),
            ],
            cwd=PROJECT_ROOT,
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL,
            text=True,
        )
        server.wrapper_pid = proc.pid
        if not _wait_endpoint(server.port, 75):
            server.error = f"endpoint on port {server.port} did not become ready"
            raise RuntimeError(server.error)
        server.endpoint_ready = True
        after = set(_llama_server_pids())
        server.llama_pids = sorted(after - before)
        before = after
    return servers


def _stop_managed_servers(servers: list[ManagedServer]) -> None:
    for server in servers:
        ids = [*server.llama_pids]
        if server.wrapper_pid:
            ids.append(server.wrapper_pid)
        ids = list(dict.fromkeys(pid for pid in ids if pid))
        if ids:
            subprocess.run(
                [
                    "powershell",
                    "-NoProfile",
                    "-Command",
                    "$ids=@(" + ",".join(str(pid) for pid in ids) + "); foreach($id in $ids){Stop-Process -Id $id -Force -ErrorAction SilentlyContinue}",
                ],
                cwd=PROJECT_ROOT,
                text=True,
                capture_output=True,
                check=False,
            )
    time.sleep(2)
    for server in servers:
        server.endpoint_stopped = _endpoint_json(server.port) is None


def _wait_endpoint(port: int, seconds: int) -> bool:
    deadline = time.time() + seconds
    while time.time() < deadline:
        if _endpoint_json(port) is not None:
            return True
        time.sleep(0.5)
    return False


def _endpoint_json(port: int) -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen(f"http://127.0.0.1:{port}/v1/models", timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def _llama_server_pids() -> list[int]:
    completed = subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            "(Get-CimInstance Win32_Process -Filter \"name = 'llama-server.exe'\" | Select-Object -ExpandProperty ProcessId) -join ','",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    if completed.returncode != 0 or not completed.stdout.strip():
        return []
    return [int(item) for item in completed.stdout.strip().split(",") if item.strip().isdigit()]


def _write_server_run(out_root: Path, servers: list[ManagedServer], server_error: str | None) -> None:
    payload = {
        "server_error": server_error,
        "servers": [
            {
                "role": server.role,
                "model_id": server.model_id,
                "port": server.port,
                "wrapper_pid": server.wrapper_pid,
                "llama_pids": server.llama_pids,
                "endpoint_ready": server.endpoint_ready,
                "endpoint_stopped": server.endpoint_stopped,
                "error": server.error,
            }
            for server in servers
        ],
    }
    (out_root / "server_run.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _write_blocker(out_root: Path, args: argparse.Namespace, error: str) -> None:
    payload = {
        "status": "blocked",
        "label": args.label,
        "mode": args.mode,
        "error": error,
    }
    (out_root / "blocker.json").write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_root / "repeated_group_trials_blocker.md").write_text(
        "# Repeated Group Trials Blocker\n\n"
        f"Status: `blocked`\n\nError: `{error}`\n\nNo fake replacement results were created.\n",
        encoding="utf-8",
    )


def _replay_command(args: argparse.Namespace) -> str:
    action_flag = "--execute-actions" if args.execute_actions else "--no-execute-actions"
    server_flag = "--manage-servers" if args.manage_servers else "--no-manage-servers"
    continue_flag = " --continue-on-trial-failure" if args.continue_on_trial_failure else ""
    optional = ""
    if args.orchestrator_base_url:
        optional += f"--orchestrator-base-url {args.orchestrator_base_url} "
    if args.executor_base_url:
        optional += f"--executor-base-url {args.executor_base_url} "
    if args.orchestrator_model_name:
        optional += f"--orchestrator-model-name {args.orchestrator_model_name} "
    if args.executor_model_name:
        optional += f"--executor-model-name {args.executor_model_name} "
    if args.orchestrator_max_tokens is not None:
        optional += f"--orchestrator-max-tokens {args.orchestrator_max_tokens} "
    if args.orchestrator_temperature is not None:
        optional += f"--orchestrator-temperature {args.orchestrator_temperature} "
    return (
        "python scripts\\run_repeated_orchestrator_executor_trials.py "
        f"--mode {args.mode} "
        f"--models-config {args.models_config} "
        f"--scenario {args.scenario} "
        f"--out-root {args.out_root} "
        f"--label {args.label} "
        f"--trials {args.trials} "
        f"--orchestrator-model-id {args.orchestrator_model_id} "
        f"--executor-model-id {args.executor_model_id} "
        f"--orchestrator-port {args.orchestrator_port} "
        f"--executor-port {args.executor_port} "
        f"{optional}"
        f"{server_flag} "
        f"--max-group-steps {args.max_group_steps or 1} "
        f"--max-steps-per-agent {args.max_steps_per_agent or 1} "
        f"--orchestrator-repair-attempts {args.orchestrator_repair_attempts} "
        f"--repair-attempts {args.repair_attempts} "
        f"{action_flag} "
        "--force"
        f"{continue_flag}"
    )


def _project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _print_summary(result: Any, out_root: Path) -> None:
    aggregate = result.aggregate
    print(f"comparison_id: {result.comparison_id}")
    print(f"status: {result.status}")
    print(f"orchestrator_model_id: {result.orchestrator_model_id}")
    print(f"executor_model_id: {result.executor_model_id}")
    print(f"trial_count: {aggregate.trial_count}")
    print(f"completed_trial_count: {aggregate.completed_trial_count}")
    print(f"failed_trial_count: {aggregate.failed_trial_count}")
    print(f"mean_pair_quality_score: {aggregate.mean_pair_quality_score}")
    print(f"mean_execution_success_rate: {aggregate.mean_execution_success_rate}")
    print(f"total_errors: {aggregate.total_errors}")
    print(f"out_root: {out_root}")


if __name__ == "__main__":
    raise SystemExit(main())
