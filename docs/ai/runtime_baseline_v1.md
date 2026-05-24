# Runtime Baseline v1

## Why this baseline exists

This baseline captures the first repeatable resource profile for the current local llama-server runtime using one fixed prompt and repeated calls.

## Relation to smoke test

The smoke test proved end-to-end connectivity and basic logging for a single run. This baseline extends that by running the same prompt multiple times and aggregating latency, CPU, RAM, token, and timing metrics.

## How to run

1. Start `llama-server` manually.
2. Run:

```powershell
python scripts\run_runtime_baseline.py `
  --base-url http://127.0.0.1:8080/v1 `
  --model-name first_model.gguf `
  --prompt-file prompts\smoke\agent_next_action_v1.txt `
  --out-dir experiments\baselines\local_runtime_baseline_v1 `
  --runs 3 `
  --force
```

## How to interpret summary.json

- `success_count` / `failure_count` show request stability.
- `wall_time_seconds` reflects response latency for successful runs.
- `cpu_percent` and `system_ram_delta_mb` are approximate system-level resource estimates.
- `tokens` and `llama_tokens_per_second` are averaged only from successful runs.
- `failure_cases` preserves exact per-run errors.

## Why repeated runs matter

Single-run measurements are noisy. Repeated runs give a better initial reference range for latency and resource usage.

## Why this is not model comparison

This baseline uses one model and one prompt. It is a local runtime reference point, not a cross-model evaluation.

## How this baseline will be used later

Future runtime or adapter changes can be compared against this baseline to detect regressions or improvements in stability and cost on the same machine.
