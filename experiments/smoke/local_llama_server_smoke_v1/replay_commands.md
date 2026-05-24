# Replay Commands (Windows PowerShell)

## 1) Start llama-server

```powershell
llama-server `
  -m models\gguf\first_model.gguf `
  --host 127.0.0.1 `
  --port 8080 `
  --ctx-size 4096
```

## 2) Run smoke script

```powershell
python scripts\run_llama_smoke.py `
  --base-url http://127.0.0.1:8080/v1 `
  --model-name first_model.gguf `
  --prompt-file prompts\smoke\agent_next_action_v1.txt `
  --out-dir logs\smoke
```

## 3) Archive latest successful run

```powershell
python scripts\archive_smoke_run.py `
  --log-dir logs\smoke `
  --out-root experiments\smoke `
  --experiment-id local_llama_server_smoke_v1 `
  --model-path models\gguf\first_model.gguf `
  --force
```

## Optional server PID variant for future runs

```powershell
python scripts\run_llama_smoke.py `
  --base-url http://127.0.0.1:8080/v1 `
  --model-name first_model.gguf `
  --prompt-file prompts\smoke\agent_next_action_v1.txt `
  --out-dir logs\smoke `
  --server-pid <PID>
```
