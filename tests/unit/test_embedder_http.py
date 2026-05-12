from __future__ import annotations

import json
from urllib.error import HTTPError

import numpy as np
import pytest

from tagmemorag.embedder import HttpEmbedder, create_embedder
from tagmemorag.errors import EmbeddingError, InvalidConfigError


class _FakeResponse:
    def __init__(self, payload: dict):
        self.payload = payload

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def read(self):
        return json.dumps(self.payload).encode("utf-8")


def test_http_embedder_posts_openai_compatible_payload(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "secret")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        captured["timeout"] = timeout
        captured["headers"] = dict(request.header_items())
        captured["body"] = json.loads(request.data.decode("utf-8"))
        return _FakeResponse(
            {
                "data": [
                    {"index": 1, "embedding": [0.0, 3.0, 4.0]},
                    {"index": 0, "embedding": [1.0, 0.0, 0.0]},
                ]
            }
        )

    monkeypatch.setattr("tagmemorag.embedder.urlopen", fake_urlopen)
    embedder = HttpEmbedder(
        "Qwen/Qwen3-VL-Embedding-8B",
        base_url="https://api.siliconflow.cn/v1",
        api_key_env="SILICONFLOW_API_KEY",
        timeout_seconds=12,
        dimensions=4096,
    )

    vectors = embedder.encode_batch(["a", "b"])

    assert captured["url"] == "https://api.siliconflow.cn/v1/embeddings"
    assert captured["timeout"] == 12
    assert captured["headers"]["Authorization"] == "Bearer secret"
    assert captured["body"] == {
        "model": "Qwen/Qwen3-VL-Embedding-8B",
        "input": ["a", "b"],
        "encoding_format": "float",
        "dimensions": 4096,
    }
    np.testing.assert_allclose(vectors, np.array([[1.0, 0.0, 0.0], [0.0, 0.6, 0.8]], dtype=np.float32))


def test_http_embedder_uses_full_embeddings_url(monkeypatch):
    monkeypatch.setenv("EMBEDDING_KEY", "secret")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["url"] = request.full_url
        return _FakeResponse({"data": [{"index": 0, "embedding": [1.0, 2.0]}]})

    monkeypatch.setattr("tagmemorag.embedder.urlopen", fake_urlopen)
    embedder = HttpEmbedder(
        "model",
        embeddings_url="https://example.test/custom/embeddings",
        api_key_env="EMBEDDING_KEY",
        normalize=False,
    )

    np.testing.assert_allclose(embedder.encode_query("hello"), np.array([1.0, 2.0], dtype=np.float32))
    assert captured["url"] == "https://example.test/custom/embeddings"


def test_http_embedder_requires_api_key_env(monkeypatch):
    monkeypatch.delenv("MISSING_EMBEDDING_KEY", raising=False)

    with pytest.raises(InvalidConfigError) as exc:
        HttpEmbedder("model", api_key_env="MISSING_EMBEDDING_KEY")

    assert exc.value.code == "INVALID_CONFIG"
    assert exc.value.detail["api_key_env"] == "MISSING_EMBEDDING_KEY"


def test_http_embedder_reads_dotenv_key(tmp_path, monkeypatch):
    monkeypatch.chdir(tmp_path)
    monkeypatch.delenv("EMBEDDING_KEY", raising=False)
    (tmp_path / ".env").write_text("EMBEDDING_KEY=dotenv-secret\n", encoding="utf-8")
    captured = {}

    def fake_urlopen(request, timeout):
        captured["headers"] = dict(request.header_items())
        return _FakeResponse({"data": [{"index": 0, "embedding": [1.0]}]})

    monkeypatch.setattr("tagmemorag.embedder.urlopen", fake_urlopen)
    embedder = HttpEmbedder("model", api_key_env="EMBEDDING_KEY")

    embedder.encode_query("hello")

    assert captured["headers"]["Authorization"] == "Bearer dotenv-secret"


def test_http_embedder_wraps_http_error(monkeypatch):
    monkeypatch.setenv("EMBEDDING_KEY", "secret")

    def fake_urlopen(request, timeout):
        raise HTTPError(request.full_url, 429, "rate limited", hdrs=None, fp=None)

    monkeypatch.setattr("tagmemorag.embedder.urlopen", fake_urlopen)
    embedder = HttpEmbedder("model", api_key_env="EMBEDDING_KEY")

    with pytest.raises(EmbeddingError) as exc:
        embedder.encode_query("hello")

    assert exc.value.code == "EMBEDDING_FAILED"
    assert exc.value.detail["status_code"] == 429


def test_create_embedder_http_provider(monkeypatch):
    monkeypatch.setenv("SILICONFLOW_API_KEY", "secret")

    embedder = create_embedder(
        "Qwen/Qwen3-VL-Embedding-8B",
        provider="http",
        api_key_env="SILICONFLOW_API_KEY",
        base_url="https://api.siliconflow.cn/v1",
    )

    assert isinstance(embedder, HttpEmbedder)
