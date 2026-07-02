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
class ServerHandle:
    model_id: str
    wrapper_pid: int | None = None
    llama_pids: list[int] = field(default_factory=list)
    started_by_cli: bool = False
    already_running: bool = False
    logs_dir: Path | None = None


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run repeated local/fake model scenario trials and aggregate artifacts."
    )
    parser.add_argument("--models-config", default="configs/evaluation_models.json")
    parser.add_argument("--model-ids", required=True, help="Comma-separated evaluation model ids.")
    parser.add_argument("--scenario", default="configs/evaluation_scenarios/office_worker_basic_session.json")
    parser.add_argument("--out-root", required=True)
    parser.add_argument("--trials", type=int, default=3)
    parser.add_argument("--max-steps", type=int, default=5)
    parser.add_argument("--repair-attempts", type=int, default=1)
    parser.add_argument("--execute-actions", dest="execute_actions", action="store_true", default=True)
    parser.add_argument("--no-execute-actions", dest="execute_actions", action="store_false")
    parser.add_argument("--mode", choices=["fake", "local"], default="fake")
    parser.add_argument("--manage-server", dest="manage_server", action="store_true", default=False)
    parser.add_argument("--no-manage-server", dest="manage_server", action="store_false")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--label", default="repeated_model_trials")
    parser.add_argument("--continue-on-trial-failure", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from src.agent.evaluation_models import (
        preflight_evaluation_model,
        resolve_evaluation_model,
    )
    from src.agent.repeated_model_trials import (
        RepeatedTrialResult,
        RepeatedTrialSeriesResult,
        RepeatedTrialSpec,
        build_repeated_trials_comparison,
        prepare_output_root,
        write_repeated_trials_report,
        write_replay_command,
    )

    if args.trials < 1:
        parser.error("--trials must be >= 1")

    model_ids = [item.strip() for item in args.model_ids.split(",") if item.strip()]
    if not model_ids:
        parser.error("--model-ids must contain at least one id")

    try:
        out_root = prepare_output_root(_project_path(args.out_root), force=args.force)
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    series_results: list[RepeatedTrialSeriesResult] = []
    server_events: list[dict[str, Any]] = []
    exit_code = 0

    for model_id in model_ids:
        model_spec = None
        preflight = None
        server_handle: ServerHandle | None = None
        model_trials: list[RepeatedTrialResult] = []
        if args.mode == "local":
            try:
                model_spec = resolve_evaluation_model(model_id, _project_path(args.models_config))
                preflight = preflight_evaluation_model(model_spec, PROJECT_ROOT, require_model_file=True)
            except Exception as exc:
                print(f"ERROR: preflight failed for {model_id}: {exc}", file=sys.stderr)
                if not args.continue_on_trial_failure:
                    return 2
            if preflight is not None and preflight.status == "fail":
                print(f"ERROR: preflight failed for {model_id}: {preflight.model_dump(mode='json')}", file=sys.stderr)
                if not args.continue_on_trial_failure:
                    return 2
            try:
                server_handle = _ensure_runtime_for_model(
                    model_id=model_id,
                    model_spec=model_spec,
                    out_root=out_root,
                    manage_server=args.manage_server,
                )
                server_events.append(_server_event(server_handle, "ready"))
            except Exception as exc:
                print(f"ERROR: runtime not ready for {model_id}: {exc}", file=sys.stderr)
                if not args.continue_on_trial_failure:
                    return 2
                exit_code = 1

        try:
            for trial_number in range(1, args.trials + 1):
                trial_id = f"trial_{trial_number:03d}"
                run_id = f"{args.label}_{model_id}_{trial_id}"
                artifact_path = out_root / "runs" / model_id / trial_id
                spec = RepeatedTrialSpec(
                    model_id=model_id,
                    trial_id=trial_id,
                    run_id=run_id,
                    artifact_path=str(artifact_path),
                )
                if args.mode == "local" and server_handle is None:
                    result = RepeatedTrialResult(
                        spec=spec,
                        status="failed",
                        return_code=1,
                        error_message="runtime_not_ready",
                    )
                else:
                    result = _run_one_trial(
                        spec=spec,
                        scenario=args.scenario,
                        mode=args.mode,
                        models_config=args.models_config,
                        max_steps=args.max_steps,
                        repair_attempts=args.repair_attempts,
                        execute_actions=args.execute_actions,
                    )
                model_trials.append(result)
                if result.status == "failed":
                    exit_code = 1
                    print(f"trial_failed: {model_id} {trial_id}: {result.error_message}", file=sys.stderr)
                    if not args.continue_on_trial_failure:
                        break
        finally:
            if server_handle is not None and server_handle.started_by_cli:
                _stop_server(server_handle)
                server_events.append(_server_event(server_handle, "stopped"))

        series_results.append(
            RepeatedTrialSeriesResult(
                model_id=model_id,
                trials=model_trials,
            )
        )
        if exit_code and not args.continue_on_trial_failure:
            break

    comparison = build_repeated_trials_comparison(series_results, comparison_id=args.label)
    write_repeated_trials_report(comparison, out_root)
    (out_root / "server_events.json").write_text(
        json.dumps(server_events, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )
    write_replay_command(out_root, _replay_command(args))

    if args.json_only:
        print(json.dumps(comparison.model_dump(mode="json"), ensure_ascii=False, indent=2))
    else:
        _print_summary(comparison, out_root)

    return 0 if exit_code == 0 or args.continue_on_trial_failure else exit_code


def _run_one_trial(
    *,
    spec: Any,
    scenario: str,
    mode: str,
    models_config: str,
    max_steps: int,
    repair_attempts: int,
    execute_actions: bool,
) -> Any:
    from src.agent.model_behavior_comparison import load_model_run_artifact
    from src.agent.repeated_model_trials import RepeatedTrialResult

    cmd = [
        sys.executable,
        "scripts/run_agent_scenario.py",
        "--mode",
        mode,
        "--model-id",
        spec.model_id,
        "--models-config",
        models_config,
        "--scenario",
        scenario,
        "--out-dir",
        spec.artifact_path,
        "--run-id",
        spec.run_id,
        "--max-steps",
        str(max_steps),
        "--repair-attempts",
        str(repair_attempts),
        "--force",
    ]
    cmd.append("--execute-actions" if execute_actions else "--no-execute-actions")
    completed = subprocess.run(
        cmd,
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    artifact_path = Path(spec.artifact_path)
    artifact_path.mkdir(parents=True, exist_ok=True)
    (artifact_path / "trial_command_stdout.log").write_text(completed.stdout, encoding="utf-8")
    (artifact_path / "trial_command_stderr.log").write_text(completed.stderr, encoding="utf-8")
    if (artifact_path / "manifest.json").exists():
        artifact = load_model_run_artifact(artifact_path)
        return RepeatedTrialResult(
            spec=spec,
            status="completed" if completed.returncode == 0 and artifact.status == "complete" else "failed",
            return_code=completed.returncode,
            error_message=None if completed.returncode == 0 else completed.stderr.strip(),
            artifact=artifact,
            metrics=artifact.metrics,
        )
    return RepeatedTrialResult(
        spec=spec,
        status="failed",
        return_code=completed.returncode,
        error_message=completed.stderr.strip() or "trial_artifact_missing",
    )


def _ensure_runtime_for_model(*, model_id: str, model_spec: Any, out_root: Path, manage_server: bool) -> ServerHandle:
    endpoint = _models_endpoint()
    if endpoint is not None:
        if _endpoint_matches_model(endpoint, model_spec):
            return ServerHandle(model_id=model_id, already_running=True)
        raise RuntimeError(
            f"127.0.0.1:8080 is already serving a different model: {endpoint}. "
            "Refusing to reuse the endpoint silently."
        )
    if not manage_server:
        raise RuntimeError("runtime endpoint is not ready and --no-manage-server was selected")

    logs_dir = out_root / "server_logs" / model_id
    logs_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = logs_dir / "llama_server_stdout.log"
    stderr_path = logs_dir / "llama_server_stderr.log"
    before_pids = _llama_server_pids()
    proc = subprocess.Popen(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            ".\\scripts\\start_llama_server.ps1",
            "-ModelId",
            model_id,
        ],
        cwd=PROJECT_ROOT,
        stdout=stdout_path.open("w", encoding="utf-8"),
        stderr=stderr_path.open("w", encoding="utf-8"),
        text=True,
    )
    handle = ServerHandle(
        model_id=model_id,
        wrapper_pid=proc.pid,
        started_by_cli=True,
        logs_dir=logs_dir,
    )
    for _ in range(90):
        time.sleep(2)
        endpoint = _models_endpoint()
        if endpoint is not None:
            if not _endpoint_matches_model(endpoint, model_spec):
                raise RuntimeError(f"started endpoint does not match expected model {model_id}: {endpoint}")
            handle.llama_pids = sorted(set(_llama_server_pids()) - set(before_pids))
            return handle
        if proc.poll() is not None:
            raise RuntimeError(f"llama-server wrapper exited early with code {proc.returncode}")
    raise RuntimeError(f"timeout waiting for llama-server endpoint for {model_id}")


def _stop_server(handle: ServerHandle) -> None:
    ids = list(dict.fromkeys([*handle.llama_pids, handle.wrapper_pid]))
    ids = [pid for pid in ids if pid]
    if not ids:
        return
    quoted = ",".join(str(pid) for pid in ids)
    subprocess.run(
        [
            "powershell",
            "-NoProfile",
            "-Command",
            f"$ids=@({quoted}); foreach($id in $ids){{Stop-Process -Id $id -Force -ErrorAction SilentlyContinue}}",
        ],
        cwd=PROJECT_ROOT,
        text=True,
        capture_output=True,
        check=False,
    )
    time.sleep(1)


def _models_endpoint() -> dict[str, Any] | None:
    try:
        with urllib.request.urlopen("http://127.0.0.1:8080/v1/models", timeout=3) as response:
            return json.loads(response.read().decode("utf-8"))
    except (urllib.error.URLError, TimeoutError, json.JSONDecodeError):
        return None


def _endpoint_matches_model(endpoint: dict[str, Any], model_spec: Any) -> bool:
    names: set[str] = set()
    for item in endpoint.get("models", []) + endpoint.get("data", []):
        for key in ["name", "model", "id"]:
            if item.get(key):
                names.add(str(item[key]))
    expected = {
        str(model_spec.model_name),
        Path(model_spec.gguf_path).name,
    }
    return bool(names & expected)


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


def _project_path(value: str) -> Path:
    path = Path(value)
    if path.is_absolute():
        return path
    return PROJECT_ROOT / path


def _server_event(handle: ServerHandle, event: str) -> dict[str, Any]:
    return {
        "event": event,
        "model_id": handle.model_id,
        "wrapper_pid": handle.wrapper_pid,
        "llama_pids": handle.llama_pids,
        "started_by_cli": handle.started_by_cli,
        "already_running": handle.already_running,
        "logs_dir": str(handle.logs_dir) if handle.logs_dir else None,
    }


def _replay_command(args: argparse.Namespace) -> str:
    action_flag = "--execute-actions" if args.execute_actions else "--no-execute-actions"
    server_flag = "--manage-server" if args.manage_server else "--no-manage-server"
    return (
        "python scripts\\run_repeated_model_trials.py "
        f"--mode {args.mode} "
        f"--models-config {args.models_config} "
        f"--model-ids {args.model_ids} "
        f"--scenario {args.scenario} "
        f"--out-root {args.out_root} "
        f"--label {args.label} "
        f"--trials {args.trials} "
        f"--max-steps {args.max_steps} "
        f"--repair-attempts {args.repair_attempts} "
        f"{action_flag} "
        f"{server_flag} "
        "--force"
        + (" --continue-on-trial-failure" if args.continue_on_trial_failure else "")
    )


def _print_summary(comparison: Any, out_root: Path) -> None:
    print(f"comparison_id: {comparison.comparison_id}")
    print(f"status: {comparison.status}")
    print(f"protocol_compatible: {comparison.protocol_compatible}")
    print(f"out_root: {out_root}")
    print("")
    print("model_id,trials,failed,mean_initial_validation,mean_final_validation,mean_execution_success,mean_normal_activity,mean_selection_latency")
    for model_id, aggregate in comparison.aggregates.items():
        metrics = aggregate.metrics
        print(
            f"{model_id},{aggregate.trial_count},{aggregate.failed_trial_count},"
            f"{_stat(metrics, 'initial_validation_accept_rate')},"
            f"{_stat(metrics, 'final_validation_accept_rate')},"
            f"{_stat(metrics, 'execution_success_rate')},"
            f"{_stat(metrics, 'normal_activity_score')},"
            f"{_stat(metrics, 'average_selection_latency_ms')}"
        )
    print("")
    print("metric_winners:")
    for winner in comparison.metric_winners:
        print(f"- {winner.name}: {winner.winner}")


def _stat(metrics: dict[str, Any], name: str) -> Any:
    return (metrics.get(name) or {}).get("mean")


if __name__ == "__main__":
    raise SystemExit(main())
