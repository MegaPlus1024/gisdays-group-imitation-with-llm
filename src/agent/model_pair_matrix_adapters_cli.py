from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Sequence

from .model_pair_matrix_adapters import (
    MATRIX_RUN_ADAPTER_SUMMARY_FILENAME,
    MatrixRunAdapterInputLoadError,
    write_matrix_run_adapter_outputs,
)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Write offline adapter outputs from a model_pair_matrix_run_summary.json.",
        exit_on_error=False,
    )
    parser.add_argument("--matrix-run-summary", required=True, help="Required model_pair_matrix_run_summary.json.")
    parser.add_argument("--output-dir", required=True, help="Required adapter output directory.")
    parser.add_argument("--write-resource-observations", action="store_true", default=True)
    parser.add_argument("--write-normality-inputs", action="store_true", default=True)
    parser.add_argument("--resource-only", action="store_true", default=False)
    parser.add_argument("--normality-only", action="store_true", default=False)
    parser.add_argument("--task-summary-map", default=None, help="Optional JSON mapping of scenario_id to task summary.")
    parser.add_argument("--adapter-id", default=None, help="Optional adapter id written to the summary.")
    return parser


def main(argv: Sequence[str] | None = None) -> int:
    parser = build_parser()
    try:
        args = parser.parse_args(list(argv) if argv is not None else None)
        if args.resource_only and args.normality_only:
            _print_json(_invalid_payload("resource_only_conflicts_with_normality_only"))
            return 2
        write_resource, write_normality = _selected_outputs(args)
        task_summary_map = _load_task_summary_map(args.task_summary_map)
        summary = write_matrix_run_adapter_outputs(
            args.matrix_run_summary,
            args.output_dir,
            write_resource=write_resource,
            write_normality=write_normality,
            task_summary_by_scenario=task_summary_map,
            adapter_id=args.adapter_id,
        )
    except argparse.ArgumentError:
        _print_json(_invalid_payload("argument_error"))
        return 2
    except MatrixRunAdapterInputLoadError as exc:
        _print_json(_invalid_payload(str(exc)))
        return 2
    except OSError:
        _print_json(_invalid_payload("write_failed", status="write_failed"))
        return 2
    except (ValueError, json.JSONDecodeError) as exc:
        _print_json(_invalid_payload(exc.__class__.__name__))
        return 2

    output_paths = summary.get("output_paths") if isinstance(summary.get("output_paths"), dict) else {}
    _print_json(
        {
            "status": "ok",
            "trial_count": summary.get("trial_count", 0),
            "resource_observation_count": summary.get("resource_observation_count", 0),
            "normality_input_count": summary.get("normality_input_count", 0),
            "normality_missing_trace_count": summary.get("normality_missing_trace_count", 0),
            "resource_observations_path": output_paths.get("resource_observations"),
            "normality_inputs_path": output_paths.get("normality_inputs"),
            "adapter_summary_path": output_paths.get("adapter_summary") or MATRIX_RUN_ADAPTER_SUMMARY_FILENAME,
            "no_runtime_execution": True,
        }
    )
    return 0


def _selected_outputs(args: argparse.Namespace) -> tuple[bool, bool]:
    if args.resource_only:
        return True, False
    if args.normality_only:
        return False, True
    return bool(args.write_resource_observations), bool(args.write_normality_inputs)


def _load_task_summary_map(path: str | None) -> dict[str, str] | None:
    if path is None:
        return None
    try:
        payload = json.loads(Path(path).read_text(encoding="utf-8"))
    except FileNotFoundError as exc:
        raise MatrixRunAdapterInputLoadError("task_summary_map_file_missing") from exc
    except OSError as exc:
        raise MatrixRunAdapterInputLoadError("task_summary_map_file_unreadable") from exc
    except json.JSONDecodeError as exc:
        raise MatrixRunAdapterInputLoadError("task_summary_map_json_malformed") from exc
    if not isinstance(payload, dict):
        raise MatrixRunAdapterInputLoadError("task_summary_map_payload_not_object")
    return {
        str(key): str(value)
        for key, value in payload.items()
        if key is not None and value is not None
    }


def _invalid_payload(error: str, *, status: str = "invalid_input") -> dict[str, object]:
    return {
        "status": status,
        "trial_count": 0,
        "resource_observation_count": 0,
        "normality_input_count": 0,
        "normality_missing_trace_count": 0,
        "resource_observations_path": None,
        "normality_inputs_path": None,
        "adapter_summary_path": None,
        "no_runtime_execution": True,
        "error": error,
    }


def _print_json(payload: dict[str, object]) -> None:
    print(json.dumps(payload, ensure_ascii=False, sort_keys=True))


if __name__ == "__main__":
    raise SystemExit(main(sys.argv[1:]))
