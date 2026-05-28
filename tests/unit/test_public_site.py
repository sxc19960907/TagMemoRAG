from __future__ import annotations

from pathlib import Path


ROOT = Path(__file__).resolve().parents[2]


def test_public_site_contains_install_free_project_guide():
    html = (ROOT / "site" / "index.html").read_text(encoding="utf-8")
    css = (ROOT / "site" / "styles.css").read_text(encoding="utf-8")

    assert "TagMemoRAG | Browser-first RAG for real documents" in html
    assert "without running TagMemoRAG" in html
    assert "Manual Library" in html
    assert "User Q&A" in html
    assert "Readiness Guide" in html
    assert "Optional OCR" in html
    assert "Access Management" in html
    assert "https://github.com/sxc19960907/TagMemoRAG/releases/tag/v0.1.0" in html
    assert "storage keys, checksums, or local paths" in html
    assert "sk-" not in html
    assert "storage_key" not in html
    assert "blob_key" not in html
    assert "@media (max-width: 920px)" in css
    assert "grid-template-columns" in css


def test_github_pages_workflow_publishes_static_site():
    workflow = (ROOT / ".github" / "workflows" / "pages.yml").read_text(encoding="utf-8")

    assert "Publish Public Site" in workflow
    assert "contents: write" in workflow
    assert "peaceiris/actions-gh-pages" in workflow
    assert "publish_dir: ./site" in workflow
    assert "publish_branch: gh-pages" in workflow
