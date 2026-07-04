# Project Structure Audit for Report

Audit date: 2026-06-22  
Project path: `<repo>`  
Scope: strict technical audit against the curator/TZ requirements for a prototype that simulates normal user activity with a group of local LLM agents.  
Important boundary: this audit did not run `llama-server`, local models, browsers, network calls, or state-changing runtime benchmark commands.

Publication note: this is a historical audit snapshot from 2026-06-22. It intentionally preserves the project status, test count, and limitations observed at that time. For current publication status, use `README.md`, `reports/experiments/final_evaluation_report.md`, and `docs/publication_consistency_audit.md`.

## 1. Executive summary

По факту проект является Python-прототипом/лабораторией для локальных LLM-агентов: есть схемы состояния агента, роли, prompt/NextAction контракт, адаптер к OpenAI-compatible `llama-server`, реестр параметризуемых действий, validation/safety слой, отдельный execution bridge, история/ошибки, stop criteria, recovery loop, role-constrained trajectory runner, multi-agent smoke orchestrator, activity profiles и evaluator.

Стадия проекта: основная инфраструктура до блока `experiments` реализована и покрыта тестами. Это подтверждается файлами `src/agent/*.py`, `configs/*.json`, `docs/ai/*.md`, `tests/*.py` и результатом `.venv\Scripts\python.exe -m pytest -q`: `567 passed in 0.58s`.

Проект нельзя считать завершившим экспериментальный этап из ТЗ. В `README.md` прямо указано, что final behavioral evaluator stack, production multi-agent scheduler и full autonomous agent loop не являются финально реализованными production capabilities. `docs/ai/experiment_readiness_audit.md` также говорит, что readiness audit не заменяет experiments.

К этапу experiments проект готов как инфраструктурный прототип с yellow/conditional green-light: есть readiness gate, сценарии, профили, fixture-based evaluation и runtime baseline artifacts. Но перед управленческим заявлением о результате экспериментов нужны реальные траектории локальных моделей, behavioral metrics, model comparison по сценариям и capacity/resource estimates для группы агентов.

Главные риски перед продолжением:

- Автономный цикл выбора, исполнения, обновления состояния, stop criteria и записи истории собран по модулям, но не подтверждён как единый production loop; `AgentRunnerConfig` запрещает `execute_actions=True`.
- Multi-agent слой является smoke/scaffolding: `MultiAgentOrchestratorSmoke` последовательно вызывает runner factory, но нет production scheduler/capacity control.
- Browser actions simulated-only; office actions являются stub/Markdown/TXT/JSON operations, а не автоматизацией офисных приложений.
- Реальные behavioral experiments с локальными моделями не найдены; есть runtime smoke/baseline/comparison artifacts, но они не доказывают нормальность поведения.
- Числа latency/CPU/RAM есть только для fixed-prompt runtime baselines, не для автономных multi-step/multi-agent траекторий.

## 2. Repository map

| path | type | purpose | evidence | comments |
|---|---|---|---|---|
| `README.md` | docs | Project framing, current status, quick commands, architecture flow | File exists; mentions local LLM agents, roles/resources/constraints/scripts/history, and not-final capabilities | `git status --short` shows `README.md` modified |
| `tz.txt` | docs/other | Local TZ file | File exists at repo root | Terminal displayed mojibake, so this audit primarily used the user-provided TZ context plus repository facts |
| `pyproject.toml` | config | Python project metadata and pytest config | Defines `testpaths = ["tests"]`, `python_files = ["test_*.py"]`, `requires-python >=3.11` | No console scripts found |
| `requirements.txt` | config | Dependency list | Contains `httpx`, `pydantic`, `pytest`, `psutil`, `rich` | Global Python lacks pytest; `.venv` has it |
| `src/agent/` | code | Core agent modules | 35 files excluding pycache | Main implementation area |
| `src/agent/scripts/` | code | Executable/simulated activity helpers | `file_activity.py`, `browser_activity.py`, `office_document_activity.py`, `shell_command_activity.py` | File/shell can execute constrained operations; browser/office are simulated/stub |
| `configs/` | config | Example configs for state, roles, registry, runtime, scenarios, profiles | 32 files | Includes roles, activity profiles, evaluation scenarios |
| `configs/roles/` | config | Role templates | `developer.example.json`, `office_worker.example.json`, `student_researcher.example.json` | Role constraints include allowed actions and file roots |
| `configs/activity_profiles/` | config | Normal activity profiles | `developer.json`, `office_worker.json`, `student_researcher.json` | Used by evaluator and stop criteria |
| `configs/evaluation_scenarios/` | config | Scenario specs | 4 scenario files including `mixed_roles_multi_agent_session.json` | Scenario configs exist; execution harness for real local-model scenarios not found |
| `docs/ai/` | docs | Design docs for implemented components | 39 files before this report | Includes contracts, registry docs, runtime docs, evaluation readiness docs |
| `docs/ai/diagrams/` | docs | Mermaid diagrams | `architecture_data_flow_v1.mmd`, `architecture_layers_v1.mmd` | Tested by `tests/test_architecture_docs.py` |
| `tests/` | tests | Unit/contract/fixture tests | 39 test files; collect-only found 567 tests | Full run passed in `.venv` |
| `tests/fixtures/registry/` | fixtures | Registry validation fixtures | Valid/invalid registries and next actions | Used by registry fixture tests |
| `tests/fixtures/behavioral_trajectories/` | fixtures | Synthetic behavioral trajectories | Normal/abnormal role trajectories | Used by behavioral evaluator tests |
| `scripts/` | code/CLI | Runtime smoke/baseline/archive/comparison CLIs | 4 Python scripts | Real runs call local `llama-server`; only `--help` was run |
| `prompts/smoke/agent_next_action_v1.txt` | config/docs | Fixed smoke prompt | File exists | Used by runtime smoke/baseline scripts |
| `experiments/smoke/local_llama_server_smoke_v1/` | logs/fixtures | Archived local llama-server smoke artifact | Contains `manifest.json`, `raw_smoke.json`, prompt/output/readme | Preliminary runtime evidence, not final behavioral experiment |
| `experiments/baselines/local_runtime_baseline_v1/` | logs/reports | Runtime baseline for first model | `summary.json`: 3/3 successful fixed-prompt calls | Resource-only, one prompt |
| `experiments/baselines/second_model_runtime_baseline_v1/` | logs/reports | Runtime baseline for second model | `summary.json`: 3/3 successful fixed-prompt calls | Worktree shows modified files here |
| `experiments/comparisons/two_model_runtime_comparison_v1/` | reports | Numeric runtime comparison | `comparison.json`, `comparison.md` | Guardrails say numeric only, no semantic quality proof |
| `logs/smoke/` | logs | Smoke log location | `logs/smoke/README.md` plus existing log files counted | Not used in this audit except inventory |
| `models/gguf/` | other | Local GGUF model location | `models/gguf/README.md`, `MODELS.md` | GGUF files not committed; real model files not inspected |
| `data/` | other | Data directory | не найдено | No `data` directory at repo root |
| `reports/` | reports | Final reports directory | не найдено | Readiness audit warns `reports/experiments` missing |
| `Makefile` | config/CLI | Make commands | не найдено | No Makefile found |
| `package.json` | config | JS package metadata | не найдено | Not a JS project |
| `docker-compose.*` | config | Container runtime | не найдено | No docker compose file found |
| project `.sh` / `.ps1` scripts | CLI | Shell entrypoints | не найдено in project tree outside `.venv` | `.venv\Scripts\Activate.ps1` exists but is environment infrastructure, not project entrypoint |

## 3. Implemented architecture

Fact-based pipeline from repository:

`configs/orchestrator.example.json` / role configs -> `AgentState` -> `PromptBuilder` -> `LocalLLMClient` -> `NextAction` JSON -> `ActionSelector` / `ScriptRegistry` validation -> `ScriptExecutionBridge` -> script helper result -> `script_runner_errors` normalization -> `ExecutionHistoryLogger` -> `ActivityTrajectoryEvaluator` / model behavior harness.

| pipeline link | exists in code | main file/class/function | what it does | evidence | limitations |
|---|---:|---|---|---|---|
| Orchestrator/config | yes | `src/agent/orchestrator.py::Orchestrator`, `configs/orchestrator.example.json` | Runs one step or sequential list of agent states | `tests/test_orchestrator_agent_boundary.py` passed | Simple sequential boundary, not production scheduler |
| Initial agent state | yes | `src/agent/state.py::AgentState`, `load_agent_state` | Defines role, objective, environment, resources, constraints, available actions, history | `configs/agent_state.example.json`, `tests/test_agent_state.py` | One example state re-used across roles in scenarios; state is not automatically derived per scenario in a real harness |
| Prompt/context rendering | yes | `src/agent/prompt_contract.py::PromptBuilder` | Builds system/user messages, includes limited history and JSON contract | `tests/test_prompt_contract.py` | Prompt truncates by count (`include_history_limit=5`), not token budget |
| Local model adapter | yes | `src/agent/llm_client.py::LocalLLMClient` | Calls `base_url/chat/completions` using `httpx`, parses assistant JSON | `tests/test_llm_client.py` with mocked `httpx.Client` | Real server not tested in unit run; depends on external `llama-server` |
| Next-action JSON contract | yes | `src/agent/schemas.py::NextAction`, `src/agent/action_contract.py::parse_next_action_text` | Requires `{action, parameters, reason, expected_result}`; forbids extra fields | `tests/test_next_action_contract.py`, `tests/test_schemas.py` | Contract validates shape only, not semantic legality |
| Validation | yes | `src/agent/script_registry.py::validate_next_action_against_registry`, `ActionSelector` | Checks unknown action, missing/wrong params, unsafe paths/commands, role constraints | `tests/test_script_registry.py`, `tests/test_script_registry_loader_validator.py` | URL host safety for browser is mostly in action helper; registry accepts `https://example.com` at registry level |
| Script runner | partial | `src/agent/script_execution_bridge.py::ScriptExecutionBridge` | Dispatches selected actions to file/browser/office/shell helpers | `tests/test_script_execution_bridge.py` | Bridge supports only 7 registry actions; not integrated into `AgentRunner` autonomous loop by default |
| Result normalization | yes | `src/agent/script_runner_errors.py` | Converts raw script errors to normalized categories/severity/retryability | `tests/test_script_runner_error_normalization.py` | Normalization covers known script error names; real app/browser failures not covered |
| History log | yes | `src/agent/execution_history.py::ExecutionHistoryLogger` | Writes JSONL history/error records | `tests/test_execution_history_error_log.py` | Logging is opt-in (`write_history=False` defaults in bridge/trajectory configs); no evidence of real persisted autonomous runs |
| Evaluator/metrics | partial | `src/agent/activity_evaluator.py`, `model_behavior_evaluation.py` | Scores synthetic/fixture trajectories for role fit, diversity, repetition, sequences, history usage | `tests/test_normal_activity_trajectory_evaluator.py`, `tests/test_model_behavior_evaluation.py` | Evaluates provided trajectories/actions; no real local-model scenario execution results found |

## 4. Alignment with ТЗ

| ТЗ requirement | current status | evidence path | comments | what is needed before green light |
|---|---|---|---|---|
| Local LLM chooses next action | implemented/partial | `src/agent/llm_client.py`, `src/agent/action_selector.py`, `scripts/run_llama_smoke.py` | Adapter exists and runtime artifacts show fixed-prompt smoke/baseline; unit tests mock HTTP | Run real model through scenario harness and save trajectories |
| Agent works autonomously after initialization | partial | `src/agent/agent.py`, `src/agent/runner.py`, `src/agent/role_constrained_trajectory.py` | Agent can decide; trajectory runner can do multi-step selection-only; `AgentRunner` forbids action execution | Integrate selection -> execution -> state update -> stop criteria -> history in one safe loop |
| Group of agents | partial | `src/agent/multi_agent_orchestrator.py`, `configs/evaluation_scenarios/mixed_roles_multi_agent_session.json` | Smoke orchestrator exists, sequential, runner-factory based | Real multi-agent run with isolated histories, shared resource policy, capacity measurement |
| User roles | implemented | `src/agent/role_template.py`, `configs/roles/*.json` | Three roles: developer, office worker, student researcher | Role-specific initial states should be generated/validated for scenarios |
| Available resources | implemented | `src/agent/state.py::AgentResources`, role configs | Files/directories/endpoints/tools represented | Confirm real environment resource mapping for experiments |
| Environment constraints | implemented | `AgentConstraints`, `RoleConstraintProfile`, registry safety specs | no internet/model download, file roots, action allow/deny lists | Add experiment-specific resource constraints and capacity boundaries |
| Parameterized scripts as allowed actions | implemented | `configs/script_registry.example.json`, `src/agent/script_registry.py` | 7 actions with parameter specs and safety | Expand registry if git/mail/real app actions are required |
| Scripts are not rigid scenarios | implemented | `ScriptRegistry`, `ActionSelector`, role/scenario configs | Registry defines allowed parameterized actions; scenarios define expectations, not fixed action sequence | Validate this with real model trajectories |
| Browser activity | partial/mock | `src/agent/scripts/browser_activity.py` | `simulated_only=True`; no browser opened, no network used | Decide whether simulated browser is enough or implement real browser automation |
| File activity | implemented | `src/agent/scripts/file_activity.py` | Read/create/append/list with safe roots | Confirm safe workspace roots for real runs |
| Office documents | partial/stub | `src/agent/scripts/office_document_activity.py` | Creates/reads/appends Markdown/TXT/JSON stubs; no office app opened | Implement real office automation only if required; otherwise document stub boundary |
| Simple shell commands | implemented/limited | `src/agent/scripts/shell_command_activity.py` | Allowlisted commands only; `shell=False`; blocked tokens | Confirm whether benchmark/test commands are sufficient normal activity |
| git/mail/other optional apps | missing | не найдено | No git/mail action implementation or registry entries | Add optional actions only if needed by experiment design |
| History of actions | implemented/partial | `AgentState.history`, `execution_history.py`, `history_aware_selection.py` | In-memory state history and JSONL logger exist | Use logger in real autonomous runs and persist trajectories |
| Errors | implemented | `script_runner_errors.py`, `execution_history.py`, `recovery.py`, `recovery_loop.py` | Normalized categories and recovery decisions exist | Exercise errors with real local model/output failures |
| Stop criteria | implemented/partial | `src/agent/autonomous_stop_criteria.py` | Criteria for max steps, failures, repetition, unsafe actions, normality | Integrate stop evaluator into full run loop |
| Behavioral evaluation | partial | `activity_profile.py`, `activity_evaluator.py`, fixtures | Evaluator works on fixture/synthetic trajectories | Run evaluator on real model trajectories |
| Model comparison readiness | partial | `model_behavior_evaluation.py`, `configs/model_behavior_evaluation.example.json`, runtime comparison artifacts | Harness supports synthetic results; runtime comparison exists | Produce behavior comparison numbers across models |
| Resource/capacity formula readiness | partial | `scripts/run_runtime_baseline.py`, scenario resource plans | CPU/RAM/latency captured for fixed prompt; scenario has capacity flags | Add multi-agent capacity formula and measurements |
| Final report readiness | partial | `README.md`, `architecture_report.md`, `docs/ai/*`, experiments artifacts | Enough material for technical status report | Missing real experiments, capacity, failure limitations |

## 5. Runtime and local model integration

Chosen runtime: `llama.cpp / llama-server`, OpenAI-compatible API style. Evidence: `configs/runtime.local.example.json` sets `runtime.name = llama.cpp`, `mode = llama-server`, `base_url = http://127.0.0.1:8080/v1`, `api_style = openai_compatible`.

Model connection:

| item | status | evidence |
|---|---|---|
| Model adapter | implemented | `src/agent/llm_client.py::LocalLLMClient` posts to `/chat/completions` |
| Model id/name | configurable | `LocalLLMClient(model_name=...)`, CLI `--model-name`, `configs/models.local.example.json` |
| Model path metadata | documented/configured | `configs/models.local.example.json`, `docs/ai/model_registry.md`, `models/gguf/README.md` |
| CLI wrapper | implemented | `scripts/run_llama_smoke.py`, `scripts/run_runtime_baseline.py`, `scripts/compare_runtime_baselines.py`, `scripts/archive_smoke_run.py` |
| Smoke test artifact | present | `experiments/smoke/local_llama_server_smoke_v1/manifest.json` |
| CPU-only assumption | present | `configs/runtime.local.example.json` has `first_assumption = CPU-first`, `gpu_required = false`; scenarios set `resource_plan.cpu_only = true` |
| Latency/RAM/CPU data | partial | `experiments/baselines/*/summary.json` contains wall time, CPU, RAM deltas for 3 fixed-prompt calls |
| Real model behavioral data | не найдено | No saved scenario/model-behavior result files under `experiments/model_behavior/results`; readiness audit warns missing optional behavior results dir |

Existing runtime numbers from committed artifacts:

| artifact | model | runs | success | wall time avg | CPU avg | RAM delta avg | limits |
|---|---|---:|---:|---:|---:|---:|---|
| `experiments/baselines/local_runtime_baseline_v1/summary.json` | `first_model.gguf` | 3 | 3 | `0.374865s` | `3.616667%` | `1.341 MB` | fixed prompt only, no semantic validation |
| `experiments/baselines/second_model_runtime_baseline_v1/summary.json` | `qwen2.5-3b-instruct-q4_k_m.gguf` | 3 | 3 | `0.387236s` | `2.622333%` | `-4.348667 MB` | fixed prompt only, worktree shows modified artifact files |
| `experiments/comparisons/two_model_runtime_comparison_v1/comparison.json` | first vs second | 3 each | 3 each | first `0.374865s`, second `0.413826s` in comparison artifact | numeric comparison only | comparison artifact differs from current second summary values | Guardrails explicitly say no semantic action correctness and no multi-agent load |

What is still missing for experiments:

- Real local-model trajectories for configured roles/scenarios.
- Model-by-model behavioral scores (`normal_activity_score`, role compliance, diversity, repetition) from actual runs.
- Per-step selection latency and total step latency inside autonomous loop.
- Multi-agent CPU/RAM/capacity estimate.
- Failure logs from malformed JSON, invalid actions, validation failures, execution errors in real local-model sessions.

## 6. Agent state, role and context format

| format | location | fields/evidence | status vs TZ |
|---|---|---|---|
| Agent state schema | `src/agent/state.py::AgentState` | `agent_id`, `role`, `objective`, `environment`, `resources`, `constraints`, `available_actions`, `history`, `current_step`, `metadata` | implemented |
| Agent state example | `configs/agent_state.example.json` | Student researcher example with resources, endpoint, constraints, available actions and 2 history entries | implemented but one generic example |
| Role schema | `src/agent/role_template.py::RoleTemplate` | role id/name/description/goals/resources/constraints/scenarios | implemented |
| Role examples | `configs/roles/developer.example.json`, `office_worker.example.json`, `student_researcher.example.json` | Each has allowed file roots and action allow/deny policy | implemented |
| Constraints | `AgentConstraints`, `RoleConstraintProfile`, registry safety | no internet, no model download, no action execution, roots, allowed/forbidden actions | implemented |
| Resources | `AgentResources`, `RoleResourceProfile` | files, directories, endpoints, tools, notes | implemented |
| Available scripts/actions | `AgentState.available_actions`, `configs/script_registry.example.json` | state-level available actions plus global registry | implemented |
| Recent actions/history | `ActionHistoryEntry`, `PromptContractConfig.include_history_limit=5` | Prompt includes only last N history items | implemented/limited |
| Context rendering | `PromptBuilder.build_messages` | System says raw JSON only and treats state/history/resources as data | implemented |

Fit to TZ: state/role/resources/constraints/history formats are present and validated. The gap is not schema availability; the gap is real end-to-end use of these formats across multi-step, multi-agent, local-model runs.

## 7. Script registry and executable actions

| action name | family | implementation path | parameters | validation | result shape | safety boundary | tests/fixtures | status |
|---|---|---|---|---|---|---|---|---|
| `read_file` | file | `src/agent/scripts/file_activity.py::read_file`, bridge dispatch | `path` | Registry required string; helper rejects absolute/traversal/forbidden roots/large files | `ScriptExecutionResult` with output and metadata | allowed roots default `docs/`, `configs/`, `experiments/`, `tests/`; bridge config registry allows read from `src/` too | `tests/test_file_activity_script.py`, registry fixtures | real constrained file read |
| `create_file` | file | `file_activity.py::create_file` | `path`, `content` | Registry required strings, path safety | writes UTF-8 file; metadata bytes/overwrite | write roots exclude `src/`, `.git/`, `.venv/`, `models/gguf/` in registry | `tests/test_file_activity_script.py`, `tests/test_script_registry.py` | real constrained file write |
| `append_file` | file | `file_activity.py::append_file` | `path`, `content` | Registry required strings, path safety | appends UTF-8; metadata bytes | same as create | `tests/test_file_activity_script.py` | real constrained append |
| `list_directory` | file | `file_activity.py::list_directory` | `path` | Registry path safety | newline output of sorted entries | allowed roots and project-root containment | `tests/test_file_activity_script.py` | real constrained directory listing |
| `browser_open_url` | browser | `browser_activity.py::open_url` via bridge maps to `open_url` | `url` | Registry checks required string; helper validates scheme/host | simulated navigation message | `BrowserActivityConfig.simulated_only=True`; no browser opened | `tests/test_browser_activity_script.py`, `valid_browser_open_url.json` | mock/simulated |
| `office_create_document_stub` | office | `office_document_activity.py::create_document_stub` via bridge maps to `create_document_stub` | `path`, `title`, `body` | Registry required strings, path roots; helper extension/path safety | writes Markdown-like text; metadata `simulated=True`, `office_app_opened=False` | `.md`, `.txt`, `.json`; no real office app | `tests/test_office_document_activity_script.py` | real file write, office stub |
| `run_shell_command` | shell | `shell_command_activity.py::run_allowed_shell_command` | `command` | Registry allowlist and forbidden substrings; helper allowlist and blocked tokens | stdout/stderr/returncode/wall time | `shell=False`, allowlist only; blocks destructive/network/shell tokens | `tests/test_shell_command_activity_script.py` | real constrained shell execution |

Additional helper actions exist but are not registry/bridge actions in `configs/script_registry.example.json`: `search_web`, `read_page_summary`, `fill_form_stub`, `append_document_section`, `read_document_stub`, `extract_document_outline_stub`, `create_table_note_stub`, `simulate_shell_command`. They are implemented in helper modules, but current registry/bridge exposes only the actions listed above.

git/mail/other actions: не найдено.

## 8. Action selection and validation

Expected JSON from LLM:

```json
{
  "action": "string",
  "parameters": {},
  "reason": "string",
  "expected_result": "string"
}
```

Contract locations:

- `src/agent/schemas.py::NextAction` requires `action`, `reason`, `expected_result` non-empty and forbids extra fields via `ConfigDict(extra="forbid")`.
- `src/agent/action_contract.py::parse_next_action_text` parses raw JSON text and raises `NextActionJSONError` or `NextActionValidationError`.
- `src/agent/prompt_contract.py::NEXT_ACTION_JSON_SCHEMA_TEXT` instructs raw JSON only: no Markdown, no prose, no arrays, no multiple actions.

Validation behavior:

| case | handling | evidence |
|---|---|---|
| Malformed JSON | `LocalLLMClient.parse_next_action_text` maps to `LocalLLMJSONError`; `ActionSelector.select_action` returns `selection_failed` with error type | `src/agent/llm_client.py`, `src/agent/action_selector.py`, `tests/test_next_action_contract.py` |
| JSON wrong schema | maps to `LocalLLMValidationError` / `selection_failed` | `tests/test_llm_client.py`, `tests/test_action_selector_prototype.py` |
| Unknown action | `validate_next_action_against_registry` returns `unknown_action`, selector returns `validation_failed` | `tests/test_script_registry.py` |
| Missing required parameter | registry returns `missing_required_parameter` | `tests/test_script_registry_loader_validator.py` |
| Wrong parameter type | registry returns `wrong_parameter_type` | `tests/test_script_registry_loader_validator.py` |
| Unsafe path | registry/helper rejects absolute, drive-prefixed, traversal, forbidden roots | `src/agent/script_registry.py`, `file_activity.py`, `office_document_activity.py` |
| Unsafe shell command | registry/helper rejects forbidden substrings, non-allowlisted commands and blocked tokens | `script_registry.py`, `shell_command_activity.py` |
| Repetition prevention | `HistoryAwareSecondActionRunner` and `RoleConstrainedTrajectoryRunner` detect exact action+params repeats | `tests/test_history_aware_second_action.py`, `tests/test_role_constrained_trajectory_run.py` |
| Role constraints | Registry validation applies `RoleTemplate.constraints.allowed_action_names`, `forbidden_action_names`, allowed/forbidden file roots | `src/agent/script_registry.py`, `tests/test_role_template.py`, `tests/test_script_registry.py` |

Limitations:

- Registry validation does not fully validate browser URL host policy; helper does this at execution time.
- Prompt says not to invent actions, but final enforcement is registry validation, not model behavior control.
- Repetition detection is exact action+parameters, not semantic repetition detection beyond evaluator metrics.

## 9. History, memory and error handling

History locations:

- In-memory state: `src/agent/state.py::AgentState.history`, list of `ActionHistoryEntry`.
- Prompt history: `PromptBuilder` includes last `include_history_limit=5` entries by count.
- Persistent logs: `src/agent/execution_history.py::ExecutionHistoryLogger` writes `logs/execution/history.jsonl` and `logs/execution/errors.jsonl` by default.
- Selection trajectory history: `src/agent/role_constrained_trajectory.py` appends selected actions into copied `AgentState`.
- Bridge execution history: `ScriptExecutionBridgeConfig.write_history` default is `False`; if enabled and logger/run_id/agent_id are supplied, bridge writes normalized execution results.

Logged fields:

- `ExecutionHistoryRecord`: `record_id`, `record_type`, `status`, `created_at`, `run_id`, `agent_id`, `step_index`, `action`, `next_action`, `summary`, `details`, `error_id`, `metadata`.
- `ExecutionErrorRecord`: `error_id`, `created_at`, `run_id`, `agent_id`, `step_index`, `action`, `error_type`, `error_message`, `severity`, `retryable`, `recovery_category`, `source`, `details`, `metadata`.

Error handling:

- LLM/network/schema failures: `LocalLLMClientError` subclasses in `src/agent/llm_client.py`.
- Validation failures: `ScriptValidationIssue` and `ScriptValidationResult`.
- Script execution failures: normalized by `src/agent/script_runner_errors.py`.
- Recovery: `src/agent/recovery.py` and `src/agent/recovery_loop.py` map categories such as invalid JSON, unsafe action, permission denied, llama server unreachable, repeated action loop.

Stop criteria:

- `src/agent/autonomous_stop_criteria.py` includes max steps, consecutive/total failures, repeated action, validation failure, unsafe action, recovery decisions, no progress, forbidden-for-normality and excessive atypical actions.
- Tests: `tests/test_autonomous_session_stop_criteria.py`.

Weak points:

- `ExecutionHistoryConfig.max_message_length` and `truncate_text` exist, but search evidence only shows the helper; no broad evidence that every history/error path truncates large fields.
- Persistent logging is opt-in and not proven in real local-model trajectories.
- `AgentRunner` does not currently execute actions, so execution history is not naturally generated by the main runner.

## 10. Orchestrator and multi-agent readiness

Orchestrator status:

- Basic orchestrator exists: `src/agent/orchestrator.py::Orchestrator` runs one agent step or sequential steps for a list of `AgentState`.
- Multi-agent smoke exists: `src/agent/multi_agent_orchestrator.py::MultiAgentOrchestratorSmoke`.
- Config exists: `configs/multi_agent_orchestrator_smoke.example.json`.
- Test exists: `tests/test_multi_agent_orchestrator_smoke.py`.
- Multi-agent evaluation scenario exists: `configs/evaluation_scenarios/mixed_roles_multi_agent_session.json`.

How agents are initialized:

- `MultiAgentRunSpec` takes `agent_id`, `agent_state`, optional `role_template_id`.
- The smoke orchestrator requires `runner_factory`, then calls `runner.run_trajectory(spec.agent_state, run_id=run_id)` sequentially.

History isolation:

- Per-agent results are separated by `agent_id`.
- `RoleConstrainedTrajectoryRunner` copies initial state and returns per-agent final state.
- Persistent history logger can include `agent_id`, but multi-agent smoke does not show a complete shared log policy by default.

Readiness assessment:

- Ready for smoke-level multi-agent selection experiments with fake/mocked or injected runners.
- Not yet ready as production group-agent scheduler: no parallel scheduling, no shared resource arbitration, no capacity model, no real multi-agent local-model run artifact found.

Needed before real multi-agent experiments:

- Scenario runner that creates role-specific states from `configs/evaluation_scenarios/*.json`.
- End-to-end local-model loop per agent.
- Per-agent and aggregate history/log output.
- Resource sampling per agent and shared `llama-server`.
- Capacity estimate formula and measured run with N agents.

## 11. Behavioral evaluation readiness

Implemented pieces:

| component | evidence | what it evaluates |
|---|---|---|
| Activity profiles | `configs/activity_profiles/*.json`, `src/agent/activity_profile.py` | Typical, atypical, forbidden-for-normality actions, expected sequences, repetition/diversity policies |
| Trajectory evaluator | `src/agent/activity_evaluator.py::ActivityTrajectoryEvaluator` | Role fit, diversity, repetition, expected sequence coherence, history usage, normal activity score |
| Behavioral fixtures | `tests/fixtures/behavioral_trajectories/` | Normal and abnormal trajectories for office/developer/student roles plus multi-agent fixture |
| Evaluation scenarios | `configs/evaluation_scenarios/*.json`, `src/agent/evaluation_scenarios.py` | Scenario mode, agents, stop policy, metrics, expected behavior, resource plan |
| Model behavior harness | `src/agent/model_behavior_evaluation.py` | Synthetic/dry/local-model result schema and verdict derivation |
| Readiness audit | `src/agent/experiment_readiness_audit.py` | Checks required artifacts and semantic loading without running models |

Safe evaluation without LLM:

- Fixture evaluation works: `tests/test_behavioral_validation_fixtures.py`.
- Synthetic model behavior result building works: `tests/test_model_behavior_evaluation.py`.
- Readiness audit run in this audit returned: `ready=True`, `required_pass_count=51`, `required_fail_count=0`, `warning_count=2`, warnings for missing `experiments/model_behavior/results` and `reports/experiments`.

Current limitations:

- Evaluator quality depends on manually curated activity profiles and fixture expectations.
- No evidence found of evaluator results from actual local-model trajectories.
- No saved `experiments/model_behavior/results` directory found.
- Model comparison readiness is structural, not completed experimental evidence.

## 12. Tests and verification

Full verification result:

- Global command `python -m pytest --collect-only -q` failed: `No module named pytest`.
- Local virtualenv command `.venv\Scripts\python.exe -m pytest --collect-only -q` succeeded: `567 tests collected in 0.26s`.
- Local virtualenv command `.venv\Scripts\python.exe -m pytest -q` succeeded: `567 passed in 0.58s`.

| test file | what it verifies | depends on local model | safe offline | result if executed | gaps |
|---|---|---:|---:|---|---|
| `tests/test_action_selector_prototype.py` | selector config, selection/validation outcomes | no | yes | passed | mocked LLM/client behavior |
| `tests/test_action_validation_cases.py` | action validation fixture suite | no | yes | passed | contract probe not real model |
| `tests/test_agent_runner_skeleton.py` | runner config and selection-only run behavior | no | yes | passed | confirms execution disabled |
| `tests/test_agent_state.py` | AgentState schema/loading/history rules | no | yes | passed | example-state only |
| `tests/test_architecture_docs.py` | README/architecture docs/diagrams | no | yes | passed | docs checks only |
| `tests/test_archive_smoke_run.py` | archive helper functions | no | yes | passed | no real archive command run |
| `tests/test_autonomous_session_stop_criteria.py` | stop criteria decisions | no | yes | passed | not integrated in live loop |
| `tests/test_behavioral_validation_fixtures.py` | behavioral fixtures and evaluator expectations | no | yes | passed | fixture-based only |
| `tests/test_browser_activity_script.py` | browser URL validation and simulated browser results | no | yes | passed | no real browser |
| `tests/test_compare_runtime_baselines.py` | comparison helpers | no | yes | passed | no new comparison command run |
| `tests/test_evaluation_scenario_v1.py` | scenario schema and references | no | yes | passed | no scenario execution |
| `tests/test_execution_history_error_log.py` | JSONL logger and error records | no | yes | passed | temp-path logs only |
| `tests/test_experiment_readiness_audit.py` | readiness audit checks | no | yes | passed | audit does not run models |
| `tests/test_failure_recovery_policy.py` | recovery policy mappings | no | yes | passed | policy only |
| `tests/test_file_activity_script.py` | file action safety and execution | no | yes | passed | tmp-path only |
| `tests/test_history_aware_second_action.py` | second-action history and repeat detection | no | yes | passed | fake selector |
| `tests/test_llm_client.py` | local LLM client parsing and mocked HTTP | no | yes | passed | HTTP mocked |
| `tests/test_models_config.py` | model config presence/shape | no | yes | passed | no GGUF verification |
| `tests/test_model_behavior_evaluation.py` | model behavior result/harness schemas | no | yes | passed | synthetic only |
| `tests/test_multi_agent_orchestrator_smoke.py` | multi-agent smoke orchestration | no | yes | passed | fake runner |
| `tests/test_next_action_contract.py` | NextAction JSON contract parsing | no | yes | passed | no semantic registry check |
| `tests/test_normal_activity_profile_schema.py` | activity profile schema/configs | no | yes | passed | profile quality is curator-defined |
| `tests/test_normal_activity_trajectory_evaluator.py` | evaluator metrics/verdicts | no | yes | passed | fixture/synthetic trajectories |
| `tests/test_office_document_activity_script.py` | office document stub actions | no | yes | passed | no real office app |
| `tests/test_orchestrator_agent_boundary.py` | agent/orchestrator boundary | no | yes | passed | mocked client |
| `tests/test_project_objective_reframe.py` | README/objective framing | no | yes | passed | docs-only |
| `tests/test_prompt_contract.py` | prompt contract and mocked payload | no | yes | passed | no real model response |
| `tests/test_recovery_loop.py` | recovery loop harness behavior | no | yes | passed | fake selector/bridge |
| `tests/test_registry_fixture_pack.py` | registry fixture pack expectations | no | yes | passed | fixture-based |
| `tests/test_role_constrained_trajectory_run.py` | role-constrained multi-step selection | no | yes | passed | no action execution |
| `tests/test_role_template.py` | role templates and conversion to state defaults | no | yes | passed | no generated scenario state execution |
| `tests/test_runtime_baseline.py` | runtime baseline helper functions | no | yes | passed | no server call |
| `tests/test_run_llama_smoke.py` | smoke helper functions | no | yes | passed | no server call |
| `tests/test_schemas.py` | basic schemas | no | yes | passed | schema-only |
| `tests/test_script_execution_bridge.py` | bridge validation/dispatch behavior | no | yes | passed | shell helper monkeypatched in one case |
| `tests/test_script_registry.py` | registry validation | no | yes | passed | registry-level only |
| `tests/test_script_registry_loader_validator.py` | loader/validator cases | no | yes | passed | registry-level only |
| `tests/test_script_runner_error_normalization.py` | error normalization | no | yes | passed | known categories only |
| `tests/test_shell_command_activity_script.py` | shell command allowlist/safety | no | yes | passed | subprocess monkeypatched for execution tests |

## 13. User instruction draft

Prerequisites:

- Windows PowerShell or equivalent shell.
- Python 3.11 or 3.12; observed versions: global `Python 3.12.10`, `.venv` `Python 3.12.10`.
- Dependencies from `requirements.txt`: `httpx`, `pydantic`, `pytest`, `psutil`, `rich`.
- For real local-model smoke/baseline only: installed `llama-server` and local GGUF model files under `models/gguf/`.

Install:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -r requirements.txt
```

Configure model:

- Runtime example: `configs/runtime.local.example.json`.
- Model registry example: `configs/models.local.example.json`.
- Human-readable registry: `docs/ai/model_registry.md`.
- GGUF files should live under `models/gguf/`; README says GGUF files are not committed.

Configure role/profile/scenario:

- Roles: `configs/roles/developer.example.json`, `office_worker.example.json`, `student_researcher.example.json`.
- Activity profiles: `configs/activity_profiles/developer.json`, `office_worker.json`, `student_researcher.json`.
- Scenarios: `configs/evaluation_scenarios/*.json`.
- Initial state example: `configs/agent_state.example.json`.

Run one agent:

- Direct CLI command for a full one-agent autonomous loop was not found.
- Code entrypoints exist: `Agent`, `ActionSelector`, `RoleConstrainedTrajectoryRunner`, `AgentRunner`.
- `AgentRunner` is selection-only by contract and rejects `execute_actions=True`.
- Probable entrypoint requires a small Python harness; command not found in project.

Run multi-agent smoke:

- Direct CLI command not found.
- Code exists in `src/agent/multi_agent_orchestrator.py`, requiring a `runner_factory`.
- Config exists at `configs/multi_agent_orchestrator_smoke.example.json`.
- Tests demonstrate usage in `tests/test_multi_agent_orchestrator_smoke.py`.

Inspect logs/history:

- Default history config: `configs/execution_history.example.json`.
- Logger writes to `logs/execution/history.jsonl` and `logs/execution/errors.jsonl` when enabled.
- Existing runtime/smoke artifacts live under `experiments/` and `logs/smoke/`.

Run evaluation harness:

- Direct CLI command not found.
- Python API exists: `ActivityTrajectoryEvaluator`, `build_synthetic_model_behavior_result`, `ExperimentReadinessAuditor`.
- Example readiness usage is documented in `docs/ai/experiment_readiness_audit.md`.

Run tests:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
```

Expected output from this audit run:

```text
567 passed in 0.58s
```

Runtime smoke/baseline commands from README/scripts:

```powershell
python scripts\run_llama_smoke.py --help
python scripts\run_runtime_baseline.py --help
python scripts\compare_runtime_baselines.py --help
```

Real smoke/baseline commands require a running local `llama-server`; they were not run in this audit:

```powershell
llama-server `
  -m models\gguf\first_model.gguf `
  --host 127.0.0.1 `
  --port 8080 `
  --ctx-size 4096

python scripts\run_runtime_baseline.py `
  --base-url http://127.0.0.1:8080/v1 `
  --model-name first_model.gguf `
  --prompt-file prompts\smoke\agent_next_action_v1.txt `
  --out-dir experiments\baselines\local_runtime_baseline_v1 `
  --runs 3 `
  --force
```

Common failure modes:

- `python -m pytest` fails on global Python if dependencies are not installed: observed `No module named pytest`.
- `LocalLLMClient` fails with `LocalLLMRequestError` when `llama-server` is unreachable.
- LLM outputs non-JSON or wrong schema: mapped to JSON/validation errors.
- Unknown/unsafe actions are rejected by `ScriptRegistry`.
- Shell commands outside allowlist are rejected.
- Browser/office expectations may be misunderstood: current browser is simulated-only; office is document-stub file writing, not real application automation.

## 14. Green-light assessment

Assessment for continuing into experiments: **yellow**.

Reasons:

- Required infrastructure exists and tests pass: `.venv\Scripts\python.exe -m pytest -q` returned `567 passed`.
- Internal readiness audit returns `ready=True`, `required_fail_count=0`, but its own docs say it does not run models or prove quality.
- Local model runtime path and fixed-prompt baseline artifacts exist, but these are not final behavioral experiments.
- Autonomous, execution-enabled agent loop is not yet demonstrated; `AgentRunner` explicitly rejects `execute_actions=True`.
- Multi-agent support is smoke/scaffold, not production scheduler or capacity-controlled experiment runner.

Blocking issues before real experiments:

- Implement or wire an end-to-end scenario runner: state load -> local LLM selection -> validation -> execution bridge -> result normalization -> state/history update -> stop criteria -> evaluator output.
- Produce real local-model trajectories for at least one single-agent scenario and one multi-agent scenario.
- Persist per-step history/errors and model outputs for auditability.
- Capture resource metrics for actual autonomous steps, not only fixed prompt runtime calls.
- Define and measure multi-agent capacity formula using CPU/RAM/latency under increasing agent counts.

Non-blocking issues:

- Browser and office actions may remain simulated/stub if the experiment scope accepts them, but this must be stated explicitly.
- git/mail actions are optional in TZ; absence is acceptable if documented.
- `reports/experiments` and `experiments/model_behavior/results` are missing; readiness audit treats them as optional warnings.
- Existing `comparison.json` and current second-model `summary.json` contain differing second-model averages; regenerate comparison before using numeric deltas in management report.
- Worktree is dirty; freeze or commit a known audit baseline before formal reporting.

Minimum work before experiments:

- Create a reproducible run command or script for one scenario.
- Run one local-model single-agent trajectory for each role or selected pilot role.
- Run one mixed-role multi-agent smoke with real model calls.
- Save trajectories, logs, errors, metrics, prompts, model IDs and resource metrics.
- Generate a model behavior comparison report from real scenario outputs.

What can be shown to leadership now:

- Architecture and contracts are implemented and test-covered.
- Local llama-server runtime path has preliminary smoke/baseline artifacts.
- Safety/validation boundaries for scripts are explicit.
- Role/profile/scenario model for normal activity is present.
- The project is ready to begin controlled experiments, not ready to claim experiment conclusions.

## 15. Missing evidence checklist

- Real model comparison numbers for behavioral scenarios: не найдено.
- Latency/RAM/CPU measurements for autonomous multi-step agent sessions: не найдено.
- Logs from real local model trajectories with action history/errors: не найдено.
- Multi-agent capacity estimate with formula and measured data: не найдено.
- Screenshots/log excerpts from real browser/office activity: не найдено; browser/office are simulated/stub.
- Limitations from actual local-model behavioral failures: не найдено.
- Final recommended configuration based on behavioral quality vs resources: не найдено.

## Raw evidence appendix

### Brief repository tree

```text
local-llm-agent-lab/
  README.md
  pyproject.toml
  requirements.txt
  architecture_report.md
  tasks.txt
  tz.txt
  configs/ (32 files)
    roles/
    activity_profiles/
    evaluation_scenarios/
  docs/ai/ (39 files before this report)
    diagrams/
  experiments/ (26 files)
    smoke/local_llama_server_smoke_v1/
    baselines/local_runtime_baseline_v1/
    baselines/second_model_runtime_baseline_v1/
    comparisons/two_model_runtime_comparison_v1/
  logs/
  models/gguf/
  prompts/smoke/
  scripts/ (4 files)
  src/agent/ (35 files)
    scripts/
  tests/ (39 test files + fixtures)
```

Directory/file-count evidence from command:

| path | files counted |
|---|---:|
| `src` | 35 |
| `configs` | 32 |
| `docs` | 39 |
| `tests` | 76 |
| `scripts` | 4 |
| `experiments` | 26 |
| `logs` | 13 |
| `models` | 4 |
| `prompts` | 1 |

### Key files found

```text
src/agent/state.py
src/agent/role_template.py
src/agent/prompt_contract.py
src/agent/llm_client.py
src/agent/action_contract.py
src/agent/action_selector.py
src/agent/script_registry.py
src/agent/script_execution_bridge.py
src/agent/scripts/file_activity.py
src/agent/scripts/browser_activity.py
src/agent/scripts/office_document_activity.py
src/agent/scripts/shell_command_activity.py
src/agent/execution_history.py
src/agent/autonomous_stop_criteria.py
src/agent/recovery.py
src/agent/recovery_loop.py
src/agent/role_constrained_trajectory.py
src/agent/multi_agent_orchestrator.py
src/agent/activity_profile.py
src/agent/activity_evaluator.py
src/agent/model_behavior_evaluation.py
src/agent/experiment_readiness_audit.py
configs/script_registry.example.json
configs/agent_state.example.json
configs/roles/*.json
configs/activity_profiles/*.json
configs/evaluation_scenarios/*.json
scripts/run_llama_smoke.py
scripts/run_runtime_baseline.py
scripts/compare_runtime_baselines.py
scripts/archive_smoke_run.py
experiments/baselines/*/summary.json
experiments/comparisons/two_model_runtime_comparison_v1/comparison.json
```

### Commands executed

| command | result |
|---|---|
| `Get-Location; Get-ChildItem -Force` from parent workspace | Showed project directory `local-llm-agent-lab` plus `plans`, `отчёты` |
| `git status --short` from parent workspace | Failed: `fatal: not a git repository` |
| `python --version` | `Python 3.12.10` |
| `rg --files ...` from parent workspace | Listed project files |
| `git status --short` inside project | Worktree dirty; many modified/untracked files, including `README.md`, runtime artifacts, `src/agent/*.py`, configs/docs/tests |
| `Get-ChildItem -Force` inside project | Showed `.git`, `.venv`, configs, docs, experiments, logs, models, prompts, scripts, src, tests |
| `rg --files -g README* ...` | Found `README.md`, `pyproject.toml`, `requirements.txt`; no project Makefile/package/docker compose/shell scripts |
| `Get-Content README.md` | Confirmed current status and explicit limitations |
| `Get-Content pyproject.toml; Get-Content requirements.txt` | Confirmed pytest config and dependencies |
| `Get-Content tz.txt` | File read showed mojibake in terminal |
| `rg -n "^(class|def) " src\agent` | Found core classes/functions |
| `Get-Content` on selected `src/agent`, `configs`, `scripts`, experiment summaries | Used for component evidence |
| `rg -n "httpx|subprocess|llama|..." tests scripts src\agent` | Checked risk before running tests |
| `python -m pytest --collect-only -q` | Failed: `No module named pytest` |
| `.venv\Scripts\python.exe --version` | `Python 3.12.10` |
| `.venv\Scripts\python.exe -m pytest --collect-only -q` | `567 tests collected in 0.26s` |
| `.venv\Scripts\python.exe -m pytest -q` | `567 passed in 0.58s` |
| `python scripts\run_llama_smoke.py --help` | Displayed CLI usage; no model call |
| `python scripts\run_runtime_baseline.py --help` | Displayed CLI usage; no model call |
| `python scripts\compare_runtime_baselines.py --help` | Displayed CLI usage; no model call |
| `.venv\Scripts\python.exe scripts\archive_smoke_run.py --help` | Displayed CLI usage; no archive run |
| readiness one-liner with `PYTHONPATH=src` | `ready=True`, `required_pass_count=51`, `required_fail_count=0`, `warning_count=2` |

### Commands not executed and why

| command/category | reason |
|---|---|
| `llama-server ...` | Starts local model runtime; explicitly avoided |
| `python scripts\run_llama_smoke.py --model-name ...` without `--help` | Would call local `llama-server` and write logs |
| `python scripts\run_runtime_baseline.py ...` without `--help` | Would call local model repeatedly and overwrite artifacts with `--force` |
| `python scripts\compare_runtime_baselines.py ... --force` | Would modify comparison artifacts |
| `python scripts\archive_smoke_run.py ... --force` | Would modify experiment archive |
| Browser/office external application runs | No such real app commands found; browser/office helpers are simulated/stub |
| Network operations/downloads | Disallowed by audit constraints and project role constraints |
