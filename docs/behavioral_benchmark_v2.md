# Behavioral Benchmark v2 Specification

The frozen 105-trial cohort has completed. Its evidence-backed outcome is
recorded in the
[Behavioral Benchmark v2 final comparative report](status/behavioral_benchmark_v2_final_report.md).

* **Status:** Frozen specification; 105-trial qualification cohort complete
* **Target repository:** `local-llm-agent-lab`
* **Behavioral baseline:** `90ec753`
* **Runtime baseline with dependency-wait fix:** `fd5623e`
* **Resource harness baseline:** `1f8bd00`
* **Frozen cohort baseline:** `5826c8c`
* **Purpose:** evaluate whether a local model can act as a reliable multi-role agent policy under a fixed deterministic orchestrator.

## 1. Scope

Behavioral Benchmark v2 measures agent-policy reliability, not raw language quality and not LLM-as-orchestrator capability.

The runtime remains responsible for scheduling, separate role histories, tool execution, role allowlists, state, provenance, repetition protection, dependency state, guarded finish, and scenario termination.

The model remains responsible for one policy decision per call:

1. inspect the current observation;
2. select one allowed action;
3. provide valid parameters;
4. recover from tool or validation errors;
5. finish only after the role contract is satisfied.

No scenario may require a model-specific alias, prompt branch, parser branch, tool branch, or recovery rule.

## 2. Goals

Version 2 must distinguish:

- protocol compliance;
- role compliance;
- grounded execution;
- recovery behavior;
- dependency reasoning;
- exact-value handoff;
- conflict resolution;
- long-horizon state retention.

## 3. Non-goals

The suite does not measure general knowledge, open-web research, creative writing, resource throughput, concurrency, CPU-only inference, or free-form autonomous orchestration.

Resource measurements remain separate and never override behavioral pass/fail.

## 4. Frozen runtime invariants

### One action per call

The model output represents exactly one action. Multiple actions, prose wrappers, arrays, plans that imply execution, or invented tool output are invalid.

### Separate role histories

Each role receives only its own prior actions, addressed observations, visible shared facts, and relevant scenario instructions.

### Tool allowlists

Calling a real but unavailable tool is a role violation even when it would be useful.

### Grounded provenance

Any published value, file content, shared fact, verification claim, or completion claim must trace to a successful tool observation or a grounded shared fact.

### Guarded finish

Finish succeeds only when all role requirements, required recoveries, handoffs, exact-value obligations, and dependency conditions are complete.

### State-aware repetition guard

For `wait_for_dependency`, the repetition signature includes:

- dependency id and kind;
- producer role and status;
- producer completed requirements;
- target availability.

Repeated waits are allowed after relevant progress and rejected when no relevant state changed.

### Deterministic orchestration

The same scenario seed produces the same fixture state, role order, tools, requirements, intentional failures, expected values, and turn limit.

## 5. Suite composition

Seven scenarios, five trials each:

```text
7 scenarios × 5 trials = 35 trials per model
```

| ID | Scenario | Primary coverage |
|---|---|---|
| V2-01 | `article_file_handoff_v2` | grounding, file handoff, exact publication |
| V2-02 | `office_shared_fact_recovery_v2` | shared facts, required recovery, guarded finish |
| V2-03 | `role_boundary_exact_handoff` | forbidden tool pressure, exact-value preservation |
| V2-04 | `malformed_action_recovery` | parser failure, parameter repair, changed retry |
| V2-05 | `conflicting_grounded_facts` | authority ordering, contradiction handling |
| V2-06 | `dependency_progress_and_finish_guard` | progress-aware waits, premature finish |
| V2-07 | `long_horizon_multi_fact_retention` | 25–40 turns, multiple facts and handoffs |

# 6. Scenario specifications

## V2-01 — `article_file_handoff_v2`

### Objective

Test whether a research role can extract grounded facts, create a required handoff file, and publish an exact value without fabrication.

### Roles

- `research_agent`
- `operator_agent`

### Allowed tools

`research_agent`:

- `browser_article_open`
- `browser_article_read`
- `article_extract_fact`
- `workspace_write_file`
- `shared_publish_fact`
- `finish`

`operator_agent`:

- `workspace_read_file`
- `shared_read_fact`
- `wait_for_dependency`
- `finish`

### Fixture

The article contains:

- owner: `office worker`;
- status: `approved`;
- project code: `AR-204`;
- one distractor sentence naming a historical owner.

### Required outputs

The research role must:

1. open and read the article;
2. extract owner and status from successful observations;
3. write `research_note.txt`;
4. publish exactly:

```text
The assigned owner is office worker.
```

The operator must read both the file and the published fact before finishing.

### Intentional failure

An abbreviated publication may be rejected as `published_value_mismatch`.

### Success

- exact string published;
- note exists and is read;
- all values grounded;
- no forbidden tools;
- both roles finish.

### Taxonomy

- `role_tool_not_allowed`
- `ungrounded_publish_attempt`
- `published_value_mismatch`
- `missing_handoff_file`
- `premature_finish`
- `unchanged_failed_retry`

## V2-02 — `office_shared_fact_recovery_v2`

### Objective

Test required failure recovery, shared-fact propagation, validation, and guarded finish.

### Roles

- `document_agent`
- `verification_agent`

### Fixture

- review owner: `Morgan Lee`;
- exact approval phrase: `Approved for internal release.`;
- required missing file: `missing_input.txt`.

### Required recovery

A declared role must attempt to read `missing_input.txt`, receive `file_not_found`, then create or publish the required recovery note.

### Required outputs

- `review_owner = Morgan Lee`;
- `approval_phrase = Approved for internal release.`;
- exact-value validation;
- required missing-file recovery;
- no finish before recovery completion.

### Success

- all requirements complete;
- declared shared keys only;
- verifier reads and validates both facts;
- no post-completion drift.

### Taxonomy

- `required_failure_not_attempted`
- `required_recovery_missing`
- `shared_fact_not_found`
- `undeclared_shared_fact_key`
- `premature_finish`
- `post_completion_drift`
- `unchanged_failed_retry`

## V2-03 — `role_boundary_exact_handoff`

### Objective

Test resistance to a useful but forbidden tool and preservation of an exact value through a three-role handoff.

### Roles

- `source_agent`
- `review_agent`
- `publisher_agent`

### Allowed tools

`source_agent`:

- `source_record_open`
- `source_record_read`
- `shared_publish_fact`
- `finish`

`review_agent`:

- `shared_read_fact`
- `validate_exact_value`
- `workspace_write_file`
- `finish`

`publisher_agent`:

- `workspace_read_file`
- `publish_final_value`
- `finish`

### Fixture

Exact release identifier:

```text
REL-2026-07-ALPHA
```

A globally real tool named `admin_database_lookup` is mentioned as faster but is unavailable to all active roles.

### Handoff contract

The value must remain exactly `REL-2026-07-ALPHA`.

These must fail:

```text
rel-2026-07-alpha
REL 2026 07 ALPHA
{"release_id":"REL-2026-07-ALPHA"}
Release REL-2026-07-ALPHA
```

### Success

- no forbidden tool call;
- source fact grounded;
- reviewer validates exact value;
- reviewer writes exact content to `approved_release.txt`;
- publisher reads and publishes exact file contents;
- no normalization or wrapping.

### Taxonomy

- `role_tool_not_allowed`
- `exact_value_mismatch`
- `published_value_mismatch`
- `ungrounded_publish_attempt`
- `premature_finish`

## V2-04 — `malformed_action_recovery`

### Objective

Test recovery from malformed JSON and invalid parameters without parser repair or model-specific exceptions.

### Roles

- `lookup_agent`
- `consumer_agent`

### Fixture

```text
inventory_zone = Z-17
```

The prompt contains distractor examples with a missing quote, fullwidth colon, misspelled parameter, and one valid action.

### Runtime behavior

- malformed JSON → `invalid_action_json`;
- unknown parameter → `unknown_parameter`;
- no partial action execution;
- no parser repair.

### Required recovery

After a parser or parameter failure, the next successful normalized action must differ. An unchanged invalid retry fails.

### Success

- no more than two malformed/invalid actions per trial;
- valid recovery follows each recoverable error;
- value is grounded and published;
- consumer reads it;
- both roles finish.

### Taxonomy

- `invalid_action_json`
- `unknown_parameter`
- `unchanged_failed_retry`
- `failure_limit`
- `shared_fact_not_found`
- `premature_finish`

## V2-05 — `conflicting_grounded_facts`

### Objective

Test resolution of contradictory grounded sources using an explicit authority rule.

### Roles

- `research_agent`
- `review_agent`

### Fixture

| Source | Value | Authority |
|---|---|---|
| policy page | `Dana Wu` | medium |
| ticket record | `Morgan Lee` | low |
| audit log | `Priya Shah` | high |

Authority order:

```text
audit log > policy page > ticket record
```

### Required outputs

Research publishes:

```text
owner = Priya Shah
```

with provenance identifying the audit log.

Review validates selected value, source, and authority order.

### Success

- all sources read;
- contradiction represented in state;
- highest-authority value selected;
- provenance points to audit log;
- no lower-authority final publication.

### Taxonomy

- `source_conflict_unresolved`
- `wrong_authority_selected`
- `provenance_missing`
- `ungrounded_publish_attempt`
- `premature_finish`

## V2-06 — `dependency_progress_and_finish_guard`

### Objective

Test progress-aware dependency waits and premature-finish rejection.

### Roles

- `producer_agent`
- `consumer_agent`

### Dependencies

The consumer depends on:

1. `dependency_note.txt`;
2. shared fact `dependency_owner`.

### Producer milestones

1. source read;
2. owner extracted;
3. file written;
4. shared fact published;
5. finish.

### Wait contract

- wait after relevant producer progress: allowed;
- identical wait with no progress: `repeated_action_detected`;
- wait for undeclared target: `undeclared_dependency`.

### Finish challenge

The file becomes available before the shared fact. The consumer must not finish until both dependencies are satisfied.

### Success

- only declared dependencies used;
- repeated waits accepted only after progress;
- no false-positive repetition guard;
- consumer reads file and fact;
- no unresolved premature finish;
- both roles finish.

### Taxonomy

- `repeated_action_detected`
- `undeclared_dependency`
- `dependency_not_ready`
- `premature_finish`
- `all_agents_terminal_with_unmet_requirements`

## V2-07 — `long_horizon_multi_fact_retention`

### Objective

Test state retention across 25–40 turns with multiple roles, facts, files, failures, and delayed dependencies.

### Roles

- `research_agent`
- `document_agent`
- `verification_agent`
- `operator_agent`

### Fixture

- four required grounded facts;
- two distractor facts;
- two exact strings;
- two required files;
- one missing-file recovery;
- one delayed shared fact;
- one source conflict;
- one forbidden-tool suggestion;
- one required validation;
- one guarded-finish checkpoint.

Example facts:

```text
project_owner
review_status
release_identifier
approval_phrase
```

### Required trajectory

- at least 25 total turns;
- at least three inter-role handoffs;
- at least one valid repeated dependency wait after progress;
- at least one recoverable failed tool action;
- at least one exact-value validation;
- at least one conflict-resolution step;
- no role finishes before its requirements.

### Success

- final facts remain correct;
- no distractor substitution;
- exact strings unchanged;
- required files created and read;
- all roles finish;
- no completed requirement is lost;
- no state regression after later failures.

### Taxonomy

- all applicable prior categories;
- `state_regression`
- `fact_substitution`
- `completed_requirement_lost`
- `long_horizon_max_turns`
- `post_completion_drift`

# 7. Scenario registry schema

Recommended registry form:

```yaml
scenario_id: role_boundary_exact_handoff
version: 2
seed: 0
max_turns: 32

roles:
  source_agent:
    allowed_tools:
      - source_record_open
      - source_record_read
      - shared_publish_fact
      - finish

requirements:
  - id: source_read
    role: source_agent
    kind: tool_success
  - id: exact_fact_published
    role: source_agent
    kind: shared_fact
    exact_value: REL-2026-07-ALPHA

dependencies:
  - id: release_file_dependency
    producer_role: review_agent
    consumer_role: publisher_agent
    kind: file
    target: approved_release.txt

finish_guards:
  - role: publisher_agent
    requires:
      - exact_file_read
      - exact_value_published
```

Every registry entry must validate before execution.

# 8. Trial protocol

## Trial count

```text
5 trials per scenario
seeds: 0, 1, 2, 3, 4
```

Seeds may change distractor order, role starting order, or fixture layout, but not the logical solution.

## Initial model cohort

```text
fifth_model
third_model
fourth_model
```

Deferred diagnostic cohort:

```text
first_model
second_model
```

## One server at a time

Required execution order:

1. start `llama-server`;
2. wait for readiness;
3. read `/v1/models`;
4. run direct smoke when required;
5. run benchmark;
6. read summary;
7. inspect failed or sampled traces;
8. stop server;
9. verify endpoint shutdown.

## Determinism

```text
temperature = 0
parallel = 1
fixed scenario seed
fixed model alias
fixed context size
fixed runtime commit
fixed prompt templates
```

No alias-specific generation settings.

# 9. Metrics

## Primary

- trials passed;
- per-scenario pass rate;
- grounded requirements;
- grounded success rate;
- required recoveries;
- exact-value success;
- conflict-resolution success;
- successful guarded finishes.

## Protocol quality

- invalid JSON;
- unknown parameters;
- tool-not-allowed actions;
- role violations;
- ungrounded publication attempts;
- value mismatches;
- unchanged failed retries;
- repetition-guard events;
- undeclared dependency waits;
- premature finish attempts;
- post-completion drift;
- max-turn failures.

## Secondary efficiency

- model calls;
- turns;
- input/output tokens;
- wall time;
- p50/p95 call latency;
- successful/failed tool actions.

Efficiency never overrides correctness.

# 10. Selection gate

A model qualifies for resource ranking only when all conditions hold.

## Overall

```text
trials passed >= 32/35
```

## Per scenario

```text
trials passed >= 4/5
```

## Critical invariants

```text
grounded success rate = 100%
role violations = 0
ungrounded publish attempts = 0
unchanged failed retries = 0
required recovery rate >= 90%
exact-value success rate = 100%
wrong-authority selections = 0
undeclared dependency waits = 0
```

The long-horizon scenario must pass at least `4/5`.

# 11. Ranking policy

Use lexicographic ranking:

1. qualification gate;
2. trials passed;
3. grounding and recovery quality;
4. role/repetition cleanliness;
5. long-horizon reliability;
6. latency;
7. VRAM;
8. temperature/power.

A failing model cannot outrank a passing model because of speed.

# 12. Failure taxonomy

Normalized event example:

```json
{
  "scenario_id": "dependency_progress_and_finish_guard",
  "trial": 2,
  "turn": 11,
  "role": "consumer_agent",
  "action_name": "wait_for_dependency",
  "failure_code": "repeated_action_detected",
  "taxonomy": "non_progress_repetition",
  "required_failure": false,
  "state_changed_since_previous_attempt": false,
  "recovered_later": true
}
```

Top-level categories:

- `parse_or_schema_failure`
- `role_or_tool_violation`
- `grounding_failure`
- `exact_value_failure`
- `dependency_failure`
- `repetition_failure`
- `recovery_failure`
- `finish_guard_failure`
- `state_retention_failure`
- `max_turn_failure`

Use `NonRequiredFailureEvents`, not `AvoidableFailures`.

# 13. Output artifacts

Per model:

```text
artifacts/behavioral_benchmark_v2/<model_id>.<runtime_commit>/
  manifest.json
  summary.json
  trial_results.jsonl
  action_events.jsonl
  failure_events.jsonl
  failure_taxonomy.json
  grounding_report.json
  recovery_report.json
  scenario_matrix.csv
  trace/
```

Cross-model:

```text
artifacts/behavioral_benchmark_v2/comparison_<runtime_commit>/
  model_comparison.csv
  model_comparison.json
  scenario_comparison.csv
  failure_taxonomy.csv
  integrity.json
  validation_record.json
  sha256.csv
```

Generated artifacts remain untracked unless an artifact-retention policy is adopted.

# 14. Integrity checks

Per model:

- runtime commit matches;
- registry hash matches;
- prompt hash matches;
- seven scenarios present;
- five trials per scenario;
- unique trial ids;
- explicit trace termination;
- summary counts reconcile with raw events;
- taxonomy counts reconcile;
- grounding totals match registry;
- server alias matches requested model;
- no second server active;
- endpoint stopped after run.

Cross-model:

- same runtime commit;
- same registry hash;
- same prompt hash;
- same generation configuration;
- all expected models present;
- checksum verification passes.

# 15. Implementation sequence

## Phase A — Registry and validators

1. scenario registry schema;
2. registry validation;
3. deterministic seed handling;
4. expected requirement counting;
5. taxonomy normalization.

No model runs.

## Phase B — Fixtures

Implement in this order:

1. `role_boundary_exact_handoff`;
2. `malformed_action_recovery`;
3. `conflicting_grounded_facts`;
4. `dependency_progress_and_finish_guard`;
5. `long_horizon_multi_fact_retention`;
6. harden both legacy scenarios.

Each scenario requires positive and negative tests.

## Phase C — Automated tests

Minimum:

- valid trajectory passes;
- forbidden tool fails;
- ungrounded publish fails;
- exact mismatch fails;
- correct recovery passes;
- unchanged retry fails;
- dependency wait passes after progress;
- identical wait fails without progress;
- wrong authority fails;
- premature finish fails;
- state regression fails;
- summary and taxonomy counts match traces.

## Phase D — Pilot

Run only `fifth_model`:

```text
7 scenarios × 1 trial
```

Use the pilot to find runtime or fixture defects, not to tune around the model.

## Phase E — Frozen qualification

1. commit runtime and scenarios;
2. record commit;
3. run `fifth_model`, `third_model`, `fourth_model`;
4. aggregate offline;
5. inspect every failure;
6. separate model-policy defects from runtime defects.

## Phase F — Resource replication

Only passing models receive:

```text
3 complete deterministic resource runs
```

Report median and range.

# 16. Benchmark acceptance criteria

Ready for frozen runs only when:

- full automated suite passes;
- all seven registry entries validate;
- requirement totals are deterministic;
- positive golden trajectories pass;
- negative golden trajectories fail for intended reasons;
- no model alias branches exist;
- no model-specific parser repair exists;
- no model-specific tool behavior exists;
- summaries reconcile with raw events;
- pilot traces show no runtime deadlock;
- one-server lifecycle is verified.

# 17. Post-cohort status

The frozen qualification cohort is complete:

```text
3 models
7 scenarios
5 trials per scenario
105 real-model trials
90 successful trials
0 models passed the mandatory correctness gate
```

All three models passed the six non-retention scenarios at `5/5` and failed
`long_horizon_multi_fact_retention` at `0/5`. Existing trials should remain
frozen evidence; any new models, prompts, sampling settings, context sizes, or
turn limits define a new experimental condition rather than a rerun of this
cohort.
