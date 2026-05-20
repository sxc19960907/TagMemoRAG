"""Rule-based intent classifier (Architecture v2 § A2 / Decision D2).

T2 emits two values: `TEXT_ANSWER` (default) and `OUT_OF_SCOPE` (matches
keyword in the query). Future tasks (T6 /answer) may expand to the full
6-value enum once routing consumers exist.
"""

from __future__ import annotations

from typing import TYPE_CHECKING

from .plan import Intent

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings


# Default keyword list. Cheap, conservative, multilingual.
# Settings.queryplan.out_of_scope_keywords overrides if non-None.
DEFAULT_OUT_OF_SCOPE_KEYWORDS: tuple[str, ...] = (
    "今天天气",
    "几点了",
    "翻译成英文",
    "翻译成中文",
    "股票",
    "新闻",
    "today's weather",
    "what time is it",
    "translate this",
    "stock price",
)


def classify_intent(question: str, kb_name: str, settings: "Settings") -> Intent:
    """Classify a query into an Intent.

    T2 implementation: keyword matching against an optional
    Settings.queryplan.out_of_scope_keywords (or DEFAULT if None).
    Case-insensitive substring match.
    """
    keywords = settings.queryplan.out_of_scope_keywords
    if keywords is None:
        keywords = list(DEFAULT_OUT_OF_SCOPE_KEYWORDS)
    if not keywords:
        return Intent.TEXT_ANSWER
    lowered = question.lower()
    for kw in keywords:
        if kw.lower() in lowered:
            return Intent.OUT_OF_SCOPE
    return Intent.TEXT_ANSWER


__all__ = ["classify_intent", "DEFAULT_OUT_OF_SCOPE_KEYWORDS"]
