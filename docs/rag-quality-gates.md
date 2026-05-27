# RAG Quality Gates

This guide defines which local checks to run for TagMemoRAG changes. Use the smallest tier that covers the risk of the change, then move up when the change touches user-facing QA, release readiness, or live-provider behavior.

## Tier Summary

| Tier | Purpose | Run When | Commands |
| --- | --- | --- | --- |
| T0 Static sanity | Catch syntax and browser-script mistakes before tests | Any Python, CLI, or browser JS/CSS-adjacent change | `python3 -m py_compile <changed-python-files>`<br>`node --check src/tagmemorag/web/static/qa_page.js` when QA JS changes<br>`git diff --check` |
| T1 Focused unit | Check the changed contract quickly | Any backend, CLI, API, answer, manual-library, or readiness change | `uv run pytest <focused-test-files> -q` |
| T2 Backend RAG composition | Prove deterministic local build/retrieve/answer/queryplan/bundle paths compose | RAG pipeline, CLI readiness, manual-library, or answer path changes | `uv run python -m tagmemorag readiness smoke` |
| T3 Browser QA readiness | Prove the normal user can experience QA in the browser | QA UI, manual-library-to-QA flow, first-run demo, feedback loop, or browser navigation changes | `uv run python -m tagmemorag readiness browser-qa` |
| T4 Browser full suite | Exercise all browser admin/RAG workflows | Before release-style local closure, or broad admin/browser changes | `uv run python -m tagmemorag readiness browser-qa --full` |
| T5 Eval regression | Check retrieval ranking and accepted fixture behavior | Retrieval ranking, parser/chunking, metadata/tagging, reranker, or eval changes | `uv run python scripts/run_eval_ci.py` |
| T6 Release local closure | Build confidence before merge/release handoff | Before a substantial PR, release branch, or user trial handoff | `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py`<br>`uv run python scripts/run_eval_ci.py`<br>`uv run python -m tagmemorag readiness browser-qa --full` |
| T7 Live/provider checks | Validate external providers and deployment surfaces | Only when touching provider config, Qdrant/S3, live model calls, or production rollout | Follow `docs/production-provider-smoke-runbook.md`, `docs/production-pilot-runbook.md`, and `docs/production-environment-verification.md` |

## Browser-First RAG Change Gate

For normal user-facing QA work, run this sequence before calling the task complete:

```bash
python3 -m py_compile src/tagmemorag/cli_parser.py src/tagmemorag/cli_eval.py src/tagmemorag/browser_qa_readiness.py
node --check src/tagmemorag/web/static/qa_page.js
uv run pytest tests/unit/test_manual_library_ui.py tests/unit/test_answer_api.py -q
uv run python -m tagmemorag readiness browser-qa
```

Adjust the file list to match the actual change. If the change does not touch QA JS, skip the `node --check` line. If the change touches a different unit contract, replace the unit test list with the focused tests for that contract.

## First-Run Demo Gate

When changing demo data, suggested questions, or the local browser walkthrough:

```bash
uv run python -m tagmemorag demo library-qa \
  --config examples/config/qa-demo.yaml \
  --output .tmp/tagmemorag-qa-demo/library-qa-response.json

uv run python -m tagmemorag readiness browser-qa
```

The demo report should have `status: "passed"`, a searchable `demo-service-manual`, and a QA question aligned with the browser suggested questions.

## Release Local Closure

Use this before a larger merge, user trial, or release handoff:

```bash
uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py
uv run python scripts/run_eval_ci.py
uv run python -m tagmemorag readiness smoke
uv run python -m tagmemorag readiness browser-qa --full
git diff --check
```

Keep browser UI tests opt-in outside this command because they require Playwright/Chromium. The `readiness browser-qa` command sets `TAGMEMORAG_RUN_BROWSER_UI=1` internally.

## Live Provider And Deployment Gates

Do not run live-provider checks by default during ordinary local RAG UX work. They may contact external services, require credentials, and depend on local Docker/provider state.

Use live checks when the task changes provider integration, production config, Qdrant/S3 behavior, or deployment readiness:

```bash
uv run python -m tagmemorag production-provider verify --level smoke
uv run python -m tagmemorag pilot run --format json --output .tmp/pilot/report.json
```

For browser-first local pilot evidence, add `--include-browser-qa` to the local
pilot command. Add `--browser-qa-full` only for release-style closure or broad
browser/admin changes.

See:

- `docs/production-provider-smoke-runbook.md`
- `docs/production-pilot-runbook.md`
- `docs/production-environment-verification.md`

## GitHub And CI

Local gates are the developer-side signal. CI remains authoritative once changes are pushed. For the current long-running RAG UX program, GitHub push is deferred until network conditions recover or the user explicitly asks to retry.
