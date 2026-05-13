from __future__ import annotations

import json

import pytest

from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.errors import ServiceError
from tagmemorag.manual_library import library_root, list_records, load_manifest, upsert_manual, validate_metadata
from tagmemorag.tag_governance import (
    commit_tag_rewrite,
    compute_tag_usage_stats,
    detect_tag_drift,
    load_tag_policy,
    parse_tag_policy,
    preview_tag_rewrite,
    save_tag_policy,
)


@pytest.fixture
def cfg(tmp_path) -> Settings:
    return Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"dim": 64},
    )


def _metadata(manual_id: str, source_file: str, tags: list[str], status: str = "active") -> dict[str, object]:
    return {
        "manual_id": manual_id,
        "title": f"{manual_id} Manual",
        "source_file": source_file,
        "product_category": "coffee",
        "status": status,
        "tags": tags,
    }


def test_policy_load_save_validation_and_cycle_detection(cfg):
    assert load_tag_policy("default", cfg).configured is False

    policy = save_tag_policy(
        "default",
        cfg,
        {
            "canonical_tags": [{"tag": "Maintenance", "label": "Maintenance"}],
            "synonyms": {"cleaning": "maintenance"},
            "deprecated_tags": {"maintainance": {"replacement": "maintenance", "reason": "typo"}},
        },
    )

    assert policy.canonical_tags[0].tag == "maintenance"
    path = library_root("default", cfg) / ".tagmemorag-tags.json"
    assert json.loads(path.read_text(encoding="utf-8"))["synonyms"] == {"cleaning": "maintenance"}

    with pytest.raises(ServiceError):
        parse_tag_policy(
            {
                "canonical_tags": [{"tag": "maintenance"}],
                "synonyms": {"cleaning": "wash", "wash": "cleaning"},
            },
            kb_name="default",
        )


def test_stats_drift_and_governance_validation(cfg):
    policy = save_tag_policy(
        "default",
        cfg,
        {
            "policy_mode": "strict",
            "canonical_tags": [{"tag": "maintenance"}],
            "synonyms": {"cleaning": "maintenance"},
            "deprecated_tags": {"maintainance": {"replacement": "maintenance"}},
        },
    )
    upsert_manual("default", _metadata("cm1", "coffee/cm1.md", ["cleaning"]), b"# Clean\n", cfg)
    upsert_manual("default", _metadata("cm2", "coffee/cm2.md", ["maintainance"], "disabled"), b"# Maintain\n", cfg)
    upsert_manual("default", _metadata("cm3", "coffee/cm3.md", ["unknown-tag"]), b"# Unknown\n", cfg)

    stats = compute_tag_usage_stats(list_records("default", cfg), policy)
    by_tag = {stat.tag: stat for stat in stats}
    assert by_tag["cleaning"].state == "synonym"
    assert by_tag["cleaning"].canonical_tag == "maintenance"
    assert by_tag["maintainance"].inactive_manual_count == 1

    issues = detect_tag_drift(stats, policy)
    codes = {issue.code for issue in issues}
    assert {"SYNONYM_IN_USE", "DEPRECATED_TAG_IN_USE", "UNKNOWN_TAG"} <= codes

    validation = validate_metadata(
        "default",
        _metadata("cm4", "coffee/cm4.md", ["unknown-tag"]),
        cfg,
        tag_policy=policy,
    )
    assert validation.valid is False
    assert validation.messages[-1].code == "TAG_UNKNOWN"


def test_rewrite_preview_and_commit_updates_sidecars_and_pending(cfg):
    save_tag_policy("default", cfg, {"canonical_tags": [{"tag": "maintenance"}]})
    upsert_manual("default", _metadata("cm1", "coffee/cm1.md", ["cleaning", "maintenance"]), b"# Clean\n", cfg)
    upsert_manual("default", _metadata("cm2", "coffee/cm2.md", ["cleaning"]), b"# Clean\n", cfg)

    preview = preview_tag_rewrite("default", cfg, source_tags=["cleaning"], target_tag="maintenance")
    assert preview.affected_count == 2
    assert preview.changes[0].after_tags == ("maintenance",)

    result = commit_tag_rewrite(
        "default",
        cfg,
        source_tags=["cleaning"],
        target_tag="maintenance",
        update_policy=True,
    )

    assert result.updated_count == 2
    assert load_manifest("default", cfg).pending_changes is True
    records = {record.manual_id: record for record in list_records("default", cfg)}
    assert records["cm1"].metadata.tags == ("maintenance",)
    assert records["cm2"].metadata.tags == ("maintenance",)
    assert load_tag_policy("default", cfg).synonyms["cleaning"] == "maintenance"
