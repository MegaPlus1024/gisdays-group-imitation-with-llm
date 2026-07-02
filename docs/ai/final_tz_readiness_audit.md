# Final ТЗ Readiness Audit

## 1. Target Formulation

Target: develop and verify a prototype in which a group of software agents imitates normal user activity in a virtual computer network.

This audit checks the repository against that target without running models, starting `llama-server`, downloading models, rewriting historical artifacts, or making production claims.

## 2. Current Implemented Evidence

- Single-agent local LLM pipeline exists.
- Fake/local scenario runner exists for one-agent scenarios.
- Role/config/resource constraints exist through role templates, activity profiles, scenario configs, and `AgentState`.
- Script registry, action validation, execution bridge, history/error logging, repair policy, and behavioral evaluation exist.
- Two local models are registered as `first_model` and `second_model`.
- Two real local-model scenarios were evaluated: office-worker and developer maintenance.
- Repeated trials exist with N=3 per model per scenario, 12 real local-model trajectories total.
- Cross-scenario behavioral analysis exists.
- Resource/capacity formula estimate exists.
- Final reports exist, but they explicitly do not make a production recommendation.

## 3. Requirement Coverage Matrix

| ТЗ requirement | Current evidence | Status | Gap | Next action |
| -------------- | ---------------- | ------ | --- | ----------- |
| local LLM agent action selection | `LocalLLMClient`, `ExperimentScenarioRunner`, local artifacts | complete | Limited to short controlled scenarios. | Keep expanding scenarios and prompts. |
| role/config/resource constraints | role templates, activity profiles, scenario configs, registry safety rules | complete | Some developer-role paths conflict with execution safety policy. | Align developer scenario allowed roots and safety policy before reruns. |
| script registry | `src/agent/script_registry.py`, registry tests | complete | Registry is local/script-oriented, not a full application automation catalog. | Add git/mail/browser-real actions only behind explicit safety controls. |
| action validation | NextAction contract and registry validation | complete | Semantic validation remains limited. | Add semantic validators for role-specific intent and path policy. |
| execution bridge | `ScriptExecutionBridge` and script helpers | complete | Browser/office actions are simulated or stub/file-based. | Add optional real automation adapters later. |
| history/error logging | `ExecutionHistoryLogger`, run artifacts | complete | Group-level shared history is not implemented. | Add group history model for multi-agent runs. |
| behavioral evaluation | activity profiles, repeated-trials analysis, cross-scenario analysis | complete | Limited to two scenarios and short trajectories. | Add at least one more scenario and longer runs. |
| multiple models | `first_model`, `second_model`, alias support, repeated comparisons | partially complete | Only two executor candidates; no orchestrator/executor pair comparison. | Add pair-level evaluation after orchestrator/executor MVP. |
| repeated trials | N=3 per model per scenario | complete | Small sample size. | Increase N only after scenario/path policy is stable. |
| group of agents | `MultiAgentOrchestratorSmoke`, multi-agent scenario config, fixture tests | partially complete | Smoke/scaffold only; no real local multi-agent run. | Build controlled multi-agent runner with isolated and shared state. |
| orchestrator/executor pair | Basic single-agent `Orchestrator`; smoke multi-agent coordinator | missing | No model-backed orchestrator planning another model's executor actions. | Implement explicit orchestrator/executor MVP in a separate task. |
| virtual network simulation | Controlled filesystem/action environment and constraints | partially complete | No real virtual network, host topology, or network traffic simulation. | Define minimal virtual network abstraction or narrow the claim. |
| CPU-only runtime | CPU-oriented local runs and resource observations | complete | Evidence is short single-agent only. | Keep CPU-only as demonstrated for short demos, not capacity claims. |
| GPU runtime | `runtime.local.example.json` marks GPU optional later | missing | No GPU flags in start script, no GPU config fields, no measured GPU run. | Add GPU runtime config and perform measured GPU smoke when hardware is available. |
| multi-agent capacity | Formula estimate exists | estimated only | No concurrent stress test or measured multi-agent throughput. | Add controlled multi-agent capacity smoke and runtime RSS probe. |
| final recommended configuration | Final reports state not ready | missing | Evidence is insufficient for final production recommendation. | Produce recommendation only after stronger behavior and measured capacity evidence. |

## 4. Honest Readiness Summary

- Single-agent prototype: complete for a research prototype.
- Behavioral evaluation pipeline: complete for limited scenarios.
- Multiple executor model comparison: partially complete.
- Group of agents: partially complete; current support is smoke/scaffolding.
- Orchestrator/executor pair: missing as an explicit model-backed architecture.
- GPU runtime: missing/not configured.
- Measured multi-agent capacity: missing.
- Virtual computer network: partially simulated, not a full network.
- Final production recommendation: not ready.

## 5. Next Audit-Based Direction

The next implementation should not add more reports first. It should build a minimal orchestrator/executor experiment path, then run a tiny fake-mode proof, then a local-mode single-step proof, and only then rerun behavioral/capacity experiments.
