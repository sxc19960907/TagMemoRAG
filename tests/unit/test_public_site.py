from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_public_site_contains_install_free_project_guide():
    html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")

    assert "TagMemoRAG 文档 | 面向真实文档的浏览器优先 RAG" in html
    assert "不需要运行 TagMemoRAG" in html
    assert "docs-sidebar" in html
    assert "本页目录" in html
    assert "搜索文档、功能、流程" in html
    assert "Manual Library" in html
    assert "用户问答" in html
    assert "RAG Readiness" in html
    assert "OCR 的作用" in html
    assert "人员与权限" in html
    assert "https://github.com/sxc19960907/TagMemoRAG/releases/tag/v0.1.0" in html
    assert "节点 ID" in html
    assert "sk-" not in html
    assert "storage_key" not in html
    assert "blob_key" not in html
    assert "@media (max-width: 1120px)" in css
    assert ".docs-layout" in css
    assert ".toc" in css


def test_github_pages_workflow_publishes_static_site():
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")

    assert "Publish Public Site" in workflow
    assert "contents: write" in workflow
    assert "actions/checkout@v6" in workflow
    assert "cp -R site/." in workflow
    assert "checkout --orphan gh-pages" in workflow
    assert "push --force origin gh-pages" in workflow
    assert "actions-gh-pages" not in workflow
