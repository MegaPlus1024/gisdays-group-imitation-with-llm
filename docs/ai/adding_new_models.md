# Adding New Local GGUF Models

## Simple Slot Convention

Use short stable project ids in commands:

- `first_model`
- `second_model`
- `third_model`
- `small_model`
- `test_model`

Put long upstream names, source links, quantization details, and download notes in metadata, not in `model_id`.

## Add A New Model

1. Put the GGUF under `models/gguf/`, for example:

```text
models/gguf/third_model.gguf
```

2. Add an entry to `configs/evaluation_models.json`:

```json
{
  "model_id": "third_model",
  "display_name": "Third Model",
  "model_name": "third_model.gguf",
  "gguf_path": "models/gguf/third_model.gguf",
  "quantization": "Q4_K_M",
  "parameter_size": "3B",
  "runtime": "llama.cpp / llama-server",
  "base_url": "http://127.0.0.1:8080/v1",
  "api_style": "openai_compatible",
  "expected_cpu_only": true,
  "ctx_size": 4096,
  "timeout_seconds": 120.0,
  "temperature": 0.0,
  "max_tokens": 512,
  "enabled": true,
  "notes": [
    "Original upstream filename, source, quantization, and selection notes."
  ]
}
```

3. Run preflight:

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py --models-config configs\evaluation_models.json --model-id third_model --json
```

4. Start the local server:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 -ModelId third_model
```

5. Run a fake or local scenario with `--model-id third_model`.

## Naming Rule

Use short stable project ids in commands. Use `model_name` for the local API name and `gguf_path` for the local file. Record long upstream model names in `upstream_model_name` or `notes`.
