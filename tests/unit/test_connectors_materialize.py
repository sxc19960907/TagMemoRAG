from __future__ import annotations

import json

from tagmemorag.connectors.base import ConnectorDocument, ConnectorRecord
from tagmemorag.connectors.materialize import materialize_connector_records
from tagmemorag.connectors.provider import fixture_markdown_record


def test_materialize_connector_record_writes_document_and_metadata(tmp_path):
    record = fixture_markdown_record(
        manual_id="reset-manual",
        source_file="fixture/reset.md",
        title="Reset Manual",
        text="# Reset\nHold reset for three seconds.",
    )

    summary = materialize_connector_records((record,), kb_name="default", root_dir=tmp_path, provider="fixture")

    doc = tmp_path / "default" / "fixture" / "reset.md"
    sidecar = tmp_path / "default" / "fixture" / "reset.metadata.json"
    assert summary.to_dict()["materialized"] == 1
    assert doc.read_text(encoding="utf-8") == "# Reset\nHold reset for three seconds."
    metadata = json.loads(sidecar.read_text(encoding="utf-8"))
    assert metadata["manual_id"] == "reset-manual"
    assert metadata["source_file"] == "fixture/reset.md"
    assert metadata["status"] == "active"


def test_materialize_connector_record_preserves_remote_metadata(tmp_path):
    record = ConnectorRecord(
        record_id="web-1",
        manual_id="web-1",
        title="Web Page",
        product_category="software_docs",
        document=ConnectorDocument(source_file="web/page.md", content=b"# Web\n"),
        remote_id="https://example.com/page",
        metadata={"domain": "software_docs", "doc_type": "documentation", "url": "https://example.com/page"},
    )

    materialize_connector_records((record,), kb_name="default", root_dir=tmp_path, provider="fixture")

    metadata = json.loads((tmp_path / "default" / "web" / "page.metadata.json").read_text(encoding="utf-8"))
    assert metadata["remote_id"] == "https://example.com/page"
    assert metadata["domain"] == "software_docs"
    assert metadata["doc_type"] == "documentation"
    assert metadata["url"] == "https://example.com/page"


def test_materialize_connector_tombstone_writes_deleted_metadata(tmp_path):
    record = fixture_markdown_record(action="delete", source_file="fixture/deleted.md")

    summary = materialize_connector_records((record,), kb_name="default", root_dir=tmp_path, provider="fixture")

    metadata = json.loads((tmp_path / "default" / "fixture" / "deleted.metadata.json").read_text(encoding="utf-8"))
    assert summary.to_dict()["tombstoned"] == 1
    assert not (tmp_path / "default" / "fixture" / "deleted.md").exists()
    assert metadata["status"] == "deleted"


def test_materialize_connector_invalid_suffix_is_bounded_failure(tmp_path):
    record = ConnectorRecord(
        record_id="bad",
        manual_id="bad",
        title="Bad",
        product_category="connector",
        document=ConnectorDocument(source_file="bad.exe", content=b"bad"),
    )

    summary = materialize_connector_records((record,), kb_name="default", root_dir=tmp_path, provider="fixture")

    assert summary.to_dict()["failed"] == 1
    assert summary.to_dict()["failure_reasons"] == {"valueerror": 1}
    assert "bad" not in str(summary.to_dict())


def test_materialize_connector_rejects_unsafe_path(tmp_path):
    record = fixture_markdown_record(source_file="../escape.md")

    summary = materialize_connector_records((record,), kb_name="default", root_dir=tmp_path, provider="fixture")

    assert summary.to_dict()["failed"] == 1
    assert not (tmp_path / "escape.md").exists()
