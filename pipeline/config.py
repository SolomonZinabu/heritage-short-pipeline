"""Paths, private values and the default settings for every stage.

Private values come from the environment or from a ``.env`` file in the
repository root, which Git ignores. The pipeline never prints them and never
writes them anywhere.
"""
from __future__ import annotations

import copy
import os
from pathlib import Path
from typing import Any

ROOT = Path(__file__).resolve().parents[1]
STORYBOARD = ROOT / "storyboard.json"
SCHEMA = ROOT / "schema" / "storyboard.schema.json"
OUTPUTS = ROOT / "outputs"
RUNS = ROOT / "runs.jsonl"
MANIFEST = OUTPUTS / "manifest.json"
ENV_FILE = ROOT / ".env"

# Variables that must stay private. They are only ever reported as set or not set.
PRIVATE_NAMES = ("GEMINI_API_KEY", "CLOUDFLARE_ACCOUNT_ID", "CLOUDFLARE_API_TOKEN")


class MissingSetting(RuntimeError):
    """A private value the pipeline needs was not given."""


def load_env(path: Path = ENV_FILE) -> list[str]:
    """Copy the KEY=VALUE lines of ``path`` into the environment.

    A variable that is already set keeps its value. Returns the names that were
    loaded, never their values.
    """
    if not path.exists():
        return []
    loaded: list[str] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#") or "=" not in line:
            continue
        name, value = line.split("=", 1)
        name, value = name.strip(), value.strip().strip("\"'")
        if name and name not in os.environ:
            os.environ[name] = value
            loaded.append(name)
    return loaded


def private(name: str) -> str:
    """Return a private value from the environment.

    The error names the variable, never its value, so it is safe to show.
    """
    load_env()
    value = os.environ.get(name, "")
    if not value:
        raise MissingSetting(f"{name} is not set. Put it in {ENV_FILE.name}, as shown in {ENV_FILE.name}.example.")
    return value


def private_status() -> dict[str, bool]:
    """Which private variables are present. No value is read out."""
    load_env()
    return {name: bool(os.environ.get(name)) for name in PRIVATE_NAMES}


# Defaults for every stage. A storyboard overrides any of them in its
# "settings" block, so that one file still describes a run completely.
DEFAULT_SETTINGS: dict[str, Any] = {
    "retries": {"attempts": 4},
    "keyframes": {
        "model": "@cf/black-forest-labs/flux-2-klein-4b",
        "width": 1280,
        "height": 1280,
        "steps": 8,
        "send_seed": True,
        "use_references": True,
    },
    "narration": {
        "model": "gemini-3.8-flash-tts",
        "voice": "Sulafat",
        "style": "warm and unhurried storytelling",
    },
    "music": {
        "model": "acestep-v15-turbo",
        "steps": 8,
        "shift": 3.0,
    },
    "assembly": {
        "fps": 24,
        "lead_in_seconds": 0.25,
        "tail_seconds": 0.45,
        "end_card_seconds": 3.0,
        "end_card_lines": ["Made with AI"],
        "fit": "cover",
        "vertical": [1080, 1920],
        "horizontal": [1920, 1080],
        "music_gain": 0.5,
        "crf": 18,
        # Starting values for ducking from the challenge's own appendix; tune by ear.
        "duck": {"threshold": 0.02, "ratio": 6, "attack": 300, "release": 1500},
        # The loudness YouTube and most platforms normalise to.
        "loudness": {"i": -14, "tp": -1, "lra": 11},
        "subtitle_font": "",
        "end_card_font": "",
    },
}


def merge_settings(overrides: dict[str, Any] | None) -> dict[str, Any]:
    """Start from the defaults and lay the storyboard's own settings on top."""
    merged = copy.deepcopy(DEFAULT_SETTINGS)
    for stage, values in (overrides or {}).items():
        if isinstance(values, dict) and isinstance(merged.get(stage), dict):
            merged[stage].update(values)
        else:
            merged[stage] = values
    return merged
