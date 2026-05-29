# Browser black-box RAG acceptance

## Goal

Validate the current TagMemoRAG browser experience as a normal user would experience it, without relying on code inspection for the outcome judgment.

## Requirements

- Start from the documented local browser demo path.
- Use real browser pages rather than CLI-only verification.
- Confirm the user can reach the main browser surfaces from the root page.
- Confirm Q&A can answer against an indexed manual and exposes citations/sources.
- Confirm the experience is understandable enough for a first-time user.
- Record user-facing gaps as concrete follow-up work instead of silently fixing unrelated scope.

## Acceptance Criteria

- [x] Local demo data can be seeded successfully.
- [x] Local server starts with `examples/config/qa-demo.yaml`.
- [x] Root, RAG Workbench, Manual Library, and Q&A pages are reachable in the browser.
- [x] Q&A answer flow returns a grounded answer for the demo manual.
- [x] Citation/source affordances are visible enough for a user to verify the answer.
- [x] Any discovered user-facing gaps are documented with severity and recommended next action.

## Black-Box Result

Overall result: pass with follow-up UX cleanup.

Clean demo path:

- Deleted the previous `.tmp/tagmemorag-qa-demo` workspace.
- Ran `uv run python -m tagmemorag demo library-qa --config examples/config/qa-demo.yaml --output .tmp/tagmemorag-qa-demo/library-qa-response.json`.
- Started the local server with `uv run python -m tagmemorag serve --host 127.0.0.1 --port 8000 --config examples/config/qa-demo.yaml`.
- Opened `http://127.0.0.1:8000/qa?kb_name=default` in the in-app browser.
- Asked `蒸汽很小怎么办？` from the visible Q&A page.

Observed browser result:

- Q&A showed `default · ready · 5 个片段`.
- The answer was high confidence and cited two `demo/demo-service-manual.md` sources.
- Clicking `cit_001` focused the matching source card, with visible card highlighting and the source passage available for manual verification.
- The page layout was understandable as a user-facing QA surface: left context/navigation, central answer, right source panel.

Follow-up gaps:

- P2: Demo workspace can be polluted by old `.tmp/tagmemorag-qa-demo` data if the user reuses an existing local directory. The first black-box pass showed stale `blackbox/temperature-manual.md` content mixed into the default KB. Recommended action: make the documented demo path either reset the demo workspace by default or clearly offer a `--clean` / reset command.
- P3: The Q&A `清除` action did not make the current browser history feel fully reset during repeated testing; duplicate answered entries remained visible after repeated asks. Recommended action: review the clear-history interaction and empty-state feedback.
- P3: Text source cards correctly show snippets, but they also say `暂无预览`. For text/markdown manuals this is accurate but slightly discouraging. Recommended action: adjust copy to distinguish "no page preview needed" from "preview unavailable".
