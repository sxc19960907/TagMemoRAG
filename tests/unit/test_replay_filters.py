from __future__ import annotations

import pytest

from tagmemorag.replay.filters import ReplayFilters, parse_filter_args


def test_parse_filter_args_empty():
    assert parse_filter_args(None) == ReplayFilters()
    assert parse_filter_args([]).to_dict() == {}


def test_parse_filter_args_valid_values():
    filters = parse_filter_args([
        "intent=text_answer",
        "created_after=2026-05-01",
        "created_before=2026-05-19T13:45:12Z",
        "cache_status=miss",
        "rerank_vendor=noop",
    ])

    assert filters.to_dict() == {
        "intent": "text_answer",
        "created_after": "2026-05-01T00:00:00Z",
        "created_before": "2026-05-19T13:45:12Z",
        "cache_status": "miss",
        "rerank_vendor": "noop",
    }


def test_parse_filter_args_normalizes_timezone_offsets():
    filters = parse_filter_args(["created_after=2026-05-19T21:45:12+08:00"])

    assert filters.created_after == "2026-05-19T13:45:12Z"


@pytest.mark.parametrize("raw", ["intent", "=x", "intent=", "unknown=x"])
def test_parse_filter_args_rejects_invalid_shape_or_key(raw):
    with pytest.raises(ValueError):
        parse_filter_args([raw])


def test_parse_filter_args_rejects_duplicate_key():
    with pytest.raises(ValueError, match="Duplicate"):
        parse_filter_args(["intent=text_answer", "intent=troubleshooting"])


@pytest.mark.parametrize("raw", ["created_after=2026-13-01", "created_before=not-a-date"])
def test_parse_filter_args_rejects_invalid_dates(raw):
    with pytest.raises(ValueError, match="Invalid"):
        parse_filter_args([raw])


def test_parse_filter_args_rejects_invalid_cache_status():
    with pytest.raises(ValueError, match="cache_status"):
        parse_filter_args(["cache_status=warm"])
