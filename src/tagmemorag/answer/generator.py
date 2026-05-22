from __future__ import annotations

import re
from typing import TYPE_CHECKING

from .base import AnswerCitation, AnswerGeneration, AnswerGenerator, AnswerRequestContext

MAX_EXTRACTIVE_EXCERPTS = 3
STEPWISE_ANSWER_PREFIX = "建议先这样处理："
GENERIC_ANSWER_PREFIX = "根据资料可确认："
SAFETY_ANSWER_PREFIX = "建议先保证安全："
UNSUPPORTED_REPAIR_PREFIX = "现有说明书证据不足，无法确认需要这样处理。"
SAFETY_TERMS = (
    "abnormal smell",
    "burning smell",
    "electric shock",
    "overheat",
    "overheating",
    "disconnect power",
    "unplug",
    "contact service",
    "异味",
    "異味",
    "漏电",
    "漏電",
    "触电",
    "觸電",
    "过热",
    "過熱",
    "持续高温",
    "持續高溫",
    "立即断电",
    "立即斷電",
    "联系售后",
    "聯絡售後",
)
UNSUPPORTED_REPAIR_TERMS = (
    "part number",
    "spare part",
    "replace",
    "replacement",
    "disassemble",
    "配件编号",
    "零件编号",
    "料号",
    "料號",
    "更换",
    "更換",
    "换泵",
    "換泵",
    "拆机",
    "拆機",
    "拆卸",
)
TROUBLESHOOTING_QUESTION_TERMS = (
    "how to",
    "what should",
    "troubleshoot",
    "fix",
    "fault",
    "problem",
    "weak",
    "low",
    "small",
    "怎么办",
    "怎麼辦",
    "如何处理",
    "如何處理",
    "怎么处理",
    "怎麼處理",
    "故障",
    "异常",
    "異常",
)
TROUBLESHOOTING_ACTION_TERMS = (
    "clean",
    "check",
    "confirm",
    "wait",
    "reset",
    "清洗",
    "清洁",
    "清潔",
    "检查",
    "檢查",
    "确认",
    "確認",
    "安装到位",
    "安裝到位",
    "预热",
    "預熱",
    "等待",
    "重启",
    "重啟",
)

if TYPE_CHECKING:  # pragma: no cover
    from ..config import Settings


class NoopAnswerGenerator:
    """Deterministic local extractive generator for offline demos and tests."""

    def __init__(self, *, model_id: str = "noop", model_version: str = "v1", prompt_version: str = "answer_prompt.v1"):
        self.model_id = model_id or "noop"
        self.model_version = model_version
        self.prompt_version = prompt_version

    def generate(self, context: AnswerRequestContext) -> AnswerGeneration:
        excerpts = _supported_excerpts(context)
        citations = tuple(AnswerCitation(citation_id) for citation_id, _excerpt in excerpts)
        text = _format_extractive_answer(context.question, excerpts) if excerpts else _insufficient_evidence_text()
        return AnswerGeneration(
            text=text,
            citations=citations,
            model_id=self.model_id,
            model_version=self.model_version,
            prompt_version=self.prompt_version,
            warnings=("answer_noop_provider",),
        )


def _supported_excerpts(context: AnswerRequestContext) -> tuple[tuple[str, str], ...]:
    allowed = set(context.prompt.allowed_citation_ids)
    candidates: list[tuple[str, str]] = []
    for item in (context.retrieve_payload.get("context_pack") or {}).get("items") or []:
        citation_id = str(item.get("citation_id") or "")
        content = _clean_excerpt(str(item.get("content") or ""))
        if citation_id in allowed and content and _is_relevant_excerpt(context.question, content):
            candidates.append((citation_id, content))
    for item in context.retrieve_payload.get("evidence") or []:
        citation_id = str(item.get("citation_id") or "")
        text = _clean_excerpt(str(item.get("text") or ""))
        if citation_id in allowed and text and _is_relevant_excerpt(context.question, text):
            candidates.append((citation_id, text))
    deduped = _dedupe_excerpts(candidates)
    if deduped:
        return tuple(deduped[:MAX_EXTRACTIVE_EXCERPTS])
    return tuple(_dedupe_excerpts(_all_supported_excerpts(context, allowed))[:MAX_EXTRACTIVE_EXCERPTS])


def _all_supported_excerpts(context: AnswerRequestContext, allowed: set[str]) -> list[tuple[str, str]]:
    out: list[tuple[str, str]] = []
    for item in (context.retrieve_payload.get("context_pack") or {}).get("items") or []:
        citation_id = str(item.get("citation_id") or "")
        content = _clean_excerpt(str(item.get("content") or ""))
        if citation_id in allowed and content:
            out.append((citation_id, content))
    for item in context.retrieve_payload.get("evidence") or []:
        citation_id = str(item.get("citation_id") or "")
        text = _clean_excerpt(str(item.get("text") or ""))
        if citation_id in allowed and text:
            out.append((citation_id, text))
    return out


def _dedupe_excerpts(candidates: list[tuple[str, str]]) -> list[tuple[str, str]]:
    seen_citations: set[str] = set()
    seen_text: set[str] = set()
    out: list[tuple[str, str]] = []
    for citation_id, excerpt in candidates:
        fingerprint = _excerpt_fingerprint(excerpt)
        if citation_id in seen_citations or fingerprint in seen_text:
            continue
        seen_citations.add(citation_id)
        seen_text.add(fingerprint)
        out.append((citation_id, excerpt))
    return out


def _excerpt_fingerprint(text: str) -> str:
    return re.sub(r"\W+", "", text.casefold())[:160]


def _format_extractive_answer(question: str, excerpts: tuple[tuple[str, str], ...]) -> str:
    if _asks_unsupported_repair(question):
        return _format_unsupported_repair_answer(excerpts)
    safety_excerpts = tuple(item for item in excerpts if _contains_any(item[1], SAFETY_TERMS))
    if safety_excerpts and _contains_any(question, SAFETY_TERMS):
        return _format_stepwise_answer(SAFETY_ANSWER_PREFIX, safety_excerpts)
    if len(excerpts) == 1:
        citation_id, excerpt = excerpts[0]
        return f"{excerpt} [{citation_id}]"
    prefix = STEPWISE_ANSWER_PREFIX if _asks_troubleshooting_question(question) else GENERIC_ANSWER_PREFIX
    return _format_stepwise_answer(prefix, excerpts)


def _format_stepwise_answer(prefix: str, excerpts: tuple[tuple[str, str], ...]) -> str:
    steps = [f"{index}. {_step_text(excerpt)} [{citation_id}]" for index, (citation_id, excerpt) in enumerate(excerpts, 1)]
    return "\n".join((prefix, *steps))


def _format_unsupported_repair_answer(excerpts: tuple[tuple[str, str], ...]) -> str:
    if len(excerpts) == 1:
        citation_id, excerpt = excerpts[0]
        return f"{UNSUPPORTED_REPAIR_PREFIX} 可确认的信息是：{_step_text(excerpt)} [{citation_id}]"
    steps = [
        f"{index}. 可确认的信息：{_step_text(excerpt)} [{citation_id}]"
        for index, (citation_id, excerpt) in enumerate(excerpts, 1)
    ]
    return "\n".join((UNSUPPORTED_REPAIR_PREFIX, *steps))


def _step_text(excerpt: str) -> str:
    text = excerpt.strip()
    if text.endswith(("。", ".", "!", "?", "！", "？")):
        return text
    return f"{text}。"


def _is_relevant_excerpt(question: str, excerpt: str) -> bool:
    if _asks_unsupported_repair(question) and _contains_any(excerpt, UNSUPPORTED_REPAIR_TERMS):
        return True
    if _contains_any(question, SAFETY_TERMS) and _contains_any(excerpt, SAFETY_TERMS):
        return True
    if (
        _contains_cjk(question)
        and _contains_any(question, TROUBLESHOOTING_QUESTION_TERMS)
        and _contains_any(excerpt, TROUBLESHOOTING_ACTION_TERMS)
    ):
        return True
    question_terms = _relevance_terms(question)
    if not question_terms:
        return True
    excerpt_terms = _relevance_terms(excerpt)
    overlap = question_terms & excerpt_terms
    if _contains_cjk(question):
        return len(overlap) >= min(2, len(question_terms))
    return len(overlap) >= min(2, len(question_terms))


def _relevance_terms(text: str) -> set[str]:
    lowered = text.casefold()
    terms = {token for token in re.findall(r"[a-z0-9]+", lowered) if len(token) >= 3}
    terms.update(char for char in lowered if _is_cjk(char) and char not in {"的", "了", "和", "是", "在", "个", "吗"})
    return terms


def _contains_cjk(text: str) -> bool:
    return any(_is_cjk(char) for char in text)


def _contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    return any(needle.casefold() in lowered for needle in needles)


def _asks_unsupported_repair(question: str) -> bool:
    return _contains_any(question, UNSUPPORTED_REPAIR_TERMS)


def _asks_troubleshooting_question(question: str) -> bool:
    return _contains_any(question, TROUBLESHOOTING_QUESTION_TERMS)


def _is_cjk(char: str) -> bool:
    return "\u4e00" <= char <= "\u9fff"


def _clean_excerpt(text: str, *, max_chars: int = 480) -> str:
    cleaned = _drop_repeated_heading(text)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    if len(cleaned) <= max_chars:
        return cleaned
    clipped = cleaned[:max_chars].rstrip()
    for mark in (". ", "; ", "! ", "? "):
        pos = clipped.rfind(mark)
        if pos >= max_chars // 3:
            return clipped[: pos + 1].strip()
    return clipped.rstrip(" ,;:")


def _drop_repeated_heading(text: str) -> str:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    if len(lines) >= 2 and lines[1].startswith(lines[0]):
        return "\n".join(lines[1:])
    if len(lines) >= 2 and _looks_like_heading(lines[0]):
        return "\n".join(lines[1:])
    return text


def _looks_like_heading(text: str) -> bool:
    return len(text) <= 80 and not re.search(r"[。.!?！？；;]", text)


def _insufficient_evidence_text() -> str:
    return "The available evidence is insufficient to produce an extractive answer."


def create_answer_generator(settings: "Settings") -> AnswerGenerator:
    cfg = settings.answer
    if cfg.provider == "noop":
        return NoopAnswerGenerator(
            model_id=cfg.model_id or "noop",
            model_version=cfg.model_version,
            prompt_version=cfg.prompt_version,
        )
    if cfg.provider == "openai_compatible":
        from .openai_compatible import OpenAICompatibleAnswerGenerator

        return OpenAICompatibleAnswerGenerator(settings)
    raise ValueError(f"Unsupported answer provider: {cfg.provider}")


__all__ = ["NoopAnswerGenerator", "create_answer_generator"]
