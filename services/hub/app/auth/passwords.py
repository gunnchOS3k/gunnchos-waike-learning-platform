"""Password hashing: Argon2id when argon2-cffi is installed; scrypt fallback otherwise.

CI and production installs argon2-cffi. Local sandboxes that cannot write native
wheels still get a strong KDF so tests can run.
"""

from __future__ import annotations

import base64
import hashlib
import hmac
import os

_ARGON2 = None
try:
    from argon2 import PasswordHasher as _PasswordHasher
    from argon2.exceptions import InvalidHashError, VerificationError, VerifyMismatchError

    _ARGON2 = _PasswordHasher(
        time_cost=2,
        memory_cost=65536,
        parallelism=2,
        hash_len=32,
        salt_len=16,
    )
except ImportError:  # pragma: no cover - exercised when wheel unavailable
    InvalidHashError = VerificationError = VerifyMismatchError = Exception  # type: ignore


def hash_password(password: str) -> str:
    if not password or len(password) < 8:
        raise ValueError("PASSWORD_TOO_SHORT")
    if _ARGON2 is not None:
        return _ARGON2.hash(password)
    salt = os.urandom(16)
    dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
    return "scrypt$" + base64.b64encode(salt).decode("ascii") + "$" + base64.b64encode(dk).decode("ascii")


def verify_password(password_hash: str, password: str) -> bool:
    if _ARGON2 is not None and not password_hash.startswith("scrypt$"):
        try:
            return _ARGON2.verify(password_hash, password)
        except (VerifyMismatchError, VerificationError, InvalidHashError):
            return False
    if not password_hash.startswith("scrypt$"):
        return False
    try:
        _, salt_b64, dk_b64 = password_hash.split("$", 2)
        salt = base64.b64decode(salt_b64.encode("ascii"))
        expected = base64.b64decode(dk_b64.encode("ascii"))
        dk = hashlib.scrypt(password.encode("utf-8"), salt=salt, n=2**14, r=8, p=1, dklen=32)
        return hmac.compare_digest(dk, expected)
    except Exception:
        return False
