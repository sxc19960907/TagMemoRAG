# User Trial Handoff - 2026-05-26

This handoff summarizes the browser-first RAG experience now merged into `master` by PR #26 plus the post-merge browser polish commits through `ca0dd70`.

For the current post-acceptance trial operator guide, use [Trial Operator Handoff - 2026-05-27](trial-operator-handoff-2026-05-27.md). This page is preserved as historical context for the PR #26 handoff.

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

The browser UI now includes an **English / 中文** language switcher. The selected language is stored in browser `localStorage` and follows the user across the admin and Q&A pages.

## Browser Pages

- RAG Workbench: `/admin/rag-workbench?kb_name=default`
- Manual Library: `/admin/manual-library?kb_name=default`
- Retrieval Quality: `/admin/retrieval-quality?kb_name=default`
- People & Access: `/admin/people?kb_name=default`
- Ask Q&A: `/qa?kb_name=default`

The local demo config has auth disabled, so the API token field can stay empty. In auth-enabled deployments, the admin/search token is shared in browser `sessionStorage` across the admin and QA pages for the current browser session.

## Trial Flow

1. Open `/`.
2. Optionally switch the UI language between **English** and **中文**.
3. Use top navigation to open Manual Library.
4. Confirm `demo-service-manual` is searchable and has no pending rebuild.
5. Click **Ask Q&A**.
6. Ask `蒸汽很小怎么办？`.
7. Confirm the answer appears as a conversation-style user question and manual answer.
8. Confirm the source list cites `demo-service-manual.md`.
9. Click a `cit_###` citation in the answer and confirm the matching source card is focused.
10. Return to Manual Library.
11. Upload a small `.md`, `.txt`, or text-based `.pdf` manual.
12. If **Trigger rebuild** is checked, wait for the **Next step** panel to say **Manual is ready for Q&A**.
13. If the page says **Manual uploaded, rebuild needed**, click **Rebuild now** and wait for completion.
14. Click **Ask in Q&A** from the next-step panel.
15. Ask a question that is directly answered by the uploaded manual.
16. Ask a follow-up such as `那下一步呢？` and confirm the Q&A page shows conversation context.

For a shorter step-by-step guide, use [Browser RAG Quick Start](browser-rag-quick-start.md).

## Verified Locally

The pre-merge closure on PR #26 passed:

- `uv run pytest tests/unit tests/e2e --ignore=tests/e2e/test_perf.py` -> `1227 passed`.
- `uv run python scripts/run_eval_ci.py` -> all 8 hashing-baseline eval suites passed.
- `uv run python -m tagmemorag demo library-qa --config examples/config/qa-demo.yaml --output .tmp/tagmemorag-qa-demo/library-qa-response.json` -> `"status": "passed"`.
- `TAGMEMORAG_RUN_BROWSER_UI=1 .venv/bin/python -m pytest tests/integration/test_browser_admin_ui.py -q` -> `6 passed`.
- Static browser/admin scripts passed `node --check`.

This post-merge handoff pass re-verified the focused master path listed in the task journal.

The post-polish master pass on 2026-05-26 also verified:

- `git push origin master` succeeded through `ca0dd70`.
- Browser flow after push: root page, language switching, manual upload, validation, rebuild next-step guidance, Q&A handoff, answer, citation focus, follow-up context, and mobile layout.
- Screenshots were saved under `/tmp/tagmemorag-post-push-user-flow`.
- Browser console errors: `[]`.
- Mobile Q&A check: no horizontal overflow and the center conversation pane starts at the top of the viewport.

## What Is Ready

- Browser navigation between the RAG admin pages and QA.
- English / 中文 UI switching across browser pages.
- Manual upload, rebuild, searchable-state visibility, and QA handoff.
- Manual Library next-step guidance after upload: rebuild needed, rebuilding, ready for Q&A, and direct Ask in Q&A handoff.
- Browser QA answers with conversation-style messages, citation chips, source cards, evidence-limited messaging, and follow-up context.
- Citation chips focus the matching source card for traceability.
- People & Access visibility for config-backed API-key identities.
- One-time browser key generation and lifecycle guidance for config updates.
- Local offline quick-start path without external providers.

## Known Non-Goals For This Trial

- Live provider rollout is not covered by this local demo path.
- Qdrant/S3 deployment verification is not covered by this local demo path.
- People & Access still guides config changes; it does not write production auth config online.
- Browser smoke tests are opt-in because they require Playwright/Chromium.

Use the production-provider and deployment runbooks before a live-provider or infrastructure trial.
