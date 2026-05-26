from __future__ import annotations

import json
import secrets

from .config_store import ConfigAuthStore


def generate_plaintext_key(prefix: str = "tmr_live_") -> str:
    return prefix + secrets.token_urlsafe(24)


def build_api_key_config_entry(
    *,
    key_id: str,
    plaintext_key: str,
    label: str = "",
    scopes: list[str] | None = None,
    kb_allowlist: list[str] | None = None,
    rate_limit_per_minute: int | None = None,
) -> dict[str, object]:
    return {
        "id": key_id,
        "hash": ConfigAuthStore.hash_plaintext(plaintext_key),
        "label": label,
        "kb_allowlist": list(kb_allowlist or []),
        "scopes": list(scopes or ["search"]),
        "rate_limit_per_minute": rate_limit_per_minute,
    }


def generate_api_key_material(
    *,
    key_id: str,
    label: str = "",
    scopes: list[str] | None = None,
    kb_allowlist: list[str] | None = None,
    rate_limit_per_minute: int | None = None,
    prefix: str = "tmr_live_",
) -> dict[str, object]:
    plaintext_key = generate_plaintext_key(prefix)
    config_entry = build_api_key_config_entry(
        key_id=key_id,
        plaintext_key=plaintext_key,
        label=label,
        scopes=scopes,
        kb_allowlist=kb_allowlist,
        rate_limit_per_minute=rate_limit_per_minute,
    )
    return {
        "schema_version": "people_access_key_generation.v1",
        "plaintext_key": plaintext_key,
        "config_entry": config_entry,
        "config_json": json.dumps(config_entry, ensure_ascii=False, indent=2),
    }
