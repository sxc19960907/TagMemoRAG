from __future__ import annotations

from dataclasses import dataclass
import os
from pathlib import Path
import subprocess
import sys
import time
from typing import Literal

SCHEMA_VERSION = "browser_qa_readiness.v1"
FOCUSED_BROWSER_QA_TARGET = "tests/integration/test_browser_admin_ui.py::test_browser_manual_library_to_qa_user_flow"
FULL_BROWSER_QA_TARGET = "tests/integration/test_browser_admin_ui.py"


@dataclass(frozen=True)
class BrowserQaReadinessReport:
    status: Literal["passed", "failed", "error"]
    mode: Literal["focused", "full"]
    target: str
    command: tuple[str, ...]
    return_code: int | None
    duration_seconds: float
    error: dict[str, str] | None = None

    def to_dict(self) -> dict[str, object]:
        payload: dict[str, object] = {
            "schema_version": SCHEMA_VERSION,
            "status": self.status,
            "mode": self.mode,
            "target": self.target,
            "command": list(self.command),
            "return_code": self.return_code,
            "duration_seconds": round(self.duration_seconds, 3),
        }
        if self.error:
            payload["error"] = self.error
        return payload


def run_browser_qa_readiness(*, full: bool = False) -> BrowserQaReadinessReport:
    mode: Literal["focused", "full"] = "full" if full else "focused"
    target = FULL_BROWSER_QA_TARGET if full else FOCUSED_BROWSER_QA_TARGET
    command = (sys.executable, "-m", "pytest", target, "-q")
    env = dict(os.environ)
    env["TAGMEMORAG_RUN_BROWSER_UI"] = "1"
    started = time.monotonic()
    try:
        result = subprocess.run(command, cwd=Path.cwd(), env=env)
    except OSError as exc:
        return BrowserQaReadinessReport(
            status="error",
            mode=mode,
            target=target,
            command=command,
            return_code=None,
            duration_seconds=time.monotonic() - started,
            error={"type": type(exc).__name__, "reason": str(exc)},
        )
    status: Literal["passed", "failed"] = "passed" if result.returncode == 0 else "failed"
    return BrowserQaReadinessReport(
        status=status,
        mode=mode,
        target=target,
        command=command,
        return_code=result.returncode,
        duration_seconds=time.monotonic() - started,
    )
