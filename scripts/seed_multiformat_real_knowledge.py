#!/usr/bin/env python3
"""Materialize an opt-in real multi-format knowledge corpus.

Fetched third-party content is written under `.tmp` by default and should not be
committed. The materialized corpus reuses the normal build/eval pipeline.
"""

from __future__ import annotations

import argparse
from dataclasses import dataclass
import io
import json
from pathlib import Path
import re
import shutil
import sys
from typing import Callable
from urllib.request import Request, urlopen
import zipfile
from xml.etree import ElementTree

REPO_ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(REPO_ROOT / "src"))

from tagmemorag.public_web_import import import_public_web  # noqa: E402


FetchBytes = Callable[[str, float], bytes]

DEFAULT_OUTPUT_DIR = ".tmp/multiformat-real-knowledge"
DEFAULT_KB = "multiformat_real"
DEFAULT_TIMEOUT_SECONDS = 30.0

HTML_SOURCES = (
    {
        "url": "https://developer.mozilla.org/en-US/docs/Web/HTTP/Guides/Caching",
        "domain": "web_platform_docs",
        "doc_type": "documentation",
        "tags": ("web-platform", "http", "caching"),
    },
)

FILE_SOURCES = (
    {
        "url": "https://www.irs.gov/pub/irs-pdf/p17.pdf",
        "source_file": "public_pdf/irs-publication-17.pdf",
        "manual_id": "irs-publication-17",
        "title": "IRS Publication 17",
        "domain": "public_service",
        "doc_type": "pdf_publication",
        "source_format": "pdf",
        "tags": ("public-service", "tax", "pdf"),
    },
    {
        "url": "https://www.epa.gov/sites/default/files/2021-04/format_for_memo_requesting_a_waiver_to_host_content_outside_of_epa_web_environment.docx",
        "source_file": "public_docx/epa-web-hosting-waiver-memo.md",
        "manual_id": "epa-web-hosting-waiver-memo",
        "title": "EPA Web Hosting Waiver Memo Template",
        "domain": "public_service",
        "doc_type": "docx_template",
        "source_format": "docx",
        "tags": ("public-service", "epa", "docx"),
    },
)


@dataclass(frozen=True)
class MaterializedFile:
    url: str
    source_file: str
    source_format: str

    def to_dict(self) -> dict[str, str]:
        return {
            "url": self.url,
            "source_file": self.source_file,
            "source_format": self.source_format,
        }


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--output-dir", default=DEFAULT_OUTPUT_DIR)
    parser.add_argument("--kb", default=DEFAULT_KB)
    parser.add_argument("--timeout-seconds", type=float, default=DEFAULT_TIMEOUT_SECONDS)
    args = parser.parse_args(argv)

    report = materialize_multiformat_corpus(
        output_dir=args.output_dir,
        kb_name=args.kb,
        timeout_seconds=args.timeout_seconds,
    )
    print(json.dumps(report, ensure_ascii=False, indent=2, sort_keys=True))
    summary = report["summary"]
    return 0 if summary["failed"] == 0 else 1


def materialize_multiformat_corpus(
    *,
    output_dir: str | Path = DEFAULT_OUTPUT_DIR,
    kb_name: str = DEFAULT_KB,
    timeout_seconds: float = DEFAULT_TIMEOUT_SECONDS,
    fetch_bytes: FetchBytes | None = None,
) -> dict:
    output_root = Path(output_dir)
    if output_root.exists():
        shutil.rmtree(output_root)
    output_root.mkdir(parents=True, exist_ok=True)
    fetch = fetch_bytes or _fetch_url

    html_reports = []
    for group in HTML_SOURCES:
        report = import_public_web(
            (str(group["url"]),),
            output_dir=output_root,
            kb_name=kb_name,
            domain=str(group["domain"]),
            doc_type=str(group["doc_type"]),
            tags=tuple(str(tag) for tag in group["tags"]),
            timeout_seconds=timeout_seconds,
            fetch_bytes=fetch,
        )
        html_reports.append(report.to_dict())
        _add_source_format_to_sidecar(
            output_root / kb_name / "public_web" / f"{_safe_id(str(group['url']))}.metadata.json",
            source_format="html",
        )

    materialized: list[MaterializedFile] = []
    failures: list[dict[str, str]] = []
    for source in FILE_SOURCES:
        try:
            materialized.append(
                _materialize_file_source(
                    source,
                    root=output_root / kb_name,
                    fetch_bytes=fetch,
                    timeout_seconds=timeout_seconds,
                )
            )
        except Exception as exc:  # noqa: BLE001 - report all materialization failures.
            failures.append({"url": str(source["url"]), "reason": _bounded_reason(type(exc).__name__)})

    html_failed = sum(int((report.get("summary") or {}).get("failed") or 0) for report in html_reports)
    return {
        "schema_version": "multiformat_real_knowledge_seed.v1",
        "kb_name": kb_name,
        "output_dir": str(output_root),
        "html": html_reports,
        "files": [item.to_dict() for item in materialized],
        "failures": failures,
        "summary": {
            "html_groups": len(html_reports),
            "file_sources": len(FILE_SOURCES),
            "materialized_files": len(materialized),
            "failed": html_failed + len(failures),
        },
    }


def _materialize_file_source(
    source: dict[str, object],
    *,
    root: Path,
    fetch_bytes: FetchBytes,
    timeout_seconds: float,
) -> MaterializedFile:
    url = str(source["url"])
    source_file = str(source["source_file"])
    source_format = str(source["source_format"])
    raw = fetch_bytes(url, timeout_seconds)
    target = root / source_file
    target.parent.mkdir(parents=True, exist_ok=True)
    if source_format == "pdf":
        content = raw
    elif source_format == "docx":
        content = _docx_to_markdown(raw, title=str(source["title"]), url=url).encode("utf-8")
    else:
        raise ValueError("unsupported_source_format")
    target.write_bytes(content)
    _write_metadata(target, source)
    return MaterializedFile(url=url, source_file=source_file, source_format=source_format)


def _write_metadata(target: Path, source: dict[str, object]) -> None:
    metadata = {
        "manual_id": str(source["manual_id"]),
        "title": str(source["title"]),
        "source_file": str(source["source_file"]),
        "product_category": str(source["domain"]),
        "domain": str(source["domain"]),
        "doc_type": str(source["doc_type"]),
        "remote_id": str(source["url"]),
        "url": str(source["url"]),
        "source_format": str(source["source_format"]),
        "tags": [str(tag) for tag in source["tags"]],
    }
    sidecar = target.with_name(f"{target.stem}.metadata.json")
    sidecar.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _add_source_format_to_sidecar(sidecar: Path, *, source_format: str) -> None:
    if not sidecar.exists():
        return
    data = json.loads(sidecar.read_text(encoding="utf-8"))
    data["source_format"] = source_format
    sidecar.write_text(json.dumps(data, ensure_ascii=False, indent=2, sort_keys=True), encoding="utf-8")


def _docx_to_markdown(raw: bytes, *, title: str, url: str) -> str:
    paragraphs = _docx_paragraphs(raw)
    lines = [f"# {title}", "", f"Source: {url}", ""]
    lines.extend(paragraphs or ("No readable text extracted.",))
    return "\n\n".join(line for line in lines if line != "").strip() + "\n"


def _docx_paragraphs(raw: bytes) -> tuple[str, ...]:
    with zipfile.ZipFile(io.BytesIO(raw)) as archive:
        document = archive.read("word/document.xml")
    root = ElementTree.fromstring(document)
    namespace = "{http://schemas.openxmlformats.org/wordprocessingml/2006/main}"
    paragraphs: list[str] = []
    for paragraph in root.iter(f"{namespace}p"):
        parts = [node.text or "" for node in paragraph.iter(f"{namespace}t")]
        text = _normalize_space("".join(parts))
        if text:
            paragraphs.append(text)
    return tuple(paragraphs)


def _fetch_url(url: str, timeout_seconds: float) -> bytes:
    request = Request(url, headers={"User-Agent": "TagMemoRAG/0.1 multiformat-sampler"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def _safe_id(value: str) -> str:
    from urllib.parse import urlparse

    parsed = urlparse(value)
    raw = "-".join(part for part in (parsed.netloc, parsed.path.strip("/")) if part) or value
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", raw.lower()).strip("-._")
    return normalized[:96] or "web-page"


def _bounded_reason(reason: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(reason).strip().lower())[:80].strip("_")
    return normalized or "unknown"


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


if __name__ == "__main__":
    raise SystemExit(main())
