# QA First-Run Guidance Loop Design

## Existing Facts

- The Q&A page already has a left-rail upload form that posts to the existing manual-library APIs and polls rebuild completion.
- The center answer workspace currently starts with generic "ask about a symptom" copy even when the KB is empty.
- Suggestions are static and do not change after upload.
- Rebuild failure messages are text-only.

## Design

Keep this as a frontend-only improvement:

- Add a first-run guidance renderer in `qa_page.js` that can replace the initial empty-state answer with upload-first guidance.
- Detect empty/not-ready state from `/kb` results when possible; also default to upload-first guidance while only the placeholder KB is known.
- Track the latest uploaded manual metadata in memory after QA-page upload.
- Build a small set of suggested questions from title/category/tags and render them in the existing suggestions list.
- Add recovery links inside the upload message area when rebuild fails.

No backend schema changes are required.

## Testing

- Static/unit tests assert the new JS functions and copy exist.
- Browser test extends the QA-page upload flow to verify upload-derived suggestions appear and are clickable.
- Existing browser readiness and Q&A tests remain green.
