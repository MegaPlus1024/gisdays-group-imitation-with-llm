# Final Project Completion Report

## Executive summary

This repository now satisfies the research-prototype closure for the stated TZ: a controlled local LLM agent stack was designed, implemented, and experimentally checked across single-agent, orchestrator/executor, guarded browser, and final stateful read-only planner tracks.

The strongest final browser-planner evidence is the repeated stateful read-only planner variance success under `third_model`: 5 controlled scenarios x 3 trials = 15 captured outputs, 15/15 validation acceptance, 15/15 evaluator workflow success, and 15/15 materialized workflows. Those model calls were manual operator runs. The evaluator and materializer stayed offline, fixture-backed, and did not launch models, browser, Playwright, Chromium, or external network activity.

This is a controlled fixture-only research prototype. It is not production-ready, not a claim of enterprise browser automation, not a claim of email/git support, and not a claim of high-scale multi-agent deployment.

## Post-completion note

Phase 14 adds an optional multi-model benchmark layer for the completed controlled read-only prototype. It reuses the five stateful read-only scenarios to prepare repeated packet paths for multiple configured model aliases and to classify captured outputs per model offline. This expansion does not change the original TZ completion claim in this report.

The first real Phase 14B benchmark result separates the final stronger planner candidate from the weaker baseline without changing prompts or evaluator rules: `third_model` reached `15/15` validation acceptance and `15/15` workflow success, while `second_model` reached `12/15` validation acceptance and `0/15` workflow success. The evaluator stayed offline, fixture-only, and performed no model, browser, or Playwright execution.

Phase 14C extends that optional benchmark registry/config path with `fourth_model` and `fifth_model` as future local benchmark candidates only. Their GGUF paths stay local-only, they are not required for the original TZ completion, and no benchmark result is claimed for them in this report.

After the Phase 14E frozen-raw runner repair, a clean runner-owned rerun was completed as a separate post-completion benchmark line. Under that bounded fixture-only raw benchmark, `fourth_model` led `third_model` at `6/8` versus `5/8` workflow success with a shared prompt/schema/evaluator contract and shared `max_tokens: 4096`. That result supersedes the earlier polluted Phase 14E preliminary run, but it remains a narrow fixture-only comparison and does not replace the stronger final `third_model` repeated-variance evidence used for the core project closure.

Phase 14F adds the final presentation benchmark result above that repaired methodology. It uses a presentation-oriented 11-scenario frozen raw packet, a five-profile sequential run config, and a Markdown/CSV/JSON summary tool over five local aliases. In that presentation layer, `first_model` points to IBM Granite 3.3 8B Instruct Q4_K_M as the small/medium non-Qwen baseline; the earlier Phi-4-mini local file was archived locally and was not committed.

Important framing: that Phase 14F line is a frozen raw one-shot workflow-JSON planner benchmark, not a high-confidence long-horizon interactive browser-agent benchmark. A single PASS/FAIL there can mix schema validity, action validity, workflow materialization, and final-answer quality. A model can therefore be semantically close to the task intent and still fail because the workflow proposes an invalid action such as clicking non-clickable text.

The final Phase 14F evaluator summary remained offline and fixture-only after capture:

- `status: completed_with_failures`
- `error_code: browser_click_target_not_found`
- `best_model_by_pass_rate: fourth_model`
- `model_execution: false`
- `real_browser_execution: false`
- `playwright_execution: false`
- `browser_opened: false`
- `no_runtime_execution: true`
- `fixture_only: true`

Final bounded outcome for that specific benchmark:

- `fourth_model`: `5/11` workflows succeeded, `11/11` validation accepted
- `third_model`: `5/11` workflows succeeded, `9/11` validation accepted, `1` length-limited output
- `fifth_model`: `3/11` workflows succeeded, `11/11` validation accepted
- `first_model`: `1/11` workflows succeeded
- `second_model`: `1/11` workflows succeeded

This does not change the core project closure basis, which still rests on the stronger repeated `third_model` Phase 13E stateful variance evidence. It records one presentation-grade, fixture-only, frozen raw comparison table with no model-specific prompt tuning and no production-readiness claim.

Phase 15 begins a separate fixture-only stepwise observation-action benchmark for article/browser-style tasks so that long-horizon interactive behavior can be measured more directly than in the frozen raw one-shot Phase 14F table.

## A. Analysis of implementation means

- Local small/medium LLMs were used through GGUF-backed local model aliases `first_model`, `second_model`, and `third_model`.
- The documented local launch method is `llama.cpp` / `llama-server` with an OpenAI-compatible `/chat/completions` API shape and PowerShell wrappers such as `scripts/start_llama_server.ps1`.
- Integration with the execution agent is implemented through `src/agent/llm_client.py`, `src/agent/action_selector.py`, `src/agent/script_registry.py`, and `src/agent/script_execution_bridge.py`.
- Role, context, and script formats are represented through `AgentState`, role templates/configs, prompt contracts, `NextAction` JSON, and the parameterized script registry.

## B. Overall design

- The project implements an orchestrator/agent interaction model with a sequential orchestrator/executor prototype for group work and a separate read-only browser-planner path for controlled fixture workflows.
- Initial state composition is built from role, objective, environment, resources, constraints, available actions, and recent history.
- Parameterized actions/scripts are archived in the script registry and scenario/config packets rather than being hard-coded as one fixed scenario.
- Local LLM next-action choice is mediated through JSON-only prompt contracts, parser/validator layers, and bounded repair logic before any execution bridge is reached.
- Action, error, and history logging exist through workflow traces, JSONL logs, evaluator summaries, and materialized workflow artifacts.

## C. Minimal activity scripts

- Browser/read/navigation is the main demonstrated activity path. The strongest evidence line is the controlled fixture-backed browser and stateful read-only workflow stack.
- File actions, document/file stubs, and simple shell commands exist at prototype level and are bounded by safe roots, allowlists, and fixture-oriented execution rules.
- Email and git actions are intentionally out of scope for final closure. They are not part of the final proven capability set and should remain optional future work only.

## D. Agent prototype

- Config and packet input paths exist for agent state, evaluation scenarios, browser-plan packets, planner-output ingestion packets, variance packets, and materializer/evaluator configs.
- The local LLM planner path is implemented as a prompt -> JSON output -> validator -> evaluator/materializer chain, with manual operator model execution where real local model outputs were needed.
- Parameterized action selection is enforced through the `NextAction` contract plus registry validation rather than free-form execution.
- Evaluator, materializer, and history artifacts exist for repeated stateful read-only workflows and for earlier orchestrator/executor experiments.
- The final browser/stateful closure remains read-only and controlled: it proves repeated workflow planning and replay against fixtures, not a general autonomous runtime.

## E. Experiments with local models

### first_model

- `first_model` now serves as the small/medium non-Qwen baseline slot for the optional Phase 14F presentation benchmark.
- Evidence across orchestrator/executor work shows it is weak as orchestrator and repeatedly failed at orchestrator plan parsing.
- It may remain a bounded executor candidate in limited scenarios, but it is not the preferred planner/orchestrator path.

### second_model

- `second_model` was the strongest earlier baseline in the single-agent and orchestrator/executor lines.
- It delivered the best simple-scenario resource-balanced pair with `second_model -> first_model` and the best preliminary quality-focused group pair with `second_model -> second_model`.
- It also underpins earlier compact browser-planner and guarded browser evidence.

### third_model

- `third_model` was introduced as the stronger browser/stateful planner candidate.
- The early compact baseline comparison with `second_model` was a tie on the lighter packet, so the project did not immediately claim it as a winner.
- The final repeated stateful read-only variance evidence is the strongest model-specific success line in the browser/stateful track:
  - 5 scenarios x 3 trials = 15 outputs
  - evaluator: 15/15 validation accepted, 15/15 workflows succeeded
  - materializer: 15/15 outputs accepted, 15/15 workflows materialized
- Important caveat: the `third_model` calls were manual operator runs. The evaluator and materializer were offline and performed no model execution.

## F. Minimal resource evaluation

### What is supported by evidence

- CPU-only feasibility is supported at prototype level. The project explicitly documents CPU-first assumptions and multiple local runs without requiring production GPU dependence.
- Windows workstation usage is documented throughout the repository, with Python 3.12 and local PowerShell workflows. An optional GPU smoke was also documented separately for an NVIDIA RTX PRO 4000 Blackwell workstation path, but it is a short readiness check rather than a capacity proof.
- The resource evidence base is mixed:
  - older single-agent resource evaluation is formula-based
  - orchestrator/executor runtime probe adds short measured RSS/CPU telemetry
  - bounded stress evidence remains preliminary and only supports stable concurrency 1 for the tested pair
- Exact latency tables for the final Phase 13E4 repeated stateful planner path are not documented. That gap should remain explicit.

### Practical resource interpretation

- If agents share one local model server and plan sequentially, model memory can be shared and the system is more likely to be latency-bound than model-memory-bound.
- If each agent owns its own local model instance, memory scales roughly linearly with the number of active model instances.
- KV cache growth, context size, browser/document fixtures, logs, and materialized artifacts add overhead beyond the bare GGUF size.

### Conservative concurrency formula

`N_agents_parallel ~= floor(Available_RAM_for_agent_runtime / RAM_per_agent_instance)`

Use this only as a conservative planning aid, not as proof of achievable concurrency.

- `Available_RAM_for_agent_runtime` should exclude OS reserve and non-agent background load.
- `RAM_per_agent_instance` should include model serving overhead, KV cache/context growth, and per-agent workflow overhead.
- Practical concurrent-agent limits should be validated by dedicated load tests; they should not be claimed from the formula alone.

### Known limitations of the resource section

- Precise latency numbers for the final stateful planner loop are missing.
- No final high-confidence concurrency table exists for the `third_model` stateful workflow path.
- The best existing group capacity evidence remains preliminary and scenario-dependent.

## G. Final recommendation

### Chosen implementation direction

- Keep the controlled local LLM architecture based on role/context/config input, JSON next-action planning, registry validation, bounded execution, and evidence-first evaluator/materializer reporting.
- For further browser/stateful development, use `third_model` as the main controlled read-only planner candidate because it is the model behind the final 15/15 repeated stateful variance success.
- Keep `second_model` as the main baseline comparator and earlier orchestrator candidate reference.
- Do not use `first_model` as the default orchestrator.

### Resource recommendation

- Continue with CPU-first or shared-endpoint local development unless a new GPU/capacity study is explicitly planned.
- Treat concurrency estimates as provisional until measured under dedicated load tests.
- Prefer shared local model serving when comparing multiple controlled agents, because it avoids linear duplication of model memory.

### Limitations and caveats

- controlled fixture-only research prototype
- not production-ready
- not real enterprise browser automation
- not external web browsing
- not email/git support
- not a production multi-agent scheduler
- not a proven high-scale deployment configuration

## Coverage against the TZ

- local LLM agent prototype with role/context/script inputs: covered
- autonomous next-action choice through a local model contract: covered at prototype level
- action and error history preservation: covered
- short report with model comparison and resource discussion: covered
- repeated stateful planner experiments with final 15/15 success: covered
- minimal resource discussion and conservative concurrency formula: covered
- production-readiness claim: intentionally not made
