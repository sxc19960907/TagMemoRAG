from __future__ import annotations

from dataclasses import dataclass
from html import unescape
from html.parser import HTMLParser
import json
from pathlib import Path
import re
from typing import Any
from urllib.parse import urljoin, urlparse
from urllib.request import Request, urlopen

from .manuals import normalize_identifier

DEFAULT_USER_AGENT = "TagMemoRAG/manualslib-import"


@dataclass(frozen=True)
class ManualslibPage:
    page_number: int
    title: str
    lines: tuple[str, ...]
    url: str


@dataclass(frozen=True)
class ManualslibManual:
    title: str
    brand: str
    product_model: str
    product_category: str
    language: str
    canonical_url: str
    pages_count: int
    pages: tuple[ManualslibPage, ...]


@dataclass(frozen=True)
class ManualslibImportResult:
    document_path: str
    metadata_path: str
    manual_id: str
    page_count: int
    line_count: int
    source_url: str

    def to_dict(self) -> dict[str, Any]:
        return {
            "document_path": self.document_path,
            "metadata_path": self.metadata_path,
            "manual_id": self.manual_id,
            "page_count": self.page_count,
            "line_count": self.line_count,
            "source_url": self.source_url,
        }


def import_manualslib_url(
    url: str,
    *,
    output_dir: str | Path,
    max_pages: int | None = None,
    timeout_seconds: float = 20.0,
    user_agent: str = DEFAULT_USER_AGENT,
) -> ManualslibImportResult:
    first_html = _fetch_url(url, timeout_seconds=timeout_seconds, user_agent=user_agent)
    first = parse_manualslib_page(first_html, url=url)
    pages = [first.pages[0]]
    total_pages = first.pages_count
    limit = total_pages if max_pages is None or max_pages <= 0 else min(total_pages, int(max_pages))
    for page_number in range(2, limit + 1):
        page_url = _page_url(first.canonical_url or url, page_number)
        html = _fetch_url(page_url, timeout_seconds=timeout_seconds, user_agent=user_agent)
        pages.append(parse_manualslib_page(html, url=page_url).pages[0])
    manual = ManualslibManual(
        title=first.title,
        brand=first.brand,
        product_model=first.product_model,
        product_category=first.product_category,
        language=first.language,
        canonical_url=first.canonical_url,
        pages_count=total_pages,
        pages=tuple(pages),
    )
    return materialize_manualslib_manual(manual, output_dir=output_dir)


def parse_manualslib_page(html: str, *, url: str) -> ManualslibManual:
    parser = _ManualslibHTMLParser()
    parser.feed(html)
    parser.close()
    metadata = _metadata_from_json_ld(parser.json_ld)
    canonical_url = parser.canonical_url or metadata.get("url") or url
    title = _clean_title(parser.h1 or metadata.get("headline") or metadata.get("name") or "ManualsLib manual")
    product_category = _category_from_breadcrumb(metadata.get("breadcrumb_names")) or _category_from_article_section(metadata.get("articleSection"))
    page_number = _page_number_from_url(url)
    page_title = parser.page_titles.get(page_number) or f"Page {page_number}"
    page_lines = tuple(_dedupe_preserve_order(parser.pdf_lines))
    page = ManualslibPage(page_number=page_number, title=page_title, lines=page_lines, url=url)
    return ManualslibManual(
        title=title,
        brand=_brand_from_title(title),
        product_model=_model_from_title(title),
        product_category=product_category or "unknown",
        language=parser.current_lang or "unknown",
        canonical_url=canonical_url,
        pages_count=parser.manual_pages_count or 1,
        pages=(page,),
    )


def materialize_manualslib_manual(manual: ManualslibManual, *, output_dir: str | Path) -> ManualslibImportResult:
    output_root = Path(output_dir)
    category = normalize_identifier(manual.product_category or "manual")
    manual_id = normalize_identifier(f"manualslib-{manual.brand}-{manual.product_model or manual.title}")
    target_dir = output_root / category
    target_dir.mkdir(parents=True, exist_ok=True)
    document_path = target_dir / f"{manual_id}.md"
    metadata_path = target_dir / f"{manual_id}.metadata.json"
    document = _manual_to_markdown(manual)
    document_path.write_text(document, encoding="utf-8")
    metadata = {
        "manual_id": manual_id,
        "title": manual.title,
        "source_file": f"{category}/{document_path.name}",
        "product_category": manual.product_category or category,
        "language": manual.language,
        "brand": manual.brand,
        "product_name": manual.product_model or manual.title,
        "product_model": manual.product_model,
        "version": "manualslib",
        "tags": [manual.product_category, "manualslib", f"brand:{manual.brand.lower()}"],
        "status": "active",
        "notes": f"Imported from ManualsLib: {manual.canonical_url}",
    }
    metadata_path.write_text(json.dumps(metadata, ensure_ascii=False, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return ManualslibImportResult(
        document_path=str(document_path),
        metadata_path=str(metadata_path),
        manual_id=manual_id,
        page_count=len(manual.pages),
        line_count=sum(len(page.lines) for page in manual.pages),
        source_url=manual.canonical_url,
    )


def _manual_to_markdown(manual: ManualslibManual) -> str:
    lines = [f"# {manual.title}", "", f"Source: {manual.canonical_url}", ""]
    for page in manual.pages:
        heading = page.title if page.title.lower().startswith("page ") else f"Page {page.page_number}: {page.title}"
        lines.extend([f"## {heading}", ""])
        if page.lines:
            lines.extend(page.lines)
        else:
            lines.append("(No extractable text on this page.)")
        lines.append("")
    return "\n".join(lines).strip() + "\n"


def _fetch_url(url: str, *, timeout_seconds: float, user_agent: str) -> str:
    request = Request(url, headers={"User-Agent": user_agent})
    with urlopen(request, timeout=timeout_seconds) as response:  # noqa: S310 - operator-supplied URL import tool.
        charset = response.headers.get_content_charset() or "utf-8"
        return response.read().decode(charset, errors="replace")


def _page_url(base_url: str, page_number: int) -> str:
    parsed = urlparse(base_url)
    path = parsed.path
    query = f"page={page_number}"
    return parsed._replace(query=query, fragment="manual").geturl()


def _page_number_from_url(url: str) -> int:
    match = re.search(r"(?:[?&]page=)(\d+)", url)
    return int(match.group(1)) if match else 1


def _page_number_from_page_id(value: str) -> int:
    match = re.match(r"page(\d+)$", value)
    return int(match.group(1)) if match else 0


def _clean_title(value: str) -> str:
    title = re.sub(r"\s+", " ", unescape(value)).strip()
    title = re.sub(r"\s+Pdf\s+Download\s*$", "", title, flags=re.IGNORECASE)
    return title


def _brand_from_title(title: str) -> str:
    first = title.split(None, 1)[0] if title.split() else ""
    return first.title() if first else ""


def _model_from_title(title: str) -> str:
    cleaned = re.sub(r"^(hisense)\s+", "", title, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+(user|owner|operation|service).*$", "", cleaned, flags=re.IGNORECASE)
    cleaned = re.sub(r"\s+", " ", cleaned).strip()
    return cleaned


def _category_from_article_section(value: Any) -> str:
    text = str(value or "").strip()
    if not text:
        return ""
    parts = text.split()
    return parts[-1].lower() if parts else ""


def _category_from_breadcrumb(names: Any) -> str:
    if not isinstance(names, list):
        return ""
    for name in names:
        text = str(name).strip()
        if text and text.lower() not in {"manuals", "brands", "hisense manuals"} and not re.search(r"manual$", text, re.IGNORECASE):
            if text.lower() not in {"dh105m3 series"}:
                return text.lower()
    return ""


def _metadata_from_json_ld(items: list[dict[str, Any]]) -> dict[str, Any]:
    out: dict[str, Any] = {}
    for item in items:
        item_type = item.get("@type")
        if item_type == "TechArticle":
            out.update({key: item.get(key) for key in ("url", "headline", "articleSection") if item.get(key)})
        elif item_type == "WebPage":
            out.update({key: item.get(key) for key in ("url", "name") if item.get(key)})
        elif item_type == "BreadcrumbList":
            names = []
            for element in item.get("itemListElement") or []:
                if isinstance(element, dict) and element.get("name"):
                    names.append(str(element["name"]))
            out["breadcrumb_names"] = names
    return out


def _dedupe_preserve_order(lines: list[str]) -> list[str]:
    seen: set[str] = set()
    out: list[str] = []
    for line in lines:
        cleaned = re.sub(r"\s+", " ", line).strip()
        if not cleaned or cleaned in seen:
            continue
        seen.add(cleaned)
        out.append(cleaned)
    return out


class _ManualslibHTMLParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.h1 = ""
        self.current_lang = ""
        self.canonical_url = ""
        self.manual_pages_count = 0
        self.current_page_title = ""
        self.page_titles: dict[int, str] = {}
        self.pdf_lines: list[str] = []
        self.json_ld: list[dict[str, Any]] = []
        self._tag_stack: list[str] = []
        self._capture_h1 = False
        self._capture_pdf = 0
        self._capture_json_ld = False
        self._json_ld_parts: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attrs_dict = {key: value or "" for key, value in attrs}
        self._tag_stack.append(tag)
        if tag == "html":
            self.current_lang = attrs_dict.get("lang") or self.current_lang
        elif tag == "link" and attrs_dict.get("rel") == "canonical":
            self.canonical_url = attrs_dict.get("href", "")
        elif tag == "h1":
            self._capture_h1 = True
        elif tag == "script" and attrs_dict.get("type") == "application/ld+json":
            self._capture_json_ld = True
            self._json_ld_parts = []
        elif tag == "a" and attrs_dict.get("id", "").startswith("page"):
            title = attrs_dict.get("title", "").strip()
            if title:
                page_number = _page_number_from_page_id(attrs_dict.get("id", ""))
                if page_number:
                    self.page_titles[page_number] = title
        elif tag == "div":
            classes = set(attrs_dict.get("class", "").split())
            if self._capture_pdf:
                self._capture_pdf += 1
            elif "pdf" in classes or any(name.startswith("pdf-") for name in classes):
                self._capture_pdf += 1

    def handle_endtag(self, tag: str) -> None:
        if tag == "h1":
            self._capture_h1 = False
        elif tag == "script" and self._capture_json_ld:
            self._capture_json_ld = False
            raw = "".join(self._json_ld_parts).strip()
            if raw:
                try:
                    data = json.loads(raw)
                except json.JSONDecodeError:
                    data = None
                if isinstance(data, dict):
                    self.json_ld.append(data)
        elif tag == "div" and self._capture_pdf:
            self._capture_pdf -= 1
        if self._tag_stack:
            self._tag_stack.pop()

    def handle_data(self, data: str) -> None:
        text = data.strip()
        if not text:
            return
        if self._capture_json_ld:
            self._json_ld_parts.append(data)
            return
        if self._capture_h1 and not self.h1:
            self.h1 = text
        if "manual_pages_count" in text:
            match = re.search(r"manual_pages_count[\"']?\s*[:=]\s*(\d+)", text)
            if match:
                self.manual_pages_count = int(match.group(1))
        if self._capture_pdf:
            self.pdf_lines.append(text)
