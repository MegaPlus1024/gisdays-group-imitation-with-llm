# Phase 8: технический статус

## 1. Snapshot

Текущая code base поддерживает controlled local orchestrator/executor workflow для пары `second_model -> first_model`, deterministic office artifact validation, mini-matrix aggregation, flagship judge prompt exchange и guarded API judge runner.

Подтвержденные метрики последнего агрегата:

- `repeat_count`: 3
- `succeeded_count`: 3
- `failed_count`: 0
- `execution_attempted_count`: 6
- `execution_success_count`: 6
- `office_artifact_count`: 6
- `office_artifact_readable_count`: 6
- `correctness_score_count`: 3
- `mean_correctness_score`: 1.0
- `normality_input_count`: 3
- `resource_observation_count`: 3

Semantic judge score отсутствует: live/API judge не запускался.

## 2. Commit milestones

Ветка `main` содержит такие важные Phase 8 milestones:

- `442364e Add guarded single trial operator runner`
- `f18b10f Add single trial model pair execution`
- `50ee00f Add model pair execution readiness validation`
- `dd90586 Add local pipeline config support to single trial runner`
- `0a6ae98 Wire local model pair entrypoint to pipeline`
- `d35b6b7 Add first controlled single trial run packet`
- `cf09105 Add dual endpoint controlled trial packet`
- `3ca3929 Add compact prompt budget for local trials`
- `a8c9871 Add office action path repair`
- `f426b3d Add controlled DOCX append precreate`
- `cedf701 Add office execution artifact summary`
- `0d01758 Add controlled mini matrix packet`
- `5974050 Add mini matrix correctness postprocess`
- `cf2d898 Add flagship judge prompt exchange`
- `71f66dd Add guarded flagship API judge runner`

## 3. Architecture layers

Offline planning:

- Scenario/config packets live under `artifacts/first_run_packets/` and committed example configs under `configs/local_pipeline/`.
- These define repeat ids, pair ids, scenario ids and guarded runtime parameters.

Readiness validation:

- Model pair/scenario readiness is checked before controlled execution.
- Missing runtime prerequisites are surfaced as controlled validation or diagnostics, not hidden traceback-driven state.

Single-trial guarded execution:

- `scripts/run_single_trial_controlled.py` is the operator entrypoint for controlled trials.
- Runtime execution requires explicit opt-in and must not be launched automatically by docs/tests.

Office action repair and precreate:

- Compact prompts reduce local context pressure.
- Path repair converts unsafe/missing model paths into safe workspace-local office outputs.
- DOCX append precreate creates a missing append target before appending, and records `precreate_metadata`.

Artifact harvesting:

- `scripts/summarize_office_execution_artifacts.py` reads a trial result and checks office artifacts.
- The latest successful mini-matrix has 6 generated/readable DOCX artifacts across 3 repeats.

Correctness scoring:

- `scripts/score_office_execution_correctness.py` scores deterministic execution criteria.
- Current deterministic criteria include trial success, validation, execution attempted/succeeded, artifact existence and artifact readability.

Mini-matrix aggregation:

- `scripts/aggregate_mini_matrix_results.py` combines repeat directories into `mini_matrix_aggregate_summary.json`.
- Current aggregate summary reports 3/3 successful repeats and mean correctness 1.0.

Judge prompt exchange:

- `scripts/build_flagship_judge_prompt_pack.py` builds offline prompt-pack inputs from aggregate evidence.
- `scripts/parse_flagship_judge_responses.py` parses saved judge responses offline.
- Prompt packs and raw responses are generated artifacts and are intentionally ignored by Git.

Guarded API judge runner:

- `scripts/run_flagship_api_judge.py` exists for future explicit operator-controlled API evaluation.
- It requires judge config, explicit `--allow-api-judge` and confirmation.
- It was not run in this documentation update and should not be run by automated checks.

## Phase 9.1 Autonomous multi-agent runtime foundation

Phase 9.1 adds a library-only autonomous multi-agent runtime foundation in `src/agent/autonomous_multi_agent_runtime.py`.

What was added:

- deterministic scheduler modes: `round_robin` and `priority_then_round_robin`;
- shared state/task board with agents, tasks, statuses, shared facts, artifacts, per-agent history, group events, resource locks, retry counters and quarantined agents;
- runtime loop foundation: observe shared state, choose next agent, call injected decision provider, validate action envelope, call injected action executor, verify result, update shared state and apply policy;
- stop policy: max ticks, total actions, per-agent actions, idle limit, total failures, retries, all-tasks-terminal and no-runnable-agents stops;
- controlled error recovery: retry task, fail task after retry exhaustion, quarantine failing agents while keeping other agents runnable;
- deterministic resource lock model for future concurrency/resource controls;
- virtual environment/session metadata: environment id, safe relative workspace root, per-agent workspaces, reset policy and allowed resource namespaces;
- JSON-serializable `to_summary()` with schema `autonomous_multi_agent_runtime_summary_v1`;
- browser-aware validation hook: browser actions can be scheduled only when the virtual environment enables the `browser` namespace.

What does not run:

- no LLM client is created;
- no model, `llama-server`, GPU probe or runtime experiment is launched;
- no Playwright/Chromium browser is launched;
- no Microsoft Office/LibreOffice action is launched;
- no API/HTTP judge or LLM-as-a-judge is launched.

Which ТЗ gaps this advances:

- long-lived scheduler foundation;
- shared state/shared memory foundation;
- autonomous loop foundation;
- stop policy and completion criteria;
- error recovery foundation;
- concurrency/resource-control foundation through deterministic locks;
- virtual environment/session layer foundation;
- browser runtime interface hook for a later browser-completion phase.

Limitations:

- no true parallel execution or worker threads yet;
- no production deployment/hardening layer;
- no live browser runtime completion yet;
- no mail/git/other app actions;
- no semantic LLM judge integration;
- current validation is unit-test/fake-provider based, not broad scenario validation.

## 4. Offline reproduction commands

The following commands are intended for offline post-processing of already-produced artifacts. They do not start models or live API calls.

```powershell
.\.venv\Scripts\python.exe scripts\summarize_office_execution_artifacts.py `
  --trial-result artifacts\single_trial_runs\phase_8_26_mini_matrix_r1\model_pair_single_trial_result.json `
  --output artifacts\single_trial_runs\phase_8_26_mini_matrix_r1\office_execution_artifact_summary.json
```

```powershell
.\.venv\Scripts\python.exe scripts\score_office_execution_correctness.py `
  --trial-result artifacts\single_trial_runs\phase_8_26_mini_matrix_r1\model_pair_single_trial_result.json `
  --office-artifact-summary artifacts\single_trial_runs\phase_8_26_mini_matrix_r1\office_execution_artifact_summary.json `
  --output artifacts\single_trial_runs\phase_8_26_mini_matrix_r1\office_execution_correctness_summary.json
```

```powershell
.\.venv\Scripts\python.exe scripts\aggregate_mini_matrix_results.py `
  --run-output-dir artifacts\single_trial_runs\phase_8_26_mini_matrix_r1 `
  --run-output-dir artifacts\single_trial_runs\phase_8_26_mini_matrix_r2 `
  --run-output-dir artifacts\single_trial_runs\phase_8_26_mini_matrix_r3 `
  --summary-id phase_8_26_mini_matrix_r3 `
  --output-dir artifacts\mini_matrix_summaries\phase_8_26_mini_matrix_r3
```

```powershell
.\.venv\Scripts\python.exe scripts\build_flagship_judge_prompt_pack.py `
  --aggregate-summary artifacts\mini_matrix_summaries\phase_8_26_mini_matrix_r3\mini_matrix_aggregate_summary.json `
  --summary-id phase_8_26_mini_matrix_r3 `
  --output-dir artifacts\judge_prompt_packs\phase_8_26_mini_matrix_r3
```

## 5. Commands that must not be launched automatically

- `scripts/run_single_trial_controlled.py --allow-runtime-execution`
- `scripts/run_flagship_api_judge.py --allow-api-judge`
- llama-server startup commands
- GPU/runtime probes
- Browser/Playwright/Chromium commands
- Microsoft Office/LibreOffice commands
- New stress tests or experiments
- Any command that reads GGUF/model binary contents

## 6. Intentionally ignored local artifacts

The following paths are runtime/generated or local-private and should remain out of commits:

- `artifacts/single_trial_runs/`
- `artifacts/mini_matrix_summaries/`
- `artifacts/judge_prompt_packs/`
- `configs/judge/*.local.json`
- `.env`
- `*.key`
- `*.pem`
- GGUF/model binaries

Committed packet/example files remain allowed, including `artifacts/first_run_packets/...` and `configs/judge/*.example.json`.

## 7. Current limitations

- Deterministic execution correctness is proven only for the controlled office scenario and N=3.
- Semantic judge scoring is not available yet.
- API judge provider integration needs a budgeted Phase 8.30 design and operator secret-handling path.
- Autonomous multi-agent runtime foundation exists, but production long-running deployment and true parallel execution are not implemented.
- Browser and real network behavior are not part of the confirmed run.
- Runtime artifacts are evidence for local work, but are not source-controlled.

## 8. Next technical stage

The next practical stage should complete browser runtime behavior on top of the Phase 9.1 foundation, still behind explicit guards and without enabling arbitrary external app integrations.

Later semantic judge work remains separate and should stay guarded:

1. Define an openai-compatible/DeepSeek-style config schema that never stores secrets in committed files.
2. Add dry-run validation for endpoint, model id, prompt pack shape and output paths.
3. Keep live API execution behind explicit flags and confirmation.
4. Parse judge outputs into a semantic scorecard separate from deterministic correctness.
5. Add tests for missing key, malformed response, schema mismatch and no-runtime safety.
