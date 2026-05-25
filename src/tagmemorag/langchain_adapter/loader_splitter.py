from __future__ import annotations

from dataclasses import dataclass
import hashlib
from pathlib import Path
from typing import Any, Protocol

from ..parser import _chunk_with_lineage
from ..types import Chunk

LANGCHAIN_ADAPTER_VERSION = "1"
SUPPORTED_LANGCHAIN_SUFFIXES = {".html", ".htm", ".md", ".pdf", ".txt"}


class LangChainAdapterUnavailable(RuntimeError):
    """Raised when the optional LangChain adapter extra is not installed."""


class _DocumentLike(Protocol):
    page_content: str
    metadata: dict[str, Any]


@dataclass(frozen=True)
class LangChainParseConfig:
    max_chars: int = 500
    min_chars: int = 50
    overlap_chars: int = 0
    loader_kind: str = "auto"
    splitter_kind: str = "recursive_character"


def parse_langchain_document(
    path: str | Path,
    *,
    config: LangChainParseConfig | None = None,
    root_dir: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
) -> list[Chunk]:
    """Parse a source file through optional LangChain loaders/splitters."""

    cfg = config or LangChainParseConfig()
    file_path = Path(path)
    documents = _load_documents(file_path, loader_kind=cfg.loader_kind)
    split_documents = _split_documents(documents, cfg)
    return documents_to_chunks(
        split_documents,
        source_path=file_path,
        root_dir=root_dir,
        metadata=metadata,
        parser_profile=_parser_profile(file_path.suffix.lower(), cfg),
    )


def documents_to_chunks(
    documents: list[_DocumentLike],
    *,
    source_path: str | Path,
    root_dir: str | Path | None = None,
    metadata: dict[str, Any] | None = None,
    parser_profile: str = "langchain:manual",
) -> list[Chunk]:
    """Convert LangChain-style documents into TagMemoRAG chunks."""

    file_path = Path(source_path)
    source_file = str(file_path.relative_to(root_dir)) if root_dir else file_path.name
    base_metadata = dict(metadata or {})
    chunks: list[Chunk] = []
    for index, doc in enumerate(documents):
        text = str(getattr(doc, "page_content", "") or "").strip()
        if not text:
            continue
        doc_metadata = getattr(doc, "metadata", {}) or {}
        chunk_metadata = {**base_metadata, **_safe_langchain_metadata(doc_metadata)}
        chunk_metadata["langchain_adapter_version"] = LANGCHAIN_ADAPTER_VERSION
        chunk_metadata["text_hash"] = _text_hash(text)
        page_number = _optional_page_number(doc_metadata)
        if page_number is not None:
            chunk_metadata["page_start"] = page_number
            chunk_metadata["page_end"] = page_number
        header = _header_for(doc_metadata, fallback=file_path.stem, page_number=page_number)
        chunk = Chunk(
            text=text,
            header=header,
            path=(header,),
            level=1,
            start_line=int(doc_metadata.get("start_line") or index + 1),
            source_file=source_file,
            metadata=chunk_metadata,
        )
        chunks.append(_chunk_with_lineage(chunk, parser_profile=parser_profile))
    return chunks


def _load_documents(path: Path, *, loader_kind: str) -> list[_DocumentLike]:
    suffix = path.suffix.lower()
    if suffix not in SUPPORTED_LANGCHAIN_SUFFIXES:
        raise ValueError(f"Unsupported LangChain adapter suffix: {suffix}")
    loader_class = _loader_class(suffix, loader_kind)
    try:
        if suffix in {".html", ".htm"}:
            loader = loader_class(str(path), bs_kwargs={"features": "html.parser"})
        else:
            loader = loader_class(str(path))
    except ImportError as exc:
        raise LangChainAdapterUnavailable(
            "Install the optional 'langchain' extra to use LangChain document loaders."
        ) from exc
    return list(loader.load())


def _split_documents(documents: list[_DocumentLike], cfg: LangChainParseConfig) -> list[_DocumentLike]:
    try:
        from langchain_text_splitters import RecursiveCharacterTextSplitter
    except ImportError as exc:
        raise LangChainAdapterUnavailable(
            "Install the optional 'langchain' extra to use LangChain text splitters."
        ) from exc
    splitter = RecursiveCharacterTextSplitter(
        chunk_size=cfg.max_chars,
        chunk_overlap=cfg.overlap_chars,
        length_function=len,
    )
    split_documents = splitter.split_documents(documents)
    return [doc for doc in split_documents if len(str(getattr(doc, "page_content", "") or "").strip()) >= cfg.min_chars]


def _loader_class(suffix: str, loader_kind: str):
    try:
        from langchain_community.document_loaders import BSHTMLLoader, PyPDFLoader, TextLoader
    except ImportError as exc:
        raise LangChainAdapterUnavailable(
            "Install the optional 'langchain' extra to use LangChain document loaders."
        ) from exc
    if loader_kind != "auto":
        loaders = {
            "text": TextLoader,
            "pdf": PyPDFLoader,
            "html": BSHTMLLoader,
        }
        try:
            return loaders[loader_kind]
        except KeyError as exc:
            raise ValueError(f"Unknown LangChain loader kind: {loader_kind}") from exc
    if suffix == ".pdf":
        return PyPDFLoader
    if suffix in {".html", ".htm"}:
        return BSHTMLLoader
    return TextLoader


def _parser_profile(suffix: str, cfg: LangChainParseConfig) -> str:
    source = suffix.lstrip(".") or "unknown"
    return f"langchain:{source}:{cfg.loader_kind}:{cfg.splitter_kind}"


def _safe_langchain_metadata(metadata: dict[str, Any]) -> dict[str, Any]:
    safe: dict[str, Any] = {}
    for key in ("page", "page_label", "source", "title"):
        value = metadata.get(key)
        if value is None:
            continue
        if key == "page":
            safe[f"langchain_{key}"] = value
        elif key == "source":
            safe[f"langchain_{key}"] = Path(str(value)).name
        else:
            safe[f"langchain_{key}"] = str(value)
    return safe


def _optional_page_number(metadata: dict[str, Any]) -> int | None:
    raw = metadata.get("page")
    if raw is None:
        return None
    try:
        return int(raw) + 1
    except (TypeError, ValueError):
        return None


def _header_for(metadata: dict[str, Any], *, fallback: str, page_number: int | None) -> str:
    title = str(metadata.get("title") or "").strip()
    if title:
        return title
    if page_number is not None:
        return f"Page {page_number}"
    return fallback


def _text_hash(text: str) -> str:
    return hashlib.sha256(text.encode("utf-8")).hexdigest()
