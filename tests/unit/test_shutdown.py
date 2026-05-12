from __future__ import annotations

import asyncio
import threading
import time

import pytest
from fastapi.testclient import TestClient

from tagmemorag import api
from tagmemorag.state import AppState, build_kb


def test_rebuild_rejected_after_begin_shutdown(tmp_path, test_config, fake_embedder):
    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能可以打奶泡。\n", encoding="utf-8")
    api.settings = test_config
    api.embedder = fake_embedder
    api.app_state = AppState()
    api.app_state.begin_shutdown()
    client = TestClient(api.app)

    response = client.post("/rebuild", json={"docs_dir": str(docs)})

    assert response.status_code == 503
    assert response.json()["code"] == "SHUTTING_DOWN"


def test_shutdown_waits_for_rebuild(tmp_path, test_config, fake_embedder):
    """lifespan shutdown must block on _rebuild_lock until the rebuild worker releases it."""

    class BlockingEmbedder:
        model_name = "blocking"

        def __init__(self, inner):
            self.inner = inner
            self.started = threading.Event()
            self.release = threading.Event()

        def encode_batch(self, texts):
            self.started.set()
            self.release.wait(timeout=5)
            return self.inner.encode_batch(texts)

        def encode_query(self, text):
            return self.inner.encode_query(text)

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# 操作\n蒸汽功能。\n", encoding="utf-8")

    state = build_kb(docs, "default", test_config, embedder=fake_embedder)
    app_state = AppState(state)
    blocker = BlockingEmbedder(fake_embedder)
    task = app_state.start_rebuild(docs, "default", test_config, embedder=blocker)

    assert blocker.started.wait(timeout=2), "rebuild worker did not start"

    drain_started = threading.Event()
    drain_completed = threading.Event()

    async def drain():
        drain_started.set()
        await asyncio.to_thread(app_state._rebuild_lock.acquire)
        app_state._rebuild_lock.release()
        drain_completed.set()

    drain_thread = threading.Thread(target=lambda: asyncio.run(drain()), daemon=True)
    drain_thread.start()

    assert drain_started.wait(timeout=1)
    # drain must not complete while rebuild is still blocked
    assert not drain_completed.wait(timeout=0.2)

    blocker.release.set()

    # After blocker releases, rebuild finishes → drain completes
    assert drain_completed.wait(timeout=3), "drain did not complete after rebuild finished"
    drain_thread.join(timeout=2)

    # Rebuild succeeded end-to-end
    for _ in range(50):
        if task.status != "running":
            break
        time.sleep(0.02)
    assert task.status == "done"


def test_lifespan_startup_exits_on_warmup_failure(tmp_path, test_config, monkeypatch):
    """If embedder.encode_query raises during warmup, lifespan must sys.exit(1)."""

    class FailingEmbedder:
        model_name = "failing"

        def encode_batch(self, texts):
            raise RuntimeError("embed down")

        def encode_query(self, text):
            raise RuntimeError("warmup failure")

    api.settings = test_config
    api.embedder = FailingEmbedder()
    api.app_state = AppState()

    # TestClient / anyio swallow SystemExit into a CancelledError; observe via spy.
    recorded = {}

    def fake_exit(code=0):
        recorded["code"] = code
        raise SystemExit(code)

    monkeypatch.setattr(api.sys, "exit", fake_exit)

    with pytest.raises(BaseException):
        with TestClient(api.app):
            pass  # entering context triggers lifespan startup

    assert recorded.get("code") == 1, f"sys.exit(1) not called; recorded={recorded}"
