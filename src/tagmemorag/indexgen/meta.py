"""KbMeta — the per-KB index file describing IndexGeneration state.

Architecture v2 § A4 / Decision D2: each KB carries a `meta.json` at its root
that names the active generation, the optional shadow generation under
construction, and a per-generation summary. This module is the canonical
read/write boundary for that file. Adapters and admin endpoints must go
through `read_meta` / `write_meta`; never touch the file directly.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum
import json
from pathlib import Path
from typing import Any

from ..storage.atomic import atomic_write


INDEXGEN_META_SCHEMA_VERSION = 1
INDEXGEN_META_FILENAME = "index.json"
DEFAULT_HISTORY_MAX = 20


class GenerationStatus(str, Enum):
    BUILDING = "building"
    READY = "ready"
    FAILED = "failed"


@dataclass(frozen=True)
class ReadyGeneration:
    """A generation that has been built and is addressable.

    Each ready generation has been at least built once. `swap_at` is set when
    the generation became active (initial generation: equal to created_at).
    `retired_at` is non-null only after a retire admin call; once retired the
    generation files and Qdrant collection have been deleted.
    """

    created_at: str
    swap_at: str
    parser_version: str
    chunker_version: str
    embedding_model_id: str
    embedding_model_version: str
    index_schema_version: int
    chunk_count: int
    build_id: str
    retired_at: str | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ReadyGeneration":
        return cls(
            created_at=str(data["created_at"]),
            swap_at=str(data["swap_at"]),
            retired_at=(str(data["retired_at"]) if data.get("retired_at") else None),
            parser_version=str(data.get("parser_version") or ""),
            chunker_version=str(data.get("chunker_version") or ""),
            embedding_model_id=str(data.get("embedding_model_id") or ""),
            embedding_model_version=str(data.get("embedding_model_version") or ""),
            index_schema_version=int(data.get("index_schema_version") or 0),
            chunk_count=int(data.get("chunk_count") or 0),
            build_id=str(data.get("build_id") or ""),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "created_at": self.created_at,
            "swap_at": self.swap_at,
            "retired_at": self.retired_at,
            "parser_version": self.parser_version,
            "chunker_version": self.chunker_version,
            "embedding_model_id": self.embedding_model_id,
            "embedding_model_version": self.embedding_model_version,
            "index_schema_version": self.index_schema_version,
            "chunk_count": self.chunk_count,
            "build_id": self.build_id,
        }


@dataclass(frozen=True)
class ShadowGeneration:
    """A generation under construction (or recently failed).

    Status is one of building/ready/failed. Note: "ready" is a transient state
    inside the shadow slot — once swap is called the entry is rewritten as a
    ReadyGeneration in the active slot. Code that reads meta.json should
    distinguish the slot (active vs shadow) before assuming a generation type.
    """

    status: GenerationStatus
    progress: float
    build_started_at: str
    trigger_diff: tuple[str, ...]
    task_id: str = ""
    requested_by: str = ""
    error: dict[str, Any] | None = None

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "ShadowGeneration":
        return cls(
            status=GenerationStatus(str(data.get("status") or "building")),
            progress=float(data.get("progress") or 0.0),
            build_started_at=str(data.get("build_started_at") or ""),
            trigger_diff=tuple(str(item) for item in data.get("trigger_diff") or ()),
            task_id=str(data.get("task_id") or ""),
            requested_by=str(data.get("requested_by") or ""),
            error=(dict(data["error"]) if isinstance(data.get("error"), dict) else None),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "status": self.status.value,
            "progress": self.progress,
            "build_started_at": self.build_started_at,
            "trigger_diff": list(self.trigger_diff),
            "task_id": self.task_id,
            "requested_by": self.requested_by,
            "error": self.error,
        }


@dataclass(frozen=True)
class KbMeta:
    """The full meta.json contents.

    `active_generation` may be None for a freshly-initialised KB that has no
    generation yet (legacy migration produces a g1 entry; new empty KB starts
    with active_generation=None until first build).

    `shadow_generation` is None unless a build is in progress, ready, or
    failed pending operator cleanup.

    `generations` maps integer-as-string keys → ReadyGeneration | ShadowGeneration.
    The slot (active vs shadow) determines which type to expect. Callers
    must use `get_active()` / `get_shadow()` rather than indexing by key.
    """

    schema_version: int
    kb_name: str
    active_generation: int | None
    shadow_generation: int | None
    generations: dict[int, ReadyGeneration | ShadowGeneration] = field(default_factory=dict)

    @classmethod
    def empty(cls, kb_name: str) -> "KbMeta":
        return cls(
            schema_version=INDEXGEN_META_SCHEMA_VERSION,
            kb_name=kb_name,
            active_generation=None,
            shadow_generation=None,
            generations={},
        )

    @classmethod
    def from_dict(cls, data: dict[str, Any]) -> "KbMeta":
        sv = int(data.get("schema_version") or 0)
        if sv != INDEXGEN_META_SCHEMA_VERSION:
            raise ValueError(
                f"Unsupported indexgen meta schema_version: got {sv}, "
                f"expected {INDEXGEN_META_SCHEMA_VERSION}"
            )
        active = data.get("active_generation")
        shadow = data.get("shadow_generation")
        raw_generations = data.get("generations") or {}
        generations: dict[int, ReadyGeneration | ShadowGeneration] = {}
        for key, value in raw_generations.items():
            if not isinstance(value, dict):
                continue
            gen_id = int(key)
            if "status" in value:
                generations[gen_id] = ShadowGeneration.from_dict(value)
            else:
                generations[gen_id] = ReadyGeneration.from_dict(value)
        return cls(
            schema_version=sv,
            kb_name=str(data.get("kb_name") or ""),
            active_generation=(int(active) if active is not None else None),
            shadow_generation=(int(shadow) if shadow is not None else None),
            generations=generations,
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "kb_name": self.kb_name,
            "active_generation": self.active_generation,
            "shadow_generation": self.shadow_generation,
            "generations": {
                str(gen_id): entry.to_dict()
                for gen_id, entry in sorted(self.generations.items())
            },
        }

    def get_active(self) -> ReadyGeneration | None:
        if self.active_generation is None:
            return None
        entry = self.generations.get(self.active_generation)
        if isinstance(entry, ReadyGeneration):
            return entry
        return None

    def get_shadow(self) -> ShadowGeneration | None:
        if self.shadow_generation is None:
            return None
        entry = self.generations.get(self.shadow_generation)
        if isinstance(entry, ShadowGeneration):
            return entry
        return None

    def validate_invariants(self) -> None:
        """Raises ValueError if invariants from design § 2.3 are violated."""
        if (
            self.active_generation is not None
            and self.shadow_generation is not None
            and self.active_generation == self.shadow_generation
        ):
            raise ValueError(
                "active_generation and shadow_generation must differ"
            )
        if self.active_generation is not None:
            entry = self.generations.get(self.active_generation)
            if not isinstance(entry, ReadyGeneration):
                raise ValueError(
                    f"active_generation={self.active_generation} must point "
                    "to a ReadyGeneration entry"
                )
            if not entry.swap_at:
                raise ValueError(
                    f"active_generation={self.active_generation} entry must have non-null swap_at"
                )
        if self.shadow_generation is not None:
            entry = self.generations.get(self.shadow_generation)
            if not isinstance(entry, ShadowGeneration):
                raise ValueError(
                    f"shadow_generation={self.shadow_generation} must point "
                    "to a ShadowGeneration entry"
                )


def read_meta(kb_root: Path) -> KbMeta | None:
    """Read meta.json for a KB. Returns None if file does not exist."""
    path = kb_root / INDEXGEN_META_FILENAME
    if not path.exists():
        return None
    try:
        data = json.loads(path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as exc:
        raise ValueError(f"meta.json at {path} is not valid JSON") from exc
    if not isinstance(data, dict):
        raise ValueError(f"meta.json at {path} must be a JSON object")
    return KbMeta.from_dict(data)


def write_meta(kb_root: Path, meta: KbMeta) -> None:
    """Atomically write meta.json. Caller is responsible for invariants;
    this function does NOT call validate_invariants() so partial states
    (e.g. mid-swap) can be persisted."""
    path = kb_root / INDEXGEN_META_FILENAME
    payload = json.dumps(meta.to_dict(), ensure_ascii=False, indent=2, sort_keys=False)

    def _write(tmp: Path) -> None:
        tmp.write_text(payload, encoding="utf-8")

    atomic_write(path, _write)


def trim_history(meta: KbMeta, history_max: int = DEFAULT_HISTORY_MAX) -> KbMeta:
    """Remove the oldest retired generations once total entry count exceeds history_max.

    Active and shadow generations are never trimmed regardless of count.
    """
    if history_max < 1:
        raise ValueError("history_max must be >= 1")
    if len(meta.generations) <= history_max:
        return meta

    protected = {
        gen_id
        for gen_id in (meta.active_generation, meta.shadow_generation)
        if gen_id is not None
    }
    retired_with_time = [
        (gen_id, entry.retired_at or "")
        for gen_id, entry in meta.generations.items()
        if gen_id not in protected
        and isinstance(entry, ReadyGeneration)
        and entry.retired_at is not None
    ]
    if not retired_with_time:
        return meta

    retired_with_time.sort(key=lambda item: item[1])
    excess = len(meta.generations) - history_max
    to_remove = {gen_id for gen_id, _ in retired_with_time[:excess]}
    new_generations = {
        gen_id: entry
        for gen_id, entry in meta.generations.items()
        if gen_id not in to_remove
    }
    return KbMeta(
        schema_version=meta.schema_version,
        kb_name=meta.kb_name,
        active_generation=meta.active_generation,
        shadow_generation=meta.shadow_generation,
        generations=new_generations,
    )
