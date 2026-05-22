# Live general web answer eval

## Goal

Add a reproducible diagnostic that runs the generic web retrieval benchmark
through the local answer generator and then evaluates the generated answers for
grounding, relevance, and citation support.

This bridges the current split between `general_web.jsonl` retrieval eval and
`answer_quality/general_web.jsonl` static answer diagnostics. It should use the
real seeded `.tmp/general-web-eval/general_web` corpus but avoid committing any
downloaded public web content.

## Requirements

- Add a script that builds/searches the seeded general web corpus, generates
  noop extractive answers, and checks the answer text against the existing
  answer-quality diagnostics.
- Reuse existing retrieval, answer prompt/generator, and answer-quality
  components where practical.
- Keep the script opt-in because it depends on a `.tmp` corpus seeded from
  public URLs.
- Default inputs should match `scripts/seed_general_web_eval.sh` and
  `tests/fixtures/eval/general_web.jsonl`.
- Emit a concise JSON report and a nonzero exit code on failed answer quality.
- Include focused tests that exercise the diagnostic on a tiny local fixture
  without network access.

## Acceptance Criteria

- [ ] `scripts/diag_general_web_answer_eval.py` can run against
      `.tmp/general-web-eval/general_web` and `tests/fixtures/eval/general_web.jsonl`.
- [ ] The diagnostic generates answer-quality cases from live retrieval output
      and reports whether each answer is grounded/relevant/citation-supported.
- [ ] A unit test covers the diagnostic using local temporary docs and a small
      eval suite.
- [ ] README documents the script next to the general web retrieval and static
      answer-quality commands.
- [ ] Existing focused answer/eval tests still pass.
- [ ] No fetched third-party web content is committed.

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
