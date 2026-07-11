# Phase 13E4 Stateful Planner Variance

## Summary

Phase 13E4 adds a repeated stateful read-only planner variance suite for `third_model`.

It prepares three manual trials for each of the five stateful workflow scenarios, then reuses the existing offline evaluator and materializer paths to keep the packet, runtime config, and workflow artifacts aligned.

The suite is fixture-only and read-only. Codex does not launch a model, browser, or Playwright to create it.

## Evidence table

| scenario_id | trials_per_scenario | model_alias | packet | evaluator | materializer |
|---|---:|---|---|---|---|
| `stateful_policy_ticket_crosscheck` | 3 | `third_model` | prepared | prepared | prepared |
| `stateful_approval_policy_crosscheck` | 3 | `third_model` | prepared | prepared | prepared |
| `stateful_intranet_overview_digest` | 3 | `third_model` | prepared | prepared | prepared |
| `stateful_ticket_priority_digest` | 3 | `third_model` | prepared | prepared | prepared |
| `stateful_policy_search_marker_review` | 3 | `third_model` | prepared | prepared | prepared |

## Scenario outcomes

- The packet builder emits per-scenario compact prompts, request records, and relative request/output paths.
- The evaluator is designed to consume 15 captured outputs across the five stateful scenarios.
- The materializer is designed to turn accepted outputs into per-workflow state, trace, and workflow-summary artifacts.

## Repairs and guards exercised

- Runtime config loading accepts UTF-8 JSON and UTF-8 with BOM via `utf-8-sig`.
- Packet/evaluator/materializer summaries stay structured and offline.
- The generated commands document the manual `third_model` flow, not an autonomous model launch from Codex.

## Safety boundaries

- fixture-only local planner variance
- no Codex-launched model calls
- no browser or Playwright execution
- no external network access
- no GGUF modification
- no generated artifacts committed

## Limitations

- This suite documents repeated local variance plumbing, not production browser automation.
- It remains constrained to the five stateful read-only workflow scenarios and `third_model` only.
- It does not prove live external browsing or security hardening.
- The evaluator and materializer remain offline replay steps.

## Next recommended phase

Use the variance packet as the repeatable fixture source for continued offline audit, comparison, or reporting without changing runtime behavior.
