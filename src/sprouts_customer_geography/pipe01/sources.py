"""Pinned public-source byte verification."""

from __future__ import annotations

import string
from typing import Any, Mapping

from .canonical import sha256_bytes
from .errors import require


REQUIRED_SOURCE_FIELDS = {
    "source_id",
    "source_name",
    "accepted_vintage",
    "source_reference",
    "byte_sha256",
    "schema_version",
    "acquisition_state",
    "lineage",
}


def verify_pinned_source(manifest: Mapping[str, Any], source_bytes: bytes) -> dict[str, Any]:
    missing = sorted(REQUIRED_SOURCE_FIELDS - manifest.keys())
    require(not missing, "SOURCE_MANIFEST_INCOMPLETE", f"missing fields: {missing}")
    require(manifest["acquisition_state"] == "acquired", "SOURCE_NOT_ACQUIRED", "source bytes are not in acquired state")
    expected = str(manifest["byte_sha256"]).lower()
    require(len(expected) == 64 and all(char in string.hexdigits for char in expected), "SOURCE_CHECKSUM_INVALID", "expected SHA-256 is not 64 hexadecimal characters")
    actual = sha256_bytes(source_bytes)
    require(actual == expected, "SOURCE_CHECKSUM_MISMATCH", "source bytes do not match the accepted pinned checksum")
    return {**dict(manifest), "verified_byte_sha256": actual, "checksum_state": "accepted"}
