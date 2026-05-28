from __future__ import annotations

import importlib.util
import os
import shutil
from typing import Any
from urllib.parse import urlencode

from . import api_eval_runs
from .api_manual import manual_library_diagnostics
from .auth.base import ApiKey
from .auth.dependencies import ensure_kb_access
from .config import Settings
from .state import AppState

SCHEMA_VERSION = "rag_readiness.v1"
STATUS_READY = "ready"
STATUS_NEEDS_REVIEW = "needs_review"
STATUS_NOT_READY = "not_ready"


def rag_readiness_summary(
    kb_name: str,
    *,
    settings: Settings,
    app_state: AppState,
    api_key: ApiKey,
    get_rebuild_queue,
) -> dict[str, Any]:
    kb = str(kb_name or "default").strip() or "default"
    ensure_kb_access(api_key, kb)
    cards: list[dict[str, Any]] = []
    actions = _base_actions(kb)

    kb_card = _kb_card(kb, app_state)
    cards.append(kb_card)
    manual_card = _manual_card(kb, settings=settings, app_state=app_state, api_key=api_key, get_rebuild_queue=get_rebuild_queue)
    cards.append(manual_card)
    eval_card = _eval_card(kb, settings=settings)
    cards.append(eval_card)
    qa_card = _qa_card(kb, kb_card)
    cards.append(qa_card)
    capabilities = _capability_cards(kb, settings=settings, manual_card=manual_card)
    delivery = _delivery_checks(kb, qa_card=qa_card, capabilities=capabilities)

    status = _overall_status(cards)
    recommendations = _recommendations(cards, capabilities, kb)
    primary_action = _primary_action(status, recommendations, kb)
    return {
        "schema_version": SCHEMA_VERSION,
        "kb_name": kb,
        "status": status,
        "summary": _status_summary(status),
        "capabilities": capabilities,
        "delivery": delivery,
        "cards": cards,
        "actions": actions,
        "primary_action": primary_action,
        "recommendations": recommendations,
    }


def _kb_card(kb_name: str, app_state: AppState) -> dict[str, Any]:
    state = app_state.kbs.get(kb_name)
    if app_state.is_shutting_down:
        status = STATUS_NOT_READY
        summary = "Server is shutting down."
    elif not app_state.embedder_ready:
        status = STATUS_NOT_READY
        summary = "Embedder is not ready."
    elif state is None:
        status = STATUS_NOT_READY
        summary = "KB is not loaded."
    else:
        status = STATUS_READY
        summary = "KB is loaded and can serve retrieval requests."
    return _card(
        "kb",
        "KB Loaded",
        status,
        summary,
        {
            "embedder_ready": bool(app_state.embedder_ready),
            "loaded": state is not None,
            "build_id": getattr(state, "build_id", "") if state is not None else "",
            "node_count": int(state.graph.number_of_nodes()) if state is not None else 0,
            "loaded_kbs": sorted(app_state.kbs.keys()),
        },
    )


def _manual_card(
    kb_name: str,
    *,
    settings: Settings,
    app_state: AppState,
    api_key: ApiKey,
    get_rebuild_queue,
) -> dict[str, Any]:
    diagnostics = manual_library_diagnostics(
        kb_name,
        verify_blobs=False,
        include_jobs=True,
        job_status=None,
        api_key=api_key,
        settings=settings,
        app_state=app_state,
        get_rebuild_queue=get_rebuild_queue,
    )
    dirty = _safe_dict(diagnostics.get("dirty"))
    blob = _safe_dict(diagnostics.get("blob_health"))
    queue = _safe_dict(diagnostics.get("rebuild_queue"))
    source_preview = _safe_dict(_safe_dict(diagnostics.get("last_rebuild")).get("source_preview"))
    jobs = queue.get("jobs") if isinstance(queue.get("jobs"), list) else []
    failed_jobs = [job for job in jobs if isinstance(job, dict) and str(job.get("status")) == "failed"]
    active_jobs = [
        job
        for job in jobs
        if isinstance(job, dict) and str(job.get("status")) in {"queued", "running", "retrying"}
    ]
    pending = bool(dirty.get("pending_changes"))
    missing_count = int(blob.get("missing_count") or 0)
    source_preview_needs_review = str(source_preview.get("status") or "") == STATUS_NEEDS_REVIEW
    if failed_jobs or missing_count > 0:
        status = STATUS_NEEDS_REVIEW
        summary = "Manual library has failed rebuild work or missing blob objects."
    elif pending:
        status = STATUS_NEEDS_REVIEW
        summary = "Manual changes are pending rebuild before the KB is fully current."
    elif active_jobs:
        status = STATUS_NEEDS_REVIEW
        summary = "Manual rebuild work is still in progress."
    elif source_preview_needs_review:
        status = STATUS_NEEDS_REVIEW
        summary = "Manual library is searchable, but PDF source previews need review."
    else:
        status = STATUS_READY
        summary = "Manual library has no pending rebuild blockers."
    return _card(
        "manuals",
        "Manual Library",
        status,
        summary,
        {
            "pending_changes": pending,
            "dirty_manual_count": int(dirty.get("dirty_manual_count") or 0),
            "missing_blob_count": missing_count,
            "failed_rebuild_jobs": len(failed_jobs),
            "active_rebuild_jobs": len(active_jobs),
            "current_build_id": str(_safe_dict(diagnostics.get("last_rebuild")).get("current_build_id") or ""),
            "source_preview_status": str(source_preview.get("status") or ""),
            "source_preview_message": str(source_preview.get("message") or ""),
            "page_snapshots_ready": int(source_preview.get("page_snapshots_ready") or 0),
            "page_snapshots_failed": int(source_preview.get("page_snapshots_failed") or 0),
        },
    )


def _eval_card(kb_name: str, *, settings: Settings) -> dict[str, Any]:
    suites = api_eval_runs.list_eval_suites(settings=settings).get("suites", [])
    reports = [_safe_dict(suite.get("latest_report")) for suite in suites if isinstance(suite, dict) and suite.get("latest_report")]
    matching = [
        (suite, _safe_dict(suite.get("latest_report")))
        for suite in suites
        if isinstance(suite, dict) and _safe_dict(suite.get("latest_report")) and _suite_matches_kb(suite, kb_name)
    ]
    selected_suite: dict[str, Any] | None = None
    latest: dict[str, Any] | None = None
    if matching:
        selected_suite, latest = max(matching, key=lambda item: float(item[1].get("modified_at") or 0.0))
    elif reports:
        latest = max(reports, key=lambda item: float(item.get("modified_at") or 0.0))
    if latest is None:
        status = STATUS_NEEDS_REVIEW
        summary = "No browser eval report has been loaded for this KB yet."
        detail = {"has_latest_report": False, "suite_id": "", "passed": None, "cases": 0, "failed": 0, "report_path": ""}
    else:
        passed = latest.get("passed")
        status = STATUS_READY if passed is True else STATUS_NEEDS_REVIEW
        summary = "Latest browser eval passed." if passed is True else "Latest browser eval needs review."
        detail = {
            "has_latest_report": True,
            "suite_id": str((selected_suite or {}).get("suite_id") or ""),
            "passed": passed,
            "cases": int(latest.get("cases") or 0),
            "failed": int(latest.get("failed") or 0),
            "modified_at": latest.get("modified_at"),
            "report_path": str(latest.get("path") or ""),
            "relative_path": str(latest.get("relative_path") or ""),
        }
    return _card("eval", "Retrieval Eval", status, summary, detail)


def _qa_card(kb_name: str, kb_card: dict[str, Any]) -> dict[str, Any]:
    if kb_card["status"] == STATUS_READY:
        status = STATUS_READY
        summary = "Q&A can be opened for this KB."
    else:
        status = STATUS_NOT_READY
        summary = "Q&A needs a loaded KB before normal use."
    return _card("qa", "User Q&A", status, summary, {"href": f"/qa?{urlencode({'kb_name': kb_name})}"})


def _capability_cards(kb_name: str, *, settings: Settings, manual_card: dict[str, Any]) -> list[dict[str, Any]]:
    return [
        _answer_capability(kb_name, settings),
        _embedding_capability(kb_name, settings),
        _ocr_capability(kb_name, settings),
        _source_preview_capability(kb_name, settings=settings, manual_card=manual_card),
    ]


def _answer_capability(kb_name: str, settings: Settings) -> dict[str, Any]:
    cfg = settings.answer
    detail = {
        "enabled": bool(cfg.enabled),
        "provider": str(cfg.provider),
        "model": str(cfg.model_id or cfg.provider),
        "api_key_env": str(cfg.api_key_env or ""),
        "api_key_present": _env_present(cfg.api_key_env) if cfg.provider == "openai_compatible" else None,
    }
    if not cfg.enabled:
        status = STATUS_NEEDS_REVIEW
        summary = "Answer generation is disabled; Q&A will not draft model answers."
    elif cfg.provider == "noop":
        status = STATUS_NEEDS_REVIEW
        summary = "Answer generation uses the offline demo provider."
    elif cfg.provider == "openai_compatible" and not detail["api_key_present"]:
        status = STATUS_NOT_READY
        summary = "Answer LLM is enabled, but its API key environment variable is missing."
    else:
        status = STATUS_READY
        summary = "Answer LLM configuration is ready for model-backed Q&A."
    return _capability(
        "answer",
        "Answer LLM",
        status,
        summary,
        detail,
        "Open Workbench",
        _kb_href("rag-workbench", kb_name),
    )


def _embedding_capability(kb_name: str, settings: Settings) -> dict[str, Any]:
    cfg = settings.model
    detail = {
        "provider": str(cfg.provider),
        "model": str(cfg.name),
        "dimensions": int(cfg.dim),
        "api_key_env": str(cfg.api_key_env or "") if cfg.provider == "http" else "",
        "api_key_present": _env_present(cfg.api_key_env) if cfg.provider == "http" else None,
    }
    if cfg.provider == "http" and not detail["api_key_present"]:
        status = STATUS_NOT_READY
        summary = "HTTP embeddings are configured, but the API key environment variable is missing."
    elif cfg.provider == "http":
        status = STATUS_READY
        summary = "HTTP embedding configuration is ready."
    else:
        status = STATUS_READY
        summary = "Local embedding configuration is ready."
    return _capability("embedding", "Embeddings", status, summary, detail, "Manual Library", _kb_href("manual-library", kb_name))


def _ocr_capability(kb_name: str, settings: Settings) -> dict[str, Any]:
    cfg = settings.ocr
    commands = []
    if cfg.enabled and cfg.provider == "tesseract_cli":
        commands = [
            _command_status("PDF renderer", cfg.pdf_renderer_command),
            _command_status("Tesseract", cfg.tesseract_command),
        ]
    missing = [item for item in commands if not item["available"]]
    detail = {
        "enabled": bool(cfg.enabled),
        "provider": str(cfg.provider),
        "language": str(cfg.language),
        "commands": commands,
        "missing_commands": len(missing),
    }
    if not cfg.enabled:
        status = STATUS_NEEDS_REVIEW
        summary = "OCR is disabled; scanned PDFs may need searchable text already embedded."
    elif cfg.provider == "tesseract_cli" and missing:
        status = STATUS_NOT_READY
        summary = "OCR is enabled, but required local commands are missing."
    else:
        status = STATUS_READY
        summary = "OCR configuration is ready for scanned PDF ingestion."
    return _capability("ocr", "OCR", status, summary, detail, "Manual Library", _kb_href("manual-library", kb_name))


def _source_preview_capability(kb_name: str, *, settings: Settings, manual_card: dict[str, Any]) -> dict[str, Any]:
    detail = _safe_dict(manual_card.get("detail"))
    preview_status = str(detail.get("source_preview_status") or "")
    payload = {
        "enabled": bool(settings.assets.enabled),
        "pdf_page_snapshots_enabled": bool(settings.assets.pdf_page_snapshots_enabled),
        "renderer_available": _command_or_module_available("fitz"),
        "source_preview_status": preview_status,
        "page_snapshots_ready": int(detail.get("page_snapshots_ready") or 0),
        "page_snapshots_failed": int(detail.get("page_snapshots_failed") or 0),
    }
    if not settings.assets.enabled or not settings.assets.pdf_page_snapshots_enabled:
        status = STATUS_NEEDS_REVIEW
        summary = "PDF source previews are disabled; citations can still show text snippets."
    elif not payload["renderer_available"]:
        status = STATUS_NOT_READY
        summary = "PDF source previews are enabled, but the page renderer is unavailable."
    elif preview_status == STATUS_NEEDS_REVIEW:
        status = STATUS_NEEDS_REVIEW
        summary = str(detail.get("source_preview_message") or "PDF source previews need review.")
    else:
        status = STATUS_READY
        summary = "PDF source preview configuration is ready."
    return _capability(
        "source_preview",
        "PDF Source Preview",
        status,
        summary,
        payload,
        "Review manuals",
        _kb_href("manual-library", kb_name),
    )


def _delivery_checks(kb_name: str, *, qa_card: dict[str, Any], capabilities: list[dict[str, Any]]) -> list[dict[str, Any]]:
    capability_status = {str(item.get("id")): str(item.get("status") or "") for item in capabilities}
    live_provider_blocked = any(
        capability_status.get(capability_id) == STATUS_NOT_READY for capability_id in ("answer", "embedding")
    )
    qa_ready = qa_card.get("status") == STATUS_READY
    return [
        _delivery_check(
            "config_validate",
            "Validate configuration",
            STATUS_NEEDS_REVIEW,
            "Checks config shape, writable paths, optional extras, and required env var names without contacting providers.",
            "Local config",
            "python -m tagmemorag config validate --config <config.yaml>",
        ),
        _delivery_check(
            "readiness_smoke",
            "Run local RAG smoke",
            STATUS_NEEDS_REVIEW,
            "Proves deterministic build, retrieve, answer, query-plan, and bundle paths compose locally.",
            "Local gate",
            "python -m tagmemorag readiness smoke",
        ),
        _delivery_check(
            "browser_qa",
            "Verify browser Q&A",
            STATUS_NEEDS_REVIEW if qa_ready else STATUS_NOT_READY,
            "Exercises the user-facing browser path from documents to grounded Q&A with citations.",
            "Browser gate",
            "python -m tagmemorag readiness browser-qa",
            _kb_href("rag-readiness", kb_name) if not qa_ready else "/qa?" + urlencode({"kb_name": kb_name}),
        ),
        _delivery_check(
            "pilot_report",
            "Retain a pilot report",
            STATUS_NEEDS_REVIEW,
            "Creates a sanitized pre-pilot report that combines config, provider, smoke, answer-quality, and eval checks.",
            "Release record",
            "python -m tagmemorag pilot run --include-browser-qa --output .tmp/pilot/report.json",
        ),
        _delivery_check(
            "provider_verify",
            "Verify live providers",
            STATUS_NOT_READY if live_provider_blocked else STATUS_NEEDS_REVIEW,
            "Run this only for production profiles that use remote embeddings, answer models, rerankers, Qdrant, or object storage.",
            "Production gate",
            "python -m tagmemorag production-provider verify --level smoke",
        ),
    ]


def _delivery_check(
    check_id: str,
    title: str,
    status: str,
    summary: str,
    kind: str,
    command: str,
    href: str = "",
) -> dict[str, Any]:
    return {
        "id": check_id,
        "title": title,
        "status": status,
        "summary": summary,
        "kind": kind,
        "command": command,
        "href": href,
    }


def _suite_matches_kb(suite: dict[str, Any], kb_name: str) -> bool:
    if suite.get("kind") == "feedback_draft":
        path = str(suite.get("suite_path") or "")
        return f"/{kb_name}/" in path or path.endswith(f"/{kb_name}.jsonl")
    return kb_name == "default"


def _overall_status(cards: list[dict[str, Any]]) -> str:
    statuses = {str(card.get("status") or "") for card in cards}
    if STATUS_NOT_READY in statuses:
        return STATUS_NOT_READY
    if STATUS_NEEDS_REVIEW in statuses:
        return STATUS_NEEDS_REVIEW
    return STATUS_READY


def _recommendations(cards: list[dict[str, Any]], capabilities: list[dict[str, Any]], kb_name: str) -> list[dict[str, str]]:
    recommendations: list[dict[str, str]] = []
    for capability in capabilities:
        status = str(capability.get("status") or "")
        if status != STATUS_NOT_READY:
            continue
        action = _safe_dict(capability.get("action"))
        recommendations.append(_recommendation(
            f"configure_{capability.get('id')}",
            str(capability.get("summary") or "Review configuration before using this capability."),
            "warning",
            str(action.get("label") or "Review configuration"),
            str(action.get("href") or f"/admin/rag-readiness?{urlencode({'kb_name': kb_name})}"),
            str(action.get("kind") or "warning"),
        ))
    for card in cards:
        status = str(card.get("status") or "")
        if status == STATUS_READY:
            continue
        detail = _safe_dict(card.get("detail"))
        if card.get("id") == "kb":
            recommendations.append(_recommendation(
                "load_kb",
                "Build or load this KB before using Q&A.",
                "error",
                "Manual Library",
                _kb_href("manual-library", kb_name),
                "warning",
            ))
        elif card.get("id") == "manuals":
            source_preview_status = str(detail.get("source_preview_status") or "")
            source_preview_message = str(detail.get("source_preview_message") or "")
            if source_preview_status == STATUS_NEEDS_REVIEW and source_preview_message:
                recommendations.append(_recommendation(
                    "review_source_previews",
                    source_preview_message,
                    "warning",
                    "Review manuals",
                    _kb_href("manual-library", kb_name),
                    "warning",
                ))
            else:
                recommendations.append(_recommendation(
                    "review_manuals",
                    "Open Manual Library and resolve pending rebuild or blob issues.",
                    "warning",
                    "Review manuals",
                    _kb_href("manual-library", kb_name),
                    "warning",
                ))
        elif card.get("id") == "eval":
            report_path = str(detail.get("report_path") or "")
            recommendations.append(_recommendation(
                "run_eval" if not detail.get("has_latest_report") else "review_eval",
                "Open Eval Report and run or review the browser eval suite.",
                "warning",
                "Open latest report" if report_path else "Open Eval Report",
                _report_href(report_path, kb_name),
                "warning",
            ))
        elif card.get("id") == "qa":
            recommendations.append(_recommendation(
                "try_qa_after_ready",
                "Open Q&A after the KB is ready.",
                "info",
                "Open Q&A",
                str(detail.get("href") or ""),
                "secondary",
            ))
    return recommendations


def _recommendation(code: str, label: str, severity: str, action_label: str, href: str, kind: str) -> dict[str, str]:
    return {
        "code": code,
        "label": label,
        "severity": severity,
        "action_label": action_label,
        "href": href,
        "kind": kind,
    }


def _capability(
    capability_id: str,
    title: str,
    status: str,
    summary: str,
    detail: dict[str, Any],
    action_label: str,
    href: str,
) -> dict[str, Any]:
    return {
        "id": capability_id,
        "title": title,
        "status": status,
        "summary": summary,
        "detail": detail,
        "action": {"label": action_label, "href": href, "kind": "secondary"},
    }


def _primary_action(status: str, recommendations: list[dict[str, str]], kb_name: str) -> dict[str, str]:
    if status == STATUS_READY:
        return {"label": "Start Q&A", "href": f"/qa?{urlencode({'kb_name': kb_name})}", "kind": "primary"}
    if recommendations:
        first = recommendations[0]
        return {
            "label": first.get("action_label") or "Review next step",
            "href": first.get("href") or f"/admin/rag-readiness?{urlencode({'kb_name': kb_name})}",
            "kind": first.get("kind") or "secondary",
        }
    return {"label": "Refresh readiness", "href": f"/admin/rag-readiness?{urlencode({'kb_name': kb_name})}", "kind": "secondary"}


def _kb_href(page: str, kb_name: str) -> str:
    return f"/admin/{page}?{urlencode({'kb_name': kb_name or 'default'})}"


def _report_href(report_path: str, kb_name: str) -> str:
    if report_path:
        return f"/admin/eval-report?{urlencode({'kb_name': kb_name or 'default', 'report_path': report_path})}"
    return f"/admin/eval-report?{urlencode({'kb_name': kb_name or 'default'})}"


def _base_actions(kb_name: str) -> list[dict[str, str]]:
    kb = urlencode({"kb_name": kb_name})
    return [
        {"label": "Open Q&A", "href": f"/qa?{kb}", "kind": "primary"},
        {"label": "Open Workbench", "href": f"/admin/rag-workbench?{kb}", "kind": "secondary"},
        {"label": "Manual Library", "href": f"/admin/manual-library?{kb}", "kind": "secondary"},
        {"label": "Retrieval Quality", "href": f"/admin/retrieval-quality?{kb}", "kind": "secondary"},
        {"label": "Eval Report", "href": f"/admin/eval-report?{kb}", "kind": "secondary"},
    ]


def _card(card_id: str, title: str, status: str, summary: str, detail: dict[str, Any]) -> dict[str, Any]:
    return {"id": card_id, "title": title, "status": status, "summary": summary, "detail": detail}


def _status_summary(status: str) -> str:
    if status == STATUS_READY:
        return "This KB is ready for normal browser Q&A."
    if status == STATUS_NEEDS_REVIEW:
        return "This KB can be inspected, but one or more signals need review."
    return "This KB is not ready for normal browser Q&A."


def _safe_dict(value: Any) -> dict[str, Any]:
    return dict(value) if isinstance(value, dict) else {}


def _env_present(env_name: str) -> bool:
    name = str(env_name or "").strip()
    return bool(name and os.environ.get(name))


def _command_status(label: str, command: str) -> dict[str, Any]:
    command_name = str(command or "").strip()
    return {"label": label, "command": command_name, "available": bool(command_name and shutil.which(command_name))}


def _command_or_module_available(module_name: str) -> bool:
    if module_name == "fitz":
        return importlib.util.find_spec("fitz") is not None
    return False
