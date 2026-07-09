# Phase 12D Hard Discrimination Packet

## Scope

- offline model-comparison packet for `second_model` vs `third_model`
- three harder local-fixture browser scenarios
- compact prompt source files saved as `planner_prompt.compact.txt`
- no Codex-launched model runs
- no real browser execution

## Evidence summary

- packet id: `browser_model_discrimination_packet_v1`
- schema_version: `autonomous_browser_model_comparison_packet_summary_v1`
- status: `succeeded`
- no_runtime_execution: `true`
- model_execution: `false`
- real_browser_execution: `false`
- packet output_dir: `artifacts/autonomous_runtime_summaries/model_discrimination_packet`
- models_total: `2`
- scenario_count: `3`
- commands_count: `18`
- expected_raw_output_paths: `6`
- third_model prompt prefix: `/no_think` was injected through the existing packet builder behavior
- build smoke result: succeeded
- evaluator missing-output smoke result: `completed_with_missing_outputs`
- evaluator missing-output error_code: `missing_captured_outputs`
- evaluator outputs_total: `6`
- evaluator outputs_present: `0`
- evaluator outputs_missing: `6`
- evaluator no_runtime_execution: `true`
- evaluator model_execution: `false`
- evaluator real_browser_execution: `false`
- evaluator playwright_execution: `false`
- evaluator browser_opened: `false`

## Fixture suite evidence

- `hard_policy_disambiguation` passed
- `hard_ticket_priority_crosscheck` passed
- `hard_approval_policy_match` passed
- browser action coverage stayed limited to:
  - `browser_open_url`
  - `browser_click`
  - `browser_extract_text`
  - `browser_snapshot`

## What this proves

- the packet can be built fully offline
- `third_model` is still configured as a stronger candidate with automatic `/no_think`
- the packet can be evaluated safely when captured outputs are missing
- the three hard fixture scenarios remain fixture-only and reproducible

## What this does not prove

- not that `third_model` is better than `second_model`
- not real browser execution
- not guarded Playwright execution for model-generated plans
- not an autonomous live LLM loop
- not production browser automation
- not general web browsing
- not a production readiness claim

## Phase 12D2 prompt strengthening

- the first operator-run hard packet attempt reached the model endpoints, but the captured outputs were rejected with `wrong_schema_version`
- that failure reflected an underspecified prompt shape, not a model/server launch problem
- Phase 12D2 strengthens the generated hard prompts so they explicitly ask for `autonomous_browser_plan_v1`
- the prompt text now spells out required top-level fields, allowed browser actions, local fixture URLs, and one-JSON-object-only output constraints
- `third_model` still keeps the existing `/no_think` prefix behavior, while `second_model` does not
- the packet remains offline and local-fixture-only from Codex's point of view

## Phase 12D3 action contract strengthening

- the first rerun after Phase 12D2 fixed `schema_version`, but validation still rejected all six outputs
- the root cause was alternate action field names such as `name`, `url`, `selector`, `target_url`, and `target_css` instead of the validator contract
- Phase 12D3 strengthens each hard prompt with the exact action object contract: `step_id`, `action_name`, `parameters`, and `expected_text`
- the prompts now include compact valid action examples, explicit `browser_open_url` and `browser_click` parameter shapes, and scenario-specific `target_text` values from the fixtures
- `max_actions` is now stated explicitly for each scenario, with the actions array required to stay within that bound
- no model, server, browser, or Playwright execution was launched by Codex

## Phase 12D4 literal expected_text anchors

- the Phase 12D3 rerun improved validation, but replay still failed because `expected_text` values were not literal enough
- the root cause is under-specified literal evidence strings: models used summaries or incomplete phrases instead of exact visible substrings from the fixtures
- Phase 12D4 strengthens the prompts with compact literal `expected_text` anchor lists for each hard scenario
- the prompts now require `expected_text` on every action, forbid invented summary wording, and remind the model that snapshot evidence still needs a literal visible page string
- `second_model` and `third_model` remain offline comparison candidates only; no production recommendation is made
- no model, server, browser, or Playwright execution was launched by Codex

## Relation to prior evidence

- Phase 12B remains the first successful `third_model` planner-output evidence.
- Phase 12C remains the compact baseline comparison and tie result.
- Phase 12D adds a harder offline discrimination packet, but still stays within local fixture replay and operator-managed artifacts.
