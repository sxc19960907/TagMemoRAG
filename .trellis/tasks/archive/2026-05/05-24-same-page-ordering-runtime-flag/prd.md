# Same-page ordering runtime flag

## Goal

Add a guarded, default-off runtime flag for the pressure-gated same-page
ordering strategy proven by the offline candidate dry run. Default behavior
must remain unchanged; the feature may only affect retrieval order when
explicitly enabled.

## Requirements

- Add configuration under `search` for same-page ordering:
  - `same_page_ordering_enabled`, default `false`
  - `same_page_ordering_min_group_size`, default `2`
- Keep default runtime retrieval results identical when the flag is disabled.
- When enabled, apply the same pressure-gated candidate shape validated in the
  dry run:
  - only consider windows dominated by repeated `source_file` or `header`
  - only reorder when the baseline first useful result is below rank 1
  - preserve rank-1 hits
  - sort by bounded usefulness score, query coverage, retrieval score, and
    original rank
- Keep the implementation local and deterministic. Do not call external
  rerankers, fetch URLs, rebuild indexes, or change fixtures.
- Do not emit raw query text, raw snippets, vectors, provider bodies, secrets,
  or absolute paths in diagnostics/logs.
- Add tests proving disabled behavior is unchanged, enabled behavior improves
  the same-page pressure shape, and rank-1 hits are preserved.

## Acceptance Criteria

- [ ] Runtime flag defaults off and can be overridden by env/YAML.
- [ ] Retrieval response construction preserves result/evidence order with the
      flag disabled.
- [ ] Retrieval response construction reorders same-page pressure results when
      explicitly enabled.
- [ ] Rank-1 hits remain rank 1 when the flag is enabled.
- [ ] Focused tests and existing adjacent retrieval/config tests pass.
- [ ] Release-readiness/reranking gate remains passed.
- [ ] Parent program log records result and next recommendation.

## Notes

- Parent program: `05-24-general-rag-stability-program`.
- This child adds the code path but does not make the feature default-on.
