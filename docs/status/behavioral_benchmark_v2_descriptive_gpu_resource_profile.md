# Behavioral Benchmark v2: Descriptive GPU Resource Profile

## Status

- Analysis type: post-hoc descriptive resource profiling.
- Project commit: `eaded9c`.
- Behavioral evidence tag: `behavioral-benchmark-v2-final` at `c667200`.
- Correctness winner: none.
- Resource winner declared: no.
- GPU offload: verified for all profiles.
- Measured requests: 30 per model.

These measurements do not override the correctness gate. All three models failed Behavioral Benchmark v2, so resource measurements are reported descriptively rather than used to select a winner.

## Common configuration

- GPU: NVIDIA RTX PRO 4000 Blackwell, 24,467 MB VRAM.
- Driver: 582.16.
- Context size: 12,288.
- GPU layers argument: 999.
- Parallel slots: 1.
- Warmup requests per case: 3.
- Measured requests per case: 10.
- Cases: short, medium, long.
- Deterministic harness lifecycle: baseline, server loading, loaded-idle stabilization, smoke, warmup, workload, shutdown.

## Results

| Model | GGUF GiB | Loaded-idle VRAM MB | Peak VRAM MB | Headroom MB | Short ms | Medium ms | Long ms | Short tok/s | Medium tok/s | Long tok/s |
| --- | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: | ---: |
| `fifth_model` | 17.353 | 19,103 | 19,370 | 5,097 | 538.0 | 1,253.5 | 2,560.0 | 163.65 | 155.74 | 131.93 |
| `third_model` | 9.792 | 11,792 | 11,816 | 12,651 | 1,497.7 | 3,526.9 | 6,866.1 | 51.45 | 49.52 | 44.48 |
| `fourth_model` | 13.349 | 15,541 | 15,580 | 8,887 | 2,071.1 | 5,008.0 | 9,710.0 | 37.95 | 36.03 | 33.48 |

## Validation

Every profile satisfied all of the following:

- harness status `succeeded`;
- zero validation failures;
- direct smoke completed successfully;
- actual GPU offload verified;
- loaded-idle state stabilized;
- 30/30 measured requests succeeded;
- every configured token budget was met;
- server process stopped without forced kill;
- no tracked repository files changed during execution.

## Interpretation

- `fifth_model` consumed the most VRAM and produced the highest throughput.
- `third_model` consumed the least VRAM and had intermediate latency and throughput.
- `fourth_model` consumed an intermediate amount of VRAM and had the highest latency of the three profiles.
- Prompt-token totals differ slightly because each model tokenizes the same textual corpus differently.
- All models reached 99–100% peak GPU utilization, confirming that the measurements represent GPU-backed execution.

## Limitation

The corpus is a deterministic synthetic resource workload, not the Behavioral Benchmark v2 multi-agent task suite. These results describe runtime characteristics on this specific machine and software configuration. They do not establish model quality, correctness, or a benchmark winner.

## Conclusion

Correctness remains lexicographically prior to resource use. Because no model passed the correctness gate, the benchmark winner remains **none**. The resource measurements are retained only as descriptive hardware/runtime evidence.
