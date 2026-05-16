"""Unit tests for scripts/build_eval_baseline.py helpers (no network required)."""
from __future__ import annotations

import json
import sys
from pathlib import Path
from urllib.error import URLError

import pytest

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPTS_ROOT = REPO_ROOT / "scripts"
if str(SCRIPTS_ROOT) not in sys.path:
    sys.path.insert(0, str(SCRIPTS_ROOT))

import build_eval_baseline as bel  # noqa: E402

from tagmemorag.errors import EmbeddingError  # noqa: E402


def test_with_retry_returns_immediately_on_success():
    calls = []

    def _fn():
        calls.append(1)
        return "ok"

    out = bel._with_retry(_fn, sleep=lambda _s: None, log=lambda _msg: None)
    assert out == "ok"
    assert len(calls) == 1


def test_with_retry_recovers_after_transient_failures():
    calls: list[int] = []

    def _fn():
        calls.append(1)
        if len(calls) < 3:
            raise EmbeddingError(
                "transient", {"status_code": 503, "endpoint": "https://x/v1/embeddings"}
            )
        return "ok"

    out = bel._with_retry(
        _fn, max_attempts=5, base_backoff=0.0,
        sleep=lambda _s: None, log=lambda _msg: None,
    )
    assert out == "ok"
    assert len(calls) == 3


def test_with_retry_fails_after_max_attempts():
    calls: list[int] = []

    def _fn():
        calls.append(1)
        raise URLError("network down")

    with pytest.raises(URLError):
        bel._with_retry(
            _fn, max_attempts=4, base_backoff=0.0,
            sleep=lambda _s: None, log=lambda _msg: None,
        )
    assert len(calls) == 4


def test_with_retry_does_not_retry_hard_errors():
    """401 / 403 / 404 must bail out on the first failure (no quota waste)."""
    for status in (401, 403, 404, 422):
        calls: list[int] = []

        def _fn(_status=status):
            calls.append(1)
            raise EmbeddingError(
                "auth-failure", {"status_code": _status, "endpoint": "https://x/v1/embeddings"}
            )

        with pytest.raises(EmbeddingError):
            bel._with_retry(
                _fn, max_attempts=5, base_backoff=0.0,
                sleep=lambda _s: None, log=lambda _msg: None,
            )
        # First failure aborts retry — exactly one call observed.
        assert len(calls) == 1, f"status {status} retried unexpectedly"


def test_with_retry_does_not_swallow_non_retriable_exceptions():
    """Programming errors (ValueError / RuntimeError / etc.) propagate immediately."""
    calls: list[int] = []

    def _fn():
        calls.append(1)
        raise ValueError("not transient")

    with pytest.raises(ValueError):
        bel._with_retry(
            _fn, max_attempts=5, base_backoff=0.0,
            sleep=lambda _s: None, log=lambda _msg: None,
        )
    assert len(calls) == 1


def test_atomic_write_creates_file_and_cleans_tmp(tmp_path: Path):
    target = tmp_path / "baselines" / "siliconflow.json"
    payload = {"embedder": "siliconflow", "suites": {"coffee.jsonl": {"recall_at_k": 1.0}}}

    bel._atomic_write_json(target, payload)

    assert target.exists()
    written = json.loads(target.read_text(encoding="utf-8"))
    assert written == payload
    # No stray .tmp file left behind.
    leftovers = list(target.parent.glob("*.tmp"))
    assert leftovers == []


def test_atomic_write_does_not_leave_partial_file_on_failure(tmp_path: Path):
    """If serialization throws after tmp is created, the tmp must be cleaned up."""
    target = tmp_path / "baseline.json"

    # Inject a payload that json.dumps cannot serialize (a set).
    bad_payload = {"data": {1, 2, 3}}

    with pytest.raises(TypeError):
        bel._atomic_write_json(target, bad_payload)

    assert not target.exists()
    leftovers = list(target.parent.glob("*.tmp"))
    assert leftovers == []


def test_print_delta_table_handles_missing_old_file(tmp_path: Path, capsys):
    new_payload = {"embedder": "siliconflow", "suites": {}}
    missing = tmp_path / "missing.json"

    bel._print_delta_table(new_payload, missing)

    captured = capsys.readouterr()
    # Skip message went to stderr.
    assert "skipping delta table" in captured.err


def test_print_delta_table_outputs_per_suite_per_metric_diff(tmp_path: Path, capsys):
    old = tmp_path / "old.json"
    old.write_text(
        json.dumps({
            "embedder": "hashing",
            "suites": {
                "coffee.jsonl": {"recall_at_k": 0.5, "mrr": 0.4},
                "fault_codes.jsonl": {"recall_at_k": 1.0, "mrr": 0.9},
            },
        }),
        encoding="utf-8",
    )
    new_payload = {
        "embedder": "siliconflow",
        "suites": {
            "coffee.jsonl": {"recall_at_k": 0.8, "mrr": 0.6},
            "fault_codes.jsonl": {"recall_at_k": 0.95, "mrr": 0.95},
        },
    }

    bel._print_delta_table(new_payload, old)

    out = capsys.readouterr().out
    assert "Delta: siliconflow - hashing" in out
    assert "coffee.jsonl" in out
    assert "fault_codes.jsonl" in out
    # +0.3 (0.8 - 0.5) and -0.05 (0.95 - 1.0) should both appear.
    assert "+0.3000" in out or "+           0.3000" in out
    assert "-0.0500" in out or "-           0.0500" in out


def test_is_retriable_classifies_correctly():
    # Hard errors → not retriable
    for status in (400, 401, 403, 404, 422):
        exc = EmbeddingError("auth", {"status_code": status})
        assert bel._is_retriable(exc) is False, f"status {status} should NOT retry"

    # Transient HTTP errors → retriable
    for status in (429, 500, 502, 503, 504):
        exc = EmbeddingError("transient", {"status_code": status})
        assert bel._is_retriable(exc) is True, f"status {status} should retry"

    # EmbeddingError without status_code (network-style failure wrapped) → retriable
    assert bel._is_retriable(EmbeddingError("net", {})) is True

    # urllib network errors → retriable
    assert bel._is_retriable(URLError("dns")) is True
    assert bel._is_retriable(TimeoutError("slow")) is True

    # Programming errors → not retriable
    assert bel._is_retriable(ValueError("oops")) is False
    assert bel._is_retriable(RuntimeError("bad")) is False
