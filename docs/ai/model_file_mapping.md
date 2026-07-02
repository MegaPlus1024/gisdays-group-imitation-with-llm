# Model File Mapping

## Purpose

This document records the publication-safe mapping between stable experiment `model_id` values, logical model names, and local GGUF file paths.

The source of truth for actual experiment runtime paths is:

`configs/evaluation_models.json`

## Canonical Mapping

| model_id | logical/model_name | local gguf_path used by project | notes |
|---|---|---|---|
| `first_model` | `first_model.gguf` | `models/gguf/first_model.gguf` | Local alias for `qwen2.5-1.5b-instruct-q4_k_m.gguf`. |
| `second_model` | `second_model.gguf` | `models/gguf/second_model.gguf` | Current user-facing id for the second local model slot. Upstream/source name: `qwen2.5-3b-instruct-q4_k_m.gguf`. |

## Important Notes

- GGUF model files are not committed to Git.
- A new user must place local model files manually under `models/gguf/` or edit `configs/evaluation_models.json`.
- `second_model` is the current user-facing model id for the second model.
- `qwen2.5-3b-instruct-q4_k_m.gguf` may appear only as an upstream/source filename in metadata.
- `qwen2_5_3b_instruct_q4_k_m` may appear in historical experiment artifacts; it is supported as a legacy alias.
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
  --model-id second_model `
  --json
```
