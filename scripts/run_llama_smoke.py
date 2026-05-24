from __future__ import annotations

import argparse
import json
import threading
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any


def make_timestamp() -> str:
    return datetime.now().strftime("%Y%m%d_%H%M%S")


def mb_from_bytes(value: int | float | None) -> float | None:
    if value is None:
        return None
    return round(float(value) / (1024.0 * 1024.0), 3)


def extract_output_text(response_json: dict[str, Any]) -> str:
    return response_json["choices"][0]["message"]["content"]


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


def build_arg_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="Run one local llama-server smoke request and persist prompt/output/metadata logs."
    )
    parser.add_argument("--base-url", default="http://127.0.0.1:8080/v1")
    parser.add_argument("--model-name", required=True)
    parser.add_argument(
        "--prompt-file", default="prompts/smoke/agent_next_action_v1.txt"
    )
    parser.add_argument("--out-dir", default="logs/smoke")
    parser.add_argument("--timeout-seconds", type=float, default=120.0)
    parser.add_argument("--server-pid", type=int, default=None)
    parser.add_argument("--temperature", type=float, default=0.0)
    parser.add_argument("--max-tokens", type=int, default=512)
    return parser


def main() -> int:
    args = build_arg_parser().parse_args()

    import httpx
    import psutil

    prompt_path = Path(args.prompt_file)
    out_dir = Path(args.out_dir)
    out_dir.mkdir(parents=True, exist_ok=True)

    timestamp = make_timestamp()
    prompt_out_path = out_dir / f"{timestamp}_prompt.txt"
    output_out_path = out_dir / f"{timestamp}_output.txt"
    smoke_out_path = out_dir / f"{timestamp}_smoke.json"

    created_at = datetime.now(timezone.utc).isoformat()
    endpoint = f"{args.base_url.rstrip('/')}/chat/completions"

    success = False
    output_text = ""
    raw_response: dict[str, Any] | None = None
    json_parse_success = False
    json_parse_error: str | None = None

    server_metric_error: str | None = None
    server_rss_before_mb: float | None = None
    server_rss_after_mb: float | None = None

    try:
        prompt_text = prompt_path.read_text(encoding="utf-8")
    except Exception as exc:
        payload = {
            "success": False,
            "runtime": "llama.cpp / llama-server",
            "base_url": args.base_url,
            "endpoint": endpoint,
            "model_name": args.model_name,
            "prompt_file": str(prompt_path),
            "prompt": "",
            "output": "",
            "raw_response": None,
            "json_parse_success": False,
            "json_parse_error": f"Prompt read failed: {exc}",
            "wall_time_seconds": None,
            "created_at": created_at,
            "resource_estimate": make_resource_estimate(
                ram_before_mb=None,
                ram_after_mb=None,
                cpu_avg=None,
                cpu_max=None,
                server_pid=args.server_pid,
                server_rss_before_mb=None,
                server_rss_after_mb=None,
                server_metric_error=None,
            ),
        }
        smoke_out_path.write_text(
            json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
        )
        return 1

    prompt_out_path.write_text(prompt_text, encoding="utf-8")

    request_body = {
        "model": args.model_name,
        "messages": [
            {
                "role": "system",
                "content": "You are a local LLM used for an agent smoke test. Return only valid JSON.",
            },
            {"role": "user", "content": prompt_text},
        ],
        "temperature": args.temperature,
        "max_tokens": args.max_tokens,
    }

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

    wall_start = time.perf_counter()
    request_error: str | None = None
    response_json_error: str | None = None

    try:
        with httpx.Client(timeout=args.timeout_seconds) as client:
            response = client.post(endpoint, json=request_body)
            response.raise_for_status()
            raw_response = response.json()
    except Exception as exc:
        request_error = str(exc)
    finally:
        wall_time_seconds = round(time.perf_counter() - wall_start, 6)
        stop_sampling.set()
        sampler_thread.join(timeout=2.0)

    ram_after_mb = mb_from_bytes(psutil.virtual_memory().used)

    if args.server_pid is not None:
        try:
            server_proc = psutil.Process(args.server_pid)
            server_rss_after_mb = mb_from_bytes(server_proc.memory_info().rss)
        except Exception as exc:
            message = f"Could not inspect server PID after request: {exc}"
            server_metric_error = (
                f"{server_metric_error}; {message}" if server_metric_error else message
            )

    cpu_avg = round(sum(cpu_samples) / len(cpu_samples), 3) if cpu_samples else None
    cpu_max = round(max(cpu_samples), 3) if cpu_samples else None

    if request_error is None and raw_response is not None:
        try:
            output_text = extract_output_text(raw_response)
            success = True
        except Exception as exc:
            response_json_error = f"Output extraction failed: {exc}"

    if output_text:
        try:
            json.loads(output_text)
            json_parse_success = True
        except Exception as exc:
            json_parse_error = str(exc)
            json_parse_success = False

    if request_error:
        json_parse_error = f"HTTP request failed: {request_error}"
    elif response_json_error:
        json_parse_error = response_json_error

    output_out_path.write_text(output_text, encoding="utf-8")

    payload = {
        "success": success,
        "runtime": "llama.cpp / llama-server",
        "base_url": args.base_url,
        "endpoint": endpoint,
        "model_name": args.model_name,
        "prompt_file": str(prompt_path),
        "prompt": prompt_text,
        "output": output_text,
        "raw_response": raw_response,
        "json_parse_success": json_parse_success,
        "json_parse_error": json_parse_error,
        "wall_time_seconds": wall_time_seconds,
        "created_at": created_at,
        "resource_estimate": make_resource_estimate(
            ram_before_mb=ram_before_mb,
            ram_after_mb=ram_after_mb,
            cpu_avg=cpu_avg,
            cpu_max=cpu_max,
            server_pid=args.server_pid,
            server_rss_before_mb=server_rss_before_mb,
            server_rss_after_mb=server_rss_after_mb,
            server_metric_error=server_metric_error,
        ),
    }

    smoke_out_path.write_text(
        json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8"
    )

    return 0 if success else 1


if __name__ == "__main__":
    raise SystemExit(main())
