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
    assert "搜索快速开始、OCR、部署、质量门禁" in html
    assert "Manual Library" in html
    assert "Ask Q&A" in html
    assert "RAG Readiness" in html
    assert "真实文档支持矩阵" in html
    assert "Production Release Checklist" in html
    assert "发布检查清单" in html
    assert "质量门禁" in html
    assert "后续规划" in html
    assert "Markdown / TXT" in html
    assert "扫描 PDF" in html
    assert "Legacy DOC" in html
    assert "备份恢复" in html
    assert "权限" in html
    assert "https://github.com/sxc19960907/TagMemoRAG/releases/tag/v0.1.0" in html
    assert "节点 ID" in html
    assert "sk-" not in html
    assert "storage_key" not in html
    assert "blob_key" not in html
    assert "@media (max-width: 1120px)" in css
    assert "@media (max-width: 820px)" in css
    assert ".docs-layout" in css
    assert ".docs-table" in css
    assert ".status-grid" in css
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
