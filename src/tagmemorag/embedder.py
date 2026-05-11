from __future__ import annotations

import hashlib
from typing import Sequence

import numpy as np


class Embedder:
    def __init__(self, model_name: str = "BAAI/bge-small-zh-v1.5", device: str = "cpu", batch_size: int = 32):
        self.model_name = model_name
        self.device = device
        self.batch_size = batch_size
        self._model = None

    @property
    def model(self):
        if self._model is None:
            try:
                from sentence_transformers import SentenceTransformer
            except ImportError as exc:
                raise RuntimeError("sentence-transformers is required to use Embedder") from exc
            self._model = SentenceTransformer(self.model_name, device=self.device)
        return self._model

    def encode_batch(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, 0), dtype=np.float32)
        vecs = self.model.encode(
            list(texts),
            batch_size=self.batch_size,
            normalize_embeddings=True,
            convert_to_numpy=True,
            show_progress_bar=False,
        )
        return np.asarray(vecs, dtype=np.float32)

    def encode_query(self, text: str) -> np.ndarray:
        vecs = self.encode_batch([text])
        return vecs[0]


class HashingEmbedder:
    """Deterministic lightweight embedder for tests and offline smoke runs."""

    def __init__(self, dim: int = 64):
        self.model_name = "hashing-embedder"
        self.dim = dim

    def encode_batch(self, texts: Sequence[str]) -> np.ndarray:
        vecs = np.vstack([self._encode_one(text) for text in texts]).astype(np.float32) if texts else np.zeros((0, self.dim), dtype=np.float32)
        return vecs

    def encode_query(self, text: str) -> np.ndarray:
        return self._encode_one(text).astype(np.float32)

    def _encode_one(self, text: str) -> np.ndarray:
        vec = np.zeros(self.dim, dtype=np.float32)
        tokens = _tokens(text)
        for token in tokens:
            idx = int(hashlib.sha256(token.encode("utf-8")).hexdigest()[:8], 16) % self.dim
            vec[idx] += 1.0
        norm = np.linalg.norm(vec)
        return vec / norm if norm else vec


def create_embedder(model_name: str = "BAAI/bge-small-zh-v1.5", device: str = "cpu", batch_size: int = 32, dim: int = 384):
    if model_name == "hashing":
        return HashingEmbedder(dim=dim)
    return Embedder(model_name, device, batch_size)


def _tokens(text: str) -> list[str]:
    words: list[str] = []
    current = ""
    for ch in text.lower():
        if ch.isascii() and ch.isalnum():
            current += ch
        else:
            if current:
                words.append(current)
                current = ""
            if not ch.isspace():
                words.append(ch)
    if current:
        words.append(current)
    bigrams = [text[i : i + 2] for i in range(max(0, len(text) - 1)) if not text[i : i + 2].isspace()]
    return words + bigrams
