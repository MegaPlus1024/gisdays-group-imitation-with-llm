from __future__ import annotations

import argparse
import json
import shutil
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def load_summary(path: Path) -> dict[str, Any]:
    if not path.exists():
        raise FileNotFoundError(f"Summary file not found: {path}")
    data = json.loads(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError(f"Summary is not a JSON object: {path}")
    return data


def get_nested(data: dict[str, Any], keys: list[str]) -> Any:
    current: Any = data
    for key in keys:
        if not isinstance(current, dict):
            return None
        current = current.get(key)
    return current


def as_number(value: Any) -> float | None:
    if isinstance(value, (int, float)):
        return float(value)
    return None


def delta(a: float | None, b: float | None) -> float | None:
    if a is None or b is None:
        return None
    return round(b - a, 6)


def ratio(a: float | None, b: float | None) -> float | None:
    if a is None or b is None or a == 0:
        return None
    return round(b / a, 6)


def extract_metrics(summary: dict[str, Any], path: str) -> dict[str, Any]:
    return {
        "summary_path": path,
        "model_name": summary.get("model_name"),
        "run_count": summary.get("run_count"),
        "success_count": summary.get("success_count"),
        "failure_count": summary.get("failure_count"),
        "json_parse_success_count": summary.get("json_parse_success_count"),
        "wall_time_seconds": {
            "avg": get_nested(summary, ["wall_time_seconds", "avg"]),
            "min": get_nested(summary, ["wall_time_seconds", "min"]),
            "max": get_nested(summary, ["wall_time_seconds", "max"]),
        },
        "cpu_percent": {
            "avg_of_avg": get_nested(summary, ["cpu_percent", "avg_of_avg"]),
            "max": get_nested(summary, ["cpu_percent", "max"]),
        },
        "system_ram_delta_mb": {
            "avg": get_nested(summary, ["system_ram_delta_mb", "avg"]),
            "min": get_nested(summary, ["system_ram_delta_mb", "min"]),
            "max": get_nested(summary, ["system_ram_delta_mb", "max"]),
        },
        "server_rss_delta_mb": {
            "avg": get_nested(summary, ["server_rss_delta_mb", "avg"]),
            "min": get_nested(summary, ["server_rss_delta_mb", "min"]),
            "max": get_nested(summary, ["server_rss_delta_mb", "max"]),
        },
        "tokens": {
            "prompt_tokens_avg": get_nested(summary, ["tokens", "prompt_tokens_avg"]),
            "completion_tokens_avg": get_nested(summary, ["tokens", "completion_tokens_avg"]),
            "total_tokens_avg": get_nested(summary, ["tokens", "total_tokens_avg"]),
        },
        "llama_tokens_per_second": {
            "prompt_per_second_avg": get_nested(summary, ["llama_tokens_per_second", "prompt_per_second_avg"]),
            "predicted_per_second_avg": get_nested(summary, ["llama_tokens_per_second", "predicted_per_second_avg"]),
        },
    }


def build_comparison(first: dict[str, Any], second: dict[str, Any], first_path: str, second_path: str) -> dict[str, Any]:
    first_metrics = extract_metrics(first, first_path)
    second_metrics = extract_metrics(second, second_path)

    first_wall = as_number(get_nested(first, ["wall_time_seconds", "avg"]))
    second_wall = as_number(get_nested(second, ["wall_time_seconds", "avg"]))
    first_cpu = as_number(get_nested(first, ["cpu_percent", "avg_of_avg"]))
    second_cpu = as_number(get_nested(second, ["cpu_percent", "avg_of_avg"]))
    first_total_tokens = as_number(get_nested(first, ["tokens", "total_tokens_avg"]))
    second_total_tokens = as_number(get_nested(second, ["tokens", "total_tokens_avg"]))
    first_pred_s = as_number(get_nested(first, ["llama_tokens_per_second", "predicted_per_second_avg"]))
    second_pred_s = as_number(get_nested(second, ["llama_tokens_per_second", "predicted_per_second_avg"]))

    return {
        "comparison_id": "two_model_runtime_comparison_v1",
        "created_at": now_utc_iso(),
        "first": first_metrics,
        "second": second_metrics,
        "deltas": {
            "wall_time_seconds_avg_delta": delta(first_wall, second_wall),
            "wall_time_seconds_avg_ratio": ratio(first_wall, second_wall),
            "cpu_percent_avg_delta": delta(first_cpu, second_cpu),
            "total_tokens_avg_delta": delta(first_total_tokens, second_total_tokens),
            "predicted_per_second_avg_delta": delta(first_pred_s, second_pred_s),
        },
        "failure_cases": {
            "first": first.get("failure_cases"),
            "second": second.get("failure_cases"),
        },
        "interpretation_guardrails": [
            "This comparison is numeric only.",
            "It does not prove general model quality.",
            "It does not validate semantic action correctness.",
            "It uses one fixed prompt only.",
            "It does not measure multi-agent load.",
        ],
    }


def build_markdown(comp: dict[str, Any]) -> str:
    f = comp["first"]
    s = comp["second"]
    d = comp["deltas"]
    return f"""# Two-model local runtime comparison v1

| Metric | First ({f.get("model_name")}) | Second ({s.get("model_name")}) |
|---|---:|---:|
| success_count | {f.get("success_count")} | {s.get("success_count")} |
| failure_count | {f.get("failure_count")} | {s.get("failure_count")} |
| json_parse_success_count | {f.get("json_parse_success_count")} | {s.get("json_parse_success_count")} |
| wall_time_seconds.avg | {get_nested(f, ["wall_time_seconds", "avg"])} | {get_nested(s, ["wall_time_seconds", "avg"])} |
| cpu_percent.avg_of_avg | {get_nested(f, ["cpu_percent", "avg_of_avg"])} | {get_nested(s, ["cpu_percent", "avg_of_avg"])} |
| tokens.total_tokens_avg | {get_nested(f, ["tokens", "total_tokens_avg"])} | {get_nested(s, ["tokens", "total_tokens_avg"])} |
| llama_tokens_per_second.predicted_per_second_avg | {get_nested(f, ["llama_tokens_per_second", "predicted_per_second_avg"])} | {get_nested(s, ["llama_tokens_per_second", "predicted_per_second_avg"])} |

## Numeric observations

- wall_time_seconds_avg_delta: {d.get("wall_time_seconds_avg_delta")}
- wall_time_seconds_avg_ratio: {d.get("wall_time_seconds_avg_ratio")}
- cpu_percent_avg_delta: {d.get("cpu_percent_avg_delta")}
- total_tokens_avg_delta: {d.get("total_tokens_avg_delta")}
- predicted_per_second_avg_delta: {d.get("predicted_per_second_avg_delta")}

## Limitations

- This comparison is numeric only.
- It does not prove general model quality.
- It does not validate semantic action correctness.
- It uses one fixed prompt only.
- It does not measure multi-agent load.

## Next step

Keep runtime comparison numeric and add semantic action validation in a separate step.
"""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Compare two runtime baseline summary.json files.")
    parser.add_argument("--first-summary", default="experiments/baselines/local_runtime_baseline_v1/summary.json")
    parser.add_argument("--second-summary", default="experiments/baselines/second_model_runtime_baseline_v1/summary.json")
    parser.add_argument("--out-dir", default="experiments/comparisons/two_model_runtime_comparison_v1")
    parser.add_argument("--force", action="store_true")
    return parser


def prepare_out_dir(path: Path, force: bool) -> None:
    if path.exists() and not force:
        raise FileExistsError(f"Output directory already exists: {path}. Use --force to overwrite.")
    if path.exists() and force:
        for child in path.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    path.mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = build_arg_parser().parse_args()
    first_path = Path(args.first_summary)
    second_path = Path(args.second_summary)
    out_dir = Path(args.out_dir)

    try:
        prepare_out_dir(out_dir, args.force)
        first = load_summary(first_path)
        second = load_summary(second_path)
    except (FileNotFoundError, FileExistsError, ValueError) as exc:
        print(str(exc))
        return 1

    comp = build_comparison(first, second, str(first_path), str(second_path))
    (out_dir / "comparison.json").write_text(json.dumps(comp, ensure_ascii=False, indent=2), encoding="utf-8")
    (out_dir / "comparison.md").write_text(build_markdown(comp), encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
