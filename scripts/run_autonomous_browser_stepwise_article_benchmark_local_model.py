from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))

from src.agent.autonomous_browser_stepwise_article_benchmark import (  # noqa: E402
    build_default_stepwise_article_scenarios,
    run_stepwise_article_benchmark,
    write_stepwise_article_benchmark_summary,
)
from src.agent.autonomous_browser_stepwise_article_local_model import (  # noqa: E402
    STEPWISE_ARTICLE_LOCAL_MODEL_SCHEMA_VERSION,
    StepwiseArticleLocalModelClient,
    StepwiseArticleLocalModelConfig,
    StepwiseArticleLocalModelError,
)


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the guarded local-model stepwise article benchmark."
    )
    parser.add_argument("--base-url", default=None)
    parser.add_argument("--model-alias", required=True)
    parser.add_argument("--scenario-id", action="append", default=[])
    parser.add_argument("--trials-per-scenario", type=int, default=1)
    parser.add_argument("--max-steps", type=int, default=12)
    parser.add_argument("--request-timeout-sec", type=float, default=600.0)
    parser.add_argument("--output-json", default=None)
    parser.add_argument("--allow-model-execution", action="store_true", default=False)
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = parse_args(argv)
    if not args.allow_model_execution:
        _emit(
            {
                "schema_version": STEPWISE_ARTICLE_LOCAL_MODEL_SCHEMA_VERSION,
                "status": "failed",
                "error_code": "allow_model_execution_required",
                "error_message": "--allow-model-execution is required before any model endpoint call.",
                "model_execution": False,
                "real_browser_execution": False,
                "playwright_execution": False,
                "browser_opened": False,
                "fixture_only": True,
                "no_runtime_execution": True,
            }
        )
        return 2
    if not args.base_url or not str(args.base_url).strip():
        _emit(
            {
                "schema_version": STEPWISE_ARTICLE_LOCAL_MODEL_SCHEMA_VERSION,
                "status": "failed",
                "error_code": "base_url_required",
                "error_message": "--base-url is required.",
                "model_execution": False,
                "real_browser_execution": False,
                "playwright_execution": False,
                "browser_opened": False,
                "fixture_only": True,
                "no_runtime_execution": True,
            }
        )
        return 2

    try:
        config = StepwiseArticleLocalModelConfig(
            model_alias=args.model_alias,
            base_url=args.base_url,
            allow_model_execution=True,
            request_timeout_seconds=args.request_timeout_sec,
        )
        scenarios = _selected_scenarios(args.scenario_id)
        summary = run_stepwise_article_benchmark(
            scenarios=scenarios,
            model_factories={
                args.model_alias: lambda: StepwiseArticleLocalModelClient(config=config)
            },
            trials_per_scenario=args.trials_per_scenario,
            max_steps=args.max_steps,
        )
        if args.output_json:
            write_stepwise_article_benchmark_summary(summary, args.output_json)
        _emit(summary)
        return 0 if summary.get("status") == "succeeded" else 1
    except (StepwiseArticleLocalModelError, ValueError) as exc:
        payload = {
            "schema_version": STEPWISE_ARTICLE_LOCAL_MODEL_SCHEMA_VERSION,
            "status": "failed",
            "error_code": getattr(exc, "error_code", "stepwise_article_local_model_failed"),
            "error_message": str(exc),
            "diagnostics": getattr(exc, "diagnostics", {}),
            "model_execution": False,
            "real_browser_execution": False,
            "playwright_execution": False,
            "browser_opened": False,
            "fixture_only": True,
            "no_runtime_execution": True,
        }
        _emit(payload)
        return 2


def _selected_scenarios(selected_ids: list[str]) -> list[object]:
    scenarios = build_default_stepwise_article_scenarios()
    if not selected_ids:
        return list(scenarios.values())
    selected: list[object] = []
    for scenario_id in selected_ids:
        if scenario_id not in scenarios:
            raise ValueError(f"Unknown scenario_id: {scenario_id}")
        selected.append(scenarios[scenario_id])
    return selected


def _emit(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, separators=(",", ":"), sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main())
