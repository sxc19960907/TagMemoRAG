from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
from typing import Any, Literal, Mapping
import uuid

from .config import Settings
from .errors import ErrorCode, ServiceError
from .storage.atomic import atomic_write


FeedbackOutcome = Literal["helpful", "not_helpful", "missing_result", "wrong_manual", "other"]
FeedbackStatus = Literal["new", "triaged", "promoted", "dismissed"]

OUTCOMES: set[str] = {"helpful", "not_helpful", "missing_result", "wrong_manual", "other"}
STATUSES: set[str] = {"new", "triaged", "promoted", "dismissed"}
MAX_QUERY_CHARS = 1000
MAX_NOTE_CHARS = 2000
MAX_TEXT_CONTAINS_CHARS = 200
MAX_TEXT_CONTAINS_ITEMS = 8
MAX_REFS = 20
MAX_LIMIT = 500
DEFAULT_LIMIT = 50


@dataclass(frozen=True)
class FeedbackResultRef:
    rank: int | None = None
    node_id: int | None = None
    anchor_key: str = ""
    source_file: str = ""
    header: str = ""
    manual_id: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "node_id": self.node_id,
            "anchor_key": self.anchor_key,
            "source_file": self.source_file,
            "header": self.header,
            "manual_id": self.manual_id,
        }


@dataclass(frozen=True)
class FeedbackExpectedRef:
    source_file: str = ""
    header: str = ""
    anchor_key: str = ""
    text_contains: tuple[str, ...] = ()
    metadata: Mapping[str, Any] = field(default_factory=dict)

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "header": self.header,
            "anchor_key": self.anchor_key,
            "text_contains": list(self.text_contains),
            "metadata": dict(self.metadata),
        }


@dataclass(frozen=True)
class SearchFeedback:
    feedback_id: str
    kb_name: str
    trace_id: str
    search_id: str
    retrieve_id: str
    build_id: str
    query: str
    outcome: FeedbackOutcome
    created_at: str
    selected_results: tuple[FeedbackResultRef, ...] = ()
    selected_evidence_ids: tuple[str, ...] = ()
    selected_context_item_ids: tuple[str, ...] = ()
    answerable: bool | None = None
    failure_reason: str = ""
    expected: tuple[FeedbackExpectedRef, ...] = ()
    note: str = ""
    status: FeedbackStatus = "new"
    operator_note: str = ""
    plan_id: str = ""  # T2: optional QueryPlan reference; "" for legacy rows.

    def to_dict(self) -> dict[str, Any]:
        return {
            "feedback_id": self.feedback_id,
            "kb_name": self.kb_name,
            "trace_id": self.trace_id,
            "search_id": self.search_id,
            "retrieve_id": self.retrieve_id,
            "build_id": self.build_id,
            "query": self.query,
            "outcome": self.outcome,
            "created_at": self.created_at,
            "selected_results": [ref.to_dict() for ref in self.selected_results],
            "selected_evidence_ids": list(self.selected_evidence_ids),
            "selected_context_item_ids": list(self.selected_context_item_ids),
            "answerable": self.answerable,
            "failure_reason": self.failure_reason,
            "expected": [ref.to_dict() for ref in self.expected],
            "note": self.note,
            "status": self.status,
            "operator_note": self.operator_note,
            "plan_id": self.plan_id,
        }


@dataclass(frozen=True)
class EvalPromotionPreview:
    kb_name: str
    feedback_ids: tuple[str, ...]
    cases: tuple[dict[str, Any], ...]
    skipped: tuple[dict[str, Any], ...]
    output_path: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "kb_name": self.kb_name,
            "feedback_ids": list(self.feedback_ids),
            "cases": list(self.cases),
            "skipped": list(self.skipped),
            "output_path": self.output_path,
        }


def create_feedback(kb_name: str, payload: Mapping[str, Any], settings: Settings) -> SearchFeedback:
    feedback = feedback_from_payload(kb_name, payload)
    path = feedback_log_path(kb_name, settings)
    line = json.dumps(feedback.to_dict(), ensure_ascii=False, sort_keys=True)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("a", encoding="utf-8") as handle:
        handle.write(line + "\n")
    return feedback


def list_feedback(
    kb_name: str,
    settings: Settings,
    *,
    status: str | None = None,
    outcome: str | None = None,
    query: str | None = None,
    limit: int = DEFAULT_LIMIT,
) -> list[SearchFeedback]:
    if status is not None and status not in STATUSES:
        raise ServiceError(ErrorCode.INVALID_INPUT, "Invalid feedback status.", {"status": status})
    if outcome is not None and outcome not in OUTCOMES:
        raise ServiceError(ErrorCode.INVALID_INPUT, "Invalid feedback outcome.", {"outcome": outcome})
    limit = _bounded_limit(limit)
    query_filter = (query or "").strip().lower()
    overlays = _read_review_overlay(kb_name, settings)
    rows: list[SearchFeedback] = []
    for feedback in reversed(_read_feedback_log(kb_name, settings)):
        feedback = _apply_overlay(feedback, overlays.get(feedback.feedback_id, {}))
        if status is not None and feedback.status != status:
            continue
        if outcome is not None and feedback.outcome != outcome:
            continue
        if query_filter and query_filter not in feedback.query.lower():
            continue
        rows.append(feedback)
        if len(rows) >= limit:
            break
    return rows


def review_feedback(
    kb_name: str,
    feedback_id: str,
    settings: Settings,
    *,
    status: str | None = None,
    operator_note: str | None = None,
) -> SearchFeedback:
    feedback_id = _bounded_text(feedback_id, "feedback_id", 120)
    if status is not None and status not in STATUSES:
        raise ServiceError(ErrorCode.INVALID_INPUT, "Invalid feedback status.", {"status": status})
    note = None if operator_note is None else _bounded_text(operator_note, "operator_note", MAX_NOTE_CHARS)
    records = {item.feedback_id: item for item in _read_feedback_log(kb_name, settings)}
    if feedback_id not in records:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Feedback not found.", {"feedback_id": feedback_id, "kb_name": kb_name})
    overlays = _read_review_overlay(kb_name, settings)
    current = dict(overlays.get(feedback_id, {}))
    if status is not None:
        current["status"] = status
    if note is not None:
        current["operator_note"] = note
    current["updated_at"] = _now_iso()
    overlays[feedback_id] = current
    _write_review_overlay(kb_name, settings, overlays)
    return _apply_overlay(records[feedback_id], current)


def preview_eval_promotion(
    kb_name: str,
    feedback_ids: list[str],
    settings: Settings,
    *,
    output_path: str | None = None,
) -> EvalPromotionPreview:
    output = eval_draft_path(kb_name, settings, output_path)
    selected = _select_feedback(kb_name, feedback_ids, settings)
    existing_ids = _existing_case_ids(output)
    cases: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    for feedback in selected:
        case, reason = _feedback_to_eval_case(feedback)
        if reason:
            skipped.append({"feedback_id": feedback.feedback_id, "reason": reason})
            continue
        assert case is not None
        if case["id"] in existing_ids:
            skipped.append({"feedback_id": feedback.feedback_id, "reason": "duplicate_case_id", "case_id": case["id"]})
            continue
        existing_ids.add(case["id"])
        cases.append(case)
    return EvalPromotionPreview(
        kb_name=kb_name,
        feedback_ids=tuple(feedback.feedback_id for feedback in selected),
        cases=tuple(cases),
        skipped=tuple(skipped),
        output_path=str(output),
    )


def export_eval_promotion(
    kb_name: str,
    feedback_ids: list[str],
    settings: Settings,
    *,
    output_path: str | None = None,
    append: bool = False,
    overwrite: bool = False,
) -> EvalPromotionPreview:
    output = eval_draft_path(kb_name, settings, output_path)
    if output.exists() and not append and not overwrite:
        raise ServiceError(
            ErrorCode.INVALID_REQUEST,
            "Eval draft already exists; set append or overwrite explicitly.",
            {"output_path": str(output)},
        )
    preview = preview_eval_promotion(kb_name, feedback_ids, settings, output_path=str(output))
    if not preview.cases:
        return preview
    existing = output.read_text(encoding="utf-8").splitlines() if output.exists() and append else []
    rows = [json.dumps(case, ensure_ascii=False, sort_keys=True) for case in preview.cases]

    def _write(tmp: Path) -> None:
        body = "\n".join([line for line in existing if line.strip()] + rows) + "\n"
        tmp.write_text(body, encoding="utf-8")

    atomic_write(output, _write)
    for feedback_id in preview.feedback_ids:
        if any(case["id"] == f"feedback-{feedback_id}" for case in preview.cases):
            review_feedback(kb_name, feedback_id, settings, status="promoted")
    return preview


def feedback_from_payload(kb_name: str, payload: Mapping[str, Any]) -> SearchFeedback:
    kb_name = _safe_name(kb_name, "kb_name")
    outcome = _bounded_text(str(payload.get("outcome") or ""), "outcome", 40)
    if outcome not in OUTCOMES:
        raise ServiceError(ErrorCode.INVALID_INPUT, "Invalid feedback outcome.", {"outcome": outcome})
    status = str(payload.get("status") or "new")
    if status not in STATUSES:
        raise ServiceError(ErrorCode.INVALID_INPUT, "Invalid feedback status.", {"status": status})
    return SearchFeedback(
        feedback_id=_feedback_id(payload),
        kb_name=kb_name,
        trace_id=_bounded_text(str(payload.get("trace_id") or ""), "trace_id", 120),
        search_id=_bounded_text(str(payload.get("search_id") or ""), "search_id", 120),
        retrieve_id=_bounded_text(str(payload.get("retrieve_id") or ""), "retrieve_id", 120),
        build_id=_bounded_text(str(payload.get("build_id") or ""), "build_id", 120),
        query=_bounded_text(str(payload.get("query") or ""), "query", MAX_QUERY_CHARS, required=True),
        outcome=outcome,  # type: ignore[arg-type]
        created_at=str(payload.get("created_at") or _now_iso()),
        selected_results=_parse_result_refs(payload.get("selected_results", [])),
        selected_evidence_ids=_parse_id_list(payload.get("selected_evidence_ids", []), "selected_evidence_ids"),
        selected_context_item_ids=_parse_id_list(payload.get("selected_context_item_ids", []), "selected_context_item_ids"),
        answerable=_parse_optional_bool(payload.get("answerable")),
        failure_reason=_bounded_text(str(payload.get("failure_reason") or ""), "failure_reason", 120),
        expected=_parse_expected_refs(payload.get("expected", [])),
        note=_bounded_text(str(payload.get("note") or ""), "note", MAX_NOTE_CHARS),
        status=status,  # type: ignore[arg-type]
        operator_note=_bounded_text(str(payload.get("operator_note") or ""), "operator_note", MAX_NOTE_CHARS),
        plan_id=_bounded_text(str(payload.get("plan_id") or ""), "plan_id", 120),
    )


def feedback_log_path(kb_name: str, settings: Settings) -> Path:
    root = _kb_feedback_root(kb_name, settings)
    return _safe_child(root, "search-feedback.jsonl")


def review_overlay_path(kb_name: str, settings: Settings) -> Path:
    root = _kb_feedback_root(kb_name, settings)
    return _safe_child(root, "search-feedback-reviews.json")


def eval_draft_path(kb_name: str, settings: Settings, output_path: str | None = None) -> Path:
    root = (Path(settings.storage.data_dir).resolve().parent / "eval_drafts").resolve()
    kb_name = _safe_name(kb_name, "kb_name")
    if output_path:
        candidate = Path(output_path)
        path = candidate if candidate.is_absolute() else root / candidate
    else:
        stamp = datetime.now(timezone.utc).strftime("%Y%m%d")
        path = root / kb_name / f"feedback-{stamp}.jsonl"
    return _safe_child(root, path)


def _select_feedback(kb_name: str, feedback_ids: list[str], settings: Settings) -> list[SearchFeedback]:
    ids = [_bounded_text(str(item), "feedback_id", 120, required=True) for item in feedback_ids]
    if not ids:
        raise ServiceError(ErrorCode.INVALID_INPUT, "At least one feedback_id is required.")
    records = {item.feedback_id: item for item in list_feedback(kb_name, settings, limit=MAX_LIMIT)}
    missing = [item for item in ids if item not in records]
    if missing:
        raise ServiceError(ErrorCode.INVALID_REQUEST, "Feedback not found.", {"feedback_ids": missing, "kb_name": kb_name})
    return [records[item] for item in ids]


def _feedback_to_eval_case(feedback: SearchFeedback) -> tuple[dict[str, Any] | None, str]:
    query = feedback.query.strip()
    if len(query) < 2:
        return None, "query_too_short"
    relevant = [_expected_to_matcher(ref) for ref in feedback.expected]
    relevant = [item for item in relevant if item]
    if not relevant and feedback.outcome == "helpful":
        relevant = [_result_to_matcher(ref) for ref in feedback.selected_results]
        relevant = [item for item in relevant if item]
    if not relevant:
        return None, "no_usable_relevant_matcher"
    tags = ["feedback", feedback.outcome]
    notes = f"Feedback {feedback.feedback_id}; outcome={feedback.outcome}"
    if feedback.operator_note:
        notes = f"{notes}; operator_note={feedback.operator_note}"
    return (
        {
            "id": f"feedback-{feedback.feedback_id}",
            "query": query,
            "kb_name": feedback.kb_name,
            "relevant": relevant,
            "tags": tags,
            "notes": notes,
        },
        "",
    )


def _expected_to_matcher(ref: FeedbackExpectedRef) -> dict[str, Any]:
    matcher: dict[str, Any] = {}
    if ref.source_file:
        matcher["source_file"] = ref.source_file
    if ref.header:
        matcher["header"] = ref.header
    if ref.anchor_key:
        matcher["anchor_key"] = ref.anchor_key
    if ref.text_contains:
        matcher["text_contains"] = list(ref.text_contains)
    if ref.metadata:
        matcher["metadata"] = dict(ref.metadata)
    return matcher


def _result_to_matcher(ref: FeedbackResultRef) -> dict[str, Any]:
    matcher: dict[str, Any] = {}
    if ref.source_file:
        matcher["source_file"] = ref.source_file
    if ref.header:
        matcher["header"] = ref.header
    if ref.anchor_key:
        matcher["anchor_key"] = ref.anchor_key
    if ref.manual_id:
        matcher["metadata"] = {"manual_id": ref.manual_id}
    return matcher


def _read_feedback_log(kb_name: str, settings: Settings) -> list[SearchFeedback]:
    path = feedback_log_path(kb_name, settings)
    if not path.exists():
        return []
    rows: list[SearchFeedback] = []
    for line_number, line in enumerate(path.read_text(encoding="utf-8").splitlines(), 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise ServiceError(ErrorCode.STORAGE_LOAD_FAILED, "Feedback log contains invalid JSON.", {"path": str(path), "line": line_number}) from exc
        if not isinstance(raw, dict):
            raise ServiceError(ErrorCode.STORAGE_LOAD_FAILED, "Feedback log row must be an object.", {"path": str(path), "line": line_number})
        rows.append(feedback_from_payload(kb_name, raw))
    return rows


def _read_review_overlay(kb_name: str, settings: Settings) -> dict[str, dict[str, Any]]:
    path = review_overlay_path(kb_name, settings)
    if not path.exists():
        return {}
    try:
        raw = json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ServiceError(ErrorCode.STORAGE_LOAD_FAILED, "Feedback review overlay contains invalid JSON.", {"path": str(path)}) from exc
    if not isinstance(raw, dict):
        raise ServiceError(ErrorCode.STORAGE_LOAD_FAILED, "Feedback review overlay must be an object.", {"path": str(path)})
    return {str(key): dict(value) for key, value in raw.items() if isinstance(value, dict)}


def _write_review_overlay(kb_name: str, settings: Settings, overlays: dict[str, dict[str, Any]]) -> None:
    path = review_overlay_path(kb_name, settings)

    def _write(tmp: Path) -> None:
        tmp.write_text(json.dumps(overlays, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")

    atomic_write(path, _write)


def _apply_overlay(feedback: SearchFeedback, overlay: Mapping[str, Any]) -> SearchFeedback:
    status = str(overlay.get("status") or feedback.status)
    operator_note = str(overlay.get("operator_note") or feedback.operator_note)
    if status not in STATUSES:
        status = feedback.status
    return SearchFeedback(
        feedback_id=feedback.feedback_id,
        kb_name=feedback.kb_name,
        trace_id=feedback.trace_id,
        search_id=feedback.search_id,
        retrieve_id=feedback.retrieve_id,
        build_id=feedback.build_id,
        query=feedback.query,
        outcome=feedback.outcome,
        created_at=feedback.created_at,
        selected_results=feedback.selected_results,
        selected_evidence_ids=feedback.selected_evidence_ids,
        selected_context_item_ids=feedback.selected_context_item_ids,
        answerable=feedback.answerable,
        failure_reason=feedback.failure_reason,
        expected=feedback.expected,
        note=feedback.note,
        status=status,  # type: ignore[arg-type]
        operator_note=operator_note,
        plan_id=feedback.plan_id,
    )


def _parse_result_refs(raw: Any) -> tuple[FeedbackResultRef, ...]:
    if raw in (None, ""):
        return ()
    if not isinstance(raw, list):
        raise ServiceError(ErrorCode.INVALID_INPUT, "selected_results must be a list.")
    if len(raw) > MAX_REFS:
        raise ServiceError(ErrorCode.INVALID_INPUT, "selected_results exceeds maximum length.", {"max": MAX_REFS})
    refs: list[FeedbackResultRef] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ServiceError(ErrorCode.INVALID_INPUT, "selected_results entries must be objects.")
        refs.append(
            FeedbackResultRef(
                rank=_optional_int(item.get("rank"), "rank"),
                node_id=_optional_int(item.get("node_id"), "node_id"),
                anchor_key=_bounded_text(str(item.get("anchor_key") or ""), "anchor_key", 200),
                source_file=_bounded_path_text(str(item.get("source_file") or ""), "source_file"),
                header=_bounded_text(str(item.get("header") or ""), "header", 200),
                manual_id=_bounded_text(str(item.get("manual_id") or ""), "manual_id", 200),
            )
        )
    return tuple(refs)


def _parse_id_list(raw: Any, field_name: str) -> tuple[str, ...]:
    if raw in (None, ""):
        return ()
    if not isinstance(raw, list):
        raise ServiceError(ErrorCode.INVALID_INPUT, f"{field_name} must be a list.")
    if len(raw) > MAX_REFS:
        raise ServiceError(ErrorCode.INVALID_INPUT, f"{field_name} exceeds maximum length.", {"max": MAX_REFS})
    return tuple(_bounded_text(str(item), field_name, 120, required=True) for item in raw)


def _parse_optional_bool(raw: Any) -> bool | None:
    if raw is None or raw == "":
        return None
    if isinstance(raw, bool):
        return raw
    raise ServiceError(ErrorCode.INVALID_INPUT, "answerable must be a boolean when provided.")


def _parse_expected_refs(raw: Any) -> tuple[FeedbackExpectedRef, ...]:
    if raw in (None, ""):
        return ()
    if not isinstance(raw, list):
        raise ServiceError(ErrorCode.INVALID_INPUT, "expected must be a list.")
    if len(raw) > MAX_REFS:
        raise ServiceError(ErrorCode.INVALID_INPUT, "expected exceeds maximum length.", {"max": MAX_REFS})
    refs: list[FeedbackExpectedRef] = []
    for item in raw:
        if not isinstance(item, dict):
            raise ServiceError(ErrorCode.INVALID_INPUT, "expected entries must be objects.")
        refs.append(
            FeedbackExpectedRef(
                source_file=_bounded_path_text(str(item.get("source_file") or ""), "source_file"),
                header=_bounded_text(str(item.get("header") or ""), "header", 200),
                anchor_key=_bounded_text(str(item.get("anchor_key") or ""), "anchor_key", 200),
                text_contains=_parse_text_contains(item.get("text_contains")),
                metadata=_parse_metadata(item.get("metadata")),
            )
        )
    return tuple(refs)


def _parse_text_contains(raw: Any) -> tuple[str, ...]:
    if raw in (None, ""):
        return ()
    items = [raw] if isinstance(raw, str) else raw
    if not isinstance(items, list):
        raise ServiceError(ErrorCode.INVALID_INPUT, "text_contains must be a string or list of strings.")
    if len(items) > MAX_TEXT_CONTAINS_ITEMS:
        raise ServiceError(ErrorCode.INVALID_INPUT, "text_contains has too many items.", {"max": MAX_TEXT_CONTAINS_ITEMS})
    return tuple(_bounded_text(str(item), "text_contains", MAX_TEXT_CONTAINS_CHARS, required=True) for item in items)


def _parse_metadata(raw: Any) -> dict[str, Any]:
    if raw in (None, ""):
        return {}
    if not isinstance(raw, dict):
        raise ServiceError(ErrorCode.INVALID_INPUT, "metadata must be an object.")
    safe: dict[str, Any] = {}
    for key, value in raw.items():
        text_key = _bounded_text(str(key), "metadata key", 80, required=True)
        if isinstance(value, (str, int, float, bool)) or value is None:
            safe[text_key] = _bounded_text(str(value), f"metadata.{text_key}", 200) if isinstance(value, str) else value
        else:
            raise ServiceError(ErrorCode.INVALID_INPUT, "metadata values must be scalar.", {"key": text_key})
    return safe


def _existing_case_ids(path: Path) -> set[str]:
    if not path.exists():
        return set()
    ids: set[str] = set()
    for line in path.read_text(encoding="utf-8").splitlines():
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(raw, dict) and isinstance(raw.get("id"), str):
            ids.add(raw["id"])
    return ids


def _feedback_id(payload: Mapping[str, Any]) -> str:
    raw = str(payload.get("feedback_id") or "").strip()
    if raw:
        return _bounded_text(raw, "feedback_id", 120)
    seed = json.dumps(
        {
            "kb_name": payload.get("kb_name"),
            "trace_id": payload.get("trace_id"),
            "search_id": payload.get("search_id"),
            "query": payload.get("query"),
            "outcome": payload.get("outcome"),
            "uuid": uuid.uuid4().hex,
        },
        ensure_ascii=False,
        sort_keys=True,
    )
    return hashlib.sha256(seed.encode("utf-8")).hexdigest()[:16]


def _kb_feedback_root(kb_name: str, settings: Settings) -> Path:
    root = Path(settings.storage.data_dir).resolve()
    kb = _safe_name(kb_name, "kb_name")
    return _safe_child(root, root / kb / "feedback")


def _safe_name(value: str, field_name: str) -> str:
    text = _bounded_text(str(value), field_name, 120, required=True)
    if text in {".", ".."} or "/" in text or "\\" in text:
        raise ServiceError(ErrorCode.INVALID_INPUT, f"{field_name} is not path-safe.", {field_name: value})
    return text


def _safe_child(root: Path, candidate: str | Path) -> Path:
    root = root.resolve()
    path = (root / candidate).resolve() if isinstance(candidate, str) else candidate.resolve()
    try:
        path.relative_to(root)
    except ValueError as exc:
        raise ServiceError(ErrorCode.INVALID_INPUT, "Path must stay under the configured root.", {"path": str(path), "root": str(root)}) from exc
    return path


def _bounded_text(value: str, field_name: str, max_chars: int, *, required: bool = False) -> str:
    text = value.strip()
    if required and not text:
        raise ServiceError(ErrorCode.INVALID_INPUT, f"{field_name} is required.", {"field": field_name})
    if len(text) > max_chars:
        raise ServiceError(ErrorCode.INVALID_INPUT, f"{field_name} exceeds maximum length.", {"field": field_name, "max": max_chars})
    return text


def _bounded_path_text(value: str, field_name: str) -> str:
    text = _bounded_text(value, field_name, 300)
    if text.startswith("/") or "\\" in text or any(part == ".." for part in Path(text).parts):
        raise ServiceError(ErrorCode.INVALID_INPUT, f"{field_name} is not path-safe.", {"field": field_name})
    return text


def _optional_int(value: Any, field_name: str) -> int | None:
    if value is None or value == "":
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError) as exc:
        raise ServiceError(ErrorCode.INVALID_INPUT, f"{field_name} must be an integer.", {"field": field_name}) from exc
    if parsed < 0:
        raise ServiceError(ErrorCode.INVALID_INPUT, f"{field_name} must be non-negative.", {"field": field_name})
    return parsed


def _bounded_limit(limit: int) -> int:
    try:
        parsed = int(limit)
    except (TypeError, ValueError) as exc:
        raise ServiceError(ErrorCode.INVALID_INPUT, "limit must be an integer.") from exc
    if parsed <= 0:
        raise ServiceError(ErrorCode.INVALID_INPUT, "limit must be positive.", {"limit": limit})
    return min(parsed, MAX_LIMIT)


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()
