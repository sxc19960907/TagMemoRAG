from __future__ import annotations

from dataclasses import dataclass, field
from typing import Protocol

from ..document_assets import AssetManifest


@dataclass(frozen=True)
class VisualQueryContext:
    query_text: str
    visual_intent: str
    kb_name: str
    manifest: AssetManifest | None
    max_candidates: int
    min_score: float


@dataclass(frozen=True)
class VisualCandidate:
    asset_id: str
    doc_id: str
    source_file: str
    page_number: int | None
    score: float
    reason: str
    provider: str
    provider_version: str
    matched_text: str = ""


class VisualCandidateProvider(Protocol):
    provider_name: str
    version: str

    def candidates(self, context: VisualQueryContext) -> tuple[VisualCandidate, ...]:
        """Return visual candidates from an indexed/manifest-backed source."""


class VisualReranker(Protocol):
    reranker_name: str
    version: str

    def rerank(self, query_text: str, candidates: tuple[VisualCandidate, ...]) -> tuple[VisualCandidate, ...]:
        """Adjust visual candidate scores/order without inventing new assets."""


@dataclass(frozen=True)
class VisualRetrievalSummary:
    enabled: bool = False
    attempted: int = 0
    candidate_count: int = 0
    attached_count: int = 0
    skipped: int = 0
    omitted: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "enabled": self.enabled,
            "attempted": self.attempted,
            "candidate_count": self.candidate_count,
            "attached_count": self.attached_count,
            "skipped": self.skipped,
            "omitted": dict(sorted(self.omitted.items())),
        }
