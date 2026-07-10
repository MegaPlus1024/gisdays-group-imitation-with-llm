# Phase 13E2a Stateful Local Planner Packet

## Summary

Phase 13E2a hardens the stateful read-only planner packet after the first `third_model` run. The first operator attempt produced five responses with `finish_reason: stop`, but the evaluator rejected all five because the raw model output missed the strict output contract.

## What happened

- operator-run `third_model` planner output capture for the five E2 scenarios
- all five raw responses completed with `finish_reason: stop`
- evaluator result: `completed_with_failures`
- error code: `missing_action_field`
- `outputs_total`: `5`
- `outputs_present`: `5`
- `outputs_ingested`: `0`
- `outputs_rejected`: `5`
- `validation_accepted`: `0`
- `validation_rejected`: `5`
- `failure_class_counts.model_failed_task`: `5`

## Why it failed

The model produced useful JSON, but the shape did not match the evaluator contract:

- `actions[]` used `action` instead of `action_name`
- action parameters were placed at the top level instead of inside `parameters`
- `facts` was shaped like an object instead of an array
- `evidence_items` used `id/text/content` aliases instead of the required fields
- `final_answer` often omitted cited fact and evidence ids

## What E2a changes

- the packet prompt now includes a strict copyable JSON skeleton
- the prompt explicitly says to use `action_name` and `parameters`
- the prompt explicitly says to use `parameters.target_text` for `browser_click`
- the schema doc now calls out forbidden aliases
- evaluator diagnostics now explain the missing-field shape more clearly

## Boundary

- strict validation stays strict
- no alias normalization is enabled yet
- no models, browser, Playwright, or llama-server are launched by Codex
- generated packet artifacts are evidence only and should not be committed

## Next step

Rebuild the packet, inspect the new prompt and schema docs, and rerun the manual `third_model` E2 operator pass.
