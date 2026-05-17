from __future__ import annotations

from typing import Any, Sequence

from .types import Result

RETRIEVE_SCHEMA_VERSION = "retrieve.v1"
CONTEXT_PACK_VERSION = "context_pack.v1"
DEFAULT_TOKEN_BUDGET = 4000
SNIPPET_CHARS = 700


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
) -> dict[str, Any]:
    evidence = [_evidence_from_result(result, index) for index, result in enumerate(results, 1)]
    citations = [_citation_from_evidence(item) for item in evidence]
    context_pack, context_warning = _context_pack(evidence, token_budget=max(0, int(token_budget)))
    answerability = _answerability(evidence, context_pack, context_warning)
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
    return {
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


def _evidence_from_result(result: Result, index: int) -> dict[str, Any]:
    metadata = dict(result.metadata or {})
    citation_id = f"cit_{index:03d}"
    evidence_id = f"ev_{index:03d}"
    doc_id = str(metadata.get("doc_id") or result.manual_id or metadata.get("manual_id") or "")
    chunk_id = str(metadata.get("chunk_id") or "")
    section_path = _section_path(result, metadata)
    page_range = _page_range(metadata)
    return {
        "evidence_id": evidence_id,
        "citation_id": citation_id,
        "chunk_id": chunk_id,
        "doc_id": doc_id,
        "node_id": int(result.node_id),
        "source_file": result.source_file,
        "page_range": page_range,
        "section_path": section_path,
        "text": _snippet(result.text),
        "score": float(result.score),
        "confidence": _confidence(result.score),
        "reason": _reason(result, section_path, page_range),
        "matched_chunk_ids": [chunk_id] if chunk_id else [],
    }


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


def _context_pack(evidence: list[dict[str, Any]], *, token_budget: int) -> tuple[dict[str, Any], str]:
    items: list[dict[str, Any]] = []
    used_tokens = 0
    warning = ""
    for index, item in enumerate(evidence, 1):
        content = str(item["text"])
        estimated = _estimate_tokens(content)
        if used_tokens + estimated > token_budget:
            if not items:
                warning = "context_budget_exhausted"
            break
        context_item = {
            "context_item_id": f"ctx_{index:03d}",
            "content_type": "text",
            "content": content,
            "source": {
                "doc_id": item["doc_id"],
                "source_file": item["source_file"],
                "page_range": item["page_range"],
                "section_path": item["section_path"],
            },
            "citation_id": item["citation_id"],
            "evidence_refs": [item["evidence_id"]],
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
