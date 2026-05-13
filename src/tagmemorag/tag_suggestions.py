from __future__ import annotations

from collections import Counter
from dataclasses import dataclass, field
from pathlib import Path
import re
from typing import Any, Iterable, Sequence

from .manual_library import ManualLibraryRecord
from .manuals import MANUAL_METADATA_FIELDS, normalize_tag
from .tag_governance import TagPolicy, resolve_tag
from .types import GraphState

DEFAULT_LIMIT = 8
MAX_TEXT_SAMPLE_CHARS = 4000

_SOURCE_WEIGHTS = {
    "existing_tags": 0.6,
    "source_file": 0.25,
    "title": 0.25,
    "product_category": 0.2,
    "brand": 0.15,
    "product_name": 0.15,
    "product_model": 0.15,
    "notes": 0.1,
    "text_sample": 0.1,
    "graph_facets": 0.1,
}

_STOP_WORDS = {
    "a",
    "an",
    "and",
    "by",
    "for",
    "from",
    "guide",
    "manual",
    "of",
    "on",
    "or",
    "pdf",
    "the",
    "to",
    "txt",
    "use",
    "user",
    "with",
}


@dataclass(frozen=True)
class TagSuggestion:
    tag: str
    label: str
    score: float
    sources: tuple[str, ...]
    reason: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "tag": self.tag,
            "label": self.label,
            "score": self.score,
            "sources": list(self.sources),
            "reason": self.reason,
        }


@dataclass
class _Candidate:
    tag: str
    sources: set[str] = field(default_factory=set)
    score: float = 0.0
    existing_count: int = 0


def suggest_tags(
    metadata: dict[str, Any],
    *,
    records: Sequence[ManualLibraryRecord] = (),
    graph_state: GraphState | None = None,
    text_sample: str = "",
    limit: int = DEFAULT_LIMIT,
    tag_policy: TagPolicy | None = None,
) -> tuple[list[TagSuggestion], list[str]]:
    existing_tags = _collect_existing_tags(records, graph_state, tag_policy=tag_policy)
    draft_tags = {
        tag
        for raw in _as_list(metadata.get("tags"))
        if (tag := normalize_tag(str(raw)))
    }
    candidates: dict[str, _Candidate] = {}
    draft_tokens: set[str] = set()

    fields = {
        "source_file": str(metadata.get("source_file") or ""),
        "title": str(metadata.get("title") or ""),
        "product_category": str(metadata.get("product_category") or ""),
        "brand": str(metadata.get("brand") or ""),
        "product_name": str(metadata.get("product_name") or ""),
        "product_model": str(metadata.get("product_model") or ""),
        "notes": str(metadata.get("notes") or ""),
        "text_sample": str(text_sample or "")[:MAX_TEXT_SAMPLE_CHARS],
    }
    for source, value in fields.items():
        source_tags = _source_candidates(source, value)
        draft_tokens.update(_tokens(value))
        for tag in source_tags:
            _add_candidate(candidates, tag, source, tag_policy=tag_policy)

    if graph_state is not None:
        for tag in _graph_facet_tags(graph_state):
            if tag in draft_tokens:
                _add_candidate(candidates, tag, "graph_facets", tag_policy=tag_policy)

    for tag, count in existing_tags.items():
        if tag in draft_tokens or _token_overlap(tag, draft_tokens) >= 0.67:
            candidate = _add_candidate(candidates, tag, "existing_tags")
            candidate.existing_count = count

    if tag_policy is not None:
        for raw_tag in draft_tags:
            resolution = resolve_tag(raw_tag, tag_policy)
            if resolution.state == "synonym" and resolution.canonical_tag not in draft_tags:
                _add_candidate(candidates, resolution.canonical_tag, "tag_policy")

    suggestions: list[TagSuggestion] = []
    for candidate in candidates.values():
        if candidate.tag in draft_tags or not _useful_tag(candidate.tag):
            continue
        candidate.score += sum(_SOURCE_WEIGHTS.get(source, 0.05) for source in candidate.sources)
        if len(candidate.sources) > 1:
            candidate.score += 0.05 * (len(candidate.sources) - 1)
        if candidate.existing_count:
            candidate.score += min(0.12, 0.02 * candidate.existing_count)
        suggestions.append(
            TagSuggestion(
                tag=candidate.tag,
                label=candidate.tag,
                score=round(min(candidate.score, 0.99), 3),
                sources=tuple(sorted(candidate.sources)),
                reason=_reason(candidate.sources, candidate.existing_count),
            )
        )

    suggestions.sort(key=lambda item: (-item.score, item.tag))
    return suggestions[: max(0, int(limit))], sorted(existing_tags)


def _add_candidate(
    candidates: dict[str, _Candidate],
    raw_tag: str,
    source: str,
    *,
    tag_policy: TagPolicy | None = None,
) -> _Candidate:
    tag = _canonical_candidate_tag(raw_tag, tag_policy)
    if not tag:
        return _Candidate(tag="")
    candidate = candidates.setdefault(tag, _Candidate(tag=tag))
    candidate.sources.add(source)
    return candidate


def _source_candidates(source: str, value: str) -> set[str]:
    if not value:
        return set()
    if source == "source_file":
        value = " ".join(Path(part).stem for part in str(value).replace("\\", "/").split("/") if part)
    tokens = _token_list(value)
    candidates = {token for token in tokens if _useful_tag(token)}
    words = [token for token in tokens if _useful_tag(token) or _looks_model_token(token)]
    for first, second in zip(words, words[1:]):
        phrase = normalize_tag(f"{first}-{second}")
        if _useful_phrase(phrase):
            candidates.add(phrase)
    return candidates


def _tokens(value: str) -> set[str]:
    return set(_token_list(value))


def _token_list(value: str) -> list[str]:
    normalized = normalize_tag(value)
    return [part for part in normalized.split("-") if part]


def _collect_existing_tags(
    records: Sequence[ManualLibraryRecord],
    graph_state: GraphState | None,
    *,
    tag_policy: TagPolicy | None = None,
) -> Counter[str]:
    tags: Counter[str] = Counter()
    for record in records:
        for tag in record.metadata.tags:
            if normalized := _canonical_candidate_tag(tag, tag_policy):
                tags[normalized] += 1
    if graph_state is not None:
        for tag in _graph_facet_tags(graph_state):
            if normalized := _canonical_candidate_tag(tag, tag_policy):
                tags[normalized] += 1
    return tags


def _canonical_candidate_tag(raw_tag: str, tag_policy: TagPolicy | None) -> str:
    tag = normalize_tag(raw_tag)
    if not tag or tag_policy is None:
        return tag
    resolution = resolve_tag(tag, tag_policy)
    if resolution.state == "deprecated":
        return ""
    return resolution.canonical_tag or tag


def _graph_facet_tags(graph_state: GraphState) -> set[str]:
    tags: set[str] = set()
    for _, node in graph_state.graph.nodes(data=True):
        metadata = node.get("metadata") if isinstance(node.get("metadata"), dict) else node
        raw_tags = metadata.get("tags", [])
        if isinstance(raw_tags, list):
            tags.update(normalize_tag(str(tag)) for tag in raw_tags if normalize_tag(str(tag)))
        for field in ("brand", "product_category", "product_model", "language"):
            if normalized := normalize_tag(str(metadata.get(field, ""))):
                tags.add(normalized)
    return tags


def _as_list(value: object) -> list[object]:
    return value if isinstance(value, list) else []


def _token_overlap(tag: str, draft_tokens: set[str]) -> float:
    tag_tokens = set(tag.split("-"))
    if not tag_tokens:
        return 0.0
    return len(tag_tokens & draft_tokens) / len(tag_tokens)


def _useful_phrase(tag: str) -> bool:
    parts = tag.split("-")
    if len(parts) < 2:
        return False
    return any(part not in _STOP_WORDS and not _version_only(part) for part in parts)


def _useful_tag(tag: str) -> bool:
    if not tag or tag in _STOP_WORDS:
        return False
    if len(tag) < 3 and not _looks_model_token(tag):
        return False
    if _version_only(tag):
        return False
    return True


def _version_only(tag: str) -> bool:
    return bool(re.fullmatch(r"v?\d+(?:-\d+)*", tag))


def _looks_model_token(tag: str) -> bool:
    return bool(re.search(r"[a-z]", tag) and re.search(r"\d", tag))


def _reason(sources: Iterable[str], existing_count: int) -> str:
    source_set = set(sources)
    parts: list[str] = []
    if "existing_tags" in source_set:
        parts.append("Matches tags already used in this KB")
    if "source_file" in source_set or "title" in source_set:
        parts.append("matches the title or source path")
    metadata_sources = source_set & set(MANUAL_METADATA_FIELDS)
    if metadata_sources - {"title", "source_file", "tags"}:
        parts.append("matches draft metadata")
    if "text_sample" in source_set:
        parts.append("matches the text sample")
    if "graph_facets" in source_set:
        parts.append("matches loaded KB facets")
    if "tag_policy" in source_set:
        parts.append("matches the tag governance policy")
    if not parts:
        parts.append("Matches the draft manual")
    reason = " and ".join(parts)
    if existing_count > 1:
        reason += f"; used by {existing_count} library records"
    return reason + "."
