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
