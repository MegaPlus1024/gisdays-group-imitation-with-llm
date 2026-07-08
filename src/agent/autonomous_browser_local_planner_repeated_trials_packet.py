from __future__ import annotations

import json
from collections.abc import Mapping
from dataclasses import dataclass
from pathlib import Path
from typing import Any

from .autonomous_browser_local_planner_operator_packet import _build_compact_prompt_text


PACKET_CONFIG_SCHEMA_VERSION = "autonomous_browser_local_planner_repeated_trials_packet_config_v1"
SUMMARY_SCHEMA_VERSION = "autonomous_browser_local_planner_repeated_trials_packet_summary_v1"
DEFAULT_PACKET_ID = "browser_local_planner_repeated_trials_packet_v1"
DEFAULT_MODEL = "second_model"
DEFAULT_TRIAL_COUNT = 3
DEFAULT_PROMPT_PROFILE = "compact_schema_following"
DEFAULT_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/local_planner_repeated_trials_packet"
DEFAULT_INGESTION_SUITE_CONFIG_PATH = "artifacts/autonomous_runtime_summaries/local_planner_repeated_trials_packet/ingestion_suite_config.local.json"
DEFAULT_INGESTION_SUITE_OUTPUT_DIR = "artifacts/autonomous_runtime_summaries/local_planner_repeated_trials_packet/ingestion_suite_runs"
ALLOWED_PROMPT_PROFILES = ("compact_schema_following",)


@dataclass(frozen=True)
class AutonomousBrowserLocalPlannerRepeatedTrialsPacketSummary:
    schema_version: str
    status: str
    error_code: str | None
    no_runtime_execution: bool
    model_execution: bool
    real_browser_execution: bool
    packet_id: str | None
    trial_count: int
    output_dir: str | None
    packet_files: tuple[str, ...] = ()
    expected_raw_output_paths: tuple[str, ...] = ()
    ingestion_suite_config_path: str | None = None
    post_run_commands_count: int = 0
    limitations: tuple[str, ...] = ()

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "error_code": self.error_code,
            "no_runtime_execution": self.no_runtime_execution,
            "model_execution": self.model_execution,
            "real_browser_execution": self.real_browser_execution,
            "packet_id": self.packet_id,
            "trial_count": self.trial_count,
            "output_dir": self.output_dir,
            "packet_files": list(self.packet_files),
            "expected_raw_output_paths": list(self.expected_raw_output_paths),
            "ingestion_suite_config_path": self.ingestion_suite_config_path,
            "post_run_commands_count": self.post_run_commands_count,
            "limitations": list(self.limitations),
        }


def build_autonomous_browser_local_planner_repeated_trials_packet(
    config_artifact: str | Path | Mapping[str, Any],
    *,
    repo_root: str | Path | None = None,
) -> dict[str, Any]:
    repo = Path(repo_root) if repo_root is not None else Path(".")
    config_result = _load_config(config_artifact)
    if config_result["status"] != "ok":
        return _failure_summary(
            packet_id=config_result.get("packet_id"),
            trial_count=int(config_result.get("trial_count") or DEFAULT_TRIAL_COUNT),
            output_dir=config_result.get("output_dir"),
            error_code=str(config_result.get("error_code") or "config_validation_failed"),
            limitations=tuple(config_result.get("limitations") or _limitations()),
        )

    packet_id = str(config_result["packet_id"])
    trial_count = int(config_result["trial_count"])
    output_dir = str(config_result["output_dir"])
    model = str(config_result["model"])
    prompt_profile = str(config_result["prompt_profile"])
    expected_raw_output_paths = tuple(str(path) for path in config_result["expected_raw_output_paths"])
    ingestion_suite_config_path = str(config_result["ingestion_suite_config_path"])
    limitations = tuple(config_result.get("limitations") or _limitations())

    packet_dir = repo / output_dir
    packet_dir.mkdir(parents=True, exist_ok=True)

    packet_files: list[str] = []

    compact_prompt_text = _build_compact_prompt_text()
    _write_text(packet_dir / "planner_prompt.compact.txt", compact_prompt_text + "\n")
    packet_files.append(f"{output_dir}/planner_prompt.compact.txt")

    request_paths: dict[str, str] = {}
    for index in range(1, trial_count + 1):
        trial_id = f"trial_{index:02d}"
        trial_dir = packet_dir / trial_id
        trial_dir.mkdir(parents=True, exist_ok=True)
        request_path = trial_dir / "trial_request.json"
        request_payload = _build_trial_request_payload(
            trial_id=trial_id,
            model=model,
            prompt_text=compact_prompt_text,
        )
        _write_json(request_path, request_payload)
        request_paths[trial_id] = f"{output_dir}/{trial_id}/trial_request.json"
        packet_files.append(request_paths[trial_id])

    trial_request_paths_path = packet_dir / "trial_request_paths.json"
    _write_json(trial_request_paths_path, request_paths)
    packet_files.append(f"{output_dir}/trial_request_paths.json")

    trial_output_paths_payload = {f"trial_{index:02d}": path for index, path in enumerate(expected_raw_output_paths, start=1)}
    _write_json(packet_dir / "trial_output_paths.json", trial_output_paths_payload)
    packet_files.append(f"{output_dir}/trial_output_paths.json")

    ingestion_suite_config = _build_ingestion_suite_config(
        packet_id=packet_id,
        expected_raw_output_paths=expected_raw_output_paths,
        output_dir=ingestion_suite_config_path,
    )
    _write_json(packet_dir / "ingestion_suite_config.local.json", ingestion_suite_config)
    packet_files.append(f"{output_dir}/ingestion_suite_config.local.json")

    commands = _build_commands(
        packet_dir=output_dir,
        request_paths=request_paths,
        expected_raw_output_paths=expected_raw_output_paths,
        ingestion_suite_config_path=ingestion_suite_config_path,
    )
    _write_json(packet_dir / "commands.json", {"commands": commands})
    packet_files.append(f"{output_dir}/commands.json")

    commands_md = _build_commands_markdown(commands, output_dir=output_dir)
    _write_text(packet_dir / "commands.md", commands_md)
    packet_files.append(f"{output_dir}/commands.md")

    readme_text = _build_readme(
        packet_id=packet_id,
        trial_count=trial_count,
        model=model,
        prompt_profile=prompt_profile,
        expected_raw_output_paths=expected_raw_output_paths,
        ingestion_suite_config_path=ingestion_suite_config_path,
    )
    _write_text(packet_dir / "README.md", readme_text)
    packet_files.append(f"{output_dir}/README.md")

    summary_relative_path = f"{output_dir}/autonomous_browser_local_planner_repeated_trials_packet_summary.json"
    packet_files.append(summary_relative_path)
    summary = AutonomousBrowserLocalPlannerRepeatedTrialsPacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="succeeded",
        error_code=None,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        packet_id=packet_id,
        trial_count=trial_count,
        output_dir=output_dir,
        packet_files=tuple(packet_files),
        expected_raw_output_paths=expected_raw_output_paths,
        ingestion_suite_config_path=ingestion_suite_config_path,
        post_run_commands_count=len(commands),
        limitations=limitations,
    )
    summary_payload = summary.to_dict()
    _write_json(packet_dir / "autonomous_browser_local_planner_repeated_trials_packet_summary.json", summary_payload)
    return summary_payload


def write_autonomous_browser_local_planner_repeated_trials_packet_summary(
    summary: Mapping[str, Any],
    output_dir: str | Path,
) -> Path:
    out = Path(output_dir)
    out.mkdir(parents=True, exist_ok=True)
    summary_path = out / "autonomous_browser_local_planner_repeated_trials_packet_summary.json"
    summary_path.write_text(json.dumps(summary, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
    return summary_path


def _load_config(config_artifact: str | Path | Mapping[str, Any]) -> dict[str, Any]:
    if isinstance(config_artifact, Mapping):
        payload = dict(config_artifact)
    else:
        try:
            payload = json.loads(Path(config_artifact).read_text(encoding="utf-8-sig"))
        except OSError:
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "packet_id": None,
                "trial_count": DEFAULT_TRIAL_COUNT,
                "output_dir": None,
                "limitations": _limitations(),
            }
    if not isinstance(payload, dict):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": None,
            "trial_count": DEFAULT_TRIAL_COUNT,
            "output_dir": None,
            "limitations": _limitations(),
        }
    if str(payload.get("schema_version", "")) != PACKET_CONFIG_SCHEMA_VERSION:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": _safe_text(payload.get("packet_id")),
            "trial_count": _safe_trial_count(payload.get("trial_count", DEFAULT_TRIAL_COUNT)) or DEFAULT_TRIAL_COUNT,
            "output_dir": _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR)),
            "limitations": _limitations(),
        }

    packet_id = _safe_identifier(payload.get("packet_id", DEFAULT_PACKET_ID), "packet_id")
    model = _safe_identifier(payload.get("model", DEFAULT_MODEL), "model")
    trial_count = _safe_trial_count(payload.get("trial_count", DEFAULT_TRIAL_COUNT))
    prompt_profile = _safe_prompt_profile(payload.get("prompt_profile", DEFAULT_PROMPT_PROFILE))
    output_dir = _safe_relative_path(payload.get("output_dir", DEFAULT_OUTPUT_DIR))
    ingestion_suite_config_path = _safe_relative_path(
        payload.get("ingestion_suite_config_path", DEFAULT_INGESTION_SUITE_CONFIG_PATH)
    )
    expected_raw_output_paths = payload.get("expected_raw_output_paths")

    if (
        packet_id is None
        or model != DEFAULT_MODEL
        or trial_count is None
        or output_dir is None
        or prompt_profile is None
        or ingestion_suite_config_path is None
    ):
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "trial_count": trial_count or DEFAULT_TRIAL_COUNT,
            "output_dir": output_dir,
            "limitations": _limitations(),
        }
    if trial_count != DEFAULT_TRIAL_COUNT:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "trial_count": trial_count,
            "output_dir": output_dir,
            "limitations": _limitations(),
        }
    if not isinstance(expected_raw_output_paths, list) or len(expected_raw_output_paths) != DEFAULT_TRIAL_COUNT:
        return {
            "status": "failed",
            "error_code": "config_validation_failed",
            "packet_id": packet_id,
            "trial_count": trial_count,
            "output_dir": output_dir,
            "limitations": _limitations(),
        }

    cleaned_expected_raw_output_paths: list[str] = []
    for index, candidate in enumerate(expected_raw_output_paths):
        safe_output = _safe_relative_path(candidate)
        if safe_output is None:
            return {
                "status": "failed",
                "error_code": "config_validation_failed",
                "packet_id": packet_id,
                "trial_count": trial_count,
                "output_dir": output_dir,
                "limitations": _limitations(),
            }
        cleaned_expected_raw_output_paths.append(safe_output)

    return {
        "status": "ok",
        "packet_id": packet_id,
        "model": model,
        "trial_count": trial_count,
        "prompt_profile": prompt_profile,
        "output_dir": output_dir,
        "expected_raw_output_paths": tuple(cleaned_expected_raw_output_paths),
        "ingestion_suite_config_path": ingestion_suite_config_path,
        "limitations": tuple(str(item) for item in payload.get("limitations", []) if isinstance(item, str) and item.strip()),
    }


def _build_trial_request_payload(*, trial_id: str, model: str, prompt_text: str) -> dict[str, Any]:
    return {
        "model": model,
        "messages": [
            {"role": "system", "content": "You are a local browser planner."},
            {"role": "user", "content": prompt_text},
        ],
        "temperature": 0,
        "max_tokens": 256,
        "stream": False,
        "metadata": {"trial_id": trial_id},
    }


def _build_ingestion_suite_config(*, packet_id: str, expected_raw_output_paths: tuple[str, ...], output_dir: str) -> dict[str, Any]:
    return {
        "schema_version": "autonomous_browser_planner_output_ingestion_suite_config_v1",
        "suite_id": f"{packet_id}_ingestion_suite_v1",
        "captured_outputs": list(expected_raw_output_paths),
        "replay_mode": "dry_run",
        "output_dir": DEFAULT_INGESTION_SUITE_OUTPUT_DIR,
        "expected_min_ingested": 3,
        "expected_max_rejected": 0,
        "limitations": [
            "repeated local planner trials only",
            "manual second_model runs only",
            "no model calls by Codex",
            "no real browser execution",
            "fixture replay remains offline only",
            "not production browser automation",
        ],
    }


def _build_commands(
    *,
    packet_dir: str,
    request_paths: dict[str, str],
    expected_raw_output_paths: tuple[str, ...],
    ingestion_suite_config_path: str,
) -> list[dict[str, Any]]:
    trial_ids = [f"trial_{index:02d}" for index in range(1, len(expected_raw_output_paths) + 1)]
    commands: list[dict[str, Any]] = [
        {
            "id": "build_repeated_trials_packet",
            "manual_only": False,
            "description": "Build the repeated local planner trials packet.",
            "command": r".\.venv\Scripts\python.exe scripts/build_autonomous_browser_local_planner_repeated_trials_packet.py --config configs/autonomous_runtime/browser_local_planner_repeated_trials_packet.example.json",
        },
        {
            "id": "confirm_local_endpoint",
            "manual_only": True,
            "description": "Confirm the local model endpoint manually before running trials.",
            "command": "# Manual operator step only: start or confirm the local llama-server endpoint outside Codex.",
        },
    ]

    for index, trial_id in enumerate(trial_ids):
        request_path = _windows_path(request_paths[trial_id])
        raw_output_path = _windows_path(expected_raw_output_paths[index])
        response_path = _windows_path(f"{packet_dir}/{trial_id}/trial_response.json")
        commands.append(
            {
                "id": f"{trial_id}_curl_request",
                "manual_only": True,
                "description": f"Run the {trial_id} model call with curl.exe and save the response JSON.",
                "command": (
                    "# Manual operator only. Do not use Invoke-RestMethod for planner generation.\n"
                    f"curl.exe --max-time 90 -sS -X POST http://127.0.0.1:8080/v1/chat/completions -H \"Content-Type: application/json\" --data-binary \"@{request_path}\" --output \"{response_path}\""
                ),
            }
        )
        commands.append(
            {
                "id": f"{trial_id}_extract_content",
                "manual_only": True,
                "description": f"Extract the model message.content for {trial_id} into raw_planner_output.txt.",
                "command": (
                    f"$response = Get-Content \"{response_path}\" -Raw | ConvertFrom-Json\n"
                    f"$response.choices[0].message.content | Set-Content \"{raw_output_path}\" -Encoding utf8"
                ),
            }
        )

    commands.extend(
        [
            {
                "id": "run_ingestion_suite_dry_run",
                "manual_only": False,
                "description": "Run the captured-output ingestion suite in dry-run mode.",
                "command": r".\.venv\Scripts\python.exe scripts/run_autonomous_browser_planner_output_ingestion_suite.py --config artifacts/autonomous_runtime_summaries/local_planner_repeated_trials_packet/ingestion_suite_config.local.json",
            },
            {
                "id": "run_ingestion_suite_fixture",
                "manual_only": False,
                "description": "Run the captured-output ingestion suite with fixture execution.",
                "command": r".\.venv\Scripts\python.exe scripts/run_autonomous_browser_planner_output_ingestion_suite.py --config artifacts/autonomous_runtime_summaries/local_planner_repeated_trials_packet/ingestion_suite_config.local.json --execute-fixture",
            },
            {
                "id": "run_pytest",
                "manual_only": False,
                "description": "Run the offline test suite.",
                "command": r".\.venv\Scripts\python.exe -m pytest",
            },
        ]
    )
    return commands


def _build_commands_markdown(commands: list[dict[str, Any]], *, output_dir: str) -> str:
    lines = [
        "# Repeated Local Planner Trials Commands",
        "",
        "Codex must not launch models.",
        "Use `planner_prompt.compact.txt` as the prompt source for each trial.",
        "Do not use Invoke-RestMethod for planner generation.",
        "A human operator may run the local planner separately and save each model output as text.",
        f"The packet output directory is `{output_dir}`.",
        "",
    ]
    for command in commands:
        lines.extend(
            [
                f"## {command['id']}",
                command["description"],
                "```powershell",
                command["command"],
                "```",
                "",
            ]
        )
    return "\n".join(lines).rstrip() + "\n"


def _build_readme(
    *,
    packet_id: str,
    trial_count: int,
    model: str,
    prompt_profile: str,
    expected_raw_output_paths: tuple[str, ...],
    ingestion_suite_config_path: str,
) -> str:
    lines = [
        "# Repeated Local Planner Trials Packet",
        "",
        f"Packet id: `{packet_id}`",
        f"Model: `{model}`",
        f"Prompt profile: `{prompt_profile}`",
        f"Trial count: `{trial_count}`",
        "",
        "## Scope",
        "",
        "- Three manual `second_model` runs using the compact prompt.",
        "- Captured outputs saved as text files.",
        "- Captured-output ingestion suite validates and replays all three outputs offline.",
        "- Purpose is stability evidence across repeated local planner outputs.",
        "",
        "## Safety",
        "",
        "- Codex must not launch models.",
        "- Do not use Invoke-RestMethod for planner generation.",
        "- No real browser execution.",
        "- Fixture replay remains offline only.",
        "- No production readiness claim.",
        "",
        "## Expected Raw Outputs",
        "",
    ]
    for path in expected_raw_output_paths:
        lines.append(f"- `{path}`")
    lines.extend(
        [
            "",
            "## Ingestion Suite",
            "",
            f"- Config: `{ingestion_suite_config_path}`",
            "",
            "## Operator Flow",
            "",
            "1. Build the repeated trials packet.",
            "2. Confirm the local endpoint manually.",
            "3. Run three separate manual planner calls with `curl.exe --max-time`.",
            "4. Save each model `message.content` to `raw_planner_output.txt`.",
            "5. Run the ingestion suite in dry-run mode.",
            "6. Run the ingestion suite with fixture execution.",
            "7. Run pytest.",
            "",
        ]
    )
    return "\n".join(lines)


def _failure_summary(
    *,
    packet_id: str | None,
    trial_count: int,
    output_dir: str | None,
    error_code: str,
    limitations: tuple[str, ...],
) -> dict[str, Any]:
    summary = AutonomousBrowserLocalPlannerRepeatedTrialsPacketSummary(
        schema_version=SUMMARY_SCHEMA_VERSION,
        status="failed",
        error_code=error_code,
        no_runtime_execution=True,
        model_execution=False,
        real_browser_execution=False,
        packet_id=packet_id,
        trial_count=trial_count,
        output_dir=output_dir,
        packet_files=(),
        expected_raw_output_paths=(),
        ingestion_suite_config_path=None,
        post_run_commands_count=0,
        limitations=limitations,
    )
    return summary.to_dict()


def _limitations() -> tuple[str, ...]:
    return (
        "repeated local planner trials packet only",
        "manual second_model runs only",
        "no model calls by Codex",
        "no real browser execution",
        "fixture replay remains offline only",
        "not production browser automation",
    )


def _safe_relative_path(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    normalized = value.replace("\\", "/").strip()
    if not normalized:
        return None
    path = Path(normalized)
    if path.is_absolute() or "://" in normalized or any(part == ".." for part in path.parts):
        return None
    return path.as_posix()


def _safe_text(value: Any) -> str | None:
    if not isinstance(value, str):
        return None
    text = value.strip()
    return text or None


def _safe_identifier(value: Any, label: str) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    if any(ch in stripped for ch in ("\\", "/", ":", "\0")):
        return None
    return stripped


def _safe_prompt_profile(value: Any) -> str | None:
    if not isinstance(value, str) or not value.strip():
        return None
    stripped = value.strip()
    return stripped if stripped in ALLOWED_PROMPT_PROFILES else None


def _windows_path(value: str) -> str:
    return value.replace("/", "\\")


def _safe_trial_count(value: Any) -> int | None:
    if isinstance(value, bool):
        return None
    try:
        trial_count = int(value)
    except (TypeError, ValueError):
        return None
    return trial_count if trial_count > 0 else None


def _write_text(path: Path, text: str) -> None:
    path.write_text(text, encoding="utf-8")


def _write_json(path: Path, payload: Mapping[str, Any]) -> None:
    path.write_text(json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")
