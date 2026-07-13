# Phase 15 Stepwise Article Benchmark

## Summary

Phase 15 starts a separate fixture-only benchmark line for stepwise article and browser-style tasks.

Unlike the frozen raw Phase 14 planner benchmark, this line evaluates a repeated loop:

- task plus observation
- one model action JSON
- fixture execution
- next observation
- final answer

Phase 15A added the deterministic offline foundation with scripted fake models only.

Phase 15B adds a guarded local-model adapter for that same stepwise benchmark:

- one action JSON per step
- OpenAI-style local `/v1/chat/completions` compatibility
- explicit parser rejection for full workflows and unsupported actions
- explicit rejection for `browser_click` in the default article benchmark
- opt-in real model execution only with `--allow-model-execution`
- failure artifacts now write to `--output-json` even for refusal and parse-failure outcomes
- runtime flags now distinguish refused/offline runs from real model-call attempts that fail during parsing
- parse failures now carry bounded diagnostics such as scenario/trial/step identifiers, parse error class, finish reason, response id, and a capped safe response preview
- some thinking-model adapters need an explicit no-think action-json protocol mode so the next-step action lands in `message.content`
- Phase 15B now supports `disable_thinking` plus a configurable `/no_think`-style prefix as protocol control rather than scenario-specific answer tuning
- article-reading scenarios now expose fixture start URLs and allowed fixture article URLs in the observation
- the benchmark now tests reading a provided fixture article rather than guessing a hidden URL
- final-answer scoring now separates exact answer matching from semantic factual correctness: a full-sentence answer can pass when it contains the required fact and cites the correct fixture section
- redundant valid actions now produce explicit observation feedback with section-read progress, unread-section counts, and generic anti-loop guidance

## Why it exists

Phase 14 is still useful for controlled model comparison, but it is a frozen raw one-shot workflow-JSON planner benchmark. A single PASS/FAIL there can combine:

- JSON/schema validity
- action validity
- workflow materialization
- final-answer correctness

Phase 15 separates those layers more clearly by measuring one interactive step at a time.

That separation matters for guarded local-model smoke runs: a run can fail before any scenario-level correctness judgment if the model does not return one valid step JSON object. Those are protocol/format failures, not article-reading failures, and should be diagnosed separately.

For Qwen3-style thinking models in particular, `message.reasoning_content` may hold chain-of-thought while `message.content` stays empty unless thinking is disabled. The stepwise adapter now supports an explicit no-think/action-json mode for these control loops, but it still parses actions only from `message.content`, not from `reasoning_content`.

The same principle applies to fixture URLs: the benchmark now exposes allowed local article URLs directly in the observation, analogous to a user giving the article link. Unknown URL attempts are treated as environment/action failures rather than as reading failures.

The same separation applies to answer scoring. `answer_exact_match` remains a diagnostic for short expected-answer strings, while `semantic_answer_correct` and `answer_contains_required_fact` determine whether a semantically correct full-sentence response can pass. A run still needs the correct citation and valid stepwise workflow; semantic answer acceptance does not forgive wrong citations, hallucinated facts, missing required facts, invalid actions, or early stopping.

The medium two-fact smoke exposed a different long-horizon control issue: a model could open the article and read one relevant section, then repeat the same valid `browser_extract_section` action without progressing to the unread section. Phase 15 now reports that as redundant-action feedback rather than treating it as a parser, URL, or browser problem. Repeated valid redundant actions are separate from invalid actions, and three consecutive identical redundant actions stop with `repeated_redundant_action_loop` instead of spending the remaining budget until `max_steps_exceeded`.

This repair is generic control-loop feedback. It reports progress such as sections read, unread section count, and whether the last action observed new text; it does not reveal answer facts, add scenario-specific answer hints, or tune behavior for one model.

## Safety boundaries

- fixture-only article environment
- no real browser execution
- no Playwright
- no Chromium
- no local server required for the benchmark fixture
- no `browser_click` in the default article action set
- local model execution is guarded and opt-in only
- safe diagnostics redact obvious authorization/token-like material from failure previews
- benchmark reports should state whether `disable_thinking` was enabled, because it is part of the response protocol setup
- benchmark prompts now instruct `browser_open_url` to use only the exposed fixture article URLs and not invent external URLs
- redundant-action diagnostics are fixture-only progress signals and do not require a browser, Playwright, Chromium, or local server

## Current scope

Default action set:

- `browser_open_url`
- `browser_read_visible_text`
- `browser_scroll_down`
- `browser_find_text`
- `browser_extract_section`
- `final_answer`

Default deterministic scenarios:

- `article_short_single_fact`
- `article_medium_two_fact_cross_section`
- `article_long_multi_section_summary`
- `article_negative_absence_check`
- `article_similar_terms_disambiguation`

## Limitations

- not production browser automation
- not general web browsing
- no real browser click/navigation behavior in the default article benchmark
- local model calls remain operator-gated
- still a controlled research prototype
- real Phase 15B smoke attempts can still fail at the one-action JSON protocol layer before scenario evaluation completes
- `disable_thinking` is a protocol setting for stepwise control, not per-scenario prompt tuning and not a production-readiness claim
- unknown fixture URL failures are classified as environment/action failures even when the rest of the stepwise protocol is working
- repeated redundant valid actions are classified as control-loop failures, not evidence of real-browser behavior
