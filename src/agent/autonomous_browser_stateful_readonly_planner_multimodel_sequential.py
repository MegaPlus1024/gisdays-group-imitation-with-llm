from __future__ import annotations

import json
import socket
import subprocess
import time
import urllib.error
import urllib.parse
import urllib.request
from collections import defaultdict
from collections.abc import Callable, Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .autonomous_browser_stateful_readonly_planner_multimodel_benchmark import (
    DEFAULT_PACKET_MANIFEST_FILENAME,
)


CONFIG_SCHEMA_VERSION = (
    "autonomous_browser_stateful_readonly_planner_multimodel_sequential_run_config_v1"
)
SUMMARY_SCHEMA_VERSION = (
    "autonomous_browser_stateful_readonly_planner_multimodel_sequential_summary_v1"
)
DEFAULT_RUN_ID = "stateful_readonly_planner_multimodel_sequential"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/stateful_readonly_planner_multimodel_sequential"
DEFAULT_SUMMARY_FILENAME = "stateful_readonly_planner_multimodel_sequential_summary.json"
DEFAULT_REQUEST_TIMEOUT_SEC = 180.0
DEFAULT_STARTUP_TIMEOUT_SEC = 180.0
ALLOWED_LOCAL_HOSTS = {"127.0.0.1", "localhost"}
DEFAULT_LIMITATIONS = (
    "frozen raw benchmark runner only",
    "shared task prompt across enabled models",
    "no browser execution",
    "no Playwright execution",
    "not production browser automation",
)
DEFAULT_REQUEST_ERROR_LIMIT = 240


@dataclass(frozen=True)
class SequentialHttpResponse:
    status_code: int
    body: bytes
    headers: Mapping[str, str]


TransportFn = Callable[[str, str, bytes | None, float], SequentialHttpResponse]
TimeFn = Callable[[], float]
SleepFn = Callable[[float], None]
PortInspectionFn = Callable[[tuple[int, ...]], list[dict[str, Any]]]
PortStopFn = Callable[[list[dict[str, Any]]], list[dict[str, Any]]]


@dataclass(frozen=True)
class StartedServer:
    model_alias: str
    pid: int | None
    started_by_script: bool
    log_dir: str | None = None


ServerStartFn = Callable[["SequentialModelProfile", Path, Path], StartedServer]
ServerStopFn = Callable[[StartedServer], None]


@dataclass(frozen=True)
class SequentialModelProfile:
    model_alias: str
    enabled: bool
    endpoint: str
    models_endpoint: str
    port: int
    ctx_size: int
    cpu_only: bool
    request_timeout_sec: float
    startup_timeout_sec: float
    start_script: str
    start_model_id: str
    start_api_model: str
    notes: tuple[str, ...] = ()

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SequentialModelProfile":
        model_alias = _safe_identifier(payload.get("model_alias"), "model_alias")
        enabled = _required_bool(payload.get("enabled", True), "enabled")
        endpoint = _safe_local_http_url(payload.get("endpoint"), "endpoint")
        models_endpoint = _safe_local_http_url(payload.get("models_endpoint"), "models_endpoint")
        port = _required_int(payload.get("port"), "port")
        ctx_size = _required_int(payload.get("ctx_size"), "ctx_size")
        cpu_only = _required_bool(payload.get("cpu_only", True), "cpu_only")
        request_timeout_sec = _required_float(
            payload.get("request_timeout_sec", DEFAULT_REQUEST_TIMEOUT_SEC),
            "request_timeout_sec",
        )
        startup_timeout_sec = _required_float(
            payload.get("startup_timeout_sec", DEFAULT_STARTUP_TIMEOUT_SEC),
            "startup_timeout_sec",
        )
        start_script = _safe_relative_path(
            payload.get("start_script", "scripts/start_llama_server.ps1"),
            "start_script",
        )
        start_model_id = _safe_identifier(
            payload.get("start_model_id", model_alias),
            "start_model_id",
        )
        start_api_model = _safe_identifier(
            payload.get("start_api_model", model_alias),
            "start_api_model",
        )
        notes = tuple(
            str(item).strip()
            for item in payload.get("notes", [])
            if isinstance(item, str) and item.strip()
        )
        if None in {
            model_alias,
            endpoint,
            models_endpoint,
            port,
            ctx_size,
            request_timeout_sec,
            startup_timeout_sec,
            start_script,
            start_model_id,
            start_api_model,
        }:
            raise ValueError("model profile contains invalid fields.")
        if port <= 0:
            raise ValueError("port must be positive.")
        if ctx_size <= 0:
            raise ValueError("ctx_size must be positive.")
        if request_timeout_sec <= 0 or startup_timeout_sec <= 0:
            raise ValueError("timeouts must be positive.")
        return cls(
            model_alias=model_alias,
            enabled=enabled,
            endpoint=endpoint,
            models_endpoint=models_endpoint,
            port=port,
            ctx_size=ctx_size,
            cpu_only=cpu_only,
            request_timeout_sec=request_timeout_sec,
            startup_timeout_sec=startup_timeout_sec,
            start_script=start_script,
            start_model_id=start_model_id,
            start_api_model=start_api_model,
            notes=notes,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "model_alias": self.model_alias,
            "enabled": self.enabled,
            "endpoint": self.endpoint,
            "models_endpoint": self.models_endpoint,
            "port": self.port,
            "ctx_size": self.ctx_size,
            "cpu_only": self.cpu_only,
            "request_timeout_sec": self.request_timeout_sec,
            "startup_timeout_sec": self.startup_timeout_sec,
            "start_script": self.start_script,
            "start_model_id": self.start_model_id,
            "start_api_model": self.start_api_model,
            "notes": list(self.notes),
        }


@dataclass(frozen=True)
class SequentialRunConfig:
    schema_version: str
    run_id: str
    output_dir: str
    model_profiles: tuple[SequentialModelProfile, ...]
    limitations: tuple[str, ...]

    @classmethod
    def from_dict(cls, payload: Mapping[str, Any]) -> "SequentialRunConfig":
        schema_version = str(payload.get("schema_version", "")).strip()
        if schema_version != CONFIG_SCHEMA_VERSION:
            raise ValueError("schema_version must match the sequential run config schema.")
        run_id = _safe_identifier(payload.get("run_id", DEFAULT_RUN_ID), "run_id")
        output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR), "output_dir")
        profiles_payload = payload.get("model_profiles")
        if not isinstance(profiles_payload, list) or not profiles_payload:
            raise ValueError("model_profiles must be a non-empty array.")
        model_profiles = tuple(
            SequentialModelProfile.from_dict(item)
            for item in profiles_payload
            if isinstance(item, Mapping)
        )
        if len(model_profiles) != len(profiles_payload):
            raise ValueError("every model profile must be an object.")
        aliases = [profile.model_alias for profile in model_profiles]
        if len(set(aliases)) != len(aliases):
            raise ValueError("model profile aliases must be unique.")
        if run_id is None or output_dir is None:
            raise ValueError("run_id and output_dir must be valid.")
        limitations = tuple(
            str(item).strip()
            for item in payload.get("limitations", [])
            if isinstance(item, str) and item.strip()
        ) or DEFAULT_LIMITATIONS
        return cls(
            schema_version=schema_version,
            run_id=run_id,
            output_dir=output_dir,
            model_profiles=model_profiles,
            limitations=limitations,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "run_id": self.run_id,
            "output_dir": self.output_dir,
            "model_profiles": [profile.to_dict() for profile in self.model_profiles],
            "limitations": list(self.limitations),
        }


def run_autonomous_browser_stateful_readonly_planner_multimodel_sequential(
    *,
    packet_dir: str | Path,
    run_config_artifact: str | Path | Mapping[str, Any],
    repo_root: str | Path | None = None,
    selected_models: tuple[str, ...] = (),
    start_servers: bool = True,
    dry_run: bool = False,
    skip_existing: bool = False,
    fail_fast: bool = False,
    allow_existing_benchmark_servers: bool = False,
    stop_existing_benchmark_servers: bool = False,
    transport: TransportFn | None = None,
    time_fn: TimeFn | None = None,
    sleep_fn: SleepFn | None = None,
    server_start_fn: ServerStartFn | None = None,
    server_stop_fn: ServerStopFn | None = None,
    port_inspector_fn: PortInspectionFn | None = None,
    port_stopper_fn: PortStopFn | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    if dry_run:
        start_servers = False
    server_mode = _determine_server_mode(dry_run=dry_run, start_servers=start_servers)
    config_result = _load_run_config(run_config_artifact)
    if config_result["status"] != "ok":
        return _failure_summary(
            run_id=config_result.get("run_id"),
            output_dir=config_result.get("output_dir"),
            error_code=str(config_result.get("error_code") or "config_validation_failed"),
            limitations=tuple(config_result.get("limitations") or DEFAULT_LIMITATIONS),
            server_mode=server_mode,
        )

    packet_result = _load_packet_manifest(repo, packet_dir)
    if packet_result["status"] != "ok":
        return _failure_summary(
            run_id=str(config_result["config"]["run_id"]),
            output_dir=str(config_result["config"]["output_dir"]),
            error_code=str(packet_result.get("error_code") or "packet_manifest_missing"),
            limitations=tuple(config_result["config"].get("limitations") or DEFAULT_LIMITATIONS),
            server_mode=server_mode,
            diagnostics={"packet_dir": _repo_relative_path(repo, Path(packet_dir))},
        )

    config = SequentialRunConfig.from_dict(config_result["config"])
    manifest = packet_result["packet"]
    output_root = repo / config.output_dir
    output_root.mkdir(parents=True, exist_ok=True)
    summary_path = output_root / DEFAULT_SUMMARY_FILENAME

    filters = tuple(item for item in selected_models if item)
    profiles = [profile for profile in config.model_profiles if profile.enabled]
    if filters:
        profiles = [profile for profile in profiles if profile.model_alias in filters]
    if not profiles:
        summary = _failure_summary(
            run_id=config.run_id,
            output_dir=config.output_dir,
            error_code="no_enabled_models_selected",
            limitations=config.limitations,
            server_mode=server_mode,
        )
        _write_json(summary_path, summary)
        return summary

    requests_by_model: dict[str, list[dict[str, Any]]] = defaultdict(list)
    for record in manifest["request_records"]:
        alias = str(record.get("model_alias") or "")
        if alias:
            requests_by_model[alias].append(dict(record))

    transport_fn = transport or _urllib_transport
    time_now = time_fn or time.perf_counter
    sleeper = sleep_fn or time.sleep
    start_fn = server_start_fn or _start_server
    stop_fn = server_stop_fn or _stop_server
    inspect_ports = port_inspector_fn or _inspect_benchmark_ports
    stop_ports = port_stopper_fn or _stop_benchmark_port_bindings

    preflight_summary = {
        "preflight_bypassed": allow_existing_benchmark_servers,
        "stop_existing_benchmark_servers": stop_existing_benchmark_servers,
        "inspected_ports": [],
        "occupied_bindings": [],
        "stopped_bindings": [],
    }
    if server_mode == "started_by_runner":
        configured_ports = tuple(sorted({profile.port for profile in config.model_profiles}))
        selected_ports = tuple(sorted({profile.port for profile in profiles}))
        preflight = _run_port_preflight(
            configured_ports=configured_ports,
            selected_ports=selected_ports,
            allow_existing_benchmark_servers=allow_existing_benchmark_servers,
            stop_existing_benchmark_servers=stop_existing_benchmark_servers,
            port_inspector=inspect_ports,
            port_stopper=stop_ports,
        )
        preflight_summary = dict(preflight["summary"])
        if preflight["status"] != "ok":
            summary = _failure_summary(
                run_id=config.run_id,
                output_dir=config.output_dir,
                error_code=str(preflight.get("error_code") or "benchmark_ports_occupied"),
                limitations=config.limitations,
                server_mode=server_mode,
                diagnostics={"port_preflight": preflight_summary},
            )
            _write_json(summary_path, summary)
            return summary

    request_results: list[dict[str, Any]] = []
    model_results: list[dict[str, Any]] = []
    models_attempted = 0
    models_completed = 0
    models_failed = 0
    requests_total = sum(len(requests_by_model.get(profile.model_alias, [])) for profile in profiles)
    requests_completed = 0
    requests_failed = 0
    requests_skipped_existing = 0
    model_execution = False
    stopped_early = False

    for profile in profiles:
        records = requests_by_model.get(profile.model_alias, [])
        model_started = False
        started_server: StartedServer | None = None
        model_error: str | None = None
        per_model_completed = 0
        per_model_failed = 0
        per_model_skipped_existing = 0
        model_start_time = time_now()
        startup_elapsed_seconds = 0.0
        endpoint_ready = False
        shutdown_attempted = False
        shutdown_succeeded: bool | None = None
        models_attempted += 1
        try:
            if dry_run:
                for record in records:
                    request_results.append(
                        _dry_run_request_result(profile=profile, record=record, repo_root=repo)
                    )
            else:
                if start_servers:
                    startup_begin = time_now()
                    started_server = start_fn(profile, repo, output_root)
                    model_started = started_server.started_by_script
                    startup_elapsed_seconds = round(time_now() - startup_begin, 6)
                ready = _wait_for_models_endpoint(
                    profile=profile,
                    transport=transport_fn,
                    sleep_fn=sleeper,
                    time_fn=time_now,
                )
                model_execution = True
                startup_elapsed_seconds = max(
                    startup_elapsed_seconds,
                    round(float(ready.get("elapsed_seconds", 0.0)), 6),
                )
                if not ready["ready"]:
                    endpoint_ready = False
                    model_error = str(ready.get("error_code") or "models_endpoint_not_ready")
                    failure = _model_level_request_failures(
                        profile=profile,
                        records=records,
                        repo_root=repo,
                        error_code=model_error,
                        error_type=str(ready.get("error_type") or "models_endpoint_not_ready"),
                        error_message=str(ready.get("error_message") or "models endpoint was not ready."),
                        server_started_by_runner=model_started,
                    )
                    request_results.extend(failure)
                    per_model_failed += len(failure)
                    requests_failed += len(failure)
                    if fail_fast:
                        stopped_early = True
                else:
                    endpoint_ready = True
                    for record in records:
                        request_result = _run_one_request(
                            profile=profile,
                            record=record,
                            repo_root=repo,
                            transport=transport_fn,
                            time_fn=time_now,
                            skip_existing=skip_existing,
                            server_started_by_runner=model_started,
                        )
                        request_results.append(request_result)
                        if request_result["status"] == "succeeded":
                            per_model_completed += 1
                            requests_completed += 1
                            model_execution = True
                        elif request_result["status"] == "skipped_existing":
                            per_model_skipped_existing += 1
                            requests_skipped_existing += 1
                        else:
                            per_model_failed += 1
                            requests_failed += 1
                            model_execution = True
                            model_error = str(request_result.get("error_code") or "request_failed")
                            if fail_fast:
                                stopped_early = True
                                break
            model_status = "dry_run" if dry_run else ("succeeded" if per_model_failed == 0 and model_error is None else "failed")
        except Exception as exc:  # pragma: no cover - kept for defensive runtime safety
            error_code, error_type, error_message = _classify_request_exception(exc)
            model_error = error_code
            failure = _model_level_request_failures(
                profile=profile,
                records=records,
                repo_root=repo,
                error_code=error_code,
                error_type=error_type,
                error_message=error_message,
                server_started_by_runner=model_started,
            )
            request_results.extend(failure)
            per_model_failed += len(failure)
            requests_failed += len(failure)
            model_status = "failed"
            if fail_fast:
                stopped_early = True
        finally:
            if started_server is not None:
                shutdown_attempted = True
                try:
                    stop_fn(started_server)
                except Exception:
                    shutdown_succeeded = False
                else:
                    shutdown_succeeded = True

        if model_status == "failed":
            models_failed += 1
        else:
            models_completed += 1
        model_results.append(
            {
                "model_alias": profile.model_alias,
                "status": model_status,
                "error_code": model_error,
                "server_started_by_runner": model_started,
                "endpoint_ready": endpoint_ready,
                "startup_elapsed_seconds": startup_elapsed_seconds,
                "shutdown_attempted": shutdown_attempted,
                "shutdown_succeeded": shutdown_succeeded,
                "requests_total": len(records),
                "requests_completed": per_model_completed,
                "requests_failed": per_model_failed,
                "requests_skipped_existing": per_model_skipped_existing,
                "elapsed_seconds": round(time_now() - model_start_time, 6),
                "endpoint_used": profile.endpoint,
                "models_endpoint": profile.models_endpoint,
                "ctx_size": profile.ctx_size,
                "cpu_only": profile.cpu_only,
                "port": profile.port,
                "request_timeout_sec": profile.request_timeout_sec,
                "startup_timeout_sec": profile.startup_timeout_sec,
            }
        )
        if stopped_early:
            break

    if dry_run:
        status = "succeeded"
        error_code = None
        no_runtime_execution = True
    elif models_failed or requests_failed:
        status = "completed_with_failures"
        error_code = "sequential_run_failed"
        no_runtime_execution = False
    else:
        status = "succeeded"
        error_code = None
        no_runtime_execution = False

    summary = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": status,
        "error_code": error_code,
        "run_id": config.run_id,
        "packet_dir": _repo_relative_path(repo, packet_result["packet_root"]),
        "output_dir": config.output_dir,
        "models_total": len(profiles),
        "models_attempted": models_attempted,
        "models_completed": models_completed,
        "models_failed": models_failed,
        "requests_total": requests_total,
        "requests_completed": requests_completed,
        "requests_failed": requests_failed,
        "requests_skipped_existing": requests_skipped_existing,
        "selected_models": [profile.model_alias for profile in profiles],
        "dry_run": dry_run,
        "skip_existing": skip_existing,
        "fail_fast": fail_fast,
        "start_servers": start_servers,
        "server_mode": server_mode,
        "preflight_bypassed": preflight_summary["preflight_bypassed"],
        "port_preflight": preflight_summary,
        "model_results": model_results,
        "request_results": request_results,
        "scenario_catalog": manifest.get("scenario_catalog"),
        "prompt_contract_mode": manifest.get("prompt_contract_mode"),
        "no_runtime_execution": no_runtime_execution,
        "model_execution": model_execution,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
        "fixture_only": True,
        "limitations": list(config.limitations),
    }
    _write_json(summary_path, summary)
    return summary


def _load_run_config(run_config_artifact: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    try:
        if isinstance(run_config_artifact, Mapping):
            payload = dict(run_config_artifact)
        else:
            payload = json.loads(Path(run_config_artifact).read_text(encoding="utf-8-sig"))
        if not isinstance(payload, Mapping):
            raise ValueError("config root must be an object")
        config = SequentialRunConfig.from_dict(payload)
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "run_id": _safe_identifier(payload.get("run_id"), "run_id")  # type: ignore[name-defined]
            if "payload" in locals() and isinstance(payload, Mapping)
            else None,
            "output_dir": _safe_relative_path(payload.get("output_dir"), "output_dir")  # type: ignore[name-defined]
            if "payload" in locals() and isinstance(payload, Mapping)
            else None,
            "limitations": list(DEFAULT_LIMITATIONS),
            "error_message": str(exc),
        }
    return {"status": "ok", "config": config.to_dict() if hasattr(config, "to_dict") else payload}


def _load_packet_manifest(repo_root: Path, packet_dir: str | Path) -> dict[str, Any]:
    packet_root = packet_dir if isinstance(packet_dir, Path) else Path(packet_dir)
    if not packet_root.is_absolute():
        packet_root = repo_root / packet_root
    manifest_path = packet_root / DEFAULT_PACKET_MANIFEST_FILENAME
    if not manifest_path.exists():
        return {"status": "failed", "error_code": "packet_manifest_missing", "packet_root": packet_root}
    try:
        payload = json.loads(manifest_path.read_text(encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError):
        return {"status": "failed", "error_code": "config_validation_failed", "packet_root": packet_root}
    if not isinstance(payload, Mapping):
        return {"status": "failed", "error_code": "config_validation_failed", "packet_root": packet_root}
    return {"status": "ok", "packet": dict(payload), "packet_root": packet_root}


def _determine_server_mode(*, dry_run: bool, start_servers: bool) -> str:
    if dry_run:
        return "dry_run"
    if start_servers:
        return "started_by_runner"
    return "existing_servers"


def _dry_run_request_result(
    *,
    profile: SequentialModelProfile,
    record: Mapping[str, Any],
    repo_root: Path,
) -> dict[str, Any]:
    request_path = repo_root / str(record["request_path"])
    response_path = repo_root / str(record["response_path"])
    raw_output_path = repo_root / str(record["raw_output_path"])
    return {
        "model_alias": profile.model_alias,
        "scenario_id": record["scenario_id"],
        "trial_id": record["trial_id"],
        "trial_label": record["trial_label"],
        "request_path": _repo_relative_path(repo_root, request_path),
        "response_path": _repo_relative_path(repo_root, response_path),
        "raw_output_path": _repo_relative_path(repo_root, raw_output_path),
        "status": "dry_run",
        "error_code": None,
        "error_type": None,
        "error_message": None,
        "finish_reason": None,
        "content_length": 0,
        "elapsed_seconds": 0.0,
        "endpoint": profile.endpoint,
        "endpoint_used": profile.endpoint,
        "server_started_by_runner": False,
        "skipped_existing": False,
    }


def _request_failure_result(
    *,
    profile: SequentialModelProfile,
    record: Mapping[str, Any],
    repo_root: Path,
    request_path: Path,
    response_path: Path,
    raw_output_path: Path,
    elapsed_seconds: float,
    server_started_by_runner: bool,
    error_code: str,
    error_type: str,
    error_message: str,
    write_timing_path: Path,
    response_text: str | None = None,
    response_json: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    failure = {
        "model_alias": profile.model_alias,
        "scenario_id": record["scenario_id"],
        "trial_id": record["trial_id"],
        "trial_label": record["trial_label"],
        "request_path": _repo_relative_path(repo_root, request_path),
        "response_path": _repo_relative_path(repo_root, response_path),
        "raw_output_path": _repo_relative_path(repo_root, raw_output_path),
        "status": "failed",
        "error_code": error_code,
        "error_type": error_type,
        "error_message": error_message,
        "finish_reason": None,
        "content_length": 0,
        "elapsed_seconds": elapsed_seconds,
        "endpoint": profile.endpoint,
        "endpoint_used": profile.endpoint,
        "models_endpoint": profile.models_endpoint,
        "server_started_by_runner": server_started_by_runner,
        "skipped_existing": False,
        "no_runtime_execution": False,
        "model_execution": True,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
    }
    try:
        if response_json is not None:
            _write_text_file(
                response_path,
                json.dumps(response_json, ensure_ascii=False, indent=2, sort_keys=True),
                encoding="utf-8",
            )
        elif response_text is not None:
            _write_text_file(response_path, response_text, encoding="utf-8")
    except OSError:
        pass
    try:
        _write_json(write_timing_path, failure)
    except OSError:
        pass
    return failure


def _model_level_request_failures(
    *,
    profile: SequentialModelProfile,
    records: list[dict[str, Any]],
    repo_root: Path,
    error_code: str,
    error_type: str,
    error_message: str,
    server_started_by_runner: bool,
) -> list[dict[str, Any]]:
    failures: list[dict[str, Any]] = []
    for record in records:
        request_path = repo_root / str(record["request_path"])
        response_path = repo_root / str(record["response_path"])
        raw_output_path = repo_root / str(record["raw_output_path"])
        failures.append(
            {
                "model_alias": profile.model_alias,
                "scenario_id": record["scenario_id"],
                "trial_id": record["trial_id"],
                "trial_label": record["trial_label"],
                "request_path": _repo_relative_path(repo_root, request_path),
                "response_path": _repo_relative_path(repo_root, response_path),
                "raw_output_path": _repo_relative_path(repo_root, raw_output_path),
                "status": "failed",
                "error_code": error_code,
                "error_type": error_type,
                "error_message": error_message,
                "finish_reason": None,
                "content_length": 0,
                "elapsed_seconds": 0.0,
                "endpoint": profile.endpoint,
                "endpoint_used": profile.endpoint,
                "models_endpoint": profile.models_endpoint,
                "server_started_by_runner": server_started_by_runner,
                "skipped_existing": False,
            }
        )
    return failures


def _run_one_request(
    *,
    profile: SequentialModelProfile,
    record: Mapping[str, Any],
    repo_root: Path,
    transport: TransportFn,
    time_fn: TimeFn,
    skip_existing: bool,
    server_started_by_runner: bool,
) -> dict[str, Any]:
    request_path = repo_root / str(record["request_path"])
    response_path = repo_root / str(record["response_path"])
    raw_output_path = repo_root / str(record["raw_output_path"])
    timing_path = response_path.parent / "per_request_timing.json"

    if skip_existing and response_path.exists() and raw_output_path.exists():
        return {
            "model_alias": profile.model_alias,
            "scenario_id": record["scenario_id"],
            "trial_id": record["trial_id"],
            "trial_label": record["trial_label"],
            "request_path": _repo_relative_path(repo_root, request_path),
            "response_path": _repo_relative_path(repo_root, response_path),
            "raw_output_path": _repo_relative_path(repo_root, raw_output_path),
            "status": "skipped_existing",
            "error_code": None,
            "error_type": None,
            "error_message": None,
            "finish_reason": None,
            "content_length": len(_read_text_file(raw_output_path, encoding="utf-8-sig")),
            "elapsed_seconds": 0.0,
            "endpoint": profile.endpoint,
            "endpoint_used": profile.endpoint,
            "server_started_by_runner": server_started_by_runner,
            "skipped_existing": True,
        }
    start = time_fn()
    try:
        payload = json.loads(_read_text_file(request_path, encoding="utf-8-sig"))
    except (OSError, json.JSONDecodeError) as exc:
        return _request_failure_result(
            profile=profile,
            record=record,
            repo_root=repo_root,
            request_path=request_path,
            response_path=response_path,
            raw_output_path=raw_output_path,
            elapsed_seconds=round(time_fn() - start, 6),
            server_started_by_runner=server_started_by_runner,
            error_code="request_payload_read_failed",
            error_type="request_payload_read_failed",
            error_message=_bounded_error_message("request payload could not be read or parsed."),
            write_timing_path=timing_path,
        )

    body = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    try:
        response = transport("POST", profile.endpoint, body, profile.request_timeout_sec)
    except Exception as exc:
        error_code, error_type, error_message = _classify_request_exception(exc)
        return _request_failure_result(
            profile=profile,
            record=record,
            repo_root=repo_root,
            request_path=request_path,
            response_path=response_path,
            raw_output_path=raw_output_path,
            elapsed_seconds=round(time_fn() - start, 6),
            server_started_by_runner=server_started_by_runner,
            error_code=error_code,
            error_type=error_type,
            error_message=error_message,
            write_timing_path=timing_path,
        )

    elapsed_seconds = round(time_fn() - start, 6)
    response_text = _decode_body(response.body)
    response_json: Mapping[str, Any] | None = None
    finish_reason: str | None = None
    content = ""

    if response.status_code >= 400:
        return _request_failure_result(
            profile=profile,
            record=record,
            repo_root=repo_root,
            request_path=request_path,
            response_path=response_path,
            raw_output_path=raw_output_path,
            elapsed_seconds=elapsed_seconds,
            server_started_by_runner=server_started_by_runner,
            error_code="endpoint_request_failed",
            error_type="http_error",
            error_message=_bounded_error_message(f"http status {response.status_code}"),
            response_text=response_text,
            write_timing_path=timing_path,
        )

    try:
        response_json = json.loads(response_text or "{}")
    except json.JSONDecodeError:
        return _request_failure_result(
            profile=profile,
            record=record,
            repo_root=repo_root,
            request_path=request_path,
            response_path=response_path,
            raw_output_path=raw_output_path,
            elapsed_seconds=elapsed_seconds,
            server_started_by_runner=server_started_by_runner,
            error_code="response_parse_failed",
            error_type="response_parse_failed",
            error_message=_bounded_error_message("response body was not valid JSON."),
            response_text=response_text,
            write_timing_path=timing_path,
        )

    finish_reason = _extract_finish_reason(response_json)
    content = _extract_response_content(response_json)
    if not content:
        return _request_failure_result(
            profile=profile,
            record=record,
            repo_root=repo_root,
            request_path=request_path,
            response_path=response_path,
            raw_output_path=raw_output_path,
            elapsed_seconds=elapsed_seconds,
            server_started_by_runner=server_started_by_runner,
            error_code="response_shape_invalid",
            error_type="response_shape_invalid",
            error_message=_bounded_error_message("response JSON did not include choices[0].message.content."),
            response_json=response_json,
            write_timing_path=timing_path,
        )

    try:
        _write_text_file(
            response_path,
            json.dumps(response_json, ensure_ascii=False, indent=2, sort_keys=True),
            encoding="utf-8",
        )
        _write_text_file(raw_output_path, content, encoding="utf-8")
    except OSError:
        return _request_failure_result(
            profile=profile,
            record=record,
            repo_root=repo_root,
            request_path=request_path,
            response_path=response_path,
            raw_output_path=raw_output_path,
            elapsed_seconds=elapsed_seconds,
            server_started_by_runner=server_started_by_runner,
            error_code="file_write_failed",
            error_type="file_write_failed",
            error_message=_bounded_error_message("response artifacts could not be written."),
            response_json=response_json,
            write_timing_path=timing_path,
        )

    timing_payload = {
        "model_alias": profile.model_alias,
        "scenario_id": record["scenario_id"],
        "trial_id": record["trial_id"],
        "trial_label": record["trial_label"],
        "request_path": _repo_relative_path(repo_root, request_path),
        "response_path": _repo_relative_path(repo_root, response_path),
        "raw_output_path": _repo_relative_path(repo_root, raw_output_path),
        "status": "succeeded",
        "error_code": None,
        "error_type": None,
        "error_message": None,
        "finish_reason": finish_reason,
        "content_length": len(content),
        "elapsed_seconds": elapsed_seconds,
        "endpoint": profile.endpoint,
        "endpoint_used": profile.endpoint,
        "models_endpoint": profile.models_endpoint,
        "server_started_by_runner": server_started_by_runner,
        "skipped_existing": False,
        "no_runtime_execution": False,
        "model_execution": True,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
    }
    _write_json(timing_path, timing_payload)
    return timing_payload


def _wait_for_models_endpoint(
    *,
    profile: SequentialModelProfile,
    transport: TransportFn,
    sleep_fn: SleepFn,
    time_fn: TimeFn,
) -> dict[str, Any]:
    deadline = time_fn() + profile.startup_timeout_sec
    start = time_fn()
    last_error = "models endpoint was not ready."
    while time_fn() < deadline:
        try:
            response = transport("GET", profile.models_endpoint, None, min(5.0, profile.startup_timeout_sec))
        except Exception as exc:
            _, error_type, error_message = _classify_request_exception(exc)
            last_error = error_message
            sleep_fn(1.0)
            continue
        if response.status_code >= 400:
            last_error = _bounded_error_message(f"http status {response.status_code}")
            sleep_fn(1.0)
            continue
        body_text = _decode_body(response.body)
        try:
            payload = json.loads(body_text or "{}")
        except json.JSONDecodeError:
            last_error = _bounded_error_message("models endpoint did not return valid JSON.")
            sleep_fn(1.0)
            continue
        names = _model_names_from_models_payload(payload)
        if not names:
            last_error = _bounded_error_message("models endpoint returned no usable model ids.")
            sleep_fn(1.0)
            continue
        if profile.start_api_model in names or profile.start_model_id in names or profile.model_alias in names:
            return {"ready": True, "names": sorted(names), "elapsed_seconds": round(time_fn() - start, 6)}
        sleep_fn(1.0)
    return {
        "ready": False,
        "error_code": "models_endpoint_not_ready",
        "error_type": "models_endpoint_not_ready",
        "error_message": last_error,
        "elapsed_seconds": round(time_fn() - start, 6),
    }


def _model_names_from_models_payload(payload: Mapping[str, Any]) -> set[str]:
    names: set[str] = set()
    for key in ("models", "data"):
        items = payload.get(key)
        if not isinstance(items, list):
            continue
        for item in items:
            if not isinstance(item, Mapping):
                continue
            for field in ("id", "model", "name"):
                value = item.get(field)
                if isinstance(value, str) and value.strip():
                    names.add(value.strip())
    return names


def _run_port_preflight(
    *,
    configured_ports: tuple[int, ...],
    selected_ports: tuple[int, ...],
    allow_existing_benchmark_servers: bool,
    stop_existing_benchmark_servers: bool,
    port_inspector: PortInspectionFn,
    port_stopper: PortStopFn,
) -> dict[str, Any]:
    summary = {
        "preflight_bypassed": allow_existing_benchmark_servers,
        "stop_existing_benchmark_servers": stop_existing_benchmark_servers,
        "inspected_ports": list(configured_ports),
        "occupied_bindings": [],
        "stopped_bindings": [],
    }
    if allow_existing_benchmark_servers:
        return {"status": "ok", "summary": summary}

    occupied = port_inspector(configured_ports)
    summary["occupied_bindings"] = _jsonable(occupied)
    if stop_existing_benchmark_servers and occupied:
        stopped = port_stopper(occupied)
        summary["stopped_bindings"] = _jsonable(stopped)
        occupied = port_inspector(configured_ports)
        summary["occupied_bindings"] = _jsonable(occupied)

    if not occupied:
        return {"status": "ok", "summary": summary}

    occupied_ports = {int(item["port"]) for item in occupied if isinstance(item.get("port"), int)}
    if occupied_ports.intersection(selected_ports):
        return {
            "status": "failed",
            "error_code": "selected_benchmark_port_occupied",
            "summary": summary,
        }
    return {
        "status": "failed",
        "error_code": "other_benchmark_port_occupied",
        "summary": summary,
    }


def _inspect_benchmark_ports(ports: tuple[int, ...]) -> list[dict[str, Any]]:
    if not ports:
        return []
    result = subprocess.run(
        ["netstat", "-ano", "-p", "tcp"],
        text=True,
        capture_output=True,
        check=False,
    )
    if result.returncode != 0:
        return []
    requested = set(ports)
    bindings: list[dict[str, Any]] = []
    seen: set[tuple[int, int | None]] = set()
    for raw_line in result.stdout.splitlines():
        line = raw_line.strip()
        if not line or "LISTENING" not in line:
            continue
        parts = line.split()
        if len(parts) < 5:
            continue
        local_address = parts[1]
        state = parts[3]
        pid_text = parts[4]
        if state.upper() != "LISTENING":
            continue
        port = _parse_port_from_local_address(local_address)
        if port is None or port not in requested:
            continue
        pid = int(pid_text) if pid_text.isdigit() else None
        key = (port, pid)
        if key in seen:
            continue
        seen.add(key)
        bindings.append({"port": port, "pid": pid})
    return bindings


def _stop_benchmark_port_bindings(bindings: list[dict[str, Any]]) -> list[dict[str, Any]]:
    stopped: list[dict[str, Any]] = []
    seen_pids: set[int] = set()
    for binding in bindings:
        pid = binding.get("pid")
        if not isinstance(pid, int) or pid <= 0 or pid in seen_pids:
            continue
        seen_pids.add(pid)
        result = subprocess.run(
            ["taskkill", "/PID", str(pid), "/T", "/F"],
            text=True,
            capture_output=True,
            check=False,
        )
        stopped.append(
            {
                "port": binding.get("port"),
                "pid": pid,
                "stop_attempted": True,
                "stop_succeeded": result.returncode == 0,
            }
        )
    return stopped


def _parse_port_from_local_address(local_address: str) -> int | None:
    text = local_address.strip()
    if text.startswith("[") and "]:" in text:
        port_text = text.rsplit("]:", 1)[-1]
    else:
        port_text = text.rsplit(":", 1)[-1]
    if not port_text.isdigit():
        return None
    return int(port_text)


def _start_server(profile: SequentialModelProfile, repo_root: Path, output_root: Path) -> StartedServer:
    log_dir = output_root / "server_logs" / profile.model_alias
    log_dir.mkdir(parents=True, exist_ok=True)
    stdout_path = log_dir / "stdout.log"
    stderr_path = log_dir / "stderr.log"
    start_script = repo_root / profile.start_script
    proc = subprocess.Popen(
        [
            "powershell",
            "-ExecutionPolicy",
            "Bypass",
            "-File",
            str(start_script),
            "-ModelId",
            profile.start_model_id,
            "-ApiModel",
            profile.start_api_model,
            "-Port",
            str(profile.port),
            "-CtxSize",
            str(profile.ctx_size),
            *(["-CpuOnly"] if profile.cpu_only else []),
        ],
        cwd=repo_root,
        stdout=stdout_path.open("w", encoding="utf-8"),
        stderr=stderr_path.open("w", encoding="utf-8"),
        text=True,
    )
    return StartedServer(
        model_alias=profile.model_alias,
        pid=proc.pid,
        started_by_script=True,
        log_dir=_repo_relative_path(repo_root, log_dir),
    )


def _stop_server(server: StartedServer) -> None:
    if server.pid is None:
        return
    subprocess.run(
        ["taskkill", "/PID", str(server.pid), "/T", "/F"],
        text=True,
        capture_output=True,
        check=False,
    )


def _urllib_transport(method: str, url: str, body: bytes | None, timeout_sec: float) -> SequentialHttpResponse:
    request = urllib.request.Request(url, data=body, method=method)
    request.add_header("Accept", "application/json")
    if body is not None:
        request.add_header("Content-Type", "application/json")
    try:
        with urllib.request.urlopen(request, timeout=timeout_sec) as response:
            return SequentialHttpResponse(
                status_code=int(getattr(response, "status", 200)),
                body=response.read(),
                headers=dict(response.headers.items()),
            )
    except urllib.error.HTTPError as exc:
        return SequentialHttpResponse(
            status_code=int(getattr(exc, "code", 500)),
            body=exc.read() if hasattr(exc, "read") else b"",
            headers=dict(getattr(exc, "headers", {}).items()) if getattr(exc, "headers", None) else {},
        )


def _extract_response_content(payload: Mapping[str, Any]) -> str:
    try:
        content = payload["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError):
        return ""
    return content if isinstance(content, str) else ""


def _extract_finish_reason(payload: Mapping[str, Any]) -> str | None:
    try:
        finish_reason = payload["choices"][0]["finish_reason"]
    except (KeyError, IndexError, TypeError):
        return None
    return finish_reason if isinstance(finish_reason, str) and finish_reason.strip() else None


def _decode_body(body: bytes) -> str:
    return body.decode("utf-8", errors="replace")


def _failure_summary(
    *,
    run_id: str | None,
    output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
    server_mode: str,
    diagnostics: Mapping[str, Any] | None = None,
) -> dict[str, Any]:
    payload = {
        "schema_version": SUMMARY_SCHEMA_VERSION,
        "status": "failed",
        "error_code": error_code,
        "run_id": run_id,
        "output_dir": output_dir,
        "models_total": 0,
        "models_attempted": 0,
        "models_completed": 0,
        "models_failed": 0,
        "requests_total": 0,
        "requests_completed": 0,
        "requests_failed": 0,
        "requests_skipped_existing": 0,
        "selected_models": [],
        "dry_run": False,
        "skip_existing": False,
        "fail_fast": False,
        "start_servers": False,
        "server_mode": server_mode,
        "preflight_bypassed": False,
        "port_preflight": {
            "preflight_bypassed": False,
            "stop_existing_benchmark_servers": False,
            "inspected_ports": [],
            "occupied_bindings": [],
            "stopped_bindings": [],
        },
        "model_results": [],
        "request_results": [],
        "no_runtime_execution": True,
        "model_execution": False,
        "real_browser_execution": False,
        "playwright_execution": False,
        "browser_opened": False,
        "fixture_only": True,
        "limitations": list(limitations),
    }
    if diagnostics:
        payload["diagnostics"] = _jsonable(diagnostics)
    return payload


def _classify_request_exception(exc: Exception) -> tuple[str, str, str]:
    if isinstance(exc, (TimeoutError, socket.timeout)):
        return (
            "endpoint_request_timeout",
            "timeout_error",
            _bounded_error_message("request timed out."),
        )
    if isinstance(exc, urllib.error.HTTPError):
        return (
            "endpoint_request_failed",
            "http_error",
            _bounded_error_message(f"http status {int(getattr(exc, 'code', 500))}"),
        )
    if isinstance(exc, urllib.error.URLError):
        reason = getattr(exc, "reason", None)
        if isinstance(reason, (TimeoutError, socket.timeout)):
            return (
                "endpoint_request_timeout",
                "timeout_error",
                _bounded_error_message("request timed out."),
            )
        return (
            "endpoint_connection_failed",
            "url_error",
            _bounded_error_message(f"url error: {reason or 'connection failed'}"),
        )
    if isinstance(exc, ConnectionRefusedError):
        return (
            "endpoint_connection_failed",
            "connection_refused",
            _bounded_error_message("connection refused."),
        )
    if isinstance(exc, ConnectionResetError):
        return (
            "endpoint_connection_failed",
            "connection_reset",
            _bounded_error_message("connection reset."),
        )
    if isinstance(exc, OSError):
        return (
            "endpoint_connection_failed",
            "os_error",
            _bounded_error_message("endpoint connection failed."),
        )
    return (
        "request_failed",
        exc.__class__.__name__.lower(),
        _bounded_error_message(str(exc) or "request failed."),
    )


def _bounded_error_message(message: str) -> str:
    compact = " ".join(str(message).split())
    if not compact:
        compact = "request failed."
    if len(compact) > DEFAULT_REQUEST_ERROR_LIMIT:
        compact = compact[: DEFAULT_REQUEST_ERROR_LIMIT - 3].rstrip() + "..."
    return compact


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    _write_text_file(
        path,
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True),
        encoding="utf-8",
    )


def _read_text_file(path: Path, *, encoding: str) -> str:
    with open(_path_for_io(path), "r", encoding=encoding) as handle:
        return handle.read()


def _write_text_file(path: Path, content: str, *, encoding: str) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with open(_path_for_io(path), "w", encoding=encoding) as handle:
        handle.write(content)


def _path_for_io(path: Path) -> str:
    resolved = str(path.resolve())
    if resolved.startswith("\\\\?\\"):
        return resolved
    if resolved.startswith("\\\\"):
        return "\\\\?\\UNC\\" + resolved[2:]
    return "\\\\?\\" + resolved


def _safe_identifier(value: Any, label: str) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text or any(ch in text for ch in "/\\"):
        return None
    return text


def _safe_relative_path(value: Any, label: str) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return None
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        return None
    return path.as_posix()


def _safe_local_http_url(value: Any, label: str) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    if not text:
        return None
    parsed = urllib.parse.urlparse(text)
    if parsed.scheme not in {"http", "https"}:
        return None
    if (parsed.hostname or "").strip().lower() not in ALLOWED_LOCAL_HOSTS:
        return None
    if not parsed.netloc:
        return None
    return text.rstrip("/")


def _required_bool(value: Any, label: str) -> bool:
    if not isinstance(value, bool):
        raise ValueError(f"{label} must be a boolean.")
    return value


def _required_int(value: Any, label: str) -> int:
    if not isinstance(value, int) or isinstance(value, bool):
        raise ValueError(f"{label} must be an integer.")
    return value


def _required_float(value: Any, label: str) -> float:
    if not isinstance(value, (int, float)) or isinstance(value, bool):
        raise ValueError(f"{label} must be numeric.")
    return float(value)


def _repo_relative_path(repo_root: Path, path: Path) -> str:
    try:
        return path.resolve().relative_to(repo_root.resolve()).as_posix()
    except ValueError:
        return path.as_posix()


def _jsonable(value: Any) -> Any:
    if isinstance(value, Mapping):
        return {str(key): _jsonable(item) for key, item in value.items()}
    if isinstance(value, (list, tuple)):
        return [_jsonable(item) for item in value]
    if isinstance(value, Path):
        return value.as_posix()
    return value
