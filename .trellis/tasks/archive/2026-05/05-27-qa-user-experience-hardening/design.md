# QA User Experience Hardening Design

## Scope

This task is a browser-first UX hardening pass for the existing QA page. It stays inside:

- `src/tagmemorag/web/templates/qa_page.html`
- `src/tagmemorag/web/static/qa_page.js`
- `src/tagmemorag/web/static/manual_library.css`
- `src/tagmemorag/web/static/i18n.js`
- focused UI/static tests

No backend retrieval or answer behavior changes are planned unless testing reveals a narrow compatibility bug.

## User Flow

The page should support this loop:

1. User lands on `/qa?kb_name=default`.
2. User understands that answers are manual-grounded and sources will appear on the right.
3. User asks a question.
4. Page shows stable progress and prevents duplicate submits.
5. User receives answer, citations, source count, follow-up prompts, and feedback controls.
6. User can click source/citation, continue with a follow-up, copy answer, or retry/rephrase after failure.

## UI Changes

- Add a compact guidance strip near the answer workspace that explains the ask-answer-sources loop.
- Improve empty state copy and visual hierarchy while keeping the composer primary.
- Improve loading state with explicit "retrieving sources" and "drafting answer" cues.
- Improve failure state with action text and a readiness link.
- Improve source metadata text after success to say how many sources were used.
- Improve follow-up section copy to make context behavior more discoverable.

## Contracts

- `/qa/answer` request and response remain unchanged.
- Feedback submission remains the existing `/search/feedback` flow.
- QA session memory remains sessionStorage-only.
- New UI strings use the existing i18n key-as-English pattern.

## Compatibility

- Existing users with saved QA session memory should continue to load prior turns.
- If JavaScript fails, the static shell still displays the composer and readiness link.
- Auth-enabled QA still shows the API token field and uses existing shared token helpers.

## Rollback

The task is additive in page structure and CSS/JS rendering. Rollback is removing the added UI blocks and reverting JS text/meta changes.
