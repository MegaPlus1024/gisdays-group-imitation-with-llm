# Local LLM Agent Lab

## Current research status

This repository now has both the original single-agent evidence base and a consolidated multi-agent orchestrator/executor research report.

- Single-agent evidence: two local GGUF models across two behavioral scenarios, N=3 per model/scenario, summarized in `reports/experiments/final_evaluation_report.md`.
- Multi-agent orchestrator/executor evidence: fake MVP, local POC, repeated group trials, simple/heavy pair matrices, runtime probe, GPU smoke, and corrected bounded stress v2.
- Latest Phase 8 controlled office-evaluation status is documented in `docs/status/phase_8_current_state_for_leadership.md` and `docs/status/phase_8_technical_status.md`.
- Latest confirmed controlled mini-matrix: 3/3 repeats succeeded, 6/6 office actions executed successfully, 6/6 DOCX artifacts were generated and readable, deterministic mean correctness is 1.0. Semantic LLM judge scoring is guarded and has not been run yet.
- Preliminary quality-focused pair: `second_model -> second_model`.
- Resource-balanced/simple-scenario pair: `second_model -> first_model`.
- `first_model` is not recommended as orchestrator in the current tests.
- Bounded stress caveat: concurrency 1 is viable for `second_model -> second_model`, but concurrency 2 is unstable and no production capacity claim is made.
- Current consolidated report: `reports/experiments/final_multi_agent_research_report.md`.

## 1. What this project is

Local LLM Agent Lab is a research prototype for a group of local LLM agents that simulate normal user activity in a controlled virtual computer/network environment.

An agent receives:

- a user role;
- available resources;
- environment constraints;
- a registry of allowed parameterized scripts/actions;
- recent action history.

A local model chooses the next action. The system parses the model response as `NextAction` JSON, validates it against the script registry and role/safety constraints, executes the action through a bounded bridge, logs history/errors, and evaluates whether the behavior looks like normal role-based user activity.

Canonical flow:

```text
config / role
  -> orchestrator
  -> AgentState
  -> PromptBuilder
  -> Local LLM / LocalLLMClient / ActionSelector
  -> NextAction JSON
  -> ScriptRegistry validation
  -> ScriptExecutionBridge / script runner
  -> result normalization
  -> history log / error log
  -> behavioral/resource evaluation
```

Safety validation is necessary infrastructure, but it is not the final objective and not only safe action selection. The research objective is behavioral normality: role compliance, coherence, diversity, realistic history use, and avoidance of repeated/template behavior.

## 2. Current status

This repository is a research prototype, not a production system.

Current evidence:

- local CPU-oriented single-agent runs were demonstrated;
- two local models were compared across two behavioral scenarios;
- repeated trials were completed with N=3 per model per scenario;
- total real local-model trajectories in the final report: 12;
- a sequential fake-mode orchestrator/executor group MVP now exists;
- a controlled two-endpoint local orchestrator/executor proof completed after executor prompt hardening, with two validated and executed local read actions;
- repeated local orchestrator/executor group trials completed N=3 for one pair and one scenario;
- orchestrator/executor pair matrix comparison completed for the basic group scenario, with `second_model -> first_model` as the best observed pair there;
- a heavier four-agent group scenario and second pair matrix completed, with `second_model -> second_model` as the best observed pair there;
- cross-scenario pair comparison now exists, but the best observed pair changes by scenario and remains preliminary only;
- heavy-scenario validation and repair errors are analyzed in `docs/ai/heavy_scenario_error_analysis_v1.md`;
- measured local runtime/resource telemetry now exists for the two top completed pairs across simple and heavy group scenarios;
- optional GPU flags are supported by `scripts/start_llama_server.ps1`, based on observed local `llama-server --help`;
- a short N=1 GPU smoke completed for `second_model -> second_model` on the heavy group scenario;
- v1 bounded stress failed due to a Windows path-length harness issue; corrected v2 bounded stress now has usable preliminary metrics, with stable concurrency 1 observed for `second_model -> second_model` under `cpu_requested_device_none` and `gpu_full_offload`.

Important limitations:

- not production-ready;
- production full autonomous agent loop is not implemented;
- production action execution scheduler/runtime is not implemented;
- corrected bounded concurrent multi-agent stress evidence is preliminary only; no stable concurrency 2 row was observed;
- pair-matrix and runtime-probe evidence covers two short group scenarios so far; no long stress test has been run;
- GPU smoke is short and not a stress test; first wall-time result was roughly comparable, not a meaningful speedup claim;
- browser behavior is confirmed at the fixture-backed autonomous runtime/scenario layer and by guarded Playwright/Chromium suite evidence against local loopback fixtures; production browser automation and external web/network behavior are not confirmed;
- earlier office behavior was stub/file-based; Phase 8 now includes a guarded real document-file office backend for controlled DOCX/XLSX/PPTX-style action validation and DOCX artifact execution;
- no git/mail actions are included;
- GGUF model files are not included in the repository;
- no final production model recommendation is made.

## 3. What is implemented

- `AgentState` and role/resource/constraint configs.
- `PromptBuilder` for model context rendering.
- `LocalLLMClient` for llama-server/OpenAI-compatible local endpoints.
- `NextAction` JSON contract and parser.
- `ScriptRegistry` validation.
- `ScriptExecutionBridge` for bounded action execution.
- File, browser-simulated, office-stub, and shell action helpers.
- History and error logging.
- Repair policy with one structured repair attempt after parse/validation failures.
- Evaluation model registry.
- Repeated-trials runner.
- Behavioral analysis.
- Cross-scenario behavioral comparison.
- Resource/capacity estimate.
- Sequential orchestrator/executor group MVP in fake mode.
- Executor prompt guidance, executor repair attempts, and per-agent attempt artifacts for the group MVP.
- Repeated local orchestrator/executor group-trials wrapper and aggregate reports.
- Orchestrator/executor pair matrix comparison and prototype pair ranking.
- Heavy four-agent group scenario and cross-scenario pair matrix comparison.
- Heavy scenario error analysis and measured orchestrator/executor runtime/capacity probe.
- Optional GPU wrapper flags and a short GPU smoke comparison.
- Runtime profile config and bounded stress probe for candidate orchestrator/executor pairs.
- Final evaluation reports.

## 4. Project structure

| path | purpose |
|---|---|
| `src/agent/` | Main implementation: state, prompts, model client, action contracts, registry, runner, analysis modules. |
| `configs/` | Runtime/evaluation configs: agent state examples, roles, activity profiles, scenarios, model registry, script registry. |
| `docs/ai/` | Engineering and research documentation. |
| `experiments/` | Generated evidence artifacts from smoke runs, repeated trials, behavioral analysis and resource analysis. |
| `reports/experiments/` | Final human-facing reports and machine-readable final summary. |
| `scripts/` | CLI wrappers for server startup, scenario runs, repeated trials and analyses. |
| `tests/` | Offline pytest suite. |
| `models/gguf/` | Local-only GGUF model location. Model binaries are ignored by Git. |

`configs/` affects runtime behavior. `src/agent/` is implementation. `docs/ai/` is research/engineering documentation. `experiments/` contains reproducible evidence artifacts. `reports/experiments/` contains final reporting outputs.

## 5. Requirements

Tested environment:

- Windows PowerShell examples are used throughout this README.
- Python 3.12.
- Git.
- Optional: GitHub CLI (`gh`) for publishing.
- For real local runs: `llama.cpp` `llama-server.exe` or a compatible local OpenAI-style endpoint.
- Local GGUF models.

Python dependencies are listed in `requirements.txt`.

## 6. Fresh setup on another machine

```powershell
git clone <YOUR_REPO_URL>
cd local-llm-agent-lab

python -m venv .venv
.\.venv\Scripts\python.exe -m pip install --upgrade pip
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Run the test suite:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

At the time of the final experiment report, the full suite passed with 636 tests. After the publication consistency audit added repository publication checks, the full suite passed with 644 tests. After the orchestrator/executor group MVP, the full suite passed with 664 tests. After the local orchestrator/executor runtime configuration work, the full suite passed with 670 tests. After orchestrator plan hardening, the full suite passed with 675 tests. After executor prompt/repair hardening, the full suite passed with 679 tests. After repeated group-trials hardening, the full suite passed with 685 tests. After pair-matrix comparison, the full suite passed with 693 tests. After publication security docs, the full suite passed with 696 tests. After the heavy multi-agent scenario and cross-scenario pair comparison, the full suite passed with 703 tests. After the runtime/capacity candidate-pair probe, the full suite passed with 710 tests. After GPU wrapper/smoke support, the full suite passed with 716 tests. After bounded stress probe support, the full suite passed with 723 tests. After bounded stress workspace handling, the full suite passed with 728 tests. After final multi-agent report consolidation, the full suite passed with 731 tests.

## 7. Model setup

GGUF files are not included in the repository. Place local models manually under:

```text
models\gguf\first_model.gguf
models\gguf\second_model.gguf
```

Or edit:

```text
configs\evaluation_models.json
```

Current canonical mapping:

| model_id | model_name | required local path |
|---|---|---|
| `first_model` | `first_model.gguf` | `models\gguf\first_model.gguf` |
| `second_model` | `second_model.gguf` | `models\gguf\second_model.gguf` |

See `docs/ai/model_file_mapping.md` and `docs/ai/model_research_metadata.md` for publication-safe mapping and research metadata. See `docs/ai/adding_new_models.md` for adding third or test models.

The earlier internal experiment id `qwen2_5_3b_instruct_q4_k_m` may appear in historical artifacts. Current user-facing commands should use `second_model`; the old id is kept as a compatibility alias.

Preflight checks:

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py `
  --models-config configs\evaluation_models.json `
  --model-id first_model `
  --json
```

```powershell
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py `
  --models-config configs\evaluation_models.json `
  --model-id second_model `
  --json
```

## 8. Start llama-server

Use `-DryRun` first to verify model and server paths:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 -ModelId first_model -DryRun
```

Start the server:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 -ModelId first_model
```

For the second model:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 -ModelId second_model
```

Run the server in one terminal and experiments in another.

The Python virtual environment does not add `llama-server.exe` to PATH. The wrapper attempts to locate it automatically; if needed, pass `-ServerPath`.

## 9. Quick fake run without a model

Fake mode validates the pipeline without llama-server:

```powershell
.\.venv\Scripts\python.exe scripts\run_agent_scenario.py `
  --mode fake `
  --model-id first_model `
  --models-config configs\evaluation_models.json `
  --scenario configs\evaluation_scenarios\office_worker_basic_session.json `
  --out-dir experiments\scenario_runs\readme_fake_smoke `
  --run-id readme_fake_smoke `
  --max-steps 2 `
  --repair-attempts 1 `
  --force
```

## Orchestrator/executor group prototype

The first group-agent MVP uses `second_model` as the default orchestrator candidate and `first_model` as the default executor candidate. In fake mode it validates the full local artifact flow without calling `llama-server`: plan, assignment, executor action selection, registry validation, bounded execution, group history, and pair-level evaluation.

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_group.py `
  --mode fake `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_group_basic.json `
  --out-dir experiments\multi_agent\orchestrator_executor\fake_office_developer_group_v1 `
  --run-id fake_office_developer_group_v1 `
  --orchestrator-model-id second_model `
  --executor-model-id first_model `
  --max-group-steps 2 `
  --max-steps-per-agent 2 `
  --repair-attempts 1 `
  --execute-actions `
  --force
```

Main documentation: `docs/ai/orchestrator_executor_pipeline_v1.md`.

For local mode, the group runner supports separate endpoint overrides:

- `--orchestrator-base-url`
- `--executor-base-url`
- `--orchestrator-model-name`
- `--executor-model-name`

A controlled local follow-up requires either two local endpoints or a future clean sequential-switching handoff. The first two-endpoint attempt started `second_model` on port 8081 and `first_model` on port 8082, but it was blocked because the real orchestrator response was not valid complete JSON. The v2 repair run hardened the plan prompt, added plan-repair artifacts, obtained a valid plan, and reached two executor calls; both executor actions were rejected by validation before execution. The v3 executor hardening run added action guidance, executor repair, and `per_agent_attempts.jsonl`; it completed with two validated and executed local `read_file` actions. See `docs/ai/local_orchestrator_executor_poc_v1.md`, `docs/ai/local_orchestrator_executor_poc_blocker.md`, `docs/ai/local_orchestrator_executor_poc_v2_repair.md`, and `docs/ai/local_orchestrator_executor_poc_v3_executor_repair.md`.

## Repeated local orchestrator/executor group trials

The repeated group wrapper runs the same group scenario multiple times, preserves every trial folder, and writes aggregate pair metrics.

```powershell
.\.venv\Scripts\python.exe scripts\run_repeated_orchestrator_executor_trials.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_group_basic.json `
  --out-root experiments\multi_agent\orchestrator_executor\repeated_local_second_to_first_group_n3_v1 `
  --label repeated_local_second_to_first_group_n3_v1 `
  --trials 3 `
  --orchestrator-model-id second_model `
  --executor-model-id first_model `
  --orchestrator-port 8081 `
  --executor-port 8082 `
  --manage-servers `
  --max-group-steps 1 `
  --max-steps-per-agent 1 `
  --orchestrator-max-tokens 768 `
  --orchestrator-repair-attempts 1 `
  --repair-attempts 1 `
  --execute-actions `
  --continue-on-trial-failure `
  --force
```

Latest artifact root: `experiments/multi_agent/orchestrator_executor/repeated_local_second_to_first_group_n3_v1`. The N=3 run completed 3/3 trials with mean pair quality `0.890528`, mean execution success rate `1.0`, and zero recorded errors. This is one-pair/one-scenario robustness evidence, not a final recommendation.

## Pair matrix comparison

The pair matrix wrapper compares multiple orchestrator/executor combinations with the same repeated group-trial protocol. The latest matrix reused the existing `second_model -> first_model` N=3 artifact and ran the missing pairs locally.

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_pair_matrix.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_group_basic.json `
  --out-root experiments\multi_agent\orchestrator_executor\pair_matrix_office_developer_group_n3_v1 `
  --label pair_matrix_office_developer_group_n3_v1 `
  --pairs second_model:first_model,second_model:second_model,first_model:first_model,first_model:second_model `
  --existing-pair-run second_model:first_model=experiments\multi_agent\orchestrator_executor\repeated_local_second_to_first_group_n3_v1 `
  --trials 3 `
  --base-orchestrator-port 8081 `
  --base-executor-port 8082 `
  --manage-servers `
  --max-group-steps 1 `
  --max-steps-per-agent 1 `
  --orchestrator-max-tokens 768 `
  --orchestrator-repair-attempts 1 `
  --repair-attempts 1 `
  --execute-actions `
  --continue-on-pair-failure `
  --force
```

Latest basic-scenario artifact root: `experiments/multi_agent/orchestrator_executor/pair_matrix_office_developer_group_n3_v1`. `second_model -> first_model` ranked first for this scenario with prototype score `0.952618`; `second_model -> second_model` also completed 3/3 trials; both `first_model` orchestrator pairs failed at `orchestrator_plan_parse_failed`. This is scenario evidence, not a final production recommendation.

## Heavy multi-agent scenario

The heavier scenario uses four agents, two group steps, local fixtures, and an `artifact_workspace_only` write policy.

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_pair_matrix.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json `
  --out-root experiments\multi_agent\orchestrator_executor\pair_matrix_heavy_group_n3_workspace_policy_v1 `
  --label pair_matrix_heavy_group_n3_workspace_policy_v1 `
  --pairs second_model:first_model,second_model:second_model,first_model:first_model,first_model:second_model `
  --existing-pair-run second_model:first_model=experiments\multi_agent\orchestrator_executor\repeated_local_second_to_first_heavy_group_n3_workspace_policy_v1 `
  --trials 3 `
  --base-orchestrator-port 8081 `
  --base-executor-port 8082 `
  --manage-servers `
  --max-group-steps 2 `
  --max-steps-per-agent 1 `
  --orchestrator-max-tokens 1024 `
  --orchestrator-repair-attempts 1 `
  --repair-attempts 1 `
  --execute-actions `
  --continue-on-pair-failure
```

Heavy artifact root: `experiments/multi_agent/orchestrator_executor/pair_matrix_heavy_group_n3_workspace_policy_v1`. `second_model -> second_model` ranked first with prototype score `0.759188`; `second_model -> first_model` completed but recorded workspace-policy validation and repair failures; both `first_model` orchestrator pairs failed at `orchestrator_plan_parse_failed`.

Cross-scenario artifact root: `experiments/multi_agent/orchestrator_executor/cross_scenario_pair_matrix_workspace_policy_v1`. The simple scenario best pair is `second_model -> first_model`, while the heavy scenario best pair is `second_model -> second_model`; this is preliminary evidence only, not a final recommendation.

## Runtime/capacity probe for candidate pairs

The runtime probe measures short local RSS/CPU telemetry for selected orchestrator/executor pairs and writes a capacity estimate from measured pair RAM. It is not a concurrent stress test.

```powershell
.\.venv\Scripts\python.exe scripts\probe_orchestrator_executor_runtime.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --out-root experiments\multi_agent\orchestrator_executor\runtime_probe_candidate_pairs_v1 `
  --label runtime_probe_candidate_pairs_v1 `
  --pairs second_model:first_model,second_model:second_model `
  --scenarios simple=configs\multi_agent_scenarios\office_developer_group_basic.json,heavy=configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json `
  --trials 3 `
  --base-orchestrator-port 8081 `
  --base-executor-port 8082 `
  --manage-servers `
  --simple-max-group-steps 1 `
  --heavy-max-group-steps 2 `
  --max-steps-per-agent 1 `
  --simple-orchestrator-max-tokens 768 `
  --heavy-orchestrator-max-tokens 1024 `
  --orchestrator-repair-attempts 1 `
  --repair-attempts 1 `
  --execute-actions `
  --sample-interval-seconds 0.5 `
  --continue-on-pair-failure
```

Latest runtime artifact root: `experiments/multi_agent/orchestrator_executor/runtime_probe_candidate_pairs_v1`. In this probe, `second_model -> second_model` had the best preliminary quality/cost score (`0.687916`) and fewer heavy-scenario errors, while `second_model -> first_model` used less RAM and was slightly faster in the short run. See `docs/ai/orchestrator_executor_runtime_capacity_v1.md`.

## GPU runtime configuration and smoke

The start wrapper now supports optional GPU/runtime flags observed in the local `llama-server --help` output. Existing commands without GPU parameters still work.

Dry-run GPU command:

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\start_llama_server.ps1 `
  -ModelId second_model `
  -Port 8081 `
  -GpuLayers all `
  -MainGpu 0 `
  -SplitMode none `
  -DryRun
```

GPU smoke command:

```powershell
.\.venv\Scripts\python.exe scripts\run_gpu_smoke_orchestrator_executor.py `
  --models-config configs\evaluation_models.json `
  --scenario configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json `
  --out-root experiments\multi_agent\orchestrator_executor\gpu_smoke_second_to_second_heavy_v1 `
  --pair second_model:second_model `
  --trials 1 `
  --gpu-layers all `
  --main-gpu 0 `
  --split-mode none `
  --ctx-size 4096 `
  --max-group-steps 2 `
  --max-steps-per-agent 1 `
  --orchestrator-max-tokens 1024 `
  --execute-actions
```

Latest GPU smoke artifact root: `experiments/multi_agent/orchestrator_executor/gpu_smoke_second_to_second_heavy_v1`. Both baseline and GPU smoke completed. Wall-time ratio was `1.006842`, so this is a readiness check, not a speedup claim. See `docs/ai/gpu_runtime_configuration_v1.md`, `docs/ai/llama_server_gpu_flags_observed.md`, and `docs/ai/gpu_smoke_second_to_second_heavy_v1.md`.

## Bounded stress probe for candidate pairs

The bounded stress runner executes concurrent heavy group runs against managed local endpoints under explicit runtime profiles from `configs/runtime_profiles.json`.

```powershell
.\.venv\Scripts\python.exe scripts\run_orchestrator_executor_stress_probe.py `
  --models-config configs\evaluation_models.json `
  --runtime-profiles-config configs\runtime_profiles.json `
  --scenario configs\multi_agent_scenarios\office_developer_maintenance_group_heavy.json `
  --out-root experiments\multi_agent\orchestrator_executor\bounded_stress_candidate_pairs_v2 `
  --label bounded_stress_candidate_pairs_v2 `
  --pairs second_model:second_model,second_model:first_model `
  --profiles cpu_requested_device_none,gpu_full_offload `
  --concurrency-levels 1,2 `
  --runs-per-level 2 `
  --base-port 8081 `
  --max-group-steps 2 `
  --max-steps-per-agent 1 `
  --orchestrator-max-tokens 1024 `
  --orchestrator-repair-attempts 1 `
  --repair-attempts 1 `
  --execute-actions `
  --timeout-seconds 180 `
  --sample-interval-seconds 0.5 `
  --continue-on-failure `
  --force `
  --skipped-concurrency-levels 4 `
  --skip-reason "bounded v2 keeps level 4 skipped until levels 1 and 2 are interpreted"
```

Latest bounded stress artifact root: `experiments/multi_agent/orchestrator_executor/bounded_stress_candidate_pairs_v2`. v1 failed because the harness created Windows paths that were too long; v2 fixed the artifact layout and produced preliminary stress metrics. Stable concurrency 1 was observed only for `second_model -> second_model`; no stable concurrency 2 row was observed. See `docs/ai/bounded_stress_candidate_pairs_v1.md`, `docs/ai/bounded_stress_failure_analysis_v1.md`, and `docs/ai/bounded_stress_candidate_pairs_v2.md`.

## 10. Real local single scenario run

Start `llama-server` first, then run:

```powershell
.\.venv\Scripts\python.exe scripts\run_agent_scenario.py `
  --mode local `
  --model-id first_model `
  --models-config configs\evaluation_models.json `
  --scenario configs\evaluation_scenarios\office_worker_basic_session.json `
  --out-dir experiments\model_behavior\results\readme_first_model_run `
  --run-id readme_first_model_run `
  --execute-actions `
  --max-steps 5 `
  --repair-attempts 1 `
  --force
```

Expected artifacts include `manifest.json`, `steps.jsonl`, `attempts.jsonl`, `raw_model_outputs.jsonl`, `selected_actions.jsonl`, `validation_results.jsonl`, `execution_results.jsonl`, `history.jsonl`, `errors.jsonl`, `activity_evaluation.json`, `resource_summary.json`, and replay commands.

## 11. Repeated trials

```powershell
.\.venv\Scripts\python.exe scripts\run_repeated_model_trials.py `
  --mode local `
  --models-config configs\evaluation_models.json `
  --model-ids first_model,second_model `
  --scenario configs\evaluation_scenarios\office_worker_basic_session.json `
  --out-root experiments\model_behavior\repeated_trials\readme_office_worker_n3 `
  --label readme_office_worker_n3 `
  --trials 3 `
  --max-steps 5 `
  --repair-attempts 1 `
  --execute-actions `
  --manage-server `
  --force `
  --continue-on-trial-failure
```

## 12. Behavioral analysis

```powershell
.\.venv\Scripts\python.exe scripts\analyze_behavioral_trials.py `
  --trials-root experiments\model_behavior\repeated_trials\readme_office_worker_n3 `
  --out-dir experiments\model_behavior\analysis\readme_office_worker_analysis `
  --label readme_office_worker_analysis `
  --force
```

## 13. Cross-scenario analysis

The final cross-scenario report used these existing repeated-trial roots:

- `experiments\model_behavior\repeated_trials\office_worker_two_model_repair_n3_v1`
- `experiments\model_behavior\repeated_trials\developer_project_maintenance_two_model_repair_n3_v1`

Recreate the cross-scenario analysis:

```powershell
.\.venv\Scripts\python.exe scripts\compare_cross_scenario_behavior.py `
  --scenario-analysis office_worker=experiments\model_behavior\analysis\office_worker_two_model_behavioral_analysis_v1=experiments\model_behavior\repeated_trials\office_worker_two_model_repair_n3_v1 `
  --scenario-analysis developer_project_maintenance=experiments\model_behavior\analysis\developer_project_maintenance_two_model_behavioral_analysis_v1=experiments\model_behavior\repeated_trials\developer_project_maintenance_two_model_repair_n3_v1 `
  --out-dir experiments\model_behavior\cross_scenario\office_worker_developer_two_model_cross_scenario_v1 `
  --label office_worker_developer_two_model_cross_scenario_v1 `
  --force
```

## 14. Resource/capacity evaluation

The older resource evaluation is formula-based unless a runtime/concurrent probe is explicitly run.

```powershell
.\.venv\Scripts\python.exe scripts\evaluate_resource_capacity.py `
  --models-config configs\evaluation_models.json `
  --model-ids first_model,second_model `
  --repeated-trials-root office_worker=experiments\model_behavior\repeated_trials\office_worker_two_model_repair_n3_v1 `
  --repeated-trials-root developer_project_maintenance=experiments\model_behavior\repeated_trials\developer_project_maintenance_two_model_repair_n3_v1 `
  --cross-scenario-analysis experiments\model_behavior\cross_scenario\office_worker_developer_two_model_cross_scenario_v1 `
  --out-dir experiments\model_behavior\resources\resource_capacity_v1 `
  --label resource_capacity_v1 `
  --target-cpu-utilization-percent 70 `
  --reserved-system-ram-mb 4096 `
  --no-probe-runtime `
  --force
```

The newer orchestrator/executor runtime probe measured short local pair RSS/CPU telemetry and produced RAM-based group capacity estimates:

- artifact root: `experiments/multi_agent/orchestrator_executor/runtime_probe_candidate_pairs_v1`
- doc: `docs/ai/orchestrator_executor_runtime_capacity_v1.md`
- best preliminary quality/cost pair in the measured probe: `second_model -> second_model`
- GPU smoke root: `experiments/multi_agent/orchestrator_executor/gpu_smoke_second_to_second_heavy_v1`
- bounded stress root: `experiments/multi_agent/orchestrator_executor/bounded_stress_candidate_pairs_v2`
- still missing: stable concurrency 2 evidence and meaningful production GPU speedup/capacity measurement

## 15. Final reports

Report files:

- `reports/experiments/final_evaluation_report.md`
- `reports/experiments/final_multi_agent_research_report.md`
- `reports/experiments/manager_summary.md`
- `reports/experiments/project_usage_appendix.md`
- `reports/experiments/final_evaluation_summary.json`

Final summary:

- total trajectories: 12;
- `second_model` has better contract validity and latency in the current evidence base;
- `first_model` had some useful execution but is repair-dependent;
- both models show weak coherence and template-like behavior;
- multi-agent preliminary quality-focused pair: `second_model -> second_model`;
- multi-agent resource-balanced/simple-scenario pair: `second_model -> first_model`;
- final production model recommendation is not ready;
- historical single-agent formula capacity estimate: 11 agents, CPU-bound, low confidence;
- newer group runtime capacity estimate: preliminary only, RAM-based from short sequential telemetry, not a concurrent stress test.

## 16. Testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

At the time of the final experiment report, the full suite passed with 636 tests. After the publication consistency audit, the full suite passed with 644 tests. After the orchestrator/executor group MVP, the full suite passed with 664 tests. After the local orchestrator/executor runtime configuration work, the full suite passed with 670 tests. After orchestrator plan hardening, the full suite passed with 675 tests. After executor prompt/repair hardening, the full suite passed with 679 tests. After repeated group-trials hardening, the full suite passed with 685 tests. After pair-matrix comparison, the full suite passed with 693 tests. After publication security docs, the full suite passed with 696 tests. After the heavy multi-agent scenario and cross-scenario pair comparison, the full suite passed with 703 tests. After the runtime/capacity candidate-pair probe, the full suite passed with 710 tests. After GPU wrapper/smoke support, the full suite passed with 716 tests. After bounded stress probe support, the full suite passed with 723 tests. After bounded stress workspace handling, the full suite passed with 728 tests. After final multi-agent report consolidation, the full suite passed with 731 tests.

## 17. Publishing to GitHub

Security check:

- review `docs/security/publication_security_check.md`;
- rotate/revoke any token that was visible in IDE/editor context, even if it was outside the repository;
- never push before staged files and history pass the publication security check.

Before publishing:

- check `git status`;
- confirm `.venv/` is not tracked;
- confirm `models/gguf/*.gguf` is not tracked;
- confirm credentials/tokens are not tracked;
- avoid initializing the GitHub repository with a README if this local README already exists.

Option A: GitHub CLI

```powershell
gh auth login
gh repo create local-llm-agent-lab --private --source=. --remote=origin --push
```

For a public repository:

```powershell
gh repo create local-llm-agent-lab --public --source=. --remote=origin --push
```

Option B: create an empty repository in the GitHub web UI, then:

```powershell
git remote add origin https://github.com/<OWNER>/<REPO>.git
git branch -M main
git push -u origin main
```

SSH alternative:

```powershell
git remote add origin git@github.com:<OWNER>/<REPO>.git
git push -u origin main
```

If `origin` already exists:

```powershell
git remote -v
git remote set-url origin https://github.com/<OWNER>/<REPO>.git
```

## 18. Limitations

- Research prototype, not production-ready.
- Corrected bounded concurrent multi-agent stress smoke exists, but no stable concurrency 2 row was observed.
- Pair-matrix and runtime-probe local orchestrator/executor evidence covers two short group scenarios only.
- Browser behavior is confirmed at the fixture-backed autonomous runtime/scenario layer and by guarded Playwright/Chromium suite evidence against local loopback fixtures; production browser automation and external web/network behavior are not confirmed.
- Phase 10.2a offline bridge connects the autonomous runtime task board to the fixture-backed browser suite in scripted mode.
- Phase 10.2b offline CLI/config wraps that bridge for reproducible offline runs.
- Phase 10.2c adds bounded runtime trace evidence to the offline bridge summary.
- Phase 10.3a adds offline browser plan schema validation for future model-planned browser tasks.
- Phase 9 milestone freeze report: `docs/status/phase_9_milestone_freeze.md`.
- Office behavior is stub/file-based.
- No git/mail actions.
- Safety policy can reject developer-relevant paths.
- GGUF models are not included.
- Final production model recommendation is not made.
