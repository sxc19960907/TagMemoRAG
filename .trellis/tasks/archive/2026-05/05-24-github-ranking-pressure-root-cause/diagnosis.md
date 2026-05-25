# Diagnosis

## Summary

The two GitHub Hello World ranking-pressure cases are real low-MRR cases, but
they do not justify an immediate runtime ranking change.

Both cases retrieve the expected evidence within top-k. The pressure comes from
the same tutorial document producing several broad overview or workflow chunks
that score slightly above the exact definition/explanation chunks. This is
acceptable for a general-purpose RAG release baseline because recall and answer
coverage are already green, and the current release-readiness gate is `passed`.

## Evidence Reviewed

- `.tmp/eval/general-web-ranking-pressure.json`
- `.tmp/eval/general-web-after-evidence-refinement.json`
- `tests/fixtures/eval/general_web.jsonl`
- `.tmp/general-web-eval/general_web/public_web/docs.github.com-en-get-started-start-your-journey-hello-world.md`
- `src/tagmemorag/wave_searcher.py`
- `src/tagmemorag/retrieval.py`

## Case Classification

### `github-hello-world-repository`

- Current metrics: `hit@k=1.0`, `recall_at_k=1.0`, `mrr=0.166667`.
- First matched evidence appears at rank 6 for the README/Markdown expectation.
- The repository/folder definition also appears later in top-k.
- Higher-ranked chunks are not irrelevant spam; they are broad tutorial overview
  and repository creation workflow chunks from the same source document.
- Classification: runtime ranking pressure, not parser failure and not a clear
  fixture bug.

The fixture expectations are semantically valid: repository-as-folder and
README-as-Markdown are answer-bearing evidence for the query. The issue is that
the query also contains broad terms (`GitHub`, `Hello World`, `repository`,
`project`) that make overview and workflow chunks competitive.

### `github-hello-world-pull-request`

- Current metrics: `hit@k=1.0`, `recall_at_k=1.0`, `mrr=0.25`.
- First matched evidence appears at rank 4.
- Higher-ranked chunks are again same-document overview/review/workflow chunks,
  not unrelated cross-domain results.
- Classification: mild runtime ranking pressure, not parser failure and not a
  fixture bug.

The expected chunk is the strongest definition-style pull request evidence, but
the preceding chunks are still useful context for a tutorial-style answer.

## Root Cause

The current retrieval path combines vector similarity, lexical candidate
inclusion, graph propagation, lexical boost, and a lexical evidence tie-break.
For these GitHub queries, broad same-document chunks receive enough query-term
and graph support to outrank narrower answer-bearing chunks.

This is a known hard boundary for lexical/vector hybrid retrieval: an overview
chunk can be genuinely relevant while still being less answer-specific than a
definition chunk. Promoting the exact evidence safely would require a broader
answer-usefulness or first-class reranker signal, not a GitHub-specific boost.

## Decision

Do not change runtime ranking in this task.

Reasons:

- Release readiness is already `passed`.
- The cases are top-k hits with full or sufficient recall.
- The two pressure items come from one source document and do not provide enough
  coverage to tune a general-purpose ranking heuristic.
- A broad lexical boost risks regressing mixed-domain, product-manual, or
  multi-format ranking by over-promoting narrow term matches or action-heavy
  chunks.
- The architecture already treats first-class reranking as the correct boundary
  for relevance improvements.

## Recommended Next Step

Keep this as a non-blocking backlog item until there is a broader reranking
evaluation batch.

When picked up, the next implementation task should evaluate a generic
evidence-usefulness or reranker signal against all current release slices:

- general-web retrieval,
- mixed-domain retrieval,
- multi-format retrieval,
- real-manual retrieval,
- context-quality normal/tight budget,
- answer-quality diagnostics.

The candidate should only ship if it improves these GitHub ranks without
lowering release-readiness status or leaking raw diagnostic content.

## Privacy

This task commits only bounded task notes. Raw fetched web content and `.tmp`
diagnostic outputs remain uncommitted.
