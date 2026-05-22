from __future__ import annotations


def contextual_question(question: str, conversation_context: list[object]) -> str:
    current_question = normalize_question(question)
    turns: list[str] = []
    for turn in conversation_context[-2:]:
        turn_question = trim_context_text(getattr(turn, "question", None), 220)
        turn_answer = trim_context_text(getattr(turn, "answer", None), 360)
        if not turn_question:
            continue
        if turn_answer:
            turns.append(f"Previous question: {turn_question}\nPrevious answer: {turn_answer}")
        else:
            turns.append(f"Previous question: {turn_question}")
    if not turns:
        return current_question
    context = "\n\n".join(turns)
    return f"{context}\n\nCurrent follow-up question: {current_question}"


def context_meta(conversation_context: list[object]) -> dict[str, object]:
    summaries: list[dict[str, str]] = []
    for turn in conversation_context[-2:]:
        question = trim_context_text(getattr(turn, "question", None), 120)
        if question:
            summaries.append({"question": question})
    return {
        "applied": bool(summaries),
        "summary": summaries,
    }


def normalize_question(question: str) -> str:
    return " ".join(question.strip().split())


def trim_context_text(value: str | None, limit: int) -> str:
    text = normalize_question(value or "")
    return text[:limit]
