from __future__ import annotations

import argparse
import hashlib
import json
import platform
import sys
from datetime import datetime, timezone
from importlib import metadata
from pathlib import Path
from typing import Any


def sha256_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()


def sha256_file(path: Path) -> str:
    hasher = hashlib.sha256()
    with path.open("rb") as f:
        while True:
            chunk = f.read(1024 * 1024)
            if not chunk:
                break
            hasher.update(chunk)
    return hasher.hexdigest()


def get_package_version(name: str) -> str | None:
    try:
        return metadata.version(name)
    except metadata.PackageNotFoundError:
        return None


def find_latest_successful_smoke_log(log_dir: Path) -> Path:
    # Filenames use YYYYMMDD_HHMMSS_smoke.json, so descending name order is
    # a deterministic newest-to-oldest ordering across filesystems.
    candidates = sorted(log_dir.glob("*_smoke.json"), key=lambda p: p.name, reverse=True)
    for path in candidates:
        try:
            payload = json.loads(path.read_text(encoding="utf-8"))
        except Exception:
            continue
        if payload.get("success") is True:
            return path
    raise FileNotFoundError(f"No successful '*_smoke.json' files found in {log_dir}")


def find_text_file_from_timestamp(log_dir: Path, smoke_log: Path, suffix: str) -> Path | None:
    stem = smoke_log.name.replace("_smoke.json", "")
    candidate = log_dir / f"{stem}_{suffix}.txt"
    return candidate if candidate.exists() else None


def extract_prompt_and_output(smoke: dict[str, Any], prompt_path: Path | None, output_path: Path | None) -> tuple[str, str]:
    prompt_text = ""
    output_text = ""

    if prompt_path and prompt_path.exists():
        prompt_text = prompt_path.read_text(encoding="utf-8")
    elif isinstance(smoke.get("prompt"), str):
        prompt_text = smoke["prompt"]

    if output_path and output_path.exists():
        output_text = output_path.read_text(encoding="utf-8")
    elif isinstance(smoke.get("output"), str):
        output_text = smoke["output"]

    return prompt_text, output_text


def parse_json_if_possible(text: str) -> tuple[dict[str, Any] | None, bool]:
    if not text.strip():
        return None, False
    try:
        parsed = json.loads(text)
    except Exception:
        return None, False
    if isinstance(parsed, dict):
        return parsed, True
    return None, True


def build_manifest(
    experiment_id: str,
    smoke_log_path: Path,
    prompt_source_path: Path | None,
    output_source_path: Path | None,
    model_path: Path,
    raw_smoke: dict[str, Any],
    prompt_text: str,
    output_text: str,
) -> dict[str, Any]:
    raw_response = raw_smoke.get("raw_response") or {}
    usage = raw_response.get("usage") if isinstance(raw_response, dict) else {}
    timings = raw_response.get("timings") if isinstance(raw_response, dict) else None
    if not isinstance(timings, dict):
        timings = None

    parsed_json, parse_ok = parse_json_if_possible(output_text)
    model_exists = model_path.exists()
    model_size = model_path.stat().st_size if model_exists else None
    model_hash = sha256_file(model_path) if model_exists else None

    resource_estimate = raw_smoke.get("resource_estimate")
    if not isinstance(resource_estimate, dict):
        resource_estimate = {}

    prompt_tokens = usage.get("prompt_tokens") if isinstance(usage, dict) else None
    completion_tokens = usage.get("completion_tokens") if isinstance(usage, dict) else None
    total_tokens = usage.get("total_tokens") if isinstance(usage, dict) else None

    return {
        "experiment_id": experiment_id,
        "archived_at": datetime.now(timezone.utc).isoformat(),
        "source": {
            "smoke_log": str(smoke_log_path),
            "prompt_file": str(prompt_source_path) if prompt_source_path else None,
            "output_file": str(output_source_path) if output_source_path else None,
        },
        "runtime": {
            "name": raw_smoke.get("runtime"),
            "base_url": raw_smoke.get("base_url"),
            "endpoint": raw_smoke.get("endpoint"),
            "system_fingerprint": raw_response.get("system_fingerprint") if isinstance(raw_response, dict) else None,
            "server_pid": resource_estimate.get("server_pid"),
        },
        "model": {
            "model_name": raw_smoke.get("model_name"),
            "model_path": str(model_path),
            "model_file_exists": model_exists,
            "model_file_size_bytes": model_size,
            "model_sha256": model_hash,
            "source_url": None,
            "source_note": "Do not invent source URL. Fill manually if known.",
        },
        "prompt": {
            "sha256": sha256_text(prompt_text),
            "text": prompt_text,
        },
        "output": {
            "sha256": sha256_text(output_text),
            "text": output_text,
            "json_parse_success": parse_ok,
            "parsed_json": parsed_json,
            "semantic_validation_performed": False,
            "semantic_validation_note": "Smoke test only checked model response extraction and JSON parsing, not whether action parameters match the future script registry schema.",
        },
        "timing": {
            "wall_time_seconds": raw_smoke.get("wall_time_seconds"),
            "llama_timings": timings,
        },
        "tokens": {
            "prompt_tokens": prompt_tokens if isinstance(prompt_tokens, int) else None,
            "completion_tokens": completion_tokens if isinstance(completion_tokens, int) else None,
            "total_tokens": total_tokens if isinstance(total_tokens, int) else None,
        },
        "resource_estimate": resource_estimate,
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
        "reproduction": {
            "llama_server_command_template_windows": "llama-server `\n  -m models\\gguf\\first_model.gguf `\n  --host 127.0.0.1 `\n  --port 8080 `\n  --ctx-size 4096",
            "smoke_command_windows": "python scripts\\run_llama_smoke.py `\n  --base-url http://127.0.0.1:8080/v1 `\n  --model-name first_model.gguf `\n  --prompt-file prompts\\smoke\\agent_next_action_v1.txt `\n  --out-dir logs\\smoke",
            "notes": [
                "Run llama-server manually before smoke script.",
                "Use --server-pid for future runs if per-process memory tracking is needed.",
                "Do not copy GGUF model files into experiments.",
            ],
        },
        "status": {
            "success": raw_smoke.get("success") is True,
            "limitations": [
                "server_pid was not provided if null in source log",
                "resource estimate is system-level unless server_pid is available",
                "model_name may be an alias if the GGUF file was renamed to first_model.gguf",
                "semantic action validation is not implemented yet",
            ],
        },
    }


def build_readme(manifest: dict[str, Any]) -> str:
    runtime = manifest["runtime"]
    model = manifest["model"]
    output = manifest["output"]
    timing = manifest["timing"]
    res = manifest["resource_estimate"]
    reproduction = manifest["reproduction"]

    return f"""# Local llama-server smoke test v1

## Purpose

Archive one successful local smoke run as a reproducible, reviewable experiment artifact.

## What was tested

- local llama-server OpenAI-compatible chat endpoint call
- fixed smoke prompt execution
- response extraction and JSON parse check
- wall time and resource estimate capture

## Result

- success: `{manifest["status"]["success"]}`
- json_parse_success: `{output["json_parse_success"]}`

This proves local llama-server end-to-end generation works.
This does not prove model quality.
This does not prove the full agent loop.
This does not compare models.
This does not validate script parameters semantically yet.

## Model

- model_name: `{model["model_name"]}`
- model_path: `{model["model_path"]}`
- model_file_exists: `{model["model_file_exists"]}`
- model_file_size_bytes: `{model["model_file_size_bytes"]}`
- model_sha256: `{model["model_sha256"]}`

## Runtime

- name: `{runtime["name"]}`
- base_url: `{runtime["base_url"]}`
- endpoint: `{runtime["endpoint"]}`
- system_fingerprint: `{runtime["system_fingerprint"]}`
- server_pid: `{runtime["server_pid"]}`

## Prompt

- sha256: `{manifest["prompt"]["sha256"]}`

## Output

- sha256: `{output["sha256"]}`

## Timing

- wall_time_seconds: `{timing["wall_time_seconds"]}`
- llama_timings: `{timing["llama_timings"]}`

## Resource estimate

- system_ram_used_before_mb: `{res.get("system_ram_used_before_mb")}`
- system_ram_used_after_mb: `{res.get("system_ram_used_after_mb")}`
- system_ram_delta_mb: `{res.get("system_ram_delta_mb")}`
- system_cpu_percent_avg: `{res.get("system_cpu_percent_avg")}`
- system_cpu_percent_max: `{res.get("system_cpu_percent_max")}`

## Reproduction commands

See `replay_commands.md`.

## Limitations

- {"; ".join(manifest["status"]["limitations"])}

## Next step

Implement model adapter / response validation / semantic action contract, not multi-agent simulation.
"""


def build_replay_commands() -> str:
    return """# Replay Commands (Windows PowerShell)

## 1) Start llama-server

```powershell
llama-server `
  -m models\\gguf\\first_model.gguf `
  --host 127.0.0.1 `
  --port 8080 `
  --ctx-size 4096
```

## 2) Run smoke script

```powershell
python scripts\\run_llama_smoke.py `
  --base-url http://127.0.0.1:8080/v1 `
  --model-name first_model.gguf `
  --prompt-file prompts\\smoke\\agent_next_action_v1.txt `
  --out-dir logs\\smoke
```

## 3) Archive latest successful run

```powershell
python scripts\\archive_smoke_run.py `
  --log-dir logs\\smoke `
  --out-root experiments\\smoke `
  --experiment-id local_llama_server_smoke_v1 `
  --model-path models\\gguf\\first_model.gguf `
  --force
```

## Optional server PID variant for future runs

```powershell
python scripts\\run_llama_smoke.py `
  --base-url http://127.0.0.1:8080/v1 `
  --model-name first_model.gguf `
  --prompt-file prompts\\smoke\\agent_next_action_v1.txt `
  --out-dir logs\\smoke `
  --server-pid <PID>
```
"""


def parse_args() -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Archive the latest successful local smoke run.")
    parser.add_argument("--log-dir", default="logs/smoke")
    parser.add_argument("--out-root", default="experiments/smoke")
    parser.add_argument("--experiment-id", default="local_llama_server_smoke_v1")
    parser.add_argument("--model-path", default="models/gguf/first_model.gguf")
    parser.add_argument("--force", action="store_true")
    return parser.parse_args()


def main() -> int:
    args = parse_args()
    log_dir = Path(args.log_dir)
    out_root = Path(args.out_root)
    out_dir = out_root / args.experiment_id
    model_path = Path(args.model_path)

    if out_dir.exists() and not args.force:
        print(f"Output directory already exists: {out_dir}. Use --force to overwrite.")
        return 1

    if out_dir.exists() and args.force:
        for p in out_dir.glob("*"):
            if p.is_file():
                p.unlink()
        for p in sorted(out_dir.glob("*"), reverse=True):
            if p.is_dir():
                p.rmdir()
    out_dir.mkdir(parents=True, exist_ok=True)

    smoke_log_path = find_latest_successful_smoke_log(log_dir)
    raw_smoke = json.loads(smoke_log_path.read_text(encoding="utf-8"))

    prompt_path = find_text_file_from_timestamp(log_dir, smoke_log_path, "prompt")
    output_path = find_text_file_from_timestamp(log_dir, smoke_log_path, "output")
    prompt_text, output_text = extract_prompt_and_output(raw_smoke, prompt_path, output_path)

    manifest = build_manifest(
        experiment_id=args.experiment_id,
        smoke_log_path=smoke_log_path,
        prompt_source_path=prompt_path,
        output_source_path=output_path,
        model_path=model_path,
        raw_smoke=raw_smoke,
        prompt_text=prompt_text,
        output_text=output_text,
    )

    (out_dir / "raw_smoke.json").write_text(
        json.dumps(raw_smoke, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "prompt.txt").write_text(prompt_text, encoding="utf-8")
    (out_dir / "output.txt").write_text(output_text, encoding="utf-8")
    (out_dir / "manifest.json").write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2), encoding="utf-8"
    )
    (out_dir / "README.md").write_text(build_readme(manifest), encoding="utf-8")
    (out_dir / "replay_commands.md").write_text(build_replay_commands(), encoding="utf-8")

    print(f"Archived successful smoke run to: {out_dir}")
    print(f"Source log: {smoke_log_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
