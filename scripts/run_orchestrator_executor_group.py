from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path


PROJECT_ROOT = Path(__file__).resolve().parents[1]
if str(PROJECT_ROOT) not in sys.path:
    sys.path.insert(0, str(PROJECT_ROOT))


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run the orchestrator/executor multi-agent MVP in fake or local-compatible mode."
    )
    parser.add_argument("--mode", choices=["fake", "local"], default="fake")
    parser.add_argument("--models-config", default="configs/evaluation_models.json")
    parser.add_argument("--scenario", default="configs/multi_agent_scenarios/office_developer_group_basic.json")
    parser.add_argument("--out-dir", required=True)
    parser.add_argument("--run-id", default="orchestrator_executor_group_run")
    parser.add_argument("--orchestrator-model-id", default="second_model")
    parser.add_argument("--executor-model-id", default="first_model")
    parser.add_argument("--orchestrator-base-url", default=None)
    parser.add_argument("--executor-base-url", default=None)
    parser.add_argument("--orchestrator-model-name", default=None)
    parser.add_argument("--executor-model-name", default=None)
    parser.add_argument("--orchestrator-max-tokens", type=int, default=None)
    parser.add_argument("--orchestrator-temperature", type=float, default=None)
    parser.add_argument("--orchestrator-repair-attempts", type=int, default=0)
    parser.add_argument("--max-group-steps", type=int, default=None)
    parser.add_argument("--max-steps-per-agent", type=int, default=None)
    parser.add_argument("--repair-attempts", type=int, default=0)
    parser.add_argument("--execute-actions", dest="execute_actions", action="store_true", default=True)
    parser.add_argument("--no-execute-actions", dest="execute_actions", action="store_false")
    parser.add_argument("--force", action="store_true")
    parser.add_argument("--json-only", action="store_true")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from src.agent.orchestrator_executor_pipeline import (
        OrchestratorExecutorRunConfig,
        OrchestratorExecutorRunner,
    )

    config = OrchestratorExecutorRunConfig(
        project_root=PROJECT_ROOT,
        mode=args.mode,
        models_config_path=args.models_config,
        scenario_path=args.scenario,
        out_dir=args.out_dir,
        run_id=args.run_id,
        orchestrator_model_id=args.orchestrator_model_id,
        executor_model_id=args.executor_model_id,
        orchestrator_base_url=args.orchestrator_base_url,
        executor_base_url=args.executor_base_url,
        orchestrator_model_name=args.orchestrator_model_name,
        executor_model_name=args.executor_model_name,
        orchestrator_max_tokens=args.orchestrator_max_tokens,
        orchestrator_temperature=args.orchestrator_temperature,
        orchestrator_repair_attempts=args.orchestrator_repair_attempts,
        max_group_steps=args.max_group_steps,
        max_steps_per_agent=args.max_steps_per_agent,
        repair_attempts=args.repair_attempts,
        execute_actions=args.execute_actions,
        force=args.force,
    )
    try:
        result = OrchestratorExecutorRunner(config).run()
    except FileExistsError as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 2
    except Exception as exc:
        print(f"ERROR: orchestrator/executor group run failed: {exc}", file=sys.stderr)
        return 1

    payload = result.model_dump(mode="json")
    if args.json_only:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
        return 0 if result.status in {"completed", "completed_with_failures"} else 1

    print(f"run_id: {result.run_id}")
    print(f"scenario_id: {result.scenario_id}")
    print(f"status: {result.status}")
    print(f"success: {result.success}")
    print(f"orchestrator_model_id: {result.orchestrator_model_id}")
    print(f"executor_model_ids: {','.join(result.executor_model_ids)}")
    print(f"orchestrator_base_url_override: {config.orchestrator_base_url or 'registry'}")
    print(f"executor_base_url_override: {config.executor_base_url or 'registry'}")
    print(f"pair_quality_score: {result.quality_metrics.pair_quality_score}")
    print(f"artifact_dir: {result.artifact_dir}")
    return 0 if result.status in {"completed", "completed_with_failures"} else 1


if __name__ == "__main__":
    raise SystemExit(main())
