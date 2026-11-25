"""Stable cache keys for stage inputs, and the manifest of what each stage made.

A generation stage hashes every input that can change its output: prompt, seed,
model identifier, parameters, and the hashes of the assets it builds on. The
hash is part of the output's file name, so an output is reused exactly while
its inputs stay the same, and a changed input makes a new file instead of
quietly replacing the old one.
"""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
from typing import Any

from .config import MANIFEST, ROOT

IMAGE_SUFFIXES = (".png", ".jpg", ".webp")


def cache_key(stage: str, inputs: dict[str, Any]) -> str:
    canonical = json.dumps(
        {"stage": stage, "inputs": inputs},
        sort_keys=True,
        separators=(",", ":"),
        ensure_ascii=False,
    ).encode("utf-8")
    return hashlib.sha256(canonical).hexdigest()


def file_hash(path: Path) -> str:
    """SHA-256 of a file's bytes.

    A stage that builds on an asset includes this, so an asset and whatever was
    made from it can never drift apart unnoticed.
    """
    digest = hashlib.sha256()
    with Path(path).open("rb") as stream:
        for block in iter(lambda: stream.read(1 << 20), b""):
            digest.update(block)
    return digest.hexdigest()


def output_path(directory: Path, label: str, key: str, suffix: str) -> Path:
    """Where a stage keeps one output: its label, the start of its key, its type."""
    return directory / f"{label}-{key[:10]}{suffix}"


def find_output(directory: Path, label: str, key: str, suffixes: str | tuple[str, ...]) -> Path | None:
    """The cached output for a key, or None.

    Several suffixes can be tried, because the image service picks the format.
    """
    if isinstance(suffixes, str):
        suffixes = (suffixes,)
    for suffix in suffixes:
        path = output_path(directory, label, key, suffix)
        if path.exists():
            return path
    return None


def relative(path: Path) -> str:
    """A path from the repository root with forward slashes, for logs and the manifest."""
    return Path(path).resolve().relative_to(ROOT).as_posix()


class Manifest:
    """What each stage last produced for each label, kept in ``outputs/manifest.json``.

    It lets the edit, and anyone reading the repository, see which file belongs
    to which shot and from which inputs, without running anything.
    """

    def __init__(self, path: Path = MANIFEST) -> None:
        self.path = path
        self.data: dict[str, dict[str, dict[str, Any]]] = {}
        if path.exists():
            self.data = json.loads(path.read_text(encoding="utf-8"))

    def get(self, stage: str, label: str) -> dict[str, Any] | None:
        return self.data.get(stage, {}).get(label)

    def record(self, stage: str, label: str, entry: dict[str, Any]) -> None:
        """Remember one output. The path is stored relative to the repository, so the manifest can travel with it."""
        self.data.setdefault(stage, {})[label] = {**entry, "file": relative(Path(entry["file"]))}

    def save(self) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        ordered = {stage: dict(sorted(items.items())) for stage, items in sorted(self.data.items())}
        self.path.write_text(json.dumps(ordered, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
