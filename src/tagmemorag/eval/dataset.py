from __future__ import annotations

from dataclasses import dataclass
import json
from pathlib import Path
from typing import Any


class EvalSuiteError(Exception):
    """Raised when an eval suite or eval data is invalid."""


@dataclass(frozen=True)
class ExpectedResult:
    id: str | None = None
    source_file: str | None = None
    header: str | None = None
    anchor_key: str | None = None
    text_contains: tuple[str, ...] = ()
    metadata: dict[str, Any] | None = None
    weight: float = 1.0


@dataclass(frozen=True)
class EvalThresholds:
    min_precision_at_k: float | None = None
    min_recall_at_k: float | None = None
    min_mrr: float | None = None
    min_hit_at_k: float | None = None

    def to_dict(self) -> dict[str, float]:
        data: dict[str, float] = {}
        for key in ("min_precision_at_k", "min_recall_at_k", "min_mrr", "min_hit_at_k"):
            value = getattr(self, key)
            if value is not None:
                data[key] = value
        return data


@dataclass(frozen=True)
class EvalCase:
    id: str
    query: str
    relevant: tuple[ExpectedResult, ...]
    kb_name: str = "default"
    tags: tuple[str, ...] = ()
    notes: str = ""
    top_k_override: int | None = None
    thresholds: EvalThresholds = EvalThresholds()
    negatives: tuple[ExpectedResult, ...] = ()


def load_eval_suite(path: str | Path) -> list[EvalCase]:
    suite_path = Path(path)
    cases: list[EvalCase] = []
    seen_ids: set[str] = set()
    try:
        lines = suite_path.read_text(encoding="utf-8").splitlines()
    except OSError as exc:
        raise EvalSuiteError(f"Could not read eval suite {suite_path}: {exc}") from exc
    for line_number, line in enumerate(lines, 1):
        if not line.strip():
            continue
        try:
            raw = json.loads(line)
        except json.JSONDecodeError as exc:
            raise EvalSuiteError(f"{suite_path}:{line_number}: invalid JSON: {exc.msg}") from exc
        if not isinstance(raw, dict):
            raise EvalSuiteError(f"{suite_path}:{line_number}: each JSONL row must be an object")
        case = _parse_case(raw, suite_path, line_number)
        if case.id in seen_ids:
            raise EvalSuiteError(f"{suite_path}:{line_number}: duplicate case id: {case.id}")
        seen_ids.add(case.id)
        cases.append(case)
    if not cases:
        raise EvalSuiteError(f"{suite_path}: eval suite is empty")
    return cases


def _parse_case(raw: dict[str, Any], suite_path: Path, line_number: int) -> EvalCase:
    case_id = _required_string(raw, "id", suite_path, line_number)
    query = _required_string(raw, "query", suite_path, line_number)
    relevant_raw = raw.get("relevant")
    if not isinstance(relevant_raw, list) or not relevant_raw:
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} must include non-empty relevant list")
    relevant = tuple(_parse_expected(item, case_id, suite_path, line_number, field="relevant") for item in relevant_raw)
    negatives_raw = raw.get("negatives", [])
    if negatives_raw is None:
        negatives_raw = []
    if not isinstance(negatives_raw, list):
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} negatives must be a list")
    negatives = tuple(_parse_expected(item, case_id, suite_path, line_number, field="negatives") for item in negatives_raw)
    tags_raw = raw.get("tags", [])
    if not isinstance(tags_raw, list) or not all(isinstance(item, str) for item in tags_raw):
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} tags must be a list of strings")
    top_k_override = raw.get("top_k_override")
    if top_k_override is not None:
        if not isinstance(top_k_override, int) or top_k_override <= 0:
            raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} top_k_override must be a positive integer")
    thresholds = EvalThresholds(
        min_precision_at_k=_optional_threshold(raw, "min_precision_at_k", suite_path, line_number, case_id),
        min_recall_at_k=_optional_threshold(raw, "min_recall_at_k", suite_path, line_number, case_id),
        min_mrr=_optional_threshold(raw, "min_mrr", suite_path, line_number, case_id),
        min_hit_at_k=_optional_threshold(raw, "min_hit_at_k", suite_path, line_number, case_id),
    )
    return EvalCase(
        id=case_id,
        query=query,
        relevant=relevant,
        kb_name=str(raw.get("kb_name") or "default"),
        tags=tuple(tags_raw),
        notes=str(raw.get("notes") or ""),
        top_k_override=top_k_override,
        thresholds=thresholds,
        negatives=negatives,
    )


def _parse_expected(raw: Any, case_id: str, suite_path: Path, line_number: int, *, field: str = "relevant") -> ExpectedResult:
    if not isinstance(raw, dict):
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} {field} entries must be objects")
    text_contains_raw = raw.get("text_contains", ())
    if isinstance(text_contains_raw, str):
        text_contains = (text_contains_raw,)
    elif isinstance(text_contains_raw, list) and all(isinstance(item, str) and item for item in text_contains_raw):
        text_contains = tuple(text_contains_raw)
    elif text_contains_raw in (None, ()):
        text_contains = ()
    else:
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} text_contains must be a string or list of strings")
    expected = ExpectedResult(
        id=_optional_string(raw.get("id")),
        source_file=_optional_string(raw.get("source_file")),
        header=_optional_string(raw.get("header")),
        anchor_key=_optional_string(raw.get("anchor_key")),
        text_contains=text_contains,
        metadata=_optional_metadata(raw.get("metadata"), case_id, suite_path, line_number),
        weight=float(raw.get("weight", 1.0)),
    )
    if expected.weight <= 0:
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} {field} weight must be positive")
    if not (expected.source_file or expected.header or expected.anchor_key or expected.text_contains or expected.metadata):
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} {field} entry must include at least one matcher field")
    return expected


def _required_string(raw: dict[str, Any], key: str, suite_path: Path, line_number: int) -> str:
    value = raw.get(key)
    if not isinstance(value, str) or not value.strip():
        raise EvalSuiteError(f"{suite_path}:{line_number}: missing or empty required field: {key}")
    return value.strip()


def _optional_string(value: Any) -> str | None:
    if value is None:
        return None
    text = str(value).strip()
    return text or None


def _optional_metadata(value: Any, case_id: str, suite_path: Path, line_number: int) -> dict[str, Any] | None:
    if value is None:
        return None
    if not isinstance(value, dict) or not value:
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} metadata must be a non-empty object")
    return dict(value)


def _optional_threshold(raw: dict[str, Any], key: str, suite_path: Path, line_number: int, case_id: str) -> float | None:
    if key not in raw or raw[key] is None:
        return None
    value = float(raw[key])
    if value < 0.0 or value > 1.0:
        raise EvalSuiteError(f"{suite_path}:{line_number}: case {case_id} {key} must be between 0.0 and 1.0")
    return value
