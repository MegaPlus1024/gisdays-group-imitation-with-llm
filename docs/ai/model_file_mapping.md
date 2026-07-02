# Model File Mapping

## Purpose

This document records the publication-safe mapping between stable experiment `model_id` values, logical model names, and local GGUF file paths.

The source of truth for actual experiment runtime paths is:

`configs/evaluation_models.json`

## Canonical Mapping

| model_id | logical/model_name | local gguf_path used by project | notes |
|---|---|---|---|
| `first_model` | `first_model.gguf` | `models/gguf/first_model.gguf` | Local alias for `qwen2.5-1.5b-instruct-q4_k_m.gguf`. |
| `qwen2_5_3b_instruct_q4_k_m` | `qwen2.5-3b-instruct-q4_k_m.gguf` | `models/gguf/second_model.gguf` | Logical/upstream model name differs from local alias path. |

## Important Notes

- GGUF model files are not committed to Git.
- A new user must place local model files manually under `models/gguf/` or edit `configs/evaluation_models.json`.
- `qwen2.5-3b-instruct-q4_k_m.gguf` may appear as `model_name` or upstream/logical filename.
- The required local file path for the second model in the current repository configuration is `models/gguf/second_model.gguf`.
- Do not rename local model files in documentation unless `configs/evaluation_models.json` is updated too.

## Preflight Commands

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py `
  --models-config configs\evaluation_models.json `
  --model-id first_model `
  --json
```

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py `
  --models-config configs\evaluation_models.json `
  --model-id qwen2_5_3b_instruct_q4_k_m `
  --json
```
