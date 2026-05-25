# Release readiness baseline refresh

## Goal

Record the new general-purpose RAG release-readiness baseline after the
general-web evidence label refinement moved the retained readiness report from
`warning` to `passed`.

This task is documentation/spec hygiene only. It prevents future work from
chasing the old `general_web_retrieval` warning after that warning has been
resolved by a fixture-label correction.

## Confirmed Facts

- Current branch: `codex/agent-loop-driver`.
- Current release-readiness report:
  `.tmp/eval/release-readiness-after-evidence-refinement.json`.
- Report status: `passed`.
- `general_web_retrieval` now reports:
  `hit@k=1.0`, `recall_at_k=0.971429`, `MRR=0.773810`.
- Previous warning baseline was:
  `hit@k=1.0`, `recall_at_k=0.928571`, `MRR=0.651361`.
- The change that moved readiness to passed was an eval-label correction, not a
  runtime ranking change.

## Requirements

- Update the backend architecture/spec text around the general-web real
  knowledge slice and release-readiness baseline.
- Make clear that the current retained release-readiness state is passed.
- Preserve the warning that GitHub general-web cases still represent future
  ranking pressure and should not be hidden by broad fixture labels.
- Do not change runtime code, ranking, parser behavior, context packing, answer
  generation, or eval fixtures.
- Do not commit `.tmp/` reports.
- Leave unrelated `.codegraph/` and `.mcp.json` untouched.

## Acceptance Criteria

- [ ] `.trellis/spec/backend/architecture.md` records the 2026-05-24 passed
      release-readiness baseline and the key metrics.
- [ ] The spec distinguishes eval-label correction from retrieval scoring
      changes.
- [ ] Release-readiness script still reports `passed` from retained `.tmp`
      reports.
- [ ] Relevant unit tests pass.
- [ ] Only spec/task artifacts are committed.

## Notes

- Lightweight documentation task; PRD plus implementation checklist is enough.
