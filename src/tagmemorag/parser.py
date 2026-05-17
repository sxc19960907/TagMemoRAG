from __future__ import annotations

from pathlib import Path
import re
from typing import Any

from pypdf import PdfReader

from .types import Chunk

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SUPPORTED_DOCUMENT_SUFFIXES = {".md", ".txt", ".pdf"}
PDF_SECTION_KEYWORDS = {
    "appliance description",
    "before first use",
    "care",
    "child safety",
    "cleaning",
    "controls",
    "cooking system",
    "display",
    "installation",
    "ionizer",
    "maintenance",
    "operation",
    "program",
    "programmes",
    "safety",
    "settings",
    "steam clean",
    "troubleshooting",
    "use",
    "warning",
    "warnings",
    "故障",
    "保養",
    "兒童",
    "安全",
    "安裝",
    "操作",
    "控制",
    "清潔",
    "程序",
    "維護",
    "设置",
    "安全",
    "安装",
    "操作",
    "控制",
    "清洁",
    "维护",
}
PDF_NUMBERED_HEADING_RE = re.compile(r"^(?:\d{1,2}(?:[.)．、]|\.\d{1,2})|[A-Z]\.)\s+\S+")
PDF_PAGE_NUMBER_RE = re.compile(r"^(?:page\s*)?\d{1,3}$", re.IGNORECASE)
PDF_TOC_LEADER_RE = re.compile(r"\.{3,}\s*\d{1,3}$")
PDF_CONTROL_CHAR_RE = re.compile(r"[\x00-\x08\x0b-\x1f\x7f-\x9f]")
PDF_MOJIBAKE_RE = re.compile(r"[\u0001-\u001f\ufffd]")
PDF_MANUALSLIB_NOISE = (
    "manualslib.com",
    "the global manuals library",
    "other manualslib projects",
    "manuals / brands /",
    "quick links",
)


def parse_document(
    path: str | Path,
    max_chars: int = 500,
    min_chars: int = 50,
    root_dir: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[Chunk]:
    file_path = Path(path)
    source_file = str(file_path.relative_to(root_dir)) if root_dir else file_path.name
    chunk_metadata = dict(metadata or {})
    if file_path.suffix.lower() == ".pdf":
        return _parse_pdf(
            file_path,
            source_file=source_file,
            max_chars=max_chars,
            min_chars=min_chars,
            metadata=chunk_metadata,
        )
    text = file_path.read_text(encoding="utf-8")
    if not text.strip():
        return []

    headings: dict[int, str] = {}
    current_lines: list[str] = []
    current_header = ""
    current_level = 0
    current_start = 1
    raw_chunks: list[Chunk] = []

    def current_path() -> tuple[str, ...]:
        if not headings:
            return ("",)
        return tuple(headings[i] for i in sorted(headings) if i <= current_level)

    def flush() -> None:
        nonlocal current_lines
        body = "\n".join(current_lines).strip()
        if not body:
            current_lines = []
            return
        raw_chunks.append(
            Chunk(
                text=body,
                header=current_header,
                path=current_path(),
                level=current_level,
                start_line=current_start,
                source_file=source_file,
                metadata=dict(chunk_metadata),
            )
        )
        current_lines = []

    for lineno, line in enumerate(text.splitlines(), 1):
        match = HEADING_RE.match(line)
        if match:
            flush()
            current_level = len(match.group(1))
            current_header = match.group(2).strip()
            headings = {level: title for level, title in headings.items() if level < current_level}
            headings[current_level] = current_header
            current_start = lineno
            current_lines = [current_header]
        else:
            if not current_lines:
                current_start = lineno
            current_lines.append(line)
    flush()

    return _post_process(raw_chunks, max_chars=max_chars, min_chars=min_chars)


def _parse_pdf(
    file_path: Path,
    *,
    source_file: str,
    max_chars: int,
    min_chars: int,
    metadata: dict[str, Any],
) -> list[Chunk]:
    reader = PdfReader(str(file_path))
    raw_chunks: list[Chunk] = []
    for index, page in enumerate(reader.pages, 1):
        text = _extract_pdf_page_text(page)
        lines = _pdf_lines(text)
        if not lines:
            continue
        raw_chunks.extend(
            _pdf_page_chunks(
                lines,
                page_number=index,
                source_file=source_file,
                metadata=metadata,
            )
        )
    return _post_process(raw_chunks, max_chars=max_chars, min_chars=min_chars)


def _extract_pdf_page_text(page: Any) -> str:
    try:
        return str(page.extract_text(extraction_mode="layout") or "").strip()
    except TypeError:
        return str(page.extract_text() or "").strip()


def _pdf_lines(text: str) -> list[str]:
    lines: list[str] = []
    for raw_line in text.splitlines():
        line = re.sub(r"\s+", " ", raw_line).strip()
        if line and not _is_pdf_noise_line(line):
            lines.append(line)
    return lines


def _pdf_page_chunks(
    lines: list[str],
    *,
    page_number: int,
    source_file: str,
    metadata: dict[str, Any],
) -> list[Chunk]:
    heading_indexes = [idx for idx, line in enumerate(lines) if _is_pdf_heading(line)]
    if not heading_indexes:
        return [
            _make_pdf_chunk(
                "\n".join(lines),
                header=f"Page {page_number}",
                path=(f"Page {page_number}",),
                page_number=page_number,
                source_file=source_file,
                metadata=metadata,
                header_source="page_fallback",
            )
        ]

    chunks: list[Chunk] = []
    if heading_indexes[0] > 0:
        preface = "\n".join(lines[: heading_indexes[0]]).strip()
        if preface:
            chunks.append(
                _make_pdf_chunk(
                    preface,
                    header=f"Page {page_number}",
                    path=(f"Page {page_number}",),
                    page_number=page_number,
                    source_file=source_file,
                    metadata=metadata,
                    header_source="page_fallback",
                )
            )
    for offset, start in enumerate(heading_indexes):
        end = heading_indexes[offset + 1] if offset + 1 < len(heading_indexes) else len(lines)
        block_lines = lines[start:end]
        body = "\n".join(block_lines).strip()
        if not body:
            continue
        if len(block_lines) == 1 and _is_low_value_standalone_pdf_heading(block_lines[0]):
            continue
        header = _clean_pdf_heading(block_lines[0])
        chunks.append(
            _make_pdf_chunk(
                body,
                header=header,
                path=(header,),
                page_number=page_number,
                source_file=source_file,
                metadata=metadata,
                header_source="detected",
            )
        )
    if chunks:
        return chunks
    return [
        _make_pdf_chunk(
            "\n".join(lines),
            header=f"Page {page_number}",
            path=(f"Page {page_number}",),
            page_number=page_number,
            source_file=source_file,
            metadata=metadata,
            header_source="page_fallback",
        )
    ]


def _make_pdf_chunk(
    text: str,
    *,
    header: str,
    path: tuple[str, ...],
    page_number: int,
    source_file: str,
    metadata: dict[str, Any],
    header_source: str,
) -> Chunk:
    chunk_metadata = dict(metadata)
    chunk_metadata["page_start"] = int(page_number)
    chunk_metadata["page_end"] = int(page_number)
    chunk_metadata["pdf_header_source"] = header_source
    return Chunk(
        text=text,
        header=header,
        path=path,
        level=1,
        start_line=int(page_number),
        source_file=source_file,
        metadata=chunk_metadata,
    )


def _is_pdf_heading(line: str) -> bool:
    normalized = _normalize_pdf_heading_candidate(line)
    if not normalized:
        return False
    if _is_pdf_noise_line(normalized):
        return False
    if PDF_PAGE_NUMBER_RE.match(normalized) or PDF_TOC_LEADER_RE.search(normalized):
        return False
    if len(normalized) > 96:
        return False
    if PDF_NUMBERED_HEADING_RE.match(normalized):
        return True
    lowered = normalized.lower().strip(":-")
    if lowered in PDF_SECTION_KEYWORDS:
        return True
    if any(keyword in lowered for keyword in PDF_SECTION_KEYWORDS if len(keyword) >= 6):
        return len(normalized) <= 72 and len(lowered.split()) <= 6 and not normalized.endswith((".", ",", ";"))
    if _has_cjk(normalized):
        return len(normalized) <= 18 and not normalized.endswith(("。", "，", "；", "："))
    words = lowered.split()
    if 1 <= len(words) <= 6 and _is_title_like(normalized):
        return True
    return False


def _clean_pdf_heading(line: str) -> str:
    return _normalize_pdf_heading_candidate(line).strip(":-") or line.strip()


def _normalize_pdf_heading_candidate(line: str) -> str:
    value = re.sub(r"\s+", " ", line).strip()
    return value.strip()


def _is_pdf_noise_line(line: str) -> bool:
    normalized = _normalize_pdf_heading_candidate(line)
    if not normalized:
        return True
    lowered = normalized.lower()
    if any(noise in lowered for noise in PDF_MANUALSLIB_NOISE):
        return True
    if PDF_TOC_LEADER_RE.search(normalized):
        return True
    if _looks_like_mojibake(normalized):
        return True
    if _looks_like_toc_mixed_line(normalized):
        return True
    return False


def _is_low_value_standalone_pdf_heading(line: str) -> bool:
    normalized = _clean_pdf_heading(line)
    lowered = normalized.lower()
    if lowered in {"manual", "operation manual", "user’s operation manual", "user's operation manual", "table of contents", "目錄"}:
        return True
    if "hisense" in lowered and ("manual" in lowered or "instructions" in lowered or "user" in lowered):
        return True
    if re.fullmatch(r"[A-Z]{2,}\d+[A-Z0-9* -]*", normalized):
        return True
    if re.fullmatch(r"ASKO\s*W?\d+", normalized, flags=re.IGNORECASE):
        return True
    return False


def _looks_like_mojibake(value: str) -> bool:
    if PDF_MOJIBAKE_RE.search(value) or PDF_CONTROL_CHAR_RE.search(value):
        return True
    if not value:
        return False
    printable = sum(1 for char in value if char.isprintable() and (char.isalnum() or char.isspace() or char in ".,:;!?()/-&'’"))
    return len(value) >= 12 and printable / len(value) < 0.55


def _looks_like_toc_mixed_line(value: str) -> bool:
    tokens = value.split()
    if len(tokens) < 4:
        return False
    digit_tokens = sum(1 for token in tokens if token.strip(".") .isdigit())
    short_tokens = sum(1 for token in tokens if len(token) <= 3)
    if _has_cjk(value) and digit_tokens >= 2:
        return True
    return digit_tokens >= 2 and short_tokens / len(tokens) >= 0.35


def _has_cjk(value: str) -> bool:
    return bool(re.search(r"[\u4e00-\u9fff]", value))


def _is_title_like(value: str) -> bool:
    letters = [char for char in value if char.isalpha()]
    if not letters:
        return False
    if value.endswith((".", ",", ";")):
        return False
    uppercase = sum(1 for char in letters if char.isupper())
    titlecase_words = sum(1 for word in value.split() if word[:1].isupper())
    return uppercase / max(len(letters), 1) >= 0.6 or titlecase_words >= max(1, len(value.split()) - 1)


def _post_process(chunks: list[Chunk], max_chars: int, min_chars: int) -> list[Chunk]:
    split_chunks: list[Chunk] = []
    for chunk in chunks:
        if len(chunk.text) <= max_chars:
            split_chunks.append(chunk)
            continue
        parts = _split_long_text(chunk.text, max_chars)
        for offset, part in enumerate(parts):
            split_chunks.append(
                Chunk(
                    text=part,
                    header=chunk.header,
                    path=chunk.path,
                    level=chunk.level,
                    start_line=chunk.start_line + offset,
                    source_file=chunk.source_file,
                    metadata=dict(chunk.metadata),
                )
            )

    merged: list[Chunk] = []
    for chunk in split_chunks:
        if merged and len(chunk.text) < min_chars and merged[-1].path == chunk.path:
            prev = merged[-1]
            merged[-1] = Chunk(
                text=(prev.text.rstrip() + "\n" + chunk.text).strip(),
                header=prev.header,
                path=prev.path,
                level=prev.level,
                start_line=prev.start_line,
                source_file=prev.source_file,
                metadata=dict(prev.metadata),
            )
        else:
            merged.append(chunk)
    return merged


def _split_long_text(text: str, max_chars: int) -> list[str]:
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    parts: list[str] = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
        elif len(current) + len(para) + 2 <= max_chars:
            current += "\n\n" + para
        else:
            parts.extend(_hard_split(current, max_chars))
            current = para
    if current:
        parts.extend(_hard_split(current, max_chars))
    return parts


def _hard_split(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    return [text[i : i + max_chars].strip() for i in range(0, len(text), max_chars) if text[i : i + max_chars].strip()]
