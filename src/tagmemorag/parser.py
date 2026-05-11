from __future__ import annotations

from pathlib import Path
import re

from .types import Chunk

HEADING_RE = re.compile(r"^(#{1,6})\s+(.+?)\s*$")


def parse_document(path: str | Path, max_chars: int = 500, min_chars: int = 50, root_dir: str | Path | None = None) -> list[Chunk]:
    file_path = Path(path)
    source_file = str(file_path.relative_to(root_dir)) if root_dir else file_path.name
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
