from __future__ import annotations

from .api_models import QaAnswerRequest
from .auth.base import ApiKey
from .errors import KbNotLoadedError
from .state import AppState
from .types import GraphState


def route_qa_question(question: str, api_key: ApiKey, app_state: AppState) -> dict[str, object]:
    candidates: list[dict[str, object]] = []
    for kb_name in app_state.list_kbs():
        if not api_key.allows_kb(kb_name):
            continue
        try:
            state = app_state.get_kb(kb_name)
        except KbNotLoadedError:
            continue
        candidates.append({
            "kb_name": kb_name,
            "label": qa_kb_label(state),
            "score": qa_route_score(question, state),
        })

    if not candidates:
        return {"kind": "not_ready", "candidates": []}
    if len(candidates) == 1:
        return {"kind": "answered", "kb_name": candidates[0]["kb_name"], "reason": "single_kb"}

    ranked = sorted(candidates, key=lambda item: (-float(item["score"]), str(item["kb_name"])))
    best = ranked[0]
    second_score = float(ranked[1]["score"])
    if float(best["score"]) >= 2 and float(best["score"]) >= second_score + 1:
        return {"kind": "answered", "kb_name": best["kb_name"], "reason": "lexical_route"}
    return {"kind": "clarification", "candidates": [qa_public_candidate(item) for item in ranked[:5]]}


def qa_not_ready_response(route: dict[str, object]) -> dict[str, object]:
    return {
        "schema_version": "qa_answer.v1",
        "route": {"kind": "not_ready", "candidates": route.get("candidates", [])},
        "answer": {
            "kind": "error",
            "text": "The manual assistant is not ready yet. Please import manuals and rebuild the knowledge base before asking questions.",
            "confidence": 0.0,
            "citations": [],
            "refusal_reason": "kb_not_ready",
            "missing_evidence_hints": ["kb_not_ready"],
            "model_id": None,
            "model_version": None,
            "prompt_version": None,
            "warnings": [],
        },
        "warnings": ["qa_route:not_ready"],
    }


def qa_clarification_response(request: QaAnswerRequest, route: dict[str, object]) -> dict[str, object]:
    candidates = route.get("candidates", [])
    return {
        "schema_version": "qa_answer.v1",
        "route": {"kind": "clarification", "candidates": candidates},
        "answer": {
            "kind": "clarification",
            "text": "Which product or manual is this question about?",
            "confidence": 0.0,
            "citations": [],
            "refusal_reason": "needs_clarification",
            "missing_evidence_hints": ["choose_product_or_manual"],
            "model_id": None,
            "model_version": None,
            "prompt_version": None,
            "warnings": [],
        },
        "warnings": ["qa_route:needs_clarification"],
        "question": request.question,
    }


def qa_public_candidate(candidate: dict[str, object]) -> dict[str, object]:
    return {
        "kb_name": candidate["kb_name"],
        "label": candidate["label"],
    }


def qa_kb_label(state: GraphState) -> str:
    labels: list[str] = []
    for _, data in list(state.graph.nodes(data=True))[:50]:
        metadata = data.get("metadata") or {}
        for key in ("manual_title", "title", "product_model", "product_category", "brand"):
            value = metadata.get(key) or data.get(key)
            if value:
                labels.append(str(value))
    return labels[0] if labels else state.kb_name


def qa_route_score(question: str, state: GraphState) -> int:
    query = question.casefold()
    score = 0
    if state.kb_name.casefold() in query:
        score += 3
    seen: set[str] = set()
    for _, data in list(state.graph.nodes(data=True))[:80]:
        metadata = data.get("metadata") or {}
        values = [
            data.get("header"),
            data.get("path"),
            data.get("source_file"),
            metadata.get("manual_title"),
            metadata.get("title"),
            metadata.get("brand"),
            metadata.get("product_category"),
            metadata.get("product_model"),
            metadata.get("manual_id"),
        ]
        for value in values:
            if not value:
                continue
            text = str(value).casefold()
            if text in seen:
                continue
            seen.add(text)
            if len(text) >= 2 and text in query:
                score += 2
    return score
