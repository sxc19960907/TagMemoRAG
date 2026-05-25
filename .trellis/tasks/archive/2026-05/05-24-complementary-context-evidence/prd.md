# Prefer Complementary Context Evidence

## Problem

Retrieval quality is now good enough that answer quality is increasingly determined by which evidence chunks enter the `context_pack`. The current packer takes evidence in retrieval order until the token budget is exhausted. For multi-evidence questions, this can spend the budget on duplicate or adjacent chunks before a complementary evidence chunk gets included.

## Goals

- Prefer complementary context evidence under tight token budgets.
- Preserve retrieval/evidence/citation schemas.
- Keep the first/highest-ranked evidence item selected when it fits.
- Avoid changing search ranking or answer generation behavior in this task.
- Validate with retrieval unit tests plus mixed/general-web/real-manual diagnostics.

## Non-Goals

- Do not introduce an LLM judge or external reranker.
- Do not summarize/compress chunks.
- Do not remove evidence from the `evidence` list; only context-pack selection changes.

## Acceptance Criteria

- A retrieval unit test proves the context pack includes complementary evidence instead of near-duplicate adjacent evidence when budget is limited.
- Existing retrieval shape tests still pass.
- Mixed-domain and general-web answer diagnostics remain green.
- Real manual eval remains green enough for the current informational thresholds.

