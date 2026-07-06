from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from pathlib import Path
from typing import Sequence

from .model_evaluation_artifact_contracts import (
    ARTIFACT_CONTRACT_VERSION,
    export_artifact_schema_contract_summaries,
    export_artifact_schema_contracts,
    get_artifact_schema_contract,
)
from .model_evaluation_artifact_validator_cli import main as artifact_validator_cli_main
from .model_evaluation_compatibility_gate import (
    run_model_evaluation_compatibility_gate,
    write_model_evaluation_compatibility_report,
)
from .model_evaluation_compatibility_gate_cli import main as compatibility_gate_cli_main
from .model_evaluation_artifact_registry import (
    CLI_TOOL_NAME,
    SUPPORTED_CLI_SUBCOMMANDS,
    build_version_payload,
)
from .model_evaluation_workflow_runner_cli import main as workflow_runner_cli_main


TOOL_NAME = CLI_TOOL_NAME
SUPPORTED_SUBCOMMANDS = SUPPORTED_CLI_SUBCOMMANDS
DEFAULT_GOLDEN_FIXTURE_RELATIVE_PATH = Path("tests") / "fixtures" / "model_evaluation_workflow_golden"


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified offline model evaluation workflow CLI.",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("run", help="Run the existing offline workflow runner.", add_help=False)
    subparsers.add_parser("validate", help="Validate existing offline workflow artifacts.", add_help=False)
    subparsers.add_parser("compatibility", help="Run the offline artifact compatibility gate.", add_help=False)
    subparsers.add_parser("check", help="Run the default offline compatibility check.", add_help=False)
    schema_parser = subparsers.add_parser("schema", help="Print offline artifact schema contracts.")
    schema_parser.add_argument("--artifact-type", default=None, help="Optional artifact type to print.")
    schema_parser.add_argument("--full", action="store_true", default=False, help="Print full field contracts.")
    subparsers.add_parser("version", help="Print supported offline workflow schemas.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    args_list = list(argv) if argv is not None else sys.argv[1:]
    parser = build_parser()
    try:
        args, remaining = parser.parse_known_args(args_list)
    except SystemExit as exc:
        return _system_exit_code(exc)

    if args.subcommand == "run":
        return _delegate_cli(workflow_runner_cli_main, remaining)
    if args.subcommand == "validate":
        return _delegate_cli(artifact_validator_cli_main, remaining)
    if args.subcommand == "compatibility":
        return _delegate_cli(compatibility_gate_cli_main, remaining)
    if args.subcommand == "check":
        return _check_cli(remaining)
    if args.subcommand == "schema":
        if remaining:
            _print_json(_invalid_payload("schema_unexpected_args"))
            return 2
        try:
            _print_json(_schema_payload(args.artifact_type, full=args.full))
        except ValueError:
            _print_json(_invalid_payload("schema_artifact_type_unknown"))
            return 2
        return 0
    if args.subcommand == "version":
        if remaining:
            _print_json(_invalid_payload("version_unexpected_args"))
            return 2
        _print_json(build_version_payload())
        return 0

    _print_json(_invalid_payload("subcommand_required"))
    return 2


def _delegate_cli(delegate: Callable[[Sequence[str] | None], int], argv: list[str]) -> int:
    try:
        return int(delegate(argv))
    except SystemExit as exc:
        return _system_exit_code(exc)


def _system_exit_code(exc: SystemExit) -> int:
    if isinstance(exc.code, int):
        return exc.code
    return 2


def _check_cli(argv: list[str]) -> int:
    parser = _build_check_parser()
    try:
        args = parser.parse_args(argv)
    except SystemExit:
        _print_json(_check_invalid_payload("model_evaluation_check", "check_args_invalid", check_mode="golden_only"))
        return 2

    check_mode = "golden_plus_workflow_output" if args.workflow_output_dir else "golden_only"
    compatibility_id = args.compatibility_id or "model_evaluation_check"
    golden_fixture_dir = _resolve_golden_fixture_dir(args.golden_fixture_dir)
    if not golden_fixture_dir.is_dir():
        _print_json(_check_invalid_payload(compatibility_id, "golden_fixture_dir_missing", check_mode=check_mode))
        return 2
    try:
        report = run_model_evaluation_compatibility_gate(
            golden_fixture_dir=golden_fixture_dir,
            workflow_output_dir=args.workflow_output_dir,
            compatibility_id=compatibility_id,
        )
        report_path, _ = write_model_evaluation_compatibility_report(
            report,
            args.output_dir,
            write_markdown_preview=args.write_markdown_preview,
        )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        _print_json(_check_invalid_payload(compatibility_id, exc.__class__.__name__, check_mode=check_mode))
        return 2

    payload = {
        "status": report.status,
        "compatibility_id": report.compatibility_id,
        "checked_artifact_count": report.checked_artifact_count,
        "error_count": report.error_count,
        "warning_count": report.warning_count,
        "report_path": report_path.name,
        "check_mode": check_mode,
        "no_runtime_execution": report.no_runtime_execution,
    }
    _print_json(payload)
    if report.status == "incompatible":
        return 2
    if args.strict and report.warning_count:
        return 2
    return 0


def _build_check_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the default offline model evaluation compatibility check.",
    )
    parser.add_argument("--output-dir", required=True, help="Compatibility report output directory.")
    parser.add_argument("--golden-fixture-dir", default=None, help="Optional golden fixture pack directory.")
    parser.add_argument("--workflow-output-dir", default=None, help="Optional workflow output directory to compare.")
    parser.add_argument("--strict", action="store_true", default=False, help="Return nonzero on warnings.")
    parser.add_argument("--compatibility-id", default=None)
    parser.add_argument("--write-markdown-preview", action="store_true", default=False)
    return parser


def _resolve_golden_fixture_dir(value: str | None) -> Path:
    if value:
        return Path(value)
    cwd_candidate = Path.cwd() / DEFAULT_GOLDEN_FIXTURE_RELATIVE_PATH
    if cwd_candidate.is_dir():
        return DEFAULT_GOLDEN_FIXTURE_RELATIVE_PATH
    return Path(__file__).resolve().parents[2] / DEFAULT_GOLDEN_FIXTURE_RELATIVE_PATH


def _schema_payload(artifact_type: str | None, *, full: bool) -> dict[str, object]:
    if artifact_type:
        contract = get_artifact_schema_contract(artifact_type)
        payload = asdict(contract) if full else _contract_summary(contract)
        return {
            "status": "ok",
            "contract_version": ARTIFACT_CONTRACT_VERSION,
            "artifact_count": 1,
            "artifacts": [payload],
            "no_runtime_execution": True,
        }
    return export_artifact_schema_contracts() if full else export_artifact_schema_contract_summaries()


def _contract_summary(contract: object) -> dict[str, object]:
    row = asdict(contract)
    return {
        "artifact_type": row["artifact_type"],
        "schema_version": row["schema_version"],
        "required_field_count": len(row["required_fields"]),
        "optional_field_count": len(row["optional_fields"]),
        "status_allowed_values": row["status_allowed_values"],
        "description": row["description"],
        "contract_version": row["contract_version"],
    }


def _invalid_payload(error: str) -> dict[str, object]:
    return {
        "status": "invalid_input",
        "tool": TOOL_NAME,
        "supported_subcommands": list(SUPPORTED_SUBCOMMANDS),
        "error": error,
        "no_runtime_execution": True,
    }


def _check_invalid_payload(
    compatibility_id: str,
    error: str,
    *,
    check_mode: str,
) -> dict[str, object]:
    return {
        "status": "invalid_input",
        "compatibility_id": compatibility_id,
        "checked_artifact_count": 0,
        "error_count": 1,
        "warning_count": 0,
        "report_path": None,
        "check_mode": check_mode,
        "no_runtime_execution": True,
        "error": error,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
