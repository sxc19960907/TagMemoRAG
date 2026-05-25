from __future__ import annotations

from dataclasses import dataclass, field
import json
from pathlib import Path
import re
from typing import Any

from .errors import ErrorCode, ServiceError

MANUAL_METADATA_SUFFIX = ".metadata.json"
MANUAL_METADATA_FIELDS = (
    "manual_id",
    "title",
    "source_file",
    "product_category",
    "language",
    "brand",
    "product_name",
    "product_model",
    "version",
    "tags",
    "status",
    "uploaded_at",
    "checksum",
    "notes",
)
GENERIC_METADATA_FIELDS = ("domain", "doc_type", "remote_id", "url", "source_format")


@dataclass(frozen=True)
class ManualMetadata:
    manual_id: str
    title: str
    source_file: str
    product_category: str
    language: str = "unknown"
    brand: str = ""
    product_name: str = ""
    product_model: str = ""
    version: str = ""
    tags: tuple[str, ...] = field(default_factory=tuple)
    status: str = "active"
    uploaded_at: str = ""
    checksum: str = ""
    notes: str = ""
    extra: dict[str, str] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any], *, source_file: str | None = None) -> "ManualMetadata":
        if not isinstance(data, dict):
            raise _invalid_metadata("metadata must be a JSON object")
        values = {key: data.get(key, "") for key in MANUAL_METADATA_FIELDS}
        extra = {
            key: str(data.get(key, "")).strip()
            for key in GENERIC_METADATA_FIELDS
            if str(data.get(key, "")).strip()
        }
        if source_file is not None:
            values["source_file"] = source_file
        values["language"] = values["language"] or "unknown"
        values["status"] = values["status"] or "active"
        tags = values.get("tags") or []
        if not isinstance(tags, list):
            raise _invalid_metadata("metadata tags must be a list", {"tags_type": type(tags).__name__})
        values["tags"] = tuple(normalize_tag(str(tag)) for tag in tags if normalize_tag(str(tag)))

        manual_id = str(values.get("manual_id", "")).strip()
        if not manual_id:
            raise _invalid_metadata("manual_id must not be empty")
        title = str(values.get("title", "")).strip()
        product_category = str(values.get("product_category", "")).strip()
        source = str(values.get("source_file", "")).strip()
        if not title or not product_category or not source:
            raise _invalid_metadata(
                "manual metadata requires title, source_file, and product_category",
                {"manual_id": manual_id},
            )
        return cls(
            manual_id=manual_id,
            title=title,
            source_file=source,
            product_category=product_category,
            language=str(values["language"]).strip() or "unknown",
            brand=str(values.get("brand", "")).strip(),
            product_name=str(values.get("product_name", "")).strip(),
            product_model=str(values.get("product_model", "")).strip(),
            version=str(values.get("version", "")).strip(),
            tags=values["tags"],
            status=str(values["status"]).strip() or "active",
            uploaded_at=str(values.get("uploaded_at", "")).strip(),
            checksum=str(values.get("checksum", "")).strip(),
            notes=str(values.get("notes", "")).strip(),
            extra=extra,
        )

    def to_node_attrs(self) -> dict[str, Any]:
        return {
            "manual_id": self.manual_id,
            "title": self.title,
            "source_file": self.source_file,
            "product_category": self.product_category,
            "language": self.language,
            "brand": self.brand,
            "product_name": self.product_name,
            "product_model": self.product_model,
            "version": self.version,
            "tags": list(self.tags),
            "status": self.status,
            "uploaded_at": self.uploaded_at,
            "checksum": self.checksum,
            "notes": self.notes,
            **dict(self.extra),
        }


def metadata_sidecar_path(source_path: str | Path) -> Path:
    path = Path(source_path)
    return path.with_name(f"{path.stem}{MANUAL_METADATA_SUFFIX}")


def load_manual_metadata(
    source_path: str | Path,
    docs_root: str | Path,
    *,
    seen_manual_ids: set[str] | None = None,
) -> ManualMetadata:
    source = Path(source_path)
    root = Path(docs_root)
    source_file = _relative_source_file(source, root)
    sidecar = metadata_sidecar_path(source)
    if sidecar.exists():
        try:
            data = json.loads(sidecar.read_text(encoding="utf-8"))
        except json.JSONDecodeError as exc:
            raise _invalid_metadata(
                "manual metadata sidecar is not valid JSON",
                {"sidecar": str(sidecar), "error": str(exc)},
            ) from exc
        metadata = ManualMetadata.from_dict(data, source_file=source_file)
    else:
        metadata = fallback_manual_metadata(source, root)
    if seen_manual_ids is not None:
        ensure_unique_manual_id(metadata.manual_id, seen_manual_ids, source_file)
    return metadata


def fallback_manual_metadata(source_path: str | Path, docs_root: str | Path) -> ManualMetadata:
    source = Path(source_path)
    source_file = _relative_source_file(source, Path(docs_root))
    relative = Path(source_file)
    product_category = "" if relative.parent == Path(".") else relative.parts[0]
    return ManualMetadata(
        manual_id=normalize_identifier(str(relative.with_suffix(""))),
        title=source.stem,
        source_file=source_file,
        product_category=product_category or "unknown",
        language="unknown",
        tags=(),
    )


def ensure_unique_manual_id(manual_id: str, seen_manual_ids: set[str], source_file: str) -> None:
    if manual_id in seen_manual_ids:
        raise _invalid_metadata("duplicate manual_id in KB build", {"manual_id": manual_id, "source_file": source_file})
    seen_manual_ids.add(manual_id)


def normalize_tag(value: str) -> str:
    normalized = re.sub(r"[\s_]+", "-", value.strip().lower())
    normalized = re.sub(r"[^a-z0-9:-]+", "-", normalized)
    return re.sub(r"-+", "-", normalized).strip("-")


def normalize_identifier(value: str) -> str:
    normalized = value.replace("\\", "/").strip().lower()
    normalized = re.sub(r"[^a-z0-9/._-]+", "-", normalized)
    normalized = normalized.replace("/", "-").replace("_", "-").replace(".", "-")
    return re.sub(r"-+", "-", normalized).strip("-") or "manual"


def metadata_from_node(node: dict[str, Any]) -> dict[str, Any]:
    metadata = node.get("metadata")
    if isinstance(metadata, dict):
        return dict(metadata)
    return {key: node[key] for key in MANUAL_METADATA_FIELDS if key in node}


def manual_result_fields(metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "manual_id": str(metadata.get("manual_id", "")),
        "manual_title": str(metadata.get("title", "")),
        "brand": str(metadata.get("brand", "")),
        "product_category": str(metadata.get("product_category", "")),
        "product_model": str(metadata.get("product_model", "")),
        "language": str(metadata.get("language", "")),
        "version": str(metadata.get("version", "")),
        "tags": public_tags_from_metadata(metadata),
    }


def public_tags_from_metadata(metadata: dict[str, Any]) -> list[str]:
    tags = metadata.get("public_tags", metadata.get("tags", []))
    if not isinstance(tags, list):
        return []
    return [str(tag) for tag in tags]


def _relative_source_file(source_path: Path, docs_root: Path) -> str:
    try:
        return source_path.relative_to(docs_root).as_posix()
    except ValueError as exc:
        raise _invalid_metadata(
            "source file must be inside docs root",
            {"source_file": str(source_path), "docs_root": str(docs_root)},
        ) from exc


def _invalid_metadata(message: str, detail: dict[str, Any] | None = None) -> ServiceError:
    return ServiceError(ErrorCode.INVALID_INPUT, message, detail)
