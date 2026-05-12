from __future__ import annotations

import json
import logging

import pytest
import structlog
from structlog.contextvars import bind_contextvars, clear_contextvars

from tagmemorag.logging_setup import configure_logging, reset_logging


@pytest.fixture(autouse=True)
def _reset_logging():
    reset_logging()
    yield
    reset_logging()


def test_configure_logging_json_format(capsys):
    configure_logging("INFO", "json")

    structlog.get_logger().info("hello")
    body = json.loads(capsys.readouterr().out)

    assert body["event"] == "hello"
    assert body["level"] == "info"
    assert "timestamp" in body


def test_contextvars_propagate(capsys):
    configure_logging("INFO", "json")
    clear_contextvars()
    bind_contextvars(trace_id="trace-123")

    structlog.get_logger().info("with_trace")
    body = json.loads(capsys.readouterr().out)

    assert body["trace_id"] == "trace-123"
    clear_contextvars()


def test_uvicorn_bridge(capsys):
    configure_logging("INFO", "json")

    logging.getLogger("uvicorn").info("server ready")

    assert "server ready" in capsys.readouterr().out


def test_configure_logging_is_idempotent(capsys):
    configure_logging("INFO", "json")
    structlog.get_logger().info("first")
    out1 = capsys.readouterr().out
    assert out1.count("\n") == 1  # one JSON line

    # Second call with different format — should be ignored (guarded)
    configure_logging("DEBUG", "console")
    structlog.get_logger().info("second")
    out2 = capsys.readouterr().out
    # Still JSON because first config wins
    body = json.loads(out2)
    assert body["event"] == "second"


def test_configure_logging_force_reconfigures(capsys):
    configure_logging("INFO", "json")
    capsys.readouterr()  # drain

    configure_logging("INFO", "console", force=True)
    structlog.get_logger().info("after_force")
    out = capsys.readouterr().out
    # ConsoleRenderer, not JSON
    with pytest.raises(json.JSONDecodeError):
        json.loads(out)
