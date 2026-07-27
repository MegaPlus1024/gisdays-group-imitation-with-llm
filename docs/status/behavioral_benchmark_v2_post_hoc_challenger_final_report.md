# Behavioral Benchmark v2 Post-Hoc Challenger Final Report

## 1. Executive Conclusion

APPROVE. The post-hoc `qwen3_6_27b_q5_k_m` challenger is documented as a separate challenger result with 35/35 Behavioral Benchmark v2 success and V2-07 at 5/5. The frozen cohort result is unchanged: third_model, fourth_model, and fifth_model remain tied at 30/35 with no frozen winner.

This is a bounded offline evidence closeout. It does not claim production readiness, concurrency capacity, multi-user throughput, sustained thermal stability, or general model quality outside this benchmark.

## 2. Frozen Cohort Result

- Frozen behavioral tag: `behavioral-benchmark-v2-final` -> `c66720057b7c728284ef500b5d131284258e9a40`.
- Frozen resource tag: `behavioral-benchmark-v2-resource-profile-final` -> `244dd5179a565544ad91bee174a41c7a3ee34ef6`.
- third_model: 30/35, V2-07 0/5, gate fail.
- fourth_model: 30/35, V2-07 0/5, gate fail.
- fifth_model: 30/35, V2-07 0/5, gate fail.
- Frozen cohort winner: none.

## 3. Post-Hoc Challenger Classification

`qwen3_6_27b_q5_k_m` is classified only as a post-hoc challenger. It is not a frozen cohort member and does not move or rewrite the frozen tags.

## 4. Behavioral Gate Table

| model_id | classification | overall | V2-07 | gate |
|---|---|---:|---:|---|
| third_model | frozen cohort | 30/35 | 0/5 | fail |
| fourth_model | frozen cohort | 30/35 | 0/5 | fail |
| fifth_model | frozen cohort | 30/35 | 0/5 | fail |
| qwen3_6_27b_q5_k_m | post-hoc challenger | 35/35 | 5/5 | pass |

## 5. Resource Profile Summary

- Accepted resource run: `artifacts/descriptive_gpu_resource_profiles/qwen3_6_27b_q5_k_m_20260727T051740Z`.
- Status: succeeded.
- Measured requests: 30/30.
- Startup evidence: 65/65 layers offloaded.
- Samples: 313 JSONL and 313 CSV samples.
- Lifecycle shutdown: process stopped and listener released.
- Resource harness commit: `407e9a8beee29e8838f4fba08f553702924a69ad`.
- Resource manifest SHA-256: `02DF54CD500BDA6D5F65EEF751437066894FEF88B6EC1C1B7CF9B99C63CCFBFB`.

## 6. Verified Four-Model Comparison

- Comparison directory: `artifacts/descriptive_gpu_resource_profiles/post_hoc_challenger_comparison_verified`.
- Comparison manifest SHA-256: `F11DD434A72A369717438CCF234A6BCDF5640FA288B8CCA4CA702586B658B482`.
- Audit: APPROVE.
- Raw request discrepancies: 0.
- Raw resource discrepancies: 0.
- Methodology: comparable with documented provenance caveats.

## 7. Correctness-First Ranking

1. qwen3_6_27b_q5_k_m: post-hoc challenger, 35/35, gate pass.
2. third_model / fourth_model / fifth_model: frozen cohort tie, 30/35, gate fail.

## 8. Resource-Only Rankings

- Lowest peak VRAM: third_model.
- Highest VRAM headroom: third_model.
- Lowest RSS/private memory: third_model.
- Fastest short/medium/long: fifth_model.
- Highest output tokens/s: fifth_model.
- Lowest peak power: fifth_model.
- Lowest peak temperature: fifth_model.

## 9. Methodology and Provenance Caveats

- Restored behavioral `model_source.json` matches the behavioral manifest: 1113 bytes and SHA-256 `0e7b5e6444fa6cca13d984ef39c0b417c3604edf7fdedc32aacdafb894c8ce41`.
- The extended resource provenance copy is preserved separately at `artifacts/challenger_qwen3_6_27b_q5_k_m/provenance_repair/model_source_resource_extended.json`.
- The generated comparison evidence manifest was refreshed after provenance repair so it hashes the restored behavioral `model_source.json`; comparison report/tables/metrics are unchanged.
- The failed closeout archive `../behavioral_benchmark_v2_post_hoc_qwen3_6_27b_q5_k_m_final_20260727T061838Z.tar.gz` is retained only as a rejected closeout attempt.
- Frozen descriptive resource evidence was recovered from the original archive and verified against 47 historical hashes.
- `frozen_v2_modified` is false.

## 10. Production-Planning Limits

- No production readiness is claimed.
- No concurrency capacity is claimed.
- No multi-user throughput is claimed.
- No sustained thermal stability is claimed.
- No general model quality outside this benchmark is claimed.
- These results can inform single-user local sizing and latency expectations for this controlled benchmark only.

## 11. Exact Evidence Paths and Hashes

| evidence | path | SHA-256 |
|---|---|---|
| original frozen resource archive | `../behavioral_benchmark_v2_descriptive_gpu_resource_244dd51.tar.gz` | `F4D7D2C1EB9BA36AFF417C449CEA972CDF45C2167F65E765B7AA1F8B457B87E5` |
| recovery manifest | `artifacts/descriptive_gpu_resource_profiles/frozen_resource_evidence_recovery/recovery_evidence_manifest.json` | `6C0B19EA06B7E193E00045EF766D1DE55F686C8B1D336CD1C29ACF3369BC2266` |
| challenger behavioral manifest | `artifacts/challenger_qwen3_6_27b_q5_k_m/full_cohort_35/full_cohort_evidence_manifest.json` | `3AD85003A3A1E42717DE73BB8B19356E474D7E049E6931EA73342B9488C5D106` |
| restored model source | `artifacts/challenger_qwen3_6_27b_q5_k_m/model_source.json` | `0e7b5e6444fa6cca13d984ef39c0b417c3604edf7fdedc32aacdafb894c8ce41` |
| extended model source copy | `artifacts/challenger_qwen3_6_27b_q5_k_m/provenance_repair/model_source_resource_extended.json` | `4f5a6b52d41fc0bc17d6ee4ae2e2e52ce1cb3dfa68df1690873a3af009fee747` |
| accepted challenger resource manifest | `artifacts/descriptive_gpu_resource_profiles/qwen3_6_27b_q5_k_m_20260727T051740Z/evidence_manifest.json` | `02DF54CD500BDA6D5F65EEF751437066894FEF88B6EC1C1B7CF9B99C63CCFBFB` |
| verified comparison manifest | `artifacts/descriptive_gpu_resource_profiles/post_hoc_challenger_comparison_verified/comparison_evidence_manifest.json` | `F11DD434A72A369717438CCF234A6BCDF5640FA288B8CCA4CA702586B658B482` |

## 12. Failed Diagnostic Run History

- Failed resource diagnostic run: `artifacts/descriptive_gpu_resource_profiles/qwen3_6_27b_q5_k_m_20260726T222420Z`.
- Status: failed.
- Validation failure: startup_log_offloaded_layers_mismatch.
- It remains classified as failed and is not used as the accepted resource profile.
- Failed closeout archive preserved unchanged: `../behavioral_benchmark_v2_post_hoc_qwen3_6_27b_q5_k_m_final_20260727T061838Z.tar.gz`.

## 13. Reproduction and Archive References

- Final archive: `../behavioral_benchmark_v2_post_hoc_qwen3_6_27b_q5_k_m_final_20260727T063525Z.tar.gz`.
- Archive bytes: `960961`.
- Archive SHA-256: `4025B5C8AF79335D1CB5EF8C553CCF7F533B11A610872800A179D15A2CFEFDB7`.
- Archive verification status: `succeeded`.
- Verified file count: `231`.
- Mismatch count: `0`.

The closeout process did not launch models, llama-server, HTTP endpoints, Behavioral Benchmark, resource workload, browser, Playwright, Chromium, or external network.
