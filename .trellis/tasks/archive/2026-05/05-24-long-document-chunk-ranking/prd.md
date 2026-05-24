# Improve Long-Document Chunk Ranking

## Problem

The mixed-domain robustness diagnostic passes, but public documentation cases reveal a narrower quality issue: the correct evidence chunk inside a long web page may rank at position 2 or 3 instead of position 1. Product-manual cases are already ranking well, so the next quality gain should focus on same-document chunk ordering rather than cross-domain isolation.

## Goals

- Improve ranking of specific long-document chunks when the query contains multiple ordinary documentation terms.
- Preserve the existing real-manual retrieval behavior, especially model/code/CJK manual matching.
- Keep the change local to retrieval ranking/lexical scoring unless diagnostics prove a wider bug.
- Validate with `mixed_knowledge`, `general_web`, and `realmanuals` diagnostics/suites.

## Non-Goals

- Do not introduce a new reranker dependency.
- Do not change answer schema, API schema, KB selection, or tenant semantics.
- Do not tune broad thresholds blindly just to make one suite pass.

## Acceptance Criteria

- A focused unit test captures the long-doc chunk ordering problem.
- Ranking improves for GitHub/Python public-doc cases in the mixed-domain report without introducing cross-domain negative hits.
- Existing lexical/manual tests continue to pass.
- Real `product_manuals/` validation remains green enough for the current real-manual diagnostic.

