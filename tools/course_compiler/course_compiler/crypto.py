"""Pack crypto: Ed25519 sign/verify + AES-256-GCM instructor encryption."""

from __future__ import annotations

import base64
import hashlib
import os
from pathlib import Path

from cryptography.hazmat.primitives.ciphers.aead import AESGCM
from nacl.exceptions import BadSignatureError
from nacl.signing import SigningKey, VerifyKey

from .compat import CompatDecision, RejectionReason
from .jsonutil import dumps_canonical


def sha256_bytes(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def sha256_file(path: Path) -> str:
    h = hashlib.sha256()
    with path.open("rb") as f:
        for chunk in iter(lambda: f.read(1024 * 1024), b""):
            h.update(chunk)
    return h.hexdigest()


def _raw32(path: Path) -> bytes:
    raw = path.read_bytes()
    if len(raw) == 32:
        return raw
    return bytes.fromhex(raw.decode("utf-8").strip())


def load_signing_key(path: Path) -> SigningKey:
    return SigningKey(_raw32(path))


def load_verify_key(path: Path) -> VerifyKey:
    return VerifyKey(_raw32(path))


def load_aes_key(path: Path) -> bytes:
    return _raw32(path)


def sign_payload(signing_key: SigningKey, payload: bytes) -> dict:
    signed = signing_key.sign(payload)
    return {
        "schema_version": "1.0.0",
        "alg": "Ed25519",
        "public_key_id": "TEST_ONLY",
        "signature_b64": base64.b64encode(signed.signature).decode("ascii"),
        "signed_payload_sha256": sha256_bytes(payload),
    }


def verify_signature(verify_key: VerifyKey, payload: bytes, meta: dict) -> CompatDecision:
    if not meta or "signature_b64" not in meta:
        return CompatDecision(False, RejectionReason.MISSING_SIGNATURE, "signature metadata absent")
    if meta.get("alg") != "Ed25519":
        return CompatDecision(False, RejectionReason.BAD_SIGNATURE, "unsupported alg")
    if sha256_bytes(payload) != meta.get("signed_payload_sha256"):
        return CompatDecision(False, RejectionReason.TAMPERED_CONTENT, "payload hash mismatch")
    try:
        sig = base64.b64decode(meta["signature_b64"])
        verify_key.verify(payload, sig)
    except (BadSignatureError, Exception) as exc:
        return CompatDecision(False, RejectionReason.BAD_SIGNATURE, str(exc))
    return CompatDecision(True)


def encrypt_aes_gcm(
    key: bytes,
    plaintext: bytes,
    associated_data: bytes | None = None,
) -> tuple[bytes, bytes]:
    """Encrypt with AES-256-GCM using a fresh CSPRNG nonce every call.

    Nonces MUST NOT be derived from SOURCE_DATE_EPOCH, path, labels, or other
    reusable deterministic inputs under a given key. Ciphertext is intentionally
    non-reproducible; reproducibility applies to the instructor *plaintext*.
    """
    if len(key) != 32:
        raise ValueError("AES-256 key must be 32 bytes")
    nonce = os.urandom(12)
    ct = AESGCM(key).encrypt(nonce, plaintext, associated_data)
    return nonce, ct


def decrypt_aes_gcm(
    key: bytes, nonce: bytes, ciphertext: bytes, associated_data: bytes | None = None
) -> bytes:
    try:
        return AESGCM(key).decrypt(nonce, ciphertext, associated_data)
    except Exception as exc:
        raise ValueError("DECRYPT_FAILED") from exc


def sign_manifest_dict(signing_key: SigningKey, manifest: dict) -> tuple[bytes, dict]:
    payload = dumps_canonical(manifest).encode("utf-8")
    meta = sign_payload(signing_key, payload)
    meta["role"] = manifest.get("role")
    meta["pack_id"] = manifest.get("pack_id")
    return payload, meta


def b64(data: bytes) -> str:
    return base64.b64encode(data).decode("ascii")


def b64d(data: str) -> bytes:
    return base64.b64decode(data.encode("ascii"))
