from __future__ import annotations

import logging
import sys
from typing import Literal

import structlog

_configured = False


def configure_logging(level: str = "INFO", format: Literal["json", "console"] | str = "json", force: bool = False) -> None:
    global _configured
    if _configured and not force:
        return
    log_level = getattr(logging, level.upper(), logging.INFO)
    processors = [
        structlog.contextvars.merge_contextvars,
        structlog.processors.add_log_level,
        structlog.processors.TimeStamper(fmt="iso", utc=True),
        structlog.processors.StackInfoRenderer(),
        structlog.processors.format_exc_info,
    ]
    renderer = (
        structlog.processors.JSONRenderer()
        if format == "json"
        else structlog.dev.ConsoleRenderer(colors=False)
    )
    structlog.configure(
        processors=processors + [renderer],
        wrapper_class=structlog.make_filtering_bound_logger(log_level),
        logger_factory=structlog.PrintLoggerFactory(),
        cache_logger_on_first_use=False,
    )
    logging.basicConfig(format="%(message)s", stream=sys.stdout, level=log_level, force=True)
    for name in ("uvicorn", "uvicorn.access", "uvicorn.error", "fastapi"):
        logger = logging.getLogger(name)
        logger.handlers = []
        logger.propagate = True
    _configured = True


def reset_logging() -> None:
    """Reset guard so tests can reconfigure."""
    global _configured
    _configured = False
