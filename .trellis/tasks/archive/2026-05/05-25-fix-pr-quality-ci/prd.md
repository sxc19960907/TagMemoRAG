# Fix PR quality CI failures

## Goal

Restore the PR #24 Quality CI check without changing the browser RAG user experience delivered on the branch.

## Requirements

- Fix the failing `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py` check from GitHub Actions run `26401070166`.
- Keep the scope limited to the observed CI failures:
  - `tests/unit/test_langchain_ingestion.py::test_langchain_provider_builds_html_document`
  - passing-path cases in `tests/unit/test_reranking_gate_batch.py`
- Preserve optional-dependency behavior for LangChain ingestion instead of making default installs depend on network-heavy or unnecessary packages unless the project metadata already intends that.
- Preserve reranking/release-readiness gate semantics for real failing reports; only fix incorrect behavior for passing synthetic reports or test setup drift.
- Do not touch unrelated untracked files (`.codegraph/`, `.mcp.json`).

## Acceptance Criteria

- [ ] Focused CI failures pass locally.
- [ ] Relevant broader test group passes locally.
- [ ] Changes are committed and pushed to `codex/agent-loop-driver`.
- [ ] PR #24 Quality CI is rechecked, or a clear status is reported if the rerun is still pending.

## Notes

- This is a lightweight CI repair task; PRD-only planning is sufficient.
