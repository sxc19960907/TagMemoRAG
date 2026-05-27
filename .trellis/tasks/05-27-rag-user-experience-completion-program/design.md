# RAG User Experience Completion Program Design

## Shape

This parent task owns the product direction and final integration review. Implementation happens in child tasks so each deliverable can be planned, checked, archived, and committed independently.

## Boundaries

- Browser-first QA behavior is the primary target.
- Admin pages matter when they feed the QA experience, but admin polish is not the main success metric for this parent.
- Retrieval, answer generation, fixtures, demo seeding, and browser tests may be touched when they directly improve user-facing RAG readiness.
- Network-dependent publishing is intentionally outside this program until the user asks to resume GitHub push.

## Data And Experience Flow

1. A user opens `/qa?kb_name=default`.
2. The page shows a useful empty state, suggested questions, KB context, and language-aware copy.
3. The user asks a question.
4. Retrieval returns relevant manual passages.
5. Answer generation produces a grounded answer, citations, and follow-up prompts.
6. If retrieval or answer generation cannot satisfy the request, the page shows visible recovery actions instead of a silent or confusing failure.
7. Feedback and eval paths help future quality improvement.

## Compatibility

- Existing API contracts should remain compatible unless a child task explicitly plans an API change.
- Browser tests should prefer stable selectors already used in `tests/integration/test_browser_admin_ui.py`.
- Demo fixtures should reuse existing coffee-machine content where possible to avoid duplicate sample truth.

## Rollback

Each child task should keep changes scoped enough to revert independently. Parent-task artifacts can remain as the program map even if a child is rolled back.
