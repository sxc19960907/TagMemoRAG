from __future__ import annotations

import re
from enum import Enum


class AnswerIntent(str, Enum):
    GENERIC = "generic"
    TROUBLESHOOTING = "troubleshooting"


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

GENERIC_DOCUMENTATION_TERMS = (
    "api",
    "apis",
    "branch",
    "branches",
    "commit",
    "commits",
    "docs",
    "documentation",
    "github",
    "markdown",
    "pull request",
    "readme",
    "repository",
    "repositories",
    "tutorial",
    "workflow",
)


def classify_answer_intent(question: str) -> AnswerIntent:
    if contains_any(question, GENERIC_DOCUMENTATION_TERMS):
        return AnswerIntent.GENERIC
    if contains_any(question, TROUBLESHOOTING_QUESTION_TERMS):
        return AnswerIntent.TROUBLESHOOTING
    return AnswerIntent.GENERIC


def contains_any(text: str, needles: tuple[str, ...]) -> bool:
    lowered = text.casefold()
    for needle in needles:
        normalized = needle.casefold()
        if _uses_ascii_word_boundaries(normalized):
            pattern = r"\b" + re.escape(normalized).replace(r"\ ", r"\s+") + r"\b"
            if re.search(pattern, lowered):
                return True
            continue
        if normalized in lowered:
            return True
    return False


def _uses_ascii_word_boundaries(value: str) -> bool:
    return all(char.isalnum() or char.isspace() or char in "-_" for char in value) and any(
        char.isascii() and char.isalnum() for char in value
    )
