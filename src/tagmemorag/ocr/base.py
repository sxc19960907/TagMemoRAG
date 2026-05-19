from __future__ import annotations

from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Protocol


@dataclass(frozen=True)
class OCRPageContext:
    source_path: Path
    source_file: str
    page_number: int
    kb_name: str
    doc_id: str
    metadata: dict[str, Any] = field(default_factory=dict)


@dataclass(frozen=True)
class OCRPageResult:
    text: str
    warnings: tuple[str, ...] = ()


class OCRProvider(Protocol):
    provider_name: str
    version: str

    def recognize_pdf_page(self, context: OCRPageContext) -> OCRPageResult:
        """Return OCR text for one PDF page."""


@dataclass(frozen=True)
class OCRSummary:
    attempted: int = 0
    created: int = 0
    skipped: int = 0
    failed: int = 0
    failure_reasons: dict[str, int] = field(default_factory=dict)
    warnings: tuple[str, ...] = ()

    def merge(self, other: "OCRSummary") -> "OCRSummary":
        failure_reasons = dict(self.failure_reasons)
        for reason, count in other.failure_reasons.items():
            failure_reasons[reason] = failure_reasons.get(reason, 0) + count
        return OCRSummary(
            attempted=self.attempted + other.attempted,
            created=self.created + other.created,
            skipped=self.skipped + other.skipped,
            failed=self.failed + other.failed,
            failure_reasons=failure_reasons,
            warnings=tuple(dict.fromkeys((*self.warnings, *other.warnings))),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "attempted": self.attempted,
            "created": self.created,
            "skipped": self.skipped,
            "failed": self.failed,
            "failure_reasons": dict(sorted(self.failure_reasons.items())),
            "warnings": list(self.warnings),
        }
