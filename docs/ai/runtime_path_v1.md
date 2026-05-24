# Local LLM Runtime Path v1

## 1. Decision

The primary runtime path for this project is `llama.cpp` using `llama-server`. The Python control layer will talk to a local HTTP server that exposes an OpenAI-compatible chat endpoint. Ollama is allowed only as a fallback for quick sanity checks and is not the primary research path.

## 2. OS assumption

The first local development target is Windows 11 x64. This is the environment to document and stabilize first. A later server target may be Ubuntu 24.04 LTS, but that is explicitly out of scope for v1.

## 3. Python assumption

Python 3.11 or 3.12 is the supported assumption for the first runtime path. The initial adapter layer should stay small and use standard Python packaging with lightweight dependencies only.

## 4. Model format

The required model format is GGUF. The first model class should be a 7B-8B instruct model using Q4 or Q5 quantization. This is a practical starting point for CPU-first local research before any later hardware-specific tuning.

## 5. Model storage

Local model files belong in `models/gguf/`. The example model path is:

```text
models/gguf/first_model.gguf
```

Model binaries are local assets and are not committed to git. Later runs should log the exact filename, source, quantization, and checksum for reproducibility.

## 6. Runtime command assumption

The v1 assumption is that a locally launched `llama-server` process will host the model and expose an HTTP interface on the local machine. The exact launch command is intentionally not standardized yet because this task is only defining the runtime path and project skeleton, not validating a concrete server invocation.

The runtime contract for v1 is therefore:

- A local process exists outside the Python adapter
- That process serves a model loaded from `models/gguf/`
- The Python layer depends on the HTTP contract, not on direct `llama.cpp` process details

## 7. API assumption

The Python adapter will target a local OpenAI-compatible endpoint. The initial assumption is:

- Host: `127.0.0.1`
- Port: `8080`
- Base URL: `http://127.0.0.1:8080/v1`
- API style: OpenAI-compatible chat endpoint

The agent code must talk through an internal Python interface and must not directly depend on `llama.cpp` request specifics throughout the rest of the codebase. This keeps the runtime replaceable later if needed.

## 8. Expected model output

The model is expected to return one structured next-action object in JSON form:

```json
{
  "action": "string",
  "parameters": {},
  "reason": "string",
  "expected_result": "string"
}
```

This output is intended to be validated by the Python control layer before any script or tool action is accepted.

Invalid output cases include:

- free-form essay
- multiple actions
- missing parameters
- action not in script registry
- impossible action
- invalid JSON

## 9. CPU/GPU assumption

The first hardware assumption is CPU-first. GPU is not required for v1 setup. GPU support may be added later, but it is optional and does not block the initial reproducible runtime path.

## 10. Non-goals for this task

- do not compare models yet
- do not tune prompts deeply yet
- do not build full agent loop yet
- do not run 10-agent simulation yet
- do not fine-tune yet
- do not optimize performance yet

## 11. Done criteria

This v1 runtime-path setup task is done when:

- the repository skeleton exists and is reproducible
- the runtime assumptions are documented in one place
- the local config example captures the runtime, model, hardware, and output contract
- the Python code exposes a minimal schema layer for the expected next-action object
- the client layer remains a strict stub until a runtime smoke test is defined
- model binaries are kept out of git
- smoke-log storage is defined without creating fake results
