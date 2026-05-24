# Smoke Test v1

## Purpose of Smoke Test

This smoke test validates one repeatable local end-to-end call path:

- fixed prompt file
- local `llama-server` OpenAI-compatible endpoint
- one model name passed explicitly
- saved prompt/output/metadata artifacts

The goal is to confirm runtime wiring and logging, not agent quality.

## What This Test Proves

- The local script can call `http://127.0.0.1:8080/v1/chat/completions` (or another provided base URL).
- A response can be received and assistant output text can be extracted.
- Logs are persisted with deterministic filenames and metadata.
- Runtime metadata includes model name, wall time, system RAM estimate, and CPU estimate.
- Optional per-process server RSS metrics can be logged when `--server-pid` is provided.

## What This Test Does Not Prove

- It does not prove model quality or reliability.
- It does not compare multiple models.
- It does not prove full agent-loop correctness.
- It does not validate autonomous planning behavior.
- It does not benchmark performance rigorously.

## Required Manual Setup

1. Install or build `llama.cpp` separately.
2. Place a GGUF model at `models/gguf/first_model.gguf` or another explicit local path.
3. Start `llama-server` manually before running the smoke script.

## Repeatable llama-server Command (Windows)

```powershell
llama-server ^
  -m models\gguf\first_model.gguf ^
  --host 127.0.0.1 ^
  --port 8080 ^
  --ctx-size 4096
```

## Smoke Script Command

```powershell
python scripts\run_llama_smoke.py ^
  --base-url http://127.0.0.1:8080/v1 ^
  --model-name first_model.gguf ^
  --prompt-file prompts\smoke\agent_next_action_v1.txt ^
  --out-dir logs\smoke
```

## Optional Command With Server PID

```powershell
python scripts\run_llama_smoke.py ^
  --base-url http://127.0.0.1:8080/v1 ^
  --model-name first_model.gguf ^
  --prompt-file prompts\smoke\agent_next_action_v1.txt ^
  --out-dir logs\smoke ^
  --server-pid 12345
```

## Success Criteria

- Script exits with code `0`.
- `*_prompt.txt`, `*_output.txt`, and `*_smoke.json` are created in `logs/smoke/`.
- JSON metadata includes required fields including `model_name`, `wall_time_seconds`, and `resource_estimate`.
- `success` is `true` only when HTTP succeeded and output text extraction succeeded.

## Failure Cases

- Server unreachable or request failure: exit code `1`.
- HTTP response malformed or output path missing: exit code `1`.
- Prompt file cannot be read: exit code `1`.
- Model output invalid JSON: exit code remains `0` if text output was extracted, but `json_parse_success` is `false`.

## Why This Is Not Yet Model Comparison

This flow runs one model per invocation and only validates connectivity + logging. It does not evaluate quality across model variants, prompt suites, or repeated trials.

## Why This Is Not Yet the Full Agent Loop

The script sends one fixed prompt and records one response. It does not execute actions, maintain iterative state, or run tool-feedback cycles.

## Model adapter layer

`scripts/run_llama_smoke.py` is a one-off experiment/logging tool.

`src/agent/llm_client.py` contains `LocalLLMClient`, the reusable runtime boundary for future agent code. Future runner code should call:

```python
next_action = client.generate_next_action(agent_state)
```

At this stage, the adapter validates JSON structure with `NextAction`. Script-registry semantic validation is intentionally a later task.

## Archiving a successful smoke run

Archive the latest successful smoke run into a reproducible experiment record:

```powershell
python scripts\archive_smoke_run.py `
  --log-dir logs\smoke `
  --out-root experiments\smoke `
  --experiment-id local_llama_server_smoke_v1 `
  --model-path models\gguf\first_model.gguf `
  --force
```

Archive output location:

```text
experiments/smoke/local_llama_server_smoke_v1/
```
