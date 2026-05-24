# Design

## Boundary

Only change `src/tagmemorag/retrieval.py` context packing. The `evidence` list, citations, ranking results, and answer generator remain unchanged.

## Selection Strategy

Keep a deterministic two-pass context selection:

1. Always consider evidence in score/rank order and select the first item that fits.
2. For subsequent items, prefer evidence whose normalized content has low overlap with already selected context items, while still respecting the token budget.
3. If the complementary pass leaves budget unused, fall back to original order for remaining fit candidates.

This preserves the current behavior when evidence is already diverse, but helps tight budgets include a second independent support point instead of a near-duplicate.

## Compatibility

- Context item ids remain `ctx_001`, `ctx_002`, etc. based on selected order.
- Evidence ids/citation ids stay tied to original evidence.
- Budget exhaustion still reports `context_budget_exhausted` when no item fits.
- No raw text is added to logs or debug metadata.

