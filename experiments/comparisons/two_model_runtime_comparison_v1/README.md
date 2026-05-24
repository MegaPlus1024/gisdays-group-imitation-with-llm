# Two-Model Runtime Comparison v1

## Purpose

This folder compares two already-generated runtime baselines using numeric metrics only.

## Inputs

- First baseline: `experiments/baselines/local_runtime_baseline_v1/summary.json`
- Second baseline: `experiments/baselines/second_model_runtime_baseline_v1/summary.json`

## Metrics compared

- run/success/failure counts
- JSON parse success count
- latency stats
- CPU and RAM aggregate estimates
- token averages
- llama token-per-second aggregates

No subjective model quality claim should be made unless supported later by JSON validity/failure data and semantic validation.

## How to generate second baseline

1. Start `llama-server` with `models/gguf/second_model.gguf`.
2. Run second smoke and archive it.
3. Run:
   `python scripts\run_runtime_baseline.py --base-url http://127.0.0.1:8080/v1 --model-name second_model.gguf --prompt-file prompts\smoke\agent_next_action_v1.txt --out-dir experiments\baselines\second_model_runtime_baseline_v1 --runs 3 --force`

## How to generate comparison JSON

Run:

`python scripts\compare_runtime_baselines.py --first-summary experiments\baselines\local_runtime_baseline_v1\summary.json --second-summary experiments\baselines\second_model_runtime_baseline_v1\summary.json --out-dir experiments\comparisons\two_model_runtime_comparison_v1 --force`

## Limitations

- one fixed prompt
- small run count
- local machine load affects timing/resource estimates
- no semantic action correctness validation

## Next step

Use numeric comparison outputs as runtime references before adding semantic action validation.
