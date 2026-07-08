# Evidence: guarded Playwright browser suite run

## Summary

- Status: succeeded
- Guarded real browser path: executed by operator
- Browser backend: chromium via playwright, headless=True
- Actions attempted/succeeded/failed: 30/30/0
- Expected results: 30/30 passed
- Scenario: suite
- Fixture server: loopback-only local fixture server
- Evidence level: guarded_real_browser_suite_succeeded

## What was verified

- Playwright/Chromium launched through the guarded operator path.
- Local fixture server served browser pages through loopback URLs.
- Logical URLs mapped to loopback fixture files.
- Browser actions opened pages, extracted text, searched content and prepared snapshots.
- Expected text markers were found.
- No external network was required.
- Suite mode attempted bounded fixture-backed scenarios.
- Required browser actions covered: 8/8

## Suite coverage

- Scenarios attempted/succeeded/failed: 4/4/0
- Scenario count: 4
- Overall action coverage ratio: 1.0

## Evidence details

- Source schema: `autonomous_browser_playwright_suite_summary_v1`
- Operator id: `browser_suite_playwright_operator_v1`
- Passed: `true`
- Served URL policy: loopback_only=True, checked=60
- Logical URLs visited:
  - `https://local.intranet/tickets/1`
  - `https://docs.local/docs/policy`
  - `https://local-intranet.test/`
  - `https://local-intranet.test/tickets`
  - `https://local-intranet.test/docs/policy`
  - `https://local-intranet.test/portal/request`
  - `https://local-intranet.test/portal/submitted`
  - `https://local.intranet/`
  - `https://local.intranet/docs/policy`
  - `https://portal.local/portal`
  - `https://portal.local/portal/approvals`
  - `https://portal.local/portal/status`

## Limitations

- local loopback fixture suite only
- headless Chromium only
- not external websites
- not production autonomous browser use
- no mail/git actions
- no LLM judge
- no production hardening claim
