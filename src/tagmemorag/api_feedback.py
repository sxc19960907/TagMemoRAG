from __future__ import annotations

import structlog

from .api_models import FeedbackPromoteRequest, FeedbackReviewRequest, FeedbackSubmitRequest
from .auth.base import ApiKey
from .auth.dependencies import ensure_kb_access
from .config import Settings
from .retrieval_feedback import (
    create_feedback,
    export_eval_promotion,
    list_feedback,
    preview_eval_promotion,
    review_feedback,
)


def submit_feedback(request: FeedbackSubmitRequest, api_key: ApiKey, settings: Settings, *, kind: str) -> dict[str, object]:
    ensure_kb_access(api_key, request.kb_name)
    feedback = create_feedback(request.kb_name, request.model_dump(), settings)
    structlog.get_logger().info(
        f"{kind}_feedback_created",
        kb_name=feedback.kb_name,
        outcome=feedback.outcome,
        status=feedback.status,
        trace_id=feedback.trace_id,
    )
    return {"feedback": feedback.to_dict()}


def list_search_feedback(
    kb_name: str,
    api_key: ApiKey,
    settings: Settings,
    *,
    status: str | None,
    outcome: str | None,
    query: str | None,
    limit: int,
) -> dict[str, object]:
    ensure_kb_access(api_key, kb_name)
    rows = list_feedback(kb_name, settings, status=status, outcome=outcome, query=query, limit=limit)
    return {"kb_name": kb_name, "feedback": [row.to_dict() for row in rows]}


def review_search_feedback(
    feedback_id: str,
    request: FeedbackReviewRequest,
    api_key: ApiKey,
    settings: Settings,
) -> dict[str, object]:
    ensure_kb_access(api_key, request.kb_name)
    feedback = review_feedback(
        request.kb_name,
        feedback_id,
        settings,
        status=request.status,
        operator_note=request.operator_note,
    )
    structlog.get_logger().info(
        "search_feedback_reviewed",
        kb_name=feedback.kb_name,
        status=feedback.status,
        outcome=feedback.outcome,
        trace_id=feedback.trace_id,
    )
    return {"feedback": feedback.to_dict()}


def preview_search_feedback(request: FeedbackPromoteRequest, api_key: ApiKey, settings: Settings) -> dict[str, object]:
    ensure_kb_access(api_key, request.kb_name)
    preview = preview_eval_promotion(
        request.kb_name,
        request.feedback_ids,
        settings,
        output_path=request.output_path,
    )
    return preview.to_dict()


def promote_search_feedback(request: FeedbackPromoteRequest, api_key: ApiKey, settings: Settings) -> dict[str, object]:
    ensure_kb_access(api_key, request.kb_name)
    preview = export_eval_promotion(
        request.kb_name,
        request.feedback_ids,
        settings,
        output_path=request.output_path,
        append=request.append,
        overwrite=request.overwrite,
    )
    structlog.get_logger().info(
        "search_feedback_promoted",
        kb_name=request.kb_name,
        status="promoted",
        count=len(preview.cases),
    )
    return preview.to_dict()
