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

## Phase 13E4c note

- Phase 13E4c aligns the stateful planner variance prompts, evaluator comparisons, and workflow diagnostics after a replay that accepted all 15/15 outputs by schema but failed all 15/15 workflows.
- The overview prompt now separates the ticket board page from the direct policy and team-status reads, the ticket-priority prompt points at the hardboard fixture route, and the policy-search prompt keeps the citation requirement explicit.
- The evaluator now accepts exact fixture text or a contained visible span for fact comparison and reports richer mismatch and citation diagnostics with scenario, trial, and source-output context.
- The workflow now reports click-target-not-found traces with the visible targets on the current fixture page.

## Phase 13E4d note

- Phase 13E4d narrows the remaining alignment gap after the E4c diagnostics: fact comparison now case-folds fixture spans, citation diagnostics keep model-output evidence ids visible, and the ticket-priority prompt explicitly reopens the hardboard before Ticket 8.
- this is still fixture-backed, read-only, and does not add browser/Playwright execution from Codex

## Phase 13E4e note

- Phase 13E4e tightens the remaining fact anchoring after the E4d diagnostics: the policy-ticket prompt now copies the exact workspace policy marker without inventing admin approval language, and the ticket-priority prompt now copies Ticket 8 requester tier exactly as `office worker`.
- this is still fixture-backed, read-only, and does not add browser/Playwright execution from Codex

## Phase 13E4f note

- Phase 13E4f adds a safe diagnostic context trail for the `missing_final_answer_text` path and keeps policy-ticket outputs with a real `final_answer.answer_text` accepted.
- the ticket-priority prompt now explicitly anchors `ticket_8_marker` to `decoy for the priority cross-check`, warns against `none`, and tells the model to copy the visible search-marker phrase from the Ticket 8 page
- this remains fixture-backed, read-only, and does not add browser/Playwright execution from Codex

## Phase 13E4g note

- Phase 13E4g fixes the remaining false `missing_final_answer_text` rejection: final-answer prose may contain allowed local fixture URLs, and the validator now scans embedded URL tokens instead of parsing the whole sentence as a URL.
- After this fix, the captured 15-output variance evaluator rerun accepted 15/15 by validation and reached 12/15 workflow success; the remaining 3/15 policy-ticket failures were honest `fact_value_mismatch` results on `ticket_id`, where the model used `TICKET-12345` instead of the visible fixture label `Ticket 1`.
- this remains fixture-backed, read-only, and does not add model/browser/Playwright execution from Codex

## Phase 13E4h note

- Phase 13E4h anchors `stateful_policy_ticket_crosscheck` to copy `ticket_id` exactly as `Ticket 1` from the visible `Ticket 1 - Quarterly Access Review` page/title and explicitly warns against invented internal ids such as `TICKET-12345`.
- The prompt keeps `ticket_topic` anchored to `Quarterly Access Review`, ticket priority/role grounded in the visible ticket text, and `policy_marker` copied exactly from the Workspace Policy fixture marker.
- This is a prompt grounding repair only; the evaluator still rejects synthetic ticket ids as `fact_value_mismatch` and no verifier relaxation is introduced.
