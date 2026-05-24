# Local GGUF Models

This folder stores local GGUF model files.

Model files are ignored by git.

Metadata is tracked in:

- `docs/ai/model_registry.md`
- `configs/models.local.example.json`

Current expected files:

- `first_model.gguf`
- `qwen2.5-3b-instruct-q4_k_m.gguf`

If a local alias is used, record the alias mapping in the registry.
Current known alias mapping: `first_model.gguf` -> `qwen2.5-1.5b-instruct-q4_k_m.gguf`.
