# Test Tier And Quality Gate Documentation Design

## Scope

This is a documentation and process task. It should not add new test runners or change runtime behavior. The work should consolidate existing commands into one durable guide and link to it from existing docs.

## Proposed Doc

Add `docs/rag-quality-gates.md`.

The doc should include:

- A short explanation of the tier model.
- A table of gates with purpose, command, when to run, and expected cost.
- A browser-first RAG change checklist.
- A release/local regression checklist.
- Notes for live-provider and deployment checks.
- Guidance that GitHub push/CI is resumed only when network conditions allow.

## Links

- README readiness section should link to the new doc after the backend and browser readiness commands.
- `docs/system-test-plan.md` should point release readers to the new gate matrix before listing lower-level command examples.

## Rollback

Reverting this task only removes documentation; no runtime behavior changes are expected.
