# Local LLM Agent Lab

Repository name: `local-llm-agent-lab`.

Research prototype for role-constrained local agents that choose and execute
one parameterized action at a time.

The current canonical slice runs two deterministic agents in round-robin
turns. They keep independent histories, share facts only through explicit
operations, validate tool access before dispatch, observe structured failures,
and can recover on a later turn.

The same runtime also has a canonical long-horizon experiment harness. Its
safe default runs repeated fixture-only fake-policy trials for article/file
handoff and office/shared-fact recovery. It records per-turn JSONL traces and
per-trial/experiment metrics without launching a model or browser.

This repository is not production-ready.

The project studies normal user activity with groups of local LLM agents:
roles receive bounded resources and constraints, choose a next action, invoke
registered scripts, and retain an independent history log. Safety is
not the final objective; it is a boundary around useful, measurable behavior.

## Quick Start

Requirements:

- Windows PowerShell;
- Python 3.11+;
- repository-local `.venv`;
- dependencies from `requirements.txt`.

Run the safe no-model demonstration:

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_multi_agent_runtime.py `
  --config configs\canonical_multi_agent.example.json
```

The compact JSON result should report:

- two completed agents;
- eight alternating turns;
- one missing-file failure and one recovery;
- independent per-agent histories;
- one shared fact publish/read;
- no model, browser, Playwright, or external-network execution.

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest tests\test_autonomous_multi_agent_runtime.py
.\.venv\Scripts\python.exe -m pytest
```

Run one safe long-horizon fake trial per default scenario:

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_multi_agent_runtime.py `
  --config configs\canonical_multi_agent_long_horizon.example.json `
  --trials-per-scenario 1 `
  --dry-run
```

Generated summaries and traces are written below the ignored
`artifacts/canonical_multi_agent_long_horizon/` root.

## Canonical Architecture

Current entrypoints:

- `src/agent/autonomous_multi_agent_runtime.py`
- `src/agent/canonical_multi_agent_experiments.py`
- `configs/canonical_multi_agent.example.json`
- `configs/canonical_multi_agent_long_horizon.example.json`
- `scripts/run_autonomous_multi_agent_runtime.py`
- `tests/test_autonomous_multi_agent_runtime.py`
- `tests/test_canonical_multi_agent_experiments.py`

The policy contract is:

```text
next_action(agent_state, observation, allowed_tools) -> one Action or stop
```

Core layers:

1. `AgentProfile`, `AgentState`, `Action`, `Observation`, `HistoryEvent`.
2. `ToolSpec`, `ToolExecutionContext`, `ToolResult`, `ToolExecutor`,
   `ToolRegistry`.
3. Fixture article, file, office-file, constrained command, coordination, and
   completion tools.
4. Deterministic fake policies and an explicit-opt-in local
   OpenAI-compatible policy.
5. Bounded round-robin multi-agent scheduling and group metrics.
6. A repeated long-horizon harness that consumes these same layers and writes
   sanitized trial traces and aggregate metrics.

The default registry adapts the existing `ScriptRegistry` and
`ScriptExecutionBridge`; file/office/command backends are not reimplemented.
`browser_click` is not part of the canonical tool surface.

The canonical data flow is:

```text
config -> orchestrator -> agent state -> local LLM or fake policy
       -> next action -> script runner -> observation -> history log
```

See [Canonical Runtime](docs/architecture/canonical_runtime.md) for the full
contract and boundaries.

## Models

`configs/evaluation_models.json` is the canonical alias registry:

| Alias | Current role |
| --- | --- |
| `first_model` | IBM Granite 3.3 8B Instruct Q4_K_M, small/medium non-Qwen baseline |
| `second_model` | Qwen2.5-3B-Instruct Q4_K_M, weak Qwen baseline |
| `third_model` | Qwen3-14B Q5_K_M, strong historical Qwen planner |
| `fourth_model` | Mistral Small 3.2 24B Instruct Q4_K_M, strong non-Qwen challenger |
| `fifth_model` | Qwen3-30B-A3B-Instruct-2507 Q4_K_M, efficient MoE challenger |

GGUF files are operator-provided local files under `models/gguf/` and are
ignored. The canonical fake run does not need them.
For example, `second_model` resolves to `models/gguf/second_model.gguf`.

Historical evaluation commands retain the stable aliases:

```powershell
.\.venv\Scripts\python.exe scripts\run_evaluation.py --model-id second_model
.\.venv\Scripts\python.exe scripts\run_evaluation.py --model-ids first_model,second_model
```

Local model calls are never the default. The library policy accepts only
localhost endpoints and requires explicit opt-in.
The long-horizon CLI additionally requires `--allow-model-execution`; omitting
it selects fake policies. No canonical local-model group result is claimed.

## Tools

The canonical registry contains:

- fixture article open/read/scroll/find/extract;
- bounded relative file actions;
- bounded office document-file actions;
- constrained simple commands;
- explicit shared fact publish/read;
- agent completion.

Role allowlists are checked before tool dispatch. Existing script-registry
parameter and path policies remain in force.

Real browser, Playwright, mail, git automation, and external web access are
outside this canonical slice.

## Evidence and Benchmarks

The repository preserves several research generations:

- early single-agent and orchestrator/executor experiments;
- deterministic autonomous browser fixtures;
- guarded local-model browser loops;
- guarded Playwright replay;
- Phase 13E/14 complete-workflow planner variance and multi-model benchmarks;
- Phase 15 stepwise fixture article benchmark.

These are evidence/benchmark paths, not competing current architectures.
Historical browser modules use
`src/agent/legacy_autonomous_multi_agent_runtime.py`.

Important interpretation:

- Phase 14 compares one-shot complete-workflow JSON under frozen fixture
  protocols.
- Phase 15 evaluates repeated observation/action behavior for one article
  agent.
- The canonical runtime proves a deterministic two-agent stepwise integration.
- The long-horizon fake evidence proves 16-turn article/file handoff and
  10-turn office/shared-fact recovery through that same integration.
- No local-model two-agent canonical run or true parallel execution is claimed.
- Historical CPU/RAM/latency probes are bounded evidence, not production
  sizing.

The full autonomous agent loop is not implemented as an unrestricted or
production system. Action execution exists only through the bounded,
allowlisted runtime and historical guarded experiments described here.

## Project Map

```text
configs/
  canonical_multi_agent.example.json
  canonical_multi_agent_long_horizon.example.json
  evaluation_models.json
  script_registry.example.json
docs/
  architecture/canonical_runtime.md
  operator/README.md
  status/current_architecture_audit.md
  status/final_project_completion_report.md
src/agent/
  autonomous_multi_agent_runtime.py
  canonical_multi_agent_experiments.py
  legacy_autonomous_multi_agent_runtime.py
  script_registry.py
  script_execution_bridge.py
  scripts/
scripts/
  run_autonomous_multi_agent_runtime.py
tests/
  test_autonomous_multi_agent_runtime.py
  test_canonical_multi_agent_experiments.py
```

Generated outputs belong under ignored `artifacts/` paths. Local models,
generated packets, model outputs, and summaries must not be committed.

## Status

The factual architecture/TZ matrix and cleanup manifest are in
[Current Architecture Audit](docs/status/current_architecture_audit.md).

The short project-level evidence summary remains in
[Final Project Completion Report](docs/status/final_project_completion_report.md).
Phase-specific status files are retained as historical evidence.

Selected retained reports and research references:

- `reports/experiments/final_evaluation_report.md`
- `reports/experiments/final_multi_agent_research_report.md`
- `reports/experiments/manager_summary.md`
- `reports/experiments/project_usage_appendix.md`
- `reports/experiments/final_evaluation_summary.json`
- `docs/security/publication_security_check.md`
- `docs/ai/model_research_metadata.md`
- `docs/ai/orchestrator_executor_runtime_capacity_v1.md`
- `docs/ai/gpu_runtime_configuration_v1.md`
- `docs/ai/gpu_smoke_second_to_second_heavy_v1.md`
- `docs/ai/bounded_stress_candidate_pairs_v1.md`

Current limitations:

- fixture/local-tool research prototype;
- no production security evaluation;
- no real browser in the canonical runtime;
- no external websites or general web browsing;
- deterministic interleaving, not true parallelism;
- no stable concurrency-2 result;
- no production resource recommendation.

## Development Checks

```powershell
.\.venv\Scripts\python.exe -m compileall -q src scripts
.\.venv\Scripts\python.exe -m pytest
git diff --check
git status --short
```

Do not use global Python for repository verification.
