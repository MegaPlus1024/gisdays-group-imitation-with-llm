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

## Long-Horizon Fake Experiments

The existing canonical CLI also recognizes the long-horizon experiment
config. This safe command executes deterministic fake policies only:

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_multi_agent_runtime.py `
  --config configs\canonical_multi_agent_long_horizon.example.json `
  --scenario-id article_file_handoff `
  --scenario-id office_shared_fact_recovery `
  --trials-per-scenario 1 `
  --dry-run
```

Useful experiment options:

- repeat `--scenario-id` to select scenarios;
- use `--models alias1,alias2` to label/select registered model profiles;
- use `--output-dir artifacts/...` for an alternate ignored output root;
- use `--skip-existing` or `--fail-fast` for bounded operator control.

The fake command writes `trial_summary.json`, `group_trace.jsonl`, and one
`experiment_summary.json`. It does not start or contact a model server.
Do not commit these generated files.

## Verification

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_autonomous_multi_agent_runtime.py
.\.venv\Scripts\python.exe -m pytest tests\test_canonical_multi_agent_experiments.py
.\.venv\Scripts\python.exe -m pytest
.\.venv\Scripts\python.exe -m compileall -q src scripts
git diff --check
git status --short
```

Use the repository-local interpreter exactly as shown.

## Local models

Model metadata is in `configs/evaluation_models.json`. GGUF files remain local
and ignored.

The canonical library and long-horizon harness include an opt-in
`LocalOpenAIModelPolicy`. Calls are limited to registered localhost endpoints
and require `--allow-model-execution`; fake execution remains the default.
Never combine this flag with `--dry-run`. The harness requests one action per
turn and does not accept complete workflow arrays.

No canonical long-horizon local-model run is documented yet. Do not infer that
a Phase 14 complete-workflow benchmark result is a stepwise multi-agent result.

## Historical operator paths

Phase-specific documents under `docs/operator/` describe preserved browser,
Playwright, planner, and benchmark research. They are not the current
architecture entrypoint. Start with:

- `docs/architecture/canonical_runtime.md`
- `docs/status/current_architecture_audit.md`
- `docs/status/final_project_completion_report.md`

Generated packets, outputs, summaries, model files, and GGUF files must not be
committed.

For canonical long-horizon smoke runs, inspect generated traces for advertised
resources, unmet completion requirements, dependency state, and sanitized model
protocol diagnostics. A failed first smoke is contract evidence, not a
model-quality result. Model calls remain explicit opt-in; the canonical runtime
is fixture-only and does not launch a browser.

For recovery scenarios, treat `generic_recovery_*` metrics as "a changed
successful action after an own failure advanced progress." Treat
`required_recoveries_*` as the scenario contract. In
`office_shared_fact_recovery`, `completion_requirements_unmet` should expose the
unmet `recovery_completed` contract, the unavailable `missing_input` resource,
the available `recovery_note` resource, and unchanged failed actions that should
not be retried.

For shared facts, a procedural pass is not enough unless the fact is grounded.
The publishing agent must first observe the source with a successful tool call,
then publish with the matching `evidence_id`. `evidence_id_required`,
`evidence_source_mismatch`, or `published_value_mismatch` mean the key was not
accepted into the shared environment and any grounded completion requirement
must remain unmet.
