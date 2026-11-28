"""Password policy, hashing and tokens."""
import pytest

from accounts import credentials as cred


@pytest.mark.parametrize("password", ["corta", "qwerty123456", "Password1234", "aaaabbbbaaaa", "andrea@example.org",
                                      "mi-clave-andrea-1"])
def test_weak_passwords_are_refused(password):
    with pytest.raises(cred.WeakPassword):
        cred.check_policy(password, "andrea@example.org", "andrea")


def test_short_usernames_do_not_forbid_ordinary_words():
    cred.check_policy("mañana-temprano-9", "ana@example.org", "ana")
    with pytest.raises(cred.WeakPassword):
        cred.check_policy("ana", "ana@example.org", "ana")


def test_hash_and_verify():
    h = cred.hash_password("luz-de-campo-2026")
    assert h.startswith("$argon2id$") and "luz-de-campo" not in h
    assert cred.verify_password(h, "luz-de-campo-2026")
    assert not cred.verify_password(h, "otra-cosa-2026")
    assert not cred.verify_password(None, "x") and not cred.verify_password("no-es-un-hash", "x")


def test_tokens_are_random_and_stored_as_hash():
    a, b = cred.new_token(), cred.new_token()
    assert a != b and len(a) >= 40
    assert cred.token_hash(a) == cred.token_hash(a) and len(cred.token_hash(a)) == 32


def test_generated_passwords_pass_the_policy():
    for _ in range(20):
        p = cred.generate_password()
        cred.check_policy(p, "andrea@example.org", "andrea")
        assert len(p) == 24
