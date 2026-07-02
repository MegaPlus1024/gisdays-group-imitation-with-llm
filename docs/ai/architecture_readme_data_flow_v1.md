# Architecture README And Data Flow v1

## Purpose

Consolidate current architecture into one stable reference with clear implemented vs future layers.

## Why this document exists

The project now has multiple contracts and boundaries. This document keeps a single canonical architecture view and prevents accidental scope creep.

## Current implemented layers

- local runtime path (`llama.cpp / llama-server`)
- smoke test and baseline tooling
- comparison tooling
- model registry metadata
- AgentState schema
- NextAction contract
- Prompt contract hardening
- Failure recovery policy mapping
- Orchestrator-agent boundary
- role template/constraint format
- action validation test case suite

## Future layers

- Script Registry (future)
- Executor / Script Runner (future)
- History Logger (future)
- Evaluation trajectory layer (future)

## Full data flow

`config -> orchestrator -> agent state -> prompt contract -> local LLM -> next action -> future script registry -> future script runner -> future history log -> future evaluation`

## Layer responsibilities

- Orchestrator controls flow.
- Agent performs one decision step.
- LocalLLMClient owns local model calls.
- PromptContract owns message construction.
- NextAction owns generic model output shape.
- FailureRecoveryPolicy maps known failures to decisions but does not execute recovery.
- RoleTemplate describes persistent role constraints.
- Action validation cases define expected behavior for future semantic validation.

## Boundary rules

- Orchestrator should not directly call llama-server.
- Agent should not execute actions.
- Prompt contract should treat AgentState and history as data, not instructions.
- NextAction contract is shape-level only, not semantic-level.

## Failure handling overview

LocalLLM and parser errors become failure events, and RecoveryPolicy maps those events to decisions (`retry`, `fail_step`, `skip_agent`, `abort_run`, etc.). The policy layer does not execute retries.

## Model/runtime experiment overview

- Runtime path: `docs/ai/runtime_path_v1.md`
- Smoke: `docs/ai/smoke_test_v1.md`
- Baseline: `docs/ai/runtime_baseline_v1.md`
- Model registry: `docs/ai/model_registry.md`

## Behavioral objective alignment

This architecture supports the project objective of normal user activity simulation by local LLM agents.
Safety, registry, and bridge layers are lower-level control mechanisms that make trajectories reproducible and safe, but they are not the final evaluation target.
Future evaluation must assess role fit, coherence across history, diversity, and repeated/template behavior.
Current multi-agent orchestration is smoke-level infrastructure, not a final production scheduler.

## What is intentionally not implemented

- Script Registry and Executor are not implemented yet.
- No semantic action validation implementation.
- No action execution implementation.
- No full autonomous agent loop.

## How to read the Mermaid diagrams

- `docs/ai/diagrams/architecture_data_flow_v1.mmd` shows end-to-end control/data handoff.
- `docs/ai/diagrams/architecture_layers_v1.mmd` shows conceptual layer stack.

## Related docs

- `docs/ai/runtime_path_v1.md`
- `docs/ai/smoke_test_v1.md`
- `docs/ai/runtime_baseline_v1.md`
- `docs/ai/model_registry.md`
- `docs/ai/agent_state_schema_v1.md`
- `docs/ai/next_action_contract_v1.md`
- `docs/ai/prompt_contract_hardening_v1.md`
- `docs/ai/failure_recovery_policy_v1.md`
- `docs/ai/orchestrator_agent_boundary_v1.md`
- `docs/ai/role_template_constraint_format_v1.md`
- `docs/ai/action_validation_test_cases_v1.md`

## Done criteria

- architecture README updated
- canonical data flow documented
- future layers clearly marked as future
- diagrams added and referenced

## Next step

Architecture freeze audit.
