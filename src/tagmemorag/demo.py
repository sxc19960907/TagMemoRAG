from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import io
import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any, Iterator
import sys
import time

from . import api
from .api_models import AnswerRequest
from .auth.base import ApiKey
from .cli_helpers import create_embedder_from_config
from .config import load_config
from .logging_setup import configure_logging
from .manual_library import build_dirty_state_report, list_records, upsert_manual
from .state import AppState, load_kb, start_library_rebuild

DEMO_QA_SCHEMA_VERSION = "demo_qa.v1"
DEMO_LIBRARY_QA_SCHEMA_VERSION = "demo_library_qa.v1"


@dataclass(frozen=True)
class DemoQaOptions:
    question: str
    config_path: str = "examples/config/qa-demo.yaml"
    kb_name: str = "default"
    top_k: int | None = None
    source_k: int | None = None
    token_budget: int | None = None
    output_path: str | None = None


@dataclass(frozen=True)
class DemoLibraryQaOptions:
    config_path: str = "examples/config/qa-demo.yaml"
    kb_name: str = "default"
    manual_id: str = "demo-service-manual"
    question: str = "蒸汽很小怎么办？"
    output_path: str | None = None
    overwrite: bool = True


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


def run_demo_library_qa(options: DemoLibraryQaOptions) -> dict[str, Any]:
    cfg = load_config(options.config_path)
    configure_logging(cfg.logging.level, cfg.logging.format)
    emb = create_embedder_from_config(cfg)
    app_state = _load_app_state(options.kb_name, cfg)

    metadata = _demo_library_metadata(options.manual_id)
    upsert_manual(
        options.kb_name,
        metadata,
        _demo_library_manual_text().encode("utf-8"),
        cfg,
        overwrite=options.overwrite,
    )
    before = build_dirty_state_report(options.kb_name, cfg, graph_state=app_state.kbs.get(options.kb_name))
    with _capture_stdout():
        task = start_library_rebuild(app_state, options.kb_name, cfg, embedder=emb, mode="incremental")
        while task.status == "running":
            time.sleep(0.05)
    rebuilt_state = app_state.kbs.get(options.kb_name)
    after = build_dirty_state_report(options.kb_name, cfg, graph_state=rebuilt_state)
    records = list_records(options.kb_name, cfg, graph_state=rebuilt_state)
    record = next((item for item in records if item.manual_id == options.manual_id), None)

    answer = _run_library_qa_answer(options, cfg, emb, app_state, task.status == "done")
    payload = {
        "schema_version": DEMO_LIBRARY_QA_SCHEMA_VERSION,
        "status": "passed" if _library_qa_passed(task, record, answer, options.manual_id) else "failed",
        "kb_name": options.kb_name,
        "manual_id": options.manual_id,
        "upload": {
            "rebuild_required_before": bool(before.get("pending_changes")),
            "dirty_manual_count_before": int(before.get("dirty_manual_count") or 0),
        },
        "rebuild": {
            "status": task.status,
            "requested_mode": task.requested_mode,
            "effective_mode": task.effective_mode,
            "build_id": task.build_id or "",
            "pending_changes_after": bool(after.get("pending_changes")),
            "dirty_manual_count_after": int(after.get("dirty_manual_count") or 0),
        },
        "manual": {
            "searchable": bool(record.searchable) if record is not None else False,
            "chunk_count": int(record.chunk_count) if record is not None else 0,
            "source_file": str(record.source_file) if record is not None else "",
        },
        "qa": {
            "status": answer.get("status", ""),
            "question": options.question,
            "answer_kind": (answer.get("answer") or {}).get("kind", ""),
            "answer_text": (answer.get("answer") or {}).get("text", ""),
            "citation_count": int((answer.get("answer") or {}).get("citation_count") or 0),
            "evidence_count": int((answer.get("retrieve") or {}).get("evidence_count") or 0),
            "sources": (answer.get("retrieve") or {}).get("sources") or [],
        },
    }
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


def _load_app_state(kb_name: str, cfg: Any) -> AppState:
    try:
        return AppState(load_kb(kb_name, cfg))
    except Exception:
        return AppState()


def _run_library_qa_answer(options: DemoLibraryQaOptions, cfg: Any, emb: Any, app_state: AppState, ready: bool) -> dict[str, Any]:
    if not ready:
        return {
            "schema_version": DEMO_QA_SCHEMA_VERSION,
            "status": "failed",
            "question": options.question,
            "answer": {"kind": "", "text": "", "citations": []},
            "retrieve": {"evidence_count": 0, "sources": []},
            "warnings": ["library_rebuild_failed"],
        }
    api.settings = cfg
    api.embedder = emb
    api.app_state = app_state
    api.app_state.mark_embedder_ready()
    api._ANSWER_GENERATOR_CACHE.clear()
    if hasattr(api, "_RERANK_DISPATCHER_CACHE"):
        api._RERANK_DISPATCHER_CACHE.clear()
    request = AnswerRequest(
        question=options.question,
        kb_name=options.kb_name,
        top_k=2,
        token_budget=4000,
        include_retrieve=True,
    )
    with _capture_stdout():
        answer_body = api.answer(
            request,
            _fake_request(),
            ApiKey(id="demo", label="Local demo", hash="", kb_allowlist=("*",), scopes=frozenset({"search"})),
            None,
        )
    return summarize_demo_qa_response(options.question, answer_body)


def _demo_library_metadata(manual_id: str) -> dict[str, Any]:
    return {
        "manual_id": manual_id,
        "title": "Demo Coffee Machine Troubleshooting Manual",
        "source_file": f"demo/{manual_id}.md",
        "product_category": "coffee",
        "language": "zh-CN",
        "tags": ["coffee", "troubleshooting", "demo"],
    }


def _demo_library_manual_text() -> str:
    return (
        "# 咖啡机排障演示手册\n"
        "本手册用于演示浏览器问答，覆盖蒸汽、出咖啡、喷嘴清洗和除垢。\n"
        "# 蒸汽很小\n"
        "若蒸汽很小，请先检查喷嘴是否堵塞并清洗喷嘴，再检查水箱水量。若长期未维护，请执行除垢程序，因为水垢会影响蒸汽压力。\n"
        "# 不出咖啡\n"
        "若不出咖啡，请检查水箱是否缺水、粉仓是否堵塞、研磨器是否卡住，并确认冲煮单元安装到位。\n"
        "# 喷嘴清洗\n"
        "每次使用蒸汽后都要冲洗喷嘴十秒。喷嘴堵塞会造成蒸汽变小、奶泡不足或出汽不稳定，可用清洁针疏通喷嘴孔。\n"
        "# 除垢\n"
        "当出水量不足、加热变慢或蒸汽压力下降时，需要进行除垢。除垢前请取下滤芯，并按照除垢程序完成冲洗。\n"
    )


def _library_qa_passed(task: Any, record: Any, answer: dict[str, Any], manual_id: str) -> bool:
    sources = (answer.get("retrieve") or {}).get("sources") or []
    return (
        task.status == "done"
        and record is not None
        and bool(getattr(record, "searchable", False))
        and int(getattr(record, "chunk_count", 0)) > 0
        and (answer.get("answer") or {}).get("kind") == "answer"
        and any(str(source.get("source_file") or "").endswith(f"{manual_id}.md") for source in sources)
    )


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
