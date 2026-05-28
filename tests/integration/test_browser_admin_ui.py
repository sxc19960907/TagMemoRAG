from __future__ import annotations

import json
import os
import importlib.util
import shutil
import socket
import subprocess
import sys
import time
import zipfile
from io import BytesIO
from pathlib import Path

import pytest
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from tagmemorag.config import ManualLibraryConfig, Settings, StorageConfig
from tagmemorag.embedder import HashingEmbedder
from tagmemorag.retrieval_feedback import create_feedback


RUN_BROWSER_UI = os.environ.get("TAGMEMORAG_RUN_BROWSER_UI") == "1"
RUN_REAL_LLM_QA = os.environ.get("TAGMEMORAG_RUN_REAL_LLM_QA") == "1"
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


def test_browser_eval_report_viewer(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_browser_config(tmp_path)
    report_path = Path.cwd() / ".tmp" / "browser-ui" / f"{tmp_path.name}-browser-eval-report.json"
    report_path.parent.mkdir(parents=True, exist_ok=True)
    report_path.write_text(json.dumps(_eval_report_payload(), ensure_ascii=False), encoding="utf-8")
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
                page.goto(f"http://127.0.0.1:{port}/admin/eval-report?kb_name=default")
                page.get_by_role("heading", name="Eval Report", exact=True).wait_for()
                page.locator("#eval-run-suite").select_option("coffee_smoke")
                page.locator("#eval-run-start").click()
                page.locator("#eval-run-status").get_by_text("Open Report").wait_for(timeout=15000)
                assert "7 cases" in page.locator("#eval-run-status").inner_text()
                page.locator("#eval-run-load-report").click()
                page.locator("#eval-report-status").get_by_text("Eval report loaded.").wait_for(timeout=10000)
                assert "coffee.jsonl" in page.locator("#eval-report-title").inner_text()
                assert page.locator("#eval-report-count-total").inner_text() == "7"
                page.locator("#eval-report-recents").get_by_text(report_path.name).wait_for(timeout=10000)
                page.locator("#eval-report-recents button").filter(has_text=report_path.name).first.click()
                page.locator("#eval-report-status").get_by_text("Eval report loaded.").wait_for(timeout=10000)
                assert page.locator("#eval-report-path").input_value() == str(report_path)
                assert "Needs review" in page.locator("#eval-report-state").inner_text()
                assert "browser-feedback.jsonl" in page.locator("#eval-report-title").inner_text()
                assert page.locator("#eval-report-count-total").inner_text() == "2"
                assert page.locator("#eval-report-count-failed").inner_text() == "1"
                assert "failed-case" in page.locator("#eval-report-cases").inner_text()
                assert "Recommended Fix" in page.locator("#eval-report-cases").inner_text()
                assert "No expected evidence matched" in page.locator("#eval-report-cases").inner_text()
                assert "Check whether the expected source is built into the KB" in page.locator("#eval-report-cases").inner_text()
                assert "Ask in Q&A" in page.locator("#eval-report-cases").inner_text()
                assert "Open in Workbench" in page.locator("#eval-report-cases").inner_text()
                assert "coffee.md" in page.locator("#eval-report-cases").inner_text()
                qa_href = page.locator("#eval-report-cases a").filter(has_text="Ask in Q&A").first.get_attribute("href")
                assert qa_href is not None
                assert "/qa?" in qa_href
                assert "question=steam+is+weak" in qa_href
                page.goto(f"http://127.0.0.1:{port}{qa_href}")
                page.locator("#qa-status").get_by_text("Question prefilled.").wait_for(timeout=10000)
                assert page.locator("#qa-question").input_value() == "steam is weak"
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
        report_path.unlink(missing_ok=True)


def test_browser_rag_readiness_onboarding_guide(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_browser_config(tmp_path)
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
                _exercise_rag_readiness_onboarding(page, port)
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


def test_browser_qa_page_upload_rebuild_then_answer(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_browser_config(tmp_path, answer_enabled=True)
    upload_path = tmp_path / "qa-upload-steam-manual.md"
    upload_path.write_text(
        "# QA 页面上传蒸汽手册\n"
        "如果 QA 页面上传后的机器蒸汽很小，请先清洗蒸汽喷嘴，并确认水箱已经加满。\n"
        "# 后续检查\n"
        "如果清洗喷嘴后蒸汽仍然很小，请执行除垢程序并重新启动机器。\n",
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
                _exercise_qa_page_upload_rebuild_answer(page, port, upload_path)
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


def test_browser_upload_scanned_pdf_rebuilds_with_real_ocr_then_qa(tmp_path):
    if shutil.which("pdftoppm") is None or shutil.which("tesseract") is None:
        pytest.skip("requires local pdftoppm and tesseract commands")
    upload_path = Path.cwd() / ".tmp" / "ocr-samples" / "scanned-coffee-manual.pdf"
    if not upload_path.exists():
        pytest.skip("requires generated scanned PDF sample under .tmp/ocr-samples")

    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_browser_config(tmp_path, answer_enabled=True, ocr_enabled=True)

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
                _exercise_scanned_pdf_ocr_user_flow(page, port, upload_path)
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


def test_browser_upload_multiformat_manuals_then_qa_user_flow(tmp_path):
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_browser_config(tmp_path, answer_enabled=True)
    txt_path = tmp_path / "service-pressure-notes.txt"
    txt_path.write_text(
        "Pressure reset notes\n"
        "When code TXT-41 appears, hold the steam button for five seconds and refill the tank.\n",
        encoding="utf-8",
    )
    pdf_path = tmp_path / "pdf-gasket-calibration.pdf"
    _write_text_pdf(
        pdf_path,
        "PDF gasket calibration says error PDF-77 requires checking the steam sensor and reseating the brew gasket.",
    )
    docx_path = tmp_path / "docx-nozzle-care.docx"
    docx_path.write_bytes(
        _docx_bytes(
            "DOCX nozzle care",
            "When code DOCX-19 appears, clean the steam nozzle weekly and purge steam for ten seconds.",
        )
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
                _exercise_multiformat_upload_qa_user_flow(page, port, txt_path, pdf_path, docx_path)
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


def test_browser_pdf_source_preview_success_path_when_renderer_available(tmp_path):
    if importlib.util.find_spec("fitz") is None:
        pytest.skip("requires optional PyMuPDF/fitz for PDF page snapshot rendering")
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_browser_config(tmp_path, answer_enabled=True, assets_enabled=True)
    pdf_path = tmp_path / "pdf-preview-success.pdf"
    _write_text_pdf(
        pdf_path,
        "PREVIEW-88 confirms the cited PDF page preview path opens the original rendered page image.",
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
                _exercise_pdf_preview_success_flow(page, port, pdf_path)
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


def test_browser_real_product_pdf_source_preview_user_flow(tmp_path):
    if importlib.util.find_spec("fitz") is None:
        pytest.skip("requires optional PyMuPDF/fitz for PDF page snapshot rendering")
    real_pdfs = {
        "washer": Path("product_manuals/washer/ASKO W6564.pdf"),
        "oven": Path("product_manuals/oven/HISENSE BSA5221.pdf"),
    }
    if any(not path.exists() for path in real_pdfs.values()):
        pytest.skip("requires local real product PDF samples")
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_browser_config(tmp_path, answer_enabled=True, assets_enabled=True)

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
                _exercise_real_product_pdf_preview_flow(page, port, real_pdfs)
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


def test_browser_real_llm_qa_provider_acceptance(tmp_path):
    if not RUN_REAL_LLM_QA:
        pytest.skip("set TAGMEMORAG_RUN_REAL_LLM_QA=1 to run real LLM QA browser acceptance")
    api_key_env = os.environ.get("TAGMEMORAG_REAL_LLM_ANSWER_API_KEY_ENV", "DEEPSEEK_API_KEY")
    if not os.environ.get(api_key_env):
        pytest.skip(f"requires answer API key in ${api_key_env}")
    real_pdfs = {
        "washer": Path("product_manuals/washer/ASKO W6564.pdf"),
        "oven": Path("product_manuals/oven/HISENSE BSA5221.pdf"),
    }
    if any(not path.exists() for path in real_pdfs.values()):
        pytest.skip("requires local real product PDF samples")
    playwright = pytest.importorskip("playwright.sync_api")
    port = _free_port()
    config_path = _write_real_llm_browser_config(tmp_path, api_key_env=api_key_env)

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
                _exercise_real_llm_qa_provider_flow(page, port, real_pdfs)
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
    first_run = page.locator("#manual-first-run")
    assert first_run.is_visible()
    assert "Start with your first manual" in first_run.inner_text()
    assert "Upload" in first_run.inner_text()
    assert "Rebuild" in first_run.inner_text()
    assert "Ask" in first_run.inner_text()
    assert page.locator("#first-run-readiness").get_attribute("href") == "/admin/rag-readiness?kb_name=ui"
    assert page.locator("#first-run-qa").get_attribute("href") == "/qa?kb_name=ui"

    page.locator("#first-run-upload").click()
    assert page.locator("#upload-dialog").is_visible()
    page.locator("#close-upload").click()
    assert not page.locator("#upload-dialog").is_visible()

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
    assert "Ready to preview or export" in page.locator("#quality-triage-panel").inner_text()
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


def _exercise_rag_readiness_onboarding(page, port: int) -> None:
    page.goto(f"http://127.0.0.1:{port}/admin/rag-readiness?kb_name=default")
    page.get_by_role("heading", name="RAG Setup Guide").wait_for()
    page.locator("#readiness-status").get_by_text("Readiness loaded.").wait_for(timeout=10000)
    hero_text = page.locator(".readiness-hero").inner_text()
    assert "Next best action" in hero_text
    assert "Finish setup before Q&A" in hero_text
    assert "KB default" in hero_text
    assert "Manual Library" in page.locator("#readiness-primary-action").inner_text()
    assert page.locator("#readiness-primary-action a").get_attribute("href") == "/admin/manual-library?kb_name=default"
    steps_text = page.locator("#readiness-steps").inner_text()
    assert "Load the knowledge base" in steps_text
    assert "Index manuals" in steps_text
    assert "Check retrieval quality" in steps_text
    assert "Start Q&A" in steps_text
    progress_text = page.locator("#readiness-progress-label").inner_text()
    assert "of 4 steps ready" in progress_text
    capability_text = page.locator("#readiness-capabilities").inner_text()
    assert "Answer LLM" in capability_text
    assert "Embeddings" in capability_text
    assert "OCR" in capability_text
    assert "PDF Source Preview" in capability_text
    assert "Local embedding configuration is ready." in capability_text
    assert "Answer generation is disabled" in capability_text
    delivery_text = page.locator("#readiness-delivery").inner_text()
    assert "Handoff checklist" not in delivery_text
    assert "Validate configuration" in delivery_text
    assert "Run local RAG smoke" in delivery_text
    assert "Verify browser Q&A" in delivery_text
    assert "Retain a pilot report" in delivery_text
    assert "Verify live providers" in delivery_text
    assert "python -m tagmemorag readiness browser-qa" in delivery_text
    assert "production-provider verify --level smoke" in delivery_text
    cards_text = page.locator("#readiness-cards").inner_text()
    assert "KB Loaded" in cards_text
    assert "Manual Library" in cards_text
    assert "Retrieval Eval" in cards_text
    assert "User Q&A" in cards_text
    recommendations = page.locator("#readiness-recommendations").inner_text()
    assert "Build or load this KB before using Q&A." in recommendations
    assert "storage_key" not in page.locator("body").inner_text()
    assert "blob_key" not in page.locator("body").inner_text()
    assert "sk-" not in page.locator("body").inner_text()
    metrics = page.evaluate(
        """
        () => {
          const hero = document.querySelector(".readiness-hero").getBoundingClientRect();
          const steps = [...document.querySelectorAll(".readiness-step")].map((item) => item.getBoundingClientRect());
          const capabilities = [...document.querySelectorAll(".readiness-capability")].map((item) => item.getBoundingClientRect());
          const delivery = [...document.querySelectorAll(".readiness-delivery-check")].map((item) => item.getBoundingClientRect());
          const cards = [...document.querySelectorAll(".readiness-card")].map((item) => item.getBoundingClientRect());
          return {
            heroHeight: Math.round(hero.height),
            stepCount: steps.length,
            capabilityCount: capabilities.length,
            deliveryCount: delivery.length,
            cardCount: cards.length,
            minStepWidth: Math.round(Math.min(...steps.map((box) => box.width))),
            minCapabilityWidth: Math.round(Math.min(...capabilities.map((box) => box.width))),
            minDeliveryWidth: Math.round(Math.min(...delivery.map((box) => box.width))),
            minCardWidth: Math.round(Math.min(...cards.map((box) => box.width))),
          };
        }
        """
    )
    assert metrics["heroHeight"] > 140
    assert metrics["stepCount"] == 4
    assert metrics["capabilityCount"] == 4
    assert metrics["deliveryCount"] == 5
    assert metrics["cardCount"] == 4
    assert metrics["minStepWidth"] > 220
    assert metrics["minCapabilityWidth"] > 220
    assert metrics["minDeliveryWidth"] > 220
    assert metrics["minCardWidth"] > 220


def _exercise_library_qa_user_flow(page, port: int) -> None:
    page.goto(f"http://127.0.0.1:{port}/admin/manual-library?kb_name=default")
    page.get_by_role("heading", name="Manual Library").wait_for()
    page.locator("#status-strip").get_by_text("Loaded").wait_for()
    row = page.locator("#manual-rows tr").filter(has_text="demo-service-manual")
    row.wait_for()
    row_text = row.inner_text()
    assert "demo/demo-service-manual.md" in row_text
    assert "yes" in row_text
    assert "5" in row_text
    assert "clear" in row_text

    page.goto(f"http://127.0.0.1:{port}/qa?kb_name=default")
    page.get_by_role("heading", name="Manual Q&A").wait_for()
    _assert_qa_first_screen_guidance(page)
    page.locator("#ui-language-switcher select").select_option("zh")
    page.get_by_text("手册问答", exact=True).wait_for()
    page.locator("#ui-language-switcher select").select_option("en")
    page.get_by_role("textbox", name="Q&A question").fill("蒸汽很小怎么办？")
    page.get_by_role("button", name="Ask question").click()
    _assert_qa_loading_guidance_or_ready(page)
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
    answer_text = page.locator("#qa-answer").inner_text()
    assert "YOUR QUESTION" in answer_text
    assert "MANUAL ANSWER" in answer_text
    assert "蒸汽很小怎么办？" in answer_text
    assert "清洗喷嘴" in answer_text
    assert page.locator("#qa-copy-answer").is_enabled()
    sources_text = page.locator("#qa-sources").inner_text()
    assert "demo-service-manual.md" in sources_text
    assert "Cited manual passage" in sources_text
    assert "Click a citation in the answer to focus a source." in page.locator("#qa-source-meta").inner_text()
    followups_text = page.locator("#qa-followups").inner_text()
    assert "Suggested follow-ups" in followups_text
    assert "These will continue from the current answer when useful." in followups_text
    feedback_text = page.locator("#qa-feedback").inner_text()
    assert "Was this useful?" in feedback_text
    assert "Helpful" in feedback_text
    assert "Not helpful" in feedback_text
    page.locator(".qa-citation-chip").first.click()
    page.locator(".qa-source-item.active").wait_for()
    _assert_qa_layout(page)

    page.get_by_role("button", name="Not helpful").click()
    page.locator("#qa-feedback-note").get_by_text("Feedback sent to Retrieval Quality.").wait_for(timeout=10000)
    review_link = page.locator("#qa-feedback-note a.qa-feedback-review-link")
    review_link.get_by_text("Review this case").wait_for(timeout=10000)
    review_href = review_link.get_attribute("href") or ""
    assert "/admin/retrieval-quality?" in review_href
    assert "kb_name=default" in review_href
    assert "feedback_id=" in review_href
    review_feedback_id = review_href.split("feedback_id=", 1)[1].split("&", 1)[0]

    review_link.click()
    page.get_by_role("heading", name="Retrieval Quality").wait_for()
    page.locator("#quality-status").get_by_text("Loaded 1 feedback records.").wait_for(timeout=10000)
    assert "1 records" in page.locator("#quality-count").inner_text()
    assert page.locator("#quality-summary-needs-review").inner_text() == "1"
    assert page.locator("#quality-summary-not-helpful").inner_text() == "1"
    assert "蒸汽很小怎么办？" in page.locator("#quality-feedback-rows").inner_text()
    assert "Not helpful" in page.locator("#quality-feedback-rows").inner_text()
    selected_id = page.locator("#quality-detail-subtitle").inner_text()
    assert selected_id == review_feedback_id
    detail_text = page.locator("#quality-detail-list").inner_text()
    assert "Q&A feedback: not_helpful" in detail_text
    assert "Q&A" in detail_text
    assert "demo/demo-service-manual.md" in page.locator("#quality-selected-evidence").inner_text()
    assert "Review the cited evidence" in page.locator("#quality-review-guidance").inner_text()
    triage_text = page.locator("#quality-triage-panel").inner_text()
    assert "NEEDS EXPECTED EVIDENCE" in triage_text
    assert "Use selected evidence" in triage_text

    page.locator("#quality-preview").click()
    page.locator("#quality-promotion-summary").get_by_text("Needs input").wait_for(timeout=10000)
    summary_text = page.locator("#quality-promotion-summary").inner_text()
    assert "No usable relevant matcher" in summary_text
    assert "Add expected evidence" in summary_text

    page.locator("#quality-use-selected-expected").click()
    assert "demo/demo-service-manual.md" in page.locator("#quality-expected-source").input_value()
    page.locator("#quality-expected-text").fill("清洗喷嘴")
    page.locator("#quality-mark-triaged").click()
    page.locator("#quality-status").get_by_text("Review saved.").wait_for(timeout=10000)
    assert "triaged" in page.locator("#quality-feedback-rows").inner_text()
    assert "Ready to preview or export" in page.locator("#quality-triage-panel").inner_text()
    assert "清洗喷嘴" in page.locator("#quality-expected-evidence").inner_text()
    page.locator("#quality-preview").click()
    page.locator("#quality-status").get_by_text("Previewed 1 eval cases.").wait_for(timeout=10000)
    ready_text = page.locator("#quality-promotion-summary").inner_text()
    assert "feedback-" in ready_text
    assert "蒸汽很小怎么办？" in ready_text
    assert "tagmemorag eval run --suite" in ready_text
    assert "--reuse-built-kb" in ready_text
    assert "--output" in ready_text
    assert "Report:" in ready_text
    assert "currently built KB" in ready_text
    assert "Run in browser" in ready_text
    assert "Matcher has specific anchor or text evidence." in ready_text
    assert "feedback-" in page.locator("#quality-promotion-preview").inner_text()
    page.locator("#quality-export").click()
    page.locator("#quality-status").get_by_text("Loaded 1 feedback records.").wait_for(timeout=10000)
    exported_text = page.locator("#quality-promotion-summary").inner_text()
    assert "tagmemorag eval run --suite" in exported_text
    assert "Run in browser" in exported_text
    run_href = page.locator("#quality-promotion-summary a").filter(has_text="Run in browser").first.get_attribute("href")
    assert run_href is not None
    assert "/admin/eval-report?" in run_href
    assert "suite_path=" in run_href
    page.goto(f"http://127.0.0.1:{port}{run_href}")
    page.get_by_role("heading", name="Eval Report", exact=True).wait_for()
    page.wait_for_function(
        "() => [...document.querySelectorAll('#eval-run-suite option')].some((option) => option.textContent.includes('Feedback draft'))",
        timeout=10000,
    )
    selected_label = page.locator("#eval-run-suite").evaluate(
        "(select) => select.options[select.selectedIndex]?.textContent || ''"
    )
    assert "Feedback draft" in selected_label
    assert "1 cases" in selected_label
    assert "Uses current KB" in page.locator("#eval-run-status").inner_text()
    page.locator("#eval-run-start").click()
    page.locator("#eval-run-status").get_by_text("Open Report").wait_for(timeout=15000)
    assert "1 cases" in page.locator("#eval-run-status").inner_text()
    page.goto(f"http://127.0.0.1:{port}/admin/retrieval-quality?kb_name=default")
    page.get_by_role("heading", name="Retrieval Quality").wait_for()
    page.locator("#quality-status").get_by_text("Loaded 1 feedback records.").wait_for(timeout=10000)
    assert "promoted" in page.locator("#quality-feedback-rows").inner_text()


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


def _exercise_qa_page_upload_rebuild_answer(page, port: int, upload_path: Path) -> None:
    page.goto(f"http://127.0.0.1:{port}/qa?kb_name=default")
    page.get_by_role("heading", name="Manual Q&A").wait_for()
    _assert_qa_first_screen_guidance(page)
    page.locator("#qa-answer").get_by_text("Start by adding a manual").wait_for(timeout=10000)
    assert "Add a manual to begin" in page.locator("#qa-answer-meta").inner_text()
    assert "Choose a manual" in page.locator("#qa-answer").inner_text()
    assert "Add manual" in page.locator(".qa-upload-card").inner_text()
    assert page.locator("#qa-manual-library-link").get_attribute("href") == "/admin/manual-library?kb_name=default"

    page.locator("#qa-upload-file").set_input_files(str(upload_path))
    assert page.locator("#qa-upload-title").input_value() == "Qa Upload Steam Manual"
    assert page.locator("#qa-upload-source").input_value() == "uploads/qa-upload-steam-manual.md"
    assert page.locator("#qa-upload-category").input_value() == "manual"
    page.locator("#qa-upload-title").fill("QA Upload Steam Manual")
    page.locator("#qa-upload-category").fill("coffee")
    page.locator("#qa-upload-language").fill("zh-CN")
    page.locator("#qa-upload-tags").fill("steam, qa-upload")
    page.locator("#qa-upload-submit").click()
    page.locator("#qa-upload-messages").get_by_text("Manual is indexed. Ask a question about it below.").wait_for(timeout=15000)
    page.locator("#qa-status").get_by_text("Manual is ready for Q&A.").wait_for(timeout=10000)
    suggestions_text = page.locator("#qa-suggestions").inner_text()
    assert "这份手册里，蒸汽很小怎么办？" in suggestions_text
    assert "QA Upload Steam Manual 有哪些常见故障处理步骤？" in suggestions_text

    page.locator("#qa-suggestions button").filter(has_text="这份手册里，蒸汽很小怎么办？").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
    answer_text = page.locator("#qa-answer").inner_text()
    assert "清洗蒸汽喷嘴" in answer_text
    assert "水箱" in answer_text
    sources_text = page.locator("#qa-sources").inner_text()
    assert "qa-upload-steam-manual.md" in sources_text
    assert "Cited manual passage" in sources_text


def _exercise_scanned_pdf_ocr_user_flow(page, port: int, upload_path: Path) -> None:
    page.goto(f"http://127.0.0.1:{port}/admin/manual-library?kb_name=default")
    page.get_by_role("heading", name="Manual Library").wait_for()
    page.locator("#status-strip").get_by_text("Loaded 0 manuals from default.").wait_for()

    page.locator("#open-upload").click()
    assert page.locator("#upload-dialog").is_visible()
    page.locator("#upload-form input[name='file']").set_input_files(str(upload_path))
    page.locator("#upload-form input[name='manual_id']").fill("scanned-coffee-manual")
    page.locator("#upload-form input[name='title']").fill("Scanned Coffee Manual")
    page.locator("#upload-form input[name='source_file']").fill("coffee/scanned-coffee-manual.pdf")
    page.locator("#upload-form input[name='product_category']").fill("coffee")
    page.locator("#upload-form input[name='language']").fill("en")
    page.locator("#upload-form textarea[name='tags']").fill("ocr, scanned, steam")
    page.locator("#upload-form input[name='trigger_rebuild']").check()
    page.locator("#validate-upload").click()
    page.locator("#upload-messages .message.success").wait_for()
    page.locator("#upload-form button.primary").click()
    page.locator("#library-next-step").get_by_text("Rebuilding search index").wait_for()

    row = page.locator("#manual-rows tr").filter(has_text="scanned-coffee-manual")
    row.wait_for()
    page.wait_for_function(
        """
        () => {
          const rows = [...document.querySelectorAll("#manual-rows tr")];
          const row = rows.find((item) => item.textContent.includes("scanned-coffee-manual"));
          if (!row) return false;
          const cells = [...row.querySelectorAll("td")].map((cell) => cell.textContent.trim());
          return cells.includes("yes") && cells.includes("clear") && Number(cells[9] || 0) > 0;
        }
        """,
        timeout=60000,
    )
    row_text = row.inner_text()
    assert "coffee/scanned-coffee-manual.pdf" in row_text
    assert "yes" in row_text
    assert "clear" in row_text
    assert "ocr" in row_text
    page.locator("#library-next-step").get_by_text("Manual is ready for Q&A").wait_for()

    diagnostics = page.evaluate(
        """
        async () => {
          const response = await fetch("/manual-library/diagnostics?kb_name=default&include_jobs=true");
          if (!response.ok) throw new Error(await response.text());
          return response.json();
        }
        """
    )
    last_rebuild = diagnostics["last_rebuild"]
    ocr = last_rebuild["ocr"]
    pdf_quality = last_rebuild["pdf_quality"]
    assert ocr["enabled"] is True
    assert ocr["provider"] == "tesseract_cli"
    assert ocr["attempted"] >= 1
    assert ocr["created"] >= 1
    assert ocr["failed"] == 0
    assert all(command["available"] for command in ocr["commands"])
    assert pdf_quality["pages_missing_text"] >= 1
    assert pdf_quality["ocr_pages_created"] >= 1
    assert "install_ocr_commands" not in {item["code"] for item in diagnostics["recommendations"]}
    assert "Weak Steam" not in json.dumps(diagnostics)
    diagnostics_text = page.locator("#diagnostics-cards").inner_text()
    assert "OCR" in diagnostics_text
    assert "tesseract_cli" in diagnostics_text
    assert "missing commands" not in diagnostics_text

    page.goto(f"http://127.0.0.1:{port}/qa?kb_name=default")
    page.get_by_role("heading", name="Manual Q&A").wait_for()
    page.get_by_role("textbox", name="Q&A question").fill("What should I do when weak steam appears with STEAM-042?")
    page.get_by_role("button", name="Ask question").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=15000)
    answer_text = page.locator("#qa-answer").inner_text()
    sources_text = page.locator("#qa-sources").inner_text()
    evidence_text = f"{answer_text}\n{sources_text}"
    assert "scanned-coffee-manual.pdf" in sources_text
    assert "STEAM-042" in evidence_text or "steam nozzle" in evidence_text or "Weak Steam" in evidence_text


def _exercise_multiformat_upload_qa_user_flow(page, port: int, txt_path: Path, pdf_path: Path, docx_path: Path) -> None:
    page.goto(f"http://127.0.0.1:{port}/admin/manual-library?kb_name=default")
    page.get_by_role("heading", name="Manual Library").wait_for()
    page.locator("#status-strip").get_by_text("Loaded 0 manuals from default.").wait_for()

    uploads = [
        {
            "path": txt_path,
            "manual_id": "txt-pressure-notes",
            "title": "TXT Pressure Notes",
            "source_file": "mixed/service-pressure-notes.txt",
            "tag": "txt-format",
            "ready_source": "mixed/service-pressure-notes.txt",
            "question": "What should I do when TXT-41 appears?",
            "expected": ("TXT-41", "steam button", "refill the tank"),
        },
        {
            "path": pdf_path,
            "manual_id": "pdf-gasket-calibration",
            "title": "PDF Gasket Calibration",
            "source_file": "mixed/pdf-gasket-calibration.pdf",
            "tag": "pdf-format",
            "ready_source": "mixed/pdf-gasket-calibration.pdf",
            "question": "What does PDF-77 require?",
            "expected": ("PDF-77", "steam sensor", "brew gasket"),
        },
        {
            "path": docx_path,
            "manual_id": "docx-nozzle-care",
            "title": "DOCX Nozzle Care",
            "source_file": "mixed/docx-nozzle-care.docx",
            "tag": "docx-format",
            "ready_source": "mixed/docx-nozzle-care.md",
            "question": "What should I do when DOCX-19 appears?",
            "expected": ("DOCX-19", "steam nozzle", "ten seconds"),
        },
    ]
    for upload in uploads:
        _upload_manual_from_library_dialog(page, upload)

    records = page.evaluate(
        """
        async () => {
          const response = await fetch("/manual-library?kb_name=default");
          if (!response.ok) throw new Error(await response.text());
          return response.json();
        }
        """
    )["manuals"]
    by_id = {record["manual_id"]: record for record in records}
    assert set(by_id) == {"txt-pressure-notes", "pdf-gasket-calibration", "docx-nozzle-care"}
    for upload in uploads:
        record = by_id[upload["manual_id"]]
        assert record["source_file"] == upload["ready_source"]
        assert record["searchable"] is True
        assert int(record["chunk_count"]) > 0
        assert record["rebuild_required"] is False
    docx_record = by_id["docx-nozzle-care"]
    assert docx_record["metadata"]["source_format"] == "docx"
    assert docx_record["metadata"]["remote_id"] == "mixed/docx-nozzle-care.docx"

    diagnostics = page.evaluate(
        """
        async () => {
          const response = await fetch("/manual-library/diagnostics?kb_name=default&include_jobs=true");
          if (!response.ok) throw new Error(await response.text());
          return response.json();
        }
        """
    )
    assert diagnostics["dirty"]["pending_changes"] is False
    pdf_quality = diagnostics["last_rebuild"]["pdf_quality"]
    assert pdf_quality["documents"] >= 1
    assert pdf_quality["pages_with_text"] >= 1
    assert "PDF-77" not in json.dumps(diagnostics)
    assert "DOCX-19" not in json.dumps(diagnostics)
    assert "TXT-41" not in json.dumps(diagnostics)

    page.goto(f"http://127.0.0.1:{port}/qa?kb_name=default")
    page.get_by_role("heading", name="Manual Q&A").wait_for()
    for upload in uploads:
        page.get_by_role("textbox", name="Q&A question").fill(upload["question"])
        page.get_by_role("button", name="Ask question").click()
        page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
        answer_text = page.locator("#qa-answer").inner_text()
        sources_text = page.locator("#qa-sources").inner_text()
        evidence_text = f"{answer_text}\n{sources_text}"
        assert Path(upload["ready_source"]).name in sources_text
        assert any(expected in evidence_text for expected in upload["expected"])

        first_chip = page.locator(".qa-citation-chip").first
        first_chip.wait_for()
        first_chip.click()
        page.locator(".qa-source-item.active").wait_for()
        assert page.locator(".qa-source-item.active").get_attribute("data-citation-id")
        page.locator(".qa-source-item.active .qa-source-badge").first.wait_for()
        active_source = page.locator(".qa-source-item.active")
        active_source.locator(".qa-source-verify").wait_for()
        assert "Verify original source" in active_source.inner_text()
        preview_links = active_source.locator("[data-source-preview]")
        if preview_links.count():
            preview_href = preview_links.first.get_attribute("href") or ""
            assert preview_href.startswith("/assets/")
            assert "kb_name=default" in preview_href
            assert "storage_key" not in preview_href
            assert "blob_key" not in preview_href
        else:
            active_source.locator("[data-source-preview-unavailable]").wait_for()
            assert "Preview unavailable" in active_source.inner_text()
            if str(upload["manual_id"]) == "pdf-gasket-calibration":
                assert (
                    "PDF snapshot renderer is missing" in active_source.inner_text()
                    or "Use the cited passage" in active_source.inner_text()
                )

        if str(upload["manual_id"]) == "pdf-gasket-calibration":
            assert "Page" in sources_text or "Pages" in sources_text
            assert "Verify original source" in active_source.inner_text()
        if str(upload["manual_id"]) == "docx-nozzle-care":
            assert "docx-nozzle-care.docx" in sources_text
            assert "Converted from DOCX" in sources_text
            assert "Indexed as mixed/docx-nozzle-care.md" in sources_text
            page.locator(".qa-source-item").filter(has_text="docx-nozzle-care.docx").get_by_text("Converted from DOCX").wait_for()

        toggle = page.locator(".qa-source-item.active [data-source-toggle]").first
        if toggle.count():
            toggle.click()
            assert "Show less" in page.locator(".qa-source-item.active").inner_text()

    page.locator("#ui-language-switcher select").select_option("zh")
    page.get_by_text("手册问答", exact=True).wait_for()
    page.locator("#ui-language-switcher select").select_option("en")

    history_item = page.locator(".qa-history-item").filter(has_text="DOCX-19").first
    history_item.wait_for()
    history_item.click()
    assert "DOCX-19" in page.locator("#qa-answer").inner_text()
    assert "docx-nozzle-care.docx" in page.locator("#qa-sources").inner_text()
    page.locator("#qa-sources .qa-source-verify").first.wait_for()
    _assert_qa_layout(page)


def _upload_manual_from_library_dialog(page, upload: dict[str, object]) -> None:
    page.locator("#open-upload").click()
    assert page.locator("#upload-dialog").is_visible()
    page.locator("#upload-form input[name='file']").set_input_files(str(upload["path"]))
    page.locator("#upload-form input[name='manual_id']").fill(str(upload["manual_id"]))
    page.locator("#upload-form input[name='title']").fill(str(upload["title"]))
    page.locator("#upload-form input[name='source_file']").fill(str(upload["source_file"]))
    page.locator("#upload-form input[name='product_category']").fill("coffee")
    page.locator("#upload-form input[name='language']").fill("en")
    page.locator("#upload-form textarea[name='tags']").fill(str(upload["tag"]))
    page.locator("#upload-form input[name='trigger_rebuild']").check()
    page.locator("#validate-upload").click()
    page.locator("#upload-messages .message.success").wait_for()
    page.locator("#upload-form button.primary").click()
    row = page.locator("#manual-rows tr").filter(has_text=str(upload["manual_id"]))
    row.wait_for()
    page.wait_for_function(
        """
        (manualId) => {
          const rows = [...document.querySelectorAll("#manual-rows tr")];
          const row = rows.find((item) => item.textContent.includes(manualId));
          if (!row) return false;
          const cells = [...row.querySelectorAll("td")].map((cell) => cell.textContent.trim());
          return cells.includes("yes") && cells.includes("clear") && Number(cells[9] || 0) > 0;
        }
        """,
        arg=str(upload["manual_id"]),
        timeout=30000,
    )
    row_text = row.inner_text()
    assert str(upload["ready_source"]) in row_text
    assert str(upload["tag"]) in row_text
    assert "yes" in row_text
    assert "clear" in row_text
    page.locator("#library-next-step").get_by_text("Manual is ready for Q&A").wait_for()


def _exercise_pdf_preview_success_flow(page, port: int, pdf_path: Path) -> None:
    page.goto(f"http://127.0.0.1:{port}/admin/manual-library?kb_name=default")
    page.get_by_role("heading", name="Manual Library").wait_for()
    page.locator("#status-strip").get_by_text("Loaded 0 manuals from default.").wait_for()
    _upload_manual_from_library_dialog(
        page,
        {
            "path": pdf_path,
            "manual_id": "pdf-preview-success",
            "title": "PDF Preview Success",
            "source_file": "preview/pdf-preview-success.pdf",
            "tag": "pdf-preview",
            "ready_source": "preview/pdf-preview-success.pdf",
        },
    )

    diagnostics = page.evaluate(
        """
        async () => {
          const response = await fetch("/manual-library/diagnostics?kb_name=default&include_jobs=true");
          if (!response.ok) throw new Error(await response.text());
          return response.json();
        }
        """
    )
    source_preview = diagnostics["last_rebuild"]["source_preview"]
    assert source_preview["status"] == "ready"
    assert source_preview["page_snapshots_ready"] >= 1
    assert source_preview["renderer_available"] is True
    assert "storage_key" not in json.dumps(source_preview)

    page.goto(f"http://127.0.0.1:{port}/qa?kb_name=default")
    page.get_by_role("heading", name="Manual Q&A").wait_for()
    page.get_by_role("textbox", name="Q&A question").fill("What does PREVIEW-88 confirm?")
    page.get_by_role("button", name="Ask question").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
    page.locator(".qa-citation-chip").first.click()
    active_source = page.locator(".qa-source-item.active")
    active_source.wait_for()
    preview = active_source.locator("[data-source-preview]").first
    preview.wait_for()
    preview_href = preview.get_attribute("href") or ""
    assert preview_href.startswith("/assets/")
    assert "kb_name=default" in preview_href
    assert "storage_key" not in preview_href
    asset_response = page.request.get(f"http://127.0.0.1:{port}{preview_href}")
    assert asset_response.status == 200
    assert asset_response.headers.get("content-type", "").startswith("image/png")
    assert asset_response.headers.get("x-document-asset-id")
    assert len(asset_response.body()) > 100


def _exercise_real_product_pdf_preview_flow(page, port: int, pdf_paths: dict[str, Path]) -> None:
    page.goto(f"http://127.0.0.1:{port}/admin/manual-library?kb_name=default")
    page.get_by_role("heading", name="Manual Library").wait_for()
    page.locator("#status-strip").get_by_text("Loaded 0 manuals from default.").wait_for()
    uploads = [
        {
            "path": pdf_paths["washer"],
            "manual_id": "asko-w6564-real",
            "title": "ASKO W6564 Real Washer Manual",
            "source_file": "real/ASKO W6564.pdf",
            "tag": "real-pdf-preview",
            "ready_source": "real/ASKO W6564.pdf",
            "question": "ASKO W6564 如何清潔過濾器和排水馬達？",
            "source_name": "ASKO W6564.pdf",
            "expected_terms": ["過濾器", "排水馬達", "清潔"],
            "forbidden_terms": ["Steam Clean", "0.6 l", "BSA5221"],
            "unsupported": False,
        },
        {
            "path": pdf_paths["oven"],
            "manual_id": "hisense-bsa5221-real",
            "title": "HISENSE BSA5221 Real Oven Manual",
            "source_file": "real/HISENSE BSA5221.pdf",
            "tag": "real-pdf-preview",
            "ready_source": "real/HISENSE BSA5221.pdf",
            "question": "How do I use Steam Clean on the HISENSE BSA5221 oven?",
            "source_name": "HISENSE BSA5221.pdf",
            "expected_terms": ["Steam Clean", "70", "water", "damp cloth"],
            "forbidden_terms": ["ASKO W6564", "排水馬達", "過濾器"],
            "unsupported": False,
        },
        {
            "question": "ASKO W6564 排水馬達故障時是不是要直接換泵？",
            "source_name": "ASKO W6564.pdf",
            "expected_terms": [],
            "forbidden_terms": ["Steam Clean", "BSA5221", "oven", "telescopic", "catalytic", "必须立即", "必須立即", "直接換泵"],
            "unsupported": True,
        },
    ]
    for upload in uploads[:2]:
        _upload_manual_from_library_dialog(page, upload)

    diagnostics = page.evaluate(
        """
        async () => {
          const response = await fetch("/manual-library/diagnostics?kb_name=default&include_jobs=true");
          if (!response.ok) throw new Error(await response.text());
          return response.json();
        }
        """
    )
    source_preview = diagnostics["last_rebuild"]["source_preview"]
    assert source_preview["status"] == "ready"
    assert source_preview["page_snapshots_ready"] >= 2
    assert source_preview["renderer_available"] is True
    assert "storage_key" not in json.dumps(source_preview)

    page.goto(f"http://127.0.0.1:{port}/qa?kb_name=default")
    page.get_by_role("heading", name="Manual Q&A").wait_for()
    for upload in uploads:
        page.get_by_role("textbox", name="Q&A question").fill(str(upload["question"]))
        page.get_by_role("button", name="Ask question").click()
        page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=15000)
        answer_text = page.locator("#qa-answer").inner_text()
        sources_text = page.locator("#qa-sources").inner_text()
        answer_without_question = answer_text.replace(str(upload["question"]), "")
        evidence_text = f"{answer_without_question}\n{sources_text}"
        evidence_text_casefold = evidence_text.casefold()
        assert str(upload["source_name"]) in sources_text
        if not upload["unsupported"]:
            assert any(str(term).casefold() in evidence_text_casefold for term in upload["expected_terms"]), {
                "question": upload["question"],
                "expected_terms": upload["expected_terms"],
                "answer": answer_without_question,
                "sources": sources_text,
            }
        forbidden_hits = [term for term in upload["forbidden_terms"] if str(term).casefold() in evidence_text_casefold]
        assert forbidden_hits == [], {
            "question": upload["question"],
            "forbidden_hits": forbidden_hits,
            "answer": answer_text,
            "sources": sources_text,
        }
        assert not any(leak in evidence_text for leak in ["storage_key", "blob_key", "checksum", "node_id", "anchor_key"])
        if upload["unsupported"]:
            assert "證據不足" in answer_without_question or "证据不足" in answer_without_question or "insufficient" in answer_without_question
            assert "直接換泵" not in answer_without_question
            assert "直接换泵" not in answer_without_question
        else:
            assert "證據不足" not in answer_without_question and "证据不足" not in answer_without_question
        page.locator(".qa-citation-chip").first.click()
        page.locator(".qa-source-item.active").wait_for()
        source_card = page.locator(".qa-source-item").filter(has_text=str(upload["source_name"])).first
        source_card.wait_for()
        preview = source_card.locator("[data-source-preview]").first
        preview.wait_for()
        assert "Open source preview" in source_card.inner_text()
        preview_href = preview.get_attribute("href") or ""
        assert preview_href.startswith("/assets/")
        assert "kb_name=default" in preview_href
        assert "storage_key" not in preview_href
        assert "blob_key" not in preview_href
        asset_response = page.request.get(f"http://127.0.0.1:{port}{preview_href}")
        assert asset_response.status == 200
        assert asset_response.headers.get("content-type", "").startswith("image/png")
        assert asset_response.headers.get("x-document-asset-id")
        assert len(asset_response.body()) > 10_000


def _exercise_real_llm_qa_provider_flow(page, port: int, pdf_paths: dict[str, Path]) -> None:
    page.goto(f"http://127.0.0.1:{port}/admin/manual-library?kb_name=default")
    page.get_by_role("heading", name="Manual Library").wait_for()
    page.locator("#status-strip").get_by_text("Loaded 0 manuals from default.").wait_for()
    uploads = [
        {
            "path": pdf_paths["washer"],
            "manual_id": "asko-w6564-real-llm",
            "title": "ASKO W6564 Real LLM Washer Manual",
            "source_file": "real-llm/ASKO W6564.pdf",
            "tag": "real-llm-qa",
            "ready_source": "real-llm/ASKO W6564.pdf",
        },
        {
            "path": pdf_paths["oven"],
            "manual_id": "hisense-bsa5221-real-llm",
            "title": "HISENSE BSA5221 Real LLM Oven Manual",
            "source_file": "real-llm/HISENSE BSA5221.pdf",
            "tag": "real-llm-qa",
            "ready_source": "real-llm/HISENSE BSA5221.pdf",
        },
    ]
    for upload in uploads:
        _upload_manual_from_library_dialog(page, upload)

    page.goto(f"http://127.0.0.1:{port}/qa?kb_name=default")
    page.get_by_role("heading", name="Manual Q&A").wait_for()

    page.get_by_role("textbox", name="Q&A question").fill("How do I use Steam Clean on the HISENSE BSA5221 oven?")
    page.get_by_role("button", name="Ask question").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=60000)
    answer_text = page.locator("#qa-answer").inner_text()
    sources_text = page.locator("#qa-sources").inner_text()
    evidence_text = f"{answer_text}\n{sources_text}"
    evidence_text_casefold = evidence_text.casefold()
    assert "HISENSE BSA5221.pdf" in sources_text
    assert page.locator(".qa-citation-chip").count() >= 1
    assert page.locator(".qa-source-item").count() >= 1
    assert any(term in evidence_text_casefold for term in ["steam clean", "water", "damp cloth", "70"])
    assert "ASKO W6564" not in answer_text
    assert not any(leak in evidence_text for leak in ["storage_key", "blob_key", "checksum", "node_id", "anchor_key"])
    page.locator(".qa-citation-chip").first.click()
    page.locator(".qa-source-item.active").wait_for()

    page.get_by_role("textbox", name="Q&A question").fill("ASKO W6564 排水馬達故障時是不是要直接換泵？")
    page.get_by_role("button", name="Ask question").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=60000)
    unsupported_answer = page.locator("#qa-answer").inner_text()
    unsupported_sources = page.locator("#qa-sources").inner_text()
    combined = f"{unsupported_answer}\n{unsupported_sources}"
    assert "直接換泵" not in unsupported_answer
    assert "直接换泵" not in unsupported_answer
    assert "must replace" not in unsupported_answer.casefold()
    assert "should replace" not in unsupported_answer.casefold()
    assert "HISENSE BSA5221" not in unsupported_answer
    assert not any(leak in combined for leak in ["storage_key", "blob_key", "checksum", "node_id", "anchor_key"])


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


def _assert_qa_first_screen_guidance(page) -> None:
    assert "default" in page.locator("#qa-active-kb").inner_text()
    page.locator("#qa-kb-select").wait_for()
    assert page.locator("#qa-kb-select").input_value() == "default"
    assert "Switching knowledge bases" in page.locator("#qa-kb-note").inner_text() or "Only this knowledge base" in page.locator("#qa-kb-note").inner_text()
    flow_text = page.locator(".qa-flow-guide").inner_text()
    assert "Ask" in flow_text
    assert "Read" in flow_text
    assert "Verify" in flow_text
    assert "Describe the symptom, task, model, or error." in flow_text
    assert "Review the grounded answer and citation chips." in flow_text
    assert "Use Sources to inspect the manual passages." in flow_text
    empty_text = page.locator("#qa-answer").inner_text()
    generic_guidance_visible = (
        "Ask about a symptom, task, model, or error." in empty_text
        and "Answers will cite the manual passages used on the right." in empty_text
    )
    first_run_guidance_visible = (
        "Start by adding a manual" in empty_text
        and "This knowledge base does not have searchable manual content yet." in empty_text
        and "Choose a manual" in empty_text
        and "Check readiness" in empty_text
    )
    assert generic_guidance_visible or first_run_guidance_visible
    source_meta_text = page.locator("#qa-source-meta").inner_text()
    assert (
        "Cited source snippets will appear here." in source_meta_text
        or "Sources appear after indexing and Q&A." in source_meta_text
    )
    assert page.locator("#qa-submit").is_enabled()


def _assert_qa_loading_guidance_or_ready(page) -> None:
    try:
        page.locator("#qa-answer").get_by_text("Working on your answer").wait_for(timeout=350)
        answer_text = page.locator("#qa-answer").inner_text()
        sources_text = page.locator("#qa-sources").inner_text()
        assert "Match the question to the active knowledge base." in answer_text
        assert "Retrieve the most relevant manual passages." in answer_text
        assert "Draft an answer with citations you can inspect." in answer_text
        assert "Finding cited passages" in sources_text
        assert "Sources will appear here as soon as the answer is ready." in sources_text
        assert "Retrieving manual evidence..." in page.locator("#qa-source-meta").inner_text()
    except Exception:
        page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)


def _exercise_rag_failure_states(page, port: int, upload_path: Path) -> None:
    page.goto(f"http://127.0.0.1:{port}/qa?kb_name=default")
    page.get_by_role("heading", name="Manual Q&A").wait_for()
    _assert_qa_first_screen_guidance(page)
    page.locator("#qa-question").fill("服务模式怎么进入？")
    page.locator("#qa-submit").click()
    _assert_qa_loading_guidance_or_ready(page)
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
    answer_text = page.locator("#qa-answer").inner_text()
    assert "not ready" in answer_text
    assert "import manuals and rebuild" in answer_text
    assert "Could not complete this answer" in answer_text
    assert "Try asking again with the product model, symptom, or error code." in answer_text
    assert "Check RAG Readiness if this keeps failing." in answer_text
    readiness_href = page.locator("#qa-answer a").filter(has_text="Check readiness").first.get_attribute("href")
    assert readiness_href is not None
    assert readiness_href == "/admin/rag-readiness?kb_name=default"
    assert "No cited sources returned." in page.locator("#qa-sources").inner_text()
    assert "Try a more specific product, symptom, task, or error code." in page.locator("#qa-sources").inner_text()

    page.goto(f"http://127.0.0.1:{port}/admin/manual-library?kb_name=default")
    page.get_by_role("heading", name="Manual Library").wait_for()
    page.locator("#status-strip").get_by_text("Loaded 0 manuals from default.").wait_for()
    assert "No managed manuals found." in page.locator("#table-empty").inner_text()
    assert page.locator("#manual-first-run").is_visible()
    assert page.locator("#first-run-readiness").get_attribute("href") == "/admin/rag-readiness?kb_name=default"
    assert page.locator("#first-run-qa").get_attribute("href") == "/qa?kb_name=default"

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
    next_step_text = page.locator("#library-next-step").inner_text()
    assert "Manual uploaded, rebuild needed" in next_step_text
    assert "Run rebuild before this manual becomes searchable in Q&A." in next_step_text
    assert "Rebuild now" in next_step_text


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
    assert "证据不足" in answer_text or "insufficient" in answer_text.casefold()
    assert "无法确认" in answer_text or "insufficient" in answer_text.casefold()
    assert "配件编号是" not in answer_text
    assert "no results" not in answer_text.lower()
    assert "PN-" not in answer_text
    sources_text = page.locator("#qa-sources").inner_text()
    assert "limited-service-manual.md" in sources_text


def _exercise_qa_followup_context(page, port: int, upload_path: Path) -> None:
    qa_payloads = []
    page.on(
        "request",
        lambda request: qa_payloads.append(request.post_data_json)
        if request.url.endswith("/qa/answer") and request.method == "POST"
        else None,
    )

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
    assert "New question" in page.locator("#qa-context-mode").inner_text()
    page.locator("#qa-submit").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
    assert qa_payloads[-1]["conversation_context"] == []
    first_answer = page.locator("#qa-answer").inner_text()
    assert "清洗喷嘴" in first_answer
    assert "followup-service-manual.md" in page.locator("#qa-sources").inner_text()

    page.locator("#qa-question").fill("下一步呢？")
    context_mode = page.locator("#qa-context-mode")
    context_mode.get_by_text("Will continue from earlier").wait_for()
    assert "蒸汽很小怎么办？" in context_mode.inner_text()
    assert page.locator("#qa-submit-new").is_enabled()
    page.locator("#qa-submit").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
    assert qa_payloads[-1]["conversation_context"]
    assert qa_payloads[-1]["conversation_context"][0]["question"] == "蒸汽很小怎么办？"
    notice = page.locator("#qa-context-notice")
    notice.wait_for()
    notice_text = notice.inner_text()
    assert "Continuing from earlier" in notice_text
    assert "蒸汽很小怎么办？" in notice_text
    followup_answer = page.locator("#qa-answer").inner_text()
    assert "喷嘴" in followup_answer or "除垢" in followup_answer
    assert "followup-service-manual.md" in page.locator("#qa-sources").inner_text()

    page.locator("#qa-question").fill("下一步呢？")
    context_mode.get_by_text("Will continue from earlier").wait_for()
    page.locator("#qa-submit-new").click()
    page.locator("#qa-status").get_by_text("Answer ready.").wait_for(timeout=10000)
    assert qa_payloads[-1]["conversation_context"] == []
    assert page.locator("#qa-context-notice").count() == 0
    assert "New question" in page.locator("#qa-context-mode").inner_text()


def _write_browser_config(tmp_path: Path, *, answer_enabled: bool = False, ocr_enabled: bool = False, assets_enabled: bool = False) -> Path:
    config_path = tmp_path / "browser-ui-config.yaml"
    answer_block = "\nanswer:\n  enabled: true\n  provider: noop\n" if answer_enabled else ""
    ocr_block = (
        "\nocr:\n"
        "  enabled: true\n"
        "  provider: tesseract_cli\n"
        "  version: tesseract.local.v1\n"
        "  language: eng\n"
        "  dpi: 240\n"
        if ocr_enabled
        else ""
    )
    assets_block = (
        "\nassets:\n"
        "  enabled: true\n"
        "  pdf_page_snapshots_enabled: true\n"
        f"  root_dir: {tmp_path / 'assets'}\n"
        if assets_enabled
        else ""
    )
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
{ocr_block}
{assets_block}
""",
        encoding="utf-8",
    )
    return config_path


def _write_real_llm_browser_config(tmp_path: Path, *, api_key_env: str) -> Path:
    model_id = os.environ.get("TAGMEMORAG_REAL_LLM_ANSWER_MODEL", "deepseek-v4-flash")
    base_url = os.environ.get("TAGMEMORAG_REAL_LLM_ANSWER_BASE_URL", "https://api.deepseek.com")
    config_path = tmp_path / "browser-real-llm-config.yaml"
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
answer:
  enabled: true
  provider: openai_compatible
  model_id: {model_id}
  base_url: {base_url}
  api_key_env: {api_key_env}
  timeout_seconds: 45
  max_output_tokens: 768
  temperature: 0
""",
        encoding="utf-8",
    )
    return config_path


def _write_text_pdf(path: Path, text: str) -> None:
    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject({NameObject("/Font"): DictionaryObject({NameObject("/F1"): font})})
    escaped = text.replace("\\", "\\\\").replace("(", "\\(").replace(")", "\\)")
    stream = DecodedStreamObject()
    stream.set_data(f"BT /F1 16 Tf 72 720 Td ({escaped}) Tj ET".encode("utf-8"))
    page[NameObject("/Contents")] = stream
    with path.open("wb") as handle:
        writer.write(handle)


def _docx_bytes(*paragraphs: str) -> bytes:
    body = "".join(f"<w:p><w:r><w:t>{paragraph}</w:t></w:r></w:p>" for paragraph in paragraphs)
    xml = (
        '<?xml version="1.0" encoding="UTF-8" standalone="yes"?>'
        '<w:document xmlns:w="http://schemas.openxmlformats.org/wordprocessingml/2006/main">'
        f"<w:body>{body}</w:body></w:document>"
    )
    out = BytesIO()
    with zipfile.ZipFile(out, "w") as archive:
        archive.writestr("word/document.xml", xml)
    return out.getvalue()


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


def _eval_report_payload() -> dict:
    return {
        "suite": "browser-feedback.jsonl",
        "docs": None,
        "kb_names": ["default"],
        "top_k": 5,
        "thresholds": {"min_recall_at_k": 0.8, "min_mrr": 0.75, "min_hit_at_k": 0.8},
        "summary": {
            "cases": 2,
            "passed": False,
            "precision_at_k": 0.4,
            "recall_at_k": 0.5,
            "mrr": 0.5,
            "hit_at_k": 0.5,
        },
        "cases": [
            {
                "id": "passed-case",
                "query": "how to descale",
                "kb_name": "default",
                "top_k": 5,
                "passed": True,
                "metrics": {"precision_at_k": 0.2, "recall_at_k": 1.0, "mrr": 1.0, "hit_at_k": 1.0},
                "thresholds": {},
                "expected": [{"source_file": "coffee.md", "text_contains": ["descale"]}],
                "actual_top_k": [{"rank": 1, "source_file": "coffee.md", "matched_expected_indexes": [0]}],
                "failures": [],
            },
            {
                "id": "failed-case",
                "query": "steam is weak",
                "kb_name": "default",
                "top_k": 5,
                "passed": False,
                "metrics": {"precision_at_k": 0.0, "recall_at_k": 0.0, "mrr": 0.0, "hit_at_k": 0.0},
                "thresholds": {},
                "expected": [{"source_file": "coffee.md", "text_contains": ["steam"]}],
                "actual_top_k": [{"rank": 1, "source_file": "coffee.md", "matched_expected_indexes": []}],
                "failures": [],
            },
        ],
        "config_snapshot": {"reuse_built_kb": True},
    }


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
