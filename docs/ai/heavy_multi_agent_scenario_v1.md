# Heavy Multi-Agent Scenario v1

## 1. Purpose

This document records the heavier four-agent orchestrator/executor scenario added after the first pair matrix. It is still an offline, local, bounded prototype scenario. It does not use external network access, does not download models, does not modify GGUF files, and does not make a final model-pair recommendation.

## 2. Scenario

- scenario config: `configs/multi_agent_scenarios/office_developer_maintenance_group_heavy.json`
- scenario id: `office_developer_maintenance_group_heavy_v1`
- agents: `office_agent_1`, `office_agent_2`, `developer_agent_1`, `developer_agent_2`
- max group steps: 2
- max steps per agent: 1 per group step
- registry: `configs/script_registry.example.json`
- write path policy: `artifact_workspace_only`

The scenario uses three local fixtures under `configs/multi_agent_fixtures/office_developer_maintenance/` and existing project documentation. It intentionally exercises a larger plan with four agents and two group steps while keeping actions local and bounded.

## 3. Safety controls

- Network and external services are marked not required.
- Browser and office real automation remain disabled; office behavior is still stub/file-based.
- GGUF model roots remain forbidden by registry and file helpers.
- Write actions in this heavy scenario are additionally constrained to the run artifact workspace.
- The first real N=3 run exposed that executor prompts could create `docs/ai/example_note.md`; that generated file was removed from the working tree and the scenario now enforces workspace-only writes instead of hiding the failure mode. The superseded diagnostic artifact is retained at `experiments/multi_agent/orchestrator_executor/repeated_local_second_to_first_heavy_group_n3_v1`.

## 4. Fake smoke

Artifact root:

```text
experiments/multi_agent/orchestrator_executor/fake_heavy_group_scenario_smoke_workspace_policy_v1
```

Result:

| metric | value |
|---|---:|
| attempted trials | 2 |
| completed trials | 2 |
| failed trials | 0 |
| mean pair quality score | `0.958333` |
| mean execution success rate | `1.0` |
| total errors | 0 |

## 5. Best-pair repeated local run

Pair: `second_model -> first_model`

Artifact root:

```text
experiments/multi_agent/orchestrator_executor/repeated_local_second_to_first_heavy_group_n3_workspace_policy_v1
```

Result:

| metric | value |
|---|---:|
| attempted trials | 3 |
| completed trials | 3 |
| failed trials | 0 |
| mean pair quality score | `0.820328` |
| mean execution success rate | `1.0` |
| mean final validation success rate | `0.454545` |
| total errors | 18 |

The run completed, but all trials were `completed_with_failures`. The common failure mode was `write_path_outside_artifact_workspace`; repair attempts then hit executor HTTP 400 responses. This is useful negative evidence: the pair can complete bounded actions, but the executor is not robust under the heavier path policy.

## 6. Heavy pair matrix

Artifact root:

```text
experiments/multi_agent/orchestrator_executor/pair_matrix_heavy_group_n3_workspace_policy_v1
```

| rank | pair | status | completed | failed | mean pair quality | execution success | total errors | common failure modes | prototype rank score |
|---:|---|---|---:|---:|---:|---:|---:|---|---:|
| 1 | `second_model -> second_model` | completed | 3 | 0 | `0.875451` | `1.0` | 6 | `NextActionJSONError: 6`, `NextActionValidationError: 6` | `0.759188` |
| 2 | `second_model -> first_model` | reused | 3 | 0 | `0.820328` | `1.0` | 18 | `validation_failed: 18`, `write_path_outside_artifact_workspace: 18`, `HTTPStatusError: 18` | `0.571269` |
| 3 | `first_model -> first_model` | failed | 0 | 3 | `0.0` | `0.0` | 6 | `orchestrator_plan_parse_failed: 6` | `0.0` |
| 4 | `first_model -> second_model` | failed | 0 | 3 | `0.0` | `0.0` | 6 | `orchestrator_plan_parse_failed: 6` | `0.0` |

The best observed pair on this heavy scenario was `second_model -> second_model`. This is not a final recommendation because the evidence is still N=3, local, short-horizon, and lacks capacity/GPU measurement.

## 7. Cross-scenario comparison

Artifact root:

```text
experiments/multi_agent/orchestrator_executor/cross_scenario_pair_matrix_workspace_policy_v1
```

| field | value |
|---|---|
| simple scenario best pair | `second_model -> first_model` |
| heavy scenario best pair | `second_model -> second_model` |
| best observed pair across tested scenarios | `second_model -> second_model` |

The cross-scenario stability verdict for both completed `second_model` orchestrator pairs is `stable_but_low_confidence`. The best pair changed between scenarios, so the current evidence is still preliminary only.

## 8. Limitations

- Only two group scenarios have pair matrices.
- N=3 per pair is directional evidence, not a benchmark.
- The runner is sequential; it is not measured concurrent multi-agent capacity.
- No GPU runtime was configured or measured.
- No stress/capacity benchmark was run.
- Browser behavior remains simulated-only and office behavior remains stub/file-based.

## 9. Next step

Run a measured capacity or resource probe for the top two `second_model` orchestrator pairs, then increase scenario diversity before making any final recommendation.
