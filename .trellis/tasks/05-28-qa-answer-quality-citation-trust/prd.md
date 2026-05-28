# QA answer quality and citation trust hardening

## Goal

Harden the user-facing `/qa` experience so realistic manual questions produce usable, grounded answers with inspectable citations, and unsafe/unsupported conclusions are refused instead of guessed.

This follows the real PDF source-preview acceptance task: previews now work, so the next risk is whether the visible answer and citation behavior remains trustworthy when users ask realistic questions across multiple manuals.

## Confirmed Facts

- `/qa` already has browser coverage for upload/rebuild/answer, insufficient evidence, follow-up context, multi-format documents, and real PDF source previews.
- The deterministic `noop` answer generator is the local/offline acceptance path and already has unit coverage for stepwise troubleshooting, safety guidance, unsupported replacement/part-number refusal, and citation validation.
- Real manual eval fixtures exist under `tests/fixtures/eval/realmanuals.jsonl` for ASKO washer, HISENSE oven/fridge/dryer manuals.
- The previous task found a real cross-layer bug through browser testing, so this task should keep black-box browser acceptance in scope.

## Requirements

- Exercise real user QA flows in a browser, not only API/unit tests.
- Use realistic multi-manual questions that can reveal cross-document confusion.
- Verify answer text is useful enough for a user: stepwise where appropriate, no unsupported replacement/part-number claim, and grounded in visible sources.
- Verify citations in the answer map to visible source cards and source cards expose the expected manual/source/page cues.
- Verify unsupported or out-of-manual questions refuse cleanly instead of answering from weak evidence.
- Fix bounded issues found during the flow when they are low-risk and consistent with existing answer/retrieval architecture.
- Avoid broad ranking rewrites, provider changes, or online LLM dependence in this task.

## Acceptance Criteria

- [x] A browser acceptance flow covers at least two real manuals and at least three user-style QA cases: supported maintenance/operation, unsupported repair/part-number, and cross-manual confusion guard.
- [x] Supported answers contain expected manual terms and cite the expected source card(s).
- [x] Unsupported answers/refusals do not contain unsupported replacement or part-number instructions.
- [x] Citation chips focus visible source cards; source cards show user-safe source names/page labels and do not expose storage/blob keys, checksums, local paths, raw manifest rows, or debug IDs.
- [x] Relevant unit coverage is added for any answer formatting/refusal behavior changed.
- [x] Focused browser tests, focused unit tests, eval CI, and full non-performance gates pass.

## Out of Scope

- Switching the default answer provider to a remote LLM.
- Large retrieval/reranker redesign.
- New admin analytics dashboards.
- Reworking the QA page visual design unless the real flow exposes a small blocking trust issue.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
