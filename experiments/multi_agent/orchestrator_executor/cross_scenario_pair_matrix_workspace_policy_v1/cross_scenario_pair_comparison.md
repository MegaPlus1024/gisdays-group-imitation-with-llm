# Cross-Scenario Orchestrator/Executor Pair Comparison v1

This report compares prototype pair-matrix results across the simple and heavy group scenarios. It names the best observed pair across tested scenarios, not a production recommendation.

- simple scenario best pair: `second_model->first_model`
- heavy scenario best pair: `second_model->second_model`
- best observed pair across tested scenarios: `second_model->second_model`

| pair | scenarios_completed | mean_rank_score | mean_quality | quality_drop_simple_to_heavy | execution_drop_simple_to_heavy | stability_verdict |
|---|---:|---:|---:|---:|---:|---|
| `second_model->second_model` | 2 | 0.854073 | 0.881595 | 0.012289 | 0.0 | `stable_but_low_confidence` |
| `second_model->first_model` | 2 | 0.761943 | 0.855428 | 0.0702 | 0.0 | `stable_but_low_confidence` |
| `first_model->first_model` | 0 | None | None | 0.0 | 0.0 | `degraded_on_heavy` |
| `first_model->second_model` | 0 | None | None | 0.0 | 0.0 | `degraded_on_heavy` |

## Limitations

- Only two group scenarios are compared.
- This is not a production recommendation.
- No GPU runtime or stress benchmark is included.
- Rank score is prototype-only.
