# Generated offline by prepare_controlled_mini_matrix_packet.py.
# This script does not start servers; start endpoints manually before running.
# Runtime execution still requires the explicit confirmation token.
.\.venv\Scripts\python.exe scripts/run_single_trial_controlled.py `
  --plan artifacts/first_run_packets/phase_8_26_mini_matrix_r3/model_pair_plan.json `
  --readiness-summary artifacts/first_run_packets/phase_8_26_mini_matrix_r3/model_pair_execution_readiness_summary.json `
  --entrypoint src.agent.model_pair_local_pipeline_entrypoint:run_local_model_pair_trial `
  --local-pipeline-config artifacts/first_run_packets/phase_8_26_mini_matrix_r3/local_pipeline_config.r02.json `
  --output-dir artifacts/single_trial_runs/phase_8_26_mini_matrix_r2 `
  --trial-id office_document_file_workflow_basic_v1__second_model__to__first_model__r02 `
  --allow-runtime-execution `
  --confirm-runtime-execution SINGLE_TRIAL_RUNTIME_OPT_IN `
  --auto-matrix-adapter-outputs `
  --run-id phase_8_26_mini_matrix_r2 `
  --tag controlled_mini_matrix
