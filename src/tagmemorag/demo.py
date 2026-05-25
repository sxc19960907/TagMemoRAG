from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator
import sys

from . import api
from .api_models import AnswerRequest
from .auth.base import ApiKey
from .cli_helpers import create_embedder_from_config
from .config import load_config
from .logging_setup import configure_logging
from .state import AppState, load_kb

DEMO_QA_SCHEMA_VERSION = "demo_qa.v1"


@dataclass(frozen=True)
class DemoQaOptions:
    question: str
    config_path: str = "examples/config/qa-demo.yaml"
    kb_name: str = "default"
    top_k: int | None = None
    source_k: int | None = None
    token_budget: int | None = None
    output_path: str | None = None


def run_demo_qa(options: DemoQaOptions) -> dict[str, Any]:
    cfg = load_config(options.config_path)
    configure_logging(cfg.logging.level, cfg.logging.format)
    emb = create_embedder_from_config(cfg)
    state = load_kb(options.kb_name, cfg)

    api.settings = cfg
    api.embedder = emb
    api.app_state = AppState(state)
    api.app_state.mark_embedder_ready()
    api._ANSWER_GENERATOR_CACHE.clear()
    if hasattr(api, "_RERANK_DISPATCHER_CACHE"):
        api._RERANK_DISPATCHER_CACHE.clear()

    request = AnswerRequest(
        question=options.question,
        kb_name=options.kb_name,
        top_k=options.top_k,
        source_k=options.source_k,
        token_budget=options.token_budget if options.token_budget is not None else 4000,
        include_retrieve=True,
    )
    with _capture_stdout():
        answer_body = api.answer(
            request,
            _fake_request(),
            ApiKey(id="demo", label="Local demo", hash="", kb_allowlist=("*",), scopes=frozenset({"search"})),
            None,
        )
    payload = summarize_demo_qa_response(options.question, answer_body)
    if options.output_path:
        output = Path(options.output_path)
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_text(json.dumps(payload, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return payload


def summarize_demo_qa_response(question: str, response: dict[str, Any]) -> dict[str, Any]:
    answer = dict(response.get("answer") or {})
    retrieve = dict(response.get("retrieve") or {})
    answerability = dict(retrieve.get("answerability") or {})
    evidence = list(retrieve.get("evidence") or [])
    citations = list(retrieve.get("citations") or [])
    payload = {
        "schema_version": DEMO_QA_SCHEMA_VERSION,
        "status": "passed" if answer.get("kind") == "answer" and evidence else "failed",
        "question": question,
        "kb_name": str(response.get("kb_name") or retrieve.get("kb_name") or ""),
        "build_id": str(response.get("build_id") or retrieve.get("build_id") or ""),
        "plan_id": str(response.get("plan_id") or retrieve.get("plan_id") or ""),
        "answer": {
            "kind": str(answer.get("kind") or ""),
            "text": str(answer.get("text") or ""),
            "citation_count": len(answer.get("citations") if isinstance(answer.get("citations"), list) else []),
            "citations": _answer_citations(answer),
            "confidence": float(answer.get("confidence") or 0.0),
            "model_id": str(answer.get("model_id") or ""),
            "prompt_version": str(answer.get("prompt_version") or ""),
            "refusal_reason": str(answer.get("refusal_reason") or ""),
        },
        "retrieve": {
            "answerable": bool(answerability.get("answerable")),
            "fallback_reason": str(answerability.get("fallback_reason") or ""),
            "evidence_count": len(evidence),
            "citation_count": len(citations),
            "sources": [_source_summary(item) for item in evidence[:5]],
        },
        "warnings": list(response.get("warnings") or []),
    }
    return payload


def _answer_citations(answer: dict[str, Any]) -> list[str]:
    citations = answer.get("citations")
    if not isinstance(citations, list):
        return []
    return [str(item.get("citation_id") or "") for item in citations if isinstance(item, dict) and item.get("citation_id")]


def _source_summary(item: Any) -> dict[str, Any]:
    evidence = dict(item or {})
    return {
        "evidence_id": str(evidence.get("evidence_id") or ""),
        "citation_id": str(evidence.get("citation_id") or ""),
        "source_file": str(evidence.get("source_file") or ""),
        "section_path": list(evidence.get("section_path") or []),
        "score": float(evidence.get("score") or 0.0),
    }


def _fake_request() -> Any:
    return SimpleNamespace(state=SimpleNamespace(trace_id="demo-qa"))


@contextmanager
def _capture_stdout() -> Iterator[None]:
    original = sys.stdout
    sys.stdout = io.StringIO()
    try:
        yield
    finally:
        sys.stdout = original
