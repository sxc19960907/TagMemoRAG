from __future__ import annotations

from dataclasses import dataclass
import json
import subprocess
from pathlib import Path
from typing import Any, Callable

from .manualslib_import import ManualslibImportResult, import_manualslib_url


@dataclass(frozen=True)
class ManualslibOpenCLIRow:
    rank: int | None
    brand: str
    category: str
    model: str
    document_type: str
    pages: str
    description: str
    url: str

    @classmethod
    def from_dict(cls, row: dict[str, Any]) -> ManualslibOpenCLIRow:
        return cls(
            rank=_optional_int(row.get("rank")),
            brand=str(row.get("brand") or ""),
            category=str(row.get("category") or ""),
            model=str(row.get("model") or ""),
            document_type=str(row.get("document_type") or ""),
            pages=str(row.get("pages") or ""),
            description=str(row.get("description") or ""),
            url=str(row.get("url") or "").strip(),
        )

    def to_dict(self) -> dict[str, Any]:
        return {
            "rank": self.rank,
            "brand": self.brand,
            "category": self.category,
            "model": self.model,
            "document_type": self.document_type,
            "pages": self.pages,
            "description": self.description,
            "url": self.url,
        }


@dataclass(frozen=True)
class ManualslibOpenCLIReport:
    schema_version: str
    status: str
    command: list[str]
    discovered: list[ManualslibOpenCLIRow]
    imported: list[dict[str, Any]]
    skipped: list[dict[str, Any]]
    failed: list[dict[str, Any]]
    preview: bool

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": self.schema_version,
            "status": self.status,
            "command": self.command,
            "preview": self.preview,
            "counts": {
                "discovered": len(self.discovered),
                "imported": len(self.imported),
                "skipped": len(self.skipped),
                "failed": len(self.failed),
            },
            "discovered": [row.to_dict() for row in self.discovered],
            "imported": self.imported,
            "skipped": self.skipped,
            "failed": self.failed,
        }


class ManualslibOpenCLIError(RuntimeError):
    def __init__(self, message: str, *, command: list[str], stderr: str = "", stdout: str = ""):
        super().__init__(message)
        self.command = command
        self.stderr = stderr
        self.stdout = stdout

    def to_dict(self) -> dict[str, Any]:
        return {
            "schema_version": "manualslib_opencli_import.v1",
            "status": "failed",
            "error": {
                "message": str(self),
                "command": self.command,
                "stderr": self.stderr,
                "stdout": self.stdout,
            },
        }


Importer = Callable[..., ManualslibImportResult]


def import_from_opencli(
    *,
    brand: str = "hisense",
    category: str | None = None,
    limit: int = 20,
    output_dir: str | Path | None = None,
    preview: bool = False,
    max_pages: int | None = None,
    timeout_seconds: float = 20.0,
    importer: Importer = import_manualslib_url,
) -> ManualslibOpenCLIReport:
    if not preview and output_dir is None:
        raise ValueError("output_dir is required unless preview=True")
    command = _opencli_command(brand=brand, category=category, limit=limit)
    rows = _load_opencli_rows(command)
    imported: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []
    failed: list[dict[str, Any]] = []
    seen_urls: set[str] = set()

    if not preview:
        for row in rows:
            if not row.url:
                failed.append({"row": row.to_dict(), "error": "missing url"})
                continue
            if row.url in seen_urls:
                skipped.append({"reason": "duplicate_url", "row": row.to_dict()})
                continue
            seen_urls.add(row.url)
            try:
                result = importer(
                    row.url,
                    output_dir=output_dir,
                    max_pages=max_pages,
                    timeout_seconds=timeout_seconds,
                )
            except Exception as exc:  # noqa: BLE001 - batch report keeps importing remaining rows.
                failed.append({"row": row.to_dict(), "error": f"{type(exc).__name__}: {exc}"})
                continue
            imported.append({"row": row.to_dict(), "result": result.to_dict()})

    status = "preview" if preview else "completed"
    if failed and imported:
        status = "partial_failed"
    elif failed:
        status = "failed"
    return ManualslibOpenCLIReport(
        schema_version="manualslib_opencli_import.v1",
        status=status,
        command=command,
        discovered=rows,
        imported=imported,
        skipped=skipped,
        failed=failed,
        preview=preview,
    )


def _opencli_command(*, brand: str, category: str | None, limit: int) -> list[str]:
    command = ["opencli", "manualslib", "list", "--brand", brand, "--limit", str(max(1, int(limit))), "-f", "json"]
    if category:
        command.extend(["--category", category])
    return command


def _load_opencli_rows(command: list[str]) -> list[ManualslibOpenCLIRow]:
    try:
        result = subprocess.run(command, check=False, text=True, capture_output=True)
    except FileNotFoundError as exc:
        raise ManualslibOpenCLIError("opencli executable not found", command=command) from exc
    if result.returncode != 0:
        raise ManualslibOpenCLIError(
            f"opencli returned exit code {result.returncode}",
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    try:
        body = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise ManualslibOpenCLIError(
            "opencli returned invalid JSON",
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
        ) from exc
    if not isinstance(body, list):
        raise ManualslibOpenCLIError(
            "opencli JSON output must be a list",
            command=command,
            stdout=result.stdout,
            stderr=result.stderr,
        )
    return [ManualslibOpenCLIRow.from_dict(row) for row in body if isinstance(row, dict)]


def _optional_int(value: Any) -> int | None:
    if value is None or value == "":
        return None
    try:
        return int(value)
    except (TypeError, ValueError):
        return None
