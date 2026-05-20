from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path
import re
from typing import Any

from .config import Settings
from .errors import ErrorCode, ServiceError, StorageSchemaMismatchError
from .manuals import ManualMetadata
from .storage.atomic import atomic_write

ASSET_SCHEMA_VERSION = "document_asset.v1"
ASSET_MANIFEST_SCHEMA_VERSION = "asset_manifest.v1"
ASSET_TYPES = {"source_file", "embedded_image", "page_snapshot", "region_crop", "table_snapshot", "ocr_layer"}
ASSET_STATUSES = {"ready", "missing", "failed", "deleted"}
PDF_RENDERER_UNAVAILABLE = "renderer_unavailable"


@dataclass(frozen=True)
class DocumentAsset:
    asset_id: str
    kb_name: str
    doc_id: str
    source_file: str
    type: str
    mime_type: str
    storage_backend: str
    storage_key: str
    checksum: str
    size_bytes: int = 0
    source_version: str = ""
    page_number: int | None = None
    bbox: tuple[float, float, float, float] | None = None
    width: int | None = None
    height: int | None = None
    caption: str = ""
    nearby_text: str = ""
    ocr_text: str = ""
    metadata: dict[str, Any] = field(default_factory=dict)
    status: str = "ready"
    failure_reason: str = ""
    created_at: str = ""
    updated_at: str = ""
    extractor_name: str = ""
    extractor_version: str = ""
    schema_version: str = ASSET_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "asset_id": self.asset_id,
            "kb_name": self.kb_name,
            "doc_id": self.doc_id,
            "source_file": self.source_file,
            "source_version": self.source_version,
            "type": self.type,
            "mime_type": self.mime_type,
            "storage_backend": self.storage_backend,
            "storage_key": self.storage_key,
            "page_number": self.page_number,
            "bbox": list(self.bbox) if self.bbox is not None else None,
            "width": self.width,
            "height": self.height,
            "checksum": self.checksum,
            "size_bytes": self.size_bytes,
            "caption": self.caption,
            "nearby_text": self.nearby_text,
            "ocr_text": self.ocr_text,
            "metadata": dict(self.metadata),
            "status": self.status,
            "failure_reason": self.failure_reason,
            "created_at": self.created_at,
            "updated_at": self.updated_at,
            "extractor_name": self.extractor_name,
            "extractor_version": self.extractor_version,
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "DocumentAsset":
        if str(data.get("schema_version") or ASSET_SCHEMA_VERSION) != ASSET_SCHEMA_VERSION:
            raise StorageSchemaMismatchError(ASSET_SCHEMA_VERSION, str(data.get("schema_version") or ""))
        asset_type = str(data.get("type") or "")
        status = str(data.get("status") or "ready")
        if asset_type not in ASSET_TYPES:
            raise ServiceError(ErrorCode.STORAGE_LOAD_FAILED, "Document asset type is not supported.", {"asset_type": asset_type})
        if status not in ASSET_STATUSES:
            raise ServiceError(ErrorCode.STORAGE_LOAD_FAILED, "Document asset status is not supported.", {"status": status})
        bbox_raw = data.get("bbox")
        bbox = tuple(float(value) for value in bbox_raw) if isinstance(bbox_raw, list) and len(bbox_raw) == 4 else None
        return cls(
            asset_id=str(data.get("asset_id") or ""),
            kb_name=str(data.get("kb_name") or ""),
            doc_id=str(data.get("doc_id") or ""),
            source_file=str(data.get("source_file") or ""),
            source_version=str(data.get("source_version") or ""),
            type=asset_type,
            mime_type=str(data.get("mime_type") or "application/octet-stream"),
            storage_backend=str(data.get("storage_backend") or "local"),
            storage_key=str(data.get("storage_key") or ""),
            page_number=_optional_int(data.get("page_number")),
            bbox=bbox,  # type: ignore[arg-type]
            width=_optional_int(data.get("width")),
            height=_optional_int(data.get("height")),
            checksum=str(data.get("checksum") or ""),
            size_bytes=int(data.get("size_bytes") or 0),
            caption=str(data.get("caption") or ""),
            nearby_text=str(data.get("nearby_text") or ""),
            ocr_text=str(data.get("ocr_text") or ""),
            metadata=dict(data.get("metadata") or {}),
            status=status,
            failure_reason=str(data.get("failure_reason") or ""),
            created_at=str(data.get("created_at") or ""),
            updated_at=str(data.get("updated_at") or ""),
            extractor_name=str(data.get("extractor_name") or ""),
            extractor_version=str(data.get("extractor_version") or ""),
        )


@dataclass(frozen=True)
class AssetRef:
    backend: str
    storage_key: str
    checksum: str
    size_bytes: int
    mime_type: str


@dataclass(frozen=True)
class AssetExtractionSummary:
    attempted: int = 0
    created: int = 0
    skipped: int = 0
    failed: int = 0
    failure_reasons: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "created": self.created,
            "skipped": self.skipped,
            "failed": self.failed,
            "failure_reasons": dict(sorted(self.failure_reasons.items())),
        }


@dataclass
class AssetManifest:
    kb_name: str
    assets: dict[str, DocumentAsset] = field(default_factory=dict)
    updated_at: str = ""
    schema_version: str = ASSET_MANIFEST_SCHEMA_VERSION

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kb_name": self.kb_name,
            "updated_at": self.updated_at,
            "assets": {asset_id: asset.to_dict() for asset_id, asset in sorted(self.assets.items())},
            "stats": asset_inventory_summary(self)["stats"],
        }

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "AssetManifest":
        if str(data.get("schema_version") or ASSET_MANIFEST_SCHEMA_VERSION) != ASSET_MANIFEST_SCHEMA_VERSION:
            raise StorageSchemaMismatchError(ASSET_MANIFEST_SCHEMA_VERSION, str(data.get("schema_version") or ""))
        assets_raw = data.get("assets") or {}
        if not isinstance(assets_raw, dict):
            raise ServiceError(ErrorCode.STORAGE_LOAD_FAILED, "Asset manifest assets must be an object.")
        assets = {str(asset_id): DocumentAsset.from_dict(dict(payload)) for asset_id, payload in assets_raw.items()}
        return cls(
            kb_name=str(data.get("kb_name") or "default"),
            assets=assets,
            updated_at=str(data.get("updated_at") or ""),
        )


class LocalDocumentAssetStore:
    backend = "local"

    def __init__(self, root_dir: str | Path):
        self.root_dir = Path(root_dir).expanduser().resolve()

    def put(self, kb_name: str, doc_id: str, asset_type: str, asset_id: str, content: bytes, mime_type: str) -> AssetRef:
        checksum = hashlib.sha256(content).hexdigest()
        key = make_asset_storage_key(kb_name, doc_id, asset_type, asset_id, _extension_for_mime(mime_type))
        path = self.path_for_key(key)

        def write(tmp_path: Path) -> None:
            tmp_path.write_bytes(content)

        atomic_write(path, write)
        return AssetRef(self.backend, key, checksum, len(content), mime_type)

    def get(self, storage_key: str) -> bytes:
        path = self.path_for_key(storage_key)
        if not path.exists():
            raise ServiceError(ErrorCode.STORAGE_LOAD_FAILED, "Document asset is missing.", {"storage_key": storage_key})
        return path.read_bytes()

    def delete(self, storage_key: str) -> None:
        self.path_for_key(storage_key).unlink(missing_ok=True)

    def exists(self, storage_key: str) -> bool:
        return self.path_for_key(storage_key).exists()

    def path_for_key(self, storage_key: str) -> Path:
        key_path = Path(storage_key)
        if key_path.is_absolute() or any(part in {"", ".", ".."} for part in key_path.parts):
            raise ServiceError(ErrorCode.INVALID_INPUT, "asset storage_key must be a safe relative path.", {"storage_key": storage_key})
        path = (self.root_dir / key_path).resolve()
        try:
            path.relative_to(self.root_dir)
        except ValueError as exc:
            raise ServiceError(ErrorCode.INVALID_INPUT, "asset storage_key escapes asset root.", {"storage_key": storage_key}) from exc
        return path

    def iter_storage_keys(self) -> list[str]:
        if not self.root_dir.exists():
            return []
        return sorted(
            str(path.relative_to(self.root_dir)).replace(os.sep, "/")
            for path in self.root_dir.rglob("*")
            if path.is_file() and not path.name.startswith(".")
        )


def create_asset_store(cfg: Settings) -> LocalDocumentAssetStore:
    if cfg.assets.store_backend == "local":
        return LocalDocumentAssetStore(cfg.assets.root_dir)
    raise ServiceError(
        ErrorCode.INVALID_CONFIG,
        "Configured document asset backend is not implemented in this build.",
        {"asset_backend": cfg.assets.store_backend},
    )


def asset_manifest_path(kb_name: str, cfg: Settings) -> Path:
    return Path(cfg.storage.data_dir) / _safe_segment(kb_name) / "assets" / "asset_manifest.json"


def load_asset_manifest(kb_name: str, cfg: Settings) -> AssetManifest:
    path = asset_manifest_path(kb_name, cfg)
    if not path.exists():
        return AssetManifest(kb_name=kb_name)
    try:
        return AssetManifest.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except json.JSONDecodeError as exc:
        raise ServiceError(ErrorCode.STORAGE_LOAD_FAILED, "Asset manifest is not valid JSON.", {"kb_name": kb_name}) from exc


def save_asset_manifest(manifest: AssetManifest, cfg: Settings) -> None:
    updated = AssetManifest(kb_name=manifest.kb_name, assets=dict(manifest.assets), updated_at=_now())

    def write_manifest(tmp_path: Path) -> None:
        tmp_path.write_text(json.dumps(updated.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    atomic_write(asset_manifest_path(manifest.kb_name, cfg), write_manifest)


def make_asset_id(
    *,
    kb_name: str,
    doc_id: str,
    source_file: str,
    source_version: str,
    asset_type: str,
    page_number: int | None = None,
    bbox: tuple[float, float, float, float] | None = None,
    extractor_name: str = "",
    extractor_version: str = "",
    content_checksum: str = "",
) -> str:
    logical = {
        "kb_name": kb_name,
        "doc_id": doc_id,
        "source_file": source_file.replace("\\", "/"),
        "source_version": source_version,
        "asset_type": asset_type,
        "page_number": page_number,
        "bbox": list(bbox) if bbox else None,
        "extractor_name": extractor_name,
        "extractor_version": extractor_version,
        "content_checksum": content_checksum,
    }
    digest = hashlib.sha256(json.dumps(logical, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()[:24]
    return f"asset:sha256:{digest}"


def make_asset_storage_key(kb_name: str, doc_id: str, asset_type: str, asset_id: str, ext: str) -> str:
    safe_ext = ext if ext.startswith(".") and re.fullmatch(r"\.[A-Za-z0-9]+", ext) else ".bin"
    return "/".join(
        [
            _safe_segment(kb_name),
            _safe_segment(doc_id),
            _safe_segment(asset_type),
            f"{_safe_segment(asset_id)}{safe_ext.lower()}",
        ]
    )


def extract_document_assets(source_path: str | Path, metadata: ManualMetadata, kb_name: str, cfg: Settings) -> tuple[list[DocumentAsset], AssetExtractionSummary]:
    if not cfg.assets.enabled:
        return [], AssetExtractionSummary(skipped=1)
    path = Path(source_path)
    if path.suffix.lower() != ".pdf" or not cfg.assets.pdf_page_snapshots_enabled:
        return [], AssetExtractionSummary(skipped=1)
    return extract_pdf_page_snapshots(path, metadata, kb_name, cfg)


def extract_pdf_page_snapshots(source_path: str | Path, metadata: ManualMetadata, kb_name: str, cfg: Settings) -> tuple[list[DocumentAsset], AssetExtractionSummary]:
    source = Path(source_path)
    try:
        import fitz  # type: ignore[import-not-found]
    except Exception:
        summary = AssetExtractionSummary(attempted=1, failed=1, failure_reasons={PDF_RENDERER_UNAVAILABLE: 1})
        if cfg.assets.strict_extraction:
            raise ServiceError(ErrorCode.INVALID_CONFIG, "PDF page snapshot renderer is unavailable.", {"renderer": "pymupdf"}) from None
        return [
            failed_asset_record(
                kb_name=kb_name,
                metadata=metadata,
                asset_type="page_snapshot",
                page_number=None,
                failure_reason=PDF_RENDERER_UNAVAILABLE,
                extractor_version=cfg.assets.extractor_version,
            )
        ], summary
    assets: list[DocumentAsset] = []
    failures: dict[str, int] = {}
    attempted = 0
    try:
        with fitz.open(source) as pdf:
            for index, page in enumerate(pdf, start=1):
                attempted += 1
                try:
                    pixmap = page.get_pixmap(matrix=fitz.Matrix(1, 1), alpha=False)
                    content = pixmap.tobytes("png")
                    content_checksum = hashlib.sha256(content).hexdigest()
                    asset_id = make_asset_id(
                        kb_name=kb_name,
                        doc_id=metadata.manual_id,
                        source_file=metadata.source_file,
                        source_version=_source_version(metadata, source),
                        asset_type="page_snapshot",
                        page_number=index,
                        extractor_name="pymupdf",
                        extractor_version=cfg.assets.extractor_version,
                        content_checksum=content_checksum,
                    )
                    ref = create_asset_store(cfg).put(kb_name, metadata.manual_id, "page_snapshot", asset_id, content, "image/png")
                    assets.append(
                        DocumentAsset(
                            asset_id=asset_id,
                            kb_name=kb_name,
                            doc_id=metadata.manual_id,
                            source_file=metadata.source_file,
                            source_version=_source_version(metadata, source),
                            type="page_snapshot",
                            mime_type=ref.mime_type,
                            storage_backend=ref.backend,
                            storage_key=ref.storage_key,
                            page_number=index,
                            width=int(pixmap.width),
                            height=int(pixmap.height),
                            checksum=ref.checksum,
                            size_bytes=ref.size_bytes,
                            metadata={"renderer": "pymupdf"},
                            status="ready",
                            created_at=_now(),
                            updated_at=_now(),
                            extractor_name="pymupdf",
                            extractor_version=cfg.assets.extractor_version,
                        )
                    )
                except Exception:
                    reason = "page_render_failed"
                    failures[reason] = failures.get(reason, 0) + 1
                    assets.append(
                        failed_asset_record(
                            kb_name=kb_name,
                            metadata=metadata,
                            asset_type="page_snapshot",
                            page_number=index,
                            failure_reason=reason,
                            extractor_version=cfg.assets.extractor_version,
                        )
                    )
    except Exception as exc:
        reason = bounded_failure_reason(type(exc).__name__)
        if cfg.assets.strict_extraction:
            raise ServiceError(ErrorCode.STORAGE_LOAD_FAILED, "PDF page snapshot extraction failed.", {"reason": reason}) from exc
        failures[reason] = failures.get(reason, 0) + 1
    failed = sum(failures.values())
    return assets, AssetExtractionSummary(attempted=attempted, created=sum(1 for asset in assets if asset.status == "ready"), failed=failed, failure_reasons=failures)


def failed_asset_record(
    *,
    kb_name: str,
    metadata: ManualMetadata,
    asset_type: str,
    page_number: int | None,
    failure_reason: str,
    extractor_version: str,
) -> DocumentAsset:
    now = _now()
    asset_id = make_asset_id(
        kb_name=kb_name,
        doc_id=metadata.manual_id,
        source_file=metadata.source_file,
        source_version=metadata.version or metadata.checksum,
        asset_type=asset_type,
        page_number=page_number,
        extractor_name="pdf_snapshot",
        extractor_version=extractor_version,
    )
    return DocumentAsset(
        asset_id=asset_id,
        kb_name=kb_name,
        doc_id=metadata.manual_id,
        source_file=metadata.source_file,
        source_version=metadata.version or metadata.checksum,
        type=asset_type,
        mime_type="image/png" if asset_type == "page_snapshot" else "application/octet-stream",
        storage_backend="local",
        storage_key="",
        checksum="",
        page_number=page_number,
        status="failed",
        failure_reason=bounded_failure_reason(failure_reason),
        created_at=now,
        updated_at=now,
        extractor_name="pdf_snapshot",
        extractor_version=extractor_version,
    )


def replace_document_assets(manifest: AssetManifest, doc_id: str, assets: list[DocumentAsset]) -> AssetManifest:
    kept = {asset_id: asset for asset_id, asset in manifest.assets.items() if asset.doc_id != doc_id}
    kept.update({asset.asset_id: asset for asset in assets})
    return AssetManifest(kb_name=manifest.kb_name, assets=kept, updated_at=_now())


def remove_document_assets(manifest: AssetManifest, doc_id: str, *, mark_deleted: bool = False) -> AssetManifest:
    if not mark_deleted:
        return AssetManifest(kb_name=manifest.kb_name, assets={asset_id: asset for asset_id, asset in manifest.assets.items() if asset.doc_id != doc_id}, updated_at=_now())
    now = _now()
    updated = {
        asset_id: (asset if asset.doc_id != doc_id else _asset_with_status(asset, "deleted", now))
        for asset_id, asset in manifest.assets.items()
    }
    return AssetManifest(kb_name=manifest.kb_name, assets=updated, updated_at=now)


def cleanup_orphan_assets(manifest: AssetManifest, store: LocalDocumentAssetStore) -> dict[str, Any]:
    referenced = {asset.storage_key for asset in manifest.assets.values() if asset.storage_backend == store.backend and asset.storage_key and asset.status == "ready"}
    deleted = []
    for storage_key in store.iter_storage_keys():
        if storage_key not in referenced:
            store.delete(storage_key)
            deleted.append(storage_key)
    return {"deleted_count": len(deleted)}


def verify_asset_manifest(manifest: AssetManifest, store: LocalDocumentAssetStore) -> dict[str, Any]:
    missing = [
        {"asset_id": asset.asset_id, "doc_id": asset.doc_id, "type": asset.type}
        for asset in manifest.assets.values()
        if asset.storage_backend == store.backend and asset.status == "ready" and asset.storage_key and not store.exists(asset.storage_key)
    ]
    return {"checked_count": sum(1 for asset in manifest.assets.values() if asset.storage_backend == store.backend and asset.status == "ready"), "missing_count": len(missing), "missing": missing}


def asset_inventory_summary(manifest: AssetManifest, extraction: AssetExtractionSummary | None = None) -> dict[str, Any]:
    by_type: dict[str, int] = {}
    by_status: dict[str, int] = {}
    by_backend: dict[str, int] = {}
    for asset in manifest.assets.values():
        by_type[asset.type] = by_type.get(asset.type, 0) + 1
        by_status[asset.status] = by_status.get(asset.status, 0) + 1
        by_backend[asset.storage_backend] = by_backend.get(asset.storage_backend, 0) + 1
    return {
        "schema_version": ASSET_MANIFEST_SCHEMA_VERSION,
        "kb_name": manifest.kb_name,
        "asset_count": len(manifest.assets),
        "stats": {
            "by_type": dict(sorted(by_type.items())),
            "by_status": dict(sorted(by_status.items())),
            "by_backend": dict(sorted(by_backend.items())),
        },
        "extraction": (extraction or AssetExtractionSummary()).to_dict(),
    }


def bounded_failure_reason(reason: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(reason).strip().lower())[:80].strip("_")
    return normalized or "unknown"


def _asset_with_status(asset: DocumentAsset, status: str, updated_at: str) -> DocumentAsset:
    data = asset.to_dict()
    data["status"] = status
    data["updated_at"] = updated_at
    return DocumentAsset.from_dict(data)


def _source_version(metadata: ManualMetadata, source: Path) -> str:
    if metadata.version:
        return metadata.version
    if metadata.checksum:
        return metadata.checksum
    try:
        stat = source.stat()
    except OSError:
        return ""
    return f"{int(stat.st_mtime_ns)}:{stat.st_size}"


def _safe_segment(value: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", str(value).strip()).strip(".-")
    return normalized or "item"


def _extension_for_mime(mime_type: str) -> str:
    if mime_type == "image/png":
        return ".png"
    if mime_type in {"image/jpeg", "image/jpg"}:
        return ".jpg"
    if mime_type == "application/pdf":
        return ".pdf"
    return ".bin"


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    return int(value)


def _now() -> str:
    return datetime.now(timezone.utc).isoformat()
