# Final Evaluation Report

## 1. Executive summary

The project goal is to prototype and experimentally evaluate local LLM agents that imitate normal user activity in a controlled computer/network environment.

The prototype infrastructure is implemented and tested: agent state, prompt construction, local model adapter, `NextAction` contract, registry validation, script execution bridge, history/error logging, repeated trials, behavioral analysis, cross-scenario comparison, and resource/capacity estimation.

Local CPU-oriented single-agent runs were demonstrated through `llama.cpp / llama-server` style local model execution and persisted scenario artifacts. Two local models were compared across two scenarios with N=3 repeated trials per model per scenario, for 12 real local-model trajectories total.

The experiments show measurable behavioral differences, but neither model is strong enough for a final production recommendation. `second_model` has better JSON/action-contract validity and lower latency in the current evidence base. `first_model` showed more useful execution in one office-worker scenario, but it is repair-dependent and scenario-sensitive. Both models show template-like/repetitive behavior and weak coherence.

Publication note: current repository setup exposes the second model as `second_model`. Some historical artifacts and tables retain the earlier recorded id `qwen2_5_3b_instruct_q4_k_m`.

Post-report prototype extension: after this final report was written, a sequential fake-mode orchestrator/executor group MVP was added under `experiments/multi_agent/orchestrator_executor/fake_office_developer_group_v1`. That extension is not part of the 12 real local-model trajectories summarized here, and it does not change the report's historical conclusions about local multi-agent capacity or final model recommendation readiness.

Multi-agent capacity is estimated by formula, not measured by stress test. The current planning estimate is 11 concurrent agents for both tested models on the current machine, CPU-bound, with low confidence.

Recommended next development: keep the artifact-based evaluation pipeline, keep both models in the evaluation set, use `repair_attempts=1`, fix workspace/safety alignment for developer scenarios, add measured runtime/concurrent capacity probes, and do not declare a final deployment model yet.

## 2. ТЗ alignment

| ТЗ requirement | evidence artifact | status | conclusion |
|---|---|---|---|
| Local LLM agent prototype | `src/agent/experiment_scenario_runner.py`, `scripts/run_agent_scenario.py`, `docs/ai/experiment_scenario_runner_v1.md` | implemented | End-to-end runner exists for fake and local modes. |
| Roles, resources, constraints, scripts | `configs/roles/`, `configs/agent_state.example.json`, `configs/script_registry.example.json`, `docs/ai/developer_walkthrough_for_newcomer.md` | implemented | State/role/registry formats exist and are used by scenario runs. |
| Local model action selection | `src/agent/llm_client.py`, `src/agent/action_selector.py`, local dry-run artifacts | evaluated | Local mode was executed for both models. |
| Parameterized script execution | `src/agent/script_registry.py`, `src/agent/script_execution_bridge.py`, `execution_results.jsonl` in trial folders | evaluated | Actions are validated and executed or rejected by safety policy. |
| History and errors | `src/agent/execution_history.py`, `history.jsonl`, `errors.jsonl`, `attempts.jsonl` | implemented/evaluated | Initial failures, repairs, validation, execution and errors are preserved. |
| Multiple local models | `configs/evaluation_models.json`, `docs/ai/evaluation_models_v1.md` | evaluated | `first_model` and `second_model` were tested; historical artifacts record the second model as `qwen2_5_3b_instruct_q4_k_m`. |
| Role compliance | `experiments/model_behavior/analysis/*`, `docs/ai/consolidated_behavioral_analysis_v1.md` | evaluated | Role-compatible action choice was observed, but useful progress remained weak. |
| Coherence, diversity, repetition | `experiments/model_behavior/cross_scenario/office_worker_developer_two_model_cross_scenario_v1` | evaluated | Both models are weak on coherence and show template-like behavior. |
| CPU/RAM/latency | `experiments/model_behavior/resources/resource_capacity_v1` | limited/evaluated | Lightweight latency/RSS/CPU observations exist; no full benchmark. |
| Capacity formula | `docs/ai/multi_agent_capacity_formula.md`, `capacity_estimate.json` | estimated | Formula implemented; capacity is planning estimate, not measured load result. |
| Final report | `reports/experiments/final_evaluation_report.md` | implemented | This report consolidates current evidence and limitations. |

## 3. Implemented prototype architecture

Factual pipeline:

`scenario/config -> AgentState -> PromptBuilder -> LocalLLMClient/ActionSelector -> NextAction -> ScriptRegistry validation -> ScriptExecutionBridge -> result -> ExecutionHistoryLogger -> ActivityTrajectoryEvaluator -> analysis artifacts`

Key components:

| component | evidence | role |
|---|---|---|
| `AgentState` | `src/agent/state.py` | Loads role, resources, constraints, available scripts and history context. |
| `PromptBuilder` | `src/agent/prompt_contract.py` | Builds messages for the local model using role, state, scripts and history. |
| `LocalLLMClient` | `src/agent/llm_client.py` | Calls OpenAI-compatible local model endpoint. |
| `NextAction` contract | `src/agent/schemas.py`, `src/agent/action_contract.py` | Defines and parses model action JSON. |
| Registry validation | `src/agent/script_registry.py` | Checks known action and required parameters. |
| Execution bridge | `src/agent/script_execution_bridge.py` | Executes bounded file/browser/office/shell actions and normalizes results. |
| History/error logging | `src/agent/execution_history.py` | Writes history and error records into artifacts. |
| Behavioral evaluator | `src/agent/activity_evaluator.py` | Computes normality, diversity, repetition, coherence and history-related scores. |
| Scenario runner | `src/agent/experiment_scenario_runner.py` | Produces per-run artifacts including attempts, validation, execution, history and resources. |
| Repeated/cross-scenario analysis | `src/agent/repeated_model_trials.py`, `src/agent/consolidated_behavioral_analysis.py`, `src/agent/cross_scenario_analysis.py` | Aggregates behavior across trials and scenarios. |
| Resource/capacity evaluation | `src/agent/resource_capacity_evaluation.py` | Aggregates resource summaries and computes capacity formula. |

## 4. Chosen implementation stack

| stack element | evidence | reason it fits the ТЗ |
|---|---|---|
| Python project | `pyproject.toml`, `requirements.txt`, `src/agent/` | Fast prototyping, local execution, strong testability. |
| `llama.cpp / llama-server` runtime | `configs/evaluation_models.json`, `scripts/start_llama_server.ps1` | Local CPU-oriented GGUF model serving with OpenAI-compatible API. |
| OpenAI-compatible endpoint | `src/agent/llm_client.py`, model `base_url` values | Keeps local model calls isolated behind a simple adapter. |
| GGUF models | `models/gguf/README.md`, `configs/evaluation_models.json` | Fits local/offline model requirement. |
| Pydantic/JSON contracts | `src/agent/schemas.py`, `src/agent/evaluation_models.py` | Makes state/action/model contracts explicit and testable. |
| Pytest validation | `tests/`, final run `636 passed` | Offline regression coverage for runner, analysis and resource layers. |
| `psutil` resource summaries | `requirements.txt`, `resource_summary.json`, `resource_capacity_v1` | Provides lightweight CPU/RAM observations without heavy benchmarking. |

## 5. Models tested

| current model_id | historical artifact id | llama-server model_name | upstream/full model name | GGUF path | size / quantization | runtime | CPU-only assumption | scenarios | total trials |
|---|---|---|---|---|---|---|---|---|---:|
| `first_model` | `first_model` | `first_model.gguf` | `qwen2.5-1.5b-instruct-q4_k_m.gguf` | `models/gguf/first_model.gguf` | 1.5B / Q4_K_M | `llama.cpp / llama-server` | true | office-worker, developer maintenance | 6 |
| `second_model` | `qwen2_5_3b_instruct_q4_k_m` | `second_model.gguf` | `qwen2.5-3b-instruct-q4_k_m.gguf` | `models/gguf/second_model.gguf` | 3B / Q4_K_M | `llama.cpp / llama-server` | true | office-worker, developer maintenance | 6 |

Source: `configs/evaluation_models.json`, `docs/ai/model_research_metadata.md`, `experiments/model_behavior/cross_scenario/office_worker_developer_two_model_cross_scenario_v1/cross_scenario_analysis.json`.

## 6. Experiment protocol

Protocol used for behavioral evidence:

- mode: local;
- scenarios: `office_worker_basic_session` and `developer_project_maintenance`;
- N=3 trials per model per scenario;
- max steps: 5;
- execute-actions enabled;
- repair policy: `repair_attempts=1`;
- same action registry, prompt contract, safety policy and evaluator across compared runs;
- artifacts persisted per run and aggregated afterward.

Repair policy:

- one structured repair attempt can be requested after parse/validation failure;
- initial failure is preserved in `attempts.jsonl` and `errors.jsonl`;
- repair does not auto-fill missing parameters and does not silently convert invalid actions into valid ones.

Primary protocol artifacts:

- `docs/ai/experiment_runner_repair_policy_v1.md`
- `docs/ai/repeated_trials_protocol_v1.md`
- `experiments/model_behavior/repeated_trials/office_worker_two_model_repair_n3_v1`
- `experiments/model_behavior/repeated_trials/developer_project_maintenance_two_model_repair_n3_v1`

## 7. Behavioral results

Source: `experiments/model_behavior/cross_scenario/office_worker_developer_two_model_cross_scenario_v1/cross_scenario_analysis.json`.

| model_id | initial validity | final validity | execution success | normal activity | diversity | repetition | history usage | latency ms | main failure pattern |
|---|---:|---:|---:|---:|---:|---:|---:|---:|---|
| `first_model` | 0.0 | 0.333334 | 0.5 | 0.215 | 0.583333 | 0.8625 | 0.25 | 753.749333 | `validation_failed_after_repair` |
| `qwen2_5_3b_instruct_q4_k_m` | 1.0 | 1.0 | 0.0 | 0.0 | 0.458334 | 0.8625 | 0.75 | 489.095667 | `file_not_found`, `unsafe_path` |

`first_model`:

- poor first-attempt validity;
- repair-dependent;
- achieved successful execution in the office-worker scenario;
- failed to produce useful execution in the developer scenario;
- repeated narrow action patterns and has high scenario sensitivity.

`qwen2_5_3b_instruct_q4_k_m`:

- strong initial and final contract validity;
- lower latency;
- zero execution success in the tested scenarios;
- repeatedly targeted missing or unsafe paths;
- also shows template-like behavior.

## 8. Role compliance

Evidence:

- `experiments/model_behavior/analysis/office_worker_two_model_behavioral_analysis_v1`
- `experiments/model_behavior/analysis/developer_project_maintenance_two_model_behavioral_analysis_v1`
- `docs/ai/consolidated_behavioral_analysis_v1.md`
- `docs/ai/developer_project_maintenance_trials_v1.md`

Main interpretation:

- Role-compatible actions do not imply useful execution.
- File/document actions were broadly compatible with the office-worker role, but both models repeated narrow patterns.
- In the developer scenario, `qwen2_5_3b_instruct_q4_k_m` selected a developer-relevant source path (`src/main.py`), but execution was rejected by the current safety policy as `unsafe_path`.
- `first_model` selected file/create actions but required repair and remained brittle.
- Shell-heavy behavior was not observed as a recommended pattern; shell execution remains bounded by allowlists.

## 9. Coherence, history usage, diversity, repetition

Both models are weak on sequence coherence. Cross-scenario `mean_sequence_coherence_score` is 0.0 for both models.

Both models show template-like behavior. Repetition score alone is not sufficient: it must be interpreted with action/parameter repetition and whether the repeated action makes progress.

`qwen2_5_3b_instruct_q4_k_m` has higher history usage score (0.75 vs 0.25), but this did not translate into useful adaptation in the office-worker missing-file loop.

`first_model` has lower history usage and repeated successful or invalid patterns. Its useful execution appears scenario-specific rather than robust.

## 10. Failure modes

| model | stable failures | scenario-specific failures | examples | impact |
|---|---|---|---|---|
| `first_model` | `validation_failed_after_repair: 6` | none detected in cross-scenario aggregate | missing required parameters, repair failure, workspace/path violations | Requires repair policy and still fails often. |
| `qwen2_5_3b_instruct_q4_k_m` | none detected | office-worker `file_not_found: 6`; developer `unsafe_path: 3` | repeated `docs/notes.txt`; repeated `src/main.py` rejected as unsafe | Contract-valid but poor environment adaptation/execution usefulness. |

Both models repeat action/parameter templates. This is a key behavioral limitation for the target of imitating normal user activity.

## 11. Resource and latency results

Source: `experiments/model_behavior/resources/resource_capacity_v1/resource_capacity_evaluation.json`.

System snapshot:

| field | value |
|---|---:|
| physical CPU count | 24 |
| logical CPU count | 24 |
| total RAM MB | 130436.711 |
| available RAM MB | 82560.059 |
| reserved RAM MB | 4096 |
| effective available RAM MB | 78464.059 |

Per-model observations:

| model_id | mean selection latency ms | mean total step latency ms | mean wall time ms | RSS delta MB | CPU observation |
|---|---:|---:|---:|---:|---:|
| `first_model` | 753.7495 | 755.302667 | 1484.923667 | 6.099833 | 5.95% |
| `qwen2_5_3b_instruct_q4_k_m` | 489.095667 | 489.742417 | 761.277167 | 5.205167 | 6.15% |

CPU-only assessment:

- short single-agent CPU-oriented local runs are demonstrated;
- runtime probe was not run in the resource step;
- concurrent multi-agent CPU-only capacity is estimated, not measured;
- model RAM is estimated from GGUF file size, not measured `llama-server` RSS.

## 12. Multi-agent capacity formula

Source: `docs/ai/multi_agent_capacity_formula.md`.

```text
effective_available_ram_mb = max(0, available_ram_mb - reserved_system_ram_mb)

ram_bound = floor(
  effective_available_ram_mb /
  (model_ram_mb + per_agent_runtime_overhead_mb)
)

cpu_bound = floor(
  target_cpu_utilization_percent /
  average_cpu_load_percent_per_agent
)

estimated_concurrent_agents = min(ram_bound, cpu_bound)
```

Numeric estimate:

| model_id | model RAM estimate MB | per-agent overhead MB | CPU %/agent | RAM bound | CPU bound | estimated agents | bottleneck | confidence |
|---|---:|---:|---:|---:|---:|---:|---|---|
| `first_model` | 1065.56 | 128 | 5.95 | 65 | 11 | 11 | CPU | low |
| `qwen2_5_3b_instruct_q4_k_m` | 1840.499 | 128 | 6.15 | 39 | 11 | 11 | CPU | low |

This is a planning estimate, not measured concurrent throughput. Real concurrent capacity requires a controlled multi-agent load test.

## 13. Recommended configuration

No final production model should be selected yet.

Provisional recommendation for further development:

- keep both models in the evaluation set;
- prefer `second_model` when strict JSON/action-contract validity and lower latency matter;
- use `first_model` only with repair policy and safety guardrails, because it showed some execution usefulness but is brittle;
- keep local `llama-server` runtime and model registry workflow;
- keep `repair_attempts=1` for fair future model comparisons;
- keep repeated trials with N>=3 and artifact-based comparison;
- keep execute-actions enabled with workspace safety boundaries;
- use the capacity formula as a low-confidence planning bound until measured multi-agent stress data exists.

## 14. Limitations

- Only two scenarios were evaluated.
- N=3 per model per scenario is a small sample.
- No multi-agent stress test was run.
- Concurrent capacity was not measured.
- Runtime probe was not run in the resource step.
- Browser behavior remains simulated-only.
- Office behavior remains stub/file-based.
- Git/mail actions were not added.
- Safety policy rejected some developer-relevant paths.
- No final production recommendation can be made from current evidence.

## 15. Recommendations for further work

1. Align workspace/resource policy so developer scenarios can safely read intended project files, or adapt scenario paths to the current safe workspace.
2. Add a third scenario or rerun the developer scenario after path-policy tuning.
3. Run controlled multi-agent stress/capacity smoke.
4. Add measured runtime probe with `llama-server` RSS.
5. Improve prompt/action schemas to reduce missing parameters and repeated invalid paths.
6. Add real browser/office automation only if required by scope.
7. Produce final model recommendation only after cross-scenario, resource and measured capacity evidence improves.

## 15a. Post-report prototype extension

The repository now contains a first fake-mode orchestrator/executor group MVP:

- scenario: `configs/multi_agent_scenarios/office_developer_group_basic.json`;
- runner: `scripts/run_orchestrator_executor_group.py`;
- implementation: `src/agent/orchestrator_executor_pipeline.py`;
- documentation: `docs/ai/orchestrator_executor_pipeline_v1.md`;
- artifacts: `experiments/multi_agent/orchestrator_executor/fake_office_developer_group_v1`.

This extension demonstrates the structural group-agent path: plan, assignment, per-agent executor actions, validation, bounded execution, group history, and prototype pair-quality metrics. It remains fake-mode evidence only. No local group inference, GPU run, production scheduler, or measured concurrent capacity test is included in this final report.

## 16. Artifact index

Architecture/onboarding:

- `docs/ai/project_structure_audit_for_report.md`
- `docs/ai/developer_walkthrough_for_newcomer.md`
- `docs/ai/experiment_scenario_runner_v1.md`
- `docs/ai/evaluation_models_v1.md`
- `docs/ai/experiment_runner_repair_policy_v1.md`

Single-model dry runs:

- `docs/ai/single_model_dry_run_first_model_v1.md`
- `docs/ai/single_model_dry_run_qwen2_5_3b_v1.md`

Repeated trials:

- `experiments/model_behavior/repeated_trials/office_worker_two_model_repair_n3_v1`
- `experiments/model_behavior/repeated_trials/developer_project_maintenance_two_model_repair_n3_v1`
- `docs/ai/repeated_trials_protocol_v1.md`
- `docs/ai/developer_project_maintenance_trials_v1.md`

Behavioral analyses:

- `experiments/model_behavior/analysis/office_worker_two_model_behavioral_analysis_v1`
- `experiments/model_behavior/analysis/developer_project_maintenance_two_model_behavioral_analysis_v1`
- `docs/ai/consolidated_behavioral_analysis_v1.md`

Cross-scenario:

- `experiments/model_behavior/cross_scenario/office_worker_developer_two_model_cross_scenario_v1`
- `docs/ai/cross_scenario_behavioral_analysis_v1.md`

Resource/capacity:

- `experiments/model_behavior/resources/resource_capacity_v1`
- `docs/ai/resource_capacity_evaluation_v1.md`
- `docs/ai/multi_agent_capacity_formula.md`

Post-report orchestrator/executor MVP:

- `docs/ai/orchestrator_executor_pipeline_v1.md`
- `configs/multi_agent_scenarios/office_developer_group_basic.json`
- `experiments/multi_agent/orchestrator_executor/fake_office_developer_group_v1`

Verification:

- latest full test run in this reporting step: `636 passed`.
