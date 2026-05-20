from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Sequence
from urllib.error import HTTPError, URLError
from urllib.request import Request, urlopen

import numpy as np

from .errors import EmbeddingError, InvalidConfigError


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


class HttpEmbedder:
    """OpenAI-compatible HTTP embedding client."""

    def __init__(
        self,
        model_name: str,
        *,
        base_url: str = "https://api.siliconflow.cn/v1",
        embeddings_url: str | None = None,
        api_key_env: str = "SILICONFLOW_API_KEY",
        timeout_seconds: float = 30.0,
        batch_size: int = 32,
        dim: int = 384,
        dimensions: int | None = None,
        normalize: bool = True,
    ):
        self.model_name = model_name
        self.endpoint = _embeddings_endpoint(base_url, embeddings_url)
        self.api_key_env = api_key_env
        self.timeout_seconds = timeout_seconds
        self.batch_size = batch_size
        self.dim = dim
        self.dimensions = dimensions
        self.normalize = normalize
        self._api_key = os.environ.get(api_key_env) or _read_dotenv_value(api_key_env)
        if not self._api_key:
            raise InvalidConfigError(
                f"Embedding API key environment variable is not set: {api_key_env}",
                {"api_key_env": api_key_env, "provider": "http"},
            )

    def encode_batch(self, texts: Sequence[str]) -> np.ndarray:
        if not texts:
            return np.zeros((0, self.dim), dtype=np.float32)
        batches = [self._request_batch_with_split(texts[i : i + self.batch_size]) for i in range(0, len(texts), self.batch_size)]
        vecs = np.vstack(batches).astype(np.float32)
        if self.normalize:
            norms = np.linalg.norm(vecs, axis=1, keepdims=True)
            vecs = np.divide(vecs, norms, out=np.zeros_like(vecs), where=norms > 0)
        return vecs

    def encode_query(self, text: str) -> np.ndarray:
        return self.encode_batch([text])[0]

    def _request_batch_with_split(self, texts: Sequence[str]) -> np.ndarray:
        try:
            return self._request_batch(texts, split_attempted=False)
        except EmbeddingError as exc:
            if len(texts) <= 1:
                raise
            midpoint = len(texts) // 2
            try:
                left = self._request_batch_with_split(texts[:midpoint])
                right = self._request_batch_with_split(texts[midpoint:])
            except EmbeddingError as nested:
                nested.detail["split_attempted"] = True
                raise
            exc.detail["split_attempted"] = True
            return np.vstack([left, right]).astype(np.float32)

    def _request_batch(self, texts: Sequence[str], *, split_attempted: bool = False) -> np.ndarray:
        payload: dict[str, object] = {
            "model": self.model_name,
            "input": list(texts),
            "encoding_format": "float",
        }
        if self.dimensions is not None:
            payload["dimensions"] = self.dimensions
        body = json.dumps(payload).encode("utf-8")
        request = Request(
            self.endpoint,
            data=body,
            headers={
                "Authorization": f"Bearer {self._api_key}",
                "Content-Type": "application/json",
                "Accept": "application/json",
            },
            method="POST",
        )
        try:
            with urlopen(request, timeout=self.timeout_seconds) as response:
                response_body = response.read().decode("utf-8")
                response_payload = json.loads(response_body)
        except HTTPError as exc:
            detail = self._failure_detail(texts, split_attempted=split_attempted, status_code=exc.code)
            raise EmbeddingError("Embedding API returned an error.", detail) from exc
        except (URLError, TimeoutError, OSError, json.JSONDecodeError) as exc:
            raise EmbeddingError(
                "Embedding API request failed.",
                self._failure_detail(texts, split_attempted=split_attempted, error_type=type(exc).__name__),
            ) from exc
        return _extract_embeddings(response_payload, expected_count=len(texts))

    def _failure_detail(
        self,
        texts: Sequence[str],
        *,
        split_attempted: bool,
        status_code: int | None = None,
        error_type: str | None = None,
    ) -> dict[str, object]:
        lengths = [len(text) for text in texts]
        detail: dict[str, object] = {
            "endpoint": self.endpoint,
            "batch_size": len(texts),
            "min_text_chars": min(lengths) if lengths else 0,
            "max_text_chars": max(lengths) if lengths else 0,
            "total_text_chars": sum(lengths),
            "split_attempted": split_attempted,
        }
        if status_code is not None:
            detail["status_code"] = status_code
        if error_type is not None:
            detail["error_type"] = error_type
        return detail


def create_embedder(
    model_name: str = "BAAI/bge-small-zh-v1.5",
    device: str = "cpu",
    batch_size: int = 32,
    dim: int = 384,
    provider: str = "local",
    base_url: str = "https://api.siliconflow.cn/v1",
    embeddings_url: str | None = None,
    api_key_env: str = "SILICONFLOW_API_KEY",
    timeout_seconds: float = 30.0,
    dimensions: int | None = None,
    normalize: bool = True,
):
    if provider == "hashing" or model_name == "hashing":
        return HashingEmbedder(dim=dim)
    if provider == "http":
        return HttpEmbedder(
            model_name,
            base_url=base_url,
            embeddings_url=embeddings_url,
            api_key_env=api_key_env,
            timeout_seconds=timeout_seconds,
            batch_size=batch_size,
            dim=dim,
            dimensions=dimensions,
            normalize=normalize,
        )
    return Embedder(model_name, device, batch_size)


def _embeddings_endpoint(base_url: str, embeddings_url: str | None) -> str:
    if embeddings_url:
        return embeddings_url
    stripped = base_url.rstrip("/")
    if stripped.endswith("/embeddings"):
        return stripped
    return f"{stripped}/embeddings"


def _read_dotenv_value(key: str, path: str | Path = ".env") -> str | None:
    dotenv_path = Path(path)
    if not dotenv_path.exists():
        return None
    prefix = f"{key}="
    for line in dotenv_path.read_text(encoding="utf-8").splitlines():
        stripped = line.strip()
        if not stripped or stripped.startswith("#") or not stripped.startswith(prefix):
            continue
        value = stripped[len(prefix) :].strip()
        if (value.startswith('"') and value.endswith('"')) or (value.startswith("'") and value.endswith("'")):
            value = value[1:-1]
        return value or None
    return None


def _extract_embeddings(payload: object, expected_count: int) -> np.ndarray:
    if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
        raise EmbeddingError("Embedding API response is missing data[].", {"response_type": type(payload).__name__})
    items = payload["data"]
    try:
        ordered = sorted(items, key=lambda item: int(item.get("index", 0)))
        vectors = [item["embedding"] for item in ordered]
    except (KeyError, TypeError, ValueError) as exc:
        raise EmbeddingError("Embedding API response has invalid data items.") from exc
    if len(vectors) != expected_count:
        raise EmbeddingError(
            "Embedding API returned an unexpected number of vectors.",
            {"expected": expected_count, "actual": len(vectors)},
        )
    try:
        return np.asarray(vectors, dtype=np.float32)
    except (TypeError, ValueError) as exc:
        raise EmbeddingError("Embedding API response contains non-numeric embeddings.") from exc


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
