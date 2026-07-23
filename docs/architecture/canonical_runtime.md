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
- Long-horizon experiments: `src/agent/canonical_multi_agent_experiments.py`
- Deterministic config: `configs/canonical_multi_agent.example.json`
- Experiment config:
  `configs/canonical_multi_agent_long_horizon.example.json`
- CLI: `scripts/run_autonomous_multi_agent_runtime.py`
- Tests: `tests/test_autonomous_multi_agent_runtime.py`
- Experiment tests: `tests/test_canonical_multi_agent_experiments.py`
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

Run the safe long-horizon fake harness:

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_multi_agent_runtime.py `
  --config configs\canonical_multi_agent_long_horizon.example.json `
  --trials-per-scenario 1 `
  --dry-run
```

This command uses the same domain objects, tool registry, policies, and
round-robin runtime. The experiment module adds scenario composition,
trace/materialization, and metrics only; it is not a second runtime.

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
`allow_model_calls=True`. Long-horizon CLI model execution also requires the
explicit `--allow-model-execution` flag. Without that flag, fake policies are
used and no endpoint is contacted.

Each model turn receives role, goal, resource and behavior constraints,
profile-filtered `ToolSpec` entries, the agent's bounded own history and
memory, explicit shared facts, the previous observation/error, and protocol
metadata. The response contract remains one `NextAction`; workflow arrays are
rejected. The prompt explicitly asks the model not to repeat a failed action
unchanged.

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

## Long-horizon experiment layer

The canonical experiment scenarios are:

- `article_file_handoff`: two agents alternate for 16 turns while reading a
  fixture article, writing/reading a bounded note, and publishing/reading one
  explicit shared fact;
- `office_shared_fact_recovery`: two agents alternate for 10 turns, including
  a missing-file observation, next-own-turn repair, office fixture reads,
  explicit shared facts, and a constrained fixture validation command;
- `bounded_repetition_and_role_guard`: deterministic fake variants exercise
  early stop, identical-action bounds, and role allowlist rejection before
  dispatch.

Every trial writes:

- `trial_summary.json` with per-agent and trial completion, action, recovery,
  repetition, role, latency, token, and fairness metrics;
- `group_trace.jsonl` in global scheduler order, with action/observation,
  recovery linkage, bounded parameters, sanitized diagnostics, and terminal
  reason.

`experiment_summary.json` aggregates pass rates by scenario, turn/wall-time
means, p50/p95 model latency, recovery/repetition/role rates, tool/action
counters, and token totals. Percentiles use deterministic standard-library
interpolation. All output paths are repository-relative below ignored
`artifacts/`.

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

## Environment Contract

Canonical long-horizon agents receive only role-relevant resources: exact
fixture URLs, readable field names, advertised relative paths, known files,
declared fact producer/consumer status, available commands, and generic task
progress. Fact values are not supplied before publication and permitted read.
Completion requirements are exposed as bounded contracts with an id,
description, status, evidence type, safe related resource ids, and the outcome
that satisfies the requirement. File resources are also described explicitly:
their repository-relative path, whether they exist, whether they are readable or
writable, their purpose, and the last safe error for that resource/action pair.
Historical file failures are kept separate from current retry advice. If a
consumer reads a declared handoff file before it exists, the descriptor records
the `file_not_found` history. When the producer later creates that same
resource, `exists` becomes true, `state_changed_since_failure` becomes true,
and `unchanged_retry_discouraged` becomes false. File-backed requirements can
bind to resource ids such as `research_note_txt`, so unrelated successful reads
do not complete the requirement.
Shared facts in canonical long-horizon scenarios require evidence-grounded
provenance. Successful observations create private bounded evidence records,
and `shared_publish_fact` must cite an owned `evidence_id` whose tool and field
match the scenario fact contract. The published value must match the observed
value after the contract normalization policy. Ungrounded, wrong-source, or
mismatched publications are recoverable failures and do not satisfy grounded
completion requirements.
`finish` is accepted only when declared generic requirements are met; pending
consumers can use non-mutating `wait_for_dependency`. Local Qwen-style action
prompts can use `/no_think`, while parsing remains limited to
`message.content`; sanitized protocol diagnostics retain content/reasoning
lengths and finish reason.

Recovery metrics distinguish generic recovery from scenario-required recovery.
Generic recovery means a changed successful action after a prior own failure
that advances a requirement or resolves dependency context. Required recovery
is an explicit scenario predicate. In `office_shared_fact_recovery`, the
required recovery evidence is: observe the expected missing-file error, then
successfully read the advertised existing `recovery_note` resource instead of
retrying the unavailable `missing_input` resource.

## Known limits

- deterministic local/fixture slice only;
- no real browser or external web;
- no Playwright in the canonical runtime;
- no true parallel execution;
- first real third_model smoke is mixed: `article_file_handoff` passed, while
  `office_shared_fact_recovery` reached 6/7 requirements before this recovery
  transparency repair;
- a later procedural `office_shared_fact_recovery` pass exposed ungrounded
  owner/status publication; future passes must satisfy value-source
  provenance, not key publication alone;
- three real `article_file_handoff` trials failed after a stale
  `file_not_found` retry warning remained visible even after `research_note_txt`
  existed; the repair distinguishes historical failure from current resource
  availability;
- long-horizon results currently prove deterministic fake/fixture behavior,
  not model quality;
- no fresh CPU/RAM/latency measurement for this runtime;
- no stable concurrency-2 evidence;
- no production recommendation.
