from __future__ import annotations

from dataclasses import dataclass, field
import hashlib
import json
from pathlib import Path
from typing import Any

import networkx as nx

from .config import Settings
from .manuals import metadata_from_node
from .storage.atomic import atomic_write
from .types import Chunk

CHUNK_IDENTITY_SCHEMA_VERSION = "1"
CHUNK_IDENTITY_FILENAME = "chunk_identity.json"


@dataclass(frozen=True)
class ChunkIdentityEntry:
    identity_key: str
    manual_id: str
    source_file: str
    path: tuple[str, ...]
    header: str
    start_line: int
    text_hash: str
    node_id: int
    vector_row: int
    metadata_hash: str

    @classmethod
    def from_dict(cls, key: str, data: dict[str, Any]) -> "ChunkIdentityEntry":
        return cls(
            identity_key=key,
            manual_id=str(data.get("manual_id") or ""),
            source_file=str(data.get("source_file") or ""),
            path=tuple(str(part) for part in data.get("path", []) if str(part)),
            header=str(data.get("header") or ""),
            start_line=int(data.get("start_line") or 1),
            text_hash=str(data.get("text_hash") or ""),
            node_id=int(data.get("node_id") or 0),
            vector_row=int(data.get("vector_row") or data.get("node_id") or 0),
            metadata_hash=str(data.get("metadata_hash") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "manual_id": self.manual_id,
            "source_file": self.source_file,
            "path": list(self.path),
            "header": self.header,
            "start_line": self.start_line,
            "text_hash": self.text_hash,
            "node_id": self.node_id,
            "vector_row": self.vector_row,
            "metadata_hash": self.metadata_hash,
        }


@dataclass(frozen=True)
class ChunkIdentityMap:
    schema_version: str
    kb_name: str
    build_id: str
    parser: dict[str, object]
    chunks: dict[str, ChunkIdentityEntry] = field(default_factory=dict)

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ChunkIdentityMap":
        chunks_data = data.get("chunks") if isinstance(data.get("chunks"), dict) else {}
        chunks = {
            str(key): ChunkIdentityEntry.from_dict(str(key), value)
            for key, value in chunks_data.items()
            if isinstance(value, dict)
        }
        return cls(
            schema_version=str(data.get("schema_version") or ""),
            kb_name=str(data.get("kb_name") or ""),
            build_id=str(data.get("build_id") or ""),
            parser=dict(data.get("parser") or {}),
            chunks=chunks,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kb_name": self.kb_name,
            "build_id": self.build_id,
            "parser": self.parser,
            "chunks": {key: value.to_dict() for key, value in sorted(self.chunks.items())},
        }


def identity_path(kb_name: str, cfg: Settings) -> Path:
    return Path(cfg.storage.data_dir) / kb_name / CHUNK_IDENTITY_FILENAME


def load_chunk_identity(kb_name: str, cfg: Settings) -> tuple[ChunkIdentityMap | None, str]:
    path = identity_path(kb_name, cfg)
    if not path.exists():
        return None, "missing_chunk_identity"
    try:
        identity = ChunkIdentityMap.from_dict(json.loads(path.read_text(encoding="utf-8")))
    except (json.JSONDecodeError, OSError, TypeError, ValueError):
        return None, "chunk_identity_corrupt"
    if identity.schema_version != CHUNK_IDENTITY_SCHEMA_VERSION:
        return None, "chunk_identity_schema_mismatch"
    if identity.kb_name != kb_name:
        return None, "chunk_identity_kb_mismatch"
    expected_parser = parser_signature(cfg)
    if identity.parser != expected_parser:
        return None, "parser_config_changed"
    if len(identity.chunks) != len({entry.identity_key for entry in identity.chunks.values()}):
        return None, "ambiguous_chunk_identity"
    return identity, ""


def save_chunk_identity(path: Path, identity: ChunkIdentityMap) -> None:
    def write(tmp_path: Path) -> None:
        tmp_path.write_text(json.dumps(identity.to_dict(), ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")

    atomic_write(path, write)


def build_chunk_identity_map(graph: nx.Graph, *, kb_name: str, build_id: str, cfg: Settings) -> ChunkIdentityMap:
    chunks: dict[str, ChunkIdentityEntry] = {}
    for node_id, node in graph.nodes(data=True):
        metadata = metadata_from_node(node)
        entry = entry_from_node(int(node_id), node, metadata=metadata)
        if entry.identity_key not in chunks:
            chunks[entry.identity_key] = entry
    return ChunkIdentityMap(
        schema_version=CHUNK_IDENTITY_SCHEMA_VERSION,
        kb_name=kb_name,
        build_id=build_id,
        parser=parser_signature(cfg),
        chunks=chunks,
    )


def entry_from_chunk(chunk: Chunk, *, node_id: int = -1, vector_row: int = -1) -> ChunkIdentityEntry:
    metadata = dict(chunk.metadata)
    manual_id = str(metadata.get("manual_id") or "")
    return _entry(
        manual_id=manual_id,
        source_file=chunk.source_file,
        path=chunk.path,
        header=chunk.header,
        start_line=chunk.start_line,
        text=chunk.text,
        metadata=metadata,
        node_id=node_id,
        vector_row=vector_row,
    )


def entry_from_node(node_id: int, node: dict[str, Any], *, metadata: dict[str, Any] | None = None) -> ChunkIdentityEntry:
    node_metadata = dict(metadata or metadata_from_node(node))
    return _entry(
        manual_id=str(node_metadata.get("manual_id") or ""),
        source_file=str(node.get("source_file") or node_metadata.get("source_file") or ""),
        path=tuple(str(part) for part in node.get("path", []) if str(part)),
        header=str(node.get("header") or ""),
        start_line=int(node.get("start_line") or 1),
        text=str(node.get("text") or ""),
        metadata=node_metadata,
        node_id=node_id,
        vector_row=node_id,
    )


def parser_signature(cfg: Settings) -> dict[str, object]:
    return {
        "provider": str(getattr(cfg.parser, "provider", "native")),
        "max_chars": int(cfg.parser.max_chars),
        "min_chars": int(cfg.parser.min_chars),
        "overlap_chars": int(cfg.parser.overlap_chars),
        "pdf_profile": str(cfg.parser.pdf_profile),
        "pdf_heading_hints_hash": _stable_string_list_hash(cfg.parser.pdf_heading_hints),
    }


def text_hash(text: str) -> str:
    return "sha256:" + hashlib.sha256(text.encode("utf-8")).hexdigest()


def metadata_hash(metadata: dict[str, Any]) -> str:
    return "sha256:" + hashlib.sha256(json.dumps(metadata, ensure_ascii=False, sort_keys=True).encode("utf-8")).hexdigest()


def _stable_string_list_hash(values: list[str]) -> str:
    normalized = sorted(str(value).strip().lower() for value in values if str(value).strip())
    return "sha256:" + hashlib.sha256(json.dumps(normalized, ensure_ascii=False).encode("utf-8")).hexdigest()


def _entry(
    *,
    manual_id: str,
    source_file: str,
    path: tuple[str, ...],
    header: str,
    start_line: int,
    text: str,
    metadata: dict[str, Any],
    node_id: int,
    vector_row: int,
) -> ChunkIdentityEntry:
    normalized_path = tuple(str(part).strip() for part in path if str(part).strip()) or ("",)
    chunk_text_hash = text_hash(text)
    key_payload = {
        "manual_id": manual_id,
        "source_file": source_file.replace("\\", "/"),
        "path": list(normalized_path),
        "header": header,
        "text_hash": chunk_text_hash,
    }
    identity_key = "sha256:" + hashlib.sha256(
        json.dumps(key_payload, ensure_ascii=False, sort_keys=True).encode("utf-8")
    ).hexdigest()
    return ChunkIdentityEntry(
        identity_key=identity_key,
        manual_id=manual_id,
        source_file=source_file.replace("\\", "/"),
        path=normalized_path,
        header=header,
        start_line=start_line,
        text_hash=chunk_text_hash,
        node_id=node_id,
        vector_row=vector_row,
        metadata_hash=metadata_hash(metadata),
    )
