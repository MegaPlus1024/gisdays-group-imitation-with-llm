# Canonical Runtime

## Purpose

The canonical runtime is the smallest current implementation of the project
goal: role-constrained agents repeatedly choose one parameterized action,
observe the result, retain independent history, and take turns in an explicit
shared environment.

It is a research prototype. The default demonstration is deterministic,
fixture/local-tool only, and does not call a model or open a browser.

## Current entrypoints

- Runtime and domain: `src/agent/autonomous_multi_agent_runtime.py`
- Deterministic config: `configs/canonical_multi_agent.example.json`
- CLI: `scripts/run_autonomous_multi_agent_runtime.py`
- Tests: `tests/test_autonomous_multi_agent_runtime.py`
- Script catalog: `configs/script_registry.example.json`
- Existing dispatch backends: `src/agent/script_execution_bridge.py` and
  `src/agent/scripts/`
- Model aliases: `configs/evaluation_models.json`

Run the no-model vertical slice:

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_multi_agent_runtime.py `
  --config configs\canonical_multi_agent.example.json
```

The command emits one compact JSON summary to stdout. It does not write an
artifact unless `--output artifacts/...` is supplied.

## Layers

### Domain

- `AgentProfile`: role, goal, allowed tools, resource constraints, and behavior
  constraints.
- `AgentState`: lifecycle, counters, memory, last observation, and that agent's
  history.
- `Action`: one tool name and one parameter object.
- `Observation`: normalized success/output or structured error.
- `HistoryEvent`: one action/observation pair for one agent turn.

Each agent owns a separate `AgentState`. Group history is an aggregate view,
not the source of an agent's memory.

### Tools

- `ToolSpec`: name, family, parameters, and read-only metadata.
- `ToolExecutionContext`: runtime id, turn, agent state, and shared
  environment.
- `ToolResult`: normalized tool output or structured failure.
- `ToolExecutor`: execution protocol.
- `ToolRegistry`: the only canonical tool lookup and dispatch surface.

`build_default_tool_registry()` adapts the existing script registry and
`ScriptExecutionBridge` instead of duplicating file, office-file, or command
backends.

Canonical families:

- `browser_article_read`: fixture article open/read/scroll/find/extract;
- `files`: bounded repository-relative file actions;
- `office_documents`: bounded DOCX/XLSX/PPTX file actions already supported by
  the script bridge;
- `simple_commands`: constrained command action;
- `coordination`: explicit shared fact publish/read;
- `control`: agent completion.

`browser_click` and generic `browser_open_url` are deliberately absent. Click,
Playwright, and real-browser work remain isolated research paths.

### Policy

The policy contract is:

```text
next_action(agent_state, observation, allowed_tools) -> one Action or stop
```

The canonical module supplies deterministic policies for tests:

- `PerfectFakePolicy`
- `RecoveringFakePolicy`
- `RepeatingFakePolicy`
- `RoleViolatingFakePolicy`
- `EarlyStopFakePolicy`

`LocalOpenAIModelPolicy` reuses `LocalLLMClient`; it is not a second HTTP
client. It accepts only localhost endpoints and refuses calls unless
`allow_model_calls=True`. The canonical CLI uses fake policies and has no model
execution flag.

Complete workflow JSON is not the policy contract. Phase 13E/14 workflow
planners are retained as historical frozen benchmarks.

### Scheduler

`AutonomousMultiAgentRuntime` is deterministic round-robin:

1. Select the next ready agent.
2. Pass only that agent's state, last observation, and allowed tool specs to its
   policy.
3. Accept at most one `Action`.
4. Enforce registry presence and the agent allowlist.
5. Apply the identical-action repetition guard.
6. Execute through the shared registry.
7. Store the resulting observation in that agent's history.
8. Continue until all agents are terminal or a bound is reached.

The scheduler is interleaved, not parallel. No thread/process concurrency is
claimed.

## Error and recovery semantics

Validation and execution failures are observations, not tracebacks. The failed
agent remains schedulable unless its failure/repetition limit is reached.
Therefore its next policy turn can inspect the error and choose a corrected
action.

The default fake config proves:

- checker reads a missing fixture and observes `file_not_found`;
- reader publishes a shared fact on the intervening turn;
- checker performs a successful recovery read on its next turn;
- checker later reads the explicit shared fact;
- both agents finish;
- group metrics record one failed action and one recovered failure.

## Summary contract

Schema: `canonical_multi_agent_runtime_summary_v1`.

Important fields:

- `status`, `stop_reason`, `policy_contract`, `scheduler`;
- `turn_count`, `scheduler_trace`;
- `tool_registry`;
- `per_agent` states and independent histories;
- `group_metrics`;
- `group_history`;
- `shared_environment` fact keys and explicit operations;
- safety fields for model/browser/Playwright/external-network execution.

Tool metadata is sanitized before summary serialization. Resolved local
absolute paths and raw responses are not emitted.

## Legacy and benchmark boundaries

These paths remain available but are not canonical runtime layers:

- `src/agent/legacy_autonomous_multi_agent_runtime.py`: callback/task scheduler
  used by historical browser fixture bridges;
- `src/agent/autonomous_runtime_scenarios.py`: prewritten fixture actions;
- `src/agent/autonomous_browser_live_loop.py`: browser-specific model loop;
- `src/agent/autonomous_browser_*playwright*`: guarded Playwright research;
- `src/agent/autonomous_browser_stateful_readonly_planner_*`: Phase 13E/14
  complete-workflow benchmarks;
- `src/agent/autonomous_browser_stepwise_article_benchmark.py`: Phase 15
  benchmark/scoring harness.

Historical evidence is preserved. These modules should not be imported when
building new canonical runtime behavior.

## Benchmark progression

1. Deterministic fake correctness and safety.
2. One local model, one action per turn, explicit operator opt-in.
3. Two local-model agents under the same round-robin protocol.
4. Repeated fixed-scenario variance with action validity, recovery, completion,
   repetition, and latency metrics.
5. Measured RSS/RAM/CPU and bounded concurrency only after stepwise behavior is
   stable.

Existing Phase 14 rankings measure a frozen complete-workflow protocol and
must not be presented as results for this stepwise runtime.

## Known limits

- deterministic local/fixture slice only;
- no real browser or external web;
- no Playwright in the canonical runtime;
- no true parallel execution;
- no canonical local-model group run yet;
- no fresh CPU/RAM/latency measurement for this runtime;
- no stable concurrency-2 evidence;
- no production recommendation.
