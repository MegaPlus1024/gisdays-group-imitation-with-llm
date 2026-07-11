# Phase 13E4 Stateful Planner Variance

This phase adds a repeated stateful read-only planner variance packet for `third_model`.

## What it does

- prepares three trials per stateful workflow scenario
- writes request records, request paths, output paths, and a local runtime config
- keeps the packet/evaluator/materializer flow offline and fixture-backed
- documents the manual `third_model` command flow without launching a model from Codex

## Suggested local commands

```powershell
.\.venv\Scripts\python.exe -m pytest tests/test_autonomous_browser_stateful_readonly_planner_variance.py
.\.venv\Scripts\python.exe scripts\build_autonomous_browser_stateful_readonly_planner_variance_packet.py --config configs\autonomous_runtime\browser_stateful_readonly_planner_variance.example.json
.\.venv\Scripts\python.exe scripts\run_autonomous_browser_stateful_readonly_planner_variance_evaluator.py --config artifacts\autonomous_runtime_planner_packets\stateful_readonly_planner_variance\variance_config.local.json
.\.venv\Scripts\python.exe scripts\materialize_autonomous_browser_stateful_readonly_planner_variance_outputs.py --config artifacts\autonomous_runtime_planner_packets\stateful_readonly_planner_variance\variance_config.local.json
```

## Troubleshooting

- If the config file was written by PowerShell with a BOM, the loader should still accept it via `utf-8-sig`.
- Missing captured outputs remain a handled failure mode in the evaluator and materializer.
- The command markdown should mention `planner_prompt.compact.txt` as the prompt source for each trial.
- The packet stays limited to `third_model` and the five stateful scenarios.

## Safety boundaries

- no model calls by Codex
- no browser or Playwright execution
- no external network access
- no GGUF modification
- no generated artifacts committed

## Notes

- The variance packet reuses the strict stateful planner packet/evaluator/materializer stack.
- It is a repeated-trials packaging layer, not a new runtime backend.

## Phase 13E4c guidance

- If the replay reports schema acceptance without workflow success, check whether the prompt is steering the model to the wrong fixture branch or whether the replay trace needs richer click-target diagnostics.
- Ticket-priority trials should point at the hardboard fixture route, not the ordinary ticket board page.
- Overview trials should use the ticket board page for navigation, then open the policy and team-status pages directly.
- Fact comparisons now accept a literal fixture span as long as the visible text still contains the expected evidence anchor.

## Phase 13E4d guidance

- Ticket-priority fact comparison now accepts case variations after punctuation trimming, so `urgent` and `Urgent` should compare equal when the visible fixture span matches.
- Final-answer citation diagnostics should keep the model-output `evidence_item_id` values visible when they are available, so the output ids can be checked directly alongside replay ids in deeper diagnostics.
- The ticket-priority prompt explicitly says to reopen the hardboard after Ticket 7 before continuing to Ticket 8; if a replay still walks straight from Ticket 7 to Ticket 8, the prompt is not yet aligned.

## Phase 13E4e guidance

- Policy-ticket prompting now explicitly anchors `policy_marker` to the exact visible Workspace Policy search marker text and warns against inventing admin approval or policy section language that is not on the fixture page.
- Ticket-priority prompting now explicitly anchors `ticket_8_requester_tier` to `office worker`, warns against using `general` unless it is visibly present, and reminds the model that Ticket 8 is a decoy whose visible facts still need to be copied exactly.
- These prompt changes are narrow anchoring fixes only; the evaluator still rejects hallucinated facts.

## Phase 13E4f guidance

- `missing_final_answer_text` now carries safe `final_answer_type` and `final_answer_keys` diagnostics when it appears, which keeps the false-rejection path auditable without relaxing validation.
- policy-ticket outputs with a real `final_answer.answer_text` are accepted; truly missing answer text still rejects.
- ticket-priority prompting now explicitly anchors `ticket_8_marker` to `decoy for the priority cross-check`, warns against `none`, and tells the model to copy the visible search-marker phrase from the Ticket 8 page.
- this remains fixture-backed, read-only, and does not add browser/Playwright execution from Codex

## Phase 13E4g guidance

- If `final_answer.answer_text` contains an allowed local fixture URL inside ordinary prose, it should now validate instead of surfacing as `missing_final_answer_text`.
- The validator still rejects truly missing or blank final answers and still blocks disallowed URL schemes or non-local hosts.
- A post-fix offline evaluator rerun on the captured 15-output packet accepted 15/15 by validation and reached 12/15 workflow success; the remaining policy-ticket failures are now honest fixture mismatches on `ticket_id`, not final-answer extraction failures.
- this remains fixture-backed, read-only, and does not add model/browser/Playwright execution from Codex

## Phase 13E4h guidance

- For `stateful_policy_ticket_crosscheck`, `ticket_id` must be copied exactly as `Ticket 1` from the visible `Ticket 1 - Quarterly Access Review` page/title.
- Do not use invented internal ids such as `TICKET-12345`; the evaluator still rejects those as `fact_value_mismatch`.
- Keep `ticket_topic` as `Quarterly Access Review`, copy priority/role from visible ticket text, and keep `policy_marker` exact.
- this remains fixture-backed, read-only, and does not add model/browser/Playwright execution from Codex

## Phase 13E4i guidance

- If `stateful_policy_ticket_crosscheck` still fails after the `ticket_id` anchor, check whether the model is putting `https://local.intranet/docs/policy` into `policy_anchor`.
- `policy_anchor` must be copied exactly as the visible title `Workspace Policy`; the URL belongs in `source_url` only and should not be normalized into the fact value by the evaluator.
- The evaluator remains strict: a policy URL in `policy_anchor` is still a `fact_value_mismatch`.
- this remains fixture-backed, read-only, and does not add model/browser/Playwright execution from Codex
