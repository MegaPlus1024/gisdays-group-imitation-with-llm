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
        description="Check an evaluation model registry entry without starting llama-server."
    )
    parser.add_argument(
        "--models-config",
        default="configs/evaluation_models.json",
        help="Evaluation model registry path.",
    )
    parser.add_argument("--model-id", required=True, help="Stable evaluation model_id to check.")
    parser.add_argument(
        "--project-root",
        default=str(PROJECT_ROOT),
        help="Project root used to resolve relative gguf_path values.",
    )
    parser.add_argument(
        "--require-model-file",
        action="store_true",
        help="Treat a missing GGUF model file as preflight failure.",
    )
    parser.add_argument("--json", action="store_true", help="Print machine-readable JSON.")
    return parser


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    from src.agent.evaluation_models import (
        preflight_evaluation_model,
        resolve_evaluation_model,
    )

    models_config = Path(args.models_config)
    if not models_config.is_absolute():
        models_config = Path(args.project_root) / models_config

    try:
        model = resolve_evaluation_model(args.model_id, models_config)
        preflight = preflight_evaluation_model(
            model,
            args.project_root,
            require_model_file=args.require_model_file,
        )
    except Exception as exc:
        if args.json:
            print(
                json.dumps(
                    {
                        "status": "fail",
                        "model_id": args.model_id,
                        "error": str(exc),
                    },
                    ensure_ascii=False,
                    indent=2,
                )
            )
        else:
            print(f"ERROR: {exc}", file=sys.stderr)
        return 2

    payload = {
        "model": model.model_dump(mode="json"),
        "preflight": preflight.model_dump(mode="json"),
    }
    if args.json:
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(f"model_id: {model.model_id}")
        print(f"display_name: {model.display_name}")
        print(f"model_name: {model.model_name}")
        print(f"gguf_path: {model.gguf_path}")
        print(f"resolved_model_path: {preflight.resolved_model_path}")
        print(f"base_url: {preflight.resolved_base_url}")
        print(f"enabled: {model.enabled}")
        print(f"status: {preflight.status}")
        print(f"can_attempt_local_run: {preflight.can_attempt_local_run}")
        if preflight.issues:
            print("issues:")
            for issue in preflight.issues:
                print(f"- {issue.code}: {issue.message}")
        if preflight.warnings:
            print("warnings:")
            for warning in preflight.warnings:
                print(f"- {warning.code}: {warning.message}")

    return 0 if preflight.status != "fail" else 1


if __name__ == "__main__":
    raise SystemExit(main())
