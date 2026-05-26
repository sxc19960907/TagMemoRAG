# Pre-Merge Release Closure - 2026-05-26

Branch: `codex/admin-people-management-ui`

Base: `master` at merge-base `2e6ed6021fe2a8733f98eb05185376e9097082a1`

## Recommendation

This branch is ready for a normal PR / merge review from the local verification side.

The browser-first RAG path is usable end to end: a user can open the server root, navigate through the admin browser pages, upload a manual, rebuild the managed library, open QA from the UI, ask a question, and receive cited evidence.

## Scope Verified

- Root route to RAG Workbench.
- RAG Workbench navigation to Manual Library, Retrieval Quality, People & Access, and Ask Q&A.
- Manual Library upload, rebuild, searchable state, diagnostics, and QA navigation.
- QA answer flow, citations, insufficient-evidence messaging, and follow-up context.
- Retrieval Quality review/promote preview flow.
- People & Access safe API-key summary, browser key generation, lifecycle guidance, and shared token handling.
- Browser quick-start documentation for local offline use.

## Local Verification

| Check | Result |
| --- | --- |
| `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py` | Passed: `1227 passed in 21.60s` |
| `uv run python scripts/run_eval_ci.py` | Passed: all 8 hashing-baseline eval suites |
| `uv run python -m tagmemorag demo library-qa --config examples/config/qa-demo.yaml --output .tmp/tagmemorag-qa-demo/library-qa-response.json` | Passed: demo report returned `"status": "passed"` |
| `TAGMEMORAG_RUN_BROWSER_UI=1 .venv/bin/python -m pytest tests/integration/test_browser_admin_ui.py -q` | Passed: `6 passed in 12.25s` |
| `node --check` for admin/browser static scripts | Passed |
| `git diff --check` | Passed |

## Eval Gate Detail

`scripts/run_eval_ci.py` passed all hashing-baseline suites:

- `coffee.jsonl`
- `cross_kb_negatives.jsonl`
- `fault_codes.jsonl`
- `mixed_language.jsonl`
- `model_numbers.jsonl`
- `product_manuals.jsonl`
- `tag_cooccurrence.jsonl`
- `tag_rerank_edge.jsonl`

## Residual Risks

- Browser automation tests are opt-in and were run locally in this pass; CI still runs the default unit/e2e plus eval gates.
- Live provider checks, Qdrant/S3 deployment checks, and production API-key environments were not part of this closure pass. Use the production-provider runbooks before a live-provider rollout.
- The local working tree still has unrelated untracked `.codegraph/` and `.mcp.json` files. They were intentionally left unstaged and should not be included in the PR unless separately reviewed.

## Merge Notes

- Expected PR theme: browser-first admin/RAG experience hardening.
- Include this report with the PR summary as the local verification record.
- Re-run CI after pushing; if CI differs from local results, treat CI as authoritative for merge readiness.
