# Phase 13B Guarded Local Model Live Loop

## Scope

- guarded local-model planner adapter for the offline live loop
- observe -> local model proposes one next action -> validate -> fixture execute -> observe -> repeat
- local fixture-backed execution only
- manual operator model endpoint only

## Safe refusal smoke

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_live_loop.py `
  --config configs\autonomous_runtime\browser_live_loop_local_model.example.json
```

This path should refuse with `allow_model_calls_required` unless the operator explicitly enables model calls.

## Guarded operator run

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_live_loop.py `
  --config configs\autonomous_runtime\browser_live_loop_local_model.example.json `
  --planner-backend local_model `
  --allow-model-calls `
  --model-endpoint http://127.0.0.1:8082/v1 `
  --model-alias third_model `
  --scenario-id browser_live_loop_local_model_policy_review_v1 `
  --output-dir artifacts\autonomous_runtime_summaries\browser_live_loop_local_model
```

## Limitations

- Codex does not launch models, llama-server, browser, Playwright, Chromium, or a local server here
- this is not production browser automation
- this does not claim autonomous live LLM-loop readiness
- third_model is treated as an operator-provided local GGUF planner candidate
