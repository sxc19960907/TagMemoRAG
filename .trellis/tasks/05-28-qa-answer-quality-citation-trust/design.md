# QA answer quality and citation trust hardening design

## Scope

This task is a browser-first acceptance hardening pass. It should strengthen the `/qa` user path with realistic manual questions and only make bounded fixes discovered by that flow.

## Boundaries

- Browser/UI: `tests/integration/test_browser_admin_ui.py` exercises the real `/admin/manual-library` and `/qa` pages.
- Answer generation: `src/tagmemorag/answer/generator.py` remains deterministic for local acceptance. Remote providers are not required.
- Retrieval/API: existing `/answer` and `/retrieve` payload contracts remain unchanged unless a real defect requires a safe additive field.
- Source trust: citation chips and source cards are the user-visible contract for grounding.

## Real Flow

1. Start the app with deterministic answer generation enabled, and PDF assets enabled when real PDFs are used.
2. Upload multiple manuals through Manual Library.
3. Ask realistic questions from `/qa`.
4. Inspect visible answer text, citation chips, source cards, page/source labels, and preview/refusal details.
5. Assert safe UI payload behavior: no storage keys, blob keys, checksums, local paths, raw manifests, or debug IDs.

## Compatibility

Existing tests that expect deterministic extractive answers should continue to pass. Any generator wording changes need targeted unit tests because the browser uses the same local generator.

## Rollback

If a broad retrieval-quality issue appears, document it as follow-up rather than forcing a high-risk ranking rewrite in this task. Keep fixes scoped to answer formatting/refusal/source trust unless the browser flow exposes a clear low-risk defect.
