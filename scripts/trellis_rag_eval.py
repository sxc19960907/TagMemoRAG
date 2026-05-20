#!/usr/bin/env python3
"""Wrapper for the T5 QueryPlan replay CLI."""

from __future__ import annotations

import sys
from pathlib import Path

_SCRIPT_DIR = Path(__file__).resolve().parent
_SRC = _SCRIPT_DIR.parent / "src"
if str(_SRC) not in sys.path:
    sys.path.insert(0, str(_SRC))

from tagmemorag.replay.cli import main


if __name__ == "__main__":
    raise SystemExit(main())
