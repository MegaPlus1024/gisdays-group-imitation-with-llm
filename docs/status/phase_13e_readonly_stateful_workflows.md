# Phase 13E Read-Only Stateful Workflows

## Purpose

Phase 13E adds a fixture-only, read-only workflow layer that can visit multiple local intranet pages, collect facts, store evidence items, maintain workflow state, and produce a final answer without broadening the browser action surface yet.

## Why the action surface stays narrow

- only read-only browser actions are used for E1
- no forms, text typing, uploads, downloads, or writes are introduced
- the workflow remains local-fixture-only and testable with scripted planners

## Workflow model

- `workflow_id`
- `scenario_id`
- `step_index`
- `current_observation`
- `visited_urls`
- `facts`
- `evidence_items`
- `pending_objectives`
- `final_answer`
- `final_status`
- `trace_entries`

The workflow state is JSON-serializable and the summary records relative `state_path`, `trace_path`, and `summary_path` values.

## Scenario policy

The read-only policy allows only:

- `browser_open_url`
- `browser_click`
- `browser_extract_text`
- `browser_snapshot`

The policy disallows:

- `browser_type_text`
- `browser_submit_form`
- `browser_upload_file`
- `browser_download_file`
- `external_url`
- `file_write`

If a scripted step proposes a disallowed action, the workflow rejects it cleanly with `action_not_allowed_by_scenario_policy` and failure class `scenario_policy_rejected`.

## Failure classification

The workflow separates at least these outcomes:

- `none`
- `model_failed_task`
- `scenario_policy_rejected`
- `script_error`
- `config_error`
- `fixture_error`
- `validation_error`

This keeps policy rejections, malformed scripted plans, fixture problems, and validation misses distinguishable in summaries and traces.

## Safety boundaries

- fixture-only and local only
- no model calls
- no real browser or Playwright execution from Codex
- no external network
- no file writes beyond local artifact summaries
- generated artifacts are evidence only and should not be committed

## Limitations

- E1 is scripted rather than model-planned
- the scenario set is intentionally small and deterministic
- read-only workflows do not yet cover editing or submission flows
- the layer is a foundation for later stateful planning, not a production recommendation

## Future path

- add a local-model stateful planner packet
- expand long-horizon reasoning and repair
- add broader local-fixture scenarios only after the read-only layer is stable
