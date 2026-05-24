# Second Model Smoke Test

## Purpose

This workflow prepares a controlled second-model run using the same local runtime path and the same fixed prompt so the results can be compared numerically to the first baseline.

## What must remain constant

- prompt file: `prompts/smoke/agent_next_action_v1.txt`
- temperature: `0`
- max_tokens: `512`
- endpoint shape: `{base_url}/chat/completions`
- smoke script: `scripts/run_llama_smoke.py`
- baseline script: `scripts/run_runtime_baseline.py`
- measurement fields and summary schema

Changing the prompt invalidates direct comparison with the first baseline.

## What is allowed to change

- model file
- model name (use explicit filename unless alias mapping is recorded)
- optional quantization choice

## Recommended second-model choices

- same base model with a different quantization
- `qwen2.5-3b-instruct-q4_k_m.gguf`
- a smaller fallback GGUF model for CPU checks

Use the same fixed prompt as the first baseline.
Model metadata must be recorded in `docs/ai/model_registry.md`.
Do not use `second_model.gguf` alias unless it is mapped in the registry.

## Why this is not full model comparison

This process uses one fixed prompt and three runs. It is a runtime sanity and resource check, not a broad quality benchmark.

## How to interpret results

- compare only numeric fields in `summary.json` and generated comparison outputs
- focus on stability (`success_count`, `failure_count`, `json_parse_success_count`)
- compare latency/CPU/RAM/tokens as fixed-prompt runtime indicators

## Avoid unsupported claims

Do not claim one model is "better" without numeric evidence from the recorded JSON fields and future semantic validation data.

## Done criteria

- second model smoke run is archived as `experiments/smoke/second_model_smoke_v1/`
- second model 3-run baseline exists as `experiments/baselines/second_model_runtime_baseline_v1/`
- comparison artifacts are generated in `experiments/comparisons/two_model_runtime_comparison_v1/`
- no prompt changes were made
