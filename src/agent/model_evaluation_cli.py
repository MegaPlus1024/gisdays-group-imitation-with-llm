from __future__ import annotations

import argparse
import json
import sys
from collections.abc import Callable
from typing import Sequence

from .model_catalog import MODEL_CATALOG_SCHEMA_VERSION
from .model_comparison_plan import MODEL_COMPARISON_PLAN_SCHEMA_VERSION
from .model_comparison_readiness import MODEL_COMPARISON_READINESS_SCHEMA_VERSION
from .model_evaluation_artifact_validator import (
    ALL_WORKFLOW_OUTPUT_ARTIFACTS,
    MODEL_EVALUATION_ARTIFACT_VALIDATION_SCHEMA_VERSION,
)
from .model_evaluation_artifact_validator_cli import main as artifact_validator_cli_main
from .model_evaluation_scorecard import MODEL_EVALUATION_SCORECARD_SCHEMA_VERSION
from .model_evaluation_workflow_bundle import MODEL_EVALUATION_WORKFLOW_BUNDLE_SCHEMA_VERSION
from .model_evaluation_workflow_runner import (
    MODEL_EVALUATION_WORKFLOW_CONFIG_SCHEMA_VERSION,
    MODEL_EVALUATION_WORKFLOW_RUN_SCHEMA_VERSION,
)
from .model_evaluation_workflow_runner_cli import main as workflow_runner_cli_main
from .model_resource_evaluation import MODEL_RESOURCE_SUMMARY_SCHEMA_VERSION
from .normality_comparison import NORMALITY_COMPARISON_SCHEMA_VERSION


TOOL_NAME = "offline_model_evaluation_cli"
SUPPORTED_SUBCOMMANDS = ("run", "validate", "version")
SUPPORTED_SCHEMA_VERSIONS = (
    MODEL_CATALOG_SCHEMA_VERSION,
    MODEL_COMPARISON_PLAN_SCHEMA_VERSION,
    MODEL_COMPARISON_READINESS_SCHEMA_VERSION,
    NORMALITY_COMPARISON_SCHEMA_VERSION,
    MODEL_RESOURCE_SUMMARY_SCHEMA_VERSION,
    MODEL_EVALUATION_SCORECARD_SCHEMA_VERSION,
    MODEL_EVALUATION_WORKFLOW_BUNDLE_SCHEMA_VERSION,
    MODEL_EVALUATION_ARTIFACT_VALIDATION_SCHEMA_VERSION,
    MODEL_EVALUATION_WORKFLOW_CONFIG_SCHEMA_VERSION,
    MODEL_EVALUATION_WORKFLOW_RUN_SCHEMA_VERSION,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Unified offline model evaluation workflow CLI.",
    )
    subparsers = parser.add_subparsers(dest="subcommand")
    subparsers.add_parser("run", help="Run the existing offline workflow runner.", add_help=False)
    subparsers.add_parser("validate", help="Validate existing offline workflow artifacts.", add_help=False)
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
    if args.subcommand == "version":
        if remaining:
            _print_json(_invalid_payload("version_unexpected_args"))
            return 2
        _print_json(_version_payload())
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


def _version_payload() -> dict[str, object]:
    return {
        "status": "ok",
        "tool": TOOL_NAME,
        "supported_subcommands": list(SUPPORTED_SUBCOMMANDS),
        "supported_schema_versions": list(SUPPORTED_SCHEMA_VERSIONS),
        "supported_artifact_types": list(ALL_WORKFLOW_OUTPUT_ARTIFACTS),
        "no_runtime_execution": True,
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
