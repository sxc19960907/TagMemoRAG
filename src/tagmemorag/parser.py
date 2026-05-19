from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass
from pathlib import Path
import re
from typing import Any

from pypdf import PdfReader

from .ocr.base import OCRPageContext, OCRProvider, OCRSummary
from .types import Chunk

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")
SUPPORTED_DOCUMENT_SUFFIXES = {".md", ".txt", ".pdf"}
PARSER_LINEAGE_VERSION = "1"
PDF_PRODUCT_MANUAL_HEADING_HINTS = {
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
SENTENCE_BOUNDARY_RE = re.compile(r"(?<=[。！？.!?])\s+|(?<=[。！？])")
PDF_MANUALSLIB_NOISE = (
    "manualslib.com",
    "the global manuals library",
    "other manualslib projects",
    "manuals / brands /",
    "quick links",
)

PDF_PROFILE_HEADING_HINTS = {
    "generic": frozenset[str](),
    "product_manual": frozenset(PDF_PRODUCT_MANUAL_HEADING_HINTS),
}


def parse_document(
    path: str | Path,
    max_chars: int = 500,
    min_chars: int = 50,
    root_dir: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
    *,
    overlap_chars: int = 0,
    pdf_profile: str = "product_manual",
    pdf_heading_hints: list[str] | tuple[str, ...] | None = None,
    ocr_provider: OCRProvider | None = None,
    ocr_enabled: bool = False,
    ocr_strict: bool = False,
    kb_name: str = "default",
) -> list[Chunk]:
    result = parse_document_with_ocr_summary(
        path,
        max_chars=max_chars,
        min_chars=min_chars,
        root_dir=root_dir,
        metadata=metadata,
        overlap_chars=overlap_chars,
        pdf_profile=pdf_profile,
        pdf_heading_hints=pdf_heading_hints,
        ocr_provider=ocr_provider,
        ocr_enabled=ocr_enabled,
        ocr_strict=ocr_strict,
        kb_name=kb_name,
    )
    return result.chunks


@dataclass(frozen=True)
class ParsedDocument:
    chunks: list[Chunk]
    ocr_summary: OCRSummary = OCRSummary()


def parse_document_with_ocr_summary(
    path: str | Path,
    max_chars: int = 500,
    min_chars: int = 50,
    root_dir: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
    *,
    overlap_chars: int = 0,
    pdf_profile: str = "product_manual",
    pdf_heading_hints: list[str] | tuple[str, ...] | None = None,
    ocr_provider: OCRProvider | None = None,
    ocr_enabled: bool = False,
    ocr_strict: bool = False,
    kb_name: str = "default",
) -> ParsedDocument:
    file_path = Path(path)
    source_file = str(file_path.relative_to(root_dir)) if root_dir else file_path.name
    chunk_metadata = dict(metadata or {})
    suffix = file_path.suffix.lower()
    if suffix == ".pdf":
        return _parse_pdf(
            file_path,
            source_file=source_file,
            max_chars=max_chars,
            min_chars=min_chars,
            overlap_chars=overlap_chars,
            metadata=chunk_metadata,
            pdf_profile=pdf_profile,
            pdf_heading_hints=pdf_heading_hints,
            ocr_provider=ocr_provider,
            ocr_enabled=ocr_enabled,
            ocr_strict=ocr_strict,
            kb_name=kb_name,
        )
    text = file_path.read_text(encoding="utf-8")
    if not text.strip():
        return ParsedDocument([])

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

    processed = _post_process(raw_chunks, max_chars=max_chars, min_chars=min_chars, overlap_chars=overlap_chars)
    return ParsedDocument(_with_lineage(processed, parser_profile=_text_parser_profile(suffix)))


def _parse_pdf(
    file_path: Path,
    *,
    source_file: str,
    max_chars: int,
    min_chars: int,
    overlap_chars: int,
    metadata: dict[str, Any],
    pdf_profile: str,
    pdf_heading_hints: list[str] | tuple[str, ...] | None,
    ocr_provider: OCRProvider | None,
    ocr_enabled: bool,
    ocr_strict: bool,
    kb_name: str,
) -> ParsedDocument:
    reader = PdfReader(str(file_path))
    raw_chunks: list[Chunk] = []
    ocr_summary = OCRSummary()
    heading_hints = _pdf_heading_hints_for_profile(pdf_profile, pdf_heading_hints)
    pdf_metadata = dict(metadata)
    pdf_metadata["pdf_parser_profile"] = pdf_profile
    for index, page in enumerate(reader.pages, 1):
        text = _extract_pdf_page_text(page)
        lines = _pdf_lines(text)
        if not lines:
            ocr_chunks, page_summary = _ocr_pdf_page_chunks(
                file_path,
                source_file=source_file,
                page_number=index,
                metadata=pdf_metadata,
                heading_hints=heading_hints,
                ocr_provider=ocr_provider,
                ocr_enabled=ocr_enabled,
                ocr_strict=ocr_strict,
                kb_name=kb_name,
            )
            raw_chunks.extend(ocr_chunks)
            ocr_summary = ocr_summary.merge(page_summary)
            continue
        if ocr_enabled:
            ocr_summary = ocr_summary.merge(OCRSummary(skipped=1))
        raw_chunks.extend(
            _pdf_page_chunks(
                lines,
                page_number=index,
                source_file=source_file,
                metadata=pdf_metadata,
                heading_hints=heading_hints,
            )
        )
    processed = _post_process(raw_chunks, max_chars=max_chars, min_chars=min_chars, overlap_chars=overlap_chars)
    native_chunks: list[Chunk] = []
    ocr_chunks: list[Chunk] = []
    for chunk in processed:
        if chunk.metadata.get("ocr_source"):
            ocr_chunks.append(chunk)
        else:
            native_chunks.append(chunk)
    return ParsedDocument(
        [
            *_with_lineage(native_chunks, parser_profile=f"pdf:{pdf_profile}"),
            *_with_lineage(ocr_chunks, parser_profile=f"pdf_ocr:{pdf_profile}"),
        ],
        ocr_summary=ocr_summary,
    )


def _ocr_pdf_page_chunks(
    file_path: Path,
    *,
    source_file: str,
    page_number: int,
    metadata: dict[str, Any],
    heading_hints: frozenset[str],
    ocr_provider: OCRProvider | None,
    ocr_enabled: bool,
    ocr_strict: bool,
    kb_name: str,
) -> tuple[list[Chunk], OCRSummary]:
    if not ocr_enabled or ocr_provider is None:
        return [], OCRSummary(skipped=1)
    doc_id = _lineage_doc_id(metadata, source_file)
    try:
        result = ocr_provider.recognize_pdf_page(
            OCRPageContext(
                source_path=file_path,
                source_file=source_file,
                page_number=page_number,
                kb_name=kb_name,
                doc_id=doc_id,
                metadata=dict(metadata),
            )
        )
    except Exception as exc:
        if ocr_strict:
            raise
        reason = _bounded_ocr_reason(type(exc).__name__)
        return [], OCRSummary(attempted=1, failed=1, failure_reasons={reason: 1})
    lines = _pdf_lines(result.text)
    if not lines:
        return [], OCRSummary(attempted=1, skipped=1, warnings=tuple(result.warnings))
    ocr_metadata = dict(metadata)
    ocr_metadata["ocr_provider"] = ocr_provider.provider_name
    ocr_metadata["ocr_version"] = ocr_provider.version
    ocr_metadata["ocr_trigger"] = "missing_text"
    ocr_metadata["ocr_source"] = "pdf_missing_text"
    chunks = _pdf_page_chunks(
        lines,
        page_number=page_number,
        source_file=source_file,
        metadata=ocr_metadata,
        heading_hints=heading_hints,
    )
    return chunks, OCRSummary(attempted=1, created=len(chunks), warnings=tuple(result.warnings))


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
    heading_hints: frozenset[str],
) -> list[Chunk]:
    heading_indexes = [idx for idx, line in enumerate(lines) if _is_pdf_heading(line, heading_hints=heading_hints)]
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
    chunk_metadata["pdf_parser_profile"] = str(metadata.get("pdf_parser_profile") or "product_manual")
    return Chunk(
        text=text,
        header=header,
        path=path,
        level=1,
        start_line=int(page_number),
        source_file=source_file,
        metadata=chunk_metadata,
    )


def _pdf_heading_hints_for_profile(
    pdf_profile: str,
    custom_hints: list[str] | tuple[str, ...] | None,
) -> frozenset[str]:
    try:
        base_hints = set(PDF_PROFILE_HEADING_HINTS[pdf_profile])
    except KeyError as exc:
        raise ValueError(f"Unknown PDF parser profile: {pdf_profile}") from exc
    for hint in custom_hints or ():
        normalized = _normalize_pdf_heading_candidate(str(hint)).lower().strip(":-")
        if normalized:
            base_hints.add(normalized)
    return frozenset(base_hints)


def _is_pdf_heading(line: str, *, heading_hints: frozenset[str] = frozenset()) -> bool:
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
    if lowered in heading_hints:
        return True
    if any(keyword in lowered for keyword in heading_hints if len(keyword) >= 6):
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


def _bounded_ocr_reason(reason: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(reason).strip().lower())[:80].strip("_")
    return normalized or "unknown"


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


def _text_parser_profile(suffix: str) -> str:
    return "markdown" if suffix == ".md" else "txt"


def _with_lineage(chunks: list[Chunk], *, parser_profile: str) -> list[Chunk]:
    return [_chunk_with_lineage(chunk, parser_profile=parser_profile) for chunk in chunks]


def _chunk_with_lineage(chunk: Chunk, *, parser_profile: str) -> Chunk:
    metadata = dict(chunk.metadata)
    doc_id = _lineage_doc_id(metadata, chunk.source_file)
    section_path = [str(part) for part in chunk.path if str(part)]
    page_start = _lineage_optional_int(metadata.get("page_start"))
    page_end = _lineage_optional_int(metadata.get("page_end"))
    text_hash = _lineage_hash(chunk.text)

    chunk_payload: dict[str, Any] = {
        "doc_id": doc_id,
        "parser_profile": parser_profile,
        "parser_version": PARSER_LINEAGE_VERSION,
        "source_file": _safe_source_for_lineage(chunk.source_file),
        "section_path": section_path,
        "start_line": int(chunk.start_line),
        "text_hash": text_hash,
    }
    if page_start is not None:
        chunk_payload["page_start"] = page_start
    if page_end is not None:
        chunk_payload["page_end"] = page_end
    for key in ("ocr_provider", "ocr_version", "ocr_trigger", "ocr_source"):
        value = str(metadata.get(key) or "")
        if value:
            chunk_payload[key] = value

    chunk_id = _lineage_id("chunk", chunk_payload)
    element_id = _lineage_id(
        "element",
        {
            "doc_id": doc_id,
            "chunk_id": chunk_id,
            "section_path": section_path,
            "page_start": page_start,
            "page_end": page_end,
        },
    )
    metadata["doc_id"] = doc_id
    metadata["chunk_id"] = chunk_id
    metadata["element_ids"] = [element_id]
    metadata["section_path"] = section_path
    metadata["asset_refs"] = _lineage_string_list(metadata.get("asset_refs"))
    metadata["parser_profile"] = parser_profile
    metadata["parser_version"] = PARSER_LINEAGE_VERSION
    for key in ("ocr_provider", "ocr_version", "ocr_trigger", "ocr_source"):
        value = str(metadata.get(key) or "")
        if value:
            metadata[key] = value
    if page_start is not None:
        metadata["page_start"] = page_start
    if page_end is not None:
        metadata["page_end"] = page_end

    return Chunk(
        text=chunk.text,
        header=chunk.header,
        path=chunk.path,
        level=chunk.level,
        start_line=chunk.start_line,
        source_file=chunk.source_file,
        metadata=metadata,
    )


def _lineage_doc_id(metadata: dict[str, Any], source_file: str) -> str:
    for key in ("doc_id", "manual_id"):
        value = str(metadata.get(key) or "").strip()
        if value:
            return value
    return "source:" + _lineage_hash(_safe_source_for_lineage(source_file))[:24]


def _safe_source_for_lineage(source_file: str) -> str:
    value = str(source_file or "").replace("\\", "/").strip()
    if not value:
        return "<unknown-source>"
    if Path(value).is_absolute():
        return Path(value).name or "<unknown-source>"
    return re.sub(r"/+", "/", value)


def _lineage_id(prefix: str, payload: dict[str, Any]) -> str:
    encoded = json.dumps(payload, ensure_ascii=False, sort_keys=True, separators=(",", ":")).encode("utf-8")
    return f"{prefix}:sha256:" + hashlib.sha256(encoded).hexdigest()[:32]


def _lineage_hash(value: str) -> str:
    return hashlib.sha256(str(value).encode("utf-8")).hexdigest()


def _lineage_optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _lineage_string_list(value: Any) -> list[str]:
    if value is None:
        return []
    if isinstance(value, (list, tuple, set)):
        return [str(item) for item in value if str(item)]
    text = str(value)
    return [text] if text else []


def _post_process(chunks: list[Chunk], max_chars: int, min_chars: int, overlap_chars: int = 0) -> list[Chunk]:
    split_chunks: list[Chunk] = []
    for chunk in chunks:
        if len(chunk.text) <= max_chars:
            split_chunks.append(chunk)
            continue
        parts = _split_long_text(chunk.text, max_chars, overlap_chars=overlap_chars)
        for offset, part in enumerate(parts):
            split_reason = _split_reason(part)
            metadata = dict(chunk.metadata)
            metadata["split_reason"] = split_reason
            if split_reason == "table_row_boundary":
                metadata["chunk_kind"] = "table"
            split_chunks.append(
                Chunk(
                    text=part,
                    header=chunk.header,
                    path=chunk.path,
                    level=chunk.level,
                    start_line=chunk.start_line + offset,
                    source_file=chunk.source_file,
                    metadata=metadata,
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


def _split_long_text(text: str, max_chars: int, *, overlap_chars: int = 0) -> list[str]:
    if _contains_markdown_table(text):
        return _with_overlap(_split_table_aware_text(text, max_chars), overlap_chars, max_chars)
    paragraphs = [p.strip() for p in re.split(r"\n\s*\n", text) if p.strip()]
    parts: list[str] = []
    current = ""
    for para in paragraphs:
        if not current:
            current = para
        elif len(current) + len(para) + 2 <= max_chars:
            current += "\n\n" + para
        else:
            parts.extend(_split_sentence_aware(current, max_chars))
            current = para
    if current:
        parts.extend(_split_sentence_aware(current, max_chars))
    return _with_overlap(parts, overlap_chars, max_chars)


def _split_sentence_aware(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    sentences = _sentence_units(text)
    if len(sentences) <= 1:
        return _hard_split(text, max_chars)
    parts: list[str] = []
    current = ""
    for sentence in sentences:
        if len(sentence) > max_chars:
            if current:
                parts.append(current.strip())
                current = ""
            parts.extend(_hard_split(sentence, max_chars))
            continue
        separator = " " if current and _needs_space_between(current, sentence) else ""
        candidate = current + separator + sentence if current else sentence
        if len(candidate) <= max_chars:
            current = candidate
        else:
            if current:
                parts.append(current.strip())
            current = sentence
    if current:
        parts.append(current.strip())
    return [part for part in parts if part]


def _sentence_units(text: str) -> list[str]:
    units = [part.strip() for part in SENTENCE_BOUNDARY_RE.split(text.strip()) if part.strip()]
    return units or [text.strip()]


def _needs_space_between(left: str, right: str) -> bool:
    if not left or not right:
        return False
    return left[-1].isascii() and right[0].isascii()


def _with_overlap(parts: list[str], overlap_chars: int, max_chars: int) -> list[str]:
    clean_parts = [part.strip() for part in parts if part.strip()]
    if overlap_chars <= 0 or len(clean_parts) <= 1:
        return clean_parts
    bounded_overlap = min(int(overlap_chars), max(max_chars // 3, 1))
    overlapped = [clean_parts[0]]
    for previous, current in zip(clean_parts, clean_parts[1:]):
        if _contains_markdown_table(previous) or _contains_markdown_table(current):
            overlapped.append(current)
            continue
        prefix = _overlap_tail(previous, bounded_overlap)
        if not prefix:
            overlapped.append(current)
            continue
        separator = "\n" if "\n" in prefix or "\n" in current else " "
        overlapped.append((prefix + separator + current).strip())
    return overlapped


def _overlap_tail(text: str, overlap_chars: int) -> str:
    if len(text) <= overlap_chars:
        return text.strip()
    window = text[-overlap_chars:]
    for boundary in ("\n\n", "\n", "。", "！", "？", ". ", "! ", "? "):
        index = window.find(boundary)
        if index >= 0:
            candidate = window[index + len(boundary) :].strip()
            if candidate:
                return candidate
    return window.strip()


def _contains_markdown_table(text: str) -> bool:
    lines = text.splitlines()
    return any(_is_markdown_table_separator(line) for line in lines)


def _split_table_aware_text(text: str, max_chars: int) -> list[str]:
    lines = text.splitlines()
    parts: list[str] = []
    current: list[str] = []
    index = 0
    while index < len(lines):
        if _is_table_start(lines, index):
            if current:
                parts.extend(_split_sentence_aware("\n".join(current).strip(), max_chars))
                current = []
            table_lines: list[str] = []
            while index < len(lines) and _is_markdown_table_line(lines[index]):
                table_lines.append(lines[index].strip())
                index += 1
            parts.extend(_split_table_lines(table_lines, max_chars))
            continue
        current.append(lines[index])
        index += 1
    if current:
        parts.extend(_split_sentence_aware("\n".join(current).strip(), max_chars))
    return parts


def _split_table_lines(lines: list[str], max_chars: int) -> list[str]:
    table = [line for line in lines if line.strip()]
    if not table:
        return []
    if len("\n".join(table)) <= max_chars:
        return ["\n".join(table)]
    if len(table) < 3:
        return _hard_split("\n".join(table), max_chars)
    header = table[:2]
    rows = table[2:]
    parts: list[str] = []
    current = list(header)
    for row in rows:
        candidate = current + [row]
        if len("\n".join(candidate)) <= max_chars:
            current.append(row)
            continue
        if len(current) > len(header):
            parts.append("\n".join(current))
            current = list(header)
        if len("\n".join(current + [row])) <= max_chars:
            current.append(row)
        elif len(row) <= max_chars:
            parts.append("\n".join(header + [row]))
            current = list(header)
        else:
            parts.extend(_hard_split("\n".join(header + [row]), max_chars))
            current = list(header)
    if len(current) > len(header):
        parts.append("\n".join(current))
    return parts or _hard_split("\n".join(table), max_chars)


def _is_table_start(lines: list[str], index: int) -> bool:
    return (
        index + 1 < len(lines)
        and _is_markdown_table_line(lines[index])
        and _is_markdown_table_separator(lines[index + 1])
    )


def _is_markdown_table_line(line: str) -> bool:
    stripped = line.strip()
    return stripped.startswith("|") and stripped.endswith("|") and stripped.count("|") >= 2


def _is_markdown_table_separator(line: str) -> bool:
    stripped = line.strip()
    if not _is_markdown_table_line(stripped):
        return False
    cells = [cell.strip() for cell in stripped.strip("|").split("|")]
    return bool(cells) and all(re.fullmatch(r":?-{3,}:?", cell or "") for cell in cells)


def _split_reason(text: str) -> str:
    if _contains_markdown_table(text):
        return "table_row_boundary"
    return "sentence_boundary"


def _hard_split(text: str, max_chars: int) -> list[str]:
    if len(text) <= max_chars:
        return [text]
    return [text[i : i + max_chars].strip() for i in range(0, len(text), max_chars) if text[i : i + max_chars].strip()]
