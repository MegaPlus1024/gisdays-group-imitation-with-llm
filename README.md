# local-llm-agent-lab

Local LLM agent simulation research prototype.

## Purpose

This repository is for researching a reproducible local LLM runtime path for agent-style experiments. The current focus is documenting and preparing the local runtime contract, not building the full agent yet.

## Current Stage

Runtime path setup.

## Non-Goals For Now

- No model comparison yet
- No full agent loop yet
- No fine-tuning
- No multi-agent simulation
- No final report yet

## Model Files

GGUF model files are expected under `models/gguf/` and are not committed to git.

## Planned Layout

- `configs/` stores local runtime configuration examples
- `docs/ai/` stores runtime-path decisions
- `models/gguf/` stores local GGUF model files
- `logs/smoke/` stores future smoke-test logs
- `src/agent/` stores the Python control-layer skeleton
- `tests/` stores schema validation tests

## Future Command Placeholders

The runtime smoke-test and server launch commands are intentionally not defined yet. They will be added after the first local runtime path is validated.

```bash
python -m pip install -r requirements.txt
pytest
# TBD: local llama-server launch command
# TBD: runtime smoke-test command
```
