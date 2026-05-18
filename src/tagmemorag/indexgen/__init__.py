"""IndexGeneration mechanism (Architecture v2 § A4)."""

from .meta import (
    INDEXGEN_META_FILENAME,
    INDEXGEN_META_SCHEMA_VERSION,
    GenerationStatus,
    KbMeta,
    ReadyGeneration,
    ShadowGeneration,
    read_meta,
    trim_history,
    write_meta,
)

__all__ = [
    "INDEXGEN_META_FILENAME",
    "INDEXGEN_META_SCHEMA_VERSION",
    "GenerationStatus",
    "KbMeta",
    "ReadyGeneration",
    "ShadowGeneration",
    "read_meta",
    "trim_history",
    "write_meta",
]
