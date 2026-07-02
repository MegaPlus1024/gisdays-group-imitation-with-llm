| Model side | Failure summary | Error types | Validation issue codes |
|---|---|---|---|
| first `first_model` | Validation/safety failure: write action targeted a path outside the experiment workspace. | `{'validation_failed_after_repair': 1}` | `{'write_path_outside_workspace': 3, 'missing_required_parameter': 2}` |
| second `qwen2_5_3b_instruct_q4_k_m` | Execution failure: model repeatedly targeted a missing file. | `{'file_not_found': 2}` | `{}` |

Shared weaknesses:
- Both runs have low sequence coherence.
- Neither run completed the full five-step trajectory.
- Both runs show repeated same-parameter behavior.