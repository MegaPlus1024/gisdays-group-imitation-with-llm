# Manager Summary

## Status

The prototype and experimental evidence base are ready for reporting as a research-stage result. They are not ready for a final production model recommendation.

## What was implemented

- Local LLM agent pipeline from state and role to action selection, validation, execution, history and evaluation.
- Model registry for reproducible `model_id` based experiments.
- End-to-end scenario runner with fake/local modes.
- Repair policy for one structured correction attempt after invalid model output.
- Repeated-trials infrastructure.
- Behavioral, cross-scenario and resource/capacity analysis layers.

## What was tested

- Two local GGUF models: `first_model` and `second_model` (recorded as `qwen2_5_3b_instruct_q4_k_m` in historical experiment artifacts).
- Research metadata: `first_model` maps to upstream filename `qwen2.5-1.5b-instruct-q4_k_m.gguf`; `second_model` maps to upstream filename `qwen2.5-3b-instruct-q4_k_m.gguf`.
- Two scenarios: office-worker activity and developer project maintenance.
- N=3 trials per model per scenario.
- 12 real local-model trajectories total.

## Main findings

- `second_model` is stronger on JSON/action-contract validity and latency in the current evidence base.
- `first_model` achieved useful execution in one office-worker scenario but is repair-dependent.
- Both models show weak coherence and repeated/template-like behavior.
- Neither model is sufficient for a final production recommendation.

## Resource estimate

The current machine snapshot has 24 physical/logical CPUs and about 130 GB RAM. The low-confidence planning formula estimates 11 concurrent agents for both tested models, CPU-bound.

This is not a measured multi-agent stress test.

## Risks

- Current behavioral quality is not strong enough for production-like imitation.
- Capacity is estimated, not measured.
- Browser automation is simulated-only and office actions are stub/file-based.
- Developer scenario safety policy rejected some role-relevant paths.
- The sample is small: two scenarios, three trials per model per scenario.

## Recommendation

Continue development with the current evaluation infrastructure. Keep both models in the evaluation set, use `repair_attempts=1`, and treat `second_model` as the stronger candidate for contract validity/latency, not as a final deployment choice.

## Next steps

1. Fix developer scenario workspace/safety alignment.
2. Add measured runtime probe and multi-agent capacity smoke test.
3. Add one more scenario or rerun developer trials after safety/path tuning.
4. Prepare final model recommendation only after improved behavioral and measured capacity evidence.
