from __future__ import annotations

import argparse
import json
import shutil
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
    parser = argparse.ArgumentParser(description="Run orchestrator/executor pair matrix comparison.")
    parser.add_argument("--models-config", default="configs/evaluation_models.json")
    parser.add_argument("--scenario", default="configs/multi_agent_scenarios/office_developer_group_basic.json")
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--label", default="pair_matrix")
    parser.add_argument("--pairs", required=True)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--mode", choices=["fake", "local"], default="fake")
    parser.add_argument("--base-orchestrator-port", type=int, default=8081)
    parser.add_argument("--base-executor-port", type=int, default=8082)
    parser.add_argument("--manage-servers", dest="manage_servers", action="store_true", default=False)
    parser.add_argument("--no-manage-servers", dest="manage_servers", action="store_false")
    parser.add_argument("--reuse-existing", action="store_true")
    parser.add_argument("--existing-pair-run", action="append", default=[])
    parser.add_argument("--max-group-steps", type=int, default=None)
    parser.add_argument("--max-steps-per-agent", type=int, default=None)
    parser.add_argument("--orchestrator-max-tokens", type=int, default=None)
    parser.add_argument("--orchestrator-repair-attempts", type=int, default=0)
    parser.add_argument("--repair-attempts", type=int, default=0)
    parser.add_argument("--execute-actions", dest="execute_actions", action="store_true", default=True)
    parser.add_argument("--no-execute-actions", dest="execute_actions", action="store_false")
    parser.add_argument("--continue-on-pair-failure", action="store_true")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    if args.trials < 1:
        parser.error("--trials must be >= 1")

    from src.agent.evaluation_models import preflight_evaluation_model, resolve_evaluation_model
    from src.agent.orchestrator_executor_pair_matrix import (
        PairSpec,
        aggregate_pair_result,
        compare_pair_results,
        failed_pair_result,
        parse_pair_specs,
        validate_repeated_run_protocol,
        write_failed_pair_artifact,
        write_pair_matrix_report,
        write_reused_pair_reference,
    )
    from src.agent.repeated_orchestrator_executor_trials import (
        RepeatedGroupRunConfig,
        run_repeated_group_trials,
    )

    try:
        pairs = parse_pair_specs(args.pairs)
        existing_pair_runs = _parse_existing_pair_runs(args.existing_pair_run)
    except ValueError as exc:
        parser.error(str(exc))

    out_root = _project_path(args.out_root)
    if args.force:
        _remove_existing_out_root(out_root)
    out_root.mkdir(parents=True, exist_ok=True)
    (out_root / "pairs").mkdir(parents=True, exist_ok=True)

    pair_results = []
    for pair in pairs:
        pair_root = out_root / "pairs" / pair.pair_id
        pair_root.mkdir(parents=True, exist_ok=True)
        existing_root = existing_pair_runs.get(pair.label) or existing_pair_runs.get(f"{pair.orchestrator_model_id}:{pair.executor_model_id}")
        server_strategy = _server_strategy(args, pair)
        server_notes = [_server_note(args, pair)]

        if existing_root:
            protocol_match, protocol_notes = validate_repeated_run_protocol(
                _project_path(existing_root),
                pair,
                scenario_path=args.scenario,
                mode=args.mode,
                trials=args.trials,
                max_group_steps=args.max_group_steps,
                max_steps_per_agent=args.max_steps_per_agent,
                orchestrator_repair_attempts=args.orchestrator_repair_attempts,
                repair_attempts=args.repair_attempts,
                execute_actions=args.execute_actions,
                orchestrator_max_tokens=args.orchestrator_max_tokens,
            )
            if protocol_match:
                write_reused_pair_reference(
                    pair_root,
                    pair,
                    str(_project_path(existing_root)),
                    protocol_match=protocol_match,
                    protocol_notes=protocol_notes,
                )
                pair_results.append(
                    aggregate_pair_result(
                        pair_root,
                        models_config_path=args.models_config,
                        project_root=PROJECT_ROOT,
                        reference_source="reused",
                        original_artifact_path=str(_project_path(existing_root)),
                        protocol_match=protocol_match,
                        protocol_notes=protocol_notes,
                        server_strategy="reused existing repeated group artifact; no servers started",
                        server_notes=["existing artifact matched requested matrix protocol"],
                    )
                )
                continue
            _write_json(
                pair_root / "reused_pair_run_rejected.json",
                {
                    "pair": pair.label,
                    "original_artifact_path": str(_project_path(existing_root)),
                    "protocol_match": protocol_match,
                    "protocol_notes": protocol_notes,
                },
            )

        servers: list[ManagedServer] = []
        server_error: str | None = None
        try:
            if args.mode == "local":
                for model_id in [pair.orchestrator_model_id, pair.executor_model_id]:
                    model = resolve_evaluation_model(model_id, _project_path(args.models_config))
                    preflight = preflight_evaluation_model(model, PROJECT_ROOT, require_model_file=True)
                    if preflight.status == "fail":
                        raise RuntimeError(f"preflight failed for {model_id}: {preflight.model_dump(mode='json')}")
                if args.manage_servers:
                    servers = _start_managed_servers(args, pair)
            run_repeated_group_trials(
                RepeatedGroupRunConfig(
                    project_root=PROJECT_ROOT,
                    mode=args.mode,
                    models_config_path=args.models_config,
                    scenario_path=args.scenario,
                    out_root=str(pair_root),
                    label=f"{args.label}_{pair.pair_id}",
                    trials=args.trials,
                    orchestrator_model_id=pair.orchestrator_model_id,
                    executor_model_id=pair.executor_model_id,
                    orchestrator_base_url=_base_url(args.base_orchestrator_port) if args.mode == "local" else None,
                    executor_base_url=_base_url(args.base_executor_port) if args.mode == "local" else None,
                    orchestrator_max_tokens=args.orchestrator_max_tokens,
                    orchestrator_repair_attempts=args.orchestrator_repair_attempts,
                    max_group_steps=args.max_group_steps,
                    max_steps_per_agent=args.max_steps_per_agent,
                    repair_attempts=args.repair_attempts,
                    execute_actions=args.execute_actions,
                    continue_on_trial_failure=True,
                    force=True,
                )
            )
            pair_result = aggregate_pair_result(
                pair_root,
                models_config_path=args.models_config,
                project_root=PROJECT_ROOT,
                reference_source="generated",
                protocol_match=True,
                protocol_notes=["generated by pair matrix run"],
                server_strategy=server_strategy,
                server_notes=server_notes,
            )
            if pair_result.aggregate and pair_result.aggregate.failed_trial_count:
                pair_result.status = "failed"
                pair_result.error_message = "one or more trials failed"
            pair_results.append(pair_result)
        except Exception as exc:
            server_error = str(exc) or exc.__class__.__name__
            pair_result = failed_pair_result(
                pair,
                pair_root,
                f"{exc.__class__.__name__}: {server_error}",
                source="failed",
                server_strategy=server_strategy,
                server_notes=server_notes,
            )
            write_failed_pair_artifact(pair_root, pair_result)
            pair_results.append(pair_result)
        finally:
            if servers:
                _stop_managed_servers(servers)
            _write_server_run(pair_root, servers, server_error)

        last_result = pair_results[-1]
        if last_result.status == "failed" and not args.continue_on_pair_failure:
            break

    result = compare_pair_results(
        pair_results,
        comparison_id=args.label,
        scenario_path=args.scenario,
        mode=args.mode,
        trials_per_pair=args.trials,
    )
    write_pair_matrix_report(result, out_root, replay_command=_replay_command(args))

    exit_code = 0
    if any(pair.status == "failed" for pair in pair_results) and not args.continue_on_pair_failure:
        exit_code = 1
    if args.json_only:
        print(json.dumps(result.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        _print_summary(result, out_root)
    return exit_code


def _parse_existing_pair_runs(values: list[str]) -> dict[str, str]:
    mapping: dict[str, str] = {}
    for item in values:
        if "=" not in item:
            raise ValueError(f"--existing-pair-run must use pair=path format: {item}")
        pair, path = item.split("=", 1)
        pair = pair.strip()
        path = path.strip()
        if not pair or not path:
            raise ValueError(f"--existing-pair-run must use pair=path format: {item}")
        if ":" not in pair:
            raise ValueError(f"--existing-pair-run pair must use orchestrator:executor format: {item}")
        orchestrator, executor = pair.split(":", 1)
        mapping[f"{orchestrator}->{executor}"] = path
        mapping[f"{orchestrator}:{executor}"] = path
    return mapping


def _start_managed_servers(args: argparse.Namespace, pair: Any) -> list[ManagedServer]:
    if _endpoint_json(args.base_orchestrator_port) is not None or _endpoint_json(args.base_executor_port) is not None:
        raise RuntimeError("One or both requested ports are already serving a local endpoint.")
    servers = [
        ManagedServer("orchestrator", pair.orchestrator_model_id, args.base_orchestrator_port),
        ManagedServer("executor", pair.executor_model_id, args.base_executor_port),
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


def _write_server_run(pair_root: Path, servers: list[ManagedServer], server_error: str | None) -> None:
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
    _write_json(pair_root / "server_run.json", payload)


def _server_strategy(args: argparse.Namespace, pair: Any) -> str:
    if args.mode == "fake":
        return "fake mode; no servers started"
    if not args.manage_servers:
        return "local mode using caller-provided endpoints"
    if pair.orchestrator_model_id == pair.executor_model_id:
        return "two separate llama-server endpoints for the same model on different ports"
    return "two separate llama-server endpoints on different ports"


def _server_note(args: argparse.Namespace, pair: Any) -> str:
    if args.mode == "fake":
        return "fake mode remained offline"
    return (
        f"orchestrator {pair.orchestrator_model_id} port {args.base_orchestrator_port}; "
        f"executor {pair.executor_model_id} port {args.base_executor_port}"
    )


def _remove_existing_out_root(out_root: Path) -> None:
    if not out_root.exists():
        return
    resolved = out_root.resolve()
    workspace = PROJECT_ROOT.resolve()
    try:
        resolved.relative_to(workspace)
    except ValueError as exc:
        raise RuntimeError(f"Refusing to remove output outside project root: {resolved}") from exc
    if resolved == workspace:
        raise RuntimeError("Refusing to remove project root.")
    shutil.rmtree(resolved)


def _base_url(port: int) -> str:
    return f"http://127.0.0.1:{port}/v1"


def _project_path(value: str | Path) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _write_json(path: Path, payload: Any) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")


def _replay_command(args: argparse.Namespace) -> str:
    action_flag = "--execute-actions" if args.execute_actions else "--no-execute-actions"
    server_flag = "--manage-servers" if args.manage_servers else "--no-manage-servers"
    continue_flag = " --continue-on-pair-failure" if args.continue_on_pair_failure else ""
    existing = " ".join(f"--existing-pair-run {item}" for item in args.existing_pair_run)
    reuse = " --reuse-existing" if args.reuse_existing else ""
    max_tokens = f"--orchestrator-max-tokens {args.orchestrator_max_tokens} " if args.orchestrator_max_tokens is not None else ""
    return (
        "python scripts\\run_orchestrator_executor_pair_matrix.py "
        f"--mode {args.mode} "
        f"--models-config {args.models_config} "
        f"--scenario {args.scenario} "
        f"--out-root {args.out_root} "
        f"--label {args.label} "
        f"--pairs {args.pairs} "
        f"{existing} "
        f"--trials {args.trials} "
        f"--base-orchestrator-port {args.base_orchestrator_port} "
        f"--base-executor-port {args.base_executor_port} "
        f"{server_flag} "
        f"--max-group-steps {args.max_group_steps or 1} "
        f"--max-steps-per-agent {args.max_steps_per_agent or 1} "
        f"{max_tokens}"
        f"--orchestrator-repair-attempts {args.orchestrator_repair_attempts} "
        f"--repair-attempts {args.repair_attempts} "
        f"{action_flag} "
        "--force"
        f"{reuse}"
        f"{continue_flag}"
    )


def _print_summary(result: Any, out_root: Path) -> None:
    print(f"comparison_id: {result.comparison_id}")
    print(f"mode: {result.mode}")
    print(f"pairs: {len(result.pairs)}")
    print(f"best_observed_pair: {result.best_observed_pair}")
    for row in result.rankings:
        print(
            f"rank {row['rank']}: {row['pair']} score={row['prototype_pair_rank_score']} "
            f"completed={row['completed_trials']} failed={row['failed_trials']}"
        )
    print(f"out_root: {out_root}")


if __name__ == "__main__":
    raise SystemExit(main())
