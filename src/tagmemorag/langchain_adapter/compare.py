from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from statistics import median
from typing import Any

from ..parser import parse_document
from ..types import Chunk
from .loader_splitter import LangChainParseConfig, parse_langchain_document


@dataclass(frozen=True)
class ChunkStats:
    count: int
    min_chars: int
    median_chars: float
    max_chars: int
    source_file_count: int
    page_coverage_count: int
    parser_profiles: tuple[str, ...]
    text_hash_samples: tuple[str, ...]

    def to_dict(self) -> dict[str, Any]:
        return {
            "count": self.count,
            "min_chars": self.min_chars,
            "median_chars": self.median_chars,
            "max_chars": self.max_chars,
            "source_file_count": self.source_file_count,
            "page_coverage_count": self.page_coverage_count,
            "parser_profiles": list(self.parser_profiles),
            "text_hash_samples": list(self.text_hash_samples),
        }


@dataclass(frozen=True)
class ChunkComparisonReport:
    source_file: str
    native: ChunkStats
    langchain: ChunkStats

    def to_dict(self) -> dict[str, Any]:
        return {
            "source_file": self.source_file,
            "native": self.native.to_dict(),
            "langchain": self.langchain.to_dict(),
        }


def compare_langchain_to_native(
    path: str | Path,
    *,
    config: LangChainParseConfig | None = None,
    root_dir: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> ChunkComparisonReport:
    cfg = config or LangChainParseConfig()
    native_chunks = parse_document(
        path,
        cfg.max_chars,
        cfg.min_chars,
        root_dir=root_dir,
        metadata=metadata,
        overlap_chars=cfg.overlap_chars,
    )
    langchain_chunks = parse_langchain_document(path, config=cfg, root_dir=root_dir, metadata=metadata)
    return ChunkComparisonReport(
        source_file=Path(path).name,
        native=_stats(native_chunks),
        langchain=_stats(langchain_chunks),
    )


def _stats(chunks: list[Chunk]) -> ChunkStats:
    lengths = [len(chunk.text) for chunk in chunks]
    profiles = sorted({str(chunk.metadata.get("parser_profile") or "") for chunk in chunks if chunk.metadata})
    return ChunkStats(
        count=len(chunks),
        min_chars=min(lengths) if lengths else 0,
        median_chars=float(median(lengths)) if lengths else 0.0,
        max_chars=max(lengths) if lengths else 0,
        source_file_count=sum(1 for chunk in chunks if chunk.source_file),
        page_coverage_count=sum(1 for chunk in chunks if "page_start" in chunk.metadata or "page_end" in chunk.metadata),
        parser_profiles=tuple(profiles),
        text_hash_samples=tuple(_hash_text(chunk.text) for chunk in chunks[:3]),
    )


def _hash_text(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()[:16]
