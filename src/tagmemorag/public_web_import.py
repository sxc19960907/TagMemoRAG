from __future__ import annotations

from dataclasses import dataclass, field
from html.parser import HTMLParser
from pathlib import Path
import re
from typing import Callable
from urllib.parse import urlparse
from urllib.request import Request, urlopen

from .connectors.base import ConnectorDocument, ConnectorRecord
from .connectors.materialize import materialize_connector_records


FetchBytes = Callable[[str, float], bytes]


@dataclass(frozen=True)
class PublicWebDocument:
    url: str
    title: str
    markdown: str
    source_file: str
    domain: str
    doc_type: str
    tags: tuple[str, ...] = ()

    def to_record(self) -> ConnectorRecord:
        record_id = _safe_id(self.url)
        return ConnectorRecord(
            record_id=record_id,
            manual_id=record_id,
            title=self.title,
            product_category=self.domain,
            document=ConnectorDocument(
                source_file=self.source_file,
                content=self.markdown.encode("utf-8"),
                content_type="text/markdown",
            ),
            tags=self.tags,
            remote_id=self.url,
            metadata={"domain": self.domain, "doc_type": self.doc_type, "url": self.url},
        )

    def to_dict(self, *, include_text: bool = False) -> dict[str, object]:
        data: dict[str, object] = {
            "url": self.url,
            "title": self.title,
            "source_file": self.source_file,
            "domain": self.domain,
            "doc_type": self.doc_type,
            "tags": list(self.tags),
            "text_chars": len(self.markdown),
        }
        if include_text:
            data["markdown"] = self.markdown
        return data


@dataclass(frozen=True)
class PublicWebFailure:
    url: str
    reason: str

    def to_dict(self) -> dict[str, str]:
        return {"url": self.url, "reason": self.reason}


@dataclass(frozen=True)
class PublicWebImportReport:
    status: str
    preview: bool
    kb_name: str
    output_dir: str | None
    documents: tuple[PublicWebDocument, ...] = ()
    failures: tuple[PublicWebFailure, ...] = ()
    materialized: int = 0
    materialize_failed: int = 0
    failure_reasons: dict[str, int] = field(default_factory=dict)

    def to_dict(self) -> dict[str, object]:
        return {
            "schema_version": "public_web_import.v1",
            "status": self.status,
            "preview": self.preview,
            "kb_name": self.kb_name,
            "output_dir": self.output_dir,
            "documents": [document.to_dict() for document in self.documents],
            "failures": [failure.to_dict() for failure in self.failures],
            "summary": {
                "attempted": len(self.documents) + len(self.failures),
                "parsed": len(self.documents),
                "failed": len(self.failures) + self.materialize_failed,
                "materialized": self.materialized,
                "failure_reasons": dict(sorted(self.failure_reasons.items())),
            },
        }


def import_public_web(
    urls: tuple[str, ...],
    *,
    output_dir: str | Path | None,
    kb_name: str = "default",
    domain: str = "public_web",
    doc_type: str = "web_page",
    tags: tuple[str, ...] = (),
    preview: bool = False,
    timeout_seconds: float = 20.0,
    fetch_bytes: FetchBytes | None = None,
) -> PublicWebImportReport:
    if not urls:
        raise ValueError("at least one --url is required")
    if not preview and not output_dir:
        raise ValueError("--output-dir is required unless --preview is set")
    fetch = fetch_bytes or _fetch_url
    documents: list[PublicWebDocument] = []
    failures: list[PublicWebFailure] = []
    failure_reasons: dict[str, int] = {}

    for url in urls:
        try:
            documents.append(
                fetch_public_web_document(
                    url,
                    domain=domain,
                    doc_type=doc_type,
                    tags=tags,
                    timeout_seconds=timeout_seconds,
                    fetch_bytes=fetch,
                )
            )
        except Exception as exc:  # noqa: BLE001
            reason = _bounded_reason(type(exc).__name__)
            failures.append(PublicWebFailure(url=url, reason=reason))
            failure_reasons[reason] = failure_reasons.get(reason, 0) + 1

    materialized = 0
    materialize_failed = 0
    if not preview and documents:
        summary = materialize_connector_records(
            tuple(document.to_record() for document in documents),
            kb_name=kb_name,
            root_dir=output_dir or "",
            provider="public_web",
        )
        materialized = summary.materialized
        materialize_failed = summary.failed
        for reason, count in summary.failure_reasons.items():
            failure_reasons[reason] = failure_reasons.get(reason, 0) + count

    status = "completed"
    if preview:
        status = "preview"
    elif failures or materialized < len(documents):
        status = "partial" if documents else "failed"
    return PublicWebImportReport(
        status=status,
        preview=preview,
        kb_name=kb_name,
        output_dir=str(output_dir) if output_dir is not None else None,
        documents=tuple(documents),
        failures=tuple(failures),
        materialized=materialized,
        materialize_failed=materialize_failed,
        failure_reasons=failure_reasons,
    )


def fetch_public_web_document(
    url: str,
    *,
    domain: str,
    doc_type: str,
    tags: tuple[str, ...] = (),
    timeout_seconds: float = 20.0,
    fetch_bytes: FetchBytes | None = None,
) -> PublicWebDocument:
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.netloc:
        raise ValueError("unsupported_url")
    raw = (fetch_bytes or _fetch_url)(url, timeout_seconds)
    text = raw.decode("utf-8", errors="replace")
    title, blocks = html_to_text_blocks(text)
    page_title = title or parsed.netloc
    markdown = _to_markdown(page_title, url, blocks)
    return PublicWebDocument(
        url=url,
        title=page_title,
        markdown=markdown,
        source_file=f"public_web/{_safe_id(url)}.md",
        domain=domain,
        doc_type=doc_type,
        tags=tags,
    )


def html_to_text_blocks(html: str) -> tuple[str, tuple[str, ...]]:
    parser = _ReadableHTMLParser()
    parser.feed(html)
    parser.close()
    return parser.title.strip(), tuple(block for block in parser.blocks if block)


def _fetch_url(url: str, timeout_seconds: float) -> bytes:
    request = Request(url, headers={"User-Agent": "TagMemoRAG/0.1 public-web-sampler"})
    with urlopen(request, timeout=timeout_seconds) as response:
        return response.read()


def _to_markdown(title: str, url: str, blocks: tuple[str, ...]) -> str:
    lines = [f"# {title}", "", f"Source: {url}", ""]
    lines.extend(blocks or ("No readable text extracted.",))
    return "\n\n".join(line for line in lines if line != "").strip() + "\n"


def _safe_id(value: str) -> str:
    parsed = urlparse(value)
    raw = "-".join(part for part in (parsed.netloc, parsed.path.strip("/")) if part) or value
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "-", raw.lower()).strip("-._")
    return normalized[:96] or "web-page"


def _bounded_reason(reason: str) -> str:
    normalized = re.sub(r"[^A-Za-z0-9._-]+", "_", str(reason).strip().lower())[:80].strip("_")
    return normalized or "unknown"


class _ReadableHTMLParser(HTMLParser):
    _block_tags = {"p", "li", "h1", "h2", "h3", "h4", "h5", "h6", "dt", "dd", "td", "th", "figcaption"}
    _skip_tags = {"script", "style", "noscript", "svg", "canvas"}

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.title = ""
        self.blocks: list[str] = []
        self._current: list[str] = []
        self._in_title = False
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs) -> None:
        tag = tag.lower()
        if tag in self._skip_tags:
            self._skip_depth += 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = True
        if tag == "br":
            self._current.append(" ")

    def handle_endtag(self, tag: str) -> None:
        tag = tag.lower()
        if tag in self._skip_tags and self._skip_depth:
            self._skip_depth -= 1
            return
        if self._skip_depth:
            return
        if tag == "title":
            self._in_title = False
            return
        if tag in self._block_tags:
            self._flush_current()

    def handle_data(self, data: str) -> None:
        if self._skip_depth:
            return
        text = _normalize_space(data)
        if not text:
            return
        if self._in_title:
            self.title = _normalize_space(f"{self.title} {text}")
        else:
            self._current.append(text)

    def close(self) -> None:
        self._flush_current()
        super().close()

    def _flush_current(self) -> None:
        block = _normalize_space(" ".join(self._current))
        self._current.clear()
        if block and (not self.blocks or self.blocks[-1] != block):
            self.blocks.append(block)


def _normalize_space(value: str) -> str:
    return re.sub(r"\s+", " ", value).strip()


__all__ = [
    "PublicWebDocument",
    "PublicWebFailure",
    "PublicWebImportReport",
    "fetch_public_web_document",
    "html_to_text_blocks",
    "import_public_web",
]
