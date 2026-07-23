# Operator Guide

## Safe default

The canonical runtime default is a deterministic two-agent fake-policy run. It
does not call a model, start a server, open a browser, import Playwright, or use
external network access.

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_multi_agent_runtime.py `
  --config configs\canonical_multi_agent.example.json
```

Expected high-level result:

- `status: succeeded`;
- `turn_count: 8`;
- two completed agents with four turns each;
- one `file_not_found` observation followed by a successful recovery;
- one explicit shared fact publish and read;
- `model_execution: false`;
- all browser/Playwright/external-network flags false.

Optional summaries may be written only to a relative ignored artifact path:

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_multi_agent_runtime.py `
  --config configs\canonical_multi_agent.example.json `
  --output artifacts\canonical_runtime\fake_summary.json
```

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_autonomous_multi_agent_runtime.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m compileall -q src scripts
git diff --check
git status --short
```

Use the repository-local interpreter exactly as shown.

## Local models

Model metadata is in `configs/evaluation_models.json`. GGUF files remain local
and ignored.

The canonical library includes an opt-in `LocalOpenAIModelPolicy`, but the
canonical fake CLI does not expose model execution. Current operator-run model
experiments remain in their phase-specific guides. Do not infer that a Phase
14 complete-workflow benchmark result is a stepwise multi-agent result.

## Historical operator paths

Phase-specific documents under `docs/operator/` describe preserved browser,
Playwright, planner, and benchmark research. They are not the current
architecture entrypoint. Start with:

- `docs/architecture/canonical_runtime.md`
- `docs/status/current_architecture_audit.md`
- `docs/status/final_project_completion_report.md`

Generated packets, outputs, summaries, model files, and GGUF files must not be
committed.
