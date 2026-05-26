from __future__ import annotations

from tagmemorag.auth.base import ApiKey
from tagmemorag.auth.config_store import ConfigAuthStore
from tagmemorag.auth.keygen import build_api_key_config_entry, generate_api_key_material


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


def test_keygen_material_matches_config_auth_store():
    material = generate_api_key_material(
        key_id="support-a",
        label="Support A",
        scopes=["search", "rebuild"],
        kb_allowlist=["default"],
        rate_limit_per_minute=120,
        prefix="tmr_test_",
    )

    plaintext = material["plaintext_key"]
    entry = material["config_entry"]
    store = ConfigAuthStore(
        [
            ApiKey(
                entry["id"],
                entry["label"],
                entry["hash"],
                tuple(entry["kb_allowlist"]),
                frozenset(entry["scopes"]),
                rate_limit_per_minute=entry["rate_limit_per_minute"],
            )
        ]
    )

    assert plaintext.startswith("tmr_test_")
    assert store.verify(plaintext).id == "support-a"
    assert '"hash": "sha256:' in material["config_json"]


def test_build_api_key_config_entry_is_deterministic_for_plaintext():
    entry = build_api_key_config_entry(
        key_id="cs-test",
        plaintext_key="tmr_live_fixed",
        label="CS Test",
        scopes=["search"],
        kb_allowlist=["kb-a"],
        rate_limit_per_minute=10,
    )

    assert entry == {
        "id": "cs-test",
        "hash": ConfigAuthStore.hash_plaintext("tmr_live_fixed"),
        "label": "CS Test",
        "kb_allowlist": ["kb-a"],
        "scopes": ["search"],
        "rate_limit_per_minute": 10,
    }
