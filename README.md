# Local LLM Agent Lab

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
- resource/capacity evaluation exists, but multi-agent capacity is formula-estimated, not stress-tested.

Important limitations:

- not production-ready;
- production full autonomous agent loop is not implemented;
- production action execution scheduler/runtime is not implemented;
- no measured multi-agent stress test;
- browser behavior is simulated-only;
- office behavior is stub/file-based;
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

At the time of the final experiment report, the full suite passed with 636 tests. After the publication consistency audit added repository publication checks, the full suite passed with 644 tests.

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

Capacity is formula-based unless a runtime/concurrent probe is explicitly run.

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

## 15. Final reports

Report files:

- `reports/experiments/final_evaluation_report.md`
- `reports/experiments/manager_summary.md`
- `reports/experiments/project_usage_appendix.md`
- `reports/experiments/final_evaluation_summary.json`

Final summary:

- total trajectories: 12;
- `second_model` has better contract validity and latency in the current evidence base;
- `first_model` had some useful execution but is repair-dependent;
- both models show weak coherence and template-like behavior;
- final model recommendation is not ready;
- capacity estimate: 11 agents, CPU-bound, low confidence.

## 16. Testing

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

At the time of the final experiment report, the full suite passed with 636 tests. After the publication consistency audit, the full suite passed with 644 tests.

## 17. Publishing to GitHub

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
- No measured multi-agent stress test.
- Browser behavior is simulated-only.
- Office behavior is stub/file-based.
- No git/mail actions.
- Safety policy can reject developer-relevant paths.
- GGUF models are not included.
- Final production model recommendation is not made.
