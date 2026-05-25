from __future__ import annotations

from dataclasses import dataclass

from tagmemorag.qa_context import context_meta, contextual_question, normalize_question, trim_context_text


@dataclass
class Turn:
    question: str
    answer: str | None = None


def test_contextual_question_returns_normalized_question_without_context():
    assert contextual_question("  蒸汽   很小怎么办？  ", []) == "蒸汽 很小怎么办？"


def test_contextual_question_uses_last_two_turns_and_trims_text():
    turns = [
        Turn("first ignored", "ignored"),
        Turn(" CM1  蒸汽很小怎么办？ ", "  清洁喷嘴并检查水箱。 "),
        Turn("还是不行？", "需要等待预热完成。"),
    ]

    text = contextual_question("  下一步呢？ ", turns)

    assert text == (
        "Previous question: CM1 蒸汽很小怎么办？\n"
        "Previous answer: 清洁喷嘴并检查水箱。\n\n"
        "Previous question: 还是不行？\n"
        "Previous answer: 需要等待预热完成。\n\n"
        "Current follow-up question: 下一步呢？"
    )


def test_context_meta_summarizes_only_recent_questions():
    turns = [
        Turn("ignored"),
        Turn(" " * 2),
        Turn("CM1 蒸汽很小怎么办？", "answer"),
    ]

    assert context_meta(turns) == {"applied": True, "summary": [{"question": "CM1 蒸汽很小怎么办？"}]}


def test_trim_context_text_normalizes_before_clipping():
    assert trim_context_text("  abc   def  ", 5) == "abc d"
    assert normalize_question("  a\n b\tc  ") == "a b c"
