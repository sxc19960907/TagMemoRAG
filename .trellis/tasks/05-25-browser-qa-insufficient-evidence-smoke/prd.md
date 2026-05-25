# Browser QA insufficient evidence smoke

## Goal

Ensure the QA browser page handles "KB is loaded but the manual evidence cannot fully answer this question" as a clear evidence-limited response, not a raw internal reason or a fabricated answer.

## Requirements

- Add/adjust user-facing QA refusal text so `no_results` is rendered as a clear evidence-insufficient message.
- Add browser-level smoke coverage for a loaded KB whose content does not contain the requested detail.
- The browser smoke must verify the page does not show a raw `no results` internal reason as the main answer.
- The browser smoke must verify the answer explicitly says the evidence is insufficient or cannot confirm the requested detail.
- If the answer includes citations, they must point to the available manual evidence rather than fabricated details.
- Keep browser coverage opt-in behind `TAGMEMORAG_RUN_BROWSER_UI=1`.
- Use deterministic local hashing/noop configuration; no external services.

## Acceptance Criteria

- [ ] QA static asset maps `no_results` to a friendly user-facing evidence-insufficient message.
- [ ] Browser smoke starts from a rebuilt local KB and asks for a detail missing from the available manual evidence.
- [ ] Browser page displays an evidence-limited response and does not expose raw `no results` copy.
- [ ] Browser page does not fabricate the missing part number and any visible source cites the available manual.
- [ ] Browser smoke fails on unexpected console errors.
- [ ] Focused unit/browser tests pass.
- [ ] Completed task is committed, archived, and recorded in the developer journal.

## Notes

- Lightweight task: production scope is limited to user-facing refusal mapping and browser regression coverage.
