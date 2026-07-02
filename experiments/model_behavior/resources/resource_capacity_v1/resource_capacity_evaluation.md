# Resource and Capacity Evaluation v1

## 1. Purpose

This evaluation addresses the TZ resource questions: CPU/RAM needs, CPU-only feasibility, action-selection latency, and a conservative estimate for concurrent local LLM agents.

## 2. Inputs

- `office_worker`: `C:\Users\m\Documents\local-llm-test-gisdays\local-llm-agent-lab\experiments\model_behavior\repeated_trials\office_worker_two_model_repair_n3_v1`
- `developer_project_maintenance`: `C:\Users\m\Documents\local-llm-test-gisdays\local-llm-agent-lab\experiments\model_behavior\repeated_trials\developer_project_maintenance_two_model_repair_n3_v1`
- cross-scenario analysis: `C:\Users\m\Documents\local-llm-test-gisdays\local-llm-agent-lab\experiments\model_behavior\cross_scenario\office_worker_developer_two_model_cross_scenario_v1`

## 3. System Snapshot

- physical CPUs: `24`
- logical CPUs: `24`
- total RAM MB: `130436.711`
- available RAM MB: `82560.059`
- platform: `Windows-10-10.0.19045-SP0`

## 4. Resource Observations

| model | observations | mean selection ms | mean total step ms | mean wall ms | mean RSS delta MB | mean CPU end % |
|---|---:|---:|---:|---:|---:|---:|
| `first_model` | 6 | 753.7495 | 755.302667 | 1484.923667 | 6.099833 | 5.95 |
| `qwen2_5_3b_instruct_q4_k_m` | 6 | 489.095667 | 489.742417 | 761.277167 | 5.205167 | 6.15 |

## 5. CPU-Only Assessment

Short single-agent local runs were demonstrated on CPU-oriented local model registry entries. This does not prove multi-agent CPU-only practicality.

## 6. Capacity Formula

See `capacity_formula.md` and `docs/ai/multi_agent_capacity_formula.md`.

## 7. Capacity Estimate

| model | effective RAM MB | model RAM MB | overhead MB | CPU %/agent | RAM bound | CPU bound | estimate | bottleneck | confidence |
|---|---:|---:|---:|---:|---:|---:|---:|---|---|
| `first_model` | 78464.059 | 1065.56 | 128.0 | 5.95 | 65 | 11 | 11 | cpu | low |
| `qwen2_5_3b_instruct_q4_k_m` | 78464.059 | 1840.499 | 128.0 | 6.15 | 39 | 11 | 11 | cpu | low |

Warnings: estimates are formula bounds, not measured concurrent throughput.

## 8. Interpretation

- Lower latency does not imply better agent usefulness when execution success is zero.
- `first_model` has some execution usefulness but lower contract validity and higher latency.
- `qwen2_5_3b_instruct_q4_k_m` has lower latency and stronger contract validity but poor execution usefulness in current scenarios.

## 9. Limitations

- Resource sampling is lightweight.
- No true concurrent multi-agent load test was run.
- No long-running sessions were measured.
- No GPU measurements were made.
- No production scheduler was created.
- Browser and office automation remain simulated/stubbed.

## 10. Next Step

Use this estimate in the final report as a planning bound, or run an optional controlled multi-agent smoke/capacity stress test if time allows.