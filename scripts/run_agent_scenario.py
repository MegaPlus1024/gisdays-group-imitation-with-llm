from __future__ import annotations

import argparse
import sys
from pathlib import Path


DEFAULT_FAKE_MODEL_ID = "fake_model"
DEFAULT_FAKE_MODEL_NAME = "fake-scripted-provider"
PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description=(
            "Run a reproducible local-LLM agent scenario. "
            "Default mode is fake/scripted and does not call llama-server."
        )
    )
    parser.add_argument(
        "--scenario",
        default="configs/evaluation_scenarios/office_worker_basic_session.json",
        help="Path to evaluation scenario JSON, relative to project root unless absolute.",
    )
    parser.add_argument(
        "--models-config",
        default="configs/evaluation_models.json",
        help="Evaluation model registry path, relative to project root unless absolute.",
    )
    parser.add_argument(
        "--model-id",
        default=None,
        help="Stable evaluation model_id. When set, model metadata is loaded from --models-config.",
    )
    parser.add_argument(
        "--model-name",
        default=DEFAULT_FAKE_MODEL_NAME,
        help="Model/runtime name. Required to be non-fake in --mode local.",
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="OpenAI-compatible local runtime base URL, required in --mode local.",
    )
    parser.add_argument(
        "--out-dir",
        default="experiments/scenario_runs/default",
        help="Artifact output directory, relative to project root unless absolute.",
    )
    parser.add_argument("--run-id", default="scenario_run", help="Run id stored in artifacts.")
    parser.add_argument("--max-steps", type=int, default=None, help="Override scenario stop_policy.max_steps.")
    parser.add_argument("--mode", choices=["fake", "local"], default="fake", help="Action provider mode.")
    parser.add_argument(
        "--scripted-actions",
        default=None,
        help="Fake-mode actions as JSON text or path to a JSON list/object with an actions list.",
    )
    parser.add_argument(
        "--execute-actions",
        dest="execute_actions",
        action="store_true",
        default=True,
        help="Execute accepted actions through ScriptExecutionBridge. This is the default.",
    )
    parser.add_argument(
        "--no-execute-actions",
        dest="execute_actions",
        action="store_false",
        help="Only render/select/parse/validate actions; do not execute ScriptExecutionBridge.",
    )
    parser.add_argument("--force", action="store_true", help="Overwrite an existing artifact directory.")
    parser.add_argument(
        "--allow-missing-model-file",
        action="store_true",
        help="Allow local mode preflight to continue when registry gguf_path is missing.",
    )
    parser.add_argument(
        "--allow-disabled-model",
        action="store_true",
        help="Allow local mode preflight to continue for a disabled registry model.",
    )
    parser.add_argument(
        "--repair-attempts",
        type=int,
        default=0,
        help="Maximum repair attempts per step after recoverable parse/validation failure.",
    )
    parser.add_argument(
        "--repair-on-parse-failure",
        dest="repair_on_parse_failure",
        action="store_true",
        default=True,
        help="Allow repair attempts after malformed or schema-invalid JSON. This is the default.",
    )
    parser.add_argument(
        "--no-repair-on-parse-failure",
        dest="repair_on_parse_failure",
        action="store_false",
        help="Disable repair attempts after parse failures.",
    )
    parser.add_argument(
        "--repair-on-validation-failure",
        dest="repair_on_validation_failure",
        action="store_true",
        default=True,
        help="Allow repair attempts after action validation failures. This is the default.",
    )
    parser.add_argument(
        "--no-repair-on-validation-failure",
        dest="repair_on_validation_failure",
        action="store_false",
        help="Disable repair attempts after validation failures.",
    )
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from src.agent.experiment_scenario_runner import (
        ExperimentScenarioRunner,
        ExperimentScenarioRunnerConfig,
        load_scripted_actions,
    )
    from src.agent.evaluation_models import (
        preflight_evaluation_model,
        resolve_evaluation_model,
    )

    requested_model_id = args.model_id
    model_id = args.model_id or DEFAULT_FAKE_MODEL_ID
    model_name = args.model_name
    base_url = args.base_url
    timeout_seconds = 120.0
    temperature = 0.0
    max_tokens = 512
    model_registry_spec = None
    model_preflight_result = None
    cli_overrides: dict[str, object] = {}

    if args.model_id:
        models_config_path = Path(args.models_config)
        if not models_config_path.is_absolute():
            models_config_path = PROJECT_ROOT / models_config_path
        try:
            model_spec = resolve_evaluation_model(args.model_id, models_config_path)
        except Exception as exc:
            print(f"ERROR: cannot resolve evaluation model_id '{args.model_id}': {exc}", file=sys.stderr)
            return 2

        preflight = preflight_evaluation_model(
            model_spec,
            PROJECT_ROOT,
            require_model_file=(args.mode == "local" and not args.allow_missing_model_file),
            allow_disabled=args.allow_disabled_model,
        )
        model_registry_spec = model_spec.model_dump(mode="json")
        model_preflight_result = preflight.model_dump(mode="json")
        model_id = model_spec.model_id
        timeout_seconds = model_spec.timeout_seconds
        temperature = model_spec.temperature
        max_tokens = model_spec.max_tokens

        if args.model_name == DEFAULT_FAKE_MODEL_NAME:
            model_name = model_spec.model_name
        elif args.model_name != model_spec.model_name:
            cli_overrides["model_name"] = {
                "registry_value": model_spec.model_name,
                "cli_value": args.model_name,
            }

        if base_url is None:
            base_url = model_spec.base_url
        elif base_url.rstrip("/") != model_spec.base_url.rstrip("/"):
            cli_overrides["base_url"] = {
                "registry_value": model_spec.base_url,
                "cli_value": base_url,
            }

        if args.mode == "local" and preflight.status == "fail":
            print(
                "ERROR: evaluation model preflight failed before local run:\n"
                + "\n".join(f"- {issue.code}: {issue.message}" for issue in preflight.issues),
                file=sys.stderr,
            )
            return 2

    if args.mode == "local":
        if not base_url:
            parser.error("--mode local requires --base-url or --model-id resolved from --models-config")
        if model_name == DEFAULT_FAKE_MODEL_NAME:
            parser.error("--mode local requires --model-name or --model-id resolved from --models-config")

    scripted_actions = load_scripted_actions(args.scripted_actions) if args.mode == "fake" else []
    config = ExperimentScenarioRunnerConfig(
        project_root=PROJECT_ROOT,
        mode=args.mode,
        scenario_path=args.scenario,
        out_dir=args.out_dir,
        run_id=args.run_id,
        model_id=model_id,
        requested_model_id=requested_model_id,
        model_name=model_name,
        base_url=base_url,
        models_config_path=args.models_config if args.model_id else None,
        model_registry_spec=model_registry_spec,
        model_preflight_result=model_preflight_result,
        model_cli_overrides=cli_overrides,
        timeout_seconds=timeout_seconds,
        temperature=temperature,
        max_tokens=max_tokens,
        max_steps=args.max_steps,
        execute_actions=args.execute_actions,
        force=args.force,
        repair_attempts_per_step=args.repair_attempts,
        repair_on_parse_failure=args.repair_on_parse_failure,
        repair_on_validation_failure=args.repair_on_validation_failure,
        scripted_actions=scripted_actions,
    )

    try:
        result = ExperimentScenarioRunner(config).run()
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: scenario run failed: {exc}", file=sys.stderr)
        return 1

    print(f"status: {result.status}")
    print(f"success: {result.success}")
    print(f"run_id: {result.run_id}")
    print(f"scenario_id: {result.scenario_id}")
    print(f"model_id: {model_id}")
    if model_preflight_result is not None:
        print(f"model_preflight_status: {model_preflight_result['status']}")
    print(f"steps: {len(result.steps)}")
    print(f"stopped_reason: {result.stopped_reason}")
    print(f"artifact_dir: {result.out_dir}")
    return 0 if result.status in {"completed", "stopped"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
