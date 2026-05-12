from __future__ import annotations

from collections.abc import Iterable
from datetime import datetime, timezone
import hashlib
import hmac

from tagmemorag.config import AuthConfig

from .base import ApiKey, AuthStore


class ConfigAuthStore(AuthStore):
    def __init__(self, keys: Iterable[ApiKey]):
        self._keys = list(keys)

    @classmethod
    def from_config(cls, config: AuthConfig) -> "ConfigAuthStore":
        keys = [
            ApiKey(
                id=item.id,
                label=item.label,
                hash=item.hash,
                kb_allowlist=tuple(item.kb_allowlist),
                scopes=frozenset(item.scopes),
                rate_limit_per_minute=item.rate_limit_per_minute,
                created_at=item.created_at,
                revoked=item.revoked,
            )
            for item in config.keys
        ]
        return cls(keys)

    @staticmethod
    def hash_plaintext(plaintext_key: str) -> str:
        return "sha256:" + hashlib.sha256(plaintext_key.encode("utf-8")).hexdigest()

    def verify(self, plaintext_key: str) -> ApiKey | None:
        computed = self.hash_plaintext(plaintext_key)
        matched: ApiKey | None = None
        for api_key in self._keys:
            if hmac.compare_digest(computed, api_key.hash):
                matched = api_key
        return matched

    def list_keys(self) -> list[ApiKey]:
        return list(self._keys)

    def touch_usage(self, key_id: str) -> None:
        now = datetime.now(timezone.utc).isoformat()
        self._keys = [
            ApiKey(
                id=key.id,
                label=key.label,
                hash=key.hash,
                kb_allowlist=key.kb_allowlist,
                scopes=key.scopes,
                rate_limit_per_minute=key.rate_limit_per_minute,
                created_at=key.created_at,
                last_used_at=now if key.id == key_id else key.last_used_at,
                revoked=key.revoked,
            )
            for key in self._keys
        ]
