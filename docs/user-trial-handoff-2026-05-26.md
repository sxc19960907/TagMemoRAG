# User Trial Handoff - 2026-05-26

This handoff summarizes the browser-first RAG experience now merged into `master` by PR #26.

## Entry Point

Start the local offline demo:

```bash
uv run python -m tagmemorag demo library-qa \
  --config examples/config/qa-demo.yaml \
  --output .tmp/tagmemorag-qa-demo/library-qa-response.json

uv run python -m tagmemorag serve \
  --host 127.0.0.1 \
  --port 8000 \
  --config examples/config/qa-demo.yaml
```

Then open:

```text
http://127.0.0.1:8000/
```

The root page opens RAG Workbench for `kb_name=default`.

## Browser Pages

- RAG Workbench: `/admin/rag-workbench?kb_name=default`
- Manual Library: `/admin/manual-library?kb_name=default`
- Retrieval Quality: `/admin/retrieval-quality?kb_name=default`
- People & Access: `/admin/people?kb_name=default`
- Ask Q&A: `/qa?kb_name=default`

The local demo config has auth disabled, so the API token field can stay empty. In auth-enabled deployments, the admin/search token is shared in browser `sessionStorage` across the admin and QA pages for the current browser session.

## Trial Flow

1. Open `/`.
2. Use top navigation to open Manual Library.
3. Confirm `demo-service-manual` is searchable and has no pending rebuild.
4. Click **Ask Q&A**.
5. Ask `服务模式怎么进入？`.
6. Confirm the answer mentions holding the clean and hot-water buttons for three seconds.
7. Confirm the source list cites `demo-service-manual.md`.
8. Return to Manual Library.
9. Upload a small `.md`, `.txt`, or text-based `.pdf` manual.
10. Keep **Trigger rebuild** checked.
11. Wait until the table marks the manual searchable and rebuild state clear.
12. Ask a question that is directly answered by the uploaded manual.

For a shorter step-by-step guide, use [Browser RAG Quick Start](browser-rag-quick-start.md).

## Verified Locally

The pre-merge closure on PR #26 passed:

- `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py` -> `1227 passed`.
- `uv run python scripts/run_eval_ci.py` -> all 8 hashing-baseline eval suites passed.
- `uv run python -m tagmemorag demo library-qa --config examples/config/qa-demo.yaml --output .tmp/tagmemorag-qa-demo/library-qa-response.json` -> `"status": "passed"`.
- `TAGMEMORAG_RUN_BROWSER_UI=1 .venv/bin/python -m pytest tests/integration/test_browser_admin_ui.py -q` -> `6 passed`.
- Static browser/admin scripts passed `node --check`.

This post-merge handoff pass re-verified the focused master path listed in the task journal.

## What Is Ready

- Browser navigation between the RAG admin pages and QA.
- Manual upload, rebuild, searchable-state visibility, and QA handoff.
- Browser QA answers with citations, evidence-limited messaging, and follow-up context.
- People & Access visibility for config-backed API-key identities.
- One-time browser key generation and lifecycle guidance for config updates.
- Local offline quick-start path without external providers.

## Known Non-Goals For This Trial

- Live provider rollout is not covered by this local demo path.
- Qdrant/S3 deployment verification is not covered by this local demo path.
- People & Access still guides config changes; it does not write production auth config online.
- Browser smoke tests are opt-in because they require Playwright/Chromium.

Use the production-provider and deployment runbooks before a live-provider or infrastructure trial.
