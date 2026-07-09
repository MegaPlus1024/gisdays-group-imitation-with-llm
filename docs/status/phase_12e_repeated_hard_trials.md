# Phase 12E1 Repeated Hard Trials Variance Packet

## Scope

- offline repeated hard-trials packet for `second_model` vs `third_model`
- three calibrated hard browser-planner scenarios
- three manual trials per model/scenario combination
- offline variance evaluator and fixture replay bridge
- no Codex-launched model runs
- no real browser execution

## Evidence summary

- packet id: `browser_model_variance_packet_v1`
- packet schema_version: `autonomous_browser_model_variance_packet_summary_v1`
- packet status: `succeeded`
- packet no_runtime_execution: `true`
- packet model_execution: `false`
- packet real_browser_execution: `false`
- packet output_dir: `artifacts/autonomous_runtime_summaries/model_variance_packet`
- models_total: `2`
- scenarios_total: `3`
- trial_count: `3`
- trials_total: `18`
- expected manual model calls: `18`
- `third_model` keeps the documented `/no_think` prefix behavior
- repeated trial layout is captured as relative paths only
- variance config is written as `variance_config.local.json`
- commands file includes explicit `planner_prompt.compact.txt` references

## What this proves

- the repository now has a bounded offline packet for repeatability/variance work
- the packet is structured for `second_model` and `third_model` comparison under the same hard prompts
- the packet remains local-fixture-only and manual-operator-only
- the evaluator can later aggregate repeated trials without any Codex model or browser execution

## What this does not prove

- not repeated model quality evidence yet
- not that either model is better on the hard prompts
- not real browser execution
- not guarded Playwright execution for model-generated plans
- not an autonomous live LLM loop
- not production browser automation
- not a production readiness claim

## Relation to prior evidence

- Phase 12D documented the harder offline discrimination packet and its calibration history.
- Phase 12B documented the first successful `third_model` planner-output evidence.
- Phase 12C documented the compact baseline comparison.
- Phase 12E1 adds repeat-stability and variance scaffolding on top of that offline evidence line.
