from __future__ import annotations

import json

import pytest

from tagmemorag.errors import ServiceError
from tagmemorag.manuals import (
    ManualMetadata,
    fallback_manual_metadata,
    load_manual_metadata,
    metadata_sidecar_path,
    normalize_tag,
)


def test_metadata_sidecar_path_uses_source_stem(tmp_path):
    assert metadata_sidecar_path(tmp_path / "manual.pdf").name == "manual.metadata.json"


def test_manual_metadata_from_sidecar_normalizes_tags_and_source_file(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "fridge.md"
    source.write_text("# 温度\n冷藏室温度调节。\n", encoding="utf-8")
    (docs / "fridge.metadata.json").write_text(
        json.dumps(
            {
                "manual_id": "gorenje-nrk6192-zh-cn-v1",
                "title": "Gorenje refrigerator manual",
                "source_file": "ignored.md",
                "product_category": "fridge",
                "language": "zh-CN",
                "brand": "Gorenje",
                "product_model": "NRK6192",
                "version": "v1",
                "tags": ["Temperature Setting", "fault_code", "温度"],
            }
        ),
        encoding="utf-8",
    )

    metadata = load_manual_metadata(source, docs)

    assert metadata.source_file == "fridge.md"
    assert metadata.tags == ("temperature-setting", "fault-code")
    assert metadata.to_node_attrs()["product_model"] == "NRK6192"


def test_manual_metadata_from_sidecar_preserves_generic_extra_fields(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "python.md"
    source.write_text("# Python\n", encoding="utf-8")
    (docs / "python.metadata.json").write_text(
        json.dumps(
            {
                "manual_id": "python-tutorial",
                "title": "Python Tutorial",
                "source_file": "ignored.md",
                "product_category": "software_docs",
                "domain": "software_docs",
                "doc_type": "documentation",
                "remote_id": "https://docs.python.org/3/tutorial/index.html",
                "url": "https://docs.python.org/3/tutorial/index.html",
            }
        ),
        encoding="utf-8",
    )

    metadata = load_manual_metadata(source, docs)

    assert metadata.source_file == "python.md"
    assert metadata.extra == {
        "domain": "software_docs",
        "doc_type": "documentation",
        "remote_id": "https://docs.python.org/3/tutorial/index.html",
        "url": "https://docs.python.org/3/tutorial/index.html",
    }
    attrs = metadata.to_node_attrs()
    assert attrs["domain"] == "software_docs"
    assert attrs["doc_type"] == "documentation"


def test_fallback_manual_metadata_uses_relative_path_and_parent_category(tmp_path):
    docs = tmp_path / "docs"
    source = docs / "fridge" / "basic-manual.txt"
    source.parent.mkdir(parents=True)
    source.write_text("temperature help", encoding="utf-8")

    metadata = fallback_manual_metadata(source, docs)

    assert metadata.manual_id == "fridge-basic-manual"
    assert metadata.title == "basic-manual"
    assert metadata.product_category == "fridge"
    assert metadata.language == "unknown"
    assert metadata.tags == ()


def test_invalid_sidecar_tags_raise_invalid_input(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    source = docs / "manual.md"
    source.write_text("body", encoding="utf-8")
    (docs / "manual.metadata.json").write_text(
        json.dumps(
            {
                "manual_id": "manual",
                "title": "Manual",
                "source_file": "manual.md",
                "product_category": "fridge",
                "tags": "temperature",
            }
        ),
        encoding="utf-8",
    )

    with pytest.raises(ServiceError) as exc:
        load_manual_metadata(source, docs)

    assert exc.value.code == "INVALID_INPUT"


def test_duplicate_manual_id_detection(tmp_path):
    docs = tmp_path / "docs"
    docs.mkdir()
    seen: set[str] = set()
    for name in ("a.md", "b.md"):
        (docs / name).write_text("body", encoding="utf-8")
        (docs / name.replace(".md", ".metadata.json")).write_text(
            json.dumps(
                {
                    "manual_id": "same",
                    "title": name,
                    "source_file": name,
                    "product_category": "fridge",
                }
            ),
            encoding="utf-8",
        )

    load_manual_metadata(docs / "a.md", docs, seen_manual_ids=seen)
    with pytest.raises(ServiceError) as exc:
        load_manual_metadata(docs / "b.md", docs, seen_manual_ids=seen)

    assert exc.value.code == "INVALID_INPUT"
    assert exc.value.detail["manual_id"] == "same"


def test_manual_metadata_rejects_empty_required_fields():
    with pytest.raises(ServiceError):
        ManualMetadata.from_dict({"manual_id": "", "title": "x", "source_file": "x.md", "product_category": "fridge"})


def test_normalize_tag_lower_kebab_case():
    assert normalize_tag(" Temperature_Setting ") == "temperature-setting"
