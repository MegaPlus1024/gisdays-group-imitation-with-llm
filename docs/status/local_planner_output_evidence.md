# Local Planner Output Evidence

## Scope

- manual operator run of `second_model`
- compact local planner prompt
- captured output ingestion
- offline fixture replay

## Evidence summary

- model: `second_model`
- prompt_tokens: `312`
- completion_tokens: `185`
- total_tokens: `497`
- finish_reason: `stop`
- response content: valid JSON without markdown or code fences
- schema_version: `autonomous_browser_plan_v1`
- plan_id: `local_planner_policy_research_plan_v1`
- actions: `3`
- ingestion schema_version: `autonomous_browser_planner_output_ingestion_summary_v1`
- ingestion status: `succeeded`
- ingestion error_code: `null`
- extraction_status: `accepted`
- validation_status: `accepted`
- dry_run_status: `accepted`
- fixture_execution_status: `succeeded`
- actions_attempted/succeeded/failed: `3/3/0`
- expected_results_passed/failed: `3/0`
- extracted_plan_id: `local_planner_policy_research_plan_v1`
- model_execution during ingestion: `false`
- real_browser_execution during ingestion: `false`
- no_runtime_execution: `true`
- fixture execution summary status: `succeeded`
- runtime trace: present for dry-run and fixture execution

The saved raw planner output lives in the local operator packet artifact area as `artifacts/autonomous_runtime_summaries/local_planner_operator_packet/raw_planner_output.txt`. Raw runtime artifacts are not committed.

## What this proves

- `second_model` can produce a valid `autonomous_browser_plan_v1` under the compact prompt.
- Captured output ingestion works on real model output.
- The validator accepts the plan.
- The autonomous dry-run bridge accepts it.
- Fixture-backed execution succeeds for 3 actions and 3 expected checks.

## What this does not prove

- not real browser execution
- not guarded Playwright
- not production autonomous browser automation
- not an autonomous live LLM loop
- model was run manually by the operator, not Codex
- only one compact prompt / one plan
- uses local fixture-backed replay only
- no production hardening claim

## Relation to prior browser evidence

- Guarded Playwright suite evidence remains separate and stronger for the real browser path.
- This evidence is about model planning output only, replayed offline.

