# Model Plan Real Playwright Replay Evidence

## Scope

* captured `second_model` browser plan
* validated `autonomous_browser_plan_v1`
* model-plan Playwright replay operator
* guarded operator flags
* real Playwright/Chromium browser backend
* local loopback fixture server only

## Evidence summary

* schema_version: `autonomous_browser_plan_playwright_replay_operator_summary_v1`
* status: `succeeded`
* error_code: `null`
* guard_status: `guarded_replay`
* no_runtime_execution: `false`
* model_execution: `false`
* real_browser_execution: `true`
* replay_backend: `playwright`
* fixture_replay_execution: `false`
* playwright_execution: `true`
* browser_opened: `true`
* real_network_traffic: `false`
* plan_id: `local_planner_policy_research_v1`
* actions_total: `3`
* actions_attempted/succeeded/failed: `3/3/0`
* expected_results_passed/failed/total: `3/0/3`
* base_url: `http://127.0.0.1:8765`
* blocked_request_count: `0`
* logical URLs:
  * `https://local.intranet/`
  * `https://docs.local/docs/policy`
* served URLs:
  * `http://127.0.0.1:8765/index.html`
  * `http://127.0.0.1:8765/docs/policy.html`
* Playwright ran headless
* fixture manifest: `tests/fixtures/local_intranet/office_site_v1/site_manifest.json`

## What this proves

* a captured model-generated plan can reach the real browser automation path
* the Playwright backend can replay the validated plan
* 3/3 planned browser actions succeeded
* 3/3 expected checks passed
* the browser was opened through Playwright/Chromium
* no external network traffic was reported
* the model was not called during replay

## What this does not prove

* not general web browsing
* not external website browsing
* not an autonomous live LLM loop
* not production browser automation
* not mail/git/calendar actions
* not production readiness
* only one validated plan
* only one scenario family
* only local fixtures / loopback server
* no LLM judge

## Relation to previous evidence

* Phase 9: manually guarded Playwright suite across fixture scenarios
* Phase 10.8: repeated `second_model` planner outputs, offline fixture replay, 3/3 outputs and 9/9 checks
* Phase 10.10: guarded fixture-backed model-plan replay
* Phase 10.11a: guarded Playwright backend option for validated model-plan replay
* Phase 10.12a: guarded replay suite for repeated model-generated plans
* Phase 10.12b: repeated-output real Playwright replay suite evidence is documented separately in `docs/status/model_plan_real_playwright_replay_suite_evidence.md`
* this page records the first successful real Playwright replay of a validated model-generated browser plan
