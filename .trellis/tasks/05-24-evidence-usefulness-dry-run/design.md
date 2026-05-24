# Design

## Boundary

This task adds an offline diagnostic for existing eval JSON reports. It does
not import runtime app state, call retrieval, modify scoring, or rewrite eval
fixtures. The module is a pure report reader and summarizer.

## Data Flow

1. Load an eval report JSON object from disk.
2. Validate that `cases` is a list.
3. Skip the synthetic `__suite__` case.
4. For each case, inspect `actual_top_k` in memory but never copy the raw list
   into output.
5. Convert each result into a bounded diagnostic row:
   - rank
   - matched status and matched expected indexes
   - source/header identifiers
   - body word count
   - cue counts reused from the general-web ranking-pressure diagnostic
   - query-term coverage as a number only
   - usefulness score as a number only
6. Summarize per-case comparisons:
   - first matched rank
   - average usefulness before the first matched result
   - best usefulness before the first matched result
   - average matched usefulness
   - whether matched evidence outranks earlier unmatched evidence by the
     diagnostic score
7. Summarize suite-level counts and averages.

## Usefulness Scoring

The diagnostic mirrors the existing context-usefulness shape without importing
private helpers from `retrieval.py`. It uses deterministic lexical terms, cue
counts, query coverage, and a chrome penalty. The score is intentionally a
diagnostic signal, not a production ranking formula.

## Privacy

The output must not include:

- raw query text
- raw snippets/result text
- `actual_top_k`
- provider response bodies
- embeddings/vectors
- secrets
- high-cardinality absolute paths

The module may read raw query and result text from the already-local eval
report to compute bounded numeric diagnostics, but it only emits counts,
booleans, ranks, identifiers, and scores.

## Compatibility

The report schema is versioned as `evidence_usefulness_diagnostic.v1`.
Markdown rendering is operator-facing and uses only bounded fields. Invalid or
missing input returns a typed input error so the script can exit with code `2`.

## Rollback

Rollback is deleting the new module, script, tests, and task artifacts. Because
the diagnostic is offline-only and not referenced by runtime paths, rollback
does not require migration or config changes.
