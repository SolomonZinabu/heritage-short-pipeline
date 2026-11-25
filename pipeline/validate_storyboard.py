#!/usr/bin/env python3
"""Validate storyboard structure and basic challenge constraints."""
from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from jsonschema import Draft202012Validator

ROOT = Path(__file__).resolve().parents[1]
STORYBOARD = ROOT / "storyboard.json"
SCHEMA = ROOT / "schema" / "storyboard.schema.json"


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


def main() -> int:
    parser = argparse.ArgumentParser()
    parser.add_argument("--allow-draft", action="store_true", help="allow TODO placeholders")
    args = parser.parse_args()

    storyboard = json.loads(STORYBOARD.read_text(encoding="utf-8"))
    schema = json.loads(SCHEMA.read_text(encoding="utf-8"))
    errors = sorted(Draft202012Validator(schema).iter_errors(storyboard), key=lambda e: list(e.path))
    if errors:
        for error in errors:
            print(f"Schema error at {list(error.path)}: {error.message}", file=sys.stderr)
        return 1

    total_seconds = sum(shot["duration_seconds"] for shot in storyboard["shots"])
    if not 60 <= total_seconds <= 90:
        print(f"Total shot duration is {total_seconds:g}s; required range is 60–90s.", file=sys.stderr)
        return 1

    todos = find_todos(storyboard)
    if todos and not args.allow_draft:
        print("Storyboard still has TODO fields:", file=sys.stderr)
        for path in todos:
            print(f"  {path}", file=sys.stderr)
        print("Complete them before generation, or run make validate-draft while planning.", file=sys.stderr)
        return 1

    mode = "draft structure valid" if todos else "storyboard valid"
    print(f"{mode}; {len(storyboard['shots'])} shots; {total_seconds:g}s total.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
