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

## Phase 9.7 Guarded Playwright execution implementation

Phase 9.7 implements the actual guarded Playwright smoke execution path behind the two explicit operator guards, while preserving offline/default behavior for Codex and automated tests.

What was added:

- execution module: `src/agent/autonomous_browser_playwright_execution.py`;
- lazy `RealPlaywrightBackend` that imports Playwright only inside the guarded execution context;
- injectable `FakePlaywrightBackend` and fakeable local fixture server interface for offline tests;
- stdlib-based local fixture HTTP server for operator-run smoke checks, constrained to loopback host and safe relative fixture roots;
- logical URL mapping from fixture scenario domains such as `local.intranet`, `docs.local` and `portal.local` to loopback fixture URLs;
- smoke summary schema `autonomous_browser_playwright_smoke_summary_v1`;
- runner integration so the guarded path calls the execution function only after readiness succeeds and both guards are present;
- execution scope config with `mode: first_scenario_only` and bounded `max_browser_actions`;
- packet/readme notes that the operator must install Playwright/Chromium separately if missing and Codex must not install dependencies.

Current behavior:

- `--dry-run` remains readiness-only and does not start a server, import Playwright, launch Chromium, run models or call judges;
- missing or incomplete guards still return refusal with `no_runtime_execution: true`;
- both guards now route to the real execution function, which is intended for manual operator use only;
- if Playwright is missing, the guarded path returns structured `playwright_dependency_missing`;
- if browser launch fails, the guarded path returns structured `playwright_launch_failed`;
- automated tests use fakes and do not launch a real browser or a real fixture server.

What does not run in Codex:

- no real browser, Playwright or Chromium is launched;
- no `playwright install` is run;
- no local HTTP fixture server is started for a real run;
- no model client, API/HTTP judge or LLM-as-a-judge is launched;
- no mail/git/calendar/other external app action namespace is added.

Limitations:

- real Playwright smoke success is not claimed yet because the guarded command has not been run by the operator;
- browser TZ status advances from readiness-only to implemented guarded execution path, but manual smoke evidence is still needed;
- this remains a controlled local fixture smoke path, not production browser automation or production hardening.

## Phase 9.8 Playwright fixture URL mapping fix

After Phase 9.7, an operator-run guarded Playwright smoke reached the real execution path: Playwright/Chromium started, six browser actions were attempted and the run produced a smoke summary. The run still failed because the loopback fixture URL mapping served logical routes such as `/tickets/1` instead of the actual fixture files such as `tickets/1.html`; the local fixture server therefore returned HTTP 404 pages, and those pages were incorrectly counted as successful browser actions.

What was fixed:

- logical URLs now resolve to served fixture file paths, not only logical route paths;
- mapping supports manifest routes plus fallback candidates: exact file, `.html`, `index.html` and domain-prefixed portal/doc paths;
- `portal.local/` maps to `portal/index.html` and `portal.local/status` maps to `portal/status.html`;
- real Playwright navigation records response status and treats HTTP status `>= 400` as `browser_http_error`;
- action-failure summaries now prefer `browser_action_failed` over expected-result failures;
- diagnostics sanitization preserves `http://` and `https://` URLs while still redacting local filesystem paths;
- the policy fixture contains the smoke search marker `fixture-backed result`.

What does not run in Codex:

- no real browser, Playwright or Chromium is launched by Codex;
- no local HTTP fixture server is started for a real run by Codex;
- no `playwright install`, model runtime, API judge or LLM-as-a-judge is launched.

Limitations:

- the corrected real Playwright smoke has not been rerun by Codex;
- the operator must rerun the guarded command manually to collect post-fix smoke evidence;
- success should not be claimed until that new operator-run summary is reviewed.

## Phase 9.9 Playwright smoke evidence

Phase 9.9 records safe committed evidence from the repeated operator-run guarded Playwright smoke after the Phase 9.8 fixture mapping fix.

Evidence source:

- raw runtime summary: `artifacts/autonomous_runtime_summaries/playwright_operator/playwright_smoke_summary.json`;
- committed evidence doc: `docs/status/playwright_smoke_evidence.md`;
- the raw runtime summary remains ignored and is not source-controlled.

Validated result:

- smoke status: `succeeded`;
- evidence level: `guarded_real_browser_smoke_succeeded`;
- guarded real browser path was executed by the operator, not by Codex;
- browser backend: headless Chromium through Playwright;
- scenario: `browser_intranet_research_group_basic`;
- actions attempted/succeeded/failed: 6/6/0;
- expected results passed: 6/6;
- logical URLs visited:
  - `https://local.intranet/tickets/1`;
  - `https://docs.local/docs/policy`;
- served URLs were loopback fixture URLs under `http://127.0.0.1:8765/`;
- no local absolute paths or secrets were present in the evidence summary.

What this confirms:

- the guarded Playwright/Chromium execution path can launch through the operator-approved command;
- the local fixture server serves the controlled pages after the Phase 9.8 mapping fix;
- browser open/extract/search/snapshot smoke actions work against committed local fixtures;
- expected text markers are found without external network access.

Limitations:

- this is one guarded smoke scenario only;
- evidence is for headless Chromium and a loopback-only fixture server;
- this is not production browser automation and not production deployment/hardening;
- no external network, mail/git actions or LLM judge were involved.

## 3.5 Phase 9.10 guarded Playwright suite path

Phase 9.10 extends the guarded Playwright operator path from a single smoke scenario to a bounded suite execution mode.

What changed:

- `configs/autonomous_runtime/playwright_operator.example.json` remains the single-scenario smoke config;
- `configs/autonomous_runtime/playwright_suite_operator.example.json` adds `execution_scope.mode: suite`, bounded `max_scenarios`, bounded `max_browser_actions_per_scenario` and required browser action coverage;
- the execution layer now supports `first_scenario_only`, `scenario_id` and `suite` scope selection;
- suite mode writes `playwright_suite_summary.json` with schema `autonomous_browser_playwright_suite_summary_v1`;
- suite summaries aggregate scenario counts, browser action counts, required action coverage, expected result counts, logical URLs and loopback diagnostics;
- Playwright action handling now includes the eight controlled browser actions: open URL, click, extract text, fill, submit, wait, search and snapshot;
- the evidence summarizer accepts both smoke and suite summary schemas;
- operator packets include readiness dry-run, guarded smoke and guarded suite commands.

What is verified in code:

- automated suite tests use fake backends and fake fixture servers only;
- suite dry-run validates config/readiness without importing Playwright or starting a browser/server;
- no real browser, Playwright, Chromium, external network, model runtime, Office runtime or LLM judge is launched by the automated checks.

What is not claimed:

- no committed evidence claims that the guarded suite was executed by the operator yet;
- the existing committed evidence now includes both the single smoke run and the guarded suite evidence recorded in Phase 9.12;
- production browser automation remains out of scope.

## 3.6 Phase 9.12 guarded Playwright suite evidence

Phase 9.12 records the successful operator-run guarded Playwright/Chromium suite against the local loopback fixtures after the Phase 9.11 marker fixes.

What was recorded:

- guarded real browser suite result succeeded with `status: succeeded` and `error_code: null`;
- browser backend: headless Chromium via Playwright;
- actions attempted/succeeded/failed: 30/30/0;
- scenarios attempted/succeeded/failed: 4/4/0;
- expected results passed/total: 30/30;
- required browser action coverage ratio: 1.0;
- logical URLs stayed inside the committed local fixture domains, with loopback-only served URLs.

Committed evidence:

- `docs/status/playwright_smoke_evidence.md` now summarizes the successful guarded suite evidence in bounded form.
- Phase 9 freeze report: `docs/status/phase_9_milestone_freeze.md`.

Limitations:

- this is still a local loopback fixture suite only;
- it is not external websites, not production autonomous browser use, and not a production hardening claim.

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

```powershell
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_playwright_operator.py `
  --config configs\autonomous_runtime\playwright_suite_operator.example.json `
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
- Browser behavior is confirmed at the fixture-backed autonomous runtime/scenario layer and by guarded Playwright/Chromium evidence against local fixtures, including a successful operator-run smoke and a successful operator-run suite; production browser automation and external web/network behavior are not confirmed.
- Runtime artifacts are evidence for local work, but are not source-controlled.

## 8. Next technical stage

The next practical browser stage should expand guarded browser coverage through the Phase 10.2a offline runtime-to-suite bridge, the Phase 10.2b offline CLI/config wrapper, the Phase 10.2c bounded runtime trace evidence layer, the Phase 10.3a offline browser plan validator, the Phase 10.3b offline validated-plan runtime dry-run bridge, the Phase 10.3c offline fixture-backed execution path, the Phase 10.3d offline planner packet builder and replay path, the Phase 10.3e offline planner replay suite/aggregator, the Phase 10.4a offline captured-output ingestion layer, the Phase 10.4b offline captured-output ingestion suite/aggregator, the Phase 10.5a offline local planner operator packet, and the Phase 10.6b compact local planner prompt profile, while keeping external network and production browser automation out of scope unless separately approved.

The offline ingestion loaders now tolerate UTF-8 BOM on Windows PowerShell-generated JSON configs and captured planner output text.

Phase 10.6a adds guarded local planner runtime diagnostics for an already-running local endpoint. It is meant to explain hangs with strict timeouts and bounded previews, not to launch models or claim production readiness.

Phase 10.6b adds a compact local planner prompt profile for manual CPU-bound schema-following checks. It is meant to reduce local operator prompt weight, not to call models or claim production readiness.

The first controlled local planner output evidence is documented separately in `docs/status/local_planner_output_evidence.md`; it is a manual `second_model` run followed by offline ingestion and fixture replay only.

The Phase 10 model-planned browser path freeze is documented separately in `docs/status/phase_10_model_planned_browser_freeze.md`; it captures the model-planned browser evidence line without extending into live browser automation.

Phase 10.8a adds a repeated local planner trials packet for three manual `second_model` runs; it is meant to check stability across repeated local planner outputs, not to call models by Codex.

Phase 10.8b documents the repeated local planner trials evidence in `docs/status/local_planner_repeated_trials_evidence.md`; it records three captured outputs, offline ingestion, dry-run acceptance, and fixture replay success, still without Codex-launched model execution or real browser automation.

Phase 10.9a prepares an offline packet for future guarded Playwright replay of a validated model-generated browser plan. It is a safety bridge from offline fixture evidence to future guarded browser replay and does not execute Playwright.

Phase 10.9b documents the offline Playwright replay packet evidence in `docs/status/model_plan_playwright_replay_packet_evidence.md`; it packages a validated model-generated browser plan without executing Playwright.

Phase 10.10a adds a guarded operator runner for validated model-plan Playwright replay. Default behavior refuses without explicit guards, dry-run validates and summarizes without browser, and real browser execution remains operator-only.

Phase 10.10b documents guarded fixture-backed replay evidence in `docs/status/model_plan_guarded_fixture_replay_evidence.md`; it confirms fixture-backed action replay, not real Playwright execution.

Phase 10.11a adds a guarded Playwright backend option for validated model-plan replay. It is disabled unless explicitly selected and guarded; Codex did not run it, existing verified evidence remains fixture-backed, and real Playwright evidence is still pending an operator-side run.

Phase 10.11b documents the first operator-run real Playwright replay evidence in `docs/status/model_plan_real_playwright_replay_evidence.md`; it stays limited to one validated plan against local loopback fixtures.

Phase 10.12b documents the successful operator-run real Playwright replay suite for three repeated model-generated plans in `docs/status/model_plan_real_playwright_replay_suite_evidence.md`; it remains limited to local loopback fixtures and repeated compact-prompt plans.

The final consolidated post-Phase-10 status is documented in `docs/status/final_consolidated_status_after_phase_10.md`.

Phase 10.12a adds a guarded replay suite for repeated model-generated plans; Codex only verified dry-run/refusal/offline paths, and real suite evidence is still pending an operator-side run.

Phase 11A later broadens local fixture-only browser scenario coverage with ticket triage and approval form review, keeping the work offline and preparing for future diverse model-generated plan trials without adding new real browser evidence.

Later semantic judge work remains separate and should stay guarded:

1. Define an openai-compatible/DeepSeek-style config schema that never stores secrets in committed files.
2. Add dry-run validation for endpoint, model id, prompt pack shape and output paths.
3. Keep live API execution behind explicit flags and confirmation.
4. Parse judge outputs into a semantic scorecard separate from deterministic correctness.
5. Add tests for missing key, malformed response, schema mismatch and no-runtime safety.
