from __future__ import annotations

import json
from pathlib import Path
import re

from ..manuals import ManualMetadata
from ..parser import SUPPORTED_DOCUMENT_SUFFIXES
from ..storage.atomic import atomic_write
from .base import ConnectorRecord, ConnectorSyncSummary


def materialize_connector_records(
    records: tuple[ConnectorRecord, ...],
    *,
    kb_name: str,
    root_dir: str | Path,
    provider: str,
    strict: bool = False,
) -> ConnectorSyncSummary:
    root = Path(root_dir) / _safe_segment(kb_name)
    attempted = 0
    materialized = 0
    tombstoned = 0
    failures: dict[str, int] = {}
    for record in records:
        attempted += 1
        try:
            _materialize_one(record, root)
            if record.action == "delete":
                tombstoned += 1
            else:
                materialized += 1
        except Exception as exc:
            if strict:
                raise
            reason = _bounded_reason(type(exc).__name__)
            failures[reason] = failures.get(reason, 0) + 1
    return ConnectorSyncSummary(
        provider=provider,
        attempted=attempted,
        materialized=materialized,
        tombstoned=tombstoned,
        failed=sum(failures.values()),
        failure_reasons=failures,
    )


def _materialize_one(record: ConnectorRecord, root: Path) -> None:
    source_rel = _safe_source_path(record.document.source_file)
    if source_rel.suffix.lower() not in SUPPORTED_DOCUMENT_SUFFIXES:
        raise ValueError("unsupported_document_suffix")
    target = root / source_rel
    metadata = _metadata_dict_for_record(record, source_rel.as_posix())
    if record.action != "delete":
        atomic_write(target, lambda tmp_path: tmp_path.write_bytes(record.document.content))
    sidecar = target.with_name(f"{target.stem}.metadata.json")
    atomic_write(
        sidecar,
        lambda tmp_path: tmp_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8"),
    )


def _metadata_dict_for_record(record: ConnectorRecord, source_file: str) -> dict:
    metadata = _metadata_for_record(record, source_file).to_node_attrs()
    if record.remote_id:
        metadata["remote_id"] = record.remote_id
    for key, value in sorted(record.metadata.items()):
        if key not in metadata and value:
            metadata[key] = value
    return metadata


def _metadata_for_record(record: ConnectorRecord, source_file: str) -> ManualMetadata:
    status = "deleted" if record.action == "delete" else "active"
    return ManualMetadata(
        manual_id=record.manual_id,
        title=record.title,
        source_file=source_file,
        product_category=record.product_category,
        language=record.language,
        version=record.version,
        tags=record.tags,
        status=status,
        notes=f"connector:{record.record_id}",
    )


def _safe_source_path(source_file: str) -> Path:
    value = str(source_file or "").replace("\\", "/").strip()
    path = Path(value)
    if path.is_absolute() or any(part in {"", ".", ".."} for part in path.parts):
        raise ValueError("unsafe_source_file")
    return path


def _safe_segment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip()).strip("-")
    return normalized or "default"


def _bounded_reason(reason: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(reason).strip().lower())[:80].strip("_")
    return normalized or "unknown"


__all__ = ["materialize_connector_records"]
