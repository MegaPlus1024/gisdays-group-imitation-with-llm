# Local Orchestrator/Executor Executor Failure Analysis

## Purpose

This note analyzes the executor-stage failures from the v2 local orchestrator/executor proof and records the hardening direction for the v3 run.

Source artifact:

```text
experiments/multi_agent/orchestrator_executor/local_second_to_first_group_poc_v2_repair
```

## v2 result

The v2 run reached the executor model with a valid orchestrator plan, but both executor actions failed validation before execution:

| agent | raw action | validation failure |
|---|---|---|
| `office_agent` | `read_file` with empty `parameters` | `missing_required_parameter` for `path` |
| `developer_agent` | `create_file` with an absolute `C:\...` path | `unsafe_path`, `path_outside_allowed_roots` |

The orchestrator plan itself was role-compatible. It assigned both agents `read_file`-focused local documentation tasks, so the failure was in executor action selection, not in scenario safety.

## Root causes

1. Executor prompt context did not expose enough explicit action guidance. The model saw the generic `NextAction` contract but not a compact task-specific reminder of required parameters, safe roots, and working examples.
2. `AgentState.to_prompt_context()` omitted `metadata`, so assignment metadata such as `assigned_goal` and `orchestrator_task_id` was not present in the rendered executor prompt.
3. Safe relative path examples were too weak. The executor had no strong nearby examples such as `docs/ai/model_research_metadata.md` or `configs/evaluation_models.json`.
4. `--repair-attempts 1` was accepted by the group runner config, but `_run_executor_step` still performed only one executor attempt. Failed executor validation did not trigger a model-backed repair call.

## What was not changed

The registry and role validators behaved correctly. The v2 failures were real safety/contract rejections, so the fix is prompt and repair-loop hardening, not weakening validation.

## v3 hardening target

The v3 implementation adds:

- executor prompt hints with `agent_id`, `role_id`, assigned goal, task id, allowed actions, required parameters, safe path roots, and JSON-only examples;
- explicit path rules: relative project paths only, no drive letters, no leading slash, no `..`;
- model-backed executor repair for parse/validation failures;
- `per_agent_attempts.jsonl` to preserve initial and repair attempts separately.
