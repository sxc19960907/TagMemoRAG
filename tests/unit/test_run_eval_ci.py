"""Unit tests for scripts/run_eval_ci.py helpers."""
from __future__ import annotations

import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import run_eval_ci as rec  # noqa: E402


def test_iter_gated_suites_excludes_informational_realmanuals(tmp_path: Path):
    for name in ("coffee.jsonl", "realmanuals.jsonl", "notes.txt"):
        (tmp_path / name).write_text("", encoding="utf-8")

    suites = rec._iter_gated_suites(tmp_path)

    assert [path.name for path in suites] == ["coffee.jsonl"]
