from __future__ import annotations

import io
from pathlib import Path
import zipfile
from xml.etree import ElementTree

from .errors import ErrorCode, ServiceError


DOCX_SUFFIX = ".docx"


def is_docx_source(source_file: str) -> bool:
    return Path(source_file).suffix.lower() == DOCX_SUFFIX


def converted_docx_source_file(source_file: str) -> str:
    path = Path(source_file.replace("\\", "/"))
    return str(path.with_suffix(".md")).replace("\\", "/")


def docx_to_markdown(raw: bytes, *, title: str, source_file: str) -> bytes:
    try:
        paragraphs = _docx_paragraphs(raw)
    except (ElementTree.ParseError, KeyError, OSError, zipfile.BadZipFile) as exc:
        raise ServiceError(
            ErrorCode.INVALID_INPUT,
            "Could not extract readable text from the .docx file.",
            {"source_file": source_file, "reason": type(exc).__name__},
        ) from exc
    lines = [f"# {title or Path(source_file).stem}", "", f"Original DOCX: {source_file}", ""]
    lines.extend(paragraphs or ("No readable text extracted.",))
    return ("\n\n".join(line for line in lines if line != "").strip() + "\n").encode("utf-8")


def _docx_paragraphs(raw: bytes) -> tuple[str, ...]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        document = archive.read("word/document.xml")
    root = ElementTree.fromstring(document)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        parts = [node.text or "" for node in paragraph.iter(f"{namespace}t")]
        text = _normalize_space("".join(parts))
        if text:
            paragraphs.append(text)
    return tuple(paragraphs)


def _normalize_space(value: str) -> str:
    return " ".join(value.replace("\xa0", " ").split())
