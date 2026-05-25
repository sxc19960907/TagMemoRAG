from __future__ import annotations

from pathlib import Path
from typing import Any

from .config import ParserConfig
from .langchain_adapter import LangChainAdapterUnavailable, LangChainParseConfig, parse_langchain_document
from .langchain_adapter.loader_splitter import SUPPORTED_LANGCHAIN_SUFFIXES
from .ocr.base import OCRProvider, OCRSummary
from .parser import SUPPORTED_DOCUMENT_SUFFIXES, ParsedDocument, parse_document, parse_document_with_ocr_summary
from .types import Chunk


def supported_document_suffixes(parser_cfg: ParserConfig) -> frozenset[str]:
    if parser_cfg.provider == "langchain":
        return frozenset(SUPPORTED_LANGCHAIN_SUFFIXES)
    return frozenset(SUPPORTED_DOCUMENT_SUFFIXES)


def _langchain_config(parser_cfg: ParserConfig) -> LangChainParseConfig:
    return LangChainParseConfig(
        max_chars=parser_cfg.max_chars,
        min_chars=parser_cfg.min_chars,
        overlap_chars=parser_cfg.overlap_chars,
    )


def _langchain_chunks(
    path: str | Path,
    parser_cfg: ParserConfig,
    *,
    root_dir: str | Path | None,
    metadata: dict[str, Any] | None,
) -> list[Chunk]:
    try:
        return parse_langchain_document(path, config=_langchain_config(parser_cfg), root_dir=root_dir, metadata=metadata)
    except LangChainAdapterUnavailable as exc:
        raise RuntimeError(str(exc)) from exc


def parse_document_for_config(
    path: str | Path,
    parser_cfg: ParserConfig,
    *,
    root_dir: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
    ocr_provider: OCRProvider | None = None,
    ocr_enabled: bool = False,
    ocr_strict: bool = False,
    kb_name: str = "default",
) -> ParsedDocument:
    if parser_cfg.provider == "langchain":
        return ParsedDocument(chunks=_langchain_chunks(path, parser_cfg, root_dir=root_dir, metadata=metadata), ocr_summary=OCRSummary())
    return parse_document_with_ocr_summary(
        path,
        parser_cfg.max_chars,
        parser_cfg.min_chars,
        root_dir=root_dir,
        metadata=metadata,
        overlap_chars=parser_cfg.overlap_chars,
        pdf_profile=parser_cfg.pdf_profile,
        pdf_heading_hints=parser_cfg.pdf_heading_hints,
        ocr_provider=ocr_provider,
        ocr_enabled=ocr_enabled,
        ocr_strict=ocr_strict,
        kb_name=kb_name,
    )


def parse_chunks_for_config(
    path: str | Path,
    parser_cfg: ParserConfig,
    *,
    root_dir: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[Chunk]:
    if parser_cfg.provider == "langchain":
        return _langchain_chunks(path, parser_cfg, root_dir=root_dir, metadata=metadata)
    return parse_document(
        path,
        parser_cfg.max_chars,
        parser_cfg.min_chars,
        overlap_chars=parser_cfg.overlap_chars,
        root_dir=root_dir,
        metadata=metadata,
        pdf_profile=parser_cfg.pdf_profile,
        pdf_heading_hints=parser_cfg.pdf_heading_hints,
    )
