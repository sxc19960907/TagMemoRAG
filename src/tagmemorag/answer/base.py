from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Protocol


@dataclass(frozen=True)
class AnswerCitation:
    citation_id: str

    def to_dict(self) -> dict[str, str]:
        return {"citation_id": self.citation_id}


@dataclass(frozen=True)
class AnswerGeneration:
    text: str
    citations: tuple[AnswerCitation, ...] = ()
    model_id: str = ""
    model_version: str = ""
    prompt_version: str = ""
    warnings: tuple[str, ...] = ()

    def to_answer_dict(self, *, confidence: float = 0.0) -> dict[str, Any]:
        return {
            "kind": "answer",
            "text": self.text,
            "confidence": float(confidence),
            "citations": [citation.to_dict() for citation in self.citations],
            "refusal_reason": "",
            "missing_evidence_hints": [],
            "model_id": self.model_id,
            "model_version": self.model_version,
            "prompt_version": self.prompt_version,
            "warnings": list(self.warnings),
        }


@dataclass(frozen=True)
class AnswerPrompt:
    messages: tuple[dict[str, str], ...]
    prompt_version: str
    allowed_citation_ids: frozenset[str] = field(default_factory=frozenset)


@dataclass(frozen=True)
class AnswerRequestContext:
    question: str
    retrieve_payload: dict[str, Any]
    prompt: AnswerPrompt
    max_output_tokens: int


class AnswerGenerator(Protocol):
    def generate(self, context: AnswerRequestContext) -> AnswerGeneration:
        """Generate an answer from a prepared, role-separated prompt."""


class AnswerGenerationError(RuntimeError):
    """Provider failure that should degrade to answer.kind=error."""

