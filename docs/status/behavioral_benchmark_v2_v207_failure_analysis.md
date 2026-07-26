# Behavioral Benchmark v2: V2-07 Offline Failure Analysis

## Status

- Analysis type: read-only post-hoc diagnostics.
- Model executions performed: none.
- Frozen behavioral execution commit: `5826c8c`.
- Evidence-manifest commit: `c667200`.
- Frozen benchmark tag: `behavioral-benchmark-v2-final`.
- Frozen evidence trials analyzed: 15.
- Benchmark result changed: no.

This document is a diagnostic appendix. It does not alter the Behavioral Benchmark v2 scenarios, gates, trial results, or final conclusion that no evaluated model passed the correctness gate.

## Executive finding

All 15 V2-07 trials failed the long-horizon retention scenario, but they did not fail through one uniform mechanism.

- `fifth_model` made useful progress late into every trial but did not converge before the 40-turn limit.
- `third_model` also progressed late, but combined turn exhaustion with invalid actions and repeated premature-finish attempts.
- `fourth_model` usually entered a terminal dead-end: two producer roles completed their local contracts, while both consumer roles became terminal before their dependencies were published.

The `fourth_model` evidence does not show loss of already retained facts. It shows failure to schedule dependency-aware consumer actions as shared state became available.

## Cross-model taxonomy

| Model | Trials | Stop reasons | Requirements met | Last progress | Invalid actions | Unchanged retries | Premature finishes | Classification |
| --- | ---: | --- | --- | --- | ---: | ---: | ---: | --- |
| `fifth_model` | 5 | `max_turns_total` × 5 | 17–23/27 | 35–38 | 0 | 5 | 1 | Late-progress turn exhaustion |
| `third_model` | 5 | `max_turns_total` × 5 | 19–20/27 | 36–39 | 5 | 6 | 12 | Unstable late-progress exhaustion |
| `fourth_model` | 5 | `all_agents_terminal` × 4, `max_turns_total` × 1 | 13–15/27 | 31–32 | 0 | 15 | 2 | Consumer terminal dead-end |

## `fifth_model`: late-progress turn exhaustion

- Stop reason: `max_turns_total` in 5/5 trials.
- Final completion: 17–23 of 27 requirements.
- Last recorded progress: event 35–38.
- Invalid actions: 0.
- The dominant failed operation was `shared_read_fact`.
- The model remained operational but did not convert late progress into complete validation and terminal convergence.

This is primarily a model-policy and planning-efficiency failure. The frozen evidence does not establish a runtime defect.

## `third_model`: unstable late-progress exhaustion

- Stop reason: `max_turns_total` in 5/5 trials.
- Final completion: 19–20 of 27 requirements.
- Last recorded progress: event 36–39.
- Invalid actions: 5.
- Premature-finish attempts: 12.
- Repeated failed operations included `retention_source_read` and `shared_read_fact`.

The model remained capable of late progress, but its finish-state judgment and action-contract compliance were less stable than `fifth_model`.

## `fourth_model`: consumer terminal dead-end

- Stop reason: `all_agents_terminal` in 4/5 trials.
- The four terminal trials each completed exactly 15 of 27 requirements.
- `research_agent` completed 9/9 local requirements.
- `document_agent` completed 6/6 local requirements.
- `operator_agent` completed 0/3 local requirements.
- `verification_agent` completed 0/9 local requirements.

### Exact unmet requirement matrix

| Agent | Requirement | Failed trials | Terminal reason |
| --- | --- | ---: | --- |
| `operator_agent` | `operator_approval_phrase_read` | 4/4 | `failure_limit` |
| `operator_agent` | `operator_document_packet_read` | 4/4 | `failure_limit` |
| `operator_agent` | `operator_release_identifier_read` | 4/4 | `failure_limit` |
| `verification_agent` | `approval_phrase_read` | 4/4 | `repetition_guard` |
| `verification_agent` | `project_owner_read` | 4/4 | `repetition_guard` |
| `verification_agent` | `release_identifier_read` | 4/4 | `repetition_guard` |
| `verification_agent` | `release_identifier_validated` | 4/4 | `repetition_guard` |
| `verification_agent` | `retained_snapshot_validated` | 4/4 | `repetition_guard` |
| `verification_agent` | `review_status_authority_validated` | 4/4 | `repetition_guard` |
| `verification_agent` | `review_status_read` | 4/4 | `repetition_guard` |
| `verification_agent` | `verification_document_packet_read` | 4/4 | `repetition_guard` |
| `verification_agent` | `verification_research_handoff_read` | 4/4 | `repetition_guard` |

No unmet requirements belonged to `research_agent` or `document_agent`.

### Repeated causal chain

The same terminal pattern occurred in all four `all_agents_terminal` trials:

1. `verification_agent` attempted shared-fact reads before the facts were published.
2. It repeatedly selected `review_status` despite unchanged unavailability and alternative permitted actions.
3. Its third identical read triggered `repeated_action_detected` and `repetition_guard`.
4. `operator_agent` attempted `release_identifier` and `approval_phrase` before publication.
5. After `release_identifier` became available, it did not read the newly available fact and instead repeated the still-unavailable `approval_phrase` read.
6. That failure triggered `failure_limit` and quarantine.
7. `research_agent` later published `review_status` and completed.
8. `document_agent` later published `approval_phrase` and completed.
9. The two consumer roles were already terminal and could not consume or validate the newly published dependencies.
10. All four agents were terminal, so runtime stopped with `all_agents_terminal` while 12 requirements remained unmet.

### Representative terminal events

| Agent | Action | Error | Terminal reason | Classification |
| --- | --- | --- | --- | --- |
| `document_agent` | `finish` | `none` | `goal_completed` | `successful_finish` |
| `operator_agent` | `shared_read_fact` | `shared_fact_not_found` | `failure_limit` | `failure_terminalization` |
| `research_agent` | `finish` | `none` | `goal_completed` | `successful_finish` |
| `verification_agent` | `shared_read_fact` | `repeated_action_detected` | `repetition_guard` | `failure_terminalization` |

## Retention interpretation

The `fourth_model` trials retained the producer-side state:

- retained facts: 4/4;
- required files: 2/2;
- completed-requirement loss events: 0;
- state-regression events: 0;
- fact-substitution events: 0.

Therefore these failures should not be described as demonstrated forgetting of already retained facts. The failed capability was end-to-end long-horizon retention workflow completion: the consumer and validation path never completed.

## Runtime interpretation

The evidence supports all of the following:

1. Guarded local finish worked: producer roles finished only after their local contracts were satisfied.
2. Global evaluation worked: local completion did not create a false successful trial.
3. The scheduler stop reason was mechanically correct after all agents became terminal.
4. Failure and repetition guards prevented unlimited unchanged retries.

The evidence also exposes a recovery limitation:

> Agent-level failure terminalization is irreversible within the trial, even when a previously unavailable dependency becomes available later.

This is a terminal dead-end in recovery semantics. The frozen evidence does not by itself prove that the behavior is an implementation bug; it may be the intended fail-closed policy.

## Attribution

### Directly supported model-policy failures

- Reading dependencies before publication instead of waiting.
- Repeating an unchanged unavailable shared-fact read.
- Failing to consume a newly available fact after shared-state transition.
- Failing to sequence consumer validation behind producer publication.

### Architecture-level limitation

- Once every consumer capable of completing the remaining requirements is terminal, later producer progress cannot recover the global task.

### Not supported by the evidence

- Loss of previously completed requirements.
- Corruption of retained fact values.
- Wrong-authority selection.
- Role-boundary violation.
- Ungrounded publication.
- False global success.

## Implications for a future benchmark version

Behavioral Benchmark v2 must remain unchanged. Any experiment with the following changes constitutes a new preregistered benchmark version or separate ablation:

- reactivating a quarantined or stopped consumer after a relevant resource-state transition;
- distinguishing recoverable dependency exhaustion from permanent agent failure;
- requiring dependency-aware waits before repeated reads;
- reserving at least one recovery-capable consumer until global completion;
- changing repetition thresholds, failure limits, prompts, or turn limits.

## Final diagnostic conclusion

V2-07 produced a common failed outcome but three different behavioral mechanisms. `fifth_model` and `third_model` primarily failed to converge within the turn budget. `fourth_model` primarily entered a reproducible terminal dead-end in which consumer agents exhausted their failure guards before producer dependencies became available.
