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
| Local OpenAI-compatible client | `src/agent/llm_client.py` | `tests/test_llm_client.py` | Reusable early client, but it is tied to the old `NextAction` and prompt contract. |
| Hardened stepwise local client | `src/agent/autonomous_browser_stepwise_article_local_model.py` | `tests/test_autonomous_browser_stepwise_article_local_model.py` | Stronger transport, opt-in, parsing, and diagnostics, but article-specific. |
| Script catalog | `src/agent/script_registry.py`, `configs/script_registry.example.json` | `tests/test_script_registry.py` | Best existing parameterized tool catalog and safety validator. |
| Script dispatch | `src/agent/script_execution_bridge.py`, `src/agent/scripts/` | `tests/test_script_execution_bridge.py` and backend tests | Existing file, office-file, shell, and fixture-open execution layer. |
| Multi-agent scheduler | `src/agent/autonomous_multi_agent_runtime.py` | `tests/test_autonomous_multi_agent_runtime.py` | Real deterministic round-robin/priority scheduler with independent event histories, shared task board, retries, quarantine, locks, and group counters. |
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

4. `autonomous_multi_agent_runtime.py`

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
- There is one substantial script registry and dispatch bridge, but no shared
  runtime-level `ToolSpec`, `ToolExecutionContext`, or `ToolResult` interface.
- There is no exact `action_history` or `tool_registry` symbol in the current
  source. Equivalent data is split between execution history, runtime events,
  browser traces, and benchmark step results.
- The canonical script registry does not contain `browser_click`; click is
  concentrated in browser planning/live-loop/Playwright research paths and
  related configs/tests/docs.
- `src/agent/autonomous_multi_agent_runtime.py` has inbound source imports from
  the fixture execution/runtime bridge/browser suite family and is therefore
  not dead code.
- `src/agent/multi_agent_orchestrator.py` has no production entrypoint import;
  its inbound references are a smoke test, readiness checks, one config, and
  historical documentation.
- `src/agent/orchestrator.py` has no active CLI import; its inbound references
  are the old boundary test and historical documentation.
- All 396 tracked Python files parsed successfully during the AST inventory.

## Twelve direct answers

1. **Is there a real multi-agent runtime?**  
   **Partial.** `AutonomousMultiAgentRuntime` is a real interleaved scheduler,
   but its current model-facing scenario composition is scripted or
   browser-specific.

2. **Can more than one agent run in one bounded session?**  
   **Proven with fakes/fixtures.** The scheduler and
   `browser_intranet_research_group_basic.example.json` run two agent states in
   one session.

3. **Does each agent retain independent history?**  
   **Proven.** `RuntimeSharedState.per_agent_history` is keyed by agent id and
   covered by runtime tests. A canonical action/observation history abstraction
   is still missing.

4. **Does one model turn select exactly one action?**  
   **Proven only in single-agent paths.** The old `NextAction` path, browser
   live loop, and Phase 15 stepwise benchmark parse one action. The scripted
   multi-agent runtime does not yet use that policy contract.

5. **Can an execution error become an observation and be repaired next turn?**  
   **Partial.** Runtime task retries and browser/Phase 15 repair tests exist,
   but this is not demonstrated in a generic multi-agent policy loop.

6. **Are activity scripts parameterized and validated?**  
   **Proven.** `ScriptRegistry`, `ScriptDescriptor`, parameter schemas, safety
   rules, and `validate_next_action_against_registry` cover this requirement.

7. **Is there one unified tool registry across browser, files, office files,
   and simple commands?**  
   **Partial.** `configs/script_registry.example.json` catalogs these families,
   and `ScriptExecutionBridge` dispatches them. The Phase 15 browser article
   actions and browser live-loop actions use separate interfaces.

8. **Are role/resource constraints enforced before execution?**  
   **Partial.** Registry safety rules, scenario policies, URL policies, and
   runtime resource locks are enforced. A single `AgentProfile.allowed_tools`
   check is not present in the reusable scheduler.

9. **Are per-agent and group metrics available?**  
   **Proven for the scheduler.** Runtime summaries include per-agent action and
   failure counts plus group events/task counts. The metric vocabulary differs
   across historical benchmark families.

10. **Is there a long multi-call benchmark rather than only complete workflow
    generation?**  
    **Partial.** Phase 15 provides repeated stepwise calls for one article
    agent. Phase 13E/14 provide broad repeated model evidence, but each output
    is a complete workflow JSON.

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
| Role, resources, constraints, and available actions in initial state | partial | `state.py`, role/config files, script registry, runtime agent specs | No single canonical `AgentProfile` owns all constraints. |
| Local model chooses the next action from state/history/tools | partial | old `NextAction`, browser live loop, Phase 15 | Not integrated into the reusable multi-agent scheduler. |
| Scripts are allowed parameterized actions, not a fixed workflow | proven | script registry and validation tests | Several benchmark families still ask for full workflows. |
| Browser read activity | proven | Phase 15 fixture article open/read/scroll/find/extract | Real browser is deliberately outside the canonical slice. |
| File activity | proven | file scripts and execution bridge tests | Canonical multi-agent demonstration still needed. |
| Office document activity | proven | DOCX/XLSX/PPTX file backends and tests | Optional dependencies/backends remain bounded. |
| Simple commands | proven | constrained shell action and tests | Command allowlist is intentionally narrow. |
| Mail/git/other applications | missing | none in canonical registry | Optional TZ clause; requires separate safety design. |
| Agent receives initial state from orchestrator/config | proven | scenario/config loaders and runtimes | Representations are duplicated. |
| Agent saves action and error history | proven | execution history and runtime events | No single canonical history event type. |
| Group of local agents | partial | autonomous scheduler and fixture scenario | Generic model-driven group vertical slice missing. |
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
| `src/agent/autonomous_multi_agent_runtime.py` | canonical_core | browser runtime/bridge/suite modules and tests | group scheduling, independent histories, retries, locks | none | 0.99 | keep and consolidate |
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

The first canonical fake slice must demonstrate two role-distinct agents,
multiple turns per agent, at least six total turns, one failed tool call
observed by the policy, recovery on that agent's next turn, independent
histories, allowlist enforcement, bounded repetition/stop behavior, and a
JSON-serializable group summary. It must not launch a model or browser.

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

