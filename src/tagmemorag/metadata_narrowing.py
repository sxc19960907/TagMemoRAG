from __future__ import annotations

from dataclasses import dataclass, field
import re
from typing import Any, Iterable, Literal, Mapping

import networkx as nx

from .manuals import metadata_from_node, normalize_identifier, normalize_tag
from .wave_searcher import filter_node_ids, normalize_filters

MetadataValue = str | tuple[str, ...]
NarrowingMode = Literal["none", "hard_filter", "boost", "mixed"]

PRODUCT_CATEGORY_ALIASES: dict[str, str] = {
    "冰箱": "refrigerator",
    "冷藏": "refrigerator",
    "fridge": "refrigerator",
    "refrigerator": "refrigerator",
    "洗衣机": "washer",
    "洗衣機": "washer",
    "washer": "washer",
    "washing-machine": "washer",
    "干衣机": "dryer",
    "乾衣機": "dryer",
    "dryer": "dryer",
    "烘干机": "dryer",
    "烘乾機": "dryer",
    "烤箱": "oven",
    "oven": "oven",
    "洗碗机": "dishwasher",
    "洗碗機": "dishwasher",
    "dishwasher": "dishwasher",
}


@dataclass(frozen=True)
class MetadataValueHit:
    field: str
    value: str
    normalized: str
    doc_ids: frozenset[str]
    node_ids: frozenset[int]


@dataclass(frozen=True)
class DetectedEntity:
    type: str
    value: str
    field: str
    confidence: float
    rule: str

    def to_dict(self) -> dict[str, object]:
        return {
            "type": self.type,
            "value": self.value,
            "field": self.field,
            "confidence": round(float(self.confidence), 3),
            "rule": self.rule,
        }


@dataclass(frozen=True)
class NarrowingDecision:
    hard_filters: Mapping[str, object] = field(default_factory=dict)
    boost_filters: Mapping[str, object] = field(default_factory=dict)
    detected: tuple[DetectedEntity, ...] = ()
    mode: NarrowingMode = "none"
    before_count: int = 0
    after_count: int | None = None
    fallback_reason: str = ""

    def to_debug_dict(self, *, enabled: bool = True) -> dict[str, object]:
        return {
            "enabled": bool(enabled),
            "mode": self.mode,
            "detected": [item.to_dict() for item in self.detected],
            "hard_filters": dict(self.hard_filters),
            "boost_filters": dict(self.boost_filters),
            "before_count": int(self.before_count),
            "after_count": self.after_count,
            "fallback_reason": self.fallback_reason,
        }


@dataclass
class MetadataIndex:
    by_field_value: dict[tuple[str, str], MetadataValueHit] = field(default_factory=dict)
    aliases: dict[str, list[tuple[str, str]]] = field(default_factory=dict)
    total_node_count: int = 0

    @classmethod
    def from_graph(cls, graph: nx.Graph) -> "MetadataIndex":
        buckets: dict[tuple[str, str], dict[str, Any]] = {}
        for node_id, node in graph.nodes(data=True):
            metadata = metadata_from_node(node)
            for field_name, raw_value in _iter_index_values(metadata):
                normalized = _normalize_for_field(field_name, raw_value)
                if not normalized:
                    continue
                key = (field_name, normalized)
                bucket = buckets.setdefault(
                    key,
                    {
                        "field": field_name,
                        "value": str(raw_value),
                        "normalized": normalized,
                        "doc_ids": set(),
                        "node_ids": set(),
                    },
                )
                doc_id = _doc_id(metadata)
                if doc_id:
                    bucket["doc_ids"].add(doc_id)
                bucket["node_ids"].add(int(node_id))
        hits = {
            key: MetadataValueHit(
                field=str(bucket["field"]),
                value=str(bucket["value"]),
                normalized=str(bucket["normalized"]),
                doc_ids=frozenset(str(item) for item in bucket["doc_ids"]),
                node_ids=frozenset(int(item) for item in bucket["node_ids"]),
            )
            for key, bucket in buckets.items()
        }
        index = cls(by_field_value=hits, total_node_count=graph.number_of_nodes())
        index.aliases = _build_aliases(hits)
        return index

    def lookup(self, field: str, value: str) -> MetadataValueHit | None:
        return self.by_field_value.get((field, _normalize_for_field(field, value)))

    def hits_for_alias(self, value: str) -> list[MetadataValueHit]:
        normalized = _normalize_text(value)
        return [
            hit
            for key in self.aliases.get(normalized, [])
            if (hit := self.by_field_value.get(key)) is not None
        ]

    def values_for_field(self, field: str) -> list[MetadataValueHit]:
        return sorted(
            (hit for (field_name, _), hit in self.by_field_value.items() if field_name == field),
            key=lambda hit: hit.normalized,
        )


def infer_metadata_narrowing(
    *,
    query_text: str,
    graph: nx.Graph,
    explicit_filters: Mapping[str, Any] | None = None,
    enabled: bool = True,
    category_policy: str = "hard_filter_product_manual",
    brand_policy: str = "boost_if_not_unique",
    min_candidates: int = 1,
) -> NarrowingDecision:
    before_count = graph.number_of_nodes()
    if not enabled or not query_text.strip() or before_count == 0:
        return NarrowingDecision(before_count=before_count)

    explicit = normalize_filters(explicit_filters or {})
    index = MetadataIndex.from_graph(graph)
    detected: list[DetectedEntity] = []
    hard_filters: dict[str, object] = {}
    boost_filters: dict[str, object] = {}

    model_hit = _detect_model(query_text, index)
    if model_hit is not None:
        detected.append(
            DetectedEntity(
                type="product_model",
                value=model_hit.value,
                field="product_model",
                confidence=1.0,
                rule="exact_model",
            )
        )
        hard_filters["product_model"] = model_hit.value

    brand_hit = _detect_field_value(query_text, index, "brand")
    if brand_hit is not None:
        detected.append(
            DetectedEntity(
                type="brand",
                value=brand_hit.value,
                field="brand",
                confidence=0.8,
                rule="metadata_alias",
            )
        )
        if brand_policy == "hard_filter" or (brand_policy == "boost_if_not_unique" and len(index.values_for_field("brand")) == 1):
            hard_filters.setdefault("brand", brand_hit.value)
        else:
            boost_filters["brand"] = brand_hit.value

    category_hit = _detect_category(query_text, index)
    if category_hit is not None:
        detected.append(
            DetectedEntity(
                type="product_category",
                value=category_hit.value,
                field="product_category",
                confidence=0.85,
                rule="category_alias",
            )
        )
        if category_policy == "hard_filter_product_manual":
            hard_filters.setdefault("product_category", category_hit.value)
        elif category_policy == "hard_filter":
            hard_filters.setdefault("product_category", category_hit.value)
        else:
            boost_filters["product_category"] = category_hit.value

    if not detected:
        return NarrowingDecision(before_count=before_count)

    conflict = _conflicting_keys(explicit, hard_filters)
    if conflict:
        return NarrowingDecision(
            boost_filters=boost_filters,
            detected=tuple(detected),
            mode="boost" if boost_filters else "none",
            before_count=before_count,
            fallback_reason=f"conflicts_with_explicit_filter:{','.join(conflict)}",
        )

    merged_filters = {**explicit, **hard_filters}
    after_count: int | None = None
    if hard_filters:
        after_count = len(filter_node_ids(graph, merged_filters))
        if after_count < int(min_candidates):
            return NarrowingDecision(
                boost_filters=boost_filters,
                detected=tuple(detected),
                mode="boost" if boost_filters else "none",
                before_count=before_count,
                after_count=after_count,
                fallback_reason="empty_candidate_fallback",
            )

    if hard_filters and boost_filters:
        mode: NarrowingMode = "mixed"
    elif hard_filters:
        mode = "hard_filter"
    elif boost_filters:
        mode = "boost"
    else:
        mode = "none"
    return NarrowingDecision(
        hard_filters=hard_filters,
        boost_filters=boost_filters,
        detected=tuple(detected),
        mode=mode,
        before_count=before_count,
        after_count=after_count,
    )


def merge_inferred_filters(explicit_filters: Mapping[str, Any] | None, decision: NarrowingDecision) -> dict[str, object]:
    explicit = dict(explicit_filters or {})
    if decision.fallback_reason:
        return explicit
    merged = {**explicit}
    for key, value in decision.hard_filters.items():
        if value is not None and str(value).strip():
            merged[key] = value
    return merged


def _iter_index_values(metadata: Mapping[str, Any]) -> Iterable[tuple[str, str]]:
    scalar_fields = ("doc_id", "domain", "doc_type", "manual_id", "brand", "product_category", "product_model", "language")
    for field_name in scalar_fields:
        value = metadata.get(field_name)
        if _has_value(value):
            yield field_name, str(value)
    attrs = metadata.get("attributes")
    if isinstance(attrs, Mapping):
        for key, value in attrs.items():
            field_name = str(key)
            if isinstance(value, list):
                for item in value:
                    if _has_value(item):
                        yield field_name, str(item)
                        yield f"attributes.{field_name}", str(item)
            elif _has_value(value):
                yield field_name, str(value)
                yield f"attributes.{field_name}", str(value)
    tags = metadata.get("tags")
    if isinstance(tags, list):
        for tag in tags:
            if _has_value(tag):
                yield "tags", str(tag)


def _doc_id(metadata: Mapping[str, Any]) -> str:
    return str(metadata.get("doc_id") or metadata.get("manual_id") or "").strip()


def _build_aliases(hits: Mapping[tuple[str, str], MetadataValueHit]) -> dict[str, list[tuple[str, str]]]:
    aliases: dict[str, list[tuple[str, str]]] = {}
    for key, hit in hits.items():
        aliases.setdefault(_normalize_text(hit.value), []).append(key)
        if hit.field == "product_category":
            aliases.setdefault(_normalize_text(hit.normalized), []).append(key)
            for alias, category in PRODUCT_CATEGORY_ALIASES.items():
                if _normalize_text(category) == _normalize_text(hit.normalized):
                    aliases.setdefault(_normalize_text(alias), []).append(key)
    return {alias: sorted(set(keys)) for alias, keys in aliases.items()}


def _detect_model(query_text: str, index: MetadataIndex) -> MetadataValueHit | None:
    normalized_query_tokens = {_normalize_identifier_token(token) for token in _query_tokens(query_text)}
    normalized_query_tokens.discard("")
    for hit in index.values_for_field("product_model"):
        normalized_model = _normalize_identifier_token(hit.value)
        if normalized_model and normalized_model in normalized_query_tokens:
            return hit
    return None


def _detect_field_value(query_text: str, index: MetadataIndex, field: str) -> MetadataValueHit | None:
    normalized_query = _normalize_text(query_text)
    for hit in index.values_for_field(field):
        value = _normalize_text(hit.value)
        if value and _contains_normalized_term(normalized_query, value):
            return hit
    return None


def _detect_category(query_text: str, index: MetadataIndex) -> MetadataValueHit | None:
    normalized_query = _normalize_text(query_text)
    for alias, category in PRODUCT_CATEGORY_ALIASES.items():
        if _contains_normalized_term(normalized_query, _normalize_text(alias)):
            hit = index.lookup("product_category", category)
            if hit is not None:
                return hit
    return _detect_field_value(query_text, index, "product_category")


def _conflicting_keys(explicit: Mapping[str, Any], inferred: Mapping[str, object]) -> list[str]:
    conflicts: list[str] = []
    for key, inferred_value in inferred.items():
        explicit_value = explicit.get(key)
        if explicit_value is None or not str(explicit_value).strip():
            continue
        if _normalize_for_field(key, explicit_value) != _normalize_for_field(key, inferred_value):
            conflicts.append(key)
    return conflicts


def _query_tokens(text: str) -> list[str]:
    return re.findall(r"[A-Za-z0-9][A-Za-z0-9._-]*", text)


def _normalize_identifier_token(value: object) -> str:
    return re.sub(r"[^a-z0-9]+", "", str(value).lower())


def _normalize_for_field(field: str, value: object) -> str:
    if field in {"tags"}:
        return normalize_tag(str(value))
    if field in {"doc_id", "manual_id", "product_model"} or field.startswith("attributes."):
        return normalize_identifier(str(value))
    return _normalize_text(str(value))


def _normalize_text(value: object) -> str:
    text = str(value or "").strip().lower()
    text = re.sub(r"[\s_]+", "-", text)
    text = re.sub(r"-+", "-", text)
    return text.strip("-")


def _contains_normalized_term(normalized_query: str, normalized_term: str) -> bool:
    if not normalized_term:
        return False
    if re.search(r"[\u4e00-\u9fff]", normalized_term):
        return normalized_term.replace("-", "") in normalized_query.replace("-", "")
    return normalized_term in normalized_query


def _has_value(value: object) -> bool:
    return bool(str(value or "").strip())
