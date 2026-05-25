# General web eval suite

## Goal

Create the first reproducible non-manual benchmark suite for the general RAG
direction. The suite should use public web documentation sampled into `.tmp`
with the existing `knowledge sample-web` command, while committing only the
eval definitions and scripts needed to reproduce the corpus.

This is intentionally the first slice of a broader benchmark. It should prove
the pipeline can evaluate software documentation as a non-product-manual domain
before expanding to policy/government, health/public information, and FAQ/help
center sources.

## Requirements

- Add a checked-in eval suite for public web documentation.
- Add a reproducible script that samples the public pages into an ignored
  `.tmp` corpus.
- Do not commit fetched third-party document content.
- Use `domain=software_docs` and `doc_type=documentation` so the generic
  metadata path is exercised.
- Keep the first suite small and stable enough for local hashing eval.
- Include source URL attribution in script comments or constants.

## Acceptance Criteria

- [ ] `scripts/seed_general_web_eval.sh` materializes at least two public web
      documents under `.tmp/general-web-eval`.
- [ ] `tests/fixtures/eval/general_web.jsonl` includes at least four cases
      across the sampled public documents.
- [ ] The suite passes with the local hashing config and realistic thresholds.
- [ ] The suite checks generic metadata such as `domain=software_docs` and
      `doc_type=documentation`.
- [ ] Existing focused eval tests still pass.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
