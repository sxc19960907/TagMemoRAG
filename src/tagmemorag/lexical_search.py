from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Any, Mapping, Sequence

import networkx as nx

from .manuals import metadata_from_node

_ALNUM_RE = re.compile(r"[a-z0-9]+(?:[-_][a-z0-9]+)*", re.IGNORECASE)
_CJK_RE = re.compile(r"[\u3400-\u9fff]+")
_CODE_RE = re.compile(r"^[a-z]{1,4}[- ]?\d{1,5}[a-z0-9]*$", re.IGNORECASE)
_SPACED_CODE_RE = re.compile(r"\b[a-z]{1,4}\s+\d{1,5}[a-z0-9]*\b", re.IGNORECASE)
_STOP_WORDS = {"a", "an", "and", "for", "if", "in", "is", "of", "on", "or", "the", "to", "with"}


@dataclass(frozen=True)
class LexicalMatch:
    node_id: int
    score: float
    mode: str


def lexical_search(
    graph: nx.Graph,
    query: str,
    *,
    eligible_node_ids: set[int] | None = None,
    candidate_k: int = 32,
    min_token_chars: int = 2,
    boost: float = 0.05,
    exact_code_boost: float = 0.15,
    model_boost: float = 0.12,
) -> list[LexicalMatch]:
    tokens = extract_lexical_tokens(query, min_token_chars=min_token_chars)
    if not tokens or candidate_k <= 0:
        return []
    eligible = set(graph.nodes) if eligible_node_ids is None else set(eligible_node_ids)
    if not eligible:
        return []

    matches: list[LexicalMatch] = []
    cap = max(float(boost), float(exact_code_boost), float(model_boost))
    for node_id in sorted(eligible):
        fields = _node_search_fields(graph.nodes[node_id])
        score, mode = _score_fields(
            fields,
            tokens,
            boost=float(boost),
            exact_code_boost=float(exact_code_boost),
            model_boost=float(model_boost),
            cap=cap,
        )
        if score > 0.0:
            matches.append(LexicalMatch(node_id=int(node_id), score=score, mode=mode))
    matches.sort(key=lambda match: (-match.score, match.node_id))
    return matches[:candidate_k]


def lexical_score_map(matches: Sequence[LexicalMatch]) -> dict[int, float]:
    return {match.node_id: match.score for match in matches}


def extract_lexical_tokens(query: str, *, min_token_chars: int = 2) -> dict[str, set[str]]:
    normalized = query.strip().lower()
    tokens = {"exact_code": set(), "model": set(), "ordinary": set(), "cjk": set()}
    if not normalized:
        return tokens

    for raw in _SPACED_CODE_RE.findall(normalized):
        compact = _compact_token(raw)
        tokens["exact_code"].update({raw.strip(), compact})

    for raw in _ALNUM_RE.findall(normalized):
        token = raw.strip("-_")
        if not token:
            continue
        compact = _compact_token(token)
        variants = {token, compact}
        if token.isdigit():
            continue
        if len(compact) >= 4 and any(ch.isalpha() for ch in compact) and any(ch.isdigit() for ch in compact):
            tokens["model"].update(variants)
        elif _CODE_RE.match(token) or _CODE_RE.match(compact):
            tokens["exact_code"].update(variants)
        elif len(token) >= min_token_chars and token not in _STOP_WORDS:
            tokens["ordinary"].add(token)

    for raw in _CJK_RE.findall(normalized):
        if len(raw) >= min_token_chars:
            tokens["cjk"].add(raw)
    return tokens


def _node_search_fields(node: Mapping[str, Any]) -> list[tuple[str, float]]:
    metadata = metadata_from_node(dict(node))
    path = node.get("path", [])
    if not isinstance(path, list):
        path = []
    high = " ".join(
        [
            str(node.get("header", "")),
            " ".join(str(part) for part in path if part),
            str(node.get("source_file", "")),
            str(metadata.get("manual_id", "")),
            str(metadata.get("product_model", "")),
        ]
    )
    tags = metadata.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    medium = " ".join(
        [
            str(metadata.get("brand", "")),
            str(metadata.get("product_category", "")),
            str(metadata.get("product_name", "")),
            str(metadata.get("title", "")),
            " ".join(str(tag) for tag in tags),
        ]
    )
    return [(high, 1.0), (medium, 0.85), (str(node.get("text", "")), 0.75)]


def _score_fields(
    fields: Sequence[tuple[str, float]],
    tokens: Mapping[str, set[str]],
    *,
    boost: float,
    exact_code_boost: float,
    model_boost: float,
    cap: float,
) -> tuple[float, str]:
    score = 0.0
    best_mode = ""
    for text, weight in fields:
        normalized = text.lower()
        compact = _compact_token(normalized)
        for token in tokens["exact_code"]:
            if _contains_token_variant(normalized, compact, token):
                score += exact_code_boost * weight
                best_mode = _max_mode(best_mode, "exact_code")
                break
        for token in tokens["model"]:
            if _contains_token_variant(normalized, compact, token):
                score += model_boost * weight
                best_mode = _max_mode(best_mode, "model")
                break
        text_hits = sum(1 for token in tokens["ordinary"] if token in normalized)
        text_hits += sum(1 for token in tokens["cjk"] if token in normalized)
        if text_hits:
            score += boost * weight * min(2, text_hits)
            best_mode = _max_mode(best_mode, "ordinary")
    if score <= 0.0:
        return 0.0, ""
    return min(score, cap), best_mode or "ordinary"


def _contains_token_variant(normalized: str, compact: str, token: str) -> bool:
    return token in normalized or _compact_token(token) in compact


def _compact_token(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", value.lower())


def _max_mode(current: str, candidate: str) -> str:
    priority = {"": 0, "ordinary": 1, "model": 2, "exact_code": 3}
    return candidate if priority[candidate] > priority[current] else current
