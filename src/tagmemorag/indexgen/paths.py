"""KbPaths — generation-aware product path helper.

A single dataclass that tells callers where every per-KB artifact lives,
parameterized by an optional generation number (Architecture v2 § A4).

Two modes:
- ``KbPaths(kb_name, cfg)`` — legacy mode: every product lives at
  ``{data_dir}/{kb_name}/...``. This matches all pre-IndexGeneration code.
- ``KbPaths(kb_name, cfg, generation=N)`` — generation mode: every product
  lives at ``{data_dir}/{kb_name}/g{N}/...``. Used by shadow build to direct
  outputs into a separate generation subdirectory without touching active
  data.

The IndexGeneration index file (``index.json``) is intentionally at the KB
root in both modes — it is the *index* that points at generations, not a
product of any generation.

This module is purely additive: existing callers continue to use ``_kb_dir``,
``identity_path``, ``impact_path``, etc. Future migration to ``KbPaths``
happens as needed (shadow build first).
"""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

from ..config import Settings
from .meta import INDEXGEN_META_FILENAME


@dataclass(frozen=True, eq=False)
class KbPaths:
    kb_name: str
    cfg: Settings
    generation: int | None = None

    @property
    def kb_root(self) -> Path:
        return Path(self.cfg.storage.data_dir) / self.kb_name

    @property
    def generation_root(self) -> Path:
        """Where this KbPaths instance writes products.

        Returns ``kb_root`` in legacy mode; ``kb_root / g{N}`` in generation
        mode.
        """
        if self.generation is None:
            return self.kb_root
        return self.kb_root / f"g{int(self.generation)}"

    @property
    def index_json(self) -> Path:
        """The IndexGeneration index file. Always at kb_root regardless of generation mode."""
        return self.kb_root / INDEXGEN_META_FILENAME

    @property
    def graph(self) -> Path:
        return self.generation_root / "graph.json"

    @property
    def vectors(self) -> Path:
        return self.generation_root / "vectors.npz"

    @property
    def chunk_identity(self) -> Path:
        return self.generation_root / "chunk_identity.json"

    @property
    def anchors(self) -> Path:
        return self.generation_root / "anchors.json"

    @property
    def anchors_dir(self) -> Path:
        return self.generation_root / "anchors"

    @property
    def epa_basis(self) -> Path:
        return self.generation_root / "epa_basis.npz"

    @property
    def tag_embeddings(self) -> Path:
        return self.generation_root / "tag_embeddings.npz"

    @property
    def tag_cooccurrence(self) -> Path:
        return self.generation_root / "tag_cooccurrence.json"

    @property
    def tag_intrinsic_residuals(self) -> Path:
        return self.generation_root / "tag_intrinsic_residuals.npz"

    @property
    def rebuild_impact(self) -> Path:
        return self.generation_root / "rebuild_impact.json"

    @property
    def meta(self) -> Path:
        """The GraphState meta.json — generation-internal metadata. Distinct from index.json."""
        return self.generation_root / "meta.json"

    @property
    def assets_root(self) -> Path:
        """Asset files under generation_root/assets/.

        Note: pre-IndexGeneration deployments stored assets under
        ``{kb_root}/assets/``. In legacy mode this still matches.
        """
        return self.generation_root / "assets"

    def ensure_generation_root(self) -> Path:
        """Create the generation directory if needed and return it.

        No-op when called in legacy mode (kb_root already exists or is
        created by the caller).
        """
        target = self.generation_root
        target.mkdir(parents=True, exist_ok=True)
        return target
