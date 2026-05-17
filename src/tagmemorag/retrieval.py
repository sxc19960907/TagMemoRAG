from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import quote
from typing import Any, Sequence

from .document_assets import AssetManifest, DocumentAsset
from .types import Result

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
    query_text: str = "",
) -> dict[str, Any]:
    visual_intent = detect_visual_intent(query_text)
    evidence = [_evidence_from_result(result, index, visual_resolver=visual_resolver) for index, result in enumerate(results, 1)]
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
        "visual_evidence": _visual_summary(evidence, visual_intent=visual_intent, manifest_present=visual_resolver is not None and visual_resolver.manifest is not None),
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


def _evidence_from_result(result: Result, index: int, *, visual_resolver: VisualEvidenceResolver | None = None) -> dict[str, Any]:
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
        "text": _snippet(result.text),
        "score": float(result.score),
        "confidence": _confidence(result.score),
        "reason": _reason(result, section_path, page_range),
        "matched_chunk_ids": [chunk_id] if chunk_id else [],
        "assets": assets,
        "asset_warnings": asset_warnings,
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
