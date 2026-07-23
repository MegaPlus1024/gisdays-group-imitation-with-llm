from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path, PurePosixPath
from typing import Any


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_multi_agent_runtime import load_runtime_from_config
from src.agent.canonical_multi_agent_experiments import (
    CONFIG_SCHEMA_VERSION as EXPERIMENT_CONFIG_SCHEMA_VERSION,
    EXPERIMENT_SUMMARY_SCHEMA_VERSION,
    load_long_horizon_experiment_config,
    run_long_horizon_experiment,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the canonical deterministic multi-agent fixture slice.",
    )
    parser.add_argument("--config", required=True, help="Relative runtime config path.")
    parser.add_argument(
        "--output",
        help="Optional relative JSON summary path under artifacts/.",
    )
    parser.add_argument(
        "--scenario-id",
        action="append",
        dest="scenario_ids",
        help="Experiment scenario id; repeat to select multiple scenarios.",
    )
    parser.add_argument(
        "--trials-per-scenario",
        type=int,
        help="Override experiment trial count.",
    )
    parser.add_argument(
        "--models",
        action="append",
        help="Optional comma-separated model aliases; repeatable.",
    )
    parser.add_argument(
        "--allow-model-execution",
        action="store_true",
        help="Explicitly permit localhost local-model calls.",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Run deterministic fake policies with fixture/local tools only.",
    )
    parser.add_argument(
        "--output-dir",
        help="Override relative experiment output directory under artifacts/.",
    )
    parser.add_argument(
        "--skip-existing",
        action="store_true",
        help="Reuse existing trial summaries when present.",
    )
    parser.add_argument(
        "--fail-fast",
        action="store_true",
        help="Stop the experiment after the first failed trial.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    experiment_output_dir: Path | None = None
    try:
        config_path = _resolve_repo_path(args.config, required_root="configs")
        config_payload = json.loads(config_path.read_text(encoding="utf-8-sig"))
        if config_payload.get("schema_version") == EXPERIMENT_CONFIG_SCHEMA_VERSION:
            if args.output:
                raise ValueError(
                    "--output is for single-runtime configs; use --output-dir."
                )
            raw_output_dir = args.output_dir or config_payload.get("output_dir")
            if isinstance(raw_output_dir, str):
                experiment_output_dir = _resolve_repo_path(
                    raw_output_dir,
                    required_root="artifacts",
                )
            config = load_long_horizon_experiment_config(config_path)
            output_dir_value = args.output_dir or config.output_dir
            summary = run_long_horizon_experiment(
                config,
                project_root=PROJECT_ROOT,
                scenario_ids=args.scenario_ids,
                trials_per_scenario=args.trials_per_scenario,
                model_ids=_parse_models(args.models),
                allow_model_execution=args.allow_model_execution,
                dry_run=args.dry_run,
                output_dir=output_dir_value,
                skip_existing=args.skip_existing,
                fail_fast=args.fail_fast,
            )
        else:
            _reject_experiment_args_for_single_runtime(args)
            runtime = load_runtime_from_config(config_path, project_root=PROJECT_ROOT)
            summary = runtime.run()
            if args.output:
                output_path = _resolve_repo_path(
                    args.output,
                    required_root="artifacts",
                )
                _write_json(output_path, summary)
                summary["summary_path"] = (
                    output_path.relative_to(PROJECT_ROOT).as_posix()
                )
    except (OSError, ValueError, json.JSONDecodeError) as exc:
        summary = {
            "schema_version": (
                EXPERIMENT_SUMMARY_SCHEMA_VERSION
                if experiment_output_dir is not None
                else "canonical_multi_agent_runtime_summary_v1"
            ),
            "status": "failed",
            "error_code": "config_or_runtime_failed",
            "error_message": _safe_error(exc),
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "external_network": False,
            "fixture_only": True,
            "no_runtime_execution": True,
        }
        if experiment_output_dir is not None:
            _write_json(
                experiment_output_dir / "experiment_summary.json",
                summary,
            )
        _emit(summary)
        return 2

    _emit(summary)
    return 0 if summary.get("status") == "succeeded" else 1


def _resolve_repo_path(value: str, *, required_root: str) -> Path:
    normalized = str(value).strip().replace("\\", "/")
    pure = PurePosixPath(normalized)
    if (
        not normalized
        or pure.is_absolute()
        or pure.drive
        or ".." in pure.parts
        or not pure.parts
        or pure.parts[0] != required_root
    ):
        raise ValueError(f"Path must be relative and under {required_root}/.")
    resolved = (PROJECT_ROOT / pure.as_posix()).resolve(strict=False)
    resolved.relative_to(PROJECT_ROOT)
    return resolved


def _safe_error(exc: Exception) -> str:
    message = str(exc).strip() or exc.__class__.__name__
    root = str(PROJECT_ROOT)
    return message.replace(root, "<repo>")[:500]


def _parse_models(values: list[str] | None) -> tuple[str, ...] | None:
    if not values:
        return None
    models = tuple(
        item.strip()
        for value in values
        for item in value.split(",")
        if item.strip()
    )
    if not models:
        raise ValueError("--models must contain at least one model alias.")
    if len(models) != len(set(models)):
        raise ValueError("--models must not contain duplicates.")
    return models


def _reject_experiment_args_for_single_runtime(args: argparse.Namespace) -> None:
    if any(
        (
            args.scenario_ids,
            args.trials_per_scenario is not None,
            args.models,
            args.allow_model_execution,
            args.dry_run,
            args.output_dir,
            args.skip_existing,
            args.fail_fast,
        )
    ):
        raise ValueError(
            "Experiment options require a long-horizon experiment config."
        )


def _write_json(path: Path, payload: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2, sort_keys=True) + "\n",
        encoding="utf-8",
    )


def _emit(payload: dict[str, Any]) -> None:
    print(
        json.dumps(
            payload,
            ensure_ascii=False,
            separators=(",", ":"),
            sort_keys=True,
        )
    )


if __name__ == "__main__":
    raise SystemExit(main())
