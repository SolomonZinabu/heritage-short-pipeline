#!/usr/bin/env python3
"""Validate the storyboard's structure and the challenge's constraints.

It runs as a script (``python pipeline/validate_storyboard.py``) and through
the package (``python -m pipeline validate``). Every stage calls
``load_storyboard`` before it starts, so a storyboard that is not ready never
reaches a model.
"""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
STORYBOARD = ROOT / "storyboard.json"
SCHEMA = ROOT / "schema" / "storyboard.schema.json"

FILM_SECONDS = (60, 90)


def find_todos(value: object, path: str = "$") -> list[str]:
    found: list[str] = []
    if isinstance(value, dict):
        for key, child in value.items():
            found.extend(find_todos(child, f"{path}.{key}"))
    elif isinstance(value, list):
        for index, child in enumerate(value):
            found.extend(find_todos(child, f"{path}[{index}]"))
    elif isinstance(value, str) and "TODO" in value.upper():
        found.append(path)
    return found


def end_card_seconds(storyboard: dict[str, Any]) -> float:
    return float(storyboard.get("end_card", {}).get("seconds", 0))


def semantic_errors(storyboard: dict[str, Any]) -> list[str]:
    """Rules a schema cannot state: repeated ids, a chosen score candidate that does not exist."""
    errors: list[str] = []
    for field, title in (("shots", "Shot"), ("references", "Reference")):
        ids = [item["id"] for item in storyboard.get(field, [])]
        repeated = sorted({item_id for item_id in ids if ids.count(item_id) > 1})
        if repeated:
            errors.append(f"{title} ids repeat: {', '.join(repeated)}")
    music = storyboard.get("music", {})
    candidates = int(music.get("candidates", 1))
    if "chosen_index" in music and music["chosen_index"] >= candidates:
        errors.append(f"music.chosen_index is {music['chosen_index']}, but only {candidates} candidate(s) are generated")
    return errors


def check_storyboard(storyboard: dict[str, Any], schema: dict[str, Any], *, allow_draft: bool) -> tuple[list[str], list[str], float]:
    """Return the errors, the paths of any TODO fields, and the film's length in seconds."""
    validator = Draft202012Validator(schema)
    errors = [
        f"Schema error at {list(error.path)}: {error.message}"
        for error in sorted(validator.iter_errors(storyboard), key=lambda error: list(error.path))
    ]
    errors.extend(semantic_errors(storyboard))
    total = round(sum(shot["duration_seconds"] for shot in storyboard["shots"]) + end_card_seconds(storyboard), 3)
    if not FILM_SECONDS[0] <= total <= FILM_SECONDS[1]:
        errors.append(f"The film runs {total:g}s including the end card; the required range is 60-90s.")
    todos = find_todos(storyboard)
    if todos and not allow_draft:
        errors.append("The storyboard still has TODO fields: " + ", ".join(todos))
    return errors, todos, total


def load_storyboard(allow_draft: bool = False) -> dict[str, Any]:
    """Load the storyboard, and stop with a clear message unless it is ready to be used."""
    try:
        storyboard = json.loads(STORYBOARD.read_text(encoding="utf-8"))
        schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise SystemExit(f"storyboard.json or the schema is not valid JSON: {exc}") from exc
    errors, _, _ = check_storyboard(storyboard, schema, allow_draft=allow_draft)
    if errors:
        raise SystemExit("The storyboard is not ready:\n  " + "\n  ".join(errors))
    return storyboard


def main() -> int:
    parser = argparse.ArgumentParser(description="Validate storyboard structure and basic challenge constraints.")
    parser.add_argument("--allow-draft", action="store_true", help="allow TODO placeholders")
    args = parser.parse_args()
    storyboard = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors, todos, total = check_storyboard(storyboard, schema, allow_draft=args.allow_draft)
    for error in errors:
        print(f"Error: {error}", file=sys.stderr)
    if errors:
        return 1
    mode = "draft structure valid" if todos else "storyboard valid"
    print(f"{mode}; {len(storyboard['shots'])} shots; {total:g}s including the end card.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
