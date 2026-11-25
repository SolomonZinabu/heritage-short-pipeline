"""Stable cache-key helper for stage inputs.

A generation stage should hash every input that can change its output:
prompt, seed, model identifier, parameters, and referenced asset hashes.
"""
from __future__ import annotations

import hashlib
import json
from typing import Any


def cache_key(stage: str, inputs: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"stage": stage, "inputs": inputs},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()
