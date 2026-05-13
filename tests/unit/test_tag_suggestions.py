from __future__ import annotations

from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.manual_library import list_records, upsert_manual
from tagmemorag.tag_governance import save_tag_policy
from tagmemorag.tag_suggestions import suggest_tags


def _settings(tmp_path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"dim": 64},
    )


def test_suggest_tags_uses_metadata_and_excludes_existing_draft_tags(tmp_path):
    cfg = _settings(tmp_path)
    upsert_manual(
        "default",
        {
            "manual_id": "cm0",
            "title": "Coffee Maintenance",
            "source_file": "coffee/cm0.md",
            "product_category": "coffee",
            "tags": ["maintenance", "steam-wand"],
        },
        b"# Maintenance\nClean the steam wand.\n",
        cfg,
    )
    records = list_records("default", cfg)

    suggestions, existing_tags = suggest_tags(
        {
            "manual_id": "cm1",
            "title": "CM1 Coffee Machine Maintenance Manual",
            "source_file": "coffee/cm1-maintenance.md",
            "product_category": "coffee",
            "product_model": "CM1",
            "tags": ["coffee"],
        },
        records=records,
        limit=6,
    )

    tags = [item.tag for item in suggestions]
    assert "maintenance" in tags
    assert "coffee" not in tags
    assert existing_tags == ["maintenance", "steam-wand"]
    maintenance = next(item for item in suggestions if item.tag == "maintenance")
    assert "existing_tags" in maintenance.sources
    assert "title" in maintenance.sources or "source_file" in maintenance.sources


def test_suggest_tags_dedupes_and_filters_low_value_tokens():
    suggestions, _ = suggest_tags(
        {
            "manual_id": "m1",
            "title": "The User Manual v2",
            "source_file": "guides/the-user-manual-v2.pdf",
            "product_category": "setup",
            "product_model": "NRK6192",
            "tags": [],
        },
        limit=10,
    )

    tags = [item.tag for item in suggestions]
    assert len(tags) == len(set(tags))
    assert "manual" not in tags
    assert "pdf" not in tags
    assert "v2" not in tags
    assert "nrk6192" in tags
    assert "setup" in tags


def test_existing_kb_tag_preferred_when_it_overlaps_draft_text(tmp_path):
    cfg = _settings(tmp_path)
    for manual_id in ("cm0", "cm2"):
        upsert_manual(
            "default",
            {
                "manual_id": manual_id,
                "title": f"{manual_id} Steam Wand",
                "source_file": f"coffee/{manual_id}.md",
                "product_category": "coffee",
                "tags": ["steam-wand"],
            },
            b"# Steam\nClean wand.\n",
            cfg,
        )

    suggestions, _ = suggest_tags(
        {
            "manual_id": "cm1",
            "title": "Steam wand cleaning",
            "source_file": "coffee/cm1.md",
            "product_category": "coffee",
            "tags": [],
        },
        records=list_records("default", cfg),
        limit=3,
    )

    assert suggestions[0].tag == "steam-wand"
    assert suggestions[0].score > 0.6


def test_suggest_tags_prefers_policy_canonical_and_hides_deprecated(tmp_path):
    cfg = _settings(tmp_path)
    policy = save_tag_policy(
        "default",
        cfg,
        {
            "canonical_tags": [{"tag": "maintenance"}],
            "synonyms": {"cleaning": "maintenance"},
            "deprecated_tags": {"maintainance": {"replacement": "maintenance"}},
        },
    )
    upsert_manual(
        "default",
        {
            "manual_id": "cm0",
            "title": "Cleaning",
            "source_file": "coffee/cm0.md",
            "product_category": "coffee",
            "tags": ["cleaning", "maintainance"],
        },
        b"# Clean\n",
        cfg,
    )

    suggestions, existing_tags = suggest_tags(
        {
            "manual_id": "cm1",
            "title": "Coffee cleaning",
            "source_file": "coffee/cm1.md",
            "product_category": "coffee",
            "tags": ["cleaning"],
        },
        records=list_records("default", cfg),
        tag_policy=policy,
        limit=5,
    )

    tags = [item.tag for item in suggestions]
    assert "maintenance" in tags
    assert "maintainance" not in tags
    assert existing_tags == ["maintenance"]
