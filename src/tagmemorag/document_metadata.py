from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Mapping

from .manuals import ManualMetadata, normalize_identifier, normalize_tag

AttributeValue = str | tuple[str, ...]


@dataclass(frozen=True)
class DocumentMetadata:
    doc_id: str
    title: str
    source_file: str
    domain: str = "generic"
    doc_type: str = "document"
    language: str = "unknown"
    status: str = "active"
    tags: tuple[str, ...] = ()
    attributes: Mapping[str, AttributeValue] = field(default_factory=dict)

    def to_node_attrs(self, *, include_legacy: Mapping[str, Any] | None = None) -> dict[str, Any]:
        attrs: dict[str, Any] = {
            "doc_id": self.doc_id,
            "title": self.title,
            "source_file": self.source_file,
            "domain": self.domain,
            "doc_type": self.doc_type,
            "language": self.language,
            "status": self.status,
            "tags": list(self.tags),
            "attributes": _attributes_to_jsonable(self.attributes),
        }
        if include_legacy:
            attrs.update(dict(include_legacy))
        return attrs


def document_metadata_from_manual(metadata: ManualMetadata) -> DocumentMetadata:
    manual_id = metadata.manual_id.strip()
    attributes: dict[str, AttributeValue] = {
        "manual_id": manual_id,
        "brand": metadata.brand,
        "product_name": metadata.product_name,
        "product_category": metadata.product_category,
        "product_model": metadata.product_model,
        "version": metadata.version,
        "checksum": metadata.checksum,
    }
    tags = _dedupe_tags(
        (
            *metadata.tags,
            *_identity_tags(
                doc_id=manual_id,
                manual_id=manual_id,
                brand=metadata.brand,
                product_category=metadata.product_category,
                product_model=metadata.product_model,
            ),
        )
    )
    return DocumentMetadata(
        doc_id=manual_id,
        title=metadata.title,
        source_file=metadata.source_file,
        domain="product_manual",
        doc_type="manual",
        language=metadata.language,
        status=metadata.status,
        tags=tags,
        attributes={key: value for key, value in attributes.items() if _has_value(value)},
    )


def manual_node_attrs(metadata: ManualMetadata) -> dict[str, Any]:
    doc = document_metadata_from_manual(metadata)
    legacy = metadata.to_node_attrs()
    legacy.pop("tags", None)
    legacy["public_tags"] = list(metadata.tags)
    return doc.to_node_attrs(include_legacy=legacy)


def _identity_tags(
    *,
    doc_id: str,
    manual_id: str,
    brand: str,
    product_category: str,
    product_model: str,
) -> tuple[str, ...]:
    values = [
        _namespaced_tag("doc", doc_id),
        _namespaced_tag("manual", manual_id),
        _namespaced_tag("brand", brand),
        _namespaced_tag("category", product_category),
        _namespaced_tag("model", product_model),
    ]
    return tuple(value for value in values if value)


def _namespaced_tag(namespace: str, value: str) -> str:
    if not _has_value(value):
        return ""
    normalized = normalize_identifier(str(value)) if namespace in {"doc", "manual", "model"} else normalize_tag(str(value))
    return f"{namespace}:{normalized}" if normalized else ""


def _dedupe_tags(tags: tuple[str, ...]) -> tuple[str, ...]:
    deduped: dict[str, None] = {}
    for tag in tags:
        normalized = normalize_tag(str(tag))
        if normalized:
            deduped.setdefault(normalized, None)
    return tuple(deduped)


def _attributes_to_jsonable(attributes: Mapping[str, AttributeValue]) -> dict[str, Any]:
    data: dict[str, Any] = {}
    for key, value in sorted(attributes.items()):
        if isinstance(value, tuple):
            if value:
                data[str(key)] = list(value)
        elif _has_value(value):
            data[str(key)] = str(value)
    return data


def _has_value(value: object) -> bool:
    if isinstance(value, tuple):
        return bool(value)
    return bool(str(value or "").strip())
