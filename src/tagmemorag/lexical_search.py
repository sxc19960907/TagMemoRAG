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
_CJK_STOP_TERMS = {
    "洗衣",
    "衣機",
    "洗衣機",
    "洗衣机",
    "烘乾",
    "烘干",
    "乾衣",
    "干衣",
    "烤箱",
    "冰箱",
    "怎麼",
    "怎么",
    "哪裡",
    "哪里",
    "如何",
    "什麼",
    "什么",
}


@dataclass(frozen=True)
class LexicalMatch:
    node_id: int
    score: float
    mode: str


@dataclass(frozen=True)
class _SearchField:
    text: str
    weight: float
    allow_term_hits: bool = True
    allow_identity_hits: bool = True
    allow_proximity_hits: bool = False
    allow_compact_evidence_hits: bool = False


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
    ordered_terms = _ordered_ordinary_terms(query, min_token_chars=min_token_chars)
    if not tokens or candidate_k <= 0:
        return []
    eligible = set(graph.nodes) if eligible_node_ids is None else set(eligible_node_ids)
    if not eligible:
        return []

    matches: list[LexicalMatch] = []
    cap = max(float(boost) * 8.0, float(exact_code_boost) + float(model_boost) + float(boost))
    for node_id in sorted(eligible):
        fields = _node_search_fields(graph.nodes[node_id])
        score, mode = _score_fields(
            fields,
            tokens,
            boost=float(boost),
            exact_code_boost=float(exact_code_boost),
            model_boost=float(model_boost),
            ordered_terms=ordered_terms,
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
            if raw not in _CJK_STOP_TERMS:
                tokens["cjk"].add(raw)
            tokens["cjk"].update(_cjk_ngrams(raw, min_token_chars=min_token_chars))
    return tokens


def _cjk_ngrams(value: str, *, min_token_chars: int) -> set[str]:
    grams: set[str] = set()
    for size in (2, 3):
        if size < min_token_chars:
            continue
        if len(value) < size:
            continue
        grams.update(
            gram
            for index in range(0, len(value) - size + 1)
            if (gram := value[index : index + size]) not in _CJK_STOP_TERMS
        )
    return grams


def _node_search_fields(node: Mapping[str, Any]) -> list[_SearchField]:
    metadata = metadata_from_node(dict(node))
    path = node.get("path", [])
    if not isinstance(path, list):
        path = []
    heading = " ".join(
        [
            str(node.get("header", "")),
            " ".join(str(part) for part in path if part),
        ]
    )
    tags = metadata.get("tags", [])
    if not isinstance(tags, list):
        tags = []
    identity = " ".join(
        [
            str(node.get("source_file", "")),
            str(metadata.get("manual_id", "")),
            str(metadata.get("product_model", "")),
            str(metadata.get("brand", "")),
            str(metadata.get("product_category", "")),
            str(metadata.get("product_name", "")),
            str(metadata.get("title", "")),
            " ".join(str(tag) for tag in tags),
        ]
    )
    body = str(node.get("text", ""))
    is_web_document = _is_web_document(node, metadata)
    fields = [
        _SearchField(heading, 1.0, allow_term_hits=True, allow_identity_hits=True),
        _SearchField(
            body,
            0.9,
            allow_term_hits=True,
            allow_identity_hits=False,
            allow_proximity_hits=True,
            allow_compact_evidence_hits=is_web_document,
        ),
        _SearchField(identity, 0.85, allow_term_hits=False, allow_identity_hits=True),
    ]
    return fields


def _score_fields(
    fields: Sequence[_SearchField],
    tokens: Mapping[str, set[str]],
    *,
    boost: float,
    exact_code_boost: float,
    model_boost: float,
    ordered_terms: Sequence[str] = (),
    cap: float,
) -> tuple[float, str]:
    score = 0.0
    best_mode = ""
    for field in fields:
        normalized = field.text.lower()
        compact = _compact_token(normalized)
        if field.allow_identity_hits:
            for token in tokens["exact_code"]:
                if _contains_token_variant(normalized, compact, token):
                    score += exact_code_boost * field.weight
                    best_mode = _max_mode(best_mode, "exact_code")
                    break
            for token in tokens["model"]:
                if _contains_token_variant(normalized, compact, token):
                    score += model_boost * field.weight
                    best_mode = _max_mode(best_mode, "model")
                    break
        if field.allow_term_hits:
            text_hits = sum(1 for token in tokens["ordinary"] if token in normalized)
            text_hits += sum(1 for token in tokens["cjk"] if token in normalized)
            if text_hits:
                score += boost * field.weight * min(4, text_hits)
                best_mode = _max_mode(best_mode, "ordinary")
            if field.allow_proximity_hits:
                proximity_hits = _proximity_hits(normalized, ordered_terms)
                if proximity_hits:
                    score += boost * field.weight * 0.5 * min(2, proximity_hits)
                    best_mode = _max_mode(best_mode, "ordinary")
                if field.allow_compact_evidence_hits:
                    compact_hits = _compact_window_hits(normalized, tokens["ordinary"])
                    if compact_hits:
                        score += boost * field.weight * 0.35 * min(2, compact_hits)
                        best_mode = _max_mode(best_mode, "ordinary")
    if score <= 0.0:
        return 0.0, ""
    return min(score, cap), best_mode or "ordinary"


def _ordered_ordinary_terms(query: str, *, min_token_chars: int) -> tuple[str, ...]:
    terms: list[str] = []
    for raw in _ALNUM_RE.findall(query.lower()):
        token = raw.strip("-_")
        if not token or token.isdigit():
            continue
        compact = _compact_token(token)
        if len(compact) >= 4 and any(ch.isalpha() for ch in compact) and any(ch.isdigit() for ch in compact):
            continue
        if _CODE_RE.match(token) or _CODE_RE.match(compact):
            continue
        if len(token) >= min_token_chars and token not in _STOP_WORDS:
            terms.append(token)
    return tuple(terms)


def _proximity_hits(normalized: str, ordered_terms: Sequence[str]) -> int:
    if len(ordered_terms) < 2:
        return 0
    hits = 0
    for left, right in zip(ordered_terms, ordered_terms[1:]):
        if _terms_within_window(normalized, left, right):
            hits += 1
    return hits


def _terms_within_window(text: str, left: str, right: str, *, max_gap_words: int = 2) -> bool:
    pattern = re.compile(
        rf"\b{re.escape(left)}\b(?:\W+\w+){{0,{max_gap_words}}}\W+\b{re.escape(right)}\b",
        re.IGNORECASE,
    )
    return bool(pattern.search(text))


def _compact_window_hits(text: str, terms: set[str], *, window_words: int = 14) -> int:
    if len(terms) < 3:
        return 0
    words = _ALNUM_RE.findall(text.lower())
    if len(words) < 24:
        return 0
    best = 0
    for index in range(len(words)):
        window = words[index : index + window_words]
        if len(window) < 3:
            break
        best = max(best, len({term for term in terms if term in window}))
        if best >= 5:
            break
    return max(0, best - 2)


def _is_web_document(node: Mapping[str, Any], metadata: Mapping[str, Any]) -> bool:
    source_file = str(node.get("source_file", ""))
    return source_file.startswith("public_web/")


def _contains_token_variant(normalized: str, compact: str, token: str) -> bool:
    return token in normalized or _compact_token(token) in compact


def _compact_token(value: str) -> str:
    return re.sub(r"[^a-z0-9\u3400-\u9fff]+", "", value.lower())


def _max_mode(current: str, candidate: str) -> str:
    priority = {"": 0, "ordinary": 1, "model": 2, "exact_code": 3}
    return candidate if priority[candidate] > priority[current] else current
