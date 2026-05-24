from __future__ import annotations

from dataclasses import dataclass
import re
from urllib.parse import quote
from typing import Any, Sequence

from .document_assets import AssetManifest, DocumentAsset
from .types import Result
from .visual_retrieval.base import VisualCandidate, VisualCandidateProvider, VisualQueryContext, VisualReranker

RETRIEVE_SCHEMA_VERSION = "retrieve.v1"
CONTEXT_PACK_VERSION = "context_pack.v1"
DEFAULT_TOKEN_BUDGET = 4000
SNIPPET_CHARS = 700
DEFAULT_MAX_ASSETS_PER_EVIDENCE = 3


@dataclass(frozen=True)
class VisualEvidenceResolver:
    kb_name: str
    manifest: AssetManifest | None
    max_assets_per_evidence: int = DEFAULT_MAX_ASSETS_PER_EVIDENCE
    asset_base_path: str = "/assets"


@dataclass(frozen=True)
class VisualRetrievalResolver:
    kb_name: str
    manifest: AssetManifest | None
    provider: VisualCandidateProvider | None
    reranker: VisualReranker | None
    enabled: bool = False
    max_candidates: int = 4
    min_score: float = 0.1
    trigger: str = "visual_intent"
    asset_base_path: str = "/assets"


def build_retrieve_response(
    *,
    results: Sequence[Result],
    build_id: str,
    kb_name: str,
    trace_id: str,
    search_id: str,
    retrieve_id: str,
    token_budget: int = DEFAULT_TOKEN_BUDGET,
    search_time_ms: float = 0.0,
    visual_resolver: VisualEvidenceResolver | None = None,
    visual_retrieval_resolver: VisualRetrievalResolver | None = None,
    query_text: str = "",
) -> dict[str, Any]:
    visual_intent = detect_visual_intent(query_text)
    result_list = list(results)
    evidence = [
        _evidence_from_result(
            result,
            index,
            visual_resolver=visual_resolver,
            adjacent_results=result_list,
        )
        for index, result in enumerate(result_list, 1)
    ]
    visual_summary: dict[str, Any] = {}
    visual_candidates: tuple[VisualCandidate, ...] = ()
    if visual_retrieval_resolver is not None:
        visual_candidates, visual_summary = _visual_retrieval_candidates(
            query_text=query_text,
            visual_intent=visual_intent,
            existing_evidence=evidence,
            resolver=visual_retrieval_resolver,
        )
        evidence.extend(
            _visual_evidence_from_candidate(
                candidate,
                len(evidence) + index,
                resolver=visual_retrieval_resolver,
            )
            for index, candidate in enumerate(visual_candidates, 1)
        )
    citations = [_citation_from_evidence(item) for item in evidence]
    context_pack, context_warning = _context_pack(evidence, token_budget=max(0, int(token_budget)), query_text=query_text)
    answerability = _answerability(evidence, context_pack, context_warning)
    visual_evidence = _visual_summary(evidence, visual_intent=visual_intent, manifest_present=visual_resolver is not None and visual_resolver.manifest is not None)
    if visual_summary:
        visual_evidence["retrieval"] = visual_summary
    return {
        "schema_version": RETRIEVE_SCHEMA_VERSION,
        "build_id": build_id,
        "kb_name": kb_name,
        "trace_id": trace_id,
        "search_id": search_id,
        "retrieve_id": retrieve_id,
        "results": [result.to_dict() for result in results],
        "evidence": evidence,
        "citations": citations,
        "context_pack": context_pack,
        "answerability": answerability,
        "visual_evidence": visual_evidence,
        "search_time_ms": round(float(search_time_ms), 3),
    }


def retrieve_inspect_payload(payload: dict[str, Any]) -> dict[str, Any]:
    evidence = list(payload.get("evidence") or [])
    context_items = list((payload.get("context_pack") or {}).get("items") or [])
    context_by_evidence = {
        str(ref): str(item.get("context_item_id") or "")
        for item in context_items
        for ref in item.get("evidence_refs", [])
    }
    selected: list[dict[str, Any]] = []
    for index, item in enumerate(evidence, 1):
        selected.append(
            {
                "rank": index,
                "evidence_id": str(item.get("evidence_id") or ""),
                "citation_id": str(item.get("citation_id") or ""),
                "context_item_id": context_by_evidence.get(str(item.get("evidence_id") or ""), ""),
                "doc_id": str(item.get("doc_id") or ""),
                "chunk_id": str(item.get("chunk_id") or ""),
                "score": float(item.get("score") or 0.0),
            }
        )
    context_pack = dict(payload.get("context_pack") or {})
    answerability = dict(payload.get("answerability") or {})
    inspect = {
        "schema_version": "retrieve_inspect.v1",
        "retrieve_id": str(payload.get("retrieve_id") or ""),
        "result_count": len(payload.get("results") or []),
        "evidence_count": len(evidence),
        "citation_count": len(payload.get("citations") or []),
        "context_item_count": len(context_items),
        "token_budget": int(context_pack.get("token_budget") or 0),
        "token_count_estimate": int(context_pack.get("token_count_estimate") or 0),
        "answerable": bool(answerability.get("answerable")),
        "fallback_reason": str(answerability.get("fallback_reason") or ""),
        "selected": selected,
    }
    visual = dict(payload.get("visual_evidence") or {})
    if visual:
        inspect["visual_evidence"] = {
            "intent": str(visual.get("intent") or ""),
            "attached_count": int(visual.get("attached_count") or 0),
            "evidence_with_assets": int(visual.get("evidence_with_assets") or 0),
            "omitted": dict(visual.get("omitted") or {}),
        }
    return inspect


def context_evidence_diagnostics(payload: dict[str, Any], *, query_text: str = "") -> list[dict[str, Any]]:
    """Return bounded context-selection diagnostics for a retrieve payload."""
    evidence = list(payload.get("evidence") or [])
    context_items = list((payload.get("context_pack") or {}).get("items") or [])
    context_rank_by_evidence = {
        str(ref): index
        for index, item in enumerate(context_items, 1)
        for ref in item.get("evidence_refs", [])
    }
    query_terms = _context_terms(query_text)
    diagnostics: list[dict[str, Any]] = []
    for rank, item in enumerate(evidence, 1):
        evidence_id = str(item.get("evidence_id") or "")
        text = str(item.get("text") or "")
        terms = _context_terms(text)
        coverage = len(terms.intersection(query_terms)) / max(1, len(query_terms)) if query_terms else 0.0
        diagnostics.append(
            {
                "rank": rank,
                "evidence_id": evidence_id,
                "citation_id": str(item.get("citation_id") or ""),
                "context_rank": context_rank_by_evidence.get(evidence_id),
                "selected": evidence_id in context_rank_by_evidence,
                "score": round(float(item.get("score") or 0.0), 6),
                "estimated_tokens": _estimate_tokens(text),
                "query_term_coverage": round(float(coverage), 6),
                "context_usefulness": round(float(_context_usefulness_score(text, query_terms)), 6),
                "source_file": str(item.get("source_file") or ""),
                "chunk_id": str(item.get("chunk_id") or ""),
                "section_path": [str(part) for part in item.get("section_path", [])],
            }
        )
    return diagnostics


def _evidence_from_result(
    result: Result,
    index: int,
    *,
    visual_resolver: VisualEvidenceResolver | None = None,
    adjacent_results: Sequence[Result] = (),
) -> dict[str, Any]:
    metadata = dict(result.metadata or {})
    citation_id = f"cit_{index:03d}"
    evidence_id = f"ev_{index:03d}"
    doc_id = str(metadata.get("doc_id") or result.manual_id or metadata.get("manual_id") or "")
    chunk_id = str(metadata.get("chunk_id") or "")
    section_path = _section_path(result, metadata)
    page_range = _page_range(metadata)
    assets, asset_warnings = _assets_for_result(result, metadata, doc_id=doc_id, page_range=page_range, citation_id=citation_id, visual_resolver=visual_resolver)
    return {
        "evidence_id": evidence_id,
        "citation_id": citation_id,
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "node_id": int(result.node_id),
        "source_file": result.source_file,
        "page_range": page_range,
        "section_path": section_path,
        "text": _snippet(_evidence_text(result, adjacent_results)),
        "score": float(result.score),
        "confidence": _confidence(result.score),
        "reason": _reason(result, section_path, page_range),
        "matched_chunk_ids": [chunk_id] if chunk_id else [],
        "assets": assets,
        "asset_warnings": asset_warnings,
    }


def _evidence_text(result: Result, adjacent_results: Sequence[Result]) -> str:
    text = str(result.text or "").strip()
    if not _is_sparse_pdf_heading_result(result):
        return text
    neighbor = _best_adjacent_body_result(result, adjacent_results)
    if neighbor is None:
        return text
    return (text.rstrip() + "\n" + str(neighbor.text or "").strip()).strip()


def _is_sparse_pdf_heading_result(result: Result) -> bool:
    metadata = result.metadata or {}
    if "pdf_parser_profile" not in metadata:
        return False
    if str(metadata.get("pdf_header_source") or "") != "detected":
        return False
    text = str(result.text or "").strip()
    if not text or "\n" in text:
        return False
    return text == str(result.header or "").strip() and len(text) < 100


def _best_adjacent_body_result(result: Result, adjacent_results: Sequence[Result]) -> Result | None:
    candidates = [
        candidate
        for candidate in adjacent_results
        if _can_supply_adjacent_context(result, candidate)
    ]
    if not candidates:
        return None
    return min(candidates, key=lambda candidate: abs(int(candidate.node_id) - int(result.node_id)))


def _can_supply_adjacent_context(result: Result, candidate: Result) -> bool:
    if int(candidate.node_id) == int(result.node_id):
        return False
    if abs(int(candidate.node_id) - int(result.node_id)) > 2:
        return False
    if candidate.source_file != result.source_file:
        return False
    if candidate.metadata.get("page_start") != result.metadata.get("page_start"):
        return False
    text = str(candidate.text or "").strip()
    if len(text) < 40:
        return False
    return not _is_sparse_pdf_heading_result(candidate)


def _citation_from_evidence(evidence: dict[str, Any]) -> dict[str, Any]:
    return {
        "citation_id": evidence["citation_id"],
        "evidence_id": evidence["evidence_id"],
        "doc_id": evidence["doc_id"],
        "chunk_id": evidence["chunk_id"],
        "source_file": evidence["source_file"],
        "page_range": evidence["page_range"],
        "section_path": evidence["section_path"],
    }


def _context_pack(evidence: list[dict[str, Any]], *, token_budget: int, query_text: str = "") -> tuple[dict[str, Any], str]:
    items: list[dict[str, Any]] = []
    used_tokens = 0
    warning = ""
    selected = _select_context_evidence(evidence, token_budget=token_budget, query_text=query_text)
    if not selected and evidence:
        warning = "context_budget_exhausted"
    selected_ids = {str(item.get("evidence_id") or "") for item in selected}
    merged_ids: set[str] = set()
    for index, item in enumerate(selected, 1):
        if str(item.get("evidence_id") or "") in merged_ids:
            continue
        bundle = _context_item_bundle(
            item,
            evidence=evidence,
            selected_ids=selected_ids,
            merged_ids=merged_ids,
            query_text=query_text,
            token_budget=max(0, int(token_budget)),
            remaining_tokens=max(0, int(token_budget) - used_tokens),
        )
        content = bundle["content"]
        estimated = _estimate_tokens(content)
        context_item = {
            "context_item_id": f"ctx_{index:03d}",
            "content_type": item.get("content_type", "text"),
            "content": content,
            "source": {
                "doc_id": item["doc_id"],
                "source_file": item["source_file"],
                "page_range": item["page_range"],
                "section_path": item["section_path"],
            },
            "citation_id": item["citation_id"],
            "citation_ids": bundle["citation_ids"],
            "evidence_refs": bundle["evidence_refs"],
            "asset_refs": [str(asset.get("asset_id") or "") for asset in item.get("assets", []) if str(asset.get("asset_id") or "")],
            "score": item["score"],
            "why_selected": item["reason"],
        }
        items.append(context_item)
        used_tokens += estimated
    return (
        {
            "version": CONTEXT_PACK_VERSION,
            "token_budget": int(token_budget),
            "token_count_estimate": int(used_tokens),
            "items": items,
        },
        warning,
    )


def _select_context_evidence(evidence: list[dict[str, Any]], *, token_budget: int, query_text: str = "") -> list[dict[str, Any]]:
    remaining = [
        (index, item, _context_item_estimated_tokens(item, query_text=query_text, token_budget=token_budget))
        for index, item in enumerate(evidence)
    ]
    selected: list[tuple[int, dict[str, Any], int]] = []
    used_tokens = 0
    query_terms = _context_terms(query_text)
    max_score = max((float(item.get("score") or 0.0) for item in evidence), default=0.0)
    while remaining:
        fit = [(index, item, estimated) for index, item, estimated in remaining if used_tokens + estimated <= token_budget]
        if not fit:
            break
        if not selected:
            chosen = max(
                fit,
                key=lambda candidate: (
                    _context_selection_score(candidate[1], candidate[0], query_terms=query_terms, max_score=max_score),
                    float(candidate[1].get("score") or 0.0),
                    -candidate[0],
                ),
            )
        else:
            selected_tokens = [_context_terms(str(item["text"])) for _index, item, _estimated in selected]
            chosen = max(
                fit,
                key=lambda candidate: (
                    _context_selection_score(candidate[1], candidate[0], query_terms=query_terms, max_score=max_score)
                    - _max_context_overlap(_context_terms(str(candidate[1]["text"])), selected_tokens) * 0.35,
                    float(candidate[1].get("score") or 0.0),
                    -candidate[0],
                ),
            )
        selected.append(chosen)
        used_tokens += chosen[2]
        remaining = [(index, item, estimated) for index, item, estimated in remaining if index != chosen[0]]
    return [item for _index, item, _estimated in selected]


def _context_item_bundle(
    item: dict[str, Any],
    *,
    evidence: list[dict[str, Any]],
    selected_ids: set[str],
    merged_ids: set[str],
    query_text: str,
    token_budget: int,
    remaining_tokens: int,
) -> dict[str, Any]:
    content = _context_item_content(item, query_text=query_text, token_budget=token_budget)
    evidence_refs = [str(item.get("evidence_id") or "")]
    citation_ids = [str(item.get("citation_id") or "")]
    used_tokens = _estimate_tokens(content)
    query_terms = _context_terms(query_text)
    for candidate in _merge_candidates(item, evidence=evidence, selected_ids=selected_ids, merged_ids=merged_ids, query_terms=query_terms):
        candidate_content = _context_item_content(candidate, query_text=query_text, token_budget=token_budget)
        merged_content = (content.rstrip() + "\n\n" + candidate_content.strip()).strip()
        merged_tokens = _estimate_tokens(merged_content)
        if merged_tokens > remaining_tokens:
            compacted_candidate = _compact_context_candidate_to_fit(
                candidate,
                query_text=query_text,
                max_tokens=max(1, remaining_tokens - used_tokens),
            )
            if not compacted_candidate:
                continue
            merged_content = (content.rstrip() + "\n\n" + compacted_candidate.strip()).strip()
            merged_tokens = _estimate_tokens(merged_content)
            if merged_tokens > remaining_tokens:
                continue
        content = merged_content
        used_tokens = merged_tokens
        evidence_id = str(candidate.get("evidence_id") or "")
        citation_id = str(candidate.get("citation_id") or "")
        evidence_refs.append(evidence_id)
        citation_ids.append(citation_id)
        merged_ids.add(evidence_id)
    return {
        "content": content,
        "evidence_refs": [item for item in evidence_refs if item],
        "citation_ids": [item for item in citation_ids if item],
        "estimated_tokens": used_tokens,
    }


def _compact_context_candidate_to_fit(
    item: dict[str, Any],
    *,
    query_text: str,
    max_tokens: int,
) -> str:
    if max_tokens <= 0 or item.get("content_type") == "visual_asset" or not query_text:
        return ""
    content = str(item.get("text") or "")
    compacted = _compact_context_content(content, query_text=query_text, max_tokens=max_tokens)
    if _estimate_tokens(compacted) <= max_tokens and compacted.strip() != content.strip():
        return compacted
    return ""


def _merge_candidates(
    item: dict[str, Any],
    *,
    evidence: list[dict[str, Any]],
    selected_ids: set[str],
    merged_ids: set[str],
    query_terms: set[str],
) -> list[dict[str, Any]]:
    candidates = [
        candidate
        for candidate in evidence
        if _can_merge_context_evidence(item, candidate, selected_ids=selected_ids, merged_ids=merged_ids, query_terms=query_terms)
    ]
    return sorted(
        candidates,
        key=lambda candidate: (
            _context_usefulness_score(str(candidate.get("text") or ""), query_terms),
            float(candidate.get("score") or 0.0),
            -abs(int(candidate.get("node_id") or 0) - int(item.get("node_id") or 0)),
        ),
        reverse=True,
    )[:3]


def _can_merge_context_evidence(
    item: dict[str, Any],
    candidate: dict[str, Any],
    *,
    selected_ids: set[str],
    merged_ids: set[str],
    query_terms: set[str],
) -> bool:
    evidence_id = str(candidate.get("evidence_id") or "")
    if not evidence_id or evidence_id == str(item.get("evidence_id") or ""):
        return False
    if evidence_id in merged_ids:
        return False
    if item.get("content_type", "text") != "text" or candidate.get("content_type", "text") != "text":
        return False
    if str(candidate.get("source_file") or "") != str(item.get("source_file") or ""):
        return False
    if str(candidate.get("doc_id") or "") != str(item.get("doc_id") or ""):
        return False
    if abs(int(candidate.get("node_id") or 0) - int(item.get("node_id") or 0)) > 5:
        return False
    page_range = candidate.get("page_range") or []
    item_page_range = item.get("page_range") or []
    if page_range and item_page_range and not _ranges_overlap(page_range, item_page_range):
        return False
    if not page_range and not item_page_range and candidate.get("section_path") != item.get("section_path"):
        return False
    text = str(candidate.get("text") or "")
    terms = _context_terms(text)
    coverage = len(terms.intersection(query_terms)) / max(1, len(query_terms)) if query_terms else 0.0
    return coverage >= 0.3 or _context_usefulness_score(text, query_terms) >= 0.45


def _context_item_content(item: dict[str, Any], *, query_text: str, token_budget: int) -> str:
    content = str(item.get("text") or "")
    if item.get("content_type") == "visual_asset":
        return content
    if not query_text:
        return content
    estimated = _estimate_tokens(content)
    if estimated <= _context_compaction_target(token_budget):
        return content
    return _compact_context_content(content, query_text=query_text, max_tokens=_context_compaction_target(token_budget))


def _context_item_estimated_tokens(item: dict[str, Any], *, query_text: str, token_budget: int) -> int:
    return _estimate_tokens(_context_item_content(item, query_text=query_text, token_budget=token_budget))


def _context_compaction_target(token_budget: int) -> int:
    if token_budget <= 0:
        return 1
    return max(48, min(180, int(token_budget * 0.45)))


def _compact_context_content(text: str, *, query_text: str, max_tokens: int) -> str:
    sentences = _context_sentences(text)
    if len(sentences) <= 1:
        return text
    query_terms = _context_terms(query_text)
    ranked = sorted(
        enumerate(sentences),
        key=lambda item: (
            _context_sentence_score(item[1], query_terms),
            -item[0],
        ),
        reverse=True,
    )
    best_score = _context_sentence_score(ranked[0][1], query_terms) if ranked else 0.0
    selected_indexes: list[int] = []
    for index, sentence in ranked:
        sentence_score = _context_sentence_score(sentence, query_terms)
        if selected_indexes and sentence_score < max(0.2, best_score * 0.45):
            continue
        candidate_indexes = sorted([*selected_indexes, index])
        candidate = " ".join(sentences[item] for item in candidate_indexes).strip()
        if _estimate_tokens(candidate) <= max_tokens:
            selected_indexes.append(index)
        if len(selected_indexes) >= 3:
            break
    if not selected_indexes:
        return text
    compacted = " ".join(sentences[index] for index in sorted(selected_indexes)).strip()
    return compacted or text


def _context_sentences(text: str) -> list[str]:
    normalized = re.sub(r"\s+", " ", str(text)).strip()
    if not normalized:
        return []
    pieces = re.split(r"(?<=[。.!?！？；;])\s+", normalized)
    sentences = [piece.strip() for piece in pieces if piece.strip()]
    if len(sentences) > 1:
        return sentences
    return [piece.strip() for piece in re.split(r"\s{2,}", normalized) if piece.strip()] or [normalized]


def _context_sentence_score(sentence: str, query_terms: set[str]) -> float:
    terms = _context_terms(sentence)
    coverage = len(terms.intersection(query_terms)) / max(1, len(query_terms)) if query_terms else 0.0
    score = coverage
    score += min(0.24, 0.08 * sum(1 for term in query_terms if term in terms))
    score += _context_usefulness_score(sentence, query_terms) * 0.5
    return score


def _context_terms(text: str) -> set[str]:
    return {token for token in re.findall(r"[a-z0-9\u3400-\u9fff]+", text.lower()) if len(token) >= 2}


def _context_selection_score(item: dict[str, Any], rank_index: int, *, query_terms: set[str], max_score: float) -> float:
    text = str(item.get("text") or "")
    score = _context_usefulness_score(text, query_terms)
    terms = _context_terms(text)
    coverage = len(terms.intersection(query_terms)) / max(1, len(query_terms)) if query_terms else 0.0
    if coverage >= 0.3 and max_score > 0.0:
        score += min(0.28, 0.28 * max(0.0, float(item.get("score") or 0.0)) / max_score)
    if coverage >= 0.3:
        score += min(0.04, 0.04 / max(1, rank_index))
    return score


def _context_usefulness_score(text: str, query_terms: set[str]) -> float:
    normalized = re.sub(r"\s+", " ", str(text).lower()).strip()
    if not normalized:
        return 0.0
    terms = _context_terms(normalized)
    coverage = len(terms.intersection(query_terms)) / max(1, len(query_terms)) if query_terms else 0.0
    score = min(0.4, coverage)
    definition_patterns = (
        r"\bis (?:a|an|the)\b",
        r"\bare (?:a|an|the|written|used|available)\b",
        r"\bmeans\b",
        r"\brefers to\b",
        r"\bas (?:a|an|the)\b",
        r"\bcontains?\b",
        r"\binclude?s?\b",
    )
    action_patterns = (
        r"\bmust\b",
        r"\bshould\b",
        r"\bcan\b",
        r"\bif\b",
        r"\bwhen\b",
        r"\bchoose\b",
        r"\bselect\b",
        r"\buse\b",
        r"\bopen\b",
        r"\bclick\b",
        r"請",
        r"如果",
        r"使用",
        r"選擇",
        r"清潔",
    )
    score += min(0.36, 0.12 * sum(1 for pattern in definition_patterns if re.search(pattern, normalized)))
    if coverage >= 0.35:
        score += min(0.12, 0.04 * sum(1 for pattern in action_patterns if re.search(pattern, normalized)))
    if "source: http" in normalized[:180] or "navigation" in normalized[:180]:
        score -= 0.2
    return max(0.0, score)


def _max_context_overlap(candidate_terms: set[str], selected_terms: list[set[str]]) -> float:
    if not candidate_terms or not selected_terms:
        return 0.0
    return max(
        len(candidate_terms.intersection(terms)) / max(1, len(candidate_terms.union(terms)))
        for terms in selected_terms
    )


def _ranges_overlap(left: list[int], right: list[int]) -> bool:
    left_start, left_end = min(left), max(left)
    right_start, right_end = min(right), max(right)
    return left_start <= right_end and right_start <= left_end


def _answerability(evidence: list[dict[str, Any]], context_pack: dict[str, Any], context_warning: str) -> dict[str, Any]:
    if not evidence:
        return {
            "answerable": False,
            "confidence": 0.0,
            "warnings": ["no_results"],
            "fallback_reason": "no_results",
        }
    if not context_pack.get("items"):
        warning = context_warning or "context_budget_exhausted"
        return {
            "answerable": False,
            "confidence": 0.0,
            "warnings": [warning],
            "fallback_reason": warning,
        }
    confidence = max(item["confidence"] for item in evidence)
    return {
        "answerable": True,
        "confidence": confidence,
        "warnings": [],
        "fallback_reason": "",
    }


def _section_path(result: Result, metadata: dict[str, Any]) -> list[str]:
    raw = metadata.get("section_path") or result.path
    if isinstance(raw, (list, tuple)):
        return [str(part) for part in raw if str(part)]
    text = str(raw)
    return [text] if text else []


def _page_range(metadata: dict[str, Any]) -> list[int]:
    start = _optional_int(metadata.get("page_start"))
    end = _optional_int(metadata.get("page_end"))
    if start is None and end is None:
        return []
    if start is None:
        start = end
    if end is None:
        end = start
    return [int(start), int(end)]


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _snippet(text: str) -> str:
    value = str(text).strip()
    if len(value) <= SNIPPET_CHARS:
        return value
    return value[:SNIPPET_CHARS].rstrip()


def _confidence(score: float) -> float:
    return round(max(0.0, min(1.0, float(score))), 6)


def _estimate_tokens(text: str) -> int:
    return max(1, (len(str(text)) + 3) // 4)


def _reason(result: Result, section_path: list[str], page_range: list[int]) -> str:
    if page_range:
        return "Matched text chunk with page lineage."
    if section_path:
        return "Matched text chunk with section lineage."
    if result.source_file:
        return "Matched text chunk from source file."
    return "Matched text chunk."


def _visual_retrieval_candidates(
    *,
    query_text: str,
    visual_intent: str,
    existing_evidence: list[dict[str, Any]],
    resolver: VisualRetrievalResolver,
) -> tuple[tuple[VisualCandidate, ...], dict[str, Any]]:
    summary = {
        "enabled": bool(resolver.enabled),
        "attempted": 0,
        "candidate_count": 0,
        "attached_count": 0,
        "skipped": 0,
        "omitted": {},
    }
    if not resolver.enabled:
        summary["skipped"] = 1
        summary["omitted"] = {"visual_retrieval_disabled": 1}
        return (), summary
    if resolver.trigger == "visual_intent" and visual_intent != "visual_reference":
        summary["skipped"] = 1
        summary["omitted"] = {"visual_intent_not_detected": 1}
        return (), summary
    if resolver.manifest is None:
        summary["attempted"] = 1
        summary["omitted"] = {"asset_manifest_missing": 1}
        return (), summary
    if resolver.provider is None:
        summary["attempted"] = 1
        summary["omitted"] = {"visual_provider_missing": 1}
        return (), summary
    summary["attempted"] = 1
    candidates = resolver.provider.candidates(
        VisualQueryContext(
            query_text=query_text,
            visual_intent=visual_intent,
            kb_name=resolver.kb_name,
            manifest=resolver.manifest,
            max_candidates=resolver.max_candidates,
            min_score=resolver.min_score,
        )
    )
    if resolver.reranker is not None:
        candidates = resolver.reranker.rerank(query_text, candidates)
    candidates = _dedupe_visual_candidates(candidates, existing_evidence)
    summary["candidate_count"] = len(candidates)
    summary["attached_count"] = len(candidates)
    if not candidates:
        summary["omitted"] = {"no_visual_candidates": 1}
    return candidates, summary


def _dedupe_visual_candidates(
    candidates: tuple[VisualCandidate, ...],
    existing_evidence: list[dict[str, Any]],
) -> tuple[VisualCandidate, ...]:
    existing_asset_ids = {
        str(asset.get("asset_id") or "")
        for item in existing_evidence
        for asset in item.get("assets", [])
        if str(asset.get("asset_id") or "")
    }
    if not existing_asset_ids:
        return candidates
    return tuple(candidate for candidate in candidates if candidate.asset_id not in existing_asset_ids)


def _visual_evidence_from_candidate(
    candidate: VisualCandidate,
    index: int,
    *,
    resolver: VisualRetrievalResolver,
) -> dict[str, Any]:
    citation_id = f"cit_{index:03d}"
    evidence_id = f"ev_{index:03d}"
    asset = resolver.manifest.assets.get(candidate.asset_id) if resolver.manifest is not None else None
    assets = []
    if asset is not None:
        assets = [
            _asset_descriptor(
                asset,
                kb_name=resolver.kb_name,
                citation_id=citation_id,
                asset_base_path=resolver.asset_base_path,
            )
        ]
    page_range = [candidate.page_number, candidate.page_number] if candidate.page_number is not None else []
    return {
        "evidence_id": evidence_id,
        "citation_id": citation_id,
        "chunk_id": "",
        "doc_id": candidate.doc_id,
        "node_id": -1,
        "source_file": candidate.source_file,
        "page_range": page_range,
        "section_path": [],
        "text": candidate.matched_text or f"Visual asset {candidate.asset_id}",
        "content_type": "visual_asset",
        "score": float(candidate.score),
        "confidence": _confidence(candidate.score),
        "reason": candidate.reason,
        "matched_chunk_ids": [],
        "assets": assets,
        "asset_warnings": [] if assets else ["visual_asset_missing"],
        "visual_candidate": {
            "asset_id": candidate.asset_id,
            "provider": candidate.provider,
            "provider_version": candidate.provider_version,
            "score": float(candidate.score),
            "reason": candidate.reason,
        },
    }


def detect_visual_intent(query_text: str) -> str:
    text = str(query_text or "").lower()
    if not text:
        return "text_answer"
    english_hints = ("show", "diagram", "image", "picture", "photo", "button", "where is", "layout")
    chinese_hints = ("图", "图片", "示意图", "按钮", "位置", "在哪", "长什么样", "给我看")
    if any(hint in text for hint in english_hints) or any(hint in str(query_text) for hint in chinese_hints):
        return "visual_reference"
    return "text_answer"


def _assets_for_result(
    result: Result,
    metadata: dict[str, Any],
    *,
    doc_id: str,
    page_range: list[int],
    citation_id: str,
    visual_resolver: VisualEvidenceResolver | None,
) -> tuple[list[dict[str, Any]], list[str]]:
    if visual_resolver is None:
        return [], []
    manifest = visual_resolver.manifest
    if manifest is None:
        return [], ["asset_manifest_missing"]
    candidates, warnings = _candidate_assets(result, metadata, doc_id=doc_id, page_range=page_range, manifest=manifest, kb_name=visual_resolver.kb_name)
    descriptors: list[dict[str, Any]] = []
    for asset in candidates[: max(0, int(visual_resolver.max_assets_per_evidence))]:
        descriptors.append(_asset_descriptor(asset, kb_name=visual_resolver.kb_name, citation_id=citation_id, asset_base_path=visual_resolver.asset_base_path))
    if not descriptors and "no_matching_assets" not in warnings:
        warnings.append("no_matching_assets")
    return descriptors, _dedupe_strings(warnings)


def _candidate_assets(
    result: Result,
    metadata: dict[str, Any],
    *,
    doc_id: str,
    page_range: list[int],
    manifest: AssetManifest,
    kb_name: str,
) -> tuple[list[DocumentAsset], list[str]]:
    warnings: list[str] = []
    assets_by_id = manifest.assets
    explicit_ids = _string_list(metadata.get("asset_refs"))
    explicit_assets: list[DocumentAsset] = []
    for asset_id in explicit_ids:
        asset = assets_by_id.get(asset_id)
        if asset is None:
            warnings.append("asset_ref_missing")
            continue
        if asset.kb_name != kb_name:
            warnings.append("asset_wrong_kb")
            continue
        if asset.status != "ready":
            warnings.append(f"asset_status_{asset.status}")
            continue
        explicit_assets.append(asset)
    if explicit_assets:
        return _sort_assets(explicit_assets, page_range), warnings

    inferred: list[DocumentAsset] = []
    for asset in assets_by_id.values():
        if asset.kb_name != kb_name:
            continue
        if asset.status != "ready":
            continue
        if asset.type not in {"page_snapshot", "region_crop"}:
            continue
        if doc_id and asset.doc_id == doc_id and _page_overlaps(asset.page_number, page_range):
            inferred.append(asset)
            continue
        if not doc_id and asset.source_file == result.source_file and _page_overlaps(asset.page_number, page_range):
            inferred.append(asset)
    if not inferred:
        warnings.append("no_matching_assets")
    return _sort_assets(inferred, page_range), warnings


def _asset_descriptor(asset: DocumentAsset, *, kb_name: str, citation_id: str, asset_base_path: str) -> dict[str, Any]:
    page_range = [asset.page_number, asset.page_number] if asset.page_number is not None else []
    return {
        "asset_id": asset.asset_id,
        "type": asset.type,
        "url": f"{asset_base_path.rstrip('/')}/{quote(asset.asset_id, safe='')}?kb_name={quote(kb_name, safe='')}",
        "mime_type": asset.mime_type,
        "page_number": asset.page_number,
        "bbox": list(asset.bbox) if asset.bbox is not None else None,
        "width": asset.width,
        "height": asset.height,
        "caption": asset.caption,
        "alt_text": asset.caption or _asset_alt_text(asset, citation_id),
        "source": {
            "doc_id": asset.doc_id,
            "source_file": asset.source_file,
            "page_range": page_range,
        },
    }


def _asset_alt_text(asset: DocumentAsset, citation_id: str) -> str:
    if asset.page_number is not None:
        return f"Page {asset.page_number} {asset.type.replace('_', ' ')} for citation {citation_id}"
    return f"{asset.type.replace('_', ' ')} for citation {citation_id}"


def _visual_summary(evidence: list[dict[str, Any]], *, visual_intent: str, manifest_present: bool) -> dict[str, Any]:
    omitted: dict[str, int] = {}
    attached = 0
    evidence_with_assets = 0
    for item in evidence:
        assets = list(item.get("assets") or [])
        if assets:
            evidence_with_assets += 1
            attached += len(assets)
        for warning in item.get("asset_warnings", []):
            key = str(warning)
            omitted[key] = omitted.get(key, 0) + 1
    return {
        "intent": visual_intent,
        "manifest_present": bool(manifest_present),
        "attached_count": attached,
        "evidence_with_assets": evidence_with_assets,
        "omitted": dict(sorted(omitted.items())),
    }


def _page_overlaps(page_number: int | None, page_range: list[int]) -> bool:
    if page_number is None:
        return False
    if not page_range:
        return True
    start = min(page_range)
    end = max(page_range)
    return start <= int(page_number) <= end


def _sort_assets(assets: list[DocumentAsset], page_range: list[int]) -> list[DocumentAsset]:
    target = min(page_range) if page_range else 0
    return sorted(
        assets,
        key=lambda asset: (
            abs((asset.page_number or target) - target),
            asset.type != "page_snapshot",
            asset.asset_id,
        ),
    )


def _string_list(raw: Any) -> list[str]:
    if not isinstance(raw, (list, tuple)):
        return []
    return [str(item) for item in raw if str(item)]


def _dedupe_strings(values: list[str]) -> list[str]:
    seen: set[str] = set()
    result: list[str] = []
    for value in values:
        if value not in seen:
            result.append(value)
            seen.add(value)
    return result
