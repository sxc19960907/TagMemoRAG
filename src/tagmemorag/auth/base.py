from __future__ import annotations

from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass(frozen=True)
class ApiKey:
    id: str
    label: str
    hash: str
    kb_allowlist: tuple[str, ...]
    scopes: frozenset[str]
    rate_limit_per_minute: int | None = None
    created_at: str | None = None
    last_used_at: str | None = None
    revoked: bool = False

    def allows_kb(self, kb_name: str) -> bool:
        if "admin" in self.scopes:
            return True
        if not self.kb_allowlist or self.kb_allowlist == ("*",):
            return True
        return kb_name in self.kb_allowlist

    def has_scope(self, required: str) -> bool:
        if "admin" in self.scopes:
            return True
        return required in self.scopes


class AuthStore(ABC):
    @abstractmethod
    def verify(self, plaintext_key: str) -> ApiKey | None:
        """Return the matching API key, or None."""

    @abstractmethod
    def list_keys(self) -> list[ApiKey]:
        """Return configured keys without exposing plaintext secrets."""

    def touch_usage(self, key_id: str) -> None:
        return None


def anonymous_key() -> ApiKey:
    return ApiKey(
        id="anonymous",
        label="Anonymous",
        hash="",
        kb_allowlist=("*",),
        scopes=frozenset({"admin"}),
        rate_limit_per_minute=None,
    )
