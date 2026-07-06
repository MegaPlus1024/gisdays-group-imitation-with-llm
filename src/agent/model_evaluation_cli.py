from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from dataclasses import asdict
from typing import Sequence

from .model_evaluation_artifact_contracts import (
    ARTIFACT_CONTRACT_VERSION,
    export_artifact_schema_contract_summaries,
    export_artifact_schema_contracts,
    get_artifact_schema_contract,
)
from .model_evaluation_artifact_validator_cli import main as artifact_validator_cli_main
from .model_evaluation_artifact_registry import (
    CLI_TOOL_NAME,
    SUPPORTED_CLI_SUBCOMMANDS,
    build_version_payload,
)
from .model_evaluation_workflow_runner_cli import main as workflow_runner_cli_main


TOOL_NAME = CLI_TOOL_NAME
SUPPORTED_SUBCOMMANDS = SUPPORTED_CLI_SUBCOMMANDS


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified offline model evaluation workflow CLI.",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("run", help="Run the existing offline workflow runner.", add_help=False)
    subparsers.add_parser("validate", help="Validate existing offline workflow artifacts.", add_help=False)
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


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
