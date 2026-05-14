# M25 Hybrid Lexical Retrieval for Fault Codes and Model Terms

## Goal

Improve product-manual retrieval for exact terms that embedding-only search can miss or under-rank: fault/error codes, product model numbers, part names, menu labels, and short maintenance terms. M25 should add a lightweight lexical signal to the existing WAVE-RAG retrieval path without replacing the current final ranking contract: Qdrant may provide ANN candidates, lexical matching may provide additional candidates or score hints, but final ranking remains local, deterministic, and explainable inside TagMemoRAG.

The work should start by adding harder eval cases that expose the lexical gap. If the current system already passes those cases, M25 should finish with documented evidence and avoid unnecessary ranking changes.

## Background / Known Context

- M23 ran retrieval tuning experiments against coffee and product-manual eval suites. The product baseline was saturated on tracked metrics: `recall_at_k=1.0`, `mrr=1.0`, and `hit_at_k=1.0`.
- M23 rejected broad parameter changes (`source_k`, `steps`, `decay`, `aggregate`, metadata/tag boosts) because they either had no measured gain or regressed quality. `aggregate=sum` specifically regressed product-manual recall and should not become a default without new evidence.
- M23 deferred lexical retrieval because existing exact-code product cases such as `E21` and `F2` already passed. M25 therefore needs harder fault-code/model/short-token cases before changing retrieval behavior.
- Current search flow:
  - API/CLI/eval embed the query.
  - `execute_search()` filters nodes, optionally asks Qdrant for ANN candidates, then calls `wave_search()`.
  - `wave_search()` chooses vector seed nodes from eligible nodes, propagates through graph edges, applies bounded metadata/tag boosts, and returns ranked results.
- Qdrant ANN is candidate generation only. Final ranking must remain local WAVE-RAG over the loaded graph and vectors.
- Search debug metadata intentionally excludes raw query text, vectors, trace/search IDs, full candidate ID lists, and high-cardinality machine paths.
- The default suite must stay offline and deterministic; live Qdrant/browser tests remain opt-in.

## Problem

Dense embeddings are not always reliable for compact, symbolic, or product-specific strings:

- Fault/error codes: `E21`, `F07`, `F2`, `Err 4`, `A-10`.
- Model numbers and SKU-like terms: `HR6FDFF701SW`, `DHQE800BW2`, `W6564`.
- Exact UI/menu labels and part names: `Steam Clean`, `filter drawer`, `排水泵`, `童锁`, `冷冻室`.
- Mixed-language queries where the exact token is the strongest clue.

When those terms are missed during seed selection or ANN candidate generation, graph propagation cannot recover the correct chunk. M25 should make these exact signals visible to retrieval while preserving semantic and graph behavior.

## Requirements

### 1. Evidence-First Eval Expansion

- Add harder deterministic eval cases for fault codes, model terms, short part names, and mixed-language exact terms.
- Include at least one case where an exact symbolic token should matter more than general semantic similarity.
- Record baseline metrics before implementing ranking changes.
- Adopt lexical retrieval only if the baseline exposes a miss or meaningful ranking weakness.
- If no weakness is exposed, document the result and finish without changing production ranking behavior.

### 2. Lightweight Lexical Signal

- Add a local, deterministic lexical scorer that uses already-loaded graph node fields:
  - chunk `text`
  - `header`
  - `path`
  - `source_file`
  - manual metadata such as `manual_id`, `product_model`, `brand`, `product_category`, `tags`
- Token handling should support:
  - case-insensitive English terms
  - Chinese substring terms where tokenization is not available
  - alphanumeric model/fault-code terms
  - punctuation variants for codes where safe, such as `E-21` vs `E21`
- Avoid introducing a search daemon, database, durable lexical index, or heavyweight dependency in M25.

### 3. Hybrid Candidate Recall

- Use lexical matches to prevent exact-term misses during candidate selection.
- Lexical candidate inclusion must respect existing metadata filters and KB isolation.
- In Qdrant ANN mode, lexical candidates and eligible anchors should be included alongside ANN candidates before local WAVE-RAG ranking.
- If no lexical matches are found, behavior should match the current search path.
- Candidate limits should be bounded and configurable to avoid broad scans dominating latency.

### 4. Bounded Ranking Influence

- Final result ordering must remain local and deterministic.
- Lexical influence should be additive and bounded, not a replacement for vector similarity or graph propagation.
- Exact fault-code/model matches may receive stronger boost than ordinary word overlap.
- Lexical scoring should not require metadata sidecars; legacy/no-sidecar KBs remain searchable.
- Existing filters, metadata boosts, tag boosts, anchors, and cache behavior must remain compatible.

### 5. API / CLI / Eval Compatibility

- Existing API and CLI request shapes should stay backward compatible.
- Any new knobs should live under `SearchConfig` and be overrideable by env/config. Request-level overrides are optional unless implementation scope remains small.
- Search cache keys must change when lexical behavior can affect ranking.
- Debug metadata may report low-cardinality lexical fields, such as enabled flag, candidate count, and match mode. It must not include raw query text, raw document text, full candidate ID lists, vectors, or secrets.
- Eval reports should capture effective lexical settings in `config_snapshot.search` if settings are added.

### 6. Documentation

- Update README with:
  - when hybrid lexical retrieval helps
  - how it interacts with WAVE-RAG and Qdrant ANN
  - reproduction commands for the new eval cases
  - safety limitations and config knobs
- Update backend specs if M25 creates durable conventions for lexical scoring, debug metadata, or search cache suffixes.

## Acceptance Criteria

- [ ] New eval cases cover harder fault-code/model/short-token retrieval scenarios and are checked into the default offline suite.
- [ ] Baseline exact-local metrics for the new cases are recorded under this task's `research/`.
- [ ] If baseline exposes a miss/regression, a deterministic lexical scorer improves or preserves aggregate metrics versus baseline.
- [ ] If baseline does not expose a miss/regression, production ranking remains unchanged and the no-change decision is documented.
- [ ] Lexical candidate inclusion respects metadata filters, KB boundaries, anchors, and Qdrant ANN candidate-generation-only semantics.
- [ ] Search cache keys and debug metadata account for lexical behavior without leaking sensitive/high-cardinality data.
- [ ] Existing M23 coffee and product-manual evals do not regress.
- [ ] Existing API, CLI, Qdrant/ANN, cache, auth, rebuild, and feedback tests continue to pass.
- [ ] README and any relevant backend specs document the accepted behavior.
- [ ] `uv run pytest tests/ -q` passes before final handoff.

## Definition of Done

- PRD, design, and implementation checklist are complete.
- Baseline and post-change retrieval evidence is written to `research/`.
- Production changes, if any, are covered by focused unit/eval tests.
- Documentation explains how to reproduce the lexical retrieval checks.
- No default test requires live Qdrant, browser automation, network access, or external model downloads.

## Out of Scope

- Replacing WAVE-RAG with BM25, Elasticsearch, Meilisearch, Lucene, or a database-backed index.
- Making Qdrant or any remote ANN score the final authoritative ranking signal.
- LLM query rewriting, LLM reranking, or cross-encoder reranking.
- Online learning from feedback.
- OCR for scanned manuals.
- Payload-filtered ANN unless required by a later task.
- Building a durable lexical index unless future evidence proves the scan-based MVP is too slow.

## Research References

- `.trellis/tasks/archive/2026-05/05-13-m23-retrieval-tuning-experiments/prd.md`
- `.trellis/tasks/archive/2026-05/05-13-m23-retrieval-tuning-experiments/research/experiments.md`
- `src/tagmemorag/search_runtime.py`
- `src/tagmemorag/wave_searcher.py`
- `src/tagmemorag/eval/runner.py`
- `tests/fixtures/eval/product_manuals.jsonl`

## Open Questions

- Should lexical retrieval ship enabled by default once eval evidence supports it, or should it start behind `search.lexical_enabled=false` for one release?

## Requirements

- TBD

## Acceptance Criteria

- [ ] TBD

## Notes

- Keep `prd.md` focused on requirements, constraints, and acceptance criteria.
- Lightweight tasks can remain PRD-only.
- For complex tasks, add `design.md` for technical design and `implement.md` for execution planning before `task.py start`.
