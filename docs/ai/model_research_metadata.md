# Model Research Metadata

## Purpose

This document separates clean project-local command ids from research metadata. Normal commands should use `first_model` and `second_model`; long upstream names are recorded here for reporting and reproducibility.

Source files inspected:

- `configs/evaluation_models.json`
- `configs/models.local.example.json`
- `docs/ai/model_registry.md`
- `docs/ai/model_file_mapping.md`
- `models/gguf/MODELS.md`
- `reports/experiments/final_evaluation_report.md`
- historical experiment artifacts under `experiments/`

## Current Model Table

| project model_id | local GGUF file | llama-server model_name | upstream/full model name | parameter size | quantization | role in experiments | notes |
| ---------------- | --------------- | ----------------------- | ------------------------ | -------------- | ------------ | ------------------- | ----- |
| `first_model` | `models/gguf/first_model.gguf` | `first_model.gguf` | `qwen2.5-1.5b-instruct-q4_k_m.gguf` | `1.5B` | `Q4_K_M` | First local smoke/baseline model and executor candidate in two-scenario repeated trials. | Upstream filename and Hugging Face Qwen source URL are recorded in `docs/ai/model_registry.md`; exact local download/checksum are not recorded. |
| `second_model` | `models/gguf/second_model.gguf` | `second_model.gguf` | `qwen2.5-3b-instruct-q4_k_m.gguf` | `3B` | `Q4_K_M` | Second executor candidate in smoke/baseline, two-model comparison, repeated trials, cross-scenario analysis, and final reports. | Legacy id `qwen2_5_3b_instruct_q4_k_m` is supported as an alias and remains in historical artifacts. |

## Source/Origin Evidence

- `first_model`: `docs/ai/model_registry.md` records source URL `https://huggingface.co/Qwen/Qwen2.5-1.5B-Instruct-GGUF`.
- `second_model`: `docs/ai/model_registry.md` records source URL `https://huggingface.co/Qwen/Qwen2.5-3B-Instruct-GGUF`.
- Neither model has a committed GGUF checksum or exact download timestamp.

## Naming Rule

- Use project ids in commands: `first_model`, `second_model`.
- Use `model_name` for the local OpenAI-compatible runtime name.
- Use upstream/full names only in research metadata, reports, and provenance notes.

## TODO

- Record GGUF checksums outside Git or in a non-secret manifest before final archival.
- Record exact source revision/download timestamp if available.
