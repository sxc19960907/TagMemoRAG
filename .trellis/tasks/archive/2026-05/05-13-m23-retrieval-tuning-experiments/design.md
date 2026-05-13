# design.md - M23 Retrieval Tuning Experiments

## Scope

M23 is an evidence-driven retrieval tuning task. The core output is a small, repeatable experiment loop that can safely decide whether to change search defaults or local ranking behavior.

The task may change search defaults or add narrowly scoped ranking logic, but only when eval evidence supports the change. If the suite does not show a clear win, the correct outcome is documentation plus no default behavior change.

## Current Retrieval Flow

```text
API / CLI / eval
  -> embed query
  -> execute_search(...)
       -> filter eligible graph node ids
       -> optional Qdrant ANN preselection
       -> wave_search(...)
            -> choose source nodes by local vector similarity
            -> propagate through graph edges
            -> apply metadata/tag boosts when filters exist
            -> return local WAVE-RAG ranking
```

Important existing contracts:

- `execute_search()` is the shared path for API, CLI, and eval.
- ANN only narrows candidate ids. It does not provide final scores.
- `wave_search()` expects graph node ids to align with vector rows.
- Metadata/tag boosts currently apply only when explicit filters are present.
- Search result ordering is deterministic by score then node id.

## Experiment Strategy

Use a staged approach:

```text
baseline
  -> parameter sweep
  -> inspect regressions/wins
  -> decide whether defaults change
  -> optional small ranking experiment
  -> focused tests
  -> README/research summary
```

The baseline is the current code and current config. Variants should be small enough that a future maintainer can explain the causal hypothesis.

## Baseline Commands

Recommended exact-local baseline:

```bash
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/coffee.jsonl \
  --docs tests/fixtures \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m23-coffee-baseline

uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m23-product-baseline
```

If a JSON report file is needed for comparison:

```bash
uv run python -m tagmemorag eval run \
  --suite tests/fixtures/eval/product_manuals.jsonl \
  --docs tests/fixtures/product_manuals \
  --config config.yaml \
  --eval-data-dir .tmp/eval/m23-product-baseline \
  --output .tmp/eval/m23-product-baseline.json
```

## Candidate Variants

### Search Parameter Sweep

Start with a bounded matrix:

| Parameter | Baseline | Candidate Values | Hypothesis |
|-----------|----------|------------------|------------|
| `source_k` | `3` | `4`, `5`, `8` | More seed nodes may improve recall on mixed-language/manual-category queries |
| `steps` | `3` | `1`, `2`, `4` | Fewer steps may reduce graph drift; more steps may recover nearby procedural chunks |
| `decay` | `0.7` | `0.55`, `0.8` | Controls propagation strength into neighbors |
| `aggregate` | `max` | `sum` | `sum` may reward multiple weak paths but can over-amplify dense neighborhoods |
| `metadata_field_boost` | `0.05` | `0.02`, `0.08`, `0.12` | Explicit filters may need stronger product/category separation |
| `tag_boost` | `0.03` | `0.01`, `0.05`, `0.08` | Tag-filtered searches may need stronger canonical tag preference |

Avoid a full combinatorial explosion. Prefer one-axis-at-a-time sweeps first, then test one or two combined variants if individual wins are coherent.

### Metadata-Aware Reranking

Only consider this if eval failures show a pattern where the right semantic chunk is in top-k but ranked below a chunk from the wrong manual/category/model.

Possible design:

- Add a bounded bonus for query-token matches against safe metadata fields such as `manual_id`, `product_category`, `product_model`, and normalized tags.
- Keep it local to `wave_search()` or a narrow helper used by it.
- Do not use raw arbitrary metadata dumps.
- Do not require sidecars.

Risks:

- Query-token parsing can be brittle for mixed Chinese/English.
- Metadata terms can overfit synthetic fixtures.
- Boosts may hide embedding quality problems.

Recommendation: defer unless parameter tuning cannot address repeated metadata misses.

### Hybrid Lexical Retrieval

Only consider this if fault codes, product models, or exact task terms are consistently missed by vector similarity.

Possible MVP:

- Compute a per-node lexical score at query time from existing node `text`, `header`, and safe metadata fields.
- Use the score only to adjust source node selection or add a small bounded rerank bonus.
- Keep tokenization simple and deterministic:
  - lowercase ASCII-ish terms
  - preserve alphanumeric fault codes like `E21` and `F2`
  - for CJK text, use substring checks for query terms rather than adding a tokenizer dependency

Risks:

- Query-time scanning may become expensive for large KBs.
- Naive lexical matching can over-rank repeated boilerplate.
- Adding a durable lexical index is out of scope for M23.

Recommendation: document as a follow-up unless product-manual eval evidence shows exact-code misses that parameter tuning cannot fix.

## Evidence Contract

Each experiment entry should include:

```markdown
## Variant: <name>

- Hypothesis:
- Change:
- Command:
- Aggregate before:
- Aggregate after:
- Wins:
- Regressions:
- Decision:
```

Store this in `research/experiments.md`. Keep raw large JSON outputs under `.tmp/` unless a compact excerpt is needed in Trellis docs.

## Success Criteria

Adopt a change only when:

- product-manual aggregate `recall_at_k`, `mrr`, and `hit_at_k` improve or remain equal
- coffee smoke suite still passes
- no critical per-case regression is introduced
- focused unit/e2e tests cover the changed behavior
- the change does not broaden sensitive output

If metrics are mixed, prefer no default change and document the tradeoff.

## Compatibility

- Existing config files must continue to load.
- Search request overrides for `steps`, `decay`, `aggregate`, `source_k`, and `top_k` must remain compatible.
- Cache keys/search IDs must keep reflecting effective ranking-affecting parameters.
- Eval report shape should remain backward compatible unless a clearly additive field is justified.
- NPZ and Qdrant-backed KBs should remain supported.

## Rollout / Rollback

Rollout is low-risk if M23 only changes defaults. Operators can override search settings in YAML or env vars.

If M23 adds ranking code, rollback should be a small revert of the helper/config default and related docs. Avoid schema changes, durable migrations, or new background artifacts.

## Open Questions

- Should M23 add a small experiment runner command to automate sweeps?
  - Recommendation: only if manual commands become repetitive. A task-local script or test helper may be enough.
- Should metadata-aware boosts apply without explicit filters?
  - Recommendation: no by default; only explore with evidence, because unfiltered boosts can surprise broad semantic search.
- Should lexical retrieval be adopted in M23?
  - Recommendation: defer unless exact-code/product-model failures are clear and repeatable.
