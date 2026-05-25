from __future__ import annotations

from dataclasses import dataclass
import re
from typing import Sequence

from .types import Result


_TERM_RE = re.compile(r"[a-z0-9\u3400-\u9fff]+", re.IGNORECASE)
_DEFINITION_PATTERNS = (
    r"\bis (?:a|an|the)\b",
    r"\bare (?:a|an|the|written|used|available)\b",
    r"\bmeans\b",
    r"\brefers to\b",
    r"\bas (?:a|an|the)\b",
    r"\bcontains?\b",
    r"\binclude?s?\b",
)
_ACTION_PATTERNS = (
    r"\bmust\b",
    r"\bshould\b",
    r"\bcan\b",
    r"\bif\b",
    r"\bwhen\b",
    r"\bchoose\b",
    r"\bselect\b",
    r"\buse\b",
    r"\bopen\b",
    r"\bclick\b",
    r"請",
    r"如果",
    r"使用",
    r"選擇",
)
_CHROME_CUES = (
    "source:",
    "navigation",
    "copy as markdown",
    "article ",
    "next :",
    "previous",
    "table of contents",
)


@dataclass(frozen=True)
class SamePageOrderingOptions:
    enabled: bool = False
    min_group_size: int = 2
    rank_one_min_usefulness: float = 0.55
    rank_one_min_score_lead: float = 0.15


@dataclass(frozen=True)
class _ScoredResult:
    result: Result
    original_rank: int
    coverage: float
    usefulness: float


def order_same_page_results(
    results: Sequence[Result],
    *,
    query_text: str,
    options: SamePageOrderingOptions | None = None,
) -> list[Result]:
    opts = options or SamePageOrderingOptions()
    ordered = list(results)
    if not opts.enabled or len(ordered) < max(2, int(opts.min_group_size)):
        return ordered
    if not _same_page_dominant(ordered, min_group_size=opts.min_group_size):
        return ordered
    query_terms = _terms(query_text)
    scored = [_score_result(result, rank=index + 1, query_terms=query_terms) for index, result in enumerate(ordered)]
    if scored[0].usefulness >= float(opts.rank_one_min_usefulness):
        return ordered
    if _rank_one_has_equivalent_top_score_peer(scored):
        return ordered
    if _rank_one_score_lead(scored) >= float(opts.rank_one_min_score_lead):
        return ordered
    first_useful_rank = _first_useful_rank(scored)
    if first_useful_rank is None or first_useful_rank <= 1:
        return ordered
    return [
        item.result
        for item in sorted(
            scored,
            key=lambda item: (
                -item.usefulness,
                -item.coverage,
                -float(item.result.score),
                item.original_rank,
            ),
        )
    ]


def _score_result(result: Result, *, rank: int, query_terms: set[str]) -> _ScoredResult:
    text = f"{result.header}\n{result.text}"
    coverage = _query_coverage(text, query_terms)
    definition_cues = _regex_count(text, _DEFINITION_PATTERNS)
    action_cues = _regex_count(text, _ACTION_PATTERNS)
    chrome_cues = _cue_count(text, _CHROME_CUES)
    return _ScoredResult(
        result=result,
        original_rank=rank,
        coverage=round(coverage, 6),
        usefulness=round(
            _usefulness_score(
                text,
                coverage=coverage,
                definition_cues=definition_cues,
                action_cues=action_cues,
                chrome_cues=chrome_cues,
            ),
            6,
        ),
    )


def _same_page_dominant(results: Sequence[Result], *, min_group_size: int) -> bool:
    return max(
        _highest_count(result.source_file for result in results),
        _highest_count(result.header for result in results),
    ) >= max(2, int(min_group_size))


def _first_useful_rank(scored: Sequence[_ScoredResult]) -> int | None:
    if not scored:
        return None
    best = max(item.usefulness for item in scored)
    if best <= 0.0:
        return None
    threshold = max(0.45, best - 1e-9)
    for rank, item in enumerate(scored, 1):
        if item.usefulness >= threshold:
            return rank
    return None


def _rank_one_score_lead(scored: Sequence[_ScoredResult]) -> float:
    if len(scored) < 2:
        return 0.0
    rank_one_score = float(scored[0].result.score)
    next_best = max(float(item.result.score) for item in scored[1:])
    return rank_one_score - next_best


def _rank_one_has_equivalent_top_score_peer(scored: Sequence[_ScoredResult]) -> bool:
    if len(scored) < 2:
        return False
    rank_one_score = float(scored[0].result.score)
    peers = [
        item
        for item in scored[1:]
        if abs(rank_one_score - float(item.result.score)) <= 1e-6
    ]
    if not peers:
        return False
    return max(item.usefulness for item in peers) <= scored[0].usefulness + 1e-9


def _usefulness_score(
    text: str,
    *,
    coverage: float,
    definition_cues: int,
    action_cues: int,
    chrome_cues: int,
) -> float:
    if not str(text).strip():
        return 0.0
    score = min(0.4, coverage)
    score += min(0.36, 0.12 * definition_cues)
    if coverage >= 0.35:
        score += min(0.12, 0.04 * action_cues)
    if _has_leading_chrome(text) or chrome_cues:
        score -= min(0.2, 0.08 * max(1, chrome_cues))
    return max(0.0, score)


def _terms(text: str) -> set[str]:
    return {token.lower() for token in _TERM_RE.findall(text) if len(token) >= 2}


def _query_coverage(text: str, query_terms: set[str]) -> float:
    if not query_terms:
        return 0.0
    terms = _terms(text)
    return len(terms.intersection(query_terms)) / max(1, len(query_terms))


def _regex_count(text: str, patterns: tuple[str, ...]) -> int:
    normalized = f" {str(text).lower()} "
    return sum(1 for pattern in patterns if re.search(pattern, normalized))


def _cue_count(text: str, cues: tuple[str, ...]) -> int:
    lowered = f" {str(text).lower()} "
    return sum(1 for cue in cues if cue in lowered)


def _has_leading_chrome(text: str) -> bool:
    normalized = re.sub(r"\s+", " ", str(text).lower()).strip()
    return "source: http" in normalized[:180] or "navigation" in normalized[:180]


def _highest_count(values) -> int:
    counts: dict[str, int] = {}
    for value in values:
        if not value:
            continue
        counts[str(value)] = counts.get(str(value), 0) + 1
    return max(counts.values(), default=0)
