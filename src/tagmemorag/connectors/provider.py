from __future__ import annotations

from typing import TYPE_CHECKING

from .base import ConnectorDocument, ConnectorProvider, ConnectorRecord

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings


class FixtureConnectorProvider:
    """Deterministic in-memory provider for tests and contract validation."""

    provider_name = "fixture"

    def __init__(self, records: tuple[ConnectorRecord, ...] = ()):
        self._records = records

    def sync(self, kb_name: str) -> tuple[ConnectorRecord, ...]:
        return self._records


def create_connector_provider(settings: "Settings", *, records: tuple[ConnectorRecord, ...] = ()) -> ConnectorProvider | None:
    if not settings.connectors.enabled:
        return None
    if settings.connectors.provider == "fixture":
        return FixtureConnectorProvider(records)
    raise ValueError(f"Unsupported connector provider: {settings.connectors.provider}")


def fixture_markdown_record(
    *,
    record_id: str = "fixture-1",
    manual_id: str = "fixture-manual",
    source_file: str = "fixture/fixture.md",
    title: str = "Fixture Manual",
    text: str = "# Fixture\nConnector text.",
    product_category: str = "connector",
    action: str = "upsert",
) -> ConnectorRecord:
    return ConnectorRecord(
        record_id=record_id,
        manual_id=manual_id,
        title=title,
        product_category=product_category,
        document=ConnectorDocument(source_file=source_file, content=text.encode("utf-8")),
        action="delete" if action == "delete" else "upsert",
    )


__all__ = ["FixtureConnectorProvider", "create_connector_provider", "fixture_markdown_record"]
