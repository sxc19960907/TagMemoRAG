# QA answer quality eval

## Goal

Add a repeatable answer-quality evaluation slice for `/qa`-style product manual answers so future answer changes can be checked against fixed cases.

## Requirements

- Reuse the existing `tagmemorag eval answer-quality` framework.
- Add a product-manual QA suite focused on troubleshooting, maintenance, refusal, citation support, and unsafe/unsupported action claims.
- Keep the suite deterministic and offline; do not require LLM-as-judge or network calls.
- Avoid storing full private customer content or debug identifiers in reports.
- Add focused tests so the suite stays loadable and the CLI path continues to pass.
- Record the suite in project architecture/spec so future answer-quality changes know which fixture to run.

## Acceptance Criteria

- [x] A new QA answer-quality JSONL fixture exists for product-manual cases.
- [x] Unit tests load and run the new suite through `run_answer_quality_diagnostics`.
- [x] CLI-style answer-quality diagnostics continue to pass on the new suite.
- [x] Spec documents the suite as the first fixed QA answer-quality slice.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
