"""Passwords and tokens.

- Passwords: argon2id (argon2-cffi defaults), at least 12 characters, not one of the common passwords, and neither the
  email nor the username.
- Session and invitation tokens: 32 random bytes; the database keeps only their SHA-256, so a leaked table cannot be
  used to sign in. A fast hash is enough here because the tokens are random, unlike passwords.
"""
from __future__ import annotations

import hashlib
import secrets as _secrets

from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

MIN_LENGTH = 12
_hasher = PasswordHasher()

# The most common passwords of public breach lists, plus local ones; any of them, whatever the case, is refused.
COMMON = {
    "123456789012", "1234567890123", "qwertyuiopas", "password1234", "passwordpassword", "contraseña123",
    "contrasena123", "contraseña1234", "administrador", "admin1234567", "adminadmin123", "iloveyou1234",
    "qwerty123456", "abc123456789", "111111111111", "000000000000", "123123123123", "letmein12345",
    "welcome12345", "bienvenido123", "peru12345678", "lima12345678", "arandano1234", "senasa123456",
}


class WeakPassword(ValueError):
    pass


def check_policy(password: str, email: str | None = None, username: str | None = None) -> None:
    if len(password) < MIN_LENGTH:
        raise WeakPassword(f"La contraseña debe tener al menos {MIN_LENGTH} caracteres")
    lowered = password.lower()
    if lowered in COMMON or len(set(lowered)) < 4:
        raise WeakPassword("La contraseña es demasiado común o repetitiva")
    if email and lowered == email.lower():
        raise WeakPassword("La contraseña no puede ser el correo")
    # a short username ("ana") would forbid ordinary words ("mañana"); from four characters on it may not appear
    if username and (lowered == username.lower() or (len(username) >= 4 and username.lower() in lowered)):
        raise WeakPassword("La contraseña no puede contener el nombre de usuario")


def hash_password(password: str) -> str:
    return _hasher.hash(password)


def verify_password(stored: str | None, password: str) -> bool:
    if not stored:
        return False
    try:
        return _hasher.verify(stored, password)
    except (VerifyMismatchError, VerificationError, InvalidHashError):
        return False


def needs_rehash(stored: str) -> bool:
    return _hasher.check_needs_rehash(stored)


def new_token() -> str:
    return _secrets.token_urlsafe(32)


def token_hash(token: str) -> bytes:
    return hashlib.sha256(token.encode("utf-8")).digest()


def generate_password(length: int = 24) -> str:
    """For the first admin: random letters, digits and a few symbols that survive copy and paste."""
    alphabet = "ABCDEFGHJKLMNPQRSTUVWXYZabcdefghijkmnopqrstuvwxyz23456789-_.!"
    while True:
        candidate = "".join(_secrets.choice(alphabet) for _ in range(length))
        if any(c.isdigit() for c in candidate) and any(c.isupper() for c in candidate):
            return candidate


# a hash to verify against when the email does not exist, so a wrong email takes as long as a wrong password
DUMMY_HASH = _hasher.hash(new_token())
