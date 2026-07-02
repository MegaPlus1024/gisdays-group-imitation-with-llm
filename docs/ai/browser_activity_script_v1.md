# Browser Activity Script v1

## Purpose
Provide controlled browser-like action helpers that validate parameters and return structured simulated results.

## Relationship to Script Registry
Script Registry decides whether an action is allowed. This module provides safe stub implementations for browser-like actions.

## Relationship to future Executor
Future Executor may call these functions after registry and policy validation.

## Supported actions
- `open_url`
- `search_web`
- `read_page_summary`
- `fill_form_stub`

## URL safety rules
- requires explicit scheme (`http`/`https` by default)
- rejects unsafe schemes (`javascript:`, `data:`, etc.)
- rejects credential URLs (`user:pass@host`)
- rejects external hosts by default unless `allow_external_hosts=true`
- rejects `file://` by default
- enforces maximum URL length

## Simulation-only behavior
All actions are simulated in v1:
- no browser process is opened
- no network requests are made
- no Playwright/Selenium integration

## Result format
Each function returns `ScriptExecutionResult` with:
- `action`, `success`, optional `output`
- `error_type`/`error_message` on failure
- metadata describing simulated behavior

## Examples
- `open_url("http://localhost:8080", config)`
- `search_web("local llm test", config)`
- `read_page_summary("http://127.0.0.1:8080", config)`
- `fill_form_stub("http://localhost/form", {"name": "alice"}, config)`

## What this does not implement
- Browser activity script v1 does not open a browser.
- It does not access the internet.
- It does not use Playwright/Selenium.
- It validates browser-like actions and returns structured simulated results.
- Future Executor or browser automation layer may replace the simulated behavior.
- This is not a security sandbox.

## Done criteria
- strict URL validation
- simulation-only outputs
- structured failure responses
- deterministic dispatch behavior

## Next step
Integrate with future executor and optional real browser automation layer behind explicit safety controls.
