# Document and browser smoke RAG user flow

## Goal

Make the current local RAG path understandable and regression-guarded for a normal user: seed demo knowledge, validate CLI/manual-library QA, start the web app, inspect Manual Library, ask a QA question, and confirm cited sources.

## Requirements

- Document the end-to-end local RAG demo path in the main user-facing docs.
- Include both CLI-only validation and browser UI validation steps.
- Keep the path offline-friendly by using the existing hashing/NPZ/noop demo configuration.
- Add an optional browser-level smoke test that exercises the same Manual Library to QA path through the local web UI.
- Gate the browser smoke behind the existing opt-in environment variable so normal unit/integration runs stay fast and deterministic.
- Do not commit generated demo data, provider payloads, secrets, vectors, or raw unbounded source snippets.

## Acceptance Criteria

- [ ] README explains how to seed the local demo KB, run `demo qa`, run `demo library-qa`, start the local server, and inspect the Manual Library and QA browser pages.
- [ ] Browser smoke verifies a managed manual becomes searchable, the QA page answers `服务模式怎么进入？`, and the visible source cites `demo-service-manual.md`.
- [ ] Browser smoke fails on unexpected console errors.
- [ ] Focused unit tests pass.
- [ ] Opt-in browser integration test is runnable with `TAGMEMORAG_RUN_BROWSER_UI=1`.
- [ ] Completed task is archived after verification and commit.

## Notes

- Lightweight task: existing APIs, CLI, fixtures, and browser-test harness should be reused instead of adding a new design layer.
