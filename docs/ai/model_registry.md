# Local Model Registry

## Purpose

Track reproducible metadata for every local GGUF model used by smoke tests, baselines, and comparisons.

## Rules

- GGUF files are not committed to git.
- Model metadata is committed.
- Alias names like `first_model.gguf` are allowed only if mapped to actual model identity.
- Do not make subjective quality claims without experiment data.
- Every smoke/baseline/comparison must reference a model record.

## Model records

### Record A: first_model.gguf

- registry_id: `first_model`
- local_alias: `first_model.gguf`
- actual_filename: `qwen2.5-1.5b-instruct-q4_k_m.gguf`
- local_path: `models/gguf/first_model.gguf`
- format: `GGUF`
- size_class: `1.5B`
- quantization: `Q4_K_M`
- source_url: `https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF`
- source_note: `Fill manually from the download page if known.`
- role: `first local smoke test and first runtime baseline`
- used_in:
- `experiments/smoke/local_llama_server_smoke_v1/`
- `experiments/baselines/local_runtime_baseline_v1/`
- notes:
- `successfully completed first smoke test`
- `completed first runtime baseline`

### Record B: qwen2.5-3b-instruct-q4_k_m.gguf

- registry_id: `qwen2_5_3b_instruct_q4_k_m`
- local_alias: `second_model.gguf` or `null`
- actual_filename: `qwen2.5-3b-instruct-q4_k_m.gguf`
- local_path: `models/gguf/qwen2.5-3b-instruct-q4_k_m.gguf`
- format: `GGUF`
- size_class: `3B`
- quantization: `Q4_K_M`
- source_url: `https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF`
- source_note: `Fill manually from the download page if known.`
- role: `second model smoke test and second runtime baseline`
- used_in:
- `experiments/smoke/second_model_smoke_v1/`
- `experiments/baselines/second_model_runtime_baseline_v1/`
- `experiments/comparisons/two_model_runtime_comparison_v1/`
- reason_for_selection:
- `The first model proved the runtime pipeline. This 3B Q4_K_M model tests whether a larger local instruct model remains practical while potentially improving instruction-following.`
- notes:
- `Do not claim quality improvement until numeric and semantic validation data exist.`

## How to add a new model

1. Add a new record with `registry_id`, filename/path, format, and known metadata.
2. Leave unknown fields as `TODO` or `null`.
3. Update `configs/models.local.example.json`.
4. Reference the model record in smoke/baseline/comparison docs before running experiments.

## How this registry relates to smoke tests, baselines, and comparisons

- Smoke tests confirm runtime path viability for one model record.
- Baselines measure repeated runtime behavior for one model record.
- Comparisons consume baseline summaries and must reference both model records.

## Known limitations

- Unknown source details must be filled manually.
- Alias-based local workflows can hide true model identity unless mapping is maintained.
- Runtime metrics alone do not prove semantic action correctness.
