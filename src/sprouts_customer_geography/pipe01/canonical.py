"""Canonical JSON, digests, and content-derived identifiers."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
from typing import Any


def canonical_bytes(value: Any) -> bytes:
    return json.dumps(
        value,
        ensure_ascii=False,
        allow_nan=False,
        sort_keys=True,
        separators=(",", ":"),
    ).encode("utf-8")


def sha256_bytes(value: bytes) -> str:
    return hashlib.sha256(value).hexdigest()


def content_digest(value: Any) -> str:
    return sha256_bytes(canonical_bytes(value))


def content_id(prefix: str, value: Any) -> str:
    return f"{prefix}:sha256:{content_digest(value)}"


def file_sha256(path: Path) -> str:
    digest = hashlib.sha256()
    with path.open("rb") as handle:
        for block in iter(lambda: handle.read(1024 * 1024), b""):
            digest.update(block)
    return digest.hexdigest()


def write_json_exclusive(path: Path, value: Any) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("x", encoding="utf-8", newline="\n") as handle:
        handle.write(canonical_bytes(value).decode("utf-8"))
        handle.write("\n")
        handle.flush()
        os.fsync(handle.fileno())
