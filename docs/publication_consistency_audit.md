# Publication Consistency Audit

## 1. Purpose

Full repository consistency audit before GitHub publication. The audit checks whether current README/docs/reports/configs/scripts/tests/artifacts agree with the actual implementation and source-of-truth configuration.

## 2. Source of Truth

| Area | Source of truth |
|---|---|
| Model ids, logical names, local GGUF paths, runtime metadata | `configs/evaluation_models.json` |
| Scenarios | `configs/evaluation_scenarios/*.json` |
| Roles | `configs/roles/*.json` |
| Activity profiles | `configs/activity_profiles/*.json` |
| Allowed action names and parameters | `configs/script_registry.example.json` |
| CLI flags and behavior | `scripts/*.py`, `scripts/start_llama_server.ps1`, `src/agent/` |
| Expected behavior | `tests/` |
| Final reported metrics | `reports/experiments/final_evaluation_summary.json`, `experiments/model_behavior/cross_scenario/office_worker_developer_two_model_cross_scenario_v1`, `experiments/model_behavior/resources/resource_capacity_v1` |
| Final experiment report test result | `636 passed` |
| Publication audit test result | `644 passed` after adding `tests/test_publication_consistency.py` |
| Publishable tracked files | `git ls-files`, `.gitignore` |

## 3. Audit Scope

- Model naming and file mapping consistency.
- README vs actual CLI consistency.
- Config/docs path consistency.
- Report/artifact folder consistency.
- Test count consistency.
- Capability/status consistency.
- Artifact schema consistency.
- Safety/path-policy statements.
- GitHub publication hygiene.
- JSON validity.
- Markdown/path sanity for current publication documents.

## 4. Findings Summary

| ID | severity | category | issue | files affected | fixed | notes |
|---|---|---|---|---|---|---|
| F-001 | high | model mapping | Second model upstream filename was documented as the required local path in current model docs. Source of truth uses `models/gguf/second_model.gguf`. | `models/gguf/MODELS.md`, `configs/models.local.example.json`, `docs/ai/model_registry.md` | yes | Added explicit logical vs local mapping. |
| F-002 | medium | model mapping | No standalone publication-safe model file mapping document existed. | `docs/ai/model_file_mapping.md` | yes | New document created. |
| F-003 | medium | current onboarding docs | Developer walkthrough still said no real scenario runner/trajectories existed. | `docs/ai/developer_walkthrough_for_newcomer.md` | yes | Updated current status while preserving limitations. |
| F-004 | low | historical docs | Old audit document contains historical `567 passed` and pre-experiment limitations. | `docs/ai/project_structure_audit_for_report.md` | yes/context | Added publication note marking it as historical snapshot. |
| F-005 | low | README discoverability | README did not point to standalone model mapping doc. | `README.md` | yes | Added model mapping table and doc pointer. |
| F-006 | medium | regression guard | No automated test covered publication model mapping and forbidden tracked file patterns. | `tests/test_publication_consistency.py` | yes | New offline test added. |

## 5. Fixed Inconsistencies

- `models/gguf/MODELS.md` now lists `models/gguf/second_model.gguf` as the expected local file for `qwen2_5_3b_instruct_q4_k_m`.
- `configs/models.local.example.json` now maps `qwen2_5_3b_instruct_q4_k_m` to local alias `second_model.gguf` and local path `models/gguf/second_model.gguf`.
- `docs/ai/model_registry.md` now matches `configs/evaluation_models.json` for the second model local path.
- `docs/ai/model_file_mapping.md` was added as the canonical human-readable mapping document.
- `README.md` now includes a model mapping table and points to `docs/ai/model_file_mapping.md`.
- `docs/ai/second_model_smoke_test.md` now explains that `second_model.gguf` is the mapped local alias.
- `docs/ai/developer_walkthrough_for_newcomer.md` now reflects the current scenario-runner/repeated-trials/cross-scenario/resource state.
- `docs/ai/project_structure_audit_for_report.md` now has a clear historical snapshot notice.

## 6. Accepted Historical Inconsistencies

| document | accepted historical content | reason |
|---|---|---|
| `docs/ai/project_structure_audit_for_report.md` | Old test count `567 passed`, pre-experiment readiness language | This is an audit snapshot from 2026-06-22 and should preserve the state observed then. A publication note was added. |
| `experiments/baselines/*` and raw artifact JSON/JSONL | Historical model names, prompts, local machine paths, run outputs | These are generated evidence artifacts. They are not rewritten because changing them would alter experiment evidence. |
| `experiments/model_behavior/*` | Historical raw prompts/results and machine paths | These are experiment artifacts and should remain immutable evidence. |

## 7. Remaining Warnings

- Some generated artifacts contain local absolute paths because they preserve real run evidence.
- Browser activity remains simulated-only.
- Office activity remains stub/file-based.
- No measured multi-agent stress test exists.
- Capacity estimate is formula-based and low confidence.
- No final production model recommendation is made.
- GGUF files are intentionally not committed; new users must provide local files or edit `configs/evaluation_models.json`.

## 8. Verification

Commands run:

```powershell
git status --short
git ls-files
git grep -n -E "qwen2\.5-3b-instruct-q4_k_m\.gguf|second_model\.gguf|first_model\.gguf|567 passed|576 passed|586 passed|592 passed|602 passed|608 passed|617 passed|618 passed|627 passed|636 passed|no real model behavior trajectories|no real scenario runner CLI|not production-ready|production-ready" -- .
.\.venv\Scripts\python.exe scripts\run_agent_scenario.py --help
.\.venv\Scripts\python.exe scripts\run_repeated_model_trials.py --help
.\.venv\Scripts\python.exe scripts\analyze_behavioral_trials.py --help
.\.venv\Scripts\python.exe scripts\compare_cross_scenario_behavior.py --help
.\.venv\Scripts\python.exe scripts\evaluate_resource_capacity.py --help
.\.venv\Scripts\python.exe scripts\check_evaluation_model.py --help
```

JSON validation was run for:

- `configs/evaluation_models.json`
- `configs/models.local.example.json`
- `reports/experiments/final_evaluation_summary.json`
- `experiments/model_behavior/cross_scenario/office_worker_developer_two_model_cross_scenario_v1/recommendation_readiness.json`
- `experiments/model_behavior/resources/resource_capacity_v1/resource_capacity_evaluation.json`

Path sanity checked:

- required configs exist;
- report files exist;
- cross-scenario/resource artifacts exist;
- representative repeated-trial folders contain the expected artifact schema.

Automated verification added:

- `tests/test_publication_consistency.py`

Test results:

- `.\.venv\Scripts\python.exe -m pytest tests\test_publication_consistency.py -q`: `8 passed`
- `.\.venv\Scripts\python.exe -m pytest tests\test_evaluation_models.py -q`: `10 passed`
- `.\.venv\Scripts\python.exe -m pytest -q`: `644 passed`

## 9. Git Publication Readiness

Ready to push after tests pass and the follow-up commit is created.

Do not push GGUF files, `.venv`, `.tmp`, logs, credentials, or local runtime binaries. Current `.gitignore` and tracked-file checks are designed to prevent that.
