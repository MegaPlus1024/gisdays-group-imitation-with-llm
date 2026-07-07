# Generated offline by prepare_first_single_trial_run_packet.py.
# This script starts local runtime only when you run it manually.
# Runtime execution still requires --allow-runtime-execution and the explicit confirmation token.
.\.venv\Scripts\python.exe scripts/run_single_trial_controlled.py `
  --plan artifacts/first_run_packets/phase_8_24_docx_precreate_retry/model_pair_plan.json `
  --readiness-summary artifacts/first_run_packets/phase_8_24_docx_precreate_retry/model_pair_execution_readiness_summary.json `
  --entrypoint src.agent.model_pair_local_pipeline_entrypoint:run_local_model_pair_trial `
  --local-pipeline-config artifacts/first_run_packets/phase_8_24_docx_precreate_retry/local_pipeline_config.json `
  --output-dir artifacts/single_trial_runs/phase_8_24_docx_precreate_retry `
  --trial-id office_document_file_workflow_basic_v1__second_model__to__first_model__r01 `
  --allow-runtime-execution `
  --confirm-runtime-execution SINGLE_TRIAL_RUNTIME_OPT_IN `
  --auto-matrix-adapter-outputs `
  --run-id phase_8_24_docx_precreate_retry `
  --tag controlled_single_trial
