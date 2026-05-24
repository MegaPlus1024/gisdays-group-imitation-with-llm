from __future__ import annotations

import argparse
import json
import platform
import shutil
import sys
import threading
import time
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any


def now_utc_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


def mb_from_bytes(value: int | float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / (1024.0 * 1024.0), 3)


def get_package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def extract_assistant_content(response_json: dict[str, Any]) -> str:
    try:
        content = response_json["choices"][0]["message"]["content"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ValueError("Missing assistant content at choices[0].message.content") from exc
    if not isinstance(content, str) or not content.strip():
        raise ValueError("Assistant content is empty")
    return content


def mean_ignore_none(values: list[float | int | None]) -> float | None:
    valid = [float(v) for v in values if v is not None]
    if not valid:
        return None
    return round(sum(valid) / len(valid), 6)


def min_ignore_none(values: list[float | int | None]) -> float | None:
    valid = [float(v) for v in values if v is not None]
    if not valid:
        return None
    return round(min(valid), 6)


def max_ignore_none(values: list[float | int | None]) -> float | None:
    valid = [float(v) for v in values if v is not None]
    if not valid:
        return None
    return round(max(valid), 6)


def make_resource_estimate(
    ram_before_mb: float | None,
    ram_after_mb: float | None,
    cpu_avg: float | None,
    cpu_max: float | None,
    server_pid: int | None,
    server_rss_before_mb: float | None,
    server_rss_after_mb: float | None,
    server_metric_error: str | None,
) -> dict[str, Any]:
    ram_delta = None
    if ram_before_mb is not None and ram_after_mb is not None:
        ram_delta = round(ram_after_mb - ram_before_mb, 3)

    server_rss_delta = None
    if server_rss_before_mb is not None and server_rss_after_mb is not None:
        server_rss_delta = round(server_rss_after_mb - server_rss_before_mb, 3)

    return {
        "system_ram_used_before_mb": ram_before_mb,
        "system_ram_used_after_mb": ram_after_mb,
        "system_ram_delta_mb": ram_delta,
        "system_cpu_percent_avg": cpu_avg,
        "system_cpu_percent_max": cpu_max,
        "server_pid": server_pid,
        "server_rss_before_mb": server_rss_before_mb,
        "server_rss_after_mb": server_rss_after_mb,
        "server_rss_delta_mb": server_rss_delta,
        "server_metric_error": server_metric_error,
    }


def build_summary(
    *,
    experiment_id: str,
    runtime: str,
    base_url: str,
    endpoint: str,
    model_name: str,
    prompt_file: str,
    runs_requested: int,
    runs: list[dict[str, Any]],
) -> dict[str, Any]:
    run_count = len(runs)
    success_runs = [r for r in runs if r.get("success") is True]
    failure_runs = [r for r in runs if r.get("success") is not True]

    def values_from_success(path: list[str]) -> list[float | int | None]:
        out: list[float | int | None] = []
        for run in success_runs:
            current: Any = run
            for key in path:
                if not isinstance(current, dict):
                    current = None
                    break
                current = current.get(key)
            out.append(current if isinstance(current, (int, float)) else None)
        return out

    wall_times = values_from_success(["wall_time_seconds"])
    cpu_avg_values = values_from_success(["resource_estimate", "system_cpu_percent_avg"])
    cpu_max_values = values_from_success(["resource_estimate", "system_cpu_percent_max"])
    ram_delta_values = values_from_success(["resource_estimate", "system_ram_delta_mb"])
    server_rss_delta_values = values_from_success(["resource_estimate", "server_rss_delta_mb"])
    prompt_tokens = values_from_success(["usage", "prompt_tokens"])
    completion_tokens = values_from_success(["usage", "completion_tokens"])
    total_tokens = values_from_success(["usage", "total_tokens"])
    prompt_per_second = values_from_success(["llama_timings", "prompt_per_second"])
    predicted_per_second = values_from_success(["llama_timings", "predicted_per_second"])

    return {
        "experiment_id": experiment_id,
        "runtime": runtime,
        "base_url": base_url,
        "endpoint": endpoint,
        "model_name": model_name,
        "prompt_file": prompt_file,
        "runs_requested": runs_requested,
        "run_count": run_count,
        "success_count": len(success_runs),
        "failure_count": len(failure_runs),
        "json_parse_success_count": sum(1 for r in runs if r.get("json_parse_success") is True),
        "wall_time_seconds": {
            "avg": mean_ignore_none(wall_times),
            "min": min_ignore_none(wall_times),
            "max": max_ignore_none(wall_times),
        },
        "cpu_percent": {
            "avg_of_avg": mean_ignore_none(cpu_avg_values),
            "max": max_ignore_none(cpu_max_values),
        },
        "system_ram_delta_mb": {
            "avg": mean_ignore_none(ram_delta_values),
            "min": min_ignore_none(ram_delta_values),
            "max": max_ignore_none(ram_delta_values),
        },
        "server_rss_delta_mb": {
            "avg": mean_ignore_none(server_rss_delta_values),
            "min": min_ignore_none(server_rss_delta_values),
            "max": max_ignore_none(server_rss_delta_values),
        },
        "tokens": {
            "prompt_tokens_avg": mean_ignore_none(prompt_tokens),
            "completion_tokens_avg": mean_ignore_none(completion_tokens),
            "total_tokens_avg": mean_ignore_none(total_tokens),
        },
        "llama_tokens_per_second": {
            "prompt_per_second_avg": mean_ignore_none(prompt_per_second),
            "predicted_per_second_avg": mean_ignore_none(predicted_per_second),
        },
        "failure_cases": [
            {
                "run_index": r.get("run_index"),
                "error_type": r.get("error_type"),
                "error_message": r.get("error_message"),
            }
            for r in failure_runs
        ],
        "created_at": now_utc_iso(),
    }


def build_manifest(
    *,
    experiment_id: str,
    base_url: str,
    endpoint: str,
    model_name: str,
    prompt_file: str,
    out_dir: str,
    runs_requested: int,
) -> dict[str, Any]:
    return {
        "experiment_id": experiment_id,
        "created_at": now_utc_iso(),
        "purpose": "First local runtime baseline for one fixed prompt across repeated calls.",
        "runtime": {
            "name": "llama.cpp / llama-server",
            "base_url": base_url,
            "endpoint": endpoint,
        },
        "model": {
            "model_name": model_name,
            "note": "One model only in this baseline.",
        },
        "prompt": {
            "prompt_file": prompt_file,
            "note": "One fixed prompt only.",
        },
        "command_templates": {
            "llama_server_windows": "llama-server `\n  -m models\\gguf\\first_model.gguf `\n  --host 127.0.0.1 `\n  --port 8080 `\n  --ctx-size 4096",
            "baseline_windows": "python scripts\\run_runtime_baseline.py `\n  --base-url http://127.0.0.1:8080/v1 `\n  --model-name first_model.gguf `\n  --prompt-file prompts\\smoke\\agent_next_action_v1.txt `\n  --out-dir experiments\\baselines\\local_runtime_baseline_v1 `\n  --runs 3 `\n  --force",
        },
        "environment": {
            "platform": platform.platform(),
            "python_version": sys.version,
            "packages": {
                "httpx": get_package_version("httpx"),
                "psutil": get_package_version("psutil"),
                "pydantic": get_package_version("pydantic"),
                "pytest": get_package_version("pytest"),
                "rich": get_package_version("rich"),
            },
        },
        "output_files": {
            "root_dir": out_dir,
            "files": [
                "README.md",
                "manifest.json",
                "runs.jsonl",
                "summary.json",
                "prompt.txt",
                "replay_commands.md",
                "raw/run_1.json ... raw/run_N.json",
            ],
        },
        "limitations": [
            "one model only",
            "one prompt only",
            "no model comparison",
            "no semantic action validation",
            "no agent loop",
            "resource estimates are approximate",
            "server RSS only available if server_pid is passed",
            "results depend on current machine load",
        ],
        "status": {
            "runs_requested": runs_requested,
            "baseline_type": "resource-only, repeated fixed-prompt calls",
        },
    }


def build_readme(summary: dict[str, Any]) -> str:
    return f"""# Local runtime resource baseline v1

## Purpose

This baseline measures the current local llama-server runtime on one fixed prompt.

## Setup

- Runtime: llama.cpp / llama-server
- Endpoint: {summary["endpoint"]}
- Model: {summary["model_name"]}
- Prompt: {summary["prompt_file"]}
- Runs requested: {summary["runs_requested"]}

## What was measured

- wall time per run
- system CPU estimate during each request
- system RAM before/after each request
- optional server RSS delta when `--server-pid` is provided
- token usage and llama timings when returned by server

## What was not measured

This does not prove model quality.
This does not compare models.
This does not test multi-agent load.
This does not validate action parameters semantically.

## Results summary

- run_count: {summary["run_count"]}
- success_count: {summary["success_count"]}
- failure_count: {summary["failure_count"]}
- json_parse_success_count: {summary["json_parse_success_count"]}
- wall_time_seconds(avg/min/max): {summary["wall_time_seconds"]["avg"]} / {summary["wall_time_seconds"]["min"]} / {summary["wall_time_seconds"]["max"]}
- cpu_percent(avg_of_avg/max): {summary["cpu_percent"]["avg_of_avg"]} / {summary["cpu_percent"]["max"]}

## Failure cases

See `summary.json` -> `failure_cases`.

## Reproduction

See `replay_commands.md`.

## Limitations

- one model only
- one prompt only
- no model comparison
- no semantic action validation
- no agent loop
- resource estimates are approximate
- server RSS only available if server_pid is passed
- results depend on current machine load

## Next step

This is the reference point for future comparisons.
"""


def build_replay_commands() -> str:
    return """# Replay Commands (Windows PowerShell)

## Start llama-server

```powershell
llama-server `
  -m models\\gguf\\first_model.gguf `
  --host 127.0.0.1 `
  --port 8080 `
  --ctx-size 4096
```

## Run baseline

```powershell
python scripts\\run_runtime_baseline.py `
  --base-url http://127.0.0.1:8080/v1 `
  --model-name first_model.gguf `
  --prompt-file prompts\\smoke\\agent_next_action_v1.txt `
  --out-dir experiments\\baselines\\local_runtime_baseline_v1 `
  --runs 3 `
  --force
```

## Optional server PID version

```powershell
python scripts\\run_runtime_baseline.py `
  --base-url http://127.0.0.1:8080/v1 `
  --model-name first_model.gguf `
  --prompt-file prompts\\smoke\\agent_next_action_v1.txt `
  --out-dir experiments\\baselines\\local_runtime_baseline_v1 `
  --runs 3 `
  --server-pid <PID> `
  --force
```
"""


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description="Run repeated local llama-server calls for runtime baseline measurement.")
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--model-name", default="first_model.gguf")
    parser.add_argument("--prompt-file", default="prompts/smoke/agent_next_action_v1.txt")
    parser.add_argument("--out-dir", default="experiments/baselines/local_runtime_baseline_v1")
    parser.add_argument("--runs", type=int, default=3)
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=512)
    parser.add_argument("--server-pid", type=int, default=None)
    parser.add_argument("--force", action="store_true")
    return parser


def prepare_output_dir(out_dir: Path, force: bool) -> None:
    if out_dir.exists() and not force:
        raise FileExistsError(f"Output directory already exists: {out_dir}. Use --force to overwrite.")
    if out_dir.exists() and force:
        for child in out_dir.iterdir():
            if child.is_dir():
                shutil.rmtree(child)
            else:
                child.unlink()
    out_dir.mkdir(parents=True, exist_ok=True)
    (out_dir / "raw").mkdir(parents=True, exist_ok=True)


def main() -> int:
    args = build_arg_parser().parse_args()
    if args.runs <= 0:
        print("--runs must be > 0")
        return 1

    import httpx
    import psutil

    base_url = args.base_url.rstrip("/")
    endpoint = f"{base_url}/chat/completions"
    out_dir = Path(args.out_dir)
    prompt_path = Path(args.prompt_file)

    try:
        prepare_output_dir(out_dir, args.force)
    except FileExistsError as exc:
        print(str(exc))
        return 1

    try:
        prompt_text = prompt_path.read_text(encoding="utf-8")
    except Exception as exc:
        print(f"Failed to read prompt file: {exc}")
        return 1

    (out_dir / "prompt.txt").write_text(prompt_text, encoding="utf-8")

    runs: list[dict[str, Any]] = []
    jsonl_path = out_dir / "runs.jsonl"
    runtime_name = "llama.cpp / llama-server"

    for run_index in range(1, args.runs + 1):
        started_at = now_utc_iso()
        started_perf = time.perf_counter()

        server_metric_error: str | None = None
        server_rss_before_mb: float | None = None
        server_rss_after_mb: float | None = None

        if args.server_pid is not None:
            try:
                server_proc = psutil.Process(args.server_pid)
                server_rss_before_mb = mb_from_bytes(server_proc.memory_info().rss)
            except Exception as exc:
                server_metric_error = f"Could not inspect server PID before request: {exc}"

        ram_before_mb = mb_from_bytes(psutil.virtual_memory().used)
        cpu_samples: list[float] = []
        stop_sampling = threading.Event()

        def cpu_sampler() -> None:
            while not stop_sampling.is_set():
                cpu_samples.append(psutil.cpu_percent(interval=0.2))

        sampler_thread = threading.Thread(target=cpu_sampler, daemon=True)
        sampler_thread.start()

        output = ""
        raw_response: dict[str, Any] | None = None
        error_type: str | None = None
        error_message: str | None = None
        success = False
        json_parse_success = False
        json_parse_error: str | None = None
        usage = {
            "prompt_tokens": None,
            "completion_tokens": None,
            "total_tokens": None,
        }
        llama_timings = {
            "prompt_n": None,
            "prompt_ms": None,
            "prompt_per_second": None,
            "predicted_n": None,
            "predicted_ms": None,
            "predicted_per_second": None,
        }

        payload = {
            "model": args.model_name,
            "messages": [
                {
                    "role": "system",
                    "content": "You are a local LLM used for an agent runtime baseline. Return only valid JSON.",
                },
                {"role": "user", "content": prompt_text},
            ],
            "temperature": args.temperature,
            "max_tokens": args.max_tokens,
        }

        try:
            with httpx.Client(timeout=args.timeout_seconds, trust_env=False) as client:
                response = client.post(endpoint, json=payload)
                response.raise_for_status()
                response_data = response.json()
                if isinstance(response_data, dict):
                    raw_response = response_data
                else:
                    raise ValueError("Response JSON is not an object.")
                output = extract_assistant_content(raw_response)
                success = True

                raw_usage = raw_response.get("usage")
                if isinstance(raw_usage, dict):
                    for key in usage:
                        val = raw_usage.get(key)
                        usage[key] = val if isinstance(val, int) else None

                raw_timings = raw_response.get("timings")
                if isinstance(raw_timings, dict):
                    for key in llama_timings:
                        val = raw_timings.get(key)
                        llama_timings[key] = val if isinstance(val, (int, float)) else None

                try:
                    json.loads(output)
                    json_parse_success = True
                except Exception as exc:
                    json_parse_success = False
                    json_parse_error = str(exc)
        except httpx.HTTPError as exc:
            error_type = "request_error"
            error_message = str(exc)
        except ValueError as exc:
            error_type = "response_error"
            error_message = str(exc)
        except Exception as exc:
            error_type = "unexpected_error"
            error_message = str(exc)
        finally:
            finished_at = now_utc_iso()
            wall_time_seconds = round(time.perf_counter() - started_perf, 6)
            stop_sampling.set()
            sampler_thread.join(timeout=2.0)

        ram_after_mb = mb_from_bytes(psutil.virtual_memory().used)
        if args.server_pid is not None:
            try:
                server_proc = psutil.Process(args.server_pid)
                server_rss_after_mb = mb_from_bytes(server_proc.memory_info().rss)
            except Exception as exc:
                msg = f"Could not inspect server PID after request: {exc}"
                server_metric_error = f"{server_metric_error}; {msg}" if server_metric_error else msg

        cpu_avg = round(sum(cpu_samples) / len(cpu_samples), 3) if cpu_samples else None
        cpu_max = round(max(cpu_samples), 3) if cpu_samples else None

        resource_estimate = make_resource_estimate(
            ram_before_mb=ram_before_mb,
            ram_after_mb=ram_after_mb,
            cpu_avg=cpu_avg,
            cpu_max=cpu_max,
            server_pid=args.server_pid,
            server_rss_before_mb=server_rss_before_mb,
            server_rss_after_mb=server_rss_after_mb,
            server_metric_error=server_metric_error,
        )

        run_record = {
            "run_index": run_index,
            "success": success,
            "error_type": error_type,
            "error_message": error_message,
            "started_at": started_at,
            "finished_at": finished_at,
            "wall_time_seconds": wall_time_seconds,
            "runtime": runtime_name,
            "base_url": base_url,
            "endpoint": endpoint,
            "model_name": args.model_name,
            "prompt_file": str(prompt_path),
            "output": output,
            "json_parse_success": json_parse_success,
            "json_parse_error": json_parse_error,
            "raw_response": raw_response,
            "usage": usage,
            "llama_timings": llama_timings,
            "resource_estimate": resource_estimate,
        }
        runs.append(run_record)

        (out_dir / "raw" / f"run_{run_index}.json").write_text(
            json.dumps(run_record, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        with jsonl_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(run_record, ensure_ascii=False) + "\n")

    summary = build_summary(
        experiment_id=out_dir.name,
        runtime=runtime_name,
        base_url=base_url,
        endpoint=endpoint,
        model_name=args.model_name,
        prompt_file=str(prompt_path),
        runs_requested=args.runs,
        runs=runs,
    )

    manifest = build_manifest(
        experiment_id=out_dir.name,
        base_url=base_url,
        endpoint=endpoint,
        model_name=args.model_name,
        prompt_file=str(prompt_path),
        out_dir=str(out_dir),
        runs_requested=args.runs,
    )

    (out_dir / "summary.json").write_text(
        json.dumps(summary, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "README.md").write_text(build_readme(summary), encoding="utf-8")
    (out_dir / "replay_commands.md").write_text(build_replay_commands(), encoding="utf-8")

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
