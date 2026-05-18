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
from .migration import migrate_kb_to_g1_if_needed
from .paths import KbPaths

__all__ = [
    "INDEXGEN_META_FILENAME",
    "INDEXGEN_META_SCHEMA_VERSION",
    "GenerationStatus",
    "KbMeta",
    "KbPaths",
    "ReadyGeneration",
    "ShadowGeneration",
    "migrate_kb_to_g1_if_needed",
    "read_meta",
    "trim_history",
    "write_meta",
]
