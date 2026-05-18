"""NoopReranker — fallback chain end (Architecture v2 § A3).

Used when:
- Settings.reranker.enabled=False
- Budget.rerank_tier="off"
- Budget.allow_external_reranker=False (private KB)
- Vendor failure / circuit-open / budget-exhausted

Returns the candidates in their input order with their original scores. The
dispatcher then constructs a RerankResult marked vendor_used="noop".
"""

from __future__ import annotations

from .base import RerankDoc, RerankerOutcome


class NoopReranker:
    id = "noop"
    version = "v1"
    max_seq_length = 0  # not applicable
    supports_instruction = False

    def rerank(
        self,
        query: str,
        docs: list[RerankDoc],
        instruction: str | None,
        budget_ms: int,
    ) -> RerankerOutcome:
        # Use 1.0 / (rank+1) as a synthetic score to preserve input order in
        # downstream sorts. Dispatcher will calibrate to [0, 1] via min-max
        # giving a smooth descending sequence; semantic equivalent of "no
        # rerank applied".
        items = tuple(
            (doc.chunk_id, 1.0 / (i + 1))
            for i, doc in enumerate(docs)
        )
        return RerankerOutcome(items=items, truncated_chunk_ids=(), vendor_id=self.id)
