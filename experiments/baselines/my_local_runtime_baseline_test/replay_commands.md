# Replay Commands (Windows PowerShell)

## Start llama-server

```powershell
llama-server `
  -m models\gguf\first_model.gguf `
  --host 127.0.0.1 `
  --port 8080 `
  --ctx-size 4096
```

## Run baseline

```powershell
python scripts\run_runtime_baseline.py `
  --base-url http://127.0.0.1:8080/v1 `
  --model-name first_model.gguf `
  --prompt-file prompts\smoke\agent_next_action_v1.txt `
  --out-dir experiments\baselines\local_runtime_baseline_v1 `
  --runs 3 `
  --force
```

## Optional server PID version

```powershell
python scripts\run_runtime_baseline.py `
  --base-url http://127.0.0.1:8080/v1 `
  --model-name first_model.gguf `
  --prompt-file prompts\smoke\agent_next_action_v1.txt `
  --out-dir experiments\baselines\local_runtime_baseline_v1 `
  --runs 3 `
  --server-pid <PID> `
  --force
```
