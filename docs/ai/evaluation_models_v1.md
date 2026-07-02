# Evaluation Models v1

## Purpose

`configs/evaluation_models.json` is the canonical registry of local models that may be used in behavior experiments. It turns `model_id` into a reproducible experiment entity with model name, GGUF path, runtime settings, generation parameters, and preflight status.

Implementation:

- `src/agent/evaluation_models.py`
- `scripts/check_evaluation_model.py`
- integrated into `scripts/run_agent_scenario.py`
- consumed by `scripts/start_llama_server.ps1 -ModelId <id>`

## Why Model Registry Is Required By TZ

The TZ requires experiments with several local models, behavior-quality comparison, repeatability, resource usage, latency, CPU/RAM, and a reproducible final report. That is not reliable if every run passes `--model-name` and `--base-url` manually.

The registry provides stable IDs such as `first_model` and `second_model`, so scenario artifacts can later be grouped and compared by a controlled model identity. The earlier id `qwen2_5_3b_instruct_q4_k_m` is retained only as a compatibility alias for historical commands and artifacts.

## Config Schema

Each model entry has:

| Field | Meaning |
|---|---|
| `model_id` | Stable internal experiment id. |
| `aliases` | Optional legacy ids accepted by the resolver. |
| `display_name` | Human-readable model label. |
| `model_name` | Name sent to the OpenAI-compatible API. |
| `upstream_model_name` | Optional source/upstream model filename for notes. |
| `gguf_path` | Relative or absolute path to local GGUF file. |
| `quantization` | Quantization label, for example `Q4_K_M`. |
| `parameter_size` | Approximate model size, for example `1.5B` or `3B`. |
| `runtime` | Runtime family, currently `llama.cpp / llama-server`. |
| `base_url` | OpenAI-compatible runtime base URL. |
| `api_style` | API style, currently `openai_compatible`. |
| `expected_cpu_only` | Whether CPU-only execution is expected. |
| `ctx_size` | Context size for `llama-server`. |
| `timeout_seconds` | HTTP timeout for local mode. |
| `temperature` | Generation temperature. |
| `max_tokens` | Max completion tokens. |
| `enabled` | Whether the model may be used without override. |
| `notes` | Reproducibility notes and alias mappings. |

## model_id vs model_name

`model_id` is the stable key used by project experiments and reports.

`model_name` is the string sent to the local OpenAI-compatible endpoint. It may be a filename or runtime alias, and it should not be used as the primary experiment identity.

## Fake Mode Uses Model Metadata

Fake mode does not call `llama-server` and does not require a model file. If `--model-id` is passed, the runner still records registry metadata and preflight status in `manifest.json`.

Example:

```powershell
.\.venv\Scripts\python.exe scripts\run_agent_scenario.py --mode fake --model-id first_model --models-config configs\evaluation_models.json --max-steps 1 --force
```

## Local Mode Uses Model Metadata

Local mode uses `model_id` to resolve:

- `model_name`
- `base_url`
- `timeout_seconds`
- `temperature`
- `max_tokens`
- model metadata for artifacts

Example shape, not executed by this document:

```powershell
.\.venv\Scripts\python.exe scripts\run_agent_scenario.py `
  --mode local `
  --model-id first_model `
  --models-config configs\evaluation_models.json `
  --scenario configs\evaluation_scenarios\office_worker_basic_session.json `
  --out-dir experiments\model_behavior\results\office_worker_first_model_run_001 `
  --execute-actions `
  --max-steps 5
```

## Preflight Checks

`preflight_evaluation_model` checks:

- `model_id` and `model_name` are non-empty;
- `base_url` has an HTTP/HTTPS URL shape;
- runtime is supported;
- `gguf_path` is configured;
- model file exists or is reported missing;
- `expected_cpu_only` is present via schema;
- `ctx_size`, `timeout_seconds`, and `max_tokens` are positive;
- model enabled/disabled state.

Missing GGUF file is a warning for general metadata checks and fake mode. It becomes a failure when `--require-model-file` is used or when local mode runs without `--allow-missing-model-file`.

## Examples

Check a model:

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py --models-config configs\evaluation_models.json --model-id first_model
```

Check a model and require the GGUF file:

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py --models-config configs\evaluation_models.json --model-id first_model --require-model-file
```

JSON output:

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py --models-config configs\evaluation_models.json --model-id first_model --json
```

Check the second model:

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py --models-config configs\evaluation_models.json --model-id second_model --json
```

Start `llama-server` by model id:

```powershell
.\scripts\start_llama_server.ps1 -ModelId first_model
```

```powershell
.\scripts\start_llama_server.ps1 -ModelId second_model
```

Dry-run server path and model path resolution without starting:

```powershell
.\scripts\start_llama_server.ps1 -ModelId first_model -DryRun
```

## Troubleshooting

`llama-server.exe not found`

The Python venv is only for Python dependencies. It does not add `llama-server.exe` to `PATH`. Pass `-ServerPath "C:\path\to\llama-server.exe"` or add the directory to User PATH.

`model file not found`

GGUF files are not committed. Put the model at the registry `gguf_path`, or pass an explicit `-ModelPath` to `start_llama_server.ps1`. Missing files block real local runs unless explicitly overridden for diagnostics.

`disabled model`

A disabled registry model will not be used for local mode unless `--allow-disabled-model` is passed to `run_agent_scenario.py`.

`fake run fails because model is missing`

This should not happen. Fake mode records model metadata but does not require the GGUF file.

`server starts but scenario runner cannot connect`

Check that the registry `base_url` matches the server host and port, normally `http://127.0.0.1:8080/v1`.

## Next Step

The normal current model ids are `first_model` and `second_model`. No real dry run or benchmark is performed by this registry/preflight task.
