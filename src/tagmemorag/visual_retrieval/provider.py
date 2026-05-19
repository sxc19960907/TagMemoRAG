from __future__ import annotations

import re
from typing import TYPE_CHECKING

from ..document_assets import DocumentAsset
from .base import VisualCandidate, VisualCandidateProvider, VisualQueryContext, VisualReranker

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings


class DeterministicVisualCandidateProvider:
    """Manifest-backed candidate provider for deterministic offline tests."""

    provider_name = "deterministic"

    def __init__(self, *, version: str = "visual_retrieval.v1"):
        self.version = version

    def candidates(self, context: VisualQueryContext) -> tuple[VisualCandidate, ...]:
        if context.manifest is None or context.max_candidates <= 0:
            return ()
        query_tokens = _tokens(context.query_text)
        scored: list[VisualCandidate] = []
        for asset in context.manifest.assets.values():
            if asset.kb_name != context.kb_name or asset.status != "ready":
                continue
            if asset.type not in {"page_snapshot", "region_crop"}:
                continue
            haystack = _asset_text(asset)
            score = _overlap_score(query_tokens, _tokens(haystack))
            if score < context.min_score:
                continue
            scored.append(
                VisualCandidate(
                    asset_id=asset.asset_id,
                    doc_id=asset.doc_id,
                    source_file=asset.source_file,
                    page_number=asset.page_number,
                    score=score,
                    reason="visual_metadata_overlap",
                    provider=self.provider_name,
                    provider_version=self.version,
                    matched_text=haystack[:240],
                )
            )
        return tuple(sorted(scored, key=lambda item: (-item.score, item.asset_id))[: context.max_candidates])


class NoopVisualReranker:
    reranker_name = "noop"

    def __init__(self, *, version: str = "visual_reranker.noop.v1"):
        self.version = version

    def rerank(self, query_text: str, candidates: tuple[VisualCandidate, ...]) -> tuple[VisualCandidate, ...]:
        return candidates


def create_visual_components(settings: "Settings") -> tuple[VisualCandidateProvider | None, VisualReranker | None]:
    cfg = settings.visual_retrieval
    if not cfg.enabled:
        return None, None
    if cfg.provider != "deterministic":
        raise ValueError(f"Unsupported visual retrieval provider: {cfg.provider}")
    if cfg.reranker != "noop":
        raise ValueError(f"Unsupported visual reranker: {cfg.reranker}")
    return (
        DeterministicVisualCandidateProvider(version=cfg.provider_version),
        NoopVisualReranker(version=cfg.reranker_version),
    )


def _asset_text(asset: DocumentAsset) -> str:
    metadata = " ".join(str(value) for value in asset.metadata.values() if isinstance(value, (str, int, float)))
    return " ".join(
        part
        for part in (
            asset.caption,
            asset.nearby_text,
            asset.ocr_text,
            asset.source_file,
            metadata,
        )
        if part
    )


def _tokens(value: str) -> set[str]:
    return {token for token in re.findall(r"[\w\u4e00-\u9fff]+", str(value).lower()) if len(token) >= 2}


def _overlap_score(query_tokens: set[str], asset_tokens: set[str]) -> float:
    if not query_tokens or not asset_tokens:
        return 0.0
    return len(query_tokens & asset_tokens) / max(len(query_tokens), 1)


__all__ = ["DeterministicVisualCandidateProvider", "NoopVisualReranker", "create_visual_components"]
