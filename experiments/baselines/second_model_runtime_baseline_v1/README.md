# Local runtime resource baseline v1

## Purpose

This baseline measures the current local llama-server runtime on one fixed prompt.

## Setup

- Runtime: llama.cpp / llama-server
- Endpoint: http://127.0.0.1:8080/v1/chat/completions
- Model: qwen2.5-3b-instruct-q4_k_m.gguf
- Prompt: prompts\smoke\agent_next_action_v1.txt
- Runs requested: 3

## What was measured

- wall time per run
- system CPU estimate during each request
- system RAM before/after each request
- optional server RSS delta when `--server-pid` is provided
- token usage and llama timings when returned by server

## What was not measured

This does not prove model quality.
This does not compare models.
This does not test multi-agent load.
This does not validate action parameters semantically.

## Results summary

- run_count: 3
- success_count: 3
- failure_count: 0
- json_parse_success_count: 3
- wall_time_seconds(avg/min/max): 0.387236 / 0.300198 / 0.558507
- cpu_percent(avg_of_avg/max): 2.622333 / 3.3

## Failure cases

See `summary.json` -> `failure_cases`.

## Reproduction

See `replay_commands.md`.

## Limitations

- one model only
- one prompt only
- no model comparison
- no semantic action validation
- no agent loop
- resource estimates are approximate
- server RSS only available if server_pid is passed
- results depend on current machine load

## Next step

This is the reference point for future comparisons.
