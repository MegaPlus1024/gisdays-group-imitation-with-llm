# Local Orchestrator/Executor POC v2 with Plan Repair

## 1. Purpose

The v1 local proof reached two live local endpoints but failed before executor calls because `second_model` returned invalid/truncated orchestrator JSON. This v2 proof hardens plan generation and artifact preservation, then reruns the same controlled local pair:

- orchestrator: `second_model`
- executor: `first_model`

This is still a narrow proof-of-concept for the final TZ group-agent path, not a benchmark, stress test, GPU run, production scheduler, or final model-pair recommendation.

## 2. Changes

- Compact orchestrator prompt with short fields and max two tasks.
- `--orchestrator-max-tokens` CLI override.
- `--orchestrator-repair-attempts` CLI option.
- Orchestrator repair prompt for invalid plan JSON or validation failure.
- `orchestrator_attempts.jsonl` with prompt, raw output, parse status, validation status, errors, and latency.
- Complete diagnostic artifact set when orchestrator plan parsing/validation fails.
- Deduplicated validation issue codes before activity evaluation.

## 3. Runtime

| role | model | endpoint | PID |
|---|---|---|---:|
| orchestrator | `second_model.gguf` | `http://127.0.0.1:8081/v1` | 14008 |
| executor | `first_model.gguf` | `http://127.0.0.1:8082/v1` | 36356 |

Both endpoints responded to `/v1/models` before the proof run. Both started processes were stopped afterward, and both endpoints stopped responding.

## 4. Result

Artifact folder:

```text
experiments/multi_agent/orchestrator_executor/local_second_to_first_group_poc_v2_repair
```

Run result:

| field | value |
|---|---|
| status | `completed_with_failures` |
| success | `false` |
| initial plan parse success | yes |
| repair attempted | no |
| repair parse success | not applicable |
| plan valid | yes |
| executor calls attempted | 2 |
| validation success count | 0 |
| execution success count | 0 |
| pair quality score | `0.291764` |

Main executor errors:

- `office_agent`: `missing_required_parameter`
- `developer_agent`: `unsafe_path`, duplicate `path_outside_allowed_roots`

The executor stage was reached. Both executor model outputs parsed as `NextAction`, but both were rejected before execution by registry/safety validation.

## 5. Interpretation

This proves:

- the two-endpoint local runtime setup works for this narrow group proof;
- `second_model` can produce a valid compact orchestrator plan with the hardened prompt;
- the group runner can route executor calls to `first_model`;
- failed executor validation is preserved as normal artifacts instead of crashing the proof.

This does not prove:

- successful useful task execution;
- robust behavior across repeated trials;
- concurrency or capacity;
- GPU readiness;
- final model-pair suitability.

## 6. Next step

Repeat N=3 local group trials only after tightening executor prompts/repair so `first_model` supplies required parameters and avoids unsafe absolute paths. Track whether validation success improves without weakening safety policy.
