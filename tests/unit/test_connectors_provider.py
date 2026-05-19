from __future__ import annotations

from tagmemorag.config import ConnectorsConfig, Settings
from tagmemorag.connectors.provider import FixtureConnectorProvider, create_connector_provider, fixture_markdown_record


def test_create_connector_provider_disabled_returns_none():
    assert create_connector_provider(Settings()) is None


def test_create_connector_provider_fixture():
    record = fixture_markdown_record()
    provider = create_connector_provider(Settings(connectors=ConnectorsConfig(enabled=True)), records=(record,))

    assert isinstance(provider, FixtureConnectorProvider)
    assert provider.sync("default") == (record,)


def test_fixture_markdown_record_shape():
    record = fixture_markdown_record(text="# Reset\nHold reset.")

    assert record.action == "upsert"
    assert record.document.source_file.endswith(".md")
    assert record.document.content == b"# Reset\nHold reset."
