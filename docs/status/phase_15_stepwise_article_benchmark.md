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

## Why it exists

Phase 14 is still useful for controlled model comparison, but it is a frozen raw one-shot workflow-JSON planner benchmark. A single PASS/FAIL there can combine:

- JSON/schema validity
- action validity
- workflow materialization
- final-answer correctness

Phase 15 separates those layers more clearly by measuring one interactive step at a time.

That separation matters for guarded local-model smoke runs: a run can fail before any scenario-level correctness judgment if the model does not return one valid step JSON object. Those are protocol/format failures, not article-reading failures, and should be diagnosed separately.

## Safety boundaries

- fixture-only article environment
- no real browser execution
- no Playwright
- no Chromium
- no local server required for the benchmark fixture
- no `browser_click` in the default article action set
- local model execution is guarded and opt-in only
- safe diagnostics redact obvious authorization/token-like material from failure previews

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
