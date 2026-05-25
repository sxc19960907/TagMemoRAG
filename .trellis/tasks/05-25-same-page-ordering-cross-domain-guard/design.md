# Design

## Approach

This child is primarily a validation child. It should use existing eval and
diagnostic commands instead of introducing runtime behavior changes.

Candidate config:

- `.tmp/eval/same-page-enabled.yaml`
- `search.same_page_ordering_enabled=true`
- default runtime config remains unchanged.

Candidate eval targets, in priority order:

1. `tests/fixtures/eval/multiformat_real_knowledge.jsonl` with docs under
   `.tmp/multiformat-real-knowledge/multiformat_real`
2. `tests/fixtures/eval/realmanuals.jsonl` with retained docs under
   `.tmp/eval-realmanuals-final/realmanuals` or the best available retained
   realmanuals directory

Baselines:

- Use retained `.tmp/eval/*baseline*` / `*-after-*` reports only for comparison
  notes. Do not mutate baseline reports.

## Guard Rules

- Candidate must preserve hit@k and recall@k for each slice relative to the
  selected retained baseline.
- Candidate MRR should not drop. If it does, classify as `hold` or `pivot`.
- If a slice cannot be run because local docs are missing, record that as an
  explicit skip with the missing path.

## Privacy

Only record summary metrics, failed case ids, and report paths. Do not paste raw
queries, snippets, provider responses, vectors, or `actual_top_k` into task
docs or committed files.
