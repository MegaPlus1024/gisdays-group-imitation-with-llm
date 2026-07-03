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
- Sequential fake-mode orchestrator/executor group MVP exists, with plan, assignments, executor actions, group history, artifacts, and prototype pair-quality metrics.
- One narrow two-endpoint local orchestrator/executor proof completed after executor prompt hardening, with two validated and executed local read actions.
- A repeated local group run completed N=3 for the same `second_model -> first_model` pair and one scenario, with zero recorded errors.
- An orchestrator/executor pair matrix compared four pairs for the basic group scenario. `second_model -> first_model` was the best observed pair there, while both `first_model` orchestrator pairs failed at plan parsing.
- A heavier four-agent group scenario was added with two group steps and workspace-only writes. Its pair matrix completed all four pair entries; `second_model -> second_model` was best observed there, while `second_model -> first_model` completed with validation/repair failures and both `first_model` orchestrator pairs failed at plan parsing.
- Cross-scenario pair comparison now covers the basic and heavy group scenarios. The top completed pairs are `stable_but_low_confidence`, and the best observed pair changes by scenario.
- Final reports exist, but they explicitly do not make a production recommendation.

## 3. Requirement Coverage Matrix

| ТЗ requirement | Current evidence | Status | Gap | Next action |
| -------------- | ---------------- | ------ | --- | ----------- |
| local LLM agent action selection | `LocalLLMClient`, `ExperimentScenarioRunner`, local artifacts | complete | Limited to short controlled scenarios. | Keep expanding scenarios and prompts. |
| role/config/resource constraints | role templates, activity profiles, scenario configs, registry safety rules | complete | Some developer-role paths conflict with execution safety policy. | Align developer scenario allowed roots and safety policy before reruns. |
| script registry | `src/agent/script_registry.py`, registry tests | complete | Registry is local/script-oriented, not a full application automation catalog. | Add git/mail/browser-real actions only behind explicit safety controls. |
| action validation | NextAction contract and registry validation | complete | Semantic validation remains limited. | Add semantic validators for role-specific intent and path policy. |
| execution bridge | `ScriptExecutionBridge` and script helpers | complete | Browser/office actions are simulated or stub/file-based. | Add optional real automation adapters later. |
| history/error logging | `ExecutionHistoryLogger`, single-agent artifacts, orchestrator/executor group artifacts | complete | Group history exists for the MVP runner only; it is not a production shared memory/runtime. | Expand group history semantics after local group runs. |
| behavioral evaluation | activity profiles, repeated-trials analysis, cross-scenario analysis | complete | Limited to two scenarios and short trajectories. | Add at least one more scenario and longer runs. |
| multiple models | `first_model`, `second_model`, alias support, repeated comparisons, default orchestrator/executor pair, pair matrices | partially complete | Only two model candidates; pair matrices cover two short group scenarios only. | Add more scenario diversity and measured resource/capacity probes. |
| repeated trials | N=3 per model per scenario | complete | Small sample size. | Increase N only after scenario/path policy is stable. |
| group of agents | `MultiAgentOrchestratorSmoke`, multi-agent scenario configs, orchestrator/executor artifacts | partially complete / MVP implemented | Sequential fake-mode and local pair-matrix evidence exist for short group scenarios; no measured concurrency. | Run measured capacity smoke and add more realistic scenario variants. |
| orchestrator/executor pair | `src/agent/orchestrator_executor_pipeline.py`, `scripts/run_orchestrator_executor_group.py`, repeated local artifacts, `docs/ai/orchestrator_executor_pair_matrix_v1.md`, `docs/ai/heavy_multi_agent_scenario_v1.md` | partially complete | Pair comparison covers two group scenarios but remains N=3, short-horizon, CPU-only, and not capacity measured. | Measure top-pair runtime/resource/capacity and add more scenario diversity. |
| virtual network simulation | Controlled filesystem/action environment and constraints | partially complete | No real virtual network, host topology, or network traffic simulation. | Define minimal virtual network abstraction or narrow the claim. |
| CPU-only runtime | CPU-oriented local runs and resource observations | complete | Evidence is short single-agent only. | Keep CPU-only as demonstrated for short demos, not capacity claims. |
| GPU runtime | `runtime.local.example.json` marks GPU optional later | missing | No GPU flags in start script, no GPU config fields, no measured GPU run. | Add GPU runtime config and perform measured GPU smoke when hardware is available. |
| multi-agent capacity | Formula estimate exists | estimated only | No concurrent stress test or measured multi-agent throughput. | Add controlled multi-agent capacity smoke and runtime RSS probe. |
| final recommended configuration | Final reports state not ready | missing | Evidence is insufficient for final production recommendation. | Produce recommendation only after stronger behavior and measured capacity evidence. |

## 4. Honest Readiness Summary

- Single-agent prototype: complete for a research prototype.
- Behavioral evaluation pipeline: complete for limited scenarios.
- Multiple executor model comparison: partially complete.
- Group of agents: partially complete; sequential fake-mode and local repeated/matrix evidence now exist, including a four-agent heavy scenario, but no measured concurrency.
- Orchestrator/executor pair comparison: partially complete for two group scenarios. The best observed pair changed from `second_model -> first_model` on the basic scenario to `second_model -> second_model` on the heavy scenario, so evidence is preliminary only.
- GPU runtime: missing/not configured.
- Measured multi-agent capacity: missing.
- Virtual computer network: partially simulated, not a full network.
- Final production recommendation: not ready.

## 5. Next Audit-Based Direction

The next implementation should not add more reports first. The minimal orchestrator/executor experiment path, fake-mode proof, local repeated pair proof, basic pair matrix, heavy pair matrix, and cross-scenario pair comparison now exist. The next step is measured runtime/resource/capacity evidence for the top completed pairs, followed by additional scenario diversity.
