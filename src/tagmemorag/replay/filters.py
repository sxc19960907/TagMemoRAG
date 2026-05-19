from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime, timezone


_SUPPORTED_FILTERS = {
    "intent",
    "created_after",
    "created_before",
    "cache_status",
    "rerank_vendor",
}
_CACHE_STATUSES = {"hit", "miss", "disabled"}


@dataclass(frozen=True)
class ReplayFilters:
    """Validated filter set for plan-log replay."""

    intent: str | None = None
    created_after: str | None = None
    created_before: str | None = None
    cache_status: str | None = None
    rerank_vendor: str | None = None

    def to_dict(self) -> dict[str, str]:
        out: dict[str, str] = {}
        if self.intent:
            out["intent"] = self.intent
        if self.created_after:
            out["created_after"] = self.created_after
        if self.created_before:
            out["created_before"] = self.created_before
        if self.cache_status:
            out["cache_status"] = self.cache_status
        if self.rerank_vendor:
            out["rerank_vendor"] = self.rerank_vendor
        return out


def parse_filter_args(values: list[str] | tuple[str, ...] | None) -> ReplayFilters:
    """Parse repeated `--filter key=value` arguments.

    Raises ValueError for invalid user input; CLI converts this to exit code 2.
    """
    fields: dict[str, str] = {}
    for raw in values or ():
        if "=" not in raw:
            raise ValueError(f"Invalid filter {raw!r}; expected key=value")
        key, value = raw.split("=", 1)
        key = key.strip()
        value = value.strip()
        if not key or not value:
            raise ValueError(f"Invalid filter {raw!r}; expected non-empty key and value")
        if key not in _SUPPORTED_FILTERS:
            allowed = ", ".join(sorted(_SUPPORTED_FILTERS))
            raise ValueError(f"Unsupported filter {key!r}; supported filters: {allowed}")
        if key in fields:
            raise ValueError(f"Duplicate filter {key!r}")
        fields[key] = _normalize_filter_value(key, value)
    return ReplayFilters(**fields)


def _normalize_filter_value(key: str, value: str) -> str:
    if key in {"created_after", "created_before"}:
        return _normalize_datetime(value)
    if key == "cache_status" and value not in _CACHE_STATUSES:
        allowed = ", ".join(sorted(_CACHE_STATUSES))
        raise ValueError(f"Invalid cache_status {value!r}; expected one of: {allowed}")
    return value


def _normalize_datetime(value: str) -> str:
    text = value.strip()
    if len(text) == 10 and text[4] == "-" and text[7] == "-":
        try:
            datetime.strptime(text, "%Y-%m-%d")
        except ValueError as exc:
            raise ValueError(f"Invalid date filter {value!r}") from exc
        return f"{text}T00:00:00Z"

    iso = text
    if iso.endswith("Z"):
        iso = iso[:-1] + "+00:00"
    try:
        parsed = datetime.fromisoformat(iso)
    except ValueError as exc:
        raise ValueError(f"Invalid datetime filter {value!r}") from exc
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    parsed = parsed.astimezone(timezone.utc).replace(microsecond=0)
    return parsed.strftime("%Y-%m-%dT%H:%M:%SZ")


__all__ = ["ReplayFilters", "parse_filter_args"]
