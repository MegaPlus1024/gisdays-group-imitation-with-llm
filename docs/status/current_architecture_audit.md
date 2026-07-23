# Current Architecture Audit

## Scope and baseline

This audit describes the executable repository at commit `d8da89f`. It was
performed without model calls, model servers, browser processes, Playwright,
Chromium, local HTTP servers, dependency installation, or generated artifact
changes.

Baseline checks:

- `src/agent`: 149 Python modules and about 82,900 lines.
- `scripts`: 69 Python entrypoints and about 6,900 lines.
- `configs`: 99 JSON files.
- `tests`: 178 Python test files and about 47,500 lines.
- pytest collection: 2,519 tests collected.
- `python -m compileall -q src scripts`: passed.
- tracked files under `artifacts/`: 45 historical first-run packet files.
- five generated artifact directories were present but untracked.

The size is not itself a defect. The architectural issue is that several
historical prototypes expose similar concepts as if they were peers, while
only a smaller subset is suitable as the current runtime foundation.

## Executable architecture

### Current foundations

| Concern | Current implementation | Evidence | Assessment |
| --- | --- | --- | --- |
| Model registry | `configs/evaluation_models.json`, `src/agent/evaluation_models.py` | `tests/test_evaluation_models.py` | Canonical metadata source for five local aliases. GGUF files are local-only. |
| Local OpenAI-compatible client | `src/agent/llm_client.py` | `tests/test_llm_client.py` | Reused by the canonical opt-in model policy, including one-action parsing and token telemetry. |
| Hardened stepwise local client | `src/agent/autonomous_browser_stepwise_article_local_model.py` | `tests/test_autonomous_browser_stepwise_article_local_model.py` | Stronger transport, opt-in, parsing, and diagnostics, but article-specific. |
| Script catalog | `src/agent/script_registry.py`, `configs/script_registry.example.json` | `tests/test_script_registry.py` | Best existing parameterized tool catalog and safety validator. |
| Script dispatch | `src/agent/script_execution_bridge.py`, `src/agent/scripts/` | `tests/test_script_execution_bridge.py` and backend tests | Existing file, office-file, shell, and fixture-open execution layer. |
| Canonical multi-agent runtime | `src/agent/autonomous_multi_agent_runtime.py` | `tests/test_autonomous_multi_agent_runtime.py` | One-action-per-turn round-robin runtime with profiles, allowlists, one tool registry, independent histories, explicit shared operations, recovery observations, repetition guard, and group metrics. |
| Canonical long-horizon experiments | `src/agent/canonical_multi_agent_experiments.py` | `tests/test_canonical_multi_agent_experiments.py` | Reuses the canonical runtime for repeated two-agent fixture trials, globally ordered JSONL traces, failure summaries, and per-agent/trial/experiment metrics. It defines no second runtime or model client. |
| Legacy callback scheduler | `src/agent/legacy_autonomous_multi_agent_runtime.py` | `tests/test_legacy_autonomous_multi_agent_runtime.py` | Preserved for historical browser runtime/bridge evidence; it is no longer the canonical import path. |
| Scripted multi-agent fixture scenario | `src/agent/autonomous_runtime_scenarios.py` | scenario and suite tests | Executes two agents through the scheduler, but decisions are prewritten one-action tasks rather than model-selected actions. |
| Stepwise observation/action benchmark | `src/agent/autonomous_browser_stepwise_article_benchmark.py` | Phase 15 tests | Genuine bounded one-action-per-turn loop, but single-agent and benchmark-specific. |
| Browser live loop | `src/agent/autonomous_browser_live_loop.py` | live-loop tests | Genuine model step loop with repair and fixture execution, but browser-specific and built around a broad action surface including clicks. |
| Frozen workflow benchmark | `src/agent/autonomous_browser_stateful_readonly_planner_*` | Phase 13E/14 tests | Historical benchmark family that asks for a complete workflow JSON. It is not the canonical interactive runtime. |
| Playwright replay | `src/agent/autonomous_browser_*playwright*` | Playwright operator/replay tests and bounded evidence docs | Optional guarded browser research path. It is not needed by the canonical fixture-only runtime. |

### Competing runtime families

1. `agent.py` + `state.py` + `runner.py` + `orchestrator.py`

   This is the earliest agent boundary. `AgentRunner.run()` performs one
   decision and intentionally forbids execution. `Orchestrator` only forwards
   one state to one agent. It remains referenced by tests and old docs, but it
   is not a multi-step or multi-agent runtime.

2. `multi_agent_orchestrator.py`

   `MultiAgentOrchestratorSmoke` runs complete per-agent runner calls
   sequentially. It does not interleave agent turns and is referenced only by
   its smoke test, readiness checks, one config, and historical docs.

3. `orchestrator_executor_pipeline.py` and related pair/probe modules

   This family implements an orchestrator-generated plan followed by executor
   actions. It has useful historical model/resource evidence, but it is a
   separate experiment stack rather than the current agent runtime.

4. `legacy_autonomous_multi_agent_runtime.py`

   This is the strongest reusable scheduler. It interleaves runnable agents,
   maintains `per_agent_history`, exposes an explicit shared task/fact state,
   and handles retries and bounded stops. Its current tasks are atomic:
   successful execution completes a task. Its action interface is callback
   based and it has no unified `ToolSpec`/`ToolResult` registry or profile
   allowlist.

5. `autonomous_runtime_scenarios.py`

   This composes the scheduler with fixture browser sessions. The example
   research group has two agents and six tasks, but all six decisions are
   stored in `scripted_steps`; it is deterministic scenario replay, not an LLM
   deciding each next action.

6. `autonomous_browser_live_loop.py`

   This has the desired observe -> one action -> validate -> execute -> observe
   shape for one agent. It is tightly coupled to browser fixtures and includes
   click/Playwright research behavior outside the canonical read-only scope.

7. Phase 15 stepwise article benchmark

   This is the cleanest proof that one model call can return one action instead
   of a complete workflow. Domain, environment, fake models, scoring, and the
   local adapter are embedded in benchmark modules rather than shared with the
   multi-agent scheduler.

8. Phase 13E/14 stateful read-only planners

   These modules build, capture, validate, materialize, and compare full
   workflow JSON outputs. They retain benchmark value, but they contradict the
   target canonical policy contract of one action per model turn.

9. `autonomous_multi_agent_runtime.py`

   The post-audit canonical runtime owns the shared domain types, tool
   interface, one-action policy contract, deterministic group scheduler, and
   current fake vertical slice. Historical browser modules import the explicit
   `legacy_` scheduler instead of sharing the canonical name.

10. `canonical_multi_agent_experiments.py`

   This is the canonical benchmark composition layer. It builds long-horizon
   scenarios from the domain/runtime/tool types above and writes traces and
   metrics. Its model path reuses `LocalOpenAIModelPolicy` and
   `LocalLLMClient`; no workflow-planner or browser-click runtime is imported.

## Reference and duplication findings

- `src/agent` contains roughly 24,900 lines of non-stateful autonomous-browser
  modules, 10,200 lines of Phase 13E/14 stateful planner modules, 17,600 lines
  of orchestrator/executor modules, and 2,400 lines of Phase 15 stepwise
  article modules.
- `orchestrator_executor_pipeline.py` is about 3,960 lines; the stateful
  variance module is about 2,830 lines; the browser live loop is about 2,790
  lines.
- Three local chat-client implementations are active in source:
  `LocalLLMClient`, `HttpxChatCompletionClient`, and
  `StepwiseArticleLocalModelClient`.
- The canonical runtime now owns shared `ToolSpec`, `ToolExecutionContext`,
  `ToolResult`, and `ToolRegistry` interfaces over the existing script
  registry and dispatch bridge.
- There is no exact `action_history` or `tool_registry` symbol in the current
  source. Equivalent data is split between execution history, runtime events,
  browser traces, and benchmark step results.
- The canonical script registry does not contain `browser_click`; click is
  concentrated in browser planning/live-loop/Playwright research paths and
  related configs/tests/docs.
- `src/agent/legacy_autonomous_multi_agent_runtime.py` has inbound source
  imports from the fixture execution/runtime bridge/browser suite family and
  remains isolated for historical evidence.
- `src/agent/multi_agent_orchestrator.py` has no production entrypoint import;
  its inbound references are a smoke test, readiness checks, one config, and
  historical documentation.
- `src/agent/orchestrator.py` has no active CLI import; its inbound references
  are the old boundary test and historical documentation.
- All 396 tracked Python files parsed successfully during the AST inventory.

## Twelve direct answers

1. **Is there a real multi-agent runtime?**  
   **Proven with deterministic policies.** `AutonomousMultiAgentRuntime`
   interleaves independent states over one shared tool registry. Local-model
   group evidence remains future opt-in work.

2. **Can more than one agent run in one bounded session?**  
   **Proven with fakes/fixtures.** The scheduler and
   `configs/canonical_multi_agent.example.json` run two agent states in one
   session. Long-horizon fake scenarios extend this to 16-turn article/file
   handoff and 10-turn office/shared-fact recovery.

3. **Does each agent retain independent history?**  
   **Proven.** Each canonical `AgentState` owns `HistoryEvent` records, and the
   two-agent test proves that agent ids never leak across histories.

4. **Does one model turn select exactly one action?**  
   **Proven by contract and fakes.** Canonical `ModelPolicy.next_action`
   returns one `Action` or stops. `LocalOpenAIModelPolicy` reuses the existing
   `LocalLLMClient` one-action parser and defaults to refusal.

5. **Can an execution error become an observation and be repaired next turn?**  
   **Proven with fakes.** The checker observes `file_not_found`, repairs the
   read on its next scheduled turn, and completes; the summary counts one
   recovered failure.

6. **Are activity scripts parameterized and validated?**  
   **Proven.** `ScriptRegistry`, `ScriptDescriptor`, parameter schemas, safety
   rules, and `validate_next_action_against_registry` cover this requirement.

7. **Is there one unified tool registry across browser, files, office files,
   and simple commands?**  
   **Proven for the canonical surface.** `ToolRegistry` adapts the existing
   script registry/bridge and adds fixture article and explicit coordination
   tools. It excludes `browser_click` and generic browser navigation.

8. **Are role/resource constraints enforced before execution?**  
   **Proven for tool access.** `AgentProfile.allowed_tools` is enforced before
   dispatch, in addition to existing registry parameter/path safety. Resource
   text constraints remain descriptive in the canonical slice.

9. **Are per-agent and group metrics available?**  
   **Proven for the scheduler and canonical experiment harness.** Runtime
   summaries include per-agent action/failure counts. Long-horizon summaries
   add completion, recovery, repetition, role, fairness, latency, token, and
   per-scenario pass-rate metrics.

10. **Is there a long multi-call benchmark rather than only complete workflow
    generation?**  
    **Proven with deterministic canonical policies; local-model evidence is
    pending.** The canonical harness executes fixed 10/16-turn two-agent
    scenarios under the one-action contract. Phase 13E/14 remain separate
    complete-workflow benchmarks.

11. **Is model variance measured?**  
    **Proven for controlled benchmark protocols.** Phase 13E/14 include repeated
    trials and multi-model comparisons. Results are fixture/protocol specific,
    not universal model rankings.

12. **Are CPU, RAM, latency, and safe concurrency established?**  
    **Partial.** Historical runtime probes contain RSS/CPU/latency measurements,
    formulas, and a bounded stress attempt. Stable concurrency 1 was observed
    for one pair; no stable concurrency 2 result or production sizing exists.

## TZ coverage matrix

Statuses mean:

- `proven`: directly exercised by current code/tests or bounded evidence.
- `partial`: a useful implementation exists but a required integration or
  breadth is absent.
- `missing`: no adequate implementation/evidence was found.
- `legacy-only`: present only in a superseded experiment path.
- `contradicted_by_current_architecture`: the current path uses a different
  interaction contract from the target architecture.

| TZ requirement | Status | Current evidence | Gap |
| --- | --- | --- | --- |
| Local small/medium model registry and launch metadata | proven | `configs/evaluation_models.json`, model registry tests | GGUF/runtime availability is operator-local. |
| Role, resources, constraints, and available actions in initial state | proven | canonical `AgentProfile`, config, tool registry | Resource strings are not a production sandbox policy. |
| Local model chooses the next action from state/history/tools | partial | canonical `ModelPolicy` and opt-in `LocalOpenAIModelPolicy` | Deterministic group run is proven; a local-model group run is not. |
| Scripts are allowed parameterized actions, not a fixed workflow | proven | script registry and validation tests | Several benchmark families still ask for full workflows. |
| Browser read activity | proven | canonical fixture article open/read/scroll/find/extract and Phase 15 | Real browser is deliberately outside the canonical slice. |
| File activity | proven | canonical fake slice, file scripts, and execution bridge tests | Write behavior is not exercised by the read-only fake config. |
| Office document activity | proven | DOCX/XLSX/PPTX file backends and tests | Optional dependencies/backends remain bounded. |
| Simple commands | proven | constrained shell action and tests | Command allowlist is intentionally narrow. |
| Mail/git/other applications | missing | none in canonical registry | Optional TZ clause; requires separate safety design. |
| Agent receives initial state from orchestrator/config | proven | scenario/config loaders and runtimes | Representations are duplicated. |
| Agent saves action and error history | proven | canonical `HistoryEvent` plus legacy evidence | Persistence is summary/JSON based, not an external store. |
| Group of local agents | partial | canonical two-agent fake slice and long-horizon harness | Local-model group execution and true parallelism are not proven. |
| Normal activity/role behavior evaluation | partial | normality and model evaluation modules | Evidence is controlled and scenario limited. |
| Coherence/diversity/repetition evaluation | proven | behavior/variance evaluators and tests | Metric definitions differ by benchmark family. |
| Several local models compared | proven | five aliases and Phase 14 evidence | Results are bounded to specific frozen protocols. |
| CPU-only feasibility | proven | local evidence and registry metadata | Not a throughput or production sizing claim. |
| RAM/CPU/latency measurement | partial | runtime baseline and pair probe evidence | No fresh canonical runtime measurement. |
| Concurrent-agent capacity formula/measurement | partial | capacity estimator and bounded stress evidence | True parallel canonical runtime and stable concurrency 2 are missing. |
| Short final report and recommendation | partial | final report and status docs | Existing docs are oversized and mix historical architectures. |
| Full-workflow planner as canonical runtime | contradicted_by_current_architecture | Phase 13E/14 | Canonical policy must return one action per turn. |

## Cleanup manifest

| path/subsystem | classification | inbound references | TZ value | replacement | confidence | action |
| --- | --- | --- | --- | --- | --- | --- |
| `src/agent/autonomous_multi_agent_runtime.py` | canonical_core | canonical CLI/config/tests | one-action policies, unified tools, group scheduling, independent histories, recovery | none | 0.99 | keep |
| `src/agent/canonical_multi_agent_experiments.py` | benchmark | canonical CLI/config/tests | long-horizon scenarios, traces, and repeated metrics over the canonical runtime | none | 0.99 | keep |
| `src/agent/legacy_autonomous_multi_agent_runtime.py` | legacy_experiment | browser runtime/bridge/suite modules and legacy tests | historical scheduler evidence | canonical runtime | 0.99 | keep isolated until browser evidence retirement |
| `src/agent/script_registry.py` | tool | bridge, runners, pipeline, tests | parameterized scripts and safety | none | 0.99 | keep |
| `src/agent/script_execution_bridge.py` and `src/agent/scripts/` | tool | experiment/pipeline/recovery modules and tests | file/office/command execution | none | 0.99 | keep and adapt |
| Phase 15 stepwise article modules | benchmark | two CLIs and tests | one-action loop and read-only browser evidence | canonical runtime should reuse concepts | 0.99 | keep as benchmark |
| `src/agent/llm_client.py` | runtime | old agent, experiment runner, pipeline, tests | local OpenAI-compatible calls | future shared client should absorb hardened behavior | 0.90 | consolidate later |
| `autonomous_browser_live_model_planner.py` client | duplicate | browser live loop and tests | guarded local model calls | shared local client | 0.90 | deprecate after migration |
| Phase 13E/14 stateful planner family | legacy_experiment | Phase 14 CLIs/tests/docs | unique frozen benchmark evidence | Phase 15/canonical stepwise runtime for current behavior | 0.98 | isolate and deprecate as runtime |
| browser live-loop family | legacy_experiment | Phase 13 CLIs/tests/docs | unique guarded fixture evidence | canonical generic loop for current runtime | 0.94 | keep evidence, deprecate as canonical |
| Playwright execution/replay family | legacy_experiment | guarded CLIs/tests/docs | unique real-browser research evidence | none | 0.99 | keep isolated |
| `src/agent/multi_agent_orchestrator.py` | duplicate | smoke test, readiness audit, config, old docs | early group scaffold only | autonomous scheduler | 0.93 | deprecate; do not delete yet |
| `src/agent/orchestrator.py` | duplicate | old boundary test and docs | early one-step boundary | canonical scheduler/policy loop | 0.93 | deprecate; do not delete yet |
| `src/agent/agent.py`, `runner.py`, `state.py` | legacy_experiment | active old CLI/experiment imports and tests | historical single-agent prototype | canonical domain/policy runtime | 0.85 | keep until migrated |
| orchestrator/executor pair/probe family | legacy_experiment | CLIs/tests/docs | unique historical group/model/resource evidence | canonical multi-agent loop for current behavior | 0.98 | isolate and deprecate as runtime |
| `configs/script_registry.example.json` | canonical_core | registry/bridge tests and runners | canonical action catalog base | normalized canonical registry | 0.99 | keep and consolidate |
| browser click configs/actions | legacy_experiment | browser/Playwright families and evidence | optional browser research | read-only article tools in canonical runtime | 0.99 | exclude from canonical registry |
| `experiments/` | required_report_evidence | docs and reports | historical model/resource results | none | 0.99 | keep read-only |
| tracked `artifacts/first_run_packets/` | required_report_evidence | historical report context | bounded first-run evidence | none | 0.96 | keep read-only |
| untracked generated artifact roots | generated_artifact | no canonical imports | none | reproducible CLIs/tests | 0.99 | generated_ignore |
| `README.md` historical command catalog | duplicate | primary project entry doc | obscures current architecture | concise README plus operator/status docs | 0.99 | consolidate |
| phase/status document collection | required_report_evidence | cross-linked historical evidence | audit trail | current audit/final report for active truth | 0.98 | archive from primary navigation, do not mass-delete |

No deletion in this audit is approved solely because a file has few imports.
The two early orchestrators are below the required `0.95` deletion confidence
because readiness tests and historical docs still assert their presence.

## Canonical target

The current implementation should converge on these layers:

1. Domain: `AgentProfile`, `AgentState`, `Action`, `Observation`,
   `HistoryEvent`.
2. Tools: `ToolSpec`, `ToolExecutionContext`, `ToolResult`, `ToolExecutor`,
   and one registry.
3. Canonical tools: fixture article open/read/scroll/find/extract, bounded file
   operations, office-file operations, and constrained simple commands.
   `browser_click` is excluded.
4. Policy:
   `next_action(agent_state, observation, allowed_tools) -> one Action`.
   Implement deterministic fake policies first and retain explicit opt-in for
   any local OpenAI-compatible client.
5. Runtime: a bounded single-agent step loop.
6. Group runtime: deterministic round-robin turns, independent agent histories,
   explicit shared environment operations, retries, and group metrics.
7. Benchmarks: separate modules that consume the runtime rather than define its
   domain types.

The canonical fake slice now demonstrates two role-distinct agents, four turns
per agent, eight total turns, one failed tool call observed by the policy,
recovery on that agent's next turn, independent histories, allowlist
enforcement, bounded repetition/stop behavior, explicit shared fact
publication/read, and a JSON-serializable group summary. It launches neither a
model nor a browser.

The canonical long-horizon harness extends that evidence without changing the
runtime: article/file handoff completes in 16 alternating turns and
office/shared-fact recovery completes in 10. Repetition, role violation,
early-stop, local-endpoint refusal, one-action parsing, trace sanitization, and
failure-summary paths are covered by deterministic tests. This is fake-policy
fixture evidence only; no local-model group run or true parallel execution is
claimed.

## Benchmark progression

1. Deterministic fake correctness: perfect, recovering, repeating,
   role-violating, and early-stop policies.
2. Single-agent local-model opt-in: one model call per turn, fixture-only tools,
   no full workflow JSON.
3. Two-agent sequential interleaving: independent histories and shared-state
   operations.
4. Repeated variance: fixed scenarios, at least three trials, action validity,
   recovery, repetition, latency, and completion metrics.
5. Resource/capacity: measured model RSS, host RAM/CPU, per-turn latency, then
   bounded concurrency experiments. No capacity recommendation before stable
   measured evidence exists.

## Canonical Multi-Agent Environment Contract Repair

The first two third_model smoke trials were diagnostic, not successful
long-horizon evidence: agents guessed resources, and `finish` could previously
complete a role before its declared work existed. The canonical runtime now
provides exact fixture URLs, field names without fixture values, scenario-safe
paths, fact inventory, dependency readiness, and generic task progress.
Premature finish is a recoverable `completion_requirements_unmet` observation.
After `5dd4820`, a real third_model smoke produced mixed evidence:
`article_file_handoff` passed with both agents completing 8/8 requirements and
no protocol/path/role failures. `office_shared_fact_recovery` reached 6/7
requirements, with the verification agent quarantined after the remaining
`recovery_completed` requirement stayed opaque. The repair now exposes
descriptive requirement contracts, explicit file resource status, and separate
generic versus scenario-required recovery metrics. This remains fixture-only
and does not claim production readiness.

A later real `office_shared_fact_recovery` smoke passed procedurally at 7/7
requirements, but trace review exposed a semantic gap: `document_agent`
published owner/status facts that were not grounded in prior owner/status
observations. That pass is therefore not full semantic evidence. Canonical
shared facts now require provenance from owned observed evidence, and future
pass criteria include value-source consistency as well as key publication.
