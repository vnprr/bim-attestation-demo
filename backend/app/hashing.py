"""Deterministic fingerprints. Same input -> same hash, on any machine."""

import hashlib
import json


def canonical_json(obj) -> bytes:
    """One fixed byte representation of a JSON value: sorted keys, no whitespace."""
    return json.dumps(obj, sort_keys=True, separators=(",", ":"), ensure_ascii=False).encode()


def sha256_hex(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()
