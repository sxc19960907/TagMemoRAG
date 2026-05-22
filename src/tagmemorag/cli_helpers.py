from __future__ import annotations

import argparse
from pathlib import Path

from .manual_bulk_import import BulkUploadedFile


def add_bulk_args(parser: argparse.ArgumentParser, *, include_import_args: bool) -> None:
    parser.add_argument("--kb", default="default")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--metadata", required=True, help="Path to JSON, JSONL, or CSV metadata.")
    parser.add_argument("--metadata-format", choices=["json", "jsonl", "csv"], default="csv")
    parser.add_argument("--file", action="append", default=[], help="Manual source document path. Repeat for many files.")
    parser.add_argument("--mode", choices=["create_only", "upsert", "dry_run"], default="create_only")
    parser.add_argument("--overwrite", action="store_true")
    if include_import_args:
        parser.add_argument("--selected-row", action="append", type=int, default=[])


def add_tag_rewrite_args(parser: argparse.ArgumentParser, *, include_commit_args: bool) -> None:
    parser.add_argument("--kb", default="default")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--source-tag", action="append", required=True)
    parser.add_argument("--target-tag", required=True)
    parser.add_argument("--mode", choices=["merge", "rename"], default="merge")
    if include_commit_args:
        parser.add_argument("--update-policy", action="store_true")
        parser.add_argument("--policy-alias-mode", choices=["synonym", "deprecated"], default=None)


def add_feedback_promote_args(parser: argparse.ArgumentParser) -> None:
    parser.add_argument("--kb", default="default")
    parser.add_argument("--config", default="config.yaml")
    parser.add_argument("--feedback-id", action="append", required=True)
    parser.add_argument("--output", default=None)


def read_text_file(path: str) -> str:
    return Path(path).read_text(encoding="utf-8")


def split_csv(value: str) -> list[str]:
    return [item.strip() for item in value.split(",") if item.strip()]


def read_bulk_files(paths: list[str]) -> list[BulkUploadedFile]:
    return [BulkUploadedFile(filename=Path(path).name, content=Path(path).read_bytes()) for path in paths]
