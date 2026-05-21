from __future__ import annotations

import hashlib
from dataclasses import dataclass
from typing import Any

from ..state import AgentStepCtx, ToolObservation


@dataclass(frozen=True)
class RewriteTool:
    name: str = "rewrite"
    description: str = "Rewrite a query for the next retrieval step."
    input_schema: dict[str, Any] = None  # type: ignore[assignment]

    def __post_init__(self) -> None:
        if self.input_schema is None:
            object.__setattr__(
                self,
                "input_schema",
                {
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "reason": {"type": "string"},
                        "append_terms": {
                            "type": "array",
                            "items": {"type": "string"},
                        },
                    },
                    "required": ["query"],
                },
            )

    def __call__(self, args: dict[str, Any], ctx: AgentStepCtx) -> ToolObservation:
        original = _normalize_query(str(args.get("query") or ""))
        terms = _append_terms(args.get("append_terms"))
        rewritten = _append_unique_terms(original, terms)
        changed = rewritten != original
        return ToolObservation(
            payload={
                "query": rewritten,
                "original_query_hash": hashlib.sha256(original.encode("utf-8")).hexdigest(),
                "changed": changed,
                "reason": str(args.get("reason") or ("c3_append_terms" if changed else "c3_no_terms_identity")),
            }
        )


def _normalize_query(query: str) -> str:
    return " ".join(query.strip().split())


def _append_terms(value: Any) -> tuple[str, ...]:
    if not isinstance(value, list | tuple):
        return ()
    normalized: list[str] = []
    seen: set[str] = set()
    for item in value:
        term = _normalize_query(str(item))
        key = term.casefold()
        if term and key not in seen:
            normalized.append(term)
            seen.add(key)
    return tuple(normalized)


def _append_unique_terms(query: str, terms: tuple[str, ...]) -> str:
    if not terms:
        return query
    existing = query.casefold()
    additions = [term for term in terms if term.casefold() not in existing]
    if not additions:
        return query
    return " ".join(part for part in (query, " ".join(additions)) if part)


__all__ = ["RewriteTool"]
