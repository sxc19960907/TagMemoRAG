from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
from typing import Any

from .manual_library import ManualLibraryManifest
from .storage.atomic import atomic_write

REBUILD_IMPACT_FILENAME = "rebuild_impact.json"


@dataclass(frozen=True)
class ManualImpact:
    manual_id: str
    operation: str
    outcome: str
    source_file: str = ""
    chunks_added: int = 0
    chunks_removed: int = 0
    chunks_changed: int = 0
    chunks_reused: int = 0
    chunks_embedded: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "manual_id": self.manual_id,
            "operation": self.operation,
            "outcome": self.outcome,
            "source_file": self.source_file,
            "chunks_added": self.chunks_added,
            "chunks_removed": self.chunks_removed,
            "chunks_changed": self.chunks_changed,
            "chunks_reused": self.chunks_reused,
            "chunks_embedded": self.chunks_embedded,
        }


@dataclass(frozen=True)
class RebuildImpactReport:
    kb_name: str
    build_id: str
    summary: dict[str, int]
    manuals: list[ManualImpact] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "kb_name": self.kb_name,
            "build_id": self.build_id,
            "summary": dict(self.summary),
            "manuals": [manual.to_dict() for manual in self.manuals],
        }


def impact_path(kb_name: str, data_dir: str | Path) -> Path:
    return Path(data_dir) / kb_name / REBUILD_IMPACT_FILENAME


def save_rebuild_impact(path: Path, report: RebuildImpactReport) -> None:
    def write(tmp_path: Path) -> None:
        tmp_path.write_text(json.dumps(report.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    atomic_write(path, write)


def make_impact_report(
    *,
    kb_name: str,
    build_id: str,
    manifest: ManualLibraryManifest | None,
    old_identity_keys: set[str],
    new_identity_keys: set[str],
    reused_identity_keys: set[str],
    embedded_identity_keys: set[str],
    old_keys_by_manual: dict[str, set[str]],
    new_keys_by_manual: dict[str, set[str]],
) -> RebuildImpactReport:
    added = new_identity_keys - old_identity_keys
    removed = old_identity_keys - new_identity_keys
    changed = (new_identity_keys & old_identity_keys) - reused_identity_keys
    summary = {
        "manuals_added": 0,
        "manuals_removed": 0,
        "manuals_changed": 0,
        "manuals_reused": 0,
        "chunks_added": len(added),
        "chunks_removed": len(removed),
        "chunks_changed": len(changed),
        "chunks_reused": len(reused_identity_keys),
        "chunks_embedded": len(embedded_identity_keys),
    }
    dirty = manifest.dirty_manuals if manifest is not None else {}
    manual_ids = sorted(set(old_keys_by_manual) | set(new_keys_by_manual) | set(dirty))
    manuals: list[ManualImpact] = []
    for manual_id in manual_ids:
        before = old_keys_by_manual.get(manual_id, set())
        after = new_keys_by_manual.get(manual_id, set())
        dirty_entry = dirty.get(manual_id)
        operation = dirty_entry.operation if dirty_entry else "unchanged"
        outcome = _manual_outcome(before, after, dirty_entry is not None)
        if outcome == "added":
            summary["manuals_added"] += 1
        elif outcome == "removed":
            summary["manuals_removed"] += 1
        elif outcome == "changed":
            summary["manuals_changed"] += 1
        elif outcome == "reused":
            summary["manuals_reused"] += 1
        manuals.append(
            ManualImpact(
                manual_id=manual_id,
                operation=operation,
                outcome=outcome,
                source_file=dirty_entry.source_file if dirty_entry else "",
                chunks_added=len(after - before),
                chunks_removed=len(before - after),
                chunks_changed=len((before & after) - reused_identity_keys),
                chunks_reused=len(after & reused_identity_keys),
                chunks_embedded=len(after & embedded_identity_keys),
            )
        )
    return RebuildImpactReport(kb_name=kb_name, build_id=build_id, summary=summary, manuals=manuals)


def _manual_outcome(before: set[str], after: set[str], dirty: bool) -> str:
    if before and not after:
        return "removed"
    if after and not before:
        return "added"
    if dirty or before != after:
        return "changed"
    return "reused"
