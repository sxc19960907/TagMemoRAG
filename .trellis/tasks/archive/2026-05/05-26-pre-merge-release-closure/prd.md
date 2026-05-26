# Pre-merge release closure

## Goal

Complete a full pre-merge closure pass for the browser-first RAG work so the branch has a clear, verified answer on user experience readiness and merge risk.

## Requirements

- Run the same core checks as CI where feasible in the local environment.
- Run browser-first RAG acceptance checks for the real user path.
- Re-run the local quick-start/demo command documented for first-time users.
- Produce a retained closure report summarizing checks, commits, scope, residual risks, and merge readiness.
- Do not hide or stage unrelated local files such as `.codegraph/` and `.mcp.json`.
- Fix any small blocker discovered during the pass; if a blocker is too large, record it clearly as a follow-up instead of stopping silently.

## Acceptance Criteria

- [x] CI-equivalent unit/e2e and eval checks pass, or any failures are fixed/recorded with root cause.
- [x] Browser RAG acceptance checks pass.
- [x] Quick-start/demo path passes.
- [x] A closure report is committed under `docs/` with verification evidence and merge recommendation.
- [x] The task is archived and journaled after the report is committed.

## Outcome

- Added `docs/pre-merge-release-closure-2026-05-26.md`.
- No production code changes were required in this closure pass.
- Local recommendation: branch is ready for normal PR / merge review, with CI re-run after push.

## Validation

- `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py` -> `1227 passed in 21.60s`.
- `uv run python scripts/run_eval_ci.py` -> all 8 eval suites passed.
- `uv run python -m tagmemorag demo library-qa --config examples/config/qa-demo.yaml --output .tmp/tagmemorag-qa-demo/library-qa-response.json` -> `"status": "passed"`.
- `TAGMEMORAG_RUN_BROWSER_UI=1 .venv/bin/python -m pytest tests/integration/test_browser_admin_ui.py -q` -> `6 passed in 12.25s`.
- `node --check` for admin/browser static scripts -> passed.
- `git diff --check` -> passed.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
