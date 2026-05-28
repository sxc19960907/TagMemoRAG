# PDF preview success path and config guidance

## Goal

Close the happy-path loop for PDF source previews: when page snapshots are enabled and PyMuPDF is available, a user can upload/index a PDF, ask in Q&A, and open the cited page preview from the browser. Admin diagnostics should also guide operators toward the exact config needed for that success path.

## Requirements

- Verify the local happy path with a real or synthetic PDF and PyMuPDF-backed page snapshots.
- Improve admin-facing configuration guidance when source previews are disabled or partially configured.
- Preserve the existing safe `/assets/{asset_id}` opening model and KB authorization.
- Keep Q&A stable when preview generation is unavailable; preview support remains a verification enhancement.
- Do not add a full PDF viewer, raw document download, or expose storage keys/local paths.

## Acceptance Criteria

- [x] A browser-facing flow validates PDF upload/rebuild/Q&A/source-preview opening when snapshots are enabled.
- [x] Readiness or Manual Library diagnostics clearly state the required config flags for enabling PDF previews.
- [x] Existing fallback behavior for missing renderer/assets still passes.
- [x] Tests cover both preview success and configuration guidance without requiring optional packages in normal CI.
- [x] No unsafe asset metadata appears in user-facing payloads or static JS.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
