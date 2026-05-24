# Two-model local runtime comparison v1

| Metric | First (first_model.gguf) | Second (qwen2.5-3b-instruct-q4_k_m.gguf) |
|---|---:|---:|
| success_count | 3 | 3 |
| failure_count | 0 | 0 |
| json_parse_success_count | 3 | 3 |
| wall_time_seconds.avg | 0.374865 | 0.413826 |
| cpu_percent.avg_of_avg | 3.616667 | 2.533333 |
| tokens.total_tokens_avg | 269.0 | 270.0 |
| llama_tokens_per_second.predicted_per_second_avg | 311.602771 | 299.145454 |

## Numeric observations

- wall_time_seconds_avg_delta: 0.038961
- wall_time_seconds_avg_ratio: 1.103933
- cpu_percent_avg_delta: -1.083334
- total_tokens_avg_delta: 1.0
- predicted_per_second_avg_delta: -12.457317

## Limitations

- This comparison is numeric only.
- It does not prove general model quality.
- It does not validate semantic action correctness.
- It uses one fixed prompt only.
- It does not measure multi-agent load.

## Next step

Keep runtime comparison numeric and add semantic action validation in a separate step.
