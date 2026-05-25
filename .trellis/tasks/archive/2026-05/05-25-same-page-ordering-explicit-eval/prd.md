# Same-page ordering explicit eval

## Goal

Verify the default-off same-page ordering runtime flag through the real eval
path, not only through retrieve-response unit tests or offline candidate
simulation. If the eval runner does not yet honor the flag, wire the same
default-off helper into eval so explicit validation can be trusted.

## Requirements

- Preserve default eval behavior when `search.same_page_ordering_enabled=false`.
- When `search.same_page_ordering_enabled=true`, `eval run` must apply the same
  deterministic same-page ordering helper that `/retrieve` uses.
- Run explicit general-web eval with the flag enabled using the retained local
  `.tmp/general-web-eval/general_web` corpus.
- Run at least one broader/non-GitHub guard slice when local docs are present.
- Produce a candidate ranking-pressure report and run the reranking gate against
  the baseline/candidate comparison.
- Do not fetch network content unless the retained local corpus is missing.
- Do not commit generated `.tmp/` reports.
- Preserve privacy constraints: no raw query text, snippets, provider bodies,
  vectors, secrets, or absolute paths in committed artifacts/logs.

## Acceptance Criteria

- [ ] Focused tests prove eval default-off behavior is unchanged.
- [ ] Focused tests prove eval with the flag enabled can improve a same-page
      pressure case.
- [ ] Explicit general-web eval with the flag enabled passes.
- [ ] Candidate ranking-pressure report improves or does not regress existing
      pressure metrics.
- [ ] Reranking gate passes for the explicit-eval candidate.
- [ ] Parent program log records the result and the next recommendation.

## Notes

- Parent program: `05-24-general-rag-stability-program`.
- Current date: `2026-05-25`.
