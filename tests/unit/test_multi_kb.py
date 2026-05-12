from __future__ import annotations

import time

import pytest

from tagmemorag.errors import RebuildInProgressError
from tagmemorag.state import AppState, build_kb, load_kb, save_kb


def test_multi_kb_save_load_and_state_isolation(tmp_path, test_config, fake_embedder):
    docs_a = tmp_path / "docs-a"
    docs_b = tmp_path / "docs-b"
    docs_a.mkdir()
    docs_b.mkdir()
    (docs_a / "manual.md").write_text("# A\n蒸汽功能。\n", encoding="utf-8")
    (docs_b / "manual.md").write_text("# B\n清洗功能。\n", encoding="utf-8")

    state_a = build_kb(docs_a, "kb-a", test_config, embedder=fake_embedder)
    state_b = build_kb(docs_b, "kb-b", test_config, embedder=fake_embedder)
    save_kb(state_a, test_config)
    save_kb(state_b, test_config)

    app = AppState()
    app.swap_kb("kb-a", load_kb("kb-a", test_config))
    app.swap_kb("kb-b", load_kb("kb-b", test_config))

    assert app.list_kbs() == ["kb-a", "kb-b"]
    assert app.get_kb("kb-a").build_id == state_a.build_id or app.get_kb("kb-a").kb_name == "kb-a"
    assert app.get_kb("kb-b").kb_name == "kb-b"


def test_same_kb_rebuild_rejected_but_different_kb_can_run(tmp_path, test_config, fake_embedder):
    class BlockingEmbedder:
        model_name = "blocking"

        def __init__(self, inner):
            self.inner = inner
            self.started = 0

        def encode_batch(self, texts):
            self.started += 1
            time.sleep(0.08)
            return self.inner.encode_batch(texts)

        def encode_query(self, text):
            return self.inner.encode_query(text)

    docs = tmp_path / "docs"
    docs.mkdir()
    (docs / "manual.md").write_text("# A\n蒸汽功能。\n", encoding="utf-8")
    app = AppState()
    blocker = BlockingEmbedder(fake_embedder)

    task_a = app.start_rebuild(docs, "kb-a", test_config, embedder=blocker)
    with pytest.raises(RebuildInProgressError):
        app.start_rebuild(docs, "kb-a", test_config, embedder=fake_embedder)
    task_b = app.start_rebuild(docs, "kb-b", test_config, embedder=fake_embedder)

    for _ in range(50):
        if task_a.status != "running" and task_b.status != "running":
            break
        time.sleep(0.02)

    assert task_a.status == "done"
    assert task_b.status == "done"
    assert set(app.list_kbs()) == {"kb-a", "kb-b"}
