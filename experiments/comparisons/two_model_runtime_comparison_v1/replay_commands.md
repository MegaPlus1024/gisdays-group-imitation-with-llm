# Replay Commands (Windows PowerShell)

## A) Start llama-server with second model

```powershell
llama-server `
  -m models\gguf\qwen2.5-3b-instruct-q4_k_m.gguf `
  --host 127.0.0.1 `
  --port 8080 `
  --ctx-size 4096
```

## B) Run second smoke

```powershell
python scripts\run_llama_smoke.py `
  --base-url http://127.0.0.1:8080/v1 `
  --model-name qwen2.5-3b-instruct-q4_k_m.gguf `
  --prompt-file prompts\smoke\agent_next_action_v1.txt `
  --out-dir logs\smoke
```

## C) Archive second smoke

```powershell
python scripts\archive_smoke_run.py `
  --log-dir logs\smoke `
  --out-root experiments\smoke `
  --experiment-id second_model_smoke_v1 `
  --model-path models\gguf\qwen2.5-3b-instruct-q4_k_m.gguf `
  --force
```

## D) Run second baseline

```powershell
python scripts\run_runtime_baseline.py `
  --base-url http://127.0.0.1:8080/v1 `
  --model-name qwen2.5-3b-instruct-q4_k_m.gguf `
  --prompt-file prompts\smoke\agent_next_action_v1.txt `
  --out-dir experiments\baselines\second_model_runtime_baseline_v1 `
  --runs 3 `
  --force
```

## E) Optional baseline with server PID

Replace `12345` with a real PID from `Get-Process`.

```powershell
python scripts\run_runtime_baseline.py `
  --base-url http://127.0.0.1:8080/v1 `
  --model-name qwen2.5-3b-instruct-q4_k_m.gguf `
  --prompt-file prompts\smoke\agent_next_action_v1.txt `
  --out-dir experiments\baselines\second_model_runtime_baseline_v1 `
  --runs 3 `
  --server-pid 12345 `
  --force
```

## F) Generate comparison

```powershell
python scripts\compare_runtime_baselines.py `
  --first-summary experiments\baselines\local_runtime_baseline_v1\summary.json `
  --second-summary experiments\baselines\second_model_runtime_baseline_v1\summary.json `
  --out-dir experiments\comparisons\two_model_runtime_comparison_v1 `
  --force
```
