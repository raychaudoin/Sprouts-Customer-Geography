"""Disclosure-safe commitment for a protected freeze manifest."""

from __future__ import annotations

import hashlib
import secrets

DOMAIN_SEPARATOR = b"sprouts-customer-geography/pipe01/freeze-commitment/v1"


def new_nonce() -> bytes:
    return secrets.token_bytes(32)


def freeze_commitment(protected_manifest_digest_hex: str, nonce: bytes) -> str:
    if len(nonce) < 32:
        raise ValueError("freeze-event nonce must contain at least 256 random bits")
    digest = bytes.fromhex(protected_manifest_digest_hex)
    if len(digest) != 32:
        raise ValueError("protected freeze-manifest digest must be a SHA-256 digest")
    payload = DOMAIN_SEPARATOR + b"\x00" + nonce + b"\x00" + digest
    return hashlib.sha256(payload).hexdigest()
