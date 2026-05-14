from __future__ import annotations

import os
import socket
import subprocess
import sys
import time
from pathlib import Path

import pytest

from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.embedder import HashingEmbedder
from tagmemorag.retrieval_feedback import create_feedback


RUN_BROWSER_UI = os.environ.get("TAGMEMORAG_RUN_BROWSER_UI") == "1"
pytestmark = pytest.mark.skipif(
    not RUN_BROWSER_UI,
    reason="set TAGMEMORAG_RUN_BROWSER_UI=1 to run browser admin UI integration tests",
)


def test_admin_ui_browser_workflows(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_browser_config(tmp_path)
    _seed_feedback(tmp_path)
    server = subprocess.Popen(
        [
            sys.executable,
            "-m",
            "tagmemorag",
            "serve",
            "--host",
            "127.0.0.1",
            "--port",
            str(port),
            "--config",
            str(config_path),
        ],
        cwd=Path.cwd(),
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        text=True,
    )
    try:
        _wait_for_server(port, server)
        with playwright.sync_playwright() as p:
            browser = p.chromium.launch()
            page = browser.new_page(viewport={"width": 1440, "height": 980})
            try:
                _exercise_manual_library(page, port)
                _exercise_retrieval_quality(page, port)
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)


def _exercise_manual_library(page, port: int) -> None:
    page.goto(f"http://127.0.0.1:{port}/admin/manual-library?kb_name=ui")
    page.get_by_role("heading", name="Manual Library").wait_for()
    page.locator("#status-strip").wait_for()
    assert "Loaded 0 manuals from ui." in page.locator("#status-strip").inner_text()
    assert "No managed manuals found." in page.locator("#table-empty").inner_text()

    page.locator("#filter-text").fill("washer")
    assert "0 of 0 manuals" in page.locator("#manual-count").inner_text()

    page.locator("#open-upload").click()
    assert page.locator("#upload-dialog").is_visible()
    page.locator("#upload-form input[name='manual_id']").fill("ui-washer")
    page.locator("#upload-form input[name='title']").fill("UI Washer Manual")
    page.locator("#upload-form input[name='source_file']").fill("washer/ui-washer.md")
    page.locator("#upload-form input[name='product_category']").fill("washer")
    page.locator("#upload-form input[name='language']").fill("zh-CN")
    page.locator("#upload-form textarea[name='tags']").fill("maintenance, filter-cleaning")
    page.locator("#validate-upload").click()
    page.locator("#upload-messages .message.success").wait_for()
    assert "Metadata is valid." in page.locator("#upload-messages").inner_text()

    page.locator("#close-upload").click()
    assert not page.locator("#upload-dialog").is_visible()

    page.locator("#open-tag-governance").click()
    assert page.locator("#tag-dialog").is_visible()
    page.locator("#tag-messages .message.success").wait_for()
    assert "tags" in page.locator("#tag-summary").inner_text()
    page.locator("#close-tag-governance").click()


def _exercise_retrieval_quality(page, port: int) -> None:
    page.goto(f"http://127.0.0.1:{port}/admin/retrieval-quality?kb_name=ui")
    page.get_by_role("heading", name="Retrieval Quality").wait_for()
    page.locator("#quality-status").wait_for()
    assert "Loaded 1 feedback records." in page.locator("#quality-status").inner_text()
    assert "1 records" in page.locator("#quality-count").inner_text()

    page.get_by_text("washer filter blocked", exact=True).click()
    assert "fb-ui-1" in page.locator("#quality-detail-subtitle").inner_text()
    page.locator("#quality-operator-note").fill("Reviewed by browser automation")
    page.locator("#quality-save-review").click()
    page.locator("#quality-status").get_by_text("Review saved.").wait_for()
    assert "Review saved." in page.locator("#quality-status").inner_text()

    page.locator("#quality-preview").click()
    page.locator("#quality-promotion-preview").get_by_text("washer filter blocked").wait_for()
    preview = page.locator("#quality-promotion-preview").inner_text()
    assert "washer filter blocked" in preview


def _write_browser_config(tmp_path: Path) -> Path:
    config_path = tmp_path / "browser-ui-config.yaml"
    config_path.write_text(
        f"""
model:
  provider: hashing
  name: hashing
  dim: 64
storage:
  data_dir: {tmp_path / "data"}
manual_library:
  root_dir: {tmp_path / "manuals"}
server:
  host: 127.0.0.1
  port: 0
auth:
  enabled: false
""",
        encoding="utf-8",
    )
    return config_path


def _seed_feedback(tmp_path: Path) -> None:
    cfg = Settings(
        storage=StorageConfig(data_dir=str(tmp_path / "data")),
        manual_library=ManualLibraryConfig(root_dir=str(tmp_path / "manuals")),
        model={"provider": "hashing", "name": "hashing", "dim": 64},
    )
    create_feedback(
        "ui",
        {
            "feedback_id": "fb-ui-1",
            "trace_id": "trace-ui",
            "search_id": "search-ui",
            "build_id": "build-ui",
            "query": "washer filter blocked",
            "outcome": "missing_result",
            "expected": [
                {
                    "source_file": "washer/ui-washer.md",
                    "header": "Filter",
                    "text_contains": ["blocked"],
                }
            ],
        },
        cfg,
    )


def _wait_for_server(port: int, process: subprocess.Popen, timeout: float = 20.0) -> None:
    deadline = time.time() + timeout
    while time.time() < deadline:
        if process.poll() is not None:
            output = process.stdout.read() if process.stdout else ""
            raise RuntimeError(f"server exited early with code {process.returncode}\n{output}")
        try:
            with socket.create_connection(("127.0.0.1", port), timeout=0.25):
                return
        except OSError:
            time.sleep(0.1)
    output = process.stdout.read() if process.stdout else ""
    raise RuntimeError(f"server did not start on port {port}\n{output}")


def _free_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])
