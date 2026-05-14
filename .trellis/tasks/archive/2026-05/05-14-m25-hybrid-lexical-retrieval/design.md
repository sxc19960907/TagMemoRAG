# design.md - M25 Hybrid Lexical Retrieval for Fault Codes and Model Terms

## Scope

M25 adds an evidence-gated lexical retrieval signal to the existing search path. The target is product-manual exact-term recall: fault codes, model numbers, part names, menu labels, and short mixed-language terms. The design keeps WAVE-RAG as the local final ranking path and avoids a durable lexical index for the MVP.

## Current Search Contract

```text
query text
  -> embedder.encode_query()
  -> execute_search()
     -> filter_node_ids()
     -> optional Qdrant ANN candidates
     -> wave_search(query_vec, eligible_node_ids)
        -> choose vector source nodes
        -> graph propagation
        -> metadata/tag boost
        -> Result[]
```

Important constraints:

- `wave_search()` currently chooses seed/source nodes purely from vector similarity inside the eligible set.
- Qdrant ANN narrows candidates but does not rank final results.
- Filters are applied before search and must remain authoritative.
- Search cache keys include strategy-affecting parameters and must account for lexical behavior.
- Debug metadata must stay low-cardinality and non-sensitive.

## Proposed Boundary

Add a small lexical helper module, for example `src/tagmemorag/lexical_search.py`.

Responsibilities:

- Normalize query text into exact-match tokens and phrase fragments.
- Normalize searchable node fields without mutating graph state.
- Score nodes using deterministic lexical rules.
- Return bounded lexical candidates and score hints.

Keep the module independent of FastAPI, CLI, Qdrant client details, and eval report formatting.

## Configuration

Add fields to `SearchConfig` only if production ranking changes:

```python
lexical_enabled: bool = True
lexical_candidate_k: int = 32
lexical_min_token_chars: int = 2
lexical_boost: float = 0.05
lexical_exact_code_boost: float = 0.15
lexical_model_boost: float = 0.12
```

Conservative option: implement config with `lexical_enabled=False` until eval evidence supports enabling by default. If the new eval cases prove a clear win with no regressions, enable by default and document the evidence.

## Token Strategy

Use standard-library-only normalization:

- Lowercase ASCII/Latin text.
- Extract alphanumeric runs for English/model/code terms.
- Preserve compact code variants:
  - `E-21` -> `e21`, `e-21`
  - `F 07` -> `f07` when pattern confidence is high
- Preserve CJK terms through substring matching for short query fragments.
- Ignore very common stop words and one-character ASCII tokens.
- Treat model-like and code-like tokens separately from ordinary terms.

Suggested token classes:

```text
exact_code: /^[a-z]{1,4}[- ]?\d{1,5}[a-z0-9]*$/
model_term: contains both letters and digits, length >= 4
ordinary_term: normalized alphanumeric or CJK fragment
```

## Searchable Node Fields

For each graph node, build a transient searchable string from:

- `header`
- `path`
- `text`
- `source_file`
- metadata fields returned by `metadata_from_node()`
- tags as normalized strings

Weight matches by field:

```text
header/path/source_file/product_model/manual_id > tags/metadata > body text
```

No raw strings should be emitted to logs, metrics, debug metadata, or eval config snapshots.

## Hybrid Candidate Flow

Recommended execution flow:

```text
filtered_node_ids = filter_node_ids(...)
ann_eligible = optional Qdrant candidates intersect filtered_node_ids
lexical_candidates = top lexical matches inside filtered_node_ids
anchor_ids = anchors inside filtered_node_ids

eligible_node_ids =
  if ANN returned candidates:
    ann_candidates union lexical_candidates union anchor_ids
  else:
    filtered_node_ids

wave_search(..., eligible_node_ids, lexical_scores=optional)
```

For exact-local mode, there are two possible approaches:

1. Candidate-only lexical:
   - Keep `eligible_node_ids=filtered_node_ids`.
   - Pass lexical score hints into `wave_search()`.
   - Least behavior change for non-ANN searches.

2. Source seeding lexical:
   - Let lexical top nodes join vector seed/source nodes.
   - Better for exact-code misses, but touches `wave_search()` more directly.

Recommended MVP: source seeding plus bounded additive score, because exact-code misses can happen before propagation if the right node is never seeded.

## Wave Search Integration

Extend `wave_search()` carefully:

```python
lexical_scores: Mapping[int, float] | None = None
lexical_source_k: int = 0
```

Seed selection:

- Keep existing vector-ranked `source_k`.
- Add up to `lexical_source_k` lexical-ranked nodes not already in vector sources.
- Apply anchors as today.

Scoring:

- Add bounded lexical score after propagation, similar to metadata/tag boost.
- Exact code/model matches should have a cap so lexical cannot swamp graph/vector relevance.
- If `lexical_scores` is empty or disabled, output must match existing behavior.

Compatibility:

- Preserve node ID tie-breaking for deterministic results.
- Keep aggregate modes unchanged.
- Do not apply lexical boosts to nodes outside filters/eligible candidates.

## ANN Interaction

ANN remains candidate generation only:

- If ANN succeeds, eligible nodes become `ANN candidates union lexical candidates union anchors`.
- If ANN fails, fall back to exact local with lexical behavior according to config.
- If filters are present and `ann_force_exact_on_filters=true`, exact local still runs with lexical scoring inside the filtered set.
- Debug metadata may include `lexical_enabled`, `lexical_candidate_count`, and `lexical_match_count_capped`.

## Cache / Debug Contract

Update `search_cache_suffix()` if lexical config can affect results:

```text
exact_local|lexical:<enabled>:<candidate_k>:<boost profile>
ann_preselect:64|lexical:<enabled>:<candidate_k>:<boost profile>
```

Do not put query tokens or matched fields in the cache suffix.

Debug metadata allowed:

- `lexical_enabled`
- `lexical_candidate_count`
- `lexical_source_count`
- `lexical_profile` such as `disabled`, `candidate_only`, or `source_boost`

Debug metadata forbidden:

- raw query text
- extracted tokens
- matched text snippets
- full candidate ID lists
- raw vectors
- source-file lists

## Eval Strategy

Add harder cases before implementation:

- fault code with short query where semantic context is weak
- code punctuation variant (`E-21` vs `E21`)
- model number query with sparse surrounding words
- Chinese part/menu term query
- mixed model + symptom query

Run:

```bash
TAGMEMORAG__MODEL__PROVIDER=hashing TAGMEMORAG__MODEL__NAME=hashing TAGMEMORAG__MODEL__DIM=64 \
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m25-product-baseline \
  --output .tmp/eval/m25-reports/product-baseline.json \
  --min-recall-at-k 0 --min-mrr 0 --min-hit-at-k 0
```

Record baseline and post-change metrics in `research/experiments.md`.

## Rollout / Rollback

Rollout:

- Add tests and docs first.
- Ship config-gated lexical behavior.
- Enable by default only if eval evidence shows clear benefit and no regression.

Rollback:

- Set `search.lexical_enabled=false` to restore previous ranking.
- Since no durable index is introduced, rollback does not require data migration.
- If `wave_search()` changes cause broad regression, remove lexical source seeding and keep only documented eval cases for a later task.

## Risks

- Lexical boosts can over-rank irrelevant chunks that repeat model numbers in generic sections.
- CJK substring matching can overmatch if too broad.
- Adding candidates in ANN mode can increase latency if every query scans every node.
- Cache suffix mistakes can serve stale rankings after config changes.

Mitigations:

- Bound candidate counts and boosts.
- Require eval evidence before default enablement.
- Keep debug metadata compact.
- Add focused tests for disabled mode exact equivalence.
