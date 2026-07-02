# Local GGUF Models

This folder stores local GGUF model files.

Model files are ignored by git.

Metadata is tracked in:

- `docs/ai/model_registry.md`
- `docs/ai/model_file_mapping.md`
- `configs/evaluation_models.json`
- `configs/models.local.example.json`

Current expected local files:

- `first_model.gguf`
- `second_model.gguf`

Canonical mapping:

| model_id | logical/model_name | required local file |
|---|---|---|
| `first_model` | `first_model.gguf` | `models/gguf/first_model.gguf` |
| `second_model` | `second_model.gguf` | `models/gguf/second_model.gguf` |

`qwen2.5-3b-instruct-q4_k_m.gguf` is the upstream/source model name recorded as metadata for the second model. In this repository's current configuration, the user-facing `model_id` is `second_model`, and the required local file is `models/gguf/second_model.gguf`.

Older experiment artifacts may still contain the historical id `qwen2_5_3b_instruct_q4_k_m`; current commands should use `second_model`.

If a local alias is used, record the alias mapping in the registry. Current known alias mappings:

- `first_model.gguf` -> `qwen2.5-1.5b-instruct-q4_k_m.gguf`
- `second_model.gguf` -> `qwen2.5-3b-instruct-q4_k_m.gguf`
