from __future__ import annotations

from tagmemorag.document_metadata import document_metadata_from_manual, manual_node_attrs
from tagmemorag.manuals import ManualMetadata


def test_document_metadata_from_manual_preserves_legacy_fields_and_adds_identity_tags():
    metadata = ManualMetadata(
        manual_id="hisense-hr6fdff701sw-zh-cn-v1",
        title="Hisense HR6FDFF701SW",
        source_file="refrigerator/HISENSE HR6FDFF701SW.pdf",
        brand="Hisense",
        product_category="refrigerator",
        product_model="HR6FDFF701SW",
        language="zh-CN",
        tags=("ice-maker",),
    )

    doc = document_metadata_from_manual(metadata)

    assert doc.doc_id == "hisense-hr6fdff701sw-zh-cn-v1"
    assert doc.domain == "product_manual"
    assert doc.doc_type == "manual"
    assert doc.attributes["manual_id"] == "hisense-hr6fdff701sw-zh-cn-v1"
    assert doc.attributes["brand"] == "Hisense"
    assert doc.attributes["product_model"] == "HR6FDFF701SW"
    assert "ice-maker" in doc.tags
    assert "brand:hisense" in doc.tags
    assert "category:refrigerator" in doc.tags
    assert "model:hr6fdff701sw" in doc.tags
    assert "manual:hisense-hr6fdff701sw-zh-cn-v1" in doc.tags


def test_manual_node_attrs_keeps_backward_compatible_manual_fields():
    metadata = ManualMetadata(
        manual_id="m1",
        title="Manual",
        source_file="manual.md",
        product_category="coffee",
        product_model="CM1",
        tags=("steam",),
    )

    attrs = manual_node_attrs(metadata)

    assert attrs["doc_id"] == "m1"
    assert attrs["domain"] == "product_manual"
    assert attrs["doc_type"] == "manual"
    assert attrs["attributes"]["product_model"] == "CM1"
    assert attrs["manual_id"] == "m1"
    assert attrs["product_category"] == "coffee"
    assert attrs["product_model"] == "CM1"
    assert "model:cm1" in attrs["tags"]


def test_manual_node_attrs_honors_generic_sidecar_metadata():
    metadata = ManualMetadata(
        manual_id="python-tutorial",
        title="Python Tutorial",
        source_file="public_web/python.md",
        product_category="software_docs",
        tags=("python",),
        extra={
            "domain": "software_docs",
            "doc_type": "documentation",
            "remote_id": "https://docs.python.org/3/tutorial/index.html",
            "url": "https://docs.python.org/3/tutorial/index.html",
        },
    )

    attrs = manual_node_attrs(metadata)

    assert attrs["doc_id"] == "python-tutorial"
    assert attrs["domain"] == "software_docs"
    assert attrs["doc_type"] == "documentation"
    assert attrs["manual_id"] == "python-tutorial"
    assert attrs["product_category"] == "software_docs"
    assert attrs["remote_id"] == "https://docs.python.org/3/tutorial/index.html"
    assert attrs["attributes"]["manual_id"] == "python-tutorial"
    assert attrs["attributes"]["url"] == "https://docs.python.org/3/tutorial/index.html"
    assert "category:software-docs" in attrs["tags"]
