from __future__ import annotations

from dataclasses import dataclass, field
from typing import Literal, Protocol


ConnectorAction = Literal["upsert", "delete"]


@dataclass(frozen=True)
class ConnectorDocument:
    source_file: str
    content: bytes
    content_type: str = "text/markdown"


@dataclass(frozen=True)
class ConnectorRecord:
    record_id: str
    manual_id: str
    title: str
    product_category: str
    document: ConnectorDocument
    action: ConnectorAction = "upsert"
    language: str = "unknown"
    tags: tuple[str, ...] = ()
    version: str = ""
    remote_id: str = ""
    metadata: dict[str, str] = field(default_factory=dict)


class ConnectorProvider(Protocol):
    provider_name: str

    def sync(self, kb_name: str) -> tuple[ConnectorRecord, ...]:
        """Return a bounded connector snapshot for one KB."""


@dataclass(frozen=True)
class ConnectorSyncSummary:
    provider: str
    attempted: int = 0
    materialized: int = 0
    tombstoned: int = 0
    failed: int = 0
    failure_reasons: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict:
        return {
            "provider": self.provider,
            "attempted": self.attempted,
            "materialized": self.materialized,
            "tombstoned": self.tombstoned,
            "failed": self.failed,
            "failure_reasons": dict(sorted(self.failure_reasons.items())),
        }
