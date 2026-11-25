"""Small helpers shared by every stage."""
from __future__ import annotations

import re
from typing import Any


def say(message: str) -> None:
    """Print progress at once, so a long run shows what it is doing."""
    print(message, flush=True)


def select_shots(shots: list[dict[str, Any]], only: str | None) -> list[dict[str, Any]]:
    """All shots, or the ones named in a comma-separated list such as "shot_03,shot_07"."""
    if not only:
        return list(shots)
    wanted = [name.strip() for name in only.split(",") if name.strip()]
    known = {shot["id"] for shot in shots}
    unknown = [name for name in wanted if name not in known]
    if unknown:
        raise SystemExit(f"No such shot: {', '.join(unknown)}. The shots are: {', '.join(sorted(known))}")
    return [shot for shot in shots if shot["id"] in wanted]


def slugify(text: str, fallback: str = "heritage-short") -> str:
    """Turn a title into a safe file-name part. A title with no Latin letters uses the fallback."""
    words = re.findall(r"[a-z0-9]+", text.lower())
    return "-".join(words)[:48] or fallback
