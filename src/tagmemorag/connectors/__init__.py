"""Connector materialization boundary for Phase 8 (T9)."""

from .base import ConnectorDocument, ConnectorProvider, ConnectorRecord, ConnectorSyncSummary
from .materialize import materialize_connector_records
from .provider import FixtureConnectorProvider, create_connector_provider

__all__ = [
    "ConnectorDocument",
    "ConnectorProvider",
    "ConnectorRecord",
    "ConnectorSyncSummary",
    "FixtureConnectorProvider",
    "create_connector_provider",
    "materialize_connector_records",
]
