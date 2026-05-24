# Local llama-server smoke test v1

## Purpose

Archive one successful local smoke run as a reproducible, reviewable experiment artifact.

## What was tested

- local llama-server OpenAI-compatible chat endpoint call
- fixed smoke prompt execution
- response extraction and JSON parse check
- wall time and resource estimate capture

## Result

- success: `True`
- json_parse_success: `True`

This proves local llama-server end-to-end generation works.
This does not prove model quality.
This does not prove the full agent loop.
This does not compare models.
This does not validate script parameters semantically yet.

## Model

- model_name: `first_model.gguf`
- model_path: `models\gguf\first_model.gguf`
- model_file_exists: `True`
- model_file_size_bytes: `1117320736`
- model_sha256: `6a1a2eb6d15622bf3c96857206351ba97e1af16c30d7a74ee38970e434e9407e`

## Runtime

- name: `llama.cpp / llama-server`
- base_url: `http://127.0.0.1:8080/v1`
- endpoint: `http://127.0.0.1:8080/v1/chat/completions`
- system_fingerprint: `b9264-ce02093fd`
- server_pid: `None`

## Prompt

- sha256: `963ae2ccb6f9c74421a9fb0447155947f555f1ff99845087e3847a37016a4d09`

## Output

- sha256: `6ae35e7cce24f3c29a346ae5b74d46d9dbab7f9e3a4222bb9f8ab56548d918fb`

## Timing

- wall_time_seconds: `5.713122`
- llama_timings: `{'cache_n': 0, 'prompt_n': 196, 'prompt_ms': 5160.868, 'prompt_per_token_ms': 26.33095918367347, 'prompt_per_second': 37.97810755865098, 'predicted_n': 74, 'predicted_ms': 436.906, 'predicted_per_token_ms': 5.904135135135135, 'predicted_per_second': 169.3728170361588}`

## Resource estimate

- system_ram_used_before_mb: `20823.812`
- system_ram_used_after_mb: `20782.23`
- system_ram_delta_mb: `-41.582`
- system_cpu_percent_avg: `4.51`
- system_cpu_percent_max: `7.4`

## Reproduction commands

See `replay_commands.md`.

## Limitations

- server_pid was not provided if null in source log; resource estimate is system-level unless server_pid is available; model_name may be an alias if the GGUF file was renamed to first_model.gguf; semantic action validation is not implemented yet

## Next step

Implement model adapter / response validation / semantic action contract, not multi-agent simulation.
