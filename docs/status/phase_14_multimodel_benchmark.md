# Phase 14 Multi-model Benchmark

## Summary

Phase 14 is an optional post-completion expansion for the already completed controlled read-only prototype.

It adds a reusable multi-model benchmark packet/evaluator for controlled stateful read-only planner scenarios. The packet prepares repeated request files for multiple configured model aliases, and the evaluator classifies captured outputs per model without launching models, browser, Playwright, Chromium, or a local server.

Phase 14E freezes the benchmark contract for broader raw comparisons:

- one shared task prompt per scenario
- one shared planner schema
- one shared offline evaluator/materializer path
- no model-specific prompt tuning
- no model-family adapters in the raw benchmark

Only technical runtime settings may vary per model alias, such as endpoint, port, context size, CPU/GPU launch mode, timeout, and whether the alias is enabled for a particular run.

Phase 14B records the first real operator-run result from that benchmark infrastructure. The model calls were manual operator runs against local endpoints for `second_model` and `third_model`. After capture, the evaluator remained offline, fixture-only, and read-only.

Phase 14C extends the optional benchmark registry/config layer so future post-completion comparisons can also include `fourth_model` and `fifth_model` without changing the original TZ completion status.

Phase 14E adds a frozen raw benchmark config, a broader model-neutral scenario set, and a sequential multi-model runner. The routine default frozen raw config compares `third_model` and `fourth_model`; `fifth_model` remains registered but is disabled by default because its observed runtime is too slow for routine benchmark runs.

Phase 14E repair hardens that sequential runner for a clean rerun:

- runner-owned start/stop is the default real-run mode
- exactly one large local model server should be active at a time
- benchmark-port preflight detects polluted benchmark ports before launch
- a shared larger output budget is applied equally across enabled models
- request failures are recorded as structured results instead of crashing the run

Phase 14F prepares the final presentation benchmark layer on top of that frozen raw methodology:

- five local aliases are registered for the presentation table
- the task contract remains frozen raw and model-neutral
- an 11-scenario difficulty ladder is added for a readable final comparison
- one ultra-easy sanity scenario is included as a model-neutral lower-bound schema/workflow check
- a dedicated summarizer can turn evaluator and sequential-run summaries into Markdown/CSV/JSON presentation tables
- no final presentation result is claimed until the operator performs the real model run

The operator has now completed that final presentation run. The result is presentation-grade benchmark evidence for this specific local fixture-only frozen raw setup, not a production-readiness claim.

Important framing for later phases: the Phase 14E/14F line is a frozen raw one-shot workflow-JSON planner benchmark. It is useful for controlled model comparison, but it is not the same thing as a high-confidence long-horizon interactive browser-agent benchmark.

In Phase 14, a single PASS/FAIL can mix several layers at once:

- raw JSON/schema validity
- action selection validity
- workflow materialization or evaluator checks
- final-answer correctness

That means a semantically reasonable answer can still miss a workflow PASS because the plan contains an invalid action such as clicking non-clickable text. Phase 15 therefore introduces a separate stepwise observation-action benchmark so semantic answer quality and interactive action validity can be measured more directly without changing the frozen raw Phase 14 methodology.

## What was added

- `src/agent/autonomous_browser_stateful_readonly_planner_multimodel_benchmark.py`
- `src/agent/autonomous_browser_stateful_readonly_planner_multimodel_sequential.py`
- `scripts/build_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_packet.py`
- `scripts/run_autonomous_browser_stateful_readonly_planner_multimodel_benchmark_evaluator.py`
- `scripts/run_autonomous_browser_stateful_readonly_planner_multimodel_sequential.py`
- `configs/autonomous_runtime/browser_stateful_readonly_planner_multimodel_benchmark.example.json`
- `configs/autonomous_runtime/browser_stateful_readonly_planner_multimodel_benchmark_extended.example.json`
- `configs/autonomous_runtime/browser_stateful_readonly_planner_frozen_raw_benchmark.example.json`
- `configs/autonomous_runtime/browser_stateful_readonly_planner_sequential_run.example.json`
- `configs/autonomous_runtime/browser_stateful_readonly_planner_final_presentation_benchmark.example.json`
- `configs/autonomous_runtime/browser_stateful_readonly_planner_final_presentation_sequential_run.example.json`
- `scripts/summarize_autonomous_browser_stateful_readonly_planner_final_benchmark.py`
- `src/agent/autonomous_browser_stateful_readonly_planner_final_summary.py`

## Optional benchmark candidates

- `fourth_model`
  - intended family: Mistral Small 3.2 24B Instruct 2506
  - quantization: `Q4_K_M`
  - local path: `models/gguf/fourth_model.gguf`
  - suggested local port: `8083`
  - role: strong non-Qwen challenger
- `first_model`
  - intended family: IBM Granite 3.3 8B Instruct
  - quantization: `Q4_K_M`
  - local path: `models/gguf/first_model.gguf`
  - suggested local port: `8081`
  - role: small/medium non-Qwen baseline
- `fifth_model`
  - intended family: Qwen3-30B-A3B-Instruct-2507
  - quantization: `Q4_K_M`
  - local path: `models/gguf/fifth_model.gguf`
  - suggested local port: `8084`
  - role: strong efficient MoE challenger

These are optional post-completion benchmark candidates only. No Phase 14 benchmark result is claimed for them yet.

`fifth_model` is kept in the registry for optional manual or slow-lane runs, but it is excluded from the default Phase 14E frozen raw benchmark config.

For Phase 14F final-presentation preparation, `first_model` and `fifth_model` are also included in a separate five-model presentation packet and sequential run config. `first_model` now represents IBM Granite 3.3 8B Instruct Q4_K_M for that presentation line; the earlier Phi-4-mini file was archived locally and was not committed. Their GGUF paths remain local-only and must not be committed.

## Frozen raw protocol

Phase 14E defines the preferred model-comparison protocol for this repository:

- compare models under one frozen task contract
- keep prompts model-neutral
- keep the planner schema fixed
- keep workflow evaluation fixed
- record technical launch/runtime differences separately

Out of scope for Phase 14E:

- prompt tuning for `fourth_model`, `fifth_model`, Mistral, Gemma, Qwen, or any other family
- adapter-specific system prompts
- profile-specific task wording changes intended to improve one model over another

If future work explores adapted prompts, that should be documented as a separate adapted/system benchmark rather than folded into the raw benchmark numbers.

Shared technical settings such as `max_tokens` are allowed in the frozen raw benchmark only when they are applied equally across enabled models. Phase 14E repair raises that shared output budget to `4096` for the default frozen raw packet so longer valid plans are not cut off asymmetrically.

## Packet behavior

- request layout is nested by `model_alias / scenario_id / trial_label`
- request count is `models_total x scenarios_total x trials_per_scenario`
- request/output paths remain relative
- packet generation is fixture-only and offline
- execution flags stay false:
  - `model_execution`
  - `real_browser_execution`
  - `playwright_execution`
  - `browser_opened`
- the extended example config uses 4 aliases over 5 scenarios x 3 trials = `60` packet requests
- the frozen raw example config uses 2 aliases over 8 broader fixture scenarios = `16` packet requests

## Frozen raw scenario set

The broader Phase 14E frozen raw scenario catalog keeps the benchmark fixture-only and deterministic while covering more task shapes than the original five-scenario stateful suite.

The current frozen raw catalog includes:

- the original five stateful read-only scenarios
- a policy-source disambiguation scenario
- an approval-queue absence review scenario
- a priority exception-rule review scenario

Those additions broaden the benchmark toward:

- multi-source cross-checking
- negative or absence-based answers
- repeated-ID disambiguation
- exact anchor/rule citation
- read-only trap rejection through workflow validation
- two-page fact digestion

The frozen raw request contract is shared across enabled aliases; only model alias selection and runtime metadata differ.

## Final presentation scenario ladder

Phase 14F adds a separate `final_presentation_v1` catalog for a bounded presentation table:

- `11` deterministic fixture-only scenarios
- `5` model aliases
- `1` trial per scenario by default
- `55` total requests in the packet

The ladder is intentionally mixed rather than uniformly hard:

- one ultra-easy single-fact sanity check
- easy exact-fact and single-page policy lookups
- medium digest, absence, numeric-comparison, and repeated-id tasks
- hard conflicting-source, trap-text, and exception-rule tasks
- one very hard composite approval workflow

This presentation ladder still uses:

- one shared prompt contract
- one shared schema
- one shared offline evaluator path
- no model-specific prompt tuning

The ultra-easy sanity scenario is intentionally model-neutral. It does not add model-specific prompt tuning; it only establishes the lower bound for whether an alias can follow the frozen raw contract, open one fixture page, and return one exact visible fact.

The `first_model` replacement from Phi-4-mini to Granite 3.3 8B Instruct is also not prompt tuning. The packet, scenario catalog, evaluator, and frozen raw methodology remain unchanged; only the local baseline model identity for the `first_model` alias changed. Because of that replacement, the final five-model presentation benchmark should be rerun before treating the presentation table as current.

It exists to make the final table interpretable, not to hide weak models. If a model fails every scenario, that should be reported honestly.

## Sequential runner

Phase 14E also adds a sequential runner for captured packet execution against local model endpoints without manual alias switching.

The sequential runner:

- reads an existing packet directory
- reads model runtime profiles from config
- can run only enabled aliases
- can optionally start one local server at a time
- waits for `/v1/models` readiness
- saves `response.json`, `raw_planner_output.txt`, and `per_request_timing.json`
- supports `--skip-existing`
- supports `--no-start-servers`
- supports `--models third_model,fourth_model`
- supports `--allow-existing-benchmark-servers`
- supports `--stop-existing-benchmark-servers`
- emits a structured run summary

Runner server semantics are now explicit:

- `dry_run` => `server_mode: dry_run`
- `--no-start-servers` => `server_mode: existing_servers`
- default real run => `server_mode: started_by_runner`

The runner does not launch browser automation, Playwright, Chromium, or local fixture servers. In dry-run mode it also avoids model calls and server startup.

If a request times out, the endpoint is unavailable, or the response shape is malformed, the runner now records a structured failed request and continues by default. `fail_fast` is optional and off by default.

Before a real runner-owned start, the benchmark-port preflight checks configured benchmark ports. The safe default is:

- do not kill anything automatically
- fail cleanly if selected benchmark ports are already occupied
- fail cleanly if other configured benchmark ports are occupied and could pollute resource conditions

Operators can override that deliberately with:

- `--allow-existing-benchmark-servers`
- `--stop-existing-benchmark-servers`

## Evaluator behavior

The evaluator keeps per-model and combined metrics separate:

- `outputs_present` vs `outputs_missing`
- `validation_accepted` vs `validation_rejected`
- `workflows_succeeded` vs `workflows_failed`
- `pass_rate_overall`
- `validation_acceptance_rate`
- deterministic `best_model_by_pass_rate`
- `fully_successful_models`
- `missing_output_models`

Missing outputs are reported as structured benchmark results, not tracebacks.

## Phase 14B first real result

### Top-level result

- `status: completed_with_failures`
- `error_code: fixture_resolution_failed`
- `models_total: 2`
- `best_model_by_pass_rate: third_model`
- `fully_successful_models: ["third_model"]`
- `missing_output_models: {}`
- `no_runtime_execution: true`
- `fixture_only: true`
- `model_execution: false`
- `real_browser_execution: false`
- `playwright_execution: false`
- `browser_opened: false`

This is the first real captured benchmark result for the optional Phase 14 comparison layer. It shows a clear separation between the stronger final planner candidate and the weaker baseline without changing prompts or relaxing the evaluator.

## Preliminary Phase 14E note

An early frozen raw Phase 14E operator run produced a preliminary comparative signal with `fourth_model` leading that particular run. That result is intentionally not treated as final benchmark evidence because the runtime state was polluted:

- multiple manually started `llama-server` processes were active across benchmark ports
- the sequential runner did not own the server lifecycle in that run
- output truncation was visible through frequent `finish_reason: length`, especially for `third_model`

After the Phase 14E repair, a clean rerun should use:

- one large model server at a time
- runner-owned start/stop by default
- shared `max_tokens: 4096`
- structured timeout/connection/response failures

Only a rerun under that cleaner protocol should be used as the routine frozen raw benchmark reference.

## Final presentation summary tooling

Phase 14F also adds a bounded summarizer for the future five-model operator run:

- input: evaluator summary, optional sequential runner summary, and optional packet manifest
- output: Markdown, CSV, and JSON under `artifacts/autonomous_runtime_planner_summaries/final_presentation_benchmark_tables`
- table columns include validation/workflow counts, finish/failure counters, elapsed timing when available, and compact model-role notes
- the Markdown output also includes a scenario matrix with `PASS`, `FAIL`, `REJECTED`, and `MISSING`

That summarizer remains offline and does not launch models, browser automation, Playwright, Chromium, or local servers.

## Final Phase 14F presentation result

The final presentation benchmark used:

- fixture-only workflow evaluation
- frozen raw methodology
- no model-specific prompt tuning
- one shared prompt/schema/evaluator contract
- shared `max_tokens: 4096`
- `5` local model aliases
- `11` deterministic scenarios
- one mixed difficulty ladder: `ultra_easy`, `easy`, `medium`, `hard`, `very_hard`

This final presentation table should still be read as a frozen raw one-shot planner benchmark. It does not by itself establish long-horizon interactive browser-agent competence.

### Top-level evaluator summary

- `status: completed_with_failures`
- `error_code: browser_click_target_not_found`
- `models_total: 5`
- `best_model_by_pass_rate: fourth_model`
- `fully_successful_models: []`
- `missing_output_models: []`
- `model_execution: false`
- `real_browser_execution: false`
- `playwright_execution: false`
- `browser_opened: false`
- `no_runtime_execution: true`
- `fixture_only: true`

The evaluator remained offline after capture, so this result adds no browser or Playwright evidence.

### Final model table

| model_alias | label | role | outputs_present | validation_accepted | validation_rejected | workflows_succeeded | workflows_failed | pass_rate_overall | validation_acceptance_rate | finish_reason_stop | finish_reason_length | failure_model_failed_task |
| --- | --- | --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `first_model` | IBM Granite 3.3 8B Instruct Q4_K_M | small/medium non-Qwen baseline | 11 | 9 | 2 | 1 | 10 | 0.091 | 0.818 | 11 | 0 | 10 |
| `second_model` | Qwen2.5-3B-Instruct Q4_K_M | weak Qwen baseline | 11 | 7 | 4 | 1 | 10 | 0.091 | 0.636 | 11 | 0 | 10 |
| `third_model` | Qwen3-14B Q5_K_M | strong historical Qwen planner | 11 | 9 | 2 | 5 | 6 | 0.455 | 0.818 | 10 | 1 | 6 |
| `fourth_model` | Mistral Small 3.2 24B Instruct Q4_K_M | strong non-Qwen challenger | 11 | 11 | 0 | 5 | 6 | 0.455 | 1.000 | 11 | 0 | 6 |
| `fifth_model` | Qwen3-30B-A3B-Instruct-2507 Q4_K_M | strong efficient MoE challenger | 11 | 11 | 0 | 3 | 8 | 0.273 | 1.000 | 11 | 0 | 8 |

### Final scenario matrix

| scenario_id | difficulty | category | fourth_model | third_model | fifth_model | first_model | second_model |
| --- | --- | --- | --- | --- | --- | --- | --- |
| `stateful_single_fact_sanity_check` | ultra_easy | sanity | FAIL | PASS | PASS | FAIL | FAIL |
| `stateful_policy_search_marker_review` | easy | A | PASS | FAIL | FAIL | FAIL | FAIL |
| `stateful_policy_allowed_activity` | easy | B | FAIL | FAIL | FAIL | REJECTED | REJECTED |
| `stateful_policy_ticket_crosscheck` | medium | C | PASS | PASS | PASS | PASS | REJECTED |
| `stateful_approval_queue_absence_review` | medium | D | PASS | PASS | FAIL | FAIL | FAIL |
| `stateful_ticket_priority_digest` | medium | E | PASS | PASS | PASS | FAIL | FAIL |
| `stateful_approval_id_review` | medium | F | FAIL | REJECTED | FAIL | REJECTED | REJECTED |
| `stateful_policy_source_disambiguation` | hard | G | FAIL | FAIL | FAIL | FAIL | REJECTED |
| `stateful_policy_trap_review` | hard | H | FAIL | FAIL | FAIL | FAIL | FAIL |
| `stateful_priority_exception_rule_review` | hard | I | FAIL | PASS | FAIL | FAIL | FAIL |
| `stateful_approval_policy_crosscheck` | very_hard | J | PASS | REJECTED | FAIL | FAIL | PASS |

### Interpretation

- `fourth_model` and `third_model` tied on completed workflows at `5/11` each.
- `fourth_model` ranked first because it paired that workflow count with perfect validation acceptance: `11/11` accepted, `0` rejected, and no length-limited outputs.
- `third_model` also reached `5/11`, but with `9/11` validation acceptance, `2` rejected outputs, and `1` length-limited output.
- `fifth_model` had perfect validation acceptance but lower workflow completion at `3/11`.
- `first_model` and `second_model` both completed `1/11`, which keeps them useful as lower presentation baselines rather than zero-pass rows.
- Every model passed at least one scenario.
- No model passed all scenarios.
- The harder scenarios create visible separation without changing prompts per model.

### Caveats

- This does not mean `fourth_model` is universally better. It means `fourth_model` ranked first in this specific local frozen raw fixture-only agent-planning benchmark.
- The result stays bounded by the shared prompt/schema/evaluator contract and shared `max_tokens: 4096`.
- No model-specific prompt tuning was introduced.
- The final evaluator `error_code` remained `browser_click_target_not_found`, so the run is still recorded as `completed_with_failures`.
- That failure mode matters for interpretation: this benchmark line mixes semantic-answer quality with action-validity and workflow-evaluator outcomes, so a model can be partly right on task semantics and still miss a workflow PASS because of an invalid action step.
- Generated summary tables and captured outputs are operator evidence only and must not be committed.

## Clean Phase 14E frozen raw result

After the Phase 14E runner repair, the operator completed a clean frozen raw rerun with:

- old `llama-server` processes stopped before the benchmark
- packet rebuilt with shared `max_tokens: 4096`
- runner-owned lifecycle
- no `--dry-run`
- no `--no-start-servers`
- `fifth_model` still excluded from the default frozen raw config

### Clean sequential runner summary

- `status: succeeded`
- `server_mode: started_by_runner`
- `start_servers: true`
- `dry_run: false`
- `model_execution: true`
- `models_total: 2`
- `models_attempted: 2`
- `models_completed: 2`
- `models_failed: 0`
- `requests_total: 16`
- `requests_completed: 16`
- `requests_failed: 0`

This confirms that the clean routine Phase 14E runner path completed end to end for the default frozen raw packet with one benchmark model active at a time.

### Clean evaluator summary

- `status: completed_with_failures`
- `error_code: truncated_model_output`
- `models_total: 2`
- `best_model_by_pass_rate: fourth_model`
- `fully_successful_models: []`
- `missing_output_models: []`
- `model_execution: false`
- `real_browser_execution: false`
- `playwright_execution: false`
- `browser_opened: false`
- `no_runtime_execution: true`
- `fixture_only: true`

The evaluator remains offline and fixture-only after capture, so the clean rerun does not add browser or Playwright evidence.

### Clean per-model metrics

#### `third_model`

- `outputs_total: 8`
- `outputs_present: 8`
- `outputs_missing: 0`
- `outputs_ingested: 7`
- `outputs_rejected: 1`
- `validation_accepted: 7`
- `validation_rejected: 1`
- `workflows_succeeded: 5`
- `workflows_failed: 3`
- `pass_rate_overall: 0.625`
- `validation_acceptance_rate: 0.875`
- `finish_reason_counts: {"length": 1, "stop": 7}`
- `failure_class_counts: {"model_failed_task": 3, "none": 5}`

#### `fourth_model`

- `outputs_total: 8`
- `outputs_present: 8`
- `outputs_missing: 0`
- `outputs_ingested: 8`
- `outputs_rejected: 0`
- `validation_accepted: 8`
- `validation_rejected: 0`
- `workflows_succeeded: 6`
- `workflows_failed: 2`
- `pass_rate_overall: 0.750`
- `validation_acceptance_rate: 1.0`
- `finish_reason_counts: {"stop": 8}`
- `failure_class_counts: {"model_failed_task": 2, "none": 6}`

## Clean-result interpretation

In the clean Phase 14E frozen raw benchmark, `fourth_model` led `third_model` on this bounded fixture-only benchmark:

- `fourth_model`: `6/8` workflows succeeded
- `third_model`: `5/8` workflows succeeded

That is not a universal model-quality claim. It means `fourth_model` performed better under this specific frozen raw benchmark:

- shared prompt contract
- shared planner schema
- shared evaluator
- shared `max_tokens: 4096`
- no model-specific prompt tuning

The evaluator still reports `completed_with_failures` because:

- `third_model` had one length-limited output
- both models still had workflow failures

This clean result supersedes the earlier polluted Phase 14E preliminary run. It does not supersede the earlier Phase 14B or later compatibility-oriented post-completion evidence; it is a separate frozen raw benchmark line.

### Per-model metrics

#### `second_model`

- `model_path: models/gguf/second_model.gguf`
- `outputs_total: 15`
- `outputs_present: 15`
- `outputs_missing: 0`
- `outputs_ingested: 12`
- `outputs_rejected: 3`
- `validation_accepted: 12`
- `validation_rejected: 3`
- `workflows_succeeded: 0`
- `workflows_failed: 15`
- `pass_rate_overall: 0.0`
- `validation_acceptance_rate: 0.8`
- `finish_reason_counts: {"stop": 15}`
- `failure_class_counts: {"model_failed_task": 15}`

#### `third_model`

- `model_path: models/gguf/third_model.gguf`
- `outputs_total: 15`
- `outputs_present: 15`
- `outputs_missing: 0`
- `outputs_ingested: 15`
- `outputs_rejected: 0`
- `validation_accepted: 15`
- `validation_rejected: 0`
- `workflows_succeeded: 15`
- `workflows_failed: 0`
- `pass_rate_overall: 1.0`
- `validation_acceptance_rate: 1.0`
- `finish_reason_counts: {"stop": 15}`
- `failure_class_counts: {"none": 15}`

## Qualitative interpretation

### `second_model`

`second_model` remains a useful baseline, but this first real Phase 14B benchmark shows that it is not reliable enough for the final stateful read-only planner role.

Observed weaknesses from the captured outputs:

- it often emits schema-shaped JSON without preserving the full required route/action structure
- `stateful_approval_policy_crosscheck` outputs sometimes collapsed to a single action where the workflow expected a multi-step route
- `stateful_policy_search_marker_review` used placeholder-like fact values such as `workspace_policy_anchor` and `workspace_policy_marker` instead of visible fixture text
- `stateful_ticket_priority_digest` sometimes produced incomplete facts or wrong marker/source-step assignments
- `stateful_policy_ticket_crosscheck` was closer after previous prompt hardening, but it still did not complete the full workflow set successfully

This note is comparative only. Phase 14B does not tune prompts to make `second_model` pass, and it does not relax the evaluator.

### `third_model`

`third_model` produced the first fully successful real benchmark result for this post-completion comparison layer:

- all 15 captured outputs were present
- all 15 were validation-accepted
- all 15 workflows succeeded
- pass rate was `1.0`

That result is still controlled, fixture-only, and offline after capture. It is evidence of stronger repeated read-only planning in this bounded benchmark, not a production-readiness claim.

## Operator note

- In PowerShell, per-model summaries use the field name `alias`, not `model_alias`.
- Example inspection command:

```powershell
Get-Content artifacts\autonomous_runtime_planner_summaries\stateful_readonly_planner_multimodel_benchmark\benchmark_evaluator_summary.json -Raw |
  ConvertFrom-Json |
  Select-Object -ExpandProperty model_summaries |
  Select-Object alias, outputs_total, outputs_present, validation_accepted, workflows_succeeded, pass_rate_overall
```

- This is a docs note only. The evaluator schema is not changed here.

## Scope and limits

- optional post-completion research expansion only
- does not change the final TZ completion claim
- does not launch models from Codex
- routine Phase 14E comparisons prefer the frozen raw shared-contract benchmark
- the clean runner-owned rerun is now the meaningful Phase 14E reference point
- does not execute browser actions
- does not add new real browser or Playwright evidence
- does not claim production readiness
- `fifth_model` remains optional/manual and is excluded from the routine frozen raw default because of observed slowness
- GGUF files are local-only artifacts and must not be committed
- generated packet/output artifacts remain operator evidence and must not be committed

## Recommended use

Use this benchmark layer when comparing repeated captured stateful planner outputs across multiple local aliases while keeping the workflow offline, fixture-backed, and read-only.

If resource pressure is high, run the larger benchmark candidates one at a time and compare them through the Phase 14 harness rather than trying to keep all local model servers active simultaneously.
