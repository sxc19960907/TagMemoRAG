# PDF page preview readiness and QA source opening

## Goal

Make PDF page preview support visible and trustworthy across the admin readiness flow and the user Q&A source cards. When page snapshots are unavailable, the UI should explain the safe, user-facing reason without exposing internal storage keys, filesystem paths, checksums, node ids, or raw diagnostics.

## Requirements

- Manual Library diagnostics must expose a bounded `source_preview` status derived from asset settings and the latest asset extraction metadata.
- RAG Readiness must surface source preview as a trust/readability signal without blocking the core Q&A path when retrieval is otherwise usable.
- Q&A source cards must continue to open only safe `/assets/{asset_id}` URLs and must show a clearer fallback reason when a preview cannot be opened.
- Missing optional PDF rendering support, disabled asset extraction, missing preview assets, and failed extraction should each have understandable admin recommendations.
- Existing RAG answer, upload, OCR, and document parsing behavior must remain compatible.

## Acceptance Criteria

- [x] Manual diagnostics include sanitized source preview readiness and recommendations for disabled snapshots or missing renderer.
- [x] RAG Readiness includes source preview detail and recommendation when PDFs exist but page previews are unavailable.
- [x] Q&A source verification fallback copy explains the reason in safe language and still avoids unsafe asset metadata.
- [x] Focused unit/static tests cover the new diagnostics, readiness, and QA sanitization/copy behavior.
- [x] Browser-facing Q&A flow is validated for the no-renderer fallback path.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
