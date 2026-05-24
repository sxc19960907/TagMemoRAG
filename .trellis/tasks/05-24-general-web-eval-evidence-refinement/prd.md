# General-web eval evidence refinement

## Goal

Refine the general-web retrieval eval fixture so it recognizes independently
useful evidence chunks for the MDN HTTP caching case without changing runtime
retrieval behavior.

The previous diagnostic showed the remaining release-readiness warning is not
safe to fix with a broad ranking tweak. In particular, the MDN
`no-cache`/`private` case has high-ranked chunks that answer the query but are
not counted by the current exact-string expectations. This task corrects that
eval label gap while preserving real ranking issues in the GitHub cases.

## Confirmed Facts

- The active direction is general-purpose RAG, not Agentic retrieval.
- Current release-readiness warning is only `general_web_retrieval`.
- The archived diagnostic task concluded no safe generic ranking signal exists.
- `compute_ranking_metrics` uses first matched result for MRR and unique matched
  expected entries for recall.
- Adding expected evidence increases the recall denominator, so only top-k
  evidence that is independently useful and actually matched should be added.
- GitHub repository / pull-request cases still represent real ranking issues and
  should not be broadened in this task.

## Requirements

- Update `tests/fixtures/eval/general_web.jsonl` only where the current expected
  evidence is too narrow.
- Add MDN HTTP caching relevant entries only for evidence that directly supports
  the query:
  - private cache stores a personalized response because it is not shared with
    other clients
  - personalized content should be stored only in the private cache using the
    `private` directive
  - combined `no-cache, private` guidance that prevents sharing personalized
    content with other users
- Do not change retrieval code, ranking weights, parser behavior, context
  packing, or answer generation.
- Do not commit fetched third-party page bodies or `.tmp/` eval outputs.
- Leave unrelated untracked `.codegraph/` and `.mcp.json` untouched.

## Acceptance Criteria

- [ ] `general_web.jsonl` recognizes the MDN query's useful top-k evidence
      without broadening GitHub cases.
- [ ] General-web retrieval MRR reaches the release-readiness target without
      reducing hit@k below `1.0`.
- [ ] General-web recall remains at or above the previous `0.928571` baseline.
- [ ] Unit coverage or fixture validation confirms the updated case shape is
      parseable and keeps the suite excluded from default fixture-only CI.
- [ ] No runtime retrieval files are changed.
- [ ] The task records why this is an eval-label correction rather than a
      ranking workaround.

## Out of Scope

- Ranking/scoring changes.
- Agentic retrieval, WAVE/geodesic changes, external rerankers, or parser
  changes.
- Broadening GitHub expected evidence to count tutorial overview/action chunks.

## Notes

- This is a small fixture task, but it affects release-readiness interpretation,
  so it includes design and implementation notes.
