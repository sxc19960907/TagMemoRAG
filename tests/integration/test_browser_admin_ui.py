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


def test_browser_manual_library_to_qa_user_flow(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_browser_config(tmp_path, answer_enabled=True)
    seed_output = tmp_path / "library-qa-response.json"
    seed = subprocess.run(
        [
            sys.executable,
            "-m",
            "tagmemorag",
            "demo",
            "library-qa",
            "--config",
            str(config_path),
            "--output",
            str(seed_output),
        ],
        cwd=Path.cwd(),
        text=True,
        stdout=subprocess.PIPE,
        stderr=subprocess.STDOUT,
        check=True,
    )
    assert seed_output.exists(), seed.stdout

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
            console_errors: list[str] = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))
            try:
                _exercise_library_qa_user_flow(page, port)
                assert console_errors == []
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)


def test_browser_upload_manual_rebuild_then_qa_user_flow(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_browser_config(tmp_path, answer_enabled=True)
    upload_path = tmp_path / "browser-upload-service-manual.md"
    upload_path.write_text(
        "# 浏览器上传服务模式\n"
        "浏览器上传的手册说明：进入服务模式时，请同时按住清洗键和热水键三秒，屏幕显示 SVC 后松开。\n"
        "# 退出服务模式\n"
        "退出服务模式时，请按电源键一次并等待机器完成自检。\n",
        encoding="utf-8",
    )

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
            console_errors: list[str] = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))
            try:
                _exercise_upload_rebuild_qa_user_flow(page, port, upload_path)
                assert console_errors == []
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)


def test_browser_rag_failure_states_are_user_visible(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_browser_config(tmp_path, answer_enabled=True)
    upload_path = tmp_path / "pending-service-manual.md"
    upload_path.write_text(
        "# 待重建服务模式\n"
        "待重建的手册说明：进入服务模式时，请同时按住清洗键和热水键三秒。\n",
        encoding="utf-8",
    )

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
            console_errors: list[str] = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))
            try:
                _exercise_rag_failure_states(page, port, upload_path)
                assert console_errors == []
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)


def test_browser_qa_insufficient_evidence_refusal(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_browser_config(tmp_path, answer_enabled=True)
    upload_path = tmp_path / "limited-service-manual.md"
    upload_path.write_text(
        "# 服务模式\n"
        "进入服务模式时，请同时按住清洗键和热水键三秒，屏幕显示 SVC 后松开。\n",
        encoding="utf-8",
    )

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
            console_errors: list[str] = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))
            try:
                _exercise_qa_insufficient_evidence_refusal(page, port, upload_path)
                assert console_errors == []
            finally:
                browser.close()
    finally:
        server.terminate()
        try:
            server.wait(timeout=10)
        except subprocess.TimeoutExpired:
            server.kill()
            server.wait(timeout=10)


def test_browser_qa_followup_uses_conversation_context(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_browser_config(tmp_path, answer_enabled=True)
    upload_path = tmp_path / "followup-service-manual.md"
    upload_path.write_text(
        "# 蒸汽故障\n"
        "蒸汽很小时，请先清洗喷嘴并检查水箱水量。若仍然很小，请执行除垢程序。\n"
        "# 喷嘴清洁\n"
        "喷嘴堵塞时，用清洁针疏通喷嘴孔，并在蒸汽结束后冲洗十秒。\n",
        encoding="utf-8",
    )

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
            console_errors: list[str] = []
            page.on("console", lambda msg: console_errors.append(msg.text) if msg.type == "error" else None)
            page.on("pageerror", lambda exc: console_errors.append(str(exc)))
            try:
                _exercise_qa_followup_context(page, port, upload_path)
                assert console_errors == []
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
    assert page.locator("#quality-summary-needs-review").inner_text() == "1"
    assert page.locator("#quality-summary-promotable").inner_text() == "1"

    page.get_by_text("washer filter blocked", exact=True).click()
    assert "fb-ui-1" in page.locator("#quality-detail-subtitle").inner_text()
    assert "Capture the source that should have matched" in page.locator("#quality-review-guidance").inner_text()
    assert "washer/ui-washer.md" in page.locator("#quality-expected-evidence").inner_text()
    page.locator("#quality-operator-note").fill("Reviewed by browser automation")
    page.locator("#quality-save-review").click()
    page.locator("#quality-status").get_by_text("Review saved.").wait_for()
    assert "Review saved." in page.locator("#quality-status").inner_text()

    page.locator("#quality-preview").click()
    page.locator("#quality-promotion-preview").get_by_text("washer filter blocked").wait_for()
    assert "READY" in page.locator("#quality-promotion-summary").inner_text()
    assert "feedback-fb-ui-1" in page.locator("#quality-promotion-summary").inner_text()
    preview = page.locator("#quality-promotion-preview").inner_text()
    assert "washer filter blocked" in preview


def _exercise_library_qa_user_flow(page, port: int) -> None:
    page.goto(f"http://127.0.0.1:{port}/admin/manual-library?kb_name=default")
    page.get_by_role("heading", name="Manual Library").wait_for()
    page.locator("#status-strip").get_by_text("Loaded").wait_for()
    row = page.locator("#manual-rows tr").filter(has_text="demo-service-manual")
    row.wait_for()
    row_text = row.inner_text()
    assert "demo/demo-service-manual.md" in row_text
    assert "yes" in row_text
    assert "2" in row_text
    assert "clear" in row_text

    page.goto(f"http://127.0.0.1:{port}/qa?kb_name=default")
    page.get_by_role("heading", name="Manual Q&A").wait_for()
    page.locator("#ui-language-switcher select").select_option("zh")
    page.get_by_text("手册问答", exact=True).wait_for()
    page.locator("#ui-language-switcher select").select_option("en")
    page.get_by_role("textbox", name="Q&A question").fill("服务模式怎么进入？")
    page.get_by_role("button", name="Ask question").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
    answer_text = page.locator("#qa-answer").inner_text()
    assert "YOUR QUESTION" in answer_text
    assert "MANUAL ANSWER" in answer_text
    assert "服务模式怎么进入？" in answer_text
    assert "同时按住清洗键和热水键三秒" in answer_text
    sources_text = page.locator("#qa-sources").inner_text()
    assert "demo-service-manual.md" in sources_text
    assert "Cited manual passage" in sources_text
    page.locator(".qa-citation-chip").first.click()
    page.locator(".qa-source-item.active").wait_for()
    _assert_qa_layout(page)

    page.get_by_role("button", name="Not helpful").click()
    page.locator("#qa-feedback-note").get_by_text("Feedback sent to Retrieval Quality.").wait_for(timeout=10000)

    page.goto(f"http://127.0.0.1:{port}/admin/retrieval-quality?kb_name=default")
    page.get_by_role("heading", name="Retrieval Quality").wait_for()
    page.locator("#quality-status").get_by_text("Loaded 1 feedback records.").wait_for(timeout=10000)
    assert "1 records" in page.locator("#quality-count").inner_text()
    assert page.locator("#quality-summary-needs-review").inner_text() == "1"
    assert page.locator("#quality-summary-not-helpful").inner_text() == "1"
    assert "服务模式怎么进入？" in page.locator("#quality-feedback-rows").inner_text()
    assert "Not helpful" in page.locator("#quality-feedback-rows").inner_text()
    page.get_by_text("服务模式怎么进入？", exact=True).click()
    detail_text = page.locator("#quality-detail-list").inner_text()
    assert "Q&A feedback: not_helpful" in detail_text
    assert "Q&A" in detail_text
    assert "demo/demo-service-manual.md" in page.locator("#quality-selected-evidence").inner_text()
    assert "Review the cited evidence" in page.locator("#quality-review-guidance").inner_text()

    page.locator("#quality-preview").click()
    page.locator("#quality-promotion-summary").get_by_text("Needs input").wait_for(timeout=10000)
    summary_text = page.locator("#quality-promotion-summary").inner_text()
    assert "No usable relevant matcher" in summary_text
    assert "Add expected evidence" in summary_text


def _exercise_upload_rebuild_qa_user_flow(page, port: int, upload_path: Path) -> None:
    page.goto(f"http://127.0.0.1:{port}/admin/manual-library?kb_name=default")
    page.get_by_role("heading", name="Manual Library").wait_for()
    page.locator("#status-strip").get_by_text("Loaded 0 manuals from default.").wait_for()

    page.locator("#open-upload").click()
    assert page.locator("#upload-dialog").is_visible()
    page.locator("#upload-form input[name='file']").set_input_files(str(upload_path))
    page.locator("#upload-form input[name='manual_id']").fill("browser-upload-service-manual")
    page.locator("#upload-form input[name='title']").fill("Browser Upload Service Manual")
    page.locator("#upload-form input[name='source_file']").fill("browser/browser-upload-service-manual.md")
    page.locator("#upload-form input[name='product_category']").fill("coffee")
    page.locator("#upload-form input[name='language']").fill("zh-CN")
    page.locator("#upload-form textarea[name='tags']").fill("service-mode, browser-upload")
    page.locator("#upload-form input[name='trigger_rebuild']").check()
    page.locator("#validate-upload").click()
    page.locator("#upload-messages .message.success").wait_for()
    page.locator("#upload-form button.primary").click()
    page.locator("#library-next-step").get_by_text("Rebuilding search index").wait_for()

    row = page.locator("#manual-rows tr").filter(has_text="browser-upload-service-manual")
    row.wait_for()
    page.wait_for_function(
        """
        () => {
          const rows = [...document.querySelectorAll("#manual-rows tr")];
          const row = rows.find((item) => item.textContent.includes("browser-upload-service-manual"));
          if (!row) return false;
          const cells = [...row.querySelectorAll("td")].map((cell) => cell.textContent.trim());
          return cells.includes("yes") && cells.includes("clear") && Number(cells[9] || 0) > 0;
        }
        """,
        timeout=15000,
    )
    row_text = row.inner_text()
    assert "browser/browser-upload-service-manual.md" in row_text
    assert "yes" in row_text
    assert "1" in row_text or "2" in row_text
    assert "clear" in row_text
    assert "browser-upload" in row_text
    page.locator("#library-next-step").get_by_text("Manual is ready for Q&A").wait_for()
    assert "Ask in Q&A" in page.locator("#library-next-step").inner_text()

    page.locator("#manual-library-qa-link").click()
    page.get_by_role("heading", name="Manual Q&A").wait_for()
    assert page.url.endswith("/qa?kb_name=default")
    page.get_by_role("textbox", name="Q&A question").fill("浏览器上传的手册里，服务模式怎么进入？")
    page.get_by_role("button", name="Ask question").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
    answer_text = page.locator("#qa-answer").inner_text()
    assert "同时按住清洗键和热水键三秒" in answer_text
    sources_text = page.locator("#qa-sources").inner_text()
    assert "browser-upload-service-manual.md" in sources_text


def _assert_qa_layout(page) -> None:
    metrics = page.evaluate(
        """
        () => ({
          scrollWidth: document.body.scrollWidth,
          innerWidth: window.innerWidth,
          bubbleCount: document.querySelectorAll(".qa-message-bubble").length,
          centerTop: Math.round(document.querySelector(".qa-center-pane").getBoundingClientRect().top),
        })
        """,
    )
    assert metrics["scrollWidth"] <= metrics["innerWidth"]
    assert metrics["bubbleCount"] >= 2

    page.set_viewport_size({"width": 390, "height": 844})
    page.reload()
    page.get_by_role("heading", name="Manual Q&A").wait_for()
    mobile_metrics = page.evaluate(
        """
        () => ({
          scrollWidth: document.body.scrollWidth,
          innerWidth: window.innerWidth,
          centerTop: Math.round(document.querySelector(".qa-center-pane").getBoundingClientRect().top),
        })
        """,
    )
    assert mobile_metrics["scrollWidth"] <= mobile_metrics["innerWidth"]
    assert mobile_metrics["centerTop"] == 0
    page.set_viewport_size({"width": 1440, "height": 980})


def _exercise_rag_failure_states(page, port: int, upload_path: Path) -> None:
    page.goto(f"http://127.0.0.1:{port}/qa?kb_name=default")
    page.get_by_role("heading", name="Manual Q&A").wait_for()
    page.locator("#qa-question").fill("服务模式怎么进入？")
    page.locator("#qa-submit").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
    answer_text = page.locator("#qa-answer").inner_text()
    assert "not ready" in answer_text
    assert "import manuals and rebuild" in answer_text
    assert "No cited sources returned." in page.locator("#qa-sources").inner_text()

    page.goto(f"http://127.0.0.1:{port}/admin/manual-library?kb_name=default")
    page.get_by_role("heading", name="Manual Library").wait_for()
    page.locator("#status-strip").get_by_text("Loaded 0 manuals from default.").wait_for()
    assert "No managed manuals found." in page.locator("#table-empty").inner_text()

    page.locator("#open-upload").click()
    assert page.locator("#upload-dialog").is_visible()
    page.locator("#upload-form input[name='manual_id']").fill("invalid-upload")
    page.locator("#upload-form input[name='title']").fill("Invalid Upload")
    page.locator("#upload-form input[name='source_file']").fill("invalid/invalid-upload.md")
    page.locator("#validate-upload").click()
    page.locator("#upload-messages .message.error").wait_for()
    assert "manual metadata requires title, source_file, and product_category" in page.locator("#upload-messages").inner_text()
    page.locator("#close-upload").click()
    assert "No managed manuals found." in page.locator("#table-empty").inner_text()

    page.locator("#open-upload").click()
    page.locator("#upload-form input[name='file']").set_input_files(str(upload_path))
    page.locator("#upload-form input[name='manual_id']").fill("pending-service-manual")
    page.locator("#upload-form input[name='title']").fill("Pending Service Manual")
    page.locator("#upload-form input[name='source_file']").fill("pending/pending-service-manual.md")
    page.locator("#upload-form input[name='product_category']").fill("coffee")
    page.locator("#upload-form input[name='language']").fill("zh-CN")
    page.locator("#upload-form textarea[name='tags']").fill("service-mode, pending-rebuild")
    page.locator("#validate-upload").click()
    page.locator("#upload-messages .message.success").wait_for()
    page.locator("#upload-form button.primary").click()

    row = page.locator("#manual-rows tr").filter(has_text="pending-service-manual")
    row.wait_for()
    page.wait_for_function(
        """
        () => {
          const rows = [...document.querySelectorAll("#manual-rows tr")];
          const row = rows.find((item) => item.textContent.includes("pending-service-manual"));
          if (!row) return false;
          const cells = [...row.querySelectorAll("td")].map((cell) => cell.textContent.trim());
          return cells.includes("no") && cells.includes("required");
        }
        """,
        timeout=10000,
    )
    row_text = row.inner_text()
    assert "pending/pending-service-manual.md" in row_text
    assert "no" in row_text
    assert "required" in row_text
    assert "pending-rebuild" in row_text
    assert "1 dirty manual" in page.locator("#dirty-summary").inner_text()


def _exercise_qa_insufficient_evidence_refusal(page, port: int, upload_path: Path) -> None:
    page.goto(f"http://127.0.0.1:{port}/admin/manual-library?kb_name=default")
    page.get_by_role("heading", name="Manual Library").wait_for()
    page.locator("#status-strip").get_by_text("Loaded 0 manuals from default.").wait_for()

    page.locator("#open-upload").click()
    page.locator("#upload-form input[name='file']").set_input_files(str(upload_path))
    page.locator("#upload-form input[name='manual_id']").fill("limited-service-manual")
    page.locator("#upload-form input[name='title']").fill("Limited Service Manual")
    page.locator("#upload-form input[name='source_file']").fill("limited/limited-service-manual.md")
    page.locator("#upload-form input[name='product_category']").fill("coffee")
    page.locator("#upload-form input[name='language']").fill("zh-CN")
    page.locator("#upload-form textarea[name='tags']").fill("service-mode")
    page.locator("#upload-form input[name='trigger_rebuild']").check()
    page.locator("#validate-upload").click()
    page.locator("#upload-messages .message.success").wait_for()
    page.locator("#upload-form button.primary").click()
    row = page.locator("#manual-rows tr").filter(has_text="limited-service-manual")
    row.wait_for()
    page.wait_for_function(
        """
        () => {
          const rows = [...document.querySelectorAll("#manual-rows tr")];
          const row = rows.find((item) => item.textContent.includes("limited-service-manual"));
          if (!row) return false;
          const cells = [...row.querySelectorAll("td")].map((cell) => cell.textContent.trim());
          return cells.includes("yes") && cells.includes("clear") && Number(cells[9] || 0) > 0;
        }
        """,
        timeout=15000,
    )

    page.goto(f"http://127.0.0.1:{port}/qa?kb_name=default")
    page.get_by_role("heading", name="Manual Q&A").wait_for()
    page.locator("#qa-question").fill("这份手册有没有蒸汽泵配件编号？")
    page.locator("#qa-submit").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
    answer_text = page.locator("#qa-answer").inner_text()
    assert "证据不足" in answer_text
    assert "无法确认" in answer_text
    assert "进入服务模式" in answer_text
    assert "no results" not in answer_text.lower()
    assert "PN-" not in answer_text
    sources_text = page.locator("#qa-sources").inner_text()
    assert "limited-service-manual.md" in sources_text


def _exercise_qa_followup_context(page, port: int, upload_path: Path) -> None:
    page.goto(f"http://127.0.0.1:{port}/admin/manual-library?kb_name=default")
    page.get_by_role("heading", name="Manual Library").wait_for()
    page.locator("#status-strip").get_by_text("Loaded 0 manuals from default.").wait_for()

    page.locator("#open-upload").click()
    page.locator("#upload-form input[name='file']").set_input_files(str(upload_path))
    page.locator("#upload-form input[name='manual_id']").fill("followup-service-manual")
    page.locator("#upload-form input[name='title']").fill("Followup Service Manual")
    page.locator("#upload-form input[name='source_file']").fill("followup/followup-service-manual.md")
    page.locator("#upload-form input[name='product_category']").fill("coffee")
    page.locator("#upload-form input[name='language']").fill("zh-CN")
    page.locator("#upload-form textarea[name='tags']").fill("steam, nozzle")
    page.locator("#upload-form input[name='trigger_rebuild']").check()
    page.locator("#validate-upload").click()
    page.locator("#upload-messages .message.success").wait_for()
    page.locator("#upload-form button.primary").click()
    row = page.locator("#manual-rows tr").filter(has_text="followup-service-manual")
    row.wait_for()
    page.wait_for_function(
        """
        () => {
          const rows = [...document.querySelectorAll("#manual-rows tr")];
          const row = rows.find((item) => item.textContent.includes("followup-service-manual"));
          if (!row) return false;
          const cells = [...row.querySelectorAll("td")].map((cell) => cell.textContent.trim());
          return cells.includes("yes") && cells.includes("clear") && Number(cells[9] || 0) > 0;
        }
        """,
        timeout=15000,
    )

    page.goto(f"http://127.0.0.1:{port}/qa?kb_name=default")
    page.get_by_role("heading", name="Manual Q&A").wait_for()
    page.locator("#qa-question").fill("蒸汽很小怎么办？")
    page.locator("#qa-submit").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
    first_answer = page.locator("#qa-answer").inner_text()
    assert "清洗喷嘴" in first_answer
    assert "followup-service-manual.md" in page.locator("#qa-sources").inner_text()

    page.locator("#qa-question").fill("下一步呢？")
    page.locator("#qa-submit").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
    notice = page.locator("#qa-context-notice")
    notice.wait_for()
    notice_text = notice.inner_text()
    assert "Continuing from earlier" in notice_text
    assert "蒸汽很小怎么办？" in notice_text
    followup_answer = page.locator("#qa-answer").inner_text()
    assert "喷嘴" in followup_answer or "除垢" in followup_answer
    assert "followup-service-manual.md" in page.locator("#qa-sources").inner_text()


def _write_browser_config(tmp_path: Path, *, answer_enabled: bool = False) -> Path:
    config_path = tmp_path / "browser-ui-config.yaml"
    answer_block = "\nanswer:\n  enabled: true\n  provider: noop\n" if answer_enabled else ""
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
{answer_block}
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
