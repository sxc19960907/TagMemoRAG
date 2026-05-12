from __future__ import annotations

from tagmemorag.auth.base import ApiKey
from tagmemorag.auth.config_store import ConfigAuthStore


def test_config_auth_store_verify_success_failure_and_revoked():
    good_secret = "tmr_live_good"
    revoked_secret = "tmr_live_revoked"
    store = ConfigAuthStore(
        [
            ApiKey("good", "Good", ConfigAuthStore.hash_plaintext(good_secret), ("kb-a",), frozenset({"search"})),
            ApiKey(
                "revoked",
                "Revoked",
                ConfigAuthStore.hash_plaintext(revoked_secret),
                ("*",),
                frozenset({"search"}),
                revoked=True,
            ),
        ]
    )

    assert store.verify(good_secret).id == "good"
    assert store.verify("bad") is None
    assert store.verify(revoked_secret).revoked is True


def test_api_key_scope_and_kb_rules():
    scoped = ApiKey("cs", "", "sha256:x", ("kb-a",), frozenset({"search"}))
    wildcard = ApiKey("ops", "", "sha256:y", ("*",), frozenset({"rebuild"}))
    empty_allows_all = ApiKey("all", "", "sha256:z", (), frozenset({"search"}))
    admin = ApiKey("admin", "", "sha256:a", ("kb-a",), frozenset({"admin"}))

    assert scoped.allows_kb("kb-a")
    assert not scoped.allows_kb("kb-b")
    assert scoped.has_scope("search")
    assert not scoped.has_scope("rebuild")
    assert wildcard.allows_kb("kb-any")
    assert empty_allows_all.allows_kb("kb-any")
    assert admin.allows_kb("kb-b")
    assert admin.has_scope("anchor.write")
