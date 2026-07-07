# Phase 8: технический статус

## 1. Snapshot

Текущая code base поддерживает controlled local orchestrator/executor workflow для пары `second_model -> first_model`, deterministic office artifact validation, mini-matrix aggregation, flagship judge prompt exchange и guarded API judge runner.

Подтвержденные метрики последнего агрегата:

- `repeat_count`: 3
- `succeeded_count`: 3
- `failed_count`: 0
- `execution_attempted_count`: 6
- `execution_success_count`: 6
- `office_artifact_count`: 6
- `office_artifact_readable_count`: 6
- `correctness_score_count`: 3
- `mean_correctness_score`: 1.0
- `normality_input_count`: 3
- `resource_observation_count`: 3

Semantic judge score отсутствует: live/API judge не запускался.

## 2. Commit milestones

Ветка `main` содержит такие важные Phase 8 milestones:

- `442364e Add guarded single trial operator runner`
- `f18b10f Add single trial model pair execution`
- `50ee00f Add model pair execution readiness validation`
- `dd90586 Add local pipeline config support to single trial runner`
- `0a6ae98 Wire local model pair entrypoint to pipeline`
- `d35b6b7 Add first controlled single trial run packet`
- `cf09105 Add dual endpoint controlled trial packet`
- `3ca3929 Add compact prompt budget for local trials`
- `a8c9871 Add office action path repair`
- `f426b3d Add controlled DOCX append precreate`
- `cedf701 Add office execution artifact summary`
- `0d01758 Add controlled mini matrix packet`
- `5974050 Add mini matrix correctness postprocess`
- `cf2d898 Add flagship judge prompt exchange`
- `71f66dd Add guarded flagship API judge runner`

## 3. Architecture layers

Offline planning:

- Scenario/config packets live under `artifacts/first_run_packets/` and committed example configs under `configs/local_pipeline/`.
- These define repeat ids, pair ids, scenario ids and guarded runtime parameters.

Readiness validation:

- Model pair/scenario readiness is checked before controlled execution.
- Missing runtime prerequisites are surfaced as controlled validation or diagnostics, not hidden traceback-driven state.

Single-trial guarded execution:

- `scripts/run_single_trial_controlled.py` is the operator entrypoint for controlled trials.
- Runtime execution requires explicit opt-in and must not be launched automatically by docs/tests.

Office action repair and precreate:

- Compact prompts reduce local context pressure.
- Path repair converts unsafe/missing model paths into safe workspace-local office outputs.
- DOCX append precreate creates a missing append target before appending, and records `precreate_metadata`.

Artifact harvesting:

- `scripts/summarize_office_execution_artifacts.py` reads a trial result and checks office artifacts.
- The latest successful mini-matrix has 6 generated/readable DOCX artifacts across 3 repeats.

Correctness scoring:

- `scripts/score_office_execution_correctness.py` scores deterministic execution criteria.
- Current deterministic criteria include trial success, validation, execution attempted/succeeded, artifact existence and artifact readability.

Mini-matrix aggregation:

- `scripts/aggregate_mini_matrix_results.py` combines repeat directories into `mini_matrix_aggregate_summary.json`.
- Current aggregate summary reports 3/3 successful repeats and mean correctness 1.0.

Judge prompt exchange:

- `scripts/build_flagship_judge_prompt_pack.py` builds offline prompt-pack inputs from aggregate evidence.
- `scripts/parse_flagship_judge_responses.py` parses saved judge responses offline.
- Prompt packs and raw responses are generated artifacts and are intentionally ignored by Git.

Guarded API judge runner:

- `scripts/run_flagship_api_judge.py` exists for future explicit operator-controlled API evaluation.
- It requires judge config, explicit `--allow-api-judge` and confirmation.
- It was not run in this documentation update and should not be run by automated checks.

## Phase 9.1 Autonomous multi-agent runtime foundation

Phase 9.1 adds a library-only autonomous multi-agent runtime foundation in `src/agent/autonomous_multi_agent_runtime.py`.

What was added:

- deterministic scheduler modes: `round_robin` and `priority_then_round_robin`;
- shared state/task board with agents, tasks, statuses, shared facts, artifacts, per-agent history, group events, resource locks, retry counters and quarantined agents;
- runtime loop foundation: observe shared state, choose next agent, call injected decision provider, validate action envelope, call injected action executor, verify result, update shared state and apply policy;
- stop policy: max ticks, total actions, per-agent actions, idle limit, total failures, retries, all-tasks-terminal and no-runnable-agents stops;
- controlled error recovery: retry task, fail task after retry exhaustion, quarantine failing agents while keeping other agents runnable;
- deterministic resource lock model for future concurrency/resource controls;
- virtual environment/session metadata: environment id, safe relative workspace root, per-agent workspaces, reset policy and allowed resource namespaces;
- JSON-serializable `to_summary()` with schema `autonomous_multi_agent_runtime_summary_v1`;
- browser-aware validation hook: browser actions can be scheduled only when the virtual environment enables the `browser` namespace.

What does not run:

- no LLM client is created;
- no model, `llama-server`, GPU probe or runtime experiment is launched;
- no Playwright/Chromium browser is launched;
- no Microsoft Office/LibreOffice action is launched;
- no API/HTTP judge or LLM-as-a-judge is launched.

Which ТЗ gaps this advances:

- long-lived scheduler foundation;
- shared state/shared memory foundation;
- autonomous loop foundation;
- stop policy and completion criteria;
- error recovery foundation;
- concurrency/resource-control foundation through deterministic locks;
- virtual environment/session layer foundation;
- browser runtime interface hook for a later browser-completion phase.

Limitations:

- no true parallel execution or worker threads yet;
- no production deployment/hardening layer;
- browser completion is still not a real browser/Chromium execution layer;
- no mail/git/other app actions;
- no semantic LLM judge integration;
- current validation is unit-test/fake-provider based, not broad scenario validation.

## Phase 9.2 Autonomous browser runtime integration

Phase 9.2 adds browser runtime completion at the controlled/fixture-backed library layer in `src/agent/autonomous_browser_runtime.py`.

What was added:

- browser session/workspace metadata with safe session ids, workspace ids, environment ids, allowed domains, visited URLs, snapshots, last observation, synthetic form state and policy counters;
- browser action envelope for `browser_open_url`, `browser_search`, `browser_click`, `browser_extract_text`, `browser_fill`, `browser_submit`, `browser_wait` and `browser_snapshot`;
- namespace-gated browser validation through the existing autonomous runtime browser namespace guard;
- fixture-backed executor using repository HTML fixtures and `browser_fixture_resolver.py`, with no external network or real browser launch;
- deterministic browser verifier for expected text, expected URL and required snapshot/artifact checks;
- integration helper that converts `RuntimeActionDecision` into browser actions and returns `RuntimeActionResult`;
- browser observations are fed into generic runtime facts/events/artifacts without changing the autonomous runtime summary schema;
- optional Playwright adapter interface that remains disabled by default and does not import or launch Playwright on import.

What does not run:

- no real browser, Playwright or Chromium is launched;
- no external HTTP/network request is made by the fixture executor;
- no model, API judge, LLM-as-a-judge, Office/LibreOffice or experiment is launched;
- no mail/git/calendar/other external app actions are added.

Which TZ gaps this advances:

- browser scripts are no longer only scaffolded: they now have fixture-backed autonomous runtime integration;
- virtual environment namespace policy is exercised by browser actions;
- browser observations and synthetic browser artifacts can be carried by the autonomous runtime shared state.

Limitations:

- real Playwright/Chromium execution remains guarded future/operator-only work;
- browser coverage is fixture-backed and deterministic, not broad production web automation;
- mail/git/other application actions remain outside the approved scope.

## Phase 9.3 Config-driven autonomous browser scenario

Phase 9.3 adds a reproducible offline/config-driven browser scenario layer on top of the autonomous runtime foundation.

What was added:

- browser-only autonomous scenario config: `configs/autonomous_runtime/browser_intranet_research_group_basic.example.json`;
- scenario loader/validator in `src/agent/autonomous_runtime_scenarios.py`;
- deterministic `ScriptedRuntimeDecisionProvider` for reproducible dry-run tests;
- builder that creates `AutonomousMultiAgentRuntime`, shared state, browser sessions, fixture-backed browser executor and browser action executor from config;
- offline scenario runner CLI: `scripts/run_autonomous_runtime_scenario.py`;
- scenario summary schema `autonomous_runtime_scenario_summary_v1` with runtime summary, browser session summaries and expected-result checks;
- tests proving scheduler/shared state/browser actions work together end-to-end without real browser/model/API calls.

What does not run:

- no model client or LLM decision provider is created;
- no real browser, Playwright or Chromium is launched;
- no external HTTP/network request is made;
- no API/HTTP judge or LLM-as-a-judge is launched;
- no mail/git/calendar/other external app actions are added.

Which TZ gaps this advances:

- browser is now integrated into autonomous runtime at controlled fixture-backed scenario level;
- scenario config describes agents, tasks, virtual environment, browser sessions, scripted browser steps, runtime policy and expected results;
- runtime summaries can be reproduced offline from committed config and repository fixtures.

Limitations:

- this is an offline deterministic test harness, not production autonomous deployment;
- scripted decisions are used for reproducibility and do not add an LLM planner;
- real Playwright/Chromium execution and broader browser scenario coverage remain future guarded work.

## Phase 9.4 Expanded autonomous browser scenario coverage

Phase 9.4 broadens the offline/config-driven browser scenario coverage while preserving the no-real-browser guardrail.

What was added:

- extended browser-only scenario config: `configs/autonomous_runtime/browser_intranet_form_workflow_extended.example.json`;
- task dependency support via `depends_on` in autonomous runtime scenarios;
- deterministic dependency-block events for tasks scheduled before prerequisites complete;
- fixture-backed click navigation, form fill, form submit, wait and snapshot coverage in one scenario;
- per-task expected-result checks for expected text, current URL, minimum snapshot count and expected artifact kinds;
- browser coverage summary schema `autonomous_browser_scenario_coverage_v1`;
- small local HTML fixtures for portal request/submit pages;
- tests proving dependencies, expected results, coverage summary and CLI dry-run behavior.

What does not run:

- no real browser, Playwright or Chromium is launched;
- no external HTTP/network request is made;
- no model client, API/HTTP judge or LLM-as-a-judge is launched;
- no Office/LibreOffice runtime and no external app action namespace is added.

Which TZ gaps this advances:

- browser scenario coverage now includes navigation, synthetic form workflow, wait action and multi-agent dependencies;
- summaries now include browser action coverage, expected-result pass/fail counts, covered agents/tasks/sessions and policy denial count;
- the runner remains deterministic and reproducible from committed configs and repository fixtures.

Limitations:

- browser execution remains fixture-backed and synthetic;
- dependency gating is scenario-provider level, not a production distributed scheduler;
- real Playwright/Chromium checks remain future guarded/operator-only work.

## Phase 9.5 Browser scenario suite

Phase 9.5 adds a fixture-backed browser scenario suite/aggregator to prove broader autonomous browser coverage without launching a real browser.

What was added:

- two new browser-only scenario configs:
  - `configs/autonomous_runtime/browser_intranet_policy_research.example.json`;
  - `configs/autonomous_runtime/browser_portal_approval_check.example.json`;
- suite config: `configs/autonomous_runtime/browser_scenario_suite.example.json`;
- suite loader/runner module: `src/agent/autonomous_browser_scenario_suite.py`;
- suite CLI runner: `scripts/run_autonomous_browser_scenario_suite.py`;
- compact suite summary schema `autonomous_browser_scenario_suite_summary_v1`;
- local portal approval/status fixtures under `tests/fixtures/local_intranet/office_site_v1/portal/`;
- tests for suite loading, validation, aggregation, CLI dry-run and no-runtime safeguards.

Current suite coverage:

- 4 browser-only configs are covered:
  - basic intranet research;
  - extended form workflow;
  - intranet policy research;
  - portal approval/status check;
- suite-level required action coverage includes:
  - `browser_open_url`;
  - `browser_click`;
  - `browser_extract_text`;
  - `browser_fill`;
  - `browser_submit`;
  - `browser_wait`;
  - `browser_search`;
  - `browser_snapshot`.

What does not run:

- no real browser, Playwright or Chromium is launched;
- no external HTTP/network request is made;
- no model client, API/HTTP judge or LLM-as-a-judge is launched;
- no mail/git/calendar/other external app action namespace is added.

Which TZ gaps this advances:

- browser is now implemented for a controlled fixture-backed autonomous scenario suite;
- scenario breadth is broader than a single workflow and includes research, portal/status and form cases;
- summary aggregation reports scenario pass/fail counts, required action coverage and structured failures.

Limitations:

- this is still not production browser automation;
- real Playwright/Chromium execution remains a guarded future/operator-only path;
- mail/git/other application actions remain out of scope.

## Phase 9.6 Guarded Playwright operator path

Phase 9.6 prepares a guarded operator-only path for future real Playwright/Chromium browser checks without launching a browser during automated development/testing.

What was added:

- operator config example: `configs/autonomous_runtime/playwright_operator.example.json`;
- static readiness/packet module: `src/agent/autonomous_browser_playwright_operator.py`;
- guarded CLI runner: `scripts/run_autonomous_browser_playwright_operator.py`;
- required guard contract:
  - `--allow-real-browser`;
  - `--confirm-real-browser BROWSER_RUNTIME_OPT_IN`;
- packet builder support for README, commands JSON, readiness summary and config copy;
- fake/offline tests proving dry-run and guard refusal do not import Playwright, start a fixture server, launch a browser, run models or call judges.

Current behavior:

- default/dry-run mode validates config, suite/scenario paths, browser namespace, fixture server settings, backend settings, safe output paths and exact guard flags;
- runner refuses real-browser execution without both guards;
- when both guards are present, Phase 9.6 still returns `real_browser_execution_not_implemented` rather than launching a browser;
- fixture-backed browser scenario suite remains the primary automated test path.

What does not run:

- no real browser, Playwright or Chromium is launched;
- no `playwright install` or browser dependency check is run;
- no local HTTP fixture server is started;
- no model client, API/HTTP judge or LLM-as-a-judge is launched;
- no mail/git/calendar/other external app action namespace is added.

Limitations:

- real browser execution is prepared but not performed or validated;
- the next browser step, if approved, is an operator-run local Playwright smoke check against the fixture server;
- this is still not production autonomous browser deployment.

## 4. Offline reproduction commands

The following commands are intended for offline post-processing of already-produced artifacts. They do not start models or live API calls.

```powershell
.\.venv\Scripts\python.exe scripts\summarize_office_execution_artifacts.py `
  --trial-result artifacts\single_trial_runs\phase_8_26_mini_matrix_r1\model_pair_single_trial_result.json `
  --output artifacts\single_trial_runs\phase_8_26_mini_matrix_r1\office_execution_artifact_summary.json
```

```powershell
.\.venv\Scripts\python.exe scripts\score_office_execution_correctness.py `
  --trial-result artifacts\single_trial_runs\phase_8_26_mini_matrix_r1\model_pair_single_trial_result.json `
  --office-artifact-summary artifacts\single_trial_runs\phase_8_26_mini_matrix_r1\office_execution_artifact_summary.json `
  --output artifacts\single_trial_runs\phase_8_26_mini_matrix_r1\office_execution_correctness_summary.json
```

```powershell
.\.venv\Scripts\python.exe scripts\aggregate_mini_matrix_results.py `
  --run-output-dir artifacts\single_trial_runs\phase_8_26_mini_matrix_r1 `
  --run-output-dir artifacts\single_trial_runs\phase_8_26_mini_matrix_r2 `
  --run-output-dir artifacts\single_trial_runs\phase_8_26_mini_matrix_r3 `
  --summary-id phase_8_26_mini_matrix_r3 `
  --output-dir artifacts\mini_matrix_summaries\phase_8_26_mini_matrix_r3
```

```powershell
.\.venv\Scripts\python.exe scripts\build_flagship_judge_prompt_pack.py `
  --aggregate-summary artifacts\mini_matrix_summaries\phase_8_26_mini_matrix_r3\mini_matrix_aggregate_summary.json `
  --summary-id phase_8_26_mini_matrix_r3 `
  --output-dir artifacts\judge_prompt_packs\phase_8_26_mini_matrix_r3
```

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_scenario_suite.py `
  --suite configs\autonomous_runtime\browser_scenario_suite.example.json `
  --output artifacts\autonomous_runtime_summaries\browser_scenario_suite.summary.json `
  --dry-run
```

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_playwright_operator.py `
  --config configs\autonomous_runtime\playwright_operator.example.json `
  --dry-run
```

## 5. Commands that must not be launched automatically

- `scripts/run_single_trial_controlled.py --allow-runtime-execution`
- `scripts/run_flagship_api_judge.py --allow-api-judge`
- llama-server startup commands
- GPU/runtime probes
- Browser/Playwright/Chromium commands
- Microsoft Office/LibreOffice commands
- New stress tests or experiments
- Any command that reads GGUF/model binary contents

## 6. Intentionally ignored local artifacts

The following paths are runtime/generated or local-private and should remain out of commits:

- `artifacts/single_trial_runs/`
- `artifacts/mini_matrix_summaries/`
- `artifacts/judge_prompt_packs/`
- `artifacts/autonomous_runtime_summaries/`
- `configs/judge/*.local.json`
- `.env`
- `*.key`
- `*.pem`
- GGUF/model binaries

Committed packet/example files remain allowed, including `artifacts/first_run_packets/...` and `configs/judge/*.example.json`.

## 7. Current limitations

- Deterministic execution correctness is proven only for the controlled office scenario and N=3.
- Semantic judge scoring is not available yet.
- API judge provider integration needs a budgeted Phase 8.30 design and operator secret-handling path.
- Autonomous multi-agent runtime foundation exists, but production long-running deployment and true parallel execution are not implemented.
- Browser behavior is confirmed at the fixture-backed autonomous runtime/scenario layer only; real browser and real network behavior are not part of the confirmed run.
- Runtime artifacts are evidence for local work, but are not source-controlled.

## 8. Next technical stage

The next practical stage should be an operator-approved real Playwright smoke run against local fixtures, or additional fixture-backed browser breadth if real browser execution remains deferred.

Later semantic judge work remains separate and should stay guarded:

1. Define an openai-compatible/DeepSeek-style config schema that never stores secrets in committed files.
2. Add dry-run validation for endpoint, model id, prompt pack shape and output paths.
3. Keep live API execution behind explicit flags and confirmation.
4. Parse judge outputs into a semantic scorecard separate from deterministic correctness.
5. Add tests for missing key, malformed response, schema mismatch and no-runtime safety.
