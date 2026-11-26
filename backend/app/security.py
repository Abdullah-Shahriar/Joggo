import hashlib
import secrets
from typing import Final

from argon2 import PasswordHasher, Type
from argon2.exceptions import InvalidHashError, VerifyMismatchError

_password_hasher: Final[PasswordHasher] = PasswordHasher(
    time_cost=2,
    memory_cost=65536,
    parallelism=1,
    hash_len=32,
    salt_len=16,
    type=Type.ID,
)

# Precomputed valid argon2id hash used to equalize timing on unknown-email logins (rules.md S8).
DUMMY_PASSWORD_HASH: Final[str] = _password_hasher.hash("DummyPasswordForTiming123")


def hash_password(password: str) -> str:
    return _password_hasher.hash(password)


def verify_password(password_hash: str, password: str) -> bool:
    try:
        return _password_hasher.verify(password_hash, password)
    except (VerifyMismatchError, InvalidHashError):
        return False


def validate_password_strength(password: str) -> bool:
    """Rules.md S1: min length 10, at least one letter and one digit."""
    if len(password) < 10:
        return False
    has_letter = any(ch.isalpha() for ch in password)
    has_digit = any(ch.isdigit() for ch in password)
    return has_letter and has_digit


def generate_refresh_token() -> str:
    """Rules.md S2: random 256-bit value."""
    return secrets.token_urlsafe(32)


def sha256_hex(value: str) -> str:
    return hashlib.sha256(value.encode("utf-8")).hexdigest()
