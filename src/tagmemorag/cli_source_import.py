from __future__ import annotations

import json
import sys

from .manualslib_import import import_manualslib_url
from .manualslib_opencli_import import ManualslibOpenCLIError, import_from_opencli
from .public_web_import import import_public_web


def run_manualslib_command(args) -> int:
    if args.manualslib_command == "import-opencli":
        try:
            report = import_from_opencli(
                brand=args.brand,
                category=args.category,
                limit=args.limit,
                output_dir=args.output_dir,
                preview=args.preview,
                max_pages=args.max_pages,
                timeout_seconds=args.timeout_seconds,
            )
        except (ManualslibOpenCLIError, ValueError) as exc:
            body = (
                exc.to_dict()
                if isinstance(exc, ManualslibOpenCLIError)
                else {
                    "schema_version": "manualslib_opencli_import.v1",
                    "status": "failed",
                    "error": {"message": str(exc)},
                }
            )
            print(json.dumps(body, ensure_ascii=False, indent=2), file=sys.stderr)
            return 2
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0 if report.status in {"preview", "completed"} else 1
    if args.manualslib_command == "import-url":
        try:
            result = import_manualslib_url(
                args.url,
                output_dir=args.output_dir,
                max_pages=args.max_pages,
                timeout_seconds=args.timeout_seconds,
            )
        except Exception as exc:  # noqa: BLE001
            print(f"manualslib import error: {type(exc).__name__}: {exc}", file=sys.stderr)
            return 2
        print(json.dumps(result.to_dict(), ensure_ascii=False, indent=2))
        return 0
    return 1


def run_knowledge_command(args) -> int:
    if args.knowledge_command == "sample-web":
        try:
            report = import_public_web(
                tuple(args.url or ()),
                output_dir=args.output_dir,
                kb_name=args.kb,
                domain=args.domain,
                doc_type=args.doc_type,
                tags=tuple(args.tag or ()),
                preview=args.preview,
                timeout_seconds=args.timeout_seconds,
            )
        except ValueError as exc:
            print(
                json.dumps(
                    {
                        "schema_version": "public_web_import.v1",
                        "status": "failed",
                        "error": {"message": str(exc)},
                    },
                    ensure_ascii=False,
                    indent=2,
                ),
                file=sys.stderr,
            )
            return 2
        print(json.dumps(report.to_dict(), ensure_ascii=False, indent=2))
        return 0 if report.status in {"preview", "completed", "partial"} else 1
    return 1
